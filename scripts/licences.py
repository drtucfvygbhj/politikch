#!/usr/bin/env python3
"""The licence of every published data file — single source of truth (GUARDRAILS.md §7.1).

Model: open data, protected website. Our own data is CC BY 4.0; official data we
pass on keeps its source's terms; official texts are public domain (URG Art. 5);
the website itself (code, design, interface and page text, names and logos) is
not licensed — see LICENSE.

Every data file carries this in its `_meta` (license, licenseUrl, attribution,
commercialReuse). The fetchers stamp their output with `licence_meta()`;
`python3 scripts/licences.py --stamp` stamps the hand-edited files; check.py
fails if a file's licence is missing or differs from this table (LIC-05/06).
data/LICENSE.txt is written from the same table (`--write-notice`).

Changing this file is a flagged change (LIC-07): relabelling data changes what
other people are allowed to do with it.
"""
import fnmatch
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CC_BY = "https://creativecommons.org/licenses/by/4.0/"
OGD_TERMS = "https://opendata.swiss/en/terms-of-use"
OWN = "Politikch (politikch.ch)"

# Pattern (relative to data/) -> licence. First match wins.
LICENCES = [
    {"files": ["parties.json"], "what": "Party descriptions, positions and spectrum placements (editorial); seat counts",
     "license": "CC-BY-4.0", "licenseUrl": CC_BY,
     "attribution": f"{OWN}, CC BY 4.0. Seat counts: Parliamentary Services (parlament.ch)",
     "commercialReuse": "yes, with credit"},
    {"files": ["donor-descriptions.json"], "what": "One-sentence descriptions of donor organisations (editorial)",
     "license": "CC-BY-4.0", "licenseUrl": CC_BY,
     "attribution": f"{OWN}, CC BY 4.0", "commercialReuse": "yes, with credit"},
    {"files": ["initiatives-translations.json", "sessions-translations.json"],
     "what": "Unofficial English and Romansh translations of official titles",
     "license": "CC-BY-4.0", "licenseUrl": CC_BY,
     "attribution": f"{OWN}, CC BY 4.0 — unofficial translations; the official DE/FR/IT titles prevail",
     "commercialReuse": "yes, with credit"},
    {"files": ["cantons.json", "council.json"], "what": "Canton and Federal Council facts compiled by Politikch",
     "license": "CC-BY-4.0", "licenseUrl": CC_BY,
     "attribution": f"{OWN}, CC BY 4.0. Figures: Federal Statistical Office (BFS); Federal Council: admin.ch",
     "commercialReuse": "yes, with credit"},
    {"files": ["mt.json"], "what": "Machine translations (English, Italian) of official texts",
     "license": "CC-BY-4.0", "licenseUrl": CC_BY,
     "attribution": f"{OWN}, CC BY 4.0. Machine translation by DeepL — unofficial; the official text prevails",
     "commercialReuse": "yes, with credit (to Politikch and DeepL)"},
    {"files": ["financing.json"], "what": "Party and campaign financing (private individuals are not named)",
     "license": "LicenseRef-opendata.swiss-terms_open", "licenseUrl": OGD_TERMS,
     "attribution": "Swiss Federal Audit Office (EFK), political financing register",
     "commercialReuse": "yes"},
    {"files": ["canton-data.json"], "what": "National Council results by canton; municipality and district counts",
     "license": "LicenseRef-opendata.swiss-terms_by", "licenseUrl": OGD_TERMS,
     "attribution": "Federal Statistical Office (BFS)", "commercialReuse": "yes, with credit"},
    {"files": ["sessions-index.json", "sessions/*.json"], "what": "Federal Assembly sessions, final votes and tallies",
     "license": "LicenseRef-opendata.swiss-terms_by", "licenseUrl": OGD_TERMS,
     "attribution": "Parliamentary Services of the Federal Assembly (parlament.ch)",
     "commercialReuse": "yes, with credit"},
    {"files": ["municipalities-index.json", "municipalities/*.json"],
     "what": "Municipality names, populations and simplified boundaries",
     "license": "LicenseRef-opendata.swiss-terms_by", "licenseUrl": OGD_TERMS,
     "attribution": "Federal Office of Topography swisstopo (swissBOUNDARIES3D), simplified by Politikch",
     "commercialReuse": "yes, with credit"},
    {"files": ["initiatives.json"], "what": "Federal votes, results, pending initiatives, party recommendations",
     "license": "LicenseRef-mixed-source-terms", "licenseUrl": OGD_TERMS,
     "attribution": "Federal Statistical Office and Federal Chancellery (VoteInfo, LINDAS); party recommendations "
                    "and English short titles: Swissvotes (Année Politique Suisse, University of Bern), CC BY 4.0",
     "commercialReuse": "ask the source: VoteInfo results are published under 'ask for permission' terms "
                        "for commercial use (Federal Statistical Office)"},
    {"files": ["overviews/*/*.json"], "what": "Federal Council voting explanations: for/against arguments, verbatim",
     "license": "LicenseRef-URG-Art-5-official-text", "licenseUrl": "https://www.fedlex.admin.ch/eli/cc/1993/1798_1798_1798/de#art_5",
     "attribution": "Federal Council voting explanations, Federal Chancellery (brochure PDFs via Swissvotes)",
     "commercialReuse": "official text, not protected by copyright (URG Art. 5); the 'for' arguments are "
                        "written by the initiative or referendum committee"},
]

# Published files that are part of the website, not data: not licensed (LICENSE).
WEBSITE_FILES = ["i18n.json", "legal.json"]
FIELDS = ("license", "licenseUrl", "attribution", "commercialReuse")


def entry_for(rel):
    """Licence entry for a path relative to data/ (None for website files)."""
    for e in LICENCES:
        if any(fnmatch.fnmatch(rel, pat) for pat in e["files"]):
            return e
    return None


def licence_meta(rel):
    e = entry_for(rel)
    if e is None:
        raise KeyError(f"no licence defined for data/{rel} — add it to scripts/licences.py")
    return {k: e[k] for k in FIELDS}


def data_files():
    return sorted(str(p.relative_to(DATA)) for p in DATA.rglob("*.json"))


def stamp(rel):
    """Add/refresh the licence fields in a data file's _meta. True if changed."""
    p = DATA / rel
    raw = p.read_text("utf-8")
    d = json.loads(raw)
    meta = dict(d.get("_meta") or {})
    new = {**meta, **licence_meta(rel)}
    if new == meta:
        return False
    d = {"_meta": new, **{k: v for k, v in d.items() if k != "_meta"}}
    compact = "\n" not in raw.strip()          # keep one-line files one-line
    text = json.dumps(d, ensure_ascii=False, separators=(",", ":")) if compact \
        else json.dumps(d, ensure_ascii=False, indent=2)
    p.write_text(text + "\n", "utf-8")
    return True


NOTICE_HEAD = """Politikch data — licences and how to credit
===========================================

You may reuse the data files in this folder, including commercially, on the
terms below. The website itself — its code, design, interface and page text
(i18n.json and legal.json in this folder) — and the names and logos
"Politikch", "PolitikCH" and "PCH" are NOT licensed: see LICENSE at
https://github.com/drtucfvygbhj/politikch and https://politikch.ch/#/page/reuse

Every JSON file repeats its own terms in its "_meta" section.

Our own data is licensed under Creative Commons Attribution 4.0 International
(CC BY 4.0, https://creativecommons.org/licenses/by/4.0/). Credit it as
"Source: Politikch (politikch.ch), CC BY 4.0" and say if you changed it.
Official data we pass on stays under its source's terms: credit the source.
Official texts are not protected by copyright (Swiss Copyright Act, Art. 5).

Private individuals who donated to parties or campaigns are never named.
Reusing the data does not imply any connection with or endorsement by
Politikch. The data is provided as is, without warranty; Politikch's editorial
data is not official, and official sources prevail.
"""


def notice_text():
    lines = [NOTICE_HEAD, "", "File by file", "------------", ""]
    for e in LICENCES:
        lines += [", ".join(e["files"]),
                  f"  What:        {e['what']}",
                  f"  Licence:     {e['license']}  ({e['licenseUrl']})",
                  f"  Credit:      {e['attribution']}",
                  f"  Commercial:  {e['commercialReuse']}", ""]
    lines += [", ".join(WEBSITE_FILES), "  Website text — not licensed (all rights reserved).", ""]
    return "\n".join(lines)


def write_notice():
    (DATA / "LICENSE.txt").write_text(notice_text(), "utf-8")


if __name__ == "__main__":
    if "--stamp" in sys.argv:
        changed = [f for f in data_files() if f not in WEBSITE_FILES and stamp(f)]
        print(f"stamped {len(changed)} file(s)")
    if "--write-notice" in sys.argv:
        write_notice()
        print("wrote data/LICENSE.txt")
