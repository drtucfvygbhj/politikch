# Pre-generated "what happens if accepted" overviews

Files here are produced **offline** by `scripts/generate_overviews.py`, reviewed
by a person, then committed. The live site only reads them (it never calls an
LLM). If a file is missing, the site shows an honest "being prepared" state.

## Layout
- `initiative/<id>.json` — for an initiative/referendum (`id` from `data/initiatives.json`)
- `session/<voteId>.json` — for a session vote (`voteId` from `data/sessions/<n>.json`)

## Shape
```json
{
  "generatedAt": "2026-09-16",
  "model": "<model id used>",
  "reviewed": true,
  "sourceUrl": "<official text the summary was written from>",
  "lang": {
    "en": ["level 1 (brief/plain)", "…", "…", "…", "level 5 (full/technical)"],
    "de": ["…","…","…","…","…"],
    "fr": ["…","…","…","…","…"],
    "it": ["…","…","…","…","…"],
    "rm": ["…","…","…","…","…"]
  }
}
```
- Exactly **5 levels** per language (the slider has 5 stops: brief → in depth).
- All five site languages should be present; the reader falls back de→en if one
  is missing.
- `reviewed: true` is the human sign-off gate — don't commit unreviewed files.
