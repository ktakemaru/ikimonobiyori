"""段階54 第9部: 回帰テストの基盤。通信しない・書き込まない。

代表的な質問(data/regress/cases.yaml)ごとに、合成の入力(集めた事実と答えの文章)を検査器と共通の条件に通す。
これまでの試用で見つかった崩れ(作業報告が答えに出る・冒頭とおすすめの食い違い・出典の漏れ・日付の範囲表記・ウェザーニュース由来・
名称の誤一致・断定的な見込み・曜日の食い違い・承認待ちの情報源)を、今後の変更で再発させないためのもの。
- expect: ok → 検査が全部通ること。 expect_fail: [コード...] → 既知の崩れを検査が見つけること(見つけられなければ検査の劣化)。
- 入力は合成データ。実在のページの文章は使わない(山と溪谷オンライン由来は合成のみ)。
段階57 第6部: 連続した会話のシナリオ(data/regress/flows.yaml)も通す(書き込みは一時フォルダだけ)。
使い方: `python -X utf8 -m ikimonobiyori.regress [--case ID] [--json]`(docs/regression.md)。終了コード 0=すべて期待どおり、1=外れがある。"""
import argparse
import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

import yaml

from . import answer_plan as AP
from . import ask_verify as V
from .paths import DATA_FILES_DIR

CASES = DATA_FILES_DIR / "regress" / "cases.yaml"
FLOWS = DATA_FILES_DIR / "regress" / "flows.yaml"
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
        if c.get("window"):                           # 段階56: 計画の見込みに使う例年の窓 [開始MM-DD, 終了MM-DD]
            out["typical"] = [{"text": c.get("typ") or "例年", "start": c["window"][0], "end": c["window"][1], "url": "https://kouyou.example.com/t", "publisher": "試験サイト"}]
        for k_src, k_dst in (("km", "distance_km"), ("rel", "relation"), ("elev", "elevation_m"), ("age", None)):
            if c.get(k_src) is not None and k_dst:
                out[k_dst] = c[k_src]
        if cur and c.get("age") is not None:
            cur["age_days"] = c["age"]
        return out

    subj = f["subject"]
    doc = {"now": f.get("now", "2026-11-06T12:00:00+09:00"), "dates": f["dates"], "region": f.get("region", "神奈川"),
           "subjects": {subj: {"subject": subj, "candidates": [spot(c) for c in f["candidates"]], "avoid": [spot(c) for c in f.get("avoid", [])],
                               "alternatives": [], "nearby_out_of_region": []}},
           "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None}, "summary_pages": []}
    if f.get("visitor_centers"):                      # 段階55: 承認済みの施設の事実（合成）
        doc["visitor_centers"] = f["visitor_centers"]
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
    from . import visitor_centers as VC            # 段階55: 承認待ちの施設の「○○発信」を答えに出さない
    pending += [c["name"] + "発信" for c in VC.pending_centers()]
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
        plan = None
        if case.get("plan"):                          # 段階56: 計画を通す形。答えの①②③が計画のおすすめと合っていること
            plan = AP.build(facts, case["facts"]["subject"], overrides=case.get("overrides"))
        r = V.check(text, facts, V.load_rules(), plan=plan)
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


# ---- 段階57 第6部: 連続した会話のシナリオ(合成データ。書き込みは一時フォルダだけ) ----

def _flow_spot(row, dates):
    d = dates[0]
    cur = {"state": "見頃", "state_raw": "見頃", "display": "見頃", "state_date": "2026-11-05", "publisher": "試験市", "url": f"https://kouyou.example.org/{row['city']}",
           "source_class": "official", "freshness": "fresh", "age_days": 2, "read_at": "2026-11-07T09:00:00+09:00"}
    out = {"id": "t-" + row["name"], "name": row["name"], "city": row["city"], "prefecture": "神奈川県", "current": cur, "current_unknown": False, "distance_km": row["km"],
           "typical": [{"text": "例年11月", "start": "11-01", "end": "11-30", "url": "https://kouyou.example.org/t", "publisher": "試験市"}], "events": [], "history": [],
           "reason_labels": [], "practical": [], "festivals": [], "relation": "in_peak", "tree_species": row.get("trees") or [], "flower_kinds": row.get("flowers") or []}
    if row.get("elev"):
        out["elevation_m"] = row["elev"]
    if row.get("birds"):
        out["park_birds"] = [{"name": n, "kind": "recent", "kind_label": "最近の記録", "why": "今季の記録があります。", "date": "2026-11-05"} for n in row["birds"]]
    return out


def compose_answer(facts, plan):
    """計画から、検査に通る合成の答えを組み立てる(シナリオ用。事実は facts の値だけ)。"""
    from .plan_page import plan_subjects
    subs = plan_subjects(plan)
    labels = AP.load_policy()["segment_headings"]
    lines = [("・".join(labels.get(sj, sj) for sj, _ in subs) if len(subs) > 1 else "次の場所") + "を楽しめそうです。"]
    urls = []

    def block(pl, sj):
        cands = {c["name"]: c for c in facts["subjects"][sj]["candidates"]}
        out = ["今回のおすすめ"]
        for i, p in enumerate(pl["picks"]):
            c = cands[p["name"]]
            cur = c["current"]
            season = "この時期に見られる鳥は" + "・".join(b["name"] for b in c.get("park_birds") or []) + "です" if sj == "birds" else "例年の見頃は11月です"
            phrase = f"{p['phrase']}。" if p.get("phrase") else ""
            note = f"{p['note']}。" if p.get("note") else ""
            out.append(f"{chr(0x2460 + i)} {p['name']}: {cur['display']}(11/5時点、{cur['publisher']})。{season}。{phrase}{note}")
            urls.append(cur["url"])
        return out
    if len(subs) > 1:
        for seg in plan["segments"]:
            pl = plan["subjects"][seg["subject"]]
            lines += ["", seg["heading"], f"{seg['heading']}を楽しめそうです。"] + block(pl, seg["subject"])
    else:
        lines += block(subs[0][1], subs[0][0])
    lines += ["", "確かさの補足", "アクセスや混雑は出かける前に公式ページで確認してください。", "", "出典"] + sorted(set(urls))
    return "\n".join(lines) + "\n"


def run_flow(flow, doc, env, workdir, now):
    from . import ask
    from .plan_page import plan_subjects
    subjects = {}
    for sj in flow["subjects"]:
        rows = doc["subjects"].get(sj)
        subjects[sj] = {"subject": sj, "candidates": [_flow_spot(r, flow["dates"]) for r in rows or [{"name": "蛍の沢", "city": "沢町", "km": 30}]],
                        "avoid": [], "nearby_out_of_region": [], "alternatives": []}
    facts = {"schema": "ikimono-ask-facts/1", "now": now.isoformat(), "dates": flow["dates"], "origin": "横浜", "region": "全範囲", "subjects": subjects,
             "lines": {"answer_rules": "stage51", "practical_rules": True, "open_urls": None}, "summary_pages": [], "this_round": {}}
    f = ask.Flow(workdir, now=now, env=env)
    f._save("facts.json", facts)
    problems = []
    plan = None
    for st in flow["steps"]:
        if st["do"] == "unsupported_page":
            try:
                f.page()
                problems.append("未対応の対象でページが作られた")
            except ask.PageUnsupported:
                pass
            continue
        if st["do"] == "refine":
            plan = f.plan(refine=st["word"])
            continue
        if st["do"] == "answer":
            plan = plan or f.plan()
            text = compose_answer(facts, plan)
            (f.workdir / "answer.txt").write_text(text, encoding="utf-8")
            r, _final = f.verify(text)
            if not r["ok"]:
                problems += [f"検査に落ちた: {x}" for x in V.report_lines(r)]
            continue
        if st["do"] == "page":
            html = Path(f.page()["path"]).read_text(encoding="utf-8")
            for sj, pl in plan_subjects(plan):
                for p in pl["picks"]:
                    if p["name"] not in html:
                        problems.append(f"ページに今回のおすすめ「{p['name']}」がない")
                if sj == "birds" and len(plan_subjects(plan)) == 1:
                    continue
                for s in pl["sections"]:
                    if s["label"] not in html:
                        problems.append(f"ページに節「{s['label']}」がない")
            continue
    return problems


def run_flows(path=None, now=None):
    from datetime import datetime, timedelta, timezone
    doc = yaml.safe_load((path or FLOWS).read_text(encoding="utf-8"))
    now = now or datetime(2026, 11, 7, 12, 0, tzinfo=timezone(timedelta(hours=9)))
    out = []
    for flow in doc["flows"]:
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IKIMONOBIYORI_DATA_DIR": tmp}
            problems = run_flow(flow, doc, env, Path(tmp) / "work", now)
        out.append({"id": flow["id"], "question": flow["question"], "ok": not problems, "codes": [], "why": "; ".join(problems) or None})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ikimonobiyori.regress")
    ap.add_argument("--case")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = run_all(a.case) + ([] if a.case else run_flows())
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        for r in res:
            print(("OK   " if r["ok"] else "FAIL ") + f"{r['id']}: {r['question']}" + ("" if r["ok"] else f"  → {r['why']}"))
        print(f"{sum(r['ok'] for r in res)}/{len(res)} 件が期待どおり")
    return 0 if res and all(r["ok"] for r in res) else 1


if __name__ == "__main__":
    sys.exit(main())
