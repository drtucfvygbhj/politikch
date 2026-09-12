#!/usr/bin/env python3
"""Fetch the latest federal votes and pending popular initiatives.

Writes data/initiatives.json from two official, machine-readable sources — no
invented figures, exactly like scripts/fetch_financing.py:

1. VoteInfo (Federal Chancellery + Federal Statistical Office) — the official
   real-time/results dataset for every federal voting day. Published as open
   data on opendata.swiss (dataset
   "echtzeitdaten-am-abstimmungstag-zu-eidgenoessischen-abstimmungsvorlagen"),
   with per-voting-day JSON on ogd-static.voteinfo-app.ch / bfs.admin.ch. Gives
   us the most recent *decided* federal votes (initiatives and referendums),
   with official results and multilingual titles.

2. LINDAS linked-data cube "Eidgenössische Volksinitiativen" of the Federal
   Chancellery (https://politics.ld.admin.ch/political-rights/popular-initiative),
   queried over the public SPARQL endpoint (cached.lindas.admin.ch). This is the
   authoritative register of every popular initiative and its current stage, so
   it gives us the initiatives that are *still gathering signatures*
   ("Im Sammelstadium") and those that have qualified and are pending a vote.

Both are the same public, unauthenticated open-data endpoints the Chancellery's
own web apps use; this is a build-time fetch (run in CI or locally) that writes
a same-origin JSON file the static site loads like any other data file.

Usage:
  python3 scripts/fetch_initiatives.py

Design notes:
  * Titles come straight from the official sources. VoteInfo carries DE/FR/IT/EN;
    the initiative cube carries DE/FR/IT, so the English title for a
    still-pending initiative keeps the official name (a proper noun) in its
    original language, framed in English ("Federal popular initiative «…»").
  * Descriptions are composed from official structured fields (result, turnout,
    stage, dates) — factual and sourced, never editorial spin.
  * On any failure the existing data/initiatives.json is left untouched, so the
    site never falls back to a blank or invented list.
"""
import json
import csv
import io
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = (
    "Politikch-data-fetcher/1.0 "
    "(non-commercial civic-education site; contact via github.com/politikch)"
)

CKAN_PACKAGE = (
    "https://ckan.opendata.swiss/api/3/action/package_show"
    "?id=echtzeitdaten-am-abstimmungstag-zu-eidgenoessischen-abstimmungsvorlagen"
)
LINDAS_ENDPOINT = "https://cached.lindas.admin.ch/query"
INITIATIVE_CUBE = "https://politics.ld.admin.ch/political-rights/popular-initiative/1"
# Federal Chancellery cube of every popular vote — includes ballots that are
# already scheduled but not yet held, which is how we surface upcoming votes
# (VoteInfo only publishes a voting day once it is imminent/past).
POPULAR_VOTE_CUBE = "https://politics.ld.admin.ch/political-rights/popular-vote/1"

# Swissvotes — the academic database of Swiss popular votes (Année Politique
# Suisse, Uni Bern). Its open dataset (CC BY-NC-SA) carries each party's official
# voting recommendation (Parole) per ballot, which no federal source publishes.
# Used only to annotate votes with party recommendations and to fill the English
# short title for upcoming ballots (LINDAS has no English there).
SWISSVOTES_CSV = "https://swissvotes.ch/page/dataset/swissvotes_dataset.csv"
# Site party key -> Swissvotes recommendation column.
SWISSVOTES_PARTY_COLS = {
    "SVP": "p-svp", "SP": "p-sps", "MITTE": "p-mitte", "FDP": "p-fdp",
    "GPS": "p-gps", "GLP": "p-glp", "EVP": "p-evp", "EDU": "p-edu",
    "LEGA": "p-lega", "MCG": "p-mcg",
}
# Swissvotes recommendation codes we surface (others = no/unknown Parole).
SWISSVOTES_REC = {"1": "yes", "2": "no", "3": "free"}

# Only include federal voting days from this date onward. The transparency era
# (and the site's financing data) starts in 2023; two-plus years of votes keeps
# the list current and useful without turning it into a full archive.
VOTES_SINCE = "20230101"

# Ballot items are classified from the official German title, which is the
# reliable signal: a popular initiative's title always starts with
# "Volksinitiative …", whereas laws, counter-proposals and mandatory referendums
# start with "Bundesgesetz"/"Bundesbeschluss"/"Änderung …". The tie-break
# question ("Stichfrage") between an initiative and its counter-proposal is not a
# standalone item and is skipped.

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "de": ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
           "August", "September", "Oktober", "November", "Dezember"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
           "agosto", "settembre", "ottobre", "novembre", "dicembre"],
    "rm": ["schaner", "favrer", "mars", "avrigl", "matg", "zercladur", "fanadur",
           "avust", "settember", "october", "november", "december"],
}
LANGS = ("en", "de", "fr", "it")
# Date/outcome strings are also composed in Romansh (rm). Titles/descriptions
# stay DE/FR/IT/EN — Romansh titles are the site's separate unofficial-translation
# files. A date/outcome needs no such disclaimer, so it is a plain translation.
DATE_LANGS = LANGS + ("rm",)

# Popular-initiative cube phases (by stable IRI code) that we surface, mapped to
# the site's status enum plus a short multilingual stage label. Voted outcomes
# (angenommen/abgelehnt) are intentionally absent here — those come from
# VoteInfo with official results. "bedingter_rueckzug" (conditional withdrawal)
# is deliberately omitted.
PHASES = {
    "im_sammelstadium": {
        "status": "collecting",
        "stage": {"en": "signature gathering", "de": "im Sammelstadium",
                  "fr": "récolte des signatures", "it": "raccolta firme"},
    },
    "in_auszaehlung": {
        "status": "pending",
        "stage": {"en": "signatures being verified", "de": "in Auszählung",
                  "fr": "décompte des signatures", "it": "conteggio delle firme"},
    },
    "beim_bundesrat_haengig": {
        "status": "pending",
        "stage": {"en": "pending before the Federal Council",
                  "de": "beim Bundesrat hängig",
                  "fr": "pendante devant le Conseil fédéral",
                  "it": "pendente davanti al Consiglio federale"},
    },
    "beim_parlament_haengig": {
        "status": "pending",
        "stage": {"en": "pending before Parliament", "de": "beim Parlament hängig",
                  "fr": "pendante devant le Parlement",
                  "it": "pendente davanti al Parlamento"},
    },
    "abstimmungsreif": {
        "status": "pending",
        "stage": {"en": "ready to be put to a vote", "de": "abstimmungsreif",
                  "fr": "prête pour la votation", "it": "pronta per la votazione"},
    },
}

# Localized Chancellery "pending popular initiatives" page (one per language).
PENDING_PAGE = {
    "en": "https://www.bk.admin.ch/de/haengige-volksinitiativen",
    "de": "https://www.bk.admin.ch/de/haengige-volksinitiativen",
    "fr": "https://www.bk.admin.ch/fr/initiatives-en-suspens",
    "it": "https://www.bk.admin.ch/it/iniziative-in-sospeso",
}


def http_get(url, retries=6):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001 — transient proxy/network errors
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def fetch_json(url, retries=6):
    return json.loads(http_get(url, retries=retries))


def sparql(query, retries=6):
    url = LINDAS_ENDPOINT + "?" + urllib.parse.urlencode({"query": query})
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/sparql-results+json"}
    )
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read())["results"]["bindings"]
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def fmt_date(iso, lang, prefix_voted, prefix_future=None, today=None):
    """iso: 'YYYYMMDD' or 'YYYY-MM-DD' -> localized 'Voted 3 March 2024'."""
    digits = re.sub(r"\D", "", iso)
    y, m, d = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
    month = MONTHS[lang][m - 1]
    if lang == "de":
        body = f"{d}. {month} {y}"
    elif lang == "rm":
        body = f"{d} da {month} {y}"
    else:
        body = f"{d} {month} {y}"
    prefix = prefix_voted
    if prefix_future and today is not None and digits > today:
        prefix = prefix_future
    return f"{prefix} {body}".strip()


VOTED_PREFIX = {
    "en": ("Voted", "Vote on"), "de": ("Abstimmung", "Abstimmung am"),
    "fr": ("Votation du", "Votation du"), "it": ("Votazione del", "Votazione del"),
    "rm": ("Votaziun ils", "Votaziun federala ils"),
}
SINCE_PREFIX = {
    "en": "Signature gathering since", "de": "Unterschriftensammlung seit",
    "fr": "Récolte des signatures depuis", "it": "Raccolta firme dal",
    "rm": "Rimnada da signaturas dapi ils",
}
LAUNCHED_PREFIX = {
    "en": "Launched", "de": "Lanciert am",
    "fr": "Lancée le", "it": "Lanciata il", "rm": "Lantschada ils",
}
UPCOMING_PREFIX = {
    "en": "Federal vote on", "de": "Abstimmung am",
    "fr": "Votation du", "it": "Votazione del", "rm": "Votaziun federala ils",
}


def add_months(iso_date, months):
    y, m, d = (int(x) for x in iso_date.split("-"))
    m0 = m - 1 + months
    y += m0 // 12
    m = m0 % 12 + 1
    # clamp day (18 months keeps the day; no month-length edge case for 18)
    return f"{y:04d}-{m:02d}-{d:02d}"


# ----------------------------------------------------------------------------
# Source 1: VoteInfo — recent decided federal votes
# ----------------------------------------------------------------------------

def de_title(vorlage):
    for tt in vorlage["vorlagenTitel"]:
        if tt["langKey"] == "de":
            return tt["text"]
    return vorlage["vorlagenTitel"][0]["text"]


def titles_from_voteinfo(vorlage):
    by_lang = {tt["langKey"]: tt["text"] for tt in vorlage["vorlagenTitel"]}
    out = {}
    for lang in LANGS:
        out[lang] = by_lang.get(lang) or by_lang.get("de") or ""
    return out


def compose_vote_desc(vorlage, is_initiative, today):
    res = vorlage.get("resultat") or {}
    beendet = vorlage.get("vorlageBeendet")
    ang = vorlage.get("vorlageAngenommen")
    yes = res.get("jaStimmenInProzent")
    turnout = res.get("stimmbeteiligungInProzent")
    kind = {
        "en": "popular initiative" if is_initiative else "referendum",
        "de": "Volksinitiative" if is_initiative else "Referendumsvorlage",
        "fr": "initiative populaire" if is_initiative else "objet soumis au référendum",
        "it": "iniziativa popolare" if is_initiative else "oggetto in referendum",
    }
    desc = {}
    if beendet and yes is not None:
        y = f"{yes:.1f}".replace(".", ",")
        t = f"{turnout:.1f}".replace(".", ",") if turnout is not None else None
        yd = f"{yes:.1f}"
        td = f"{turnout:.1f}" if turnout is not None else None
        if ang:
            desc["en"] = (f"A federal {kind['en']} approved by voters with "
                          f"{yd}% voting yes"
                          + (f" (turnout {td}%)." if td else "."))
            desc["de"] = (f"Eine eidgenössische {kind['de']}, vom Volk mit "
                          f"{y}% Ja angenommen"
                          + (f" (Stimmbeteiligung {t}%)." if t else "."))
            desc["fr"] = (f"Une {kind['fr']} fédérale acceptée par le peuple avec "
                          f"{y}% de oui"
                          + (f" (participation {t}%)." if t else "."))
            desc["it"] = (f"Un'{kind['it']} federale accettata dal popolo con "
                          f"il {y}% di sì"
                          + (f" (partecipazione {t}%)." if t else "."))
        else:
            no = f"{100 - yes:.1f}".replace(".", ",")
            nod = f"{100 - yes:.1f}"
            desc["en"] = (f"A federal {kind['en']} rejected by voters, with "
                          f"{nod}% voting no"
                          + (f" (turnout {td}%)." if td else "."))
            desc["de"] = (f"Eine eidgenössische {kind['de']}, vom Volk mit "
                          f"{no}% Nein abgelehnt"
                          + (f" (Stimmbeteiligung {t}%)." if t else "."))
            desc["fr"] = (f"Une {kind['fr']} fédérale rejetée par le peuple, avec "
                          f"{no}% de non"
                          + (f" (participation {t}%)." if t else "."))
            desc["it"] = (f"Un'{kind['it']} federale respinta dal popolo, con "
                          f"il {no}% di no"
                          + (f" (partecipazione {t}%)." if t else "."))
    else:
        desc["en"] = f"A federal {kind['en']} scheduled for a nationwide vote."
        desc["de"] = f"Eine eidgenössische {kind['de']}, die zur Abstimmung kommt."
        desc["fr"] = f"Une {kind['fr']} fédérale soumise à la votation."
        desc["it"] = f"Un'{kind['it']} federale sottoposta alla votazione."
    return desc


def compose_outcome(vorlage):
    res = vorlage.get("resultat") or {}
    if not vorlage.get("vorlageBeendet") or res.get("jaStimmenInProzent") is None:
        return None
    yes = res["jaStimmenInProzent"]
    ang = vorlage.get("vorlageAngenommen")
    y_en = f"{yes:.1f}"
    n_en = f"{100 - yes:.1f}"
    y_x = y_en.replace(".", ",")
    n_x = n_en.replace(".", ",")
    if ang:
        return {
            "en": f"Adopted ({y_en}% yes)", "de": f"Angenommen ({y_x}% Ja)",
            "fr": f"Acceptée ({y_x}% oui)", "it": f"Accettata ({y_x}% sì)",
            "rm": f"Acceptada ({y_x}% gea)",
        }
    return {
        "en": f"Rejected ({n_en}% no)", "de": f"Abgelehnt ({n_x}% Nein)",
        "fr": f"Rejetée ({n_x}% non)", "it": f"Respinta ({n_x}% no)",
        "rm": f"Refusada ({n_x}% na)",
    }


def fetch_votes(today):
    print("Fetching VoteInfo dataset (recent federal votes)...")
    pkg = fetch_json(CKAN_PACKAGE)["result"]
    dated = []
    for r in pkg["resources"]:
        title = (r.get("title") or {}).get("de") or r.get("name", "")
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", title)
        if m:
            iso = f"{m.group(3)}{m.group(2)}{m.group(1)}"
        else:
            m2 = re.search(r"-(\d{8})-", r["url"])
            if not m2:
                continue
            iso = m2.group(1)
        if iso >= VOTES_SINCE:
            dated.append((iso, r["url"]))
    dated.sort(key=lambda x: x[0], reverse=True)
    print(f"  {len(dated)} voting days since {VOTES_SINCE}")

    items = []
    for iso, url in dated:
        try:
            day = fetch_json(url)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {iso}: fetch failed: {e}", file=sys.stderr)
            continue
        for vorlage in day["schweiz"]["vorlagen"]:
            title_de = de_title(vorlage)
            low = title_de.strip().lower()
            if "stichfrage" in low or vorlage.get("vorlagenArtId") == 6:
                continue
            is_init = low.startswith("volksinitiative")
            beendet = vorlage.get("vorlageBeendet")
            ang = vorlage.get("vorlageAngenommen")
            status = "pending"
            if beendet and (vorlage.get("resultat") or {}).get("jaStimmenInProzent") is not None:
                status = "adopted" if ang else "rejected"
            items.append({
                "id": f"vote-{iso}-{vorlage['vorlagenId']}",
                "type": "initiative" if is_init else "referendum",
                "title": titles_from_voteinfo(vorlage),
                "desc": compose_vote_desc(vorlage, is_init, today),
                "status": status,
                "date": {lang: fmt_date(iso, lang, VOTED_PREFIX[lang][0],
                                        VOTED_PREFIX[lang][1], today) for lang in DATE_LANGS},
                "outcome": compose_outcome(vorlage),
                "url": f"https://www.bk.admin.ch/ch/d/pore/va/{iso}/index.html",
                "_sort": iso,
                "_voteTitleDe": de_title(vorlage),
                "_voteDateIso": f"{iso[0:4]}-{iso[4:6]}-{iso[6:8]}",
            })
    print(f"  {len(items)} federal ballot items")
    return items


# ----------------------------------------------------------------------------
# Source 2: LINDAS popular-initiative cube — signature-gathering & pending
# ----------------------------------------------------------------------------

def english_from_name(de_name, is_initiative=True):
    """Fallback English title framed around the official (untranslated) name.

    Used only when no source provides an English title. Initiatives get an
    English frame around their quoted proper-noun name; referendums (laws,
    decrees) keep their official German title verbatim rather than being
    mislabelled as an initiative.
    """
    if not is_initiative:
        return de_name
    m = re.search(r"[«'\"’]\s*(.+?)\s*[»'\"’]\s*$", de_name)
    core = m.group(1) if m else re.sub(r"^Eidgenössische Volksinitiative\s*", "", de_name)
    return f"Federal popular initiative «{core}»"


def fetch_pending():
    print("Fetching LINDAS popular-initiative cube (pending & collecting)...")
    # Build a VALUES list of the phase IRIs we accept.
    phase_values = " ".join(
        f"<https://politics.ld.admin.ch/political-rights/popular-initiative/phase/{c}>"
        for c in PHASES
    )
    query = f"""
PREFIX cube: <https://cube.link/>
PREFIX schema: <http://schema.org/>
PREFIX pr: <https://politics.ld.admin.ch/political-rights/popular-initiative/>
SELECT ?id ?beginn ?phaseCode ?de ?fr ?it WHERE {{
  <{INITIATIVE_CUBE}> cube:observationSet/cube:observation ?obs .
  ?obs pr:id ?id ; pr:sammelbeginn ?beginn ; pr:titel ?titel ; pr:phase ?phase .
  VALUES ?phase {{ {phase_values} }}
  BIND(REPLACE(STR(?phase), "^.*/", "") AS ?phaseCode)
  ?titel schema:name ?de . FILTER(LANG(?de)="de")
  OPTIONAL {{ ?titel schema:name ?fr . FILTER(LANG(?fr)="fr") }}
  OPTIONAL {{ ?titel schema:name ?it . FILTER(LANG(?it)="it") }}
}} ORDER BY DESC(?beginn)
"""
    rows = sparql(query)
    items = []
    seen = set()
    for b in rows:
        g = lambda k: b.get(k, {}).get("value")
        iid = g("id")
        if iid in seen:  # a cube observation can repeat across dimensions
            continue
        seen.add(iid)
        code = g("phaseCode")
        phase = PHASES.get(code)
        if not phase:
            continue
        beginn = g("beginn")  # YYYY-MM-DD
        de = g("de") or ""
        fr = g("fr") or de
        it = g("it") or de
        title = {"en": english_from_name(de), "de": de, "fr": fr, "it": it}
        stage = phase["stage"]
        status = phase["status"]
        deadline = add_months(beginn, 18)
        desc = {}
        if status == "collecting":
            desc["en"] = (f"Popular initiative in the signature-gathering stage. It "
                          f"has until {fmt_date(deadline, 'en', '')} to collect "
                          f"100,000 valid signatures and force a nationwide vote.")
            desc["de"] = (f"Volksinitiative im Sammelstadium. Bis "
                          f"{fmt_date(deadline, 'de', '')} müssen 100 000 gültige "
                          f"Unterschriften zusammenkommen, damit es zur Abstimmung kommt.")
            desc["fr"] = (f"Initiative populaire au stade de la récolte des signatures. "
                          f"Elle a jusqu'au {fmt_date(deadline, 'fr', '')} pour réunir "
                          f"100 000 signatures valables et provoquer une votation.")
            desc["it"] = (f"Iniziativa popolare nella fase di raccolta firme. Ha tempo "
                          f"fino al {fmt_date(deadline, 'it', '')} per raccogliere "
                          f"100 000 firme valide e arrivare alla votazione.")
        else:
            desc["en"] = (f"Popular initiative that has qualified and is now pending "
                          f"({stage['en']}), awaiting its nationwide vote.")
            desc["de"] = (f"Zustande gekommene Volksinitiative, derzeit hängig "
                          f"({stage['de']}), vor der Volksabstimmung.")
            desc["fr"] = (f"Initiative populaire aboutie, actuellement pendante "
                          f"({stage['fr']}), avant la votation populaire.")
            desc["it"] = (f"Iniziativa popolare riuscita, attualmente pendente "
                          f"({stage['it']}), prima della votazione popolare.")
        item = {
            "id": f"initiative-{iid}",
            "type": "initiative",
            "title": title,
            "desc": desc,
            "status": status,
            "date": {lang: f"{(SINCE_PREFIX if status == 'collecting' else LAUNCHED_PREFIX)[lang]}"
                           f" {fmt_date(beginn, lang, '')}" for lang in DATE_LANGS},
            "outcome": None,
            "url": PENDING_PAGE["de"],
            "_sort": beginn.replace("-", ""),
            "_titleTokens": norm_tokens(de),
        }
        if status == "collecting":
            # Signature-gathering deadline: 18 months after launch. The client
            # uses this to sort by "least time left" and show a countdown.
            item["deadline"] = deadline
        items.append(item)
    n_coll = sum(1 for i in items if i["status"] == "collecting")
    print(f"  {len(items)} pending initiatives ({n_coll} collecting signatures)")
    return items


# ----------------------------------------------------------------------------
# Source 3: LINDAS popular-vote cube — upcoming (scheduled but not yet held)
# ----------------------------------------------------------------------------

_TITLE_STOP = {
    "der", "die", "das", "und", "für", "vom", "von", "über", "eine", "einer",
    "einen", "des", "den", "dem", "zur", "zum", "mit", "auf", "bundesgesetz",
    "bundesbeschluss", "änderung", "volksinitiative", "initiative", "eidgenössische",
    "initiativepopulaire", "populaire", "iniziativa", "popolare", "federale",
}


def norm_tokens(text):
    text = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b", " ", text.lower())
    text = re.sub(r"[«»'\"“”’()–—\-.,!?:;]", " ", text)
    return {w for w in text.split() if len(w) > 3 and w not in _TITLE_STOP
            and not w.isdigit()}


def strip_vote_prefix(title):
    """Drop the 'Volksinitiative vom DD.MM.YYYY' / 'Änderung vom …' date stamp."""
    return re.sub(r"\s+(vom|du|del|dell['’]|dals)\s+\d{1,2}\.\d{1,2}\.\d{4}",
                  "", title).strip()


def fetch_upcoming(today):
    """Scheduled federal votes not yet held (from the popular-vote cube)."""
    print("Fetching LINDAS popular-vote cube (upcoming scheduled votes)...")
    today_iso = f"{today[0:4]}-{today[4:6]}-{today[6:8]}"
    query = f"""
PREFIX cube: <https://cube.link/>
PREFIX schema: <http://schema.org/>
PREFIX pv: <https://politics.ld.admin.ch/political-rights/popular-vote/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?id ?date ?typ ?de ?fr ?it WHERE {{
  <{POPULAR_VOTE_CUBE}> cube:observationSet/cube:observation ?o .
  ?o pv:id ?id ; pv:date ?date ; pv:abstimmungstitel ?t .
  OPTIONAL {{ ?o pv:typologie ?tr . ?tr schema:name ?typ . FILTER(LANG(?typ)="de") }}
  ?t schema:name ?de . FILTER(LANG(?de)="de")
  OPTIONAL {{ ?t schema:name ?fr . FILTER(LANG(?fr)="fr") }}
  OPTIONAL {{ ?t schema:name ?it . FILTER(LANG(?it)="it") }}
  FILTER(?date > "{today_iso}"^^xsd:date)
}} ORDER BY ?date
"""
    rows = sparql(query)
    items = []
    seen = set()
    for b in rows:
        g = lambda k: b.get(k, {}).get("value")
        iid = g("id")
        if iid in seen:
            continue
        seen.add(iid)
        de = strip_vote_prefix(g("de") or "")
        typ = (g("typ") or "").lower()
        if "stichfrage" in de.lower() or "stichfrage" in typ:
            continue
        is_init = "volksinitiative" in typ or de.lower().startswith("volksinitiative")
        fr = strip_vote_prefix(g("fr") or de)
        it = strip_vote_prefix(g("it") or de)
        date_iso = g("date")  # YYYY-MM-DD
        kind = {"en": "popular initiative" if is_init else "referendum",
                "de": "Volksinitiative" if is_init else "Referendumsvorlage",
                "fr": "initiative populaire" if is_init else "objet soumis au référendum",
                "it": "iniziativa popolare" if is_init else "oggetto in referendum"}
        desc = {
            "en": f"A federal {kind['en']} scheduled for a nationwide vote on "
                  f"{fmt_date(date_iso, 'en', '')}.",
            "de": f"Eine eidgenössische {kind['de']}, die am "
                  f"{fmt_date(date_iso, 'de', '')} zur Abstimmung kommt.",
            "fr": f"Une {kind['fr']} fédérale soumise à la votation du "
                  f"{fmt_date(date_iso, 'fr', '')}.",
            "it": f"Un'{kind['it']} federale in votazione il "
                  f"{fmt_date(date_iso, 'it', '')}.",
        }
        items.append({
            "id": f"vote-{date_iso.replace('-', '')}-{iid}",
            "type": "initiative" if is_init else "referendum",
            "title": {"en": english_from_name(de, is_init), "de": de, "fr": fr, "it": it},
            "desc": desc,
            "status": "upcoming",
            "date": {lang: f"{UPCOMING_PREFIX[lang]} {fmt_date(date_iso, lang, '')}"
                     for lang in DATE_LANGS},
            "outcome": None,
            "url": f"https://www.bk.admin.ch/ch/d/pore/va/"
                   f"{date_iso.replace('-', '')}/index.html",
            "voteDate": date_iso,
            "_sort": date_iso.replace("-", ""),
            "_titleTokens": norm_tokens(de),
            "_enFallback": True,
        })
    print(f"  {len(items)} upcoming scheduled ballot items")
    return items


# ----------------------------------------------------------------------------
# Swissvotes — party voting recommendations (Parolen) + English short titles
# ----------------------------------------------------------------------------

def fetch_recommendations():
    """Return a list of {dateIso, tokens, en, recs} rows from Swissvotes."""
    print("Fetching Swissvotes dataset (party recommendations)...")
    try:
        raw = http_get(SWISSVOTES_CSV).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"  ! Swissvotes fetch failed ({e}); votes will have no "
              "recommendations", file=sys.stderr)
        return []
    reader = csv.DictReader(io.StringIO(raw), delimiter=";")
    anr_key = None
    rows = []
    for row in reader:
        if anr_key is None:
            anr_key = next((k for k in row if k and "anr" in k), None)
        datum = (row.get("datum") or "").strip()  # DD.MM.YYYY
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", datum)
        if not m:
            continue
        date_iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        recs = {}
        for party_key, col in SWISSVOTES_PARTY_COLS.items():
            code = (row.get(col) or "").strip()
            if code in SWISSVOTES_REC:
                recs[party_key] = SWISSVOTES_REC[code]
        # Match on the official long title (aligns with the federal sources);
        # display the clean English short title.
        title = row.get("titel_off_d") or row.get("titel_kurz_d") or ""
        rows.append({
            "dateIso": date_iso,
            "tokens": norm_tokens(title),
            "en": (row.get("titel_kurz_e") or "").strip(),
            "recs": recs,
        })
    print(f"  {len(rows)} Swissvotes ballots parsed")
    return rows


def annotate_recommendations(items, sv_rows):
    """Attach party recommendations (and fill EN title) to dated vote items."""
    by_date = {}
    for r in sv_rows:
        by_date.setdefault(r["dateIso"], []).append(r)
    matched = 0
    for it in items:
        date_iso = it.get("voteDate") or it.get("_voteDateIso")
        if not date_iso:
            continue
        cands = by_date.get(date_iso, [])
        itok = it.get("_titleTokens") or norm_tokens(it["title"].get("de", ""))
        best, best_score = None, 0.0
        for r in cands:
            if not r["tokens"] or not itok:
                continue
            score = len(r["tokens"] & itok) / min(len(r["tokens"]), len(itok))
            if score > best_score:
                best, best_score = r, score
        if not best or best_score < 0.5:
            continue
        matched += 1
        if best["recs"]:
            it["recommendations"] = best["recs"]
        # Fill a real English title for items that only had a framed fallback.
        if best["en"] and it.get("_enFallback"):
            it["title"]["en"] = best["en"]
    print(f"  matched recommendations to {matched} votes")


def clean(item):
    out = {k: v for k, v in item.items() if not k.startswith("_")}
    if out.get("outcome") is None:
        out.pop("outcome", None)
    return out


def main():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    try:
        upcoming = fetch_upcoming(today)
        votes = fetch_votes(today)
        pending = fetch_pending()
        sv_rows = fetch_recommendations()
    except urllib.error.URLError as e:
        print(f"Network error reaching an official source: {e}", file=sys.stderr)
        print("Keeping existing data/initiatives.json unchanged.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"Fetch failed: {e}", file=sys.stderr)
        print("Keeping existing data/initiatives.json unchanged.", file=sys.stderr)
        sys.exit(1)

    # A scheduled vote also appears in the popular-initiative cube as an
    # "abstimmungsreif"/pending item — drop that duplicate in favour of the
    # scheduled entry, which carries the actual vote date.
    scheduled_tokens = [u["_titleTokens"] for u in upcoming if u.get("_titleTokens")]

    def is_scheduled_dupe(item):
        itok = item.get("_titleTokens")
        if not itok:
            return False
        return any(len(itok & stok) / min(len(itok), len(stok)) >= 0.6
                   for stok in scheduled_tokens if stok)

    pending = [p for p in pending if not is_scheduled_dupe(p)]

    # Party recommendations (and English short titles) onto every dated vote.
    annotate_recommendations(upcoming + votes, sv_rows)

    # Order for the default (flat) list: upcoming soonest-first, then
    # qualified-pending, then signature-gathering by nearest deadline, then
    # decided newest-first. The client re-groups these into tabs, but a sensible
    # base order keeps the raw file readable and the no-JS view coherent.
    up = sorted([i for i in upcoming if i["status"] == "upcoming"],
                key=lambda i: i["_sort"])
    pend = sorted([i for i in pending if i["status"] == "pending"],
                  key=lambda i: i["_sort"], reverse=True)
    coll = sorted([i for i in pending if i["status"] == "collecting"],
                  key=lambda i: i.get("deadline", "9999"))
    decided = sorted([i for i in votes if i["status"] in ("adopted", "rejected")],
                     key=lambda i: i["_sort"], reverse=True)
    ordered = up + pend + coll + decided

    output = {
        "_meta": {
            "source": (
                "Decided federal votes: VoteInfo (Federal Chancellery / Federal "
                "Statistical Office), opendata.swiss dataset "
                "'echtzeitdaten-am-abstimmungstag-zu-eidgenoessischen-abstimmungsvorlagen'. "
                "Upcoming scheduled votes and pending/signature-gathering "
                "initiatives: Federal Chancellery linked-data cubes "
                "(politics.ld.admin.ch) via the LINDAS SPARQL endpoint. Party "
                "recommendations (Parolen): Swissvotes (Année Politique Suisse, "
                "Uni Bern), CC BY-NC-SA. Official authority texts are not subject "
                "to copyright (Art. 5 URG)."
            ),
            "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": (
                "Titles and results are taken verbatim from the official sources. "
                "Descriptions are composed from official structured fields (result, "
                "turnout, stage, dates), not editorialised. English titles for "
                "still-pending initiatives keep the official name in its original "
                "language. This is a curated-by-recency selection, not a full archive."
            ),
        },
        "initiatives": [clean(i) for i in ordered],
    }

    out_path = ROOT / "data" / "initiatives.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"Wrote {out_path} ({len(ordered)} items: {len(up)} upcoming, "
          f"{len(pend)} pending, {len(coll)} collecting, {len(decided)} decided)")


if __name__ == "__main__":
    main()
