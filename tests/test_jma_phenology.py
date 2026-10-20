"""気象庁 生物季節観測の累年値ファイルの正規化(段階13。ikimonobiyori/jma_phenology.py)。通信なし。
実際の CSV はリポジトリに置かない(docs/data-sources.md §1.4)ので、同じ形の小さな合成データ(cp932)をテストの中で作る。"""
import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import jma_phenology as J
from ikimonobiyori.fetch import ParseError

DEF = J.load_definition()
PHEN = {p["key"]: p for p in DEF["phenomena"]}
LAYOUT = DEF["layout"]
SUMMARY = ",".join(LAYOUT["summary_columns"])


def synthetic(code, name, rows, years=(2020, 2021, 2022, 2023), last_rm="e"):
    """合成の累年値 CSV の本文。rows = [(番号, 地点名, [(値, rm), ...]), ...]。最後の年の rm の列名は実物と同じく 'e'。"""
    hdr = ["番号", "地点名"]
    for i, y in enumerate(years):
        hdr += [str(y), last_rm if i == len(years) - 1 else "rm"]
    hdr += LAYOUT["summary_columns"]
    lines = [",".join([str(int(code)), name] + [""] * (len(hdr) - 2)), ",".join(hdr)]
    for no, nm, cells in rows:
        flat = [x for c in cells for x in c]
        lines.append(",".join([no, nm] + flat + ["0"] * len(LAYOUT["summary_columns"])))
    return "\r\n".join(lines) + "\r\n"


KAEDE = synthetic("015", "かえでの紅葉", [
    ("662", "東京　　", [("1125", "8"), ("0", "0"), ("1203", "9"), ("0", "0")]),     # 2021 年は値なし。2023 年は全地点で値なし(未来の年の扱い)
    ("678", "八丈島　", [("0", "0"), ("105", "8"), ("0", "0"), ("0", "0")]),                  # 1月5日 = 翌年(2022-01-05)
])
UME = synthetic("001", "うめの開花", [
    ("662", "東京　　", [("1215", "8"), ("201", "8"), ("0", "0"), ("0", "0")]),       # 12月15日 = 前年(2019-12-15)
])


class Parse(unittest.TestCase):
    def parse(self, text, key="kaede_koyo", stations=None):
        return J.parse_text(text, PHEN[key], LAYOUT, stations)

    def test_values_no_values_and_cross_year_dates(self):
        rows, info = self.parse(KAEDE)
        got = {(r["station_no"], r["year"]): (r["date"], r["status"], r["rm"], r["cross_year"]) for r in rows}
        self.assertEqual(got, {("662", 2020): ("2020-11-25", "observed", "8", "0"), ("662", 2021): ("", "no_value", "", "0"),
                               ("662", 2022): ("2022-12-03", "observed", "9", "0"),
                               ("678", 2020): ("", "no_value", "", "0"), ("678", 2021): ("2022-01-05", "observed", "8", "1"),
                               ("678", 2022): ("", "no_value", "", "0")})
        self.assertEqual((info["first_year"], info["last_year_with_value"], info["header_last_year"], info["stations"]), (2020, 2022, 2023, 2))
        self.assertEqual({r["station_name"] for r in rows}, {"東京", "八丈島"})          # 全角空白を除く
        self.assertTrue(all(r["lat"] == "" and r["elevation_m"] == "" for r in rows))   # 座標・標高は CSV にない(空。0 で埋めない)

    def test_spring_december_values_belong_to_the_previous_year(self):
        rows, _ = self.parse(UME, "ume_kaika")
        got = {r["year"]: (r["date"], r["cross_year"]) for r in rows}
        self.assertEqual(got, {2020: ("2019-12-15", "1"), 2021: ("2021-02-01", "0")})   # 2022 年以降は値がないので落とす

    def test_station_metadata_is_copied_when_known(self):
        rows, _ = self.parse(KAEDE, stations=[{"station_no": "662", "lat": 35.1, "lon": 139.1, "elevation_m": 25}])
        r = next(r for r in rows if r["station_no"] == "662")
        self.assertEqual((r["lat"], r["lon"], r["elevation_m"]), (35.1, 139.1, 25))

    def test_unexpected_shapes_raise_parse_error(self):
        bad = {
            "存在しない日付": KAEDE.replace("1125", "1131"),
            "数字でない値": KAEDE.replace("1125", "11/25"),
            "値なしなのに rm": KAEDE.replace(",1125,8,0,0,", ",1125,8,0,8,"),
            "rm が数字でない": KAEDE.replace("1125,8", "1125,x"),
            "1行目の現象が違う": KAEDE.replace("かえでの紅葉", "かえでの落葉"),
            "見出しが違う": KAEDE.replace("地点名", "地点"),
            "まとめの列が違う": KAEDE.replace("最晩年", "最晩"),
            "列の数が違う": KAEDE.replace("1125,8,", "1125,8,1,"),
            "年が並んでいない": KAEDE.replace("2021,rm", "2025,rm"),
            "番号が数字でない": KAEDE.replace("\r\n662,", "\r\nX62,"),
            "行が足りない": KAEDE.split("\r\n")[0],
        }
        for why, text in bad.items():
            with self.subTest(why=why):
                self.assertNotEqual(text, KAEDE, why)
                with self.assertRaises(ParseError):
                    self.parse(text)

    def test_a_file_with_no_values_at_all_gives_no_rows(self):
        rows, info = self.parse(synthetic("015", "かえでの紅葉", [("662", "東京", [("0", "0")] * 4)]))
        self.assertEqual((rows, info["last_year_with_value"]), ([], None))


class NormalizeAndSummary(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="ikimono-jma-"))
        self.addCleanup(shutil.rmtree, self.d, True)
        raw = self.d / "raw"
        raw.mkdir()
        (raw / "015.csv").write_bytes(KAEDE.encode("cp932"))
        (raw / "001.csv").write_bytes(UME.encode("cp932"))
        self.raw = raw

    def test_normalize_reads_cp932_and_reports_missing_files(self):
        rows, infos, missing = J.normalize(self.raw, DEF)
        self.assertEqual([i["file"] for i in infos], ["015.csv", "001.csv"])
        self.assertEqual(sorted(missing), ["icho_koyo", "icho_rakuyo", "kaede_rakuyo", "sakura_kaika", "sakura_mankai"])
        self.assertEqual(len(rows), 6 + 2)
        self.assertEqual([r["phenomenon_code"] for r in rows][:2], ["001", "001"])      # 並びは 現象 → 地点 → 年

    def test_cli_writes_only_the_given_output_and_round_trips(self):
        out = self.d / "out" / "normalized.csv"
        before = sorted(p.name for p in self.raw.iterdir())
        with contextlib.redirect_stdout(io.StringIO()) as s:
            self.assertEqual(J.main(["normalize", "--raw-dir", str(self.raw), "--out", str(out)]), 0)
        self.assertIn("を加工して作成", s.getvalue())                                    # 出典と加工したことを表示する
        self.assertEqual(sorted(p.name for p in self.raw.iterdir()), before)              # 元のファイルは変えない
        self.assertEqual(sorted(p.name for p in self.d.rglob("*") if p.is_file()), ["001.csv", "015.csv", "normalized.csv"])
        back = J.read_csv(out)
        self.assertEqual(list(back[0]), J.COLUMNS)
        self.assertEqual(len(back), 8)
        with contextlib.redirect_stdout(io.StringIO()) as s:
            self.assertEqual(J.main(["summary", "--normalized", str(out), "--region", "関東甲信"]), 0)
        self.assertIn("662 東京\tkaede_koyo\t3\t2\t1\t2020\t2022", s.getvalue())

    def test_summary_counts(self):
        rows, _, _ = J.normalize(self.raw, DEF)
        s = J.summarize(rows)
        self.assertEqual(s[("662", "東京", "kaede_koyo")], {"years": 3, "observed": 2, "no_value": 1, "first": 2020, "last": 2022})
        self.assertEqual(s[("678", "八丈島", "kaede_koyo")], {"years": 3, "observed": 1, "no_value": 2, "first": 2021, "last": 2021})
        self.assertEqual(set(J.summarize(rows, {"678"})), {("678", "八丈島", "kaede_koyo")})


class Definition(unittest.TestCase):
    def test_the_seven_phenomena(self):
        self.assertEqual({p["code"]: p["key"] for p in DEF["phenomena"]},
                         {"015": "kaede_koyo", "016": "kaede_rakuyo", "013": "icho_koyo", "014": "icho_rakuyo",
                          "004": "sakura_kaika", "005": "sakura_mankai", "001": "ume_kaika"})

    def test_station_numbers_are_strings_and_kanto_koshin_is_listed(self):
        for s in DEF["stations"]:
            self.assertIsInstance(s["station_no"], str)
            self.assertRegex(s["station_no"], r"^\d{3}$")
        self.assertEqual(len(J.region_station_nos(DEF, "関東甲信")), 15)
        self.assertEqual(len(J.region_station_nos(DEF, "関東甲信", include_islands=False)), 12)

    def test_no_jma_data_is_tracked(self):
        lines = [l.strip() for l in (H.ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()]
        self.assertIn("/data/jma_phenology/raw/*", lines)
        self.assertIn("/data/jma_phenology/normalized.csv", lines)


if __name__ == "__main__":
    unittest.main()
