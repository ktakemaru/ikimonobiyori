"""エリア名の質問(段階58 第1部・第9部)。通信しない。辞書は data/ask/areas.yaml(座標は Wikidata で確認した市町村の代表点だけ)。

「秩父・長瀞のエリア」「飯能あたり」「A・B、C〜D〜E、F周辺など」をエリアに分解し、エリア内の名所で計画を作る。"""
import re


from . import yamlcache
from . import catalog as C
from .paths import DATA_FILES_DIR

PATH = DATA_FILES_DIR / "ask" / "areas.yaml"
_doc = None


def load():
    global _doc
    if _doc is None:
        _doc = yamlcache.load(PATH)
    return _doc


def resolve(name):
    """エリア名 → 辞書の項目か None。完全一致(名前・別名)だけ(同名の別地域・似た名前を取り違えない)。"""
    n = (name or "").strip()
    for a in load()["areas"]:
        if n == a["name"] or n in (a.get("aliases") or []):
            return a
    return None


def near_names(name):
    """確実に近い名前だけ(辞書の名前を含む・含まれる)。"""
    n = (name or "").strip()
    if len(n) < 2:
        return []
    return [a["name"] for a in load()["areas"] if a["name"] in n or n in a["name"]]


def split_names(text):
    d = load()
    out = []
    for w in re.split(d["split_re"], text or ""):
        w = re.sub(r"(のエリア|エリア|あたり|周辺|方面|の$)", "", w.strip())
        if len(w) >= 2 and w not in d["stop_words"] and w not in out:
            out.append(w)
    return out


def from_question(question):
    """質問の文 → エリア名の一覧。「○○のエリア」「○○あたり」「○○周辺」の形か、辞書の名前が 2 つ以上あるとき。ないときは []。"""
    q = re.sub(r"(で|の)?(紅葉|花|野鳥|おすすめ).*$", "", question or "")
    d = load()
    if re.search(d["question_re"], question or ""):
        return split_names(q)
    names = split_names(q)
    return names if len([n for n in names if resolve(n)]) >= 2 else []


def members(area, candidates, policy=None):
    """エリアの名所(市区町村が一致、または中心から半径の内)。"""
    policy = policy or C.load_policy()
    r = policy["range_limit"]["earth_radius_km"]
    out = []
    for c in candidates:
        city = c.get("city") or ""
        if any(city.startswith(x) for x in area.get("cities") or []):
            out.append(c)
            continue
        p = c.get("point")
        if p and p.get("lat") is not None and C.distance_km(p["lat"], p["lon"], area["center"]["lat"], area["center"]["lon"], r) <= area["radius_km"]:
            out.append(c)
    return out


def describe(names):
    """エリア名の一覧 → {found: [項目], unknown: [文]}。"""
    L = load()["lines"]
    found, unknown = [], []
    for n in names:
        a = resolve(n)
        if a:
            if a not in found:
                found.append(a)
            continue
        line = L["unknown"].format(name=n)
        near = near_names(n)
        if near:
            line += L["near"].format(names="・".join(near))
        unknown.append(line)
    return {"found": found, "unknown": unknown}
