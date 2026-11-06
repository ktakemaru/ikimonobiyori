"""段階54 第9部: 回帰テストの基盤。通信しない・書き込まない。

代表的な質問(data/regress/cases.yaml)ごとに、合成の入力(集めた事実と答えの文章)を検査器と共通の条件に通す。
これまでの試用で見つかった崩れ(作業報告が答えに出る・冒頭とおすすめの食い違い・出典の漏れ・日付の範囲表記・ウェザーニュース由来・
名称の誤一致・断定的な見込み・曜日の食い違い・承認待ちの情報源)を、今後の変更で再発させないためのもの。
- expect: ok → 検査が全部通ること。 expect_fail: [コード...] → 既知の崩れを検査が見つけること(見つけられなければ検査の劣化)。
- 入力は合成データ。実在のページの文章は使わない(山と溪谷オンライン由来は合成のみ)。
使い方: `python -X utf8 -m ikimonobiyori.regress [--case ID] [--json]`(docs/regression.md)。終了コード 0=すべて期待どおり、1=外れがある。"""
import argparse
import json
import re
import sys
from datetime import date

import yaml

from . import ask_verify as V
from .paths import DATA_FILES_DIR

CASES = DATA_FILES_DIR / "regress" / "cases.yaml"
WEEKDAYS = "月火水木金土日"
WD_RE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})\s*[(（]([月火水木金土日])")
RANGE_RE = re.compile(r"\d{1,2}/\d{1,2}\s*[～~〜-]\s*\d{1,2}/\d{1,2}\s*(?:時点|現在)")
LEAD_BAD_START = ("①", "②", "③", "出典", "根拠", "#", "-", "・", "*", "http")


def load_cases(path=None):
    return yaml.safe_load((path or CASES).read_text(encoding="utf-8"))


def build_facts(case):
    """合成の事実(candidates など)から ask facts の形を作る。"""
    f = case.get("facts")
    if not f:
        return None

    def spot(c):
        cur = None
        if c.get("state"):
            cur = {"state": c["state"], "state_raw": c["state"], "state_date": c.get("date"), "publisher": c.get("publisher", "試験サイト"),
                   "url": c.get("url", "https://kouyou.example.com/k"), "source_class": c.get("cls", "secondary"), "freshness": c.get("fresh", "fresh")}
        out = {"id": "t-" + c["name"], "name": c["name"], "city": c.get("city", "試験町"), "current": cur, "current_unknown": cur is None,
               "typical": [{"text": c["typ"], "url": "https://kouyou.example.com/t", "publisher": "試験サイト"}] if c.get("typ") else [],
               "events": c.get("events", []), "reason_labels": [], "history": []}
        if c.get("festivals"):
            out["festivals"] = c["festivals"]
        return out

    subj = f["subject"]
    doc = {"now": f.get("now", "2026-11-06T12:00:00+09:00"), "dates": f["dates"], "region": f.get("region", "神奈川"),
           "subjects": {subj: {"subject": subj, "candidates": [spot(c) for c in f["candidates"]], "avoid": [spot(c) for c in f.get("avoid", [])],
                               "alternatives": [], "nearby_out_of_region": []}},
           "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None}, "summary_pages": []}
    return doc


def common_checks(text, case, facts, policy_words, min_lead=0):
    """全部の答えに当てる共通の条件。→ [{code, detail}]"""
    errs = []
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or len(lines[0]) < min_lead or lines[0].lstrip().startswith(LEAD_BAD_START):
        errs.append({"code": "no_lead", "detail": "先頭に結論の文がない"})
    g = V.generic_check(text)
    for e in g["errors"]:
        if e["code"] in ("forbidden_phrase", "process_phrase", "dev_term", "internal_term", "typo"):
            errs.append({"code": "work_or_internal_word", "detail": e["detail"]})
    if RANGE_RE.search(text):
        errs.append({"code": "date_range", "detail": "状態の日付が範囲になっている"})
    low = text.lower()
    for w in policy_words["blocked"]:
        if w.lower() in low:
            errs.append({"code": "blocked_source", "detail": w})
    for w in policy_words["pending"]:
        if w in text:
            errs.append({"code": "pending_source", "detail": w})
    year = int(case.get("year", 2026))
    for m, d, wd in WD_RE.findall(text):
        try:
            real = WEEKDAYS[date(year, int(m), int(d)).weekday()]
        except ValueError:
            continue
        if real != wd:
            errs.append({"code": "weekday_mismatch", "detail": f"{m}/{d}({wd})"})
    return errs


def policy_words():
    from . import observations as O
    pol = O.load_policy()
    rec = pol["record"]
    blocked = list(O._v(rec["not_read_hosts"])) + list(O._v(pol["not_read_words"]))
    pending = ["山と溪谷オンライン掲載", "yamakei-online"] if not (rec.get("restricted_sources") or {}).get("approved") else []
    return {"blocked": blocked, "pending": pending}


def generated_text(g):
    """コードが組み立てる答え(通信しない)を、決まった日で作る。"""
    if g["kind"] == "species":
        from . import wildflower_species as WS
        return WS.species_answer(g["name"], month=g.get("month"), date_=g.get("date"))["text"]
    if g["kind"] == "overview":
        from . import wildflower
        return wildflower.overview(date_=g["date"], area=g.get("area"), site=g.get("site"))["text"]
    raise ValueError(g["kind"])


def run_case(case, words, min_lead=0):
    text = case["answer"] if "answer" in case else generated_text(case["generate"])
    facts = build_facts(case)
    errs = common_checks(text, case, facts, words, min_lead)
    if case.get("generate"):                      # コードが作る文は、聞き返しだけで終わらないなどの汎用の検査も通す
        errs += [{"code": e["code"], "detail": e.get("detail", "")} for e in V.generic_check(text)["errors"] if e["code"] not in ("ask_back_only", "too_few_candidates")]
    if facts is not None:
        r = V.check(text, facts, V.load_rules())
        for s in r["sentences"]:
            errs += [{"code": e["code"], "detail": e.get("detail", "")} for e in s["errors"]]
        errs += [{"code": e["code"], "detail": e.get("detail", "")} for e in r["answer_errors"]]
    got = sorted({e["code"] for e in errs})
    if case.get("expect") == "ok":
        ok = not got
        why = None if ok else f"通るはずの答えが落ちた: {got}"
    else:
        want = case["expect_fail"]
        missing = [c for c in want if c not in got]
        ok = not missing
        why = None if ok else f"既知の崩れを見つけられなかった: {missing}(見つけたもの: {got})"
    return {"id": case["id"], "question": case["question"], "ok": ok, "codes": got, "why": why}


def run_all(only=None, path=None):
    doc = load_cases(path)
    words = policy_words()
    min_lead = doc.get("min_lead_chars", 0)
    out = [run_case(c, words, min_lead) for c in doc["cases"] if not only or c["id"] == only]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ikimonobiyori.regress")
    ap.add_argument("--case")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = run_all(a.case)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in res:
            print(("OK   " if r["ok"] else "FAIL ") + f"{r['id']}: {r['question']}" + ("" if r["ok"] else f"  → {r['why']}"))
        print(f"{sum(r['ok'] for r in res)}/{len(res)} 件が期待どおり")
    return 0 if res and all(r["ok"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
