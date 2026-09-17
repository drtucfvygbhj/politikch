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

## 2. AI-assisted upkeep — one local trigger + a private review desk

**Every week, double-click `Weekly Update.command`.** It opens your private review
desk in the browser — everything is done from there:

- **▶ Run maintenance** button — triggers every Claude process (title
  translations **and** vote overviews). It uses the **local `claude` CLI** (your
  logged-in subscription, **no API key**), spends normal quota bound by the 5-hour
  and weekly limits, and stops the moment a limit is hit, saving progress. Runs
  are **resumable** — click again anytime to continue from the first unfinished
  item.
- **Review queue** — approve / edit / reject each staged proposal. Nothing goes
  live until you approve it.
- **History** tab — every past run and change, with the exact text that was
  approved; filter by id/title to see, e.g., an initiative's translation from
  months ago.
- **Official-title handover** — if an official title in a language is published
  upstream after we generated an unofficial one, the site uses the official one
  automatically and a **notification** appears here (our redundant one is retired).

Under the hood the desk runs these (you can also run them directly):
```bash
python3 scripts/ai_maintain.py       # stage proposals (--task / --max to tune)
python3 scripts/review_server.py     # the review desk → http://127.0.0.1:8777
```
- **It resumes.** Each finished item is saved the moment it's 100% complete;
  the next click skips everything already live or staged and continues at the
  first unfinished item — a few minutes later, after the hourly limit resets, or
  weeks later. By default it does as many as your limit allows (then stops
  cleanly); you can approve staged items any time in between.
- `ai_maintain.py` never touches live data — it writes proposals to
  `review/queue/…` (git-ignored). It skips items it can't ground in an official
  source rather than fabricating.
- The review desk lists each proposal with editable fields. **Approve** writes the
  (edited) result into the live files — translations into
  `data/<initiatives|sessions>-translations.json`, overviews into
  `data/overviews/<kind>/<id>.json` with `reviewed:true` — and drops it from the
  queue. **Reject** discards it. Then commit the changed data files.
- The weekly fetch still opens a GitHub issue listing untranslated titles as a
  reminder; `ai_maintain.py --task translation` is how you clear them.

*Alternative (bulk, uses an API key instead of the subscription):*
`scripts/generate_overviews.py` writes overviews directly as `reviewed:false`
files — same review gate, but it needs `ANTHROPIC_API_KEY` and bills per token.
Prefer the `ai_maintain.py` + review-desk flow for routine upkeep.

### If you'd rather hand-edit
You can always add translations directly: `data/initiatives-translations.json` /
`data/sessions-translations.json` under `titles.<id>` as `{ "en": …, "rm": … }`.
Until an item is translated, the site falls back to the official DE/FR/IT title.

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

## 6. AI "what happens if accepted" overviews  *(recurring, after each fetch)*
Each initiative/referendum and session vote can show an AI-generated overview of
what changes if it passes. These are **pre-generated offline and human-reviewed**
— the live page never calls an LLM, and it will not display a file until a human
approves it.

**When:** whenever the weekly fetch adds new votes/sessions (i.e. the same items
that need translations), generate overviews for them.

**How:**
1. `pip install -r scripts/requirements-overviews.txt` and set `ANTHROPIC_API_KEY`
   (or `ant auth login`).
2. `python3 scripts/generate_overviews.py --kind all` (add `--limit N` to batch,
   `--force` to regenerate). It fetches each item's **official text**, generates
   5 detail levels × 5 languages into `data/overviews/<kind>/<id>.json`, and marks
   each `"reviewed": false`. Items whose official text can't be fetched are
   **skipped**, never fabricated.
3. **Review each new file** — read it against the official text, fix anything
   wrong or partisan, then set `"reviewed": true`. The site shows the overview
   only once that flag is true; until then it displays "being prepared".
4. Commit the reviewed files. Deploy publishes them like any other data.

**Cost/quality:** defaults to `claude-opus-5` (override with `--model` or
`POLITIKCH_OVERVIEW_MODEL`). This is the one recurring task with an API cost and a
mandatory human-review step — treat the review as editorial, not a rubber stamp:
these are legal-consequence claims on a non-partisan site.

---

### One-glance weekly checklist
1. **Double-click `Weekly Update.command`** → let Claude stage proposals, then
   approve/edit them in the review desk that opens. Commit & push the approved
   data files.
2. Actions tab → "Fetch live data" green & committed?
3. (Once live) poll backend healthy?

(The cache token is auto-bumped on deploy; `validate.py` runs in CI — run it
locally only if you hand-edited data before pushing.)
