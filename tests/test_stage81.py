"""段階81 第1部: 小さな直し(旬を日付にしない / 見られる期間と数が多い時期を分ける / 場所の質問に関係のない一般の話を入れない /
頭の日付がかかる状態の文を崩さない)。合成データ(通信しない)。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import observations as O

POL = O.load_policy()


class ThirdsStayThirds(unittest.TestCase):
    """1: 名所カタログの窓が旬の区切りなら、資料でも旬のまま(「12/21〜2/28」にしない)。"""

    def test_window_on_third_boundaries_is_written_in_thirds(self):
        self.assertEqual(O.window_plain_text({"start": "12-21", "end": "02-28"}), "12月下旬〜2月下旬")
        self.assertEqual(O.window_plain_text({"start": "03-11", "end": "04-10"}), "3月中旬〜4月上旬")

    def test_real_dates_stay_dates(self):
        self.assertEqual(O.window_plain_text({"start": "12-25", "end": "02-28"}), "12/25〜2/28")
        self.assertEqual(O.window_plain_text({"start": "12-21", "end": "02-28", "note": "試験園: 12月21日から2月28日まで"}), "12/21〜2/28")

    def test_catalog_flower_window_text(self):
        e = {"name": "試験ロウバイ園", "flower_windows": [{"kind": "ロウバイ", "start": "12-21", "end": "02-28",
                                                         "source_url": "https://example.org/a", "note": "試験町: 12月下旬から2月下旬まで"}]}
        t = O._typical_from_catalog(e, POL)[0]
        self.assertEqual(t["text_thirds"], "12月下旬〜2月下旬")              # ガイドの資料に出す文
        self.assertEqual(t["text"], "12/21〜2/28")                          # 今までの形の文は変えない(段階35・67 のテスト)


class PeakIsNotTheStart(unittest.TestCase):
    """2: 数が多い時期(ピーク)の文を、見られる期間の始まりにしない。"""

    def test_peak_then_end_only(self):
        t = "毎年冬に渡ってくる。近年は1月下旬〜2月上旬に飛来数がピーク。3月上旬頃まで観察できる"
        self.assertIsNone(O.parse_typical(t, POL))                       # 始まりは分からない(1月下旬からにしない)
        self.assertEqual(O.peak_text(t, POL), "1月下旬〜2月上旬")

    def test_season_and_peak(self):
        t = "11月下旬から3月上旬。飛来数のピークは例年1月中下旬頃で、例年100羽ほど(試験年度は1月12日に400羽)"
        self.assertEqual(O.parse_typical(t, POL), ("11-21", "03-10"))
        self.assertEqual(O.peak_text(t, POL), "1月")

    def test_peak_only_text_is_the_season(self):
        self.assertEqual(O.parse_typical("紅葉の見頃ピークは例年10月下旬〜11月中旬", POL), ("10-21", "11-20"))
        self.assertIsNone(O.peak_text("紅葉の見頃ピークは例年10月下旬〜11月中旬", POL))

    def test_early_bloom_aside(self):
        self.assertEqual(O.parse_typical("見頃は1月中旬〜2月下旬。早咲きは12月上旬から咲き始める", POL), ("01-11", "02-28"))

    def test_without_peak_unchanged(self):
        self.assertEqual(O.parse_typical("11月中旬～12月上旬", POL), ("11-11", "12-10"))


class DatedState(unittest.TestCase):
    """4: 頭の日付が次の語にかかる状態の文(「10/21の活動で13種」)は、答えに出す語で「10月21日の活動で13種」。"""

    def test_dated_short(self):
        raw = "10/21の活動で13種(カルガモ・コガモ)。強い風"
        short = O.short_state(raw, POL)
        self.assertEqual(short, "活動で13種(カルガモ・コガモ)")         # 短い語そのもの(段階77)は変えない
        self.assertEqual(O.dated_short(raw, short, POL), "10月21日の活動で13種(カルガモ・コガモ)")

    def test_state_display(self):
        disp, sym = O.state_display("10/21の活動で13種", "試験公園", POL)
        self.assertEqual((disp, sym), ("10月21日の活動で13種", False))
        self.assertEqual(O.state_display("11/6現在 色づき始め", "試験公園", POL)[0], "色づき始め")


class UnrelatedGeneralCards(unittest.TestCase):
    """3: 場所を聞く質問では、その場所の候補にない種の一般の話のカードを入れない。"""

    def test_drop(self):
        c = GB.cfg()
        theme = c["card_links"]["theme"]
        cards = [{"title": "冬桜の話", "place": "冬桜", "link": theme, "facts": ["冬桜は11月に咲く"]},
                 {"title": "バラの話", "place": "バラ一般", "link": theme, "facts": ["バラは春と秋"]},
                 {"title": "ロウバイの話", "place": "ロウバイ一般", "link": theme, "facts": ["ロウバイは冬"]},
                 {"title": "生き物の話", "place": "生き物", "link": theme, "facts": ["生き物の観察のマナー"]},
                 {"title": "試験園の話", "place": "試験園", "link": c["card_links"]["place"], "facts": ["試験園の芝桜"]}]
        cands = [{"name": "試験ロウバイ園", "theme": "ロウバイ"}, {"name": "試験の丘", "theme": "芝桜"}]
        F = GB._Facts(c, set())
        got = [k["title"] for k in GB._drop_unrelated_general(cards, "試験町で見られる花は?", cands, F, c)]
        self.assertEqual(got, ["ロウバイの話", "生き物の話", "試験園の話"])     # 芝桜の候補で「桜」の話を残さない

    def test_question_species_kept(self):
        c = GB.cfg()
        cards = [{"title": "冬桜の話", "place": "冬桜", "link": c["card_links"]["theme"], "facts": []}]
        got = GB._drop_unrelated_general(cards, "試験町で冬桜は見られる?", [], GB._Facts(c, set()), c)
        self.assertEqual(len(got), 1)


class GuideAnswerPage(unittest.TestCase):
    """第2部: 新しい形の答えのあとの写真つきページは、合格した最終の文と資料から作る(計画を作り直さない)。"""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def _save(self, text, saved_at, bid="b20261112-test0001", cands=None):
        import json
        from pathlib import Path
        from ikimonobiyori import guide_verify as GV
        p = GV.last_guide_path(self.env)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"saved_at": saved_at, "brief": bid, "question": "試験町の花は?", "text": text}, ensure_ascii=False), encoding="utf-8")
        w = GB.brief_dir(self.env) / f"{bid}.work"
        w.mkdir(parents=True, exist_ok=True)
        (w / "facts.json").write_text(json.dumps({"subjects": {"flowers": {"candidates": cands or []}}}, ensure_ascii=False), encoding="utf-8")
        return Path(p)

    def test_newest_and_species_in_text_order(self):
        from datetime import datetime
        from ikimonobiyori import guide_answer_page as GAP
        text = "試験の丘の芝桜と、試験川の河津桜が見どころです。\n\n- **試験川**: 例年2月\n\n出典\n・梅の会 https://example.org/a"
        self._save(text, "2026-11-12T09:00:00+09:00", cands=[{"name": "試験の丘", "flower_kinds": ["シバザクラ"]}])
        now = datetime.fromisoformat("2026-11-12T10:00:00+09:00")
        g = GAP.newest(now, self.env)
        self.assertEqual(g["brief"], "b20261112-test0001")
        names = [n for n, _ in GAP.species(g, self.env)]
        self.assertEqual(names[:2], ["シバザクラ", "カワヅザクラ"])        # 文に出た順。出典の節の「梅」は数えない
        self.assertNotIn("ウメ", names)
        self.assertIsNone(GAP.load_last(datetime.fromisoformat("2026-11-14T10:00:00+09:00"), self.env))   # 有効期間の外

    def test_page_keeps_the_text_and_links(self):
        from datetime import datetime
        from pathlib import Path
        from ikimonobiyori import guide_answer_page as GAP
        text = "試験川の河津桜が見どころです。\n\n- **試験川**: 例年2月上旬〜3月上旬\n\n出典\n・試験町観光協会 https://example.org/a"
        self._save(text, "2026-11-12T09:00:00+09:00")
        now = datetime.fromisoformat("2026-11-12T10:00:00+09:00")
        r = GAP.make(GAP.newest(now, self.env), now, self.env, fetch=False)
        html = Path(r["path"]).read_text(encoding="utf-8")
        self.assertIn("試験川の河津桜が見どころです。", html)
        import re                                                          # 段階81 の続き(本人の承認 2026-11-12): 太字はタグになるので、タグを除いた文字で比べる
        self.assertIn("試験川: 例年2月上旬〜3月上旬", re.sub(r"<[^>]+>", "", html))
        self.assertNotIn("**", html)
        self.assertIn('<a href="https://example.org/a"', html)
        self.assertIn("写真が取れなかった種: カワヅザクラ", html)          # 写真がなければ名前だけ(手書きの図にしない)


class CommonsDomesticFirst(unittest.TestCase):
    """第3部: 学名で Commons を探すとき、撮影地が国内と分かる写真を先に選ぶ(なければ今までの順)。"""

    def info(self, text):
        return {"descriptionurl": "https://commons.wikimedia.org/wiki/File:x.jpg",
                "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/x.jpg/500px-x.jpg",
                "mime": "image/jpeg", "license_short": "CC BY-SA 4.0", "artist": "A", "restrictions": "", "categories": text, "description": text}

    def pick(self, items):
        from ikimonobiyori import guide
        from ikimonobiyori.fetch import commons_photos as CP
        cm = guide.load_policy()["photos"]["commons"]
        pages = [(t, self.info(txt)) for t, txt in items]
        return CP.scientific_pick(pages, {"scientific": "Testus avis"}, cm, [t for t, _ in items])[0]

    def test_domestic_first(self):
        got = self.pick([("File:a.jpg", "Testus avis in Iceland"), ("File:b.jpg", "Testus avis in Chiba, Japan")])
        self.assertEqual(got["title"], "File:b.jpg")

    def test_foreign_only_keeps_the_order(self):
        got = self.pick([("File:a.jpg", "Testus avis in Iceland"), ("File:b.jpg", "Testus avis in Spain")])
        self.assertEqual(got["title"], "File:a.jpg")


class IceFlowerIsNotTheFlower(unittest.TestCase):
    """第3部・第4部: 「氷の花」(シモバシラの茎の氷)とシモバシラの花の写真を取り違えない。"""

    def test_names(self):
        from unittest import mock
        from ikimonobiyori import guide_answer_page as GAP
        from ikimonobiyori import guide_photos as GP
        table = {"シモバシラ": {"name": "シモバシラ", "scientific": "Keiskea japonica", "taxon_id": 1}}
        with mock.patch.object(GP, "load_table", return_value=table):
            names = [n for n, _ in GAP.species({"brief": "x", "text": "試験山ではシモバシラの花が終わり、冬はシモバシラの氷の花が見られます。"})]
        self.assertEqual(names[:2], ["シモバシラ", "シモバシラ(氷の花)"])


class PseudoTaxonIsNotAskedToINaturalist(unittest.TestCase):
    """第3部: 学名で Commons から取った種(仮の id)の写真がキャッシュにないとき、iNaturalist に問い合わせない。"""

    def test_no_request(self):
        import tempfile
        from ikimonobiyori import guide, guide_photos as GP
        policy = guide.load_policy()
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            GP.add_to_table([{"name": "試験ザクラ", "scientific": "Testus-zakura", "taxon_id": policy["photos"]["phenology"]["pseudo_taxon_min"]["value"] + 5,
                              "checked_on": "2026-11-12"}], "花", env, policy)
            calls = []

            def get(url):
                calls.append(url)
                raise AssertionError("通信しない")
            r = GP.ensure(["試験ザクラ"], theme="花", env=env, policy=policy, http_get=get, http_bytes=get, max_requests=0)
        self.assertEqual((r["results"], calls), ({"試験ザクラ": "none"}, []))


if __name__ == "__main__":
    unittest.main()


class PageAfterReview81(unittest.TestCase):
    """段階81 の追記(本人の判断 2026-11-12): 載せる種は 12 まで・上限で載せなかった種と写真が取れなかった種を分ける・
    写真の説明に状態を出さない(種の名前・撮影者・ライセンス・元のページ)・総称の種は代表の写真で「写真は○○」。合成データ。"""

    def _meta(self, i, source=None):
        return {"image_type": "jpeg", "license": "CC BY", "attribution": f"撮影者{i}", "photo_page": f"https://www.inaturalist.org/photos/{i}",
                "source": source, "state": "開花", "scientific": "Testus testus", "rule": 1}

    def _build(self, names, have, max_bytes=None):
        from ikimonobiyori import answer_page as APG
        photos = {n: (self._meta(i), b"\xff\xd8\xff" + bytes([i]) * 100) for i, n in enumerate(have, start=1)}
        doc = {"route": "guide", "question": "試験?", "text": "試験の文です。", "species": names}
        return APG.build(doc, photo_for=photos.get, photo_credit=lambda m: f"写真: {m['attribution']}・{m['license']}",
                         csp="default-src 'none'", max_bytes=max_bytes)

    def test_cap_is_twelve_and_over_is_its_own_line(self):
        from ikimonobiyori import answer_page as APG
        c = APG.cfg()
        self.assertEqual(c["max_species"], 12)
        names = [f"種{i:02d}" for i in range(1, 15)]                      # 14 種。13・14 種目は上限の行
        html, _l, shown = self._build(names + ["写真なし種"], names)
        self.assertEqual(sum(1 for _n, x in shown if x), 12)
        self.assertIn(c["over_limit_names"].format(names="種13・種14・写真なし種"), html)
        self.assertNotIn(c["no_photo_names"].split("{")[0], html)

    def test_no_photo_and_over_are_separate(self):
        from ikimonobiyori import answer_page as APG
        c = APG.cfg()
        html, _l, _s = self._build(["種01", "種02"], ["種01"])
        self.assertIn(c["no_photo_names"].format(names="種02"), html)
        self.assertNotIn(c["over_limit_names"].split("{")[0], html)

    def test_embed_budget_goes_to_the_over_line(self):
        from ikimonobiyori import answer_page as APG
        c = APG.cfg()
        html, _l, _s = self._build(["種01", "種02"], ["種01", "種02"], max_bytes=150)   # 2 枚目は大きさの上限で載らない(写真はある)
        self.assertIn(c["over_limit_names"].format(names="種02"), html)
        self.assertNotIn(c["no_photo_names"].split("{")[0], html)

    def test_caption_has_no_state_and_links_the_source(self):
        html, _l, _s = self._build(["種01"], ["種01"])
        self.assertNotIn("状態", html)
        self.assertNotIn("Testus testus", html)
        self.assertIn('<a href="https://www.inaturalist.org/photos/1"', html)
        self.assertIn("写真: 撮影者1・CC BY", html)

    def test_generic_name_uses_the_representative_and_says_so(self):
        from ikimonobiyori import answer_page as APG
        c = APG.cfg()
        r = APG.representative("ツツジ")
        self.assertIsNotNone(r)
        html, _l, shown = self._build(["ツツジ"], [r["name"]])
        self.assertEqual(shown, [("ツツジ", True)])
        self.assertIn(c["representative_caption"].format(label=r["label"]), html)
        self.assertIn("<h3>ツツジ</h3>", html)
        html2, _l, _s = self._build(["ヤマツツジ"], [r["name"]])           # 代表の種そのものの写真には「写真は○○」を付けない
        self.assertNotIn(c["representative_caption"].format(label=r["label"]), html2)

    def test_every_representative_has_a_reason_and_label(self):
        from ikimonobiyori import answer_page as APG
        reps = APG.cfg()["representatives"]
        self.assertTrue({"ツツジ", "シャクナゲ", "バラ", "スイレン", "ヤエザクラ"} <= set(reps))
        for k, v in reps.items():
            self.assertTrue(v.get("name") and v.get("label") and v.get("reason"), k)

    def test_generic_word_in_the_guide_text_is_found(self):
        import json
        import tempfile
        from ikimonobiyori import guide_answer_page as GAP
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IKIMONOBIYORI_DATA_DIR": tmp}
            doc = {"brief": "b-none", "text": "試験園のツツジとバラが見どころです。"}
            names = [n for n, _ in GAP.species_all(doc, env)]
            self.assertEqual(names[:2], ["ツツジ", "バラ"])
            json.dumps(names)

    def test_guide_page_and_wildflower_captions_have_no_state(self):
        import inspect
        from ikimonobiyori import answer_page, ask, guide_answer_page, guide_page, plan_page, wildflower_page
        for m in (answer_page, ask, guide_answer_page, guide_page, plan_page, wildflower_page):
            import re
            src = inspect.getsource(m)
            calls = re.findall(r"(?<!def )state_text\(meta", src)
            self.assertFalse(calls, m.__name__)                              # 写真の説明に状態を出す呼び出しがない(関数の定義は残す)
