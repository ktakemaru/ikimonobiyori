"""段階29 フェーズB: 野鳥の案内の HTML ページ。文は guide find --text と同じ・安全(エスケープ・CSP・data URI・リンク)。通信なし。"""
import html
import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide, guide_page
from test_stage23 import item, recs, build
from test_stage29 import JPEG, PNG

P = guide.load_policy()
NOW = datetime(2026, 10, 31, 9, 0, tzinfo=timezone(timedelta(hours=9)))
U1, U2, U3 = "https://rurubu.jp/andmore/spot/1", "https://www.walkerplus.com/article/1/", "https://www.city.example.lg.jp/kanko/a.html"
WINTER = {"text": "11月〜2月", "from": "11月", "to": "2月末"}
EVIL = '<script>alert("x")</script>'
KINDS = {U1: {"kinds": ["カワセミ", "ヤマセミ"]}, U2: {"kinds": ["カワセミ"]}}
META = {"name": "カワセミ", "image_type": "jpeg", "license": "CC BY", "attribution": "(c) 撮影者, some rights reserved (CC BY)",
        "photo_page": "https://www.inaturalist.org/photos/111"}


class TextNodes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text, self.tags = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        if data.strip():
            self.text.append(data)


def parse(page):
    p = TextNodes()
    p.feed(page)
    return p


def entries(*specs, theme="野鳥"):
    """specs: (名前, [url...], {url: 追加の項目})"""
    rows = []
    for name, urls, extra in specs:
        rows += recs(*[item(u, name=name, theme=theme, **(extra.get(u) or {})) for u in urls])
    return list(build(rows).values())


def parts_for(es, on=date(2026, 10, 30), themes=("野鳥",)):
    found = guide.find(es, themes=set(themes), on=on, policy=P)
    return found, guide.answer_parts(found, P, origin_line="出発地: 横浜", themes=set(themes))


def page_for(parts, found=None, photos=None, retired=frozenset()):
    return guide_page.build_page(parts, policy=P, now=NOW, kind_notes=(found or {}).get("kind_notes") or [],
                                 photo_for=lambda n: (photos or {}).get(n), retired_urls=retired)


class SameSentences(unittest.TestCase):
    def test_every_row_is_in_the_page_exactly_as_find_text_says(self):
        found = guide.find(guide.build()[0], themes={"野鳥", "冬鳥"}, on=date(2026, 10, 30), policy=P)
        parts = guide.answer_parts(found, P, origin_line="出発地: 横浜", themes={"野鳥", "冬鳥"})
        text = guide.render_answer(found, P, origin_line="出発地: 横浜", themes={"野鳥", "冬鳥"})
        nodes = parse(page_for(parts, found)).text
        rows = [r for sec in parts["sections"] for r in sec["rows"]]
        self.assertGreater(len(rows), 20)
        for r in rows:
            self.assertIn(r["line"] + "\n", text)                                    # 文字の答えの 1 行そのもの
            self.assertIn(r["body"], nodes)                                          # 本文は、そのままの文字列で出る
            self.assertIn(r["where"], nodes)
            head = f"{r['index']}. {r['name']}" if r["index"] else r["name"]
            self.assertIn(head, nodes)
            self.assertEqual(r["line"].split(" — ", 1)[1], r["body"])
        for w in (parts["origin_line"], parts["legend"], *parts["notes"]):
            self.assertIn(w, nodes)
        self.assertEqual(sum(1 for t in nodes if t == parts["legend"]), 1)           # 凡例は 1 回

    def test_sections_of_find_all_appear_with_their_headings(self):
        es = entries(("試験の沼", [U1, U2], KINDS), ("一件の池", [U1], {}))
        found, parts = parts_for(es, on=date(2026, 5, 1))
        nodes = parse(page_for(parts, found)).text
        self.assertIn(P["answer"]["headings"]["reference"], nodes)
        self.assertIn("一件の池", nodes)

    def test_unknown_season_and_out_of_range_sections_appear(self):
        es = entries(("冬鳥の池", [U1, U2], {}), theme="冬鳥")
        found = guide.find(es, themes={"冬鳥"}, on=date(2026, 10, 30), policy=P)
        far = {**es[0], "name": "遠い池", "range": {**es[0]["range"], "status": "out_of_range", "km": 300}}
        found["out_of_range"] = [far]
        parts = guide.answer_parts(found, P, origin_line="出発地: 横浜", themes={"冬鳥"}, show_out_of_range=True)
        nodes = parse(page_for(parts, found)).text
        self.assertIn(P["answer"]["headings"]["no_season"], nodes)
        self.assertIn(P["answer"]["headings"]["out_of_range"], nodes)
        self.assertIn("遠い池", nodes)

    def test_numbers_in_the_page_come_from_the_answer(self):
        found = guide.find(guide.build()[0], themes={"野鳥", "冬鳥"}, on=date(2026, 10, 30), policy=P)
        parts = guide.answer_parts(found, P, origin_line="出発地: 横浜", themes={"野鳥", "冬鳥"})
        answer = guide.render_answer(found, P, origin_line="出発地: 横浜", themes={"野鳥", "冬鳥"})
        for n in re.findall(r"約\d+ km|参照数 \d+", " ".join(parse(page_for(parts, found)).text)):
            self.assertIn(n, answer)


class Photos(unittest.TestCase):
    def setUp(self):
        self.es = entries(("試験の沼", [U1, U2], KINDS))
        self.found, self.parts = parts_for(self.es)

    def test_species_card_without_photo_says_so_and_never_borrows_another_image(self):
        page = page_for(self.parts, self.found)
        self.assertIn(P["photos"]["html"]["no_photo"], parse(page).text)
        self.assertEqual([t for t in parse(page).tags if t[0] == "img"], [])
        self.assertIn("カワセミ", parse(page).text)

    def test_photo_is_embedded_as_data_uri_with_credit_and_license_and_link(self):
        page = page_for(self.parts, self.found, photos={"カワセミ": (META, JPEG)})
        imgs = [a for t, a in parse(page).tags if t == "img"]
        self.assertTrue(imgs)
        for a in imgs:
            self.assertTrue(a["src"].startswith("data:image/jpeg;base64,"), a["src"][:30])
        text = " ".join(parse(page).text)
        self.assertIn("(c) 撮影者, some rights reserved (CC BY)", text)
        self.assertIn("CC BY", text)
        self.assertIn(P["photos"]["html"]["photo_note"], text)
        self.assertIn(P["photos"]["html"]["credit"], text)
        hrefs = [a["href"] for t, a in parse(page).tags if t == "a"]
        self.assertIn("https://www.inaturalist.org/photos/111", hrefs)

    def test_only_species_that_have_photos_get_credits(self):
        page = page_for(self.parts, self.found, photos={"カワセミ": (META, JPEG)})
        self.assertEqual(len([t for t in parse(page).text if t.startswith("カワセミ: 撮影者")]), 1)
        self.assertFalse([t for t in parse(page).text if t.startswith("ヤマセミ: 撮影者")])

    def test_png_uses_its_mime_type(self):
        page = page_for(self.parts, self.found, photos={"カワセミ": ({**META, "image_type": "png"}, PNG)})
        self.assertIn("data:image/png;base64,", page)


class Safety(unittest.TestCase):
    def evil_page(self):
        es = entries((EVIL, [U1, U2], {U1: {"kinds": [EVIL, "カワセミ"]}, U2: {"kinds": [EVIL, "カワセミ"]}}))
        for e in es:
            e["sources"] = [{"url": "javascript:alert(1)", "publisher": EVIL, "host": "x"},
                            {"url": 'https://ok.example.org/a"onmouseover="x', "publisher": "p", "host": "ok.example.org"},
                            {"url": "https://ok.example.org/fine", "publisher": "<img src=x onerror=alert(1)>", "host": "ok.example.org"},
                            {"url": "data:text/html,<script>1</script>", "publisher": "d", "host": "d"}]
        found, parts = parts_for(es)
        meta = {**META, "attribution": EVIL, "photo_page": "javascript:alert(2)"}
        return page_for(parts, found, photos={"カワセミ": (meta, JPEG)})

    def test_script_in_data_is_shown_as_text_not_run(self):
        page = self.evil_page()
        self.assertNotIn("<script", page.lower())
        self.assertNotIn("<img src=x", page.lower())
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", page)
        self.assertIn(EVIL, " ".join(parse(page).text))                               # 文字として表示される
        self.assertFalse([t for t, a in parse(page).tags if t == "script"])
        for t, a in parse(page).tags:
            self.assertFalse([k for k in a if k.startswith("on")], (t, a))

    def test_no_javascript_and_csp_meta_present(self):
        page = self.evil_page()
        metas = [a for t, a in parse(page).tags if t == "meta" and a.get("http-equiv") == "Content-Security-Policy"]
        self.assertEqual([m["content"] for m in metas], ["default-src 'none'; img-src data:; style-src 'unsafe-inline'"])

    def test_images_are_only_data_uris(self):
        page = self.evil_page()
        imgs = [a for t, a in parse(page).tags if t == "img"]
        self.assertTrue(imgs)
        self.assertTrue(all(a["src"].startswith("data:") for a in imgs))
        self.assertNotRegex(page, r'<img[^>]+src="https?:')
        self.assertNotRegex(page, r"url\(")

    def test_links_are_http_https_only_with_noopener(self):
        page = self.evil_page()
        links = [a for t, a in parse(page).tags if t == "a"]
        self.assertTrue(links)
        for a in links:
            self.assertRegex(a["href"], r"^https?://")
            self.assertEqual(a["rel"], "noopener noreferrer")
        self.assertNotIn("javascript:", page)
        self.assertNotIn('onmouseover="x', page)

    def test_retired_source_links_are_not_shown(self):
        es = entries(("試験の沼", [U1, U2, U3], KINDS))
        found, parts = parts_for(es)
        hrefs = [a["href"] for t, a in parse(page_for(parts, found, retired={U1})).tags if t == "a"]
        self.assertNotIn(U1, hrefs)
        self.assertIn(U2, hrefs)
        self.assertIn(U3, hrefs)

    def test_mobile_and_print_css_and_text_badges(self):
        found, parts = parts_for(entries(("試験の沼", [U1, U2], KINDS)))
        page = page_for(parts, found)
        self.assertIn("@media (max-width", page)
        self.assertIn("@media print", page)
        self.assertIn('name="viewport"', page)
        self.assertIn(P["answer"]["headings"]["recommend"], parse(page).text)          # 時期のバッジは文字でも示す(色だけに頼らない)


class Command(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"IKIMONOBIYORI_DATA_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = guide.main(argv)
        return rc, out.getvalue().strip(), err.getvalue()

    def test_writes_under_the_data_dir_and_prints_the_absolute_path_on_one_line(self):
        rc, out, _ = self.run_main(["page", "--theme", "野鳥", "--from", "横浜", "--date", "2026-10-30"])
        self.assertEqual(rc, 0)
        p = Path(out)
        self.assertTrue(p.is_absolute() and p.is_file())
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIn(Path(self.tmp.name).resolve(), p.resolve().parents)
        page = p.read_text(encoding="utf-8")
        self.assertIn("<title>野鳥の案内</title>", page)
        self.assertIn("出発地: 横浜", page)

    def test_the_page_has_the_same_places_as_find_text(self):
        _, out, _ = self.run_main(["page", "--date", "2026-10-30"])
        names = {html.unescape(n) for n in re.findall(r"<h3>(?:\d+\. )?(.+?)</h3>", Path(out).read_text(encoding="utf-8"))}
        found = guide.find(guide.build()[0], themes={"野鳥", "冬鳥"}, on=date(2026, 10, 30), policy=P)
        expected = {r["name"] for sec in guide.answer_parts(found, P)["sections"] for r in sec["rows"]}
        self.assertTrue(expected <= names)

    def test_from_tokyo_changes_the_origin_line(self):
        _, out, _ = self.run_main(["page", "--from", "東京", "--date", "2026-10-30"])
        self.assertIn("出発地: 東京", Path(out).read_text(encoding="utf-8"))

    def test_refuses_to_write_into_the_repository(self):
        target = H.ROOT / "docs" / "oops.html"
        rc, _, _ = self.run_main(["page", "--out", str(target)])
        self.assertEqual(rc, 2)
        self.assertFalse(target.exists())

    def test_allows_a_path_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as d2:
            rc, _, _ = self.run_main(["page", "--out", str(Path(d2) / "x" / "a.html")])
            self.assertEqual(rc, 0)
            self.assertTrue((Path(d2) / "x" / "a.html").is_file())

    def test_unknown_word_is_not_guessed(self):
        rc, _, _ = self.run_main(["page", "--theme", "ありえない言葉"])
        self.assertEqual(rc, 1)

    def test_page_command_makes_no_requests(self):
        with mock.patch("socket.socket", side_effect=AssertionError("通信しない")):
            rc, _, _ = self.run_main(["page", "--date", "2026-10-30"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
