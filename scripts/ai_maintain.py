#!/usr/bin/env python3
"""One local trigger for ALL AI-assisted upkeep: vote overviews + title
translations. You run it whenever you like; it does a small batch and stops.

How it stays safe, cheap, and within your limits
------------------------------------------------
* It calls the **local `claude` CLI** (Claude Code) in print mode. That uses
  your already-logged-in Claude subscription — there is **no API key** in the
  repo or environment, nothing to leak or exploit.
* Each `claude -p` call carries a large fixed overhead (agent system prompt +
  tool schemas + project context), so we keep cost down by (a) using a light
  model — Haiku by default, set POLITIKCH_MODEL to change — (b) BATCHING many
  items into one call (POLITIKCH_TR_BATCH titles / POLITIKCH_OV_BATCH overviews),
  (c) passing `--allowedTools ""` and running from a neutral dir so no tools or
  project files load. Overviews are grounded on official text fetched here (not
  by the model), so the call is a pure, cheap text task.
* It therefore spends your normal subscription quota and is bound by the same
  5-hour and weekly limits. The moment `claude` reports a limit (or any error),
  this script **stops immediately** and leaves the rest for next time — "if the
  limit doesn't allow it, it just doesn't happen."
* It is fully **resumable and incremental**. Each finished item is saved on its
  own the instant it's 100% complete (translations validated for the missing
  language; overviews validated for all 5 levels × 5 languages), written with a
  temp-file+rename so a crash never leaves a partial file. The next run skips
  everything already live or already staged and picks up at the first item that
  isn't done — minutes, an hour (after the limit resets), or weeks later. You can
  approve the staged ones any time in between.
* By default it attempts as many items as your usage limit allows (stopping the
  moment Claude reports a limit); pass `--max N` to cap a run.

It never writes to the live site. Every result is staged as a proposal in
`review/queue/…` for you to approve or edit in the local review website
(`python3 scripts/review_server.py`). Nothing goes live until you approve it.

Usage:
  python3 scripts/ai_maintain.py                 # a small batch of everything
  python3 scripts/ai_maintain.py --task translation --max 10
  python3 scripts/ai_maintain.py --task overview --max 3
  python3 scripts/ai_maintain.py --dry-run       # stage stubs, don't call claude
"""
import argparse, glob, html, json, os, re, subprocess, sys, tempfile, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "review", "queue")
LANGS = ["en", "de", "fr", "it", "rm"]
LEVELS = 5

# Each `claude -p` call spins up a full Claude Code agent (big system prompt +
# tool schemas + project context), so the FIXED per-call cost dwarfs a small
# translation. Two levers keep us cheap: a light model, and BATCHING many items
# into one call so that fixed cost is amortised. Both are overridable via env.
MODEL = os.environ.get("POLITIKCH_MODEL", "haiku")        # 'haiku' | 'sonnet' | 'opus' | full id
TR_BATCH = int(os.environ.get("POLITIKCH_TR_BATCH", "20"))  # titles per call
OV_BATCH = int(os.environ.get("POLITIKCH_OV_BATCH", "3"))   # overviews per call (large output each)
# A neutral working dir so the CLI doesn't load this project's CLAUDE.md / .claude
# context into every call (pure token overhead for a plain text task).
NEUTRAL_CWD = tempfile.gettempdir()


def write_json_atomic(path, obj):
    """Write JSON via a temp file + rename, so a crash/kill mid-write can never
    leave a half-written (non-100%-complete) file behind."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------- claude CLI
# Phrases Claude Code actually uses when you're out of quota. Kept deliberately
# specific — broad words like "out of" or "quota" falsely flagged normal replies.
LIMIT_MARKERS = [
    "usage limit", "rate limit", "reached your limit", "limit reached",
    "limit will reset", "usage limit reached", "please try again later",
    "too many requests", "overloaded", "session limit", "you've hit your",
    "weekly limit", "5-hour limit", "resets ",
]


def run_claude(prompt, dry_run=False):
    """Return (text, status, raw, cost). status is 'ok' | 'limit' | 'error'; cost
    is the call's total_cost_usd (a proxy for how much of your limit it used).
    Uses --output-format json so we get the cost + a clean result field. Prompt on
    stdin; light model, no tools, neutral cwd to keep per-call overhead down."""
    if dry_run:
        return "__DRY_RUN__", "ok", "", 0.0, 0
    cmd = ["claude", "-p", "--model", MODEL, "--allowedTools", "", "--output-format", "json"]
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                           timeout=1200, cwd=NEUTRAL_CWD)
    except FileNotFoundError:
        sys.exit("The 'claude' CLI isn't on PATH. Install Claude Code and run "
                 "`claude` once to log in, then re-run this script.")
    except subprocess.TimeoutExpired:
        return None, "error", "claude timed out after 1200s", 0.0, 0
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    raw = f"exit={p.returncode}" + (f"\n{out[-800:]}" if out else "") + (f"\n[stderr] {err[-500:]}" if err else "")
    text, cost, tokens, is_err = out, 0.0, 0, False
    try:  # JSON envelope from --output-format json
        env = json.loads(out)
        text = env.get("result", "") or ""
        cost = float(env.get("total_cost_usd") or 0.0)
        u = env.get("usage") or {}
        tokens = int((u.get("input_tokens") or 0) + (u.get("output_tokens") or 0)
                     + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0))
        is_err = bool(env.get("is_error"))
    except Exception:
        pass  # auth/other failures print plain text, not JSON — handle below
    blob = (out + "\n" + err + "\n" + text).lower()
    if any(m in blob for m in LIMIT_MARKERS):
        return None, "limit", raw, cost, tokens
    if p.returncode != 0 or is_err or not text.strip():
        return None, "error", raw, cost, tokens
    return text, "ok", raw, cost, tokens


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    return json.loads(text)


def handle_stop(status, raw):
    """Print why we're stopping and return True if the run should stop. Errors are
    shown verbatim so a failing CLI is never mistaken for a usage limit."""
    if status == "limit":
        print("    · Claude usage limit reached — stopping. Progress so far is saved; "
              "run again after it resets.")
        return True
    if status == "error":
        low = (raw or "").lower()
        if any(w in low for w in ("authenticate", "oauth", "not logged in", "log in", "login", "session expired", "unauthorized")):
            print("    ! Claude is NOT LOGGED IN (its session expired) — this is not a usage limit.")
            print("      Fix: open a terminal and run  claude  once to log in again, then click Run maintenance.")
        else:
            print("    ! Claude returned an ERROR (not a usage limit) — stopping so it isn't hidden.")
            print("      Sanity-check in a terminal:  claude -p \"say OK\"")
        print("      What `claude -p` actually returned:")
        for line in (raw or "(no output)").splitlines():
            print("        " + line)
        return True
    return False


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
def _needed_langs(cur, title):
    """Languages we still need to generate: en/rm that are absent from BOTH our
    translations AND the official title. If the official title already has a
    language (e.g. official English on federal initiatives), we never generate an
    unofficial one for it — the site uses the official version."""
    official = title if isinstance(title, dict) else {}
    return [lg for lg in ("en", "rm") if not official.get(lg) and not cur.get(lg)]


def translation_tasks():
    tasks = []
    for it in load_initiatives():
        cur = existing_titles("initiative").get(it["id"]) or {}
        cur = cur if isinstance(cur, dict) else {"en": cur}
        need = _needed_langs(cur, it.get("title"))
        if need and not queued("translation", "initiative", it["id"]):
            tasks.append(("initiative", it["id"], official_titles(it.get("title")), cur, need))
    for v in load_session_votes():
        vid = str(v["id"])
        cur = existing_titles("session").get(vid) or {}
        cur = cur if isinstance(cur, dict) else {"en": cur}
        need = _needed_langs(cur, v.get("title"))
        if need and not queued("translation", "session", vid):
            tasks.append(("session", vid, official_titles(v.get("title")), cur, need))
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


# ---------------------------------------------------------------- source text
def fetch_source(url):
    """Best-effort fetch of an official page's visible text, passed into the prompt
    so the model doesn't need (expensive, tool-using) web access. '' on failure →
    the item is skipped, never fabricated."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolitikchBot/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read(500_000).decode("utf-8", "replace")
        raw = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
        text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
        return re.sub(r"\s+", " ", text).strip()[:6000]
    except Exception:
        return ""


# ---------------------------------------------------------------- batch prompts
def tr_batch_prompt(batch):
    """batch: list of (kind, id, official{de/fr/it}, cur, need[list])."""
    lines = []
    for _k, iid, official, _cur, need in batch:
        src = " | ".join(f"{k.upper()}: {v}" for k, v in official.items())
        lines.append(f'- id "{iid}" — need {",".join(need)} — {src}')
    return (
        "Translate each Swiss vote/act TITLE below into UNOFFICIAL versions in the requested "
        "languages (en=English, rm=Romansh). Faithful and neutral; add no words not in the "
        "original. Output ONLY a JSON object mapping each id to its requested translations, "
        'e.g. {"<id>": {"en": "…", "rm": "…"}}. Include only the requested languages per item.\n\n'
        "ITEMS:\n" + "\n".join(lines)
    )


def ov_batch_prompt(batch):
    """batch: list of (kind, id, title, desc, url, source)."""
    blocks = []
    for _k, iid, title, desc, _url, source in batch:
        blocks.append(f'### id "{iid}"\nTITLE: {title}\nDESCRIPTION: {desc}\nOFFICIAL TEXT: {source}')
    return (
        "For each Swiss proposal below, explain what would concretely change if it is ACCEPTED, "
        "in 5 detail levels (1 = one brief plain sentence … 5 = full technical account) in each "
        "of en, de, fr, it, rm. Base it ONLY on that item's OFFICIAL TEXT; never invent figures, "
        "articles, dates or effects. Be strictly non-partisan; never say whether accepting is "
        "good or bad; no party positions. If an item's text is too thin, use "
        '{"insufficient_source": true} for that id.\n'
        'Output ONLY a JSON object mapping each id to {"lang": {"en":[l1..l5], "de":[...], '
        '"fr":[...], "it":[...], "rm":[...]}} (or {"insufficient_source": true}).\n\n'
        + "\n\n".join(blocks)
    )


def chunk(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ---------------------------------------------------------------- staging
def stage(task, kind, item_id, payload):
    payload.update({"task": task, "kind": kind, "id": item_id, "status": "pending",
                    "generatedAt": time.strftime("%Y-%m-%d %H:%M"), "via": "claude-cli"})
    path = os.path.join(QUEUE, task, kind, f"{item_id}.json")
    write_json_atomic(path, payload)  # temp+rename: only a complete file ever appears
    return os.path.relpath(path, ROOT)


def count_staged():
    n = 0
    for _b, _d, files in os.walk(QUEUE):
        n += sum(1 for f in files if f.endswith(".json"))
    return n


# Running cost averages, so the review desk can predict how far your limit goes.
USAGE_FILE = os.path.join(ROOT, "review", "usage.json")


def record_usage(task, cost, tokens, items):
    try:
        u = json.load(open(USAGE_FILE, encoding="utf-8"))
    except Exception:
        u = {}
    t = u.setdefault(task, {"items": 0, "tokens": 0, "cost": 0.0, "calls": 0})
    t["items"] += items
    t["tokens"] += int(tokens or 0)
    t["cost"] += float(cost or 0.0)
    t["calls"] += 1
    u["updated"] = time.strftime("%Y-%m-%d %H:%M")
    write_json_atomic(USAGE_FILE, u)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["translation", "overview", "all"], default="all")
    ap.add_argument("--max", type=int, default=0,
                    help="max NEW items this run (0 = as many as your usage limit allows)")
    ap.add_argument("--dry-run", action="store_true", help="stage stubs without calling claude")
    args = ap.parse_args()

    tr_units = translation_tasks() if args.task in ("translation", "all") else []
    ov_units = overview_tasks() if args.task in ("overview", "all") else []
    total_pending = len(tr_units) + len(ov_units)

    staged_before = count_staged()
    if not total_pending:
        print(f"Nothing left to generate. {staged_before} proposal(s) already staged for your review.")
        print("Open the review desk: python3 scripts/review_server.py  →  http://127.0.0.1:8777")
        return

    print(f"Resuming: {total_pending} item(s) still to generate, {staged_before} already staged.")
    print(f"Model: {MODEL} · batching {TR_BATCH} titles / {OV_BATCH} overviews per Claude call "
          f"(fewer, cheaper calls). Stops cleanly on a usage limit; saves each item as it lands.\n")
    made = [0]
    remaining_cap = [args.max if args.max else 10**9]

    def budget():  # items we may still generate this run
        return remaining_cap[0] - made[0]

    # ---- translations (batched) ----
    stop = False
    for batch in chunk(tr_units, TR_BATCH):
        if stop or budget() <= 0:
            break
        batch = batch[:budget()]
        ids = ", ".join(b[1] for b in batch)
        print(f"[translation ×{len(batch)}] {ids[:80]}")
        text, status, raw, cost, tokens = run_claude(tr_batch_prompt(batch), args.dry_run)
        if handle_stop(status, raw):
            stop = True
            break
        try:
            obj = {b[1]: {lg: f"DRY RUN {lg}" for lg in b[4]} for b in batch} if args.dry_run else parse_json(text)
        except Exception as e:  # noqa: BLE001
            print(f"    ! could not parse this batch ({e}); skipping it."); continue
        staged_here = 0
        for _k, iid, official, cur, need in batch:
            got = obj.get(iid) or {}
            if not all(got.get(lg) for lg in need):
                print(f"    · {iid}: model omitted a language; left pending."); continue
            proposal = {lg: (cur.get(lg) or got.get(lg)) for lg in ("en", "rm")}
            stage("translation", _k, iid, {"official": official, "existing": cur, "proposal": proposal})
            made[0] += 1; staged_here += 1
        if not args.dry_run:
            record_usage("translation", cost, tokens, staged_here)
            print(f"    ≈ {tokens:,} tokens for {staged_here} item(s)")

    # ---- overviews (batched; source text fetched here, not by the model) ----
    for batch in chunk(ov_units, OV_BATCH):
        if stop or budget() <= 0:
            break
        batch = batch[:budget()]
        enriched = []
        for (_k, iid, title, desc, url) in batch:
            src = "__DRY__" if args.dry_run else fetch_source(url)
            if len(src) < 200 and not args.dry_run:
                print(f"    · overview {iid}: no official text to ground it; skipped."); continue
            enriched.append((_k, iid, title, desc, url, src))
        if not enriched:
            continue
        print(f"[overview ×{len(enriched)}] {', '.join(b[1] for b in enriched)[:80]}")
        text, status, raw, cost, tokens = run_claude(ov_batch_prompt(enriched), args.dry_run)
        if handle_stop(status, raw):
            stop = True
            break
        try:
            obj = {b[1]: {"lang": {lg: [f"DRY RUN {lg} L{i+1}" for i in range(LEVELS)] for lg in LANGS}} for b in enriched} if args.dry_run else parse_json(text)
        except Exception as e:  # noqa: BLE001
            print(f"    ! could not parse this batch ({e}); skipping it."); continue
        staged_here = 0
        for (_k, iid, title, desc, url, _src) in enriched:
            data = obj.get(iid) or {}
            if data.get("insufficient_source"):
                print(f"    · overview {iid}: model reported insufficient source; skipped."); continue
            try:
                for lg in LANGS:
                    assert isinstance(data["lang"][lg], list) and len(data["lang"][lg]) == LEVELS
            except Exception:
                print(f"    · overview {iid}: incomplete result; left pending."); continue
            stage("overview", _k, iid, {"title": title, "sourceUrl": url, "proposal": {"lang": data["lang"]}})
            made[0] += 1; staged_here += 1
        if not args.dry_run:
            record_usage("overview", cost, tokens, staged_here)
            print(f"    ≈ {tokens:,} tokens for {staged_here} item(s)")

    total_staged = count_staged()
    print(f"\nDone this run: {made[0]} new proposal(s) generated.")
    print(f"{total_staged} awaiting your review; {total_pending - made[0]} still to generate next time.")
    print("Review them: python3 scripts/review_server.py  →  http://127.0.0.1:8777")


if __name__ == "__main__":
    main()
