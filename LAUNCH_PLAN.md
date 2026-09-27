# Politikch — plan from today's free site to PolitikCH+ and after

Adopted by the owner 2026-09-27. This is the order of work from today's state
(free reference site, currently in maintenance mode) to a paid PolitikCH+ tier
and beyond. The rules are in `GUARDRAILS.md`; how articles are written is in
`EDITORIAL.md`.

> Not legal advice. Items marked **Q** are the lawyer questions in
> `GUARDRAILS.md` §10 and stay open until answered in writing.

## Principles

1. **Compliant at every stage, not just at launch.** Every stage keeps all
   BLOCK checks passing. It also meets the law and every data source's terms
   **as they apply at that stage**. A stage starts only when the previous
   stage's exit conditions hold.
2. **Paid comes last.** PolitikCH+ launches only after the free site has built
   a solid audience (Stage C exit). Until then nothing on the site offers or
   advertises a paid product (`PAID_PRODUCT_LIVE` stays false).
3. **The reference site stays free and neutral** at every stage.

## Overview

| Stage | What | Exit condition |
|---|---|---|
| **A** | Close the open compliance items of today's free site | Every item fixed or accepted by the owner with a reason |
| **B** | Legal foundation: Verein, lawyer, operator identity | Controller and operator named (S1-F-01 closed) |
| **C** | Grow the free audience | Audience target met (owner sets it) |
| **D** | Build PolitikCH+ behind the scenes | Every item in the launch gate (Stage E) is true |
| **E** | Launch gate and launch | PolitikCH+ live |
| **F** | After launch: routines and growth | Ongoing |

Stages A and B run in parallel. **Leave maintenance mode (go public again)
only when S1-F-01 is closed.** The Stage 1 audit rates it LEGAL-HIGH: the
privacy policy must name the controller (revFADP Art. 19).

---

## Stage A — the free site, today

From the Stage 1 audit (`audit/reports/stage-1-2026-09-21/findings.json`) and
`GUARDRAILS.md` §12. **Who**: O = owner, C = Claude (with a pre-change review), L = lawyer.

| # | Item | Ref | Who | Blocks |
|---|---|---|---|---|
| A1 | Privacy policy names the controller | S1-F-01, revFADP Art. 19 | O → Stage B | Going public |
| A2 | Branch protection on `main` (block force-push and deletion, require the Checks run) | S1-C-01 | O | — |
| A3 | HTTPS on the three language domains | S1-E-02 | O | — |
| A4 | Mail: DMARC reporting → `p=reject`, CAA record, MTA-STS | S1-E-04 | O | — |
| A5 | Domain Shield, auto-renew all four domains, 2FA on Hostpoint and GitHub, recovery codes stored, one-page incident plan | S1-G-01 | O (+C for the plan) | — |
| A6 | Confirm the analytics database is in the EU (Cloudflare dashboard) | §13.4 | O | — |
| A7 | Set the `DEEPL_API_KEY` secret, or accept English/Italian fallbacks | §13.1 | O | — |
| A8 | Re-check download size caps (audit says open, §13.1 says added) | S1-B-04 | C | — |
| A9 | Donor descriptions: per-entry source field | POL-07, §12.5 | C | — |
| A10 | Review the 421 baseline HTML insertions one by one; shrink the list | SEC-01, §12.6 | C | — |
| A11 | Hash-pin Python requirements | SEC-08 | C | — |
| A12 | Accessibility: axe run, contrast, heading levels | S1-F-08, OPS-05 | C | — |
| A13 | Municipality boundaries: current swissBOUNDARIES3D release | S1-F-07 | C | — |
| A14 | Decide: headless-browser checks in CI (OPS-02/05/06) need a new dependency | §14 | O | — |
| A15 | Swiss cross in the logo | S1-F-06, Q2 | L | — |
| A16 | Donor names in old git history | Q11 | L | — |
| A17 | Analytics and EU visitors (consent?) | Q13 | L | — |

## Stage B — legal foundation (during the free phase)

| # | Step | Who | Notes |
|---|---|---|---|
| B1 | Find a second founding member, ideally also the second reader for articles | O | A Verein needs at least two founders in practice |
| B2 | **One lawyer consultation**, answers in writing. First: Q19, Q15, Q3, Q13, Q2, Q11. Before Stage E: Q1, Q4, Q14, Q16, Q17, Q18, Q5–Q10 | O + L | Several cantonal bar associations offer low-cost first consultations |
| B3 | Found the Verein: statutes with a purpose clause per Q19c (e.g. independent information and analysis on Swiss democracy, funded by subscriptions and donations), founding meeting, board | O | No capital needed. Only the Verein's assets are liable (ZGB Art. 75a) |
| B4 | Domicile (c/o) address as the Verein's seat | O | Keeps a home address off the site |
| B5 | Bank account in the Verein's name | O | |
| B6 | Commercial register: register if Q19b says so (then board names are public in Zefix) | O | |
| B7 | Privacy policy and legal notice name the Verein as controller and operator | C (PRIV-04, POL-12 sign-off) | **Closes S1-F-01 → the site may go public** |
| B8 | Media liability insurance: get a quote. Needed before the first PolitikCH+ article; consider it now for the reference site's editorial texts (Q4, Q14) | O | |
| B9 | Optional: trademark for the name (IPI), per `GUARDRAILS.md` §7.1 | O | |
| B10 | Decide whether to declare the Press Council code (Q18) | O | |

**Exit:** the Verein exists with a bank account and an address; the privacy
policy and legal notice name it; Q19 and Q15 are answered.

## Stage C — growing the free audience

**Audience target.** The owner sets the number that counts as a solid audience
before Stage E, e.g. average daily visitors over 90 days, and how it behaves
around ballots. Measure it from the analytics daily totals. The analytics keep
no cross-day identifiers (daily salt), so count daily visitors, not "unique
visitors".

**Growth activities and what each needs first:**

| Activity | Allowed? | Needs first |
|---|---|---|
| Social media accounts (in the Verein's name) | ✅ | Share images and texts neutral (POL rules); no tracking pixels on the site (PRIV-02) |
| Paid promotion of the reference site | ✅ | Promoting content about a specific vote during its campaign: Q16 first |
| Newsletter | ✅ | Stage B done; a provider with a data processing agreement (HOST-02); privacy text (PRIV-04); double opt-in (UWG Art. 3(1)(o)); never CC, always a proper mailing tool |
| Donations | ✅ | Stage B done; payment provider as processor (HOST-02); ED-01 applies already: no money from parties, campaigns or organisations campaigning on a pending vote; donations disclosed |
| Advertising on the site | ❌ | Would bring third-party scripts and trackers (PRIV-02, SEC-03) and possibly political advertisers (ED-01) |
| Community poll (`POLL_API`) | ✅ | PRIV-07 review, Q9 |
| Cantonal votes and other new data | ✅ | Source registry row per new host (SRC-01), licence check (SRC-02) |
| Collaboration with other media (reuse of our data) | ✅ | Our data is CC BY 4.0; no endorsement implied (LIC-09) |

**Work that doesn't need the backend, best done in this stage:**

- **C1 Move hosting off GitHub Pages** to a host with a data processing
  agreement and EU/CH data location. This adds security headers (S1-E-03) and
  scales with traffic; GitHub Pages has usage limits and bars primarily
  commercial use. (C, HOST-02, SEC-06 sign-offs)
- **C2 Deep links with temporary highlighting** on reference pages. A link can
  open a vote, party or session page with one figure highlighted until the next
  click or tap. This is needed for ED-04 and also useful for sharing. (C)
- **C3 Watch free-tier limits.** Cloudflare Worker (analytics) and DeepL quota;
  any paid plan is an OPS-07 sign-off.
- **C4 Write articles early** (`EDITORIAL.md`). Nothing is published; this
  builds the backlog and the habit.

**Exit:** the audience target is met, and every Stage A item is fixed or
accepted.

## Stage D — build PolitikCH+ (nothing sold or advertised yet)

| # | Step | Who | Rules |
|---|---|---|---|
| D1 | Results data: switch from the VoteInfo real-time feed (`terms_ask`) to the openly licensed BFS results datasets, or get BFS permission in writing | C / O | SRC-02, S1-F-03 |
| D2 | Confirm the Swissvotes licence (CC BY 4.0) in writing; answer Q1 (brochure arguments on a commercial site) | O / L | SRC-02, SRC-07 |
| D3 | Accounts and subscriptions backend: login, subscription status, article storage **outside the repo**, publishing tool for the editor | C | ED-13, OWASP ASVS L2 |
| D4 | Payments: hosted checkout (card data never touches the site), verified webhooks, cancelling as easy as subscribing, no lingering access after a refund | C | AUDIT_PLAN S2-P |
| D5 | Article display: front-page cards in the middle column, article page, red border + PolitikCH+ + type label everywhere, internal data links (C2), source list, corrections log, translation labels. With it, the render checks for ED-02, 03, 04, 05, 08 and 10 | C | ED-*, SEC-01 |
| D6 | Translation of articles: paid DeepL with a data processing agreement, glossary (`EDITORIAL.md` §9.1), checked/unchecked status per language, no Italian where ED-10 forbids it | C / O | OPS-07, OPS-09, ED-10 |
| D7 | Privacy: policy for accounts, payments and subscribers; storage list; processor list; transfers abroad; DPIA (Art. 22); record of processing (Art. 12); breach plan (PRIV-12); minors; no reading history per subscriber | C drafts, O + L approve | PRIV-02/03/04/11/12, HOST-02, Q5, Q6 |
| D8 | Legal texts: terms of service (renewal, cancellation, no implied cooling-off right); Impressum per Q15/Q19; public editorial policy page (ED-01, 09, 10, 12); legal notice: "not voting advice" limited to the reference pages; About: "currently one editor" (ED-11) | C drafts, O + L approve | POL-12, UWG Art. 3(1)(s) |
| D9 | VAT (Q8). Swiss VAT only above CHF 100,000 turnover. **EU VAT for digital services to EU consumers can apply from the first sale** for a seller outside the EU; either register (non-Union OSS) or sell only to Switzerland at first | O + L | Q8 |
| D10 | Editorial: backlog of 6–8 articles; press-office contact list for ED-06; second reader agreed; insurance in force (B8) | O | ED-* |
| D11 | Stage 2 audit (`audit/AUDIT_PLAN.md` §5, entry criteria §9) and an external penetration test | C + external | — |

## Stage E — launch gate and launch

`PAID_PRODUCT_LIVE` stays false until **every** line is true:

- [ ] Stage C audience target met
- [ ] Verein exists; operator and controller named (B7)
- [ ] Q3, Q15, Q16, Q19 answered in writing; Q1, Q4, Q8, Q14 answered
- [ ] Hosting off GitHub Pages (HOST-01)
- [ ] No `terms_ask` source feeding the site without permission (SRC-02)
- [ ] Terms of service, Impressum and editorial policy page ready in every language
- [ ] Privacy policy, DPIA, record of processing and breach plan done
- [ ] Payments tested in test mode; cancellation tested
- [ ] ED render checks in `check.py` and passing
- [ ] Stage 2 audit verdict GO; penetration test findings fixed or accepted
- [ ] Media liability insurance in force
- [ ] At least 6 articles ready, each through the `EDITORIAL.md` checklist
- [ ] Not within 10 days of a ballot that any launch article covers (ED-08)

**Launch:** switch `PAID_PRODUCT_LIVE` on with the owner's sign-offs (POL-12,
HOST-01, SRC-02 and any flagged privacy rule); publish the backlog gradually;
announce.

## Stage F — after launch

| When | Routine |
|---|---|
| Every article | `EDITORIAL.md` §12 checklist |
| Every ballot | Quiet period (POL-09, ED-08); results checked (POL-03) |
| Weekly | Data job with source monitoring (automatic, SRC-10); "source check" issues handled |
| Monthly | Corrections log; open issues; free-tier and quota limits |
| Quarterly | Privacy policy still matches the code (PRIV-04); legal references still current |
| Yearly | Funding disclosure (ED-01); Stage 2 re-audit; insurance renewal; lawyer check-in on new law |
| When possible | GmbH once CHF 20,000 of capital exists and it's worth it · human Italian translation · a second writer (update ED-11 About text) · cantonal votes and recommendations (ED-07) |

---

## Data sources: what each stage may do

From `COMPLIANCE.md`, `GUARDRAILS.md` §2 and §13.1. "Paid" means from Stage E.

| Source | Terms | Free site (A–D) | Paid (E–F) |
|---|---|---|---|
| parlament.ch OData | `terms_by` | ✅ with credit | ✅ with credit |
| Swissvotes dataset | CC BY 4.0 | ✅ credit + licence + link | ✅, confirm the licence in writing first (D2) |
| Federal Council brochure texts | Art. 5 URG | ✅ | ✅ for the Federal Council's own text; committee arguments = Q1 |
| BFS election results | CC BY 4.0 | ✅ | ✅ |
| BFS municipality register | `terms_open` | ✅ | ✅ |
| LINDAS (Federal Chancellery) | open government data | ✅ credit | ✅ credit |
| EFK financing register | `terms_open` | ✅ private donors never named (PRIV-08) | ✅ same |
| **VoteInfo real-time feed** | **`terms_ask`** | ✅ | ❌ until permission or switch (D1, SRC-02 blocks) |
| swisstopo boundaries (via labs.karavia.ch) | attribution | ✅ credit | ✅ credit, re-check the registry row |
| DeepL API **Free** | output ours; credit DeepL; may keep inputs | ✅ public official texts only | ✅ same; **never article text** (OPS-09) |
| DeepL API **Pro** | data processing agreement | — | ✅ for article translations (D6) |
| GitHub Pages | no primarily commercial use | ✅ | ❌ move first (HOST-01) |
| Cloudflare (analytics) | free plan, DPA in terms | ✅ | ✅, watch limits (OPS-07) |
