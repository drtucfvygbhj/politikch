# Politikch — plan from today's free site to PolitikCH+ and after

Adopted by the owner 2026-09-27. This is the order of work from today's state
(free reference site, currently in maintenance mode) to a paid PolitikCH+ tier
and beyond. The rules are in `GUARDRAILS.md`; how articles are written is in
`EDITORIAL.md`.

> Not legal advice. Items marked **Q** are the legal questions in
> `GUARDRAILS.md` §10. Since 2026-10-16 each is closed there (designed away,
> researched or decided by the owner); what is still to do before anything is
> sold is in **Before commercialisation** below.

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
| **B** | Legal foundation: Verein, operator identity | Controller and operator named (S1-F-01 closed) |
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
`GUARDRAILS.md` §12. **Who**: O = owner, C = Claude (with a pre-change review), L = lawyer (none planned since 2026-10-16: L items fall to O, see Stage B).

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
| A15 | ~~Swiss cross in the logo~~ — removed 2026-10-16 | S1-F-06, Q2 | C | — |
| A16 | ~~Donor names in old git history~~ — rewritten 2026-10-16; purged by GitHub Support, confirmed 2026-10-22 | Q11 | C + O | — |
| A17 | ~~Analytics and EU visitors~~ — nothing read on the device, no city, 2026-10-16; worker redeploy + clean-up of old fields | Q13 | O | — |

## Stage B — legal foundation (during the free phase)

> **Owner decision 2026-10-16: no lawyer consultation.** The Verein relies only
> on what the Civil Code states outright, and Q19 is decided (`GUARDRAILS.md`
> §10). The other **Q** items were closed the same day (designed away,
> researched or decided, §10); what remains is in **Before commercialisation**. The founding papers (statutes,
> minutes, templates) are kept privately, outside this repo.

| # | Step | Who | Notes |
|---|---|---|---|
| B1 | Find a second founding member: a voting member, not on the board | O | Two members is the minimum in practice. Members are not public while the Verein is unregistered |
| B2 | ~~One lawyer consultation~~ — replaced by the owner decision above | O | Q19 decided 2026-10-16 |
| B3 | Found the Verein: statutes (English binding, a French version ready for any registration), founding meeting, one-person board, purpose clause per Q19 | O | No capital needed. Only the Verein's assets are liable (ZGB Art. 75a) |
| B4 | PO box in the Verein's name as its postal address | O | Keeps every member's name and home address off the site; a c/o address would print a name. Before anything is sold, a street business address is added (Q3, see Before commercialisation) |
| B5 | Bank account in the Verein's name, opened before the first income | O | Nothing passes through a personal account. Costs paid earlier are recorded as loans to the Verein |
| B6 | Commercial register: stay unregistered while small; adopt the French statutes before any registration | O | Registration puts the board's name in Zefix permanently |
| B7 | Privacy policy and legal notice name the Verein as controller and operator | C (PRIV-04, POL-12 sign-off) | **Closes S1-F-01 → the site may go public** |
| B8 | Media liability insurance: get a quote. Needed before the first PolitikCH+ article; consider it now for the reference site's editorial texts (Q4, Q14) | O | |
| B9 | Optional: trademark for the name (IPI), per `GUARDRAILS.md` §7.1 | O | |
| B10 | ~~Decide whether to declare the Press Council code~~ — decided 2026-10-16: declare it (Q18) | O | Done with the editorial policy page, see Before commercialisation |
| B11 | Written licence from the owner to the Verein for the name, code, domains and articles: free, non-exclusive, revocable | O (+C draft) | Keeps ownership clear; a later company needs nothing transferred from the Verein |
| B12 | Register the Verein with the Vaud tax office once its first financial year is closed; file a return every year from then on | O | |

**Exit:** the Verein exists with a PO box address; the privacy policy and legal
notice name it; Q19 is decided. Q15 concerns PolitikCH+ and is closed before
Stage E.

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
| Paid promotion of the reference site | ✅ | Never an Analysis article (ED-14) |
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
| D2 | Confirm the Swissvotes licence (CC BY 4.0) in writing (Q1 is closed: Art. 5 URG makes no commercial distinction) | O | SRC-02, SRC-07 |
| D3 | Accounts and subscriptions backend: login, subscription status, article storage **outside the repo**, publishing tool for the editor | C | ED-13, OWASP ASVS L2 |
| D4 | Payments: hosted checkout (card data never touches the site), verified webhooks, cancelling as easy as subscribing, no lingering access after a refund | C | AUDIT_PLAN S2-P |
| D5 | Article display: front-page cards in the middle column, article page, red border + PolitikCH+ + type label everywhere, internal data links (C2), source list, corrections log, translation labels. With it, the render checks for ED-02, 03, 04, 05, 08 and 10 | C | ED-*, SEC-01 |
| D6 | Translation of articles: paid DeepL with a data processing agreement, glossary (`EDITORIAL.md` §9.1), checked/unchecked status per language, no Italian where ED-10 forbids it | C / O | OPS-07, OPS-09, ED-10 |
| D7 | Privacy: policy for accounts, payments and subscribers; extend the processor list, record of processing and DPIA in `COMPLIANCE.md` (Art. 12, 22); transfers abroad; breach plan (PRIV-12); subscriptions from 18; no reading history per subscriber | C drafts, O approves | PRIV-02/03/04/11/12, HOST-02, Q5, Q6 |
| D8 | Legal texts: terms of service (renewal, cancellation, no implied cooling-off right, 18+); Impressum per the Q15 decision and Q19, with the street business address (Q3); public editorial policy page (ED-01, 09, 10, 12, 14, 15, and the Press Council code, Q18); legal notice: "not voting advice" limited to the reference pages; About: "currently one editor" (ED-11) | C drafts, O approves | POL-12, UWG Art. 3(1)(s) |
| D9 | VAT (Q8), decided 2026-10-16: **sell only to Swiss billing addresses at launch**, so EU VAT (owed by a non-EU seller from the first sale) doesn't arise. Swiss VAT only above CHF 100,000 turnover | O | Q7, Q8 |
| D10 | Editorial: backlog of 6–8 articles; press-office contact list for ED-06; second reader agreed; insurance in force (B8) | O | ED-* |
| D11 | Stage 2 audit (`audit/AUDIT_PLAN.md` §5, entry criteria §9) and an external penetration test | C + external | — |

## Before commercialisation — the legal checklist

From the legal questions closed on 2026-10-16 (`GUARDRAILS.md` §10). Every line
is done before `PAID_PRODUCT_LIVE` goes on, and before the Stage 2 audit
(`audit/AUDIT_PLAN.md` §5) starts. Not legal advice.

| # | Item | From | Who |
|---|---|---|---|
| L1 | **Street business address** in the Verein's name (a business address service), shown in the imprint and the terms of service. A PO box alone likely doesn't meet the identity duty for selling online (UWG Art. 3(1)(s)) | Q3, Q19 | O |
| L2 | **Decide the imprint (Q15).** Either name a responsible editor in the PolitikCH+ imprint (StGB Art. 322(2)), or don't and accept that the point is unsettled (penalty: a fine). Either way, every request under Art. 322(1) is answered promptly and in writing with the seat and the responsible person. Record the decision in `GUARDRAILS.md` §10 | Q15 | O |
| L3 | **Swiss billing addresses only** at launch: checkout accepts only Switzerland as billing country; prices in CHF. Selling into the EU later needs non-Union OSS registration and a GDPR review (incl. an Art. 27 representative) first | Q7, Q8 | C + O |
| L4 | **Subscriptions from age 18**: in the terms of service and confirmed at checkout | Q6 | C |
| L5 | **Press Council code declared**: the editorial policy page and About say Politikch follows it, and how to complain | Q18 | O (+C draft) |
| L6 | **Privacy for subscribers**: DPIA, record of processing and processor list in `COMPLIANCE.md` extended to accounts, payments and hosting (D7); every **confirm** line there checked | Q5, Q10 | C drafts, O |
| L7 | **ED-14 and ED-15 in force**: no paid promotion of an Analysis; quotes short and sourced; both on the article checklist (`EDITORIAL.md` §12) | Q16, Q17 | O |
| L8 | ~~**Donor history purged** from public git history (A16) and the GitHub purge confirmed~~ — done 2026-10-22 | Q11 | C + O |
| L9 | **Description claims reviewed**: every donor/party description says only what its `source` supports | Q4, Q14 | O |

## Stage E — launch gate and launch

`PAID_PRODUCT_LIVE` stays false until **every** line is true:

- [ ] Stage C audience target met
- [ ] Verein exists; operator and controller named (B7)
- [ ] Every item in **Before commercialisation** done, including the Q15 decision
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
| Yearly | Funding disclosure (ED-01); Stage 2 re-audit; insurance renewal; check for new law affecting §10 (owner) |
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
