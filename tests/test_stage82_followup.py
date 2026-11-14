"""段階82 の続き(本人の判断 2026-11-13 の 3〜5): 紅葉の木の夏の葉の写真(説明に「写真は夏の葉」)・全体の目安は公式の記録を先に・
チングルマを種の名所として引き、綿毛の姿の写真を資料とページに。合成データ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide
from ikimonobiyori import guide_answer_page as GAP
from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_materials as GM
from ikimonobiyori import guide_photos as GP
from ikimonobiyori import plan_page as PP
from ikimonobiyori import research as RS
from ikimonobiyori import season_place as SP

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 13, 9, 0, tzinfo=JST)
TODAY = date(2026, 11, 13)


def no_net(*a, **k):
    raise AssertionError("通信しない")


class TempEnv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()


class SummerLeafPhotos(TempEnv):
    """3: 秋の姿の写真がない紅葉の木は、点検で可の緑の葉の写真を「写真は夏の葉」と書いて使う。"""

    def archive(self, tid, tag, **meta):
        d = GP.cache_dir(self.env)
        a = d / GP.photos_policy()["check_archive_dir"]
        a.mkdir(parents=True, exist_ok=True)
        (a / f"{tid}-{tag}.jpeg").write_bytes(bytes([255, 216, 255]) + b"0" * 20)
        m = {"name": "コナラ", "taxon_id": tid, "photo_id": 431465759, "image_type": "jpeg", "license": "CC BY 4.0",
             "photo_page": "https://www.inaturalist.org/photos/431465759", "check": {"verdict": "ng"}, **meta}
        (a / f"{tid}-{tag}.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")

    def test_restore_marks_ok_and_clears_the_no_photo_lists(self):
        GP.add_to_table([{"name": "コナラ", "scientific": "Quercus serrata", "taxon_id": 359972, "checked_on": "2026-11-12"}], "紅葉", self.env)
        self.archive(359972, "431465759")
        GP._save_json(GP.skip_photo_path(self.env), {"359972": [431465759]})
        GP.review_path(self.env).parent.mkdir(parents=True, exist_ok=True)
        GP.review_path(self.env).write_text(json.dumps({"359972": "写真なし"}), encoding="utf-8")
        row = GP.restore_checked(359972, "359972-431465759", note="summer_leaf", reason="夏の葉", today=TODAY, env=self.env)
        self.assertEqual(row["verdict"], "ok")
        meta, _b = GP.load_photo(359972, self.env)
        self.assertEqual(meta["caption_note"], "summer_leaf")
        self.assertNotIn("check", meta)
        self.assertNotIn("359972", GP.load_review(self.env))
        self.assertNotIn(431465759, GP.load_skip_photos(self.env).get(359972, set()))
        self.assertTrue(GP.checked_ok(359972, self.env))
        res = GP.ensure(["コナラ"], theme="紅葉", env=self.env, http_get=no_net, http_bytes=no_net, phenology=True, max_requests=10,
                        today=TODAY, sleep=lambda s: None)                          # 点検済みで可なので、取り直さない・置き換えない
        self.assertEqual((res["results"]["コナラ"], res["requests"]), ("cached", 0))

    def test_unknown_note_is_refused(self):
        self.archive(359972, "431465759")
        with self.assertRaises(ValueError):
            GP.restore_checked(359972, "359972-431465759", note="winter", reason="x", today=TODAY, env=self.env)

    def test_every_caption_builder_writes_the_note(self):
        meta = {"license": "CC BY 4.0", "artist": "someone", "attribution": "(c) someone, some rights reserved", "caption_note": "summer_leaf"}
        gp = GP.photos_policy()
        self.assertTrue(PP.author_credit(meta, gp).startswith("写真は夏の葉。写真: "))       # 答えのページ・ガイドの答えのページ・ask photos
        h = guide.load_policy()["photos"]["html"]
        self.assertTrue(PP.with_caption_note(meta, "写真: x・CC BY 4.0", h).startswith("写真は夏の葉。"))   # guide_page・wildflower_page
        self.assertEqual(PP.with_caption_note({"license": "CC BY 4.0"}, "写真: x", h), "写真: x")           # 断りのない写真はそのまま


class OfficialFirst(TempEnv):
    """4: 全体の目安は、公式の記録を紹介サイト由来の記録より先に使って作る。"""
    URL = "https://www.showakinen-koen.jp/flower-information/"

    def test_official_record_replaces_secondary_window(self):
        RS._save_state("b-t", {"pages": [{"url": self.URL, "at": NOW.isoformat(), "status": 200}], "first_at": NOW.isoformat(),
                               "question": "サザンカ"}, self.env)
        r = RS.record([{"subject": "flowers", "name": "国営昭和記念公園", "prefecture": "東京都", "city": "立川市", "kind": "サザンカ",
                        "typical": "10月下旬〜2月下旬", "url": self.URL, "publisher": "国営昭和記念公園"}], "b-t", question="サザンカ", env=self.env, now=NOW)
        self.assertEqual(r["written"], 1)
        sp = SP.resolve_all("サザンカの見頃")[0]
        rows = {x["name"]: x for x in SP.gather(sp, "東京", env=self.env)}
        self.assertEqual((rows["国営昭和記念公園"]["start"], rows["国営昭和記念公園"]["official"]), ("10-21", True))
        keep, _ = SP.select(list(rows.values()), "東京")
        for x in keep:
            x["species"] = "サザンカ"
        lead = GM.species_leads(keep, TODAY)["サザンカ"][0]
        a, b = SP.month_span([x for x in keep if x.get("start")])
        self.assertEqual(a, 10)                                          # 公式の 10月下旬が目安に入る
        self.assertIn("10月", lead)

    def test_other_kinds_season_text_is_not_this_kinds(self):
        kinds = [{"kind": "サザンカ"}, {"kind": "ツバキ"}, {"kind": "梅"}]
        self.assertTrue(SP._season_of_other_kind("2月上旬頃から4月にかけて春の植物(ウメ・ツバキ・サクラ)", ["サザンカ"], kinds))
        self.assertFalse(SP._season_of_other_kind("サザンカとツバキは11月から", ["サザンカ"], kinds))
        self.assertFalse(SP._season_of_other_kind("梅の見頃のあとにツバキ", ["梅"], kinds))
        self.assertTrue(SP._season_of_other_kind("梅は1月上旬から", ["サザンカ"], kinds))       # 今までの決まり(名前で始まる)はそのまま
        birds = [{"kind": "カモ"}, {"kind": "シギ"}, {"kind": "チドリ"}]
        self.assertFalse(SP._season_of_other_kind("通年(秋〜春にカモ・シギ)", ["チドリ"], birds))   # 月のない名所全体の文は外さない


class Chingruma(TempEnv):
    """5: チングルマを種の名所として引き、綿毛の姿の写真を資料とページに。"""
    Q = "チングルマの夏と秋の姿が見たい。どこで見られる?"

    def test_species_route(self):
        self.assertEqual([s["name"] for s in SP.resolve_all(self.Q)], ["チングルマ"])
        self.assertEqual([s["name"] for s in SP.resolve_all("稚児車はどこで見られる")], ["チングルマ"])

    def seed_photo(self, verdict="ok"):
        GP.add_to_table([{"name": "チングルマ(綿毛)", "scientific": "Sieversia pentapetala", "taxon_id": 9100000001, "checked_on": "2026-11-12"}], "野草", self.env)
        d = GP.cache_dir(self.env)
        d.mkdir(parents=True, exist_ok=True)
        (d / "9100000001.jpeg").write_bytes(bytes([255, 216, 255]) + b"0" * 20)
        (d / "9100000001.json").write_text(json.dumps({"name": "チングルマ(綿毛)", "taxon_id": 9100000001, "image_type": "jpeg", "license": "CC BY-SA 4.0",
                                                       "source": "wikimedia_commons", "photo_page": "https://commons.wikimedia.org/wiki/File:A.jpg"}), encoding="utf-8")
        GP.set_check(9100000001, verdict, None, today=TODAY, env=self.env)

    def test_form_photo_in_brief_only_when_checked_ok(self):
        self.assertEqual(GB.form_photos(self.Q, self.env), [])
        self.seed_photo()
        self.assertEqual(GB.form_photos(self.Q, self.env), [{"name": "チングルマ(綿毛)", "species": "チングルマ", "word": "綿毛"}])
        self.assertEqual(GB.form_photos("サザンカの見頃", self.env), [])

    def test_form_photo_lines_in_markdown(self):
        self.seed_photo()
        b = GB.build(self.Q, now=NOW, env=self.env)
        self.assertEqual(b["photos"][0]["name"], "チングルマ(綿毛)")
        self.assertIn("チングルマ(綿毛): 答えでチングルマの「綿毛」の姿を書くと", GB.render_md(b))

    def test_page_picks_the_form_photo_from_the_word(self):
        self.seed_photo()
        b = GB.build(self.Q, now=NOW, env=self.env)
        GB.save(b, self.env)
        doc = {"brief": b["id"], "text": "チングルマは夏に白い花を咲かせ、花のあとは羽毛のような綿毛になります。"}
        names = [n for n, _t, _w in GAP._found(doc, self.env)]
        self.assertIn("チングルマ(綿毛)", names)
        doc2 = {"brief": b["id"], "text": "チングルマは夏に白い花を咲かせます。"}
        self.assertNotIn("チングルマ(綿毛)", [n for n, _t, _w in GAP._found(doc2, self.env)])


if __name__ == "__main__":
    unittest.main()
