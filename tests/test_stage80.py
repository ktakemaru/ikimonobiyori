"""段階80: 段階79 の提案の直し(A 知らない地名 / B 発行元の確かめ / C 出発地の距離 / D 承認待ちの範囲 / E テーマの語・重複・場所の書き方 /
F カードの題名の変更・取り下げ・「行く前に」だけの記録・上限の文)。合成データ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_materials as GM
from ikimonobiyori import knowledge as K
from ikimonobiyori import observations as O
from ikimonobiyori import place_guard as PG
from ikimonobiyori import research as RS

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 11, 9, 0, tzinfo=JST)


class UnknownTown(unittest.TestCase):
    """A(提案4): 場所の辞書にない市町村の名前(「南伊豆」)を、別の場所の候補に置き換えない。"""

    def test_town_not_in_dictionary_is_unknown(self):
        with mock.patch.object(RS, "question_places", return_value=["試験伊豆"]), \
                mock.patch.object(PG, "is_known", return_value=False):
            self.assertEqual(PG.unknown_places("試験伊豆で見られる花"), ["試験伊豆"])

    def test_town_resolved_by_town_dictionary_is_known(self):
        from ikimonobiyori import season_place as SP
        with mock.patch.object(RS, "question_places", return_value=["試験津"]), \
                mock.patch.object(PG, "is_known", return_value=False), mock.patch.object(SP, "resolve_town", return_value="試験津町"):
            self.assertEqual(PG.unknown_towns("試験津で見られる花"), [])
        with mock.patch.object(RS, "question_places", return_value=["南試験"]), \
                mock.patch.object(PG, "is_known", return_value=False), mock.patch.object(SP, "resolve_town", return_value="試験市"):
            self.assertEqual(PG.unknown_towns("南試験で見られる花"), ["南試験"])     # 「伊豆市」の部分の一致では解決しない

    def test_known_questions_stay(self):
        for q in ("今週末の紅葉の情報は?", "野鳥のおすすめを教えて", "梅と桜の見分け方を教えて", "白鳥を見たい"):
            self.assertEqual(PG.unknown_places(q), [], q)

    def test_no_alternative_places_for_unknown_place(self):
        typ = [{"name": "試験の遠い公園", "theme": "花", "kinds": []}]
        self.assertEqual(GB._alt_filter(typ, "試験伊豆で見られる花", {"route": "unknown_place"}, [], [], GB.cfg()), [])

    def test_only_plain_general_cards(self):
        c = GB.cfg()
        self.assertTrue(GB._plain_general_card({"place": "桜一般", "where": "桜一般"}, c))
        self.assertFalse(GB._plain_general_card({"place": "冬桜", "where": "桜山公園・群馬県藤岡市"}, c))      # ほかの場所の話
        self.assertFalse(GB._plain_general_card({"place": "試験町建具会館の花畑", "where": "試験町建具会館の花畑"}, c))

    def test_missing_line(self):
        with mock.patch.object(PG, "unknown_places", return_value=["試験伊豆"]), mock.patch.object(PG, "candidates", return_value=[]):
            out = GB._missing("試験伊豆で見られる花", {"route": "unknown_place"}, [], [], [], None)
        self.assertTrue(any("場所の辞書にない地名「試験伊豆」" in x for x in out), out)

    def test_research_ignores_lines_without_source(self):
        facts = [{"content": "確認できている公式ページの範囲では、試験伊豆の花の情報はまだ見つかっていません。", "url": None}]
        with mock.patch.object(RS, "question_places", return_value=["試験伊豆"]), mock.patch.object(PG, "candidates", return_value=[]):
            t = RS.needs("試験伊豆で見られる花", {}, [], [], [], facts)
        self.assertEqual([x["where"] for x in t], ["試験伊豆"])


class DeclaredPublisher(unittest.TestCase):
    """B(提案9): --publisher の名前は、ページの運営者の欄(フッター・著作権表示・運営者情報)で探す。"""

    PAGE = ("<html><head><meta name='author' content='試験ナビ株式会社'></head><body><p>試験県の紅葉の名所 例年11月</p>"
            "<footer><p>運営: 試験ナビ株式会社</p><small>Copyright 試験ナビ</small></footer></body></html>")

    def test_operator_text(self):
        op = RS.operator_text(self.PAGE)
        self.assertIn("試験ナビ株式会社", op)
        self.assertNotIn("試験県の紅葉", op)

    def test_name_only_in_body_is_not_enough(self):
        t = RS.html_text(self.PAGE)
        op = RS.operator_text(self.PAGE, t)
        self.assertFalse(RS._verified(t, "試験県", op))
        self.assertTrue(RS._verified(t, "試験ナビ株式会社", op))

    def test_copyright_line_and_class(self):
        h = "<div class='site-footer'><div>(C) 試験温泉観光協会<div>x</div></div></div><p>本文 試験県</p>"
        self.assertIn("試験温泉観光協会", RS.operator_text(h))
        self.assertIn("試験町観光協会", RS.operator_text(None, "本文\n© 2026 試験町観光協会\n"))

    def test_fetch_rejects_body_only_name(self):
        def get(url):
            if url.endswith("/robots.txt"):
                return 404, b"", {}
            return 200, self.PAGE.encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"}
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            r = RS.fetch("https://navi.example.jp/a", "b-80b", now=NOW, http_get=get, publisher="試験県", env=env, sleep=lambda s: None)
            self.assertFalse(r["ok"])
            self.assertIn("運営者の欄", r["reason"])
            r2 = RS.fetch("https://navi.example.jp/a", "b-80b", now=NOW, http_get=get, publisher="試験県", env=env)    # 控えでも同じ
            self.assertFalse(r2["ok"])


class OriginDistance(unittest.TestCase):
    """C(提案8): 例年の目安の候補の距離は、出発地の距離がないとき出発地から出し直す(東京の距離をそのまま使わない)。"""

    def test_recomputed_for_other_origin(self):
        from ikimonobiyori import guide
        e = {"name": "試験の濠", "scope": "place", "theme": "野鳥", "prefecture": "東京都", "municipality": "千代田区",
             "season": {"window": {"start": "10-01", "end": "03-31"}, "text": "秋〜冬"},
             "range": {"status": "in_range", "km": 0, "from": "東京", "by_origin": {"東京": {"km": 2}, "横浜": {"km": 27}}},
             "sources": [{"url": "https://www.env.go.jp/x", "class": "A", "publisher": "環境省"}], "kinds": []}
        c = GB.cfg()
        theme = (c["typical_themes"].get("birds") or ["野鳥"])[0]
        e["theme"] = theme
        cond = {"subjects": ["birds"], "periods": [["2026-11-14"]], "origin": "大宮"}
        with mock.patch.object(guide, "build", return_value=([e], None)), mock.patch.object(guide, "approved", return_value=True), \
                mock.patch.object(GM, "straight_range", return_value=({"origin": "大宮", "km": 27, "status": "in_range"}, "city", None)) as sr:
            rows = GB.typical_candidates(cond, NOW, "wide", set(), c, set())
        sr.assert_called()
        self.assertEqual([r["km"] for r in rows if r["name"] == "試験の濠"], [27])
        with mock.patch.object(guide, "build", return_value=([e], None)), mock.patch.object(guide, "approved", return_value=True), \
                mock.patch.object(GM, "straight_range") as sr2:
            rows = GB.typical_candidates(dict(cond, origin="横浜"), NOW, "wide", set(), c, set())
        sr2.assert_not_called()                                                   # 出発地の距離がある
        self.assertEqual([r["km"] for r in rows if r["name"] == "試験の濠"], [27])


class LedgerRange(unittest.TestCase):
    """D(提案2): 承認待ちの判定は、情報源の URL の範囲で(ホスト単位にしない)。"""

    def test_same_host_other_page_is_not_gated(self):
        rows = [("city.example.lg.jp", "/nishi/spot/hana.html", "pending", "flowers", "t-n")]
        P = O.load_policy()
        with mock.patch.object(O, "_ledger_urls", return_value=rows):
            self.assertEqual(O.ledger_status_in_range("https://www.city.example.lg.jp/nishi/spot/hana.html"), "pending")
            self.assertIsNone(O.ledger_status_in_range("https://www.city.example.lg.jp/city-info/koho/rose.html"))
            self.assertTrue(O._ledger_gated({"url": "https://www.city.example.lg.jp/nishi/spot/hana.html", "source_class": "official"}, "flowers", P))
            self.assertFalse(O._ledger_gated({"url": "https://www.city.example.lg.jp/city-info/koho/rose.html", "source_class": "official"}, "flowers", P))
            self.assertFalse(GB._ledger_pending("https://www.city.example.lg.jp/city-info/koho/rose.html"))


class ThemeAndPlaces(unittest.TestCase):
    """E(提案1・6・11)。"""

    def test_theme_words_skip_excluded_terms(self):
        c = GB.cfg()
        self.assertNotIn("冬桜", GB._theme_words("芝桜の名所を教えて", [], c))
        self.assertIn("冬桜", GB._theme_words("桜の名所を教えて", [], c))

    def test_excluded_topic(self):
        c = GB.cfg()
        card = {"title": "芝桜は北アメリカ原産", "subject": "芝桜", "place": "芝桜一般"}
        self.assertTrue(GB._excluded_topic(card, "桜の見られる時期", c))
        self.assertFalse(GB._excluded_topic(card, "芝桜の名所", c))
        self.assertFalse(GB._excluded_topic({"title": "冬桜とは", "place": "冬桜"}, "桜の見られる時期", c))

    def test_merge_same_places(self):
        rows = [{"species": "スイセン", "name": "試験崎", "city": "試験市"}, {"species": "スイセン", "name": "試験崎の水仙", "city": "試験市"},
                {"species": "スイセン", "name": "試験崎の水仙", "city": "別の市"}]
        GM.merge_same_places(rows)
        self.assertEqual([r["name"] for r in rows], ["試験崎", "試験崎", "試験崎の水仙"])
        self.assertEqual(rows[1]["merged_from"], "試験崎の水仙")

    def test_location_not_doubled(self):
        self.assertEqual(GB._loc({"name": "試験県立自然の博物館", "prefecture": "試験県", "city": "長生町"}), "長生町")
        self.assertEqual(GB._loc({"name": "長生(月の石公園)", "prefecture": "試験県", "city": "長生町"}), "試験県")
        self.assertEqual(GB._loc({"name": "金石橋", "prefecture": "試験県", "city": "試験町"}), "試験県試験町")


class KnowledgeCommands(unittest.TestCase):
    """F(提案5): カードの題名の変更・取り下げ(控えを残す)。"""

    CARD = {"title": "試験の鳥(オオバンとバン)", "category": "種の解説", "place": "冬鳥一般", "subject": "オオバン",
            "facts": ["オオバンは全体が黒く、額が白い"], "condition": {"months": [12]},
            "source": {"name": "試験県", "url": "https://www.pref.example.lg.jp/x", "checked_on": "2026-11-11"},
            "confidence": "公的資料", "rights": "確認済み(試験)。事実のみ", "usage": "そのまま"}

    def test_rename_and_retire(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            K.add(dict(self.CARD), env=env)
            K.rename("試験の鳥(オオバンとバン)", "オオバンの見分け方", at=NOW.isoformat(), env=env)
            self.assertEqual([r["title"] for r in K.load(env)], ["オオバンの見分け方"])
            with self.assertRaises(ValueError):
                K.rename("ないカード", "x", at=NOW.isoformat(), env=env)
            with self.assertRaises(ValueError):
                K.retire("オオバンの見分け方", "", at=NOW.isoformat(), env=env)          # 理由が要る
            K.retire("オオバンの見分け方", "同じ出典の重複", at=NOW.isoformat(), env=env)
            rows = K.load(env)
            self.assertEqual(len(rows), 1)                                              # 消さない
            self.assertTrue(rows[0]["retired"])
            self.assertEqual(K.load_shown(env, centers=[]), [])                         # 答えには出ない
            log = [json.loads(x) for x in (K.path(env).parent / "card_changes.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([x["action"] for x in log], ["rename", "retire"])
            self.assertEqual(log[0]["before"]["title"], "試験の鳥(オオバンとバン)")

    def test_rename_collision(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            K.add(dict(self.CARD), env=env)
            K.add(dict(self.CARD, title="オオバンの見分け方"), env=env)
            with self.assertRaises(ValueError):
                K.rename("試験の鳥(オオバンとバン)", "オオバンの見分け方", at=NOW.isoformat(), env=env)


class NoticeOnly(unittest.TestCase):
    """F(提案7): 公式ページで読んだ「行く前に」だけの記録。"""

    def test_observation_record(self):
        P = O.load_policy()
        rec = {"subject": "flowers", "name": "試験の花の国", "url": "https://www.example.lg.jp/a", "source_class": "official",
               "notice": "台風の被害で一部開園", "basis": "page"}
        self.assertEqual(O.validate(rec, P), [])
        self.assertIn("state がない", O.validate(dict(rec, source_class="secondary"), P))
        self.assertIn("state がない", O.validate({k: v for k, v in rec.items() if k != "notice"}, P))

    def test_ask_record_writes_notice_only(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            res = O.record([{"subject": "flowers", "name": "試験の花の国", "city": "横須賀市", "prefecture": "神奈川県",
                             "url": "https://www.kanagawaparks.com/kurihama/", "source_class": "official", "notice": "台風の被害で一部開園",
                             "basis": "page"}], env=env, now=NOW)
            self.assertEqual(res["written"], 1, res)
            rows = [r for r in O.read_records("flowers", env) if r.get("name") == "試験の花の国"]
            self.assertEqual(rows[0]["notice"], "台風の被害で一部開園")
            F = GB._Facts(GB.cfg(), set())
            with mock.patch.object(RS, "question_places", return_value=["横須賀"]):
                cands = []
                GB._place_records(F, "横須賀で見られる花", cands, {"origin": "横浜"}, GB.cfg(), env)
            self.assertEqual(cands, [])                                                    # 候補にはしない(事実だけ)
            self.assertTrue(any("行く前に: 台風の被害で一部開園" in f["content"] for f in F.rows), F.rows)

    def test_limit_message_has_first_time(self):
        def get(url):
            if url.endswith("/robots.txt"):
                return 404, b"", {}
            return 200, "<p>x</p>".encode("utf-8"), {"Content-Type": "text/html; charset=utf-8"}
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            RS.fetch("https://www.town.minamiizu.shizuoka.jp/t1", "b-80t", now=NOW, http_get=get, env=env, sleep=lambda s: None)
            late = RS.fetch("https://www.town.minamiizu.shizuoka.jp/t2", "b-80t", now=NOW + timedelta(seconds=500), http_get=get, env=env,
                            sleep=lambda s: None)
        self.assertFalse(late["ok"])
        self.assertIn(NOW.isoformat(), late["reason"])


class AfterReview80(unittest.TestCase):
    """段階80 の報告書への本人の判断(2026-11-11)のあと。"""

    def test_no_operator_section_is_not_read(self):                       # 判断 3: B の例外をなくす
        h = "<p>試験町観光協会 例年2月に菜の花</p>"
        t = RS.html_text(h)
        self.assertEqual(RS.operator_text(h, t), "")
        self.assertFalse(RS._verified(t, "試験町観光協会", RS.operator_text(h, t)))

    def test_card_changes_are_backed_up(self):                             # 判断 2
        from ikimonobiyori import knowledge_backup as KB
        self.assertIn("card_changes.jsonl", KB.cfg()["allowed_files"])

    def test_town_of(self):                                                # 判断 4: 市町村の名前で名所を引く
        names = {"南伊豆町", "伊豆市", "松田町", "中区"}
        self.assertEqual(GM.town_of("南伊豆", names), "南伊豆町")
        self.assertEqual(GM.town_of("松田町", names), "松田町")
        self.assertIsNone(GM.town_of("南試験", names))
        self.assertIsNone(GM.town_of("中", names))                          # 1 字は引かない
        self.assertEqual(GM._city_parts("横浜市中区・伊豆市"), ["横浜市中区", "中区", "伊豆市"])

    def test_town_is_not_unknown(self):
        with mock.patch.object(RS, "question_places", return_value=["試験伊豆"]),                 mock.patch.object(PG, "is_known", return_value=False), mock.patch.object(GM, "town_of", return_value="試験伊豆町"):
            self.assertEqual(PG.unknown_towns("試験伊豆で見られる花"), [])

    def test_town_candidates_replace_other_places(self):
        c = GB.cfg()
        F = GB._Facts(c, set())
        F.add("typical", "横浜の試験庭園: 例年 11月", place="横浜の試験庭園", url="https://www.city.example.lg.jp/a", source_class="official")
        F.add("other", "日付の指定がなかったので、11/14・11/15で探しました。")
        F.add("typical", "試験の畑(試験県試験伊豆町): 菜の花 2月", place="試験の畑", url="https://www.town.example.lg.jp/b", source_class="official")
        cands = [{"name": "横浜の試験庭園", "city": "横浜市中区", "chosen": True}, {"name": "試験の畑", "city": "試験伊豆町", "basis": "species"}]
        spot = {"name": "試験の桜並木", "prefecture": "試験県", "city": "試験伊豆町", "seasons": [("例年2月上旬〜3月上旬", "河津桜")], "kinds": ["河津桜"],
                "url": "https://kanko.example.jp/c", "publisher": "試験紹介", "source_class": "secondary", "tentative": True}
        with mock.patch.object(GM, "town_spots", return_value=[spot]):
            keep, dropped = GB._town_candidates(F, cands, ["試験伊豆町"], {"origin": "横浜"}, c)
        self.assertEqual([r["name"] for r in keep], ["試験の畑", "試験の桜並木"])
        self.assertEqual(dropped, {"横浜の試験庭園"})
        self.assertEqual([f["id"] for f in F.rows], ["F001", "F002"])           # 番号は振り直す
        self.assertTrue(all("横浜" not in f["content"] and "日付の指定" not in f["content"] for f in F.rows))
        self.assertIn("試験の桜並木(試験県試験伊豆町): 例年2月上旬〜3月上旬(河津桜)(検索で集めた名所。仮)", [f["content"] for f in F.rows])
        self.assertIn(c["town_candidates"]["tentative_label"], keep[1]["reasons"])



class AfterReview80b(unittest.TestCase):
    """段階80 の追記への本人の判断(2026-11-11)のあと: 仮の名所の確かめ・広い地域の名前・カードに事実を足す。"""

    def _names(self):
        return mock.patch.object(GM, "_town_names", return_value={"南伊豆町", "伊豆市", "伊豆の国市", "日光市"}),             mock.patch.object(RS, "_municipalities", return_value={"南伊豆町", "伊豆市"})

    def test_confirm_tentative_with_official_record(self):              # 判断 1
        key = lambda n: n.replace("・", "")
        rows = [{"name": "試験の菜の花畑", "city": "試験伊豆町", "seasons": [("例年1月〜2月", "菜の花")], "kinds": ["菜の花"],
                 "url": "https://kanko.example.jp/a", "publisher": "試験紹介", "source_class": "secondary", "tentative": True},
                {"name": "試験の桜並木", "city": "試験伊豆町", "seasons": [], "kinds": ["河津桜"], "url": "https://kanko.example.jp/b",
                 "publisher": "試験紹介", "source_class": "secondary", "tentative": True}]
        recs = [{"name": "試験の菜の花畑(日野)", "city": "試験伊豆町", "kind": "菜の花", "typical": "例年1月中旬〜2月下旬",
                 "url": "https://www.town.example.lg.jp/n", "publisher": "試験伊豆町", "source_class": "official"},
                {"name": "試験の桜並木", "city": "試験伊豆町", "kind": "河津桜", "typical": "例年2月", "url": "https://blog.example.jp/x",
                 "source_class": "secondary"},                                 # 公式でない記録では外さない
                {"name": "試験の梅林", "city": "試験伊豆町", "kind": "梅", "typical": "例年2月", "url": "https://www.town.example.lg.jp/u",
                 "publisher": "試験伊豆町", "source_class": "official"}]
        with mock.patch.object(O, "read_records", side_effect=lambda sj, *a, **k: recs if sj == "flowers" else []):
            GM._confirm_with_records(rows, "試験伊豆町", key)
        self.assertFalse(rows[0]["tentative"])
        self.assertEqual((rows[0]["url"], rows[0]["source_class"], rows[0]["confirmed_by"]),
                         ("https://www.town.example.lg.jp/n", "official", "https://www.town.example.lg.jp/n"))
        self.assertEqual(rows[0]["seasons"], [("例年1月中旬〜2月下旬", "菜の花")])
        self.assertTrue(rows[1]["tentative"])                                   # 確かめられなければ仮のまま
        self.assertEqual([r["name"] for r in rows[2:]], ["試験の梅林"])
        self.assertFalse(rows[2]["tentative"])

    def test_tentative_only_town_is_research_target(self):              # 判断 1
        c = GB.cfg()
        T = c["town_candidates"]
        cands = [{"name": "試験の菜の花畑", "reasons": [T["label"].format(town="試験伊豆町"), T["tentative_label"]]}]
        t = GB._tentative_targets("試験伊豆で見られる花", ["試験伊豆町"], None, cands, [], c)
        self.assertEqual([x["where"] for x in t], ["試験伊豆町"])
        self.assertIn("仮", t[0]["why"])
        cands.append({"name": "試験の梅林", "reasons": [T["label"].format(town="試験伊豆町")]})
        self.assertEqual(GB._tentative_targets("試験伊豆で見られる花", ["試験伊豆町"], None, cands, [], c), [])

    def test_izu_is_peninsula(self):                                     # 判断 2
        from ikimonobiyori import areas as AR
        a = AR.resolve("伊豆")
        self.assertIsNotNone(a)
        self.assertGreater(len(a["cities"]), 1)
        self.assertIn("南伊豆町", a["cities"])
        self.assertIs(AR.resolve("伊豆半島"), a)
        n1, n2 = self._names()
        with n1, n2:
            self.assertTrue(AR.mentioned("伊豆", "伊豆で見られる花"))
            self.assertFalse(AR.mentioned("伊豆", "南伊豆で見られる花"))
            self.assertFalse(AR.mentioned("伊豆", "伊豆市で見られる花"))
            self.assertFalse(AR.mentioned("伊豆", "伊豆の国市の花"))
            self.assertFalse(AR.mentioned("那須", "那須塩原の紅葉"))          # 記録にない長い地名は not_within
            self.assertEqual(AR.find_in("伊豆で見られる花")[0]["name"], "伊豆")
            self.assertEqual(AR.find_in("日光の紅葉")[0]["name"], "日光")
            self.assertIsNone(AR.find_in("伊豆市で見られる花")[0])
            from ikimonobiyori import season_place as SP
            self.assertEqual(SP.place_filter("伊豆で見られる花")["cities"], a["cities"])
            self.assertEqual(SP.place_filter("伊豆市で見られる花")["cities"], ["伊豆市"])

    def test_question_areas(self):                                       # 追記3 の判断 1 で置き換えた(エリアの質問は、いつもエリアの名所だけ)
        from ikimonobiyori import areas as AR
        n1, n2 = self._names()
        with n1, n2:
            self.assertEqual([a["name"] for a in GB._question_areas("伊豆で見られる花", {})], ["伊豆"])
            self.assertEqual([a["name"] for a in GB._question_areas("秩父で見られる花は?", {"region": "秩父"})], ["秩父"])
            self.assertEqual(GB._question_areas("秩父から近い花の名所は?", {}), [])          # 出発地は今までどおり
            self.assertEqual(GB._question_areas("伊豆市で見られる花", {}), [])
            self.assertEqual([a["name"] for a in GB._question_areas("x", {"area_names": ["秩父", "長瀞"]})], ["秩父", "長瀞"])
        nikko = AR.resolve("日光")
        with mock.patch.object(GM, "place_info", return_value={"point": {"lat": 36.75, "lon": 139.6}}):
            self.assertTrue(GB._in_areas({"name": "試験の滝"}, [nikko]))                    # 市区町村の欄がなくても座標で
        with mock.patch.object(GM, "place_info", return_value={}):
            self.assertFalse(GB._in_areas({"name": "試験公園", "city": "藤岡市"}, [nikko]))

    def test_area_drops_other_places(self):                              # 追記3 の判断 1
        from ikimonobiyori import areas as AR
        c = GB.cfg()
        F = GB._Facts(c, set())
        cands = [{"name": "横浜の試験庭園", "city": "横浜市中区"}, {"name": "試験の梅林", "city": "秩父市"}]
        with mock.patch.object(GM, "town_spots", return_value=[]), mock.patch.object(GM, "place_info", return_value={}):
            keep, dropped = GB._town_candidates(F, cands, ["秩父市"], {}, c, label="秩父", areas=[AR.resolve("秩父")])
        self.assertEqual([r["name"] for r in keep], ["試験の梅林"])
        t = GB._tentative_targets("那須で見られる紅葉", ["那須町"], "那須", [], [], c)       # 0 件は調べる対象
        self.assertEqual(t[0]["why"], c["town_candidates"]["none_why"].format(where="那須"))

    def test_izu_and_fuji_dictionary(self):                               # 追記3 の判断 2・3
        from ikimonobiyori import areas as AR
        izu = AR.resolve("伊豆")
        self.assertIn("沼津市", izu["cities"])
        self.assertTrue({"三島市", "清水町", "長泉町"} <= set(izu["cities"]))    # 追記4 の判断 3: 全体構想の 15 市町にそろえた
        self.assertEqual(len(izu["cities"]), 15)
        self.assertTrue(izu["sources"])
        fuji = AR.resolve("富士")
        self.assertTrue({"富士河口湖町", "富士宮市", "御殿場市"} <= set(fuji["cities"]))
        n1, n2 = self._names()
        with n1, n2:
            self.assertEqual(AR.find_in("富士で見られる花")[0]["name"], "富士")
            self.assertEqual(AR.find_in("富士山周辺で見られる花")[0]["name"], "富士五湖")
            self.assertFalse(AR.mentioned("富士", "富士市で見られる花"))
            self.assertFalse(AR.mentioned("富士", "富士宮の花"))
        from ikimonobiyori import season_place as SP
        self.assertEqual(SP.place_filter("富士市で見られる花は?")["cities"], ["富士市"])

    def test_subject_spots(self):
        from ikimonobiyori import ask
        c = GB.cfg()
        spots = [{"name": "試験の梅林", "subject": "花", "kinds": ["梅"]}, {"name": "試験の渓谷", "subject": "autumn_leaves", "kinds": ["紅葉"]},
                 {"name": "試験の沢", "subject": "ホタル", "kinds": ["ホタル"]}]
        self.assertEqual([s["name"] for s in GB._subject_spots(spots, {"subjects": ["autumn_leaves"], "question": "試験の紅葉"}, c)], ["試験の渓谷"])
        dflt = list(ask.load_policy()["default_subjects"])
        self.assertEqual(len(GB._subject_spots(spots, {"subjects": dflt, "question": "試験で見られるもの"}, c)), 3)

    def test_needs_counts_area_cities(self):
        from ikimonobiyori import season_place as SP
        pf = {"label": "試験半島", "cities": ["試験伊豆町"]}
        with mock.patch.object(SP, "place_filter", return_value=pf), mock.patch.object(PG, "candidates", return_value=[]),                 mock.patch.object(RS, "question_places", return_value=[]), mock.patch.object(GM, "species_names", return_value=[]):
            self.assertEqual(RS.needs("試験半島の花", {}, [], [{"name": "試験の梅林", "city": "試験伊豆町"}], [], [], GB.cfg()), [])
            self.assertEqual(len(RS.needs("試験半島の花", {}, [], [], [], [], GB.cfg())), 1)

    def test_add_fact(self):                                             # 判断 3
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            K.add(dict(KnowledgeCommands.CARD), env=env)
            K.add_fact("試験の鳥(オオバンとバン)", "オオバンは冬に池で見られる", "次の季節", at=NOW.isoformat(), env=env)
            self.assertEqual(K.load(env)[0]["facts"][-1], "オオバンは冬に池で見られる")
            with self.assertRaises(ValueError):
                K.add_fact("試験の鳥(オオバンとバン)", "オオバンは冬に池で見られる", "次の季節", at=NOW.isoformat(), env=env)   # 同じ文
            with self.assertRaises(ValueError):
                K.add_fact("試験の鳥(オオバンとバン)", "x", "", at=NOW.isoformat(), env=env)
            log = [json.loads(x) for x in (K.path(env).parent / "card_changes.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([x["action"] for x in log], ["add_fact"])


class AfterReview80d(unittest.TestCase):
    """段階80 の追記4: エリアを市町で決める(秩父・那須・伊豆・富士)・記録だけにある市区町村(那須塩原市)。"""

    def test_chichibu_by_cities(self):                                     # 判断 2
        from ikimonobiyori import areas as AR
        ch = AR.resolve("秩父")
        self.assertEqual(ch["cities"], ["秩父市", "横瀬町", "皆野町", "長瀞町", "小鹿野町"])
        self.assertEqual(len(AR.members(ch, [{"name": "宝登山", "city": "長瀞町"}])), 1)
        near = {"name": "隣町の公園", "city": "神川町", "point": dict(ch["center"])}
        self.assertEqual(AR.members(ch, [near]), [])                       # 市町の欄があれば半径では入れない
        nag = AR.resolve("長瀞")
        self.assertEqual(len(AR.members(ch, [{"name": "欄なし", "point": dict(nag["center"])}])), 1)   # 欄なしは中の長瀞の半径で
        self.assertEqual(nag["cities"], ["長瀞町"])                       # 長瀞は今までどおり

    def test_nasu_region(self):                                            # 判断 4
        from ikimonobiyori import areas as AR
        self.assertEqual(AR.resolve("那須")["cities"], ["那須町", "那須塩原市"])
        self.assertFalse(AR.mentioned("那須", "那須塩原で見られる紅葉"))
        recs = [{"name": "試験の吊橋", "city": "那須塩原市", "kind": "紅葉", "typical": "見ごろは11月上旬から11月中旬まで",
                 "url": "https://www.city.example.lg.jp/k", "source_class": "official"},
                {"name": "試験の茶屋", "city": "那須塩原市", "kind": "紅葉", "url": "https://www.city.example.lg.jp/k", "source_class": "official"}]
        with mock.patch.object(O, "read_records", side_effect=lambda sj, *a, **k: recs if sj == "autumn_leaves" else []):
            got = GM._official_records()
            self.assertEqual([(r["name"], r["_subject"]) for r in got], [("試験の吊橋", "autumn_leaves")])   # 例年の時期のないものは使わない
            with mock.patch.object(GM, "_index", return_value={}):
                self.assertIn("那須塩原市", GM._town_names())
            rows = []
            GM._confirm_with_records(rows, "那須塩原市", lambda n: n)
            self.assertEqual([(r["name"], r["subject"], r["tentative"]) for r in rows], [("試験の吊橋", "autumn_leaves", False)])

    def test_fuji_source(self):                                            # 判断 1
        from ikimonobiyori import areas as AR
        f = AR.resolve("富士")
        self.assertEqual(f.get("membership"), "cities")
        self.assertIn("裾野市", f["sources"][0]["lists"])
        self.assertEqual({a["name"] for a in AR.load()["areas"] if a.get("membership") == "cities"}, {"秩父", "那須", "伊豆", "富士"})


class AfterReview80e(unittest.TestCase):
    """段階80 の追記5(本人の判断 2026-11-12): 名前の形が違う同じ場所を、資料の候補で 1 つにまとめる。"""

    def setUp(self):
        self.c = GB.cfg()
        self.noinfo = mock.patch.object(GM, "place_info", return_value={})

    def test_same_place_by_name(self):
        with self.noinfo:
            a = {"name": "宝登山ロウバイ園", "city": "長瀞町"}
            self.assertTrue(GB.same_place(a, {"name": "長瀞宝登山臘梅園", "city": "長瀞町"}, self.c))       # 町の名前・種の別名を除いて同じ
            self.assertFalse(GB.same_place(a, {"name": "宝登山梅百花園", "city": "長瀞町"}, self.c))       # 種が違う
            self.assertFalse(GB.same_place(a, {"name": "宝登山ロウバイ園", "city": "秩父市"}, self.c))     # 市区町村が違う
            self.assertFalse(GB.same_place(a, {"name": "宝登山山頂ロウバイ園", "city": "長瀞町"}, self.c))  # 迷うものはまとめない
            self.assertFalse(GB.same_place({"name": "試験公園", "city": "長瀞町"}, {"name": "長瀞試験公園", "city": "長瀞町"}, self.c))   # 種が分からない
        self.assertEqual(self.c["merge_same"]["max_m"], 200)

    def test_same_place_by_point(self):
        a = {"name": "試験の梅林", "city": "試験市", "point": {"lat": 35.0, "lon": 139.0}}
        near = {"name": "試験梅園", "city": "試験市", "point": {"lat": 35.0015, "lon": 139.0}}      # 約 167m
        far = {"name": "試験の梅林", "city": "試験市", "point": {"lat": 35.003, "lon": 139.0}}      # 約 333m
        with self.noinfo:
            self.assertTrue(GB.same_place(a, near, self.c))
            self.assertFalse(GB.same_place(a, far, self.c))                  # 座標があれば名前が同じでも距離で

    def test_months(self):
        self.assertEqual(GB._months("例年 12/21〜2/28"), {12, 1, 2})
        self.assertEqual(GB._months("1月中旬〜2月下旬ごろ"), {1, 2})
        self.assertEqual(GB._months("例年の時期は未確認"), set())

    def test_merge_candidates(self):
        F = GB._Facts(self.c, set())
        F.add("typical", "長瀞宝登山臘梅園(埼玉県長瀞町): 例年 1月中旬〜2月下旬ごろ(ロウバイ)", place="長瀞宝登山臘梅園", url="https://news.example.jp/a", source_class="secondary")
        F.add("typical", "宝登山ロウバイ園: 例年 12/21〜2/28", place="宝登山ロウバイ園", url="https://www.town.example.lg.jp/b", source_class="official")
        cands = [{"name": "長瀞宝登山臘梅園", "city": "長瀞町", "theme": "ロウバイ", "reasons": ["町の名所"]},
                 {"name": "宝登山梅百花園", "city": "長瀞町", "theme": "梅"},
                 {"name": "宝登山ロウバイ園", "city": "長瀞町", "reasons": ["例年の目安"], "distance_text": "約80km"}]
        with self.noinfo:
            out, merges, conflicts = GB.merge_same_candidates(cands, F, self.c)
        self.assertEqual([r["name"] for r in out], ["宝登山ロウバイ園", "宝登山梅百花園"])     # 公式の出典の名前
        self.assertEqual(out[0]["merged_from"], ["長瀞宝登山臘梅園"])
        self.assertEqual(out[0]["reasons"], ["例年の目安", "町の名所"])
        self.assertEqual(out[0]["theme"], "ロウバイ")
        self.assertEqual({f["place"] for f in F.rows}, {"宝登山ロウバイ園"})          # 事実は両方を残す
        self.assertEqual(len(F.rows), 2)
        self.assertEqual((merges, conflicts), ([{"name": "宝登山ロウバイ園", "merged_from": ["長瀞宝登山臘梅園"]}], []))

    def test_conflicting_facts_are_not_merged(self):
        F = GB._Facts(self.c, set())
        F.add("typical", "長瀞宝登山臘梅園: 例年 6月", place="長瀞宝登山臘梅園", url="https://news.example.jp/a", source_class="secondary")
        F.add("typical", "宝登山ロウバイ園: 例年 12/21〜2/28", place="宝登山ロウバイ園", url="https://www.town.example.lg.jp/b", source_class="official")
        cands = [{"name": "長瀞宝登山臘梅園", "city": "長瀞町"}, {"name": "宝登山ロウバイ園", "city": "長瀞町"}]
        with self.noinfo:
            out, merges, conflicts = GB.merge_same_candidates(cands, F, self.c)
        self.assertEqual(len(out), 2)
        self.assertEqual(merges, [])
        self.assertEqual(conflicts[0]["names"], ["長瀞宝登山臘梅園", "宝登山ロウバイ園"])

if __name__ == "__main__":
    unittest.main()
