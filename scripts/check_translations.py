#!/usr/bin/env python3
"""Report vote/act titles that still need an (unofficial) English or Romansh
translation, and leave a committed reminder — TRANSLATIONS_TODO.md — so the
project needs no AI/translation API anywhere.

Swiss popular-vote and federal-act titles are official only in German, French
and Italian. The English (`en`) and Romansh (`rm`) titles the site shows are
hand-made, unofficial, and live in:
  * data/initiatives-translations.json   (popular votes & initiatives)
  * data/sessions-translations.json      (Federal Assembly final-vote act titles)

This runs in CI right after the data fetch. When a new initiative or session
arrives without an EN/RM title it lists it (with the German title for context)
in TRANSLATIONS_TODO.md, which is committed with the data. A human then opens a
Claude Code session and asks for the pending titles to be translated by hand.

It calls no network service, needs no key, and always exits 0 — until a
translation is added the site simply falls back to the official DE/FR/IT title.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("en", "rm")


def load_titles(name):
    p = ROOT / "data" / name
    if not p.exists():
        return {}
    titles = json.loads(p.read_text(encoding="utf-8")).get("titles", {})
    # Normalise legacy plain-string entries ("<english>") to {"en": "<english>"}.
    return {k: ({"en": v} if isinstance(v, str) else (v or {})) for k, v in titles.items()}


# A language is covered if the item already carries that title (e.g. VoteInfo
# supplies an official English title) OR a hand-made translation exists for it.
def _real(lang, text):
    """A title only counts if it is really in that language: fetch_initiatives.py
    writes a pending initiative's English title as the German name framed in
    English ("Federal popular initiative «…»"), which is a placeholder."""
    text = (text or "").strip()
    return bool(text) and not (lang == "en" and text.startswith("Federal popular initiative «"))


def missing_langs(own_title, entry):
    own_title = own_title or {}
    entry = entry or {}
    return [lg for lg in LANGS
            if not (_real(lg, own_title.get(lg)) or (entry.get(lg) or "").strip())]


def source_title(title):
    title = title or {}
    return title.get("de") or title.get("fr") or title.get("it") or ""


def collect():
    items = []  # (category, id, missing_langs, german_title)

    inits = json.loads((ROOT / "data" / "initiatives.json").read_text(encoding="utf-8")).get("initiatives", [])
    itr = load_titles("initiatives-translations.json")
    for it in inits:
        miss = missing_langs(it.get("title"), itr.get(it["id"]))
        if miss:
            items.append(("initiative", it["id"], miss, source_title(it.get("title"))))

    str_ = load_titles("sessions-translations.json")
    sdir = ROOT / "data" / "sessions"
    if sdir.exists():
        for f in sorted(sdir.glob("*.json")):
            for v in json.loads(f.read_text(encoding="utf-8")).get("votes", []):
                miss = missing_langs(v.get("title"), str_.get(str(v["id"])))
                if miss:
                    items.append(("session act", str(v["id"]), miss, source_title(v.get("title"))))
    return items


def main():
    items = collect()
    out = ROOT / "TRANSLATIONS_TODO.md"
    lines = ["# Translations to do", ""]
    if not items:
        lines += ["✓ Everything is translated — every initiative and session act title has an "
                  "English and Romansh version.", ""]
    else:
        lines += [
            f"## {len(items)} title(s) need translation",
            "",
            "Swiss vote/act titles are official only in German, French and Italian. The site shows "
            "hand-made **unofficial** English (`en`) and Romansh (`rm`) titles; the ones below are "
            "missing and currently fall back to the official German title.",
            "",
            "**To fix:** open a Claude Code session and say "
            "*“translate the pending titles in TRANSLATIONS_TODO.md”*. Add each translation to "
            "`data/initiatives-translations.json` or `data/sessions-translations.json` under "
            "`titles.<id>` as `{ \"en\": …, \"rm\": … }`.",
            "",
            "| Type | ID | Missing | German title |",
            "|---|---|---|---|",
        ]
        for cat, id_, miss, de in items:
            de_safe = de.replace("|", "\\|")
            lines.append(f"| {cat} | `{id_}` | {', '.join(miss)} | {de_safe} |")
        lines.append("")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if items:
        # GitHub Actions annotation — shows up on the workflow run.
        print(f"::warning::{len(items)} title(s) need an unofficial EN/RM translation — see TRANSLATIONS_TODO.md")
    else:
        print("All initiative and session-act titles have EN and RM translations.")


if __name__ == "__main__":
    main()
