# Notice, sources & disclaimers

## Independence

Politikch is an **independent civic project**. It is **not** affiliated with, endorsed by, or representing:

- the Swiss Confederation or any federal authority,
- any cantonal or communal government, or
- any political party.

Nothing on the site should be read as an official communication of any authority or party.

## Data sources

| Data | Source |
|------|--------|
| Federal election results & seat counts (2023) | Federal Statistical Office (BFS) / [wahlen.admin.ch](https://www.wahlen.admin.ch) |
| Parliament composition & parliamentary groups | [parlament.ch](https://www.parlament.ch) |
| Popular vote results & official texts | Federal Chancellery (Bundeskanzlei) / [bk.admin.ch](https://www.bk.admin.ch) |
| Vote arguments (for / against) | Federal Council's official voting explanations ("Erläuterungen des Bundesrates" / Abstimmungsbüechli), Federal Chancellery ([bk.admin.ch](https://www.bk.admin.ch)) — reproduced verbatim. DE/FR fetched automatically from the officially-published PDF hosted by [Swissvotes](https://swissvotes.ch) (CC BY 4.0); native IT optionally added by hand. Public-domain official text (Art. 5 URG); each page links to the official Chancellery source. |
| Session votes — "what this vote is about" | Parliamentary record (Curia Vista) via [parlament.ch](https://www.parlament.ch) web service (opendata.swiss "Open use, cite source") — official background text, reproduced verbatim. |
| Machine translations (English, Italian) | Where a text has no official English (session vote titles, for/against arguments, session summaries), or the for/against arguments have no official Italian yet, a **machine translation** is produced by **DeepL** from the official DE/FR/IT and shown with a "machine translation" badge and a link to the official source. Not an official translation. Romansh is not machine-translated (DeepL doesn't support it). |
| Canton statistics (population, area) | Federal Statistical Office (BFS) — rounded approximations |

Figures were current as of the 2023–2027 legislature at the time of writing. Population figures are approximate. Verify against the primary source before relying on any number.

## Copyright

- **Official texts.** Under Art. 5 of the Swiss Copyright Act (URG), official authority texts (laws, official announcements, decisions) are not protected by copyright. Where such texts are reproduced, they are used on that basis. This includes the Federal Council's official voting explanations ("Erläuterungen des Bundesrates"), whose *for* and *against* arguments the vote pages reproduce **verbatim** and **in full for both sides**, each attributed to its author and linked to the official source. The committee's arguments (*for* an initiative, *against* a law challenged by referendum) are written by that committee (the brochure states the committee is responsible for their content and wording); they are shown as the committee's own words, labelled as such, never as the site's or an authority's position. Politikch adds no argument of its own and shows neither side alone. *(A native-language legal check of this reproduction is listed in `TRANSLATIONS_TODO.md`.)*
- **Editorial content.** Party descriptions and issue positions in `data/parties.json` are original editorial summaries based on published party manifestos and parliamentary voting records. They are interpretive and provided for information only — they are not statements by the parties themselves.
- **The party spectrum** (economic and social axes) is an editorial approximation intended to aid orientation, not a validated political-science measurement.
- **Reuse.** Politikch's own data is licensed CC BY 4.0. Official data keeps its source's terms. The website itself, including its code, design and text and the names and logos "Politikch", "PolitikCH" and "PCH", is all rights reserved. Per-file terms are in each file's `_meta` and in `data/LICENSE.txt`, both generated from `scripts/licences.py`. The site's **Data & reuse** page explains them. See `LICENSE`.

## Privacy

The site collects no personal data and sets no tracking cookies. Client-side storage holds the remembered interface language and the (unofficial) votes a visitor casts, kept on the visitor's own device. The one thing sent to a server is the **optional community poll**: when a visitor opts to vote on a present/future item or a session vote, an anonymous choice (no account, name, or identifier) is sent so aggregate counts can be shown; only running totals are stored, never a record linking a vote to a person. User data is never sold, rented, or shared with advertisers or data brokers, and there is no behavioural tracking or third-party profiling. See the full [Privacy Policy](#/privacy) (in-app, all four national languages), aligned with the revised Swiss Federal Act on Data Protection (revFADP/nFADP). The poll backend is off until `js/config.js` `POLL_API` is set (see `BACKEND.md`).

**Visit statistics.** The site counts visits with its own anonymous, cookie-free statistics service (a Cloudflare Worker with an EU-jurisdiction D1 database; code in `analytics-worker/`, switched on by `js/config.js` `ANALYTICS_API`). It records the page, referring site, approximate location (country/region/city), device, browser, OS, screen size, language and a few named actions. No IP address is stored; unique visitors are counted with a one-way hash using a salt that is deleted daily, so no visitor can be recognised across days. Raw records are deleted after 7 days; only anonymous daily totals are kept. How a visitor voted is never sent (only that a vote was cast). Global Privacy Control / Do Not Track are honoured, and visitors can opt out with the switch on the Privacy page or `?analytics=off`. Described in the Privacy Policy's "Anonymous visit statistics" section.

## Corrections

Data errors and factual corrections are welcome via an issue or pull request. The validator in `scripts/validate.py` guards structural integrity; factual accuracy relies on contributors and primary sources.
