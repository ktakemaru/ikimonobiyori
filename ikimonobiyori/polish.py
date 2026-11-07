"""段階60 第2部: 整えた文章と骨組みの、事実の一致検査(通信しない・書き込まない)。

流れ: 計画(ask plan)→ 骨組み(ask skeleton。コード)→ 文章の整え(エージェント)→ 検査(ask verify)→ 事実の一致検査(ここ)。
整えた文章に、骨組みにない事実(日付・曜日・時刻・距離・月・数値・URL・名前)が出たら不合格。
骨組みにある重要な事実(現況の日付・見込みの言い回し・確かさの補足の語・出典の URL)が落ちたら不合格。
値と文は data/ask/plan.yaml の polish。
"""
import re
import unicodedata

from . import answer_plan as AP

URL_RE = re.compile(r"https?://[^\s)）」』、。<>\"']+")
YMD_RE = re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
YMD_JA_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
MD_JA_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")
MD_RE = re.compile(r"(?<![\d.])(\d{1,2})/(\d{1,2})(?![\d])")
WEEKDAY_RE = re.compile(r"[(（]([月火水木金土日])[)）]")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})|(\d{1,2})時(?:(\d{1,2})分)?")
KM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:km|キロ)")
MONTH_RE = re.compile(r"(\d{1,2})月(上旬|中旬|下旬|初旬|末)?")
YEAR_RE = re.compile(r"(\d{4})年")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")
CURRENT_RE = re.compile(r"(\d{1,2}/\d{1,2})時点")


def cfg():
    return AP.load_policy()["polish"]


def _n(text):
    return unicodedata.normalize("NFKC", text or "")


def _md(m, d):
    return f"{int(m)}/{int(d)}"


def extract(text, names=(), min_name_chars=None):
    """文章の事実(種類 → 値の集合)。数字は種類ごとに一度だけ数える(日付の数字を数値に重ねない)。"""
    t = _n(text)
    out = {k: set() for k in ("url", "date", "weekday", "time", "km", "month", "year", "number", "name")}

    def take(rx, kind, fmt):
        nonlocal t
        for m in rx.finditer(t):
            out[kind].add(fmt(m))
        t = rx.sub(" ", t)

    take(URL_RE, "url", lambda m: m.group(0).rstrip(".,;:"))
    take(YMD_RE, "date", lambda m: _md(m.group(2), m.group(3)))
    take(YMD_JA_RE, "date", lambda m: _md(m.group(2), m.group(3)))
    take(MD_JA_RE, "date", lambda m: _md(m.group(1), m.group(2)))
    take(MD_RE, "date", lambda m: _md(m.group(1), m.group(2)))
    take(WEEKDAY_RE, "weekday", lambda m: m.group(1))
    take(TIME_RE, "time", lambda m: f"{int(m.group(1))}:{m.group(2)}" if m.group(1) else f"{int(m.group(3))}:{int(m.group(4) or 0):02d}")
    take(KM_RE, "km", lambda m: m.group(1))
    take(MONTH_RE, "month", lambda m: f"{int(m.group(1))}月{m.group(2) or ''}")
    take(YEAR_RE, "year", lambda m: m.group(1))
    take(NUM_RE, "number", lambda m: m.group(0))
    whole = _n(text)
    lo = cfg()["min_name_chars"] if min_name_chars is None else min_name_chars
    for nm in names:
        nm = _n(nm)
        if len(nm) >= lo and nm in whole:
            out["name"].add(nm)
    return out


def _count(text, word):
    return _n(text).count(_n(word))


def check(skeleton, text, names=()):
    """整えた文章(text)と骨組み(skeleton)の事実の一致。戻り値 {ok, errors: [{code, kind, items, detail}]}。"""
    pol = AP.load_policy()
    c = pol["polish"]
    kinds, msg = c["kinds"], c["messages"]
    sk, tx = extract(skeleton, names, c["min_name_chars"]), extract(text, names, c["min_name_chars"])
    errors = []
    for kind in ("url", "date", "weekday", "time", "km", "month", "year", "number", "name"):
        added = sorted(tx[kind] - sk[kind])
        if kind == "name":                       # 骨組みの名前の一部(「箱根美術館」の「箱根」)は足した名前としない
            added = [x for x in added if not any(x in s for s in sk["name"])]
        if added:
            errors.append({"code": "polish_added_fact", "kind": kind, "items": added,
                           "detail": msg["added"].format(kind=kinds[kind], items="・".join(added))})
    dropped_current = sorted({_md(*d.split("/")) for d in CURRENT_RE.findall(_n(skeleton))} - tx["date"])
    if dropped_current:
        errors.append({"code": "polish_dropped_fact", "kind": "current_date", "items": dropped_current,
                       "detail": msg["dropped"].format(kind=kinds["current_date"], items="・".join(dropped_current))})
    phrases = [p for p in list((pol["outlook"]["phrases"] or {}).values()) + list((pol["outlook"].get("phrases_typical_only") or {}).values()) if p]
    lost = [p for p in phrases if _count(text, p) < _count(skeleton, p)]
    if lost:
        errors.append({"code": "polish_dropped_fact", "kind": "phrase", "items": lost,
                       "detail": msg["dropped"].format(kind=kinds["phrase"], items="・".join(lost))})
    words = [w for w in c["required_words"] if _count(skeleton, w) and not _count(text, w)]
    if words:
        errors.append({"code": "polish_dropped_fact", "kind": "certainty", "items": words,
                       "detail": msg["dropped"].format(kind=kinds["certainty"], items="・".join(words))})
    srcs = sorted(sk["url"] - tx["url"])
    if srcs:
        errors.append({"code": "polish_dropped_fact", "kind": "source", "items": srcs,
                       "detail": msg["dropped"].format(kind=kinds["source"], items="・".join(srcs))})
    if _count(skeleton, c["sources_heading"]) and not _count(text, c["sources_heading"]):
        errors.append({"code": "polish_dropped_fact", "kind": "source", "items": [c["sources_heading"]],
                       "detail": msg["dropped"].format(kind=kinds["source"], items=c["sources_heading"])})
    return {"ok": not errors, "errors": errors}


def decide(state, skeleton_text, fact_ok, verify_ok):
    """整えなおしの回数の決まり。state = {"skeleton": 骨組みの文, "attempts": 回数}。
    戻り値 (use, state): use は "polished"(整えた文章を出す)・"retry"(あと 1 回だけ整えなおせる)・"skeleton"(骨組みのまま出す)。"""
    if (state or {}).get("skeleton") != skeleton_text:
        state = {"skeleton": skeleton_text, "attempts": 0}
    state = {**state, "attempts": state["attempts"] + 1}
    if fact_ok and verify_ok:
        return "polished", state
    if state["attempts"] <= cfg()["max_rewrites"]:
        return "retry", state
    return "skeleton", state
