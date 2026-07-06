# Politikch

An independent, non-partisan reference for Swiss democracy — parliament, parties, cantons and popular votes, in four national languages (DE / FR / IT / EN).

> **Not an official site.** Politikch is not affiliated with, endorsed by, or representing the Swiss Confederation, any cantonal government, or any political party. Official texts are reproduced under Art. 5 URG (no copyright on official authority texts). Party positions are editorial summaries for information only.

## What it does

- **Interactive canton map** — click any of the 26 cantons to open its page.
- **Federal Assembly** — hemicycle seat charts for the National Council (200) and Council of States (46), from the 2023–2027 legislature.
- **Party profiles** — each party's positions, seat counts, a left/right × progressive/traditional spectrum, and links to official sources.
- **Popular votes** — recent and pending federal initiatives and referendums, with search, type filters, and official outcomes linked to the Federal Chancellery.
- **Four languages** — the whole interface switches between German, French, Italian and English; the choice is remembered.
- **Shareable URLs** — every canton and party has its own hash route (e.g. `#/party/SVP`, `#/canton/ZH`), so links and the back button work.

## Project structure

```
.
├── index.html            # Page shell (semantic HTML, no inline logic)
├── css/
│   └── styles.css        # All styling; design tokens as CSS variables
├── js/
│   ├── app.js            # App logic: data loading, i18n, router, rendering
│   └── map-data.js       # Simplified canton SVG paths + label centroids
├── data/                 # All content lives here as JSON, separate from code
│   ├── parties.json
│   ├── cantons.json
│   ├── initiatives.json
│   └── i18n.json         # UI string translations for the four languages
├── scripts/
│   └── validate.py       # Data integrity checks (also run in CI)
└── .github/workflows/    # Pages deploy + data validation
```

The site is **fully static** — no build step, no framework, no dependencies. Data is deliberately separated from code so it can be updated (or wired to a real API) without touching the rendering logic.

## Running locally

Because the app loads JSON with `fetch` and uses ES modules, it must be served over HTTP (opening `index.html` from disk won't work). Any static server does:

```bash
python3 -m http.server 8000
# then open http://localhost:8000
```

## Updating the data

Edit the relevant file in `data/` and reload — no rebuild needed.

- **Parties:** `data/parties.json`. Seat counts must sum to 200 (National Council) and 46 (Council of States).
- **Cantons:** `data/cantons.json`. All 26 cantons; `seats` must sum to 200.
- **Votes:** `data/initiatives.json`. `type` is `initiative` or `referendum`; `status` is `adopted`, `rejected`, `pending` or `collecting`.
- **Interface text:** `data/i18n.json`. Every key must exist in all four languages.

Before committing, run the validator:

```bash
python3 scripts/validate.py
```

This checks JSON validity, seat totals, required fields, and that all four languages share the same set of translation keys. It runs automatically on every push and pull request.

## Connecting real data sources

Several sections (cantonal elections, municipalities, cantonal parliaments and votes) currently show clearly-labelled placeholders describing where official data will come from. They're intentionally honest rather than filled with invented figures. To wire them up, fetch from the official open-data endpoints and render into the existing containers in `renderCantonPage()`:

- Federal & cantonal results: [opendata.swiss](https://opendata.swiss) / [wahlen.admin.ch](https://www.wahlen.admin.ch)
- Parliament composition and groups: [parlament.ch](https://www.parlament.ch)
- Vote results and texts: [Federal Chancellery](https://www.bk.admin.ch)

## Deployment

Pushing to `main` triggers `.github/workflows/deploy.yml`, which publishes the repository to GitHub Pages.

### Custom domain

If you're serving this from a domain you own, add a `CNAME` file at the repository root containing just the domain (e.g. `politikch.ch`) and configure the domain's DNS per [GitHub's custom-domain docs](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site). A template is included as `CNAME.example`.

## Accessibility

Keyboard-navigable throughout (map, seats, spectrum, cards, modal), visible focus states, ARIA labels on interactive SVG elements, a skip link, and `prefers-reduced-motion` support.

## Licence

Code is released under the MIT Licence (see `LICENSE`). Content in `data/` consists of official authority texts (not subject to copyright under Art. 5 URG) and original editorial summaries. See `NOTICE.md` for details on sources and attribution.
