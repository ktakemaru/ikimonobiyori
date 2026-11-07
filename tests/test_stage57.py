"""段階57(指示書 docs/stage57-conversation-flow-instructions.md): 会話の流れの改善。通信しない。合成データだけ。"""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import ask, guide, offers as OF
from ikimonobiyori import ask_verify as V

ROOT = Path(__file__).resolve().parent.parent
RULES = V.load_rules()
OFFER = OF.all_texts()[0]


def run(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = mod.main(argv)
    return rc, out.getvalue().strip(), err.getvalue().strip()


class Part1UnsupportedThemes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_unsupported_theme_is_an_error_and_writes_no_page(self):
        for word in ("ホタル", "蛍"):
            out = Path(self.tmp.name) / "x.html"
            rc, stdout, err = run(guide, ["page", "--theme", word, "--out", str(out), "--no-ensure-photos"])
            self.assertNotEqual(rc, 0, word)
            self.assertEqual(stdout, "")
            self.assertIn("未対応", err)
            self.assertIn("野鳥", err)                                         # 対応の一覧を示す
            self.assertFalse(out.exists(), word)                              # 野鳥のページが誤って作られない

    def test_list_themes(self):
        rc, out, _ = run(guide, ["page", "--list-themes"])
        self.assertEqual(rc, 0)
        for w in ("野鳥", "花", "野草"):
            self.assertIn(w, out)

    def test_flower_page_is_not_written_under_the_bird_file_name(self):
        rc, out, _ = run(guide, ["page", "--theme", "花", "--date", "2026-11-08", "--no-ensure-photos"])
        self.assertEqual(rc, 0)
        self.assertEqual(Path(out).name, "flower-guide.html")
        self.assertIn("花の案内", Path(out).read_text(encoding="utf-8"))
        self.assertNotIn("野鳥の案内", Path(out).read_text(encoding="utf-8"))


class Part1Offers(unittest.TestCase):
    def test_conditions(self):
        ok = {"subject_supported": True, "plan": True, "photo_candidates": True}
        self.assertEqual(OF.texts(OF.available(ok)), [OFFER])
        for k in ok:
            self.assertEqual(OF.available({**ok, k: False}), [], k)           # 条件が 1 つでも欠けたら、案内の行を出さない

    def test_guide_answer_has_the_line_only_when_supported_and_photos_exist(self):
        rows = [{"entry": {"kinds": [{"kind": "ジョウビタキ", "shown": True}]}}]
        parts = {"sections": [{"key": "recommend", "rows": rows}]}
        self.assertEqual(guide._page_offer_lines(parts, {"野鳥"}), [OFFER])
        self.assertEqual(guide._page_offer_lines(parts, {"ホタル"}), [])
        self.assertEqual(guide._page_offer_lines({"sections": [{"key": "recommend", "rows": []}]}, {"野鳥"}), [])

    def test_free_form_offers_fail_the_check(self):
        for s in ("紅葉の写真つきページをお作りします。", "写真つきで紹介しましょうか。", "Artifact にします。", "ページを公開できます。", "図も作れます。"):
            self.assertEqual([e["code"] for e in V.offer_errors(s, [OFFER])], ["offer_not_allowed"], s)
        self.assertEqual(V.offer_errors(OFFER, [OFFER]), [])
        self.assertEqual([e["code"] for e in V.offer_errors(OFFER, [])], ["offer_not_allowed"])      # 条件を満たさないときは一覧の文でも不合格

    def test_generic_check_uses_the_list(self):
        text = "おすすめです。\n① あ\n② い\n③ う\n"
        self.assertTrue(V.generic_check(text + OFFER)["ok"])
        self.assertFalse(V.generic_check(text + "ほかのページもお作りします。")["ok"])
        self.assertFalse(V.generic_check(text + OFFER, offers=[])["ok"])

    def test_cannot_do_reply_is_one_line_plus_only_a_possible_offer(self):
        self.assertEqual(OF.unsupported_reply("蛍の写真つきページ"), ["今は蛍の写真つきページには対応していません。"])
        self.assertEqual(OF.unsupported_reply("蛍の写真つきページ", [{"id": "photo_page", "text": OFFER}]),
                         ["今は蛍の写真つきページには対応していません。", OFFER])
        rc, out, _ = run(ask, ["unsupported", "--what", "蛍の写真つきページ"])
        self.assertEqual((rc, out), (0, "今は蛍の写真つきページには対応していません。"))

    def test_rule_is_in_the_instructions(self):
        for f in ("CLAUDE.md", "AGENTS.md", ".claude/skills/ikimono-weekend/SKILL.md"):
            t = (ROOT / f).read_text(encoding="utf-8")
            self.assertIn("できないことを提案しない", t, f)
            self.assertIn("手書きの HTML・図で代用しない", t, f)


if __name__ == "__main__":
    unittest.main()
