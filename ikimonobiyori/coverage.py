"""段階72 第4部 1: 探索範囲全体のデータの棚卸し(`ask coverage`)。通信しない・書き込まない。

範囲の都県(既定の出発地から range_limit.max_km 以内に代表点がある都県。地域の辞書 data/regions.yaml の代表点と、
代表点のない「範囲の中」の地域の都県)ごとに、テーマ(紅葉・花(季節別)・野鳥・ススキ・ホタル・行事・山のカード・
承認済みの情報源・ビジターセンター)の件数を数える。数えるのは、名所カタログ・ガイドの名所・観察の名所(リポジトリ)と、
データ置き場の読んだ記録(名所の数)・知識カード。段階73 の収集の計画に使う。"""
import re
from collections import defaultdict

from . import catalog as C
from . import yamlcache
from .paths import DATA_FILES_DIR

NL = "\n"
UNKNOWN = "(都県不明)"


def cfg():
    return yamlcache.load(DATA_FILES_DIR / "ask" / "plan.yaml")["coverage"]


def _origin_point():
    pol = C.load_policy()
    name = pol["range_limit"]["default_origin"]
    from . import origins
    o = origins.lookup(name)
    return ({"lat": o["lat"], "lon": o["lon"]} if o else None), name


PARTIAL = set()      # 範囲の外の代表点もある都県(福島県など。range_prefectures が埋める)


def partial_prefectures():
    """段階72 第5部 4: 一部だけが範囲に入る都県(範囲の外の代表点もある)。"""
    range_prefectures()
    return set(PARTIAL) & {p for p, _ in range_prefectures()}


def range_prefectures():
    """範囲の都県(代表点の近い順)。→ [(都県, 代表点までの最短 km か None)]"""
    pol = C.load_policy()
    mx, r = pol["range_limit"]["max_km"], pol["range_limit"]["earth_radius_km"]
    edge = pol["range_limit"]["edge_min_km"]["value"]
    op, _ = _origin_point()
    best = {}
    for reg in yamlcache.load(DATA_FILES_DIR / "regions.yaml")["regions"]:
        prefs = (reg.get("match") or {}).get("prefectures") or []
        pts = reg.get("points") or []
        if not pts:
            for p in prefs:
                best.setdefault(p, None)
            continue
        for pt in pts:
            p = pt.get("prefecture") or (prefs[0] if len(prefs) == 1 else None)
            if not p or op is None:
                continue
            km = C.distance_km(op["lat"], op["lon"], pt["lat"], pt["lon"], r)
            if km < edge and (best.get(p) is None or km < best[p]):         # 範囲の端(edge_min_km 以上)にしか代表点がない都県は範囲に入れない(愛知県)
                best[p] = round(km)
            if km > mx:
                PARTIAL.add(p)
    return sorted(best.items(), key=lambda x: (x[1] is not None, x[1] or 0, x[0]))


def _pref(e):
    t = e.get("tags") if isinstance(e.get("tags"), dict) else {}
    p = t.get("prefecture") or e.get("prefecture")
    pt = e.get("point") or {}
    if not p and pt.get("lat") is not None:              # 都県の書いていない名所は、座標から代表点のいちばん近い都県(目安)
        p = _nearest_pref(pt["lat"], pt["lon"])
    return p or UNKNOWN


def _season(month, c):
    for s in c["seasons"]:
        if month in s["months"]:
            return s["name"]
    return None


def _month(md):
    m = re.match(r"^(\d{1,2})-", str(md or ""))
    return int(m.group(1)) if m else None


def count(env=None, cards=None, records=None):
    """→ {都県: {テーマ: 件数}}。records: {subject: [記録]}(省くとデータ置き場から)。"""
    c = cfg()
    tab = defaultdict(lambda: defaultdict(int))
    names = defaultdict(set)

    def add(pref, theme, key):
        if key in names[(pref, theme)]:
            return
        names[(pref, theme)].add(key)
        tab[pref][theme] += 1
    for sub, theme in (("autumn_leaves", "紅葉"), ("birds", "野鳥"), ("wintering_birds", "野鳥")):
        for e in (C.load_catalog(sub) or {}).get("entries") or []:
            add(_pref(e), theme, e.get("name"))
            if e.get("events") or e.get("festivals"):
                add(_pref(e), "行事", e.get("name"))
    for e in (C.load_catalog("flowers") or {}).get("entries") or []:
        p = _pref(e)
        ws = e.get("flower_windows") or []
        for w in ws:
            s = _season(_month(w.get("start")), c)
            if s:
                add(p, "花(" + s + ")", e.get("name"))
        if not ws:
            add(p, "花(時期不明)", e.get("name"))
        if e.get("events") or e.get("festivals"):
            add(p, "行事", e.get("name"))
    guide = yamlcache.load(DATA_FILES_DIR / "guide" / "catalog.yaml").get("entries") or []
    for g in guide:
        th = c["guide_themes"].get(g.get("theme"))
        if th == "花":
            sea = g.get("season") if isinstance(g.get("season"), dict) else {}
            win = sea.get("window") if isinstance(sea.get("window"), dict) else {}
            s = _season(_month(win.get("start")), c)
            th = "花(" + s + ")" if s else "花(時期不明)"
        if th:
            add(g.get("prefecture") or UNKNOWN, th, g.get("name"))
    for s in (yamlcache.load(DATA_FILES_DIR / "observations" / "spots.yaml") or {}).get("spots") or []:
        th = c["subject_themes"].get(s.get("subject"))
        if th:
            add(s.get("prefecture") or UNKNOWN, th, s.get("name"))
    if records is None:
        from . import observations as O
        records = {}
        for sj in c["subject_themes"]:
            try:
                records[sj] = O.read_records(sj, env)
            except (OSError, ValueError, KeyError):
                records[sj] = []
    for sj, rows in records.items():
        for r in rows:
            kind = r.get("kind") or ""
            th = next((v for k, v in c["kind_themes"].items() if k in kind), None) or c["subject_themes"].get(sj)
            if th == "花":
                th = "花(時期不明)"
            if th:
                add(r.get("prefecture") or UNKNOWN, th, r.get("name") or r.get("spot"))
            if r.get("event"):
                add(r.get("prefecture") or UNKNOWN, "行事", (r.get("name") or "") + str(r.get("event"))[:20])
    if cards is None:
        from . import knowledge as K
        try:
            cards = K.load_shown(env)
        except (OSError, ValueError):
            cards = []
    mts = {s["name"]: s for s in (yamlcache.load(DATA_FILES_DIR / "sites.yaml").get("sites") or []) if s.get("kind") == "mountain"}
    for r in cards:
        m = mts.get(r.get("place"))
        if m:
            add(_nearest_pref(m["lat"], m["lon"]), "山のカード", r.get("title"))
    cat_pref = {}
    for sub in ("autumn_leaves", "flowers", "birds", "wintering_birds"):
        for e in (C.load_catalog(sub) or {}).get("entries") or []:
            cat_pref[e.get("id")] = _pref(e)
    for sub in ("autumn_leaves", "flowers", "birds", "wintering_birds"):
        try:
            doc = yamlcache.load(DATA_FILES_DIR / "sources" / f"{sub}.yaml")
        except OSError:
            continue
        for s in doc.get("sources") or []:
            if (s.get("approval") or {}).get("status") != "approved":
                continue
            prefs = {cat_pref.get(x.get("site")) for x in s.get("covers") or [] if isinstance(x, dict) and x.get("site")} - {None}
            for p in prefs or {UNKNOWN}:
                add(p, "承認済みの情報源", s.get("id"))
    for v in (yamlcache.load(DATA_FILES_DIR / "visitor_centers" / "centers.yaml").get("centers") or []):
        if (v.get("approval") or {}).get("status") == "approved" and not v.get("closed"):
            add(v.get("prefecture") or UNKNOWN, "ビジターセンター", v.get("name"))
    return {p: dict(t) for p, t in tab.items()}


_pts = None


def _nearest_pref(lat, lon):
    """山の座標 → 代表点がいちばん近い都県(地域の辞書の代表点で見た目安)。"""
    global _pts
    pol = C.load_policy()
    r = pol["range_limit"]["earth_radius_km"]
    if _pts is None:
        _pts = []
        for reg in yamlcache.load(DATA_FILES_DIR / "regions.yaml")["regions"]:
            prefs = (reg.get("match") or {}).get("prefectures") or []
            for pt in reg.get("points") or []:
                p = pt.get("prefecture") or (prefs[0] if len(prefs) == 1 else None)
                if p:
                    _pts.append((p, pt["lat"], pt["lon"]))
        for o in yamlcache.load(DATA_FILES_DIR / "ask" / "origins.yaml")["origins"]:
            if o.get("prefecture") and o.get("lat") is not None:
                _pts.append((o["prefecture"], o["lat"], o["lon"]))
    if not _pts:
        return UNKNOWN
    return min(_pts, key=lambda x: C.distance_km(lat, lon, x[1], x[2], r))[0]


def table(env=None, cards=None, records=None):
    """→ Markdown の表(範囲の都県の行 + 範囲外・都県不明の行)。"""
    c = cfg()
    counts = count(env, cards, records)
    prefs = range_prefectures()
    _, origin = _origin_point()
    cols = c["columns"]
    lines = [f"| 都県({origin}から代表点まで) | " + " | ".join(cols) + " | 計 |", "|" + "---|" * (len(cols) + 2)]
    inside = {p for p, _ in prefs}
    for p, km in prefs:
        row = counts.get(p, {})
        lines.append(f"| {p}" + (f"(約{km}km)" if km is not None else "") + " | " + " | ".join(str(row.get(k, 0)) for k in cols) + f" | {sum(row.get(k, 0) for k in cols)} |")
    rest = sorted(p for p in counts if p not in inside)
    for p in rest:
        row = counts[p]
        label = p if p == UNKNOWN else p + "(範囲外)"
        lines.append(f"| {label} | " + " | ".join(str(row.get(k, 0)) for k in cols) + f" | {sum(row.get(k, 0) for k in cols)} |")
    return NL.join(lines) + NL
