#!/usr/bin/env python3
"""Generate the AI "what happens if accepted" overviews, OFFLINE.

For every initiative/referendum (data/initiatives.json) and session vote
(data/sessions/<n>.json), this writes data/overviews/<kind>/<id>.json holding
five detail levels (brief -> in-depth) in all five site languages. The live
site only READS these files; it never calls an LLM.

Honesty guardrails (this is a non-partisan civic site making legal claims):
  * The summary is grounded ONLY in the official text fetched from the item's
    own official URL. If that text can't be retrieved, the item is SKIPPED —
    the script never writes an overview from the model's own memory.
  * Every file is written with "reviewed": false. The site treats that as
    "being prepared" and will NOT display it until a human sets it to true.
    Read each overview, correct it, flip the flag, then commit.

Usage:
  export ANTHROPIC_API_KEY=...            # or `ant auth login`
  python3 scripts/generate_overviews.py --kind initiative --limit 5
  python3 scripts/generate_overviews.py --kind session
Options:
  --kind {initiative,session,all}  what to generate (default: all)
  --limit N                        stop after N newly-generated items
  --force                          regenerate even if a file already exists
  --model ID                       override model (default: claude-opus-5)

Requires the official SDK: pip install anthropic
"""
import argparse, glob, html, json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ["en", "de", "fr", "it", "rm"]
LEVELS = 5
MODEL = os.environ.get("POLITIKCH_OVERVIEW_MODEL", "claude-opus-5")

SYSTEM = (
    "You write neutral, non-partisan explanations of Swiss federal votes for an "
    "independent civic reference site. You are given the OFFICIAL text of a "
    "proposal. Explain, strictly from that text, what would concretely change if "
    "it is ACCEPTED — the actual legal/administrative changes, who is affected, "
    "and when they take effect. Rules: (1) Use ONLY the provided official text; "
    "never invent figures, articles, dates or effects. If the text does not say "
    "something, do not state it. (2) Be strictly non-partisan — describe, never "
    "recommend, and never say whether accepting is good or bad. (3) No party "
    "positions. (4) If the text is too thin to say what changes, say so plainly."
)

INSTR = (
    "Produce EXACTLY {levels} detail levels, from level 1 (one brief, plain-"
    "language sentence) to level {levels} (a full, technical account of every "
    "change, the articles amended, affected parties, timing and exceptions). "
    "Provide all levels in each of these languages: {langs}. Return ONLY a JSON "
    "object of this exact shape, no prose around it:\n"
    '{{"lang": {{"en": ["l1","l2","l3","l4","l5"], "de": [...], "fr": [...], '
    '"it": [...], "rm": [...]}}}}'
)


def strip_html(raw):
    raw = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_source(url):
    """Best-effort fetch of the official page's visible text. Returns '' on
    failure — the caller then SKIPS the item rather than fabricating."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolitikchOverviewBot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read(600_000).decode("utf-8", "replace")
        text = strip_html(raw)
        return text[:16000]
    except Exception as e:  # noqa: BLE001
        print(f"    ! could not fetch {url}: {e}", file=sys.stderr)
        return ""


def load_items(kind):
    items = []
    if kind in ("initiative", "all"):
        data = json.load(open(os.path.join(ROOT, "data/initiatives.json"), encoding="utf-8"))
        arr = data if isinstance(data, list) else data.get("initiatives", [])
        for it in arr:
            items.append(("initiative", it["id"], localized(it.get("title")), localized(it.get("desc")), it.get("url")))
    if kind in ("session", "all"):
        for f in sorted(glob.glob(os.path.join(ROOT, "data/sessions/*.json"))):
            sess = json.load(open(f, encoding="utf-8"))
            for v in sess.get("votes", []):
                url = (f"https://www.parlament.ch/de/ratsbetrieb/suche-curia-vista/geschaeft?AffairId={v['businessNumber']}"
                       if v.get("businessNumber") else None)
                items.append(("session", str(v["id"]), localized(v.get("title")), "", url))
    return items


def localized(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for k in ("de", "fr", "it", "en"):
            if obj.get(k):
                return obj[k]
    return ""


def out_path(kind, item_id):
    return os.path.join(ROOT, "data/overviews", kind, f"{item_id}.json")


def generate(client, title, desc, source):
    msg = (
        f"TITLE: {title}\n\nDESCRIPTION: {desc}\n\nOFFICIAL TEXT (extracted):\n{source}\n\n"
        + INSTR.format(levels=LEVELS, langs=", ".join(LANGS))
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM,
        messages=[{"role": "user", "content": msg}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # tolerate code fences
    data = json.loads(text)
    lang = data["lang"]
    for lg in LANGS:
        arr = lang.get(lg)
        if not isinstance(arr, list) or len(arr) != LEVELS:
            raise ValueError(f"language {lg} did not return {LEVELS} levels")
    return {"lang": {lg: lang[lg] for lg in LANGS}, "model": MODEL}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["initiative", "session", "all"], default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic  (see scripts/requirements.txt)")
    global MODEL
    MODEL = args.model
    client = anthropic.Anthropic()  # resolves ANTHROPIC_API_KEY / ant auth profile

    made = 0
    for kind, item_id, title, desc, url in load_items(args.kind):
        path = out_path(kind, item_id)
        if os.path.exists(path) and not args.force:
            continue
        if args.limit and made >= args.limit:
            break
        print(f"[{kind}] {item_id}: {title[:70]}")
        source = fetch_source(url)
        if len(source) < 200:
            print("    · skipped (no official text to ground the summary)")
            continue
        try:
            payload = generate(client, title, desc, source)
        except Exception as e:  # noqa: BLE001
            print(f"    ! generation failed: {e}", file=sys.stderr)
            continue
        payload.update({
            "generatedAt": time.strftime("%Y-%m-%d"),
            "sourceUrl": url,
            "reviewed": False,  # a human must read, correct, and flip this to true
        })
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(payload, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        made += 1
        print(f"    ✓ wrote {os.path.relpath(path, ROOT)} (reviewed:false — review before publishing)")
        time.sleep(1)  # be gentle on the API + source servers

    print(f"\nDone. {made} overview(s) generated. Review each, set \"reviewed\": true, then commit.")


if __name__ == "__main__":
    main()
