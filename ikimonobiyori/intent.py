"""質問の意図の分類と、知識を先にする答えの型(段階59 第7部)。通信しない。

意図: knowledge(知識)・difference(違い)・chat(雑談的な発見)・place_time(場所・時期)・now(今の状況)・plan(計画)。
知識の答えの順: どんなもの → 似たものとの違い → 見分け方・出会い方 → いつ・どこで(短く)→ ガイドの目(保全・安全)。名所の一覧を主にしない。事実は知識カードだけ。
語は data/knowledge/policy.yaml の intent。カードがないときは、先に調べて記録してから答える(「調べます」と書かない)。"""
import re

from . import facility_events as FE
from . import jma_normals as JN
from . import knowledge as K
from . import pdf_text as PT
from .ask_verify import URL_RE, _n, internal_word_errors, load_rules, process_excuse_errors, question_errors, term_errors


def cfg():
    return PT.policy()["intent"]


def classify(question):
    """質問の文 → 主たる意図。"""
    c = cfg()
    q = question or ""
    if JN.match(q):                                  # 段階61 第1部: 平年の目安の質問(「東京の紅葉は、平年はいつ頃?」)は知識の答えの型
        return "normal"
    if FE.match(q):                                  # 段階61 第2部: 観察会・講座・展示の質問(行事の台帳。承認済みの施設だけ)
        return "event"
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
    keys = set(JN.match(question))                   # 段階61 第1部: 平年の目安の質問は、同じ種目の観測の決め方のカード(jma_phenomena)を先に
    jc = [r for r in rows if keys & set(r.get("jma_phenomena") or [])]
    if jc:
        hits = [r for r in hits if r not in jc]
    order = {k: i for i, k in enumerate(c["section_order"])}
    for pat, cat in (c.get("category_first") or {}).items():
        if re.search(pat, question or ""):
            order = {**order, cat: -1}
    uniq, seen = [], set()
    for r in jc:
        if r["title"] not in seen:
            seen.add(r["title"])
            uniq.append(r)
    for r in sorted(hits, key=lambda r: (order.get(r.get("category"), len(order)), tp.index(next((t for t in tp if K.place_match(r, t)), tp[0])) if tp else 0, r["title"])):
        if r["title"] not in seen:
            seen.add(r["title"])
            uniq.append(r)
    return uniq


def scope_limit(key, **kw):
    """段階62 第1部 2: 範囲の限界の文(利用者の語。ask/policy.yaml の scope_limit_lines)。"""
    return load_rules()["scope_limit_lines"][key].format(**kw)


def event_none_line(question):
    """行事が見つからないときの 1 行(「確認できている公式ページの範囲では、今週末の観察会・行事は見つかりませんでした。」)。"""
    pol = FE.policy()
    when = next((w for w in pol["when_words"] if w in (question or "")), pol["when_default"])
    return scope_limit("events_none", when=when)


def compose(question, cards=None, env=None, month=None, today=None, events=None):
    """知識の答え(カードの事実と出典だけ)。カードがなければ None(先に調べて記録する)。
    行事の質問は、承認済みの施設の行事の行だけ(なければ None)。today は行事の日付と比べる日(省くと今日)。"""
    c = cfg()
    kind = classify(question)
    if kind == "event":
        from datetime import date as _date
        ev, ev_urls = FE.lines_for(question, today or _date.today(), events)
        if not ev:
            return None
        return "\n".join(ev + ["", scope_limit("events_other"), "", c["sources_heading"]] + ev_urls) + "\n"
    rows = cards_for(question, cards, env, month)
    normals, normal_src = JN.lines_for(question)     # 段階61 第1部: 気象庁の標本木・観測の平年の目安(カードとは別。出典と加工の明記つき)
    if not rows and not normals:
        return None
    limit = c["max_cards"][kind] if kind in c["max_cards"] else c["max_cards"]["knowledge"]
    use = rows[:limit]
    guide = [r for r in use if r.get("category") in c["guide_categories"]]
    if len(guide) == len(use):                       # 段階61 第3部: 保全・安全のカードしかないときは、質問が名指しした種・場所のカードを本文に置く
        named = set(topics(question, rows))
        guide = [r for r in guide if r.get("place") not in named]
    main = [r for r in use if r not in guide]
    lines = list(normals) + ([""] if normals and main else [])
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
    years = sorted({(r.get("condition") or {}).get("year") for r in use if (r.get("condition") or {}).get("year_dependent")
                    and r.get("category") in (c.get("past_note_categories") or [])} - {None})
    if years and c.get("now_words") and any(w in (question or "") for w in c["now_words"]):    # 段階61 第4部: 年つきの調査の数は今年の現況ではない
        lines += ["", c["past_season_note"].format(year=years[-1])]
    if normal_src:                                   # 出典の行に同じ URL があるので、URL だけの行は重ねない
        urls = [u for u in urls if u not in normal_src]
    lines += ["", c["sources_heading"]] + ([normal_src] if normal_src else []) + sorted(set(urls))
    return "\n".join(lines) + "\n"


def check(text, cards, rules=None):
    """知識の答えの検査: 先頭が名所の列挙でない・質問が出ない・「調べます」型が出ない・一覧にないと断らない・数字と出典がカードと一致する。"""
    c = cfg()
    rules = rules or load_rules()
    errs = process_excuse_errors(text, rules) + question_errors(text, rules) + JN.answer_errors(text)
    normal_blob = _n("\n".join([JN.policy()["text"]["source_line"]] + _normal_values()))
    head = next((l for l in text.splitlines() if l.strip()), "")
    if re.match(c["list_head_re"], head):
        errs.append({"code": "knowledge_starts_with_list", "detail": head[:30]})
    for w in c["refuse_phrases"]:
        if w in text:
            errs.append({"code": "knowledge_refused", "detail": w})
    blob = _n("\n".join(" ".join(r["facts"]) + r["source"]["name"] + str((r.get("condition") or {}).get("year") or "") for r in cards))   # 年に依存する知識の年(ガイドの目の「○年の記録では」)もカードの事実
    for n in set(re.findall(r"\d[\d,.]*", URL_RE.sub(" ", _n(text)))):
        if n not in blob and n not in normal_blob:
            errs.append({"code": "knowledge_fact_not_in_card", "detail": n})
    used_urls = {r["source"].get("url") for r in cards} | {JN.policy()["source"]["page"]}
    for u in URL_RE.findall(text):
        if u not in used_urls:
            errs.append({"code": "knowledge_source_unused", "detail": u[:50]})
    for r in cards:
        if any(x.rstrip("。") in text for x in r["facts"]) and r["source"].get("url") and r["source"]["url"] not in text:
            errs.append({"code": "knowledge_source_missing", "detail": r["title"]})
    return errs


def check_event(text, today, events=None, rules=None):
    """行事の答えの検査(意図が event のとき。知識カードの検査と名所の候補数の下限は当てない)。
    台帳との照合(facility_events.answer_errors)+ 作業の事情・内部用語・答えの中の質問(既存の規則)。"""
    rules = rules or load_rules()
    if events is None:                                   # 段階62 第6部: 行事の台帳と記録済みの行事の索引
        from . import event_index as EI
        events = EI.build(today)
    return (FE.answer_errors(text, today, events) + process_excuse_errors(text, rules) + question_errors(text, rules)
            + [{"code": e["code"], "detail": e["detail"]} for e in term_errors(text, rules) + internal_word_errors(text, rules)])


def _normal_values():
    """平年の目安の表の数字(検査で、カードにない数字として落とさないため)。表の行の文そのもの。"""
    doc = JN.load()
    return [JN.line(e) for e in (doc or {}).get("entries") or []]
