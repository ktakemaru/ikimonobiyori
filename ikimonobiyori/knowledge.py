"""ネイチャーガイドの知識の層(段階59)。通信しない。カードの本体はリポジトリの外(IKIMONOBIYORI_DATA_DIR の下の knowledge/cards.jsonl)。

カード(1 枚 = 1 つの事実のまとまり): 題・分類・場所・事実(最大 5 項目・1 項目 60 字以内。自分の言葉)・条件(季節・年)・出典・確度・権利メモ・答えでの出し方。
年に依存する事実は年が必須。今年の現況と混ぜない。文章・図・写真を写さない。原文のような長い文は拒否する。値は data/knowledge/policy.yaml。"""
import json
import re
from pathlib import Path

from . import pdf_text as PT
from .paths import data_path


def cfg():
    return PT.policy()["cards"]


def path(env=None):
    return Path(data_path(cfg()["file"], env))


def validate(card):
    """→ エラーの一覧(空なら合格)。"""
    c = cfg()
    errs = []
    for k in c["required"]:
        if not card.get(k):
            errs.append(f"{k} がない")
    if card.get("category") and card["category"] not in c["categories"]:
        errs.append(f"分類は {c['categories']} のどれか")
    if card.get("confidence") and card["confidence"] not in c["confidences"]:
        errs.append(f"確度は {c['confidences']} のどれか")
    facts = card.get("facts") or []
    if len(facts) > c["max_facts"]:
        errs.append(f"事実は {c['max_facts']} 項目まで")
    for f in facts:
        if len(f) > c["max_fact_chars"]:
            errs.append(f"事実は {c['max_fact_chars']} 字以内: {f[:20]}")
        if "「" in f or "」" in f:
            errs.append(f"引用符で原文を残さない: {f[:20]}")
        if len(re.findall(r"[。]", f)) > c["max_sentences"]:
            errs.append(f"原文のような長い文: {f[:20]}")
    cond = card.get("condition") or {}
    if cond.get("year_dependent") and not cond.get("year"):
        errs.append("年に依存する事実には年が要る")
    src = card.get("source") or {}
    for k in c["source_required"]:
        if not src.get(k):
            errs.append(f"出典の {k} がない")
    return errs


def add(card, env=None):
    """カードを足す。不合格なら ValueError。同じ題・同じ場所のカードは置き換える。"""
    errs = validate(card)
    if errs:
        raise ValueError("; ".join(errs))
    rows = [r for r in load(env) if (r["title"], r.get("place")) != (card["title"], card.get("place"))]
    rows.append(card)
    p = path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return card


def load(env=None):
    p = path(env)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _months(card):
    return set((card.get("condition") or {}).get("months") or [])


def search(env=None, place=None, category=None, month=None, text=None, cards=None):
    """場所・分類・月・語で探す。"""
    rows = cards if cards is not None else load(env)
    out = []
    for r in rows:
        if place and not place_match(r, place):
            continue
        if category and r.get("category") != category:
            continue
        if month and _months(r) and month not in _months(r):
            continue
        if text and text not in (r["title"] + " ".join(r["facts"])):
            continue
        out.append(r)
    return out


def place_match(card, place):
    names = [card.get("place") or ""] + list(card.get("place_aliases") or [])
    return any(len(n) >= 2 and (n in place or place in n) for n in names)     # 1 文字の語(桜など)では当てない


def select(places, month=None, cards=None, env=None, topics=()):
    """答えに添える「ガイドの目」の候補(最大 max_shown 枚)。場所の一致が必須、季節の一致、分類の優先(安全・保全マナーを先に)でコードが決める。"""
    c = cfg()
    rows = cards if cards is not None else load(env)
    pri = {k: i for i, k in enumerate(c["category_priority"])}
    hits = []
    for r in rows:
        if not any(place_match(r, p) for p in places):
            continue
        ms = _months(r)
        if month and ms and month not in ms:
            continue
        hits.append(r)
    hits.sort(key=lambda r: (pri.get(r.get("category"), len(pri)), r["title"]))
    return hits[: c["max_shown"]]


def line_for(card):
    """「ガイドの目」の 1 行(カードの事実だけ。年に依存する知識は年を明記)。"""
    c = cfg()
    cond = card.get("condition") or {}
    facts = "。".join(x.rstrip("。") for x in card["facts"][: c["max_facts_in_answer"]])
    year = c["year_prefix"].format(year=cond["year"]) if cond.get("year_dependent") else ""
    return c["line"].format(year=year, facts=facts, source=card["source"]["name"])


def split_lines(cards):
    """安全の知識は「行く前に」の欄へ、ほかは「ガイドの目」の欄へ。→ (ガイドの目の行, 行く前の行, 出典の URL)。"""
    c = cfg()
    eye, before, urls = [], [], []
    for r in cards:
        (before if r.get("category") in c["before_categories"] else eye).append(line_for(r) if r.get("category") not in c["before_categories"] else c["before_line"].format(facts="。".join(x.rstrip("。") for x in r["facts"][: c["max_facts_in_answer"]]), source=r["source"]["name"]))
        if r["source"].get("url"):
            urls.append(r["source"]["url"])
    return eye, before, urls


def answer_errors(text, cards, env=None):
    """検査: 「ガイドの目」の行の事実がカードと一致するか、出典が合っているか、原文のような長い文でないか。"""
    c = cfg()
    errs = []
    rows = cards if cards is not None else load(env)
    allowed = [line_for(r) for r in rows]
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith(c["line_prefix"]):
            continue
        if s not in allowed:
            errs.append({"code": "guide_eye_not_from_card", "detail": s[:40]})
    return errs
