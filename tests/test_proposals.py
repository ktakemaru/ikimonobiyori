"""現地の情報の答えを biyori-proposal/1 で出す(段階18。ikimonobiyori/proposals.py、docs/proposal-mapping.md)。通信なし。合成のデータだけ。
answer との整合(同じ名所・おすすめは maybe)、契約の検査、ゴールデン、性質(決定的・go なし・印の付いた記録を使わない・年のない日付・evidence・禁止語)。"""
import contextlib
import copy
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import helpers as H
from helpers import FIXTURES

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


if __name__ == "__main__":
    unittest.main()
