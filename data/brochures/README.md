# Official voting brochures (optional, for native Italian)

`scripts/fetch_arguments.py` writes the pro/con arguments shown on vote pages by
extracting them **verbatim** from the Federal Council's official voting
explanations ("Erläuterungen des Bundesrates" / Abstimmungsbüechli). German and
French come **automatically** from the officially-published brochure (mirrored
by Swissvotes) — nothing to do.

**Italian is optional and manual**, because the Italian brochure isn't available
from that automatic source. English and Romansh never exist officially and fall
back on the site to DE/FR with a language chip.

## To add native Italian for a ballot (a few times a year, optional)

1. Download the **official** Italian brochure PDF for the ballot date from the
   Federal Chancellery: <https://www.bk.admin.ch> → the vote's "Spiegazioni"
   (one PDF covers every proposal on that date). Use the authority's own copy.
2. Save it here as `<YYYYMMDD>-it.pdf` — the ballot date with no dashes, e.g.
   `20261129-it.pdf`. (You may add `-de` / `-fr` files the same way to override
   the automatic ones, but that's rarely needed.)
3. Re-run `python3 scripts/fetch_arguments.py --force`; commit the changed files
   under `data/overviews/initiative/`.

If you skip this, Italian simply falls back to the official DE/FR text — nothing
breaks. Only the **official** brochure may be used here; never a summary, a
translation, or a third-party rewrite. See `NOTICE.md` for the legal basis.

## Why Italian is manual (scraping compliance)

The automatic fetch only ever talks to **swissvotes.ch**, whose `robots.txt`
permits it (`Disallow: /auth/` only, with `Crawl-delay: 10`, which the fetcher
honours). Swissvotes hosts the German and French brochures — so those need no
manual step.

It does **not** host Italian. The Italian brochure lives only on the Federal
Chancellery site (**admin.ch / bk.admin.ch**), which **blocks automated access**
(its edge returns "Access Denied" even for `robots.txt`). We must not script
against it. So any admin.ch PDF you want — in practice just the **Italian
brochure** — has to be downloaded **by hand in a normal browser** and dropped
here. That is the only manual fetch, and it exists specifically to respect
admin.ch's no-bots policy.
