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

## 2. Recurring tasks — almost none; the data pipeline is fully automatic

The weekly GitHub Action refreshes **everything** and commits it: votes,
initiatives, **vote for/against arguments**, financing, canton data, Federal
Assembly sessions, **the session votes' "What this vote is about" summaries**,
**and the English machine translations** (DeepL) of everything that has no
official English. All from official / openly-licensed sources (see
`COMPLIANCE.md`) — commercially reusable with the attribution the site shows.
Nothing here is manual.

### 2a. English translations — automatic (one-time setup, zero cost)

Anything with no official English (session vote titles, for/against arguments,
session summaries) is machine-translated to English by **DeepL** and shown with a
"machine translation" badge + a link to the official source.

**One-time setup — and it must be a FREE key so you can never be charged:**
1. Sign up for the **DeepL API free tier** ("Developer" plan) and **add no
   payment method / no paid plan**. This is what guarantees zero cost: a free
   account has nothing to bill — it just stops translating (HTTP 456) when the
   allowance is used, never spilling into charges.
2. Copy its API key — a free key **ends in `:fx`**.
3. Add it as the repo secret **`DEEPL_API_KEY`** (GitHub → Settings → Secrets →
   Actions).

**About the free allowance (important):** DeepL changed it. New free ("Developer")
accounts get **1,000,000 characters *one-time*, not monthly** — once spent, the
free tier stops until you'd upgrade (we won't). Legacy "API Free" accounts get
500,000/month recurring. Either way this pipeline reads DeepL's real remaining
quota and never exceeds it, so **no charge, ever**. Our volume is tiny (~0.2M
once, then ~0.12M/year), so the one-time million lasts **several years**; when it
finally runs out, English simply falls back to the official DE/FR/IT (no charge,
no breakage) — top up by adding a fresh free key if you want it to resume.

`scripts/translate.py` **refuses to run with a non-`:fx` key** (unless you
deliberately set `DEEPL_ALLOW_PAID=1`), reads DeepL's `/v2/usage` and stays under
the limit minus a safety margin, and caps each run — so even if someone changed
the code, a no-payment-method account still can't be billed. Until the secret is
set, `data/mt.json` stays empty and English falls back with a language chip.
See `COMPLIANCE.md` for the full charge-safety framework.

### 2b. Romansh titles — hand-translate  *(optional, as needed)*

DeepL has **no Romansh**, so Romansh vote/act titles aren't machine-translated.
When the weekly fetch finds one missing it lists it in `TRANSLATIONS_TODO.md` /
opens a GitHub issue. To add it, put the `rm` value in
`data/initiatives-translations.json` or `data/sessions-translations.json` under
`titles.<id>`, then commit. Until then Romansh falls back to the official
DE/FR/IT title. (Or ask a Claude Code session to translate the pending titles.)

### 2c. Native Italian brochure arguments  *(optional, ~4×/year)*

DE/FR for/against arguments are fetched automatically (from the Swissvotes-hosted
official brochure). Swissvotes doesn't host **Italian**, so IT falls back to DE/FR
with a language chip. If you want native Italian, once per ballot download the
official IT brochure from admin.ch, drop it in `data/brochures/` as
`YYYYMMDD-it.pdf`, and run `python3 scripts/fetch_arguments.py --force`. See
`data/brochures/README.md`. Purely optional.

> The old AI "overview" review desk is gone — no `Weekly Update.command`,
> `ai_maintain.py` or `review_server.py`.
>
> **Before monetising:** `COMPLIANCE.md` — everything is already commercial-safe
> with the shown attribution; the only recommended (non-blocking) step is one
> courtesy note to BFS about the real-time vote-results feed, or switching that
> feed to BFS's `terms_by` results dataset.

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
shown alone. **Automatic** — `scripts/fetch_arguments.py` runs in the weekly job
and pulls the officially-published brochure (DE/FR) via Swissvotes. Native
Italian is the one optional manual add (§2b); EN/RM fall back with a chip.

**Session votes — "What this vote is about"** (stored on each vote in
`data/sessions/<id>.json`). The official background/summary from the
parliamentary record (Curia Vista) — `InitialSituation`, falling back to
`Description` — in DE/FR/IT, EN/RM falling back. **Automatic**, fetched by
`scripts/fetch_sessions.py` in the weekly job (parlament.ch is commercially
reusable with attribution). A settled session already on disk keeps its data;
run `python3 scripts/fetch_sessions.py --force` once to backfill older sessions.

---

### One-glance weekly checklist
1. **Actions tab → "Fetch live data" green & committed?** That's the whole
   routine — it refreshes votes, **for/against arguments**, financing, cantons,
   sessions, the session "what this vote is about" text, **and the English
   machine translations**. Nothing to run by hand.
2. **Pending Romansh titles?** If the fetch flagged one in `TRANSLATIONS_TODO.md`,
   add the `rm` value and commit (§2b). Optional (English is auto-translated).
3. **Want native Italian arguments for a new ballot?** Drop the official IT PDF in
   `data/brochures/` and re-run `fetch_arguments.py` (§2c). Optional.
4. (Once live) poll backend healthy?

(The cache token is auto-bumped on deploy; `validate.py` runs in CI — run it
locally only if you hand-edited data before pushing.)
