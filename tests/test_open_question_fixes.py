"""2026-11-28 の会話で見つかった小さな直し(指示書 open-question-breadth 第4部 1〜8)。通信しない。材料はすべて作り物。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide_brief as GB
from ikimonobiyori import guide_materials as GM
from ikimonobiyori import guide_verify as GV


def _s(text, ids, line=1):
    return {"line": line, "text": text, "clean": text, "ids": ids}


class SourceDates(unittest.TestCase):
    """第4部 2・3: 出典の「〜時点」は発信の日付があるときだけ。本文に日付つきで書いた発行元は「ほか」にまとめない。"""

    def test_read_date_is_checked_not_as_of(self):
        c = GB.cfg()
        cited = [{"id": "F001", "kind": "current", "url": "https://garden-test.example.jp/", "source": "試験の庭園(作り物)",
                  "source_class": "official", "observed": None, "read_at": "2026-11-09T19:05:29+09:00"}]
        line = GV.short_sources(cited, c)
        self.assertIn("11/9に確認", line)
        self.assertNotIn("時点", line)
        full = GV.final_sources(cited, c)
        self.assertIn("11/9に確認", full[0])

    def test_dated_publisher_not_folded(self):
        c = GB.cfg()
        cited = [{"id": f"K{i:03d}", "kind": "card", "url": f"https://card{i}-test.example.jp/", "source": f"試験の解説{i}(作り物)",
                  "checked_on": "2026-11-11"} for i in range(1, 9)]
        cited.append({"id": "F009", "kind": "current", "url": "https://kana-test.example.jp/", "source": "試験の花の園(作り物)",
                      "source_class": "official", "observed": "2026-11-27", "read_at": "2026-11-28T09:00:00+09:00"})
        line = GV.short_sources(cited, c)
        self.assertIn("試験の花の園(作り物)(11/27時点)", line)
        self.assertTrue(line.index("試験の花の園") < line.index("試験の解説1"))
        self.assertIn("ほか", line)


class DateBasis(unittest.TestCase):
    """第4部 2: 本文と事実の日付の持ち方の食い違いを照合で止める。"""

    def setUp(self):
        self.c = GB.cfg()
        self.brief = {"facts": [
            {"id": "F001", "kind": "current", "content": "試験の庭園: 見ごろの花", "observed": None},
            {"id": "F002", "kind": "current", "content": "試験の園: サザンカ", "observed": "2026-11-27"}]}

    def codes(self, sents):
        return [e["code"] for e in GV.date_basis_errors(sents, self.brief, self.c)]

    def test_undated_fact_with_as_of(self):
        self.assertEqual(self.codes([_s("試験の庭園では、11/9時点で見ごろの花が挙がっています。", ["F001"])]), ["date_basis_mismatch"])

    def test_dated_fact_said_unknown(self):
        self.assertEqual(self.codes([_s("試験の園の発信は、いつの発信か分かりません。", ["F002"])]), ["date_basis_mismatch"])

    def test_consistent(self):
        self.assertEqual(self.codes([_s("試験の庭園の発信は日付の書かれていないもので、いつの発信か分かりません。", ["F001"]),
                                     _s("11月27日時点で、試験の園ではサザンカが見ごろです。", ["F002"])]), [])


class UpcomingHeading(unittest.TestCase):
    """第4部 4: 「これから」の節に、対象の日がもう時期の中に入るものを入れない。"""

    def setUp(self):
        self.c = GB.cfg()
        self.brief = {"dates": {"periods": [["2026-11-28", "2026-11-29"]]}}

    def codes(self, body):
        return [e["code"] for e in GV.upcoming_heading_errors(body, self.brief, self.c)]

    def test_in_season_under_upcoming(self):
        body = "## これから\n\n冬桜は11月中旬〜12月上旬がいちばん良い時期とされます。\n"
        self.assertEqual(self.codes(body), ["upcoming_heading_in_season"])

    def test_future_under_upcoming(self):
        body = "## これからの桜\n\n河津桜は例年2月中旬〜3月上旬です。\n"
        self.assertEqual(self.codes(body), [])

    def test_in_season_under_other_heading(self):
        body = "## 冬桜\n\n冬桜は11月中旬〜12月上旬がいちばん良い時期とされます。\n"
        self.assertEqual(self.codes(body), [])


class IslandDistance(unittest.TestCase):
    """第4部 5: 船か飛行機が要る島は、直線の距離だけを書かない。"""

    def test_label(self):
        km, label = GM.distance_text("試験の島の公園(作り物)", 83.0, "横浜", prefecture="東京都", city="大島町")
        self.assertIn("船か飛行機", label)
        self.assertIn("直線で約83km", label)

    def test_verify(self):
        c = GB.cfg()
        brief = {"candidates": [{"name": "試験の島の公園", "city": "大島町", "distance_text": "船か飛行機で渡る島(直線で約83km)"}]}
        bad = GV.distance_errors([_s("試験の島の公園(直線で約83km)は、ツバキの名所です。", [])], brief, c)
        good = GV.distance_errors([_s("試験の島の公園は船か飛行機で渡る島で、直線で約83kmです。", [])], brief, c)
        self.assertEqual([e["code"] for e in bad], ["island_distance"])
        self.assertEqual(good, [])


class WeatherAndToday(unittest.TestCase):
    """第4部 6・7: 出かける日の答えの最後の天気の一言、対象の日に今日が入るときの書き方。"""

    def test_weather_line(self):
        c = GB.cfg()
        self.assertEqual(GV.weather_line({"route": "plan"}, "本文。", c), c["weather_line"]["line"])
        self.assertIsNone(GV.weather_line({"route": "knowledge"}, "本文。", c))
        self.assertIsNone(GV.weather_line({"route": "plan"}, "山の天気はヤマビヨリで確かめてください。", c))

    def test_today_line(self):
        d = {"today": "2026-11-28", "periods": [["2026-11-28", "2026-11-29"]]}
        lines = GB._today_lines(d)
        self.assertEqual(len(lines), 1)
        self.assertIn("11/28(土)は今日", lines[0])
        self.assertEqual(GB._today_lines({"today": "2026-11-26", "periods": [["2026-11-28", "2026-11-29"]]}), [])


if __name__ == "__main__":
    unittest.main()
