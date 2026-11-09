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
        out.append((i, dict(item, label=word)))                  # 答えの見出しは質問に書かれた語(「高尾山」を辞書の「高尾」にしない)

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
    # 同じ長さの語では、山の地点(半径 site_radius_km)をエリア辞書より先にする(段階69 第7部: 「高尾山」をエリア「高尾」(八王子駅付近から 12km)に
    # 解決すると、立川の昭和記念公園まで高尾山の見どころに入った)。sorted は安定なので、ほかの順は変わらない
    for word, item in sorted(vocab, key=lambda x: (-len(x[0]), not x[1].get("site_id"))):
        if word in q and item["name"] not in [o[1]["name"] for o in out]:
            add(word, item)
    got = [x[1] for x in sorted(out, key=lambda x: x[0])]
    if c.get("drop_region_names_with_other_places") and len(got) > 1:       # 段階69 第2部 2: 「神奈川 大山」の神奈川は絞り込みの語
        regs = _region_names()
        rest = [x for x in got if x.get("label") not in regs and x["name"] not in regs]
        got = rest or got
    return got


def _region_names():
    from . import sources as S
    out = set()
    for r in S.load_regions()["regions"]:
        out |= {r["name"], *(r.get("aliases") or [])}
    return out


def is_place_dated(question, cards=None):
    """段階69 第2部 2: 日付のある場所の質問(「今週末、高尾山の見どころ」)。見どころの言い方・日付の語・山や名所の場所がそろうとき。
    山・名所・エリア(「今週末の日光の見どころ」も。本人の指示 2026-11-09)が対象。地域全体(都県・関東)だけの質問は計画の型のまま。"""
    c = cfg()
    q = question or ""
    if not any(p in q for p in c["patterns"]):
        return False
    if not any(re.search(w, q) for w in c["date_words"]):
        return False
    from . import areas as AR
    area_names = {a["name"] for a in AR.load()["areas"]}             # エリア辞書の場所(日光・箱根など)は、地域の一覧にも名前があっても場所
    regs = _region_names() - area_names
    return any(pl["name"] in area_names or pl.get("site_id") or (pl.get("label") not in regs and pl["name"] not in regs)
               for pl in places(q, cards))


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
    terms = [t for pl in pls for t in pl["terms"] if t]
    spot_terms = [_strip(s["name"]) for s in spots]
    rows = cards if cards is not None else K.load_shown(env)
    sids = {pl.get("site_id") for pl in pls if pl.get("site_id")}
    site_terms = {t for pl in pls if pl.get("site_id") for t in pl["terms"] if t}

    def by_place(r, ts):
        # 段階67: 山(地点)の名前は、カードの場所・別名が名前の一部(「木曽駒ヶ岳」の中の箱根の「駒ヶ岳」)では当てない
        names = [r.get("place") or "", *(r.get("place_aliases") or [])]
        for t in ts:
            if len(t) < 2:
                continue
            if t in site_terms:
                if any(n == t or (len(n) >= 2 and t in n) for n in names):
                    return True
            elif K.place_match(r, t):
                return True
        return False
    # 段階66 第3部: 地点 id でも引く。名所の名前で引くときはカードの主な場所だけで当てる(別名の「丹沢」で外来種のカードが丹沢湖に当たらないように)。
    # 種の解説(場所が種の名前のカード)は名所の名前では引かない
    main_place = lambda r, ts: any(K.place_match({"place": r.get("place")}, t) for t in ts if len(t) >= 2)
    hits = [r for r in rows if by_place(r, terms) or sids & set(r.get("sites") or [])
            or (main_place(r, spot_terms) and r.get("category") not in c["spot_only_skip_categories"])]
    order = {k: i for i, k in enumerate(K.cfg()["category_priority"])}

    def month_gap(r):                                         # 段階66 第3部: 月のあるカード(季節の花など)は、今の月に近いものを先に
        ms = K._months(r)
        return min(((m - today.month) % 12 for m in ms), default=0)
    by_cat = {}
    exact = {pl.get("label") for pl in pls} | {pl.get("name") for pl in pls}
    for r in sorted(hits, key=lambda r: (order.get(r.get("category"), len(order)), r.get("place") not in exact, month_gap(r), r["title"])):   # 段階67: 同じ分類なら、質問の山そのもののカードを先に
        by_cat.setdefault(r.get("category"), []).append(r)
    picked = []
    side = []                                                 # 段階67 第4部 2: 施設・行き方のカードは枚数の外で各分類 1 枚まで(施設の欄・行く前に・歩き方の欄)
    for k in list(c["facility_categories"]) + list(c["walk_categories"]):
        if by_cat.get(k):
            side.append(by_cat.pop(k)[0])
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
    lead_cats = set(c["lead_categories"])
    if not any(r.get("place") in exact and r.get("category") in lead_cats for r in picked):     # 段階67 第4部 3: 冒頭に使える、質問の山そのもののカードを入れる
        own = next((r for r in hits if r.get("place") in exact and r.get("category") in lead_cats and r not in picked), None)
        if own:
            picked = [own] + picked[: max(0, c["max_cards"] - 1)]
    return {"cards": picked + side, "spots": spots, "facilities": vc_names, "vc_rows": vc_rows, "current": current[: c["max_current_lines"]]}


_MONTH_RE = re.compile(r"(\d{1,2})(?:〜(\d{1,2}))?月(上旬|中旬|下旬)?(?:〜(?:(\d{1,2})月)?(上旬|中旬|下旬)?)?")
_KATA_RE = re.compile(r"[ァ-ヶー]{2,}")


def card_season_items(cards, c, today=None):
    """段階67 第4部 1: 月の書かれたカードの事実 → [(季節, 場所の語, 名前の一覧, 時期の文, 出典名, URL)]。名前は花・紅葉の語(カタカナの語か紅葉)。"""
    out = []
    for r in cards:
        if r.get("category") not in c["card_season_categories"]:
            continue
        for f in r.get("facts") or []:
            m = _MONTH_RE.search(f)
            if not m:
                continue
            names = [w for w in _KATA_RE.findall(f) if w not in c["card_season_not_names"] and not any(w in x and w != x for x in c["card_season_not_names"])]
            names += [w for w in c["card_season_extra_names"] if w in f and w not in names and not any(w in n for n in names)]
            names = [n for n in names if not any(n != o and n in o for o in names)]
            if not names:
                continue
            lead = re.match(r"^([^、。0-9０-９]{1,10}?)(は|では)", f)
            where = lead.group(1) if lead and lead.end() <= m.start() and not any(n in lead.group(1) for n in names) and not _KATA_RE.fullmatch(lead.group(1)) else ""
            out.append((_season_of(f"{int(m.group(1)):02d}", c), where, names, m.group(0), r["source"]["name"], r["source"].get("url"), r, f))
    return out


def _lead_rank(r, pls, area_names):
    """段階67 第4部 3: 冒頭のカードの順。カードの場所が質問の場所・エリア全体のものを先に(1地点の話を冒頭にしない)。"""
    labels = {pl.get("label") for pl in pls} | {pl.get("name") for pl in pls}
    place = r.get("place") or ""
    if place in labels:
        return 0
    if place in area_names:
        return 1
    return 2


def _days(on):
    return "・".join(f"{d.month}/{d.day}" for d in on)


def _md_in(d, start, end, near=0):
    """日付 d が例年の時期(MM-DD の start〜end。年をまたぐ時期も)の中か。near 日だけ前後に広げる。"""
    from datetime import timedelta
    for k in range(-near, near + 1):
        md = (d + timedelta(days=k)).strftime("%m-%d")
        if (start <= md <= end) if start <= end else (md >= start or md <= end):
            return True
    return False


def _seasons_from(c, on):
    """季節の並び(その日の月の季節を先に)。"""
    ss = list(c["seasons"])
    if not on:
        return ss
    i = next((k for k, s in enumerate(ss) if on[0].month in s["months"]), 0)
    return ss[i:] + ss[:i]


def _own(s, pls):
    """名所が、質問の場所そのもの(名前に場所の語・市町村が一致)か(半径の内だけの名所は含めない)。"""
    names = [s.get("name") or "", s.get("area") or ""]
    if any(t and len(t) >= 2 and any(t in n for n in names if n) for pl in pls for t in pl["terms"]):
        return True
    return bool(s.get("city")) and any(ct in re.split(r"[・、]", s["city"]) for pl in pls for ct in pl["cities"])


def outlook_lines(g, on, c, opol, pls=None):
    """段階69 第2部 2: その日の見込み(その場所の現況・例年の時期・行事)。質問の場所そのものの名所があれば、それだけ。→ (行, URL)"""
    from . import observations as O
    from . import season_place as SP
    if pls:
        own = [s for s in g["spots"] if _own(s, pls)]
        if own:
            ids = {id(s) for s in own}
            g = dict(g, spots=own, current=[x for x in g["current"] if id(x[1]) in ids])
    t = c["text"]
    thirds = SP.cfg()["text"]["thirds"]
    days = _days(on)
    lines, urls = [], []
    for sd, s, rec in g["current"]:
        d = date.fromisoformat(sd)
        disp, sym_only = O.state_display(rec.get("state"), rec.get("publisher"), opol)
        if sym_only or not disp:
            continue
        lines.append(t["now_line"].format(name=s["name"], state=disp, month=d.month, day=d.day, publisher=rec.get("publisher") or ""))
        urls.append(rec.get("url"))
    seen = set()
    from . import publisher as P
    for s in sorted(g["spots"], key=lambda s: s["name"]):
        for w in s.get("typical") or []:
            if not (w.get("start") and w.get("end")) or w.get("event_derived") or O.event_derived(w, s.get("events"), opol, s["name"]):
                continue
            if P.unused_source(w.get("url")):
                continue
            kind = w.get("kind") or c["kind_labels"].get(s["subject"]) or "・".join(s.get("flower_kinds") or [])
            if not kind or (s["name"], kind) in seen:
                continue
            fmt = None
            if any(_md_in(d, w["start"], w["end"]) for d in on):
                fmt = t["outlook_window_in"]
            elif any(_md_in(d, w["start"], w["end"], c["outlook_near_days"]) for d in on):
                fmt = t["outlook_window_near"]
            if fmt:
                seen.add((s["name"], kind))
                lines.append(fmt.format(name=s["name"], kind=kind, window=SP.window_text(w["start"], w["end"], thirds), days=days))
                urls.append(w.get("url"))
        for e in s.get("events") or []:
            if e.get("source_class") == "secondary" or not e.get("start") or not e.get("end"):
                continue
            sd, ed = date.fromisoformat(str(e["start"])[:10]), date.fromisoformat(str(e["end"])[:10])
            if any(sd <= d <= ed for d in on):
                ln = t["outlook_event"].format(name=s["name"], event=e["name"], start=f"{sd.month}/{sd.day}", end=f"{ed.month}/{ed.day}")
                if ln not in lines:
                    lines.append(ln)
                    urls.append(e.get("url"))
    lines = lines[: c["outlook_max_lines"]]
    if not lines:
        lines = [t["outlook_none"].format(days=days)]
    return lines, [u for u in urls if u]


def compose(question, *, today, env=None, cards=None, centers=None, reports=None, cands=None, records=None, on=None):
    """質問の文 → {text, places, cards, spots}。場所が分からなければ None。
    on: その日(日付の一覧)。あれば季節はその日の月の季節を先にし、「今の時期」の代わりに「その日の見込み」を書く(段階69 第2部 2)。"""
    from . import knowledge as K
    from . import observations as O
    from . import publisher as P
    from . import season_place as SP
    c = cfg()
    t = c["text"]
    pls = places(question, cards)
    if not pls:
        return None
    name = "・".join(pl.get("label") or pl["name"] for pl in pls)
    g = gather(pls, today, env, cards, centers, reports, cands, records)
    opol = O.load_policy()
    thirds = SP.cfg()["text"]["thirds"]
    urls = []

    def url(u):
        if u and u not in urls:
            urls.append(u)

    lines = [t["title_dated"].format(place=name, days=_days(on)) if on else t["title"].format(place=name)]
    lead_pri = {k: i for i, k in enumerate(c["lead_categories"])}
    from . import areas as AR
    area_names = {n for a in AR.load()["areas"] for n in [a["name"], *(a.get("aliases") or [])]}
    lead_cards = sorted([r for r in g["cards"] if r.get("category") in lead_pri], key=lambda r: (_lead_rank(r, pls, area_names), lead_pri[r["category"]]))
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
            if P.unused_source(w.get("url")):                                 # 段階69 第4部 1: 使わない出典の時期は書かない
                continue
            kind = w.get("kind") or c["kind_labels"].get(s["subject"]) or "・".join(s.get("flower_kinds") or [])
            if not kind:
                continue
            key = (_strip(s["name"]), kind)
            if key in seen:
                continue
            seen.add(key)
            note = t["secondary_note"] if (w.get("source_class") == "secondary" and not w.get("publisher_official")) else ""   # 段階67(承認欄 C)
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
    # 段階67 第4部 1: 月の書かれたカードから季節の行(名所カタログの花と重なる名前は 1 回だけ)
    card_n = {}
    converted = {}
    for season, where, names, when, src, u, card, fact in card_season_items(g["cards"], c, today):
        have = " ".join(by_season.get(season) or [])
        names = [n for n in names if n not in have]
        if not names or card_n.get(season, 0) >= c["card_season_max_per_season"]:
            continue
        converted.setdefault(id(card), (card, set()))[1].add(fact)
        card_n[season] = card_n.get(season, 0) + 1
        by_season.setdefault(season, []).append(t["card_season_line"].format(
            where=t["card_season_where"].format(where=where) if where else "", names="・".join(names), when=when, source=src))
        url(u)
    if by_season:
        lines += ["", t["season_heading"]]
        for s in _seasons_from(c, on):
            if by_season.get(s["name"]):
                lines += [t["season_sub"].format(season=s["name"])] + by_season[s["name"]][: c["max_spots_per_season"]]
        lines += events
    elif events:
        lines += ["", t["season_heading"]] + events
    # ガイドの目・行く前に
    rest = [r for r in g["cards"] if r is not lead_card]
    fac_cards = [r for r in rest if r.get("category") in c["facility_categories"]]            # 段階67 第4部 2
    walk_cards = [r for r in rest if r.get("category") in c["walk_categories"]]
    rest = [r for r in rest if r not in fac_cards and r not in walk_cards]
    shown_n = K.cfg()["max_facts_in_answer"]
    used_for_season = {k for k, (card, fs) in converted.items() if set((card.get("facts") or [])[:shown_n]) <= fs}
    rest = [r for r in rest if id(r) not in used_for_season]                                # 季節の行にした事実のカードはガイドの目に重ねない
    eye, before, cu = K.split_lines(rest)
    pre = K.cfg()["line_prefix"]
    eye = [ln[len(pre):].lstrip() if ln.startswith(pre) else ln for ln in eye]                # 段階67 第4部 5: 見出しがあるので行の先頭に付けない
    walk = [K.plain_line(r) for r in walk_cards]
    if eye:
        lines += ["", t["eye_heading"]] + eye
    if on:                                                    # 段階69 第2部 2: その日の見込み(見どころのあと、行く前に確認することの前)
        ol, ou = outlook_lines(g, on, c, opol, pls)
        lines += ["", t["outlook_heading"].format(days=_days(on))] + ol + [t["outlook_note"]]
        for u in ou:
            url(u)
    if before or walk:
        lines += ["", t["walk_heading"] if walk else t["before_heading"]] + before + walk
    for u in cu + [r["source"].get("url") for r in walk_cards + fac_cards]:
        url(u)
    # 施設
    if g["facilities"] or fac_cards:
        lines += ["", t["facility_heading"]]
        for x in g["facilities"]:
            lines.append(t["facility_line"].format(name=x["name"]))
            r = g["vc_rows"].get(x["id"])
            if r:
                lines += ["  " + s for s in r["sentences"] if s.strip() != x["name"]]      # 段階67 第3部 6: 名前だけの文は重ねない
                url(r["url"])
        lines += ["・" + K.plain_line(r) for r in fac_cards]
    # 今の時期(主役にしない)
    if g["current"] and not on:
        lines += ["", t["now_heading"]]
        for sd, s, rec in g["current"]:
            d = date.fromisoformat(sd)
            disp, sym_only = O.state_display(rec.get("state"), rec.get("publisher"), opol)        # 段階67 第3部 3: 全経路で凡例の語と短い語
            if sym_only or not disp:
                continue
            lines.append(t["now_line"].format(name=s["name"], state=disp,
                                              month=d.month, day=d.day, publisher=rec.get("publisher") or ""))
            url(rec.get("url"))
    if len(lines) <= 1:
        return {"text": t["none"].format(place=name) + NL, "places": [p["name"] for p in pls], "cards": [], "spots": [], "needs_research": True}
    if urls:
        lines += ["", t["sources_heading"]] + urls
    return {"text": NL.join(lines) + NL, "places": [p["name"] for p in pls], "cards": [r["title"] for r in g["cards"]],
            "spots": [s["name"] for s in g["spots"]], "needs_research": not g["cards"] and not g["spots"]}
