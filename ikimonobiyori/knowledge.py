"""ネイチャーガイドの知識の層(段階59)。通信しない。カードの本体はリポジトリの外(IKIMONOBIYORI_DATA_DIR の下の knowledge/cards.jsonl)。

カード(1 枚 = 1 つの事実のまとまり): 題・分類・場所・事実(最大 5 項目・1 項目 60 字以内。自分の言葉)・条件(季節・年)・出典・確度・権利メモ・答えでの出し方。
年に依存する事実は年が必須。今年の現況と混ぜない。文章・図・写真を写さない。原文のような長い文は拒否する。値は data/knowledge/policy.yaml。"""
import json
import re
from pathlib import Path

from . import pdf_text as PT
from .paths import data_path

NL = chr(10)


def cfg():
    return PT.policy()["cards"]


def path(env=None):
    return Path(data_path(cfg()["file"], env))


def subject_names(card):
    """段階72 第2部 1: カードの主語(何の話か)の名前。subject・subject_aliases、なければ場所と場所の別名。"""
    names = [card.get("subject")] + list(card.get("subject_aliases") or [])
    names = [n for n in names if n]
    if not names:
        names = [n for n in [card.get("place")] + list(card.get("place_aliases") or []) if n]
    return names


def subject_errors(card, strict=False):
    """段階72 第2部 1: 事実の文に、何の話か(生き物・現象の名前)が書いてあるか。
    主語のない書き出し(policy の subject.subjectless_starts。「例年」「早朝」など)で始まり、主語の名前を含まない文は不合格。
    strict(新しく足すカード)では、subject が必須で、どの文にも主語の名前(subject・subject_aliases・場所)が要る。"""
    sc = cfg().get("subject") or {}
    names = subject_names(card)
    errs = []
    if strict and not card.get("subject"):
        errs.append("subject(何の話か。生き物・現象の名前)がない")
    if strict:
        names = names + [n for n in [card.get("place")] + list(card.get("place_aliases") or []) if n and n not in names]
    for f in card.get("facts") or []:
        if any(n in f for n in names):
            continue
        if strict or any(re.match(p, f) for p in sc.get("subjectless_starts") or []):
            errs.append(f"事実の文に何の話か(主語)がない: {f[:20]}")
    return errs


def subject_audit(cards=None, env=None):
    """段階72 第2部 1: 既存のカードの点検。主語のない文があるカード → [{title, place, url, facts: [主語のない文]}]。答えに出さないカードは除く。"""
    rows = cards if cards is not None else load(env)
    out = []
    for r in rows:
        if r.get("retired"):
            continue
        bad = [e.split(": ", 1)[1] for e in subject_errors(r) if ": " in e]
        if bad:
            out.append({"title": r.get("title"), "place": r.get("place"), "url": (r.get("source") or {}).get("url"), "facts": bad})
    return out


def validate(card, strict_subject=False):
    """→ エラーの一覧(空なら合格)。strict_subject: 新しく足すカードの主語の決まり(段階72 第2部 1。ask knowledge add)。"""
    c = cfg()
    errs = list(subject_errors(card, strict=True)) if strict_subject else []      # 既存のカード(読むとき)は点検の一覧(subject_audit)だけ
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
    from urllib.parse import urlparse
    from . import observations as O
    host = (urlparse(src.get("url") or "").hostname or "").lower()
    if any(host == b or host.endswith("." + b) for b in O.load_policy()["record"].get("rejected_hosts") or []):     # 段階62 第9部
        errs.append(f"出典のホスト {host} は使わない(本人が不採用と決めた情報源)")
    for k in c["source_required"]:
        if not src.get(k):
            errs.append(f"出典の {k} がない")
    errs += contrast_errors(card.get("contrasts"))
    errs += special_errors(card)
    return errs


def special_errors(card):
    """段階83 第3部・第4部: 季節の暦(calendar)と小話(tale)の項目の形。"""
    from . import guide_brief as GB
    errs = []
    cal = card.get("calendar")
    if cal is not None:
        C = GB.cfg()["calendar"]
        if not isinstance(cal, dict) or cal.get("environment") not in C["environments"]:
            errs.append(f"calendar.environment は {C['environments']} のどれか")
        elif not cal.get("months") or any(not isinstance(m, int) or not 1 <= m <= 12 for m in cal["months"]):
            errs.append("calendar.months は 1〜12 の月の一覧")
        elif cal.get("target") not in C["targets"]:
            errs.append(f"calendar.target は {C['targets']} のどれか")
        elif not cal.get("where"):
            errs.append("calendar.where(どの地域・標高の話か)がない")
    tale = card.get("tale")
    if tale is not None and (not isinstance(tale, dict) or not tale.get("topic")):
        errs.append("tale.topic(何の話か: 名前の由来・人との関わり・歴史・文学や行事)がない")
    return errs


def contrast_errors(items):
    """段階82 の続き(本人の判断 2026-11-13 の 1): 2 つの種を比べる見分け方のカードの項目 contrasts
    [{a: [種の名前], a_re: 特徴の語(正規表現), b: [種の名前], b_re: 特徴の語(正規表現。片側だけの比べ方なら空)}] の形の検査。"""
    if items is None:
        return []
    if not isinstance(items, list) or not items:
        return ["contrasts は 1 つ以上の項目の配列"]
    errs = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errs.append(f"contrasts[{i}] がオブジェクトでない")
            continue
        for side in ("a", "b"):
            names = it.get(side)
            if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
                errs.append(f"contrasts[{i}].{side} は種の名前の配列")
            try:
                re.compile(it.get(side + "_re") or "")
            except re.error as e:
                errs.append(f"contrasts[{i}].{side}_re が正規表現として読めない: {e}")
        if not it.get("a_re"):
            errs.append(f"contrasts[{i}].a_re(a の種の特徴の語)が要る")
        if set(it.get("a") or []) & set(it.get("b") or []):
            errs.append(f"contrasts[{i}] の a と b に同じ種")
    return errs


def set_contrasts(title, items, *, at, place=None, note=None, env=None):
    """カードに contrasts(どちらの種が、どの特徴か)を付ける(控えを残す)。特徴の語は出典の本文と照らしてから(照らすのは付ける人)。"""
    def fn(card):
        card["contrasts"] = items
        errs = validate(card)
        if errs:
            raise ValueError("; ".join(errs))
        return card
    return _change(title, place, fn, "set_contrasts", at=at, note=note, env=env)


def add(card, env=None, strict_subject=False):
    """カードを足す。不合格なら ValueError。同じ題・同じ場所のカードは置き換える。"""
    errs = validate(card, strict_subject=strict_subject)
    if errs:
        raise ValueError("; ".join(errs))
    rows = [r for r in load(env) if (r["title"], r.get("place")) != (card["title"], card.get("place"))]
    rows.append(card)
    p = path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return card


def _change(title, place, fn, action, *, at, note=None, env=None):
    """段階80 F(提案5): 1 枚のカード(題名と、指定があれば場所で 1 枚に絞る)を fn で直して書き戻す。
    変更の前と後のカードを控え(changes_file)に残す。当たるカードが 1 枚でなければ ValueError。"""
    rows = load(env)
    hits = [i for i, r in enumerate(rows) if r.get("title") == title and (place is None or r.get("place") == place)]
    if len(hits) != 1:
        raise ValueError(f"題名「{title}」" + (f"・場所「{place}」" if place is not None else "") + f"のカードが {len(hits)} 枚(1 枚に絞る。場所は --place)")
    before = rows[hits[0]]
    after = fn(json.loads(json.dumps(before, ensure_ascii=False)))
    rows[hits[0]] = after
    log = Path(data_path(cfg()["changes_file"], env))
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": at, "action": action, "note": note, "before": before, "after": after}, ensure_ascii=False) + NL)
    p = path(env)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + NL for r in rows), encoding="utf-8")
    return after


def rename(title, new_title, *, at, place=None, note=None, env=None):
    """カードの題名を変える(控えを残す)。同じ場所に同じ題名のカードがあれば ValueError。"""
    new_title = (new_title or "").strip()
    if not new_title or new_title == title:
        raise ValueError("新しい題名がない・元と同じ")

    def fn(card):
        if any(r.get("title") == new_title and r.get("place") == card.get("place") for r in load(env)):
            raise ValueError(f"同じ場所に題名「{new_title}」のカードがすでにある")
        card["title"] = new_title
        errs = validate(card)
        if errs:
            raise ValueError("; ".join(errs))
        return card
    return _change(title, place, fn, "rename", at=at, note=note, env=env)


def retire(title, reason, *, at, place=None, env=None):
    """カードを取り下げる(消さずに retired の印。答えには出なくなる。控えを残す)。"""
    if not (reason or "").strip():
        raise ValueError("取り下げの理由(--reason)が要る")

    def fn(card):
        card["retired"] = True
        card["retired_reason"] = reason.strip()
        card["retired_at"] = at
        return card
    return _change(title, place, fn, "retire", at=at, note=reason, env=env)


def add_fact(title, fact, narrative, *, at, place=None, note=None, env=None):
    """段階80 の追記2(本人の判断 2026-11-11): カードに事実を 1 行足す(語りの種類も 1 つ。控えを残す)。
    事実は出典の本文と照らしてから足す(照らすのは足す人。同じ文がすでにあれば ValueError)。"""
    fact = (fact or "").strip()
    if not fact or not (narrative or "").strip():
        raise ValueError("足す事実(--fact)と語りの種類(--narrative)が要る")

    def fn(card):
        if fact in (card.get("facts") or []):
            raise ValueError("同じ事実がすでにある")
        card["facts"] = list(card.get("facts") or []) + [fact]
        if card.get("narrative") is not None:
            card["narrative"] = list(card["narrative"]) + [narrative.strip()]
        errs = validate(card)
        if errs:
            raise ValueError("; ".join(errs))
        return card
    return _change(title, place, fn, "add_fact", at=at, note=note, env=env)


def load(env=None):
    p = path(env)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _centers():
    from . import visitor_centers as VC
    return VC.load_centers()


def usable(card, centers=None):
    """段階60 第9部: 答えに出してよいカードか → (可否, 理由)。
    確度が施設のもの(施設の観察記録・解説・発信)は、出典の施設が施設台帳で承認待ち・取り消しなら出さない(台帳にない施設は従来どおり)。
    公的資料・研究機関の解説は、権利メモが確認済みのときだけ。紹介(紹介サイト。公式ではないと明記して出す)はこれまでどおり。"""
    g = cfg()["gate"]
    if card.get("retired"):                                   # 段階62 第9部: 出典を差し替えて作り直した古いカード(宮ヶ瀬の 2010 年の資料など)は出さない
        return False, "retired"
    conf = card.get("confidence")
    name = (card.get("source") or {}).get("name") or ""
    if conf in g["facility_confidences"]:
        cs = _centers() if centers is None else centers
        hit = next((c for c in cs if name and (name == c["name"] or name in c["name"])), None)
        if hit is None:
            return True, "facility_not_in_ledger"          # 施設台帳にない施設は従来どおり(段階59 のテストの前提。台帳に足せば承認まで隠れる)
        if (hit.get("approval") or {}).get("status") != "approved":
            return False, "facility_pending"
        return True, None
    if conf in g["public_confidences"]:
        if not str(card.get("rights") or "").startswith(g["rights_confirmed_prefix"]):
            return False, "rights_unconfirmed"
    return True, None


def is_special(card):
    """段階83 第3部・第4部: 季節の暦(calendar)と小話(tale)のカード。ふつうの選び方では使わず、資料が決まった数だけ足す。"""
    return bool(card.get("calendar") or card.get("tale"))


def calendar_tags(env=None):
    """段階83 第3部: 既存のカードに付けた季節の暦の札(データ置き場の knowledge/calendar_tags.jsonl。1 行 1 件:
    {title, place, environment, months, target, where})。カードは複製しない(ふつうの選び方もそのまま)。"""
    p = Path(data_path(PT.policy()["cards"].get("calendar_tags_file") or "knowledge/calendar_tags.jsonl", env))
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def calendar_pool(env=None, centers=None):
    """季節の暦の材料: calendar の項目を持つカードと、札を付けた既存のカード(札の calendar を付けた写し)。"""
    rows = load_shown(env, centers, include_special=True)
    tags = {}
    for t in calendar_tags(env):
        tags[(t.get("title"), t.get("place"))] = t
    out = []
    for r in rows:
        if r.get("calendar"):
            out.append(r)
            continue
        t = tags.get((r.get("title"), r.get("place")))
        if t and not is_special(r):
            out.append({**r, "calendar": {k: t[k] for k in ("environment", "months", "target", "where") if k in t}, "calendar_tag": True})
    return out


def load_shown(env=None, centers=None, include_special=False):
    """答えに出してよいカードだけ(承認されれば自動で出る)。季節の暦・小話のカードは include_special のときだけ。"""
    cs = _centers() if centers is None else centers
    return [r for r in load(env) if usable(r, cs)[0] and (include_special or not is_special(r))]


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
    rows = cards if cards is not None else load_shown(env)
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
    year = c["year_prefix"].format(year=cond["year"]) if cond.get("year_dependent") and not has_year_in_facts(card) else ""
    return c["line"].format(year=year, facts=facts, source=card["source"]["name"])


def plain_line(card):
    """段階67 第4部 2: 見出しの下に置く行(「ガイドの目:」を付けない)。事実と出典。"""
    c = cfg()
    return c["before_line"].format(facts="。".join(x.rstrip("。") for x in card["facts"][: c["max_facts_in_answer"]]), source=card["source"]["name"])


def has_year_in_facts(card):
    """段階67 第4部 4(承認欄 G): 事実の中に年(「2026年」)があるカードは「○年の記録では」の前置きを付けない。"""
    c = cfg()
    facts = card.get("facts") or []
    return any(re.search(r"(19|20)\d{2}年", f) for f in facts[: c["max_facts_in_answer"]])


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
    rows = cards if cards is not None else load_shown(env)
    allowed = [line_for(r) for r in rows]
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith(c["line_prefix"]):
            continue
        if s not in allowed:
            errs.append({"code": "guide_eye_not_from_card", "detail": s[:40]})
    return errs


# ---- 段階82 第3部 2: カードの主題のテーマ(苔・滝・湿原など。data/ask/themes.yaml) ----

def themes_cfg():
    from . import yamlcache
    from .paths import DATA_FILES_DIR
    return yamlcache.load(DATA_FILES_DIR / "ask" / "themes.yaml")


def themes_of(card, tc=None):
    """カード → テーマの名前の一覧(題・主題にテーマの語があるか、事実の min_fact_hits 行以上にあるもの)。"""
    tc = tc or themes_cfg()
    head = " ".join([card.get("title") or "", card.get("subject") or ""])
    out = []
    for t in tc["themes"]:
        ws = t["words"]
        n = sum(1 for f in card.get("facts") or [] if any(w in f for w in ws))
        if any(w in head for w in ws) or n >= tc["min_fact_hits"]:
            out.append(t["name"])
    return out


NL_ = chr(10)


def tag_themes(env=None, dry_run=False):
    """今あるカードに themes 欄を付ける(題と本文の語から機械的に)。→ {cards, tagged, by_theme}。カードの本体はデータ置き場の下。"""
    rows = load(env)
    tc = themes_cfg()
    by, tagged = {}, 0
    for r in rows:
        ts = themes_of(r, tc)
        if ts:
            tagged += 1
            for t in ts:
                by[t] = by.get(t, 0) + 1
        if ts:
            r["themes"] = ts
        else:
            r.pop("themes", None)
    if not dry_run and rows:
        p = path(env)
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + NL_ for r in rows), encoding="utf-8")
    return {"cards": len(rows), "tagged": tagged, "by_theme": by}

