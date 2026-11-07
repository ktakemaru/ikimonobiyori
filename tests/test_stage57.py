"""段階57(指示書 docs/stage57-conversation-flow-instructions.md): 会話の流れの改善。通信しない。合成データだけ。"""
import io
import json
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask, guide, offers as OF
from ikimonobiyori import ask_verify as V

ROOT = Path(__file__).resolve().parent.parent
RULES = V.load_rules()
OFFER = OF.all_texts()[0]


def run(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = mod.main(argv)
    return rc, out.getvalue().strip(), err.getvalue().strip()


class Part1UnsupportedThemes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_unsupported_theme_is_an_error_and_writes_no_page(self):
        for word in ("ホタル", "蛍"):
            out = Path(self.tmp.name) / "x.html"
            rc, stdout, err = run(guide, ["page", "--theme", word, "--out", str(out), "--no-ensure-photos"])
            self.assertNotEqual(rc, 0, word)
            self.assertEqual(stdout, "")
            self.assertIn("未対応", err)
            self.assertIn("野鳥", err)                                         # 対応の一覧を示す
            self.assertFalse(out.exists(), word)                              # 野鳥のページが誤って作られない

    def test_list_themes(self):
        rc, out, _ = run(guide, ["page", "--list-themes"])
        self.assertEqual(rc, 0)
        for w in ("野鳥", "花", "野草"):
            self.assertIn(w, out)

    def test_flower_page_is_not_written_under_the_bird_file_name(self):
        rc, out, _ = run(guide, ["page", "--theme", "花", "--date", "2026-11-08", "--no-ensure-photos"])
        self.assertEqual(rc, 0)
        self.assertEqual(Path(out).name, "flower-guide.html")
        self.assertIn("花の案内", Path(out).read_text(encoding="utf-8"))
        self.assertNotIn("野鳥の案内", Path(out).read_text(encoding="utf-8"))


class Part1Offers(unittest.TestCase):
    def test_conditions(self):
        ok = {"subject_supported": True, "plan": True, "photo_candidates": True}
        self.assertEqual(OF.texts(OF.available(ok)), [OFFER])
        for k in ok:
            self.assertEqual(OF.available({**ok, k: False}), [], k)           # 条件が 1 つでも欠けたら、案内の行を出さない

    def test_guide_answer_has_the_line_only_when_supported_and_photos_exist(self):
        rows = [{"entry": {"kinds": [{"kind": "ジョウビタキ", "shown": True}]}}]
        parts = {"sections": [{"key": "recommend", "rows": rows}]}
        self.assertEqual(guide._page_offer_lines(parts, {"野鳥"}), [OFFER])
        self.assertEqual(guide._page_offer_lines(parts, {"ホタル"}), [])
        self.assertEqual(guide._page_offer_lines({"sections": [{"key": "recommend", "rows": []}]}, {"野鳥"}), [])

    def test_free_form_offers_fail_the_check(self):
        for s in ("紅葉の写真つきページをお作りします。", "写真つきで紹介しましょうか。", "Artifact にします。", "ページを公開できます。", "図も作れます。"):
            self.assertEqual([e["code"] for e in V.offer_errors(s, [OFFER])], ["offer_not_allowed"], s)
        self.assertEqual(V.offer_errors(OFFER, [OFFER]), [])
        self.assertEqual([e["code"] for e in V.offer_errors(OFFER, [])], ["offer_not_allowed"])      # 条件を満たさないときは一覧の文でも不合格

    def test_generic_check_uses_the_list(self):
        text = "おすすめです。\n① あ\n② い\n③ う\n"
        self.assertTrue(V.generic_check(text + OFFER)["ok"])
        self.assertFalse(V.generic_check(text + "ほかのページもお作りします。")["ok"])
        self.assertFalse(V.generic_check(text + OFFER, offers=[])["ok"])

    def test_cannot_do_reply_is_one_line_plus_only_a_possible_offer(self):
        self.assertEqual(OF.unsupported_reply("蛍の写真つきページ"), ["今は蛍の写真つきページには対応していません。"])
        self.assertEqual(OF.unsupported_reply("蛍の写真つきページ", [{"id": "photo_page", "text": OFFER}]),
                         ["今は蛍の写真つきページには対応していません。", OFFER])
        rc, out, _ = run(ask, ["unsupported", "--what", "蛍の写真つきページ"])
        self.assertEqual((rc, out), (0, "今は蛍の写真つきページには対応していません。"))

    def test_rule_is_in_the_instructions(self):
        for f in ("CLAUDE.md", "AGENTS.md", ".claude/skills/ikimono-weekend/SKILL.md"):
            t = (ROOT / f).read_text(encoding="utf-8")
            self.assertIn("できないことを提案しない", t, f)
            self.assertIn("手書きの HTML・図で代用しない", t, f)


def spot(name, km=20, state="見頃", date_="2026-11-05", window=("11-01", "11-30"), city="試験町", **kw):
    cur = {"state": state, "state_raw": state, "state_date": date_, "publisher": "試験市", "url": f"https://kouyou.example.org/{km}", "source_class": "official",
           "freshness": "fresh", "age_days": 2, "read_at": "2026-11-07T09:00:00+09:00"} if state else None
    return {"id": "t-" + name, "name": name, "city": city, "prefecture": "神奈川県", "current": cur, "current_unknown": cur is None, "distance_km": km,
            "typical": [{"text": "例年11月", "start": window[0], "end": window[1], "url": "https://kouyou.example.org/t", "publisher": "試験市"}],
            "typical_line": "例年の見頃: 11月", "events": [], "history": [], "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak", **kw}


def facts_doc(subjects, dates=("2026-11-08",), now="2026-11-07T12:00:00+09:00", origin="横浜"):
    return {"schema": "ikimono-ask-facts/1", "now": now, "dates": list(dates), "origin": origin, "region": "全範囲", "subjects": subjects,
            "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None}, "summary_pages": [], "this_round": {}}


def koyo_subject():
    return {"subject": "autumn_leaves", "candidates": [spot("試験の園", 20, city="園町", tree_species=["モミジ", "イチョウ"]), spot("試験の山", 60, city="山町", elevation_m=800, tree_species=["ブナ"]),
                                                     spot("試験の湖", 130, city="湖町", tree_species=[])], "avoid": [], "nearby_out_of_region": [], "alternatives": []}


def flower_subject():
    return {"subject": "flowers", "candidates": [spot("花の庭", 15, city="庭町", flower_kinds=["秋バラ"]), spot("花の丘", 70, city="丘町", flower_kinds=["コスモス"]), spot("花の里", 120, city="里町", flower_kinds=["キク"])],
            "avoid": [], "nearby_out_of_region": [], "alternatives": []}


def bird_subject():
    birds = [{"name": "ジョウビタキ", "kind": "recent", "kind_label": "最近の記録", "why": "今季の記録があります。"}]
    return {"subject": "birds", "candidates": [spot("鳥の池", 25, city="池町", park_birds=birds), spot("鳥の沼", 65, city="沼町", park_birds=birds), spot("鳥の浜", 110, city="浜町", park_birds=birds)],
            "avoid": [], "nearby_out_of_region": [], "alternatives": []}


JPEG = b"\xff\xd8\xff" + b"0" * 64
META = {"image_type": "jpeg", "attribution": "(c) 試験, some rights reserved (CC BY)", "license": "CC BY", "photo_page": "https://www.inaturalist.org/photos/1"}


def pick_block(name, subject, facts):
    c = next(x for x in facts["subjects"][subject]["candidates"] if x["name"] == name)
    season = "この時期に見られる鳥はジョウビタキです" if subject == "birds" else "例年の見頃は11月です"
    return f"① {name}: {c['current']['state']}(11/5時点、試験市)。{season}。"


def segment_answer(facts, plan, drop=None, swap=None):
    """合成の複数対象の答え(対象別の節。それぞれに今回のおすすめ)。"""
    lines = ["今週末は、" + "や".join(s["heading"] for s in plan["segments"]) + "を楽しめそうです。"]
    urls = []
    for seg in plan["segments"]:
        pl = plan["subjects"][seg["subject"]]
        lines += ["", seg["heading"], f"{seg['heading']}は見頃が続いている可能性があります。", "今回のおすすめ"]
        for p in pl["picks"]:
            if p["name"] == drop:
                continue
            lines.append(pick_block(swap if swap and p["name"] == swap[0] else p["name"], seg["subject"], facts))
            c = next(x for x in facts["subjects"][seg["subject"]]["candidates"] if x["name"] == p["name"])
            urls.append(c["current"]["url"])
    lines += ["", "確かさの補足", "アクセスや混雑は出かける前に公式ページで確認してください。", "", "出典"] + sorted(set(urls))
    return "\n".join(lines) + "\n"


class Part3MultiSubject(unittest.TestCase):
    def facts(self, *keys):
        make = {"autumn_leaves": koyo_subject, "flowers": flower_subject, "birds": bird_subject}
        return facts_doc({k: make[k]() for k in keys})

    def check(self, *keys, **kw):
        from ikimonobiyori import answer_plan as AP
        f = self.facts(*keys)
        for s in f["subjects"].values():
            for c in s["candidates"]:                                          # 実用情報なしの決まった一文で通す形
                c["practical"] = []
        plan = AP.build_all(f)
        return V.check(segment_answer(f, plan, **kw), f, RULES, plan=plan)

    def test_two_and_three_subjects_pass(self):
        for keys in (("flowers", "birds"), ("autumn_leaves", "flowers"), ("autumn_leaves", "flowers", "birds")):
            r = self.check(*keys)
            self.assertTrue(r["ok"], (keys, V.report_lines(r)))

    def test_a_missing_pick_is_found_per_subject(self):
        r = self.check("flowers", "birds", drop="鳥の沼")
        codes = [(e["code"], e["detail"]) for e in r["answer_errors"]]
        self.assertTrue(any(c == "plan_pick_missing" and d.startswith("野鳥:") for c, d in codes), codes)

    def test_a_section_lead_mismatch_is_found_per_subject(self):
        from ikimonobiyori import answer_plan as AP
        f = self.facts("flowers", "birds")
        plan = AP.build_all(f)
        text = segment_answer(f, plan).replace("花は見頃が続いている可能性があります。", "鳥の池も楽しめそうです。")
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(any(e["code"] == "lead_mismatch" and e["detail"].startswith("花:") for e in r["answer_errors"]), V.report_lines(r))

    def test_same_spot_in_two_subjects_needs_only_its_own_source(self):
        from ikimonobiyori import answer_plan as AP
        f = self.facts("flowers", "birds")
        plan = AP.build_all(f)
        segs = AP.split_segments(segment_answer(f, plan), plan)
        self.assertEqual([s["seg"]["heading"] for s in segs], ["花", "野鳥"])

    def test_answer_without_headings_keeps_the_old_way(self):
        from ikimonobiyori import answer_plan as AP
        self.assertIsNone(AP.split_segments("花は\n① 花の庭\n", AP.build_all(self.facts("flowers", "birds"))))


class Part4Wording(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import observations as O
        self.O = O
        self.pol = O.load_policy()

    def test_symbols_become_words_only_with_a_legend(self):
        d = self.O.state_display
        self.assertEqual(d("△", "日光市観光協会", self.pol), ("色づき始め", False))
        self.assertEqual(d("◎", "日光市観光協会", self.pol), ("真っ盛り", False))
        self.assertEqual(d("▼", "日光市観光協会", self.pol), ("色褪せ・落葉始め", False))
        self.assertEqual(d("△", "どこかの観光協会", self.pol), (None, True))    # 凡例が読めていない記号は断定しない
        self.assertEqual(d("◎ 真っ盛り", "どこか", self.pol), ("◎ 真っ盛り", False))
        self.assertEqual(d("見ごろ", "どこか", self.pol), ("見ごろ", False))

    def base_facts(self):
        return facts_doc({"autumn_leaves": koyo_subject()})

    def codes(self, text, f=None):
        f = f or self.base_facts()
        return [e["code"] for e in V.stage57_text_errors(text, f, V.Material(f, RULES), RULES)]

    def test_check_rejects_bare_symbols(self):
        self.assertIn("state_symbol_raw", self.codes("試験の園は「△」です。"))
        self.assertNotIn("state_symbol_raw", self.codes("試験の園は「◎ 真っ盛り」です。"))

    def test_other_day_hours_are_replaced_and_rejected(self):
        d = [date(2026, 11, 8)]
        items = [{"text": "11/6の有料エリア 9:30〜21:00"}, {"text": "11/8の有料エリア 9:30〜21:00"}, {"text": "開園 9:00〜16:30"}]
        got = [x["text"] for x in self.O.practical_for_dates(items, d, self.pol)]
        self.assertEqual(got, [self.pol["practical_other_day"]["replace"], items[1]["text"], items[2]["text"]])
        self.assertIn("practical_other_day", self.codes("11/6の有料エリア 9:30〜21:00"))
        self.assertNotIn("practical_other_day", self.codes("11/8の有料エリア 9:30〜21:00"))

    def test_season_line_does_not_contradict_a_record(self):
        lab = self.pol["birds"]["season_labels"]
        line = self.O.season_line({"current": {"state_date": "2026-11-06", "publisher": "試験公園"}}, self.pol)
        self.assertNotEqual(line, lab["unknown"])
        self.assertIn("試験公園", line)
        self.assertEqual(self.O.season_line({}, self.pol), lab["unknown"])
        f = facts_doc({"birds": bird_subject()})
        self.assertIn("season_contradiction", self.codes("① 鳥の池: " + lab["unknown"] + "。\n", f))

    def test_bird_park_without_a_record_is_not_ranked_above_recorded_ones(self):
        from ikimonobiyori import answer_plan as AP
        s = bird_subject()
        s["candidates"][0]["current"] = None                                   # いちばん近い公園だけ記録なし
        s["candidates"][0]["current_unknown"] = True
        plan = AP.build(facts_doc({"birds": s}), "birds")
        names = [p["name"] for p in plan["picks"]]
        self.assertTrue(names[0] != "鳥の池" and (("鳥の池" not in names) or names[-1] == "鳥の池"), names)
        row = next(r for r in plan["ranking"] if r["name"] == "鳥の池")
        self.assertLess(row["breakdown"]["no_official"], 0)
        p = next((x for x in plan["picks"] if x["name"] == "鳥の池"), None)
        if p:
            self.assertEqual(p["note"], AP.load_policy()["birds_no_current"]["note"])

    def test_pick_note_is_required_in_the_answer(self):
        from ikimonobiyori import answer_plan as AP
        plan = {"picks": [{"name": "鳥の池", "note": "公式の最近の観察記録は確認できていません"}], "ranking": [{"name": "鳥の池"}], "overrides": []}
        errs = AP.plan_errors("", plan, None, ["① 鳥の池: この時期のカモ。"], V.short_names)
        self.assertIn("pick_note_missing", [e["code"] for e in errs])
        self.assertEqual(AP.plan_errors("", plan, None, ["① 鳥の池: 公式の最近の観察記録は確認できていません。"], V.short_names), [])

    def test_jinba_has_a_typical_window_with_source(self):
        c = next(x for x in self.O.all_candidates("autumn_leaves", self.pol) if x["name"] == "陣馬山")
        t = c["typical"][0]
        self.assertEqual((t["start"], t["end"], t["source_class"]), ("11-11", "11-30", "secondary"))


class Part5Refine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        self.now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))

    def flow(self, facts):
        f = ask.Flow(Path(self.tmp.name) / "w", now=self.now, env=self.env)
        f._save("facts.json", facts)
        return f

    def test_near_keeps_only_near_and_updates_last_plan(self):
        f = self.flow(facts_doc({"autumn_leaves": koyo_subject()}))
        first = f.plan()
        self.assertGreater(len(first["picks"]), 1)
        doc = f.plan(refine="もっと近場で")
        self.assertEqual([p["name"] for p in doc["picks"]], ["試験の園"])
        self.assertEqual(doc["refine"], "もっと近場で")
        last = ask.load_last_plan(self.now, self.env)
        self.assertEqual([p["name"] for p in last["plan"]["picks"]], ["試験の園"])
        r = next(x for x in doc["ranking"] if x["name"] == "試験の湖")
        self.assertEqual(r["reason"], "refine_excluded")

    def test_trek_and_unknown_word(self):
        f = self.flow(facts_doc({"autumn_leaves": koyo_subject()}))
        self.assertEqual([p["name"] for p in f.plan(refine="山歩きで")["picks"]], ["試験の山"])
        with self.assertRaises(ValueError):
            f.plan(refine="おいしいものが食べたい")

    def test_near_falls_back_to_the_nearest_when_none(self):
        s = koyo_subject()
        s["candidates"] = [c for c in s["candidates"] if c["name"] == "試験の湖"]
        f = self.flow(facts_doc({"autumn_leaves": s}))
        doc = f.plan(refine="近場")
        self.assertTrue(doc["refine_relaxed"])
        self.assertEqual([p["name"] for p in doc["picks"]], ["試験の湖"])

    def test_refined_answer_with_fewer_picks_passes_the_candidate_count(self):
        from ikimonobiyori import answer_plan as AP
        f = facts_doc({"autumn_leaves": koyo_subject()})
        plan = AP.build(f, "autumn_leaves", refine="近場")
        r = V.check("① 試験の園: 例年の見頃です。\n", f, RULES, plan=plan)
        self.assertNotIn("too_few_candidates", [e["code"] for e in r["answer_errors"]])

    def test_same_day_pages_are_not_read_twice(self):
        ask.mark_fetched(["https://a.example/1"], self.now, self.env)
        self.assertEqual(ask.fetched_today(self.now, self.env), {"https://a.example/1"})
        self.assertEqual(ask.fetched_today(self.now + timedelta(days=1), self.env), set())
        doc = {"subjects": {"x": {"summary_pages": [{"url": "https://a.example/1"}], "items": [{"id": "a", "pages": [{"url": "https://a.example/1"}]},
                                                                                              {"id": "b", "pages": [{"url": "https://a.example/2"}]}]}}}
        ask.drop_fetched(doc, {"https://a.example/1"})
        self.assertEqual([i["id"] for i in doc["subjects"]["x"]["items"]], ["b"])
        self.assertEqual(doc["subjects"]["x"]["summary_pages"], [])
        self.assertTrue(doc["needs_fetch"])


class Part6Flows(unittest.TestCase):
    def test_conversation_flows(self):
        from ikimonobiyori import regress
        res = regress.run_flows()
        self.assertEqual([r for r in res if not r["ok"]], [])
        self.assertGreaterEqual(len(res), 4)


class Part8Origin(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import origins
        self.o = origins

    def test_extract(self):
        for q, want in (("今週末か来週末、大宮から紅葉を見に行きたい", "大宮"), ("新宿発で花を見たい", "新宿"), ("千葉から行ける紅葉", "千葉"), ("宇都宮駅から日帰りで", "宇都宮")):
            self.assertEqual(self.o.extract(q), want, q)
        self.assertIsNone(self.o.extract("富士山の周囲で紅葉のおすすめを教えて"))
        self.assertIsNone(self.o.extract("明日から紅葉を見たい"))

    def test_lookup_uses_only_the_tables(self):
        self.assertAlmostEqual(self.o.lookup("大宮")["lat"], 35.906, places=2)
        self.assertEqual(self.o.lookup("大宮駅")["name"], "大宮")
        self.assertEqual(self.o.lookup("千葉")["prefecture"], "千葉県")           # 市区町村の代表点の表から
        self.assertIsNone(self.o.lookup("ありえない町"))

    def test_unknown_origin_is_one_sentence_with_the_default(self):
        c = self.o.choose("ありえない町から紅葉を見たい")
        self.assertEqual((c["origin"], c["source"]), ("横浜", "unknown"))
        self.assertEqual(c["line"], "ありえない町の位置を特定できませんでした。横浜からの距離で選びます。")

    def test_no_origin_is_yokohama(self):
        self.assertEqual(self.o.choose("紅葉のおすすめを教えて")["origin"], "横浜")

    def test_follow_up_keeps_and_new_question_resets(self):
        c = self.o.choose("もっと近場で", follow_up=True, last_origin="大宮")
        self.assertEqual((c["origin"], c["line"]), ("大宮", "先ほどの大宮のままです。"))
        c = self.o.choose("富士山の周囲で紅葉のおすすめを教えて", follow_up=False, last_origin="大宮")
        self.assertEqual((c["origin"], c["source"]), ("横浜", "default"))
        self.assertIn("横浜", c["line"])

    def test_distance_and_saitama_ranks_higher_from_omiya(self):
        from ikimonobiyori import answer_plan as AP, catalog as C, observations as O
        pol = C.load_policy()
        pt = {"lat": 36.114805555555556, "lon": 139.10972222222222}              # 長瀞町
        km_o, km_y = C.range_from(pol, pt, "大宮")["km"], C.range_from(pol, pt, "横浜")["km"]
        self.assertLess(km_o, km_y)
        self.assertEqual(O._distance({"city": "さいたま市南区"}, "大宮", pol), C.range_from(pol, O_point("さいたま市"), "大宮")["km"])
        self.assertIsNone(O._distance({"city": "さいたま市南区"}, "横浜", pol))    # 横浜はこれまでどおり
        def plan(origin):
            cands = []
            for name, p in (("埼玉の渓谷", pt), ("横浜の庭", {"lat": 35.45, "lon": 139.63})):
                km = C.range_from(pol, p, origin)["km"]
                cands.append(spot(name, km, city=name))
            return AP.build(facts_doc({"autumn_leaves": {"candidates": cands}}, origin=origin), "autumn_leaves")
        score = lambda pl, n: next(r["score"] for r in pl["ranking"] if r["name"] == n)
        self.assertGreater(score(plan("大宮"), "埼玉の渓谷"), score(plan("横浜"), "埼玉の渓谷"))
        self.assertEqual(next(p for p in plan("大宮")["picks"] if p["name"] == "埼玉の渓谷")["distance_text"], f"約{km_o}km")

    def test_answer_must_state_origin_and_distance(self):
        from ikimonobiyori import answer_plan as AP
        f = facts_doc({"autumn_leaves": {"candidates": [spot("埼玉の渓谷", 45, city="渓町")]}}, origin="大宮")
        f["lines"]["origin_line"] = "大宮からの距離で選びました。"
        plan = AP.build(f, "autumn_leaves")
        codes = [e["code"] for e in V.check("① 埼玉の渓谷: 例年の見頃は11月です。\n", f, RULES, plan=plan)["answer_errors"]]
        self.assertIn("origin_missing", codes)
        self.assertIn("origin_km_missing", codes)
        codes = [e["code"] for e in V.check("大宮からの距離で選びました。\n① 埼玉の渓谷: 約45km。例年の見頃は11月です。\n", f, RULES, plan=plan)["answer_errors"]]
        self.assertNotIn("origin_missing", codes)
        self.assertNotIn("origin_km_missing", codes)

    def test_cache_is_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            self.o.add_to_cache("試験町", 36.0, 139.0, "Q1", env=env)
            self.assertEqual(self.o.lookup("試験町", env)["qid"], "Q1")
            self.assertTrue(Path(d, "ask", "origins_cache.json").is_file())


def O_point(name):
    from ikimonobiyori import origins
    return origins.municipal_point(name)


class Part2Page(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        self.wd = Path(self.tmp.name) / "work"
        self.now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))

    def flow(self, facts):
        f = ask.Flow(self.wd, now=self.now, env=self.env)
        f._save("facts.json", facts)
        return f

    def test_koyo_page_has_the_same_picks_and_sections_as_the_plan(self):
        f = self.flow(facts_doc({"autumn_leaves": koyo_subject()}))
        plan = f.plan()
        doc = f.page()
        html = Path(doc["path"]).read_text(encoding="utf-8")
        for p in plan["picks"]:
            self.assertIn(p["name"], html)
        for s in plan["sections"]:
            self.assertIn(s["label"], html)
        self.assertIn("紅葉", html)
        self.assertNotIn("公園で見られる鳥", html)                               # 野鳥のページではない
        self.assertNotIn("<svg", html)

    def test_page_uses_tree_species_photos_not_spot_photos(self):
        from ikimonobiyori import plan_page
        f = self.flow(facts_doc({"autumn_leaves": koyo_subject()}))
        plan = f.plan()
        asked = []

        def photo_for(name):
            asked.append(name)
            return (META, JPEG)
        pp = ask.load_policy()["plan_page"]
        html, _lines, shown = plan_page.build(f._load("facts.json", None), plan, policy=pp, photo_for=photo_for, photo_credit=lambda m: "c", now=self.now)
        self.assertEqual(set(asked), {"イロハモミジ", "イチョウ", "ブナ"})         # 樹種だけ(地点の名前で写真を引かない)。モミジは代表の種に丸める
        self.assertFalse({"試験の園", "試験の山", "試験の湖"} & set(asked))
        self.assertNotIn("試験の湖", shown)                                       # 樹種が不明な地点は写真なし
        self.assertIn("base64", html)

    def test_flowers_and_birds_are_both_on_the_page(self):
        f = self.flow(facts_doc({"flowers": flower_subject(), "birds": bird_subject()}))
        f.plan()
        html = Path(f.page()["path"]).read_text(encoding="utf-8")
        self.assertIn("花の庭", html)
        self.assertIn("鳥の池", html)
        self.assertIn("<h2>花</h2>", html)
        self.assertIn("<h2>野鳥</h2>", html)

    def test_birds_only_stays_the_park_page(self):
        f = self.flow(facts_doc({"birds": bird_subject()}))
        f.plan()
        self.assertIn("公園で見られる鳥", Path(f.page()["path"]).read_text(encoding="utf-8"))

    def test_unknown_subject_makes_no_page(self):
        f = self.flow(facts_doc({"fireflies": {"candidates": [spot("蛍の沢")]}}))
        with self.assertRaises(ask.PageUnsupported):
            f.page()

    def test_no_plan_makes_no_page(self):
        f = self.flow(facts_doc({"autumn_leaves": koyo_subject()}))
        with self.assertRaises(ask.PageUnsupported):
            f.page()

    def test_last_plan_is_saved_and_valid_for_24_hours(self):
        f = self.flow(facts_doc({"autumn_leaves": koyo_subject()}))
        f.plan()
        doc = ask.load_last_plan(self.now + timedelta(hours=23), self.env)
        self.assertEqual(doc["subject"], "autumn_leaves")
        self.assertTrue(Path(self.tmp.name, "ask", "last_plan.json").is_file())    # データ置き場
        self.assertIsNone(ask.load_last_plan(self.now + timedelta(hours=25), self.env))
        self.assertIsNone(ask.load_last_plan(self.now - timedelta(hours=1), self.env))

    def test_restore_rebuilds_a_missing_workdir(self):
        f = self.flow(facts_doc({"autumn_leaves": koyo_subject()}))
        f.plan()
        doc = ask.load_last_plan(self.now, self.env)
        (self.wd / "facts.json").unlink()
        (self.wd / "answer_plan.json").unlink()
        ask.restore_workdir(doc)
        self.assertTrue((self.wd / "facts.json").is_file() and (self.wd / "answer_plan.json").is_file())

    def test_no_recent_plan_message(self):
        with tempfile.TemporaryDirectory() as d, unittest.mock.patch.dict("os.environ", {"IKIMONOBIYORI_DATA_DIR": d}):
            rc, out, err = run(ask, ["page"])
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("先に質問してください", err)

    def test_offer_needs_a_photo_candidate(self):
        s = koyo_subject()
        for c in s["candidates"]:
            c["tree_species"] = []
        f = self.flow(facts_doc({"autumn_leaves": s}))
        self.assertEqual(f.plan()["offers"], [])
        f2 = self.flow(facts_doc({"autumn_leaves": koyo_subject()}))
        self.assertEqual(OF.texts(f2.plan()["offers"]), [OFFER])

    def test_facts_carry_tree_species_from_the_spot_list(self):
        from ikimonobiyori import observations as O
        c = O._from_spot({"id": "x", "subject": "autumn_leaves", "name": "x", "trees": {"species": "モミジ・イチョウ"}}, O.load_policy(), {})
        self.assertEqual(c["tree_species"], ["モミジ", "イチョウ"])


if __name__ == "__main__":
    unittest.main()
