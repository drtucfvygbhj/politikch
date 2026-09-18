# Data sources — reuse & (future) commercial compliance

PolitikCH is independent and currently non-commercial. This file records, per
source, **how the data is retrieved** and **whether it may be reused commercially**
(the site plans to monetise), so nothing has to be re-derived later. Verified
2026-09-18 against each source's own terms.

Two rules cover almost everything: **(1)** official Swiss authority texts (laws,
decisions, vote results, the Federal Council's voting explanations) are **not
copyrighted** (Art. 5 URG) and may be reused, including commercially; **(2)** open
government data on opendata.swiss carries one of three terms — `terms_open`
(reuse freely), `terms_by` (reuse freely, **cite the source**), or `terms_ask`
(**commercial use needs the owner's permission**).

## Per-source status

| Source | Data used | Retrieval | Licence / terms | Commercial |
|---|---|---|---|---|
| **parlament.ch** OData | session final votes, per-party tallies, **"what this vote is about"** text | automatic (official web service) | opendata.swiss `terms_by` | ✅ cite source |
| **BFS** election results | National Council / canton party results | automatic (opendata.swiss) | **CC BY 4.0** | ✅ attribution |
| **BFS** geo / municipality register | maps, municipality/district counts | automatic | `terms_open` | ✅ |
| **LINDAS** (Federal Chancellery) | pending / upcoming initiatives | automatic (SPARQL) | `terms_by` / CC BY | ✅ cite source |
| **Federal Council brochure** | vote **for / against** arguments | **manual** download from admin.ch (bot-blocked) | Art. 5 URG (public domain) | ✅ |
| **Swissvotes** dataset | party recommendations (Parolen), English short titles | automatic (CSV) | **CC BY 4.0** | ✅ attribution *(see note)* |
| **EFK** register | party / campaign financing | automatic | official transparency register | ✅ cite source |
| **VoteInfo** (BFS) | federal **vote results & titles** | automatic (opendata.swiss) | **`terms_ask`** | ⚠️ **needs BFS permission** |

Attribution is already surfaced in-app for every source (see `NOTICE.md`, and the
`rec.source` / `financing.source` / `canton.sources` i18n strings) — keep it.

## Action items before monetising

1. **VoteInfo results — get BFS permission (the one real blocker).**
   The vote-results dataset is `terms_ask` (commercial use requires the owner's
   permission). Request it from the dataset owner: **poku@bfs.admin.ch**
   (BFS, popular-votes unit). This is routine for transparency reuse. *Fallback
   if needed:* the raw official results (percentages, pass/fail) are Art. 5 URG
   facts and not themselves copyrightable — but get the written OK to be clean.

2. **Swissvotes — confirm the licence (likely already fine).**
   swissvotes.ch/page/dataset states the dataset + codebook are **CC BY 4.0**
   (commercial use allowed with attribution). An earlier project note said
   "CC BY-NC-SA"; the live page says CC BY 4.0. Before commercial launch, send a
   one-line confirmation email to **info@anneepolitique.swiss** and keep the
   reply. If it ever turns out to be NC, the affected features are only the party
   **recommendations** and the English short titles — replace those with a
   primary-source compilation or drop them; nothing else depends on Swissvotes.

3. **Keep sourcing the Federal Council brochure from admin.ch by hand.**
   Its content is public-domain (Art. 5), so it's commercially fine — and taking
   it directly from the authority avoids any third-party dependency entirely.
   This is a recurring manual task (see `MAINTENANCE.md` §2 and
   `data/brochures/README.md`).

4. **Re-confirm the two per-dataset `terms_*` codes stay open** when BFS/LINDAS
   refresh a dataset (they can change the tier). Everything currently used is
   `terms_open` / `terms_by` / CC BY except VoteInfo (`terms_ask`, item 1).

## Not a concern
- All the automatic parliamentary/statistical/Chancellery feeds are `terms_by` /
  `terms_open` / CC BY → commercial-safe with the attribution already shown.
- The site is retrieved only from official open-data APIs and a robots-permitted
  dataset; admin.ch (which blocks bots) is **never** scraped — its one document
  we need (the brochure) is downloaded by hand.
