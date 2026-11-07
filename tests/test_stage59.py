"""段階59(指示書 docs/stage59-nature-guide-knowledge-instructions.md): 知識の層。通信しない。合成データだけ。"""
import json
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import pdf_text as PT

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))


def minimal_pdf(path, text_lines=()):
    """手で作った最小の PDF(ASCII の本文。text_lines が空ならテキストなし)。"""
    content = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({l}) Tj 0 -14 Td" for l in text_lines) + " ET" if text_lines else ""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for x in offs:
        out += f"{x:010d} 00000 n \n".encode()
    out += f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    Path(path).write_bytes(out)


class Part6Pdf(unittest.TestCase):
    def test_vertical_lines_are_joined(self):
        self.assertEqual(PT.join_vertical("見\n出\nし\nの\n文\n普通の行"), "見出しの文\n普通の行")
        self.assertEqual(PT.join_vertical("1\n2\n普通"), "1\n2\n普通")               # 短い並びは連結しない

    def test_assess_status(self):
        self.assertEqual(PT.assess(""), "読めない")
        self.assertEqual(PT.assess("1 2 3 45 678"), "画像のみ")
        self.assertEqual(PT.assess("紅葉" * 20), "一部")
        self.assertEqual(PT.assess("紅葉" * 200), "読めた")

    def test_pdfminer_reads_minimal_pdfs(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "t.pdf", Path(d) / "n.pdf"
            minimal_pdf(a, ["Autumn leaves", "Okutama"])
            minimal_pdf(b)
            self.assertIn("Okutama", PT.extract_with_pdfminer(a))
            self.assertEqual(PT.extract_with_pdfminer(b).strip(), "")

    def test_methods_in_order_and_unread(self):
        good = "紅葉" * 200
        got = PT.read_with_methods([("a", lambda: ""), ("c", lambda: good)])
        self.assertEqual((got["method"], got["status"]), ("c", "読めた"))

        def boom():
            raise OSError("拒否")
        got = PT.read_with_methods([("a", boom), ("c", lambda: "1 2 3")])
        self.assertEqual((got["method"], got["status"], got["text"]), ("d", "PDF 未読", None))

    def test_ledger_keeps_no_full_text(self):
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            body = "奥多摩の紅葉は標高で約一か月ずれるという本文" * 30
            row = PT.record_publication({"facility": "試験VC", "title": "季刊誌", "issue": "10号", "published": "2023-10", "url": "https://x.example/a.pdf", "format": "pdf", "taken_on": "2026-11-07"},
                                        text=body, env=env, read_method="c")
            self.assertEqual(row["status"], "読めた")
            self.assertTrue(row["hash"])
            raw = PT.ledger_path(env).read_text(encoding="utf-8")
            self.assertNotIn("標高で約一か月", raw)
            self.assertEqual(PT.load_publications(env)[0]["method"], "c")
            un = PT.record_publication({"facility": "試験VC", "title": "図", "url": "https://x.example/b.pdf"}, env=env)
            self.assertEqual(un["status"], "PDF 未読")

    def test_latest_issue_uses_only_dated(self):
        rows = [{"title": "a", "published": "2023-10"}, {"title": "b", "published": "2025-04"}, {"title": "c", "published": None}, {"title": "d", "published": "秋号"}]
        self.assertEqual(PT.latest_issue(rows)["title"], "b")
        self.assertIsNone(PT.latest_issue([{"title": "c", "published": None}]))

    def test_dependency_is_pinned(self):
        self.assertRegex((ROOT / "requirements.txt").read_text(encoding="utf-8"), r"pdfminer\.six==\d+")


class Part1Survey(unittest.TestCase):
    OLD = ("env.go.jp/content/900509696.pdf", "env.go.jp/nature/ari_kata/shiryou/031010-7.pdf", "env.go.jp/nature/yasei/guide/pdf/VC.pdf")

    def test_old_material_is_not_in_the_ledger(self):
        raw = (ROOT / "ikimonobiyori" / "data" / "visitor_centers" / "centers.yaml").read_text(encoding="utf-8")
        for u in self.OLD:
            self.assertNotIn(u, raw)

    def test_new_centers_are_pending_and_checked(self):
        from ikimonobiyori import visitor_centers as VC
        rows = {c["id"]: c for c in VC.load_centers()}
        for i in ("urabandai-vc", "oze-fnd", "kamikochi-vc", "picchio", "tanigawa-ic"):
            self.assertEqual(rows[i]["approval"]["status"], "pending", i)
            self.assertEqual(rows[i]["checked_on"], "2026-11-07")
            self.assertNotIn("approved_by", rows[i]["approval"])


def card(**kw):
    base = {"title": "試験の紅葉は標高でずれる", "category": "季節の仕組み", "place": "試験山", "place_aliases": ["試験の森"], "facts": ["高いところから順に色づく", "見頃は約1か月続く"],
            "condition": {"months": [10, 11], "year_dependent": False}, "source": {"name": "試験VC", "title": "季刊誌", "url": "https://vc.example.org/a.pdf", "checked_on": "2026-11-07", "page": 2},
            "confidence": "施設の観察記録", "rights": "無断転載不可。事実のみ", "usage": "ガイドの目として1行"}
    base.update(kw)
    return base


class Part2Cards(unittest.TestCase):
    def setUp(self):
        from ikimonobiyori import knowledge as K
        self.K = K
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.tmp.name}

    def test_valid_card(self):
        self.assertEqual(self.K.validate(card()), [])

    def test_limits(self):
        self.assertTrue(self.K.validate(card(facts=["a"] * 6)))
        self.assertTrue(self.K.validate(card(facts=["あ" * 61])))
        self.assertTrue(self.K.validate(card(facts=["「原文の文です」"])))                 # 引用符で原文を残さない
        self.assertTrue(self.K.validate(card(facts=["文です。二つめの文です。三つめ。"])))   # 原文のような文
        self.assertTrue(self.K.validate(card(source={"name": "x"})))                        # 出典が必須
        self.assertTrue(self.K.validate(card(confidence=None)))
        self.assertTrue(self.K.validate(card(condition={"year_dependent": True})))          # 年に依存する事実には年
        self.assertEqual(self.K.validate(card(condition={"year_dependent": True, "year": 2023})), [])

    def test_add_search_and_store_outside_the_repository(self):
        self.K.add(card(), self.env)
        self.K.add(card(title="別のカード", category="安全", facts=["クマに注意する"], condition={"months": [6]}), self.env)
        self.assertEqual(len(self.K.load(self.env)), 2)
        self.assertEqual([r["title"] for r in self.K.search(self.env, category="安全")], ["別のカード"])
        self.assertEqual([r["title"] for r in self.K.search(self.env, month=11)], ["試験の紅葉は標高でずれる"])
        self.assertEqual(len(self.K.search(self.env, place="試験の森")), 2)
        self.assertIn(Path(self.tmp.name).resolve(), self.K.path(self.env).resolve().parents)
        with self.assertRaises(ValueError):
            self.K.add(card(facts=["あ" * 61]), self.env)

    def test_no_real_cards_in_the_repository(self):
        for f in (ROOT / "ikimonobiyori" / "data").rglob("*"):
            self.assertNotIn(f.name, ("cards.jsonl", "publications.jsonl"), str(f))


if __name__ == "__main__":
    unittest.main()
