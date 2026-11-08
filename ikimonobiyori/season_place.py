"""段階64 第3部: 日付を聞いていない「いつ・どこ」の質問の答え(時期と場所)。通信しない・書き込まない。

「藤が有名な場所と時期を教えて」「ニッコウキスゲはいつどこへ行けばいい?」のように、種や花の名前と「いつ・どこ」を聞く質問に、
名所カタログ(data/catalog/*.yaml)・ガイドのカタログ(data/guide/catalog.yaml)・読んだ事実の記録(ask record の kind と typical)から、
時期の早い順の名所の一覧を作る。**今の日付で候補を絞らない**(時期の外でも名所を出し、次の時期を 1 文で書く)。
範囲(出発地から 250km 前後)の外と、都県の指定の外は出さない。事実は記録・カタログの値だけ(一般知識から作らない)。
語と文は data/ask/season_place.yaml。"""
import re
from datetime import date
from urllib.parse import urlparse

from . import yamlcache
from .paths import DATA_FILES_DIR

CONFIG = DATA_FILES_DIR / "ask" / "season_place.yaml"
NL = chr(10)


def cfg():
    return yamlcache.load(CONFIG)


# ---- 質問 → 種 ----

def _catalog_kinds():
    """名所カタログ・ガイドのカタログにある種の語(長い順)。"""
    out = set()
    for e in _flower_entries():
        out |= set((e.get("tags") or {}).get("flower_kinds") or [])
        out |= {w.get("kind") for w in e.get("flower_windows") or [] if w.get("kind")}
    for e in _guide_entries():
        out |= {k.get("kind") for k in e.get("kinds") or [] if k.get("kind")}
    return sorted((k for k in out if k and len(k) >= 2), key=len, reverse=True)


def _sp_doc(sp):
    return {"name": sp["name"], "match": list(sp["match"]), "words": list(sp.get("words") or sp["match"]), "includes": list(sp.get("includes") or [])}


def resolve_all(question, c=None):
    """質問の文 → 種の一覧(質問に出た順。「菜の花や桜」は 2 つ)。ほかの語の中の語(「冬桜」の中の「桜」)は数えない。
    別名の表(長い語から)→ カタログの種の語がそのまま質問にある、の順。推測で結びつけない。"""
    c = c or cfg()
    q = question or ""
    hits = []
    for sp in c["species"]:
        for w in sorted(sp["words"], key=len, reverse=True):
            for m in re.finditer(re.escape(w), q):
                hits.append((m.start(), m.end(), sp))
    keep = []
    for a, b, sp in sorted(hits, key=lambda x: (x[0], -(x[1] - x[0]))):
        if any(a >= a2 and b <= b2 and (a, b) != (a2, b2) for a2, b2, _ in hits):
            continue                                                      # もっと長い語の中にある
        if sp["name"] not in [x["name"] for x in keep]:
            keep.append(_sp_doc(sp))
    if keep:
        return keep
    for k in _catalog_kinds():
        if k in q:
            return [{"name": k, "match": [k], "words": [k], "includes": []}]
    return []


def resolve_species(question, c=None):
    """質問の文 → 最初の種 {name, match, words, includes} か None。"""
    got = resolve_all(question, c)
    return got[0] if got else None


def is_season_place(question, c=None):
    """日付を聞いていない「いつ・どこ」の質問か(種の名前があり、時期と場所の言い方があり、日付の語がない)。"""
    c = c or cfg()
    q = question or ""
    if any(re.search(w, q) for w in c["date_words"]):
        return False
    if not any(re.search(p, q) for p in c["patterns"]):
        return False
    return resolve_species(q, c) is not None


# ---- 名所の材料 ----

def _flower_entries():
    from . import catalog as CM
    out = []
    for sj in ("flowers", "birds", "wintering_birds"):
        try:
            doc = CM.load_catalog(sj)
        except (OSError, ValueError, KeyError):
            continue
        out += [dict(e, _subject=sj) for e in doc.get("entries") or [] if not e.get("example") and e.get("status") == "approved"]
    return out


def _guide_entries():
    try:
        doc = yamlcache.load(DATA_FILES_DIR / "guide" / "catalog.yaml")
    except OSError:
        return []
    return [e for e in doc.get("entries") or [] if e.get("scope") == "place" and e.get("prefecture")
            and (e.get("approval") or {}).get("state") in ("provisional", "approved")]


def _matches(text, match, sp=None, c=None):
    """種の語に当たるか。ほかの種の、より長い語に当たる語(梅の質問の「蝋梅」)は外す(その種が includes にあるときは含める)。"""
    if not text or not any(m in text for m in match):
        return False
    if sp is None:
        return True
    c = c or cfg()
    best = max(len(m) for m in match if m in text)
    inc = set(sp.get("includes") or [])
    for other in c["species"]:
        if other["name"] == sp["name"] or other["name"] in inc:
            continue
        if any(m2 in text and len(m2) > best for m2 in other["match"]):
            return False
    return True


def _name_matches(name, match, sp, c):
    """名所の名前で当てるのは 2 字以上の語だけ(「桜木」「藤沢」のような地名に当てない)。"""
    return _matches(name, [m for m in match if len(m) >= 2], sp, c)


def _third(md, thirds):
    m, d = int(md[:2]), int(md[3:])
    for name, (a, b) in thirds.items():
        if a <= d <= b:
            return f"{m}月{name}"
    return f"{m}月"


def window_text(start, end, thirds):
    a, b = _third(start, thirds), _third(end, thirds)
    return a if a == b else f"{a}〜{b}"


def _km(point, city, origin, cat_pol):
    """(km, 見積もりか)。座標 → 市区町村の代表点 → (None, False)。"""
    from . import catalog as CM
    from . import origins
    if point and point.get("lat") is not None:
        return CM.range_from(cat_pol, point, origin)["km"], False
    p = origins.municipal_point(city) if city else None
    if p:
        return CM.range_from(cat_pol, p, origin)["km"], True
    return None, False


def _publisher(url):
    return (urlparse(url or "").hostname or "").removeprefix("www.")


def gather(sp, origin, c=None, env=None):
    """種 → 名所の行の一覧(範囲・都県の絞り込みの前)。同じ名所は 1 行(カタログが先)。"""
    from . import catalog as CM
    from . import observations as O
    c = c or cfg()
    cat_pol = CM.load_policy()
    opol = O.load_policy()
    thirds = c["text"]["thirds"]
    match = list(sp["match"]) + list(sp.get("includes") or [])
    rows = {}

    def key(name):
        return re.sub(r"[\s()（）・]", "", name or "")

    for e in _flower_entries():
        t = e.get("tags") or {}
        kinds = [k for k in (t.get("flower_kinds") or []) if _matches(k, match, sp, c)]
        wins = [w for w in e.get("flower_windows") or [] if _matches(w.get("kind"), match, sp, c)
                and not O.event_derived(w, e.get("events"), opol, e.get("name"))]
        if not kinds and not wins and not _name_matches(e.get("name"), match, sp, c):
            continue
        km, est = _km(e.get("point"), t.get("city"), origin, cat_pol)
        w = wins[0] if wins else None
        rows.setdefault(key(e["name"]), {
            "name": e["name"], "prefecture": t.get("prefecture"), "city": t.get("city"), "km": km, "km_estimated": est,
            "kinds": sorted(set(kinds) | {x["kind"] for x in wins}),
            "start": w["start"] if w else None, "end": w["end"] if w else None,
            "season": window_text(w["start"], w["end"], thirds) if w else None,
            "url": w["source_url"] if w else ((e.get("sources") or [{}])[0].get("url")),
            "official": bool(w) and not (w.get("source_class") == "secondary" or w.get("unapproved_host")),
            "care": t.get("care_note"), "from": "catalog", "subject": e["_subject"]})
    for e in _guide_entries():
        kinds = [k["kind"] for k in e.get("kinds") or [] if _matches(k.get("kind"), match, sp, c)]
        if not kinds:
            continue
        s = e.get("season") or {}
        if isinstance(s, str):
            s = {"text": s}
        win = s.get("window") if isinstance(s.get("window"), dict) else {}
        by = ((e.get("range") or {}).get("by_origin") or {}).get(origin) or {}
        km, est = (by.get("km"), False) if by.get("km") is not None else _km(None, e.get("municipality"), origin, cat_pol)
        if by.get("status") == "out_of_range":
            km = by.get("km")
        srcs = e.get("sources") or []
        src = next((x for x in srcs if x.get("url") == s.get("from_url")), srcs[0] if srcs else {})
        rows.setdefault(key(e["name"]), {
            "name": e["name"], "prefecture": e.get("prefecture"), "city": e.get("municipality"), "km": km, "km_estimated": est,
            "kinds": kinds, "start": win.get("start"), "end": win.get("end"), "season": s.get("text") if s.get("shown", True) else None,
            "url": src.get("url"), "official": src.get("class") in ("A", "B"), "care": None, "from": "guide", "subject": e.get("theme")})
    for r in _records(match, env, sp, c):
        k = key(r["name"])
        if k in rows:
            if not rows[k]["season"] and r.get("season"):
                rows[k].update(season=r["season"], start=r["start"], end=r["end"], url=r["url"], official=r["official"])
            continue
        km, est = _km(None, r.get("city"), origin, cat_pol)
        rows[k] = {**r, "km": km, "km_estimated": est}
    return list(rows.values())


def _records(match, env=None, sp=None, c=None):
    """読んだ事実の記録(花・野鳥)のうち、種(kind)が当たり、例年の時期(typical)があるもの。"""
    from . import observations as O
    opol = O.load_policy()
    thirds = cfg()["text"]["thirds"]
    out = []
    for sj in ("flowers", "birds"):
        try:
            rows = O.read_records(sj, env, opol)
        except (OSError, ValueError, KeyError):
            continue
        for r in rows:
            if not _matches(r.get("kind") or "", match, sp, c) or not r.get("name"):
                continue
            win = O.parse_typical(r.get("typical"), opol) if r.get("typical") else None
            out.append({"name": r["name"], "prefecture": r.get("prefecture"), "city": r.get("city"), "kinds": [r["kind"]],
                        "start": win[0] if win else None, "end": win[1] if win else None,
                        "season": window_text(win[0], win[1], thirds) if win else None,
                        "url": r.get("url"), "official": r.get("source_class") == "official", "care": None, "from": "record", "subject": sj})
    return out


def select(rows, origin, prefectures=None, c=None, by_distance=False):
    """範囲(出発地から max_km)・都県の指定で絞る。→ (使う行, 範囲外で外した数)"""
    from . import catalog as CM
    c = c or cfg()
    max_km = CM.load_policy()["range_limit"]["max_km"]
    ok_pref = set(c["unknown_distance_prefectures"])
    keep, out = [], 0
    for r in rows:
        if prefectures and r.get("prefecture") not in prefectures:
            continue
        if r["km"] is not None:
            if r["km"] > max_km:
                out += 1
                continue
        elif r.get("prefecture") not in ok_pref:
            out += 1
            continue
        keep.append(r)

    def sk(r):
        km = r["km"] if r["km"] is not None else 9999
        return (km, r["name"]) if by_distance else (r["start"] is None, r["start"] or "", km, r["name"])
    return sorted(keep, key=sk)[: c["max_items"]], out


# ---- 文 ----

def _month_of(md):
    return int(md[:2])


def _in_window(today, start, end):
    md = today.strftime("%m-%d")
    return start <= md <= end if start <= end else (md >= start or md <= end)


def _next_month(today, rows):
    best = None
    for r in rows:
        if not r["start"]:
            continue
        s = date(today.year, _month_of(r["start"]), int(r["start"][3:]))
        if s < today:
            s = date(today.year + 1, s.month, s.day)
        if best is None or s < best:
            best = s
    return best.month if best else None


def _species_part(sp, rows, n_out, *, today, origin, region, prefectures, table, c):
    """1 つの種の節 → (行, 出典の URL, 紹介サイトを含むか)。"""
    t = c["text"]
    is_bird = sp["name"] in c.get("bird_species", [])
    lines, urls, any_secondary = [], [], False
    if not rows:
        if prefectures:
            lines.append(t["region_none"].format(region=region, name=sp["name"]))
        elif n_out:
            lines.append(t["out_of_range"].format(origin=origin))
        else:
            lines.append(t["none"].format(name=sp["name"]))
        return lines, urls, False
    wins = [r for r in rows if r["start"] and r["end"]]
    if is_bird:                                                           # 鳥は場所ごとに時期が違う(通年・秋〜春)。月の幅の 1 文にしない
        lines.append(t["lead_birds"].format(name=sp["name"]))
    elif wins:
        start_m = min(wins, key=lambda r: r["start"])["start"]
        end_m = max(wins, key=lambda r: r["end"] if r["end"] >= r["start"] else "99")["end"]
        a, b = f"{_month_of(start_m)}月", f"{_month_of(end_m)}月"
        lines.append(t["lead_one"].format(name=sp["name"], start=a) if a == b else t["lead"].format(name=sp["name"], start=a, end=b))
        if any(_in_window(today, r["start"], r["end"]) for r in wins):
            lines.append(t["in_season"])
        else:
            nm = _next_month(today, wins)
            if nm:
                lines.append(t["off_season"].format(month=nm))
    if table:
        lines += [""] + list(t["table_head"])
    for r in rows:
        where = (r.get("prefecture") or "") + (r.get("city") or "")
        km = t["km"].format(km=r["km"]) if r["km"] is not None else ""
        if table:
            lines.append(t["table_row"].format(name=r["name"], where=where, season=r["season"] or "分かりません", km=km.strip() or "—"))
        else:
            lines += ["", t["head"].format(name=r["name"], where=where, km=km)]
            if r["season"]:
                ln = (t["typical"] if r["official"] else t["typical_secondary"]).format(text=r["season"], publisher=_publisher(r["url"]))
            else:
                ln = t["typical_unknown"]
            if is_bird:
                for a, b in (t.get("bird_label") or {}).items():
                    ln = ln.replace(a, b)
            lines.append(ln)
            if r["kinds"]:
                lines.append(t["kinds"].format(kinds="・".join(r["kinds"])))
            if r.get("care"):
                lines.append(t["care"].format(care=r["care"]))
        if r["url"] and r["url"] not in urls:
            urls.append(r["url"])
        any_secondary = any_secondary or not r["official"]
    return lines, urls, any_secondary


def compose(question, *, today, origin, region=None, prefectures=None, env=None, species=None, max_items=None):
    """→ {text, spots, species, species_all, needs_research}。種が 2 つ以上なら種ごとの節。必ず空でない文。
    species: 種の一覧を渡すとき(知識の答えの最後の短い一覧など)。max_items: 1 つの種の名所の上限(既定は設定の max_items)。"""
    c = cfg()
    t = c["text"]
    sps = species if species is not None else resolve_all(question, c)
    if not sps:
        return None
    table = any(w in (question or "") for w in t["table_words"])
    head = [t["origin_line"].format(origin=origin)]
    body, urls, any_secondary, all_rows, missing = [], [], False, [], []
    birds_only = all(sp["name"] in c.get("bird_species", []) for sp in sps)
    for sp in sps:
        is_bird = sp["name"] in c.get("bird_species", [])
        rows, n_out = select(gather(sp, origin, c, env), origin, prefectures, c, by_distance=is_bird)
        if max_items is not None:
            rows = rows[:max_items]
        part, u, sec = _species_part(sp, rows, n_out, today=today, origin=origin, region=region, prefectures=prefectures, table=table, c=c)
        if len(sps) > 1:
            body += ["", t["species_heading"].format(name=sp["name"])]
        elif body:
            body.append("")
        body += part
        urls += [x for x in u if x not in urls]
        any_secondary = any_secondary or sec
        all_rows += rows
        if not rows:
            missing.append(sp["name"])
    if len(sps) == 1:
        lines = body[:1] + body[1:2] if body and not all_rows else []
        if all_rows:                                                      # 1 種: 冒頭の 1〜2 文のあとに距離の 1 文
            lead = [x for x in body[:2] if x and not x.startswith(("**", "|", "・"))]
            rest = body[len(lead):]
            lines = lead + head + rest
    else:
        lines = head + body
    if all_rows:
        lines.append("")
        lines.append(t["confidence_birds"] if birds_only else t["confidence"])
        if any_secondary:
            lines.append(t["secondary_note"])
    if urls:
        lines += ["", t["sources_heading"]] + urls
    return {"text": NL.join(lines) + NL, "spots": all_rows, "species": sps[0], "species_all": [x["name"] for x in sps],
            "missing": missing, "needs_research": bool(missing)}
