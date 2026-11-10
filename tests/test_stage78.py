"""段階78: 会話で見つかった不具合(第1部)・記録があるのに使われない問題(第2部)。合成データ(通信しない)。"""
import unittest
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_run as AR
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_materials as GM
from ikimonobiyori import guide_verify as GV
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=JST)
PL = "\n\n[場所]\n記録: 試験の渓谷\n"


def brief(**kw):
    c = GB.cfg()

    def f(fid, kind, content, url="https://example.org/a"):
        return {"id": fid, "kind": kind, "kind_label": c["kinds"][kind], "place": "試験の渓谷", "content": content, "values": GB.values(content),
                "source": "試験町", "source_class": "official", "url": url, "observed": None, "read_at": None}
    b = {"id": "b-s78", "question": "今週末の紅葉は?", "route": "plan", "intent": "plan",
         "candidates": [{"name": "試験の渓谷", "distance_text": "直線で約20km"},
                        {"name": "試験の岬", "distance_text": c["distance"]["across_bay_label"]}],
         "dates": {"today": "2026-11-11", "this_weekend": ["2026-11-14", "2026-11-15"], "next_weekend": ["2026-11-21", "2026-11-22"],
                   "periods": [["2026-11-14", "2026-11-15"]]},
         "facts": [f("F001", "typical", "試験の渓谷: 例年 11月中旬〜下旬")], "cards": [], "fallback": {"text": "今の形の答え\n"}}
    b.update(kw)
    return b


def codes(body, **kw):
    return [e["code"] for e in GV.check(body + PL, brief(**kw))["errors"]]


class Preamble(unittest.TestCase):
    """第1部 1・第3部 3: 先頭・末尾の作業の説明と英語の文。"""

    def test_work_note_at_the_head_fails(self):
        body = "資料から下書きを書き、検査に合格しました。合格した答えを、そのまま送ります。\n\n試験の渓谷は例年11月中旬〜下旬が見頃です。[F001]"
        self.assertIn("work_note", codes(body))

    def test_english_note_fails(self):
        body = "試験の渓谷は例年11月中旬〜下旬が見頃です。[F001]\n\nSame sentence needed; keep it as is."
        self.assertIn("english_note", codes(body))

    def test_plain_answer_passes(self):
        self.assertEqual(codes("試験の渓谷は例年11月中旬〜下旬が見頃です。[F001]"), [])


class Distance(unittest.TestCase):
    """第1部 2・3: 直線と明記する。東京湾の向こう側は数字を書かない。"""

    def test_across_bay_number_fails(self):
        self.assertIn("bay_distance", codes("試験の岬は直線で約51kmです。"))

    def test_without_straight_fails_and_with_straight_passes(self):
        self.assertIn("straight_distance", codes("試験の渓谷は横浜から約20kmです。"))
        self.assertEqual(codes("試験の渓谷は横浜から直線で約20kmです。"), [])

    def test_across_bay_places(self):
        self.assertTrue(GM.across_bay("千葉県", "南房総市", None, "横浜"))
        self.assertTrue(GM.across_bay("千葉県", None, {"lat": 34.9, "lon": 139.9}, "横浜"))
        self.assertFalse(GM.across_bay("千葉県", "我孫子市", None, "横浜"))
        self.assertFalse(GM.across_bay("神奈川県", "三浦市", None, "横浜"))

    def test_estimated_distance_is_not_shown_as_a_number(self):
        with mock.patch.object(GM, "place_info", return_value={}), mock.patch.object(GM, "straight_km", return_value=(None, None, None)):
            km, label = GM.distance_text("試験の公園", 40, "横浜", estimated=True, prefecture="神奈川県")
        self.assertIsNone(km)
        self.assertNotIn("40", label)

    def test_estimated_distance_is_recomputed_from_coordinates(self):
        with mock.patch.object(GM, "place_info", return_value={"prefecture": "神奈川県", "city": "横浜市泉区", "point": None}), \
                mock.patch.object(GM, "straight_km", return_value=(15, "point", {"lat": 35.39, "lon": 139.48})):
            km, label = GM.distance_text("試験の公園", 40, "横浜", estimated=True)
        self.assertEqual((km, label), (15, "直線で約15km"))


class Bold(unittest.TestCase):
    """第1部 8: 太字の記号が文字のまま見えないように。"""

    def test_paren_moved_out(self):
        self.assertEqual(GV.fix_bold("**南沢あじさい山(あきる野市)**は6月"), "**南沢あじさい山**(あきる野市)は6月")

    def test_unclosable_bold_is_removed(self):
        self.assertEqual(GV.fix_bold("は**「氷の花」**です"), "は「氷の花」です")

    def test_normal_bold_kept(self):
        self.assertEqual(GV.fix_bold("**高尾山**は"), "**高尾山**は")
        self.assertEqual(GV.fix_bold("**A(B)**。"), "**A(B)**。")

    def test_final_text_is_fixed(self):
        r = GV.check("**試験の渓谷(試験町)**は例年11月中旬〜下旬が見頃です。[F001]" + PL, brief())
        self.assertIn("**試験の渓谷**(試験町)は", r["final"])


class SourceNames(unittest.TestCase):
    """第1部 5・6: ドメインのままの出典の名前・指定管理者の区分。"""

    def test_prefecture_domain_gets_the_prefecture_name(self):
        self.assertEqual(GM.source_name("https://www.pref.saitama.lg.jp/e1601/a.html", "saitama.lg.jp"), "埼玉県")

    def test_city_domain_uses_the_place(self):
        self.assertEqual(GM.source_name("https://www.city.abiko.chiba.jp/x.pdf", "abiko.chiba.jp"), "我孫子市(鳥の博物館)")

    def test_given_name_is_kept(self):
        self.assertEqual(GM.source_name("https://example.org/", "試験町観光協会"), "試験町観光協会")

    def test_designated_manager_is_official(self):
        self.assertEqual(GB._source_class("https://machida-shikisainomori.com/news/"), "official")

    def test_transport_operator_stays_not_official(self):
        self.assertEqual(GB._source_class("https://www.ooyama-cable.co.jp/"), "secondary")


class PendingArticle(unittest.TestCase):
    """第1部 7: 承認待ちの一覧(花だより)の下の記事の今年の現況は、資料に入れない。承認済みの情報源のページは入る。"""

    def test_pending_article_dropped(self):
        F = GB._Facts(GB.cfg(), GB._pending_urls())
        self.assertIsNone(F.add("current", "国営昭和記念公園: 見頃始め(11/5時点)", url="https://www.showakinen-koen.jp/hanadayori/76765/",
                                source_class="official"))

    def test_approved_page_kept(self):
        F = GB._Facts(GB.cfg(), GB._pending_urls())
        self.assertIsNotNone(F.add("current", "国営昭和記念公園(日本庭園): カエデ類 色づき始め(11/3時点)", url="https://www.showakinen-koen.jp/",
                                   source_class="official"))


class AltDestination(unittest.TestCase):
    """第1部 4: 代わりの行き先は、場所を聞いていてその場所が今は楽しめないときだけ。種を聞く質問には付けない。"""
    TYP = [{"name": "試験沼", "theme": "野鳥", "kinds": ["冬鳥"]}, {"name": "試験の桜山", "theme": "桜", "kinds": ["冬桜"]}]

    def test_species_question_keeps_only_the_species(self):
        self.assertEqual(GB._alt_filter(self.TYP, "ホタルが見られる地域と時期を教えて", {"route": "season_place"}, [], [], GB.cfg()), [])
        got = GB._alt_filter(self.TYP, "冬桜はどこで見られる?", {"route": "season_place"}, [], [], GB.cfg())
        self.assertEqual([t["name"] for t in got], ["試験の桜山"])

    def test_place_question_only_when_not_enjoyable(self):
        cands = [{"name": "試験の渓谷", "basis": "current", "current_state": "見頃"}]
        cond = {"route": "highlights", "area_names": ["試験山"]}
        self.assertEqual(GB._alt_filter(self.TYP, "今の時期、試験山の見どころは?", cond, cands, [], GB.cfg()), [])
        self.assertEqual(len(GB._alt_filter(self.TYP, "今の時期、試験山の見どころは?", cond, [], [({}, True)], GB.cfg())), 2)

    def test_plan_question_unchanged(self):
        self.assertEqual(len(GB._alt_filter(self.TYP, "今週末のおすすめは?", {"route": "plan"}, [], [], GB.cfg())), 2)


class SpeciesRoute(unittest.TestCase):
    """第2部 2: 種の「地域と時期」「見たい」も、名所の一覧の経路。"""

    def test_routes(self):
        for q in ("ホタルが見られる地域と時期を教えて", "ホタルの名所を教えて", "ロウバイを見たい", "ホタルはいつどこで見られる?"):
            self.assertEqual(AR.resolve(q, NOW)["route"], "season_place", q)

    def test_dated_or_generic_unchanged(self):
        self.assertEqual(AR.resolve("今週末、カワセミを見たい", NOW)["route"], "species_dated")
        self.assertEqual(AR.resolve("紅葉を見たい", NOW)["route"], "plan")

    def test_species_rows_mark_vague_and_old(self):
        rows = [{"name": "試験川", "prefecture": "東京都", "city": "試験市", "km": None, "km_estimated": False, "kinds": ["ホタル"],
                 "start": None, "end": "07-10", "season": "2014年の記載では、7月上旬まで", "url": None, "official": True},
                {"name": "試験の里", "prefecture": "東京都", "city": "試験市", "km": 30, "km_estimated": False, "kinds": ["ホタル"],
                 "start": None, "end": None, "season": "初夏", "url": None, "official": True}]
        from ikimonobiyori import season_place as SP
        with mock.patch.object(SP, "gather", return_value=rows), mock.patch.object(SP, "select", side_effect=lambda r, *a, **k: (r, 0)):
            got = GM.species_rows("ホタルの名所を教えて", {"route": "season_place", "origin": "横浜"})
        notes = {r["name"]: r["note"] for r in got}
        self.assertEqual(notes["試験川"], GB.cfg()["species_rows"]["old_note"])
        self.assertEqual(notes["試験の里"], GB.cfg()["species_rows"]["vague_note"])


if __name__ == "__main__":
    unittest.main()
