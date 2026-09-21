#!/usr/bin/env python3
"""One-off builder for the per-canton municipality maps.

Turns the official swisstopo swissBOUNDARIES3D municipality polygons into small,
pre-projected, simplified SVG paths — one file per canton in
data/municipalities/<CODE>.json — that the site renders as a hover map (name +
population per municipality). This is a *baked* snapshot: run once, commit the
output, and it stays static (it is deliberately NOT in the weekly CI fetch).

Source: swissBOUNDARIES3D (swisstopo / Federal Office of Topography), the
official municipal boundary set, distributed as GeoJSON (WGS84). Each feature
carries NAME, BFS_NUMMER, KANTONSNUM, BEZIRKSNUM, EINWOHNERZ (population) and
GEM_FLAECH (area, hectares).

Usage:
  python3 scripts/build_municipality_maps.py [path-to-hoheitsgebiet.geojson]
If no path is given it downloads the GeoJSON (large, ~50 MB).
"""
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "Politikch-map-builder/1.0 (+https://politikch.ch; contact.form@politikch.ch)"
GEOJSON_URL = ("https://labs.karavia.ch/swiss-boundaries-geojson/geojson/2020/"
               "swissBOUNDARIES3D_1_3_TLM_HOHEITSGEBIET.geojson")

TARGET_W = 1000.0   # SVG viewBox width per canton
PAD = 10.0          # padding inside the viewBox
SIMPLIFY_PX = 0.9   # Douglas–Peucker tolerance, in projected pixels


def load_geojson(argv):
    if len(argv) > 1 and Path(argv[1]).exists():
        print(f"Reading {argv[1]}")
        return json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    print(f"Downloading {GEOJSON_URL} (large)…")
    req = urllib.request.Request(GEOJSON_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def perp_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points, tol):
    """Iterative Douglas–Peucker on a list of (x, y)."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        s, e = stack.pop()
        dmax, idx = 0.0, -1
        for i in range(s + 1, e):
            d = perp_dist(points[i], points[s], points[e])
            if d > dmax:
                dmax, idx = d, i
        if idx != -1 and dmax > tol:
            keep[idx] = True
            stack.append((s, idx))
            stack.append((idx, e))
    return [pt for pt, k in zip(points, keep) if k]


# cantons.json capitals are in mixed local/English; map the few that differ from
# the boundary file's official local NAME so the capital gets flagged.
CAPITAL_ALIAS = {"geneva": "genève"}


def norm_capital(s):
    """Lowercase and drop any parenthetical, e.g. 'Bern (federal city)' -> 'bern'."""
    s = re.sub(r"\(.*?\)", "", s or "").strip().lower()
    return CAPITAL_ALIAS.get(s, s)


def canton_num_to_code():
    data = json.loads((ROOT / "data" / "cantons.json").read_text(encoding="utf-8"))
    cantons = data.get("cantons", {})
    codes = list(cantons.keys())
    num_to_code = {i + 1: code for i, code in enumerate(codes)}
    capitals = {code: norm_capital(cantons[code].get("capital")) for code in codes}
    return num_to_code, capitals


def main():
    gj = load_geojson(sys.argv)
    num_to_code, capitals = canton_num_to_code()

    # Group Swiss municipality polygons by canton, then by BFS number (a
    # municipality can appear as several features / exclave parts).
    by_canton = {}
    for feat in gj["features"]:
        p = feat["properties"]
        if p.get("OBJEKTART") != "Gemeindegebiet" or p.get("ICC") != "CH":
            continue
        knum = p.get("KANTONSNUM")
        bfs = p.get("BFS_NUMMER")
        code = num_to_code.get(knum)
        if not code or not bfs:
            continue
        rings = []
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "Polygon" else sum(geom["coordinates"], [])
        for ring in polys:
            rings.append([(pt[0], pt[1]) for pt in ring])
        muni = by_canton.setdefault(code, {}).setdefault(bfs, {
            "name": p.get("NAME") or str(bfs),
            "pop": p.get("EINWOHNERZ"),
            "area": p.get("GEM_FLAECH"),
            "district": p.get("BEZIRKSNUM"),
            "rings": [],
        })
        muni["rings"].extend(rings)
        if (p.get("EINWOHNERZ") or 0) > (muni["pop"] or 0):
            muni["pop"] = p.get("EINWOHNERZ")

    out_dir = ROOT / "data" / "municipalities"
    out_dir.mkdir(parents=True, exist_ok=True)
    total_muni = 0
    search_index = []

    for code, munis in by_canton.items():
        # Canton bounding box over every point.
        min_lon = min_lat = 1e9
        max_lon = max_lat = -1e9
        for m in munis.values():
            for ring in m["rings"]:
                for lon, lat in ring:
                    min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)
                    min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
        mean_lat = math.radians((min_lat + max_lat) / 2)
        kx = math.cos(mean_lat)
        span_x = (max_lon - min_lon) * kx
        scale = (TARGET_W - 2 * PAD) / span_x
        height = round((max_lat - min_lat) * scale + 2 * PAD, 1)

        def project(lon, lat):
            return (PAD + (lon - min_lon) * kx * scale,
                    PAD + (max_lat - lat) * scale)

        muni_list = []
        for bfs, m in munis.items():
            subpaths = []
            for ring in m["rings"]:
                pts = [project(lon, lat) for lon, lat in ring]
                pts = simplify(pts, SIMPLIFY_PX)
                if len(pts) < 3:
                    continue
                d = "M" + " ".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"
                subpaths.append(d)
            if not subpaths:
                continue
            cap = norm_capital(m["name"]) == (capitals.get(code) or "")
            entry = {
                "name": m["name"],
                "d": "".join(subpaths),
            }
            if m["pop"]:
                entry["pop"] = int(m["pop"])
            if m["area"]:
                entry["km2"] = round(m["area"] / 100.0, 1)   # hectares → km²
            if cap:
                entry["capital"] = True
            muni_list.append(entry)

        muni_list.sort(key=lambda e: e.get("pop", 0), reverse=True)
        total_muni += len(muni_list)
        for e in muni_list:
            idx = {"n": e["name"], "c": code}
            if "pop" in e:
                idx["p"] = e["pop"]
            search_index.append(idx)
        payload = {
            "w": round(TARGET_W, 1),
            "h": height,
            "source": "swisstopo swissBOUNDARIES3D (2020); population EINWOHNERZ.",
            "municipalities": muni_list,
        }
        (out_dir / f"{code}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8")

    # Compact all-municipalities index for the site-wide search (name + canton
    # + population), biggest first for sensible default ranking.
    search_index.sort(key=lambda e: -(e.get("p", 0)))
    (ROOT / "data" / "municipalities-index.json").write_text(
        json.dumps({"_meta": {"source": "swisstopo swissBOUNDARIES3D via data/municipalities/*.json",
                              "count": len(search_index)}, "m": search_index},
                   ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8")

    print(f"Wrote {len(by_canton)} canton map files, {total_muni} municipalities → {out_dir}")
    print(f"Wrote data/municipalities-index.json ({len(search_index)} entries)")


if __name__ == "__main__":
    main()
