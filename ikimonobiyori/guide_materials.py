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


def _city_parts(city):
    """市区町村の欄 → 名前の一覧(「横浜市中区」→ 横浜市中区・中区。「伊東市・伊豆市」は分ける)。"""
    out = []
    for part in re.split(r"[・、]", city or ""):
        part = part.strip()
        if not part:
            continue
        out.append(part)
        m = re.match(r"^(.+?[市郡])(.+[町村区])$", part)
        if m:
            out.append(m.group(2))
    return out


def _town_names():
    """段階80 の追記(本人の判断 2026-11-11): 名所の記録にある市区町村の名前の集合(名所カタログ・観察の名所・ガイドのカタログ)。"""
    out = {p for v in _index().values() for p in _city_parts(v.get("city"))}
    out |= {p for r in _official_records() for p in _city_parts(r.get("city"))}    # 段階80 の追記4: 読んだ事実の記録だけにある市区町村(那須塩原市の紅葉)
    return out


RECORD_SUBJECTS = ("flowers", "birds", "autumn_leaves")


def _official_records():
    """読んだ事実の記録のうち、公式・名前・市区町村・種・例年の時期のそろったもの(名所の記録として使えるもの)。[(subject, record)] ではなく record に _subject を付ける。"""
    from . import observations as O
    out = []
    for sj in RECORD_SUBJECTS:
        try:
            recs = O.read_records(sj)
        except (OSError, ValueError, KeyError):
            continue
        out += [{**r, "_subject": sj} for r in recs if r.get("source_class") == "official" and r.get("name") and r.get("city")
                and r.get("typical") and r.get("kind")]
    return out


def town_of(word, names=None):
    """質問の地名(「南伊豆」「松田町」)→ 名所の記録にある市区町村の名前(「南伊豆町」)か None。
    名前そのもの、または末尾の 市・町・村・区 を除いた形(2 字以上)が一致するときだけ(「南伊豆」を「伊豆市」にしない)。"""
    w = (word or "").strip()
    if len(w) < 2:
        return None
    names = _town_names() if names is None else names
    if w in names:
        return w
    for n in sorted(names, key=lambda x: (-len(x), x)):
        stem = re.sub(r"(市|町|村|区)$", "", n)
        if len(stem) >= 2 and stem == w:
            return n
    return None


def question_towns(question):
    """質問の文 → 名所の記録にある市区町村の名前の一覧。エリア・地域・出発地・名所の辞書で分かる地名(箱根・横浜・秩父など)は除く
    (今までどおりエリアや出発地として扱う)。"""
    from . import guide_verify as GV
    from . import place_guard as PG
    from . import research as RS
    dic = GV._dictionary_places()
    out = []
    for w in RS.question_places(question):
        if w in dic or PG.is_known(w):
            continue
        t = town_of(w)
        if t and t not in out:
            out.append(t)
    return out


def in_town(name, city, towns):
    """名所が市区町村の一覧のどれかにあるか(名所の欄の市区町村、なければ名所の辞書の市区町村)。"""
    parts = _city_parts(city or place_info(name).get("city"))
    return any(t in parts for t in towns)


def town_spots(town, origin=None):
    """段階80 の追記: 市区町村 → その名所の一覧 [{name, prefecture, city, seasons: [(text, kind)], kinds, url, publisher, source_class, tentative}]。
    名所カタログ(承認済み)・ガイドのカタログ(承認済みと、検索で集めた仮の名所)。行事の期間は例年の時期にしない。"""
    from . import guide
    from . import observations as O
    from . import publisher as P
    from . import season_place as SP
    opol = O.load_policy()
    thirds = SP.cfg()["text"]["thirds"]
    rows, seen = [], {}

    def key(n):
        return re.sub(r"[\s()（）・]", "", n or "")
    for e in SP._all_entries():
        if not e.get("city") or town not in _city_parts(e["city"]):
            continue
        seasons = [(SP.catalog_window_text(w, thirds), w.get("kind")) for w in e.get("windows") or []
                   if w.get("start") and w.get("end") and not O.event_derived(w, e.get("events"), opol, e["name"])]
        if e.get("season_text"):
            seasons.append((e["season_text"], "・".join(x for x in e["kinds"][:2] if x)))
        k = key(e["name"])
        if k in seen:
            r = seen[k]
            r["seasons"] += [x for x in seasons if x not in r["seasons"]]
            r["kinds"] = list(dict.fromkeys(r["kinds"] + [x for x in e["kinds"] if x]))
            continue
        url = e.get("url")
        seen[k] = {"name": e["name"], "prefecture": e.get("prefecture"), "city": e.get("city"), "seasons": seasons,
                   "kinds": [x for x in e["kinds"] if x], "url": url, "publisher": None,
                   "source_class": "official" if url and P.shows_official(url) else ("secondary" if url else None), "tentative": False,
                   "subject": e.get("subject")}
        rows.append(seen[k])
    try:
        entries = guide.build()[0]
    except (OSError, ValueError, KeyError):
        entries = []
    for e in entries:
        if e.get("scope") != "place" or town not in _city_parts(e.get("municipality")) or key(e.get("name")) in seen:
            continue
        src = [x for x in e.get("sources") or [] if x.get("url") and not P.unused_source(x["url"])]
        if not src:
            continue
        best = sorted(src, key=lambda x: (x.get("class") or "Z", x["url"]))[0]
        season = e.get("season") or {}
        kinds = [k["kind"] for k in e.get("kinds") or [] if k.get("kind")]
        r = {"name": e["name"], "prefecture": e.get("prefecture"), "city": e.get("municipality"),
             "seasons": [(season["text"], "・".join(kinds[:2]))] if season.get("text") else [], "kinds": kinds,
             "url": best["url"], "publisher": best.get("publisher"),
             "source_class": "official" if best.get("class") in ("A", "B") else "secondary", "tentative": not guide.approved(e),
             "subject": e.get("theme")}
        seen[key(e["name"])] = r
        rows.append(r)
    _confirm_with_records(rows, town, key)
    return rows


def _confirm_with_records(rows, town, key):
    """段階80 の追記2(本人の判断 2026-11-11): 公式ページで確かめて記録した名所(読んだ事実の記録。公式・種と例年の時期つき)で、仮の名所の印を外す
    (出典を確かめたページにする)。名前は記号を除いて一致するか、片方がもう片方を含むとき同じ名所とみなす。記録だけにある名所は仮でない行として足す。
    確かめられなかった名所は仮のまま。"""
    for rec in _official_records():
        sj = rec["_subject"]
        if town not in _city_parts(rec.get("city")):
            continue
        k = key(rec["name"])
        same = [r for r in rows if k and (key(r["name"]) == k or (key(r["name"]) and (key(r["name"]) in k or k in key(r["name"]))))]
        season = (rec["typical"], rec["kind"])
        if not same:
            rows.append({"name": rec["name"], "prefecture": rec.get("prefecture"), "city": rec.get("city"), "seasons": [season],
                         "kinds": [rec["kind"]], "url": rec.get("url"), "publisher": rec.get("publisher"), "source_class": "official",
                         "tentative": False, "confirmed_by": rec.get("url"), "subject": sj})
            continue
        for r in same:
            if not r["tentative"]:
                continue
            r.update(tentative=False, url=rec.get("url"), publisher=rec.get("publisher"), source_class="official",
                     seasons=[season], confirmed_by=rec.get("url"))


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


def straight_range(name, origin, *, prefecture=None, city=None):
    """名所 → (範囲 {origin, km, status} か None, 根拠: point / city / None, point)。座標 → 市区町村の代表点の順。"""
    from . import catalog as CM
    from . import origins
    info = place_info(name)
    pt = info.get("point")
    pol = CM.load_policy()
    try:
        if pt:
            return CM.range_from(pol, pt, origin), "point", pt
        city = city or info.get("city")
        mp = origins.municipal_point(city) if city else None
        if mp:
            return CM.range_from(pol, mp, origin), "city", None
    except (KeyError, TypeError, ValueError, StopIteration):
        pass
    return None, None, None


def straight_km(name, origin, *, prefecture=None, city=None):
    """名所 → (km, 根拠: point / city / None, point)。座標 → 市区町村の代表点 → (None, None, None)。"""
    rg, basis, pt = straight_range(name, origin, prefecture=prefecture, city=city)
    return (rg["km"] if rg else None), basis, pt


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
        return SpeciesRows()
    spread = bool(cond.get("defaulted_date")) and bool(R.get("spread"))      # 段階78 の追記: 日付の指定がない種の質問は、まとまりごとに枠を分ける
    spc = dict(SP.cfg(), max_items=(10 ** 6 if spread else R["max_known"]), max_unknown_items=R["max_unknown"])
    prefs = None
    if cond.get("region"):
        try:
            prefs = (O.resolve(cond["region"], cond.get("origin"), O.load_policy()) or {}).get("prefectures") or None
        except (KeyError, TypeError, ValueError):
            prefs = None
    place = SP.place_filter(question)
    origin = cond.get("origin")
    out, dropped = SpeciesRows(), []
    for sp in sps:
        is_bird = sp["name"] in (spc.get("bird_species") or [])
        try:
            rows, _n = SP.select(SP.gather(sp, origin, spc, env), origin, prefs, spc, by_distance=is_bird)
        except (OSError, ValueError, KeyError, TypeError):
            rows = []
        if spread:
            if is_bird:
                rows = rows[: R["max_known"]]
            else:
                known = [r for r in rows if r.get("start") and r.get("season")]
                rows = spread_rows(known, sp["name"], R["max_known"], R["spread"]) + [r for r in rows if r not in known]
        if R.get("drop_unknown_when_known") and sum(1 for r in rows if r.get("season")) >= R["drop_unknown_when_known"]:
            keep = [r for r in rows if r.get("season") or (place and place.get("cities") and SP._in_cities(r, place["cities"]))]   # 段階79 第1部 3: 時期の分かる名所が十分あれば、時期の記載のない名所は入れない(聞かれた場所の名所は残す)
            dropped += [r["name"] for r in rows if r not in keep]
            rows = keep
        if place and place.get("cities"):
            own = [r for r in rows if SP._in_cities(r, place["cities"])]
            rows = own + [r for r in rows if r not in own]
        for r in rows:
            note = None
            if re.search(r"\d{4}年の記載", r.get("season") or ""):
                note = R["old_note"]
            elif r.get("season") and not r.get("start") and r["season"] not in SP._year_round_words():   # 通年は「あいまい」ではない(段階82)
                note = R["vague_note"]
            out.append({"species": sp["name"], "name": r["name"], "prefecture": r.get("prefecture"), "city": r.get("city"),
                        "km": r.get("km"), "km_estimated": r.get("km_estimated"), "season": r.get("season"), "kinds": r.get("kinds") or [],
                        "start": r.get("start") if r.get("season") else None, "end": r.get("end") if r.get("season") else None,
                        "url": r.get("url"), "official": bool(r.get("official")), "publisher": r.get("publisher") or None,
                        "care": r.get("care"), "note": note, "in_place": bool(place and place.get("cities") and SP._in_cities(r, place["cities"])),
                        **{k: r[k] for k in ("notice", "closed_period", "best_conditions", "secondary_season") if r.get(k)}})
    merge_same_places(out)
    out.dropped = [n for n in dropped if n not in {r["name"] for r in out}]
    return out


def merge_same_places(rows):
    """段階80 E(提案6): 「爪木崎」と「爪木崎の水仙」は同じ名所(同じ種・同じ市町村で、名前が「<短い名前>の…」)。
    長い名前の行を短い名前にそろえる(時期と出典はそれぞれの行に残す。元の名前は merged_from)。"""
    for r in rows:
        same = [o for o in rows if o is not r and o["species"] == r["species"] and (o.get("city") or "") == (r.get("city") or "")
                and len(o["name"]) >= 2 and r["name"].startswith(o["name"] + "の")]
        if same:
            r["merged_from"], r["name"] = r["name"], min(same, key=lambda o: len(o["name"]))["name"]
    return rows


class SpeciesRows(list):
    """種の名所の行の一覧。dropped は、時期の記載がないので外した名所の名前(段階79 第1部 3。資料のほかの節にも入れない)。"""
    dropped = ()


def _md_in(md, lo, hi):
    return lo <= md <= hi if lo <= hi else (md >= lo or md <= hi)


def row_group(r, groups):
    """名所の行 → まとまりの名前。種がまとまりの種に当たり、始まりの月日がその範囲に入るものを先に。なければ月日だけで。"""
    kinds = set(r.get("kinds") or [])
    md = r.get("start") or ""
    for g in groups:
        if kinds & set(g.get("kinds") or []) and _md_in(md, g["from"], g["to"]):
            return g["name"]
    for g in groups:
        if _md_in(md, g["from"], g["to"]):
            return g["name"]
    return groups[-1]["name"]


def spread_rows(rows, species, limit, conf):
    """時期の分かる名所の行(今から近い順に並んでいる)を、まとまりごとに順に 1 件ずつ取って limit 件まで(段階78 の追記。本人の指示 2026-11-11)。
    種の表がなければ、始まりの月ごとのまとまり。まとまりの並びは表の順(表がなければ月の順)、まとまりの中は元の順。"""
    groups = (conf.get("groups") or {}).get(species)
    if groups:
        order = [g["name"] for g in groups]
        key = lambda r: row_group(r, groups)          # noqa: E731
    else:
        order = sorted({(r.get("start") or "")[:2] for r in rows})
        key = lambda r: (r.get("start") or "")[:2]    # noqa: E731
    bins = {k: [] for k in order}
    for r in rows:
        bins.setdefault(key(r), []).append(r)
    picked, i = [], 0
    while len(picked) < limit and any(len(b) > i for b in bins.values()):
        for k in order:
            if len(picked) < limit and len(bins[k]) > i:
                picked.append(bins[k][i])
        i += 1
    return [r for k in order for r in bins[k] if r in picked]


def months_of(start, end):
    from . import season_place as SP
    return SP.months_of(start, end)


def _span(rows):
    """名所の行の例年の時期 → (始まりの月, 終わりの月)。今までの形の答えと同じ計算(season_place.month_span)。"""
    from . import season_place as SP
    return SP.month_span(rows)


def species_leads(sprows, today, c=None):
    """段階78 の追記(本人の指示 2026-11-11): 日付の指定がない種の質問の全体の目安を、資料に入った名所の時期から作る。
    → {種: [文]}。種の表(まとまり)があれば、まとまりごとの時期。今が例年の時期か・次はいつかも同じ名所から。"""
    from . import season_place as SP
    c = c or cfg()
    conf = c["species_rows"].get("spread") or {}
    T = conf["text"]
    t = SP.cfg()["text"]
    out = {}
    for sp in dict.fromkeys(r["species"] for r in sprows):
        rows = [r for r in sprows if r["species"] == sp and r.get("start") and r.get("end")]
        if sp in (SP.cfg().get("bird_species") or []):
            continue
        if not rows:                                  # 資料の名所に時期の分かるものがない: コードの答えの時期(ほかの名所から)は書かない
            out[sp] = [T["none"].format(name=sp)]
            continue
        groups = (conf.get("groups") or {}).get(sp)
        lines = []
        if groups:
            parts = []
            for g in groups:
                sp_ = _span([r for r in rows if row_group(r, groups) == g["name"]])
                if sp_:
                    parts.append(T["part_one"].format(group=g["name"], start=sp_[0]) if sp_[0] == sp_[1]
                                 else T["part"].format(group=g["name"], start=sp_[0], end=sp_[1]))
            lines.append(T["lead_groups"].format(name=sp, parts=T["sep"].join(parts)))
        else:
            a, b = _span(rows)
            lines.append(t["lead_one"].format(name=sp, start=f"{a}月") if a == b else t["lead"].format(name=sp, start=f"{a}月", end=f"{b}月"))
        if any(SP._in_window(today, r["start"], r["end"]) for r in rows):
            lines.append(t["in_season"])
        else:
            nm = SP._next_month(today, rows)
            if nm:
                lines.append(t["off_season"].format(month=nm))
        out[sp] = lines
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
