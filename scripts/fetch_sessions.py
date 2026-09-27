#!/usr/bin/env python3
"""Fetch Federal Assembly sessions, their final votes and per-party tallies.

Writes an index plus one file per session from the official, machine-readable
Federal Assembly web service — no invented figures, exactly like the other
fetchers in this directory:

  * data/sessions-index.json — the ordinary (spring/summer/autumn/winter) and
    special sessions of the Federal Assembly, with real start/end dates, the
    legislative period, a final-vote count and the topics that session touched.

  * data/sessions/<id>.json — that session's final votes (Schlussabstimmungen):
    on the last day of each ordinary session the National Council holds a final,
    recorded vote on every enacted act. For each we store the act title
    (DE/FR/IT — Swiss acts have no official English title), the topics and
    business type (canonical keys, translated in the UI), and the overall and
    per parliamentary-group Yes/No/Abstain tally.

Splitting per session keeps each page load small and lets history grow cheaply:
an already-fetched older session is never re-fetched (its result can't change),
so adding more history is a one-time cost and the scheduled job only refreshes
the newest sessions.

Source: the Federal Assembly's public OData web service
(https://ws.parlament.ch/odata.svc/), the same open, unauthenticated endpoint
the parliament's own applications use. The recorded per-member final votes are
National Council votes; the Council of States and the United Federal Assembly do
not publish per-member final-vote records here (this is made clear in the UI).

The site never links to or embeds video here — the frontend only points to the
Federal Assembly's own YouTube channel ("The Swiss Parliament — the Federal
Assembly", @ParlCH) and to the official business pages, staying a link-out
reference rather than a re-host.

Usage:
  python3 scripts/fetch_sessions.py            # incremental (skips settled sessions already on disk)
  python3 scripts/fetch_sessions.py --force    # re-fetch every session

Design notes:
  * Build-time fetch (CI or local) writing same-origin JSON the static site
    loads like any other data file.
  * On any failure the existing files are left untouched, so the site never
    falls back to a blank or invented list.
  * Unofficial English act-title translations live in a SEPARATE, hand-curated
    file, data/sessions-translations.json (voteId → English), which this script
    never writes or reads. Swiss acts have no official English title, so the UI
    shows those English titles with an "unofficial" badge and falls back to the
    official DE/FR/IT title when a translation is missing. New votes added by a
    future run won't have an English title until one is added to that file.
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from licences import licence_meta  # the file's licence (scripts/licences.py)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INDEX = DATA / "sessions-index.json"
SESSIONS_DIR = DATA / "sessions"

BASE = "https://ws.parlament.ch/odata.svc"
UA = (
    "Politikch-data-fetcher/1.0 "
    "(+https://politikch.ch; contact.form@politikch.ch)"
)

# How many of the most recent already-started sessions to include (≈ 5 years).
MAX_SESSIONS = 20
# A session ended within this many days is re-fetched even if a file exists —
# recorded final votes can land in the service a little after the session ends.
REFRESH_WINDOW_DAYS = 45
TITLE_LANGS = ["DE", "FR", "IT"]  # Swiss acts have official titles only in these

# Parliamentary-group code → the site's party key in data/parties.json.
GROUP_TO_PARTY = {
    "V": "SVP", "S": "SP", "RL": "FDP", "M-E": "MITTE", "G": "GPS", "GL": "GLP",
    "CE": "MITTE", "C": "MITTE", "BD": "MITTE",  # legacy groups
}

YES, NO, ABSTAIN = 1, 2, 3  # Voting.Decision codes; else = did not vote

# Final-vote subject, stored in whichever language the clerk used.
FINAL_VOTE_SUBJECTS = ("Schlussabstimmung", "Vote final", "Votazione finale")

# Business "Tags" (thematic areas), German canonical spelling → topic key.
# The UI translates each key into all four languages (session.topic.<key>).
TOPIC_MAP = {
    "Wirtschaft": "economy", "Gesundheit": "health", "Staatspolitik": "statePolicy",
    "Sicherheitspolitik": "security", "Finanzwesen": "finance",
    "Medien und Kommunikation": "media", "Internationale Politik": "international",
    "Umwelt": "environment", "Soziale Fragen": "socialQuestions", "Migration": "migration",
    "Landwirtschaft": "agriculture", "Beschäftigung und Arbeit": "labour",
    "Verkehr": "transport", "Strafrecht": "criminalLaw", "Parlament": "parliament",
    "Menschenrechte": "humanRights", "Energie": "energy", "Bildung": "education",
    "Kultur": "culture", "Wissenschaft und Forschung": "science", "Steuer": "taxation",
    "Sozialer Schutz": "socialSecurity", "Europapolitik": "europe",
    "Gerichtswesen": "judiciary", "Internationales Recht": "internationalLaw",
    "Zivilrecht": "civilLaw", "Raumplanung und Wohnungswesen": "spatialPlanning",
    "Recht Allgemein": "lawGeneral",
}
# Business type, German canonical → type key (UI: session.btype.<key>).
TYPE_MAP = {
    "Geschäft des Bundesrates": "federalCouncil",
    "Parlamentarische Initiative": "parliamentaryInitiative",
    "Geschäft des Parlaments": "parliament",
    "Standesinitiative": "cantonalInitiative",
    "Motion": "motion", "Postulat": "postulate", "Interpellation": "interpellation",
    "Petition": "petition", "Anfrage": "query",
}


# A larger response is refused rather than read into memory (GUARDRAILS.md SEC-09).
MAX_BYTES = 32 * 1024 * 1024


def read_capped(resp):
    data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"response larger than {MAX_BYTES} bytes: {resp.geturl()}")
    return data


def http_get(url, tries=4):
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(read_capped(r).decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}\n  {last}")


def odata(entity, *, select=None, filt=None, orderby=None, top=None, lang="DE"):
    parts = [f"Language eq '{lang}'"]
    if filt:
        parts.append(filt)
    params = {"$format": "json", "$filter": " and ".join(parts)}
    if select:
        params["$select"] = select
    if orderby:
        params["$orderby"] = orderby
    if top:
        params["$top"] = str(top)
    url = f"{BASE}/{entity}?" + urllib.parse.urlencode(params, safe="'")
    data = http_get(url)
    time.sleep(0.35)
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(data["error"].get("message", {}).get("value", "OData error"))
    d = data.get("d", [])
    return d.get("results", []) if isinstance(d, dict) else d


def dotnet_date(s):
    if not s:
        return None
    m = re.search(r"(-?\d+)", s)
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc) if m else None


def season_of(name, start_month, session_type):
    """Only ordinary sessions (Type 2) carry a season; special/extraordinary
    sessions are 'special'. The German SessionName names the season reliably
    (start months drift — spring can begin in Feb or Mar, etc.), with a month
    range as a fallback."""
    if session_type != 2:
        return "special"
    n = (name or "").lower()
    for kw, key in (("frühjahr", "spring"), ("sommer", "summer"), ("herbst", "autumn"), ("winter", "winter")):
        if kw in n:
            return key
    return ({2: "spring", 3: "spring", 5: "summer", 6: "summer",
             8: "autumn", 9: "autumn", 11: "winter", 12: "winter"}).get(start_month, "special")


def fetch_sessions():
    rows = odata(
        "Session",
        select="ID,Abbreviation,SessionName,StartDate,EndDate,Type,LegislativePeriodNumber",
        orderby="StartDate desc",
        top=MAX_SESSIONS * 2,
    )
    now = datetime.now(tz=timezone.utc)
    out = []
    for s in rows:
        start = dotnet_date(s.get("StartDate"))
        end = dotnet_date(s.get("EndDate"))
        if not start or start > now:
            continue
        out.append({
            "id": s["ID"],
            "abbr": s.get("Abbreviation"),
            "year": start.year,
            "season": season_of(s.get("SessionName"), start.month, s.get("Type")),
            "start": start.date().isoformat(),
            "end": end.date().isoformat() if end else None,
            "legislativePeriod": s.get("LegislativePeriodNumber"),
        })
        if len(out) >= MAX_SESSIONS:
            break
    return out


def strip_html(s, cap=600):
    """Official Curia Vista fields are HTML; reduce to a capped plain-text
    excerpt (sentence-ish boundary) for the 'What this vote is about' section."""
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > cap:
        s = s[:cap].rsplit(" ", 1)[0].rstrip(" ,;:—-") + "…"
    return s


def fetch_business_meta(business_ids):
    """Batch-fetch, per business: thematic topics + business type (from the DE
    record, canonicalised to keys), plus the official background text
    (InitialSituation, falling back to Description) in DE/FR/IT — the source for
    the 'What this vote is about' section. That text is official Curia Vista
    content from parlament.ch (opendata.swiss 'terms_by' — reusable, incl.
    commercially, with attribution)."""
    meta = {}
    ids = sorted(set(i for i in business_ids if i))
    for i in range(0, len(ids), 20):
        chunk = ids[i:i + 20]
        filt = "(" + " or ".join(f"ID eq {bid}" for bid in chunk) + ")"
        for lang in TITLE_LANGS:  # DE first, so topics/btype come from that pass
            sel = ("ID,TagNames,BusinessTypeName,InitialSituation,Description"
                   if lang == "DE" else "ID,InitialSituation,Description")
            for b in odata("Business", select=sel, filt=filt, lang=lang):
                m = meta.setdefault(b["ID"], {"topics": [], "btype": None, "summary": {}})
                if lang == "DE":
                    m["topics"] = [TOPIC_MAP[t.strip()]
                                   for t in (b.get("TagNames") or "").split("|")
                                   if t.strip() in TOPIC_MAP]
                    m["btype"] = TYPE_MAP.get((b.get("BusinessTypeName") or "").strip())
                txt = strip_html(b.get("InitialSituation")) or strip_html(b.get("Description"))
                if txt:
                    m["summary"][lang.lower()] = txt
    return meta


def fetch_final_votes(session_id):
    subj = " or ".join(f"Subject eq '{s}'" for s in FINAL_VOTE_SUBJECTS)
    filt = f"IdSession eq {session_id} and ({subj})"
    select = "ID,BusinessNumber,BusinessShortNumber,BusinessTitle,BillTitle,BillNumber,MeaningYes,MeaningNo,VoteEnd"
    by_id, order = {}, []
    for lang in TITLE_LANGS:
        for v in odata("Vote", select=select, filt=filt, orderby="VoteEnd", lang=lang):
            vid = v["ID"]
            title = v.get("BillTitle") or v.get("BusinessTitle") or v.get("BusinessShortNumber") or ""
            if vid not in by_id:
                order.append(vid)
                by_id[vid] = {
                    "id": vid,
                    "business": v.get("BusinessShortNumber"),
                    "businessNumber": v.get("BusinessNumber"),
                    "title": {},
                    "voteEnd": (dotnet_date(v.get("VoteEnd")) or datetime.now(timezone.utc)).date().isoformat(),
                }
                add_meaning(by_id[vid], v)
            by_id[vid]["title"][lang.lower()] = title.strip()
    return [by_id[i] for i in order]


# What a Yes and a No meant in the vote, as the Parliamentary Services record it
# (official text, kept verbatim; entered once, in German or French, the same in
# every language version). For a federal decree on a popular initiative it says
# which way the decree recommends, e.g. "Annahme der Vorlage (Empfehlung auf
# Ablehnung der Volksinitiative)".
def add_meaning(vote, row):
    yes, no = (row.get("MeaningYes") or "").strip(), (row.get("MeaningNo") or "").strip()
    if yes or no:
        vote["meaning"] = {"yes": yes[:300], "no": no[:300]}
    if isinstance(row.get("BillNumber"), int):
        vote["bill"] = row["BillNumber"]


def is_initiative_decree(vote):
    """A federal decree on a popular initiative (not a counter-proposal): its
    Yes adopts Parliament's recommendation, not the initiative."""
    t = ((vote.get("title") or {}).get("de") or "").lower()
    return "volksinitiative" in t and "gegenentwurf" not in t and "gegenvorschlag" not in t


def decree_direction(meaning_yes):
    """Which way a decree recommends, only when the official text says so plainly."""
    m = (meaning_yes or "").lower()
    rej = re.search(r"ablehnung der (eidgenössischen )?volksinitiative|rejeter l[’']?(initiative|iv\.)", m)
    acc = re.search(r"annahme der (eidgenössischen )?volksinitiative|accepter l[’']?(initiative|iv\.)", m)
    if rej and not acc:
        return "reject"
    if acc and not rej:
        return "accept"
    return None


def annotate_decree(vote):
    """Mark a decree on a popular initiative with the direction it recommends
    (from the official meaning text; checked against Swissvotes later)."""
    if not is_initiative_decree(vote):
        vote.pop("initiativeDecree", None)
        return
    rec = decree_direction((vote.get("meaning") or {}).get("yes"))
    vote["initiativeDecree"] = {"recommend": rec, "source": "parlament.ch" if rec else None}


def backfill_meanings(session_id, votes):
    """Settled sessions are reused from disk; fetch the meaning of each vote once
    for files written before it was recorded. Returns True if anything changed."""
    if all("meaning" in v for v in votes):
        return False
    subj = " or ".join(f"Subject eq '{s}'" for s in FINAL_VOTE_SUBJECTS)
    rows = odata("Vote", select="ID,BillNumber,MeaningYes,MeaningNo",
                 filt=f"IdSession eq {session_id} and ({subj})")
    by_id = {r["ID"]: r for r in rows}
    changed = False
    for v in votes:
        r = by_id.get(v["id"])
        if r and "meaning" not in v:
            add_meaning(v, r)
            changed = True
    return changed


# Link each ballot to the National Council final vote behind it: same business
# number, and the vote counts agree with Swissvotes' (counted relative to the
# proposal). Two independent sources agreeing is the test; nothing is guessed.
# Swissvotes' recommendation also confirms (or fills in) the decree direction;
# where the two disagree the direction is dropped and a warning printed.
def link_ballots(session_votes):
    path = DATA / "initiatives.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    by_business = {}
    for sid, v in session_votes:
        by_business.setdefault(v.get("business"), []).append((sid, v))
    touched_sessions, linked, changed = set(), 0, False
    for item in data.get("initiatives", []):
        par = item.get("parliament")
        if not par or par.get("form") == "tiebreak" or "ncFor" not in par:
            continue
        found = []
        for sid, v in by_business.get(par["business"], []):
            t = v.get("tally") or {}
            decree = is_initiative_decree(v)
            if par["form"] == "initiative":
                if not decree or par.get("position") not in ("reject", "accept"):
                    continue
                pro, con = (t.get("no"), t.get("yes")) if par["position"] == "reject" else (t.get("yes"), t.get("no"))
            else:
                if decree:
                    continue
                pro, con = t.get("yes"), t.get("no")
            if (pro, con) == (par["ncFor"], par["ncAgainst"]):
                found.append((sid, v))
        if len(found) != 1:
            if par.get("link"):
                par.pop("link")
                changed = True
            continue
        sid, v = found[0]
        link = {"session": sid, "vote": v["id"]}
        if par.get("link") != link:
            par["link"] = link
            changed = True
        linked += 1
        if par["form"] == "initiative":
            d = v.get("initiativeDecree") or {}
            if d.get("recommend") is None:
                v["initiativeDecree"] = {"recommend": par["position"], "source": "swissvotes"}
                touched_sessions.add(sid)
            elif d.get("recommend") != par["position"]:
                print(f"  ! vote {v['id']}: parlament.ch says {d['recommend']}, Swissvotes says {par['position']} — direction dropped",
                      file=sys.stderr)
                v["initiativeDecree"] = {"recommend": None, "source": "conflict"}
                touched_sessions.add(sid)
            elif d.get("source") == "parlament.ch":
                v["initiativeDecree"]["source"] = "parlament.ch+swissvotes"
                touched_sessions.add(sid)
    if changed:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  linked {linked} ballots to their National Council final vote")
    return touched_sessions


def fetch_tally(vote_id):
    rows = odata("Voting", select="Decision,ParlGroupCode", filt=f"IdVote eq {vote_id}", top=300)
    total = {"yes": 0, "no": 0, "abstain": 0}
    by_party = {}
    for r in rows:
        dec = r.get("Decision")
        bucket = "yes" if dec == YES else "no" if dec == NO else "abstain" if dec == ABSTAIN else None
        if not bucket:
            continue
        total[bucket] += 1
        party = GROUP_TO_PARTY.get(r.get("ParlGroupCode"))
        if party:
            by_party.setdefault(party, {"yes": 0, "no": 0, "abstain": 0})[bucket] += 1
    return total, by_party


def build_session(session):
    """Fetch one session's final votes with tallies + business metadata."""
    votes = fetch_final_votes(session["id"])
    meta = fetch_business_meta([v["businessNumber"] for v in votes]) if votes else {}
    kept = []
    for v in votes:
        total, by_party = fetch_tally(v["id"])
        if total["yes"] + total["no"] + total["abstain"] == 0:
            continue
        bm = meta.get(v["businessNumber"], {})
        v["topics"] = bm.get("topics", [])
        v["btype"] = bm.get("btype")
        summary = bm.get("summary") or {}
        if summary:
            v["summary"] = summary
        v["tally"] = total
        v["byParty"] = by_party
        v["passed"] = total["yes"] > total["no"]
        annotate_decree(v)
        kept.append(v)
    return kept


def main():
    force = "--force" in sys.argv[1:]
    try:
        sessions = fetch_sessions()
    except Exception as e:  # noqa: BLE001
        print(f"Could not fetch sessions ({e}); leaving files untouched.", file=sys.stderr)
        sys.exit(0)
    if not sessions:
        print("No sessions returned; leaving files untouched.", file=sys.stderr)
        sys.exit(0)

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=timezone.utc)
    index = []
    files = {}                                  # session id -> (path, file dict) for the linking step
    for s in sessions:
        # The id comes from parlament.ch and becomes a filename: accept digits
        # only, so an unexpected value can never write outside data/sessions/.
        if not re.fullmatch(r"\d{1,8}", str(s.get("id", ""))):
            print(f"  skipping session with unexpected id {s.get('id')!r}", file=sys.stderr)
            continue
        path = SESSIONS_DIR / f"{s['id']}.json"
        end = datetime.fromisoformat(s["end"] + "T00:00:00+00:00") if s.get("end") else now
        recent = (now - end) <= timedelta(days=REFRESH_WINDOW_DAYS)
        # Reuse a settled session already on disk; refetch recent/missing ones.
        if path.exists() and not force and not recent:
            doc = json.loads(path.read_text(encoding="utf-8"))
            votes = doc.get("votes", [])
            try:
                if backfill_meanings(s["id"], votes):
                    for v in votes:
                        annotate_decree(v)
                    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                print(f"  session {s['id']}: meanings not added ({e})", file=sys.stderr)
        else:
            try:
                votes = build_session(s)
                path.write_text(json.dumps({
                    "_meta": licence_meta(f"sessions/{s['id']}.json"),
                    "id": s["id"], "season": s["season"], "year": s["year"],
                    "start": s["start"], "end": s.get("end"),
                    "legislativePeriod": s.get("legislativePeriod"),
                    "votes": votes,
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                print(f"  session {s['id']} fetch failed ({e}); using existing file if any.", file=sys.stderr)
                votes = json.loads(path.read_text(encoding="utf-8")).get("votes", []) if path.exists() else []
        if path.exists():
            files[s["id"]] = path
        topics = sorted({tk for v in votes for tk in v.get("topics", [])})
        entry = {k: s[k] for k in ("id", "abbr", "season", "year", "start", "end", "legislativePeriod")}
        entry["voteCount"] = len(votes)
        entry["topics"] = topics
        index.append(entry)
        print(f"  {s['season']} {s['year']} (id {s['id']}): {len(votes)} final votes")

    # Link ballots to their final votes; rewrite the session files whose decree
    # direction the cross-check with Swissvotes confirmed or changed.
    docs = {sid: json.loads(p.read_text(encoding="utf-8")) for sid, p in files.items()}
    touched = link_ballots([(sid, v) for sid, d in docs.items() for v in d.get("votes", [])])
    for sid in touched:
        files[sid].write_text(json.dumps(docs[sid], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    INDEX.write_text(json.dumps({
        "_meta": {
            **licence_meta("sessions-index.json"),
            "source": "Federal Assembly OData web service (ws.parlament.ch)",
            "channel": "https://www.youtube.com/@ParlCH",
            "fetchedAt": now.isoformat(timespec="seconds"),
        },
        "sessions": index,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {INDEX.relative_to(ROOT)} — {len(index)} sessions.")


if __name__ == "__main__":
    main()
