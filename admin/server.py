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
  * Status and checks: maintenance mode (read-only, SEC-10), data freshness,
    next ballot, sitting session, translations to do, changed files, and a
    button that runs scripts/check.py and scripts/validate.py.

Safety
  * Listens on 127.0.0.1 only and never contacts the internet.
  * Every request must carry the Host 127.0.0.1:8002 / localhost:8002 (stops DNS
    rebinding); every change needs the per-start token embedded in the page and a
    same-origin Origin header (stops other websites in your browser from posting
    here). Writes are limited to js/site-settings.js, images/ and admin/.backup/.
  * Two publish buttons, pressed by you: "Make changes live" commits only
    js/site-settings.js, "Publish images" only images/ + js/site-images.js. Each
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
}
IMAGES_HEADER = ("/* Politikch photos — written by the local admin tool (admin/, localhost:8002).\n"
                 "   Which photo goes with which vote, with alt text in five languages and a credit.\n"
                 "   Published separately from the design settings (\"Publish images\" in the admin);\n"
                 "   every file listed here must have a licence record in images/LICENSES.json (LIC-01). */\n")
PUBLISH = {
    "settings": {"paths": ["js/site-settings.js"], "title": "Admin: make design settings live"},
    "images": {"paths": ["js/site-images.js", "images"], "title": "Admin: publish images"},
}
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
    return raw


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


# ---------------------------------------------------------------- status
def words(s):
    return {w for w in re.findall(r"[a-zäöüéèàç]{5,}", (s or "").lower())}


def link_candidates(init):
    """National Council final votes whose title matches the proposal (for the Vote links page)."""
    de = (init.get("title") or {}).get("de", "")
    m = re.search(r"«(.+?)»", de)
    key = (m.group(1) if m else de)
    kw = words(key)
    out = []
    for f in sorted(glob.glob(str(ROOT / "data" / "sessions" / "*.json"))):
        sf = load_json(f, {}) or {}
        for v in sf.get("votes", []):
            t = (v.get("title") or {}).get("de", "")
            if m and key[:40].lower() in t.lower():
                score = 1.0
            else:
                tw = words(t)
                score = len(kw & tw) / max(len(kw), 1)
            if score >= 0.6:
                out.append({"session": sf.get("id"), "vote": v.get("id"), "title": t, "date": v.get("voteEnd"),
                            "tally": v.get("tally"), "score": round(score, 2)})
    out.sort(key=lambda c: (-c["score"], c["date"] or ""), reverse=False)
    return out[:5]


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
    return {
        "today": today.isoformat(),
        "maintenance": {"on": maint.exists(), "text": maint.read_text("utf-8") if maint.exists() else ""},
        "nextBallot": {"date": nxt, "days": days, "count": sum(1 for i in upcoming if i["voteDate"] == nxt), "quiet": days is not None and days <= 10},
        "session": {"name": f"{sitting['season']} {sitting['year']}", "start": sitting["start"], "end": sitting["end"]} if sitting else None,
        "freshness": fresh,
        "translations": todo.read_text("utf-8") if todo.exists() else "",
        "changed": git,
        "votes": votes,
        "fonts": FONTS,
        "limits": LIMITS,
        "register": (load_json(REGISTER, {}) or {}).get("images", {}),
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


def undo():
    old = sorted(BACKUPS.glob("site-settings-*.js")) if BACKUPS.exists() else []
    if not old:
        raise BadRequest("nothing to undo")
    shutil.copy2(old[-1], SETTINGS_JS)
    old[-1].unlink()


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
            html = (ADMIN / "index.html").read_text("utf-8").replace("%%TOKEN%%", TOKEN)
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
            return self.send(200, {"settings": read_settings(), "images": read_images(), "status": status(), "publish": pub})
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
                write_settings(clean_settings(body))
                return self.send(200, {"ok": True, "settings": read_settings()})
            if path == "/api/undo":
                undo()
                return self.send(200, {"ok": True, "settings": read_settings()})
            if path == "/api/images":
                iid = upload_image(body)
                return self.send(200, {"ok": True, "id": iid, "images": read_images()})
            if path == "/api/images/update":
                update_image(body)
                return self.send(200, {"ok": True, "images": read_images()})
            if path == "/api/images/delete":
                delete_image(body)
                return self.send(200, {"ok": True, "images": read_images()})
            if path == "/api/images/assign":
                assign_images(body)
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

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        if self.headers.get("Host", "") not in PREVIEW_HOSTS or ".." in path or not PREVIEW_ALLOW.match(path):
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
