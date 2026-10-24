#!/usr/bin/env python3
"""Plan and render a week of social posts locally, for review. Posts nothing.

  python3 scripts/social/dry_run.py --week 2026-09-28
  python3 scripts/social/dry_run.py --week 2026-09-28 --ticker-day 2026-10-01 --no-render
  python3 scripts/social/dry_run.py --week 2026-10-19 --langs de,fr

Output goes to social-out/<monday>/ (git-ignored): one folder per slot and
language with the PNG pages, the Instagram caption and the X text, plus an
index.html to look through. --save-state remembers what was "posted", so the
next week's evergreen posts move on (social-out/state.json).

Rendering needs playwright (scripts/requirements-social.txt) and Chrome.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan  # noqa: E402
import sitedata as sd  # noqa: E402

OUT = sd.ROOT / "social-out"


def next_monday(today=None):
    today = today or dt.date.today()
    return today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", help="the Monday the week starts (default: next Monday)")
    ap.add_argument("--langs", default=",".join(sd.LANGS))
    ap.add_argument("--state", default=str(OUT / "state.json"))
    ap.add_argument("--save-state", action="store_true", help="remember this week's posts for the next run")
    ap.add_argument("--ticker-day", action="append", default=[], help="add the daily-votes post for this sitting day (YYYY-MM-DD)")
    ap.add_argument("--correction", help="JSON file with a correction to add (date, wrong, right, source)")
    ap.add_argument("--no-render", action="store_true", help="plan and write captions only")
    args = ap.parse_args(argv)

    monday = dt.date.fromisoformat(args.week) if args.week else next_monday()
    if monday.weekday() != 0:
        ap.error(f"{monday} is not a Monday")
    langs = [l for l in args.langs.split(",") if l in sd.LANGS]
    state_path = Path(args.state)
    state = json.loads(state_path.read_text("utf-8")) if state_path.exists() else {}

    extra = []
    for d in args.ticker_day:
        day = sd.ticker_day(d)
        if not day:
            print(f"no ticker data for {d} on the ticker-data branch", file=sys.stderr)
            continue
        extra.append(plan.Item("daily_votes", 2, dt.date.fromisoformat(d), f"daily:{d}", {"day": day, "times": ["19:30"]}))
    if args.correction:
        info = json.loads(Path(args.correction).read_text("utf-8"))
        extra.append(plan.Item("correction", 6, monday, f"correction:{info['date']}", {"info": info}))

    slots = plan.plan_week(monday, state, extra)
    week = OUT / monday.isoformat()
    week.mkdir(parents=True, exist_ok=True)

    renderer = None
    if not args.no_render:
        from render import Renderer
        renderer = Renderer().__enter__()
    index, summary = [], [f"# Social posts, week of {monday}", ""]
    try:
        for n, slot in enumerate(slots, 1):
            name = f"{n:02d}-{slot.day}-{slot.time.replace(':', '')}-{slot.item.type}"
            summary.append(f"- {slot.day} {sd.S('en')['weekdays'][slot.day.weekday()][:3]} {slot.time} · "
                           f"P{slot.item.priority} · {slot.item.type} · {slot.item.key}")
            for lang in langs:
                ig, x = plan.build(slot.item, lang)
                d = week / name / lang
                d.mkdir(parents=True, exist_ok=True)
                (d / "caption.txt").write_text(ig.caption + "\n", "utf-8")
                (d / "x.txt").write_text(plan.x_text(x or ig) + "\n", "utf-8")
                pages = []
                if renderer:
                    for i, page in enumerate(ig.pages, 1):
                        renderer.png(page, lang, d / f"page-{i}.html", d / f"page-{i}.png")
                        pages.append(f"{name}/{lang}/page-{i}.png")
                    if x:
                        renderer.png(x.pages[0], lang, d / "x.html", d / "x.png")
                        pages.append(f"{name}/{lang}/x.png")
                index.append((slot, lang, ig, pages))
    finally:
        if renderer:
            renderer.__exit__(None, None, None)

    (week / "plan.md").write_text("\n".join(summary) + "\n", "utf-8")
    html = ["<!doctype html><meta charset='utf-8'><title>Social posts</title>",
            "<style>body{font-family:system-ui;margin:24px}img{height:420px;margin:4px;border:1px solid #ddd}"
            "pre{white-space:pre-wrap;background:#f6f4f0;padding:8px;max-width:900px}</style>",
            f"<h1>Week of {monday}</h1>"]
    for slot, lang, ig, pages in index:
        html.append(f"<h2>{slot.day} {slot.time} · {escape(slot.item.type)} · {lang.upper()}</h2>")
        html.append("".join(f"<img src='{escape(p)}'>" for p in pages))
        html.append(f"<pre>{escape(ig.caption)}</pre>")
    (week / "index.html").write_text("\n".join(html), "utf-8")
    if args.save_state:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=1, default=str), "utf-8")
    print("\n".join(summary))
    print(f"\n{len(slots)} slot(s) × {len(langs)} language(s) → {week}/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
