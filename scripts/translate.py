#!/usr/bin/env python3
"""Machine-translate official DE/FR/IT texts into English via DeepL (build-time).

Fills the English gaps the site otherwise shows in a fallback language:
  * session (parliamentary) vote titles — Swiss acts have no official EN title;
  * the Federal Council for/against arguments (data/overviews/initiative/*.json);
  * the session "what this vote is about" summaries (data/sessions/*.json).

English only. DeepL has no Romansh, so RM keeps its official DE/FR/IT fallback
with a language chip — nothing here touches RM.

These are DEDICATED machine translations from DeepL, a purpose-built translation
engine — NOT LLM-generated content. Every one is shown on the site with a
"machine translation" badge and a link to the official source (see NOTICE.md /
COMPLIANCE.md). The live site never calls an API; it just reads data/mt.json.

Needs the DEEPL_API_KEY environment variable (a GitHub Actions secret in CI).
Without it the script no-ops and the site keeps its official-language fallback.
Incremental: a text is re-translated only when its source text changes (tracked
by a short content hash), so repeated runs cost almost nothing.

Usage: python3 scripts/translate.py [--force] [--limit N]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MT_PATH = DATA / "mt.json"
OVERVIEWS = DATA / "overviews" / "initiative"
SESSIONS = DATA / "sessions"

TARGET = "EN-GB"            # site English leans European/British (en-CH locale)
SRC_LANGS = ("DE", "FR", "IT")   # official Swiss languages we translate FROM
BATCH = 40                 # texts per DeepL request (also bounded by 128 KiB)


def api_key():
    return (os.environ.get("DEEPL_API_KEY") or "").strip()


def endpoint(key):
    # Free API keys end in ":fx"; everything else is the Pro endpoint.
    return ("https://api-free.deepl.com/v2/translate" if key.endswith(":fx")
            else "https://api.deepl.com/v2/translate")


def deepl(texts, src, key, retries=5):
    """Translate a list of texts DE/FR/IT -> English. Returns list, same order."""
    if not texts:
        return []
    body = json.dumps({
        "text": texts,
        "source_lang": src,
        "target_lang": TARGET,
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
        except Exception as e:  # noqa: BLE001 — transient / rate-limit (429)
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

    # 2) Federal Council for/against arguments (DE/FR present; EN falls back)
    for f in sorted(OVERVIEWS.glob("*.json")):
        data = json.loads(f.read_text("utf-8"))
        lang = data.get("lang") or {}
        if lang.get("en"):
            continue
        src = pick_src(lang)
        if not src:
            continue
        block = lang[src.lower()]
        pros, cons = block.get("pros") or [], block.get("cons") or []
        src_join = "\n".join(pros) + "␟" + "\n".join(cons)  # hash both sides
        iid = f.stem
        if pros or cons:
            if not cached_ok("args", iid, src_join):
                jobs.append({"store": "args", "id": iid, "src": src,
                             "texts": pros + cons, "shape": "args",
                             "np": len(pros), "hkey": src_join})
    return jobs, keep


def run(jobs, keep, key, limit=0):
    out = {k: dict(v) for k, v in keep.items()}
    # Batch by source language to keep each DeepL request single-source.
    by_src = {}
    for j in jobs:
        by_src.setdefault(j["src"], []).append(j)
    done = 0
    for src, group in by_src.items():
        # Flatten every text in this source group, remember where each came from.
        flat, owners = [], []
        for j in group:
            for t in j["texts"]:
                flat.append(t)
                owners.append(j)
        translated = {}
        for i in range(0, len(flat), BATCH):
            chunk = flat[i:i + BATCH]
            res = deepl(chunk, src, key)
            if len(res) != len(chunk):
                print(f"  ! DeepL returned {len(res)}/{len(chunk)} for {src}; "
                      f"skipping this batch", file=sys.stderr)
                continue
            for owner, text in zip(owners[i:i + BATCH], res):
                translated.setdefault(id(owner), []).append(text)
        # Reassemble per job.
        for j in group:
            texts = translated.get(id(j))
            if not texts:
                continue
            if j["shape"] == "text":
                entry = {"t": texts[0], "src": j["src"].lower(),
                         "h": h(j["texts"][0])}
            else:  # args
                np = j["np"]
                entry = {"pros": texts[:np], "cons": texts[np:],
                         "src": j["src"].lower(), "h": h(j["hkey"])}
            out[j["store"]][str(j["id"])] = entry
            done += 1
            if limit and done >= limit:
                return out, done
    return out, done


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
        out, done = run(jobs, keep, key, limit)
    except Exception as e:  # noqa: BLE001 — never break CI on a flaky API
        print(f"  ! DeepL request failed ({e}); leaving data/mt.json unchanged.",
              file=sys.stderr)
        return 0
    _write(out)
    print(f"Done. translated {done} item(s) -> data/mt.json")
    return 0


def _write(stores):
    doc = {
        "_meta": {
            "engine": "DeepL",
            "target": "EN-GB",
            "generatedAt": date.today().isoformat(),
            "note": "Unofficial machine translations (English) of official "
                    "DE/FR/IT texts, by DeepL. Shown with a machine-translation "
                    "badge and a link to the official source.",
        },
        "titles": stores.get("titles", {}),
        "args": stores.get("args", {}),
        "summaries": stores.get("summaries", {}),
    }
    MT_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
