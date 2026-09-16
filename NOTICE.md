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
| Canton statistics (population, area) | Federal Statistical Office (BFS) — rounded approximations |

Figures were current as of the 2023–2027 legislature at the time of writing. Population figures are approximate. Verify against the primary source before relying on any number.

## Copyright

- **Official texts.** Under Art. 5 of the Swiss Copyright Act (URG), official authority texts (laws, official announcements, decisions) are not protected by copyright. Where such texts are reproduced, they are used on that basis.
- **Editorial content.** Party descriptions and issue positions in `data/parties.json` are original editorial summaries based on published party manifestos and parliamentary voting records. They are interpretive and provided for information only — they are not statements by the parties themselves.
- **The party spectrum** (economic and social axes) is an editorial approximation intended to aid orientation, not a validated political-science measurement.

## Privacy

The site collects no personal data and sets no tracking cookies. Client-side storage holds the remembered interface language and the (unofficial) votes a visitor casts, kept on the visitor's own device. The one thing sent to a server is the **optional community poll**: when a visitor opts to vote on a present/future item or a session vote, an anonymous choice (no account, name, or identifier) is sent so aggregate counts can be shown; only running totals are stored, never a record linking a vote to a person. User data is never sold, rented, or shared with advertisers or data brokers, and there is no behavioural tracking or third-party profiling. See the full [Privacy Policy](#/privacy) (in-app, all four national languages), aligned with the revised Swiss Federal Act on Data Protection (revFADP/nFADP). The poll backend is off until `js/config.js` `POLL_API` is set (see `BACKEND.md`).

## Corrections

Data errors and factual corrections are welcome via an issue or pull request. The validator in `scripts/validate.py` guards structural integrity; factual accuracy relies on contributors and primary sources.
