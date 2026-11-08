"""必須の4つの検査(段階63a 第2部)。通信しない。

これまでの検査器(ask_verify.check など)の判定はそのまま使い、結果を答えの仕様(data/ask/answer_contract.json)で分ける:
- 事実の照合・安全・整合・出力可能 → 合否に使う(どれかが不合格なら、その答えは使わない。第3部で候補ごとに外す)
- 自動修正(内部用語・作業の事情・質問・提案の文の削除、出典の作り直し、字数の超過) → コードが直してから、もう一度検査する
- 警告 → 合否に使わない(記録にだけ残す)
4つ以外の検査を合否に使わない。新しい検査は、先に答えの仕様で分類する(分類のない ID は事実の検査として扱う)。"""
import json
import re

from . import answer_plan as AP
from . import ask_verify as V
from . import offers as OF
from .paths import DATA_FILES_DIR

CONTRACT_PATH = DATA_FILES_DIR / "ask" / "answer_contract.json"
GATES = ("fact", "safety", "consistency", "output")
_CONTRACT = None


def contract():
    global _CONTRACT
    if _CONTRACT is None:
        _CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return _CONTRACT


def gate_of(code):
    """検査の ID → 'fact' / 'safety' / 'consistency' / 'output' / 'warn'。分類のない ID は事実の検査。"""
    c = contract()
    for g in GATES:
        if code in c["gates"][g]["codes"]:
            return g
    if code in c["warn"]["codes"]:
        return "warn"
    return "fact"


def autofix_kind(code):
    a = contract()["autofix"]
    for k in ("delete_sentence", "rebuild_sources", "reduce_candidates"):
        if code in a[k]:
            return k
    return None


# ---- 自動修正 ----

def _sources_heading():
    return AP.load_policy()["skeleton"]["sources_heading"]


def _is_sources_heading(line):
    return re.fullmatch(r"\s*[#*\s]*" + re.escape(_sources_heading()) + r"\s*[:：]?\s*[*]*\s*", line) is not None


def _bad_sentence(s, facts, plan, rules, allowed_offers):
    """答えから外す文か(内部用語・作業の事情・作業の報告・質問・一覧にない提案・試していないのに読めていないと書く文)。"""
    body = V.URL_RE.sub(" ", s)
    if not body.strip():
        return False
    if V.term_errors(body, rules) or V.internal_word_errors(body, rules) or V.process_excuse_errors(body, rules) or V.question_errors(body, rules):
        return True
    if V.offer_errors(body, allowed_offers):
        return True
    st = rules.get("stage51") or {}
    if any(p in body for p in st.get("work_report_phrases") or []):
        return True
    if any(w in body for w in rules.get("reread_words") or []):
        return True
    if facts is not None and V.not_tried_errors(body, facts):
        return True
    from . import intent
    if any(w in body for w in (intent.cfg().get("refuse_words") or [])):
        return True
    return False


def delete_bad_sentences(text, facts=None, plan=None, rules=None, offers=None):
    """出典の見出しより前の文のうち、外す文を消す。空になった行・番号だけの行は消す。→ (直した文, 消した文の一覧)"""
    rules = rules or V.load_rules()
    allowed = offers if offers is not None else OF.texts((plan or {}).get("offers"))
    out, removed, in_sources = [], [], False
    for line in text.splitlines():
        if in_sources or _is_sources_heading(line):
            in_sources = True
            out.append(line)
            continue
        if V.URL_RE.fullmatch(line.strip() or "-"):
            out.append(line)
            continue
        parts = re.findall(r"[^。]+。?", line) or [line]
        kept = []
        for p in parts:
            if _bad_sentence(p, facts, plan, rules, allowed):
                removed.append(p.strip())
            else:
                kept.append(p)
        new = "".join(kept)
        if line.strip() and not new.strip():
            continue
        if re.fullmatch(r"\s*([*・\-]|[①-⑳]|\d+\.)\s*", new):
            continue
        out.append(new)
    return "\n".join(out).rstrip() + "\n", removed


def rebuild_sources(text, facts, plan, rules=None):
    """出典の一覧を、本文で使った事実の出どころだけにする(検査器の source_unused・source_missing と同じ対応表 V.source_map を使う)。
    → (直した文, {"added": [...], "removed": [...]})"""
    rules = rules or V.load_rules()
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines) if _is_sources_heading(l)), None)
    body_lines = lines if idx is None else lines[:idx]
    tail = [] if idx is None else lines[idx + 1:]
    listed, rest_tail = [], []
    for j, l in enumerate(tail):
        if V.URL_RE.search(l) and (l.strip().startswith("http") or l.strip().startswith("-") or l.strip().startswith("・") or "(http" in l
                                    or l.strip().startswith("気象庁")):
            listed.append(l)
        elif l.strip():
            rest_tail = tail[j:]
            break
    body = "\n".join(body_lines)
    m = V.source_map(body + "\n", facts, plan, rules)
    allowed, required = m["allowed"], m["required"]
    keep, removed = [], []
    for l in listed:
        us = [u.rstrip("/") for u in V.URL_RE.findall(l)]
        if all(u in allowed for u in us):
            keep.append(l)
        else:
            removed.append(l.strip())
    have = {u.rstrip("/") for l in keep for u in V.URL_RE.findall(l)} | {u.rstrip("/") for u in V.URL_RE.findall(body)}
    added = [u for u in sorted(required) if u not in have]
    keep += added
    out = list(body_lines)
    while out and not out[-1].strip():
        out.pop()
    if keep:
        out += ["", _sources_heading()] + keep
    if rest_tail:
        out += [""] + rest_tail
    return "\n".join(out).rstrip() + "\n", {"added": added, "removed": removed}


def length_limit(plan, text=None):
    """字数の上限(答えの仕様の length)。対象・期間の節と、地域の数で広げる。"""
    L = contract()["length"]
    segs = AP.split_segments(text, plan) if text is not None else None
    n_seg = len(segs) if segs else max(1, len((plan or {}).get("segments") or []))
    n_reg = len((plan or {}).get("region_parts") or [])
    return L["base"] + L["per_segment"] * (n_seg - 1) + L["per_region"] * max(0, n_reg - 1)


def autofix(text, facts, plan, offers=None, rules=None):
    """→ (直した文, 直した内容の記録)。"""
    rules = rules or V.load_rules()
    fixed, removed = delete_bad_sentences(text, facts, plan, rules, offers)
    fixed, src = rebuild_sources(fixed, facts, plan, rules) if facts is not None else (fixed, {"added": [], "removed": []})
    return fixed, {"deleted_sentences": removed, "sources": src}


# ---- 判定 ----

def evaluate(text, facts, plan, gazetteer=(), offers=None, rules=None):
    """答えの文 → {ok, gates: {fact: [...], ...}, warnings: [...], autofix_left: [...]}。ok は必須の4つの検査に合格。"""
    rules = rules or V.load_rules()
    out = {g: [] for g in GATES}
    warnings, left = [], []
    if not (text or "").strip():
        out["output"].append({"code": "empty_answer", "detail": "空の答え"})
        return {"ok": False, "gates": out, "warnings": [], "autofix_left": []}
    r = V.check(text, facts, rules, gazetteer, plan=plan, offers=offers)
    errs = [{**e, "line": x["line"]} for x in r["sentences"] for e in x["errors"]] + [dict(e) for e in r["answer_errors"]]
    limit = length_limit(plan, text)
    for e in errs:
        code = e["code"]
        if code == "too_long":
            if len(text) > limit:
                warnings.append({**e, "detail": f"{len(text)} 字(目安 {limit} 字)"})
            continue
        if autofix_kind(code):
            if code in contract()["gates"]["output"]["codes"]:
                out["output"].append(e)                                    # 直せなかった質問の文は出力可能の不合格
            elif gate_of(code) == "warn" or code in contract()["warn"]["codes"]:
                warnings.append(e)
            else:
                left.append(e)
                warnings.append(e)
            continue
        g = gate_of(code)
        (warnings if g == "warn" else out[g]).append(e)
    return {"ok": not any(out.values()), "gates": out, "warnings": warnings, "autofix_left": left}


def run(text, facts, plan, gazetteer=(), offers=None, rules=None):
    """自動修正 → 4つの検査。→ {ok, text(直した文), gates, warnings, fixed}"""
    fixed, how = autofix(text, facts, plan, offers, rules)
    ev = evaluate(fixed, facts, plan, gazetteer, offers, rules)
    return {**ev, "text": fixed, "fixed": how}


def errors_of(ev):
    return [{**e, "gate": g} for g in GATES for e in ev["gates"][g]]


# ---- 問題の局所化(段階63a 第3部) ----

def localize(errors, text, plan):
    """検査の不合格を、候補(場所)ごと・主張(文)ごとに分ける。→ {"by_candidate": {名所: [誤り]}, "by_line": {行番号: [誤り]}, "general": [誤り]}
    候補の名前は、その誤りの行と詳細から探す(共通の地域名で別の名所を取り違えない)。"""
    from . import skeleton as SK
    lines = text.splitlines()
    picks = [p["name"] for p in SK._flat_picks(plan or {})]
    blocks = V.candidate_blocks(text)
    out = {"by_candidate": {}, "by_line": {}, "general": []}
    for e in errors:
        ln = e.get("line")
        where = (lines[ln] if isinstance(ln, int) and 0 <= ln < len(lines) else "")
        if not where:                                                     # 行のない誤り(答え全体の検査): 詳細の文がある行を探す
            core = (e.get("detail") or "").strip()
            core = core.split(": ", 1)[-1] if core.startswith(("紅葉:", "花:", "野鳥:")) else core
            hit = next((i for i, l in enumerate(lines) if len(core) >= 6 and core[:30] in l), None)
            if hit is not None:
                ln, where = hit, lines[hit]
        hay = V._n(where + " " + (e.get("detail") or ""))
        blk = next((b for b in blocks if where and where in b), None) if where else None
        names = [n for n in picks if any(f in V._n(blk.splitlines()[0] if blk else hay) for f in V.strict_names(n))]
        if names:
            for n in names[:1]:
                out["by_candidate"].setdefault(n, []).append(e)
        elif isinstance(ln, int):
            out["by_line"].setdefault(ln, []).append(e)
        else:
            out["general"].append(e)
    return out


def drop_lines(text, line_numbers):
    """主張(行)ごとに外す。番号つきの候補の行は外さない(候補は計画から外す)。"""
    keep = []
    for i, l in enumerate(text.splitlines()):
        if i in line_numbers and not re.match(r"^\s*[①-⑳]", l):
            continue
        keep.append(l)
    return "\n".join(keep).rstrip() + "\n"


# ---- 文書(段階63a 第6部): docs/answer-checks.md は、この仕様から作る(手で二重に管理しない) ----

def doc_text():
    c = contract()
    d = c.get("descriptions") or {}
    L = c["length"]
    out = ["# 答えの検査(自動で作る文書。手で直さない)", "",
           "> この文書は `ikimonobiyori/data/ask/answer_contract.json`(答えの仕様)から `python -X utf8 -m ikimonobiyori.answer_gates doc --write` で作る。",
           "> 仕様を直したら作り直す(`tests/test_stage63a.py` が一致を確かめる)。段階63a(2026-11-08)。", "",
           "## 答えの形と流れ", "",
           "質問 → `ask answer`(`ikimonobiyori/answer_run.py`)→ 記録から材料・計画・骨組み → 自動修正 → 必須の4つの検査 → 答え。",
           "フォールバックの順: " + " → ".join(f"{i + 1} {x}" for i, x in enumerate(c["fallback"])) + "。どの段でも空の答えにしない。", "",
           "| 状態 | 意味 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in c["status"].items()] + [""]
    out += ["## 必須の4つの検査(合否に使う)", ""]
    for g in GATES:
        G = c["gates"][g]
        out += [f"### {G['label']}(`{g}`)", "", G["what"], "", "| 検査のID | 見ること |", "|---|---|"]
        out += [f"| `{x}` | {d.get(x, '')} |" for x in G["codes"]] + [""]
    out += ["## 自動修正(コードが直してから、もう一度4つの検査を通す)", "", c["autofix"]["note"], ""]
    names = {"delete_sentence": "その文を消す", "rebuild_sources": "出典の一覧を本文の事実から作り直す", "reduce_candidates": "点数の低い候補から減らす"}
    for k in ("delete_sentence", "rebuild_sources", "reduce_candidates"):
        out += [f"### {names[k]}(`{k}`)", "", "| 検査のID | 見ること |", "|---|---|"] + [f"| `{x}` | {d.get(x, '')} |" for x in c["autofix"][k]] + [""]
    out += ["## 警告(合否に使わない。記録だけ)", "", c["warn"]["note"], "", "| 検査のID | 見ること |", "|---|---|"]
    out += [f"| `{x}` | {d.get(x, '')} |" for x in c["warn"]["codes"]] + [""]
    out += ["## 字数の上限", "", L["note"], "", f"- 基本: {L['base']} 字", f"- 対象・期間の節が 1 つ増えるごと: +{L['per_segment']} 字",
            f"- 地域が 1 つ増えるごと: +{L['per_region']} 字", "",
            "## 新しい検査を足すとき", "",
            "4つの検査で扱えない理由と、それを捉えるテストを書いてから、先にこの仕様で分類する。分類のない ID は事実の検査として扱われる(合否に使う)。", ""]
    return "\n".join(out)


def main(argv=None):
    import argparse
    import sys
    ap = argparse.ArgumentParser(prog="answer_gates")
    ap.add_argument("cmd", choices=["doc"])
    ap.add_argument("--write", action="store_true", help="docs/answer-checks.md に書く(開発のときだけ)")
    a = ap.parse_args(argv)
    text = doc_text()
    if a.write:
        from .paths import PKG
        (PKG.parent / "docs" / "answer-checks.md").write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
