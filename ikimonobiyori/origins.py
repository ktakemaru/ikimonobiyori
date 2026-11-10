"""質問から取り出す出発地(段階57 第8部)。座標の表は data/ask/origins.yaml と data/guide/places.yaml(どちらも Wikidata で確認した値)。通信しない。

- 取り出し: 「大宮から」「新宿発」。指定がなければ既定(横浜)。
- 引き継ぎ: 直前の質問の追質問のときだけ。新しい質問で指定がなければ既定に戻す。どの場合も、使った出発地を 1 文で答えに書く。
- 表にない出発地は、Wikidata で確かめて ask origin --add で手元のキャッシュ(IKIMONOBIYORI_DATA_DIR の下)に足す。確かめられなければ既定の距離で選ぶ。"""
import json
import re
from pathlib import Path


from . import yamlcache
from .paths import DATA_FILES_DIR, data_path

ORIGINS_PATH = DATA_FILES_DIR / "ask" / "origins.yaml"
PLACES_PATH = DATA_FILES_DIR / "guide" / "places.yaml"
CACHE = "ask/origins_cache.json"
_doc, _places = None, None


def load():
    global _doc
    if _doc is None:
        _doc = yamlcache.load(ORIGINS_PATH)
    return _doc


def places():
    global _places
    if _places is None:
        _places = {p["municipality"]: p for p in (yamlcache.load(PLACES_PATH) or {}).get("places") or []}
    return _places


def _cache(env=None):
    try:
        return json.loads(Path(data_path(CACHE, env)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def add_to_cache(name, lat, lon, qid, prefecture=None, env=None):
    """Wikidata で確かめた出発地を手元に足す(リポジトリの外)。"""
    c = _cache(env)
    c[name] = {"name": name, "lat": float(lat), "lon": float(lon), "qid": qid, "prefecture": prefecture}
    p = Path(data_path(CACHE, env))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    return c[name]


def lookup(name, env=None):
    """出発地の名前 → {name, lat, lon, prefecture} か None(推測しない)。"""
    if not name:
        return None
    for o in load()["origins"]:
        if name == o["name"] or name in (o.get("aliases") or []):
            return o
    p = places()
    for key in (name, name + "市", name + "区", re.sub(r"駅$", "", name) + "市", re.sub(r"駅$", "", name) + "区"):
        if key in p:
            r = p[key]
            return {"name": re.sub(r"[市区]$", "", key) if len(key) > 2 else key, "lat": r["lat"], "lon": r["lon"], "prefecture": r.get("prefecture"), "qid": r.get("qid")}
    return _cache(env).get(name)


def municipal_point(city):
    """名所の市区町村の代表点(座標のない名所の距離に使う)。「相模原市緑区」は市で引く。"""
    if not city:
        return None
    p = places()
    r = p.get(city)
    if not r:
        m = re.match(r"^(.+?市)", city)
        r = p.get(m.group(1)) if m else None
    if not r:
        o = lookup(city)
        return {"lat": o["lat"], "lon": o["lon"]} if o else None
    return {"lat": r["lat"], "lon": r["lon"]}


def extract(question):
    """質問の文 → 出発地の語(「大宮から」→ 大宮)。なければ None。"""
    stop = set(load()["stop_words"])
    for m in re.finditer(r"([一-龠ぁ-んァ-ヶーa-zA-Z]{1,12}?)(?:駅)?(?:から|発)(?![ぁ-ん]*(?:した|する))", question or ""):
        w = m.group(1)
        w = re.sub(r"^.*[はのをにでとがも]", "", w) or w
        if w not in stop:
            return w
    return None


def default_name():
    return load()["default"]


def is_default_table(name, policy_origins=("横浜", "東京")):
    return name in policy_origins


def choose(question=None, follow_up=False, last_origin=None, env=None):
    """使う出発地と、答えに書く 1 文。→ {origin, line, source: question / follow_up / default / unknown}。
    追質問のときだけ前の出発地を引き継ぐ。新しい質問で指定がなければ既定に戻す。"""
    L = load()["lines"]
    dflt = default_name()
    name = extract(question)
    known = {"横浜", "東京"}
    if name:
        row = lookup(name, env) if name not in known else {"name": name}
        if row:
            return {"origin": row["name"], "line": L["named"].format(origin=row["name"]), "source": "question"}
        return {"origin": dflt, "line": L["unknown"].format(name=name, origin=dflt), "source": "unknown", "asked": name}
    if follow_up and last_origin:
        return {"origin": last_origin, "line": L["follow_up"].format(origin=last_origin), "source": "follow_up"}
    return {"origin": dflt, "line": L["default"].format(origin=dflt), "source": "default"}


def line_for(origin, wide=False):
    """facts に載せる 1 文(使った出発地)。wide: 「遠くても」の質問(段階74。範囲全体から選んだ文)。"""
    return load()["lines"]["wide" if wide else "named"].format(origin=origin)
