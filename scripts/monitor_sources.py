#!/usr/bin/env python3
"""Weekly check that our sources still allow what we do (GUARDRAILS.md SRC-10, HOST-04).

Runs first in the weekly data job. If a source has changed the terms we rely on,
the job stops before fetching anything, so nothing is published under terms
that no longer allow it:

  * the opendata.swiss licence code (terms_open / terms_by / terms_ask) of every
    dataset in the source registry must equal the one recorded there;
  * the robots.txt of every host we fetch from must be unchanged since it was
    last reviewed (snapshot in scripts/guardrails/robots-snapshot.json).

It also warns (without stopping anything) when a site certificate expires within
21 days or can't be checked, or a licence couldn't be read. In CI the warnings are
also written to $MONITOR_WARNINGS_FILE, from which the workflow opens an issue.

  python3 scripts/monitor_sources.py            # check (exit 1 on drift)
  python3 scripts/monitor_sources.py --update   # accept the current robots.txt files
                                                # after reviewing them (flagged change)
"""
import hashlib
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GR = ROOT / "scripts" / "guardrails"
CFG = json.loads((GR / "config.json").read_text("utf-8"))
SNAPSHOT = GR / "robots-snapshot.json"
UA = "Politikch-source-monitor/1.0 (+https://politikch.ch; contact.form@politikch.ch)"
CKAN = "https://ckan.opendata.swiss/api/3/action/package_show?id="
CKAN_DELAY = 10          # ckan.opendata.swiss robots.txt Crawl-delay
MAX_BYTES = 2 * 1024 * 1024
CERT_WARN_DAYS = 21

drift, warnings = [], []


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(MAX_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def sources():
    return {h: m for h, m in CFG["sources"].items() if not h.startswith("_")}


def check_licences():
    first = True
    for host, meta in sources().items():
        if not meta.get("ckan"):
            continue
        if not first:
            time.sleep(CKAN_DELAY)
        first = False
        try:
            status, body = get(CKAN + meta["ckan"])
            res = json.loads(body)["result"]["resources"] if status == 200 else None
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{host}: couldn't read the licence of '{meta['ckan']}' ({e}) — not verified this week")
            continue
        if res is None:
            drift.append(f"{host}: dataset '{meta['ckan']}' is gone from opendata.swiss (HTTP {status})")
            continue
        codes = sorted({(r.get("license") or r.get("rights") or "").rsplit("#", 1)[-1] for r in res} - {""})
        if codes != sorted(meta["terms"]):
            drift.append(f"{host}: licence of '{meta['ckan']}' changed from {meta['terms']} to {codes}")


def robots_now():
    out = {}
    for host, meta in sources().items():
        if meta.get("role") != "fetch":
            continue
        try:
            status, body = get(f"https://{host}/robots.txt")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{host}: robots.txt unreachable ({e})")
            continue
        text = body if status == 200 and "<html" not in body[:300].lower() else ""
        norm = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#"))
        out[host] = {"status": status if text else "none", "sha": hashlib.sha256(norm.encode()).hexdigest()[:16],
                     "text": norm[:2000]}
    return out


def check_robots(update):
    current = robots_now()
    if update:
        SNAPSHOT.write_text(json.dumps({"_about": "robots.txt of every fetched host, as last reviewed. "
                                        "Regenerate with `python3 scripts/monitor_sources.py --update` after "
                                        "reviewing the change (flagged: PROC-05).",
                                        "reviewed": datetime.now(timezone.utc).date().isoformat(),
                                        "hosts": current}, indent=1) + "\n", "utf-8")
        print(f"robots.txt snapshot updated ({len(current)} hosts)")
        return
    known = json.loads(SNAPSHOT.read_text("utf-8"))["hosts"] if SNAPSHOT.exists() else {}
    for host, now in current.items():
        was = known.get(host)
        if was is None:
            drift.append(f"{host}: robots.txt never reviewed — run with --update after reviewing it")
        elif was["sha"] != now["sha"]:
            drift.append(f"{host}: robots.txt changed —\n      was: {was['text'][:300]!r}\n      now: {now['text'][:300]!r}")


def check_certs():
    for dom in CFG.get("monitorDomains", []):
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((dom, 443), timeout=15) as sock:
                with ctx.wrap_socket(sock, server_hostname=dom) as s:
                    exp = datetime.strptime(s.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days = (exp - datetime.now(timezone.utc)).days
            if days < CERT_WARN_DAYS:
                warnings.append(f"{dom}: certificate expires in {days} days")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{dom}: HTTPS certificate problem ({type(e).__name__}: {str(e)[:100]})")


def main(argv):
    update = "--update" in argv
    check_robots(update)
    if update:
        return 0
    check_licences()
    check_certs()
    for w in warnings:
        print(f"  ! {w}")
        print(f"::warning::{w}")
    out = os.environ.get("MONITOR_WARNINGS_FILE")
    if out:
        Path(out).write_text("".join(f"- {w}\n" for w in warnings), "utf-8")
    if drift:
        print("\nSource terms changed — the data job stops so nothing is published under terms "
              "we haven't reviewed (GUARDRAILS.md SRC-10):")
        for d in drift:
            print(f"  ✗ {d}")
            print(f"::error::{d.splitlines()[0]}")
        print("\nReview the change. If it's fine, update scripts/guardrails/config.json (licence) or run "
              "`python3 scripts/monitor_sources.py --update` (robots.txt), with sign-off.")
        return 1
    print("Source terms unchanged ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
