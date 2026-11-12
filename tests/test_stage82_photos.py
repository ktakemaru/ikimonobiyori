"""段階82 第4部: 写真の選び方(卵・標本などの語・国内と東アジアを先に・地域で分かれる鳥)・点検の記録・写真の指摘のあとの最後の文。合成データ(通信しない)。"""
import json
import tempfile
import unittest
from datetime import date

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide
from ikimonobiyori import guide_photos as GP
from ikimonobiyori import stop_hook as SH
from ikimonobiyori.fetch import commons_photos as CP

CM = guide.load_policy()["photos"]["commons"]
TODAY = date(2026, 11, 12)


def info(cat="", desc=""):
    return {"categories": cat, "description": desc}


class Selection(unittest.TestCase):
    def test_denied_words(self):
        self.assertTrue(CP.denied("File:Asio flammeus MHNT.ZOO.2010.11.jpg", info(), CM))
        self.assertTrue(CP.denied("File:Asio flammeus eggs.jpg", info(), CM))
        self.assertTrue(CP.denied("File:X.jpg", info(cat="Taxidermy of birds"), CM))
        self.assertTrue(CP.denied("File:X.jpg", info(desc="分布図"), CM))
        self.assertIsNone(CP.denied("File:Asio flammeus in flight Japan.jpg", info(), CM))
        self.assertIsNone(CP.denied("File:Eggshell-colored flowers.jpg".replace("Eggshell-colored", "Begging"), info(), CM))   # 語の一部(begging)は当たらない

    def test_denied_titles(self):
        cm = {**CM, "deny_titles": frozenset(["File:A b.jpg"])}
        self.assertTrue(CP.denied("File:A b.jpg", info(), cm))

    def test_region_rank(self):
        self.assertEqual(CP.region_rank("File:Circus spilonotus Chiba.jpg", info(), CM), 0)
        self.assertEqual(CP.region_rank("File:X.jpg", info(cat="Birds of Korea"), CM), 1)
        self.assertEqual(CP.region_rank("File:X.jpg", info(cat="Birds of France"), CM), 2)

    def test_regional_species_need_japan_or_east_asia(self):
        row = {"name": "チュウヒ", "scientific": "Circus spilonotus", "taxon_id": 1}
        self.assertTrue(CP.regional(row, CM))
        ok = {"license_short": "CC BY-SA 4.0", "restrictions": "", "mime": "image/jpeg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:A.jpg",
              "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a.jpg", "artist": "someone"}
        pages = [("File:Circus spilonotus Europe.jpg", {**ok, "categories": "Circus spilonotus", "description": ""}),
                 ("File:Circus spilonotus Taiwan.jpg", {**ok, "categories": "Circus spilonotus", "description": ""})]
        pick, _seen = CP.scientific_pick(pages, row, CM, [t for t, _ in pages])
        self.assertEqual(pick["title"], "File:Circus spilonotus Taiwan.jpg")
        pick2, seen2 = CP.scientific_pick(pages[:1], row, CM, [pages[0][0]])
        self.assertIsNone(pick2)


class Checks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}
        d = GP.cache_dir(self.env)
        d.mkdir(parents=True)
        (d / "5.jpeg").write_bytes(b"\xff\xd8\xff" + b"0" * 20)
        (d / "5.json").write_text(json.dumps({"name": "試験の鳥", "taxon_id": 5, "photo_id": 77, "image_type": "jpeg",
                                              "photo_page": "https://www.inaturalist.org/photos/77"}), encoding="utf-8")
        (d / "6.jpeg").write_bytes(b"\xff\xd8\xff" + b"0" * 20)
        (d / "6.json").write_text(json.dumps({"name": "試験の花", "taxon_id": 6, "photo_id": None, "image_type": "jpeg", "source": "wikimedia_commons",
                                              "photo_page": "https://commons.wikimedia.org/wiki/File:Test_flower_egg.jpg"}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unchecked_then_ok(self):
        self.assertEqual([r["check"] for r in GP.cached_photos(self.env)], [None, None])
        GP.set_check(5, "ok", None, today=TODAY, env=self.env)
        self.assertEqual(GP.load_checks(self.env)["5"]["verdict"], "ok")
        self.assertIsNotNone(GP.load_photo(5, self.env))

    def test_ng_keeps_a_copy_and_skips_the_photo(self):
        GP.set_check(5, "ng", "卵の写真", today=TODAY, env=self.env)
        self.assertFalse(GP.has_cache(5, self.env))
        arch = GP.cache_dir(self.env) / GP.photos_policy()["check_archive_dir"]
        self.assertTrue(any(p.suffix == ".jpeg" for p in arch.iterdir()))          # 消さずに控え
        self.assertIn(77, GP.load_skip_photos(self.env)[5])                          # 次は別の写真を選ぶ
        self.assertEqual(GP.load_checks(self.env)["5"]["reason"], "卵の写真")

    def test_ng_commons_title_is_denied(self):
        GP.set_check(6, "ng", "手が写っている", today=TODAY, env=self.env)
        self.assertIn("File:Test flower egg.jpg", GP.load_commons_denied(self.env))


class PhotoFixHook(unittest.TestCase):
    def turn(self, *cmds):
        return {"prompt": "この写真はおかしい", "calls": [{"name": "Bash", "input": {"command": c}} for c in cmds]}

    def test_photo_reply_text_passes_and_other_text_blocks(self):
        t = self.turn("python -X utf8 -m ikimonobiyori.ask photo-review set --name A --verdict ng",
                      "python -X utf8 -m ikimonobiyori.ask page", "python -X utf8 -m ikimonobiyori.ask photo-reply --name A --url u")
        ok = SH.decide({"last_assistant_message": "決まった文"}, t, None, page_ok=lambda m: m == "決まった文")
        self.assertEqual((ok["block"], ok["why"]), (False, "photo_fix"))
        ng = SH.decide({"last_assistant_message": "写真を直しました!"}, t, None, page_ok=lambda m: m == "決まった文")
        self.assertEqual((ng["block"], ng["why"]), (True, "photo_fix_mismatch"))


if __name__ == "__main__":
    unittest.main()
