# Running Politikch — recurring tasks & how to manage them

The site is static and most data refresh is **already automated** in GitHub
Actions. This file lists everything that recurs, whether it's automatic or
manual, how often, and how to keep on top of it.

## How it's managed (the short version)

- **Automation first.** Anything that can run on a schedule lives in
  `.github/workflows/`. The weekly fetch commits fresh data straight to `main`,
  which the deploy workflow then publishes — no human in the loop for routine
  data.
- **GitHub Issues are the to-do queue.** The fetch job opens/updates issues when
  something needs a human (e.g. missing translations). Treat the issue list as
  the maintenance backlog.
- **CI is the safety net.** `validate.py` runs on every push and PR; a broken
  data file can't merge or deploy.
- **Cadence:** a ~15-minute check once a week (after the Monday fetch) covers
  almost everything; a few tasks are per-release or rare.

---

## 1. Automated — just keep an eye on them

| Task | Where | When | What to watch |
|---|---|---|---|
| Refresh votes, financing, canton results, sessions, **vote arguments (for/against)** | `.github/workflows/fetch-financing.yml` → `scripts/fetch_*.py` | Weekly (Mon 04:00 UTC) + manual `workflow_dispatch` | That the run is green and actually committed. Check the Actions tab if the site looks stale. |
| Data integrity check | `.github/workflows/validate.yml` → `scripts/validate.py` | Every push / PR | A red check blocks deploy — fix the reported file. |
| Publish | `.github/workflows/deploy.yml` | Every push to `main` | Green = live within ~1 min. |
| Missing-translation reminder | `scripts/check_translations.py` (inside the fetch job) | Weekly | It opens/updates a GitHub issue listing untranslated titles. |

**Managing them:** once a week, open the **Actions** tab, confirm the "Fetch live
data" run succeeded, and skim any issue it opened. That's the core routine.

## 2. Your recurring MANUAL tasks (everything else is automatic)

Only **two** things ever need your hands. Both are optional in the sense that the
site stays correct (with honest fallbacks) if you skip them.

### 2a. Vote for/against arguments — download the brochure  *(~4×/year, per federal ballot)*

This is the one recurring data task. The Federal Council's voting brochure (the
source of the on-site **for / against** arguments) is only on the Federal
Chancellery site, which blocks bots — so you fetch it by hand. It's done
**directly from the authority on purpose**: the content is public-domain
official text, and taking it from admin.ch (not a third party) keeps the site
clean for commercial use.

**When:** a new federal vote is coming up and its brochure is published (~6 weeks
before the ballot). **Steps:**
1. Download the official **"Erläuterungen des Bundesrates"** PDF for that ballot
   date from <https://www.bk.admin.ch>, in **German, French and Italian**.
2. Save them in `data/brochures/` as `YYYYMMDD-de.pdf`, `YYYYMMDD-fr.pdf`,
   `YYYYMMDD-it.pdf` (ballot date, no dashes).
3. Run `python3 scripts/fetch_arguments.py --force`
   (needs `pip install -r scripts/requirements-arguments.txt` once).
4. Commit the changed files under `data/overviews/initiative/`.

Full details: `data/brochures/README.md`. Skip a language → it falls back on the
site; skip a ballot → its pages show an honest "not published yet".

### 2b. Unofficial EN / RM titles — hand-translate  *(as needed)*

Swiss vote/act titles are official only in DE/FR/IT; English and Romansh titles
are unofficial and hand-made. When the weekly fetch finds a new one it opens a
GitHub issue and lists it in `TRANSLATIONS_TODO.md`. To clear it, add the
translation to `data/initiatives-translations.json` or
`data/sessions-translations.json` under `titles.<id>` as `{ "en": …, "rm": … }`,
then commit. Until then the site falls back to the official DE/FR/IT title. (Or
open a Claude Code session and say *"translate the pending titles in
TRANSLATIONS_TODO.md"*.)

### Everything else is automatic (nothing to do)

The weekly GitHub Action refreshes votes, initiatives, financing, canton data,
Federal Assembly sessions **and the session votes' "What this vote is about"
official summaries** (from parlament.ch). The old AI "overview" review desk is
gone — no `Weekly Update.command`, `ai_maintain.py` or `review_server.py`.

> **Commercial note:** before the site monetises, see `COMPLIANCE.md` — one email
> to BFS (`poku@bfs.admin.ch`) authorises commercial use of the vote-results feed,
> and one to Swissvotes confirms their CC BY 4.0 licence. Everything else is
> already commercial-safe with the attribution shown on the site.

### Review flagged translations  *(as needed)*
`TRANSLATIONS_TODO.md` also lists UI/legal strings whose FR/IT/DE/RM wording was
best-effort and wants a native/legal check (privacy, poll, share terms). Clear
these before relying on them publicly.

## 3. Per-release — when you push site changes

### Cache-busting token  *(now automated — nothing to do)*
Assets and data fetches are versioned with `?v=…`. **`deploy.yml` rewrites every
token to the commit SHA at publish time**, so each deploy serves fresh CSS/JS/JSON
automatically and no visitor is left on a stale copy — including after the weekly
data fetch (its commit triggers a deploy, which re-tokenises the data-fetch URLs).
- You no longer need to bump it by hand. The `?v=20260916e` value in the source
  is just a local-dev placeholder; the deployed artifact always uses the SHA.
- If you add a new JS file that references assets with `?v=`, keep the same
  `?v=<token>` spelling so the deploy step's find/replace catches it.

### Run the validator locally
`python3 scripts/validate.py` before pushing data/i18n changes (JSON validity,
seat totals, four-language key parity).

## 4. Services — once the poll goes live

### Community-poll backend  *(monitor)*
See `BACKEND.md`. Once `js/config.js` `POLL_API` is set:
- Watch the provider's dashboard for errors / quota (free tiers have daily caps).
- It's an unofficial straw poll and can be gamed — don't over-trust the numbers;
  the UI already labels them unofficial.

### Domains, TLS, email  *(rare)*
- `politikch.ch` DNS → GitHub Pages; the three language domains 301-redirect to
  it. TLS auto-renews (GitHub/Let's Encrypt).
- `contact@politikch.ch` (in `data/legal.json`) must stay a real mailbox — it's
  the privacy-contact and subscribe address.

## 5. Editorial / legal  *(quarterly-ish or on change)*
- Keep the "not affiliated" disclaimer and the official/unofficial (poll)
  distinction intact.
- Refresh the Federal Council composition (`data/council.json`) after any change
  of member or annual presidency.
- Review the Privacy Policy / About / Subscribe copy if the product plans change.

## 6. The two official "what it means" texts
Both are **official, verbatim, no AI, no review gate**. Each is clearly
attributed and linked to its source; the site adds nothing of its own.

**Popular votes — for / against arguments** (`data/overviews/initiative/`). From
the Federal Council brochure (Art. 5 URG). `pros` = the initiative/referendum
committee's words, `cons` = the Federal Council and Parliament's; neither side is
shown alone. **This is the manual brochure download in §2a** — DE/FR/IT from the
PDFs you drop in `data/brochures/`, EN/RM fall back with a language chip.

**Session votes — "What this vote is about"** (stored on each vote in
`data/sessions/<id>.json`). The official background/summary from the
parliamentary record (Curia Vista) — `InitialSituation`, falling back to
`Description` — in DE/FR/IT, EN/RM falling back. **Automatic**, fetched by
`scripts/fetch_sessions.py` in the weekly job (parlament.ch is commercially
reusable with attribution). A settled session already on disk keeps its data;
run `python3 scripts/fetch_sessions.py --force` once to backfill older sessions.

---

### One-glance weekly checklist
1. **Actions tab → "Fetch live data" green & committed?** (Refreshes votes,
   financing, cantons, sessions **and the session "what this vote is about" text**
   — nothing to run by hand.)
2. **New federal ballot coming up?** Download its brochure PDFs (DE/FR/IT) from
   admin.ch → `data/brochures/` → `python3 scripts/fetch_arguments.py --force` →
   commit (§2a). ~4×/year.
3. **Pending title translations?** If the fetch flagged one in `TRANSLATIONS_TODO.md`,
   add it and commit (§2b). As needed.
4. (Once live) poll backend healthy?

(The cache token is auto-bumped on deploy; `validate.py` runs in CI — run it
locally only if you hand-edited data before pushing.)
