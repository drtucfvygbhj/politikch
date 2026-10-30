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
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cards  # noqa: E402
import pack as pack_mod  # noqa: E402
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


class Pack(unittest.TestCase):
    """The weekend X pack: nothing planned from data that isn't in yet, and a pack that stays as it is."""

    def weekend(self, monday, state=None):
        return plan.plan_week(D(monday), state if state is not None else {}, weekend=True)

    def test_results_left_out_and_monday_free(self):
        slots = self.weekend("2026-09-28")
        self.assertFalse([s for s in slots if s.item.type == "results"])
        self.assertFalse([s for s in slots if s.day == D("2026-09-28")])

    def test_results_added_once_with_every_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack = {"monday": "2026-09-28", "posts": []}
            self.assertTrue(pack_mod.add_results(D("2026-09-28"), pack, Path(tmp), None))
            self.assertFalse(pack_mod.add_results(D("2026-09-28"), pack, Path(tmp), None))
            r = pack["posts"][0]
            self.assertEqual((r["day"], r["time"], r["type"]), ("2026-09-28", plan.RESULTS_TIME, "results"))
            self.assertEqual(len(pack["posts"]), 1)

    def test_no_results_on_an_ordinary_week(self):
        self.assertIsNone(plan.results_item(D("2026-10-05")))

    def test_summary_waits_for_the_last_day(self):
        self.assertFalse([s for s in self.weekend("2026-10-05") if s.item.type == "session_summary"])
        r = [s for s in self.weekend("2026-10-12") if s.item.type == "session_summary"]
        self.assertEqual([s.day for s in r], [D("2026-10-13")])
        self.assertFalse([s for s in self.weekend("2026-10-12", {"posted": {"session:5215": "2026-10-13"}})
                          if s.item.type == "session_summary"])

    def test_quiet_period_kept(self):
        for s in self.weekend("2026-11-23"):
            if s.item.args.get("ballot"):
                self.assertTrue(s.item.args.get("sunday"), s.item.key)

    def test_at_most_four_images_and_the_text_fits(self):
        state = {}
        for monday in ("2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"):
            for slot in plan.plan_week(D(monday), state, weekend=True):
                for lang in sd.LANGS:
                    ig, x = plan.build(slot.item, lang)
                    self.assertLessEqual(len(plan.x_pages(x or ig)), 4, slot.item.key)
                    text, link = plan.x_text(x or ig).rsplit("\n", 1)
                    self.assertLessEqual(len(text) + 1 + 23, 280, slot.item.key)   # X counts every link as 23

    def test_long_ballot_posts_keep_every_proposal(self):   # POL-01
        ballot = D("2026-11-29")
        votes = [sd.site()["votes"][v["id"]] for v in plan.ballots()[ballot]]
        self.assertGreaterEqual(len(votes), 4)
        for lang in sd.LANGS:
            for post in (cards.runup_overview(ballot, votes, lang), cards.runup_money(ballot, votes, lang)):
                self.assertGreater(len(post.pages), 4)
                page = plan.x_pages(post)
                self.assertEqual(len(page), 1)
                self.assertNotIn('class="pg"', page[0])
                for v in votes:
                    self.assertIn(cards.e(sd.vote_title(v, lang)[0]), page[0], (post.type, lang))

    def test_a_post_with_no_summary_page_is_not_cut(self):
        ballot = D("2026-11-29")
        votes = [sd.site()["votes"][v["id"]] for v in plan.ballots()[ballot]]
        post = cards.runup_args(ballot, votes + votes[:1], "de")
        self.assertEqual(len(post.pages), 5)
        self.assertIsNone(plan.x_pages(post))
        with tempfile.TemporaryDirectory() as tmp:
            item = plan.Item("runup_args", 4, ballot, "runup:test", {"ballot": ballot, "votes": [v["id"] for v in votes + votes[:1]]})
            made = pack_mod.make_post(plan.Slot(ballot, "07:30", item), Path(tmp), None)
            self.assertTrue(made["langs"]["de"]["problem"])
            self.assertEqual(made["langs"]["de"]["images"], [])

    def test_long_summary_goes_as_its_cover(self):   # POL-16: no selection of votes on X
        sess = next(s for s in sd.site()["sessionsIndex"]["sessions"] if s["id"] == 5215)
        post = cards.session_summary(sess, "en", per_page=2)
        self.assertGreater(len(post.pages), 4)
        page = plan.x_pages(post)[0]
        self.assertNotIn(cards.e(sd.S("en")["parliament"]["summaryNext"][:20]), page)
        self.assertIn(">18<", page)
        self.assertNotIn("colItem", page)

    def test_rebuild_gives_the_same_week_and_state_moves_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            state.write_text("{}", "utf-8")
            folder = root / "2026-11-02"
            folder.mkdir()
            first = pack_mod.build_week(D("2026-11-02"), folder, None, state)
            again = pack_mod.build_week(D("2026-11-02"), folder, None, state)
            self.assertTrue(first)
            self.assertEqual(first, again)
            self.assertEqual(json.loads((folder / "state-before.json").read_text("utf-8")), {})
            self.assertIn(first[0]["key"], json.loads(state.read_text("utf-8"))["posted"])

    def test_an_older_week_doesnt_move_the_state_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            for monday in ("2026-11-09", "2026-11-02"):
                (root / monday).mkdir()
            pack_mod.build_week(D("2026-11-09"), root / "2026-11-09", None, state)
            (root / "2026-11-09" / "posts.json").write_text("{}", "utf-8")
            kept = state.read_text("utf-8")
            pack_mod.build_week(D("2026-11-02"), root / "2026-11-02", None, state)
            self.assertEqual(state.read_text("utf-8"), kept)

    def test_practice_moves_no_cooldowns_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            (root / "2026-11-02").mkdir()
            pack_mod.build_week(D("2026-11-02"), root / "2026-11-02", None, state, practice=True)
            self.assertFalse(state.exists())

    def test_which_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(pack_mod.target_week(D("2026-10-31"), root), D("2026-11-02"))   # Saturday
            self.assertEqual(pack_mod.target_week(D("2026-11-01"), root), D("2026-11-02"))   # Sunday
            self.assertEqual(pack_mod.target_week(D("2026-09-28"), root), D("2026-09-28"))   # Monday after a ballot
            (root / "2026-09-28").mkdir()
            (root / "2026-09-28" / "posts.json").write_text(json.dumps({"posts": [{"type": "results"}]}), "utf-8")
            self.assertEqual(pack_mod.target_week(D("2026-09-28"), root), D("2026-10-05"))   # results are in

    def test_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            pack = {"monday": "2026-11-02", "posts": pack_mod.build_week(D("2026-11-02"), folder, None, folder / "state.json")}
            pack["posts"][0]["langs"]["de"]["text"] = "<script>alert(1)</script>"
            html = pack_mod.page_html(D("2026-11-02"), pack, folder, site_offline=True)
            self.assertNotIn("<script>alert", html)
            self.assertIn("maintenance mode", html)
            for lang in sd.LANGS:
                self.assertIn(f'id="{lang}"', html)
                self.assertEqual(html.count(f'lang="{lang}" aria-label'), len(pack["posts"]))
            self.assertNotIn("http", html.replace("http-equiv", ""))   # the page itself loads nothing from outside

    def test_draft_wording_is_shown(self):
        pack = {"posts": []}
        warn, _ = pack_mod.notices(D("2026-11-02"), pack, False)
        self.assertEqual(bool(warn), not sd.strings().get("_approved"))

    def test_results_notice(self):
        _, note = pack_mod.notices(D("2026-09-28"), {"posts": []}, False)
        self.assertTrue([n for n in note if "Results" in n])
        _, note = pack_mod.notices(D("2026-09-28"), {"posts": [{"type": "results"}]}, False)
        self.assertFalse([n for n in note if "Results" in n])


if __name__ == "__main__":
    unittest.main(verbosity=1)
