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
