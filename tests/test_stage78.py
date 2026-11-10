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


# ---- 第3部・第4部・第5部 ----

from ikimonobiyori import gaps as GP           # noqa: E402
from ikimonobiyori import guide_narrative as GN   # noqa: E402
from ikimonobiyori import research as RS       # noqa: E402


class Narrative(unittest.TestCase):
    """第3部 1・3: 語りの材料と、使っていない答えを止める照合。"""

    def test_classify(self):
        self.assertEqual(GN.classify_fact("冬鳥は秋に北から渡来して越冬する"), "なぜ今")
        self.assertEqual(GN.classify_fact("朝の早い時間に水面を探すと見つけやすい"), "どこをどう見る")
        self.assertEqual(GN.classify_fact("寒桜は冬桜とは別の種"), "見分け方")
        self.assertEqual(GN.classify_fact("花が終わると実をつける"), "次の季節")
        self.assertEqual(GN.classify_fact("ライトアップは2025年は20時まで"), "その他")
        self.assertEqual(GN.classify_fact("駐車場は30台"), "その他")

    def test_card_field_is_used(self):
        card = {"facts": ["文A", "文B"], "narrative": ["見分け方", "その他"]}
        self.assertEqual(GN.kinds_of(card), ["見分け方", "その他"])

    def test_materials_and_missing(self):
        cards = [{"id": "K001", "title": "t", "place": "p", "facts": ["冬鳥は北から渡ってくる", "駐車場は30台"]},
                 {"id": "K002", "title": "u", "place": "q", "facts": ["双眼鏡で水面を探す"]}]
        m = GN.materials(cards)
        self.assertEqual([(x["kind"], x["card"]) for x in m["items"]], [("なぜ今", "K001"), ("どこをどう見る", "K002")])
        self.assertEqual(m["missing"], ["見分け方", "次の季節"])
        self.assertIn("材料なし", "\n".join(GN.render(m)))

    def _b(self, **kw):
        items = [{"kind": "なぜ今", "card": "K001", "text": "a"}, {"kind": "どこをどう見る", "card": "K002", "text": "b"}]
        return brief(narrative={"items": items, "missing": []},
                     cards=[{"id": "K001", "title": "t", "facts": ["a"], "values": GB.values("a")},
                            {"id": "K002", "title": "u", "facts": ["b"], "values": GB.values("b")}], **kw)

    def test_unused_materials_fail(self):
        r = GV.check("試験の渓谷は例年11月中旬〜下旬が見頃です。[F001]" + PL, self._b())
        self.assertIn("no_narrative", [e["code"] for e in r["errors"]])

    def test_used_material_passes(self):
        r = GV.check("試験の渓谷は例年11月中旬〜下旬が見頃です。[F001] 谷の上から色づきます。[K001]" + PL, self._b())
        self.assertNotIn("no_narrative", [e["code"] for e in r["errors"]])

    def test_event_and_name_questions_are_skipped(self):
        for kw in ({"intent": "event"}, {"route": "name"}):
            r = GV.check("試験の渓谷は例年11月中旬〜下旬が見頃です。[F001]" + PL, self._b(**kw))
            self.assertNotIn("no_narrative", [e["code"] for e in r["errors"]], kw)


class Research(unittest.TestCase):
    """第4部: その場で調べる(通信しない。取得は偽の関数)。"""

    def test_only_official_pages(self):
        self.assertIsNone(RS.allowed_page("https://www.town.minamiizu.shizuoka.jp/x"))
        self.assertIsNotNone(RS.allowed_page("https://matcha-jp.com/jp/1"))
        self.assertIsNotNone(RS.allowed_page("https://weathernews.jp/x"))

    def test_robots(self):
        txt = "User-agent: *\nDisallow: /private/\nAllow: /private/open/\n"
        self.assertTrue(RS.robots_allows(txt, "https://a.example/news/1"))
        self.assertFalse(RS.robots_allows(txt, "https://a.example/private/x"))
        self.assertTrue(RS.robots_allows(txt, "https://a.example/private/open/x"))

    def test_html_text(self):
        self.assertEqual(RS.html_text("<html><head><title>x</title></head><body><p>菜の花</p><script>a()</script><p>例年1月</p></body></html>"),
                         "菜の花\n例年1月")

    def test_question_places(self):
        with mock.patch.object(RS, "_municipalities", return_value={"南伊豆町", "河津町", "松田町"}):
            self.assertEqual(RS.question_places("南伊豆や河津は菜の花や桜で有名です"), ["南伊豆", "河津"])
            self.assertEqual(RS.question_places("神奈川県松田町にも菜の花はありますか"), ["松田町"])
            self.assertEqual(RS.question_places("今週末の紅葉の情報は?"), [])

    def test_no_network_under_test(self):
        r = RS.fetch("https://www.town.minamiizu.shizuoka.jp/x", "b-t1", now=NOW)
        self.assertFalse(r["ok"])

    def _get(self, pages):
        def get(url):
            pages.append(url)
            if url.endswith("/robots.txt"):
                return 200, b"User-agent: *\nDisallow: /no/\n", {}
            return 200, "<p>試験の菜の花畑 例年1月中旬〜2月下旬</p>".encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"}
        return get

    def test_declared_publisher_must_be_in_the_text(self):
        def get(url):
            if url.endswith("/robots.txt"):
                return 404, b"", {}
            return 200, "<p>試験町観光協会 例年2月に菜の花</p>".encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"}
        u = "https://kanko.example.jp/a"
        self.assertFalse(RS.fetch(u, "b-d1", now=NOW, http_get=get)["ok"])                      # 名前なし: 公式の一覧にないホストは読まない
        self.assertFalse(RS.fetch(u, "b-d1", now=NOW, http_get=get, publisher="別の町観光協会")["ok"])  # 本文に名前がない
        self.assertTrue(RS.fetch(u, "b-d1", now=NOW, http_get=get, publisher="試験町観光協会")["ok"])
        res = RS.record([{"subject": "flowers", "name": "試験の畑", "kind": "菜の花", "typical": "例年2月", "url": u}], "b-d1", now=NOW)
        self.assertEqual(res["written"], 1, res)

    def test_fetch_limits_and_record(self):
        pages = []
        url = "https://www.town.minamiizu.shizuoka.jp/a"
        r = RS.fetch(url, "b-t2", now=NOW, http_get=self._get(pages), sleep=lambda s: None)
        self.assertTrue(r["ok"], r)
        self.assertIn("例年1月中旬", r["text"])
        self.assertEqual(pages[0], "https://www.town.minamiizu.shizuoka.jp/robots.txt")
        self.assertTrue(RS.fetch(url, "b-t2", now=NOW, http_get=self._get(pages))["from_cache"])
        self.assertFalse(RS.fetch("https://www.town.minamiizu.shizuoka.jp/no/x", "b-t2", now=NOW, http_get=self._get(pages), sleep=lambda s: None)["ok"])
        for i in range(3):
            RS.fetch(f"https://www.town.minamiizu.shizuoka.jp/p{i}", "b-t2", now=NOW, http_get=self._get(pages), sleep=lambda s: None)
        over = RS.fetch("https://www.town.minamiizu.shizuoka.jp/p9", "b-t2", now=NOW, http_get=self._get(pages), sleep=lambda s: None)
        self.assertFalse(over["ok"])
        late = RS.fetch("https://www.town.minamiizu.shizuoka.jp/q", "b-t3", now=NOW, http_get=self._get(pages), sleep=lambda s: None)
        self.assertTrue(late["ok"])
        later = RS.fetch("https://www.town.minamiizu.shizuoka.jp/q2", "b-t3", now=NOW + timedelta(seconds=200), http_get=self._get(pages),
                         sleep=lambda s: None)
        self.assertFalse(later["ok"])
        res = RS.record([{"subject": "flowers", "name": "試験の菜の花畑", "prefecture": "静岡県", "city": "南伊豆町", "kind": "菜の花",
                          "typical": "例年1月中旬〜2月下旬", "url": url, "publisher": "南伊豆町"},
                         {"subject": "flowers", "name": "試験の菜の花畑", "kind": "菜の花", "state": "見頃", "typical": "例年1月", "url": url,
                          "publisher": "南伊豆町"},
                         {"subject": "flowers", "name": "よそ", "kind": "菜の花", "typical": "例年1月", "url": "https://www.town.minamiizu.shizuoka.jp/zz",
                          "publisher": "南伊豆町"}], "b-t2", question="南伊豆で見られる花を教えて", now=NOW)
        self.assertEqual(res["written"], 1, res)
        self.assertEqual(sorted(x["index"] for x in res["rejected"]), [1, 2])
        rows = RS.listing()["records"]
        self.assertTrue(any(r["name"] == "試験の菜の花畑" and r["question"].startswith("南伊豆") for r in rows))


class PlaceRecords(unittest.TestCase):
    """第4部: その場で調べて記録した名所が、作り直した資料(利用者が挙げた場所の質問)に入る。"""

    def test_records_of_the_named_place(self):
        from ikimonobiyori import observations as O
        rec = {"subject": "flowers", "name": "試験の菜の花畑", "prefecture": "静岡県", "city": "南伊豆町", "kind": "菜の花",
               "typical": "例年2月", "url": "https://www.town.minamiizu.shizuoka.jp/a", "publisher": "南伊豆町", "source_class": "official"}
        F, cands = GB._Facts(GB.cfg(), set()), []
        with mock.patch.object(RS, "question_places", return_value=["南伊豆"]), \
                mock.patch.object(O, "read_records", side_effect=lambda sj, env=None: [rec] if sj == "flowers" else []):
            GB._place_records(F, "南伊豆で見られる花を教えて", cands, {"origin": "横浜"}, GB.cfg())
        self.assertEqual([r["name"] for r in cands], ["試験の菜の花畑"])
        self.assertTrue(any("例年2月" in f["content"] for f in F.rows))


class Part7Fixes(unittest.TestCase):
    """第7部の確かめで見つかったもの: 県名つきの町の名前・崩れた断り。"""

    def test_prefecture_prefix_is_removed_from_the_town(self):
        from ikimonobiyori import season_place as SP
        self.assertEqual(SP.place_filter("神奈川県松田町にも菜の花はありますか")["cities"], ["松田町"])

    def test_broken_disclaimer_fails(self):
        self.assertIn("long_disclaimer", codes("紹介サイトによると、とのことで、公式ではありません。試験の渓谷は例年11月中旬〜下旬が見頃です。[F001]"))


class Gaps(unittest.TestCase):
    """第5部: 足りなかったことの記録と、対象×場所ごとの回数。"""

    def test_rows_and_summary(self):
        b = {"id": "b-g", "question": "南伊豆で見られる花を教えて", "subjects": ["flowers"], "areas": [], "region": None,
             "missing": ["今年の現況の記録がある候補がない", "「南伊豆」についての確かめた事実は 2 件"]}
        txt = "南伊豆の今年の状況は確かめられていません。例年は1月です。\n\n出典\n・南伊豆町 https://x\n"
        rows = GP.rows_for(txt, b, NOW)
        self.assertEqual([r["kind"] for r in rows], ["answer", "missing"])
        GP.append(txt, b, NOW)
        GP.append(txt, b, NOW)
        top = GP.summary()[0]
        self.assertEqual(top["count"], 4)
        self.assertIn("|", GP.render(GP.summary()))


if __name__ == "__main__":
    unittest.main()
