#!/usr/bin/env python3
"""Politikch guardrail checks — enforces GUARDRAILS.md (stdlib only).

  python3 scripts/check.py                  # your working tree vs origin/main
  python3 scripts/check.py --base REF       # everything changed since REF
  python3 scripts/check.py --base REF --strict   # also fail on unsigned flags (CI, pre-push)
  python3 scripts/check.py --update-sink-baseline  # accept the current HTML insertions (flagged: PROC-05)

Two kinds of result, named by their GUARDRAILS.md rule ID:
  BLOCK  — must be fixed; the check fails.
  FLAG   — a sensitive area changed; it passes only once the owner signs it off
           with a line in a commit message of the change:
               Approved-Rule: POL-05 — "radical" is the party's own name
Exit code: 0 = pass, 1 = a BLOCK failed (or, with --strict, a FLAG is unsigned).
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GR = ROOT / "scripts" / "guardrails"
sys.path.insert(0, str(GR))
import jsscan  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
import licences  # noqa: E402

CFG = json.loads((GR / "config.json").read_text("utf-8"))
SINK_BASELINE = GR / "sinks-baseline.json"
BOT_NAME = "politikch-bot"

blocks: list[tuple[str, str]] = []
flags: dict[str, list[str]] = {}
notes: list[str] = []


def block(rule, msg):
    blocks.append((rule, msg))


def flag(rule, msg):
    flags.setdefault(rule, [])
    if msg not in flags[rule]:
        flags[rule].append(msg)


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def read(rel):
    p = ROOT / rel
    return p.read_text("utf-8", errors="replace") if p.exists() else ""


def tracked():
    return [f for f in git("ls-files").splitlines() if (ROOT / f).is_file()]


def match(path, pattern):
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/")
    return fnmatch.fnmatch(path, pattern)


def js_files():
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "js").glob("*.js"))


# =========================================================================
# Whole-repo checks — run on every invocation, whatever changed
# =========================================================================
def check_validator():
    r = subprocess.run([sys.executable, "scripts/validate.py"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        for line in r.stdout.splitlines():
            if line.strip().startswith("✗"):
                block("VALIDATE", line.strip()[1:].strip())


def check_js_syntax():
    node = shutil.which("node")
    if not node:
        notes.append("node not installed — JavaScript syntax check skipped (CI runs it)")
        return
    for f in js_files() + ["analytics-worker/src/index.js"]:
        r = subprocess.run([node, "--check", f], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            block("OPS-02", f"{f}: JavaScript syntax error — {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ''}")


HTML_TPL = re.compile(r"<[a-zA-Z/!]|=\"?\x00")
SAFE_CALLS = ["escapeAttr", "escapeHtml"]
FORMATTERS = ["formatCHF", "formatNum", "fmtPct", "icon"]


def sink_exprs():
    """Every ${...} in an HTML-building template that isn't escaped by
    construction, counted per file (SEC-01)."""
    found = {}
    for f in js_files():
        c = Counter()
        for _line, static, exprs in jsscan.templates(read(f)):
            if not HTML_TPL.search(static):
                continue
            for e in exprs:
                e = " ".join(e.split())
                if "`" in e:                       # nested template: checked on its own
                    continue
                if jsscan.whole_call(e, SAFE_CALLS + FORMATTERS):
                    continue
                if re.fullmatch(r"t\('[\w.\-]+'\)", e):   # owner-written i18n string
                    continue
                if re.fullmatch(r"-?\d+(\.\d+)?", e):
                    continue
                c[e] += 1
        found[f] = dict(c)
    return found


def check_sinks(update=False):
    current = sink_exprs()
    if update:
        SINK_BASELINE.write_text(json.dumps({
            "_about": "SEC-01 ratchet. Values inserted into HTML without escapeAttr/escapeHtml "
                      "that existed when the checks were introduced (2026-09-24). New ones are "
                      "blocked; this list may only shrink. Regenerate with "
                      "`python3 scripts/check.py --update-sink-baseline` (a flagged change).",
            "files": current}, indent=1, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
        notes.append(f"sink baseline written ({sum(sum(v.values()) for v in current.values())} entries)")
        return
    base = json.loads(SINK_BASELINE.read_text("utf-8"))["files"] if SINK_BASELINE.exists() else {}
    for f, exprs in current.items():
        allowed = base.get(f, {})
        for e, n in exprs.items():
            if n > allowed.get(e, 0):
                block("SEC-01", f"{f}: new unescaped value in HTML: ${{{e[:80]}}} — wrap it in escapeAttr(...) "
                                "(or, if it is provably safe, re-baseline with sign-off)")


def parse_csp(html):
    m = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', html)
    if not m:
        return None
    out = {}
    for part in m.group(1).split(";"):
        bits = part.split()
        if bits:
            out[bits[0]] = bits[1:]
    return out


def check_csp():
    csp = parse_csp(read("index.html"))
    want = {k: v for k, v in CFG["csp"].items() if not k.startswith("_")}
    if csp is None:
        block("SEC-03", "index.html has no Content-Security-Policy")
        return
    for d, vals in csp.items():
        if d not in want:
            block("SEC-03", f"CSP directive '{d}' is not in the approved policy")
            continue
        extra = set(vals) - set(want[d])
        if extra:
            block("SEC-03", f"CSP {d} loosened with {sorted(extra)} — update scripts/guardrails/config.json with sign-off if intended")
    for d in want:
        if d not in csp:
            block("SEC-03", f"CSP directive '{d}' was removed")
    for v in sum(csp.values(), []):
        if v in ("'unsafe-eval'", "*", "http:", "https:") or v.startswith("http://"):
            block("SEC-03", f"CSP contains {v}")
    if "'unsafe-inline'" in csp.get("script-src", []):
        block("SEC-03", "CSP script-src allows inline scripts")
    # PRIV-02: the endpoints in js/config.js must be exactly what connect-src allows.
    cfg = read("js/config.js")
    connect = set(csp.get("connect-src", []))
    for name in ("ANALYTICS_API", "POLL_API"):
        m = re.search(rf"export const {name} = '([^']*)'", cfg)
        val = m.group(1) if m else ""
        if val:
            origin = re.match(r"https://[^/]+", val)
            if not origin:
                block("PRIV-02", f"{name} must be an https URL")
            elif origin.group(0) not in connect:
                block("PRIV-02", f"{name} origin {origin.group(0)} is not in CSP connect-src")


def check_third_party_loads():
    for f in ["index.html", "404.html", "maintenance.html"]:
        html = read(f)
        for tag, attr in (("script", "src"), ("link", "href"), ("img", "src"), ("iframe", "src"),
                          ("embed", "src"), ("object", "data"), ("source", "src"), ("video", "src"), ("audio", "src")):
            for m in re.finditer(rf"<{tag}\b[^>]*\b{attr}=[\"'](https?:)?//", html, re.I):
                block("PRIV-02", f"{f}: <{tag}> loads a third-party resource")
    for f in ["css/styles.css", "css/fonts.css"]:
        for m in re.finditer(r"(@import|url\()\s*['\"]?(https?:)?//", read(f)):
            block("PRIV-02", f"{f}: loads a third-party resource ({m.group(0)})")
    for f in js_files():
        src = read(f)
        for m in re.finditer(r"\b(fetch|sendBeacon|XMLHttpRequest|WebSocket|EventSource)\s*\(\s*['\"`]https?://", src):
            block("PRIV-02", f"{f}: contacts a hard-coded external URL ({m.group(0)[:60]}) — use js/config.js + CSP")
        for m in re.finditer(r"import\s[^;]*from\s+['\"]https?://", src):
            block("PRIV-02", f"{f}: imports a script from another site")


def check_dangerous_js():
    for f in js_files() + ["analytics-worker/src/index.js"]:
        src = read(f)
        for pat, what in ((r"\beval\s*\(", "eval()"), (r"\bnew\s+Function\s*\(", "new Function()"),
                          (r"document\.write(ln)?\s*\(", "document.write()"),
                          (r"\bset(Timeout|Interval)\s*\(\s*['\"`]", "string timer")):
            if re.search(pat, src):
                block("SEC-04", f"{f}: uses {what}")
        for m in re.finditer(r'target=\\?"_blank\\?"', src):
            tag_start = src.rfind("<", 0, m.start())
            tag_end = src.find(">", m.end())
            if "noopener" not in src[tag_start:tag_end]:
                block("SEC-11", f"{f}: target=\"_blank\" without rel=\"noopener noreferrer\" near line {src.count(chr(10), 0, m.start()) + 1}")
        for m in re.finditer(r"window\.open\(", src):
            stmt = src[m.start():src.find(";", m.start())]
            if "noopener" not in stmt:
                block("SEC-11", f"{f}: window.open without 'noopener'")


SECRET_PATTERNS = [
    (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(:fx)\b", "DeepL API key"),
    (r"\bgh[pousr]_[A-Za-z0-9]{30,}", "GitHub token"),
    (r"\bgithub_pat_[A-Za-z0-9_]{30,}", "GitHub token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "AWS key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key"),
    (r"\bxox[abpr]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"\bsk-[A-Za-z0-9]{32,}", "API secret key"),
    (r"DASHBOARD_PASSWORD\s*=\s*\S{4,}", "dashboard password"),
]


def check_secrets(files):
    for f in files:
        if Path(f).name in (".dev.vars", ".env") or f.endswith((".pem", ".key")):
            block("SEC-05", f"{f}: secrets file is tracked")
            continue
        if f.startswith("fonts/"):
            continue
        text = read(f)
        for pat, what in SECRET_PATTERNS:
            if re.search(pat, text):
                block("SEC-05", f"{f}: looks like a {what}")


def check_deploy_guard():
    d = read(".github/workflows/deploy.yml")
    for marker, what in (("Assemble site (allowlist)", "the allowlist step"),
                         ("Non-runtime files in deploy artifact", "the file-type guard"),
                         ("-f MAINTENANCE_MODE", "the maintenance switch"),
                         ("scripts/check.py", "the guardrail checks before deploying")):
        if marker not in d:
            block("SEC-06" if "check.py" not in marker else "OPS-01", f"deploy.yml lost {what}")
    if re.search(r"cp\s+-r\s+\.\s|cp\s+-r\s+\*|rsync\s+-a\s+\./", d):
        block("SEC-06", "deploy.yml copies the whole repository")


def check_workflows():
    for p in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        f = str(p.relative_to(ROOT))
        y = p.read_text("utf-8")
        if not re.search(r"(?m)^permissions:", y):
            block("SEC-07", f"{f}: no top-level permissions: block")
        for m in re.finditer(r"(?m)^\s*-?\s*uses:\s*(\S+)", y):
            ref = m.group(1)
            if not ref.startswith("./") and not re.search(r"@[0-9a-f]{40}$", ref):
                block("SEC-07", f"{f}: {ref} is not pinned to a commit SHA")
        if "pull_request_target" in y:
            block("SEC-07", f"{f}: uses pull_request_target")
        for ln in y.splitlines():
            # Untrusted event text may only be passed through env:/with: values,
            # never pasted into a shell command.
            if re.search(r"\$\{\{\s*github\.(event\.(issue|pull_request|comment|review|head_commit)|head_ref)", ln) \
                    and not re.match(r"\s*[A-Za-z_][A-Za-z0-9_-]*:\s*\$\{\{[^}]*\}\}\s*$", ln):
                block("SEC-07", f"{f}: interpolates event text into a command: {ln.strip()[:80]}")
        if "DEEPL_ALLOW_PAID" in y:
            flag("OPS-07", f"{f}: allows a billable DeepL key")
    fetch = read(".github/workflows/fetch-financing.yml")
    if "persist-credentials: false" not in fetch:
        block("SEC-07", "fetch-financing.yml: checkout keeps the write token while third-party code runs")


def check_requirements():
    for p in (ROOT / "scripts").glob("requirements*.txt"):
        for line in p.read_text("utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line and not re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[0-9][\w.\-]*", line):
                block("SEC-08", f"{p.name}: '{line}' is not pinned to an exact version")


def fetch_scripts():
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "scripts").glob("fetch_*.py"))


def check_fetchers():
    for f in fetch_scripts():
        s = read(f)
        if "def read_capped" not in s or "MAX_BYTES" not in s:
            block("SEC-09", f"{f}: no download size cap (read_capped / MAX_BYTES)")
        if re.search(r"\b(resp|r|response)\.read\(\s*\)", s):
            block("SEC-09", f"{f}: reads a response without the size cap")
    for f in fetch_scripts() + ["scripts/build_municipality_maps.py"]:
        s = read(f)
        m = re.search(r"UA\s*=\s*\(?\s*((?:\"[^\"]*\"\s*)+)", s)
        ua = "".join(re.findall(r"\"([^\"]*)\"", m.group(1))) if m else ""
        if "Politikch" not in ua or "politikch.ch" not in ua:
            block("SRC-06", f"{f}: User-Agent must name Politikch and give a contact")
    for p in (ROOT / "scripts").glob("*.py"):
        if re.search(r"Mozilla/\d", p.read_text("utf-8")):
            block("SRC-06", f"scripts/{p.name}: imitates a browser User-Agent")
    # SRC-05: every script that contacts a host with a crawl delay honours it.
    for host, meta in CFG["sources"].items():
        if host.startswith("_") or not meta.get("crawlDelay"):
            continue
        for f in fetch_scripts():
            s = read(f)
            if host in s:
                m = re.search(r"CRAWL_DELAY\s*=\s*float\(os\.environ\.get\(\"POLITIKCH_CRAWL_DELAY\",\s*\"(\d+)\"\)\)", s)
                if not m or int(m.group(1)) < meta["crawlDelay"]:
                    block("SRC-05", f"{f}: contacts {host} without honouring its {meta['crawlDelay']} s crawl delay")
    # SRC-01: follow-on URLs from VoteInfo metadata are checked at run time.
    if "VOTEINFO_HOSTS" not in read("scripts/fetch_initiatives.py"):
        block("SRC-01", "fetch_initiatives.py no longer restricts which hosts VoteInfo metadata may send it to")


HOST_RE = re.compile(r"https?://([A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9])")


def check_hosts():
    known = {h for h in CFG["sources"] if not h.startswith("_")}
    files = [str(p.relative_to(ROOT)) for p in (ROOT / "scripts").glob("*.py")]
    files += [str(p.relative_to(ROOT)) for p in (ROOT / ".github" / "workflows").glob("*.yml")]
    files += js_files()
    for f in files:
        for h in set(HOST_RE.findall(read(f))):
            if h not in known:
                block("SRC-01", f"{f}: contacts or links to {h}, which has no row in the source registry "
                                "(scripts/guardrails/config.json)")
    for h in CFG["voteinfoHosts"]:
        if h not in known:
            block("SRC-01", f"VoteInfo host {h} has no registry row")


def check_attribution():
    legal = json.loads(read("data/legal.json") or "{}")
    body = ((legal.get("pages") or {}).get("sources") or {}).get("body") or {}
    for lang, words in CFG["attribution"]["sourcesPage"].items():
        text = body.get(lang, "")
        for w in words:
            if w.lower() not in text.lower():
                block("SRC-03", f"Sources page ({lang}) no longer credits '{w}'")
    i18n = json.loads(read("data/i18n.json") or "{}")
    for lang, strings in i18n.items():
        for k in CFG["attribution"]["deeplKeys"]:
            if "DeepL" not in strings.get(k, ""):
                block("SRC-03", f"i18n {lang}.{k} must credit DeepL")


def check_privacy_code():
    # PRIV-01: a visitor's choices never reach analytics, share links or URLs.
    for f in js_files():
        s = read(f)
        for m in re.finditer(r"\btrack\(([^)]*)\)", s):
            if "choice" in m.group(1):
                block("PRIV-01", f"{f}: sends a vote choice to analytics")
        if f != "js/myvotes.js" and re.search(r"['\"]politikch-votes", s):
            block("PRIV-01", f"{f}: reads the visitor's stored votes outside myvotes.js")
    if re.search(r"from\s+['\"]\./myvotes\.js", read("js/share.js")):
        block("PRIV-01", "share.js imports the visitor's votes")
    mv = read("js/myvotes.js")
    if mv.count("if (!POLL_API) return null") < 2:
        block("PRIV-01", "myvotes.js: network calls are no longer guarded by POLL_API")
    # PRIV-03: device storage inventory (FMG Art. 45c).
    inv = {k for k in CFG["storageKeys"] if not k.startswith("_")}
    for f in js_files():
        s = read(f)
        for k in set(re.findall(r"['\"](politikch-[a-z0-9-]+)['\"]", s)):
            if k not in inv:
                block("PRIV-03", f"{f}: stores '{k}' on the visitor's device but it is not in the storage inventory")
        for api in ("document.cookie", "sessionStorage", "indexedDB"):
            if api in s:
                block("PRIV-03", f"{f}: uses {api} — not covered by the Privacy page")
    # PRIV-05: the analytics Worker records only the listed fields and events.
    w = read("analytics-worker/src/index.js")
    m = re.search(r"EVENT_NAMES = new Set\(\[([^\]]*)\]\)", w)
    events = set(re.findall(r"'([a-z_]+)'", m.group(1))) if m else set()
    if events != set(CFG["analytics"]["events"]):
        block("PRIV-05", f"analytics Worker event list changed: {sorted(events ^ set(CFG['analytics']['events']))}")
    for f in js_files():
        for name in re.findall(r"\btrack\('([a-z_]+)'", read(f)):
            if name not in CFG["analytics"]["events"]:
                block("PRIV-05", f"{f}: tracks '{name}', which the Worker/Privacy page don't list")
    schema = read("analytics-worker/schema.sql")
    m = re.search(r"CREATE TABLE IF NOT EXISTS events \((.*?)\n\);", schema, re.S)
    cols = [re.match(r"\s*(\w+)", ln).group(1) for ln in (m.group(1).splitlines() if m else [])
            if re.match(r"\s*\w+\s+[A-Z]", ln)]
    if cols != CFG["analytics"]["eventsColumns"]:
        block("PRIV-05", f"analytics events table columns changed: {sorted(set(cols) ^ set(CFG['analytics']['eventsColumns']))}")
    if re.search(r"\b(ip|ip_address|user_agent|ua)\b\s+TEXT", schema, re.I):
        block("PRIV-05", "analytics schema stores an IP address or user agent")
    wr = read("analytics-worker/wrangler.jsonc")
    m = re.search(r'"RAW_RETENTION_DAYS":\s*"(\d+)"', wr)
    if not m or m.group(1) != CFG["analytics"]["rawRetentionDays"]:
        block("PRIV-05", "analytics raw-record retention changed from 7 days")
    # PRIV-06: opt-outs.
    a = read("js/analytics.js")
    for marker in CFG["analytics"]["optOutMarkers"]:
        if marker not in a:
            block("PRIV-06", f"js/analytics.js no longer checks {marker}")
    # PRIV-08: private donors.
    app = read("js/app.js")
    if "anonymiseIndividualDonors(financing)" not in app:
        block("PRIV-08", "app.js no longer strips private donors' names on load")
    if re.search(r'"name":\s*f"\{first\}', read("scripts/fetch_financing.py")):
        block("PRIV-08", "fetch_financing.py stores private donors' names again")


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
EMAIL_OK = ("politikch.ch", "users.noreply.github.com", "admin.ch", "anneepolitique.swiss",
            "example.com", "example.org", "anthropic.com")


def check_personal_data(files):
    for f in files:
        if f.startswith("fonts/") or f == "LICENSE":
            continue
        text = read(f)
        for m in EMAIL_RE.finditer(text):
            dom = m.group(0).split("@", 1)[1].lower()
            if not any(dom == d or dom.endswith("." + d) for d in EMAIL_OK):
                block("PRIV-10", f"{f}: contains an email address ({m.group(0)})")
        if re.search(r"(\+41|0041)\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}", text):
            block("PRIV-10", f"{f}: contains a phone number")


def check_data_links():
    # SEC-02: links shipped in data are https and never script URLs.
    for p in sorted((ROOT / "data").rglob("*.json")):
        text = p.read_text("utf-8")
        for m in re.finditer(r'"(javascript:|data:text/html|http://)[^"]{0,60}', text, re.I):
            block("SEC-02", f"{p.relative_to(ROOT)}: unsafe link {m.group(0)[:70]}")


def check_licensing():
    # LIC-03/05/06: every data file carries exactly the licence scripts/licences.py
    # gives it, and data/LICENSE.txt is generated from the same table.
    for rel in licences.data_files():
        if rel in licences.WEBSITE_FILES:
            continue
        try:
            want = licences.licence_meta(rel)
        except KeyError:
            block("LIC-05", f"data/{rel}: no licence defined in scripts/licences.py")
            continue
        meta = (json.loads(read(f"data/{rel}")) or {}).get("_meta") or {}
        for k, v in want.items():
            if not meta.get(k):
                block("LIC-05", f"data/{rel}: _meta.{k} is missing — run `python3 scripts/licences.py --stamp`")
            elif meta[k] != v:
                block("LIC-06", f"data/{rel}: _meta.{k} doesn't match scripts/licences.py (relabelled data?)")
    notice = read("data/LICENSE.txt")
    if not notice:
        block("LIC-03", "data/LICENSE.txt is missing")
    elif notice != licences.notice_text():
        block("LIC-03", "data/LICENSE.txt is out of date — run `python3 scripts/licences.py --write-notice`")
    lic = read("LICENSE")
    if "All rights reserved" not in lic or "data/LICENSE.txt" not in lic or "Permission is hereby granted" in lic:
        block("LIC-03", "LICENSE must reserve the website's rights and point to data/LICENSE.txt")
    # LIC-09: the Data & reuse page stays complete in every language.
    legal = json.loads(read("data/legal.json") or "{}")
    page = (legal.get("pages") or {}).get("reuse") or {}
    for lang in ("en", "de", "fr", "it"):
        body = (page.get("body") or {}).get(lang, "")
        for must in ("CC BY 4.0", "Politikch", "PolitikCH", "PCH", "data/LICENSE.txt"):
            if must not in body:
                block("LIC-09", f"Data & reuse page ({lang}) no longer mentions '{must}'")
    if 'href="#/page/reuse"' not in read("index.html"):
        block("LIC-09", "the footer no longer links to the Data & reuse page")
    if "'reuse'" not in read("js/app.js"):
        block("LIC-09", "app.js no longer lists the Data & reuse page")


def check_both_sides():
    app = read("js/app.js")
    if not ("col('ai-ov-for'" in app and "col('ai-ov-against'" in app):
        block("POL-01", "app.js: the for/against arguments no longer render as a pair")
    for p in sorted((ROOT / "data" / "overviews").rglob("*.json")):
        d = json.loads(p.read_text("utf-8"))
        for lang, b in (d.get("lang") or {}).items():
            if bool(b.get("pros")) != bool(b.get("cons")):
                block("POL-01", f"{p.relative_to(ROOT)}: {lang} has only one side")
    if app.count("mtBadge()") < 3:
        block("POL-13", "app.js: machine translations are no longer badged everywhere they appear")


def check_claims():
    # Claims about Politikch itself live in our own text. Official texts reproduced
    # verbatim (arguments, parliamentary summaries, fetched titles) may quote such
    # phrases about someone else ("a study commissioned by the Confederation").
    official = [g for g in CFG["generatedData"] if g.startswith("data/")]
    for f in tracked():
        if not any(f == p or f.startswith(p) for p in CFG["published"]) or f.startswith("fonts/"):
            continue
        if any(f == g or (g.endswith("/") and f.startswith(g)) for g in official):
            continue
        low = read(f).lower()
        for phrase in CFG["claimPhrases"]["phrases"]:
            for m in re.finditer(re.escape(phrase.lower()), low):
                # "Politikch is NOT an official website" is the disclaimer we want.
                before = low[max(0, m.start() - 30):m.start()]
                if re.search(r"\b(not|no|keine?|nicht|pas|non|n[’']est)\b", before):
                    continue
                block("POL-12", f"{f}: says '{phrase}'")


def registered_images():
    """Photos under images/ with a complete licence record in images/LICENSES.json
    (written by the admin tool): 'images/<id>-800.webp' / '-1600.webp' whose entry
    names a credit and a licence."""
    try:
        reg = json.loads(read("images/LICENSES.json")).get("images", {})
    except Exception:  # noqa: BLE001 — no register yet means no registered images
        return set()
    out = set()
    for iid, e in reg.items():
        if not (isinstance(e, dict) and str(e.get("credit", "")).strip() and str(e.get("licence", "")).strip()):
            continue
        for name in e.get("files", []):
            if re.fullmatch(re.escape(iid) + r"-(800|1600)\.webp", str(name)):
                out.add("images/" + name)
    return out


def check_site_images(registered):
    """LIC-01 / OPS-03: every photo js/site-images.js puts on the site exists, has a
    licence record, and has alt text in all five languages."""
    try:
        m = re.search(r"window\.PCH_IMAGES\s*=\s*(\{.*\})\s*;\s*$", read("js/site-images.js"), re.S)
        lib = json.loads(m.group(1)).get("library", {}) if m else {}
    except Exception:  # noqa: BLE001
        block("LIC-01", "js/site-images.js is not readable")
        return
    for iid, e in lib.items():
        for key in ("w800", "w1600"):
            f = "images/" + str(e.get(key, ""))
            if f not in registered or not (ROOT / f).is_file():
                block("LIC-01", f"js/site-images.js uses {f} without the file or its licence record")
        alt = e.get("alt") or {}
        missing = [l for l in ("en", "de", "fr", "it", "rm") if not str(alt.get(l, "")).strip()]
        if missing:
            block("OPS-03", f"photo {iid} has no alt text in {', '.join(missing).upper()}")


def settings_links(text):
    m = re.search(r"window\.PCH_SETTINGS\s*=\s*(\{.*\})\s*;\s*$", text or "", re.S)
    try:
        return json.loads(m.group(1)).get("parliamentLinks", {}) if m else {}
    except ValueError:
        return None


def check_hosting_and_media(files):
    cfg = read("js/config.js")
    if re.search(r"PAID_PRODUCT_LIVE\s*=\s*true", cfg) and "actions/deploy-pages" in read(".github/workflows/deploy.yml"):
        block("HOST-01", "a paid product can't be switched on while the site is hosted on GitHub Pages")
    if re.search(r"PAID_PRODUCT_LIVE\s*=\s*true", cfg):
        for host, meta in CFG["sources"].items():
            if not host.startswith("_") and meta.get("role") == "fetch" and "ask" in str(meta.get("commercial", "")):
                block("SRC-02", f"a paid product can't go live while {host} requires permission for "
                                "commercial use — record the permission in the source registry first")
    if re.search(r"export const POLL_API = '[^']+'", cfg):
        flag("PRIV-07", "the community poll is switched on (POLL_API) — needs its privacy review")
    registered = registered_images()
    for f in files:
        if re.search(r"\.(pdf|png|jpe?g|gif|webp|svg|mp4|webm|mp3|ico)$", f, re.I):
            if f in registered:          # the owner's own photo, with a licence record (LIC-01)
                continue
            block("SRC-09", f"{f}: media files need a recorded licence before they're added (LIC-01)")
    check_site_images(registered)
    for f in ["index.html"] + js_files():
        if re.search(r"<(iframe|embed|object)\b", read(f), re.I):
            block("SRC-09", f"{f}: embeds third-party content")
    if not (ROOT / "fonts" / "OFL.txt").exists():
        block("LIC-01", "fonts/OFL.txt (the fonts' licence) is missing")
    for f in [f for f in files if f.startswith(("scripts/", ".github/", "js/"))]:
        if re.search(r"\bMAINTENANCE_MODE\b", read(f)) and f not in (
                ".github/workflows/deploy.yml", "scripts/check.py", "scripts/guardrails/config.json"):
            block("SEC-10", f"{f}: automation must not touch the maintenance switch")
    if re.search(r"(rm|touch|git\s+rm)\s+[^\n]*MAINTENANCE_MODE", read(".github/workflows/deploy.yml")):
        block("SEC-10", "deploy.yml changes the maintenance switch")


# =========================================================================
# Change-based checks — what changed since --base, and its sign-offs
# =========================================================================
def resolve_base(arg):
    def ok(ref):
        return subprocess.run(["git", "rev-parse", "--verify", "-q", ref + "^{commit}"],
                              cwd=ROOT, capture_output=True).returncode == 0
    if arg and not re.fullmatch(r"0+", arg):
        if ok(arg):
            return arg
        notes.append(f"base {arg} not found (force-push or shallow clone) — comparing with HEAD~1")
    for ref in (() if arg else ("origin/main",)) + ("HEAD~1",):
        if ok(ref):
            return ref
    return None


def changes(base):
    names = set(git("diff", "--name-only", base).splitlines())
    names |= set(git("ls-files", "--others", "--exclude-standard").splitlines())
    deleted = set(git("diff", "--name-only", "--diff-filter=D", base).splitlines())
    return sorted(names), deleted


def added_lines(base, f):
    if f in git("ls-files", "--others", "--exclude-standard").splitlines():
        return read(f).splitlines()
    out = git("diff", "-U0", base, "--", f)
    return [ln[1:] for ln in out.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


def token_bump_only(base, f):
    """True if a file's only change is the cache-busting ?v= token (no sign-off needed)."""
    if f in git("ls-files", "--others", "--exclude-standard").splitlines():
        return False
    out = git("diff", "-U0", base, "--", f)
    norm = lambda ln: re.sub(r"\?v=[\w.\-]+", "?v=", ln[1:])
    plus = sorted(norm(ln) for ln in out.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
    minus = sorted(norm(ln) for ln in out.splitlines() if ln.startswith("-") and not ln.startswith("---"))
    return bool(plus) and plus == minus


def approvals(base):
    msgs = git("log", f"{base}..HEAD", "--format=%B%x00", check=False)
    return {m.group(1) for m in re.finditer(r"(?mi)^Approved-Rule:\s*([A-Z]+-\d+|UNKNOWN)\b", msgs)}


def bot_only(base):
    authors = set(git("log", f"{base}..HEAD", "--format=%an", check=False).splitlines())
    return bool(authors) and authors == {BOT_NAME}


def next_ballot(today):
    try:
        inits = json.loads(read("data/initiatives.json"))["initiatives"]
    except Exception:  # noqa: BLE001
        return None
    dates = sorted({i["voteDate"] for i in inits if i.get("voteDate") and i["voteDate"] >= today.isoformat()})
    return dt.date.fromisoformat(dates[0]) if dates else None


def check_changes(base, worktree_dirty, data_job=False):
    files, deleted = changes(base)
    bot = data_job or (bot_only(base) and not worktree_dirty)
    trig = CFG["triggers"]
    for f in files:
        if f not in deleted and token_bump_only(base, f):
            continue
        rules = [r for pat, rs in trig["flag"] for r in rs if match(f, pat)]
        for r in rules:
            flag(r, f"{f} changed")
        if not rules and not any(match(f, pat) for pat in trig["reviewOnly"]):
            flag("UNKNOWN", f"{f} matches no guardrail rule (default: flagged, not assumed safe)")
        if not bot and any(f == g or (g.endswith("/") and f.startswith(g)) for g in CFG["generatedData"]):
            flag("OPS-04", f"{f} is generated by the data job but was edited by hand")
    # POL-05: banned words in text this change adds to editorial files.
    for f in files:
        if f not in CFG["editorialFiles"] or f in deleted:
            continue
        added = "\n".join(added_lines(base, f))
        for lang, words in CFG["bannedWords"].items():
            if lang.startswith("_"):
                continue
            for w in words:
                if re.search(r"(?i)(?<![\wÀ-ÿ])" + re.escape(w) + r"(?![\wÀ-ÿ])", added):
                    flag("POL-05", f"{f}: adds '{w}' ({lang}) — confirm it is neutral")
    # SEC-06: the deploy allowlist / file-type guard may only change with sign-off.
    if ".github/workflows/deploy.yml" in files:
        flag("SEC-06", "deploy.yml changed — confirm the allowlist and file-type guard still publish runtime files only")
    # POL-03: which official final vote a vote page shows is a result shown on the site.
    if "js/site-settings.js" in files:
        old = git("show", f"{base}:js/site-settings.js", check=False)
        if settings_links(old) != settings_links(read("js/site-settings.js")):
            flag("POL-03", "the Parliament final-vote links in js/site-settings.js changed — check each one against parlament.ch")
    # PRIV-04 / SEC-03: privacy text or CSP edited.
    if "data/i18n.json" in files and any('"privacy.' in ln for ln in added_lines(base, "data/i18n.json")):
        flag("PRIV-04", "Privacy-page text changed — confirm it still matches what the code does")
    if "index.html" in files and any("Content-Security-Policy" in ln for ln in added_lines(base, "index.html")):
        flag("SEC-03", "the Content-Security-Policy changed")
    # POL-09: quiet period before a federal ballot.
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=2))).date()   # Swiss time (CEST; close enough for a date)
    ballot = next_ballot(today)
    if ballot and (ballot - today).days <= CFG["quietPeriodDays"] and not bot:
        maintenance = (ROOT / "MAINTENANCE_MODE").exists()
        published = [f for f in files if any(f == p or f.startswith(p) for p in CFG["published"])]
        if "MAINTENANCE_MODE" in deleted:
            flag("POL-09", f"the site goes live again {(ballot - today).days} day(s) before the {ballot} ballot — "
                           "everything changed while it was off is published at once")
        elif published and not maintenance:
            flag("POL-09", f"{len(published)} published file(s) change {(ballot - today).days} day(s) before the "
                           f"{ballot} ballot — allowed only for a correction or privacy fix (say which)")
    return files


# =========================================================================
def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="compare against this git ref (default: origin/main)")
    ap.add_argument("--strict", action="store_true", help="unsigned flags fail too (CI, pre-push)")
    ap.add_argument("--update-sink-baseline", action="store_true")
    ap.add_argument("--data-job", action="store_true",
                    help="the weekly data job's own refresh (generated data only, no quiet-period flag)")
    args = ap.parse_args(argv)

    files = tracked() + [f for f in git("ls-files", "--others", "--exclude-standard").splitlines() if (ROOT / f).is_file()]
    check_validator()
    check_js_syntax()
    check_sinks(update=args.update_sink_baseline)
    check_csp()
    check_third_party_loads()
    check_dangerous_js()
    check_secrets(files)
    check_deploy_guard()
    check_workflows()
    check_requirements()
    check_fetchers()
    check_hosts()
    check_attribution()
    check_privacy_code()
    check_personal_data(files)
    check_data_links()
    check_licensing()
    check_both_sides()
    check_claims()
    check_hosting_and_media(files)

    base = resolve_base(args.base)
    approved, changed = set(), []
    if base:
        dirty = bool(git("status", "--porcelain").strip())
        changed = check_changes(base, dirty, data_job=args.data_job)
        approved = approvals(base)
    else:
        notes.append("no base commit found — change-based checks skipped")

    # ---- report ----
    print(f"Politikch guardrails — {len(changed)} changed file(s) vs {base or 'nothing'}\n")
    for rule, msg in blocks:
        print(f"  ✗ BLOCK {rule}: {msg}")
    unsigned = {r: m for r, m in flags.items() if r not in approved}
    for rule, msgs in sorted(flags.items()):
        state = "signed off" if rule in approved else "NEEDS SIGN-OFF"
        for msg in msgs:
            print(f"  {'✓' if rule in approved else '!'} FLAG  {rule} ({state}): {msg}")
    for n in notes:
        print(f"  · {n}")
    if unsigned:
        print("\nTo sign off, the owner adds one line per rule to a commit message in this change:")
        for r in sorted(unsigned):
            print(f"    Approved-Rule: {r} — <why this is fine>")
    failed = bool(blocks) or (args.strict and bool(unsigned))
    print("\n" + ("FAILED" if failed else ("PASSED" if not unsigned else "PASSED (flags need sign-off before pushing)")))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
