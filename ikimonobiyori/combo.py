"""複数テーマの組み合わせ(「白鳥と季節の花」「紅葉と花」。段階58 第10部)。通信しない。

同じ地点で複数の見どころがあるものと、近く(直線距離の上限は data/ask/plan.yaml の combo.max_km)の組み合わせだけを出す。遠い地点どうしを 1 日の組み合わせにしない。所要時間は書かない。"""
from . import yamlcache
from . import answer_plan as AP
from . import catalog as C
from . import observations as O
from .paths import DATA_FILES_DIR



def cfg():
    return AP.load_policy()["combo"]


def _candidates(subject):
    """対象の名所(点のあるもの・名前)。観察の一覧とカタログ。"""
    if subject == "wintering_birds":
        doc = yamlcache.load((DATA_FILES_DIR / "catalog" / "wintering_birds.yaml")) or {}
        return [{"name": e["name"], "point": e.get("point"), "city": (e.get("tags") or {}).get("city")} for e in doc.get("entries") or []
                if not e.get("example") and e.get("status") not in ("retired", "rejected", "candidate")]
    return O.all_candidates(subject)


def _key(name):
    import re
    return re.sub(r"[\s(（].*$", "", name or "")


def find(a, b, cand_a=None, cand_b=None, policy=None):
    """テーマ a と b の組み合わせ。→ {"same": [名所], "near": [{a, b, km}], "line": 見つからないときの文}。"""
    pol = policy or C.load_policy()
    r = pol["range_limit"]["earth_radius_km"]
    aa = cand_a if cand_a is not None else _candidates(a)
    bb = cand_b if cand_b is not None else _candidates(b)
    same, near = [], []
    keys_b = {_key(x["name"]): x for x in bb}
    for x in aa:
        if _key(x["name"]) in keys_b and _key(x["name"]) not in same:
            same.append(_key(x["name"]))
    mx = cfg()["max_km"]
    for x in aa:
        px = x.get("point") or {}
        if px.get("lat") is None or _key(x["name"]) in same:
            continue
        for y in bb:
            py = y.get("point") or {}
            if py.get("lat") is None or _key(y["name"]) in same:
                continue
            km = C.distance_km(px["lat"], px["lon"], py["lat"], py["lon"], r)
            if km <= mx:
                near.append({"a": x["name"], "b": y["name"], "km": int(round(km))})
    near.sort(key=lambda p: (p["km"], p["a"], p["b"]))
    out = {"same": same, "near": near[: cfg()["max_pairs"]]}
    if not same and not near:
        out["line"] = cfg()["none_line"].format(km=mx)
    return out


def lines(result):
    """答えに書く行(距離の目安つき)。"""
    t = cfg()
    out = [t["same_line"].format(name=n) for n in result["same"]]
    out += [t["near_line"].format(a=p["a"], b=p["b"], km=p["km"]) for p in result["near"]]
    if result.get("line"):
        out.append(result["line"])
    return out


# ---- 段階69 第2部 4: 「AとBが見られる場所」の質問 ----

def topics_of(question):
    """質問の文 → [(語, [対象])](質問に出た順。長い語から。2 つ以上の別の対象のときだけ組み合わせの質問)。"""
    import re
    t = cfg()
    q = question or ""
    hits, taken = [], []
    for w in sorted(t.get("topic_words") or {}, key=len, reverse=True):
        for m in re.finditer(re.escape(w), q):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            hits.append((m.start(), w, list(t["topic_words"][w])))
    hits.sort()
    out = []
    for _i, w, sjs in hits:
        if not any(set(sjs) == set(x[1]) for x in out):
            out.append((w, sjs))
    return out


def is_combo_question(question):
    t = cfg()
    q = question or ""
    tp = topics_of(q)
    if len(tp) < 2 or not any(p in q for p in t.get("patterns") or []):
        return False
    a, b = tp[0][0], tp[1][0]
    i, j = q.find(a), q.find(b)
    between = q[i + len(a):j] if i < j else ""
    return any(x in between for x in t.get("joins") or []) and len(between) <= max(len(x) for x in t["joins"]) + len("の")


def _cands(sjs):
    out, seen = [], set()
    for sj in sjs:
        for x in _candidates(sj):
            k = _key(x["name"])
            if k not in seen:
                seen.add(k)
                out.append(x)
    return out


def _window_of(name, sjs, thirds):
    """名所の例年の時期(名所の一覧の typical のうち、時期の分かるもの 1 つ)。→ (種の語, 時期の文, 発行元) か None。"""
    from . import season_place as SP
    for sj in sjs:
        if sj == "wintering_birds":
            continue
        for x in O.all_candidates(sj):
            if _key(x["name"]) != _key(name):
                continue
            for w in x.get("typical") or []:
                if w.get("start") and w.get("end") and w.get("source_class") == "official":
                    return (w.get("kind") or {"autumn_leaves": "紅葉"}.get(sj, ""), SP.window_text(w["start"], w["end"], thirds), w.get("publisher") or "",
                            w.get("url"))
    return None


def compose(question, *, origin, on=None, today=None, env=None):
    """組み合わせの質問 → {text, same, near, found}。組み合わせを先に。見つからないときだけ、別々の一覧(1 文つき)。"""
    from . import season_place as SP
    t = cfg()
    tp = topics_of(question)[:2]
    (wa, sa), (wb, sb) = tp
    pol = C.load_policy()
    res = find(sa[0], sb[0], cand_a=_cands(sa), cand_b=_cands(sb), policy=pol)
    thirds = SP.cfg()["text"]["thirds"]
    days = "・".join(f"{d.month}/{d.day}" for d in on) if on else None
    lines = [t["title_dated"].format(days=days, a=wa, b=wb) if on else t["title"].format(a=wa, b=wb)]
    if on:
        lines.append(SP.cfg()["dated"]["date_line"].format(days=days))
    found = bool(res["same"] or res["near"])
    urls = []
    if found:
        lines.append(t["lead"].format(km=t["max_km"]))
        lines.append("")
        for n in res["same"]:
            lines.append("・" + t["same_line"].format(name=n))
            for nm, sjs in ((n, sa), (n, sb)):
                w = _window_of(nm, sjs, thirds)
                if w:
                    lines.append(t["window_line"].format(name=nm, kind=w[0], window=w[1], publisher=w[2]))
                    if w[3] and w[3] not in urls:
                        urls.append(w[3])
        for pr in res["near"]:
            lines.append("・" + t["near_line"].format(a=pr["a"], b=pr["b"], km=pr["km"]))
            for nm, sjs in ((pr["a"], sa), (pr["b"], sb)):
                w = _window_of(nm, sjs, thirds)
                if w:
                    lines.append(t["window_line"].format(name=nm, kind=w[0], window=w[1], publisher=w[2]))
                    if w[3] and w[3] not in urls:
                        urls.append(w[3])
    else:
        lines += [t["separate_lead"]]
        r = pol["range_limit"]["earth_radius_km"]
        from . import origins as OR
        op = OR.choose(origin or "")
        o = OR.point_of(origin) if hasattr(OR, "point_of") else None
        for w, sjs in ((wa, sa), (wb, sb)):
            rows = []
            for x in _cands(sjs):
                p = x.get("point") or {}
                km = None
                if p.get("lat") is not None and o:
                    km = C.distance_km(p["lat"], p["lon"], o[0], o[1], r)
                rows.append((km if km is not None else 9999, x["name"]))
            rows.sort()
            lines += ["", t["separate_head"].format(label=w)]
            for km, n in rows[: t["separate_max"]]:
                lines.append(t["separate_line"].format(name=n, km=f" 約{int(round(km))}km" if km != 9999 else ""))
    if on and found:
        from . import highlights as HL
        names = res["same"] + [x for pr in res["near"] for x in (pr["a"], pr["b"])]
        pls = [{"name": n, "terms": [_key(n)], "cities": [], "center": None, "radius_km": None} for n in dict.fromkeys(names)]
        g = HL.gather(pls, today or on[0], env)
        ol, ou = HL.outlook_lines(g, on, HL.cfg(), O.load_policy(), pls)
        lines += ["", HL.cfg()["text"]["outlook_heading"].format(days=days)] + ol
        urls += [u for u in ou if u not in urls]
    lines += ["", t["confidence"]]
    if urls:
        lines += ["", SP.cfg()["text"]["sources_heading"]] + urls
    return {"text": "\n".join(lines) + "\n", "same": res["same"], "near": res["near"], "found": found}
