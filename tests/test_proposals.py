"""現地の情報の答えを biyori-proposal/1 で出す(段階18。ikimonobiyori/proposals.py、docs/proposal-mapping.md)。通信なし。合成のデータだけ。
answer との整合(同じ名所・おすすめは maybe)、契約の検査、ゴールデン、性質(決定的・go なし・印の付いた記録を使わない・年のない日付・evidence・禁止語)。"""
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

import helpers as H
from helpers import FIXTURES

import proposal_fixtures as F
import test_answer as T
from ikimonobiyori import answer, catalog, profiles, proposals, sources

POLICY = T.POLICY
PROFILES = profiles.load_profiles()
CAT_POLICY = catalog.load_policy()


def parts_of(recs=None, dates=T.DATES, reg=T.REG, cat=T.CAT, early=False, late=False):
    recs = T.records() if recs is None else recs
    return [{"subject": "autumn_leaves", "name": "紅葉", "catalog": cat, "registry": reg,
             "summary": sources.summarize(recs, registry=reg, catalog_doc=cat, policy=POLICY, on=T.NOW.date(), dates=dates, early=early, late=late),
             "candidates": sources.candidates(cat, reg, dates, POLICY), "care": None}]


def build(ps, dates=T.DATES, early=False, late=False, now=T.NOW):
    return proposals.build(ps, PROFILES, policy=POLICY, catalog_policy=CAT_POLICY, now=now, dates=dates, early=early, late=late)


def catalog_names(cat=T.CAT):
    return {e["name"] for e in cat["entries"]}


def names_in(text, heading, names):
    body = "\n".join(T.body_lines(text, heading))
    return {n for n in names if n in body}


class SameAsAnswer(unittest.TestCase):
    """answer の文章(おすすめ・根拠)に出る名所と、提案の名所が同じ。おすすめに出る名所は band: maybe。"""

    def check(self, dates, early=False, late=False, recs=None):
        ps = parts_of(recs, dates=dates, early=early, late=late)
        text = answer.compose(ps, now=T.NOW, dates=dates, policy=POLICY, early=early, late=late)
        doc = build(ps, dates=dates, early=early, late=late)
        names = catalog_names()
        h = POLICY["answer"]["headings"]
        shown = names_in(text, h["recommend"], names) | names_in(text, h["evidence"], names)
        self.assertEqual(shown, {p["place"]["name"] for p in doc["proposals"]}, text)
        maybe = {p["place"]["name"] for p in doc["proposals"] if p["suitability"]["band"] == "maybe"}
        recommended = {r.get("site") for _, gs in [(None, answer.recommend_groups(ps, POLICY, dates, early=early, late=late,
                                                                                   ahead=(min(dates) - T.NOW.date()).days >= POLICY["answer"]["ahead_min_days"]["value"]))]
                       for _, g in gs for _, r, _ in g}
        site_names = {e["id"]: e["name"] for e in T.CAT["entries"]}
        self.assertLessEqual({site_names[s] for s in recommended if s}, maybe)
        return doc

    def test_this_weekend(self):
        self.check([date(2026, 10, 24), date(2026, 10, 25)])

    def test_a_later_weekend(self):
        self.check(T.DATES)

    def test_early_and_late(self):
        self.check(T.DATES, early=True, late=True)

    def test_answer_and_proposals_share_the_usable_row_check(self):
        import ast
        import inspect
        src = inspect.getsource(answer.pick)
        self.assertIn("usable_status_row", src)
        self.assertIn("usable_status_row", inspect.getsource(proposals.subject_proposals))
        self.assertTrue(ast.parse(src))

    def test_a_state_without_a_stage_is_maybe_when_answer_may_recommend_it(self):
        reg = copy.deepcopy(T.REG)
        recs = [sources.make_record(registry=reg, policy=POLICY, read_at=T.NOW.isoformat(), source_id="test-koyo", site="kouyou-0001",
                                    label="渓谷", state="見ごろ間近", updated="2026-10-23")]
        doc = self.check([date(2026, 10, 24), date(2026, 10, 25)], recs=recs)
        p = doc["proposals"][0]
        self.assertEqual(p["suitability"], {"band": "maybe", "score": None})
        self.assertNotIn("phenology_stage", p)
        self.assertIn(POLICY["proposals"]["known_limits"]["no_stage"], p["uncertainty"]["known_limits"])


GOLDEN = FIXTURES / "proposals"


def subject_doc(subject, recs=None, dates=F.DATES, now=F.NOW, early=False, late=False):
    return proposals.build([F.part(subject, recs=recs, dates=dates, early=early, late=late, profile_name=PROFILES[subject]["name"])], PROFILES,
                           policy=POLICY, catalog_policy=CAT_POLICY, now=now, dates=dates, early=early, late=late)


class Contract(unittest.TestCase):
    """契約の検査は、既存の検査(tests/helpers.py の schema_errors。biyori-proposal/1 の写し)をそのまま使う。"""

    def test_every_subject_passes_the_contract(self):
        for s in F.SUBJECTS:
            with self.subTest(s):
                self.assertEqual(H.schema_errors("biyori-proposal/1", subject_doc(s)), [])

    def test_an_empty_log_passes_too(self):
        doc = subject_doc("autumn_leaves", recs=[])
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        self.assertEqual((doc["status"], doc["status_reason"], doc["proposals"]), ("partial", "no_official_status_today", []))


class Golden(unittest.TestCase):
    """合成データの出力を固定する(tests/fixtures/proposals/。意図した形を目で確かめて置いた。作り直さない)。"""

    def test_each_subject_matches_its_golden(self):
        for s in F.SUBJECTS:
            with self.subTest(s):
                gold = json.loads((GOLDEN / f"{s}.json").read_text(encoding="utf-8"))
                self.assertEqual(json.loads(json.dumps(subject_doc(s), ensure_ascii=False)), gold)


class Properties(unittest.TestCase):
    def test_deterministic(self):
        for s in F.SUBJECTS:
            self.assertEqual(json.dumps(subject_doc(s), ensure_ascii=False), json.dumps(subject_doc(s), ensure_ascii=False))

    def test_no_go_and_no_go_threshold(self):
        for s in F.SUBJECTS:
            for p in subject_doc(s, late=True)["proposals"]:
                self.assertIn(p["suitability"]["band"], ("no", "maybe"))
                if p["suitability"]["score"] is not None:
                    self.assertIsNone(p["suitability"]["score"]["go_threshold"])
                    self.assertIn("not-probability", p["suitability"]["score"]["scale"])
                self.assertEqual((p["uncertainty"]["confidence"]["value"], p["uncertainty"]["confidence"]["validated"]), (None, False))

    def test_evidence_has_the_values_that_need_checking(self):
        need = {"official_state", "freshness", "read_by"}
        for s in F.SUBJECTS:
            for p in subject_doc(s)["proposals"]:
                metrics = {e["metric"] for e in p["evidence"]}
                self.assertLessEqual(need, metrics, p["id"])
                self.assertTrue(metrics & {"official_updated", "official_observed"}, p["id"])
                for o in p["details"]["observations"]:            # details にもある(details だけではない)
                    self.assertTrue(all(k in o for k in ("official_state", "freshness", "read_by", "official_updated", "official_observed")))

    def test_read_by_is_a_label_in_evidence_and_the_value_in_details(self):
        p = subject_doc("birds")["proposals"][0]
        ev = {e["metric"]: e["value"] for e in p["evidence"]}
        self.assertEqual((ev["read_by"], p["details"]["observations"][0]["read_by"]), (POLICY["proposals"]["read_by_labels"]["code"], "code"))

    def test_a_date_without_a_year_is_freshness_unknown(self):
        doc = subject_doc("autumn_leaves")
        p = next(p for p in doc["proposals"] if p["details"]["site_id"] == "s-al-4")
        ev = {e["metric"]: e for e in p["evidence"]}
        self.assertEqual((ev["freshness"]["value"], ev["official_observed"]["value"], ev["official_observed"]["last_updated"]),
                         (POLICY["freshness"]["labels"]["year_unknown"], "10/21", None))
        self.assertIn(POLICY["proposals"]["known_limits"]["year_unknown"], p["uncertainty"]["known_limits"])
        self.assertIs(p["details"]["observations"][0]["observed_year_inferred"], True)

    def test_a_year_filled_from_the_same_item_keeps_its_mark(self):
        reg, _, _ = F.scenario("autumn_leaves")
        r = sources.make_record(registry=reg, policy=POLICY, read_at=F.NOW.isoformat(), source_id="al-main", site="s-al-2", label="試験の湖",
                                state="見ごろ", updated="2026-10-23", observed_md="10-22")
        p = subject_doc("autumn_leaves", recs=[r])["proposals"][0]
        mark = POLICY["freshness"]["observed_year_from_update_mark"]
        self.assertEqual(p["details"]["observations"][0]["observed_year_inferred"], mark)
        self.assertIn(POLICY["proposals"]["known_limits"]["year_inferred"], p["uncertainty"]["known_limits"])

    def test_band_rules(self):
        doc = subject_doc("flowers")
        band = {(p["details"]["site_id"], p["time_window"]["start"][:10]): p["suitability"]["band"] for p in doc["proposals"]}
        self.assertEqual(band[("s-fl-1", "2026-10-31")], "maybe")            # 見頃
        self.assertEqual(band[("s-fl-2", "2026-10-31")], "no")               # つぼみ・見頃予測(11月上旬)がかからない
        self.assertEqual(band[("s-fl-2", "2026-11-01")], "maybe")            # 見頃予測がかかる
        auto = {p["details"]["site_id"]: p["suitability"]["band"] for p in subject_doc("autumn_leaves")["proposals"]}
        self.assertEqual((auto["s-al-1"], auto["s-al-2"], auto["s-al-4"]), ("maybe", "no", "maybe"))   # 見ごろ以上 / まだ / 始まり

    def test_freshness_does_not_change_the_band_but_old_is_written(self):
        reg, _, _ = F.scenario("autumn_leaves")
        mk = lambda up: sources.make_record(registry=reg, policy=POLICY, read_at=F.NOW.isoformat(), source_id="al-main", site="s-al-2",  # noqa: E731
                                            label="試験の湖", state="見ごろ", updated=up)
        new, old = (subject_doc("autumn_leaves", recs=[mk(up)])["proposals"][0] for up in ("2026-10-23", "2026-10-09"))
        self.assertEqual((new["suitability"]["band"], old["suitability"]["band"]), ("maybe", "maybe"))
        self.assertNotIn(POLICY["proposals"]["known_limits"]["old"], new["uncertainty"]["known_limits"])
        self.assertIn(POLICY["proposals"]["known_limits"]["old"], old["uncertainty"]["known_limits"])           # 15 日前(14 日以上)

    def test_records_older_than_30_days_before_the_target_are_not_used(self):
        doc = subject_doc("autumn_leaves")
        self.assertNotIn("s-al-3", {p["details"]["site_id"] for p in doc["proposals"]})
        self.assertTrue(any("試験の峠" in w and "30" in w for w in doc["diagnostics"]["warnings"]))

    def test_far_dates_use_only_the_official_forecast(self):
        far = [date(2026, 11, 14)]                                           # 読んだ日から 21 日先(14 日より先)
        doc = subject_doc("autumn_leaves", dates=far)
        band = {p["details"]["site_id"]: p for p in doc["proposals"]}
        self.assertEqual(band["s-al-2"]["suitability"]["band"], "no")
        self.assertEqual(band["s-al-4"]["suitability"]["band"], "no")      # 始まりでも、先の日は今の状態で判断しない
        self.assertIn(POLICY["proposals"]["known_limits"]["beyond_horizon"], band["s-al-4"]["uncertainty"]["known_limits"])

    def test_places_without_proposals_are_warned_once(self):
        doc = subject_doc("autumn_leaves")
        w = doc["diagnostics"]["warnings"]
        self.assertEqual(len(w), len(set(w)))
        self.assertTrue(any("試験の高原" in x for x in w))
        self.assertTrue(any("試験の外の滝" in x for x in w))
        self.assertEqual(sum("試験の峠" in x for x in w), 1)

    def test_a_place_with_a_proposal_is_not_also_without_status(self):
        reg, _, _ = F.scenario("wintering_birds")
        reg = copy.deepcopy(reg)
        reg["sources"].append(F.src("wb-b", "wintering_birds", [{"site": "s-wb-1", "label": "試験の沼・別"}], {"初飛来": "arriving"}))
        mk = lambda sid, label, state: sources.make_record(registry=reg, policy=POLICY, read_at=F.NOW.isoformat(), source_id=sid,  # noqa: E731
                                                           site="s-wb-1", label=label, state=state, updated="2026-10-23")
        recs = [mk("wb-a", "試験の沼", "初飛来"), mk("wb-b", "試験の沼・別", None)]
        part = F.part("wintering_birds", recs=recs, profile_name="冬鳥")
        part["registry"] = reg
        part["summary"] = sources.summarize(recs, registry=reg, catalog_doc=part["catalog"], policy=POLICY, on=F.NOW.date(), dates=F.DATES)
        doc = proposals.build([part], PROFILES, policy=POLICY, catalog_policy=CAT_POLICY, now=F.NOW, dates=F.DATES)
        self.assertIn("s-wb-1", {p["details"]["site_id"] for p in doc["proposals"]})
        self.assertFalse([w for w in doc["diagnostics"]["warnings"] if "試験の沼" in w])

    def test_two_labels_of_one_place_become_one_proposal(self):
        doc = subject_doc("autumn_leaves")
        ps = [p for p in doc["proposals"] if p["details"]["site_id"] == "s-al-1"]
        self.assertEqual(len(ps), len(F.DATES))
        self.assertEqual({o["label"] for o in ps[0]["details"]["observations"]}, {"試験の谷・木々", "試験の谷・草紅葉"})
        self.assertEqual((ps[0]["phenology_stage"], ps[0]["suitability"]["score"]["value"]), ("peak", 3))   # 真っ盛り(3)が代表

    def test_sensitive_places_are_rounded(self):
        p = subject_doc("wintering_birds")["proposals"][0]
        self.assertEqual((p["place"]["lat"], p["place"]["lon"], p["place"]["location_precision"]), (36.12, 139.99, "area_1km"))
        self.assertTrue(p["care"]["do_not_disclose_exact_location"])
        b = subject_doc("birds")["proposals"][0]
        self.assertEqual((b["place"]["lat"], b["place"]["location_precision"]), (35.6, "area_10km"))      # プロファイルの粗さ(粗い方)

    def test_traffic_note_goes_to_care(self):
        p = next(p for p in subject_doc("autumn_leaves")["proposals"] if p["details"]["site_id"] == "s-al-1")
        self.assertIn("紅葉期は試験の道が混みやすい", p["care"]["manners"])

    def test_no_internal_terms_in_known_limits_warnings_and_texts(self):
        for s in F.SUBJECTS:
            doc = subject_doc(s)
            texts = list(doc["diagnostics"]["warnings"]) + [x for p in doc["proposals"] for x in p["uncertainty"]["known_limits"]]
            texts += [str(e["value"]) for p in doc["proposals"] for e in p["evidence"] if isinstance(e["value"], str)]
            texts += [e["source"] for p in doc["proposals"] for e in p["evidence"]] + [p["title"] for p in doc["proposals"]]
            texts += [m for p in doc["proposals"] for m in p["care"]["manners"]]
            self.assertEqual(answer.forbidden_found("\n".join(texts), POLICY), [], s)
        for k, t in POLICY["proposals"]["warnings"].items():
            self.assertEqual(answer.forbidden_found(t, POLICY), [], k)


class MarkedRecordsAndCli(unittest.TestCase):
    """記録のファイル(IKIMONOBIYORI_DATA_DIR)からの経路と CLI。誤りの印・置き換えの印の記録は使わない。通信しない(子プロセスもソケット禁止)。"""

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="ikimono-proposals-")
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = {"IKIMONOBIYORI_DATA_DIR": self.d}
        reg = sources.load_registry("autumn_leaves")
        mk = lambda **kw: sources.make_record(registry=reg, policy=POLICY, read_at=F.NOW.isoformat(), source_id="nikko-kankou-autumn-leaves",  # noqa: E731
                                              site="kouyou-0001", label="【奥日光】湯ノ湖、湯滝", **kw)
        sources.append_records([mk(state="✕", updated="2026-10-20"), mk(state="◎", updated="2026-10-22"), mk(state="〇", updated="2026-10-21")],
                               registry=reg, policy=POLICY, env=self.env)
        sources.mark_erroneous("autumn_leaves", {"official_state": "◎"}, reason="試験", corrected_on="2026-10-24", env=self.env)
        sources.supersede_records("autumn_leaves", {"official_state": "〇"}, reason="試験", on="2026-10-24", env=self.env)

    def test_marked_records_are_not_used(self):
        parts = sources.answer_parts(["autumn_leaves"], policy=POLICY, now=F.NOW, dates=F.DATES, env=self.env)
        doc = proposals.build(parts, PROFILES, policy=POLICY, catalog_policy=CAT_POLICY, now=F.NOW, dates=F.DATES)
        ps = [p for p in doc["proposals"] if p["details"]["site_id"] == "kouyou-0001"]
        self.assertEqual({o["official_state"] for p in ps for o in p["details"]["observations"]}, {"✕"})
        self.assertEqual({p["suitability"]["band"] for p in ps}, {"no"})

    def test_cli_child_without_network_twice_gives_the_same_output(self):
        cmd = [sys.executable, "-X", "utf8", "-m", "ikimonobiyori.sources", "--subject", "autumn_leaves", "proposals",
               "--now", F.NOW.isoformat(), "--date", "2026-10-31", "--date", "2026-11-01"]
        outs = [H.run_child_env(cmd, self.env, cwd=str(H.ROOT), capture_output=True, text=True, encoding="utf-8") for _ in range(2)]
        for r in outs:
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(outs[0].stdout, outs[1].stdout)
        doc = json.loads(outs[0].stdout)
        self.assertEqual(H.schema_errors("biyori-proposal/1", doc), [])
        self.assertIn("ikimonobiyori:autumn_leaves:2026-10-31:kouyou-0001", {p["id"] for p in doc["proposals"]})
        self.assertEqual(doc["diagnostics"]["api_calls"], 0)

    def test_cli_writes_a_file_only_with_out(self):
        out = os.path.join(self.d, "o", "p.json")
        buf = io.StringIO()
        with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(buf):
            rc = sources.main(["--subject", "autumn_leaves", "proposals", "--now", F.NOW.isoformat(), "--out", out])
        self.assertEqual((rc, buf.getvalue()), (0, ""))
        self.assertEqual(json.loads(Path(out).read_text(encoding="utf-8"))["schema"], "biyori-proposal/1")

    def test_next_weekend_option(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, self.env), contextlib.redirect_stdout(buf):
            sources.main(["--subject", "autumn_leaves", "proposals", "--now", F.NOW.isoformat(), "--weekend", "next"])
        days = {p["time_window"]["start"][:10] for p in json.loads(buf.getvalue())["proposals"]}
        self.assertLessEqual(days, {"2026-10-31", "2026-11-01"})          # 10/24(土)の「来週末」


if __name__ == "__main__":
    unittest.main()
