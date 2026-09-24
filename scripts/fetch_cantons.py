#!/usr/bin/env python3
"""Fetch per-canton reference data from official federal open-data sources.

Writes data/canton-data.json — the recurring, machine-readable facts behind two
of the canton-page sections, from national datasets that cover all 26 cantons
uniformly (no invented figures, exactly like scripts/fetch_financing.py):

1. National Council election results per canton — Federal Statistical Office
   (BFS) official results of the 2023 federal election, published on
   opendata.swiss. Gives each canton's party strengths (Wähleranteile), the
   seats each party won, and the change since the previous election. Feeds the
   "Elections & results" section.

2. Municipality & district counts per canton — BFS official municipality
   register (Amtliches Gemeindeverzeichnis / agvchapp), the authoritative list
   of every political municipality with its canton and district. Feeds the
   "Municipalities" section.

Both are public, unauthenticated open-data sources the Confederation publishes
for reuse; this is a build-time fetch (run in CI or locally) that writes a
same-origin JSON file the static site loads like any other data file. On any
failure the existing data/canton-data.json is left untouched, so the site never
falls back to a blank or invented section.

Usage:
  python3 scripts/fetch_cantons.py
"""
import csv
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = (
    "Politikch-data-fetcher/1.0 "
    "(+https://politikch.ch; contact.form@politikch.ch)"
)

# BFS National Council 2023 results, party-level, all geographic levels
# (dataset "nationalratswahlen-2023-mandate-...-parteistarke..." on
# opendata.swiss; CSV distribution served from the BFS asset hub).
NC_CSV = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/28845352/appendix"
NC_YEAR = 2023

# BFS municipality register (agvchapp): every current political municipality
# with its canton and district. `date` is a DD-MM-YYYY snapshot.
AGV_URL = "https://www.agvchapp.bfs.admin.ch/api/communes/levels?date={date}"

# BFS German party abbreviation -> this site's party key (colours/labels reuse
# data/parties.json). Parties without a site key keep their official name and
# render in a neutral colour.
NC_PARTY_KEY = {
    "SVP": "SVP", "SP": "SP", "FDP": "FDP", "GLP": "GLP",
    "GRÜNE": "GPS", "Mitte": "MITTE", "EVP": "EVP", "EDU": "EDU",
    "Lega": "LEGA", "MCR": "MCG",
}


# www.agvchapp.bfs.admin.ch asks for 10 s between requests (robots.txt
# Crawl-delay); its REST API is documented by the BFS for programmatic use.
CRAWL_DELAY = float(os.environ.get("POLITIKCH_CRAWL_DELAY", "10"))
_last_hit = [0.0]


def _polite_wait():
    wait = CRAWL_DELAY - (time.time() - _last_hit[0])
    if wait > 0:
        time.sleep(wait)
    _last_hit[0] = time.time()


# A larger response is refused rather than read into memory (GUARDRAILS.md SEC-09).
MAX_BYTES = 32 * 1024 * 1024


def read_capped(resp):
    data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"response larger than {MAX_BYTES} bytes: {resp.geturl()}")
    return data


def http_get(url):
    _polite_wait()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return read_capped(resp)


def canton_num_to_code():
    """Map BFS canton number (1..26) -> site canton code, from cantons.json,
    which is maintained in the canonical BFS order (ZH=1 … JU=26)."""
    data = json.loads((ROOT / "data" / "cantons.json").read_text(encoding="utf-8"))
    codes = list(data.get("cantons", {}).keys())
    return {str(i + 1): code for i, code in enumerate(codes)}


def fetch_nc_results(num_to_code):
    """Return {code: {year, totalSeats, parties:[...]}} from the BFS NC results."""
    print("Fetching National Council 2023 results (BFS)...")
    raw = http_get(NC_CSV).decode("utf-8", "replace")
    reader = csv.DictReader(io.StringIO(raw), delimiter=";")
    by_canton = {}
    for row in reader:
        if row.get("ebene_resultat") != "Kanton":
            continue
        code = num_to_code.get((row.get("kanton_nummer") or "").strip())
        if not code:
            continue

        def num(field):
            v = (row.get(field) or "").strip().replace(",", ".")
            try:
                return float(v)
            except ValueError:
                return None

        strength = num("partei_staerke")
        seats = num("anzahl_gewaehlte")
        delta = num("differenz_partei_staerke")
        de = (row.get("partei_bezeichnung_de") or "").strip()
        party = {
            "key": NC_PARTY_KEY.get(de),
            "name": {
                "de": de,
                "fr": (row.get("partei_bezeichnung_fr") or de).strip(),
                "it": (row.get("partei_bezeichnung_it") or de).strip(),
                "en": (row.get("partei_bezeichnung_en") or de).strip(),
            },
            "strength": round(strength, 1) if strength is not None else None,
            "seats": int(seats) if seats is not None else 0,
            "delta": round(delta, 1) if delta is not None else None,
        }
        by_canton.setdefault(code, []).append(party)

    result = {}
    for code, parties in by_canton.items():
        parties.sort(key=lambda p: (p["strength"] is not None, p["strength"] or 0), reverse=True)
        total_seats = sum(p["seats"] for p in parties)
        result[code] = {"year": NC_YEAR, "totalSeats": total_seats, "parties": parties}
    print(f"  {len(result)} cantons with NC results")
    return result


def fetch_municipalities():
    """Return ({code: {municipalities, districts}}, snapshot_date_iso)."""
    print("Fetching municipality register (BFS agvchapp)...")
    year = datetime.now(timezone.utc).year
    last_err = None
    for snap_year in (year, year - 1):
        date = f"01-01-{snap_year}"
        try:
            raw = http_get(AGV_URL.format(date=date)).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
        reader = csv.DictReader(io.StringIO(raw))
        muni, dist = {}, {}
        for row in reader:
            cid = (row.get("CantonId") or "").strip()
            if not cid:
                continue
            muni[cid] = muni.get(cid, 0) + 1
            did = (row.get("DistrictId") or "").strip()
            if did:
                dist.setdefault(cid, set()).add(did)
        if muni:
            num_to_code = canton_num_to_code()
            out = {}
            for cid, count in muni.items():
                code = num_to_code.get(cid)
                if code:
                    out[code] = {"municipalities": count, "districts": len(dist.get(cid, set()))}
            iso = f"{snap_year}-01-01"
            print(f"  {len(out)} cantons, {sum(m['municipalities'] for m in out.values())} "
                  f"municipalities (snapshot {iso})")
            return out, iso
    raise RuntimeError(f"municipality register unavailable: {last_err}")


def main():
    try:
        num_to_code = canton_num_to_code()
        nc = fetch_nc_results(num_to_code)
        munis, muni_date = fetch_municipalities()
    except (urllib.error.URLError, RuntimeError) as e:
        print(f"Network/data error reaching BFS: {e}", file=sys.stderr)
        print("Keeping any existing data/canton-data.json unchanged.", file=sys.stderr)
        sys.exit(1)

    cantons = {}
    for code in num_to_code.values():
        entry = {}
        if code in munis:
            entry.update(munis[code])
        if code in nc:
            entry["nc"] = nc[code]
        if entry:
            cantons[code] = entry

    output = {
        "_meta": {
            "source": "Federal Statistical Office (BFS) — National Council 2023 "
                      "results and the official municipality register, via "
                      "opendata.swiss.",
            "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ncElectionYear": NC_YEAR,
            "municipalitySnapshot": muni_date,
            "note": "Election figures are the official BFS results; municipality "
                    "and district counts are from the federal register on the "
                    "snapshot date shown.",
        },
        "cantons": cantons,
    }
    out_path = ROOT / "data" / "canton-data.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out_path} ({len(cantons)} cantons)")


if __name__ == "__main__":
    main()
