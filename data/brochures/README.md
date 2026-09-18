# Official voting brochures — your recurring manual download

`scripts/fetch_arguments.py` builds the **for / against arguments** shown on each
popular-vote page by extracting them **verbatim** from the Federal Council's
official voting explanations ("Erläuterungen des Bundesrates" / Abstimmungs­büechli).

**This is a manual step, on purpose.** The brochure content is public-domain
official text (Art. 5 URG), but the only machine-reachable copy was on a
third-party site under a **non-commercial** licence. To keep the site clean for
**commercial** use, we take the PDFs straight from the authority (the Federal
Chancellery), which **blocks automated download** — so a person fetches them by
hand. Nothing here is scraped.

## Recurring task — once per federal ballot (about 4×/year)

1. When a new federal vote is coming up (the brochure is published ~6 weeks
   before the ballot), download the official **"Erläuterungen des Bundesrates"**
   brochure PDF for that ballot date from the Federal Chancellery
   (<https://www.bk.admin.ch> → the vote → the explanations PDF), in each
   language: **German, French, Italian**. One PDF per language covers every
   proposal on that date.
2. Save them here, named by the ballot date (no dashes) and language:
   - `YYYYMMDD-de.pdf`
   - `YYYYMMDD-fr.pdf`
   - `YYYYMMDD-it.pdf`
   e.g. `20261129-de.pdf`. (RM/EN aren't published officially — they fall back to
   these on the site with a small language chip.)
3. Run: `python3 scripts/fetch_arguments.py --force`
4. Commit the changed files under `data/overviews/initiative/`. (The PDFs
   themselves stay local — they're git-ignored.)

If a language's PDF is missing, that language simply falls back on the site;
if no PDF is present for a ballot, its pages keep an honest "not published yet"
state. **Only the official Chancellery brochure may be used — never a summary, a
translation, or a third-party rewrite.** See `NOTICE.md` for the legal basis.
