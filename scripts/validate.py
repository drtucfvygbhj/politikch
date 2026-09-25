#!/usr/bin/env python3
"""Validate Politikch data files.

Run locally with:  python3 scripts/validate.py
Exits non-zero (and prints what's wrong) if any check fails, so it can
gate merges in CI.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LANGS = ["en", "de", "fr", "it", "rm"]
errors = []


def load(name):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"{name}: invalid JSON — {e}")
        return None


def check_parties(data):
    if not data:
        return
    parties = data.get("parties", {})
    nc = sum(p.get("ncSeats", 0) for p in parties.values())
    cs = sum(p.get("csSeats", 0) for p in parties.values())
    if nc != 200:
        errors.append(f"parties.json: National Council seats sum to {nc}, expected 200")
    if cs != 46:
        errors.append(f"parties.json: Council of States seats sum to {cs}, expected 46")
    for key, p in parties.items():
        for field in ("name", "abbr", "color", "spectrum", "website"):
            if field not in p:
                errors.append(f"parties.json: {key} missing '{field}'")
        if "en" not in p.get("name", {}):
            errors.append(f"parties.json: {key} name missing English label")
        sp = p.get("spectrum", {})
        for axis in ("x", "y"):
            v = sp.get(axis)
            if not isinstance(v, (int, float)) or not (0 <= v <= 100):
                errors.append(f"parties.json: {key} spectrum.{axis} must be 0–100")


def check_cantons(data):
    if not data:
        return
    cantons = data.get("cantons", {})
    if len(cantons) != 26:
        errors.append(f"cantons.json: expected 26 cantons, found {len(cantons)}")
    seats = sum(c.get("seats", 0) for c in cantons.values())
    if seats != 200:
        errors.append(f"cantons.json: National Council seats sum to {seats}, expected 200")
    for code, c in cantons.items():
        for field in ("name", "capital", "pop", "area", "seats", "language", "desc"):
            if field not in c:
                errors.append(f"cantons.json: {code} missing '{field}'")


def check_initiatives(data):
    if not data:
        return
    for i, init in enumerate(data.get("initiatives", [])):
        label = init.get("id", f"index {i}")
        if init.get("type") not in ("initiative", "referendum"):
            errors.append(f"initiatives.json: {label} has invalid type '{init.get('type')}'")
        if init.get("status") not in ("adopted", "rejected", "pending", "collecting", "upcoming"):
            errors.append(f"initiatives.json: {label} has invalid status '{init.get('status')}'")
        for field in ("title", "desc", "date", "url"):
            if field not in init:
                errors.append(f"initiatives.json: {label} missing '{field}'")
        if "en" not in init.get("title", {}):
            errors.append(f"initiatives.json: {label} title missing English text")


def check_financing(data, parties_data, initiatives_data):
    if not data:
        return  # financing.json is optional: absent means "show the placeholder"
    known_parties = set((parties_data or {}).get("parties", {}).keys())
    known_initiatives = {i.get("id") for i in (initiatives_data or {}).get("initiatives", [])}

    for key, entry in data.get("parties", {}).items():
        if key not in known_parties:
            errors.append(f"financing.json: party '{key}' not found in parties.json")
        for field in ("totalRevenue", "monetaryDonations", "nonMonetaryDonations"):
            v = entry.get(field)
            if not isinstance(v, (int, float)) or v < 0:
                errors.append(f"financing.json: party {key}.{field} must be a non-negative number")

    for key, sides in data.get("initiatives", {}).items():
        if key not in known_initiatives:
            errors.append(f"financing.json: initiative '{key}' not found in initiatives.json")
        for side in ("pro", "contra"):
            v = (sides.get(side) or {}).get("totalRevenue")
            if not isinstance(v, (int, float)) or v < 0:
                errors.append(f"financing.json: initiative {key}.{side}.totalRevenue must be a non-negative number")

    # GUARDRAILS.md PRIV-08: a private person's donation reveals a political
    # opinion, so an individual donor is only ever "Private individual" — the
    # data must carry no name or place for them.
    lists = [(f"parties.{k}", e.get("largeDonors")) for k, e in data.get("parties", {}).items()]
    lists += [(f"initiatives.{k}.{s}", (sides.get(s) or {}).get("largeDonors"))
              for k, sides in data.get("initiatives", {}).items() for s in ("pro", "contra")]
    for where, donors in lists:
        for d in donors or []:
            if d.get("type") != "organization" and ({"name", "location"} & d.keys()):
                errors.append(f"financing.json: {where} has a private individual with a name or place (PRIV-08)")


def check_sessions(index, parties_data):
    # sessions-index.json + data/sessions/<id>.json are optional: absent means
    # the Sessions page shows its honest "not fetched yet" empty state.
    if not index:
        return
    known_parties = set((parties_data or {}).get("parties", {}).keys())
    seasons = {"spring", "summer", "autumn", "winter", "special"}
    for i, s in enumerate(index.get("sessions", [])):
        label = s.get("id", f"index {i}")
        for field in ("id", "season", "year", "start"):
            if field not in s:
                errors.append(f"sessions-index.json: session {label} missing '{field}'")
        if s.get("season") not in seasons:
            errors.append(f"sessions-index.json: session {label} has invalid season '{s.get('season')}'")
        # Validate the per-session votes file if present.
        path = DATA / "sessions" / f"{s.get('id')}.json"
        if not path.exists():
            continue
        try:
            votes = json.loads(path.read_text(encoding="utf-8")).get("votes", [])
        except Exception as e:  # noqa: BLE001
            errors.append(f"sessions/{s.get('id')}.json: invalid JSON — {e}")
            continue
        for v in votes:
            tally = v.get("tally", {})
            for k in ("yes", "no", "abstain"):
                if not isinstance(tally.get(k), int) or tally.get(k) < 0:
                    errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} tally.{k} must be a non-negative integer")
            if not v.get("title"):
                errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} has no title")
            for pk in (v.get("byParty") or {}):
                if pk not in known_parties:
                    errors.append(f"sessions/{s.get('id')}.json: vote {v.get('id')} references unknown party '{pk}'")


def check_i18n(data):
    if not data:
        return
    for lang in LANGS:
        if lang not in data:
            errors.append(f"i18n.json: missing language '{lang}'")
    base = set(data.get("en", {}).keys())
    for lang in LANGS:
        if lang == "en" or lang not in data:
            continue
        diff = base ^ set(data[lang].keys())
        if diff:
            errors.append(f"i18n.json: '{lang}' key mismatch vs 'en': {sorted(diff)}")


# Upstream-derived files: written by the weekly fetch job from third-party
# sources (VoteInfo, LINDAS, Swissvotes, parlament.ch, EFK, BFS, DeepL) and
# published without human review. The site escapes this text, but anything that
# looks like markup or a script URL is a sign an upstream source changed or was
# tampered with — fail loudly here, before the job commits and deploys it.
UPSTREAM_FILES = [
    "initiatives.json", "financing.json", "canton-data.json",
    "sessions-index.json", "mt.json",
]
UPSTREAM_GLOBS = ["sessions/*.json", "overviews/*/*.json"]
MARKUP = re.compile(r"<\s*[a-zA-Z!/?]|javascript\s*:|\bon[a-z]+\s*=", re.I)
MAX_TEXT = 20000   # longest legitimate text today is a brochure argument (~4k)


def check_upstream_text():
    files = [DATA / f for f in UPSTREAM_FILES]
    for g in UPSTREAM_GLOBS:
        files.extend(sorted(DATA.glob(g)))

    def walk(node, where):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")
        elif isinstance(node, str):
            if MARKUP.search(node):
                errors.append(f"{where}: looks like markup/script — {node[:80]!r}")
            elif len(node) > MAX_TEXT:
                errors.append(f"{where}: unexpectedly long text ({len(node)} chars)")

    for path in files:
        if path.exists():
            walk(json.loads(path.read_text(encoding="utf-8")), path.relative_to(DATA).as_posix())


def check_all_languages():
    # Editorial and composed texts must exist in every site language, so no page
    # quietly falls back to another language (official DE/FR/IT texts and their
    # machine translations are handled separately).
    def need(obj, where):
        if not isinstance(obj, dict):
            errors.append(f"{where} must be a per-language object")
            return
        missing = [l for l in LANGS if not (obj.get(l) or "").strip()]
        if missing:
            errors.append(f"{where} is missing {missing}")
    parties = (load("parties.json") or {}).get("parties", {})
    for k, pa in parties.items():
        need(pa.get("name"), f"parties.json: {k}.name")
        need(pa.get("desc"), f"parties.json: {k}.desc")
        for i, pos in enumerate(pa.get("positions") or []):
            need(pos.get("stance"), f"parties.json: {k}.positions[{i}].stance")
    for code, c in ((load("cantons.json") or {}).get("cantons", {})).items():
        for f in ("name", "capital", "language", "desc"):
            need(c.get(f), f"cantons.json: {code}.{f}")
    for slug, dd in ((load("donor-descriptions.json") or {}).get("donors", {})).items():
        need(dd.get("desc"), f"donor-descriptions.json: {slug}.desc")
    for it in ((load("initiatives.json") or {}).get("initiatives", [])):
        for f in ("desc", "date"):
            need(it.get(f), f"initiatives.json: {it.get('id')}.{f}")


def check_argument_text():
    # Official arguments must be clean verbatim text: no page furniture (vote
    # tables, footnotes, navigation, badge links) and never one side alone.
    sys.path.insert(0, str(ROOT / "scripts"))
    from fetch_arguments import FURNITURE, BADGE_LINK  # same rules as the fetcher
    for path in sorted((DATA / "overviews").rglob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        rel = path.relative_to(DATA).as_posix()
        for lang, block in (d.get("lang") or {}).items():
            if bool(block.get("pros")) != bool(block.get("cons")):
                errors.append(f"{rel}: {lang} has only one side (POL-01)")
            for side in ("pros", "cons"):
                for i, para in enumerate(block.get(side) or []):
                    if FURNITURE.search(para) or BADGE_LINK.search(para):
                        errors.append(f"{rel}: {lang}.{side}[{i}] contains page layout, not argument text")


def check_mt_args(data):
    # GUARDRAILS.md POL-01: a machine-translated argument set always carries both
    # sides; one side must never be published translated on its own.
    for iid, by_lang in (data or {}).get("args", {}).items():
        if not isinstance(by_lang, dict):
            errors.append(f"mt.json: args.{iid} must map language -> {{pros, cons}}")
            continue
        for tl, e in by_lang.items():
            if tl not in ("en", "it"):
                errors.append(f"mt.json: args.{iid}.{tl} is not a supported target language")
            if not (isinstance(e, dict) and e.get("pros") and e.get("cons")):
                errors.append(f"mt.json: args.{iid}.{tl} must have both pros and cons (POL-01)")


def main():
    parties_data = load("parties.json")
    initiatives_data = load("initiatives.json")
    check_parties(parties_data)
    check_cantons(load("cantons.json"))
    check_initiatives(initiatives_data)
    check_i18n(load("i18n.json"))
    check_all_languages()
    check_argument_text()

    financing_path = DATA / "financing.json"
    if financing_path.exists():
        check_financing(load("financing.json"), parties_data, initiatives_data)

    if (DATA / "sessions-index.json").exists():
        check_sessions(load("sessions-index.json"), parties_data)

    if (DATA / "mt.json").exists():
        check_mt_args(load("mt.json"))

    check_upstream_text()

    if errors:
        print("Validation FAILED:\n")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    print("All data checks passed ✓")


if __name__ == "__main__":
    main()
