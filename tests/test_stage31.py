"""段階31: 案内ページの見せ方(鳥のグループ・名所のカードの行・写真の位置・出どころの折りたたみ・作成日時)と、冬羽の写真を探す Commons の検索。通信なし。固定の応答だけ。"""
import json
import re
import unittest
from datetime import date, datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import guide, guide_page
from ikimonobiyori.fetch import ParseError, commons_photos as C

import test_stage29 as T29
import test_stage29_page as TP
import test_stage30 as T30

P = guide.load_policy()
PH = P["photos"]
H_ = PH["html"]
CM = PH["commons"]
JST = timezone(timedelta(hours=9))


def note(name, start=None, end=None, shown=True, year_round=False):
    se = {"text": f"{name}の時期", "independent_sources": 2, "shown": shown}
    if start:
        se["window"] = {"start": start, "end": end}
    if year_round:
        se["year_round"] = True
    return {"scope": "kind", "theme": "野鳥", "name": name, "kinds": [name], "season": se}


def meta(**kw):
    return {**TP.META, **kw}


def strip_hidden(page):
    """表示されない本文(hidden)・style を除いた HTML。画面に出る文字だけを調べるため。"""
    page = re.sub(r'<p class="body" hidden>.*?</p>', "", page, flags=re.S)
    return re.sub(r"<style>.*?</style>", "", page, flags=re.S)


def visible(page):
    return " ".join(TP.parse(strip_hidden(page)).text)


NAMES = ["カワセミ", "ヤマセミ", "アオバズク", "ジョウビタキ"]


class BirdGroups(unittest.TestCase):
    def setUp(self):
        self.es = TP.entries(("試験の沼", [TP.U1, TP.U2], {u: {"kinds": NAMES} for u in (TP.U1, TP.U2)}))
        self.found, self.parts = TP.parts_for(self.es)

    def page(self, notes, now=TP.NOW, photos=True):
        return guide_page.build_page(self.parts, policy=P, now=now, kind_notes=notes,
                                     photo_for=(lambda n: (meta(name=n), T29.JPEG)) if photos else (lambda n: None))

    def sections(self, page):
        """見出し → その欄のカードの和名の並び(鳥の欄だけ)。"""
        out = {}
        for h, body in re.findall(r"<h2>(.*?)</h2>(.*?)(?=<h2>|$)", page, flags=re.S):
            out[h] = re.findall(r'<li class="card">.*?<h3>(.*?)</h3>', body, flags=re.S)
        return out

    def test_three_groups_now_out_and_unknown(self):
        notes = [note("ジョウビタキ", "10-21", "10-31"), note("ヤマセミ", "12-01", "02-29"), note("アオバズク", "05-01", "08-31", shown=False)]
        sec = self.sections(self.page(notes))                                      # 作成日は 10 月
        self.assertEqual(sec[H_["headings"]["birds"]], ["ジョウビタキ"])
        self.assertEqual(sec[H_["headings"]["birds_out"]], ["ヤマセミ"])
        self.assertEqual(sorted(sec[H_["headings"]["birds_unknown"]]), ["アオバズク", "カワセミ"])     # 出どころ 1 件(shown でない)・説明なし → 未確認

    def test_year_round_and_year_crossing_windows_match_the_month(self):
        notes = [note("カワセミ", year_round=True), note("ヤマセミ", "12-01", "02-29")]
        jan = datetime(2027, 1, 15, 9, 0, tzinfo=JST)
        sec = self.sections(self.page(notes, now=jan))
        self.assertEqual(sorted(sec[H_["headings"]["birds"]]), ["カワセミ", "ヤマセミ"])

    def test_the_heading_for_now_is_not_shown_when_nothing_matches(self):
        notes = [note("ヤマセミ", "12-01", "02-29")]
        page = self.page(notes)
        sec = self.sections(page)
        self.assertNotIn(H_["headings"]["birds"], sec)
        self.assertIn(H_["headings"]["birds_out"], sec)
        self.assertNotIn(f"<h2>{H_['headings']['birds']}</h2>", page)

    def test_no_group_at_all_without_species(self):
        es = TP.entries(("一件の池", [TP.U1], {}))
        found, parts = TP.parts_for(es)
        page = guide_page.build_page(parts, policy=P, now=TP.NOW, kind_notes=[], photo_for=lambda n: None)
        for k in ("birds", "birds_out", "birds_unknown"):
            self.assertNotIn(f"<h2>{H_['headings'][k]}</h2>", page)

    def test_unknown_season_cards_have_no_season_line_but_one_note_under_the_heading(self):
        page = self.page([note("ジョウビタキ", "10-21", "10-31")])
        unknown = re.search(r"<h2>%s</h2>(.*?)(?=<h2>)" % re.escape(H_["headings"]["birds_unknown"]), page, flags=re.S).group(1)
        self.assertEqual(unknown.count(H_["birds_unknown_note"]), 1)
        self.assertNotIn("確かめられていない", unknown.replace(H_["birds_unknown_note"], ""))
        self.assertNotIn("時期:", unknown)
        known = re.search(r"<h2>%s</h2>(.*?)(?=<h2>)" % re.escape(H_["headings"]["birds"]), page, flags=re.S).group(1)
        self.assertIn("時期: ジョウビタキの時期", known)

    def test_confirmed_seasons_come_first_inside_a_group_and_the_rest_keep_their_order(self):
        names = ["ホ", "ロ", "ハ", "ニ"]
        es = TP.entries(("試験の沼", [TP.U1, TP.U2], {u: {"kinds": names} for u in (TP.U1, TP.U2)}))
        found, parts = TP.parts_for(es)
        order = guide_page.species_in(parts)
        page = guide_page.build_page(parts, policy=P, now=TP.NOW, kind_notes=[note("ニ", "10-01", "10-31")], photo_for=lambda n: None)
        sec = self.sections(page)
        self.assertEqual(sec[H_["headings"]["birds"]], ["ニ"])
        self.assertEqual(sec[H_["headings"]["birds_unknown"]], [n for n in order if n != "ニ"])

    def test_sort_puts_confirmed_before_unknown_within_one_group(self):
        notes = {"a": note("a", "10-01", "10-31"), "b": None}
        self.assertEqual(guide_page.season_state(notes["a"], 10), "now")
        self.assertEqual(guide_page.season_state(notes["b"], 10), "unknown")
        self.assertEqual(guide_page.season_state(note("x", "12-01", "02-29"), 6), "out")
        self.assertEqual(guide_page.season_state(note("x", "12-01", "02-29", shown=False), 12), "unknown")
        self.assertEqual(guide_page.season_state(note("x", shown=True), 12), "unknown")          # 時期の範囲が読めない → 未確認


class PlaceCard(unittest.TestCase):
    def setUp(self):
        self.es = TP.entries(("試験の沼", [TP.U1, TP.U2], TP.KINDS))
        self.found, self.parts = TP.parts_for(self.es)
        self.page = guide_page.build_page(self.parts, policy=P, now=TP.NOW, kind_notes=self.found.get("kind_notes") or [],
                                          photo_for=lambda n: (meta(name=n), T29.JPEG))
        i = self.page.index('<li class="card"><h3>1. 試験の沼</h3>')
        j = self.page.find('<li class="card">', i + 1)
        self.card = self.page[i:j if j != -1 else self.page.index("<h2>", i)]

    def test_rows_are_items_not_one_sentence(self):
        facts = re.findall(r"<li>(.*?)</li>", re.search(r'<ul class="facts">(.*?)</ul>', self.card, flags=re.S).group(1))
        self.assertEqual(len(facts), 3)
        self.assertTrue(facts[0].startswith("例年の時期: "))
        self.assertEqual(facts[1], "見られる鳥: カワセミ")
        self.assertRegex(facts[2], r"^横浜から約\d+ km・参照数 2$")
        self.assertIn('<p class="faint">出どころの区分: ', self.card)
        self.assertLess(self.card.index('class="facts"'), self.card.index('class="faint"'))      # 区分は最後の行

    def test_tier_word_and_reference_comma_are_not_visible_but_badge_is(self):
        text = visible(self.page)
        for w in ("定評", "参考、"):
            self.assertNotIn(w, text)
        self.assertIn(P["answer"]["headings"]["recommend"], TP.parse(strip_hidden(self.page)).text)      # バッジ(おすすめ)は出る

    def test_reference_card_has_no_tier_word_either(self):
        es = TP.entries(("一件の池", [TP.U1], {}))
        found, parts = TP.parts_for(es, on=date(2026, 5, 1))
        page = guide_page.build_page(parts, policy=P, now=TP.NOW, kind_notes=[], photo_for=lambda n: None)
        self.assertNotIn("参考、", visible(page))
        self.assertIn("一件の池", visible(page))

    def test_there_is_no_hidden_paragraph_with_the_whole_sentence(self):
        row = self.parts["sections"][0]["rows"][0]
        self.assertNotIn("hidden", self.page)
        self.assertNotIn(row["body"], self.page)                                   # 1 文のまま載せない(項目ごとの行だけ)

    def test_photos_are_at_the_top_under_the_heading_and_larger_than_before(self):
        self.assertLess(self.card.index("<h3>"), self.card.index('class="thumbs"'))
        self.assertLess(self.card.index('class="thumbs"'), self.card.index('class="facts"'))
        css = re.search(r"\.thumbs figure \{([^}]*)\}", guide_page.CSS).group(1)
        self.assertGreaterEqual(float(re.search(r"width: ([\d.]+)rem", css).group(1)), 9)          # 以前は 4.5rem

    def test_names_do_not_wrap_in_the_middle_of_a_word(self):
        css = re.search(r"figcaption \.name \{([^}]*)\}", guide_page.CSS).group(1)
        self.assertIn("white-space: nowrap", css)
        self.assertIn("word-break: keep-all", css)
        self.assertIn('<span class="name">カワセミ</span>', self.card)

    def test_each_photo_has_a_small_credit_with_author_and_licence_same_as_the_list(self):
        m = meta(name="カワセミ", attribution="(c) 撮影者, some rights reserved (CC BY)", license="CC BY")
        page = guide_page.build_page(self.parts, policy=P, now=TP.NOW, kind_notes=self.found.get("kind_notes") or [],
                                     photo_for=lambda n: (m, T29.JPEG) if n == "カワセミ" else None)
        self.assertIn('<span class="credit">写真: 撮影者・CC BY</span>', page)
        lst = re.search(r'<details class="credits">.*?</details>', page, flags=re.S).group(0)
        self.assertIn("ライセンス CC BY", lst)                                      # 一覧と同じ表記
        self.assertIn("(c) 撮影者, some rights reserved (CC BY)", lst)              # 一覧は表記そのまま

    def test_non_standard_attribution_is_shown_as_is_and_escaped(self):
        m = meta(name="カワセミ", attribution="<script>alert(1)</script> & Co.", license="CC BY-SA 3.0")
        page = guide_page.build_page(self.parts, policy=P, now=TP.NOW, kind_notes=[], photo_for=lambda n: (m, T29.JPEG) if n == "カワセミ" else None)
        self.assertNotIn("<script>alert", page)
        self.assertIn("写真: &lt;script&gt;alert(1)&lt;/script&gt; &amp; Co.・CC BY-SA 3.0", page)

    def test_short_author_of_inaturalist_boilerplate(self):
        for raw, short in (("(c) caroline legg, some rights reserved (CC BY)", "caroline legg"),
                           ("(c) Kim, Hyun-tae, some rights reserved (CC BY), uploaded by Kim, Hyun-tae", "Kim, Hyun-tae"),
                           ("no rights reserved, uploaded by Andy Wilson", "Andy Wilson"),
                           ("(c) Foo Bar, no rights reserved (CC0)", "Foo Bar"),
                           ("Diliff", "Diliff"), ("U.S. Fish and Wildlife Service", "U.S. Fish and Wildlife Service")):
            self.assertEqual(guide_page.short_author({"attribution": raw}, P), short)


class Links(unittest.TestCase):
    def entry(self, labels):
        return {"sources": [{"url": f"https://example.org/{i}", "publisher": lab} for i, lab in enumerate(labels)]}

    def test_duplicates_get_numbers_and_unique_names_do_not(self):
        out = guide_page.source_links_numbered(self.entry(["東京都", "るるぶ", "東京都", "東京都"]), set(), P)
        self.assertEqual([lab for _, lab in out], ["東京都(1)", "るるぶ", "東京都(2)", "東京都(3)"])

    def build(self, labels):
        es = TP.entries(("試験の沼", [TP.U1, TP.U2], TP.KINDS))
        found, parts = TP.parts_for(es)
        parts["sections"][0]["rows"][0]["entry"] = {**parts["sections"][0]["rows"][0]["entry"], **self.entry(labels)}
        return guide_page.build_page(parts, policy=P, now=TP.NOW, kind_notes=[], photo_for=lambda n: None)

    def test_first_three_are_shown_and_the_rest_are_in_a_details_without_script(self):
        page = self.build(["東京都", "るるぶ", "東京都", "BE-PAL", "東京都"])
        card = page[page.index("<h3>1. 試験の沼"):]
        visible_part, more = card.split('<details class="more">', 1)
        self.assertEqual(visible_part.count("<a href"), 3)
        self.assertIn(f"<summary>{H_['links_more'].format(n=2)}</summary>", more)         # 残りの件数
        self.assertEqual(more.split("</details>")[0].count("<a href"), 2)
        self.assertNotIn(" open", more.split(">", 1)[0])
        self.assertNotIn("<script", page)

    def test_three_or_fewer_have_no_details(self):
        page = self.build(["a", "b", "c"])
        self.assertNotIn('<details class="more">', page)
        self.assertEqual(self.build(["a"]).count("<a href"), 1 + page.count("<a href") - 3)

    def test_numbers_are_over_all_links_of_the_card_so_the_hidden_ones_do_not_repeat_names(self):
        page = self.build(["東京都"] * 5)
        for i in range(1, 6):
            self.assertIn(f">東京都({i})</a>", page)

    def test_unsafe_urls_stay_unlinked_in_both_parts(self):
        out = guide_page.source_links_numbered({"sources": [{"url": "javascript:alert(1)", "publisher": "x"}, {"url": "https://a.example.org/", "publisher": "y"}]}, set(), P)
        self.assertEqual(out, [("https://a.example.org/", "y")])


class WholePage(unittest.TestCase):
    def setUp(self):
        self.found = guide.find(guide.build()[0], themes={"野鳥", "冬鳥"}, on=date(2026, 10, 30), policy=P)
        self.parts = guide.answer_parts(self.found, P, origin_line="出発地: 横浜", themes={"野鳥", "冬鳥"})
        self.text = guide.render_answer(self.found, P, origin_line="出発地: 横浜", themes={"野鳥", "冬鳥"})
        self.page = guide_page.build_page(self.parts, policy=P, now=TP.NOW, kind_notes=self.found.get("kind_notes") or [],
                                          photo_for=lambda n: (meta(name=n), T29.JPEG))

    def test_created_text_is_japanese_date_and_time(self):
        self.assertIn("作成: 2026年10月31日 9:00", self.page)
        at = datetime(2026, 10, 31, 6, 19, tzinfo=JST)
        self.assertEqual(guide_page.created_text(at, H_), "作成: 2026年10月31日 6:19")
        self.assertEqual(guide_page.created_text(datetime(2027, 1, 2, 14, 5, tzinfo=JST), H_), "作成: 2027年1月2日 14:05")
        self.assertNotIn("T09:00", self.page)

    def test_photo_credits_list_is_a_closed_details(self):
        m = re.search(r'<details class="credits">(.*?)</details>', self.page, flags=re.S)
        self.assertIsNotNone(m)
        self.assertNotRegex(self.page, r'<details[^>]*\bopen\b')
        self.assertIn(H_["credits_summary"], m.group(1))
        self.assertIn(H_["photo_note"], self.page)

    def test_photos_appear_in_every_section_where_a_confirmed_species_has_one(self):
        cards = {}
        for h, body in re.findall(r"<h2>(.*?)</h2>(.*?)(?=<h2>|$)", self.page, flags=re.S):
            h = P["answer"]["headings"]["recommend"] if h == H_["headings"]["places"] else h              # おすすめの欄の見出しは「おすすめの名所」
            for c in re.split(r'<li class="card">', body)[1:]:
                m = re.match(r"<h3>(?:\d+\. )?(.*?)</h3>", c)
                if m:
                    cards[(h, m.group(1))] = c
        seen_sections = set()
        for sec in self.parts["sections"]:
            for r in sec["rows"]:
                card = cards[(sec["heading"], r["name"])]
                for k in r["entry"]["kinds"]:
                    alt = f'alt="{k["kind"]}"'
                    if k["shown"]:
                        self.assertIn(alt, card, (sec["heading"], r["name"], k["kind"]))
                        seen_sections.add(sec["key"])
                    else:
                        self.assertNotIn(alt, card)                                  # 確認できていない種の写真は出さない
        self.assertIn("no_season", seen_sections)                                    # 「時期を確かめられていない」の欄にも出る

    def test_no_external_image_url_no_lazy_loading_no_script(self):
        srcs = re.findall(r'<img [^>]*src="([^"]*)"', self.page)
        self.assertGreater(len(srcs), 10)
        self.assertTrue(all(s.startswith("data:image/") for s in srcs))
        self.assertNotIn("loading=", self.page)
        self.assertNotIn("<script", self.page)
        self.assertIn("default-src &#x27;none&#x27;; img-src data:", self.page)

    def test_every_visible_fact_is_in_the_find_text_line_of_the_same_place(self):
        n_rows = 0
        for sec in self.parts["sections"]:
            for r in sec["rows"]:
                n_rows += 1
                f, line = r["fields"], r["line"]
                if f["season"]:
                    self.assertIn(P["answer"]["bits"]["season"].format(text=f["season"]), line)
                for k in f["kinds"]:
                    self.assertIn(k, line)
                if f["classes"]:
                    self.assertIn(f["classes"], line)
                if f["distance"]:
                    self.assertIn(f"約{f['distance']['km']} km", line)
                if f["n"] is not None:
                    self.assertIn(P["reference_count"]["suffix"].format(n=f["n"]), line)
        self.assertGreater(n_rows, 20)
        text = visible(self.page)
        for n in re.findall(r"約\d+ km|参照数 \d+", text):
            self.assertIn(n, self.text)

    def test_find_text_is_unchanged_by_the_new_fields(self):
        for sec in self.parts["sections"]:
            for r in sec["rows"]:
                self.assertIn(r["line"] + "\n", self.text)
                self.assertEqual(r["line"].split(" — ", 1)[1], r["body"])


class FactCheckCatchesMistakes(unittest.TestCase):
    """test_stage29_page の「項目ごとの事実が find --text の 1 行と食い違わない」確認が、事実の欠け・数や名前の違いで落ちること(反例)。"""

    def setUp(self):
        self.found = guide.find(guide.build()[0], themes={"野鳥", "冬鳥"}, on=date(2026, 10, 30), policy=P)
        self.parts = guide.answer_parts(self.found, P, origin_line="出発地: 横浜", themes={"野鳥", "冬鳥"})
        self.page = guide_page.build_page(self.parts, policy=P, now=TP.NOW, kind_notes=self.found.get("kind_notes") or [], photo_for=lambda n: None)

    def mismatches(self, page):
        return TP.fact_mismatches(page, self.parts, P)

    def mutate(self, pattern, repl, count=1):
        """ページの HTML を 1 か所だけ書き換える(その書き換えが実際に起きたことも確かめる)。"""
        new, n = re.subn(pattern, repl, self.page, count=count)
        self.assertEqual(n, count, pattern)
        self.assertNotEqual(new, self.page)
        return new

    def test_the_real_page_passes(self):
        self.assertEqual(self.mismatches(self.page), [])

    def test_the_real_page_has_every_kind_of_fact_so_the_check_is_not_vacuous(self):
        kinds = {k: 0 for k in ("season", "kinds", "classes", "origin", "km", "n")}                # 範囲の端は、この日の実データにはない(下の別のテストで作る)
        for _, row, card in TP.page_cards(self.page, self.parts):
            for k, v in TP.card_facts(card, P).items():
                if k in kinds:
                    kinds[k] += bool(v)
        self.assertTrue(all(kinds.values()), kinds)                                  # どの項目も実データに出てくる

    def test_a_missing_fact_fails_for_each_kind_of_fact(self):
        cases = {
            "時期": r'<li>例年の時期: [^<]*</li>',
            "種類": r'<li>見られる鳥: [^<]*</li>',
            "距離と参照数": r'<li>[^<]*から約\d+ km[^<]*・参照数 \d+</li>',
            "出どころの区分": r'<p class="faint">[^<]*</p>',
        }
        for name, pat in cases.items():
            bad = self.mismatches(self.mutate(pat, ""))
            self.assertEqual(len({b[0] for b in bad}), 1, name)                      # 1 枚のカードの項目が欠けると、そのカードが食い違いになる
            self.assertTrue(all(len(b) == 4 for b in bad), name)

    def test_a_changed_number_or_name_fails(self):
        cases = {
            "距離": (r"から約(\d+) km", lambda m: f"から約{int(m.group(1)) + 1} km"),
            "参照数": (r"参照数 (\d+)</li>", lambda m: f"参照数 {int(m.group(1)) + 1}</li>"),
            "出発地": (r"<li>横浜から約", lambda m: "<li>東京から約"),
            "時期": (r"<li>例年の時期: ", lambda m: "<li>例年の時期: 偽の"),
            "種類の名前": (r"<li>見られる鳥: ", lambda m: "<li>見られる鳥: 偽の鳥・"),
            "区分": (r'<p class="faint">出どころの区分: ', lambda m: '<p class="faint">出どころの区分: 偽の'),
        }
        for name, (pat, repl) in cases.items():
            bad = self.mismatches(self.mutate(pat, repl))
            self.assertEqual(len({b[0] for b in bad}), 1, name)

    def test_an_extra_fact_fails_too(self):
        # 種類の行が 1 つも出ていない名所に、見られる鳥の行を足す
        row = next(r for sec in self.parts["sections"] for r in sec["rows"] if not r["fields"]["kinds"])
        title = f'{row["index"]}. {row["name"]}' if row["index"] else row["name"]
        page = self.page.replace(f"<h3>{title}</h3>", f"<h3>{title}</h3>", 1)
        i = page.index(f"<h3>{title}</h3>")
        j = page.index('<ul class="facts">', i) + len('<ul class="facts">')
        page = page[:j] + "<li>見られる鳥: 余分な鳥</li>" + page[j:]
        bad = self.mismatches(page)
        self.assertEqual([b[1] for b in bad], ["kinds"])

    def edge_page(self):
        """範囲の端(240〜250 km)の名所がある答えとページを作る。→ (parts, page)。"""
        es = TP.entries(("試験の沼", [TP.U1, TP.U2], TP.KINDS))
        found, _ = TP.parts_for(es)
        found["recommend"][0] = {**found["recommend"][0], "distance": {"origin": "横浜", "km": 245, "status": "edge"}}
        parts = guide.answer_parts(found, P, origin_line="出発地: 横浜", themes={"野鳥"})
        page = guide_page.build_page(parts, policy=P, now=TP.NOW, kind_notes=[], photo_for=lambda n: None)
        return parts, page

    def test_a_range_edge_mark_that_is_missing_or_extra_fails(self):
        parts, page = self.edge_page()
        self.assertIn("範囲の端", parts["sections"][0]["rows"][0]["line"])
        self.assertEqual(TP.fact_mismatches(page, parts, P), [])
        self.assertTrue(TP.line_facts(parts["sections"][0]["rows"][0]["line"], P)["edge"])
        missing = page.replace(P["photos"]["html"]["row_edge"], "", 1)
        self.assertEqual([b[2:] for b in TP.fact_mismatches(missing, parts, P)], [(True, False)])      # 欠けた
        row = parts["sections"][0]["rows"][0]
        plain = {**parts, "sections": [{**parts["sections"][0], "rows": [{**row, "line": row["line"].replace("、範囲の端", "")}]}]}
        self.assertEqual([b[2:] for b in TP.fact_mismatches(page, plain, P)], [(False, True)])         # 余分

    def test_a_card_that_does_not_match_its_row_in_title_or_count_fails(self):
        with self.assertRaises(AssertionError):
            TP.page_cards(self.page.replace("<h3>1. ", "<h3>9. ", 1), self.parts)
        head = f"<h2>{P['photos']['html']['headings']['places']}</h2>"
        i = self.page.index('<li class="card">', self.page.index(head))
        with self.assertRaises(AssertionError):                                      # 名所のカードが 1 枚足りない
            TP.page_cards(self.page[:i] + self.page[i:].replace('<li class="card">', "<li>", 1), self.parts)

    def test_a_line_of_find_text_that_cannot_be_read_is_not_overlooked(self):
        self.assertIsNone(TP.line_facts("名前(所在) — 読めない文", P))
        bad = TP.fact_mismatches(self.page, {**self.parts, "sections": [{**self.parts["sections"][0], "rows": [
            {**self.parts["sections"][0]["rows"][0], "line": "名前(所在) — 読めない文"}] + self.parts["sections"][0]["rows"][1:]}]}, P)
        self.assertTrue(bad)


class SeasonSearch(unittest.TestCase):
    SCI = "Chroicocephalus ridibundus"
    ROW = {"name": "ユリカモメ", "scientific": SCI, "taxon_id": 144510, "checked_on": "2026-10-31"}

    def page_doc(self, title, lic="CC BY 2.0", artist="Diliff", cats="", desc="", thumb=T30.THUMB, page=T30.PAGE, mime="image/jpeg"):
        em = {"LicenseShortName": {"value": lic}, "Artist": {"value": artist}, "Restrictions": {"value": ""},
              "Categories": {"value": cats}, "ImageDescription": {"value": desc}}
        return {"title": title, "imageinfo": [{"descriptionurl": page, "thumburl": thumb, "mime": mime, "extmetadata": em}]}

    def pages(self, *docs):
        return C.parse_imageinfo_pages({"query": {"pages": list(docs)}})

    def test_pick_needs_licence_scientific_name_and_a_season_word(self):
        docs = [self.page_doc("File:a.jpg", lic="CC BY-NC 2.0", cats=f"{self.SCI} winter"),          # NC
                self.page_doc("File:b.jpg", cats="Some other bird winter"),                         # 学名なし
                self.page_doc("File:c.jpg", cats=self.SCI),                                          # 季節の語なし
                self.page_doc("File:d.jpg", cats=f"{self.SCI} in winter plumage"),                    # これ
                self.page_doc("File:e.jpg", cats=f"{self.SCI} winter")]
        pick, seen = C.seasonal_pick(self.pages(*docs), self.ROW, CM, [d["title"] for d in docs])
        self.assertEqual((pick["title"], pick["term"]), ("File:d.jpg", "winter"))
        self.assertEqual(len(seen), 3)

    def test_season_word_can_come_from_the_file_name_or_description(self):
        for kw in ({"title": f"File:{self.SCI} non-breeding.jpg"}, {"title": "File:x.jpg", "desc": f"{self.SCI}, Winter plumage"}):
            kw.setdefault("title", "File:x.jpg")
            d = self.page_doc(**kw)
            pick, _ = C.seasonal_pick(self.pages(d), self.ROW, CM, [d["title"]])
            self.assertIsNotNone(pick, kw)

    def test_order_of_the_search_is_kept(self):
        a, b = (self.page_doc(f"File:{x}.jpg", cats=f"{self.SCI} winter") for x in "ab")
        pick, _ = C.seasonal_pick(self.pages(a, b), self.ROW, CM, ["File:b.jpg", "File:a.jpg"])
        self.assertEqual(pick["title"], "File:b.jpg")

    def test_author_too_long_is_not_cut_but_not_used(self):
        long = "own work " * 40
        ok, why = C.usable(C.parse_imageinfo({"query": {"pages": [self.page_doc("File:x.jpg", artist=long)]}}), CM)
        self.assertIsNone(ok)
        self.assertIn("長すぎる", why)

    def search_doc(self, *titles):
        return json.dumps({"query": {"search": [{"ns": 6, "title": t} for t in titles]}})

    def responses(self, titles=("File:d.jpg",), lic="CC BY 2.0"):
        docs = [self.page_doc(t, lic=lic, cats=f"{self.SCI} winter") for t in titles]
        return {"list=search": (200, self.search_doc(*titles)), "prop=imageinfo": (200, json.dumps({"query": {"pages": docs}}))}

    def run_fetch(self, responses, image=T29.JPEG, max_requests=10, wait_first=False):
        g, calls, saved, waits = T29.getter(responses), [], [], []

        def http_bytes(url, max_bytes):
            calls.append(url)
            return 200, image, {}
        out = C.fetch_commons_season(self.ROW, http_get=g, http_bytes=http_bytes, ph=PH, max_requests=max_requests, today=date(2026, 10, 31),
                                     sleep=waits.append, on_got=saved.append, wait_first=wait_first)
        return out, g, calls, waits, saved

    def test_three_requests_one_search_one_batched_imageinfo_one_image(self):
        (got, unused, rep), g, calls, waits, saved = self.run_fetch(self.responses(("File:d.jpg", "File:e.jpg")))
        self.assertEqual((rep["requests"], rep["status"], unused), (3, "ok", {}))
        self.assertEqual(len(g.calls), 2)
        self.assertIn("File%3Ad.jpg%7CFile%3Ae.jpg", g.calls[1])                            # 候補は 1 回にまとめる
        self.assertIn("srnamespace=6", g.calls[0])
        self.assertIn("winter+plumage", g.calls[0])
        self.assertEqual(urlsplit_host(calls[0]), "upload.wikimedia.org")
        self.assertEqual(saved, got)
        self.assertEqual((got[0]["meta"]["season_term"], got[0]["meta"]["source"]), ("winter", "wikimedia_commons"))
        self.assertTrue(all(w >= 1 for w in waits))

    def test_wait_first_spaces_the_first_request_from_the_previous_species(self):
        _, _, _, waits, _ = self.run_fetch(self.responses(), wait_first=True)
        self.assertEqual(len(waits), 3)
        _, _, _, waits, _ = self.run_fetch(self.responses(), wait_first=False)
        self.assertEqual(len(waits), 2)

    def test_no_candidate_or_no_match_means_no_replacement(self):
        (got, unused, rep), *_ = self.run_fetch({"list=search": (200, self.search_doc())})
        self.assertEqual((got, rep["requests"]), ([], 1))
        (got, unused, rep), _, calls, *_ = self.run_fetch(self.responses(lic="CC BY-NC 2.0"))
        self.assertEqual((got, calls, rep["requests"]), ([], [], 2))
        self.assertIn("満たす候補がない", unused["ユリカモメ"])

    def test_429_stops_without_retry(self):
        (got, unused, rep), g, calls, *_ = self.run_fetch({"list=search": (429, "")})
        self.assertEqual((rep["status"], rep["requests"], len(g.calls)), ("HTTP 429", 1, 1))
        r = self.responses()
        (got, unused, rep), g, calls, *_ = self.run_fetch(r, image=b"")                      # 画像が 429 のときも同じ(下の別の確認)

    def test_image_429_stops_and_nothing_is_saved(self):
        g = T29.getter(self.responses())
        saved = []
        got, unused, rep = C.fetch_commons_season(self.ROW, http_get=g, http_bytes=lambda u, m: (429, b"", {}), ph=PH, max_requests=10,
                                                  sleep=lambda s: None, on_got=saved.append)
        self.assertEqual((rep["status"], rep["requests"], got, saved), ("HTTP 429", 3, [], []))

    def test_max_requests_stops_before_the_next_one(self):
        (got, unused, rep), g, calls, *_ = self.run_fetch(self.responses(), max_requests=2)
        self.assertEqual((rep["requests"], calls, got), (2, [], []))

    def test_network_error_stops(self):
        def hg(url, *a):
            raise OSError("x")
        got, unused, rep = C.fetch_commons_season(self.ROW, http_get=hg, http_bytes=None, ph=PH, max_requests=10, sleep=lambda s: None)
        self.assertEqual((rep["status"], rep["requests"]), ("network_error", 1))

    def test_unexpected_shapes_stop(self):
        (got, unused, rep), *_ = self.run_fetch({"list=search": (200, '{"query": {}}')})
        self.assertEqual(rep["status"], "parse_error")
        with self.assertRaises(ParseError):
            C.parse_file_search({"query": {"search": [{"title": "Category:x"}]}}, CM)

    def test_policy_values_for_the_season_search(self):
        self.assertEqual(CM["season_query"].format(scientific="X y"), "X y winter plumage")
        self.assertIn("winter", CM["season_terms"])
        self.assertEqual(urlsplit_host(C.search_files_url("q", CM)), "commons.wikimedia.org")
        self.assertEqual(urlsplit_host(C.titles_imageinfo_url(["File:a"], CM)), "commons.wikimedia.org")


def urlsplit_host(u):
    from urllib.parse import urlsplit
    return urlsplit(u).hostname


if __name__ == "__main__":
    unittest.main()
