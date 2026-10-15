# Site version

The footer shows the site version ("Version 1.1014"). It started at **1.1** on
2026-10-15. It is a plain decimal number that only goes up: each change adds a
fixed value for each type of update it contains, so bigger changes move it
further. It is not semver, and the jumps are not even (1.1303 → 1.1342 →
1.4283 is normal).

**Not the design name.** "1.0" and "1.1" are also the names of the two designs
(the frozen original and the news layout) that `js/design.js` and the admin
switch between. Those names stay as they are; the site version is separate.

## What each type adds

| Type | Use it for | Adds |
|---|---|---|
| `text` | Text or translation fix: typo, wording, translation correction | +0.0001 |
| `data` | Data or link fix: fetcher bug, wrong or better link target | +0.0003 |
| `fix` | Bug fix: something broken on the site | +0.0005 |
| `gui` | Interface tweak: layout, styling, small UI element | +0.0010 |
| `rules` | Rules, privacy or legal change: guardrails, privacy or legal text | +0.0010 |
| `content` | New content: glossary entries, new data shown on an existing page | +0.0020 |
| `feature` | New feature: new page, tool or data source | +0.0050 |
| `major` | Major feature: like the session ticker, or the PolitikCH+ launch | +0.0200 |
| `design` | New design version: like 1.0 → 1.1 | +0.1000 |

A change that contains several types adds each one once. Example: a change with
a text fix, a link fix and a small interface addition is `text data gui`, so
1.1 + 0.0001 + 0.0003 + 0.0010 = **1.1014**. The number simply carries on past
1.1999 into 1.2…; that has no special meaning.

## How to bump it

One bump per change, in the same commit as the change:

```bash
python3 scripts/version.py bump text data gui --note "Government disclaimer, direct initiative links, version in footer"
```

- `python3 scripts/version.py show` prints the current version.
- `python3 scripts/version.py types` lists the types and values.
- The script writes `data/version.json` (the version plus a history of bumps).
  Don't edit that file by hand.
- The weekly data job and the session ticker **don't** bump the version: a data
  refresh isn't a change to the site.
