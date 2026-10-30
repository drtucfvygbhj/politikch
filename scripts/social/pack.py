#!/usr/bin/env python3
"""The week's X posts in one place, to schedule by hand on x.com. Posts nothing.

  python3 scripts/social/pack.py                 # the coming week (or this week's results)
  python3 scripts/social/pack.py --week 2026-11-02 --no-render
  python3 scripts/social/pack.py --week 2026-11-02 --rebuild

Run it on the weekend (double-click "Prepare Social Week.command"). The output is
social-out/x-pack/<monday>/ (git-ignored): pack.html with every post in time
order, one tab per language, and one folder per language with the images, named
in time order for X's file picker.

A pack is planned once. Running it again opens the same posts, so what is already
scheduled stays right, and only adds what has come in since: run it again after
Monday's data job when there was a ballot on Sunday, for the results.
--rebuild plans the week again from the same starting point.

While the site is offline or the wording is a draft, a pack is practice: it moves
no cooldowns on, and is planned again once both are settled.

Not in the pack: daily votes (not known yet on the weekend) and corrections (at once).
Rendering needs playwright (scripts/requirements-social.txt) and Chrome.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan  # noqa: E402
import sitedata as sd  # noqa: E402
from dry_run import OUT, next_monday  # noqa: E402

PACKS = OUT / "x-pack"
LABEL = {"results": "Results", "runup_overview": "Ballot: overview", "runup_recs": "Ballot: recommendations",
         "runup_args": "Ballot: arguments", "runup_money": "Ballot: campaign money", "spotlight": "Spotlight",
         "pipeline": "Monthly pipeline", "session_summary": "Session summary", "seats": "Seats changed",
         "final_vote": "Final vote", "how": "How it works", "party": "Party in figures", "glossary": "Glossary",
         "canton": "Canton", "history": "Vote history"}
PAGE_JS = """
var week = document.body.dataset.week, tabKey = 'politikch-x-pack-tab';
function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function save(k, v) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) {} }
function count() {
  document.querySelectorAll('[data-tab]').forEach(function (b) {
    var lang = b.dataset.tab, all = document.querySelectorAll('#' + lang + ' .post');
    b.querySelector('span').textContent = document.querySelectorAll('#' + lang + ' .post.done').length + ' of ' + all.length;
  });
}
function show(lang) {
  document.querySelectorAll('.lang').forEach(function (s) { s.hidden = s.id !== lang; });
  document.querySelectorAll('[data-tab]').forEach(function (b) { b.setAttribute('aria-pressed', b.dataset.tab === lang); });
  save(tabKey, lang);
}
document.querySelectorAll('[data-tab]').forEach(function (b) { b.onclick = function () { show(b.dataset.tab); }; });
document.querySelectorAll('.post').forEach(function (p) {
  var box = p.querySelector('input'), key = 'politikch-x-pack:' + week + ':' + p.dataset.id;
  box.checked = load(key) === '1';
  p.classList.toggle('done', box.checked);
  box.onchange = function () { p.classList.toggle('done', box.checked); save(key, box.checked ? '1' : null); count(); };
  var btn = p.querySelector('button'), text = p.querySelector('textarea');
  btn.onclick = function () {
    function ok() { btn.textContent = 'Copied'; setTimeout(function () { btn.textContent = 'Copy text'; }, 1500); }
    function old() { text.select(); document.execCommand('copy'); ok(); }
    if (navigator.clipboard) navigator.clipboard.writeText(text.value).then(ok, old); else old();
  };
});
var first = document.querySelector('[data-tab]').dataset.tab, last = load(tabKey);
show(last && document.getElementById(last) ? last : first);
count();
"""
PAGE_CSS = """
body { font: 16px/1.45 system-ui, sans-serif; margin: 0 auto; padding: 16px; max-width: 980px; background: #fff; color: #161616; }
h1 { font-size: 24px; margin: 0 0 4px; } h2 { font-size: 18px; margin: 28px 0 8px; border-bottom: 2px solid #161616; padding-bottom: 4px; }
.how, .path { color: #5F5E5A; font-size: 14px; margin: 4px 0; overflow-wrap: anywhere; }
.warn { background: #F2E5E7; color: #7A1C2A; border-left: 6px solid #7A1C2A; padding: 8px 12px; margin: 8px 0; font-weight: 600; }
.note { background: #F6F4F0; border-left: 6px solid #B9B5AC; padding: 8px 12px; margin: 8px 0; }
.tabs { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; position: sticky; top: 0; background: #fff; padding: 8px 0; }
.tabs button { font: inherit; font-weight: 600; padding: 8px 12px; border: 2px solid #161616; background: #fff; color: #161616; cursor: pointer; }
.tabs button[aria-pressed=true] { background: #161616; color: #fff; }
.tabs span { font-weight: 400; margin-left: 6px; }
.post { border: 1px solid #DCDAD3; padding: 12px; margin: 10px 0; }
.post.done { opacity: .45; }
.when { font-size: 20px; font-weight: 700; } .kind { color: #5F5E5A; margin-left: 8px; }
textarea { width: 100%; box-sizing: border-box; font: inherit; height: 104px; margin: 8px 0; padding: 8px; border: 1px solid #DCDAD3; resize: vertical; }
.imgs { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.imgs img { height: 180px; max-width: 100%; border: 1px solid #DCDAD3; cursor: grab; }
.row { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
.row button { font: inherit; font-weight: 600; padding: 8px 14px; border: 0; background: #534AB7; color: #fff; cursor: pointer; }
"""


def target_week(today, packs=PACKS):
    """This week while a ballot's results are still to come, otherwise the coming week."""
    this = today - dt.timedelta(days=today.weekday())
    if today.weekday() < 5 and this - dt.timedelta(days=1) in plan.ballots():
        pack = load_pack(packs / this.isoformat())
        if not pack or not any(p["type"] == "results" for p in pack["posts"]):
            return this
    return next_monday(today)


def load_pack(folder):
    f = folder / "posts.json"
    return json.loads(f.read_text("utf-8")) if f.exists() else None


def make_post(slot, folder, renderer):
    """One slot in every language: the text and the images to attach."""
    time = slot.time.replace(":", "")
    post = {"id": f"{slot.day}-{time}-{slot.item.type}", "day": slot.day.isoformat(), "time": slot.time,
            "type": slot.item.type, "key": slot.item.key, "langs": {}}
    for lang in sd.LANGS:
        ig, x = plan.build(slot.item, lang)
        pages = plan.x_pages(x or ig)
        entry = {"text": plan.x_text(x or ig), "images": [], "problem": ""}
        if pages is None:
            entry["problem"] = (f"{len(ig.pages)} pages don't fit X's 4 images, and leaving a page out could drop a "
                                "proposal. Not prepared: decide by hand.")
        for i, page in enumerate(pages or [], 1):
            name = f"{lang}/{slot.day}_{time}_{i}.png"
            if renderer:
                (folder / lang).mkdir(parents=True, exist_ok=True)
                (folder / ".cards").mkdir(exist_ok=True)
                renderer.png(page, lang, folder / ".cards" / f"{slot.day}_{time}_{i}_{lang}.html", folder / name)
            entry["images"].append(name)
        post["langs"][lang] = entry
    return post


def build_week(monday, folder, renderer, state_path, practice=False):
    """Plan the week once, from the state saved before it, and move the state on (not for practice)."""
    before = folder / "state-before.json"
    if before.exists():
        state = json.loads(before.read_text("utf-8"))
    else:
        state = json.loads(state_path.read_text("utf-8")) if state_path.exists() else {}
        before.write_text(json.dumps(state, indent=1, default=str), "utf-8")
    slots = plan.plan_week(monday, state, weekend=True)
    posts = [make_post(s, folder, renderer) for s in slots]
    later = [p for p in folder.parent.glob("*/posts.json") if p.parent.name > monday.isoformat()]
    if not later and not practice:
        state_path.write_text(json.dumps(state, indent=1, default=str), "utf-8")
    return posts


def add_results(monday, pack, folder, renderer):
    """Monday after a ballot, once the data job has brought the results."""
    if any(p["type"] == "results" for p in pack["posts"]):
        return False
    item = plan.results_item(monday)
    if not item:
        return False
    pack["posts"].append(make_post(plan.Slot(monday, plan.RESULTS_TIME, item), folder, renderer))
    pack["posts"].sort(key=lambda p: (p["day"], p["time"]))
    return True


def notices(monday, pack, site_offline):
    warn, note = [], []
    if site_offline:
        warn.append("The site is in maintenance mode, so the links lead to the notice page. Don't schedule yet.")
    if not sd.strings().get("_approved"):
        warn.append("The wording in strings.json is a draft you haven't approved yet (POL-13). Don't schedule yet.")
    if monday - dt.timedelta(days=1) in plan.ballots() and not any(p["type"] == "results" for p in pack["posts"]):
        note.append("Results aren't in this pack yet. Monday is kept free for them: run this again after "
                    "Monday's data job, and they appear here for each language.")
    if any(monday - dt.timedelta(days=7) <= dt.date.fromisoformat(s["end"]) < monday and s.get("voteCount")
           for s in sd.site()["sessionsIndex"]["sessions"]):
        note.append("A session has just ended. Its summary comes in next weekend's pack, once its last day is in the data.")
    return warn, note


def day_title(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d:%a} {d.day} {d:%b %Y}"


def post_html(post, lang):
    entry = post["langs"][lang]
    e = escape
    late = " · post right away if that has passed" if post["type"] == "results" else ""
    imgs = "".join(f'<img src="{e(p, True)}" alt="Page {i} of the post" title="{e(Path(p).name, True)}">'
                   for i, p in enumerate(entry["images"], 1))
    problem = f'<div class="warn">{e(entry["problem"])}</div>' if entry["problem"] else ""
    return (f'<article class="post" data-id="{e(post["id"], True)}"><div><span class="when">{e(post["time"])}</span>'
            f'<span class="kind">{e(LABEL.get(post["type"], post["type"]))}{e(late)}</span></div>{problem}'
            f'<textarea readonly lang="{lang}" aria-label="Post text">{e(entry["text"])}</textarea>'
            f'<div class="imgs">{imgs}</div><div class="row"><button type="button">Copy text</button>'
            f'<label><input type="checkbox"> Scheduled</label></div></article>')


def page_html(monday, pack, folder, site_offline=False):
    warn, note = notices(monday, pack, site_offline)
    parts = ["<!doctype html>", '<html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             f"<title>X posts {monday}</title><style>{PAGE_CSS}</style></head>",
             f'<body data-week="{monday}"><h1>X posts for the week of {monday.day} {monday:%B %Y}</h1>',
             '<p class="how">For each post: copy the text, paste it into x.com, drag in the images, schedule it '
             "for the date and time shown, tick Scheduled. Switch to that language's account first.</p>",
             f'<p class="path">Images, in time order, if dragging doesn\'t work: {escape(str(folder))}</p>']
    parts += [f'<div class="warn">{escape(w)}</div>' for w in warn]
    parts += [f'<div class="note">{escape(n)}</div>' for n in note]
    parts.append('<div class="tabs">' + "".join(f'<button type="button" data-tab="{l}">{l.upper()}<span></span></button>'
                                                for l in sd.LANGS) + "</div>")
    if not pack["posts"]:
        parts.append('<p class="note">No posts planned for this week.</p>')
    for lang in sd.LANGS:
        parts.append(f'<section class="lang" id="{lang}">')
        day = None
        for post in pack["posts"]:
            if post["day"] != day:
                day = post["day"]
                parts.append(f"<h2>{escape(day_title(day))}</h2>")
            parts.append(post_html(post, lang))
        parts.append("</section>")
    parts.append(f"<script>{PAGE_JS}</script></body></html>")
    return "\n".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", help="the Monday the week starts (default: the coming week, or this week's results)")
    ap.add_argument("--rebuild", action="store_true", help="plan the week again from the same starting point")
    ap.add_argument("--no-render", action="store_true", help="skip the images")
    ap.add_argument("--site-offline", action="store_true", help="show the maintenance warning")
    ap.add_argument("--open", action="store_true", help="open the pack in the browser")
    args = ap.parse_args(argv)

    monday = dt.date.fromisoformat(args.week) if args.week else target_week(dt.date.today())
    if monday.weekday() != 0:
        ap.error(f"{monday} is not a Monday")
    folder = PACKS / monday.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    pack = None if args.rebuild else load_pack(folder)
    practice = bool(args.site_offline or not sd.strings().get("_approved"))
    if pack and pack.get("practice") and not practice:
        pack = None

    renderer = None
    if not args.no_render:
        from render import Renderer
        renderer = Renderer().__enter__()
    try:
        if pack is None:
            for old in [folder / l for l in sd.LANGS] + [folder / ".cards"]:
                shutil.rmtree(old, ignore_errors=True)
            pack = {"monday": monday.isoformat(), "practice": practice,
                    "posts": build_week(monday, folder, renderer, PACKS / "state.json", practice)}
        added = add_results(monday, pack, folder, renderer)
    finally:
        if renderer:
            renderer.__exit__(None, None, None)

    (folder / "posts.json").write_text(json.dumps(pack, indent=1, ensure_ascii=False), "utf-8")
    page = folder / "pack.html"
    page.write_text(page_html(monday, pack, folder, args.site_offline), "utf-8")
    n = len(pack["posts"])
    print(f"{n} post(s) per language, {n * len(sd.LANGS)} in all{' (results added)' if added else ''} → {page}")
    if args.open:
        subprocess.run(["open", str(page)], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
