#!/usr/bin/env python3
"""Fetch official party & campaign financing disclosures from the EFK.

Source: the Federal Audit Office's (EFK) public "Politikfinanzierung" register
(https://politikfinanzierung.efk.admin.ch), published under Switzerland's
political-financing transparency law (BPR/VPofi, in force since 2023) and
listed as "open use" data on opendata.swiss. This script reads the same
public, unauthenticated JSON/XLSX endpoints the register's own web app uses;
it does not bypass any access control.

This is a build-time fetch, not a runtime one: the register's API sends no
CORS headers, so a browser cannot read it directly. Run this script
(in CI or locally) to refresh data/financing.json, which the static site then
loads like any other same-origin JSON file — no server needed at request time.

Usage:
  pip install openpyxl
  python3 scripts/fetch_financing.py

If a party or initiative isn't found on the register (e.g. no recent filing,
or a vote that predates the law), it's simply omitted from the output — the
site falls back to its "see official register" placeholder for whatever is
missing, rather than showing a wrong or invented figure.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("This script needs openpyxl: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://politikfinanzierung.efk.admin.ch"
UA = (
    "Politikch-data-fetcher/1.0 "
    "(non-commercial civic-education site; contact via github.com/politikch)"
)
REQUEST_DELAY_SECONDS = 0.5
MAX_DONORS_SHOWN = 8

# Stable actor IDs on the EFK register, matched by hand to this site's party
# keys (matched via the actors' registered names in the party_financings tree).
PARTY_ACTOR_IDS = {
    42: "SVP", 8: "SP", 59: "MITTE", 43: "FDP", 9: "GPS",
    33: "GLP", 219: "EVP", 331: "EDU", 394: "LEGA", 268: "MCG",
}

# Stable campaign_financing root IDs, matched by hand to this site's
# initiative ids (data/initiatives.json). "ahv-21" (voted 2022) predates the
# 4 March 2023 start of the vote-campaign disclosure duty, so it has no
# corresponding register entry and is intentionally left out.
INITIATIVE_ROOT_IDS = {
    "13th-ahv": 3,
    "pension-age": 4,
    "cost-brake": 6,
    "electricity-act": 8,
    "biodiversity": 10,
}

FINAL_REVENUE_LABEL = "Offenlegung der Schlussrechnung über die Einnahmen"
BUDGET_REVENUE_LABEL = "Offenlegung der budgetierten Einnahmen"
FINAL_DONORS_LABEL = "Offenlegung von Zuwendungen über 15 000 Franken (Schlussrechnung)"
BUDGET_DONORS_LABEL = "Offenlegung von Zuwendungen über 15 000 Franken"
PARTY_DONORS_LABEL = "Offenlegung von Zuwendungen über 15 000 Franken"


def http_get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_json(path):
    return json.loads(http_get(path))


def fetch_workbook(download_path):
    time.sleep(REQUEST_DELAY_SECONDS)
    data = http_get(download_path)
    return openpyxl.load_workbook(BytesIO(data), data_only=True)


def find_form(forms, label):
    for f in forms:
        if f["label"] == label:
            return f
    return None


def parse_party_revenue(campaign_id, form_id):
    wb = fetch_workbook(f"/api/frontend/latest/de/downloads/campaigns/{campaign_id}/forms/{form_id}")
    ws = wb["Parteifinanzierung"]
    row = next(r for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0])
    return {
        "year": int(row[0]),
        "totalRevenue": row[4] or 0,
        "monetaryDonations": row[5] or 0,
        "nonMonetaryDonations": row[6] or 0,
        "events": row[7] or 0,
        "sales": row[8] or 0,
        "membershipFees": row[9] or 0,
        "mandateFees": row[10] or 0,
    }


def parse_donors_sheet(wb, natural_sheet, legal_sheet):
    donors = []
    if natural_sheet in wb.sheetnames:
        for r in wb[natural_sheet].iter_rows(min_row=2, values_only=True):
            if not r or not r[0]:
                continue
            # natural-person sheets: ...name, first name, municipality, ..., amount, date (last 4 cols)
            name, first, muni, _, amount, date = r[-6], r[-5], r[-4], r[-3], r[-2], r[-1]
            donors.append({
                "name": f"{first} {name}".strip(),
                "type": "individual",
                "location": muni,
                "amount": amount or 0,
                "date": date.date().isoformat() if hasattr(date, "date") else None,
            })
    if legal_sheet in wb.sheetnames:
        for r in wb[legal_sheet].iter_rows(min_row=2, values_only=True):
            if not r or not r[0]:
                continue
            firm, muni, amount, date = r[-4], r[-3], r[-2], r[-1]
            donors.append({
                "name": firm,
                "type": "organization",
                "location": muni,
                "amount": amount or 0,
                "date": date.date().isoformat() if hasattr(date, "date") else None,
            })
    donors.sort(key=lambda d: d["amount"], reverse=True)
    return donors[:MAX_DONORS_SHOWN]


def parse_party_donors(campaign_id, form_id):
    wb = fetch_workbook(f"/api/frontend/latest/de/downloads/campaigns/{campaign_id}/forms/{form_id}")
    return parse_donors_sheet(wb, "Natürliche P. | monetär", "Juristische P. | monetär")


def parse_campaign_revenue(campaign_id, form_id):
    wb = fetch_workbook(f"/api/frontend/latest/de/downloads/campaigns/{campaign_id}/forms/{form_id}")
    ws = wb["Export"]
    row = next(r for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0])
    return {
        "totalRevenue": row[6] or 0,
        "monetaryDonations": row[7] or 0,
        "nonMonetaryDonations": row[8] or 0,
        "events": row[9] or 0,
        "sales": row[10] or 0,
        "ownFunds": row[11] or 0,
    }


def parse_campaign_donors(campaign_id, form_id):
    wb = fetch_workbook(f"/api/frontend/latest/de/downloads/campaigns/{campaign_id}/forms/{form_id}")
    return parse_donors_sheet(wb, "Natürliche P. | monetär", "Juristische P. | monetär")


def fetch_parties():
    print("Fetching party financing tree...")
    tree = fetch_json("/api/frontend/v1/search/party_financings")
    roots = tree["data"]["tree_roots"]
    latest_year_root = max(roots, key=lambda r: int(r["label"]))
    print(f"  latest year: {latest_year_root['label']}")

    result = {}
    for actor in latest_year_root["children"]:
        party_key = PARTY_ACTOR_IDS.get(actor["id"])
        if not party_key:
            continue
        revenue_form = find_form(actor["children"], "Offenlegung der jährlichen Einnahmen")
        if not revenue_form:
            continue
        try:
            entry = parse_party_revenue(revenue_form["campaign_id"], revenue_form["id"])
        except Exception as e:  # noqa: BLE001
            print(f"  ! {party_key}: revenue fetch failed: {e}", file=sys.stderr)
            continue

        donors_form = find_form(actor["children"], PARTY_DONORS_LABEL)
        entry["largeDonors"] = []
        if donors_form:
            try:
                entry["largeDonors"] = parse_party_donors(donors_form["campaign_id"], donors_form["id"])
            except Exception as e:  # noqa: BLE001
                print(f"  ! {party_key}: donors fetch failed: {e}", file=sys.stderr)

        result[party_key] = entry
        print(f"  ok {party_key}: CHF {entry['totalRevenue']:,.0f} ({len(entry['largeDonors'])} large donors)")
    return result


def side_for_campaign_label(label):
    if label.startswith("Annahme"):
        return "pro"
    if label.startswith("Ablehnung"):
        return "contra"
    return None


def fetch_initiatives():
    print("Fetching campaign (vote) financing tree...")
    tree = fetch_json("/api/frontend/v1/search/campaign_financings")
    roots = {r["id"]: r for r in tree["data"]["tree_roots"]}

    result = {}
    for init_id, root_id in INITIATIVE_ROOT_IDS.items():
        root = roots.get(root_id)
        if not root:
            print(f"  ! {init_id}: root {root_id} not found", file=sys.stderr)
            continue

        sides = {
            "pro": {"totalRevenue": 0, "actorCount": 0, "largeDonors": []},
            "contra": {"totalRevenue": 0, "actorCount": 0, "largeDonors": []},
        }
        for category in root["children"]:
            for actor in category["children"]:
                for campaign in actor["children"]:
                    side = side_for_campaign_label(campaign["label"])
                    if side is None:
                        continue
                    forms = campaign["children"]
                    revenue_form = find_form(forms, FINAL_REVENUE_LABEL) or find_form(forms, BUDGET_REVENUE_LABEL)
                    if not revenue_form:
                        continue
                    try:
                        rev = parse_campaign_revenue(revenue_form["campaign_id"], revenue_form["id"])
                    except Exception as e:  # noqa: BLE001
                        print(f"  ! {init_id}/{actor['label']}: revenue fetch failed: {e}", file=sys.stderr)
                        continue
                    sides[side]["totalRevenue"] += rev["totalRevenue"]
                    sides[side]["actorCount"] += 1

                    donors_form = find_form(forms, FINAL_DONORS_LABEL) or find_form(forms, BUDGET_DONORS_LABEL)
                    if donors_form:
                        try:
                            sides[side]["largeDonors"].extend(
                                parse_campaign_donors(donors_form["campaign_id"], donors_form["id"])
                            )
                        except Exception as e:  # noqa: BLE001
                            print(f"  ! {init_id}/{actor['label']}: donors fetch failed: {e}", file=sys.stderr)

        for side in sides.values():
            side["largeDonors"].sort(key=lambda d: d["amount"], reverse=True)
            side["largeDonors"] = side["largeDonors"][:MAX_DONORS_SHOWN]

        result[init_id] = sides
        print(
            f"  ok {init_id}: pro CHF {sides['pro']['totalRevenue']:,.0f} "
            f"({sides['pro']['actorCount']} actors), "
            f"contra CHF {sides['contra']['totalRevenue']:,.0f} "
            f"({sides['contra']['actorCount']} actors)"
        )
    return result


def main():
    try:
        parties = fetch_parties()
        initiatives = fetch_initiatives()
    except urllib.error.URLError as e:
        print(f"Network error reaching the EFK register: {e}", file=sys.stderr)
        print("Keeping any existing data/financing.json unchanged.", file=sys.stderr)
        sys.exit(1)

    output = {
        "_meta": {
            "source": "Federal Audit Office (EFK) — https://politikfinanzierung.efk.admin.ch",
            "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": (
                "Figures are self-reported by parties and campaign committees under "
                "Swiss law (BPR/VPofi) and republished here as-is; the EFK does not "
                "guarantee their accuracy, and neither do we."
            ),
        },
        "parties": parties,
        "initiatives": initiatives,
    }

    out_path = ROOT / "data" / "financing.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} ({len(parties)} parties, {len(initiatives)} initiatives)")


if __name__ == "__main__":
    main()
