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

## 2. The only recurring hand step: title translations

**Vote arguments (for / against) are automatic and official — nothing to do.**
The weekly fetch reproduces them **verbatim** from the Federal Council's voting
brochure (no AI, no review gate). See §6 for how it works and the one *optional*
manual add (native Italian). This replaces the old AI-generated "overview"
review desk, which is no longer part of the routine (the local
`Weekly Update.command` / `ai_maintain.py` / `review_server.py` tooling is no
longer needed).

**Titles occasionally need a hand translation.** Swiss vote/act titles are
official only in DE/FR/IT; the English and Romansh titles shown are unofficial
and hand-made. When the weekly fetch finds a new one it opens a GitHub issue and
lists it in `TRANSLATIONS_TODO.md`.

**To clear one:** add the translation to `data/initiatives-translations.json` or
`data/sessions-translations.json` under `titles.<id>` as `{ "en": …, "rm": … }`,
then commit. Until then the site falls back to the official DE/FR/IT title —
nothing breaks. (Or open a Claude Code session and say *"translate the pending
titles in TRANSLATIONS_TODO.md"*.)

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

## 6. Vote arguments (for / against)  *(automatic — official text)*
Each vote page shows the **for** and **against** arguments, reproduced
**verbatim** from the Federal Council's official voting explanations
("Erläuterungen des Bundesrates" / Abstimmungsbüechli). There is **no AI and no
review gate** — it is official text (Art. 5 URG; see `NOTICE.md`). `pros` = the
initiative/referendum committee's arguments, `cons` = the Federal Council and
Parliament's, each attributed and linked to the official source. Neither side is
ever shown alone, and the site adds no argument of its own.

**Automatic (nothing to do).** `scripts/fetch_arguments.py` runs in the weekly
fetch. For each vote it finds the officially-published brochure, extracts that
vote's arguments, and writes `data/overviews/initiative/<id>.json` in **German
and French**. A vote whose brochure isn't out yet (roughly >6 weeks before the
ballot) is simply skipped — the page shows an honest "not published yet" until
the next fetch picks it up. Nothing is ever fabricated. English and Romansh have
no official version and fall back to DE/FR with a small language chip.

**Optional — native Italian (a few times a year).** Swissvotes, the automatic
source, doesn't host the Italian brochure. If you want native Italian (rather
than the DE/FR fallback), once per ballot:
1. Download the **official** Italian brochure PDF from the Federal Chancellery
   (<https://www.bk.admin.ch>) — one PDF covers all proposals on that date.
2. Save it as `data/brochures/<YYYYMMDD>-it.pdf` (ballot date, no dashes).
3. Run `python3 scripts/fetch_arguments.py --force` and commit the changed
   files. (See `data/brochures/README.md`.)

Only the **official** brochure may be used — never a summary, translation, or
third-party rewrite.

---

### One-glance weekly checklist
1. **Actions tab → "Fetch live data" green & committed?** (This now also refreshes
   the vote arguments — nothing to run by hand.)
2. **Pending title translations?** If the fetch opened/updated a translation issue
   (or `TRANSLATIONS_TODO.md` lists one), add it to the relevant
   `*-translations.json` and commit (§2). Optional.
3. **Native Italian arguments?** Only if you want them for a new ballot — drop the
   official IT brochure in `data/brochures/` and re-run (§6). Optional.
4. (Once live) poll backend healthy?

(The cache token is auto-bumped on deploy; `validate.py` runs in CI — run it
locally only if you hand-edited data before pushing.)
