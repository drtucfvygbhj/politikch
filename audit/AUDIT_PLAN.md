# Politikch — Legal-Compliance & Adversarial Security Audit

**Instructions for Claude Code.** This file is the runbook for the audit. It is
not the audit itself. Read the whole file before you start. Then run **Stage 1**
now, or **Stage 2** once the entry criteria in §9 are met.

> **Not legal advice.** The audit gathers evidence, points to primary legal
> sources and ranks risk. Anything rated `LEGAL-HIGH`, and every item in §8.4
> ("Questions for a lawyer"), must go to a Swiss lawyer or the relevant
> authority before launch. Never state a legal conclusion as settled unless it
> is backed by a primary source you actually fetched: fedlex.admin.ch, an
> official FDPIC/SECO/ESTV page, or the data source's own terms page. Record the
> retrieval date.

---

## 0. Operator context (the facts the analysis depends on)

| Fact | Value | Why it matters |
|---|---|---|
| Operator | One natural person, age 18–29, resident in Lausanne (VD), Switzerland. No company yet | Swiss law applies first. The Impressum must give the operator's real name and postal address once the site is commercial. revFADP criminal fines hit the *individual* (up to CHF 250,000) |
| Domains | politikch.ch, politicsch.ch, politicach.ch, politiquech.ch (registrar/DNS: **Hostpoint**) | Four DNS zones to harden: takeover, spoofing, expiry |
| Mail | `contact@politikch.ch` inbox. Aliases the owner says exist: `contact.form@`, `legal.notice@`, `privacy@`, `subscriptions@` | Deliverability and spoofing checks. **Lead:** `data/legal.json` routes "Feedback" to `feedback@politikch.ch`, which is not on the owner's alias list. It also says `subscriptions@` "was removed" and that aliases deliver to the `privacy@` inbox. The owner says everything goes to `contact@`. Resolve this |
| Current hosting | GitHub Pages from the public repo `drtucfvygbhj/politikch` (`.github/workflows/deploy.yml`), custom domain planned (`CNAME.example`) | GitHub's terms (Pages usage limits, Acceptable Use) apply. GitHub Pages cannot set HTTP response headers |
| Current architecture | Fully static SPA (`index.html`, `js/*.js`, `data/*.json`). Weekly CI job fetches official data, commits it to `main`, which auto-deploys. There is an optional poll backend (`BACKEND.md`, `js/config.js` `POLL_API`, currently empty). The contact form is `mailto:` only | The attack surface is small today but includes the **supply chain**: upstream data → CI → `main` → live |
| Planned (Stage 2) | Real hosting (off GitHub Pages or behind a CDN), a paid **subscription**, **user accounts** with optionally **saved data** (votes, profile, party alignment), probably the poll backend, probably a newsletter | Votes and party alignment reveal **political opinions**, which are *sensitive personal data* under revFADP Art. 5(c). This one fact drives most of the Stage 2 obligations |

---

## 1. Rules of engagement (read first, obey always)

1. **Scope — authorised targets only.** Test only what the owner controls:
   - the local checkout and its git history,
   - the local dev server `http://localhost:8001` (start it with `preview_start {name: "static-site"}` and never through Bash),
   - the owner's GitHub repo and its settings (read-only through `gh`/the web UI unless the owner approves a change),
   - the four domains' **public** DNS/TLS/HTTP surface, and the deployed site once it exists.

   **Never** probe, scan, fuzz or load-test Hostpoint's shared infrastructure, GitHub's platform, Cloudflare, DeepL, or any upstream data source (parlament.ch, swissvotes.ch, BFS, LINDAS, EFK, admin.ch, karavia.ch). Unauthorised access is a criminal offence in Switzerland (StGB Art. 143bis) even when the intent is good. Upstream sources are reviewed by **reading their terms**, not by testing them.
2. **No denial of service.** Rate-limit checks against the owner's endpoints may send at most ~50 requests per test, with the owner's approval, and never against a shared host.
3. **No real-world side effects without explicit approval in chat:** sending email (including spoof tests, and only ever *to the owner's own inbox*), opening issues or PRs, changing repo, DNS or GitHub settings, submitting forms, contacting data owners (BFS, Swissvotes, etc.). Draft the text and let the owner send it.
4. **Report only, don't fix.** Do not edit production code during the audit. Findings go in the report. Fixes happen afterwards on a separate branch, one finding at a time, after the owner approves.
5. **Report confidentiality.** `deploy.yml` publishes the **entire repository** (`path: '.'`). Write all reports under `audit/reports/`, which is git-ignored, and never commit exploit detail to a tracked path. Include a finding if this plan file itself would be deployed.
6. **Tooling.** Prefer tools already on the machine (`curl`, `dig`, `openssl`, `python3`, `git`). Before installing anything (semgrep, gitleaks, trufflehog, OWASP ZAP, nuclei, testssl.sh, pa11y/axe, osv-scanner, zizmor/actionlint), list the tool, its source and its size, and ask once for a batch approval. Install into the scratchpad or a venv, never globally. Never add a dependency to the project.
7. **Evidence standard.** Every finding needs a file:line, a command with its output, a screenshot, or a URL plus retrieval date. Mark anything you inferred but could not verify as `UNVERIFIED`.
8. **Parallelism.** Workstreams A–F in §4 are independent. You *may* fan them out to subagents (`Agent`, `general-purpose`), but only if the owner asks. Each subagent gets this file's path, its workstream letter and the rules in §1. Merge their outputs into one report and check each finding again yourself.

---

## 2. Methodology (how large organisations do this, adapted)

The audit follows the frameworks below. Cite the control ID in each finding so it can be traced.

| Practice | Used by | Applied here as |
|---|---|---|
| **Threat modelling**: STRIDE for security, **LINDDUN** for privacy | Microsoft SDL; NIST SSDF PW.1 | Workstream A. Produce a data-flow diagram *first* and derive the tests from it |
| **NIST SSDF (SP 800-218)** | US federal suppliers, large vendors | Grades the dev process: PO (prepare), PS (protect software), PW (produce), RV (respond to vulns) |
| **OWASP ASVS 5.0** | Industry verification checklist | Stage 1 at **L1** (static site). Stage 2 at **L2** for everything touching accounts, payments or political-opinion data |
| **OWASP Top 10:2025** | Common baseline | Coverage check. A03 *Software Supply Chain Failures* is the most relevant category today |
| **OWASP WSTG** | Pen-test firms | Test-case catalogue for Workstream D |
| **OpenSSF Scorecard / SLSA** | Google, OSS foundations | Repo and CI hygiene (Workstream C) |
| **SAST / SCA / secret scanning / DAST** | Standard CI gates | Tools listed in §1.6 |
| **Red team, assume breach** | Big-tech red teams | Workstream D is written as attacker narratives, not a checklist |
| **Incident-response tabletop** | Regulated firms | Workstream F. Walk a breach end to end against revFADP Art. 24 |
| **security.txt (RFC 9116)**, vulnerability disclosure | Most large sites | Check that one exists and works |

### 2.1 Incidents to learn from (each maps to a test below)

| Incident | What went wrong | Where it applies here |
|---|---|---|
| **tj-actions/changed-files, Mar 2025 (CVE-2025-30066)**: 23k repos | Attacker re-pointed the action's version tags at malicious code, which dumped CI secrets into logs | Our workflows use actions by **tag** (`@v4`, `@v5`), not by commit SHA. `fetch-financing.yml` holds `DEEPL_API_KEY` and `contents: write`. See C-2 |
| **polyfill.io, 2024**: ~100k–490k sites | A trusted third-party script domain was sold and began serving malware | We currently load **no** third-party JS (CSP `script-src 'self'`). Stage 2 must keep it that way, especially for payment widgets and analytics. See D-6, S2-P |
| **British Airways / Magecart, 2018**: £20m ICO fine | 22 injected lines on the payment page skimmed cards. There was no CSP, no SRI and weak testing | Stage 2 checkout page. See S2-P |
| **Xplain, 2023**: 65k federal files leaked; FDPIC found no adequate security at the supplier | A processor held personal data without contractual safeguards | Stage 2 processors (host, email, payments, Cloudflare). revFADP Art. 9 processor contracts |
| **GitHub Pages domain takeovers** | A custom domain stays in DNS after Pages is disabled or the repo is deleted, and someone else claims it | Four domains. Is the domain verified in GitHub? Any wildcard records? See E-1 |
| **Dutch PVV Overijssel, 2021**: DPA fine | Email to supporters went out with CC instead of BCC, which revealed political opinions | Stage 2 newsletter / subscriber emails |
| **Finnish voting-advice apps, 2023** (research) | Third-party trackers received users' political answers | Stage 2 analytics and embeds must never see vote data |
| **Equifax, 2017** | A known-vulnerable dependency went unpatched | Stage 2 backend dependencies (SCA, patch SLA) |

---

## 3. Deliverables

Write into `audit/reports/stage-<N>-<YYYY-MM-DD>/`:

1. `REPORT.md`: executive summary, **GO / NO-GO verdict** (§8), findings register, open lawyer questions.
2. `findings.json`: one object per finding, schema below. Stage 2 diffs against Stage 1 using it.
3. `threat-model.md`: data-flow diagram (Mermaid), trust boundaries, and STRIDE + LINDDUN tables.
4. `legal-register.md`: every obligation, its source URL, retrieval date, status (`MET` / `GAP` / `N/A` / `UNVERIFIED`) and evidence.
5. `sources-terms.md`: one row per upstream data source, with a snapshot of the terms text at audit time (paraphrase plus a short quote under 15 words, and the URL).
6. `evidence/`: command outputs and screenshots.

```json
{ "id": "S1-D-03", "stage": 1, "workstream": "D", "title": "…",
  "type": "security|legal|privacy|licence|operational",
  "severity": "critical|high|medium|low|info",
  "cvss4": "CVSS:4.0/… (security only)",
  "legal_risk": "LEGAL-HIGH|LEGAL-MED|LEGAL-LOW (legal only)",
  "likelihood": "…", "impact": "…",
  "location": "js/app.js:1434 | URL | setting",
  "evidence": "evidence/…", "reproduce": "exact steps",
  "control_refs": ["ASVS 5.0 V3.x", "OWASP A03:2025", "revFADP Art. 19"],
  "remediation": "…", "effort": "S|M|L",
  "blocks_launch": true, "status": "open", "confidence": "confirmed|likely|unverified" }
```

---

## 4. STAGE 1: current repo, "can this go public?"

Record the commit SHA you audit (`git rev-parse HEAD`) and the branch. Audit the **exact tree that would deploy**: the working tree as of `main` plus the pending branch, whichever the owner names.

### Workstream A: Inventory and threat model (do this first, the others depend on it)

- **A-1 Asset inventory.** List every file that `deploy.yml` would publish. Mark anything that is not needed at runtime. **Leads to check:** `politikch.zip` (a tracked archive: what is inside it, and is it stale or leaking?), `.claude/launch.json`, `Start Politikch.command`, `scripts/`, `COMPLIANCE.md`, `BACKEND.md` (it documents the poll API and says the design "can be gamed"), `MAINTENANCE.md`, `TRANSLATIONS_TODO.md`, the internal notes in `data/legal.json` `_meta` (they reveal inbox routing and filtering rules), and `audit/`.
- **A-2 Data-flow diagram.** Cover visitor browser ↔ static host. Include localStorage (`politikch-lang`, the vote store in `js/myvotes.js`), the optional `POLL_API`, the `mailto:` handoff, share targets in `js/share.js`, and CI ↔ upstream sources ↔ DeepL ↔ git `main` ↔ Pages.
- **A-3 Personal-data inventory.** For every datum: what it is, where it lives, who can see it, how long it is kept, and whether it counts as *sensitive* under revFADP Art. 5(c). Note that votes stored in localStorage are political opinions, even though they stay on the device.
- **A-4 STRIDE + LINDDUN tables** per trust boundary. Every row either becomes a test ID in B–F or gets a reason why it is N/A.

### Workstream B: Code-level security (SAST and manual review)

- **B-1 DOM XSS sink review.** Enumerate every `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `href=`/`src=` template, and `style=` interpolation (`grep -n` over `js/`). There are dozens in `js/app.js`, `js/myvotes.js` and `js/share.js`. For each, trace every input back to where it comes from: `data/*.json`, i18n strings, the URL hash/route params, localStorage, or poll API responses. Classify each input as *first-party static*, *CI-generated from upstream* (untrusted!) or *attacker-controlled*. Confirm that `escapeAttr`/escaping is applied to every non-first-party value. Look closely at:
  - route params from `location.hash` (`#/party/<x>`, `#/canton/<x>`, `#/page/<slug>`, session ids) flowing into HTML or `fetch()` paths (`data/sessions/${id}.json`, `data/municipalities/${code}.json`): look for path traversal or unintended fetches,
  - upstream text (vote titles, brochure arguments, EFK donor names, parlament.ch descriptions, DeepL output) rendered with `innerHTML`. A poisoned upstream record or DeepL response becomes **stored XSS on the live site with no human review**, because the weekly job commits and deploys automatically,
  - `data/legal.json` bodies, documented as "trusted first-party HTML",
  - the contact form: `origin`, subject and body flow into a `mailto:` URL (`encodeURIComponent` coverage, header injection via `%0A` into cc/bcc, recipient taken from JSON),
  - `data-share` JSON specs and canvas text in `js/share.js`, and share URLs built from `location`.
- **B-2 Prove it or dismiss it.** For each suspect sink, write a local proof of concept: a modified copy of a JSON file served from the scratchpad, or a crafted hash URL on `localhost:8001`. Use `alert(document.domain)` only. Record whether the CSP blocks it. A blocked payload still gets reported, with its severity reduced.
- **B-3 CSP review** (`index.html:12`). `style-src 'unsafe-inline'` allows CSS injection and data exfiltration. `img-src data:` is also noted. Check that `connect-src 'self'` will **break** the poll once `POLL_API` is set (a functional and security trade-off). Note that `frame-ancestors` has no effect in a `<meta>` tag.
- **B-4 Secrets.** Run gitleaks or trufflehog over the **full git history** and the tracked zip. Grep for keys, tokens, personal emails, the owner's real name or address, and absolute local paths (`/Users/...`).
- **B-5 Python scripts** (`scripts/*.py`, which run in CI with a write token). Check for unsafe parsing: PDF parsing in `fetch_arguments.py`, CSV/JSON handling, no `eval`/`pickle`/`yaml.load`, and TLS verification left on. Check that timeouts and size limits exist, and whether a malicious upstream response can make the script write outside `data/` (path from an upstream id, e.g. `anr_path`). Check that dependency pins in `scripts/requirements*.txt` are exact, and run `osv-scanner`/`pip-audit` against them.
- **B-6 Validator as a security control.** Does `scripts/validate.py` reject HTML or script in text fields, or oversized or unexpected values, before the auto-commit? If it does not, that is a finding (defence in depth for B-1).

### Workstream C: Supply chain, repository and CI/CD

- **C-1 Workflow permissions.** Check least privilege per job. `fetch-financing.yml` has `contents: write` + `issues: write` for the whole job, including the third-party pip installs. Check `deploy.yml` `id-token: write` scoping.
- **C-2 Action pinning.** Actions are referenced by mutable tag (`actions/checkout@v4`, `setup-python@v5`, `configure-pages@v5`, `upload-pages-artifact@v3`, `deploy-pages@v4`). Recommend full-SHA pins plus Dependabot for actions (tj-actions lesson). Run `zizmor` or `actionlint` if approved.
- **C-3 Auto-publish chain.** Upstream data → auto-commit to `main` → auto-deploy, with no review. Model the worst case: a compromised upstream, DeepL, or PyPI package injects content or code. Recommend PR-based data updates or a content-sanitising gate.
- **C-4 Branch protection and account security** (read-only check; ask the owner to show settings or use `gh api`): is `main` protected, is 2FA on for the owner account, are there deploy keys or PATs, what is `GITHUB_TOKEN` allowed to do by default, are secret-scanning and push-protection enabled, is the Pages source limited to Actions, is the custom domain **verified**.
- **C-5 Public repo exposure.** Since the repo is public, list everything a stranger learns from it: the author handle, the commit timestamps (time-zone/behaviour profiling of the owner), `.claude/` config, internal docs, and the plan to monetise.
- **C-6 OpenSSF Scorecard.** Run it if approved (`scorecard --repo=…`), or run through its checks by hand.

### Workstream D: Attacker simulation (worst-case adversary, Stage 1 surface)

Write each as a narrative: goal → steps tried → result → evidence. Personas: (1) a politically motivated defacer before a vote; (2) a disinformation actor who wants to insert false results or arguments; (3) a spammer or phisher abusing the brand and the mail domain; (4) a script kiddie with scanners; (5) someone with access to a shared device.

- **D-1 Defac