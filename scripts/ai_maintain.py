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
# Overviews: one per call by default. Each overview is 5 levels × 5 languages (25
# text blocks) — batching several made a single reply so large the model TRUNCATED
# it (invalid JSON → nothing validated). One per call keeps the reply complete.
OV_BATCH = int(os.environ.get("POLITIKCH_OV_BATCH", "1"))
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


def parse_batch(text):
    """Parse a batch reply into ONE {id: value} dict, tolerating: markdown fences,
    leading/trailing prose, a JSON array, and — the common Haiku habit — several
    separate JSON objects (one per id) concatenated. Everything dict-shaped is
    merged, so partial/odd formatting still yields whatever ids parsed cleanly."""
    if not text:
        return {}
    s = re.sub(r"```(?:json)?", "", text).strip()
    dec = json.JSONDecoder()
    merged, i, n = {}, 0, len(s)
    while i < n:
        while i < n and s[i] not in "{[":
            i += 1
        if i >= n:
            break
        try:
            obj, end = dec.raw_decode(s, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            merged.update(obj)
        elif isinstance(obj, list):
            for el in obj:
                if isinstance(el, dict):
                    merged.update(el)
        i = end
    return merged


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


# ---- Swissvotes → parliamentary business number, for grounding INITIATIVE
# overviews. A federal vote has no per-item official text in our data, but the
# Swissvotes dataset maps each vote (by date + title) to its Geschäftsnummer
# (gesch_nr, e.g. "24.092"), which is the parliament.ch OData Business id
# (2000+YY)*10000+NNNN — so we reuse the same real official text as session votes.
SWISSVOTES_CSV = "https://swissvotes.ch/page/dataset/swissvotes_dataset.csv"
_sv_index = None


def _toks(s):
    return set(w for w in re.findall(r"[a-zäöüéèà]+", (s or "").lower()) if len(w) > 3)


def _gesch_to_business_id(g):
    m = re.match(r"(\d{2})\.(\d+)", (g or "").strip())
    return (2000 + int(m.group(1))) * 10000 + int(m.group(2)) if m else None


def swissvotes_index():
    """[{date:'YYYY-MM-DD', tokens:set, bid:int}] from the Swissvotes CSV, cached
    per process. [] on failure → initiative overviews just skip (never fabricate)."""
    global _sv_index
    if _sv_index is not None:
        return _sv_index
    _sv_index = []
    try:
        import csv, io, urllib.request
        raw = urllib.request.urlopen(urllib.request.Request(
            SWISSVOTES_CSV, headers={"User-Agent": "PolitikchBot/1.0"}), timeout=90).read().decode("utf-8", "replace")
        for r in csv.DictReader(io.StringIO(raw), delimiter=";"):
            m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", (r.get("datum") or "").strip())
            bid = _gesch_to_business_id(r.get("gesch_nr"))
            if not m or not bid:
                continue
            _sv_index.append({"date": f"{m.group(3)}-{m.group(2)}-{m.group(1)}",
                              "tokens": _toks(r.get("titel_off_d") or r.get("titel_kurz_d")),
                              "bid": bid})
    except Exception as e:  # noqa: BLE001
        print(f"    · Swissvotes lookup unavailable ({e}); initiative overviews skipped.", file=sys.stderr)
    return _sv_index


def initiative_business_id(vote_date_iso, title):
    """Match an initiative to its parliamentary business id via Swissvotes
    (same date + best title-token overlap). None if no confident match."""
    if not vote_date_iso:
        return None
    want = _toks(title)
    best = (1, None)  # require overlap >= 2 to avoid a wrong match
    for row in swissvotes_index():
        if row["date"] != vote_date_iso:
            continue
        ov = len(want & row["tokens"])
        if ov > best[0]:
            best = (ov, row["bid"])
    return best[1]


def overview_tasks():
    tasks = []
    for it in load_initiatives():
        iid = it["id"]
        if os.path.exists(os.path.join(ROOT, "data/overviews/initiative", f"{iid}.json")):
            continue
        if queued("overview", "initiative", iid):
            continue
        bid = initiative_business_id(it.get("voteDate"), localized(it.get("title")))
        if not bid:
            continue  # no groundable official text (unmatched) — skip, don't fabricate
        url = f"https://www.parlament.ch/de/ratsbetrieb/suche-curia-vista/geschaeft?AffairId={bid}"
        tasks.append(("initiative", iid, localized(it.get("title")), localized(it.get("desc")), url, bid))
    for v in load_session_votes():
        vid = str(v["id"])
        if os.path.exists(os.path.join(ROOT, "data/overviews/session", f"{vid}.json")):
            continue
        if queued("overview", "session", vid):
            continue
        bn = v.get("businessNumber")
        url = (f"https://www.parlament.ch/de/ratsbetrieb/suche-curia-vista/geschaeft?AffairId={bn}" if bn else None)
        tasks.append(("session", vid, localized(v.get("title")), "", url, bn))
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
PARL_ODATA = "https://ws.parlament.ch/odata.svc"


def strip_html(raw):
    raw = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))).strip()


def fetch_business_text(business_number):
    """Real per-item official text for a Federal Assembly business, from the
    parlament.ch OData API (not the JS page). Returns the substantive fields —
    the submitted legal text, the initial situation, and the reasoning — which are
    official texts (not copyright, Art. 5 URG). '' on failure → item skipped."""
    if not business_number:
        return ""
    url = f"{PARL_ODATA}/Business?$filter=ID%20eq%20{business_number}&$format=json&$top=1"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "PolitikchBot/1.0", "Accept": "application/json", "Accept-Language": "DE"})
        with urllib.request.urlopen(req, timeout=40) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        node = d.get("d", d) if isinstance(d, dict) else d
        if isinstance(node, dict) and "results" in node:
            node = node["results"]
        b = node[0] if isinstance(node, list) and node else (node if isinstance(node, dict) else {})
        parts = []
        for f in ("Title", "SubmittedText", "InitialSituation", "ReasonText", "Description"):
            v = b.get(f)
            if isinstance(v, str) and v.strip():
                parts.append(f"{f}: {strip_html(v)}")
        return "\n\n".join(parts)[:8000]
    except Exception:
        return ""


def fetch_source(url):
    """Best-effort fetch of an official page's visible text (fallback, e.g. for
    initiatives if a source is ever wired). '' on failure → item skipped."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PolitikchBot/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read(500_000).decode("utf-8", "replace")
        return strip_html(raw)[:6000]
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
        "in exactly 5 detail levels, in each of en, de, fr, it, rm. Base it ONLY on that item's "
        "OFFICIAL TEXT; never invent figures, articles, dates or effects. Be strictly "
        "non-partisan; never say whether accepting is good or bad; no party positions.\n"
        "KEEP IT SHORT so the reply is complete: level 1 = one sentence; level 2 ≤ 30 words; "
        "level 3 ≤ 60 words; level 4 ≤ 100 words; level 5 ≤ 150 words. Plain sentences, no "
        "markdown. If an item's text is too thin, use {\"insufficient_source\": true} for it.\n"
        'Output ONLY minified JSON mapping each id to {"lang": {"en":[l1,l2,l3,l4,l5], "de":[…], '
        '"fr":[…], "it":[…], "rm":[…]}} (or {"insufficient_source": true}). No prose, no code fences.\n\n'
        + "\n\n".join(blocks)
    )


def normalize_overview(data):
    """Coerce a model reply for one item into {"lang": {lg: [5 strings]}} or None.
    Tolerates: a missing "lang" wrapper, levels given as a dict ({"1":…}) instead
    of a list, and >5 levels (trimmed). Returns None if any language is missing or
    has fewer than 5 non-empty levels (treated as incomplete → left pending)."""
    if not isinstance(data, dict):
        return None
    lang = data.get("lang")
    if not isinstance(lang, dict):
        lang = data if any(k in data for k in LANGS) else None
    if not isinstance(lang, dict):
        return None
    out = {}
    for lg in LANGS:
        v = lang.get(lg)
        if isinstance(v, dict):
            v = [v[k] for k in sorted(v, key=lambda x: str(x))]
        if not isinstance(v, list):
            return None
        v = [str(x).strip() for x in v if str(x).strip()]
        if len(v) < LEVELS:
            return None
        out[lg] = v[:LEVELS]
    return {"lang": out}


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
            obj = {b[1]: {lg: f"DRY RUN {lg}" for lg in b[4]} for b in batch} if args.dry_run else parse_batch(text)
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
        for (_k, iid, title, desc, url, bn) in batch:
            if args.dry_run:
                src = "__DRY__"
            else:
                src = fetch_business_text(bn) if bn else fetch_source(url)
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
            obj = {b[1]: {"lang": {lg: [f"DRY RUN {lg} L{i+1}" for i in range(LEVELS)] for lg in LANGS}} for b in enriched} if args.dry_run else parse_batch(text)
        except Exception as e:  # noqa: BLE001
            print(f"    ! could not parse this batch ({e}); skipping it."); continue
        staged_here = 0
        for (_k, iid, title, desc, url, _src) in enriched:
            data = obj.get(iid) or {}
            if isinstance(data, dict) and data.get("insufficient_source"):
                print(f"    · overview {iid}: model reported insufficient source; skipped."); continue
            norm = normalize_overview(data)
            if not norm:
                # Save the raw reply so an odd/truncated shape can be diagnosed.
                dbg = os.path.join(ROOT, "review", "debug", f"overview-{iid}.txt")
                try:
                    os.makedirs(os.path.dirname(dbg), exist_ok=True)
                    open(dbg, "w", encoding="utf-8").write((text or "")[:20000])
                except Exception:
                    pass
                print(f"    · overview {iid}: incomplete result; left pending. (raw saved to review/debug/)")
                continue
            data = norm
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
