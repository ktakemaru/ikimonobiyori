"""段階63a 第7部: 受け入れケース 10 件(docs/ikimonobiyori-design-review-proposal.md 第7節)と、ask answer の答えの総当たり(1,000 件)。
通信しない。合成データだけ。"""
import random
import unittest
from datetime import date, datetime, timedelta, timezone

import helpers as H  # noqa: F401  (通信禁止)

from ikimonobiyori import answer_gates as AG, answer_plan as AP, answer_run as AR
from ikimonobiyori import ask_verify as V, polish as PL, skeleton as SK

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=JST)
NL = "\n"
CANNOT = "答えを用意できません"
RULES = V.load_rules()


def spot(name, km=20, state="見頃", date_="2026-11-07", city=None, subject="autumn_leaves", source_class="official", fresh=True, **kw):
    cur = {"state": state, "state_raw": state, "display": state, "state_date": date_, "publisher": "試験市", "url": f"https://kouyou.example.org/{name}",
           "source_class": source_class, "freshness": "fresh" if fresh else "stale", "age_days": 1, "read_at": "2026-11-07T09:00:00+09:00"} if state else None
    return {"id": "t-" + name, "name": name, "city": city or (name + "町"), "prefecture": kw.pop("prefecture", "神奈川県"), "current": cur,
            "current_unknown": cur is None, "distance_km": km,
            "typical": [{"text": "例年11月", "start": "11-01", "end": "11-30", "url": "https://kouyou.example.org/t", "publisher": "試験市", "source_class": "official"}],
            "typical_line": "例年の見頃: 11月", "events": [], "history": [], "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak",
            "subject": subject, **kw}


def subj(sj, *cands):
    return {"subject": sj, "candidates": list(cands), "avoid": [], "nearby_out_of_region": [], "alternatives": []}


def facts_doc(subjects, dates=("2026-11-08",), **extra):
    return {"schema": "ikimono-ask-facts/1", "now": NOW.isoformat(), "dates": list(dates), "origin": "横浜", "region": "全範囲", "subjects": subjects,
            "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None, "origin_line": "横浜からの距離で選びました。"},
            "summary_pages": [], "this_round": {}, "knowledge_cards": [], **extra}


def three():
    return facts_doc({"autumn_leaves": subj("autumn_leaves", spot("試験の谷", 10), spot("試験の滝", 60), spot("試験の湖", 150))})


def answer(f, plan=None, **kw):
    plan = plan or AP.build(f, "autumn_leaves")
    return AR.answer_from_facts(f, plan, **kw), plan


def body(t):
    return t.split("出典")[0]


def ok_text(tc, t, label=""):
    tc.assertTrue(t.strip(), label)
    tc.assertNotIn(CANNOT, t, label)
    tc.assertEqual(V.question_errors(t, RULES), [], label)
    tc.assertEqual(V.internal_word_errors(t), [], label)


def inject(text, name, extra):
    return NL.join(l + extra if l.startswith(("①", "②", "③")) and name in l else l for l in text.splitlines()) + NL


class Acceptance(unittest.TestCase):
    """レビュー第7節の受け入れケース。期待する状態・答えの内容・外した主張・記録を確かめる。"""

    def test_01_all_facts_confirmed_gives_pass(self):
        got, _ = answer(three())
        self.assertEqual((got["status"], got["stage"]), (AR.STATUS_PASS, 2))
        ok_text(self, got["text"])
        for n in ("試験の谷", "試験の滝", "試験の湖"):
            self.assertIn(n, got["text"])

    def test_02_one_spot_without_a_confirmable_source_is_removed_and_the_others_kept(self):
        f = three()
        plan = AP.build(f, "autumn_leaves")
        g = AR.gate_check(inject(SK.compose(f, plan), "試験の滝", "詳しくは https://unknown.example.org/taki を見てください。"), f, plan, ())
        got = AR.partial_answer(f, plan, g, [], False, ())
        self.assertEqual((got["status"], got["removed"]), (AR.STATUS_DEGRADED, ["試験の滝"]))
        self.assertIn("試験の谷", got["text"])
        self.assertNotIn("unknown.example.org", got["text"])

    def test_03_missing_date_evidence_is_not_asserted(self):
        f = facts_doc({"autumn_leaves": subj("autumn_leaves", spot("試験の谷", 10, date_=None), spot("試験の湖", 150))})
        got, _ = answer(f)
        line = next(l for l in got["text"].splitlines() if "試験の谷" in l and l.startswith(("①", "②", "③")))
        self.assertNotIn("時点", line)                                       # 日付を断定しない
        self.assertIn("試験の湖", got["text"])                                # 確認済みの範囲は答える
        ok_text(self, got["text"])

    def test_04_a_number_that_does_not_match_the_source_is_not_adopted(self):
        f = three()
        plan = AP.build(f, "autumn_leaves")
        g = AR.gate_check(inject(SK.compose(f, plan), "試験の湖", "駐車場は1234台です。"), f, plan, ())
        self.assertIn("unknown_number", [e["code"] for e in g["errors"]])     # 問題を記録する
        got = AR.partial_answer(f, plan, g, [], False, ())
        self.assertNotIn("1234", got["text"])
        ok_text(self, got["text"])

    def test_05_unreadable_source_is_stated_as_unconfirmed(self):
        f = facts_doc({"autumn_leaves": subj("autumn_leaves", spot("試験の谷", 10), spot("試験の湖", 150, state=None))},
                      fetch={"failed": [{"url": "https://kouyou.example.org/mizuumi", "reason": "403"}]})
        f["lines"]["open_urls"] = "公式ページ(ご自身で開いてください): https://kouyou.example.org/mizuumi"
        got, _ = answer(f)
        ok_text(self, got["text"])
        t = got["text"]
        if "試験の湖" in t:
            self.assertTrue(any(w in t for w in ("確認できていません", "分かりません")))
        self.assertNotIn("試験の湖: 今の状況は", t)                            # 根拠のない主張(今の状況)を書かない

    def test_06_dangerous_guidance_is_removed_and_the_rest_answered(self):
        f = three()
        plan = AP.build(f, "autumn_leaves")
        phrase = RULES["stage51"]["assertive_phrases"][0]
        g = AR.gate_check(inject(SK.compose(f, plan), "試験の谷", f"今週末は{phrase}。"), f, plan, ())
        got = AR.partial_answer(f, plan, g, [], False, ())
        self.assertEqual(got["status"], AR.STATUS_BLOCKED)
        self.assertNotIn(phrase, got["text"])
        self.assertIn("試験の湖", got["text"])

    def test_07_polish_that_changes_a_number_or_date_is_caught_and_the_data_wins(self):
        f = three()
        plan = AP.build(f, "autumn_leaves")
        sk = SK.compose(f, plan)
        bad = sk.replace("11/7時点", "11/5時点", 1)
        got = AR.answer_from_facts(f, plan, polished=bad)
        self.assertNotEqual(got["stage"], 1)
        self.assertNotIn("11/5時点", got["text"])
        self.assertIn("polish_fixed_line_changed", [w["code"] for w in got["warnings"]])

    def test_08_no_usable_candidate_still_gives_reason_and_how_to_check(self):
        f = facts_doc({"autumn_leaves": subj("autumn_leaves")})
        got, plan = answer(f)
        ok_text(self, got["text"])
        self.assertIn(AP.load_policy()["answer_run"]["minimal"]["how_heading"], AR.minimal_answer(f, plan))

    def test_09_a_record_is_not_a_claim_that_it_can_be_seen_now(self):
        old = spot("鳥の沼", subject="birds", fresh=False)
        f = facts_doc({"birds": subj("birds", old)})
        codes = [e["code"] for s in V.check("鳥の沼では今もカモが見られます。" + NL, f)["sentences"] for e in s["errors"]]
        self.assertIn("now_visible_unsupported", codes)
        self.assertEqual(AG.gate_of("now_visible_unsupported"), "safety")

    def test_10_style_only_issues_are_warnings_and_do_not_fail(self):
        f = three()
        plan = AP.build(f, "autumn_leaves")
        text = SK.compose(f, plan).replace("出典", "公式ではない情報もあります。公式ではない情報は参考です。" + NL + NL + "出典", 1)   # 表現の繰り返し(品質)
        ev = AG.evaluate(text, f, plan)
        self.assertTrue(ev["ok"], AG.errors_of(ev))
        self.assertIn("repeated_phrase", [w["code"] for w in ev["warnings"]])


# ---- 総当たり(段階63 第3部を ask answer の答えに対して行う) ----

STATES = [None, "見頃", "色づき始め", "まだ", "見頃過ぎ", "◎", "△", "コスモス: 現在2～3分咲きです"]
PREFS = ["神奈川県", "東京都", "埼玉県"]
LEGEND = {"◎": "真っ盛り", "△": "色づき始め"}


def random_facts(rng):
    subjects = rng.sample(["autumn_leaves", "flowers", "birds"], rng.randint(1, 3))
    subjects.sort(key=["autumn_leaves", "flowers", "birds"].index)
    dates = ["2026-11-08"] if rng.random() < 0.6 else ["2026-11-14", "2026-11-15"]
    out = {}
    for sj in subjects:
        cands = []
        for i in range(rng.randint(0, 6)):
            st = rng.choice(STATES)
            d = None if rng.random() < 0.15 else (date(2026, 11, 8) - timedelta(days=rng.randint(0, 12))).isoformat()
            kw = {}
            if rng.random() < 0.3:
                kw["festivals"] = [{"name": f"まつり{i}", "url": f"https://matsuri.example.org/{sj}{i}", "period_line": f"主催者が設定した期間: まつり期間中(11/1〜11/30)"}]
            if rng.random() < 0.3:
                kw["practical"] = [{"text": f"開園 9:00〜16:30", "url": f"https://park.example.org/{sj}{i}"}]
            if rng.random() < 0.15:
                kw["notices"] = [{"text": "一部の園路が通行止め", "date": "2026-11-06", "url": f"https://park.example.org/n{sj}{i}"}]
            if rng.random() < 0.2:
                kw["typical"] = []
                kw["typical_line"] = None
                kw["typical_unknown"] = True
            name = f"試{sj[:2]}{i}の{'谷滝湖森丘池'[i % 6]}"
            c = spot(name, km=rng.choice([None, 8, 25, 48, 70, 140, 230]), state=st, date_=d, subject=sj,
                     source_class=rng.choice(["official", "official", "secondary"]), fresh=rng.random() < 0.6,
                     prefecture=rng.choice(PREFS), city=rng.choice(["横浜市", "町田市", "秩父市", "平塚市", name + "町"]), **kw)
            if c.get("current") and st in LEGEND:                              # 材料(facts)では、記号は凡例の語で表示する(observations の display)
                c["current"]["display"] = LEGEND[st]
            if sj == "birds":
                c["season_line"] = "この時期に見られる鳥: カモの記録があります"
                c["park_birds"] = []
            cands.append(c)
        out[sj] = subj(sj, *cands)
    f = facts_doc(out, dates=dates)
    if len(dates) == 2 and rng.random() < 0.5:
        f["periods"] = [{"dates": ["2026-11-08"], "subjects": out}, {"dates": dates, "subjects": out}]
        f["dates"] = ["2026-11-08"] + dates
    if rng.random() < 0.3:
        f["region"] = "東京か神奈川"
    return f, subjects


def plan_for(f, subjects):
    if f.get("periods"):
        plan = AP.build_periods(f)
    elif len(subjects) > 1:
        plan = AP.build_all(f)
    else:
        plan = AP.build(f, subjects[0])
    AP.attach_region_parts(plan, f)
    plan["offers"] = []
    return plan


class Exhaustive(unittest.TestCase):
    N = 1000

    def test_ask_answer_always_gives_a_body(self):
        rng = random.Random(6301)
        stages = {}
        for i in range(self.N):
            f, subjects = random_facts(rng)
            plan = plan_for(f, subjects)
            got = AR.answer_from_facts(f, plan, defaulted=rng.random() < 0.5)
            stages[got["stage"]] = stages.get(got["stage"], 0) + 1
            ok_text(self, got["text"], f"case {i}")
            self.assertEqual(got["stage"], 2, f"case {i}: 骨組みが検査に通らない {[(e['code'], e['detail'][:40]) for e in got['errors']]}")   # 段階63 第3部
        self.__class__.stages = stages
        self.assertEqual(sum(stages.values()), self.N)


if __name__ == "__main__":
    unittest.main()
