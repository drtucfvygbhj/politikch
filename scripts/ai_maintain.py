#!/usr/bin/env python3
"""One local trigger for ALL AI-assisted upkeep: vote overviews + title
translations. You run it whenever you like; it does a small batch and stops.

How it stays safe and within your limits
----------------------------------------
* It calls the **local `claude` CLI** (Claude Code) in print mode. That uses
  your already-logged-in Claude subscription — there is **no API key** in the
  repo or environment, nothing to leak or exploit.
* It therefore spends your normal subscription quota and is bound by the same
  5-hour and weekly limits. The moment `claude` reports a limit (or any error),
  this script **stops immediately** and leaves the rest for next time — "if the
  limit doesn't allow it, it just doesn't happen."
* `--max` caps how many items one run will attempt (default 6), so a single run
  is always small and predictable.

It never writes to the live site. Every result is staged as a proposal in
`review/queue/…` for you to approve or edit in the local review website
(`python3 scripts/review_server.py`). Nothing goes live until you approve it.

Usage:
  python3 scripts/ai_maintain.py                 # a small batch of everything
  python3 scripts/ai_maintain.py --task translation --max 10
  python3 scripts/ai_maintain.py --task overview --max 3
  python3 scripts/ai_maintain.py --dry-run       # stage stubs, don't call claude
"""
import argparse, glob, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "review", "queue")
LANGS = ["en", "de", "fr", "it", "rm"]
LEVELS = 5


# ---------------------------------------------------------------- claude CLI
def run_claude(prompt, dry_run=False):
    """Return (text, limited). `limited` True means stop the whole run."""
    if dry_run:
        return "__DRY_RUN__", False
    try:
        p = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        sys.exit("The 'claude' CLI isn't on PATH. Install Claude Code and run "
                 "`claude` once to log in, then re-run this script.")
    except subprocess.TimeoutExpired:
        print("    ! claude timed out; stopping.")
        return None, True
    out = (p.stdout or "").strip()
    blob = (out + "\n" + (p.stderr or "")).lower()
    limit_markers = ["usage limit", "rate limit", "limit reached", "limit exceeded",
                     "quota", "try again later", "you've hit", "resets at", "out of"]
    if p.returncode != 0 or any(m in blob for m in limit_markers):
        return None, True
    return out, False


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    return json.loads(text)


# ---------------------------------------------------------------- data helpers
def load_initiatives():
    d = json.load(open(os.path.join(ROOT, "data/initiatives.json"), encoding="utf-8"))
    return d if isinstance(d, list) else d.get("initiatives", [])


def load_session_votes():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/sessions/*.json"))):
        s = json.load(open(f, encoding="utf-8"))
        for v in s.get("votes", []):
            out.append(v)
    return out


def trans_file(kind):
    return os.path.join(ROOT, f"data/{'initiatives' if kind == 'initiative' else 'sessions'}-translations.json")


def existing_titles(kind):
    try:
        return json.load(open(trans_file(kind), encoding="utf-8")).get("titles", {})
    except Exception:
        return {}


def queued(task, kind, item_id):
    return os.path.exists(os.path.join(QUEUE, task, kind, f"{item_id}.json"))


def official_titles(title):
    if isinstance(title, dict):
        return {k: title.get(k) for k in ("de", "fr", "it") if title.get(k)}
    return {"de": title} if title else {}


# ---------------------------------------------------------------- task discovery
def translation_tasks():
    tasks = []
    for it in load_initiatives():
        cur = existing_titles("initiative").get(it["id"]) or {}
        cur = cur if isinstance(cur, dict) else {"en": cur}
        if (not cur.get("en") or not cur.get("rm")) and not queued("translation", "initiative", it["id"]):
            tasks.append(("initiative", it["id"], official_titles(it.get("title")), cur))
    for v in load_session_votes():
        vid = str(v["id"])
        cur = existing_titles("session").get(vid) or {}
        cur = cur if isinstance(cur, dict) else {"en": cur}
        if (not cur.get("en") or not cur.get("rm")) and not queued("translation", "session", vid):
            tasks.append(("session", vid, official_titles(v.get("title")), cur))
    return tasks


def overview_tasks():
    tasks = []
    for it in load_initiatives():
        if os.path.exists(os.path.join(ROOT, "data/overviews/initiative", f"{it['id']}.json")):
            continue
        if queued("overview", "initiative", it["id"]):
            continue
        tasks.append(("initiative", it["id"], localized(it.get("title")), localized(it.get("desc")), it.get("url")))
    for v in load_session_votes():
        vid = str(v["id"])
        if os.path.exists(os.path.join(ROOT, "data/overviews/session", f"{vid}.json")):
            continue
        if queued("overview", "session", vid):
            continue
        url = (f"https://www.parlament.ch/de/ratsbetrieb/suche-curia-vista/geschaeft?AffairId={v['businessNumber']}"
               if v.get("businessNumber") else None)
        tasks.append(("session", vid, localized(v.get("title")), "", url))
    return tasks


def localized(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for k in ("de", "fr", "it", "en"):
            if obj.get(k):
                return obj[k]
    return ""


# ---------------------------------------------------------------- prompts
def translation_prompt(official):
    src = "\n".join(f"{k.upper()}: {v}" for k, v in official.items())
    return ("Translate this official Swiss vote/act title into an UNOFFICIAL English (en) "
            "and Romansh (rm) title. Keep it faithful and neutral; do not add words that "
            "aren't in the original. Return ONLY JSON: {\"en\": \"…\", \"rm\": \"…\"}\n\n" + src)


def overview_prompt(title, desc, url):
    return (
        "You are writing a neutral, non-partisan explanation for an independent Swiss civic "
        "reference site. Explain what would concretely change if this proposal is ACCEPTED, "
        "in 5 detail levels (1 = one brief plain sentence … 5 = full technical account), in "
        "en, de, fr, it, rm.\n"
        "STRICT RULES: base it ONLY on the official text; if you cannot access the official "
        "source, reply exactly {\"insufficient_source\": true} and nothing else. Never invent "
        "figures, articles, dates or effects. Be non-partisan; never say whether accepting is "
        "good or bad; no party positions.\n"
        f"OFFICIAL SOURCE URL: {url}\nTITLE: {title}\nDESCRIPTION: {desc}\n\n"
        "Return ONLY JSON: {\"lang\": {\"en\": [l1..l5], \"de\": [...], \"fr\": [...], "
        "\"it\": [...], \"rm\": [...]}}"
    )


# ---------------------------------------------------------------- staging
def stage(task, kind, item_id, payload):
    d = os.path.join(QUEUE, task, kind)
    os.makedirs(d, exist_ok=True)
    payload.update({"task": task, "kind": kind, "id": item_id, "status": "pending",
                    "generatedAt": time.strftime("%Y-%m-%d %H:%M"), "via": "claude-cli"})
    path = os.path.join(d, f"{item_id}.json")
    json.dump(payload, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return os.path.relpath(path, ROOT)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["translation", "overview", "all"], default="all")
    ap.add_argument("--max", type=int, default=6, help="max items this run (keeps within limits)")
    ap.add_argument("--dry-run", action="store_true", help="stage stubs without calling claude")
    args = ap.parse_args()

    units = []
    if args.task in ("translation", "all"):
        units += [("translation", *t) for t in translation_tasks()]
    if args.task in ("overview", "all"):
        units += [("overview", *t) for t in overview_tasks()]

    if not units:
        print("Nothing pending — everything is generated or already queued for review.")
        return

    print(f"{len(units)} item(s) pending; attempting up to {args.max} this run.")
    made = 0
    for unit in units:
        if made >= args.max:
            print(f"Reached --max ({args.max}). Run again later for the rest.")
            break
        task = unit[0]
        if task == "translation":
            _, kind, item_id, official, _cur = unit
            if not official:
                continue
            print(f"[translation] {kind}/{item_id}: {list(official.values())[0][:60]}")
            text, limited = run_claude(translation_prompt(official), args.dry_run)
            if limited:
                print("    · Claude usage limit reached — stopping. The rest stays pending.")
                break
            try:
                prop = {"en": "DRY RUN en", "rm": "DRY RUN rm"} if args.dry_run else parse_json(text)
                assert prop.get("en") and prop.get("rm")
            except Exception as e:  # noqa: BLE001
                print(f"    ! could not parse translation ({e}); skipping.")
                continue
            rel = stage("translation", kind, item_id, {"official": official, "proposal": {"en": prop["en"], "rm": prop["rm"]}})
        else:
            _, kind, item_id, title, desc, url = unit
            print(f"[overview] {kind}/{item_id}: {title[:60]}")
            text, limited = run_claude(overview_prompt(title, desc, url), args.dry_run)
            if limited:
                print("    · Claude usage limit reached — stopping. The rest stays pending.")
                break
            if args.dry_run:
                prop = {"lang": {lg: [f"DRY RUN {lg} L{i+1}" for i in range(LEVELS)] for lg in LANGS}}
            else:
                try:
                    data = parse_json(text)
                    if data.get("insufficient_source"):
                        print("    · Claude couldn't reach the official source; skipping (not fabricated).")
                        continue
                    for lg in LANGS:
                        assert isinstance(data["lang"][lg], list) and len(data["lang"][lg]) == LEVELS
                    prop = {"lang": {lg: data["lang"][lg] for lg in LANGS}}
                except Exception as e:  # noqa: BLE001
                    print(f"    ! could not parse overview ({e}); skipping.")
                    continue
            rel = stage("overview", kind, item_id, {"title": title, "sourceUrl": url, "proposal": prop})
        made += 1
        print(f"    ✓ staged {rel}")
        if not args.dry_run:
            time.sleep(1)

    print(f"\nDone. {made} proposal(s) staged for review.\n"
          f"Review them: python3 scripts/review_server.py  →  http://127.0.0.1:8777")


if __name__ == "__main__":
    main()
