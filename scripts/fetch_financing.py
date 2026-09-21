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
import re
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
    "(+https://politikch.ch; contact.form@politikch.ch)"
)
REQUEST_DELAY_SECONDS = 0.5
MAX_DONORS_SHOWN = 8

# Stable actor IDs on the EFK register, matched by hand to this site's party
# keys (matched via the actors' registered names in the party_financings tree).
PARTY_ACTOR_IDS = {
    42: "SVP", 8: "SP", 59: "MITTE", 43: "FDP", 9: "GPS",
    33: "GLP", 219: "EVP", 331: "EDU", 394: "LEGA", 268: "MCG",
}

# Campaign financing is no longer matched to a hand-maintained list of root IDs.
# Instead every vote-campaign root on the register is discovered automatically
# and matched to a decided vote in data/initiatives.json by ballot date + title,
# so the moment the register publishes filings for a new voting day, the next run
# picks them up. Election-campaign roots (National Council / Council of States
# seats) are skipped — the site tracks vote financing, not candidate financing.
ELECTION_LABEL_MARKERS = ("nationalratswahl", "ständeratswahl", "standeratswahl")

# Vote-campaign disclosure only began on 4 March 2023, so ballots before then
# have no register entry and simply won't match — they fall back to the site's
# "see official register" placeholder.

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


_STOPWORDS = {
    "der", "die", "das", "und", "für", "vom", "von", "über", "eine", "einer",
    "einen", "des", "den", "dem", "zur", "zum", "mit", "auf", "bundesgesetz",
    "bundesbeschluss", "änderung", "volksinitiative", "initiative", "september",
    "dezember", "juni", "märz", "januar", "februar", "vice", "eidgenössische",
}


def _tokens(text):
    text = re.sub(r"[«»'\"“”()–—\-.,!?:;]", " ", text.lower())
    return {w for w in text.split() if len(w) > 3 and w not in _STOPWORDS and not w.isdigit()}


def _root_date_and_title(label):
    """EFK root labels look like 'DD.MM.YYYY <title>'. Split them."""
    m = re.match(r"\s*(\d{2})\.(\d{2})\.(\d{4})\s+(.*)", label)
    if not m:
        return None, label
    return f"{m.group(3)}{m.group(2)}{m.group(1)}", m.group(4).strip()


def load_dated_votes():
    """Read every scheduled or decided ballot item from data/initiatives.json.

    Includes *upcoming* votes as well as decided ones: committees file their
    (budgeted) campaign financing with the EFK register before the ballot, so
    the register carries entries for votes that haven't happened yet. Matching
    is by ballot date, so only items with a dated `vote-YYYYMMDD-` id qualify
    (that is exactly the upcoming/adopted/rejected set); undated pending and
    signature-gathering items have no ballot date to match on and are skipped.

    Returns {ballot_date 'YYYYMMDD': [(initiative_id, title_token_set), ...]}.
    """
    path = ROOT / "data" / "initiatives.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    by_date = {}
    for it in data.get("initiatives", []):
        m = re.match(r"vote-(\d{8})-", it.get("id", ""))
        date = m.group(1) if m else re.sub(r"\D", "", "".join(
            (it.get("date") or {}).get("en", "")))
        if not m:
            continue
        title = (it.get("title") or {}).get("de") or (it.get("title") or {}).get("en", "")
        by_date.setdefault(date, []).append((it["id"], _tokens(title)))
    return by_date


def match_initiative(root_date, root_title, by_date):
    """Best initiative id for an EFK root, by same ballot date + title overlap."""
    candidates = by_date.get(root_date, [])
    if not candidates:
        return None
    rtok = _tokens(root_title)
    if not rtok:
        return None
    best_id, best_score = None, 0.0
    for init_id, itok in candidates:
        if not itok:
            continue
        overlap = len(rtok & itok) / min(len(rtok), len(itok))
        if overlap > best_score:
            best_id, best_score = init_id, overlap
    return best_id if best_score >= 0.5 else None


def fetch_initiatives():
    print("Fetching campaign (vote) financing tree...")
    tree = fetch_json("/api/frontend/v1/search/campaign_financings")
    by_date = load_dated_votes()
    if not by_date:
        print("  ! data/initiatives.json has no dated votes to match against; "
              "run fetch_initiatives.py first", file=sys.stderr)

    result = {}
    for root in tree["data"]["tree_roots"]:
        label = root["label"]
        if any(m in label.lower() for m in ELECTION_LABEL_MARKERS):
            continue
        root_date, root_title = _root_date_and_title(label)
        if not root_date:
            continue
        init_id = match_initiative(root_date, root_title, by_date)
        if not init_id:
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

        # Skip ballots where no committee has filed anything on either side —
        # showing "CHF 0 / 0 actors" would read as "no money spent" when it
        # really means "nothing reported yet". Let the site's placeholder show.
        if sides["pro"]["actorCount"] == 0 and sides["contra"]["actorCount"] == 0:
            continue

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
