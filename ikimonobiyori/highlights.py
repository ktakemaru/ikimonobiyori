"""段階65 第4部: 「見どころ」の型(日付のない、場所の質問)。通信しない・書き込まない。

「日光や那須で見どころを教えて」「筑波山ってどんなところ」「尾瀬で何が見られる」に、ネイチャーガイドとしてその場所の自然を案内する。
材料はすべてコードが集める: 知識カード(ガイドの目。場所の一致・分類の偏りなく最大 max_cards 枚)・名所カタログと名所の一覧の名所
(種と例年の時期。季節ごと)・承認済みの施設の名前と 14 日以内の発信・今年の行事(年つき)・今の時期の現況 1〜2 行(主役にしない)。
材料が少ないときは確かめられたことだけを書き、一般知識で補わない。値と文は data/ask/highlights.yaml。"""
import re
from datetime import date

from . import yamlcache
from .paths import DATA_FILES_DIR

PATH = DATA_FILES_DIR / "ask" / "highlights.yaml"
NL = "\n"
SUBJECTS = ("autumn_leaves", "flowers", "birds")


def cfg():
    return yamlcache.load(PATH)


def _strip(name):
    return re.sub(r"[(（].*?[)）]", "", name or "").strip()


def _sites():
    doc = yamlcache.load(DATA_FILES_DIR / "sites.yaml") or {}
    return doc.get("sites") if isinstance(doc, dict) else doc or []


def places(question, cards=None):
    """質問の文 → 場所の一覧 [{name, terms, cities, center, radius_km}]。エリア辞書・山の地点・知識カードの場所の順。"""
    from . import areas as AR
    from . import knowledge as K
    c = cfg()
    q = question or ""
    out, taken = [], []

    def add(word, item):
        i = q.find(word)
        if i < 0 or any(a <= i < b or i <= a < i + len(word) for a, b in taken):
            return
        taken.append((i, i + len(word)))
        out.append((i, item))

    vocab = []
    for a in AR.load()["areas"]:
        for n in [a["name"], *(a.get("aliases") or [])]:
            vocab.append((n, {"name": a["name"], "terms": [a["name"], *(a.get("aliases") or [])], "cities": list(a.get("cities") or []),
                              "center": a.get("center"), "radius_km": a.get("radius_km")}))
    for s in _sites():
        n = _strip(s.get("name"))
        if len(n) >= 2 and s.get("lat") is not None:
            vocab.append((n, {"name": n, "terms": [n], "cities": [], "center": {"lat": s["lat"], "lon": s["lon"]}, "radius_km": c["site_radius_km"],
                              "site_id": s.get("id")}))
    rows = cards if cards is not None else K.load_shown()
    for r in rows:
        for n in [r.get("place") or "", *(r.get("place_aliases") or [])]:
            if len(n) >= 2:
                vocab.append((n, {"name": r.get("place"), "terms": [r.get("place"), *(r.get("place_aliases") or [])], "cities": [], "center": None, "radius_km": None}))
    for word, item in sorted(vocab, key=lambda x: -len(x[0])):
        if word in q and item["name"] not in [o[1]["name"] for o in out]:
            add(word, item)
    return [x[1] for x in sorted(out, key=lambda x: x[0])]


def is_highlights_question(question, cards=None):
    c = cfg()
    q = question or ""
    if not any(p in q for p in c["patterns"]):
        return False
    if any(re.search(w, q) for w in c["date_words"]):
        return False
    return bool(places(q, cards))


def _member(cand, pl):
    from . import observations as O
    names = [cand.get("name") or "", cand.get("area") or ""]
    if any(t and len(t) >= 2 and any(t in n for n in names if n) for t in pl["terms"]):
        return True
    if cand.get("city") and any(ct in re.split(r"[・、]", cand["city"]) for ct in pl["cities"]):
        return True
    p = O._point(cand)
    if p and pl.get("center") and pl.get("radius_km"):
        return O._km(p, (pl["center"]["lat"], pl["center"]["lon"])) <= pl["radius_km"]
    return False


def _season_of(md, c):
    m = int(str(md)[:2])
    return next(s["name"] for s in c["seasons"] if m in s["months"])


def gather(pls, today, env=None, cards=None, centers=None, reports=None, cands=None, records=None):
    """場所 → 材料 {cards, spots, events, facilities, vc_rows, current}。"""
    from . import knowledge as K
    from . import observations as O
    from . import visitor_centers as VC
    c = cfg()
    opol = O.load_policy()
    spots = []
    for sj in SUBJECTS:
        cs = cands[sj] if cands is not None else O.all_candidates(sj)
        recs = records[sj] if records is not None else O.read_records(sj, env)
        by_c, _rest = O.assign_records(recs, cs, opol, env)
        for x in cs:
            if any(_member(x, pl) for pl in pls):
                spots.append(dict(x, subject=sj, records=by_c.get(x["id"]) or []))
    terms = [t for pl in pls for t in pl["terms"] if t] + [_strip(s["name"]) for s in spots]
    rows = cards if cards is not None else K.load_shown(env)
    sids = {pl.get("site_id") for pl in pls if pl.get("site_id")}
    hits = [r for r in rows if any(K.place_match(r, t) for t in terms if len(t) >= 2) or sids & set(r.get("sites") or [])]   # 段階66 第3部: 地点 id でも引く
    order = {k: i for i, k in enumerate(K.cfg()["category_priority"])}

    def month_gap(r):                                         # 段階66 第3部: 月のあるカード(季節の花など)は、今の月に近いものを先に
        ms = K._months(r)
        return min(((m - today.month) % 12 for m in ms), default=0)
    by_cat = {}
    for r in sorted(hits, key=lambda r: (order.get(r.get("category"), len(order)), month_gap(r), r["title"])):
        by_cat.setdefault(r.get("category"), []).append(r)
    picked = []
    while len(picked) < c["max_cards"] and any(by_cat.values()):         # 分類の偏りなく(分類ごとに 1 枚ずつ順に)
        for k in sorted(by_cat, key=lambda k: order.get(k, len(order))):
            if by_cat[k] and len(picked) < c["max_cards"]:
                picked.append(by_cat[k].pop(0))
    cs_all = VC.load_centers() if centers is None else centers
    vc_names = [x for x in cs_all if (x.get("approval") or {}).get("status") == "approved" and not x.get("closed")
                and any(t and len(t) >= 2 and t in x["name"] for pl in pls for t in pl["terms"])]
    vc_rows = {r["center"]: r for r in VC.fact_rows(today, subjects=None, env=env, centers=cs_all, reports=reports)} if vc_names else {}
    current = []
    for s in spots:
        rec = O.best_record([r for r in s["records"] if r.get("state") and r.get("state_norm") != opol["unknown_state"]])
        if not rec or rec.get("source_class") != "official":
            continue
        sd = O.state_date_of(rec)
        if not sd:
            continue
        age = (today - date.fromisoformat(sd)).days
        if 0 <= age <= c["current_max_age_days"]:
            current.append((sd, s, rec))
    current.sort(key=lambda x: x[0], reverse=True)
    return {"cards": picked, "spots": spots, "facilities": vc_names, "vc_rows": vc_rows, "current": current[: c["max_current_lines"]]}


def compose(question, *, today, env=None, cards=None, centers=None, reports=None, cands=None, records=None):
    """質問の文 → {text, places, cards, spots}。場所が分からなければ None。"""
    from . import knowledge as K
    from . import observations as O
    from . import season_place as SP
    c = cfg()
    t = c["text"]
    pls = places(question, cards)
    if not pls:
        return None
    name = "・".join(pl["name"] for pl in pls)
    g = gather(pls, today, env, cards, centers, reports, cands, records)
    opol = O.load_policy()
    thirds = SP.cfg()["text"]["thirds"]
    urls = []

    def url(u):
        if u and u not in urls:
            urls.append(u)

    lines = [t["title"].format(place=name)]
    lead_pri = {k: i for i, k in enumerate(c["lead_categories"])}
    lead_cards = sorted([r for r in g["cards"] if r.get("category") in lead_pri], key=lambda r: lead_pri[r["category"]])
    lead_card = lead_cards[0] if lead_cards else None
    if lead_card:
        lines.append(t["lead"].format(place=name, facts="。".join(f.rstrip("。") for f in lead_card["facts"][:2])))
        url(lead_card["source"].get("url"))
    elif g["spots"] or g["facilities"]:
        lines.append(t["lead_none"].format(place=name))
    # 季節ごとの見どころ
    by_season = {}
    seen = set()
    year = today.year
    events = []
    for s in sorted(g["spots"], key=lambda s: s["name"]):
        for w in s.get("typical") or []:
            if not (w.get("start") and w.get("end")) or w.get("event_derived") or O.event_derived(w, s.get("events"), opol, s["name"]):
                continue
            kind = w.get("kind") or c["kind_labels"].get(s["subject"]) or "・".join(s.get("flower_kinds") or [])
            if not kind:
                continue
            key = (_strip(s["name"]), kind)
            if key in seen:
                continue
            seen.add(key)
            note = t["secondary_note"] if w.get("source_class") == "secondary" else ""
            by_season.setdefault(_season_of(w["start"], c), []).append(
                t["season_line"].format(name=s["name"], kind=kind, window=SP.window_text(w["start"], w["end"], thirds), note=note))
            url(w.get("url"))
        for e in s.get("events") or []:
            if str(e.get("start") or "")[:4] == str(year) and e.get("source_class") != "secondary":
                sd, ed = date.fromisoformat(str(e["start"])[:10]), date.fromisoformat(str(e["end"])[:10])
                ln = t["event_line"].format(name=s["name"], event=e["name"], start=f"{sd.month}/{sd.day}", end=f"{ed.month}/{ed.day}", year=sd.year)
                if ln not in events:
                    events.append(ln)
                    url(e.get("url"))
    if by_season:
        lines += ["", t["season_heading"]]
        for s in c["seasons"]:
            if by_season.get(s["name"]):
                lines += [t["season_sub"].format(season=s["name"])] + by_season[s["name"]][: c["max_spots_per_season"]]
        lines += events
    elif events:
        lines += ["", t["season_heading"]] + events
    # ガイドの目・行く前に
    rest = [r for r in g["cards"] if r is not lead_card]
    eye, before, cu = K.split_lines(rest)
    if eye:
        lines += ["", t["eye_heading"]] + eye
    if before:
        lines += ["", t["before_heading"]] + before
    for u in cu:
        url(u)
    # 施設
    if g["facilities"]:
        lines += ["", t["facility_heading"]]
        for x in g["facilities"]:
            lines.append(t["facility_line"].format(name=x["name"]))
            r = g["vc_rows"].get(x["id"])
            if r:
                lines += ["  " + s for s in r["sentences"]]
                url(r["url"])
    # 今の時期(主役にしない)
    if g["current"]:
        lines += ["", t["now_heading"]]
        for sd, s, rec in g["current"]:
            d = date.fromisoformat(sd)
            lines.append(t["now_line"].format(name=s["name"], state=rec.get("state"),
                                              month=d.month, day=d.day, publisher=rec.get("publisher") or ""))
            url(rec.get("url"))
    if len(lines) <= 1:
        return {"text": t["none"].format(place=name) + NL, "places": [p["name"] for p in pls], "cards": [], "spots": [], "needs_research": True}
    if urls:
        lines += ["", t["sources_heading"]] + urls
    return {"text": NL.join(lines) + NL, "places": [p["name"] for p in pls], "cards": [r["title"] for r in g["cards"]],
            "spots": [s["name"] for s in g["spots"]], "needs_research": not g["cards"] and not g["spots"]}
