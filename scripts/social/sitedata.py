"""Read the site's own data for the social cards, and format it per language.

Everything here comes from data/ (and, for the session ticker, a day file read
from the ticker-data branch). Nothing is fetched from the internet. Official
texts are used word for word; where an English text is a machine translation
(DeepL) or Politikch's own unofficial translation, the caller gets a flag so the
card can show its badge (POL-13).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
HERE = Path(__file__).resolve().parent
LANGS = ("de", "fr", "it", "en")


def _load(rel):
    return json.loads((DATA / rel).read_text("utf-8"))


@lru_cache(maxsize=None)
def strings():
    return json.loads((HERE / "strings.json").read_text("utf-8"))


def S(lang):
    return strings()[lang]


@lru_cache(maxsize=None)
def site():
    """All data files the cards use, loaded once."""
    d = {
        "initiatives": _load("initiatives.json"),
        "financing": _load("financing.json"),
        "mt": _load("mt.json"),
        "sessionsIndex": _load("sessions-index.json"),
        "parties": _load("parties.json"),
        "cantons": _load("cantons.json"),
        "cantonData": _load("canton-data.json"),
        "glossary": _load("glossary.json"),
        "i18n": _load("i18n.json"),
        "initTranslations": _load("initiatives-translations.json"),
    }
    d["votes"] = {v["id"]: v for v in d["initiatives"]["initiatives"]}
    return d


@lru_cache(maxsize=None)
def session(sid):
    return _load(f"sessions/{sid}.json")


@lru_cache(maxsize=None)
def overview(vote_id):
    p = DATA / "overviews" / "initiative" / f"{vote_id}.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else None


@lru_cache(maxsize=None)
def map_paths():
    """Canton shapes from js/map-data.js (stylised, as on the site's map)."""
    src = (ROOT / "js" / "map-data.js").read_text("utf-8")
    return {m.group(1): m.group(2) for m in re.finditer(r'\b([A-Z]{2}):\s*\{\s*d:\s*"([^"]+)"', src)}


def ticker_day(date_iso):
    """A session-ticker day file from the ticker-data branch (OPS-10: it never lives on main)."""
    for ref in ("origin/ticker-data", "ticker-data"):
        r = subprocess.run(["git", "show", f"{ref}:data/sessions/days/{date_iso}.json"],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout)
    return None


# ---------------------------------------------------------------- formatting
def fill(text, **kw):
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def date_long(d, lang):
    m = S(lang)["months"][d.month - 1]
    if lang == "de":
        return f"{d.day}. {m} {d.year}"
    if lang == "fr":
        return f"{'1er' if d.day == 1 else d.day} {m} {d.year}"
    return f"{d.day} {m} {d.year}"


def date_short(d, lang):
    return date_long(d, lang).rsplit(" ", 1)[0]


def date_num(d):
    return d.strftime("%d.%m.%Y")


def weekday_date(d, lang):
    return f"{S(lang)['weekdays'][d.weekday()]}, {date_long(d, lang)}" if lang in ("de", "en") \
        else f"{S(lang)['weekdays'][d.weekday()]} {date_long(d, lang)}"


def num(n, lang):
    s = f"{int(round(n)):,}"
    if lang == "en":
        return s
    if lang == "fr":
        return s.replace(",", "\u202f")
    return s.replace(",", "’")


def pct(x, lang):
    s = f"{x:.1f}"
    return (s if lang == "en" else s.replace(".", ",")) + ("%" if lang == "en" else "\u00a0%")


def chf(n, lang):
    return "CHF " + num(n, lang)


def fetched(iso, lang):
    """'19.10.2026, 11:37' in Swiss time, from a _meta.fetchedAt value (SRC-12)."""
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    off = 2 if 3 < t.month < 11 else 1   # CEST/CET; good enough for a label
    t = t + dt.timedelta(hours=off)
    return t.strftime("%d.%m.%Y, %H:%M")


# ---------------------------------------------------------------- votes
VOTE_DATE = re.compile(r"^vote-(\d{4})(\d{2})(\d{2})-")
PREFIXES = ("Eidgenössische Volksinitiative ", "Volksinitiative ", "Initiative populaire fédérale ",
            "Initiative populaire ", "Iniziativa popolare federale ", "Iniziativa popolare ",
            "Federal popular initiative ", "Popular Initiative ", "Popular initiative ")


def vote_date(v):
    if v.get("voteDate"):
        return dt.date.fromisoformat(v["voteDate"])
    m = VOTE_DATE.match(v["id"])
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def vote_form(v):
    """initiative / mandatory / optional / counter / referendum."""
    form = (v.get("parliament") or {}).get("form")
    return form or ("initiative" if v.get("type") == "initiative" else "referendum")


def needs_cantons(v):
    f = vote_form(v)
    return {"initiative": True, "mandatory": True, "counter": True, "optional": False}.get(f)


def _english_title(v):
    """(text, badge) — badge 'unofficial' for Politikch's own translations."""
    tr = (site()["initTranslations"].get("titles") or {}).get(v["id"], {})
    if tr.get("en"):
        return tr["en"], "unofficial"
    en = (v.get("title") or {}).get("en") or ""
    de = (v.get("title") or {}).get("de") or ""
    if en and "«" in en and de and en.split("«")[-1][:20] == de.replace("'", "«").split("«")[-1][:20]:
        return de, "german"     # no English version: show the official German title
    return en, None


def vote_title(v, lang, strip_type=True):
    """(title, badge). Official DE/FR/IT; English from Swissvotes or labelled."""
    if lang == "en":
        t, badge = _english_title(v)
    else:
        t, badge = v["title"][lang], None
    if strip_type:
        for p in PREFIXES:
            if t.startswith(p):
                t = t[len(p):]
                break
    return t, badge


def short_name(v, lang):
    """The name in brackets at the end of an official title ('Neutralitätsinitiative'), else the title."""
    t, badge = vote_title(v, lang)
    m = re.search(r"\(([^()]*)\)\s*['’»”“\"]*\s*$", t)
    if m and len(m.group(1)) <= 60:
        s = m.group(1).strip()
        return s[0].upper() + s[1:], badge
    return t, badge


def outcome(v, lang):
    """(label, yes_pct) from the official outcome text, e.g. 'Abgelehnt (70,2% Nein)'."""
    o = v.get("outcome") or {}
    m = re.match(r"\s*([^(]+?)\s*\(([\d.,]+)\s*%\s*(\w+)\)", o.get("en", ""))
    if not m:
        return None, None
    share = float(m.group(2).replace(",", "."))
    yes = share if m.group(3).lower().startswith("yes") else round(100 - share, 1)
    label = re.match(r"\s*([^(]+?)\s*\(", o.get(lang, "")).group(1)
    return label, yes


def parliament_rec(v):
    """'yes' / 'no' / None — Parliament's recommendation on the ballot (from Swissvotes)."""
    pos = (v.get("parliament") or {}).get("position")
    return {"accept": "yes", "reject": "no"}.get(pos)


# ---------------------------------------------------------------- other lookups
def party_short(key, lang):
    return strings()["parties"].get(key, {}).get(lang, key)


def party_color(key):
    return (site()["parties"]["parties"].get(key) or {}).get("color", "#B9B5AC")


def parties_by_seats():
    P = site()["parties"]["parties"]
    return sorted(P, key=lambda k: (-P[k].get("ncSeats", 0), k))


def gloss_text(term, lang):
    """The editor's own explanation of a glossary term (data/i18n.json gloss.*)."""
    if (term.get("definition") or {}).get(lang):
        return term["definition"][lang]
    key = term.get("definitionKey")
    return site()["i18n"].get(lang, {}).get(f"gloss.{key}", "") if key else ""


def mt_title(vote_id):
    return ((site()["mt"].get("titles") or {}).get(str(vote_id)) or {}).get("t")


def first_sentence(text):
    m = re.match(r"(.+?[.!?])(\s|$)", text.strip(), re.S)
    return (m.group(1) if m else text.strip()).strip()


def arguments(vote_id, lang):
    """{'sides': {...}, 'pros': [...], 'cons': [...], 'mt': bool} or None."""
    o = overview(vote_id)
    if not o:
        return None
    sides = o.get("sides") or {}
    if lang in (o.get("lang") or {}):
        b = o["lang"][lang]
        return {"sides": sides, "pros": b.get("pros", []), "cons": b.get("cons", []), "mt": False}
    a = ((site()["mt"].get("args") or {}).get(vote_id) or {}).get(lang)
    if a:
        return {"sides": sides, "pros": a.get("pros", []), "cons": a.get("cons", []), "mt": True}
    return None
