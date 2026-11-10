"""段階78 第3部 1: 語りの材料(通信しない)。

知識カードの文を、次の種類に分けて、資料の新しい節「語りの材料」に並べる(1 つの答えで合わせて 4〜8 点)。
- なぜ今: なぜこの時期・この場所で見られるのか
- どこをどう見る: 現地で目を向ける場所・時間帯・歩き方
- 見分け方: 似たものとの違い
- 次の季節: このあと何が起きるか
カードの文ごとの種類はカードの項目 `narrative`(文と同じ並びの種類の一覧)。項目がなければ、文の語とカードの分類から機械的に分ける
(分けられない文は「その他」で、材料にしない)。材料がない種類は「材料なし」と資料に書く(AI が無理に作らないため)。
値と語は data/ask/guide_mode.yaml の narrative。"""
import re


def cfg():
    from . import guide_brief as GB
    return GB.cfg()["narrative"]


def classify_fact(text, category=None, N=None):
    """カードの文 1 つ → 種類(なぜ今・どこをどう見る・見分け方・次の季節・その他)。語の決まり → 分類の既定 → その他。"""
    N = N or cfg()
    t = text or ""
    from . import guide_brief as GB
    v = GB.values(t)
    if re.search(N["not_material_re"], t) or v["years"] or v["times"] or v["money"] or v["phones"]:
        return N["other"]                                # 語りではない事実(行事・開園・料金・年つきの事実)
    for rule in N["word_rules"]:
        if any(re.search(w, t) for w in rule["words"]):
            return rule["kind"]
    return (N.get("by_category") or {}).get(category) or N["other"]


def kinds_of(card, N=None):
    """カード → 文ごとの種類。カードに narrative があればそれを使う(文の数と合わなければ分け直す)。"""
    N = N or cfg()
    facts = card.get("facts") or []
    got = card.get("narrative")
    if isinstance(got, list) and len(got) == len(facts) and all(k in N["kinds"] + [N["other"]] for k in got):
        return list(got)
    return [classify_fact(f, card.get("category"), N) for f in facts]


def annotate(cards, N=None):
    """カードの一覧に narrative の項目を足す(すでにあるカードはそのまま)。→ (カードの一覧, 足した枚数)。"""
    N = N or cfg()
    out, n = [], 0
    for c in cards:
        if isinstance(c.get("narrative"), list) and len(c["narrative"]) == len(c.get("facts") or []):
            out.append(c)
            continue
        out.append({**c, "narrative": kinds_of(c, N)})
        n += 1
    return out, n


def materials(cards, N=None):
    """資料のカード(id つき)→ {items: [{kind, card, title, place, text}], missing: [種類]}。
    種類の順に、1 種類 per_kind_max 点まで、合わせて max_items 点まで。"""
    N = N or cfg()
    pool = {k: [] for k in N["kinds"]}
    for k in cards or []:
        for text, kind in zip(k.get("facts") or [], k.get("narrative_kinds") or kinds_of(k, N)):
            if kind in pool:
                pool[kind].append({"kind": kind, "card": k.get("id"), "title": k.get("title"), "place": k.get("place"), "text": text})
    items = []
    for rnd in range(N["per_kind_max"]):
        for kind in N["kinds"]:
            if len(items) >= N["max_items"]:
                break
            if rnd < len(pool[kind]):
                items.append(pool[kind][rnd])
    order = {k: i for i, k in enumerate(N["kinds"])}
    items.sort(key=lambda x: order[x["kind"]])
    return {"items": items, "missing": [k for k in N["kinds"] if not pool[k]]}


def extra_cards(shown, have, names, words, months, N=None, require_words=()):
    """語りの材料が少ないときに足すカード(候補の場所・種の語・テーマの語に結びつき、その他でない文があるもの)。"""
    from . import knowledge as K
    N = N or cfg()
    seen = {(k.get("title"), k.get("place")) for k in have}
    scored = []
    for r in shown:
        if (r.get("title"), r.get("place")) in seen or isinstance(r.get("closure"), dict):
            continue
        kinds = [k for k in kinds_of(r, N) if k in N["kinds"]]
        if not kinds:
            continue
        ms = (r.get("condition") or {}).get("months") or []
        if ms and months and not set(ms) & set(months):
            continue
        blob = " ".join([r.get("title") or "", r.get("subject") or "", r.get("place") or ""] + list(r.get("facts") or []))
        if require_words and not any(w in blob for w in require_words):
            continue                                     # 種の質問: その種の話のカードだけ
        score = 0
        if any(K.place_match(r, n) for n in names if n and len(n) >= 2):
            score += 3
        score += sum(1 for w in words if w and w in blob)
        if score:
            scored.append((-score, -len(set(kinds)), r.get("title") or "", r))
    scored.sort(key=lambda x: x[:3])
    return [r for *_x, r in scored[: N["extra_cards"]]]


def render(mat, N=None):
    """資料の Markdown の節。"""
    N = N or cfg()
    L = ["## 語りの材料", "", N["md_note"], ""]
    by = {}
    for it in mat.get("items") or []:
        by.setdefault(it["kind"], []).append(it)
    for kind in N["kinds"]:
        L.append(f"### {kind}")
        if by.get(kind):
            L += [f"- [{it['card']}] {it['text']}({it.get('place') or ''})" for it in by[kind]]
        else:
            L.append(f"- {N['none']}")
    return L + [""]
