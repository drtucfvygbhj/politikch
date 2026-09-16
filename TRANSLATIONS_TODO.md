# Translations to do

## 1 title(s) need translation

Swiss vote/act titles are official only in German, French and Italian. The site shows hand-made **unofficial** English (`en`) and Romansh (`rm`) titles; the ones below are missing and currently fall back to the official German title.

**To fix:** open a Claude Code session and say *“translate the pending titles in TRANSLATIONS_TODO.md”*. Add each translation to `data/initiatives-translations.json` or `data/sessions-translations.json` under `titles.<id>` as `{ "en": …, "rm": … }`.

| Type | ID | Missing | German title |
|---|---|---|---|
| initiative | `initiative-586` | rm | Eidgenössische Volksinitiative "Wer vertreibt, muss zahlen (Initiative für eine Kostenverantwortung der Herkunftsstaaten)"
 |

## To review
- **Share controls** (`share.*` keys in `data/i18n.json`): added for the per-graph share buttons. EN/DE/FR/IT are confident; the **Romansh (rm)** strings are best-effort and would benefit from a native review — `share.button`, `share.menuLabel`, `share.saveImage`, `share.copyLink`, `share.copied`, `share.nativeShare`, `share.imageNote`, `share.vote.yes/no/abstain`.
- **Privacy / About / Subscribe pages + share terms** (`privacy.*`, `about.*`, `subscribe.*`, `share.terms`, `share.src.*`, `footer.disclaimer`, `common.*`): EN/DE/FR/IT are confident, but the **legal wording** (especially FADP/nFADP references, "profiling", "data brokers", "redress"/FDPIC) should get a native legal/native-speaker check in **FR, IT and DE**, and all **Romansh (rm)** strings on these pages are best-effort and need a native review before launch.
- **Privacy effective date** (`privacy.effective`) is set to 12 September 2026; update if the policy's real effective date differs.
