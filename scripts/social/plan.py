"""The weekly planner: which posts go out when, from Monday's data.

Run on a Monday after the data job. It lists the week's events by priority,
gives each a time slot, and fills the empty days with evergreen posts in a
strict order. Every account (DE/FR/IT/EN) gets the same posts at the same time.

Priorities (GUARDRAILS.md §13.1c; the canvas legend):
  5 results · 4 ballot run-up · 3 initiatives & referendums · 2 Parliament · 1 evergreen
Corrections are not planned; they go out on their own, at once.

Run-up, for a ballot on Sunday B (the official documents come out about six
weeks before):  B-41 overview + Yes/No pages (Mon) · B-34 recommendations (Tue) ·
B-27 arguments (Wed) · B-20 campaign money (Thu) · B-6 reminder (Mon).
Quiet period (POL-09): in the 10 days before B only the reminder goes out for B.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import cards
import sitedata as sd

WEEKDAY_SLOTS = ["07:30", "12:15"]
WEEKEND_SLOTS = ["10:00"]
QUIET_DAYS = 10
COOLDOWN = {"how": 182, "party": 182, "glossary": 365, "canton": 365, "history": 300}
# At most this many posts of one evergreen kind per week, so a quiet week doesn't
# become six party cards in a row; the strict order then moves to the next kind.
WEEKLY_CAP = {"final_vote": 4, "how": 2, "party": 2, "glossary": 2, "canton": 2, "history": 2}
HOW_TOPICS = ["doubleMajority"]


@dataclass
class Item:
    type: str
    priority: int
    day: dt.date
    key: str
    args: dict = field(default_factory=dict)


@dataclass
class Slot:
    day: dt.date
    time: str
    item: Item


def week_days(monday):
    return [monday + dt.timedelta(days=i) for i in range(7)]


def slots_for(day):
    return WEEKEND_SLOTS if day.weekday() >= 5 else WEEKDAY_SLOTS


# ---------------------------------------------------------------- events
def ballots():
    """{date: [votes in data order]} for every federal ballot day in the data."""
    out = {}
    for v in sd.site()["initiatives"]["initiatives"]:
        d = sd.vote_date(v)
        if d and (v.get("voteDate") or v["status"] in ("adopted", "rejected")):
            out.setdefault(d, []).append(v)
    return out


def events(monday, state):
    days, sunday = week_days(monday), monday + dt.timedelta(days=6)
    items = []
    B = ballots()
    # 5 · results of yesterday's ballot
    yesterday = monday - dt.timedelta(days=1)
    decided = [v for v in B.get(yesterday, []) if sd.outcome(v, "en")[1] is not None]
    if decided and len(decided) == len(B.get(yesterday, [])):
        items.append(Item("results", 5, monday, f"results:{yesterday}", {"votes": [v["id"] for v in decided]}))
    # 4 · ballot run-up
    for ballot, votes in sorted(B.items()):
        ids = [v["id"] for v in votes]
        steps = {41: ("runup_overview", 0, {"sunday": False}), 34: ("runup_recs", 1, {}),
                 27: ("runup_args", 2, {}), 20: ("runup_money", 3, {}), 6: ("runup_overview", 0, {"sunday": True})}
        for before, (typ, offset, extra) in steps.items():
            if ballot - dt.timedelta(days=before) == monday:
                day = monday + dt.timedelta(days=offset)
                items.append(Item(typ, 4, day, f"{typ}:{ballot}:{before}", {"ballot": ballot, "votes": ids, **extra}))
    # 3 · spotlight at 100 days left, for every collecting initiative and referendum
    for v in sd.site()["initiatives"]["initiatives"]:
        if v["status"] == "collecting" and v.get("deadline"):
            on = dt.date.fromisoformat(v["deadline"]) - dt.timedelta(days=100)
            if monday <= on <= sunday:
                items.append(Item("spotlight", 3, on, f"spotlight:{v['id']}", {"vote": v["id"], "on": on}))
    # 3 · monthly pipeline on the first Friday of the month
    friday = monday + dt.timedelta(days=4)
    if friday.day <= 7:
        items.append(Item("pipeline", 3, friday, f"pipeline:{friday:%Y-%m}", {"on": friday}))
    # 2 · session summary on the Tuesday after a session ends
    for sess in sd.site()["sessionsIndex"]["sessions"]:
        end = dt.date.fromisoformat(sess["end"])
        if monday - dt.timedelta(days=7) <= end < monday and sess.get("voteCount"):
            items.append(Item("session_summary", 2, monday + dt.timedelta(days=1), f"session:{sess['id']}", {"session": sess["id"]}))
    # 2 · seats changed (only when they do)
    now = {k: p.get("ncSeats", 0) for k, p in sd.site()["parties"]["parties"].items()}
    before = state.get("seats")
    if before and before != now:
        changes = {k: (before.get(k, 0), n) for k, n in now.items() if before.get(k, 0) != n}
        items.append(Item("seats", 2, monday + dt.timedelta(days=2), f"seats:{monday}", {"changes": changes}))
    state["seats"] = now
    # POL-09: in the 10 days before a ballot, only the reminder goes out about it
    kept = []
    for it in items:
        b = it.args.get("ballot")
        if b and 0 < (b - it.day).days <= QUIET_DAYS and not (it.type == "runup_overview" and it.args.get("sunday")):
            continue
        kept.append(it)
    return kept


# ---------------------------------------------------------------- evergreen
def _fresh(key, day, posted, days):
    last = posted.get(key)
    return last is None or (day - dt.date.fromisoformat(last)).days >= days


def evergreen(day, posted, used=None):
    """The highest-ranked evergreen post that is due (strict fill order).
    `used` counts this week's evergreen posts by kind (WEEKLY_CAP)."""
    used = used or {}
    ok = lambda kind: used.get(kind, 0) < WEEKLY_CAP[kind]   # noqa: E731
    # 1 · final-vote spotlights of the last session, in the official order, until the next session starts
    sessions = sorted(sd.site()["sessionsIndex"]["sessions"], key=lambda s: s["end"])
    past = [s for s in sessions if dt.date.fromisoformat(s["end"]) < day and s.get("voteCount")]
    nxt = [s for s in sessions if dt.date.fromisoformat(s["start"]) > dt.date.fromisoformat(past[-1]["end"])] if past else []
    # (only after the session summary is out, so the spotlights follow the overview)
    summary_on = posted.get(f"session:{past[-1]['id']}") if past else None
    if ok("final_vote") and past and summary_on and summary_on < day.isoformat() \
            and not (nxt and dt.date.fromisoformat(nxt[0]["start"]) <= day):
        sess = past[-1]
        votes = sd.session(sess["id"])["votes"]
        for n, v in enumerate(votes, 1):
            k = f"finalvote:{v['id']}"
            if k not in posted:
                return Item("final_vote", 1, day, k, {"session": sess["id"], "vote": v["id"], "n": n, "total": len(votes)})
    # 2 · how it works
    for t in HOW_TOPICS if ok("how") else []:
        if _fresh(f"how:{t}", day, posted, COOLDOWN["how"]):
            return Item("how", 1, day, f"how:{t}", {"topic": t})
    # 3 · party in figures, by seats
    for k in sd.parties_by_seats() if ok("party") else []:
        if _fresh(f"party:{k}", day, posted, COOLDOWN["party"]):
            return Item("party", 1, day, f"party:{k}", {"party": k})
    # 4 · glossary terms the editor has explained in every language
    for t in sd.site()["glossary"]["terms"] if ok("glossary") else []:
        if all(sd.gloss_text(t, l) for l in sd.LANGS) and _fresh(f"glossary:{t['id']}", day, posted, COOLDOWN["glossary"]):
            return Item("glossary", 1, day, f"glossary:{t['id']}", {"term": t["id"]})
    # 5 · canton profiles
    for n, code in enumerate(sd.site()["cantons"]["cantons"] if ok("canton") else [], 1):
        if _fresh(f"canton:{code}", day, posted, COOLDOWN["canton"]):
            return Item("canton", 1, day, f"canton:{code}", {"canton": code, "n": n})
    # 6 · from the vote history: a ballot day whose anniversary falls this week
    monday = day - dt.timedelta(days=day.weekday())
    for bday, votes in sorted(ballots().items()) if ok("history") else []:
        if bday.year >= day.year:
            continue
        try:
            anniv = bday.replace(year=day.year)
        except ValueError:
            continue
        if monday <= anniv <= monday + dt.timedelta(days=6) and all(sd.outcome(v, "en")[1] is not None for v in votes) \
                and _fresh(f"history:{bday}", day, posted, COOLDOWN["history"]):
            return Item("history", 1, day, f"history:{bday}", {"day": bday, "votes": [v["id"] for v in votes], "years": day.year - bday.year})
    return None


# ---------------------------------------------------------------- the week
def plan_week(monday, state, extra=()):
    """The week's slots. `extra` = same-day items (daily votes, a correction)."""
    assert monday.weekday() == 0, "the planner runs for a week starting on Monday"
    posted = dict(state.get("posted", {}))
    taken, slots = set(), []
    planned = list(events(monday, state))
    evs = sorted(planned + list(extra), key=lambda i: (i.day, -i.priority))
    for it in evs:
        for day in [d for d in week_days(monday) if d >= it.day]:
            free = [t for t in (it.args.get("times") or slots_for(day)) if (day, t) not in taken]
            if free:
                taken.add((day, free[0]))
                slots.append(Slot(day, free[0], it))
                posted[it.key] = day.isoformat()
                break
    quiet = len(planned) <= 1      # same-day posts (daily votes, corrections) don't make a week busy
    used = {}
    for day in week_days(monday):
        if day.weekday() < 4 and not quiet:
            continue
        first = slots_for(day)[0]
        if (day, first) in taken:
            continue
        it = evergreen(day, posted, used) or evergreen(day, posted)   # caps reached everywhere: ignore them
        if it:
            taken.add((day, first))
            slots.append(Slot(day, first, it))
            posted[it.key] = day.isoformat()
            used[it.type] = used.get(it.type, 0) + 1
    state["posted"] = posted
    return sorted(slots, key=lambda s: (s.day, s.time))


def build(item, lang):
    """The Post(s) for one slot in one language: (instagram, x)."""
    a, V = item.args, sd.site()["votes"]
    t = item.type
    if t == "results":
        votes = [V[i] for i in a["votes"]]
        return cards.results(votes, lang), cards.results_x(votes, lang)
    if t in ("runup_overview", "runup_recs", "runup_args", "runup_money"):
        votes = [V[i] for i in a["votes"]]
        fn = getattr(cards, t)
        post = fn(a["ballot"], votes, lang, sunday=a["sunday"]) if t == "runup_overview" else fn(a["ballot"], votes, lang)
        return post, None
    if t == "spotlight":
        return cards.spotlight(V[a["vote"]], a["on"], lang), None
    if t == "pipeline":
        return cards.pipeline(a["on"], lang), None
    if t == "session_summary":
        sess = next(s for s in sd.site()["sessionsIndex"]["sessions"] if s["id"] == a["session"])
        return cards.session_summary(sess, lang), None
    if t == "seats":
        return cards.seats_changed(a["changes"], lang), None
    if t == "final_vote":
        sess = next(s for s in sd.site()["sessionsIndex"]["sessions"] if s["id"] == a["session"])
        v = next(x for x in sd.session(a["session"])["votes"] if x["id"] == a["vote"])
        return cards.final_vote(sess, v, a["n"], a["total"], lang), None
    if t == "how":
        return cards.how_double_majority(lang), None
    if t == "party":
        return cards.party(a["party"], lang), None
    if t == "glossary":
        term = next(x for x in sd.site()["glossary"]["terms"] if x["id"] == a["term"])
        return cards.glossary(term, lang), None
    if t == "canton":
        return cards.canton(a["canton"], a["n"], lang), None
    if t == "history":
        return cards.history(a["day"], [V[i] for i in a["votes"]], a["years"], lang), None
    if t == "daily_votes":
        return cards.daily_votes(a["day"], lang), None
    if t == "correction":
        return cards.correction(a["info"], lang), None
    raise ValueError(f"unknown post type {t}")


def x_text(post):
    """The post text for X: first caption line and the link, within 280 characters (a link counts 23)."""
    first = post.caption.split("\n", 1)[0]
    room = 280 - 23 - 1
    return (first if len(first) <= room else first[: room - 1] + "…") + "\n" + post.url
