"""野草・高山植物(花が咲くもの)の「例年の時期」の知識を、コンシェルジュが山の提案に添えられる形で出す(段階40。指示書 docs/stage40-wildflower-instructions.md)。

- 通信しない。データは data/guide/ の wildflower_areas.yaml(山域 → 地点)・wildflower_facts.yaml(種と出どころ)・wildflower_calendar.yaml(山域×花期×標高)。
- 地点の鍵は data/sites.yaml の識別子(ヤマビヨリの mNNN と同じ)。今年の開花は読まない(例年の目安)。
- 保護が必要な種(protected)は地点を出さない。山域の出力にだけ載せ、地点の出力には載せない。
- 値と文は policy.yaml の wildflower。山の天気・コース・危険箇所は扱わない。"""
import functools
import json
from datetime import date

import yaml

from . import guide
from .paths import SITES_PATH

SCHEMA_OUT = "ikimono-wildflower/1"


@functools.lru_cache(maxsize=1)
def _pol():
    return guide.load_policy()["wildflower"]


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def _load(name):
    return yaml.safe_load((guide.GUIDE_DIR / name).read_text(encoding="utf-8"))


def load():
    p = _pol()
    return {"areas": _load(p["areas_file"])["areas"], "facts": _load(p["facts_file"]), "rows": _load(p["calendar_file"])["rows"]}


def parse_bloom(s, tens=None):
    """'5上-6中' / '3-4' / '8中' → (開始 (月, 旬), 終了 (月, 旬))。旬の記載がない開始は上旬、終了は下旬として扱う（精度は月）。"""
    tens = tens or _pol()["tens"]
    parts = str(s).split("-")
    a, b = parts[0], parts[-1]

    def one(tok, default):
        tok = tok.strip()
        t = tok[-1] if tok and tok[-1] in tens else None
        m = int(tok[:-1] if t else tok)
        return m, tens[t] if t else tens[default]
    return one(a, "上"), one(b, "下")


def month_active(bloom, month, tens=None):
    (m1, t1), (m2, t2) = parse_bloom(bloom, tens)
    span = list(range(m1, m2 + 1)) if m1 <= m2 else list(range(m1, 13)) + list(range(1, m2 + 1))
    return month in span


def independent_publishers(row, sources):
    return sorted({sources[s]["publisher"] for s in row["src"]})


def grade(row, sources):
    return "established" if len(independent_publishers(row, sources)) >= _v(_pol()["min_sources_established"]) else "tentative"


def sites_by_id():
    d = yaml.safe_load(SITES_PATH.read_text(encoding="utf-8"))
    return {s["id"]: s for s in d["sites"]}


def area_of_site(site_id, areas):
    for name, a in areas.items():
        if site_id in (a.get("sites") or []):
            return name
    return None


_TABLE = {}


def _photo(name):
    try:
        from . import guide_photos
        if "t" not in _TABLE:
            _TABLE["t"] = guide_photos.load_table()
        t = _TABLE["t"].get(name)
        if not t:
            return None, False
        return int(t["taxon_id"]), bool(guide_photos.has_cache(t["taxon_id"]))
    except Exception:                                      # 写真の表が読めなくても出力を止めない
        return None, False


def _flower(row, facts, with_photo=True):
    src = facts["sources"]
    sp = facts["species"].get(row["name"]) or {}
    tid, has = _photo(row["name"]) if with_photo else (None, False)
    t = _pol()["text"]
    return {
        "name": row["name"], "scientific": sp.get("scientific"), "taxon_id": tid, "family": sp.get("family"),
        "elevation_m": row.get("elev"), "bloom": row["bloom"], "bloom_precision": "decade" if any(c in str(row["bloom"]) for c in _pol()["tens"]) else "month",
        "tip": sp.get("tip"), "caution": sp.get("caution"), "protected": bool(sp.get("protected")),
        "grade": grade(row, src), "grade_label": t["established"] if grade(row, src) == "established" else t["tentative"],
        "source_count": len(independent_publishers(row, src)),
        "sources": [{"url": src[s]["url"], "publisher": src[s]["publisher"], "class": src[s]["class"], "read_on": src[s]["read_on"]} for s in row["src"]],
        "photo": has, "note": row.get("note"),
    }


def _rank(f):
    return (0 if f["grade"] == "established" else 1, -f["source_count"], 0 if f["elevation_m"] else 1, f["name"])


def _item(f):
    t = _pol()["text"]
    e = f["elevation_m"]
    if e and e[0] is not None and e[1] is not None:
        return t["item_elev"].format(name=f["name"], lo=e[0], hi=e[1])
    if e and e[0] is not None:
        return t["item_elev_lo"].format(name=f["name"], lo=e[0])
    if e and e[1] is not None:
        return t["item_elev_hi"].format(name=f["name"], hi=e[1])
    return t["item_plain"].format(name=f["name"])


def query(site=None, area=None, month=None, date_=None, today=None, with_photo=True):
    """→ {schema, site, area, month, status, flowers[], upcoming[], season_note, caveats[], text}。該当がなければ空の結果。"""
    data = load()
    p = _pol()
    t = p["text"]
    if date_:
        month = date.fromisoformat(date_).month
    month = month or (today or date.today()).month
    site_info = None
    if site:
        sites = sites_by_id()
        if site not in sites:
            raise ValueError(f"地点 {site} は data/sites.yaml にありません")
        s = sites[site]
        site_info = {"id": s["id"], "name": s["name"], "elevation_m": s["elevation_m"]}
        area = area_of_site(site, data["areas"])
    if not area:
        raise ValueError("--site か --area が要ります(site が山域に結ばれていないときは --area を使う)")
    if area not in data["areas"]:
        raise ValueError(f"山域 {area} は wildflower_areas.yaml にありません")
    meta = data["areas"][area]
    out = {"schema": SCHEMA_OUT, "site": site_info, "area": area, "month": month, "status": "ok", "flowers": [], "upcoming": [],
           "season_note": t["season_note"], "caveats": [t["care"], t["weather"]]}
    if meta["status"] != "ready":
        out["status"] = "preparing"
        out["text"] = t["preparing"]
        out["caveats"] = [t["weather"]]
        return out
    rows = [r for r in data["rows"] if r["area"] == area]
    nxt = (month + _v(p["upcoming_months"]) - 1) % 12 + 1

    def keep(r):
        sp = data["facts"]["species"].get(r["name"]) or {}
        if site_info and sp.get("protected"):                  # 保護が必要な種は、地点を出さない（山域までにする）
            return False
        e = r.get("elev")
        if site_info and e and e[0] is not None and site_info["elevation_m"] + _v(p["site_elevation_floor_margin_m"]) < e[0]:
            return False
        return True
    cur = sorted((_flower(r, data["facts"], with_photo) for r in rows if keep(r) and month_active(r["bloom"], month)), key=_rank)
    nx = sorted((_flower(r, data["facts"], False) for r in rows if keep(r) and not month_active(r["bloom"], month) and month_active(r["bloom"], nxt)), key=_rank)
    out["flowers"] = cur
    out["upcoming"] = [{"name": f["name"], "bloom": f["bloom"], "elevation_m": f["elevation_m"]} for f in nx]
    if any((data["facts"]["species"].get(r["name"]) or {}).get("protected") for r in rows if month_active(r["bloom"], month)) and site_info:
        out["caveats"].append(t["protected_note"])
    if area == "箱根":
        out["caveats"].append(t["garden_note"])
    if not cur:
        out["status"] = "no_data"
        out["text"] = t["no_data"] + t["season_note"]
        return out
    names = [f for f in cur][: _v(p["max_names_in_sentence"])]
    sent = t["sentence_site" if site_info else "sentence_area"].format(month=month, area=(site_info["name"] + "（" + area + "）") if site_info else area, items="・".join(_item(f) for f in names))
    if nx:
        sent += t["upcoming"].format(month=nxt, items="・".join(f["name"] for f in nx[: _v(p["max_names_in_sentence"])]))
    if area == "箱根":
        sent += t["garden_note"]
    out["text"] = sent + t["season_note"] + t["care"] + t["weather"]
    return out


def wildflower_cmd(a):
    r = query(site=a.site, area=a.area, month=a.month, date_=a.date)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(r["text"])
    return 0
