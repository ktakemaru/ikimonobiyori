"""段階65: 段階64の積み残しと、会話の練習(11/9)の修正。合成データ・通信なし。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_plan as AP

import test_stage56 as T56

POL = AP.load_policy()
cand = T56.cand


def plan_of(cands, origin="大宮", dates=("2026-11-14", "2026-11-15")):
    f = T56.facts_of(cands, dates=dates)
    f["origin"] = origin
    return AP.build(f, "autumn_leaves", POL)


class Part1DriveAimFromOtherOrigins(unittest.TestCase):
    """第1部: 出発地が横浜以外でも「ドライブ・足を延ばして」の枠が今回のおすすめに入る。"""

    CS = [cand("近い公園", km=27, state="色づき始め", sdate="2026-11-06", age=2, typical=("11-20", "11-30"), prefecture="埼玉県"),
          cand("試験の渓谷の橋", km=51, state="色づき始め", sdate="2026-11-05", age=3, typical=None, city="試験町", prefecture="埼玉県"),
          cand("試験の山", km=46, state="色づき始め", sdate="2026-11-06", age=2, typical=("11-10", "12-05"), elev=600, prefecture="東京都")]

    def test_drive_first_is_a_pick_for_omiya(self):
        p = plan_of(self.CS)
        drive = next(s for s in p["sections"] if s["aim"] == "drive")
        self.assertEqual(drive["items"][0]["name"], "試験の渓谷の橋")
        self.assertIn("試験の渓谷の橋", [x["name"] for x in p["picks"]])

    def test_same_plan_shape_for_another_origin(self):
        p = plan_of(self.CS, origin="新宿")
        self.assertIn("drive", [x["aim"] for x in p["picks"]])

    def test_boundary_distance_is_near_not_drive(self):
        # 長瀞(月の石もみじ公園)が大宮から 50km で「近場」に入る決まり(近場は near_max_km 以内)をそのまま確かめる
        c = cand("境の渓谷", km=POL["aims"]["near_max_km"], state="色づき始め", sdate="2026-11-05", age=3, typical=None)
        self.assertEqual(AP.score_candidate(c, ["2026-11-14"], POL)["aim"], "near")


class Part3ApprovalList(unittest.TestCase):
    """第3部: 承認の一覧(docs/sources-approval.md)は台帳から作る。台帳と一覧の承認の状態が食い違ったら落ちる。"""

    def setUp(self):
        from ikimonobiyori import approval_list as AL
        self.AL = AL
        self.doc = (H.ROOT / "docs" / "sources-approval.md").read_text(encoding="utf-8")

    def test_the_doc_is_what_the_ledgers_produce(self):
        self.assertEqual(self.doc, self.AL.render(), "台帳を変えたら python -X utf8 -m ikimonobiyori.ask sources --approval > docs/sources-approval.md")

    def test_each_item_is_in_the_section_of_its_ledger_status(self):
        pending = self.doc.split("## 1. 承認待ち")[1].split("## 2. 承認済み")[0]
        approved = self.doc.split("## 2. 承認済み")[1].split("## 3.")[0]
        for r in self.AL.collect():
            if r["ledger"] == "catalog" and r["status"] == "approved" and r["by"] != "user":
                continue                                          # 仮の承認のカタログは件数だけ
            key = r["name"] if r["ledger"] == "centers" and r["status"] == "pending" else f"（{r['id']}）" if r["ledger"] != "centers" else r["id"]
            if r["status"] == "pending":
                self.assertIn(key, pending, r["id"])
                self.assertNotIn(f"（{r['id']}）", approved, r["id"])
            elif r["status"] == "approved":
                self.assertIn(key, approved, r["id"])
                self.assertNotIn(f"（{r['id']}）", pending, r["id"])

    def test_render_follows_a_changed_status(self):
        rows = [{"ledger": "sources", "file": "x.yaml", "id": "t-src", "name": "試験の協会", "status": "pending", "by": None, "on": None, "url": "https://example.org/",
                 "kind": "status_page", "publisher_kind": "municipality", "reason": "試験", "readable": {}, "terms": {}}]
        a = self.AL.render(rows, {"sources": {}})
        rows[0].update(status="approved", by="user", on="2026-11-09")
        b = self.AL.render(rows, {"sources": {}})
        self.assertIn("試験の協会（t-src）", a.split("## 2. 承認済み")[0])
        self.assertIn("試験の協会（t-src）", b.split("## 2. 承認済み")[1])
        self.assertNotIn("試験の協会（t-src）", b.split("## 2. 承認済み")[0])

    def test_named_items_are_approved_in_the_list(self):
        approved = self.doc.split("## 2. 承認済み")[1].split("## 3.")[0]
        for i in ("nagatoro-kanko-koyo", "chichibu-navi-koyo", "yamanashi-kankou-koyo-csv", "nagatoro-koyo-matsuri-2026", "kanagawa-museum", "kana-garden-news",
                  "kouyou-0063", "kouyou-0064", "kouyou-0065"):
            self.assertIn(f"（{i}）", approved, i)


def _card(title, place, cat, facts, aliases=(), src="試験の自然博物館"):
    return {"title": title, "category": cat, "place": place, "place_aliases": list(aliases), "facts": list(facts), "condition": {"year_dependent": False},
            "source": {"name": src, "title": "試験の資料", "url": "https://example.org/" + title, "checked_on": "2026-11-01"},
            "confidence": "紹介", "rights": "確認済み", "usage": "ガイドの目として1行"}


def _hcand(cid, name, city, start, end, kind=None, events=(), point=None):
    return {"id": cid, "name": name, "city": city, "area": None, "prefecture": "栃木県", "point": point, "flower_kinds": [kind] if kind else [],
            "typical": [{"start": start, "end": end, "text": "例年", "url": "https://example.org/w-" + cid, "kind": kind, "source_class": "official"}],
            "events": list(events)}


class Part4Highlights(unittest.TestCase):
    """第4部: 「見どころ」の型(日付のない、場所の質問)。"""

    CARDS = [_card("試験の高原の湿原", "戦場ヶ原", "季節の仕組み", ["湿原の草原は秋に黄金色になる", "周りの森はカラマツが多い"]),
             _card("試験のクマ", "奥日光", "安全", ["クマがいることを意識して歩く"]),
             _card("試験の花の流れ", "奥日光", "見頃の流れ", ["4月下旬に花が咲き始める"]),
             _card("よその町の話", "神奈川", "季節の仕組み", ["関係のない事実"])]
    CENTERS = [{"id": "t-vc", "name": "試験の日光ビジターセンター", "operator": "試験", "class": "official", "approval": {"status": "approved"}},
               {"id": "t-vc2", "name": "試験の那須の森", "operator": "試験", "class": "official", "approval": {"status": "pending"}}]

    def compose(self, q, **kw):
        from datetime import date
        from ikimonobiyori import highlights as HL
        cands = {"autumn_leaves": [_hcand("t-1", "奥日光 戦場ヶ原", "日光市", "10-01", "10-20")],
                 "flowers": [_hcand("t-2", "試験の高原", "日光市", "06-10", "07-10", kind="ニッコウキスゲ"),
                             _hcand("t-3", "よその公園", "横浜市", "03-20", "04-10", kind="桜")],
                 "birds": []}
        return HL.compose(q, today=date(2026, 11, 9), cards=self.CARDS, centers=self.CENTERS, reports=[], cands=cands,
                          records={"autumn_leaves": [], "flowers": [], "birds": []}, **kw)

    def test_question_types(self):
        from ikimonobiyori import highlights as HL
        self.assertTrue(HL.is_highlights_question("日光や那須で見どころを教えて", cards=self.CARDS))
        self.assertTrue(HL.is_highlights_question("日光ってどんなところ", cards=self.CARDS))
        self.assertTrue(HL.is_highlights_question("戦場ヶ原で何が見られる", cards=self.CARDS))
        self.assertFalse(HL.is_highlights_question("今週末の日光の見どころは?", cards=self.CARDS))     # 日付があれば計画の型
        self.assertFalse(HL.is_highlights_question("日光の紅葉は今どう?", cards=self.CARDS))

    def test_route_is_highlights_only_without_a_date(self):
        from ikimonobiyori import answer_run as R
        from ikimonobiyori import ask
        self.assertEqual(R.resolve("筑波山の見どころを教えて", ask._clock())["route"], "highlights")
        self.assertEqual(R.resolve("今週末の日光の見どころは?", ask._clock())["route"], "plan")

    def test_answer_shape(self):
        r = self.compose("日光の見どころを教えて")
        t = r["text"]
        self.assertTrue(t.startswith("**日光の見どころ**"))
        self.assertIn("日光の自然: 湿原の草原は秋に黄金色になる。周りの森はカラマツが多い。", t)      # 冒頭はカードの事実
        self.assertLess(t.index("### 夏"), t.index("### 秋"))                                 # 季節の順
        self.assertIn("・試験の高原: ニッコウキスゲ(例年 6月上旬〜7月上旬)", t)
        self.assertNotIn("よその公園", t)
        self.assertNotIn("関係のない事実", t)
        self.assertIn("## 行く前に確認すること", t)                                            # 安全のカードは行く前に
        self.assertIn("・試験の日光ビジターセンター", t)                                       # 承認済みの施設
        self.assertNotIn("那須の森", t)                                                        # 承認待ちは出さない
        self.assertIn("出典", t)

    def test_no_material_no_padding(self):
        from datetime import date
        from ikimonobiyori import highlights as HL
        r = HL.compose("那須の見どころを教えて", today=date(2026, 11, 9), cards=[], centers=[], reports=[], cands={"autumn_leaves": [], "flowers": [], "birds": []},
                       records={"autumn_leaves": [], "flowers": [], "birds": []})
        self.assertTrue(r["needs_research"])
        self.assertNotIn("資料", r["text"])
        self.assertNotIn("観光名所", r["text"])

    def test_at_most_five_cards_and_categories_spread(self):
        many = [_card(f"試験{i}", "奥日光", "季節の仕組み", [f"事実{i}"]) for i in range(6)] + [_card("試験の鳥", "奥日光", "出会い方・歩き方", ["鳥の事実"])]
        from datetime import date
        from ikimonobiyori import highlights as HL
        g = HL.gather(HL.places("奥日光の見どころ", many), date(2026, 11, 9), cards=many, centers=[], reports=[],
                      cands={"autumn_leaves": [], "flowers": [], "birds": []}, records={"autumn_leaves": [], "flowers": [], "birds": []})
        self.assertEqual(len(g["cards"]), HL.cfg()["max_cards"])
        self.assertIn("試験の鳥", [c["title"] for c in g["cards"]])


class Part6Fixes(unittest.TestCase):
    """第6部: 会話の練習(11/9)の修正。"""

    def test_legend_symbols_are_read_for_the_publisher(self):
        from ikimonobiyori import observations as O
        n = lambda t, pub="日光市観光協会(日光旅ナビ)": O.normalize_with_legend("autumn_leaves", t, pub)
        self.assertEqual(n("▼ 10/23現在、終わりです。"), "見頃過ぎ")                      # 六方沢の型
        self.assertEqual(n("◎ ５割程度の色付きです。"), "見頃")                           # 足尾 銀山平の型(凡例の「真っ盛り」)
        self.assertEqual(n("◎ ５割程度の色付きです。", pub="凡例のない発行元"), O.load_policy()["unknown_state"])   # 凡例のない記号は断定しない
        self.assertEqual(n("11/3現在 終わりです。", pub="凡例のない発行元"), "見頃過ぎ")

    def _facts(self, region):
        avoid = [{"name": "試験の沢", "prefecture": "栃木県", "current": {"state": "見頃過ぎ", "state_raw": "▼ 10/23現在、終わりです。", "state_date": "2026-10-23",
                                                                        "publisher": "日光市観光協会", "source_class": "official", "url": "https://example.org/s"}}]
        return {"region": region, "subjects": {"autumn_leaves": {"candidates": [{"name": "試験の公園", "prefecture": "栃木県"}], "avoid": avoid}},
                "visitor_centers": [{"center": "nikko-yumoto-vc", "line": "x", "sentences": ["試験の発信。"], "url": "https://example.org/vc"}]}

    def test_avoid_and_facilities_only_when_a_region_was_asked(self):
        from ikimonobiyori import skeleton as SK
        t = SK.cfg()
        f = self._facts("茨城・栃木")
        self.assertEqual(SK.asked_prefectures(f), {"栃木県"})
        self.assertEqual(SK.avoid_lines(f, t)[0][0], "・試験の沢: 色褪せ・落葉始め 10/23現在、終わりです。(10/23時点、日光市観光協会)")
        self.assertEqual(len(SK.vc_lines(f, [{"name": "試験の公園"}], t, SK.asked_prefectures(f))), 1)    # 地域の承認済みの施設の発信
        self.assertEqual(SK.vc_lines(f, [{"name": "試験の公園"}], t), [])                                  # 地域の指定がなければ名所の地域だけ
        g = self._facts("全範囲")
        self.assertEqual(SK.asked_prefectures(g), set())

    def test_refresh_prefers_a_page_that_covers_many_candidates(self):
        from datetime import datetime
        from ikimonobiyori import answer_plan as AP2
        now = datetime.fromisoformat("2026-11-09T10:00:00+09:00")
        big = "https://example.org/list"
        cands = [{"name": f"試験の名所{i}", "current": None, "pages": [{"url": f"https://example.org/p{i}", "source_class": "official"}]
                  + ([{"url": big, "source_class": "official"}] if i >= 2 else [])} for i in range(6)]
        f = {"now": now.isoformat(), "subjects": {"autumn_leaves": {"candidates": cands}}}
        plan = {"subject": "autumn_leaves", "picks": [{"name": c["name"], "subject": "autumn_leaves"} for c in cands]}
        from unittest import mock
        from ikimonobiyori import page_cache as PC
        with mock.patch.object(PC, "page_kind", return_value="status"):
            got = AP2.refresh_targets(f, plan, reads={}, now=now)
        self.assertEqual(got[0]["url"], big)
        self.assertLessEqual(len(got), AP2.load_policy()["refresh"]["max_pages"])

    def test_skill_says_no_work_talk_around_the_answer(self):
        s = (H.ROOT / ".claude" / "skills" / "ikimono-weekend" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("前後に添える文にも書かない", s)
        self.assertIn("公開後の説明は題名と何のページか 1 文だけ", s)


if __name__ == "__main__":
    unittest.main()
