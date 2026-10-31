"""段階32: 地域を指定した花の答え(ikimonobiyori/regional.py)。通信なし。合成のデータだけ(実データの記録は使わない)。
指示書 4 のテスト 1〜8 に対応: 地域・終盤・段階(A/B/C)・終了した名所・禁止語・同じ日の再利用・既存テスト(ほかのテストファイルが見る)。"""
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import catalog, regional, sources

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=JST)
DATES = [date(2026, 10, 31), date(2026, 11, 1)]
POLICY = sources.load_policy()
RP = regional.load_policy()
KINDS = ["秋バラ", "菊", "コスモス"]
KANAGAWA = sources.resolve_region("神奈川", sources.load_regions())


def win(kind, s, e, year=2025):
    return {"kind": kind, "start": s, "end": e, "source_url": "https://example.org/w", "source_year": year}


def ev(kind, name, s, e, year=2026, verified=True):
    return {"kind": kind, "name": name, "start": s, "end": e, "year": year, "source_url": "https://example.org/e", "checked_on": "2026-10-31", "verified": verified}


def site(sid, name, kinds, pref="神奈川県", city="試験市", windows=(), events=(), status="approved", point=None, ledgers=()):
    e = {"id": sid, "name": name, "subjects": ["flowers"], "timing_type": "managed", "kind": "area", "location_precision": "exact",
         "status": status, "sources": [{"url": "https://example.org/a"}], "status_sources": list(ledgers),
         "tags": {"prefecture": pref, "city": city, "flower_kinds": list(kinds)}}
    if status == "approved":
        e["approved_at"] = "2026-10-31"
    if point:
        e["point"] = {"lat": point[0], "lon": point[1], "elevation_m": None}
    if windows:
        e["flower_windows"] = list(windows)
    if events:
        e["events"] = list(events)
    return e


def src(sid, covers, approved=True, kind="status_page", map_=None):
    return {"id": sid, "publisher": "試験公園", "publisher_kind": "park_manager", "url": f"https://example.org/{sid}", "kind": kind, "covers": covers,
            "notation": {"style": "word", "map": map_ if map_ is not None else {"咲き始め": "starting", "見頃": "good", "散り始め": "falling"},
                         "updated": "per_item", "year_shown": True},
            "readable": {"status": "ok", "checked_on": "2026-10-31", "robots": "allows"}, "terms": {"status": "no_prohibition_found"},
            "approval": ({"status": "approved", "approved_by": "user", "approved_on": "2026-10-31"} if approved else {"status": "pending", "reason": "試験"})}


COVERS = [{"site": "hana-0001", "label": "バラ", "flower_kind": "秋バラ"},
          {"site": "hana-0002", "label": "バラ", "flower_kind": "秋バラ"},
          {"site": "hana-0003", "label": "バラ", "flower_kind": "秋バラ"},
          {"site": "hana-0004", "label": "バラ", "flower_kind": "秋バラ"},
          {"site": "hana-0005", "label": "コスモス", "flower_kind": "コスモス"}]
REG = {"schema": "ikimono-status-sources/1", "subject": "flowers", "sources": [src("test-hana", COVERS)]}


def mkrec(site_id, label, state, updated="2026-10-30", now=NOW, **kw):
    return sources.make_record(registry=REG, policy=POLICY, read_at=now.isoformat(), source_id="test-hana", site=site_id, label=label, state=state, updated=updated, **kw)


def build_part(entries, recs, dates=DATES, now=NOW, region=None, kinds=KINDS, registry=REG):
    cat = {"schema": "ikimono-site-catalog/1", "subject": "flowers", "entries": entries}
    return {"subject": "flowers", "name": "花", "catalog": cat, "registry": registry,
            "summary": sources.summarize(recs, registry=registry, catalog_doc=cat, policy=POLICY, on=now.date(), dates=dates),
            "candidates": {}, "care_manners": None}


def answer_text(entries, recs, region=KANAGAWA, nearby=True, kinds=KINDS, dates=DATES, now=NOW):
    cat_entries = [e for e in entries]
    part = build_part([e for e in cat_entries if not region or sources.in_region(e, region)], recs, dates, now)
    near = build_part(cat_entries, recs, dates, now) if region and nearby else None
    return regional.compose(region=region, kinds=kinds, dates=dates, now=now, part=part, nearby_part=near, policy=POLICY)


def section(text, heading):
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            on = line[3:].strip() == heading
            continue
        if on and line.strip():
            out.append(line)
    return out


H_REC = RP["text"]["headings"]["recommend"]
IN_KANAGAWA = [
    site("hana-0001", "試験バラ園A", ["秋バラ"], city="平塚市", windows=[win("秋バラ", "10-15", "11-15")]),
    site("hana-0002", "試験バラ園B", ["秋バラ"], city="小田原市", windows=[win("秋バラ", "10-15", "11-15")]),
    site("hana-0003", "試験バラ園C", ["秋バラ"], city="横浜市", windows=[win("秋バラ", "10-15", "11-15")]),
]
IBARAKI = site("hana-0090", "試験の茨城の花園", ["コスモス", "秋バラ"], pref="茨城県", city="ひたちなか市", point=(36.40, 140.59), windows=[win("コスモス", "10-01", "11-10")])


class Region(unittest.TestCase):
    def test_1_other_prefecture_never_recommended_when_region_given(self):
        """神奈川と聞かれたら、茨城の名所は推薦に出ない(回帰: 国営ひたち海浜公園)。県内が足りていれば近隣の欄も出ない。"""
        t = answer_text(IN_KANAGAWA + [IBARAKI], [])
        rec = "\n".join(section(t, H_REC))
        self.assertIn("試験バラ園A", rec)
        self.assertNotIn("茨城", t)
        self.assertNotIn("ひたちなか", t)
        self.assertEqual(section(t, RP["text"]["headings"]["nearby"]), [])

    def test_1_real_catalog_has_no_ibaraki_recommendation(self):
        """実データのカタログ・台帳でも、神奈川の質問に国営ひたち海浜公園は出ない(記録は合成)。"""
        cat = catalog.load_catalog("flowers")
        reg = sources.load_registry("flowers")
        part = {"subject": "flowers", "name": "花", "catalog": cat, "registry": reg,
                "summary": sources.summarize([], registry=reg, catalog_doc=cat, policy=POLICY, on=NOW.date(), dates=DATES),
                "candidates": {}, "care_manners": None}
        t = regional.compose(region=KANAGAWA, kinds=KINDS, dates=DATES, now=NOW, part=part, nearby_part=None, policy=POLICY)
        self.assertNotIn("ひたち海浜公園", "\n".join(section(t, H_REC)))
        self.assertNotIn("ひたち海浜公園", t)

    def test_2_zero_in_region_is_said_first_and_nearby_is_separate(self):
        """指定地域内に該当が 0 件のとき、その旨が答えの先頭(見出しの直後)に出る。近隣は県外と明示して別の見出し。"""
        near = site("hana-0091", "試験の東京の花園", ["秋バラ"], pref="東京都", city="目黒区", point=(35.63, 139.70), windows=[win("秋バラ", "10-15", "11-15")])
        t = answer_text([near], [])
        lines = [x for x in t.splitlines() if x.strip()]
        self.assertIn("神奈川県の秋バラ・菊・コスモスの名所は、名所の一覧にまだありません", lines[1])
        self.assertIn("追加の候補", lines[2])
        nb = section(t, RP["text"]["headings"]["nearby"])
        self.assertEqual(len(nb), 1)
        self.assertIn("県外です", nb[0])
        self.assertEqual(section(t, H_REC), [])

    def test_2_nothing_found_in_region_with_sites(self):
        """地域内に名所はあるが、対象の日におすすめできるものがないとき、その旨が先頭に出る。"""
        out_of_season = [site("hana-0001", "試験バラ園A", ["秋バラ"], windows=[win("秋バラ", "04-20", "05-31")])]
        t = answer_text(out_of_season, [], nearby=False)
        self.assertIn("おすすめできる秋バラ・菊・コスモスの名所は見つかりませんでした", [x for x in t.splitlines() if x.strip()][1])

    def test_no_region_uses_distance_only(self):
        """地域の指定がないときだけ、出発地からの距離で絞る(範囲の外は出さない。代表点のない名所は出さない)。"""
        far = site("hana-0092", "試験の遠い花園", ["秋バラ"], pref="北海道", point=(43.06, 141.35), windows=[win("秋バラ", "10-15", "11-15")])
        close = site("hana-0093", "試験の近い花園", ["秋バラ"], pref="東京都", point=(35.63, 139.70), windows=[win("秋バラ", "10-15", "11-15")])
        nopt = site("hana-0094", "試験の座標なし", ["秋バラ"], pref="東京都", windows=[win("秋バラ", "10-15", "11-15")])
        t = answer_text([far, close, nopt], [], region=None)
        self.assertIn("試験の近い花園", t)
        self.assertNotIn("試験の遠い花園", t)
        self.assertNotIn("試験の座標なし", t)
        self.assertIn("出発地: 横浜", t)


class Ended(unittest.TestCase):
    def test_3_past_peak_and_unreadable_are_not_recommended(self):
        """状態が終盤・見頃過ぎ・終了の地点は推薦に入らない。花の種類に固有の語(ブラウンがメイン)は正規化できず推薦に入らない。"""
        ents = IN_KANAGAWA + [site("hana-0004", "試験の終盤園", ["秋バラ"], windows=[win("秋バラ", "10-15", "11-15")]),
                              site("hana-0005", "試験のコスモス園", ["コスモス"], windows=[win("コスモス", "10-01", "11-10")])]
        recs = [mkrec("hana-0001", "バラ", "見頃"),
                mkrec("hana-0002", "バラ", "散り始め"),
                mkrec("hana-0003", "バラ", "ブラウンがメイン"),
                mkrec("hana-0004", "バラ", "終了"),
                mkrec("hana-0005", "コスモス", "咲いています")]
        t = answer_text(ents, recs, nearby=False)
        rec = "\n".join(section(t, H_REC))
        self.assertIn("試験バラ園A", rec)
        self.assertEqual(rec.count("**"), 2)                       # 太字の名前は 1 件だけ
        for name in ("試験バラ園B", "試験バラ園C", "試験の終盤園", "試験のコスモス園"):
            self.assertNotIn(name, rec)
        past = "\n".join(section(t, RP["text"]["headings"]["past"]))
        self.assertIn("試験バラ園B", past)
        self.assertIn("おすすめには入れていません", past)
        unreadable = "\n".join(section(t, RP["text"]["headings"]["unreadable"]))
        self.assertIn("ブラウンがメイン", unreadable)
        self.assertIn("咲いています", unreadable)
        self.assertLessEqual(len(section(t, RP["text"]["headings"]["past"])), 2)

    def test_3_vocabulary_is_exact_match_and_never_guesses(self):
        for raw in ("ブラウンがメイン", "咲いています", "満開に近い", "", None):
            self.assertIsNone(regional.vocab_stage(raw, RP), raw)
        self.assertEqual(regional.vocab_stage("見頃です", RP), "good")
        self.assertEqual(regional.vocab_stage("終了", RP), "falling")
        self.assertEqual(regional.vocab_stage("つぼみ", RP), "bud")

    def test_3_vocabulary_stages_exist_in_profile(self):
        from ikimonobiyori import profiles
        ids = {s["id"] for s in profiles.load_profiles()["flowers"]["stages"]["items"]}
        for st in RP["state_vocabulary"]["words"]:
            self.assertIn(st, ids)
        for ids_ in RP["stage_groups"].values():
            self.assertTrue(set(ids_) <= ids)

    def test_3_early_stage_goes_to_coming_section_not_recommend(self):
        ents = [site("hana-0001", "試験バラ園A", ["秋バラ"], windows=[win("秋バラ", "10-15", "11-15")])]
        t = answer_text(ents, [mkrec("hana-0001", "バラ", "咲き始め")], nearby=False)
        self.assertEqual(section(t, H_REC), [])
        self.assertIn("見頃はこれからです", "\n".join(section(t, RP["text"]["headings"]["early"])))

    def test_5_retired_and_candidate_sites_are_never_recommended(self):
        """終了した名所(retired)・未確認の名所(candidate)は、例年の時期の中でも推薦に出ない。"""
        ents = [site("hana-0001", "試験の終了した菊", ["菊"], status="retired", windows=[win("菊", "10-20", "11-30")]),
                site("hana-0002", "試験の休止中のばら苑", ["秋バラ"], status="candidate", windows=[win("秋バラ", "10-15", "11-15")])]
        t = answer_text([e for e in ents], [], nearby=False)
        self.assertNotIn("試験の終了した菊", t)
        self.assertNotIn("試験の休止中のばら苑", t)

    def test_5_real_catalog_isozu_and_ikuta_not_approved(self):
        by = {e["name"]: e for e in catalog.load_catalog("flowers")["entries"]}
        self.assertEqual(by["新磯ざる菊花見会"]["status"], "retired")
        self.assertIn("終了", by["新磯ざる菊花見会"]["retired_reason"])
        self.assertEqual(by["生田緑地ばら苑"]["status"], "candidate")
        approved = {e["name"] for e in catalog.approved_entries(catalog.load_catalog("flowers"))}
        self.assertNotIn("新磯ざる菊花見会", approved)
        self.assertNotIn("生田緑地ばら苑", approved)


class Tiers(unittest.TestCase):
    def test_4_official_status_shows_original_wording_and_date(self):
        ents = IN_KANAGAWA[:1]
        t = answer_text(ents, [mkrec("hana-0001", "バラ", "見頃", updated="2026-10-29", observed="2026-10-30")], nearby=False)
        line = section(t, H_REC)[0]
        self.assertIn("確度: 公式の現況", line)
        self.assertIn("公式の状態「見頃」", line)
        self.assertIn("10/30時点", line)
        self.assertNotIn("例年の時期のみ", line)

    def test_4_event_period_this_year_with_typical_overlap(self):
        ents = [site("hana-0001", "試験バラ園A", ["秋バラ"], windows=[win("秋バラ", "10-10", "11-08")], events=[ev("秋バラ", "試験のバラ祭り", "2026-10-10", "2026-11-08")])]
        line = section(answer_text(ents, [], nearby=False), H_REC)[0]
        self.assertIn("確度: 今年のイベント期間つき", line)
        self.assertIn("試験のバラ祭り", line)
        self.assertIn("10/10〜11/8", line)

    def test_4_typical_only_says_so(self):
        ents = IN_KANAGAWA[:1]
        line = section(answer_text(ents, [], nearby=False), H_REC)[0]
        self.assertIn("確度: 例年の時期のみ", line)
        self.assertIn("例年 10/15〜11/15", line)
        self.assertIn("今年の公式の情報は確認できていません", line)

    def test_4_previous_year_period_is_not_shown_as_this_years(self):
        """前年の開催期間は、段階『今年のイベント期間つき』にならない(例年の時期のみ)。未確認の今年の期間も同じ。"""
        old = [site("hana-0001", "試験バラ園A", ["秋バラ"], windows=[win("秋バラ", "10-10", "11-08", 2025)],
                    events=[ev("秋バラ", "昨年のバラ祭り", "2025-10-10", "2025-11-08", year=2025)])]
        unverified = [site("hana-0001", "試験バラ園A", ["秋バラ"], windows=[win("秋バラ", "10-10", "11-08", 2026)],
                           events=[ev("秋バラ", "未確認のバラ祭り", "2026-10-10", "2026-11-08", verified=False)])]
        for ents in (old, unverified):
            line = section(answer_text(ents, [], nearby=False), H_REC)[0]
            self.assertIn("確度: 例年の時期のみ", line)
            self.assertNotIn("今年のイベント期間つき", line)
            self.assertNotIn("昨年のバラ祭り", line)
            self.assertNotIn("未確認のバラ祭り", line)

    def test_4_catalog_check_rejects_event_year_mismatch(self):
        policy = catalog.load_policy()
        bad = site("hana-0001", "試験", ["秋バラ"], events=[ev("秋バラ", "祭り", "2025-10-10", "2025-11-08", year=2026)])
        errs = catalog.check_entry(bad, subject="flowers", profile_ids={"flowers"}, policy=policy)
        self.assertTrue(any("前年の日付を今年として扱わない" in e for e in errs), errs)

    def test_4_real_catalog_events_have_source_year_and_verified_have_sources(self):
        doc = catalog.load_catalog("flowers")
        policy = catalog.load_policy()
        ids = {p for p in ("flowers",)}
        for e in doc["entries"]:
            self.assertEqual(catalog.check_entry(e, subject="flowers", profile_ids=ids, policy=policy), [], e["id"])
            for w in e.get("flower_windows") or []:
                self.assertIn("source_year", w)
            for x in e.get("events") or []:
                self.assertEqual(x["year"], int(x["start"][:4]))

    def test_event_row_read_today_gives_event_tier(self):
        """今日読んだイベントのページの記録(期間つき)は、今年のイベント期間つきの根拠になる。"""
        reg = {"schema": "ikimono-status-sources/1", "subject": "flowers", "sources": [
            src("test-event", [{"site": "hana-0001", "label": "バラ祭り", "flower_kind": "秋バラ"}], kind="event_page")]}
        rec = sources.make_record(registry=reg, policy=POLICY, read_at=NOW.isoformat(), source_id="test-event", site="hana-0001", label="バラ祭り",
                                  state=None, event_start="2026-10-31", event_end="2026-11-23")
        cat = {"schema": "ikimono-site-catalog/1", "subject": "flowers", "entries": [IN_KANAGAWA[0]]}
        part = {"subject": "flowers", "name": "花", "catalog": cat, "registry": reg,
                "summary": sources.summarize([rec], registry=reg, catalog_doc=cat, policy=POLICY, on=NOW.date(), dates=DATES),
                "candidates": {}, "care_manners": None}
        t = regional.compose(region=KANAGAWA, kinds=KINDS, dates=DATES, now=NOW, part=part, nearby_part=None, policy=POLICY)
        line = section(t, H_REC)[0]
        self.assertIn("確度: 今年のイベント期間つき", line)
        self.assertIn("10/31〜11/23", line)


class Wording(unittest.TestCase):
    def full_text(self):
        ents = IN_KANAGAWA + [site("hana-0004", "試験の終盤園", ["秋バラ"], windows=[win("秋バラ", "10-15", "11-15")]),
                              site("hana-0005", "試験のコスモス園", ["コスモス"], windows=[win("コスモス", "10-01", "11-10")], ledgers=["test-hana"])]
        recs = [mkrec("hana-0001", "バラ", "見頃"), mkrec("hana-0004", "バラ", "終了"), mkrec("hana-0005", "コスモス", "ブラウンがメイン")]
        ents = ents + [site("hana-0006", "試験の未確認園", ["菊"], windows=[win("菊", "10-20", "11-30")])]
        return answer_text(ents, recs, nearby=True)

    def test_6_forbidden_terms_never_appear(self):
        t = self.full_text()
        self.assertEqual(regional.forbidden_found(t, RP), [])
        body = re.sub(r"https?://\S+", " ", t)
        for term in ("簡易な読み取り", "承認待ち", "承認待ちの情報源", "作業メモ", "reader", "規則", "record", "status_log", "v0",
                     "参照数は付けられませんでした", "カタログにない"):
            self.assertNotIn(term, body)
        self.assertNotRegex(body, r"確度[:：]\s*[ABC]\b")
        self.assertNotRegex(body, r"[（(][ABC][）)]")

    def test_6_forbidden_list_matches_instruction(self):
        self.assertEqual(set(RP["forbidden_terms"]) >= {"簡易な読み取り", "承認待ち", "承認待ちの情報源", "作業メモ", "reader", "規則", "record",
                                                         "status_log", "v0", "参照数は付けられませんでした", "カタログにない"}, True)

    def test_6_self_check_raises_on_forbidden_text(self):
        rp = dict(RP, text={**RP["text"], "note_hours": "作業メモ: 内部の事情"})
        with mock.patch.object(regional, "load_policy", return_value=rp):
            with self.assertRaises(ValueError):
                answer_text(IN_KANAGAWA[:1], [], nearby=False)

    def test_conclusion_comes_first_and_has_tier(self):
        t = answer_text(IN_KANAGAWA, [mkrec("hana-0001", "バラ", "見頃")], nearby=False)
        lines = [x for x in t.splitlines() if x.strip()]
        self.assertTrue(lines[0].startswith("**"))
        self.assertIn("おすすめできるのは", lines[1])
        self.assertIn("(公式の現況)", lines[1])
        self.assertTrue(lines[2].startswith("## "))

    def test_unread_sites_get_official_url_without_internal_words(self):
        reg = {**REG, "sources": [src("test-hana", COVERS), src("test-pending", [{"site": "hana-0006", "label": "菊", "flower_kind": "菊"}], approved=False)]}
        e = site("hana-0006", "試験の未確認園", ["菊"], windows=[win("菊", "10-20", "11-30")], ledgers=["test-pending"])
        part = build_part([e], [], registry=reg)
        t = regional.compose(region=KANAGAWA, kinds=KINDS, dates=DATES, now=NOW, part=part, nearby_part=None, policy=POLICY)
        # 例年の時期のみで推薦に出る名所は、読めなかった名所の欄に重ねない
        self.assertEqual(section(t, RP["text"]["headings"]["unread"]), [])
        e2 = site("hana-0007", "試験の時期不明園", ["菊"], ledgers=["test-pending"])
        reg2 = {**reg, "sources": reg["sources"] + [src("test-pending2", [{"site": "hana-0007", "label": "菊", "flower_kind": "菊"}], approved=False)]}
        e2["status_sources"] = ["test-pending2"]
        t2 = regional.compose(region=KANAGAWA, kinds=KINDS, dates=DATES, now=NOW, part=build_part([e2], [], registry=reg2), nearby_part=None, policy=POLICY)
        lines = section(t2, RP["text"]["headings"]["unread"])
        self.assertEqual(len(lines), 1)
        self.assertIn("公式の現況は未確認です。公式ページ: https://example.org/test-pending2", lines[0])


class SameDay(unittest.TestCase):
    def test_7_records_are_reused_only_within_the_same_day(self):
        """記録の再利用は同じ日のうちだけ。日付が変わると昨日の記録は答えに使われない(通信しない)。"""
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "IKIMONOBIYORI_DATA_DIR": d}
            rec = mkrec("hana-0001", "バラ", "見頃")
            sources.append_records([rec], registry=REG, policy=POLICY, env=env)
            self.assertEqual(len(sources.records_on("flowers", NOW.date(), env)), 1)
            self.assertEqual(sources.records_on("flowers", (NOW + timedelta(days=1)).date(), env), [])
            # 昨日の記録は、翌日の答えの『公式の現況』にならない
            nxt = NOW + timedelta(days=1)
            part = build_part(IN_KANAGAWA[:1], sources.records_on("flowers", nxt.date(), env), dates=[nxt.date()], now=nxt)
            t = regional.compose(region=KANAGAWA, kinds=KINDS, dates=[nxt.date()], now=nxt, part=part, nearby_part=None, policy=POLICY)
            self.assertNotIn("確度: 公式の現況", t)
            self.assertIn("確度: 例年の時期のみ", t)


class Cli(unittest.TestCase):
    def test_cli_regional_runs_on_real_catalog_with_empty_log(self):
        """実データのカタログ・台帳で CLI が動く(記録は空の一時フォルダ)。神奈川の質問に県外の名所の推薦は出ない。"""
        with tempfile.TemporaryDirectory() as d:
            env = {"IKIMONOBIYORI_DATA_DIR": d}
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env), redirect_stdout(buf):
                code = sources.main(["regional", "--now", NOW.isoformat(), "--date", "2026-10-31", "--date", "2026-11-01", "--region", "神奈川",
                                     "--flower-kind", "秋バラ", "--flower-kind", "菊", "--flower-kind", "コスモス"])
        self.assertEqual(code, 0)
        t = buf.getvalue()
        self.assertTrue(t.startswith("**2026年10月31日(土)・2026年11月1日(日)の秋バラ・菊・コスモス**(神奈川県)"))
        self.assertNotIn("ひたち海浜公園", t)
        self.assertEqual(regional.forbidden_found(t, RP), [])
        by = {e["name"]: e["tags"]["prefecture"] for e in catalog.approved_entries(catalog.load_catalog("flowers"))}
        for name in re.findall(r"\*\*(.+?)\*\*", "\n".join(section(t, H_REC))[2:]):
            if name in by:
                self.assertEqual(by[name], "神奈川県", name)

    def test_cli_unknown_region_is_rejected(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = sources.main(["regional", "--now", NOW.isoformat(), "--region", "どこにもない県", "--flower-kind", "菊"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
