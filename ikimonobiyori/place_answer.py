"""場所を指定した質問(「西沢渓谷や大菩薩嶺の紅葉はどう?」)の材料(段階57 第10部)。通信しない。

- 質問から場所名を取り出し、名所の一覧と照合する(同名・類似名を取り違えない。あいまいなときは「一致なし」)。
- 名所の一覧にある場所: 場所ごとの事実(今年の現況・例年の見頃・見込み・行事・実用情報・距離)を返す。
- ない場所: 読むべき公式ページの探し方(検索語)と、使わないホストを除いた検索結果の絞り込み。読めた事実は「仮」として記録する。
値・語は data/ask/plan.yaml の place。"""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

from . import answer_plan as AP
from . import ask_verify as V
from . import observations as O
from .paths import DATA_FILES_DIR, data_path


def cfg():
    return AP.load_policy()["place"]


def extract_names(question):
    """「西沢渓谷や大菩薩嶺の紅葉はどう?」→ [西沢渓谷, 大菩薩嶺]。助詞「や・と・、・」で区切る。"""
    c = cfg()
    q = re.sub(c["tail_re"], "", question or "")
    q = re.sub(c["head_re"], "", q)
    out = []
    for w in re.split(c["split_re"], q):
        w = re.sub(r"(周辺|あたり|付近)$", "", w.strip())
        if len(w) >= 2 and w not in c["stop_words"] and w not in out:
            out.append(w)
    return out


def _key(x):
    return re.sub(r"[・\s]", "", x or "")


def _norm(x):
    return V._n(x or "").replace(" ", "")


ALIAS_PATH = O.PLACE_ALIAS_PATH
ALIAS_CACHE = O.PLACE_ALIAS_LOCAL


def alias_table(env=None):
    return O.place_alias_table(env)


def add_alias(alias, official, env=None):
    """確かめた別名をデータ置き場に足す(次回から使う)。"""
    p = Path(data_path(ALIAS_CACHE, env))
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    doc[alias] = official
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=0), encoding="utf-8")


def official_name(name, env=None):
    """別名 → 正式名称(「・」「の」の有無の違いを無視して引く)。ないときは入力のまま。"""
    table = alias_table(env)
    key = lambda s: re.sub(r"[・\s]", "", s)
    k = key(name or "")
    for a, o in table.items():
        if key(a) == k:
            return o
    return name


def match(name, cands):
    """→ 候補か None。完全一致(名前・別名・短い形)→ 名前が質問の語を含むものが 1 件だけ → 質問の語が名前を含むものが 1 件だけ。ほかは取り違えを避けて None。"""
    q = _norm(name)
    exact = [c for c in cands if q == _norm(c.get("name")) or q in {_norm(a) for a in c.get("aliases") or []} or q in {_norm(f) for f in V.short_names(c.get("name") or "")}]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    if len(q) < cfg()["min_partial_chars"]:
        return None
    part = [c for c in cands if q in _norm(c.get("name"))]
    if len(part) == 1:
        return part[0]
    if part:
        return None
    wider = [c for c in cands if len(_norm(c.get("name"))) >= cfg()["min_partial_chars"] and _norm(c.get("name")) in q]
    return wider[0] if len(wider) == 1 else None


def blocked_host(url, policy=None):
    policy = policy or O.load_policy()
    return O._blocked_host(urlparse(url or "").hostname, policy)


def filter_results(rows, policy=None):
    """検索結果の絞り込み。使わないホスト、民間の予想・その転載(英語圏の旅行サイトの引用を含む)を落とす。
    rows: [{url, title, snippet}]。全国の予測は公的・公式のものだけ。"""
    c = cfg()
    policy = policy or O.load_policy()
    words = list(O._v(policy.get("not_read_words") or {"value": []})) + c["forecast_reprint_words"]
    out = []
    for r in rows:
        if blocked_host(r.get("url"), policy):
            continue
        text = f"{r.get('title') or ''} {r.get('snippet') or ''}"
        host = (urlparse(r.get("url") or "").hostname or "").lower()
        public = any(host.endswith(s) for s in c["public_suffixes"])
        if not public and any(w.lower() in text.lower() for w in words):
            continue
        out.append(r)
    return out


def official_first(rows):
    """公的なドメインを先に(1 回の質問で読むページの順)。最大 max_pages。"""
    c = cfg()

    def key(r):
        host = (urlparse(r.get("url") or "").hostname or "").lower()
        return 0 if any(host.endswith(s) for s in c["public_suffixes"]) else 1
    return sorted(rows, key=key)[: c["max_pages"]]


def plan_for(names, subject, facts_doc):
    """名前ごとの照合の結果 → {found: [...], missing: [...]}。"""
    cands = (facts_doc["subjects"].get(subject) or {}).get("candidates") or []
    found, missing = [], []
    for n in names:
        c = match(official_name(n), cands) or match(n, cands)
        if c:
            sec = section(c, facts_doc)
            if _key(n) != _key(c["name"]) and _key(official_name(n)) == _key(c["name"]):   # 段階58 第6部: 入力と正式名称が違うときは 1 回だけ示す
                sec[0] = cfg()["lines"]["official"].format(name=c["name"])
            found.append({"query": n, "candidate": c, "section": sec})
        else:
            missing.append({"query": n, "search": cfg()["search_query"].format(name=n, year=str(facts_doc["now"])[:4])})
    return {"found": found, "missing": missing}


def section(c, facts_doc):
    """場所の節の行(事実は facts の値だけ)。今年の現況と日付／例年の見頃／見込み／行事／実用情報／距離／出典。"""
    t = cfg()["lines"]
    out = [c["name"]]
    cur = c.get("current")
    if AP.has_current(c):
        when = O._md(cur["state_date"]) if cur.get("state_date") else None
        state = cur.get("display") or cur.get("state_raw")
        out.append(t["current"].format(state=state, md=when, publisher=cur.get("publisher") or "") if when else t["current_nodate"].format(state=state, publisher=cur.get("publisher") or ""))
    else:
        out.append(t["no_current"])
    if c.get("typical_line"):
        out.append(c["typical_line"])
    for f in c.get("festivals") or []:
        if f.get("period_line"):
            out.append(f["period_line"])
    for p in (c.get("practical") or [])[:1]:
        out.append(t["practical"].format(text=p["text"]))
    if c.get("distance_km") is not None and facts_doc.get("origin"):
        out.append(t["distance"].format(origin=facts_doc["origin"], km=int(round(c["distance_km"]))))
    return out


def record_provisional(rows, env=None, now=None):
    """カタログにない場所の読めた事実を「仮」(検索で集めたもの)として記録する(データ置き場)。rows は O.record の形(name+city・state・url・publisher・source_class)。"""
    batch = [{**r, "provisional_search": True} for r in rows]
    return O.record(batch, env=env, now=now)
