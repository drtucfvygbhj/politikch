#!/usr/bin/env python3
"""Replay tests for the social planner and cards (stdlib only; no browser needed).

  python3 scripts/social/test_social.py

Replays real weeks from the site's data: the results week after the
27 September 2026 ballot, the autumn session's summary and final votes, the
run-up to 29 November 2026 (including its quiet period), a 100-day spotlight
and a quiet summer week. Every post is built in all four languages and checked
for the language's domain and disclaimer, leftover placeholders, banned words
(POL-05), 'live' wording (POL-14) and the DeepL badge (POL-13).
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cards  # noqa: E402
import plan  # noqa: E402
import sitedata as sd  # noqa: E402

D = dt.date.fromisoformat
CFG = json.loads((sd.ROOT / "scripts" / "guardrails" / "config.json").read_text("utf-8"))
LIVE = {"de": ["live", "Echtzeit"], "fr": ["en direct", "temps réel", "live"], "it": ["in diretta", "tempo reale", "live"],
        "en": ["live", "real-time", "real time"]}


def run_weeks(mondays, state=None):
    state = state if state is not None else {}
    return {m: plan.plan_week(D(m), state) for m in mondays}, state


def text_of(html):
    return re.sub(r"<[^>]+>", " ", html)


class Planner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.weeks, cls.state = run_weeks(["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26",
                                          "2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"])

    def slots(self, monday, typ):
        return [s for s in self.weeks[monday] if s.item.type == typ]

    def test_results_monday_after_ballot(self):
        r = self.slots("2026-09-28", "results")
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0].day, r[0].time), (D("2026-09-28"), "07:30"))
        self.assertEqual(r[0].item.args["votes"], ["vote-20260927-6880", "vote-20260927-6890"])   # every proposal (POL-01)

    def test_runup_dates(self):
        expected = {"2026-10-19": ("runup_overview", "2026-10-19"), "2026-10-27": ("runup_recs", "2026-10-27"),
                    "2026-11-04": ("runup_args", "2026-11-04"), "2026-11-12": ("runup_money", "2026-11-12"),
                    "2026-11-23": ("runup_overview", "2026-11-23")}
        got = {s.day.isoformat(): (s.item.type, s.day.isoformat()) for w in self.weeks.values() for s in w if s.item.type.startswith("runup")}
        self.assertEqual(got, expected)
        reminder = [s for w in self.weeks.values() for s in w if s.item.key.endswith(":6")][0]
        self.assertTrue(reminder.item.args["sunday"])

    def test_quiet_period(self):
        ballot = D("2026-11-29")
        for w in self.weeks.values():
            for s in w:
                b = s.item.args.get("ballot")
                if b == ballot and 0 < (ballot - s.day).days <= plan.QUIET_DAYS:
                    self.assertTrue(s.item.type == "runup_overview" and s.item.args["sunday"], s.item.key)

    def test_spotlight_at_100_days(self):
        sp = self.slots("2026-11-02", "spotlight")
        self.assertEqual([(s.day, s.item.args["vote"]) for s in sp], [(D("2026-11-04"), "initiative-574")])

    def test_session_summary_then_final_votes(self):
        summ = self.slots("2026-10-05", "session_summary")
        self.assertEqual([s.day for s in summ], [D("2026-10-06")])
        firsts = [s for w in self.weeks.values() for s in w if s.item.type == "final_vote"]
        self.assertTrue(firsts and all(s.day > D("2026-10-06") for s in firsts))
        order = [s.item.args["n"] for s in sorted(firsts, key=lambda s: (s.day, s.time))]
        self.assertEqual(order, sorted(order))      # official order, no skipping (POL-16)

    def test_one_post_per_slot(self):
        for w in self.weeks.values():
            keys = [(s.day, s.time) for s in w]
            self.assertEqual(len(keys), len(set(keys)))

    def test_quiet_week_is_full(self):
        weeks, _ = run_weeks(["2026-07-20"])
        w = weeks["2026-07-20"]
        self.assertEqual(len(w), 7)                  # a week without events: one evergreen post a day
        self.assertTrue(all(s.item.priority == 1 for s in w))
        kinds = [s.item.type for s in w]
        self.assertTrue(all(kinds.count(k) <= plan.WEEKLY_CAP[k] for k in set(kinds)) or len(set(kinds)) == 1)


class Cards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        weeks, _ = run_weeks(["2026-09-28", "2026-10-05", "2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09", "2026-11-23"])
        cls.items = [s.item for w in weeks.values() for s in w]
        day = sd.ticker_day("2026-10-01")
        if day:
            cls.items.append(plan.Item("daily_votes", 2, D("2026-10-01"), "daily", {"day": day}))
        cls.items.append(plan.Item("correction", 6, D("2026-10-01"), "c", {"info": {
            "date": "2026-09-28", "source": "VoteInfo",
            "wrong": {l: "x" for l in sd.LANGS}, "right": {l: "y" for l in sd.LANGS}}}))
        cls.items.append(plan.Item("seats", 2, D("2026-10-01"), "s", {"changes": {"SVP": (61, 62)}}))
        cls.posts = [(it, lang, plan.build(it, lang)) for it in cls.items for lang in sd.LANGS]

    def test_every_type_built(self):
        types = {it.type for it in self.items}
        for t in ("results", "runup_overview", "runup_recs", "runup_args", "runup_money", "spotlight", "pipeline",
                  "session_summary", "final_vote", "how", "party", "correction", "seats"):
            self.assertIn(t, types)

    def test_domain_and_disclaimer_on_every_page(self):
        for it, lang, (ig, x) in self.posts:
            s = sd.S(lang)
            for page in ig.pages + (x.pages if x else []):
                self.assertIn(f"{s['domain']} · {s['disclaimer']}", page, f"{it.type} {lang}")
                self.assertIn('class="brand">Politikch<', page)

    def test_no_placeholders_or_markup_from_data(self):
        for it, lang, (ig, x) in self.posts:
            for page in ig.pages:
                body = text_of(page)
                self.assertNotRegex(body, r"\{[a-z]+\}", f"{it.type} {lang}: unfilled placeholder")
                self.assertNotIn("<script", page.lower())
            self.assertNotRegex(ig.caption, r"\{[a-z]+\}")
            self.assertIn(ig.url, ig.caption)

    def test_pager(self):
        for it, lang, (ig, _) in self.posts:
            n = len(ig.pages)
            for i, page in enumerate(ig.pages, 1):
                if n > 1:
                    self.assertIn(f">{i} / {n}<", page)
                self.assertEqual("arrow" in page, i < n, f"{it.type} {lang} page {i}")

    def test_x_text_fits(self):
        for it, lang, (ig, x) in self.posts:
            t = plan.x_text(x or ig)
            body, link = t.rsplit("\n", 1)
            self.assertLessEqual(len(body) + 1 + 23, 280)

    def test_machine_translation_badged(self):
        fv = [(lang, ig) for it, lang, (ig, _) in self.posts if it.type == "final_vote"]
        for lang, ig in fv:
            v = next(x for x in sd.session(5215)["votes"] if ig.key == f"finalvote:{x['id']}")
            if lang == "en" and sd.mt_title(v["id"]):
                self.assertIn('class="mt">DeepL<', ig.pages[0])
            if lang != "en":
                self.assertNotIn("DeepL", ig.pages[0])

    def test_daily_votes_complete_and_in_order(self):
        daily = [(lang, ig) for it, lang, (ig, _) in self.posts if it.type == "daily_votes"]
        if not daily:
            self.skipTest("no ticker data on this machine")
        votes = sd.ticker_day("2026-10-01")["councils"]["N"]["votes"]
        for lang, ig in daily:
            times = re.findall(r'<span class="muted" style="font-weight:600">(\d\d:\d\d)</span>', "".join(ig.pages))
            self.assertEqual(times, [v["time"] for v in votes])     # every vote, official order (POL-16)


class Wording(unittest.TestCase):
    def test_strings_have_every_key_in_every_language(self):
        def keys(d, prefix=""):
            out = set()
            for k, v in d.items():
                if isinstance(v, dict):
                    out |= keys(v, prefix + k + ".")
                else:
                    out.add(prefix + k)
            return out
        base = keys(sd.strings()["de"])
        self.assertGreater(len(base), 100)
        for lang in sd.LANGS:
            self.assertEqual(keys(sd.strings()[lang]), base, lang)

    def test_no_banned_or_live_words(self):
        for lang in sd.LANGS:
            text = json.dumps(sd.strings()[lang], ensure_ascii=False)
            for w in CFG["bannedWords"].get(lang, []) + LIVE[lang]:
                self.assertIsNone(re.search(r"(?i)(?<![\wÀ-ÿ])" + re.escape(w) + r"(?![\wÀ-ÿ])", text), f"{lang}: '{w}'")

    def test_disclaimer_matches_the_site(self):
        i18n = sd.site()["i18n"]
        for lang in sd.LANGS:
            self.assertIn(sd.S(lang)["disclaimer"], i18n[lang]["news.copy"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
