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
        self.assertEqual(d("◯ 山内地区全体見ごろ始まりました", "日光市観光協会", self.pol), ("山内地区全体見ごろ始まりました", False))

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


class Part9Procedure(unittest.TestCase):
    def test_process_excuses_fail_both_checks(self):
        for s in ("今回は新しく取りに行っていません。", "今日この会話で読んだ情報だけで答えます。", "ツールが横浜と東京としか扱えません。", "ご希望なら調べます。"):
            self.assertEqual([e["code"] for e in V.process_excuse_errors(s, RULES)], ["process_excuse"], s)
            self.assertFalse(V.generic_check("おすすめです。\n① あ\n② い\n③ う\n" + s)["ok"], s)

    def periods_doc(self):
        ks = koyo_subject()
        ks2 = koyo_subject()
        f = facts_doc({"autumn_leaves": ks}, dates=("2026-11-07", "2026-11-08", "2026-11-14", "2026-11-15"))
        f["periods"] = [{"dates": ["2026-11-07", "2026-11-08"], "subjects": {"autumn_leaves": ks}}, {"dates": ["2026-11-14", "2026-11-15"], "subjects": {"autumn_leaves": ks2}}]
        return f

    def test_two_periods_answer_passes_and_needs_both(self):
        from ikimonobiyori import answer_plan as AP
        f = self.periods_doc()
        plan = AP.build_periods(f)
        self.assertEqual([s["heading"] for s in plan["segments"]], ["11/7・11/8のおすすめ", "11/14・11/15のおすすめ"])
        lines = ["どちらの週末も楽しめそうです。"]
        urls = set()
        for s in plan["segments"]:
            lines += ["", s["heading"], "今週は次の場所です。", "今回のおすすめ"]
            for i, p in enumerate(s["plan"]["picks"]):
                c = next(x for x in f["subjects"]["autumn_leaves"]["candidates"] if x["name"] == p["name"])
                lines.append(f"{'①②③'[i]} {p['name']}: {c['current']['state']}(11/5時点、試験市)。例年の見頃は11月です。")
                urls.add(c["current"]["url"])
        lines += ["", "確かさの補足", "アクセスや混雑は出かける前に公式ページで確認してください。", "", "出典"] + sorted(urls)
        text = "\n".join(lines) + "\n"
        r = V.check(text, f, RULES, plan=plan)
        self.assertTrue(r["ok"], V.report_lines(r))
        head2 = plan["segments"][1]["heading"]
        a, b = text.split(head2)
        b = "\n".join(l for l in b.splitlines() if not l.startswith("①"))     # 2 つ目の節のおすすめを 1 件抜く
        codes = [(e["code"], e["detail"][:14]) for e in V.check(a + head2 + b, f, RULES, plan=plan)["answer_errors"]]
        self.assertTrue(any(c == "plan_pick_missing" and d.startswith(head2[:6]) for c, d in codes), codes)

    def test_refresh_targets_are_old_or_missing_and_capped(self):
        from ikimonobiyori import answer_plan as AP
        s = koyo_subject()
        s["candidates"][0]["current"] = None
        s["candidates"][1]["current"]["state_date"] = "2026-11-07"              # 新しい現況は読まない
        s["candidates"][2]["current"]["state_date"] = "2026-11-01"
        for i, c in enumerate(s["candidates"]):
            c["pages"] = [{"url": f"https://a.example/{i}/{j}", "publisher": "試験市"} for j in range(10)]
        f = facts_doc({"autumn_leaves": s})
        plan = AP.build(f, "autumn_leaves")
        got = AP.refresh_targets(f, plan)
        self.assertEqual(len(got), AP.load_policy()["refresh"]["max_pages"])
        self.assertNotIn("試験の山", {x["name"] for x in got})
        self.assertNotIn("https://a.example/0/0", {x["url"] for x in AP.refresh_targets(f, plan, seen={"https://a.example/0/0"})})

    def test_steps_are_written_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            f = ask.Flow(Path(d) / "w", now=datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9))), env=env)
            f._save("facts.json", facts_doc({"autumn_leaves": koyo_subject()}))
            before = sorted(str(p) for p in (ROOT / "ikimonobiyori").rglob("*.yaml"))
            f.plan()
            self.assertTrue(Path(d, "ask", "last_plan.json").is_file())
            self.assertEqual(before, sorted(str(p) for p in (ROOT / "ikimonobiyori").rglob("*.yaml")))

    def test_rule_is_in_the_instructions(self):
        for name in ("CLAUDE.md", "AGENTS.md", ".claude/skills/ikimono-weekend/SKILL.md"):
            t = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("リポジトリのファイルを変更しない", t)


class Part10Place(unittest.TestCase):
    def test_extract_names(self):
        from ikimonobiyori import place_answer as PA
        self.assertEqual(PA.extract_names("西沢渓谷や大菩薩嶺の紅葉はどう?"), ["西沢渓谷", "大菩薩嶺"])
        self.assertEqual(PA.extract_names("御岳昇仙峡の紅葉状況は?"), ["御岳昇仙峡"])

    def test_match_does_not_mistake_similar_names(self):
        from ikimonobiyori import place_answer as PA
        cands = [{"name": "高尾山"}, {"name": "高尾の森"}, {"name": "箱根(芦ノ湖)"}, {"name": "箱根(湯本)"}, {"name": "西沢渓谷周辺"}]
        self.assertEqual(PA.match("高尾山", cands)["name"], "高尾山")
        self.assertEqual(PA.match("芦ノ湖", cands)["name"], "箱根(芦ノ湖)")
        self.assertIsNone(PA.match("箱根", cands))                              # 2 件に当たる語は決めない
        self.assertEqual(PA.match("西沢渓谷", cands)["name"], "西沢渓谷周辺")
        self.assertIsNone(PA.match("大菩薩嶺", cands))

    def test_filter_results_drops_blocked_and_reprints(self):
        from ikimonobiyori import place_answer as PA
        rows = [{"url": "https://tenki.jp/kouyou/3/", "title": "紅葉"},
                {"url": "https://www.weathernews.jp/koyo/", "title": "紅葉"},
                {"url": "https://www.japan-travel.example.com/autumn", "title": "Autumn leaves forecast 2026", "snippet": "Japan Weather Association says later"},
                {"url": "https://www.city.yamanashi.yamanashi.lg.jp/x", "title": "西沢渓谷"},
                {"url": "https://www.example.com/nishizawa", "title": "西沢渓谷の見どころ"}]
        got = [r["url"] for r in PA.official_first(PA.filter_results(rows))]
        self.assertEqual(got, ["https://www.city.yamanashi.yamanashi.lg.jp/x", "https://www.example.com/nishizawa"])

    def test_check_rejects_blocked_sources_phones_and_english_heading(self):
        f = facts_doc({"autumn_leaves": koyo_subject()})
        f["subjects"]["autumn_leaves"]["candidates"][0]["practical"] = [{"text": "問い合わせ 0120-111-222", "url": "https://kouyou.example.org/20"}]
        mat = V.Material(f, RULES)
        codes = lambda t, blob=mat.blob: [e["code"] for e in V.source_rule_errors(t, RULES, blob)]
        self.assertIn("blocked_source", codes("出典\nhttps://tenki.jp/kouyou/"))
        self.assertIn("blocked_source", codes("日本気象協会の予想では遅れます。"))
        self.assertIn("phone_not_from_official", codes("電話 0553-22-1111"))
        self.assertEqual(codes("問い合わせ 0120-111-222"), [])
        self.assertIn("phone_not_from_official", codes("問い合わせ 0120-111-222", None))
        self.assertIn("sources_heading", codes("Sources:\nhttps://a.example"))
        self.assertEqual(codes("出典\nhttps://a.example"), [])

    def test_provisional_record_goes_to_the_data_dir(self):
        from ikimonobiyori import place_answer as PA, observations as O
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            out = PA.record_provisional([{"subject": "autumn_leaves", "name": "試験の渓谷", "city": "試験市", "state": "色づき始め", "state_date": "2026-11-05",
                                          "url": "https://www.city.example.lg.jp/k", "publisher": "試験市", "source_class": "official"}], env=env,
                                        now=datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9))))
            self.assertEqual(out["written"], 1)
            self.assertTrue(O.log_path("autumn_leaves", env).is_file())
            self.assertIn(Path(d).resolve(), O.log_path("autumn_leaves", env).resolve().parents)

    def test_section_has_facts_only_and_no_phone_when_absent(self):
        from ikimonobiyori import place_answer as PA
        f = facts_doc({"autumn_leaves": koyo_subject()}, origin="大宮")
        sec = PA.section(f["subjects"]["autumn_leaves"]["candidates"][0], f)
        self.assertEqual(sec[0], "試験の園")
        self.assertTrue(any("11/5時点" in x for x in sec))
        self.assertTrue(any(x == "大宮から約20km" for x in sec))
        self.assertFalse(any("-" in x and x[0] == "0" for x in sec))


CSV_TEXT = """エリア名,市町村名,スポット名,URL,,見頃,標高,備考,状況
石和・勝沼・西沢渓谷,山梨市,試験の渓谷周辺,https://example.org/a,a.jpg,10月中旬～11月上旬,1100m,,3: 見頃
富士山・富士五湖,試験村,試験の湖畔　しけんのこはん,https://example.org/b,b.jpg,10月下旬～11月上旬,981m,【紅葉まつり】10/30～11/15,2: 色付き始め
富士山・富士五湖,試験村,試験の森（ライブカメラ）,https://example.org/c,c.jpg,,900m,,
,,,,,,,,
"""
HTML = '<p>更新日：2026年11月6日</p><p>現在、情報がありません</p><a href="/special/documents/koyo_1106.csv">koyo_1106（CSV：7KB）</a>'


class Part11OfficialCsv(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import official_csv as C
        self.C = C

    def test_page_link_and_update_date(self):
        self.assertEqual(self.C.find_csv_link(HTML, "https://www.yamanashi-kankou.jp/special/yamanashi-koyo.html"), "https://www.yamanashi-kankou.jp/special/documents/koyo_1106.csv")
        self.assertEqual(self.C.page_updated(HTML), "2026-11-06")
        self.assertIsNone(self.C.find_csv_link("<p>現在、情報がありません</p>", "https://a.example/"))

    def test_parse_uses_csv_words_and_page_date(self):
        rows = self.C.parse(CSV_TEXT)
        self.assertEqual([r["name"] for r in rows], ["試験の渓谷周辺", "試験の湖畔", "試験の森"])
        self.assertEqual(rows[0]["state"], "見頃")
        self.assertEqual(rows[1]["state"], "色付き始め")
        recs = self.C.to_records(rows, csv_url="https://www.yamanashi-kankou.jp/special/documents/koyo_1106.csv", updated="2026-11-06", prefecture="山梨県", publisher="試験", label="山梨県観光サイト{md}更新")
        self.assertEqual(len(recs), 2)                                         # 状態のない行は除く
        self.assertEqual(recs[0]["state_date"], "2026-11-06")
        self.assertEqual(recs[0]["state_date_text"], "山梨県観光サイト11/6更新")

    def test_festival_note_is_separate_from_typical(self):
        rows = self.C.parse(CSV_TEXT)
        self.assertEqual(self.C.festivals_of(rows[1], 2026), [{"name": "試験の湖畔 紅葉まつり", "start": "2026-10-30", "end": "2026-11-15"}])
        self.assertNotIn("10/30", rows[1]["typical"])

    def test_wrong_shape_stops(self):
        with self.assertRaises(ValueError):
            self.C.parse("名前,状態\na,b\n")

    def test_records_are_hidden_until_the_source_is_approved(self):
        from ikimonobiyori import observations as O
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            recs = self.C.to_records(self.C.parse(CSV_TEXT), csv_url="https://www.yamanashi-kankou.jp/special/documents/koyo_1106.csv", updated="2026-11-06",
                                     prefecture="山梨県", publisher="試験", label="山梨県観光サイト{md}更新")
            now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))
            self.assertEqual(O.record(recs, env=env, now=now)["written"], 2)
            self.assertEqual(O.read_records("autumn_leaves", env), [])          # 承認待ち: 答えの材料にしない(記録は残る)
            with unittest.mock.patch.object(O, "_source_approved", return_value=True):
                rows = O.read_records("autumn_leaves", env)
            self.assertEqual({r["name"] for r in rows}, {"試験の渓谷周辺", "試験の湖畔"})   # 承認後は HTML が空でも CSV の現況が使われる
            self.assertEqual(rows[0]["state_date"], "2026-11-06")


class Part12Ordering(unittest.TestCase):
    def koyo(self):
        s = {"candidates": [spot("高尾山", 40, state=None, city="八王子市", elevation_m=599, festivals=[{"name": "もみじまつり", "start": "2026-11-01", "end": "2026-11-30"}]),
                            spot("昭和記念公園", 45, city="立川市", window=("11-05", "11-30"))]}
        s["candidates"][1]["current"]["age_days"] = 2
        return s

    def test_takao_without_status_is_below_showa_with_status(self):
        from ikimonobiyori import answer_plan as AP
        f = facts_doc({"autumn_leaves": self.koyo()}, dates=("2026-11-14", "2026-11-15"))
        plan = AP.build(f, "autumn_leaves")
        names = [p["name"] for p in plan["picks"]]
        self.assertLess(names.index("昭和記念公園"), names.index("高尾山"))

    def test_outlook_rank_still_comes_first(self):
        from ikimonobiyori import answer_plan as AP
        pol = AP.load_policy()
        peak = {"outlook": "in_peak", "has_current": False, "current_date": None, "score": 1, "name": "a"}
        late = {"outlook": "late", "has_current": True, "current_date": "2026-11-05", "current_age_days": 1, "score": 90, "name": "b"}
        self.assertLess(AP.rank_key(peak, pol), AP.rank_key(late, pol))

    def test_newer_status_ranks_above_older(self):
        from ikimonobiyori import answer_plan as AP
        pol = AP.load_policy()
        new = {"outlook": "in_peak", "has_current": True, "current_date": "2026-11-06", "current_age_days": 1, "score": 1, "name": "a"}
        old = {"outlook": "in_peak", "has_current": True, "current_date": "2026-11-01", "current_age_days": 6, "score": 90, "name": "b"}
        stale = {"outlook": "in_peak", "has_current": True, "current_date": "2026-10-01", "current_age_days": 37, "score": 99, "name": "c"}
        self.assertEqual(sorted([stale, old, new], key=lambda x: AP.rank_key(x, pol))[0]["name"], "a")
        self.assertEqual(sorted([stale, old, new], key=lambda x: AP.rank_key(x, pol))[-1]["name"], "c")

    def test_two_of_three_picks_have_status_when_available(self):
        from ikimonobiyori import answer_plan as AP
        c = [spot("現況なしの園", 20, state=None, city="一町"), spot("現況なしの山", 60, state=None, city="二町", elevation_m=900), spot("現況なしの湖", 130, state=None, city="三町"),
             spot("現況ありの園", 25, city="四町"), spot("現況ありの森", 70, city="五町"), spot("現況ありの浜", 125, city="六町")]
        for x in c:
            if x["current"]:
                x["current"]["age_days"] = 2
        plan = AP.build(facts_doc({"autumn_leaves": {"candidates": c}}), "autumn_leaves")
        self.assertGreaterEqual(sum(1 for p in plan["picks"] if p["has_current"]), 2)

    def test_pick_without_status_needs_the_note(self):
        from ikimonobiyori import answer_plan as AP
        f = facts_doc({"autumn_leaves": {"candidates": [spot("高尾山", 40, state=None, city="八王子市", elevation_m=900)]}})
        plan = AP.build(f, "autumn_leaves")
        note = plan["picks"][0]["note"]
        self.assertEqual(note, AP.load_policy()["evidence"]["no_current_note"])
        self.assertEqual([e["code"] for e in AP.plan_errors("", plan, None, ["① 高尾山: 例年の見頃です。"], V.short_names)], ["pick_note_missing"])
        self.assertEqual(AP.plan_errors("", plan, None, [f"① 高尾山: {note}。"], V.short_names), [])

    def test_festival_does_not_replace_status(self):
        from ikimonobiyori import answer_plan as AP
        pol = AP.load_policy()
        self.assertGreater(pol["bonus"]["festival_active"], 0)
        p = AP.build(facts_doc({"autumn_leaves": self.koyo()}), "autumn_leaves")
        takao = next(r for r in p["ranking"] if r["name"] == "高尾山")
        self.assertIsNone(takao["current_state"])                              # まつりがあっても現況にはならない


class Part13NoQuestions(unittest.TestCase):
    def test_question_sentences_fail(self):
        for s in ("好みを1つ教えてください。", "近さと、見られる種類のどちらを優先しますか。", "花と野鳥のどちらを先に見に行きたいですか?", "冬桜と紅葉を重視しますか。", "いかがでしょうか。"):
            self.assertEqual([e["code"] for e in V.question_errors(s, RULES)], ["question_in_answer"], s)

    def test_statements_pass(self):
        for s in ("アクセスや混雑は出かける前に公式ページで確認してください。", OFFER, "連絡先は公式ページで確認してください。", "例年の見頃は11月です。"):
            self.assertEqual(V.question_errors(s, RULES), [], s)

    def test_answer_types_have_no_tail_question(self):
        from ikimonobiyori import wildflower, wildflower_species as WS, regress
        texts = [wildflower.overview(date_="2026-07-15", area="丹沢")["text"], WS.species_answer("チングルマ", month=7)["text"]]
        P = guide.load_policy()
        for t in texts:
            self.assertEqual(V.question_errors(t, RULES), [], t[-60:])
        self.assertNotIn("next_question", P["answer"])
        f = facts_doc({"autumn_leaves": koyo_subject()})
        from ikimonobiyori import answer_plan as AP
        plan = AP.build(f, "autumn_leaves")
        self.assertEqual(V.question_errors(regress.compose_answer(f, plan), RULES), [])
        self.assertEqual(regress.run_flows()[0]["ok"], True)

    def test_check_fails_an_answer_with_a_tail_question(self):
        f = facts_doc({"autumn_leaves": koyo_subject()})
        r = V.check("試験の園です。\n近さと見どころのどちらを優先しますか。\n", f, RULES)
        self.assertIn("question_in_answer", [e["code"] for e in r["answer_errors"]])
        self.assertFalse(V.generic_check("おすすめです。\n① あ\n② い\n③ う\n好みを教えてください。")["ok"])

    def test_clarify_exception(self):
        self.assertTrue(V.generic_check("どの場所のことでしょうか。", clarify=True)["ok"])
        self.assertFalse(V.generic_check("おすすめです。\nどの場所のことでしょうか。", clarify=True)["ok"])


class Part7Skeleton(unittest.TestCase):
    """動作確認で見つけた点(合成データ)。「記載なし」は現況に数えない。骨組みは初回の検査に通る。"""
    def test_unreadable_state_is_not_current(self):
        from ikimonobiyori import answer_plan as AP
        c = spot("試験の園", 20)
        self.assertTrue(AP.has_current(c))
        from ikimonobiyori import observations as O
        c["current"]["state"] = O.load_policy()["unknown_state"]
        self.assertFalse(AP.has_current(c))
        c = spot("試験の園", 20)
        c["current"]["symbol_only"] = True
        self.assertFalse(AP.has_current(c))
        self.assertFalse(AP.has_current(spot("試験の園", 20, state=None)))

    def test_skeleton_passes_first_check(self):
        from ikimonobiyori import answer_plan as AP, skeleton as SK
        cases = [{"autumn_leaves": koyo_subject()}, {"flowers": flower_subject(), "birds": bird_subject()}]
        for subs in cases:
            f = facts_doc(subs)
            f["lines"]["origin_line"] = "横浜からの距離で選びました。"
            plan = AP.build_all(f) if len(subs) > 1 else AP.build(f, next(iter(subs)))
            text = SK.compose(f, plan)
            r = V.check(text, f, RULES, plan=plan)
            self.assertTrue(r["ok"], (text, V.report_lines(r)))


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
