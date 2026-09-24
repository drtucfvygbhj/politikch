#!/usr/bin/env python3
"""Machine-translate official DE/FR/IT texts via DeepL (build-time).

Fills the gaps the site otherwise shows in a fallback language:
  * session (parliamentary) vote titles -> English (acts have no official EN title);
  * the session "what this vote is about" summaries -> English;
  * the for/against arguments (data/overviews/initiative/*.json) -> English AND
    Italian. The brochure is fetched automatically only in DE/FR (Swissvotes has
    no IT), so Italian readers would otherwise get German or French. An official
    Italian brochure, once added, always takes precedence over the machine one.

Both sides of a vote are translated as ONE item and stored only if every
paragraph of both came back, so one side can never appear translated alone
(GUARDRAILS.md POL-01). DeepL has no Romansh, so RM keeps its official DE/FR/IT
fallback with a language chip — nothing here touches RM.

These are DEDICATED machine translations from DeepL, a purpose-built translation
engine — NOT LLM-generated content. Every one is shown on the site with a
"machine translation" badge and a link to the official source (see NOTICE.md /
COMPLIANCE.md). The live site never calls an API; it just reads data/mt.json.

Needs the DEEPL_API_KEY environment variable (a GitHub Actions secret in CI).
Without it the script no-ops and the site keeps its official-language fallback.
Incremental: a text is re-translated only when its source text changes (tracked
by a short content hash), so repeated runs cost almost nothing.

=====================================================================
CHARGE SAFETY — this pipeline is designed so DeepL can NEVER bill you
=====================================================================
Four independent layers, strongest first:

  0. ACCOUNT (the real guarantee): use a DeepL free API key on an account with
     **NO payment method / no paid plan**. A free account has nothing to bill —
     when its character allowance is used up DeepL returns HTTP 456 and simply
     stops translating. This holds even if every other layer below is deleted by
     someone with repo access, because there is no card to charge. THIS is what
     makes overruns impossible; the rest is defence-in-depth.
     NOTE: DeepL's free allowance for new "Developer" accounts is 1,000,000
     characters ONE-TIME (not monthly); legacy "API Free" (:fx) accounts get
     500,000/month recurring. This script reads the real remaining quota from
     DeepL's /v2/usage, so it works either way. Our volume (~0.21M once, then
     ~0.15M/yr incl. Italian arguments) leaves the one-time million lasting about
     5 years; when it's
     exhausted the site simply falls back to the official language.
  1. KEY CHECK: the script REFUSES to run with a non-free key (one that could be
     billed) unless DEEPL_ALLOW_PAID=1 is set deliberately.
  2. SERVER QUOTA CHECK: before translating it reads DeepL's /v2/usage and will
     not send past (monthly limit − safety margin). Aligned to DeepL's own reset.
  3. PER-RUN CAP + graceful partial: a single run sends at most DEEPL_RUN_CAP
     characters, translates whole items only while they fit, and STOPS when the
     budget is reached — untranslated items just fall back on the site and are
     picked up next run / next month. Nothing is ever forced through.

Tunable via env (safe defaults): DEEPL_SAFETY_MARGIN, DEEPL_RUN_CAP,
DEEPL_ALLOW_PAID.

Usage: python3 scripts/translate.py [--force] [--limit N]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from licences import licence_meta  # the file's licence (scripts/licences.py)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MT_PATH = DATA / "mt.json"
OVERVIEWS = DATA / "overviews" / "initiative"
SESSIONS = DATA / "sessions"

TARGET = "EN-GB"            # site English leans European/British (en-CH locale)
# The for/against arguments get every language they lack officially that DeepL
# offers: site language code -> DeepL target code.
ARG_TARGETS = {"en": "EN-GB", "it": "IT"}
SRC_LANGS = ("DE", "FR", "IT")   # official Swiss languages we translate FROM
BATCH = 40                 # texts per DeepL request (also bounded by 128 KiB)

# --- Charge-safety knobs (see the module docstring). Safe defaults. ---
FREE_TIER_CHARS = 500_000
# Never spend the last N characters of the monthly free allowance (headroom for
# any usage this pipeline can't see, e.g. a manual test on the same key).
SAFETY_MARGIN = max(0, int(os.environ.get("DEEPL_SAFETY_MARGIN", "50000")))
# Hard ceiling on how many characters ANY single run may send.
RUN_CAP = max(0, int(os.environ.get("DEEPL_RUN_CAP", "120000")))
# Deliberate opt-in to a billable (non ":fx") key. Off by default.
ALLOW_PAID = os.environ.get("DEEPL_ALLOW_PAID", "") == "1"


class QuotaExceeded(Exception):
    """DeepL reported the monthly quota is exhausted (HTTP 456)."""


def api_key():
    return (os.environ.get("DEEPL_API_KEY") or "").strip()


def is_free_key(key):
    return key.endswith(":fx")


def _host(key):
    return "api-free" if is_free_key(key) else "api"


def endpoint(key):
    return f"https://{_host(key)}.deepl.com/v2/translate"


def deepl_usage(key):
    """Return (used, limit) characters for the current billing period, or
    (None, None) if the usage endpoint can't be read."""
    url = f"https://{_host(key)}.deepl.com/v2/usage"
    req = urllib.request.Request(
        url, headers={"Authorization": f"DeepL-Auth-Key {key}",
                      "User-Agent": "politikch-mt"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        return int(d.get("character_count", 0)), int(d.get("character_limit", 0))
    except Exception:  # noqa: BLE001
        return None, None


def deepl(texts, src, key, target=TARGET, retries=5):
    """Translate a list of texts from `src` into `target`. Returns list, same order."""
    if not texts:
        return []
    body = json.dumps({
        "text": texts,
        "source_lang": src,
        "target_lang": target,
        "preserve_formatting": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        endpoint(key), data=body, method="POST",
        headers={"Authorization": f"DeepL-Auth-Key {key}",
                 "Content-Type": "application/json", "User-Agent": "politikch-mt"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                out = json.loads(resp.read().decode("utf-8"))
            return [t["text"] for t in out.get("translations", [])]
        except urllib.error.HTTPError as e:
            # 456 = quota exhausted: stop immediately (retrying can't help, and a
            # free key is billed nothing — it just refuses). 429 = rate limit: back off.
            if e.code == 456:
                raise QuotaExceeded()
            last = e
            time.sleep(2.0 * (attempt + 1))
        except Exception as e:  # noqa: BLE001 — transient network/proxy errors
            last = e
            time.sleep(2.0 * (attempt + 1))
    raise last


def h(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def pick_src(langs):
    """Prefer German, then French, then Italian, as the translation source."""
    for code in SRC_LANGS:
        if langs.get(code.lower()):
            return code
    return None


# ---------------------------------------------------------------------------
# Collect the texts that need an English machine translation
# ---------------------------------------------------------------------------
def collect(existing):
    """Yield work items and note which cached entries are still valid.

    Returns (jobs, keep). jobs = list of dicts {store, id, field, src, texts,
    shape}. keep = {store: {id: entry}} for cache hits that stay unchanged.
    """
    jobs, keep = [], {"titles": {}, "args": {}, "summaries": {}}

    def cached_ok(store, iid, src_text):
        e = (existing.get(store) or {}).get(str(iid))
        if e and e.get("h") == h(src_text):
            keep[store][str(iid)] = e
            return True
        return False

    def cached_arg_ok(iid, tl, src_text):
        e = ((existing.get("args") or {}).get(str(iid)) or {}).get(tl)
        if e and e.get("h") == h(src_text):
            keep["args"].setdefault(str(iid), {})[tl] = e
            return True
        return False

    # 1) Session vote titles (title.{de,fr,it}; no official EN) + summaries
    for f in sorted(SESSIONS.glob("*.json")):
        data = json.loads(f.read_text("utf-8"))
        votes = data.get("votes") if isinstance(data, dict) else data
        for v in (votes or []):
            title = v.get("title") or {}
            src = pick_src(title)
            if src and not title.get("en"):
                st = title[src.lower()]
                if st and not cached_ok("titles", v["id"], st):
                    jobs.append({"store": "titles", "id": v["id"], "src": src,
                                 "texts": [st], "shape": "text"})
            summ = v.get("summary") or {}
            ssrc = pick_src(summ)
            if ssrc and not summ.get("en"):
                stext = summ[ssrc.lower()]
                if stext and not cached_ok("summaries", v["id"], stext):
                    jobs.append({"store": "summaries", "id": v["id"], "src": ssrc,
                                 "texts": [stext], "shape": "text"})

    # 2) For/against arguments (official DE/FR; EN and IT fall back otherwise).
    #    One job per missing language, carrying BOTH sides together.
    for f in sorted(OVERVIEWS.glob("*.json")):
        data = json.loads(f.read_text("utf-8"))
        lang = data.get("lang") or {}
        src = pick_src(lang)
        if not src:
            continue
        block = lang[src.lower()]
        pros, cons = block.get("pros") or [], block.get("cons") or []
        if not (pros and cons):
            continue  # never translate one side on its own
        src_join = "\n".join(pros) + "␟" + "\n".join(cons)  # hash both sides
        iid = f.stem
        for tl, target in ARG_TARGETS.items():
            if lang.get(tl) or tl == src.lower():
                continue  # an official text in that language exists
            if not cached_arg_ok(iid, tl, src_join):
                jobs.append({"store": "args", "id": iid, "src": src, "tl": tl,
                             "target": target, "texts": pros + cons,
                             "shape": "args", "np": len(pros), "hkey": src_join})
    return jobs, keep


def run(jobs, keep, key, budget, limit=0):
    """Translate within a hard character `budget`. Sends at most `budget`
    characters this run; stops the moment the next text wouldn't fit, leaving
    the rest for a later run. Only WHOLE items (all their texts translated) are
    stored, so nothing is written half-translated. Returns (out, done, sent)."""
    out = {k: dict(v) for k, v in keep.items()}
    out["args"] = {iid: dict(v) for iid, v in keep.get("args", {}).items()}
    by_pair = {}
    for j in jobs:
        by_pair.setdefault((j["src"], j.get("target", TARGET)), []).append(j)
    done = sent = 0
    stop = False
    for (src, target), group in by_pair.items():
        if stop:
            break
        flat, owners = [], []
        for j in group:
            for t in j["texts"]:
                flat.append(t)
                owners.append(j)
        translated = {}
        i = 0
        while i < len(flat) and not stop:
            # Fill a batch bounded by BATCH count AND the remaining budget.
            batch, batch_owners, blen = [], [], 0
            while i < len(flat) and len(batch) < BATCH:
                tl = len(flat[i])
                if sent + blen + tl > budget:
                    stop = True          # budget reached — stop cleanly
                    break
                batch.append(flat[i])
                batch_owners.append(owners[i])
                blen += tl
                i += 1
            if not batch:
                break
            try:
                res = deepl(batch, src, key, target)
            except QuotaExceeded:
                print("  DeepL free allowance reached — stopping cleanly; the rest "
                      "stays on the official-language fallback.", file=sys.stderr)
                stop = True
                break
            if len(res) != len(batch):
                print(f"  ! DeepL returned {len(res)}/{len(batch)} for {src}; "
                      f"skipping this batch", file=sys.stderr)
                continue
            sent += blen
            for owner, text in zip(batch_owners, res):
                translated.setdefault(id(owner), []).append(text)
        # Store only items whose EVERY text came back (never a partial item).
        for j in group:
            texts = translated.get(id(j))
            if not texts or len(texts) != len(j["texts"]):
                continue
            if j["shape"] == "text":
                entry = {"t": texts[0], "src": j["src"].lower(),
                         "h": h(j["texts"][0])}
            else:  # args — both sides, nested per target language
                np = j["np"]
                entry = {"pros": texts[:np], "cons": texts[np:],
                         "src": j["src"].lower(), "h": h(j["hkey"])}
                out["args"].setdefault(str(j["id"]), {})[j["tl"]] = entry
                done += 1
                if limit and done >= limit:
                    return out, done, sent
                continue
            out[j["store"]][str(j["id"])] = entry
            done += 1
            if limit and done >= limit:
                return out, done, sent
    return out, done, sent


def main(argv):
    force = "--force" in argv
    limit = 0
    if "--limit" in argv:
        try:
            limit = int(argv[argv.index("--limit") + 1])
        except (ValueError, IndexError):
            limit = 0

    key = api_key()
    if not key:
        print("DEEPL_API_KEY not set — skipping machine translation "
              "(the site keeps its official-language fallback).", file=sys.stderr)
        return 0

    # LAYER 1 — refuse a key that could be billed. A free key ends ':fx' and
    # cannot incur charges. Overriding this is a deliberate, explicit act.
    if not is_free_key(key) and not ALLOW_PAID:
        print("REFUSING to run: DEEPL_API_KEY is not a Free API key (it must end "
              "':fx'). A free key cannot be charged; a paid one can. If you truly "
              "intend to allow billing, set DEEPL_ALLOW_PAID=1.", file=sys.stderr)
        return 0

    # LAYER 2 — read DeepL's authoritative monthly usage and leave a safety margin.
    used, cap_limit = deepl_usage(key)
    if cap_limit:
        remaining = max(0, cap_limit - used - SAFETY_MARGIN)
        budget = min(remaining, RUN_CAP)
        print(f"DeepL usage {used:,}/{cap_limit:,}; {remaining:,} usable after a "
              f"{SAFETY_MARGIN:,} margin; this run capped at {budget:,} chars.")
    else:
        # Usage unreadable. A free key still can't be charged (it 456s at the
        # limit), so proceed but only up to the per-run cap; a paid key we don't.
        budget = RUN_CAP if is_free_key(key) else 0
        print(f"DeepL usage unreadable; capping this run at {budget:,} chars "
              f"(free key can't be billed).", file=sys.stderr)
    if budget <= 0:
        print("Free allowance reached (or unverifiable) — translating nothing this "
              "run; texts stay on the official-language fallback.", file=sys.stderr)
        if not MT_PATH.exists():
            _write({"titles": {}, "args": {}, "summaries": {}})
        return 0

    existing = {}
    if MT_PATH.exists() and not force:
        try:
            existing = json.loads(MT_PATH.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            existing = {}

    jobs, keep = collect(existing)
    print(f"{sum(len(j['texts']) for j in jobs)} text(s) to translate across "
          f"{len(jobs)} item(s); {sum(len(v) for v in keep.values())} cached.")
    if not jobs:
        # Still (re)write so _meta/date stay current if the file is missing.
        if not MT_PATH.exists():
            _write({"titles": {}, "args": {}, "summaries": {}})
        return 0

    try:
        out, done, sent = run(jobs, keep, key, budget, limit)
    except Exception as e:  # noqa: BLE001 — never break CI on a flaky API
        print(f"  ! DeepL request failed ({e}); leaving data/mt.json unchanged.",
              file=sys.stderr)
        return 0
    _write(out)
    remaining_items = sum(len(j["texts"]) for j in jobs) and (
        len(jobs) - done)
    print(f"Done. translated {done} item(s) using ~{sent:,} chars -> data/mt.json"
          + (f"; {remaining_items} item(s) left for next run (budget reached)."
             if sent >= budget and remaining_items > 0 else "."))
    return 0


def _write(stores):
    doc = {
        "_meta": {
            **licence_meta("mt.json"),
            "engine": "DeepL",
            "target": "EN-GB (titles, summaries, arguments); IT (arguments)",
            "generatedAt": date.today().isoformat(),
            "note": "Unofficial machine translations of official DE/FR/IT texts, "
                    "by DeepL. titles/summaries: {id: English}; args: {id: {en|it: "
                    "{pros, cons}}}. Shown with a machine-translation badge and a "
                    "link to the official source.",
        },
        "titles": stores.get("titles", {}),
        "args": stores.get("args", {}),
        "summaries": stores.get("summaries", {}),
    }
    MT_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
