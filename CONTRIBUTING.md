# Contributing

Thanks for helping keep Politikch accurate. It's a small, dependency-free static site, so contributing is straightforward.

## Ground rules

- **Keep descriptions even-handed and sourced.** Summarise positions rather than arguing for them; avoid advocacy or loaded language.
- **Cite primary sources.** Prefer official sources (BFS, parlament.ch, Federal Chancellery, cantonal chancelleries) over secondary reporting for facts and figures.
- **Be honest about gaps.** If data isn't available yet, use a clearly-labelled placeholder rather than an estimate presented as fact.

## Making a change

Every change follows [`GUARDRAILS.md`](GUARDRAILS.md). In practice:

1. Once per clone, turn on the pre-push check:
   ```bash
   git config core.hooksPath .githooks
   ```
2. Edit the relevant file in `data/` (content) or the `css`/`js` files (behaviour and design).
3. Run the guardrail checks and fix anything marked **BLOCK**:
   ```bash
   python3 scripts/check.py
   ```
4. Serve locally and click through what you changed (at least EN, DE, FR; desktop and phone width):
   ```bash
   python3 -m http.server 8001
   ```
5. Commit. For every **FLAG** the owner has approved, add one line to the commit message:
   `Approved-Rule: <ID> — why this is fine`. The push is refused while a flag is unsigned,
   and `deploy.yml` won't deploy until the checks pass.

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
