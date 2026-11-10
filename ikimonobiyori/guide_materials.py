"""段階78: ガイドの資料の材料(通信しない)。guide_brief.build が使う。

- 距離: 直線と明記する。座標のない名所に県ごとの見積もり(plan.yaml の estimate_km_by_prefecture)を「約40km」と出さない。
  名所の座標(名所カタログ・観察の名所)、なければ市区町村の代表点から直線の距離を出す。東京湾をはさむ場所(千葉県の内房・外房・南房総)は
  距離の数字を出さない(第1部 2・3)。
- 種の名所の一覧: 種の「いつ・どこ」「地域と時期」「名所」「見たい」で同じ一覧(season_place の gather/select を、資料用に多めの件数で)。
  例年の時期が古い・あいまいな名所も入れて、その旨を書く(第2部 2・3)。
- 語りの材料: 知識カードの文を、なぜ今・どこをどう見る・見分け方・次の季節に分ける(第3部 1)。
- 調べる指示: 資料が薄いとき(第4部 1)。
値と語は data/ask/guide_mode.yaml(distance・species_rows・narrative・research)。"""
import re

from . import yamlcache
from .paths import DATA_FILES_DIR

_INDEX = None


def cfg():
    from . import guide_brief as GB
    return GB.cfg()


# ---- 名所の位置 ----

def _index():
    """名所の名前 → {prefecture, city, point}(名所カタログ・観察の名所・ガイドのカタログ)。"""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    out = {}

    def put(name, pref, city, pt):
        if not name:
            return
        cur = out.setdefault(name, {"prefecture": None, "city": None, "point": None})
        cur["prefecture"] = cur["prefecture"] or pref
        cur["city"] = cur["city"] or city
        if pt and pt.get("lat") is not None and pt.get("lon") is not None and not cur["point"]:
            cur["point"] = {"lat": pt["lat"], "lon": pt["lon"]}
    for p in sorted((DATA_FILES_DIR / "catalog").glob("*.yaml")):
        if p.name == "policy.yaml":
            continue
        try:
            doc = yamlcache.load(p) or {}
        except (OSError, ValueError):
            continue
        for e in doc.get("entries") or []:
            if isinstance(e, dict) and not e.get("example"):
                t = e.get("tags") or {}
                put(e.get("name"), t.get("prefecture"), t.get("city"), e.get("point"))
    try:
        sp = yamlcache.load(DATA_FILES_DIR / "observations" / "spots.yaml") or {}
    except (OSError, ValueError):
        sp = {}
    for e in sp.get("spots") or []:
        if isinstance(e, dict):
            put(e.get("name"), e.get("prefecture"), e.get("city"), e.get("point") or e.get("bird_range"))
    try:
        from . import guide
        for e in guide.build()[0]:
            put(e.get("name"), e.get("prefecture"), e.get("municipality"), None)
    except (OSError, ValueError, KeyError):
        pass
    _INDEX = out
    return out


def place_info(name):
    return dict(_index().get(name) or {})


def across_bay(prefecture, city=None, point=None, origin=None, c=None):
    """東京湾をはさむ場所か(千葉県の内房・外房・南房総。出発地が千葉県なら当てない)。"""
    c = c or cfg()
    ab = c["distance"]["across_bay"]
    if prefecture != ab["prefecture"]:
        return False
    from . import guide_brief as GB
    if GB._origin_pref(origin) in ab["origin_prefectures_not"]:
        return False
    if point and point.get("lat") is not None:
        return point["lat"] < ab["max_lat"]
    return bool(city) and any(city.startswith(m) for m in ab["municipalities"])


def straight_km(name, origin, *, prefecture=None, city=None):
    """名所 → (km, 根拠: point / city / None, point)。座標 → 市区町村の代表点 → (None, None, None)。"""
    from . import catalog as CM
    from . import origins
    info = place_info(name)
    pt = info.get("point")
    pol = CM.load_policy()
    try:
        if pt:
            return CM.range_from(pol, pt, origin)["km"], "point", pt
        city = city or info.get("city")
        mp = origins.municipal_point(city) if city else None
        if mp:
            return CM.range_from(pol, mp, origin)["km"], "city", None
    except (KeyError, TypeError, ValueError, StopIteration):
        pass
    return None, None, None


def distance_text(name, km, origin, *, estimated=False, prefecture=None, city=None, c=None):
    """資料に出す距離の語。→ (km か None, 語)。見積もりの距離は使わず、直線の距離を出し直す。"""
    c = c or cfg()
    D = c["distance"]
    info = place_info(name)
    pref = prefecture or info.get("prefecture")
    ct = city or info.get("city")
    pt = info.get("point")
    if estimated or km is None:
        km2, basis, pt2 = straight_km(name, origin, prefecture=pref, city=ct)
        km = km2
        pt = pt2 or pt
    if across_bay(pref, ct, pt, origin, c):
        return None, D["across_bay_label"]
    if km is None:
        return None, D["estimated_label"]
    return km, D["straight_label"].format(km=int(round(km)))


# ---- 種の名所の一覧(第2部 2・3) ----

def species_rows(question, cond, env=None, c=None):
    """種の質問 → 名所の行の一覧 [{species, name, prefecture, city, km, season, kinds, url, official, publisher, note}]。
    種がなければ []。質問の場所(市区町村・エリア)があれば、その場所の名所を先に。"""
    from . import observations as O
    from . import season_place as SP
    c = c or cfg()
    R = c["species_rows"]
    if (cond.get("route") in R["routes_skip"]) or not question:
        return []
    try:
        sps = SP.resolve_all(question)
    except (KeyError, TypeError, ValueError):
        sps = []
    if not sps:
        return []
    spc = dict(SP.cfg(), max_items=R["max_known"], max_unknown_items=R["max_unknown"])
    prefs = None
    if cond.get("region"):
        try:
            prefs = (O.resolve(cond["region"], cond.get("origin"), O.load_policy()) or {}).get("prefectures") or None
        except (KeyError, TypeError, ValueError):
            prefs = None
    place = SP.place_filter(question)
    origin = cond.get("origin")
    out = []
    for sp in sps:
        is_bird = sp["name"] in (spc.get("bird_species") or [])
        try:
            rows, _n = SP.select(SP.gather(sp, origin, spc, env), origin, prefs, spc, by_distance=is_bird)
        except (OSError, ValueError, KeyError, TypeError):
            rows = []
        if place and place.get("cities"):
            own = [r for r in rows if SP._in_cities(r, place["cities"])]
            rows = own + [r for r in rows if r not in own]
        for r in rows:
            note = None
            if re.search(r"\d{4}年の記載", r.get("season") or ""):
                note = R["old_note"]
            elif r.get("season") and not r.get("start"):
                note = R["vague_note"]
            out.append({"species": sp["name"], "name": r["name"], "prefecture": r.get("prefecture"), "city": r.get("city"),
                        "km": r.get("km"), "km_estimated": r.get("km_estimated"), "season": r.get("season"), "kinds": r.get("kinds") or [],
                        "url": r.get("url"), "official": bool(r.get("official")), "publisher": r.get("publisher") or None,
                        "care": r.get("care"), "note": note, "in_place": bool(place and place.get("cities") and SP._in_cities(r, place["cities"]))})
    return out


def species_names(question):
    from . import season_place as SP
    try:
        return [sp["name"] for sp in SP.resolve_all(question)]
    except (KeyError, TypeError, ValueError):
        return []


def species_match_words(question):
    from . import season_place as SP
    try:
        sps = SP.resolve_all(question)
    except (KeyError, TypeError, ValueError):
        return []
    out = []
    for sp in sps:
        out += [w for w in list(sp.get("match") or []) + list(sp.get("includes") or []) + list(sp.get("words") or []) if w not in out]
    return out


# ---- 発行元の名前(第1部 5) ----

_HOSTISH = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$", re.I)


def source_name(url, given=None, *, prefecture=None, city=None, c=None):
    """出典の名前。ドメインのままの名前は使わず、台帳・ガイドの発行元の表・自治体のドメインの市区町村・都道府県の名前で出す。
    分からなければ None(最後の出典ではドメイン名になる)。"""
    from . import publisher as P
    c = c or cfg()
    if given and not _HOSTISH.match(str(given).strip()):
        return given
    if not url:
        return None
    try:
        n = P.name(url, {"tags": {"prefecture": prefecture, "city": city}} if (prefecture or city) else None)
    except (OSError, KeyError, TypeError, ValueError):
        n = None
    if n:
        return n
    host = P.host_of(url) or ""
    m = re.match(r"^(?:www\.)?pref\.([a-z]+)\.(?:lg\.)?jp$", host)
    if m:
        return (c.get("pref_romaji") or {}).get(m.group(1))
    return None
