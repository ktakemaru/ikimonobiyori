"""段階84 の続き(本人の判断 2026-11-15 の 1〜4・直し A・B)。合成データ(通信しない)。"""
import unittest
from datetime import datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_verify as GV
from ikimonobiyori import knowledge as K
from ikimonobiyori import observations as O
from ikimonobiyori import research as R

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 15, 9, 0, tzinfo=JST)


class NoPolicyRights(unittest.TestCase):
    def card(self, rights, url):
        return {"confidence": "公的資料", "rights": rights, "source": {"name": "試験市", "url": url}}

    def test_municipal_page_without_policy_is_shown(self):
        self.assertTrue(K.usable(self.card("規約の記載なし(2026-11-15)。事実のみ", "https://www.city.example.lg.jp/a"), [])[0])
        self.assertTrue(K.usable(self.card("規約の記載なし(2026-11-15)。事実のみ", "https://www.city.toda.saitama.jp/a"), [])[0])

    def test_not_municipal_or_unread_is_hidden(self):
        self.assertFalse(K.usable(self.card("規約の記載なし(2026-11-15)", "https://www.env.go.jp/a"), [])[0])      # 国の機関は対象外
        self.assertFalse(K.usable(self.card("規約の記載なし(2026-11-15)", "https://maruchiba.jp/a"), [])[0])
        self.assertFalse(K.usable(self.card("規約の確認: 未読", "https://www.city.example.lg.jp/a"), [])[0])    # 読めていないものは出さない

    def test_confirmed_unchanged(self):
        self.assertTrue(K.usable(self.card("確認済み(2026-11-15)。…", "https://www.env.go.jp/a"), [])[0])


class OperatorCheck(unittest.TestCase):
    def test_address_and_longer_names_not_counted(self):
        op = "清津峡渓谷トンネル管理事務所 〒949-8433 新潟県十日町市小出 写真提供:(一社)十日町市観光協会"
        self.assertFalse(R._verified("", "十日町市", op))
        self.assertTrue(R._verified("", "清津峡渓谷トンネル管理事務所", op))

    def test_copyright_lines_counted(self):
        self.assertTrue(R._verified("", "十日町市", "© 十日町市 All rights reserved."))
        self.assertTrue(R._verified("", "日高市", "© 2024 埼玉県日高市巾着田管理事務所"))
        self.assertTrue(R._verified("", "日動美術財団", "Copyright © 2025 公益財団法人 日動美術財団笠間日動美術館"))

    def test_temple_and_garden_operators_are_official_forms(self):
        for name in ("大本山方広寺", "乾徳山恵林寺", "谷保天満宮", "浜名湖えんてつグループ", "○○庭園"):
            self.assertTrue(R._declared_ok(name), name)
        self.assertFalse(R._declared_ok("株式会社試験"))


class RecordEvents(unittest.TestCase):
    def setUp(self):
        self.old = O.read_records
        recs = {
            "flowers": [
                {"name": "試験梅林", "prefecture": "茨城県", "city": "試験市", "kind": "梅", "source_class": "official", "url": "https://a.example.lg.jp/1",
                 "publisher": "試験市", "event": {"name": "第1回試験梅まつり(2027)", "start": "2027-02-11", "end": "2027-03-22"}},
                {"name": "試験公園", "prefecture": "群馬県", "city": "試験町", "kind": "冬桜", "source_class": "official", "url": "https://b.example.lg.jp/1",
                 "publisher": "試験町", "event": {"name": "冬桜まつり(2026)", "start": "2026-12-06", "end": None}},
                {"name": "試験公園", "prefecture": "群馬県", "city": "試験町", "kind": "冬桜", "source_class": "official", "url": "https://b.example.lg.jp/1",
                 "publisher": "試験町", "event": {"name": "冬桜まつり(2026)", "start": "2026-12-06", "end": "2026-12-06"}},
                {"name": "試験庭園", "prefecture": "東京都", "city": "試験区", "kind": "梅", "source_class": None, "url": "https://c.example.com/1",
                 "event": {"name": "紹介サイトの梅まつり", "start": "2027-02-01", "end": "2027-02-28"}},
            ],
            "birds": [],
        }
        O.read_records = lambda sj, *a, **k: recs.get(sj, [])

    def tearDown(self):
        O.read_records = self.old

    def facts(self, q, cond=None):
        F = GB._Facts(GB.cfg(), set())
        GB._record_events(F, q, cond or {"defaulted_date": True}, NOW, None, GB.cfg())
        return [f["content"] for f in F.rows if f["kind"] == "event"]

    def test_month_question_with_species(self):
        got = self.facts("2月の週末、梅を見たい")
        self.assertEqual(len(got), 1)
        self.assertIn("2027年2月11日(木)〜2027年3月22日(月)", got[0])          # 紹介サイトの記録は入れない

    def test_event_question_next_month_falls_back_to_later(self):
        got = self.facts("来月、梅の行事はある?")                             # 12 月の梅の行事はない → そのあとの行事
        self.assertEqual(len(got), 1)
        self.assertIn("試験梅まつり", got[0])

    def test_place_question_one_record_once(self):
        got = self.facts("試験公園の冬桜の行事はいつ?")
        self.assertEqual(got, ["試験公園: 冬桜まつり(2026): 2026年12月6日(日)"])

    def test_no_event_for_plain_question(self):
        self.assertEqual(self.facts("梅について教えて"), [])


class TraitsIdentifyForm(unittest.TestCase):
    def errs(self, text):
        return [e["code"] for e in GV.trait_errors(GV.sentences([text]), {}, GV.cfg())]

    def test_only_identify_form(self):
        self.assertIn("trait_without_card", self.errs("白い大きな鳥がいたら、ハクチョウです。"))
        self.assertIn("trait_without_card", self.errs("くちばしの黄色が小さいのがコハクチョウです。"))
        for t in ("カワセミは小さな池でも見られます。", "大きな群れのコハクチョウが見られます。", "白い花が咲く公園でツワブキも見られます。"):
            self.assertEqual(self.errs(t), [], t)


if __name__ == "__main__":
    unittest.main()
