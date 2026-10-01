#!/usr/bin/env python3
"""Politikch admin — a local-only site for managing the main site.

Run:  python3 admin/server.py      (or double-click "Start Admin.command")
Open: http://127.0.0.1:8002

What it does
  * Design: switch the version every visitor gets (1.0 = original, 1.1 = news
    layout), fonts, sizes of the layout, "live" rules and rotation times.
    Written to js/site-settings.js.
  * Images: upload your own photos (resized and stripped of metadata in the
    browser), alt text in five languages, credit, licence; assign them to votes.
    Files go to images/, the licence record to images/LICENSES.json (LIC-01).
  * Vote links: which National Council final vote belongs to each proposal.
  * Edit text: click any text in the preview and change it in all five
    languages — interface text (data/i18n.json) and our own editorial texts
    (party, canton and donor descriptions, the legal pages). Official and
    fetched texts can't be edited here (SRC-08, OPS-04).
  * Edit positioning: click two blocks of the front page to swap them; the
    order is kept in js/site-settings.js.
  * Undo / redo for every change made here except adding or deleting a photo.
  * Status and checks: maintenance mode (read-only, SEC-10), data freshness,
    next ballot, sitting session, translations to do, changed files, and a
    button that runs scripts/check.py and scripts/validate.py.

Safety
  * Listens on 127.0.0.1 only and never contacts the internet.
  * Every request must carry the Host 127.0.0.1:8002 / localhost:8002 (stops DNS
    rebinding); every change needs the per-start token embedded in the page and a
    same-origin Origin header (stops other websites in your browser from posting
    here). Writes are limited to js/site-settings.js, images/, the text files
    listed in TEXT_FILES and admin/.backup/.
  * Photos: the browser redraws every photo into a new WebP (which drops all
    metadata); the server refuses a WebP that still carries EXIF, XMP or ICC
    data.
  * The preview (a separate port) gets a small helper script, admin/preview-agent.js,
    that reports clicks back to this page in the edit modes. It is served only by
    the preview and is never part of the site.
  * Three publish buttons, pressed by you: "Make changes live" commits only
    js/site-settings.js, "Publish images" only images/ + js/site-images.js,
    "Publish text" only the files in TEXT_FILES. Each
    builds the commit in a temporary clean worktree on origin/main, runs
    scripts/check.py there, takes your typed reason for every flagged rule
    (the Approved-Rule: lines) and your preview confirmation, then commits and
    pushes through the normal pre-push hook (never --no-verify). Everything else
    goes live only through your normal git flow.
  * The admin folder is not in the deploy allowlist, so it is never published.
Standard library only.
"""
import base64
import datetime as dt
import glob
import hashlib
import http.server
import json
import re
import secrets
import shutil
import subprocess
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
ADMIN = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("PCH_ADMIN_PORT", 8002))
PREVIEW_PORT = int(os.environ.get("PCH_PREVIEW_PORT", 8003))   # read-only copy of the site for the preview, never cached
TOKEN = secrets.token_urlsafe(32)
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ALLOWED_ORIGINS = {f"http://{h}" for h in ALLOWED_HOSTS}
PREVIEW_HOSTS = {f"127.0.0.1:{PREVIEW_PORT}", f"localhost:{PREVIEW_PORT}"}
# Only what the deploy allowlist publishes is served by the preview.
AGENT_PATH = "/__admin/preview-agent.js"   # served only by the preview port, never part of the site
PREVIEW_ALLOW = re.compile(r"^/(index\.html|404\.html|(css|js|fonts)/[\w.-]+|data/(?!brochures/)[\w./-]+\.json|images/[\w.-]+\.webp)$")

SETTINGS_JS = ROOT / "js" / "site-settings.js"
IMAGES_JS = ROOT / "js" / "site-images.js"
IMAGES = ROOT / "images"
REGISTER = IMAGES / "LICENSES.json"
BACKUPS = ADMIN / ".backup"
MAX_BODY = 12 * 1024 * 1024
LANGS = ["en", "de", "fr", "it", "rm"]

FONTS = {"playfair": "Playfair Display (the 1.0 logo font)", "dmsans": "DM Sans",
         "serif": "System serif (Charter / Georgia)", "sans": "System sans-serif"}
LIMITS = {"left": (0.5, 3), "centre": (1, 4), "right": (0.5, 3), "gutter": (8, 40), "sectionGap": (8, 80),
          "maxWidth": (960, 1800), "rule": (1, 4), "baseSize": (13, 18),
          "mastPad": (4, 60), "titleSize": (32, 110), "titleScaleX": (70, 140), "titleScaleY": (70, 160)}
DEFAULT_SETTINGS = {
    "version": 1, "design": "1.1",
    "fonts": {"headline": "playfair", "body": "dmsans"},
    "layout": {"left": 1, "centre": 2, "right": 1, "gutter": 26, "sectionGap": 32, "maxWidth": 1320, "rule": 2, "baseSize": 15,
               "mastPad": 18, "titleSize": 58, "titleScaleX": 100, "titleScaleY": 100},
    "live": {"ballotDays": 28, "deadlineDays": 7},
    "rotation": {"canton": 9, "explainer": 12},
    "parliamentLinks": {},
    "decreeDirections": {},
}
IMAGES_HEADER = ("/* Politikch photos — written by the local admin tool (admin/, localhost:8002).\n"
                 "   Which photo goes with which vote, with alt text in five languages and a credit.\n"
                 "   Published separately from the design settings (\"Publish images\" in the admin);\n"
                 "   every file listed here must have a licence record in images/LICENSES.json (LIC-01). */\n")
# Texts the admin may edit: the interface text and our own editorial files.
# Official or fetched texts (titles, arguments, results, session data) are not
# here: they must stay verbatim (SRC-08) and the data job would overwrite them.
TEXT_FILES = ["data/i18n.json", "data/parties.json", "data/cantons.json", "data/donor-descriptions.json", "data/legal.json"]
PUBLISH = {
    "settings": {"paths": ["js/site-settings.js"], "title": "Admin: make design settings live"},
    "images": {"paths": ["js/site-images.js", "images"], "title": "Admin: publish images"},
    "text": {"paths": TEXT_FILES, "title": "Admin: publish text edits"},
}
HISTORY = BACKUPS / "history.json"
HEADER = ("/* Politikch site settings — written by the local admin tool (admin/, localhost:8002).\n"
          "   Change these there, not by hand: the tool validates every value. Applies to every\n"
          "   visitor; there is no per-visitor choice. Read by js/design.js and js/news.js. */\n")


class BadRequest(Exception):
    pass


# ---------------------------------------------------------------- data access
def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return default


def read_settings():
    try:
        text = SETTINGS_JS.read_text("utf-8")
        m = re.search(r"window\.PCH_SETTINGS\s*=\s*(\{.*\})\s*;\s*$", text, re.S)
        return json.loads(m.group(1)) if m else json.loads(json.dumps(DEFAULT_SETTINGS))
    except (OSError, ValueError, AttributeError):
        return json.loads(json.dumps(DEFAULT_SETTINGS))


def write_settings(s):
    BACKUPS.mkdir(exist_ok=True)
    if SETTINGS_JS.exists():
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(SETTINGS_JS, BACKUPS / f"site-settings-{stamp}.js")
        old = sorted(BACKUPS.glob("site-settings-*.js"))
        for f in old[:-30]:                       # keep the last 30 versions
            f.unlink()
    SETTINGS_JS.write_text(HEADER + "window.PCH_SETTINGS = " + json.dumps(s, indent=2, ensure_ascii=False) + ";\n", "utf-8")


def initiatives():
    return (load_json(ROOT / "data" / "initiatives.json", {}) or {}).get("initiatives", [])


def session_file(sid):
    return load_json(ROOT / "data" / "sessions" / f"{int(sid)}.json", None)


# ---------------------------------------------------------------- validation
def num(v, lo, hi, name, integer=False):
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise BadRequest(f"{name}: not a number")
    if not (lo <= x <= hi):
        raise BadRequest(f"{name}: must be between {lo} and {hi}")
    return int(round(x)) if integer else round(x, 2)


def clean_settings(body):
    cur = read_settings()
    ids = {i["id"] for i in initiatives()}
    out = {"version": 1}
    design = body.get("design")
    if design not in ("1.0", "1.1"):
        raise BadRequest("design must be 1.0 or 1.1")
    out["design"] = design
    f = body.get("fonts") or {}
    if f.get("headline") not in FONTS or f.get("body") not in FONTS:
        raise BadRequest("unknown font")
    out["fonts"] = {"headline": f["headline"], "body": f["body"]}
    lay = body.get("layout") or {}
    out["layout"] = {k: num(lay.get(k, DEFAULT_SETTINGS["layout"][k]), lo, hi, k, integer=k not in ("left", "centre", "right"))
                     for k, (lo, hi) in LIMITS.items()}
    if out["layout"]["centre"] < max(out["layout"]["left"], out["layout"]["right"]):
        raise BadRequest("the centre column must stay at least as wide as each side column")
    live = body.get("live") or {}
    out["live"] = {"ballotDays": num(live.get("ballotDays"), 0, 90, "ballotDays", True),
                   "deadlineDays": num(live.get("deadlineDays"), 0, 60, "deadlineDays", True)}
    rot = body.get("rotation") or {}
    out["rotation"] = {"canton": num(rot.get("canton"), 4, 60, "canton", True),
                       "explainer": num(rot.get("explainer"), 4, 60, "explainer", True)}
    links = {}
    for vid, link in (body.get("parliamentLinks") or {}).items():
        if vid not in ids:
            raise BadRequest(f"unknown vote {vid}")
        if not link:
            continue
        sid, vote = int(link.get("session", 0)), int(link.get("vote", 0))
        sf = session_file(sid)
        if not sf or not any(v.get("id") == vote for v in sf.get("votes", [])):
            raise BadRequest(f"final vote {vote} not found in session {sid}")
        links[vid] = {"session": sid, "vote": vote}
    out["parliamentLinks"] = links
    # Which way a decree on a popular initiative recommends, set by the owner
    # only where the official wording leaves it open (POL-03: checked against the
    # decree itself). The data's own direction always wins, so an entry the data
    # has since settled is dropped rather than refused.
    open_ids = {str(d["vote"]) for d in open_decrees()}
    all_ids = {str(v.get("id")) for sf in session_files() for v in sf.get("votes", [])}
    dirs = {}
    for vid, rec in (body.get("decreeDirections") or {}).items():
        if not rec:
            continue
        if rec not in ("reject", "accept"):
            raise BadRequest(f"decree {vid}: direction must be reject or accept")
        if str(vid) not in all_ids:
            raise BadRequest(f"final vote {vid} not found in the session data")
        if str(vid) in open_ids:
            dirs[str(vid)] = rec
    out["decreeDirections"] = dirs
    pos = body.get("positions")
    if pos:
        if not isinstance(pos, dict):
            raise BadRequest("positions: expected columns")
        seen, out["positions"] = set(), {}
        for col in ("l", "c", "r"):
            ids = pos.get(col) or []
            if not isinstance(ids, list) or len(ids) > 80:
                raise BadRequest("positions: at most 80 blocks per column")
            for i in ids:
                if not isinstance(i, str) or not re.fullmatch(r"[a-z]+(:[\w.-]{1,60})?", i) or i in seen:
                    raise BadRequest(f"positions: bad block id {i!r}")
                seen.add(i)
            out["positions"][col] = ids
    return out


def read_images():
    try:
        m = re.search(r"window\.PCH_IMAGES\s*=\s*(\{.*\})\s*;\s*$", IMAGES_JS.read_text("utf-8"), re.S)
        d = json.loads(m.group(1)) if m else {}
    except (OSError, ValueError, AttributeError):
        d = {}
    return {"library": d.get("library", {}), "assign": d.get("assign", {})}


def write_images(d):
    IMAGES_JS.write_text(IMAGES_HEADER + "window.PCH_IMAGES = " + json.dumps(d, indent=2, ensure_ascii=False) + ";\n", "utf-8")


def assign_images(body):
    ids = {i["id"] for i in initiatives()}
    d = read_images()
    assign = {}
    for vid, img in (body.get("assign") or {}).items():
        if vid not in ids:
            raise BadRequest(f"unknown vote {vid}")
        if img:
            if img not in d["library"]:
                raise BadRequest(f"unknown image {img}")
            assign[vid] = img
    d["assign"] = assign
    write_images(d)


# ---------------------------------------------------------------- images
def data_url_webp(s, cap, name):
    m = re.fullmatch(r"data:image/webp;base64,([A-Za-z0-9+/=]+)", s or "")
    if not m:
        raise BadRequest(f"{name}: expected a WebP image")
    raw = base64.b64decode(m.group(1))
    if len(raw) > cap:
        raise BadRequest(f"{name}: too large ({len(raw) // 1024} KB, limit {cap // 1024} KB)")
    if not (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"):
        raise BadRequest(f"{name}: not a WebP file")
    meta = webp_metadata(raw)
    if meta:
        raise BadRequest(f"{name}: the file still carries {', '.join(meta)} — it was not redrawn in the browser; add it again")
    return raw


def webp_metadata(raw):
    """Metadata a WebP carries: EXIF / XMP / ICC chunks, or the VP8X flags for them.
    A photo redrawn on a canvas has none; anything found means it wasn't."""
    found = []
    i = 12
    while i + 8 <= len(raw):
        tag, size = raw[i:i + 4], int.from_bytes(raw[i + 4:i + 8], "little")
        if tag == b"EXIF":
            found.append("EXIF (camera, date, location)")
        elif tag == b"XMP ":
            found.append("XMP")
        elif tag == b"ICCP":
            found.append("an ICC profile")
        elif tag == b"VP8X" and size >= 1 and raw[i + 8] & 0x2C:
            found.append("metadata flags")
        i += 8 + size + (size & 1)
    return sorted(set(found))


def clean_text(s, name, limit=300, required=True):
    s = str(s or "").strip()
    if required and not s:
        raise BadRequest(f"{name} is required")
    if len(s) > limit or re.search(r"[<>]|javascript:", s, re.I):
        raise BadRequest(f"{name}: plain text only, at most {limit} characters")
    return s


def image_meta(body):
    alt = body.get("alt") or {}
    return {
        "alt": {l: clean_text(alt.get(l), f"alt text ({l.upper()})", 250) for l in LANGS},
        "credit": clean_text(body.get("credit"), "credit", 120),
        "licence": clean_text(body.get("licence"), "licence", 200),
    }


def upload_image(body):
    if not body.get("confirm"):
        raise BadRequest("confirm the photo checklist first")
    meta = image_meta(body)
    big = data_url_webp(body.get("w1600"), 1_500_000, "large version")
    small = data_url_webp(body.get("w800"), 600_000, "small version")
    iid = dt.date.today().strftime("%Y%m%d") + "-" + hashlib.sha256(big).hexdigest()[:8]
    IMAGES.mkdir(exist_ok=True)
    (IMAGES / f"{iid}-1600.webp").write_bytes(big)
    (IMAGES / f"{iid}-800.webp").write_bytes(small)
    reg = load_json(REGISTER, None) or {"_about": "LIC-01 licence record for every image in images/. Written by the admin tool.", "images": {}}
    reg["images"][iid] = {"files": [f"{iid}-1600.webp", f"{iid}-800.webp"], "credit": meta["credit"], "licence": meta["licence"],
                          "added": dt.date.today().isoformat(), "checklist": "own photo; no identifiable people; no arms or logos; metadata stripped"}
    REGISTER.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", "utf-8")
    d = read_images()
    d["library"][iid] = {"w800": f"{iid}-800.webp", "w1600": f"{iid}-1600.webp", "alt": meta["alt"], "credit": meta["credit"]}
    write_images(d)
    return iid


def update_image(body):
    iid = str(body.get("id", ""))
    d = read_images()
    lib = d["library"]
    if iid not in lib:
        raise BadRequest("unknown image")
    meta = image_meta(body)
    lib[iid].update({"alt": meta["alt"], "credit": meta["credit"]})
    reg = load_json(REGISTER, {"images": {}})
    if iid in reg.get("images", {}):
        reg["images"][iid].update({"credit": meta["credit"], "licence": meta["licence"]})
        REGISTER.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", "utf-8")
    write_images(d)


def delete_image(body):
    iid = str(body.get("id", ""))
    if not re.fullmatch(r"\d{8}-[0-9a-f]{8}", iid):
        raise BadRequest("unknown image")
    imgs = read_images()
    imgs["library"].pop(iid, None)
    imgs["assign"] = {k: v for k, v in imgs["assign"].items() if v != iid}
    for f in (f"{iid}-1600.webp", f"{iid}-800.webp"):
        p = IMAGES / f
        if p.exists():
            p.unlink()
    reg = load_json(REGISTER, None)
    if reg and iid in reg.get("images", {}):
        del reg["images"][iid]
        REGISTER.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", "utf-8")
    write_images(imgs)


# ---------------------------------------------------------------- undo / redo
# Every change made here is recorded as the files' contents before and after.
# Undo puts "before" back, redo puts "after" back — but only if the file still
# holds exactly what the admin left there, so a hand edit or a git pull in the
# meantime is never overwritten. Adding or deleting a photo is not recorded.
JOURNALED = [SETTINGS_JS, IMAGES_JS, REGISTER] + [ROOT / f for f in TEXT_FILES]


def _snap(paths):
    return {str(Path(p).relative_to(ROOT)): (Path(p).read_text("utf-8") if Path(p).exists() else None) for p in paths}


def _history():
    h = load_json(HISTORY, None) or {}
    return {"undo": h.get("undo", []), "redo": h.get("redo", [])}


def _save_history(h):
    BACKUPS.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps(h, ensure_ascii=False), "utf-8")


def journaled(label, fn):
    before = _snap(JOURNALED)
    out = fn()
    after = _snap(JOURNALED)
    changed = [k for k in before if before[k] != after[k]]
    if changed:
        h = _history()
        h["undo"] = (h["undo"] + [{"label": label, "at": dt.datetime.now().isoformat(timespec="seconds"),
                                   "before": {k: before[k] for k in changed}, "after": {k: after[k] for k in changed}}])[-40:]
        h["redo"] = []
        _save_history(h)
    return out


def history_step(direction):
    h = _history()
    src, dst = (h["undo"], h["redo"]) if direction == "undo" else (h["redo"], h["undo"])
    if not src:
        raise BadRequest(f"Nothing to {direction}.")
    e = src[-1]
    expect, put = (e["after"], e["before"]) if direction == "undo" else (e["before"], e["after"])
    allowed = {str(p.relative_to(ROOT)) for p in JOURNALED}
    for rel, content in expect.items():
        if rel not in allowed:
            raise BadRequest("history entry names an unexpected file")
        cur = (ROOT / rel).read_text("utf-8") if (ROOT / rel).exists() else None
        if cur != content:
            raise BadRequest(f"{rel} was changed outside the admin since — {direction} would overwrite that, so it is not done.")
    for rel, content in put.items():
        if content is None:
            (ROOT / rel).unlink(missing_ok=True)
        else:
            (ROOT / rel).write_text(content, "utf-8")
    src.pop()
    dst.append(e)
    _save_history(h)
    return e["label"]


def history_state():
    h = _history()
    return {"undo": h["undo"][-1]["label"] if h["undo"] else None, "redo": h["redo"][-1]["label"] if h["redo"] else None,
            "undoCount": len(h["undo"]), "redoCount": len(h["redo"])}


# ---------------------------------------------------------------- text editing
import html as _html

BLOCK_RE = re.compile(r"<(h[1-6]|p|li)>(.*?)</\1>", re.S)
PLACEHOLDER = re.compile(r"\{\w+\}")


def _norm(s):
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", "", str(s))).split()).casefold()


def _is_localized(d):
    return isinstance(d, dict) and len(d) >= 2 and set(d) <= set(LANGS) and all(isinstance(v, str) for v in d.values())


def _walk(obj, path=()):
    """Every localized text ({en:…, de:…}) in an editorial file, with its path."""
    if _is_localized(obj):
        yield list(path), obj
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k != "_meta":
                yield from _walk(v, path + (k,))


def _legal_blocks(body):
    return [m.group(2) for m in BLOCK_RE.finditer(body or "")]


def _score(value, text, raw_text):
    n = _norm(value)
    if not n:
        return 0
    if n == text:
        return 3
    # A text with {placeholders}: the clicked text is it with the gaps filled in,
    # or contains it (when the fixed words make up a good part of the text).
    if PLACEHOLDER.search(value):
        literal = _norm(PLACEHOLDER.sub("", value))
        if len(literal) >= 6:
            pat = ".+?".join(re.escape(_norm(x)) for x in PLACEHOLDER.split(value))
            if re.fullmatch(pat, text):
                return 2.5
            if len(literal) >= 0.4 * len(text) and re.search(pat, text):
                return 2
    # Part of a longer text (e.g. one sentence clicked in a paragraph), or a text
    # that makes up most of what was clicked.
    if len(text) >= 20 and (text in n or (n in text and len(n) >= 0.6 * len(text))):
        return 1
    return 0


def text_candidates(body):
    """Where a text clicked in the preview comes from: the entries whose text
    in the preview's language matches it, best first."""
    lang = body.get("lang") if body.get("lang") in LANGS else "en"
    raw_text = str(body.get("text") or "")[:4000]
    text = _norm(raw_text)
    if len(text) < 2:
        return []
    out = []
    i18n = load_json(ROOT / "data" / "i18n.json", {}) or {}
    for key, v in (i18n.get(lang) or {}).items():
        sc = _score(v, text, raw_text)
        if sc:
            out.append({"file": "data/i18n.json", "path": [key], "label": key, "score": sc,
                        "values": {l: (i18n.get(l) or {}).get(key, "") for l in LANGS}})
    for f in TEXT_FILES[1:4]:
        data = load_json(ROOT / f, {}) or {}
        for path, loc in _walk(data):
            sc = _score(loc.get(lang, ""), text, raw_text) if lang in loc else 0
            if sc:
                out.append({"file": f, "path": path, "label": " › ".join(path), "score": sc, "values": dict(loc)})
    legal = (load_json(ROOT / "data" / "legal.json", {}) or {}).get("pages", {})
    for page, d in legal.items():
        if _is_localized(d.get("title")) and lang in d["title"]:
            sc = _score(d["title"][lang], text, raw_text)
            if sc:
                out.append({"file": "data/legal.json", "path": ["pages", page, "title"], "label": f"legal › {page} › title", "score": sc, "values": dict(d["title"])})
        body_ = d.get("body") or {}
        blocks = {l: _legal_blocks(b) for l, b in body_.items()}
        for n, blk in enumerate(blocks.get(lang, [])):
            sc = _score(blk, text, raw_text)
            if sc:
                same = {l: bl for l, bl in blocks.items() if len(bl) == len(blocks[lang])}
                cand = {"file": "data/legal.json", "path": ["pages", page, "body", n], "label": f"legal › {page} › paragraph {n + 1}", "score": sc,
                        "values": {l: _html.unescape(bl[n]) for l, bl in same.items()}}
                if any("<" in bl[n] for bl in same.values()):
                    cand["locked"] = "This paragraph contains links or formatting — edit data/legal.json by hand."
                out.append(cand)
    for c in out:
        if c["file"] != "data/legal.json" and any("<" in v for v in c["values"].values()):
            c["locked"] = "This text contains formatting — edit it by hand."
    out.sort(key=lambda c: (-c["score"], abs(len(_norm(c["values"].get(lang, ""))) - len(text))))
    return out[:10]


def _write_json(rel, raw, new_obj, pairs):
    """Write an edited JSON file without reformatting it: files written by
    json.dumps(indent=2) are dumped again; hand-formatted ones get each changed
    string replaced in place, and the result must parse back to new_obj."""
    path = ROOT / rel
    old_obj = json.loads(raw)
    if json.dumps(old_obj, indent=2, ensure_ascii=False) + "\n" == raw:
        path.write_text(json.dumps(new_obj, indent=2, ensure_ascii=False) + "\n", "utf-8")
        return
    text = raw
    for old, new in pairs:
        enc = json.dumps(old, ensure_ascii=False)
        if text.count(enc) != 1:
            raise BadRequest(f"{rel}: this text appears more than once in the file — edit it by hand")
        text = text.replace(enc, json.dumps(new, ensure_ascii=False))
    if json.loads(text) != new_obj:
        raise BadRequest(f"{rel}: could not change the file safely — edit it by hand")
    path.write_text(text, "utf-8")


def _clean_value(lang, new, old, keep_placeholders):
    new = str(new if new is not None else "").strip()
    if not new:
        raise BadRequest(f"{lang.upper()}: the text can't be empty")
    if len(new) > 5000 or re.search(r"[<>]|javascript:", new, re.I):
        raise BadRequest(f"{lang.upper()}: plain text only (no < or >), at most 5000 characters")
    if keep_placeholders and set(PLACEHOLDER.findall(new)) != set(PLACEHOLDER.findall(old)):
        raise BadRequest(f"{lang.upper()}: keep the placeholders {' '.join(sorted(set(PLACEHOLDER.findall(old)))) or '(none)'} exactly as they are")
    return new


def save_text(body):
    rel = body.get("file")
    path = body.get("path")
    values = body.get("values") or {}
    if rel not in TEXT_FILES or not isinstance(path, list) or not path or not isinstance(values, dict):
        raise BadRequest("unknown text")
    raw = (ROOT / rel).read_text("utf-8")
    data = json.loads(raw)
    pairs = []
    if rel == "data/i18n.json":
        key = path[0]
        if len(path) != 1 or not all(key in (data.get(l) or {}) for l in LANGS):
            raise BadRequest("unknown text")
        for l, v in values.items():
            if l not in LANGS:
                raise BadRequest("unknown language")
            old = data[l][key]
            if "<" in old:
                raise BadRequest("This text contains formatting — edit it by hand.")
            new = _clean_value(l, v, old, True)
            if new != old:
                pairs.append((old, new))
                data[l][key] = new
    elif rel == "data/legal.json" and len(path) == 4 and path[2] == "body":
        page = (data.get("pages") or {}).get(path[1])
        if not page or not isinstance(path[3], int):
            raise BadRequest("unknown text")
        for l, v in values.items():
            bodytxt = (page.get("body") or {}).get(l)
            if bodytxt is None:
                raise BadRequest("unknown language")
            ms = list(BLOCK_RE.finditer(bodytxt))
            if path[3] >= len(ms):
                raise BadRequest("unknown paragraph")
            m = ms[path[3]]
            if "<" in m.group(2):
                raise BadRequest("This paragraph contains links or formatting — edit data/legal.json by hand.")
            new = _clean_value(l, v, _html.unescape(m.group(2)), False)
            inner = _html.escape(new, quote=False)
            if inner != m.group(2):
                new_body = bodytxt[:m.start(2)] + inner + bodytxt[m.end(2):]
                pairs.append((bodytxt, new_body))
                page["body"][l] = new_body
    else:
        node = data
        for k in path:
            if not isinstance(node, dict) or k not in node or k == "_meta":
                raise BadRequest("unknown text")
            node = node[k]
        if not _is_localized(node):
            raise BadRequest("unknown text")
        for l, v in values.items():
            if l not in node:
                raise BadRequest("unknown language")
            new = _clean_value(l, v, node[l], True)
            if new != node[l]:
                pairs.append((node[l], new))
                node[l] = new
    if not pairs:
        raise BadRequest("Nothing changed.")
    _write_json(rel, raw, data, pairs)


# ---------------------------------------------------------------- status
def words(s):
    return {w for w in re.findall(r"[a-zäöüéèàç]{5,}", (s or "").lower())}


_SESSIONS = {"key": None, "files": []}


def session_files():
    """Every data/sessions/*.json, re-read only when one of them changed."""
    paths = sorted(glob.glob(str(ROOT / "data" / "sessions" / "*.json")))
    key = tuple((p, os.path.getmtime(p)) for p in paths)
    if key != _SESSIONS["key"]:
        _SESSIONS.update(key=key, files=[load_json(p, {}) or {} for p in paths])
    return _SESSIONS["files"]


def link_candidates(init):
    """National Council final votes whose title matches the proposal (for the Vote links page).
    An initiative only matches a decree on a popular initiative, a referendum only
    an act that isn't one, so a counter-proposal is never offered as the initiative's
    own vote (a counter-proposal decree goes with the referendum on it). A score of 1.0 means the quoted initiative title (or the whole act
    title) appears in the vote's title; it is a suggestion, never a link."""
    de = (init.get("title") or {}).get("de", "")
    m = re.search(r"«(.+?)»", de)
    key = (m.group(1) if m else de)
    kw = words(key)
    is_init = init.get("type") == "initiative"
    if init.get("status") == "collecting":
        return []                      # still collecting signatures: Parliament hasn't voted
    out = []
    for sf in session_files():
        for v in sf.get("votes", []):
            t = (v.get("title") or {}).get("de", "")
            tl = t.lower()
            on_initiative = "volksinitiative" in tl and "gegenentwurf" not in tl and "gegenvorschlag" not in tl
            if on_initiative != is_init:
                continue
            if m and key[:40].lower() in t.lower():
                score = 1.0
            else:
                tw = words(t)
                score = len(kw & tw) / max(len(kw), 1)
            if score >= 0.6:
                out.append({"session": sf.get("id"), "vote": v.get("id"), "title": t, "date": v.get("voteEnd"),
                            "tally": v.get("tally"), "score": round(score, 2), "business": v.get("businessNumber")})
    out.sort(key=lambda c: (-c["score"], c["date"] or ""), reverse=False)
    return out[:5]


def open_decrees():
    """Final votes on a decree on a popular initiative whose direction the data
    job couldn't read from the official wording (for the Vote links page)."""
    out = []
    for sf in session_files():
        for v in sf.get("votes", []):
            d = v.get("initiativeDecree")
            if d is None or d.get("recommend") in ("reject", "accept"):
                continue
            sides = {}
            for k, g in (v.get("byParty") or {}).items():
                y, n = g.get("yes", 0), g.get("no", 0)
                if y or n:
                    sides[k] = "yes" if y > n else "no" if n > y else "split"
            out.append({"session": sf.get("id"), "vote": v.get("id"), "title": (v.get("title") or {}).get("de", ""),
                        "date": v.get("voteEnd"), "meaning": v.get("meaning") or {}, "tally": v.get("tally"),
                        "sides": sides, "business": v.get("businessNumber")})
    out.sort(key=lambda d: d["date"] or "", reverse=True)
    return out


def status():
    today = dt.date.today()
    inits = initiatives()
    upcoming = sorted([i for i in inits if i.get("status") == "upcoming" and i.get("voteDate") and i["voteDate"] >= today.isoformat()],
                      key=lambda i: (i["voteDate"], i["id"]))
    nxt = upcoming[0]["voteDate"] if upcoming else None
    days = (dt.date.fromisoformat(nxt) - today).days if nxt else None
    sessions = (load_json(ROOT / "data" / "sessions-index.json", {}) or {}).get("sessions", [])
    sitting = next((s for s in sessions if s.get("start", "") <= today.isoformat() <= s.get("end", "")), None)
    fresh = []
    for f in sorted(glob.glob(str(ROOT / "data" / "*.json"))):
        meta = (load_json(f, {}) or {}).get("_meta", {}) if isinstance(load_json(f, {}), dict) else {}
        when = meta.get("fetchedAt") or meta.get("generatedAt")
        if when:
            try:
                d = dt.datetime.fromisoformat(str(when).replace("Z", "+00:00")).date()
                fresh.append({"file": Path(f).name, "when": d.isoformat(), "days": (today - d).days})
            except ValueError:
                fresh.append({"file": Path(f).name, "when": str(when), "days": None})
    maint = ROOT / "MAINTENANCE_MODE"
    try:
        git = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        git = []
    todo = ROOT / "TRANSLATIONS_TODO.md"
    fin = (load_json(ROOT / "data" / "financing.json", {}) or {}).get("initiatives", {})
    votes = []
    for i in upcoming:
        f = fin.get(i["id"]) or {}
        total = sum((f.get(s) or {}).get("totalRevenue", 0) for s in ("pro", "contra"))
        votes.append({"id": i["id"], "date": i["voteDate"], "type": i.get("type"),
                      "title": (i.get("title") or {}).get("en") or (i.get("title") or {}).get("de"),
                      "funding": total, "candidates": link_candidates(i)})
    # Vote links: every proposal except those still collecting signatures —
    # upcoming (soonest first), then decided (newest first), then pending.
    def by(status, newest=False):
        return sorted((i for i in inits if i.get("status") in status), key=lambda i: (i.get("voteDate") or "", i["id"]), reverse=newest)
    link_votes = [{"id": i["id"], "date": i.get("voteDate") or "", "type": i.get("type"), "status": i.get("status"),
                   "title": (i.get("title") or {}).get("en") or (i.get("title") or {}).get("de"),
                   "candidates": link_candidates(i)}
                  for i in by({"upcoming"}) + by({"adopted", "rejected"}, newest=True) + by({"pending"})]
    return {
        "today": today.isoformat(),
        "maintenance": {"on": maint.exists(), "text": maint.read_text("utf-8") if maint.exists() else ""},
        "nextBallot": {"date": nxt, "days": days, "count": sum(1 for i in upcoming if i["voteDate"] == nxt), "quiet": days is not None and days <= 10},
        "session": {"name": f"{sitting['season']} {sitting['year']}", "start": sitting["start"], "end": sitting["end"]} if sitting else None,
        "freshness": fresh,
        "translations": todo.read_text("utf-8") if todo.exists() else "",
        "changed": git,
        "votes": votes,
        "linkVotes": link_votes,
        "openDecrees": open_decrees(),
        "fonts": FONTS,
        "limits": LIMITS,
        "register": (load_json(REGISTER, {}) or {}).get("images", {}),
        "imageMeta": {f.name[:17]: webp_metadata(f.read_bytes()) for f in sorted(IMAGES.glob("*-1600.webp"))} if IMAGES.exists() else {},
    }


def run_checks():
    out = {}
    for name, args in (("check.py", [sys.executable, "scripts/check.py"]), ("validate.py", [sys.executable, "scripts/validate.py"])):
        try:
            p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=600)
            out[name] = {"code": p.returncode, "output": (p.stdout + p.stderr)[-20000:]}
        except (OSError, subprocess.SubprocessError) as e:
            out[name] = {"code": -1, "output": str(e)}
    return out


# ---------------------------------------------------------------- publishing
GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")   # never wait for a password prompt


def run_git(*args, cwd=None, timeout=120, check=True):
    p = subprocess.run(["git", *args], cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout, env=GIT_ENV)
    if check and p.returncode != 0:
        raise BadRequest(f"git {args[0]} failed: {(p.stderr or p.stdout).strip()[-600:]}")
    return p


def pending_files(kind, ref="origin/main"):
    """Files under this button's paths that differ from GitHub's main (no network)."""
    paths = PUBLISH[kind]["paths"]
    changed = run_git("diff", "--name-only", ref, "--", *paths, check=False).stdout.split()
    untracked = run_git("ls-files", "--others", "--exclude-standard", "--", *paths, check=False).stdout.split()
    return sorted(set(changed) | set(untracked))


def copy_into(kind, wt):
    """Mirror this button's paths from the working copy into the clean worktree."""
    for rel in PUBLISH[kind]["paths"]:
        src, dst = ROOT / rel, Path(wt) / rel
        if rel == "images":
            if dst.exists():
                shutil.rmtree(dst)
            if src.is_dir():
                dst.mkdir(parents=True)
                for f in src.iterdir():
                    if f.is_file() and (re.fullmatch(r"\d{8}-[0-9a-f]{8}-(800|1600)\.webp", f.name) or f.name == "LICENSES.json"):
                        shutil.copy2(f, dst / f.name)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif dst.exists():
            dst.unlink()


def parse_check(out):
    blocks = re.findall(r"^\s*✗ BLOCK (\S+): (.*)$", out, re.M)
    flags = {}
    for rule, msg in re.findall(r"^\s*[!✓] FLAG\s+(\S+) \([^)]*\): (.*)$", out, re.M):
        flags.setdefault(rule, []).append(msg)
    return blocks, flags


def prepare_publish(kind):
    if kind not in PUBLISH:
        raise BadRequest("unknown publish button")
    if run_git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != "main":
        raise BadRequest("Switch to the main branch first.")
    if run_git("fetch", "origin", "main", timeout=90, check=False).returncode != 0:
        raise BadRequest("Could not reach GitHub to check main — are you online?")
    ahead, behind = (int(x) for x in run_git("rev-list", "--left-right", "--count", "HEAD...origin/main").stdout.split())
    if behind:
        raise BadRequest("Your main is behind GitHub. Pull first (git pull), then publish.")
    if ahead:
        raise BadRequest("Your main has commits that aren't on GitHub yet. Push those with your normal git flow first.")
    if run_git("cat-file", "-e", "origin/main:js/news.js", check=False).returncode != 0:
        raise BadRequest("The 1.1 code isn't on GitHub yet. Commit and push it with your normal git flow first.")
    if kind == "images" and "registered_images" not in run_git("show", "origin/main:scripts/check.py", check=False).stdout:
        raise BadRequest("Image publishing (deploy.yml / check.py) isn't on GitHub yet. Push that change first.")
    files = pending_files(kind)
    if not files:
        raise BadRequest("Nothing to publish — this is already live.")
    tmp = tempfile.mkdtemp(prefix="pch-publish-")
    wt = os.path.join(tmp, "wt")
    run_git("worktree", "add", "--detach", wt, "origin/main", timeout=120)
    ctx = {"tmp": tmp, "wt": wt, "files": files}
    try:
        copy_into(kind, wt)
        chk = subprocess.run([sys.executable, "scripts/check.py", "--base", "origin/main"], cwd=wt,
                             capture_output=True, text=True, timeout=900)
        ctx["output"] = (chk.stdout + chk.stderr)[-12000:]
        ctx["blocks"], ctx["flags"] = parse_check(chk.stdout)
    except Exception:
        cleanup_publish(ctx)
        raise
    return ctx


def cleanup_publish(ctx):
    run_git("worktree", "remove", "--force", ctx["wt"], check=False)
    shutil.rmtree(ctx["tmp"], ignore_errors=True)
    run_git("worktree", "prune", check=False)


def publish_preview(body):
    ctx = prepare_publish(body.get("kind"))
    try:
        return {"files": ctx["files"], "blocks": ctx["blocks"], "flags": ctx["flags"], "output": ctx["output"]}
    finally:
        cleanup_publish(ctx)


def publish(body):
    kind = body.get("kind")
    if not body.get("previewed"):
        raise BadRequest("Confirm that you've looked at the preview first (PROC-03).")
    reasons = body.get("reasons") or {}
    ctx = prepare_publish(kind)
    try:
        if ctx["blocks"]:
            raise BadRequest("The checks found a problem that must be fixed first: " + "; ".join(f"{r}: {m}" for r, m in ctx["blocks"]))
        lines = []
        for rule in sorted(ctx["flags"]):
            why = " ".join(str(reasons.get(rule, "")).split())
            if len(why) < 5:
                raise BadRequest(f"Give a reason for {rule} (it becomes your Approved-Rule line).")
            if len(why) > 300 or re.search(r"[<>]", why):
                raise BadRequest(f"The reason for {rule}: plain text, at most 300 characters.")
            lines.append(f"Approved-Rule: {rule} — {why}")
        wt = ctx["wt"]
        run_git("add", "-A", "--", *PUBLISH[kind]["paths"], cwd=wt)
        if not run_git("diff", "--cached", "--name-only", cwd=wt).stdout.strip():
            raise BadRequest("Nothing to publish — this is already live.")
        msg = PUBLISH[kind]["title"] + "\n\nFiles:\n" + "\n".join("- " + f for f in ctx["files"]) + ("\n\n" + "\n".join(lines) if lines else "")
        run_git("commit", "-q", "-m", msg, cwd=wt)
        sha = run_git("rev-parse", "--short", "HEAD", cwd=wt).stdout.strip()
        push = run_git("push", "origin", "HEAD:refs/heads/main", cwd=wt, timeout=900, check=False)
        if push.returncode != 0:
            raise BadRequest("The push was refused — nothing went live. " + (push.stdout + push.stderr).strip()[-1500:])
        # Bring the working copy's main up to the new commit. Its files already hold
        # exactly what was committed; other work (staged or not) is left as it was.
        run_git("fetch", "origin", "main", timeout=90, check=False)
        run_git("reset", "--soft", "origin/main")
        run_git("restore", "--staged", "--", *PUBLISH[kind]["paths"], check=False)
        return {"ok": True, "commit": sha, "files": ctx["files"], "output": (push.stdout + push.stderr)[-4000:]}
    finally:
        cleanup_publish(ctx)


# ---------------------------------------------------------------- HTTP
STATIC = {"/admin.css": ("admin.css", "text/css; charset=utf-8"), "/admin.js": ("admin.js", "text/javascript; charset=utf-8")}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; "
       f"connect-src 'self'; frame-src http://127.0.0.1:{PREVIEW_PORT}; frame-ancestors 'none'; "
       "base-uri 'none'; form-action 'none'; object-src 'none'")


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "PolitikchAdmin"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.command, self.path))

    def headers_ok(self):
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.headers_ok():
            return self.send(403, {"error": "wrong host"})
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (ADMIN / "index.html").read_text("utf-8").replace("%%TOKEN%%", TOKEN).replace("%%PREVIEW%%", f"http://{HOST}:{PREVIEW_PORT}")
            return self.send(200, html, "text/html; charset=utf-8")
        if path in STATIC:
            f, ctype = STATIC[path]
            return self.send(200, (ADMIN / f).read_bytes(), ctype)
        if path == "/css/fonts.css":
            return self.send(200, (ROOT / "css" / "fonts.css").read_bytes(), "text/css; charset=utf-8")
        m = re.fullmatch(r"/fonts/([a-z0-9-]+\.woff2)", path)
        if m and (ROOT / "fonts" / m.group(1)).exists():
            return self.send(200, (ROOT / "fonts" / m.group(1)).read_bytes(), "font/woff2")
        m = re.fullmatch(r"/images/(\d{8}-[0-9a-f]{8}-(?:800|1600)\.webp)", path)
        if m and (IMAGES / m.group(1)).exists():
            return self.send(200, (IMAGES / m.group(1)).read_bytes(), "image/webp")
        if path == "/api/state":
            pub = {k: {"pending": pending_files(k)} for k in PUBLISH}
            return self.send(200, {"settings": read_settings(), "images": read_images(), "status": status(), "publish": pub, "history": history_state()})
        return self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.headers_ok():
            return self.send(403, {"error": "wrong host"})
        origin = self.headers.get("Origin")
        if origin not in ALLOWED_ORIGINS or not secrets.compare_digest(self.headers.get("X-Admin-Token", ""), TOKEN):
            return self.send(403, {"error": "not allowed"})
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self.send(415, {"error": "JSON only"})
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self.send(413, {"error": "too large"})
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            path = urlparse(self.path).path
            if path == "/api/settings":
                journaled(str(body.pop("_label", "") or "Settings saved")[:80], lambda: write_settings(clean_settings(body)))
                return self.send(200, {"ok": True, "settings": read_settings(), "history": history_state()})
            if path in ("/api/history/undo", "/api/history/redo"):
                label = history_step(path.rsplit("/", 1)[1])
                return self.send(200, {"ok": True, "label": label, "settings": read_settings(), "images": read_images(), "history": history_state()})
            if path == "/api/text/find":
                return self.send(200, {"candidates": text_candidates(body)})
            if path == "/api/text/save":
                journaled("Text: " + " › ".join(str(x) for x in (body.get("path") or []))[:80], lambda: save_text(body))
                return self.send(200, {"ok": True, "history": history_state()})
            if path == "/api/images":
                iid = upload_image(body)
                return self.send(200, {"ok": True, "id": iid, "images": read_images()})
            if path == "/api/images/update":
                journaled("Photo text", lambda: update_image(body))
                return self.send(200, {"ok": True, "images": read_images()})
            if path == "/api/images/delete":
                delete_image(body)
                return self.send(200, {"ok": True, "images": read_images()})
            if path == "/api/images/assign":
                journaled("Photo assignments", lambda: assign_images(body))
                return self.send(200, {"ok": True, "images": read_images()})
            if path == "/api/publish/preview":
                return self.send(200, publish_preview(body))
            if path == "/api/publish":
                return self.send(200, publish(body))
            if path == "/api/check":
                return self.send(200, run_checks())
            return self.send(404, {"error": "not found"})
        except BadRequest as e:
            return self.send(400, {"error": str(e)})
        except (ValueError, TypeError) as e:
            return self.send(400, {"error": f"bad request: {e}"})
        except subprocess.TimeoutExpired:
            return self.send(504, {"error": "git or the checks took too long — nothing was published"})


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the site read-only on its own port (a separate origin from the admin),
    with caching switched off so the preview always shows the saved settings."""

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, fmt, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def _send_bytes(self, data, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        if self.headers.get("Host", "") not in PREVIEW_HOSTS or ".." in path:
            self.send_error(404)
            return
        # The edit modes: the page gets the helper script (with the admin's port,
        # the only origin it talks to); the site's own files are not changed.
        if path == AGENT_PATH:
            return self._send_bytes((ADMIN / "preview-agent.js").read_bytes(), "text/javascript; charset=utf-8")
        if path == "/index.html":
            page = (ROOT / "index.html").read_text("utf-8")
            tag = f'<script type="module" src="{AGENT_PATH}?admin={PORT}"></script>'
            return self._send_bytes(page.replace("</body>", tag + "\n</body>", 1).encode("utf-8"), "text/html; charset=utf-8")
        if not PREVIEW_ALLOW.match(path):
            self.send_error(404)
            return
        self.path = path
        super().do_GET()

    def do_HEAD(self):
        self.send_error(405)

    def do_POST(self):
        self.send_error(405)


def main():
    import threading
    preview = http.server.ThreadingHTTPServer((HOST, PREVIEW_PORT), PreviewHandler)
    threading.Thread(target=preview.serve_forever, daemon=True).start()
    srv = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Politikch admin running at http://{HOST}:{PORT}  (local only — Ctrl+C to stop)")
    print(f"Preview of the site at http://{HOST}:{PREVIEW_PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
