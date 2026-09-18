# Official for/against vote arguments

Files here are produced by `scripts/fetch_arguments.py`, which reproduces the
**official** for/against arguments **verbatim** from the Federal Council's voting
explanations ("Erläuterungen des Bundesrates" / Abstimmungsbüechli). They are
official texts (Art. 5 URG — see `NOTICE.md`), so there is **no AI and no review
gate**. The live site only reads them. If a file is missing, the page shows an
honest "not published yet" state.

## Layout
- `initiative/<id>.json` — for an initiative/referendum (`id` from `data/initiatives.json`)

## Shape
```json
{
  "generatedAt": "2026-09-18",
  "source": "Federal Council voting explanations (Erläuterungen des Bundesrates) … Art. 5 URG",
  "sourceUrl": { "de": "…brochure-de.pdf", "fr": "…brochure-fr.pdf" },
  "lang": {
    "de": { "pros": ["…"], "cons": ["…"] },
    "fr": { "pros": ["…"], "cons": ["…"] }
  }
}
```
- **One reading level.** `pros` = arguments of the initiative/referendum
  committee; `cons` = arguments of the Federal Council and Parliament — both
  verbatim, each an array of paragraphs. The neutral framing stays the
  initiative's own title/description already on the page.
- **DE/FR are automatic** (from the officially-published brochure, mirrored by
  Swissvotes). **IT** appears only if an official PDF is supplied via
  `--pdf-dir` (see `data/brochures/README.md`). **EN/RM never exist officially**
  and fall back on-site to DE/FR/IT with a small language chip.
- No `reviewed` flag: these are official texts, shown as soon as they exist.
