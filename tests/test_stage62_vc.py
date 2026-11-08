"""段階62 第5部: 施設の発信の文(状態の語と種名を別の文に・種名に区分)と、その検査。通信なし・合成データ。"""
import unittest

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask_verify as AV
from ikimonobiyori import visitor_centers as V

C = {"id": "t-vc", "name": "試験ビジターセンター"}
REP = {"date": "2026-11-06", "state": "色づき始めの草木の葉", "species": ["ジョウビタキ", "ナゾノトリ"], "url": "https://vc.example.org/news"}


def facts():
    return {"visitor_centers": [{"center": "t-vc", "name": C["name"], "state": REP["state"], "species": REP["species"],
                                 "line": V.report_line(C, REP), "sentences": V.report_sentences(C, REP), "url": REP["url"]}]}


def codes(text):
    return [e["code"] for e in AV.vc_sentence_errors(text, facts())]


class Sentences(unittest.TestCase):
    def test_state_and_species_are_separate_sentences_with_kind(self):
        s = V.report_sentences(C, REP)
        self.assertEqual(s[0], "試験ビジターセンターは、11/6時点で「色づき始めの草木の葉」と発信しています。")
        self.assertEqual(s[1], "同じ発信に、ジョウビタキ(鳥)、ほか1種の名があります。")            # 区分の分からない種名は出さない
        self.assertNotIn("ナゾノトリ", "".join(s))

    def test_unknown_kinds_only_gives_no_species_sentence(self):
        self.assertEqual(len(V.report_sentences(C, dict(REP, species=["ナゾノトリ"]))), 1)

    def test_restricted_center_writes_no_species(self):
        c = dict(C, allowed_fields=["state", "date", "url"])
        s = V.report_sentences(c, REP)
        self.assertEqual(len(s), 1)
        self.assertNotIn("ジョウビタキ", s[0])

    def test_species_kind(self):
        self.assertEqual(V.species_kind("ジョウビタキ"), "鳥")
        self.assertIsNone(V.species_kind("ナゾノトリ"))


class Verifier(unittest.TestCase):
    def test_generated_sentences_pass(self):
        self.assertEqual(codes(" ".join(V.report_sentences(C, REP)) + "\n"), [])

    def test_state_followed_by_species_in_brackets_fails(self):
        self.assertIn("vc_state_species_joined", codes("試験ビジターセンターは、11/6時点で色づき始めの草木の葉（ジョウビタキ）を発信しています。\n"))

    def test_species_without_kind_fails(self):
        self.assertIn("vc_species_without_kind", codes("試験ビジターセンターは、11/6時点で「色づき始めの草木の葉」と発信しています。同じ発信に、ジョウビタキの名があります。\n"))

    def test_species_elsewhere_in_the_answer_is_not_checked(self):
        self.assertEqual(codes("① 試験の森: この時期に見られる鳥はジョウビタキです。\n"), [])

    def test_unapproved_center_in_new_form_fails(self):
        n = next(c["name"] for c in V.load_centers() if (c.get("approval") or {}).get("status") == "pending")
        self.assertIn("visitor_center_not_approved", codes(f"{n}は、11/6時点で「見ごろ」と発信しています。\n"))


if __name__ == "__main__":
    unittest.main()
