#!/usr/bin/env python3
"""Validate Politikch data files.

Run locally with:  python3 scripts/validate.py
Exits non-zero (and prints what's wrong) if any check fails, so it can
gate merges in CI.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LANGS = ["en", "de", "fr", "it"]
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
        if init.get("status") not in ("adopted", "rejected", "pending", "collecting"):
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


def main():
    parties_data = load("parties.json")
    initiatives_data = load("initiatives.json")
    check_parties(parties_data)
    check_cantons(load("cantons.json"))
    check_initiatives(initiatives_data)
    check_i18n(load("i18n.json"))

    financing_path = DATA / "financing.json"
    if financing_path.exists():
        check_financing(load("financing.json"), parties_data, initiatives_data)

    if errors:
        print("Validation FAILED:\n")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    print("All data checks passed ✓")


if __name__ == "__main__":
    main()
