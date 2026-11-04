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
from . import yamlcache
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


def effective_src(row, hana=None):
    """行の出どころ。地点を指定した行で、そのすべての地点が花の百名山（sites.yaml の hana_hyakumeizan）なら、「花の百名山に選定」を独立した出どころ 1 件として足す
    （山名の選定の事実。単独では定評にならない: 行には必ず別の出どころが 1 件以上ある）。"""
    src = list(row["src"])
    key = _pol()["hana_source"]
    sites = row.get("sites")
    if sites and key not in src and not row.get("no_hana"):        # no_hana: 紹介サイトなどの 1 件だけの行は、選定の事実で定評に上げない（段階44）
        hana = sites_by_id() if hana is None else hana
        if all(hana.get(s, {}).get("hana_hyakumeizan") for s in sites):
            src.append(key)
    return src


def independent_publishers(row, sources):
    return sorted({sources[s]["publisher"] for s in effective_src(row)})


def grade(row, sources):
    return "established" if len(independent_publishers(row, sources)) >= _v(_pol()["min_sources_established"]) else "tentative"


def sites_by_id():
    """地点 ID → 地点。YAML は大きく、1 回の呼び出しで何百回も呼ばれるので、読み込みは yamlcache で 1 回だけにする（段階46: テストの時間を減らす。出力は変えない）。"""
    d = yamlcache.load(SITES_PATH)
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
        "sources": [{"url": src[s]["url"], "publisher": src[s]["publisher"], "class": src[s]["class"], "read_on": src[s]["read_on"]} for s in effective_src(row)],
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
    if not area and not site_info:
        raise ValueError("--site か --area が要ります")
    if not area:                                           # 地点はあるが、まだどの山域にも結ばれていない
        t = _pol()["text"]
        return {"schema": SCHEMA_OUT, "site": site_info, "area": t["no_area"], "month": month, "status": "preparing", "flowers": [], "upcoming": [],
                "season_note": t["season_note"], "caveats": [t["weather"]], "text": t["preparing"], "conclusion": t["preparing"]}
    if area not in data["areas"]:
        raise ValueError(f"山域 {area} は wildflower_areas.yaml にありません")
    meta = data["areas"][area]
    out = {"schema": SCHEMA_OUT, "site": site_info, "area": area, "month": month, "status": "ok", "flowers": [], "upcoming": [],
           "season_note": t["season_note"], "caveats": [t["care"], t["weather"]]}
    partial = bool(site_info and site_info["id"] in (meta.get("partial_sites") or []))     # 山域全体は準備中でも、一部の地点だけ花暦がある
    if meta["status"] != "ready" and not partial:
        out["status"] = "preparing"
        out["text"] = t["preparing"]
        out["conclusion"] = t["preparing"]
        out["caveats"] = [t["weather"]]
        return out
    rows = [r for r in data["rows"] if r["area"] == area and (not site_info or (not r.get("area_only") and (not r.get("sites") or site_info["id"] in r["sites"])))]
    if partial:
        out["caveats"].append(t["partial_note"])
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
        out["conclusion"] = t["no_data"]
        return out
    names = [f for f in cur][: _v(p["max_names_in_sentence"])]
    sent = t["sentence_site" if site_info else "sentence_area"].format(month=month, area=(site_info["name"] + "（" + area + "）") if site_info else area, items="・".join(_item(f) for f in names))
    if nx:
        sent += t["upcoming"].format(month=nxt, items="・".join(f["name"] for f in nx[: _v(p["max_names_in_sentence"])]))
    if area == "箱根":
        sent += t["garden_note"]
    out["text"] = sent + t["season_note"] + t["care"] + t["weather"]
    out["conclusion"] = sent
    return out


def _months(bloom, tens):
    (m1, _), (m2, _) = parse_bloom(bloom, tens)
    return list(range(m1, m2 + 1)) if m1 <= m2 else list(range(m1, 13)) + list(range(1, m2 + 1))


def _span(rows, tens):
    """花期の月の集合 → '7月〜8月'（続いた月）か '3月・11月'。"""
    ms = sorted({m for r in rows for m in _months(r["bloom"], tens)})
    if not ms:
        return ""
    if ms == list(range(ms[0], ms[-1] + 1)):
        return f"{ms[0]}月" if len(ms) == 1 else f"{ms[0]}月〜{ms[-1]}月"
    return "・".join(f"{m}月" for m in ms)


def _end_key(e, tens):
    """種の花期の終わりの並び順（月×3+旬）。"""
    return max(parse_bloom(pl["bloom"], tens)[1][0] * 3 + parse_bloom(pl["bloom"], tens)[1][1] for pl in e["places"])


def overview(month=None, date_=None, today=None, area=None, site=None):
    """山域も地点も指定がない質問用。データのある地点（高山: 地点つきの花暦）と山域の例年の見頃を、種ごとにまとめる。
    → {kind: overview, month, conclusion, text, species[], ...}。species[] の各: name・section(alpine/lowland)・places[{place, bloom_text, ...}]・flower(代表の行)・start(並び順)。"""
    data = load()
    p = _pol()
    t = p["text"]
    o = p["overview"]
    if date_:
        month = date.fromisoformat(date_).month
    month = month or (today or date.today()).month
    sites = sites_by_id()
    facts = data["facts"]
    tens = p["tens"]
    tens_name = {v: k for k, v in tens.items()}
    ready = {n for n, a in data["areas"].items() if a["status"] == "ready"}
    scope = None
    if site or area:                                       # 山・山域を指定した「この山で見られる」: その場所の全部の花を、見ごろの早い順に
        site_info = None
        if site:
            if site not in sites:
                raise ValueError(f"地点 {site} は data/sites.yaml にありません")
            site_info = {"id": site, "name": sites[site]["name"], "elevation_m": sites[site]["elevation_m"]}
            area = area_of_site(site, data["areas"])
        if not area or area not in data["areas"]:
            raise ValueError("この地点はまだどの山域にも結ばれていません")
        meta = data["areas"][area]
        partial = bool(site_info and site_info["id"] in (meta.get("partial_sites") or []))
        scope = {"area": area, "site": site_info, "ready": meta["status"] == "ready" or partial}

        def keep(r):
            sp = facts["species"].get(r["name"]) or {}
            if site_info:
                if r.get("area_only") or sp.get("protected"):
                    return False
                if r.get("sites") and site_info["id"] not in r["sites"]:
                    return False
                e = r.get("elev")
                if e and e[0] is not None and site_info["elevation_m"] + _v(p["site_elevation_floor_margin_m"]) < e[0]:
                    return False
            return True
        scoped = [r for r in data["rows"] if r["area"] == area and keep(r)] if scope["ready"] else []
        pool_rows = scoped
    else:
        pool_rows = [r for r in data["rows"] if r.get("sites") or r["area"] in ready]
    floor = _v(p["alpine_min_elevation_m"])

    sub_floor = _v(p["subalpine_min_elevation_m"])

    def row_elev(r):                                       # 行の場所の標高: 地点つきはいちばん低い地点、地点なしは行の place_elev_m（出どころに標高があるときだけ）
        if r.get("sites"):
            return min(sites[x]["elevation_m"] for x in r["sites"])
        return r.get("place_elev_m")

    def is_alpine(r):                                      # 高山: 地点つきの行で、すべての地点が森林限界の目安の標高以上
        return bool(r.get("sites")) and all(sites[x]["elevation_m"] >= floor for x in r["sites"])

    def tier_of(r):                                        # alpine（2500m以上）/ subalpine（1500m以上の亜高山・高原）/ lowland
        if is_alpine(r):
            return "alpine"
        e = row_elev(r)
        return "subalpine" if e is not None and e >= sub_floor else "lowland"
    alpine_rows = [r for r in pool_rows if is_alpine(r)]
    low_rows = [r for r in pool_rows if not is_alpine(r)]
    place_names = []
    for r in alpine_rows:
        for sid in r["sites"]:
            if sites[sid]["name"] not in place_names:
                place_names.append(sites[sid]["name"])

    def bloom_text(r):
        (m1, t1), (m2, t2) = parse_bloom(r["bloom"], tens)
        prec = any(c in str(r["bloom"]) for c in tens)
        a = f"{m1}月" + (tens_name[t1] if prec else "")
        b = f"{m2}月" + (tens_name[t2] if prec else "")
        return a if a == b else f"{a}〜{b}"
    tier_rank = {"alpine": 0, "subalpine": 1, "lowland": 2}
    entries = {}
    for section, rows in (("alpine", alpine_rows), ("lowland", low_rows)):
        for r in rows:
            sp = facts["species"].get(r["name"]) or {}
            label = "・".join(sites[x]["name"] for x in r["sites"]) if r.get("sites") else r["area"]
            f = _flower(r, facts, False)
            e = entries.setdefault((section, r["name"]), {"name": r["name"], "section": section, "tier": tier_of(r), "places": [], "flower": f, "protected": bool(sp.get("protected")), "_rows": []})
            if tier_rank[tier_of(r)] < tier_rank[e["tier"]]:        # 同じ種が複数の場所にあるときは、いちばん高い場所の区分に置く
                e["tier"] = tier_of(r)
            e["places"].append({"place": label, "bloom_text": bloom_text(r), "bloom": r["bloom"], "elevation_m": r.get("elev"), "note": r.get("note"),
                                "active_now": month_active(r["bloom"], month, tens)})
            e["_rows"].append(r)
            if (f["source_count"], f["grade"] == "established") > (e["flower"]["source_count"], e["flower"]["grade"] == "established"):
                e["flower"] = f
    species = []
    for e in entries.values():
        rows = e.pop("_rows")
        e["sources"] = list({s["url"]: s for r in rows for s in _flower(r, facts, False)["sources"]}.values())
        e["start"] = min(parse_bloom(r["bloom"], tens)[0][0] * 3 + parse_bloom(r["bloom"], tens)[0][1] for r in rows)
        e["active_now"] = any(pl["active_now"] for pl in e["places"])
        species.append(e)
    species.sort(key=lambda e: (0 if e["section"] == "alpine" else 1, e["start"], e["name"]))
    span = _span(alpine_rows, tens)
    alpine_now = any(month_active(r["bloom"], month, tens) for r in alpine_rows)
    now_low = sorted((e for e in species if e["section"] == "lowland" and e["active_now"] and not e["protected"]),
                     key=lambda e: (-e["flower"]["source_count"], e["name"]))
    k = _v(p["max_names_in_sentence"])
    places = "・".join(place_names)
    sent = (o["alpine_now"] if alpine_now else o["not_now"]).format(month=month, span=span, places=places)
    sent += o["lowland_now"].format(month=month, items="・".join(e["name"] for e in now_low[:k])) if now_low else o["lowland_none"].format(month=month)
    if scope:
        for e in species:
            e["section"] = "mountain"
        species.sort(key=lambda e: (e["start"], e["name"]))
        place = (scope["site"]["name"] + "（" + scope["area"] + "）") if scope["site"] else scope["area"]
        if not species:
            sent = t["preparing"] if not scope["ready"] else t["no_data"]
        else:
            first, last = species[0], max(species, key=lambda e: (_end_key(e, tens), e["name"]))
            sent = o["mountain"].format(place=place, first=first["name"], first_month=first["start"] // 3, last=last["name"], last_month=_end_key(last, tens) // 3)
            now_names = [e["name"] for e in species if e["active_now"]][:k]
            sent += o["mountain_now"].format(month=month, items="・".join(now_names)) if now_names else o["mountain_none"].format(month=month)
        return {"schema": SCHEMA_OUT, "kind": "mountain", "site": scope["site"], "area": place, "month": month, "status": "ok" if species else "no_data", "alpine_now": False,
                "alpine_span": "", "places": [place], "species": species, "flowers": [], "upcoming": [], "season_note": t["season_note"],
                "caveats": [t["care"], t["weather"]], "conclusion": sent, "text": sent + t["season_note"] + t["care"] + t["weather"]}
    return {"schema": SCHEMA_OUT, "kind": "overview", "site": None, "area": o["area_label"], "month": month, "status": "ok", "alpine_now": alpine_now,
            "alpine_span": span, "places": place_names, "species": species, "flowers": [], "upcoming": [],
            "season_note": t["season_note"], "caveats": [t["care"], t["weather"], t["partial_note"]], "conclusion": sent,
            "text": sent + t["season_note"] + t["care"] + t["weather"]}


def wildflower_cmd(a):
    if not a.site and not a.area:                          # 山域も地点も指定がない質問: データのある地点・山域の例年の見頃をまとめて答える
        r = overview(month=a.month, date_=a.date)
    elif not a.month and not a.date:
        r = overview(area=a.area, site=a.site)
    else:
        r = query(site=a.site, area=a.area, month=a.month, date_=a.date)
    if a.json:
        if r.get("kind") in ("overview", "mountain"):
            r = dict(r, species=[{k: v for k, v in e.items() if k != "flower"} for e in r["species"]])
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(r["text"])
    return 0


def audit():
    """野草の点検(通信しない・書き込まない): 出どころのない行・標高と花期の矛盾・保護種の説明の欠け・山域ごとの被覆率と定評/仮の内訳。"""
    d = load()
    src, sp = d["facts"]["sources"], d["facts"]["species"]
    problems, by_area = [], {}
    for r in d["rows"]:
        a = by_area.setdefault(r["area"], {"rows": 0, "species": set(), "months": set(), "established": 0, "tentative": 0, "publishers": set()})
        a["rows"] += 1
        a["species"].add(r["name"])
        a["months"].update(m for m in range(1, 13) if month_active(r["bloom"], m))
        a[grade(r, src)] += 1
        a["publishers"].update(independent_publishers(r, src))
        if not r.get("src") or any(s not in src for s in r["src"]):
            problems.append(f"{r['area']} {r['name']}: 出どころがない")
        if r.get("elev") and r["elev"][0] is not None and r["elev"][1] is not None and r["elev"][0] > r["elev"][1]:
            problems.append(f"{r['area']} {r['name']}: 標高の範囲が逆")
        if sp.get(r["name"], {}).get("protected") and not sp[r["name"]].get("caution"):
            problems.append(f"{r['name']}: 保護種に注意の文がない")
        if sp.get(r["name"], {}).get("protected") and r.get("note") and any(w in r["note"] for w in ("山", "林道", "尾根", "沢")):
            problems.append(f"{r['area']} {r['name']}: 保護種の行に場所を思わせる語がある")
    cover = {k: {"rows": v["rows"], "species": len(v["species"]), "months_covered": len(v["months"]), "established": v["established"],
                 "tentative": v["tentative"], "publishers": len(v["publishers"])} for k, v in by_area.items()}
    return {"problems": problems, "areas": cover, "preparing": [k for k, v in d["areas"].items() if v["status"] != "ready"]}


if __name__ == "__main__":
    r = audit()
    print(json.dumps(r, ensure_ascii=False, indent=1))
    raise SystemExit(1 if r["problems"] else 0)
