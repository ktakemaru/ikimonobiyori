"""段階59(指示書 docs/stage59-nature-guide-knowledge-instructions.md): 知識の層。通信しない。合成データだけ。"""
import json
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import pdf_text as PT

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))


def minimal_pdf(path, text_lines=()):
    """手で作った最小の PDF(ASCII の本文。text_lines が空ならテキストなし)。"""
    content = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({l}) Tj 0 -14 Td" for l in text_lines) + " ET" if text_lines else ""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for x in offs:
        out += f"{x:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(path).write_bytes(out)


class Part6Pdf(unittest.TestCase):
    def test_vertical_lines_are_joined(self):
        self.assertEqual(PT.join_vertical("見\n出\nし\nの\n文\n普通の行"), "見出しの文\n普通の行")
        self.assertEqual(PT.join_vertical("1\n2\n普通"), "1\n2\n普通")               # 短い並びは連結しない

    def test_assess_status(self):
        self.assertEqual(PT.assess(""), "読めない")
        self.assertEqual(PT.assess("1 2 3 45 678"), "画像のみ")
        self.assertEqual(PT.assess("紅葉" * 20), "一部")
        self.assertEqual(PT.assess("紅葉" * 200), "読めた")

    def test_pdfminer_reads_minimal_pdfs(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "t.pdf", Path(d) / "n.pdf"
            minimal_pdf(a, ["Autumn leaves", "Okutama"])
            minimal_pdf(b)
            self.assertIn("Okutama", PT.extract_with_pdfminer(a))
            self.assertEqual(PT.extract_with_pdfminer(b).strip(), "")

    def test_methods_in_order_and_unread(self):
        good = "紅葉" * 200
        got = PT.read_with_methods([("a", lambda: ""), ("c", lambda: good)])
        self.assertEqual((got["method"], got["status"]), ("c", "読めた"))

        def boom():
            raise OSError("拒否")
        got = PT.read_with_methods([("a", boom), ("c", lambda: "1 2 3")])
        self.assertEqual((got["method"], got["status"], got["text"]), ("d", "PDF 未読", None))

    def test_ledger_keeps_no_full_text(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            body = "奥多摩の紅葉は標高で約一か月ずれるという本文" * 30
            row = PT.record_publication({"facility": "試験VC", "title": "季刊誌", "issue": "10号", "published": "2023-10", "url": "https://x.example/a.pdf", "format": "pdf", "taken_on": "2026-11-07"},
                                        text=body, env=env, read_method="c")
            self.assertEqual(row["status"], "読めた")
            self.assertTrue(row["hash"])
            raw = PT.ledger_path(env).read_text(encoding="utf-8")
            self.assertNotIn("標高で約一か月", raw)
            self.assertEqual(PT.load_publications(env)[0]["method"], "c")
            un = PT.record_publication({"facility": "試験VC", "title": "図", "url": "https://x.example/b.pdf"}, env=env)
            self.assertEqual(un["status"], "PDF 未読")

    def test_latest_issue_uses_only_dated(self):
        rows = [{"title": "a", "published": "2023-10"}, {"title": "b", "published": "2025-04"}, {"title": "c", "published": None}, {"title": "d", "published": "秋号"}]
        self.assertEqual(PT.latest_issue(rows)["title"], "b")
        self.assertIsNone(PT.latest_issue([{"title": "c", "published": None}]))

    def test_dependency_is_pinned(self):
        self.assertRegex((ROOT / "requirements.txt").read_text(encoding="utf-8"), r"pdfminer\.six==\d+")


class Part1Survey(unittest.TestCase):
    OLD = ("env.go.jp/content/900509696.pdf", "env.go.jp/nature/ari_kata/shiryou/031010-7.pdf", "env.go.jp/nature/yasei/guide/pdf/VC.pdf")

    def test_old_material_is_not_in_the_ledger(self):
        raw = (ROOT / "ikimonobiyori" / "data" / "visitor_centers" / "centers.yaml").read_text(encoding="utf-8")
        for u in self.OLD:
            self.assertNotIn(u, raw)

    def test_new_centers_are_pending_and_checked(self):
        from ikimonobiyori import visitor_centers as VC
        rows = {c["id"]: c for c in VC.load_centers()}
        for i in ("urabandai-vc", "kamikochi-vc", "picchio", "tanigawa-ic"):
            self.assertEqual(rows[i]["approval"]["status"], "pending", i)
            self.assertEqual(rows[i]["checked_on"], "2026-11-07")
            self.assertNotIn("approved_by", rows[i]["approval"])
        oz = rows["oze-fnd"]                                                         # 段階67: 本人の承認(2026-11-09。承認欄 E)
        self.assertEqual((oz["approval"]["status"], oz["approval"]["approved_by"], oz["approval"]["approved_on"], oz["checked_on"]), ("approved", "user", "2026-11-09", "2026-11-07"))


def card(**kw):
    base = {"title": "試験の紅葉は標高でずれる", "category": "季節の仕組み", "place": "試験山", "place_aliases": ["試験の森"], "facts": ["高いところから順に色づく", "見頃は約1か月続く"],
            "condition": {"months": [10, 11], "year_dependent": False}, "source": {"name": "試験VC", "title": "季刊誌", "url": "https://vc.example.org/a.pdf", "checked_on": "2026-11-07", "page": 2},
            "confidence": "施設の観察記録", "rights": "無断転載不可。事実のみ", "usage": "ガイドの目として1行"}
    base.update(kw)
    return base


class Part2Cards(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import knowledge as K
        self.K = K
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def test_valid_card(self):
        self.assertEqual(self.K.validate(card()), [])

    def test_limits(self):
        self.assertTrue(self.K.validate(card(facts=["a"] * 6)))
        self.assertTrue(self.K.validate(card(facts=["あ" * 61])))
        self.assertTrue(self.K.validate(card(facts=["「原文の文です」"])))                 # 引用符で原文を残さない
        self.assertTrue(self.K.validate(card(facts=["文です。二つめの文です。三つめ。"])))   # 原文のような文
        self.assertTrue(self.K.validate(card(source={"name": "x"})))                        # 出典が必須
        self.assertTrue(self.K.validate(card(confidence=None)))
        self.assertTrue(self.K.validate(card(condition={"year_dependent": True})))          # 年に依存する事実には年
        self.assertEqual(self.K.validate(card(condition={"year_dependent": True, "year": 2023})), [])

    def test_add_search_and_store_outside_the_repository(self):
        self.K.add(card(), self.env)
        self.K.add(card(title="別のカード", category="安全", facts=["クマに注意する"], condition={"months": [6]}), self.env)
        self.assertEqual(len(self.K.load(self.env)), 2)
        self.assertEqual([r["title"] for r in self.K.search(self.env, category="安全")], ["別のカード"])
        self.assertEqual([r["title"] for r in self.K.search(self.env, month=11)], ["試験の紅葉は標高でずれる"])
        self.assertEqual(len(self.K.search(self.env, place="試験の森")), 2)
        self.assertIn(Path(self.tmp.name).resolve(), self.K.path(self.env).resolve().parents)
        with self.assertRaises(ValueError):
            self.K.add(card(facts=["あ" * 61]), self.env)

    def test_no_real_cards_in_the_repository(self):
        for f in (ROOT / "ikimonobiyori" / "data").rglob("*"):
            self.assertNotIn(f.name, ("cards.jsonl", "publications.jsonl"), str(f))


def spot(name, km=20, city="試験山", **kw):
    cur = {"state": "見頃", "state_raw": "見頃", "state_date": "2026-11-05", "publisher": "試験市", "url": f"https://kouyou.example.org/{km}", "source_class": "official", "freshness": "fresh", "age_days": 2,
           "read_at": "2026-11-07T09:00:00+09:00"}
    return {"id": "t-" + name, "name": name, "city": city, "prefecture": "東京都", "current": cur, "current_unknown": False, "distance_km": km,
            "typical": [{"text": "例年11月", "start": "11-01", "end": "11-30", "url": "https://kouyou.example.org/t", "publisher": "試験市", "source_class": "official"}], "typical_line": "例年の見頃: 11月",
            "events": [], "history": [], "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak", **kw}


def facts_doc(cards, *spots, month="11"):
    return {"schema": "ikimono-ask-facts/1", "now": "2026-11-07T12:00:00+09:00", "dates": [f"2026-{month}-08"], "origin": "横浜", "region": "全範囲", "knowledge_cards": cards,
            "subjects": {"autumn_leaves": {"subject": "autumn_leaves", "candidates": list(spots), "avoid": [], "nearby_out_of_region": [], "alternatives": []}},
            "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None, "origin_line": "横浜からの距離で選びました。"}, "summary_pages": [], "this_round": {}}


class Part5Skeleton(unittest.TestCase):
    def test_old_display_of_the_named_publisher_is_written_as_reference(self):
        from ikimonobiyori import skeleton as SK
        cur = {"publisher": "箱根町観光協会", "state_date": "2026-11-03"}
        self.assertTrue(SK._stale_display(cur, date(2026, 11, 7)))
        self.assertFalse(SK._stale_display(cur, date(2026, 11, 5)))
        self.assertFalse(SK._stale_display({"publisher": "試験市", "state_date": "2026-10-01"}, date(2026, 11, 7)))


class Part4GuideEye(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import knowledge as K, answer_plan as AP, skeleton as SK, ask_verify as V
        self.K, self.AP, self.SK, self.V = K, AP, SK, V
        self.rules = V.load_rules()

    def test_selection_by_place_season_and_priority(self):
        cards = [card(), card(title="安全のカード", category="安全", facts=["クマに注意する"]), card(title="保全のカード", category="保全・マナー", facts=["登山道を外れない"]),
                 card(title="別の山", place="別山", place_aliases=[]), card(title="春のカード", condition={"months": [4]})]
        got = self.K.select(["試験山"], month=11, cards=cards)
        self.assertEqual([c["title"] for c in got], ["安全のカード", "保全のカード"])        # 最大 2 枚。安全・保全が先
        self.assertEqual(self.K.select(["遠い町"], month=11, cards=cards), [])

    def test_eye_line_is_separate_with_source_and_passes(self):
        c1 = card()
        f = facts_doc([c1], spot("試験山の森", 40, city="試験山"))
        plan = self.AP.build(f, "autumn_leaves")
        text = self.SK.compose(f, plan, cards=[c1])
        self.assertIn("ガイドの目: 高いところから順に色づく。見頃は約1か月続く(試験VC)", text)
        eye_line = next(l for l in text.splitlines() if l.startswith("ガイドの目:"))
        self.assertNotIn("11/5時点", eye_line)                                     # 現況と別の行
        self.assertIn("https://vc.example.org/a.pdf", text)
        r = self.V.check(text, f, self.rules, plan=plan)
        self.assertTrue(r["ok"], (text, self.V.report_lines(r)))

    def test_year_dependent_says_the_year(self):
        c1 = card(condition={"year_dependent": True, "year": 2023, "months": [11]})
        self.assertIn("2023年の記録では、", self.K.line_for(c1))

    def test_safety_goes_to_before_you_go(self):
        s = card(title="クマ", category="安全", facts=["朝夕はクマに注意する"])
        eye, before, urls = self.K.split_lines([s])
        self.assertEqual(eye, [])
        self.assertEqual(before, ["朝夕はクマに注意する(試験VC)"])
        self.assertEqual(urls, ["https://vc.example.org/a.pdf"])

    def test_no_card_no_line_and_no_offer(self):
        f = facts_doc([], spot("試験山の森", 40))
        text = self.SK.compose(f, self.AP.build(f, "autumn_leaves"), cards=[])
        self.assertNotIn("ガイドの目", text)

    def test_check_rejects_invented_facts(self):
        c1 = card()
        errs = self.K.answer_errors("ガイドの目: 高いところから順に色づく。夜はライトアップされる(試験VC)\n", [c1])
        self.assertEqual([e["code"] for e in errs], ["guide_eye_not_from_card"])
        errs = self.K.answer_errors(self.K.line_for(c1) + "\n", [c1])
        self.assertEqual(errs, [])
        wrong = self.K.line_for(c1).replace("試験VC", "別の施設")
        self.assertEqual([e["code"] for e in self.K.answer_errors(wrong, [c1])], ["guide_eye_not_from_card"])


def sakura_cards():
    S = {"name": "試験の研究所", "url": "https://kenkyu.example.org/s", "checked_on": "2026-11-07"}
    return [card(title="冬桜とは", category="種の解説", place="冬桜", place_aliases=["フユザクラ"], facts=["秋から冬と春に二度咲く", "見頃は例年11月中旬〜12月上旬"], source=S, condition={"months": list(range(1, 13))}),
            card(title="冬桜と寒桜の違い", category="種の解説", place="冬桜", place_aliases=["寒桜"], facts=["寒桜は1〜2月に咲く淡紅色の一重"], source=S, condition={"months": list(range(1, 13))}),
            card(title="山桜", category="種の解説", place="ヤマザクラ", place_aliases=["山桜"], facts=["葉の展開と同時に咲く"], source=S, condition={"months": list(range(1, 13))}),
            card(title="桜を守る", category="保全・マナー", place="冬桜", place_aliases=["桜"], facts=["枝を折らない"], source=S, condition={"months": list(range(1, 13))})]


class Part7Intent(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import intent
        self.I = intent

    def test_classify(self):
        for q, want in (("冬桜について教えて", "knowledge"), ("冬桜と寒桜の違いを教えて", "difference"), ("山桜とか豆桜というのもあるんだ", "chat"), ("今見られる桜ってある?", "now"),
                        ("明日 紅葉を見に行きたい。おすすめある?", "plan"), ("カワセミはどこで見られる?", "place_time"), ("西沢渓谷の紅葉はどう?", "now")):
            self.assertEqual(self.I.classify(q), want, q)

    def test_knowledge_answer_leads_with_knowledge_and_passes(self):
        cards = sakura_cards()
        text = self.I.compose("冬桜について教えて", cards=cards)
        self.assertTrue(text.startswith("冬桜とは:"), text)
        self.assertIn("ガイドの目: 枝を折らない", text)
        self.assertEqual(self.I.check(text, cards), [])
        self.assertNotIn("？", text)

    def test_shorter_word_inside_a_longer_one_is_not_a_topic(self):
        self.assertEqual(self.I.topics("冬桜について教えて", sakura_cards()), ["冬桜"])

    def test_no_card_returns_none(self):
        self.assertIsNone(self.I.compose("知らない花について教えて", cards=sakura_cards()))

    def test_check_finds_defects(self):
        cards = sakura_cards()
        for text, code in (("① 桜山公園\n② 別の公園\n", "knowledge_starts_with_list"), ("冬桜です。\n好みを1つ教えてください。\n", "question_in_answer"), ("冬桜です。ご希望なら調べます。\n", "process_excuse"),
                           ("名所の一覧に入っていないのでお答えできません。\n", "knowledge_refused"), ("冬桜は7000本あります。\n", "knowledge_fact_not_in_card"), ("冬桜です。\nhttps://other.example/x\n", "knowledge_source_unused"),
                           ("葉の展開と同時に咲く。\n", "knowledge_source_missing")):
            self.assertIn(code, [e["code"] for e in self.I.check(text, cards)], text)

    def test_cards_recorded_before_use(self):
        from ikimonobiyori import knowledge as K
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            self.assertIsNone(self.I.compose("試験の花について教えて", env=env))
            K.add(card(title="試験の花", category="種の解説", place="試験の花", facts=["春に咲く"]), env)
            self.assertIn("春に咲く", self.I.compose("試験の花について教えて", env=env))


if __name__ == "__main__":
    unittest.main()
