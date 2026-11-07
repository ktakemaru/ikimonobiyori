"""質問の意図の分類と、知識を先にする答えの型(段階59 第7部)。通信しない。

意図: knowledge(知識)・difference(違い)・chat(雑談的な発見)・place_time(場所・時期)・now(今の状況)・plan(計画)。
知識の答えの順: どんなもの → 似たものとの違い → 見分け方・出会い方 → いつ・どこで(短く)→ ガイドの目(保全・安全)。名所の一覧を主にしない。事実は知識カードだけ。
語は data/knowledge/policy.yaml の intent。カードがないときは、先に調べて記録してから答える(「調べます」と書かない)。"""
import re

from . import knowledge as K
from . import pdf_text as PT
from .ask_verify import URL_RE, _n, load_rules, process_excuse_errors, question_errors


def cfg():
    return PT.policy()["intent"]


def classify(question):
    """質問の文 → 主たる意図。"""
    c = cfg()
    q = question or ""
    for name in c["order"]:
        if any(re.search(p, q) for p in c["patterns"][name]):
            return name
    return c["default"]


def topics(question, cards=None, env=None):
    """質問に出る語のうち、カードの場所・別名に当たるもの(長い語から)。"""
    rows = cards if cards is not None else K.load_shown(env)
    words = set()
    for r in rows:
        words.add(r.get("place") or "")
        words |= set(r.get("place_aliases") or [])
    q = question or ""
    hit = {w for w in words if w and w in q}
    hit = {w for w in hit if not any(w != x and w in x for x in hit)}    # 「冬桜」に含まれる「桜」は語にしない
    return sorted(hit, key=lambda w: (q.index(w), -len(w)))


def cards_for(question, cards=None, env=None, month=None):
    """質問に合うカード。語が当たらないときは、質問の型の語で分類を引く(「足元に面白いもの」→ 痕跡・暮らし)。"""
    c = cfg()
    rows = cards if cards is not None else K.load_shown(env)
    tp = topics(question, rows)
    hits = [r for r in rows if any(K.place_match(r, t) for t in tp)]
    if not hits:
        for pat, cat in c["category_words"].items():
            if re.search(pat, question or ""):
                hits += [r for r in rows if r.get("category") == cat and (not month or not K._months(r) or month in K._months(r))]
    order = {k: i for i, k in enumerate(c["section_order"])}
    uniq, seen = [], set()
    for r in sorted(hits, key=lambda r: (order.get(r.get("category"), len(order)), tp.index(next((t for t in tp if K.place_match(r, t)), tp[0])) if tp else 0, r["title"])):
        if r["title"] not in seen:
            seen.add(r["title"])
            uniq.append(r)
    return uniq


def compose(question, cards=None, env=None, month=None):
    """知識の答え(カードの事実と出典だけ)。カードがなければ None(先に調べて記録する)。"""
    c = cfg()
    kind = classify(question)
    rows = cards_for(question, cards, env, month)
    if not rows:
        return None
    limit = c["max_cards"][kind] if kind in c["max_cards"] else c["max_cards"]["knowledge"]
    use = rows[:limit]
    guide = [r for r in use if r.get("category") in c["guide_categories"]]
    main = [r for r in use if r not in guide]
    lines = []
    for r in main:
        lines.append(r["title"] + ": " + "。".join(x.rstrip("。") for x in r["facts"]) + f"({r['source']['name']})。")
    urls = [r["source"]["url"] for r in use if r["source"].get("url")]
    if guide:
        lines += [""] + [K.line_for(r) for r in guide]
    related = [r for r in rows[limit:] if r not in use][: c["max_related"]]
    if related and kind != "chat":
        lines += ["", c["related_heading"]] + [f"- {r['title']}: {r['facts'][0].rstrip('。')}({r['source']['name']})。" for r in related]
        urls += [r["source"]["url"] for r in related if r["source"].get("url")]
    if any(r.get("confidence") == "紹介" for r in use + related):
        lines += ["", c["secondary_note"]]
    lines += ["", c["sources_heading"]] + sorted(set(urls))
    return "\n".join(lines) + "\n"


def check(text, cards, rules=None):
    """知識の答えの検査: 先頭が名所の列挙でない・質問が出ない・「調べます」型が出ない・一覧にないと断らない・数字と出典がカードと一致する。"""
    c = cfg()
    rules = rules or load_rules()
    errs = process_excuse_errors(text, rules) + question_errors(text, rules)
    head = next((l for l in text.splitlines() if l.strip()), "")
    if re.match(c["list_head_re"], head):
        errs.append({"code": "knowledge_starts_with_list", "detail": head[:30]})
    for w in c["refuse_phrases"]:
        if w in text:
            errs.append({"code": "knowledge_refused", "detail": w})
    blob = _n("\n".join(" ".join(r["facts"]) + r["source"]["name"] for r in cards))
    for n in set(re.findall(r"\d[\d,.]*", URL_RE.sub(" ", _n(text)))):
        if n not in blob:
            errs.append({"code": "knowledge_fact_not_in_card", "detail": n})
    used_urls = {r["source"].get("url") for r in cards}
    for u in URL_RE.findall(text):
        if u not in used_urls:
            errs.append({"code": "knowledge_source_unused", "detail": u[:50]})
    for r in cards:
        if any(x.rstrip("。") in text for x in r["facts"]) and r["source"].get("url") and r["source"]["url"] not in text:
            errs.append({"code": "knowledge_source_missing", "detail": r["title"]})
    return errs
