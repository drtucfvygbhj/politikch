# Data sources — reuse & commercial-use compliance

PolitikCH is independent and plans to monetise. This file records, per source,
**how the data is retrieved** and **whether it may be reused commercially**, so
nothing has to be re-derived later. Verified 2026-09-18 against each source's own
terms.

**Conclusion: the current use case *and* commercial operation are permitted for
every source in use, with attribution.** The whole pipeline is therefore fully
automatic — there are no required manual data steps (one optional one remains:
native Italian brochures, below).

Two rules cover almost everything: **(1)** official Swiss authority texts (laws,
decisions, vote results, the Federal Council's voting explanations) are **not
copyrighted** (Art. 5 URG) and may be reused, including commercially; **(2)** open
government data on opendata.swiss carries one of: `terms_open` (reuse freely),
`terms_by` (reuse freely, **cite the source**), `terms_ask` (commercial use needs
the owner's permission) — plus CC BY (reuse incl. commercial, attribution).

## Per-source status

| Source | Data used | Retrieval | Licence / terms | Commercial |
|---|---|---|---|---|
| **parlament.ch** OData | session votes, tallies, **"what this vote is about"** | automatic | opendata.swiss `terms_by` | ✅ cite source |
| **Federal Council brochure** via **Swissvotes** | vote **for / against** arguments (DE/FR) | automatic (robots-permitted, `Crawl-delay 10` honoured) | Art. 5 URG (public domain) **+** Swissvotes **CC BY 4.0** | ✅ |
| **Swissvotes** dataset | party recommendations (Parolen), EN short titles | automatic (CSV) | **CC BY 4.0** | ✅ attribution |
| **BFS** election results | National Council / canton results | automatic | **CC BY 4.0** | ✅ attribution |
| **BFS** geo / municipality register | maps, counts | automatic | `terms_open` | ✅ |
| **LINDAS** (Chancellery) | pending / upcoming initiatives | automatic (SPARQL) | `terms_by` / CC BY | ✅ cite source |
| **EFK** register | party / campaign financing | automatic | official transparency register | ✅ cite source |
| **VoteInfo** (BFS) | federal **vote results & titles** (real-time feed) | automatic | `terms_ask` — see note | ✅ *(via the two routes below)* |

Attribution is surfaced in-app for every source (see `NOTICE.md` and the
`rec.source` / `financing.source` / `canton.sources` i18n strings) — keep it.

## Machine translation (DeepL)

English texts that have no official version (session vote titles, for/against
arguments, session summaries) are machine-translated by **DeepL** at build time
(`scripts/translate.py` → `data/mt.json`), labelled "machine translation" on the
site with a link to the official source. Commercial status:

- **Output ownership:** DeepL's terms grant the customer full, unrestricted
  rights to use the translations, including commercially — DeepL claims no
  copyright over them. ✅
- **Input data:** we send only **public official texts** (no personal or
  confidential data). The **free** API tier may use input to improve DeepL's
  models — immaterial here, because the inputs are already public. So there is
  no confidentiality reason to pay.
- **Cost — guaranteed zero.** We deliberately use the **DeepL API Free** tier
  (500,000 characters/month) on an account with **no payment method**, so DeepL
  *cannot* bill us — when the monthly allowance is used up the API simply refuses
  (HTTP 456) and any not-yet-translated text waits until next month. On top of
  that, `scripts/translate.py` enforces four layers (see its header): it refuses
  a billable (non-`:fx`) key, checks DeepL's `/v2/usage` and stays under the
  limit minus a safety margin, caps each run, and only ever writes fully
  translated items. Our full volume (~196k chars once, then a few tens of
  thousands/month) sits well under the free cap anyway.
- **Labelling:** each machine translation carries a badge and links to the
  authoritative source, so it is never presented as official. ✅
- **Attribution:** DeepL's API terms require crediting DeepL to end users; the
  on-page MT disclaimer names "DeepL" and `NOTICE.md` records it.
- Romansh is **not** machine-translated (DeepL has no Romansh); RM keeps the
  official DE/FR/IT fallback. The only quality Romansh MT engine is Supertext —
  a possible future add if native RM is wanted.

## The one nuance: VoteInfo results (`terms_ask`) — still fine, two ways

The **real-time** voting-day feed we use (`echtzeitdaten-am-abstimmungstag-…`) is
`terms_ask`, i.e. its dataset terms ask permission for commercial use. That does
**not** make the use case impermissible, because the same official results are
available commercially two other ways:

1. **The results are Art. 5 URG facts.** Vote results (percentages, pass/fail,
   cantons) are official decisions and plain facts — not copyrightable — so
   displaying them commercially is permitted regardless of a dataset's terms.
2. **BFS also publishes the same results under `terms_by`** (commercial-OK with
   attribution): `eidgenossische-volksabstimmungen-detaillierte-ergebnisse` and
   `volksabstimmungen-ergebnisse-ebene-kanton-seit-1866`. Switching
   `fetch_initiatives.py`'s *results* source to one of these removes all doubt
   (trade-off: those are final results, not the real-time voting-day feed).

**Recommended before commercial launch (belt-and-suspenders, not blocking):**
send a one-line courtesy permission request for the real-time feed to the dataset
owner **poku@bfs.admin.ch**, *or* switch the results source to the `terms_by`
dataset above. Either fully settles it; until then the Art. 5 basis holds.

## Also worth a one-line confirmation
- **Swissvotes licence.** swissvotes.ch/page/dataset states **CC BY 4.0** for the
  dataset + codebook (an earlier project note said "CC BY-NC-SA" — that was
  wrong). Before commercial launch, confirm once with
  **info@anneepolitique.swiss** and keep the reply. If it ever turned out to be
  NC, only the party recommendations and EN short titles would be affected.

## Not a concern
- Everything is retrieved from official open-data APIs or robots-permitted,
  openly-licensed sources; **admin.ch (which blocks bots) is never scraped**.
- The Federal Council brochure is auto-fetched from Swissvotes (DE/FR); native
  Italian is the one *optional* manual add (Swissvotes has no IT) — see
  `data/brochures/README.md`. Skipping it just falls back to DE/FR.
- Re-confirm a dataset's `terms_*` code hasn't changed when BFS/LINDAS republish
  it (tiers can change); all current ones are open except VoteInfo (above).
