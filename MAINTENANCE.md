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
| Refresh votes, financing, canton results, sessions | `.github/workflows/fetch-financing.yml` → `scripts/fetch_*.py` | Weekly (Mon 04:00 UTC) + manual `workflow_dispatch` | That the run is green and actually committed. Check the Actions tab if the site looks stale. |
| Data integrity check | `.github/workflows/validate.yml` → `scripts/validate.py` | Every push / PR | A red check blocks deploy — fix the reported file. |
| Publish | `.github/workflows/deploy.yml` | Every push to `main` | Green = live within ~1 min. |
| Missing-translation reminder | `scripts/check_translations.py` (inside the fetch job) | Weekly | It opens/updates a GitHub issue listing untranslated titles. |

**Managing them:** once a week, open the **Actions** tab, confirm the "Fetch live
data" run succeeded, and skim any issue it opened. That's the core routine.

## 2. Manual — triggered by the automation

### Hand-translate new vote/act titles  *(weekly, ~5–15 min)*
Swiss vote/act titles are official only in DE/FR/IT. New items need **unofficial
EN and RM** titles by hand (the project uses no machine translation).
- **Trigger:** the weekly job files/updates a GitHub issue and lists them in
  `TRANSLATIONS_TODO.md`.
- **Do:** add each to `data/initiatives-translations.json` or
  `data/sessions-translations.json` under `titles.<id>` as `{ "en": …, "rm": … }`.
- Until done, the site falls back to the official DE/FR/IT title (not broken).

### Review flagged translations  *(as needed)*
`TRANSLATIONS_TODO.md` also lists UI/legal strings whose FR/IT/DE/RM wording was
best-effort and wants a native/legal check (privacy, poll, share terms). Clear
these before relying on them publicly.

## 3. Per-release — when you push site changes

### Bump the cache-busting token  *(every release)*
Assets are versioned with `?v=YYYYMMDD` (currently `20260916b`) in `index.html`,
the `js/*.js` imports, and every `data/*.json` fetch in `app.js`. **Bump this
token whenever you change JS/CSS/data by hand**, or returning visitors get stale
files (this is what caused the old contact-email to linger).
- Find/replace the old token with a new one across `index.html`, `js/app.js`,
  `js/myvotes.js`.
- *Recommended:* automate it — have `deploy.yml` rewrite the token to the commit
  SHA at publish time so it's never forgotten. (Ask and I'll wire this up.)
- Note: the **weekly auto-fetch does _not_ bump the token**, because data fetches
  already carry it; if you change the token scheme, keep the fetcher in mind.

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

## 6. Planned — the AI "what happens if accepted" overviews
If/when per-item AI overviews ship (see the open design question), they become a
recurring task: **whenever the weekly fetch adds or changes a vote/session item,
its overview must be (re)generated and human-reviewed before publish.** The
honest, static-safe design is to pre-generate variants offline into
`data/overviews/…` (never call an LLM from the live page), review, then commit —
so it slots into the same "fetch → review issue → commit → deploy" loop above.
This is a content pipeline with an API cost and an editorial-review step; it is
**not yet built**.

---

### One-glance weekly checklist
1. Actions tab → "Fetch live data" green & committed?
2. Any new GitHub issue for translations? → fill `*-translations.json`.
3. Site changed by hand this week? → bump the `?v=` token, run `validate.py`.
4. (Once live) poll backend healthy?
