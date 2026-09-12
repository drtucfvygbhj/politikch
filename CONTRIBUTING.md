# Contributing

Thanks for helping keep Politikch accurate. It's a small, dependency-free static site, so contributing is straightforward.

## Ground rules

- **Keep descriptions even-handed and sourced.** Summarise positions rather than arguing for them; avoid advocacy or loaded language.
- **Cite primary sources.** Prefer official sources (BFS, parlament.ch, Federal Chancellery, cantonal chancelleries) over secondary reporting for facts and figures.
- **Be honest about gaps.** If data isn't available yet, use a clearly-labelled placeholder rather than an estimate presented as fact.

## Making a change

1. Edit the relevant file in `data/` (content) or the `css`/`js` files (behaviour and design).
2. Run the validator:
   ```bash
   python3 scripts/validate.py
   ```
3. Serve locally and click through what you changed:
   ```bash
   python3 -m http.server 8000
   ```
4. Open a pull request. CI will re-run the validator automatically.

## Data invariants (enforced by CI)

- National Council seats sum to **200** in both `parties.json` and `cantons.json`.
- Council of States seats sum to **46** in `parties.json`.
- `cantons.json` contains exactly **26** cantons.
- Every UI string key exists in **all four** languages in `i18n.json`.
- `type` ∈ {initiative, referendum}; `status` ∈ {adopted, rejected, pending, collecting}.

## Adding a translation string

Add the key to **all four** language blocks in `data/i18n.json` (`en`, `de`, `fr`, `it`). The validator will fail if any language is missing a key.

## Adding a vote

Append an object to the `initiatives` array in `data/initiatives.json`. Include `title`, `desc`, `date` and (where decided) `outcome` in at least English, plus a `url` to the official page. Set `status` accurately.
