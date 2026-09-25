# Politikch — Change guardrails (rulebook)

**Status: in force since 2026-09-24.** This file is the single source of truth
for the pre-change review and for the automated checks (`scripts/check.py`,
`scripts/data_guard.py`, `scripts/monitor_sources.py`; configuration in
`scripts/guardrails/config.json`). Every rule has an ID; the checks, the review
template and CI all cite these IDs. §14 lists what is automated and what still
relies on review.

> **Not legal advice.** This rulebook turns the laws and source terms we know
> about into checks. A check can prove a change *didn't touch* a risky area, or
> that it *kept* a known-good pattern; it cannot prove a new piece of content is
> lawful. That is why every rule has an enforcement level, and why the items
> marked **LAWYER** stay open until a Swiss lawyer answers them.

Sources: the Stage 1 audit (`audit/reports/stage-1-2026-09-21/`), `COMPLIANCE.md`,
`NOTICE.md`, the code as of `3ce4228`. Legal references were last verified by the
Stage 1 audit on 2026-09-21; rule SRC-10 keeps them from going stale.

---

## 1. Enforcement levels

| Level | Meaning | What happens |
|---|---|---|
| **BLOCK** | Machine-checkable, no judgement needed | `check.sh` fails; pre-push hook refuses; deploy never starts |
| **FLAG** | Machine detects that a sensitive area was touched | Check fails until the change log records an explicit owner sign-off naming the rule ID |
| **REVIEW** | Needs judgement | Covered by the written pre-change review (§11); owner approves before any file is edited |
| **MONITOR** | Can break without any change in the repo (a source changes its terms, a certificate expires) | Scheduled job; opens an issue and, where it matters, stops the data job |
| **LAWYER** | Open legal question | Blocks the named feature/launch until answered in writing; listed in §10 |

**Default rule:** a change that touches a file or pattern no rule recognises is
treated as **FLAG**, not as safe. "Unknown" never means "allowed".

---

## 2. Data sources — terms of use and access (SRC)

Laws: URG Art. 5 (official works not protected), URG Art. 2/10 (copyright in
compilations/non-official text), UWG Art. 5(c) (taking over another's
market-ready work by technical reproduction), StGB Art. 143bis (unauthorised
access), and each source's own licence.

| ID | Rule | Level |
|---|---|---|
| SRC-01 | **Allowlist of sources.** A fetcher may only contact hosts in the source registry (below). A new host in `scripts/*.py`, a workflow, or `js/` is blocked until it has a registry row: owner, licence, commercial status, attribution text, rate limit, robots.txt result, date verified. | BLOCK |
| SRC-02 | **Licence fits the use.** Each registry row states whether reuse is allowed *today* (free site) and *commercially*. A `terms_ask` or "no licence stated" source cannot feed the site once `PAID_PRODUCT_LIVE` is true without written permission on file. | BLOCK (with flag) |
| SRC-03 | **Attribution present.** Every source in the registry has its credit visible on the Sources page / next to the data, in every language. Removing or editing an attribution string (`rec.source`, `financing.source`, `canton.sources`, MT badge naming DeepL, swisstopo credit, Swissvotes CC BY credit with licence name + link) fails. | BLOCK |
| SRC-04 | **CC BY 4.0 details.** Where CC BY applies (Swissvotes, BFS): credit + licence name + link + "modified" note where we transform the data. | BLOCK (string presence) / REVIEW |
| SRC-05 | **Respect robots.txt and rate limits.** Crawl-delay honoured on every request *including retries* (swissvotes.ch, ckan.opendata.swiss, agvchapp: 10 s); no parallel hammering; a retry cap and back-off in every fetcher; a download size cap. robots.txt `Disallow` is honoured for crawling web pages; a path it disallows may be called only when the provider **publicly documents it as an API for programmatic use**, and the registry row cites that documentation (today: the opendata.swiss CKAN API, the LINDAS SPARQL endpoint and the BFS commune-register REST API). | BLOCK (static check of delays/retries) + MONITOR (robots.txt drift) |
| SRC-06 | **No circumvention.** Never bypass a bot block, WAF, login, paywall or CAPTCHA; never scrape admin.ch (it blocks bots); never use endpoints discovered in a site's private front-end bundle unless the source documents or permits them. Browser-imitating User-Agents are forbidden — every fetcher sends one honest UA naming Politikch and a contact address. | BLOCK (UA pattern) / REVIEW |
| SRC-07 | **Official vs. non-official text.** Only texts that are official acts/decisions/explanations (URG Art. 5) may be reproduced verbatim without a licence. Anything else (committee texts, journalism, party material, Swissvotes' own summaries) needs a licence or must be summarised in our own words with a link. | REVIEW + LAWYER (Q1) |
| SRC-08 | **Verbatim means verbatim.** Reproduced official text (brochure arguments, Curia Vista summaries) is never edited, shortened selectively or reordered; any MT is labelled as such. | REVIEW |
| SRC-09 | **Link, don't re-host, media.** Video, images and PDFs from third parties are linked, not embedded or copied (no YouTube embeds, no hosting brochure PDFs). | BLOCK (no `<iframe>`, no third-party media in `data/`) |
| SRC-10 | **Terms drift.** Weekly: re-read each opendata.swiss dataset's licence code via the CKAN API, and each source's robots.txt. If anything changed, the data job stops publishing that source and opens an issue. | MONITOR |
| SRC-11 | **Rights-holder takedown.** A documented path to remove a source's data within 48 h if a rights-holder objects (kill switch per source in the fetchers). | REVIEW (exists?) |

**Source registry (to be machine-readable in `scripts/sources.json`):**
parlament.ch OData (`terms_by`, verified 2026-09-24) · Swissvotes dataset + brochure PDFs (CC BY 4.0; brochure text via Art. 5) · BFS election results (CC BY 4.0) · BFS municipality register (`terms_open`) · LINDAS / Federal Chancellery (no licence on the cubes; LINDAS publishes open government data for unrestricted reuse; content is official facts — credit the Chancellery) · EFK financing register (`terms_open`, verified 2026-09-24) · VoteInfo real-time feed (**`terms_ask`**) · swisstopo swissBOUNDARIES3D via labs.karavia.ch (attribution) · DeepL API Free (output ours, credit DeepL).

---

## 3. Personal data & privacy (PRIV)

Laws: revFADP (nDSG) Art. 5(c) (political opinions are **sensitive data**),
Art. 6 (lawfulness, purpose, proportionality), Art. 7 (privacy by design and
default), Art. 8 (security), Art. 9 (processors), Art. 16–17 (disclosure
abroad), Art. 19–20 (duty to inform), Art. 24 (breach notification), Art. 25
(access), Art. 60 (fines on the individual); FMG Art. 45c (storing/reading data
on the visitor's device); GDPR/ePrivacy for EU visitors (reach UNVERIFIED — Q7).

| ID | Rule | Level |
|---|---|---|
| PRIV-01 | **A visitor's political choices never leave their device.** Votes, profile, party alignment and anything derived from them are never sent to any server, never put in a URL, share text, analytics event, error message or log. The only exception is the documented anonymous poll (PRIV-07). | BLOCK (static: data from `myvotes` never reaches `fetch`, `track()`, `location`, share URLs) |
| PRIV-02 | **Network allowlist.** The only origins the browser may contact are `'self'` and the ones in the CSP `connect-src`. Adding an origin to the CSP, a new `fetch`/`sendBeacon`/`XMLHttpRequest`/`WebSocket` target, an `<img>`/`<link>`/`<script>` to a third-party host, or a third-party font (e.g. Google Fonts) is blocked unless the privacy policy names that recipient, in every language, in the same change. | BLOCK |
| PRIV-03 | **Device storage inventory (FMG 45c).** Every `localStorage`/`sessionStorage`/IndexedDB/cookie key is listed in an inventory with its purpose and is described on the Privacy page. A new key without both fails. Cookies: none allowed. | BLOCK |
| PRIV-04 | **Privacy policy matches the code.** The Privacy page must describe every processor (GitHub, Cloudflare, Hostpoint), every recipient abroad and its transfer basis, every data field analytics records, retention periods, and how to object — in all five languages. Changing `analytics-worker/`, `js/analytics.js`, `ANALYTICS_API`, `POLL_API`, the CSP or a storage key without touching the matching `privacy.*` keys fails. | FLAG |
| PRIV-05 | **Analytics field allowlist.** The worker may store only the fields listed in the policy. A new column in `schema.sql`, a new `track()` event name, a new `cf.*` property, or storing an IP / full user-agent / unhashed identifier is blocked. Retention (7 days raw, daily salt deletion) cannot be lengthened without a policy change. Search terms and vote choices are never sent. | BLOCK |
| PRIV-06 | **Opt-outs keep working.** GPC, DNT, `?analytics=off` and the Privacy-page switch must stay honoured; localhost/automated browsers stay excluded. | BLOCK (unit check on `analytics.js`) |
| PRIV-07 | **Poll.** Turning on `POLL_API` is a new processing of political opinions: needs the backend's IP/rate-limit design reviewed (no IP stored against a vote), the Privacy page section, and the "unofficial straw poll" label. | FLAG + LAWYER (Q9) |
| PRIV-08 | **Private donors are never identified.** A donation by a natural person reveals a political opinion (sensitive data), so individuals appear only as "Private individual" with amount and date — no name, no place, no page, no search entry, no grouping across records. Enforced three times: the fetcher never stores the name/place, `validate.py` fails if one appears, and `app.js` strips them on load. Only organisations are named. *(Owner decision 2026-09-24.)* | BLOCK |
| PRIV-09 | **Members of parliament.** Per-member votes are public official acts and may be shown; never combine them with non-official personal data (private life, social media, photos not from the official source). | REVIEW |
| PRIV-10 | **No personal data in the repo.** No real email addresses (other than the site's own aliases), phone numbers, postal addresses, IPs, or names of private individuals outside `data/financing.json`. | BLOCK (regex scan incl. git history on new commits) |
| PRIV-11 | **Profiling stays on-device.** Party alignment/"leaning" calculations run only in the browser. Moving any of it server-side or into accounts triggers the Stage 2 legal module (explicit consent, DPIA). | FLAG |
| PRIV-12 | **Breach readiness.** A written decision tree for a breach (FDPIC notification "as soon as possible", Art. 24) exists before any server stores visitor data. | REVIEW |

---

## 4. Truthfulness, neutrality & political integrity (POL)

Laws: UWG Art. 3(1)(a) (disparaging others with false/misleading statements),
UWG Art. 3(1)(b) (misleading statements about oneself), StGB Art. 173–174
(defamation), ZGB Art. 28 (personality rights), BPR/StGB Art. 279–283 (offences
against votes and elections), WSchG (coats of arms). Plus the site's own
promise to be non-partisan.

| ID | Rule | Level |
|---|---|---|
| POL-01 | **Both sides, always together.** For/against arguments render together, with equal prominence, the same collapse behaviour and the same length handling. Neither side may ever render alone. | BLOCK (render test) |
| POL-02 | **No invented figures.** Every number on the site comes from a fetched source or is a labelled placeholder. No hand-typed results, seats, percentages or money figures in `js/` or `index.html`. | BLOCK (static scan for numeric literals in copy) / REVIEW |
| POL-03 | **Vote dates, results and "how to vote" are high-harm.** Any change to how dates, results, deadlines or the voting-process steps are computed or shown needs a render check against the source for the next and last ballot; the site must never show a wrong ballot date or result. | FLAG |
| POL-04 | **Editorial = labelled.** Party descriptions, spectrum placements, topic labels, donor descriptions and leaning graphs are marked as editorial approximations, link to the methodology page, and cite what they're based on. | REVIEW |
| POL-05 | **Neutral wording.** No evaluative adjectives about parties, people, donors or proposals ("extreme", "dangerous", "radical", "fringe", …); no calls to vote either way. A banned-term list per language (EN/DE/FR/IT/RM) runs on every changed string; a hit never blocks outright but the change cannot merge until the owner signs off that hit by rule ID in the change log. *(Owner decision 2026-09-24.)* | FLAG |
| POL-06 | **Symmetry.** Edits to one party's text are checked for equal treatment (length, tone, structure) across all parties; spectrum changes need a stated source. | REVIEW |
| POL-07 | **Donor descriptions.** Descriptions of organisations in `donor-descriptions.json` state only verifiable facts from the organisation's own/official sources, with a source link per entry. No descriptions of private individuals ever. | BLOCK (source field required) + REVIEW |
| POL-08 | **Straw polls aren't results.** Poll or "how visitors voted" figures are always labelled unofficial and non-representative, visually distinct from official results. | BLOCK (label present) + LAWYER (Q9) |
| POL-09 | **Quiet period** *(adopted by owner 2026-09-24)*. In the 10 days before a federal ballot, changes to the pages about the proposals on that ballot are limited to corrections, privacy fixes and the automatic data refresh. Not a legal requirement: a last-minute change to how a proposal is presented is when a mistake does the most harm and when a change is most easily read as taking sides. Swiss pollsters and media apply a similar self-imposed pause on new polls. | BLOCK (date check against the next ballot in `initiatives.json`) |
| POL-10 | **No official look.** No Swiss coat of arms (shield), cantonal or communal arms, federal logos, or wording implying we are an authority ("official", "Confederation", "the Federal Chancellery says"). Party logos not used; party colours only. Independence disclaimer stays on the legal page. | BLOCK (asset + phrase scan) |
| POL-11 | **Corrections path.** The contact/corrections route stays reachable in every language; a known factual error is fixed or placeholder-ed, never left up. | REVIEW |
| POL-12 | **Claims about ourselves.** No "non-commercial", "official", "certified", "complete", "real-time" claims unless true. Changes to `PAID_PRODUCT_LIVE` or anything advertising a paid product require the Impressum with real name + postal address (UWG Art. 3(1)(s)) and ToS in the same change. | BLOCK (phrase scan) + FLAG |
| POL-13 | **AI/MT labelling.** Machine translation is always badged and credits DeepL; no LLM-generated text published as fact. Any future AI-written content is labelled and human-reviewed before publishing (EU AI Act Art. 50 for EU readers). | BLOCK (badge present where `mt.json` used) + REVIEW |

---

## 5. Security & integrity (SEC)

| ID | Rule | Level |
|---|---|---|
| SEC-01 | **No unescaped upstream or user text into HTML.** Every value from `data/*.json`, the URL, storage or the network passes through `escapeHtml`/`escapeAttr` or `textContent` before an `innerHTML`/`insertAdjacentHTML` sink. New sinks with unescaped interpolation are blocked. | BLOCK (sink scanner) |
| SEC-02 | **Validator rejects markup in data.** No `<`, `>` or `javascript:` in any fetched text field; URLs in data must be `https:` on registry hosts. | BLOCK |
| SEC-03 | **CSP only tightens.** `script-src 'self'` stays; no `'unsafe-eval'`, no inline scripts, no third-party script hosts, `object-src 'none'`, `base-uri 'self'`, `form-action 'none'`. Any CSP change is FLAG; any loosening is BLOCK. | BLOCK |
| SEC-04 | **No `eval`, `new Function`, `document.write`, string `setTimeout`.** | BLOCK |
| SEC-05 | **No secrets.** No API keys, tokens, private keys or `.dev.vars` content in any tracked file or commit; DeepL key only as a GitHub secret. | BLOCK (secret scan) |
| SEC-06 | **Deploy allowlist intact.** The allowlist and file-type guard in `deploy.yml` can't be widened without FLAG; `audit/`, `*.md`, `scripts/`, `analytics-worker/`, `data/brochures/` are never published. | BLOCK |
| SEC-07 | **Workflows least-privilege.** Every workflow has an explicit `permissions:` block; actions pinned to full SHAs; `persist-credentials: false` where third-party code runs; no `pull_request_target`; no untrusted `${{ }}` interpolation into `run:`. | BLOCK |
| SEC-08 | **Dependencies pinned.** Python requirements pinned to exact versions + hashes; new dependency = FLAG with licence check (§7). Front-end stays zero-dependency. | BLOCK / FLAG |
| SEC-09 | **Fetcher hardening.** Size caps on downloads, timeouts, IDs from upstream validated before being used as file names, output confined to `data/`. | BLOCK (static) |
| SEC-10 | **Maintenance switch untouchable by automation.** No script or workflow may create or delete `MAINTENANCE_MODE`; the deploy guard for it stays. | BLOCK |
| SEC-11 | **External links safe.** `target="_blank"` always with `rel="noopener noreferrer"`; share targets built only from our own URL + our own text. | BLOCK |

---

## 6. Availability, correctness & safety of the running site (OPS)

| ID | Rule | Level |
|---|---|---|
| OPS-01 | **Validation gates deploy.** Deploy runs only after `check.sh` passes on the exact commit. | BLOCK |
| OPS-02 | **Smoke test every route.** Headless load of every route in all five languages: no console errors, no failed requests, no raw i18n keys, no `undefined`/`NaN` on screen. | BLOCK |
| OPS-03 | **i18n parity + no hardcoded copy.** Every key in all five languages; no user-facing string literals in `js/`/`index.html`. | BLOCK |
| OPS-04 | **Data-job sanity.** A weekly data refresh that shrinks a file by >20 %, drops a past vote, changes a decided result, or changes seat totals is held for review instead of auto-published. | BLOCK (diff guard in data job) |
| OPS-05 | **Accessibility floor.** axe/pa11y on main routes: no new WCAG 2.2 AA violations (contrast, names, focus, lang). | BLOCK (no regressions) |
| OPS-06 | **Mobile + performance floor.** No horizontal scroll at 375 px; no data file > 2 MB loaded on first paint. | BLOCK |
| OPS-09 | **Free DeepL plan = public texts only.** DeepL's terms let it keep everything sent on the free Developer plan permanently (T&C 3.3.2). Only already-public official texts may go there. Anything non-public or personal (user input, account data, drafts) needs a paid plan with a data processing agreement first. | BLOCK (`translate.py` may only read `data/overviews`, `data/sessions`) + REVIEW |
| OPS-07 | **Cost can't run away.** DeepL stays on a `:fx` key with no payment method; Cloudflare Worker stays on the free plan; any change that could create a bill (paid key, `DEEPL_ALLOW_PAID`, a paid plan in `wrangler.jsonc`) = FLAG. | FLAG |
| OPS-08 | **Rollback is one step.** Each deploy is a single commit; the maintenance switch and a revert are documented in `MAINTENANCE.md`. | REVIEW |

---

## 7. Licences of what we ship (LIC)

| ID | Rule | Level |
|---|---|---|
| LIC-01 | Fonts ship with their OFL; any new font/icon/image has a recorded licence allowing commercial web use. No stock images without a licence file. | BLOCK |
| LIC-02 | New code dependency: licence must be permissive (MIT/BSD/Apache/ISC/OFL); no GPL/AGPL in shipped front-end; no "non-commercial" licences anywhere. | BLOCK |
| LIC-03 | The repo's MIT licence must not appear to cover third-party data — `data/` keeps a notice that it stays under its sources' terms. | BLOCK (notice present) |
| LIC-04 | No copying of text/code from other sites or projects without a compatible licence. | REVIEW |

### 7.1 Licensing model: "open data, protected website" — *adopted by owner 2026-09-24, implemented 2026-09-24*

Goal: anyone may reuse the **data** (including commercially), nobody may clone
the **website**.

**What Swiss law already gives us, and what it doesn't**

- **Facts are free.** Seat counts, results, amounts and dates can't be
  copyrighted anywhere. Switzerland has **no database right**. The EU's database
  right only protects makers based in the EU. So a licence can't stop anyone
  reusing the facts. It can only set clear terms, like attribution, for
  anything we do own.
- **Official texts** (URG Art. 5): anyone may reuse them, and we can't license
  or restrict them.
- **What we do own:** original editorial text (party descriptions, positions,
  donor descriptions, methodology), our own selection and arrangement where it
  is original (URG Art. 4), hand-made translations, UI copy, design, code (URG
  Art. 2(3)), the name and the logo.
- **Caveat on AI-written material.** Swiss copyright requires a *human*
  intellectual creation. Code and text that were largely AI-generated may have
  thin or no copyright, which weakens "all rights reserved" as protection for
  the site. The dependable protections for the website are therefore
  **(a)** a registered trademark for the name, **(b)** UWG Art. 5(c), which
  forbids taking over another's market-ready work product by technical
  reproduction without effort of one's own (this protects against a
  wholesale clone even without copyright), and **(c)** not granting a licence
  that permits cloning.
- **The current MIT licence works against the goal.** It lets anyone copy,
  rebrand and sell the whole site, code and data. Changing the licence only
  applies from that point on. Every version already published under MIT stays
  MIT for anyone who has a copy (MIT grants are generally treated as
  irrevocable).

**Proposed split**

| Layer | Examples | Proposed terms | Why |
|---|---|---|---|
| Our own data & editorial content | `parties.json` descriptions/positions/spectrum, `donor-descriptions.json`, `*-translations.json`, computed tallies/leanings, methodology text | **CC BY 4.0** (reuse incl. commercial, credit "Politikch (politikch.ch)") | Matches Swissvotes/BFS; simplest for reusers; also covers database rights where they exist. *Alternative:* ODbL (share-alike — derived databases must stay open) |
| Machine translations | `mt.json` | CC BY 4.0 **+ "Machine translation by DeepL"** credit kept | DeepL assigns us the output but requires the credit |
| Official texts | brochure arguments, Curia Vista summaries, official titles | **Public domain, URG Art. 5** — stated as such, not licensed by us | We don't own them; committee arguments remain lawyer Q1 |
| Third-party datasets passed through | parlament.ch, BFS, LINDAS, Swissvotes, swisstopo geometry, EFK | **Under the original source's terms**, named per file with its required credit | We can't relicense them. **VoteInfo (`terms_ask`) and EFK (unknown)** are marked "commercial reuse: ask the source" |
| Website: code, CSS, layout, UI copy, share-image design | `js/`, `css/`, `index.html`, `i18n.json` UI strings | **All rights reserved** (source visible, no reuse licence) — or a source-available licence (e.g. PolyForm Strict) | Stops cloning; still lets people read the code |
| Name & logo | Word mark **PolitikCH**; logo = **"PCH" set in Playfair Display** (the site's display font); the language domains | **Not licensed**; register with the IPI | Stops lookalike sites and false endorsement regardless of copyright |
| Fonts | `fonts/` | Stay under **SIL OFL 1.1** (their own licence) | Not ours |

**How it is implemented**

1. ✅ `LICENSE`: all rights reserved for the website, and it points to the
   data licence. It records that versions up to `733e141` were MIT and keep that
   licence. `data/LICENSE.txt` (published) is generated from `scripts/licences.py`.
2. ✅ Every published data file carries `_meta.license`, `licenseUrl`,
   `attribution` and `commercialReuse`, taken from `scripts/licences.py`, the
   single source of truth. The fetchers stamp their own output, and
   `python3 scripts/licences.py --stamp` stamps hand-edited files.
   `i18n.json` and `legal.json` are website text and are not licensed.
3. ✅ **Data & reuse** page (`#/page/reuse`, footer link) in EN/DE/FR/IT. As
   with the other legal pages, Romansh falls back to German with a note. The
   legal notice's "Intellectual property" section now points to it.
4. *Optional, not done:* move the website code to a private repo and publish only
   `data/` publicly. Note that GitHub Pages from a private repo needs a paid
   GitHub plan, or the planned move off Pages.
5. *Owner's step, not done:* register the marks with the IPI (Swissreg). Before filing:
   - **Descriptiveness risk.** "Politik" + "CH" can be read as "politics,
     Switzerland"; the IPI refuses marks that only describe the service plus an
     indication of origin (MSchG Art. 2(a)). Plain lettering in a standard font
     rarely overcomes that. Get an opinion or an IPI assisted search first.
   - **"PCH"** is short and used by others; a similarity search is needed.
   - **Font:** Playfair Display is under the SIL OFL, which allows using it in a
     logo or trademark. The font itself stays OFL; only your arrangement is
     protected.
   - The current site logo also has a white cross on red. It isn't part of the
     planned marks. Keep it out of the filing (Coat of Arms Act, Q2).

**Rules once adopted**

| ID | Rule | Level |
|---|---|---|
| LIC-05 | Every published data file carries `_meta.license`, `_meta.attribution`, `_meta.commercialReuse`; missing or blank fails. | BLOCK |
| LIC-06 | A file's licence must match the source registry (§2). Nobody may relabel third-party or `terms_ask` data as CC BY. | BLOCK |
| LIC-07 | Changes to `LICENSE`, `data/LICENSE.txt`, the Data & reuse page or the IP section of the legal notice. | FLAG |
| LIC-08 | No private individuals' data in any downloadable/licensed file (ties to PRIV-08). | BLOCK |
| LIC-09 | The name, logo and domains are never described as licensed; the Data & reuse page keeps its "no endorsement / don't imply affiliation" line. | BLOCK (string present) |

---

## 8. Hosting, domains & providers (HOST)

| ID | Rule | Level |
|---|---|---|
| HOST-01 | **GitHub Pages terms.** No paid product, accounts, passwords or card data on Pages. `PAID_PRODUCT_LIVE=true` while `deploy.yml` targets Pages is blocked. | BLOCK |
| HOST-02 | Any new provider (hosting, email, analytics, CDN, payments, translation) needs: processor agreement (revFADP Art. 9), data location + transfer basis (Art. 16), and a Privacy-page entry. | FLAG |
| HOST-03 | `CNAME`, DNS-dependent URLs and the language-domain map (`LANG_DOMAIN` in `share.js`, `?lang=` handling) change only with a DNS check that every domain still serves a valid certificate. | FLAG + MONITOR |
| HOST-04 | Monitor: certificate expiry, domain expiry/auto-renew, DNS record changes, uptime. | MONITOR |

---

## 9. Process rules (PROC)

| ID | Rule | Level |
|---|---|---|
| PROC-01 | **Plan before edit.** Every change starts with the pre-change review (§11); no file is edited until the owner approves it. | REVIEW |
| PROC-02 | **Checks before anything leaves the machine or goes live.** The pre-push hook runs `check.py --strict`; CI runs it on every branch/PR; `deploy.yml` deploys only after it passes on the exact commit. *Optional extra:* protect `main` in GitHub settings. | BLOCK |
| PROC-03 | **Local preview is mandatory.** The change is viewed at `localhost:8001` (all affected routes, at least EN + DE + FR, desktop + 375 px) before the push, with a screenshot in the change log. | REVIEW |
| PROC-04 | **Sign-offs are recorded in git.** A flagged rule is signed off with a line `Approved-Rule: <ID> — reason` in a commit message of the change, added only on the owner's say-so. The git history is the change log. | BLOCK (unsigned flags fail with `--strict`) |
| PROC-05 | **The rulebook itself.** Editing `GUARDRAILS.md`, the check scripts, `scripts/guardrails/*` (config, sink baseline, robots snapshot) or the hook is FLAG and must say why; a rule can be relaxed only by the owner, never by an automated change. | FLAG |

---

## 10. Open legal questions (LAWYER) — block the named feature, not the site

Q1–Q10 are in `audit/AUDIT_PLAN.md` §10 (Art. 5 URG and committee arguments on
a commercial site · emblems/official appearance · Impressum for a sole
individual · defamation/UWG exposure of editorial descriptions · DPIA/records ·
consent for political-opinion data · GDPR targeting · VAT · straw polls before a
vote · processor contracts). This review adds:

- **Q11 — Republishing individual donors.** *Resolved by design 2026-09-24:*
  individuals are no longer named (PRIV-08). Residual question: the names
  remain in the public git history of earlier `data/financing.json` commits —
  is a history rewrite warranted, given the EFK publishes the same names by law?
- **Q12 — EFK register reuse.** *Resolved 2026-09-24:* opendata.swiss lists the
  EFK "Politikfinanzierung" dataset as `terms_open` (free use, including
  commercial; credit courteous but not required).
- **Q13 — Analytics and EU visitors.** Does reading screen size / user agent for
  statistics fall under ePrivacy Art. 5(3) consent for EU visitors, and is
  city-level location proportionate under revFADP Art. 6?
- **Q14 — Donor/party descriptions.** Are descriptions of named organisations
  (UBS, economiesuisse, …) next to their political donations exposed under UWG
  Art. 3(1)(a) or ZGB Art. 28 if a wording is contested?

---

## 11. The pre-change review (what Claude produces before editing anything)

For every request, before touching a file:

1. **Scope** — what will change, and which files.
2. **Rule map** — every rule ID the change could touch, from the trigger table
   below, with "not affected / affected — how it stays compliant".
3. **New external contact?** hosts, origins, storage keys, data fields, providers.
4. **Content check** — for any user-facing text: neutrality, symmetry,
   labelling, all five languages.
5. **Risks & unknowns** — anything that maps to a LAWYER question or no rule.
6. **Test plan** — which routes/languages will be previewed locally, which
   checks run.
7. **Verdict** — GO / GO WITH SIGN-OFF (listing the FLAG IDs) / STOP.

The owner approves; then the edit, `check.sh`, local preview, change-log entry.

### Trigger table (file or pattern → rules checked)

| Touched | Rules |
|---|---|
| `scripts/fetch_*.py`, `translate.py`, `requirements*.txt`, `fetch-financing.yml` | SRC-*, SEC-07/08/09, OPS-04/07 |
| `data/*.json` (fetched) | SEC-02, POL-02/03, OPS-04, PRIV-08/10 |
| `data/parties.json`, `donor-descriptions.json`, `legal.json`, editorial i18n | POL-04/05/06/07/10/12, OPS-03 |
| `data/i18n.json` `privacy.*`, `legal.*` | PRIV-04, POL-12, OPS-03 |
| `js/myvotes.js`, `js/share.js` | PRIV-01/11, SEC-11 |
| `js/analytics.js`, `analytics-worker/**`, `ANALYTICS_API` | PRIV-02/04/05/06, HOST-02, OPS-07 |
| `js/config.js` (`POLL_API`, `PAID_PRODUCT_LIVE`) | PRIV-07, POL-12, HOST-01 |
| `index.html` (CSP, meta, assets) | SEC-03, PRIV-02, POL-10, LIC-01 |
| any `innerHTML`/template rendering in `js/app.js` | SEC-01, POL-01/08/13, OPS-02/03 |
| vote pages, dates, results, process steps | POL-01/03/09 |
| `fonts/`, images, icons | LIC-01, POL-10 |
| `images/*` (owner's photos) + `images/LICENSES.json` | LIC-01, POL-10, PRIV-09 (a photo passes only with a licence record; alt text in five languages) |
| `js/site-settings.js` (admin) | reviewed; POL-03 when the Parliament final-vote links change |
| `js/news.js`, `js/design.js`, `js/site-images.js` | SEC-01 (sink scanner), OPS-03 |
| `admin/server.py` (local admin, publishes) | PROC-02 |
| `.github/workflows/deploy.yml` | SEC-06, SEC-07 |
| `.github/workflows/*` | SEC-06/07/10, OPS-01 |
| `CNAME`, `LANG_DOMAIN`, `?lang=` | HOST-03 |
| `GUARDRAILS.md`, `check.sh` | PROC-05 |
| anything else | default FLAG |

---

## 12. Known state today (what the first run will report)

These are not new problems introduced by a change. They're what the checks
will find the first time they run. Each is either fixed or explicitly accepted
by the owner, with the reason recorded:

1. ~~Validation doesn't gate deploy~~ — **fixed 2026-09-24**: `deploy.yml` runs
   the checks first (OPS-01).
2. ~~54 private individuals named as donors~~ — **fixed 2026-09-24** (PRIV-08);
   names remain in earlier public commits (Q11).
3. ~~EFK register reuse terms unrecorded~~ — **resolved 2026-09-24**: `terms_open`.
4. **VoteInfo feed is `terms_ask`** — fine while free; blocks `PAID_PRODUCT_LIVE`
   until permission or a source switch (SRC-02).
5. **Donor descriptions have no per-entry source field** (POL-07).
6. **HTML insertions (SEC-01):** 421 existing unescaped insertions (386 in
   `app.js`, 23 in `myvotes.js`, 12 in `share.js`) are recorded in
   `scripts/guardrails/sinks-baseline.json`. New ones are blocked. The
   existing ones are mostly colours, numbers and IDs, but haven't been reviewed
   one by one yet. The list may only shrink.
7. ~~No storage inventory~~ — **done**: `storageKeys` in the config (PRIV-03).
8. **Uncommitted changes in the working tree** now pass every BLOCK check. The
   flags they raise need the owner's sign-off at commit.
11. **Languages (2026-09-24).** Filled once, enforced from now on:
    - Every editorial text in all five languages: canton names, capitals and
      descriptions; donor descriptions; vote descriptions (now also composed in
      Romansh by the fetcher); all initiative titles in English and Romansh.
      `validate.py` `check_all_languages()` blocks gaps.
    - The official arguments now cover decided votes and referendums too, with
      the correct side per author, and are cleaned of brochure layout.
      `validate.py` `check_argument_text()` blocks layout or one-sided text.
    - Still falling back by design: Romansh for long official texts (arguments,
      session summaries) has no machine translation (DeepL lacks Romansh), so
      Romansh readers see the official German with a language chip. The legal
      pages show German with a note, like before. English and Italian argument
      translations come from DeepL in the weekly job, arguments first.
10. ~~French arguments for vote 6890 (27 Sept) had only the "against" side~~ —
    **fixed 2026-09-24**: fetcher matching bug fixed, French "for" side restored,
    one-sided languages now dropped by the fetcher, blocked by the checks and
    skipped by the page (POL-01).
9. Stage 1 items still open per its report (branch protection, language-domain
   DNS/TLS, Domain Shield, Dependabot etc.) — to be re-checked, not assumed.

---

## 13. Automated processes register (verified 2026-09-24)

Everything that runs without a person pressing a button. Each row must stay
✅, or be ⚠ with an accepted reason. A new automated process = FLAG (PROC-05)
until it has a row here.

### 13.1 Weekly data job — `.github/workflows/fetch-financing.yml` ("Fetch live data", Mondays 04:00 UTC + manual)

| Step | Contacts | Terms (checked 2026-09-24) | Access rules | Personal data | Status |
|---|---|---|---|---|---|
| `fetch_initiatives.py` — vote results & titles | ckan.opendata.swiss (metadata), ogd-static.voteinfo-app.ch / dam-api.bfs.admin.ch (per-day JSON) | VoteInfo resources **`terms_ask`** | CKAN API is documented for developers; robots `Disallow: /api/` + Crawl-delay 10 → delay now honoured incl. retries | none | ✅ free site · ⚠ **blocks `PAID_PRODUCT_LIVE`** until BFS permission or switch to the `terms_by` results datasets |
| same — pending & upcoming initiatives | cached.lindas.admin.ch/query (SPARQL) | no licence stated on the cubes; LINDAS = open government data for unrestricted reuse; official facts | robots `Disallow: /` is for crawling; the cached SPARQL endpoint is the one LINDAS recommends for live websites | none | ✅ |
| same — party recommendations, EN short titles | swissvotes.ch dataset CSV | CC BY 4.0 | Crawl-delay 10 → **was not honoured on retries; fixed 2026-09-24** | none | ✅ (fixed) |
| `fetch_arguments.py` — for/against arguments | swissvotes.ch brochure PDFs | brochure text: URG Art. 5; Swissvotes CC BY 4.0 | Crawl-delay 10 on every attempt; **size cap added 2026-09-24** (PDFs go into a parser) | none | ✅ · committee arguments on a commercial site = Q1 |
| `fetch_financing.py` — party & campaign finance | politikfinanzierung.efk.admin.ch (the register's own public JSON + XLSX download endpoints) | **`terms_open`** (opendata.swiss "Politikfinanzierung") | no robots.txt; unauthenticated; 0.5 s spacing; size cap added | **private donors: name & place never stored (PRIV-08, fixed 2026-09-24)**; organisations named | ✅ · note: the official resource is the register's Exports page; we read the same register's per-filing downloads — public and unauthenticated, but not separately documented as an API |
| `fetch_cantons.py` — NC 2023 results by canton | dam-api.bfs.admin.ch | BFS `terms_by` (credit) | no robots.txt; single request | none | ✅ |
| same — municipality counts | www.agvchapp.bfs.admin.ch/api | `terms_open` | robots `Disallow: /api*`, Crawl-delay 10; REST API is officially documented (BFS PDF); one request/week, no retry | none | ✅ |
| `fetch_sessions.py` — Federal Assembly final votes | ws.parlament.ch OData | **`terms_by`** (verified) | no robots.txt; 0.35 s spacing; size cap added | per-party tallies only; MPs' votes are official public acts | ✅ |
| `translate.py` — MT: EN (titles, summaries, arguments), IT (arguments) | api(-free).deepl.com | DeepL T&C: output ours; credit DeepL (named in both badges) | contracted API; free key, no payment method, usage caps (~5 years at current volume) | none sent (public official texts only); free tier may train on them — immaterial | ✅ · both sides translated as one item; `validate.py` rejects a one-sided set (POL-01) · ⚠ **not running: the `DEEPL_API_KEY` secret appears unset** (the step took 0 s on 2026-09-22) |
| `check_translations.py` | nothing (local) | — | — | none | ✅ |
| `validate.py` | nothing (local) | — | — | now enforces PRIV-08 | ✅ |
| `monitor_sources.py` — runs first | ckan.opendata.swiss, every fetched host's robots.txt, own domains' certificates | — | Crawl-delay honoured | none | ✅ stops the job if a licence code or robots.txt changed (SRC-10); certificate or unreadable-licence warnings open/refresh the issue "Weekly source check: warnings to review", closed automatically after a clean week (HOST-04) |
| `data_guard.py` + `check.py --data-job` — before the commit | nothing (local) | — | — | — | ✅ refuses a refresh that changes decided results, loses votes/sessions or shrinks files (OPS-04); override only by a manual re-run with `allow_data_changes` |
| Commit & push to `main` as `politikch-bot` | GitHub | — | token only in this step | — | ✅ only after the monitor, validator, data guard and checks pass |
| Open/refresh "Weekly data job stopped" issue | GitHub (public issue) | — | — | run link only | ✅ on failure |
| Open/refresh "Translations needed" issue | GitHub (public issue) | — | — | official titles only | ✅ |

Runs while the site is in maintenance mode too. Compliant, but it contacts sources and spends DeepL's one-time allowance for a site that is off.

### 13.2 Deploy — `.github/workflows/deploy.yml` (push to `main`, after the data job succeeds, manual)

| What | Status |
|---|---|
| Allowlisted files only; file-type guard; cache-busting | ✅ |
| Maintenance mode publishes only the notice page, `robots: Disallow: /`, keeps security.txt | ✅ (active now) |
| After the data job: deploys only if that job succeeded (which includes `validate.py`) | ✅ |
| After a human push: the `check` job must pass (with sign-offs) before the `deploy` job starts | ✅ OPS-01 (since 2026-09-24) |

### 13.3 Other GitHub automation

| What | Status |
|---|---|
| `validate.yml` ("Checks") runs `check.py --strict` on every PR and non-main push (read-only token) | ✅ |
| Dependabot — weekly PRs for Actions (SHA-pinned) and pip (exact pins); **never auto-merged** | ✅ · pip pins have no hashes yet (SEC-08) |
| GitHub Pages access logs (IP etc.) — GitHub, USA, DPF-certified | ✅ disclosed in the Privacy page |

### 13.4 Analytics — `analytics-worker/` on Cloudflare (always on; receives nothing while the site is off)

| What | Status |
|---|---|
| Beacons only on the live https site; never on localhost or automated browsers; never with GPC/DNT or after opt-out | ✅ |
| Only allowlisted event names; route/referrer/lang validated by pattern; body ≤ 4 KB; flood guard; CORS limited to the site's origins | ✅ |
| Stored fields = exactly those in the Privacy page (page, time, referring site, country/region/city, device, browser, OS, screen, language, named actions); **no IP, no search text, no vote choice** | ✅ |
| Visitor hash = daily salt + IP + UA; salt deleted after its day (hourly cron); raw rows deleted after 7 days; only daily totals kept | ✅ |
| Dashboard behind a password, with lockout after failed attempts; strict CSP; `no-store` | ✅ |
| Database in the EU — set when the database was created (`--jurisdiction eu`), **not visible in the repo** | ⚠ owner to confirm in the Cloudflare dashboard |
| EU visitors: does ePrivacy require consent for reading screen size/UA? | ⚠ Q13 |

### 13.5 In the visitor's browser, without them clicking anything

| What | Status |
|---|---|
| Picks the language from `?lang=` or the browser language; saves it (`politikch-lang`) | ✅ disclosed (privacy "storage") |
| Sends analytics page views (see 13.4) | ✅ disclosed, objectable |
| `?analytics=off/on` stores an opt-out flag, then strips the parameter from the address | ✅ disclosed in the analytics section |
| Votes the visitor casts are saved on the device (`politikch-votes`) — only after they click | ✅ disclosed |
| Poll sync (`politikch-votes-pushed`, network calls) — **off** (`POLL_API` empty); the key is never written while off | ✅ · turning on = PRIV-07 (the key must then be added to the storage text) |
| 404 page redirects to the home page keeping the `#` route | ✅ |

### 13.6 Local admin site — `admin/` (never published)

Runs only on the owner's machine (`Start Admin.command`, 127.0.0.1:8002; a read-only,
uncached copy of the site for its preview on :8003). It writes only
`js/site-settings.js`, `js/site-images.js`, `images/` and its own `admin/.backup/`,
and every change needs a per-start token and a same-origin request.

It has two separate publish buttons, each pressed by the owner:

| Button | Commits | Tab |
|---|---|---|
| Make changes live | `js/site-settings.js` only | Design / Vote links |
| Publish images | `images/` + `js/site-images.js` only | Images |

Each one builds the commit in a temporary, clean git worktree on `origin/main` (so
other uncommitted work is neither published nor judged), runs `check.py` there,
asks the owner to type a reason for every flagged rule (those become the
`Approved-Rule:` lines, PROC-04) and to confirm the local preview (PROC-03), then
commits and pushes through the normal pre-push hook — never `--no-verify`. It
refuses when `main` is behind GitHub or the 1.1 code isn't on `origin/main` yet.
Uploaded photos show in the admin preview straight away but reach the public site
only through "Publish images". Everything else still goes through the normal git flow.

### 13.7 Outside this repo (not reviewed here)

The three language-domain redirect repos, DNS/registrar (Hostpoint), mailboxes.
Stage 1 findings E-01/E-02/G-01 cover them — re-check, don't assume.

---

## 14. What is automated (since 2026-09-24)

**Commands**

| Command | When |
|---|---|
| `python3 scripts/check.py` | After every edit: your working tree vs `origin/main`. Blocks fail; flags are listed for sign-off |
| `python3 scripts/check.py --base <ref> --strict` | Pre-push hook, CI, deploy: unsigned flags fail too |
| `python3 scripts/data_guard.py` | Data job, before committing a refresh |
| `python3 scripts/monitor_sources.py [--update]` | Data job, first step; `--update` accepts reviewed robots.txt changes |
| `git config core.hooksPath .githooks` | Once per clone, to enable the pre-push hook |

**Coverage**

| Automated — BLOCK | Automated — FLAG (needs sign-off) | Still REVIEW / not yet automated |
|---|---|---|
| Data validity and invariants, i18n parity (VALIDATE, OPS-03) · SEC-01 (ratchet) · SEC-02 · SEC-03 · SEC-04 · SEC-05 · SEC-06 · SEC-07 · SEC-08 (exact pins) · SEC-09 · SEC-10 · SEC-11 · SRC-01 (static + VoteInfo host guard at run time) · SRC-02 (paid product vs `terms_ask`) · SRC-03 · SRC-05 · SRC-06 · SRC-09 · SRC-10 (weekly) · PRIV-01 (static) · PRIV-02 · PRIV-03 · PRIV-05 · PRIV-06 · PRIV-08 · PRIV-10 · POL-01 · POL-12 · POL-13 · HOST-01 · HOST-04 (warnings → GitHub issue) · LIC-01 · LIC-03 · LIC-05 · LIC-06 · LIC-08 (via PRIV-08) · LIC-09 · OPS-01 · OPS-04 (data guard) | Every file in the trigger table (incl. LIC-07 licence files) · UNKNOWN files (default rule) · POL-05 banned words · POL-09 quiet period · PRIV-04 privacy text · PRIV-07 poll · SEC-03 CSP edits · OPS-04 hand-edited generated data · OPS-07 billable DeepL | OPS-02 route smoke test, OPS-05 accessibility, OPS-06 mobile/performance (need a headless browser in CI — a new dependency, owner to decide) · POL-02/03/04/06/07/10 editorial judgement · SEC-08 hash pinning · LIC-02/04 (dependency and copied-text licences) · SRC-07/08/11 · PRIV-09/11/12 · PROC-01/03 (CLAUDE.md instructs; not machine-enforced) |
