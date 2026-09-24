#!/usr/bin/env python3
"""Stop the weekly data job from publishing a suspicious refresh (GUARDRAILS.md OPS-04).

Runs in .github/workflows/fetch-financing.yml after the fetchers and before the
commit. Compares the freshly fetched data files (working tree) with the
published ones (HEAD). A refresh that looks like a broken or tampered upstream
source is refused, so nothing is published without a person looking:

  * a data file shrinks by more than 20 %, disappears, or stops being valid JSON;
  * a decided federal vote disappears or its result or outcome changes;
  * fewer sessions, parties, campaigns, cantons or machine translations than before;
  * a settled session's (ended > 60 days ago) vote tallies change;
  * an official for/against argument file or one of its languages disappears.

Legitimate changes (e.g. an official correction of a result) are published by
re-running the workflow by hand with "allow_data_changes" ticked, after checking
the change against the official source.

Exit 0 = safe to publish; 1 = refused (reasons printed).
"""
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHRINK_LIMIT = 0.20
SETTLED_DAYS = 60

problems = []


def head(rel):
    r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def now(rel):
    p = ROOT / rel
    return p.read_text("utf-8") if p.exists() else None


def load(text, rel, when):
    try:
        return json.loads(text)
    except Exception as e:  # noqa: BLE001
        problems.append(f"{rel}: {when} version is not valid JSON ({e})")
        return None


def generated_files():
    files = ["data/initiatives.json", "data/financing.json", "data/canton-data.json",
             "data/sessions-index.json", "data/mt.json"]
    listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", "data/sessions", "data/overviews"],
                            cwd=ROOT, capture_output=True, text=True).stdout.split()
    return files + [f for f in listed if f.endswith(".json")]


def check_sizes_and_presence():
    for rel in generated_files():
        old, new = head(rel), now(rel)
        if old is None:
            continue                                  # new file: nothing to compare
        if new is None:
            problems.append(f"{rel}: published file would be deleted")
            continue
        if len(new) < len(old) * (1 - SHRINK_LIMIT):
            problems.append(f"{rel}: shrinks from {len(old):,} to {len(new):,} bytes (> {SHRINK_LIMIT:.0%})")
        load(new, rel, "new")


def pair(rel):
    old, new = head(rel), now(rel)
    if old is None or new is None:
        return None, None
    return load(old, rel, "published"), load(new, rel, "new")


def check_votes():
    old, new = pair("data/initiatives.json")
    if not old or not new:
        return
    new_by_id = {i["id"]: i for i in new.get("initiatives", [])}
    for i in old.get("initiatives", []):
        if i.get("status") not in ("adopted", "rejected"):
            continue
        n = new_by_id.get(i["id"])
        if n is None:
            problems.append(f"initiatives.json: decided vote {i['id']} disappeared")
        elif n.get("status") != i.get("status"):
            problems.append(f"initiatives.json: {i['id']} result changed from {i.get('status')} to {n.get('status')}")
        elif n.get("outcome") != i.get("outcome"):
            problems.append(f"initiatives.json: {i['id']} outcome changed "
                            f"({(i.get('outcome') or {}).get('en')} -> {(n.get('outcome') or {}).get('en')})")


def check_counts():
    def count(rel, fn):
        old, new = pair(rel)
        if old is None or new is None:
            return
        a, b = fn(old), fn(new)
        if b < a:
            problems.append(f"{rel}: count dropped from {a} to {b}")
    count("data/sessions-index.json", lambda d: len(d.get("sessions", [])))
    count("data/financing.json", lambda d: len(d.get("parties", {})))
    count("data/financing.json", lambda d: len(d.get("initiatives", {})))
    count("data/canton-data.json", lambda d: len(d.get("cantons", {})))
    count("data/mt.json", lambda d: sum(len(d.get(k, {})) for k in ("titles", "summaries"))
          + sum(len(v) for v in d.get("args", {}).values()))


def check_settled_sessions():
    cutoff = (date.today() - timedelta(days=SETTLED_DAYS)).isoformat()
    idx = load(now("data/sessions-index.json") or "{}", "data/sessions-index.json", "new") or {}
    for s in idx.get("sessions", []):
        if (s.get("end") or "9999") >= cutoff:
            continue
        rel = f"data/sessions/{s['id']}.json"
        old, new = pair(rel)
        if not old or not new:
            continue
        new_votes = {v["id"]: v for v in new.get("votes", [])}
        for v in old.get("votes", []):
            n = new_votes.get(v["id"])
            if n is None:
                problems.append(f"{rel}: vote {v['id']} of a settled session disappeared")
            elif n.get("tally") != v.get("tally") or n.get("passed") != v.get("passed"):
                problems.append(f"{rel}: vote {v['id']} of a settled session changed its result")


def check_overviews():
    listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", "HEAD", "data/overviews"],
                            cwd=ROOT, capture_output=True, text=True).stdout.split()
    for rel in listed:
        if not rel.endswith(".json"):
            continue
        old, new = pair(rel)
        if old and new:
            gone = set(old.get("lang", {})) - set(new.get("lang", {}))
            if gone:
                problems.append(f"{rel}: official argument language(s) removed: {sorted(gone)}")


def main():
    check_sizes_and_presence()
    check_votes()
    check_counts()
    check_settled_sessions()
    check_overviews()
    allowed = os.environ.get("ALLOW_DATA_CHANGES", "").lower() == "true"
    if not problems:
        print("Data guard: refresh looks normal ✓")
        return 0
    head_line = ("Data guard: publishing ANYWAY (allow_data_changes was ticked)"
                 if allowed else "Data guard: refusing to publish this refresh")
    print(head_line + ":")
    for p in problems:
        print(f"  ✗ {p}")
        print(f"::{'warning' if allowed else 'error'}::{p}")
    if not allowed:
        print("\nCheck these against the official source. If they are genuine, re-run the "
              "'Fetch live data' workflow by hand with 'allow_data_changes' ticked.")
    return 0 if allowed else 1


if __name__ == "__main__":
    sys.exit(main())
