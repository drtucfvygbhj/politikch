#!/usr/bin/env python3
"""Site version for Politikch (data/version.json). The scheme is in VERSIONING.md.

Every change adds the value of each type it contains, each type counted once:

    python3 scripts/version.py show
    python3 scripts/version.py bump gui fix --note "Footer spacing, broken link"
    python3 scripts/version.py types

The version is a plain decimal number that only grows (1.1 -> 1.1014 -> ...);
it is not semver and has nothing to do with the design names "1.0" / "1.1"
that js/design.js and the admin switch between. The automatic data job and the
session ticker do not bump it. Standard library only.
"""

import argparse
import datetime
import json
import os
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "version.json")

# Steps are counted in ten-thousandths, so sums never pick up float error.
SCALE = 10000
TYPES = {
    "text":    (1,    "Text or translation fix (typo, wording, translation correction)"),
    "data":    (3,    "Data or link fix (fetcher bug, wrong or better link target)"),
    "fix":     (5,    "Bug fix (something broken on the site)"),
    "gui":     (10,   "Interface tweak (layout, styling, small UI element)"),
    "rules":   (10,   "Rules, privacy or legal change (guardrails, privacy or legal text)"),
    "content": (20,   "New content (glossary entries, new data on an existing page)"),
    "feature": (50,   "New feature (new page, tool or data source)"),
    "major":   (200,  "Major feature (e.g. the session ticker, the PolitikCH+ launch)"),
    "design":  (1000, "New design version (like 1.0 -> 1.1)"),
}


def to_units(version):
    whole, _, frac = version.partition(".")
    if not whole.isdigit() or not frac.isdigit() or len(frac) > 4:
        raise ValueError(f"not a version: {version!r}")
    return int(whole) * SCALE + int(frac.ljust(4, "0"))


def to_text(units):
    whole, frac = divmod(units, SCALE)
    return f"{whole}.{(f'{frac:04d}'.rstrip('0') or '0')}"


def load():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def save(doc):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="print the current version")
    sub.add_parser("types", help="list the update types and what each adds")
    b = sub.add_parser("bump", help="add one change to the version")
    b.add_argument("types", nargs="+", metavar="TYPE", help=", ".join(TYPES))
    b.add_argument("--note", default="", help="one line on what changed")
    args = ap.parse_args()

    if args.cmd == "types":
        for key, (units, label) in TYPES.items():
            print(f"  {key:<8} +{units / SCALE:.4f}  {label}")
        return 0

    doc = load()
    if args.cmd == "show":
        print(doc["version"])
        return 0

    unknown = [t for t in args.types if t not in TYPES]
    if unknown:
        print(f"Unknown type(s): {', '.join(unknown)}. Known: {', '.join(TYPES)}", file=sys.stderr)
        return 2
    types = list(dict.fromkeys(args.types))  # each type counted once
    old = doc["version"]
    new = to_text(to_units(old) + sum(TYPES[t][0] for t in types))
    doc["version"] = new
    doc.setdefault("history", []).append({
        "version": new,
        "date": datetime.datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat(),
        "types": types,
        "note": args.note,
    })
    save(doc)
    print(f"{old} -> {new}  ({' + '.join(types)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
