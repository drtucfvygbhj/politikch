#!/usr/bin/env python3
"""Machine-translate missing session act titles into EN + RM (Rumantsch Grischun).

Swiss federal acts carry official titles only in German, French and Italian. The
site shows an *unofficial* English/Romansh title (clearly badged in the UI) when
one exists in data/sessions-translations.json. This build-time step fills the
titles that are missing — e.g. the acts from a newly-fetched session — using the
Anthropic API, so EN/RM appear within a week of a new session instead of waiting
for a hand translation.

It runs right after scripts/fetch_sessions.py in CI and is:

  * Incremental — only (id, language) pairs missing from the file are translated;
    existing entries (hand-curated or previously machine-made) are never
    overwritten, so manual corrections always win and the API cost stays tiny.
    When nothing is missing it makes no API call at all.
  * Safe & honest — if ANTHROPIC_API_KEY is unset (e.g. before the secret is
    configured) or the API/parse fails, it exits 0 without changes and the site
    keeps its DE/FR/IT fallback. A title it cannot translate is left missing, not
    guessed into the file. Output is marked "unofficial" in the UI as before.

Usage:
  python3 scripts/translate_sessions.py            # translate missing EN+RM
  python3 scripts/translate_sessions.py --dry-run  # list what's missing, no API calls

Env:
  ANTHROPIC_API_KEY   required to call the API (unset -> safe no-op)
  TRANSLATE_MODEL     optional model override (default claude-opus-5)
  TRANSLATE_TARGETS   optional comma-separated target langs (default "en,rm")
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = ROOT / "data" / "sessions"
TRANS_FILE = ROOT / "data" / "sessions-translations.json"

MODEL = os.environ.get("TRANSLATE_MODEL", "claude-opus-5")
TARGETS = [t.strip() for t in os.environ.get("TRANSLATE_TARGETS", "en,rm").split(",") if t.strip()]
BATCH_SIZE = 25

LANG_NAMES = {"en": "English", "rm": "Romansh (Rumantsch Grischun)"}

SYSTEM_PROMPT = (
    "You are a professional translator of official Swiss federal legislation titles. "
    "You are given the official German title of a Swiss federal act (with the French and "
    "Italian versions for reference) and must translate the title into the requested "
    "languages. Use the established English renderings of Swiss legal terms "
    "(e.g. 'Bundesgesetz über …' -> 'Federal Act on …', 'Verordnung' -> 'Ordinance', "
    "'Bundesbeschluss' -> 'Federal Decree', 'Änderung' -> 'Amendment'), and keep any "
    "parenthetical short title and abbreviation. For Romansh use Rumantsch Grischun. "
    "Translate only the title text; do not add commentary. "
    "Return ONLY a JSON array, one object per input id, of the form "
    '[{"id": "<id>", "en": "…", "rm": "…"}] with exactly the requested language keys.'
)


def load_titles():
    if not TRANS_FILE.exists():
        return {"note": "Unofficial translations.", "count": 0}, {}
    data = json.loads(TRANS_FILE.read_text(encoding="utf-8"))
    meta = data.get("_meta", {})
    titles = data.get("titles", {})
    # Normalise legacy plain-string entries ("<english>") to {"en": "<english>"}.
    for k, v in list(titles.items()):
        if isinstance(v, str):
            titles[k] = {"en": v}
    return meta, titles


def collect_acts():
    """{ id -> {de, fr, it} } for every final-vote act across all session files."""
    acts = {}
    for f in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            votes = json.loads(f.read_text(encoding="utf-8")).get("votes", [])
        except Exception:  # noqa: BLE001
            continue
        for v in votes:
            title = v.get("title") or {}
            if not (title.get("de") or title.get("fr") or title.get("it")):
                continue
            acts[str(v["id"])] = {k: title.get(k, "") for k in ("de", "fr", "it")}
    return acts


def missing_for(entry):
    """Target languages not yet present for one translation entry."""
    entry = entry or {}
    return [lg for lg in TARGETS if not (entry.get(lg) or "").strip()]


def translate_batch(client, items):
    """items: [{id, de, fr, it}] -> {id: {lang: text}} for the requested targets."""
    langs = ", ".join(LANG_NAMES.get(lg, lg) for lg in TARGETS)
    user = (
        f"Translate each of these Swiss federal act titles into: {langs}.\n"
        f"Return the JSON array described in the system prompt with keys "
        f"{', '.join(TARGETS)} for each id.\n\n"
        + json.dumps(items, ensure_ascii=False)
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    a, b = text.find("["), text.rfind("]")
    if a == -1 or b == -1 or b < a:
        raise ValueError("no JSON array in model response")
    out = {}
    for obj in json.loads(text[a:b + 1]):
        sid = str(obj.get("id", ""))
        if not sid:
            continue
        out[sid] = {lg: (obj.get(lg) or "").strip() for lg in TARGETS if (obj.get(lg) or "").strip()}
    return out


def main():
    dry = "--dry-run" in sys.argv[1:]
    meta, titles = load_titles()
    acts = collect_acts()

    todo = []  # ids missing at least one target language
    for sid, src in acts.items():
        if missing_for(titles.get(sid)):
            todo.append(sid)

    if not todo:
        print("All session act titles already have " + "/".join(TARGETS) + " translations; nothing to do.")
        return

    print(f"{len(todo)} act title(s) missing a {'/'.join(TARGETS)} translation.")
    if dry:
        for sid in todo[:50]:
            print(f"  {sid}: {acts[sid].get('de', '')[:70]}")
        if len(todo) > 50:
            print(f"  … and {len(todo) - 50} more")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY not set — skipping translation; the site keeps its "
              "DE/FR/IT fallback for these titles.", file=sys.stderr)
        return

    try:
        import anthropic
    except ImportError:
        print("The 'anthropic' package is required (pip install anthropic); skipping.", file=sys.stderr)
        return

    client = anthropic.Anthropic()
    filled = 0
    for i in range(0, len(todo), BATCH_SIZE):
        chunk = todo[i:i + BATCH_SIZE]
        items = [{"id": sid, **acts[sid]} for sid in chunk]
        try:
            result = translate_batch(client, items)
        except Exception as e:  # noqa: BLE001
            print(f"  batch {i // BATCH_SIZE + 1} failed ({e}); leaving those titles untranslated.",
                  file=sys.stderr)
            continue
        for sid in chunk:
            got = result.get(sid)
            if not got:
                continue
            entry = titles.setdefault(sid, {})
            for lg in TARGETS:
                # Fill only what's missing — never overwrite an existing (possibly
                # hand-corrected) translation.
                if got.get(lg) and not (entry.get(lg) or "").strip():
                    entry[lg] = got[lg]
                    filled += 1
        print(f"  translated batch {i // BATCH_SIZE + 1}/{-(-len(todo) // BATCH_SIZE)}")

    if not filled:
        print("No new translations were produced.")
        return

    meta["count"] = len(titles)
    TRANS_FILE.write_text(
        json.dumps({"_meta": meta, "titles": titles}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"Wrote {TRANS_FILE.relative_to(ROOT)} — filled {filled} translation field(s), "
          f"{len(titles)} acts total.")


if __name__ == "__main__":
    main()
