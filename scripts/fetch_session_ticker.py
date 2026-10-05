#!/usr/bin/env python3
"""Session ticker: what the Federal Assembly has on today's programme, who has
spoken, how the National Council voted and what each council decided.

Writes one file per sitting day plus a small index, from the same official,
unauthenticated web service as fetch_sessions.py:

  * data/sessions/days/<YYYY-MM-DD>.json — that day's programme per council
    (meetings, agenda items with their official DE/FR/IT titles), the list of
    speakers (name, role, parliamentary group, canton, start and end time —
    never what they said), every recorded National Council vote with its
    official subject and Yes/No meaning and the tallies by parliamentary group,
    and the councils' official decisions on business that day.
  * data/sessions/days/index.json — the days on file, with counts, for the
    front page and the day picker.

The official data runs about one to two hours behind the chamber: speakers
appear when the provisional Official Bulletin is published, National Council
votes about 90 minutes after the vote. The site says so next to the data and
never calls it live (GUARDRAILS.md POL-14).

Rules this file is held to (GUARDRAILS.md, checked by check.py and validate.py):
  * SRC-12 — every file carries the date and time of download (_meta.fetchedAt).
  * SRC-13 — no speech text: transcripts are only ever requested with $select,
    and never with the Text field.
  * SRC-14 — gentle on the source: one host, SPACING between requests,
    MAX_REQUESTS per run, only on days the Federal Assembly sits, a cheap
    change probe before a full fetch, and TICKER_OFF stops it.
  * POL-15 — no outcome is computed from a tally; decisions come only from the
    councils' official decision records.
  * PRIV-13 — tallies by parliamentary group only; no member's individual vote,
    no person numbers, no photos. Decision records that aren't a standard
    decision (e.g. judicial elections naming private persons and where they
    live) are left out.

Times in the source are Swiss local time; they are stored as "HH:MM".

Usage:
  python3 scripts/fetch_session_ticker.py                    # today (Swiss date)
  python3 scripts/fetch_session_ticker.py --date 2026-10-01  # one day (replay/testing)
  python3 scripts/fetch_session_ticker.py --check-session    # only: is today a session day?

Runs in .github/workflows/session-ticker.yml; the files go to the
`ticker-data` branch, never to main (GUARDRAILS.md OPS-10).
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fetch_sessions import GROUP_TO_PARTY, season_of  # pure helpers, no requests
from licences import licence_meta

ROOT = Path(__file__).resolve().parent.parent
DAYS_DIR = ROOT / "data" / "sessions" / "days"
INDEX = DAYS_DIR / "index.json"

BASE = "https://ws.parlament.ch/odata.svc"
UA = (
    "Politikch-data-fetcher/1.0 "
    "(+https://politikch.ch; contact.form@politikch.ch)"
)
SWISS = ZoneInfo("Europe/Zurich")

# SRC-14: the source's load. At most this many requests per run, this far apart.
MAX_REQUESTS = 120
SPACING = 0.35
# A tally is fetched once per vote; at most this many new ones per run (the
# rest follow 20 minutes later).
MAX_NEW_TALLIES = 40
# Without a change in the probe, a day is still fully refreshed this often
# (agenda changes and decisions don't move the probe).
FULL_REFRESH = timedelta(hours=2)

# A larger response is refused rather than read into memory (GUARDRAILS.md SEC-09).
MAX_BYTES = 8 * 1024 * 1024

COUNCILS = {1: "N", 2: "S", 3: "V"}          # Meeting.Council: National Council, Council of States, United Federal Assembly
YES, NO, ABSTAIN = 1, 2, 3                   # Voting.Decision codes; anything else = did not vote
# Speaker roles as the Official Bulletin records them (…-M / …-F); anything else
# is shown as "other". The UI translates each code (ticker.role.<code>).
ROLES = {"Mit-M", "Mit-F", "P-M", "P-F", "1VP-M", "1VP-F", "2VP-M", "2VP-F",
         "BR-M", "BR-F", "BPR-M", "BPR-F", "VPBR-M", "VPBR-F", "BK-M", "BK-F"}
LANGS = ("DE", "FR", "IT")

requests_made = 0


class Budget(Exception):
    pass


def read_capped(resp):
    data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"response larger than {MAX_BYTES} bytes: {resp.geturl()}")
    return data


def http_get(url, tries=3):
    global requests_made
    last = None
    for attempt in range(tries):
        if requests_made >= MAX_REQUESTS:
            raise Budget(f"request budget of {MAX_REQUESTS} used up")
        requests_made += 1
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(read_capped(r).decode("utf-8"))
            time.sleep(SPACING)
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(SPACING + 1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {tries} tries: {url}\n  {last}")


def odata(entity, *, select, filt, orderby=None, top=None, skip=None, lang="DE"):
    """Every request names its fields ($select): nothing is downloaded that isn't used."""
    params = {"$format": "json", "$filter": f"Language eq '{lang}' and {filt}", "$select": select}
    if orderby:
        params["$orderby"] = orderby
    if top:
        params["$top"] = str(top)
    if skip:
        params["$skip"] = str(skip)
    data = http_get(f"{BASE}/{entity}?" + urllib.parse.urlencode(params, safe="'"))
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(data["error"].get("message", {}).get("value", "OData error"))
    d = data.get("d", [])
    return d.get("results", []) if isinstance(d, dict) else d


def epoch(s):
    m = re.search(r"(-?\d+)", s or "")
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc) if m else None


def clock(s):
    """Source times are Swiss wall-clock time encoded as UTC: keep them as HH:MM."""
    d = epoch(s)
    return d.strftime("%H:%M") if d else None


def day_bounds(d):
    nxt = d + timedelta(days=1)
    return f"datetime'{d.isoformat()}T00:00:00'", f"datetime'{nxt.isoformat()}T00:00:00'"


def clean(s, cap):
    return re.sub(r"\s+", " ", s or "").strip()[:cap]


# ---------------------------------------------------------------------------
def session_for(d):
    lo, _ = day_bounds(d)
    rows = odata("Session", select="ID,SessionName,StartDate,EndDate,Type",
                 filt=f"StartDate le {lo} and EndDate ge {lo}", top=5)
    if not rows:
        return None
    s = rows[0]
    start = epoch(s.get("StartDate"))
    return {"id": s["ID"], "year": start.year if start else d.year,
            "season": season_of(s.get("SessionName"), start.month if start else d.month, s.get("Type")),
            "start": start.date().isoformat() if start else None,
            "end": (epoch(s.get("EndDate")) or start).date().isoformat() if start else None}


def meetings_on(d):
    lo, hi = day_bounds(d)
    return odata("Meeting", select="ID,Council,Begin,Modified,IdSession",
                 filt=f"Date ge {lo} and Date lt {hi}", orderby="Begin")


def probe(session_id, d, meetings):
    """A cheap signature of the day: if none of it moved, nothing new to fetch."""
    lo, hi = day_bounds(d)
    tr = odata("Transcript", select="Modified",
               filt=f"IdSession eq '{session_id}' and MeetingDate eq '{d.strftime('%Y%m%d')}'",
               orderby="Modified desc", top=1)
    vo = odata("Vote", select="ID", filt=f"IdSession eq {session_id} and VoteEnd ge {lo} and VoteEnd lt {hi}",
               orderby="ID desc", top=1)
    return {"transcripts": (tr[0]["Modified"] if tr else None), "lastVote": (vo[0]["ID"] if vo else None),
            "meetings": sorted((str(m["ID"]), m.get("Modified")) for m in meetings)}


def agenda(meetings):
    """Agenda items per council, in the official order, with DE/FR/IT titles."""
    out = {}
    if not meetings:
        return out
    ids = " or ".join(f"IdMeeting eq {int(m['ID'])}L" for m in meetings)
    subjects = odata("Subject", select="ID,IdMeeting,SortOrder", filt=f"({ids})", top=500)
    by_meeting = {str(m["ID"]): m for m in meetings}
    business = []
    sids = [int(s["ID"]) for s in subjects]
    for n in range(0, len(sids), 25):
        chunk = " or ".join(f"IdSubject eq {i}L" for i in sids[n:n + 25])
        business += odata("SubjectBusiness",
                          select="IdSubject,BusinessNumber,BusinessShortNumber,SortOrder,PublishedNotes,TitleDE,TitleFR,TitleIT",
                          filt=f"({chunk})", top=500)
    items_by_subject = {}
    for b in sorted(business, key=lambda x: (x.get("SortOrder") or 0)):
        items_by_subject.setdefault(str(b["IdSubject"]), []).append({
            "business": clean(b.get("BusinessShortNumber"), 20),
            "businessId": b.get("BusinessNumber"),
            "title": {lg.lower(): clean(b.get("Title" + lg), 1000) for lg in LANGS if b.get("Title" + lg)},
            "note": clean(b.get("PublishedNotes"), 200) or None,
        })
    for s in sorted(subjects, key=lambda x: (by_meeting[str(x["IdMeeting"])].get("Begin") or "", x.get("SortOrder") or 0)):
        m = by_meeting[str(s["IdMeeting"])]
        c = COUNCILS.get(m.get("Council"))
        if not c:
            continue
        out.setdefault(c, []).append({"subject": int(s["ID"]), "meeting": int(m["ID"]),
                                      "items": items_by_subject.get(str(s["ID"]), [])})
    return out


def speakers(session_id, d):
    """Who spoke, when, on which item. SRC-13: the Text field is never requested."""
    rows = []
    for skip in (0, 500, 1000, 1500):                 # a long sitting day has a few hundred speeches
        page = odata("Transcript",
                     select="ID,IdSubject,SpeakerFullName,SpeakerFunction,ParlGroupAbbreviation,"
                            "CantonAbbreviation,MeetingCouncilAbbreviation,Start,End",
                     filt=f"IdSession eq '{session_id}' and MeetingDate eq '{d.strftime('%Y%m%d')}' and Type eq 1",
                     orderby="Start,ID", top=500, skip=skip)
        rows += page
        if len(page) < 500:
            break
    out = {}
    for r in rows:
        c = r.get("MeetingCouncilAbbreviation")
        name = clean(r.get("SpeakerFullName"), 80)
        if c not in ("N", "S", "V") or not name or not r.get("Start"):
            continue
        role = r.get("SpeakerFunction")
        out.setdefault(c, []).append({
            "subject": int(r["IdSubject"]) if r.get("IdSubject") else None,
            "start": clock(r.get("Start")), "end": clock(r.get("End")),
            "name": name,
            "role": role if role in ROLES else "other",
            "group": GROUP_TO_PARTY.get(r.get("ParlGroupAbbreviation")),
            "canton": clean(r.get("CantonAbbreviation"), 2) or None,
        })
    return out


def tally(vote_id):
    rows = odata("Voting", select="Decision,ParlGroupCode", filt=f"IdVote eq {int(vote_id)}", top=300)
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


def votes(session_id, d, previous):
    """Every recorded National Council vote of the day. Tallies are fetched once
    per vote; the data guard stops the job if a published one changes."""
    lo, hi = day_bounds(d)
    by_id, order = {}, []
    for lg in LANGS:
        for v in odata("Vote", select="ID,BusinessNumber,BusinessShortNumber,BillNumber,BillTitle,BusinessTitle,"
                                      "Subject,MeaningYes,MeaningNo,VoteEnd",
                       filt=f"IdSession eq {session_id} and VoteEnd ge {lo} and VoteEnd lt {hi}",
                       orderby="VoteEnd", lang=lg):
            vid = int(v["ID"])
            if vid not in by_id:
                order.append(vid)
                by_id[vid] = {"id": vid, "time": clock(v.get("VoteEnd")),
                              "business": clean(v.get("BusinessShortNumber"), 20),
                              "businessId": v.get("BusinessNumber"),
                              "bill": v.get("BillNumber") if isinstance(v.get("BillNumber"), int) else None,
                              "billTitle": {},
                              # Official text, entered once in the clerk's language (kept verbatim).
                              "subject": clean(v.get("Subject"), 200) or None,
                              "meaning": {"yes": clean(v.get("MeaningYes"), 300), "no": clean(v.get("MeaningNo"), 300)}}
            t = clean(v.get("BillTitle") or v.get("BusinessTitle"), 1000)
            if t:
                by_id[vid]["billTitle"][lg.lower()] = t
    known = {v["id"]: v for v in previous}
    fetched = 0
    out = []
    for vid in order:
        v = by_id[vid]
        old = known.get(vid)
        if old and sum(old["tally"].values()) > 0:
            v["tally"], v["byParty"] = old["tally"], old["byParty"]
        elif fetched < MAX_NEW_TALLIES:
            v["tally"], v["byParty"] = tally(vid)
            fetched += 1
        else:
            continue                                  # next run
        out.append(v)
    return out


def decisions(d):
    """The councils' official decisions on business that day (standard decision
    records only: free-text records such as judicial elections are left out)."""
    lo, hi = day_bounds(d)
    rows = {}
    for lg in LANGS:
        for r in odata("Resolution", select="ID,ResolutionId,ResolutionText,ResolutionNumber,Council,IdBill",
                       filt=f"ResolutionDate ge {lo} and ResolutionDate lt {hi} and Council ne null", lang=lg):
            if r.get("ResolutionId") is None or COUNCILS.get(r.get("Council")) not in ("N", "S"):
                continue
            e = rows.setdefault(r["ID"], {"council": COUNCILS[r["Council"]], "bill": r.get("IdBill"),
                                          "order": r.get("ResolutionNumber") or 0, "text": {}})
            txt = clean(r.get("ResolutionText"), 120)
            if txt:
                e["text"][lg.lower()] = txt
    bills = sorted({e["bill"] for e in rows.values() if e["bill"]})
    business = {}
    for n in range(0, len(bills), 20):
        chunk = " or ".join(f"ID eq guid'{b}'" for b in bills[n:n + 20] if re.fullmatch(r"[0-9a-f-]{36}", b))
        if chunk:
            for b in odata("Bill", select="ID,BusinessNumber,BusinessShortNumber,BillNumber", filt=f"({chunk})"):
                business[b["ID"]] = b
    out = []
    for e in sorted(rows.values(), key=lambda x: (x["council"], x["order"])):
        b = business.get(e["bill"])
        if not b or not e["text"]:
            continue
        out.append({"council": e["council"], "business": clean(b.get("BusinessShortNumber"), 20),
                    "businessId": b.get("BusinessNumber"), "bill": b.get("BillNumber"), "text": e["text"]})
    return out


# ---------------------------------------------------------------------------
def load(path):
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def same_content(a, b):
    strip = lambda d: {k: v for k, v in (d or {}).items() if k != "_meta"}
    return strip(a) == strip(b)


def build_day(d, session, previous, full):
    meetings = [m for m in meetings_on(d) if str(m.get("IdSession")) == str(session["id"])]
    sig = probe(session["id"], d, meetings)
    prev_meta = (previous or {}).get("_meta") or {}
    prev_at = datetime.fromisoformat(prev_meta["fetchedAt"]) if prev_meta.get("fetchedAt") else None
    if previous and not full and prev_meta.get("probe") == sig and prev_at \
            and datetime.now(timezone.utc) - prev_at < FULL_REFRESH:
        return None                                    # nothing moved
    councils = {}
    for c, items in agenda(meetings).items():
        councils.setdefault(c, {})["agenda"] = items
    for m in meetings:
        c = COUNCILS.get(m.get("Council"))
        if c:
            councils.setdefault(c, {}).setdefault("meetings", []).append(
                {"id": int(m["ID"]), "begin": f"{m['Begin'][:2]}:{m['Begin'][2:]}" if re.fullmatch(r"\d{4}", m.get("Begin") or "") else None})
    for c, rows in speakers(session["id"], d).items():
        councils.setdefault(c, {})["speeches"] = rows
    prev_votes = (((previous or {}).get("councils") or {}).get("N") or {}).get("votes") or []
    nv = votes(session["id"], d, prev_votes)
    if nv:
        councils.setdefault("N", {})["votes"] = nv
    for c in councils.values():
        for k in ("meetings", "agenda", "speeches"):
            c.setdefault(k, [])
    if "N" in councils:
        councils["N"].setdefault("votes", [])
    return {
        "_meta": {**licence_meta(f"sessions/days/{d.isoformat()}.json"),
                  "source": "Federal Assembly OData web service (ws.parlament.ch)",
                  "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  "probe": sig},
        "date": d.isoformat(),
        "session": {k: session[k] for k in ("id", "season", "year")},
        "councils": councils,
        "decisions": decisions(d),
    }


def counts(doc):
    out = {}
    for c, v in (doc.get("councils") or {}).items():
        spoken = {s["subject"] for s in v.get("speeches") or [] if s.get("subject")}
        out[c] = {"items": sum(len(a.get("items") or []) for a in v.get("agenda") or []),
                  # business items on the programme that have at least one speaker
                  "debated": sum(len(a.get("items") or []) for a in v.get("agenda") or [] if a.get("subject") in spoken),
                  "speeches": len(v.get("speeches") or []),
                  "votes": len(v.get("votes") or [])}
    return out


def write_index():
    days = []
    for p in sorted(DAYS_DIR.glob("????-??-??.json")):
        doc = load(p)
        if not doc:
            continue
        days.append({"date": doc["date"], "session": doc["session"], "fetchedAt": doc["_meta"]["fetchedAt"],
                     "counts": counts(doc), "decisions": len(doc.get("decisions") or [])})
    doc = {"_meta": {**licence_meta("sessions/days/index.json"),
                     "source": "Federal Assembly OData web service (ws.parlament.ch)"},
           "days": days}
    old = load(INDEX)
    if not old or old.get("days") != days:
        INDEX.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")


def swiss_today():
    return datetime.now(SWISS).date()


def main(argv):
    if os.environ.get("TICKER_OFF", "").lower() in ("1", "true", "yes"):
        print("TICKER_OFF is set — the session ticker is switched off (SRC-11).")
        return 0
    d = swiss_today()
    if "--date" in argv:
        val = argv[argv.index("--date") + 1] if argv.index("--date") + 1 < len(argv) else ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
            print("--date needs YYYY-MM-DD", file=sys.stderr)
            return 2
        d = date.fromisoformat(val)
    session = session_for(d)
    if "--check-session" in argv:
        sitting = bool(session and meetings_on(d))
        print(f"sitting={'true' if sitting else 'false'}")
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as f:
                f.write(f"sitting={'true' if sitting else 'false'}\n")
        return 0
    if not session:
        print(f"{d}: the Federal Assembly is not in session — nothing to fetch.")
        return 0
    if not re.fullmatch(r"\d{1,8}", str(session["id"])):
        print(f"unexpected session id {session['id']!r}", file=sys.stderr)
        return 1
    DAYS_DIR.mkdir(parents=True, exist_ok=True)
    path = DAYS_DIR / f"{d.isoformat()}.json"
    previous = load(path)
    try:
        doc = build_day(d, session, previous, full="--full" in argv or "--date" in argv)
    except Budget as e:
        print(f"{d}: stopped — {e}; the existing file is kept.", file=sys.stderr)
        return 1
    if doc is None:
        print(f"{d}: no change at parlament.ch since {previous['_meta']['fetchedAt']}.")
    elif not doc["councils"] and not doc["decisions"]:
        print(f"{d}: no sitting on this day.")
    elif previous and same_content(previous, doc):
        print(f"{d}: refreshed, nothing new.")
    else:
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", "utf-8")
        c = counts(doc)
        print(f"{d}: wrote {path.relative_to(ROOT)} — " +
              "; ".join(f"{k}: {v['items']} items, {v['speeches']} speeches, {v['votes']} votes" for k, v in c.items()) +
              f"; {len(doc['decisions'])} decisions ({requests_made} requests)")
    write_index()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
