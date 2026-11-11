"""段階72 第3部: 知らない地名をすり替えない。通信しない。

質問に場所らしい語(「霞ヶ浦には」「大宮南部浄化センター付近」)があり、その語がどの辞書(エリア・地域・出発地・名所カタログ・
ガイドの名所・観察の名所・知識カードの場所・場所の別名)でも解決できないとき、既定の出発地や無関係なエリア(箱根の解説など)に
落とさず、その地名を「調べる対象」にする。大きな地名(湖・川・沼)で範囲をまだ決めていないものは、エリア辞書の pending_areas。
語と値は data/ask/areas.yaml の unknown_place。"""
import re

from . import areas as AR
from . import yamlcache
from .paths import DATA_FILES_DIR

NL = "\n"


def cfg():
    return AR.load()["unknown_place"]


def pending_area(name):
    """範囲をまだ決めていない大きな地名(エリア辞書の pending_areas)→ 項目か None。"""
    n = (name or "").strip()
    for a in AR.load().get("pending_areas") or []:
        if n == a["name"] or n in (a.get("aliases") or []):
            return a
    return None


def _norm(s):
    return re.sub(r"[・\s()（）]", "", s or "").replace("ケ", "ヶ").replace("が", "ヶ")


_known = None


def known_names():
    """辞書で解決できる場所の名前(正規化した形)の集合。"""
    global _known
    if _known is not None:
        return _known
    names = set()
    for a in AR.load()["areas"]:
        names |= {a["name"], *(a.get("aliases") or [])}
    from . import sources as S
    for r in S.load_regions()["regions"]:
        names |= {r["name"], *(r.get("aliases") or [])}
    from . import origins
    for o in yamlcache.load(DATA_FILES_DIR / "ask" / "origins.yaml").get("origins") or []:
        names |= {o.get("name"), *(o.get("aliases") or [])}
    try:
        from . import catalog as C
        for sub in ("autumn_leaves", "flowers", "birds", "wintering_birds"):
            try:
                for s in (C.load_catalog(sub) or {}).get("entries") or []:
                    names |= {s.get("name"), *(s.get("aliases") or [])}
            except (OSError, KeyError, TypeError, ValueError):
                continue
    except ImportError:
        pass
    try:
        from . import observations as O
        for s in (O.load_spots() or {}).get("spots") or []:
            names |= {s.get("name"), *(s.get("aliases") or [])}
    except (OSError, KeyError, TypeError, ValueError, AttributeError):
        pass
    try:
        doc = yamlcache.load(DATA_FILES_DIR / "guide" / "catalog.yaml")
        for e in (doc.get("entries") or doc.get("spots") or []) if isinstance(doc, dict) else doc or []:
            if isinstance(e, dict):
                names.add(e.get("name"))
    except (OSError, KeyError, TypeError, ValueError):
        pass
    _ = origins
    _known = {_norm(n) for n in names if n}
    return _known


def card_places(env=None):
    try:
        from . import knowledge as K
        rows = K.load_shown(env)
    except (OSError, ValueError):
        return set()
    out = set()
    for r in rows:
        out |= {_norm(r.get("place")), *(_norm(a) for a in r.get("place_aliases") or [])}
    return {x for x in out if x}


def candidates(question, c=None):
    """質問の文 → 場所らしい語の一覧(出てくる順)。"""
    c = c or cfg()
    q = question or ""
    out = []
    for pat in c["patterns"]:
        for m in re.finditer(pat, q):
            w = m.group(1)
            w = re.sub(c["strip_head_re"], "", w).strip()
            if len(w) >= c["min_chars"] and not any(s in w for s in c["not_place_words"]) and w not in out:
                out.append(w)
    return [w for w in out if not any(x != w and w.startswith(x) for x in out)]     # 「○○付近」と「○○」は短い方だけ


def is_known(name, env=None, extra=()):
    n = _norm(name)
    known = known_names() | card_places(env) | {_norm(x) for x in extra}
    if n in known:
        return True
    if AR.resolve(name):
        return True
    return False


def unknown_towns(question, env=None, extra=()):
    """段階80 A(提案4): 「南伊豆で」のような市区町村の名前(略称を含む)で、場所の辞書(エリア・地域・出発地・名所の名前・
    名所のある市区町村)で解決できないもの。別の場所(既定の出発地の近く)の候補に置き換えず、調べる対象にする。"""
    from . import guide_verify as GV
    from . import research as RS
    from . import season_place as SP
    out = []
    dic = GV._dictionary_places()
    for w in RS.question_places(question):
        if w in dic or is_known(w, env, extra):          # 名所・エリア・山の辞書の名前は知っている場所
            continue
        t = SP.resolve_town(w)
        if t and (t == w or re.sub(r"[市町村区]$", "", t) == w):
            continue
        out.append(w)
    return out


def unknown_places(question, env=None, extra=()):
    """解決できない場所の語の一覧(範囲を決めていない大きな地名を含む)。"""
    out = [w for w in candidates(question) if pending_area(w) or not is_known(w, env, extra)]
    for w in unknown_towns(question, env, extra):
        if not any(w in x or x in w for x in out):
            out.append(w)
    return out


def subject_label(subjects, question, c=None):
    c = c or cfg()
    for w, label in c["subject_words"].items():
        if w in (question or ""):
            return label
    labels = AR.load()["lines"]["subject_labels"]
    return "・".join(labels[s] for s in subjects if s in labels) or c["default_label"]


def records_for(name, subjects, env=None):
    """調べて記録した事実(データ置き場の観察の記録)のうち、名前・エリア・市町村にその地名を含むもの。"""
    from . import observations as O
    n = _norm(name)
    a = pending_area(name)
    keys = {n} | ({_norm(x) for x in [a["name"], *(a.get("aliases") or [])]} if a else set())
    out = []
    for sj in subjects or []:
        try:
            rows = O.read_records(sj, env)
        except (OSError, ValueError, KeyError):
            continue
        for r in rows:
            hay = _norm(" ".join(str(r.get(k) or "") for k in ("name", "spot", "area", "city")))
            if any(k and k in hay for k in keys) and (r.get("state") or r.get("typical") or r.get("species")):
                out.append(r)
    return out


def _md(d):
    try:
        y, m, dd = str(d)[:10].split("-")
        return f"{int(m)}/{int(dd)}"
    except (ValueError, TypeError):
        return None


def _record_line(r, c):
    t = c["lines"]
    bits = []
    if r.get("state"):
        bits.append(t["state"].format(state=r["state"], date=_md(r.get("state_date")) or t["no_date"]))
    if r.get("typical"):
        bits.append(t["typical"].format(typical=r["typical"]))
    if r.get("species"):
        sp = r["species"] if isinstance(r["species"], list) else [r["species"]]
        bits.append(t["species"].format(species="・".join(map(str, sp[: c["max_species"]]))))
    pub = r.get("publisher") or r.get("host") or ""
    return t["record"].format(name=r.get("name") or r.get("spot") or "", text="、".join(bits), publisher=pub)


def compose(question, names, subjects, c=None, env=None):
    """解決できない地名の質問の答え(すり替えない)と、調べる対象。→ (text, research_targets, 記録の事実で答えたか)
    調べて記録した事実(名前・エリアに地名を含む記録)があれば、その事実だけで答える。"""
    c = c or cfg()
    label = subject_label(subjects, question, c)
    lines, targets, urls, found = [], [], [], False
    for n in names:
        a = pending_area(n)
        where = n + (f"({'・'.join(a['prefectures'])})" if a and a.get("prefectures") else "")
        recs = records_for(n, subjects, env)[: c["max_records"]]
        if recs:
            found = True
            lines.append(c["lines"]["found"].format(name=where, label=label))
            lines += [_record_line(r, c) for r in recs]
            urls += [r["url"] for r in recs if r.get("url")]
            continue
        lines.append(c["lines"]["none"].format(name=where, label=label))
        targets.append({"what": label, "where": n, "search": c["search"].format(name=n, label=label)})
    if found:
        lines += ["", c["lines"]["check"]]
    if urls:
        lines += ["", "出典"] + list(dict.fromkeys(urls))
    return NL.join(lines) + NL, targets, found
