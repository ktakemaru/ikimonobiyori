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


if __name__ == "__main__":
    unittest.main()
