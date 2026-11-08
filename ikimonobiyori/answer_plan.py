"""答えの「計画」をコードで作る(段階56。通信しない・書き込まない。ask.py の plan が作業フォルダに書く)。

目的: 答えに載せる候補の選び方を、その場の手の判断ではなく、再現できる式にする(2026-11-07 の調査: 段階55の答えの3件は手で選んでいた)。
入力は ask facts の出力(facts.json)、出力は計画(JSON): 狙い別の節・各節の採用と順位・全体の「今回のおすすめ」・不採用の一覧と理由コード。
点数の重み・区分・語は data/ask/plan.yaml(コードに数値を書かない)。理由コードは内部用で、答えには出さない。

  python -X utf8 -m ikimonobiyori.ask plan --out-dir DIR [--subject S] [--explain 名所] [--override 名所 --reason 理由 [--replace 計画の名所]]
"""
import re
from datetime import date, timedelta


from . import yamlcache
from . import observations as O
from .paths import DATA_FILES_DIR

PLAN_PATH = DATA_FILES_DIR / "ask" / "plan.yaml"
SCHEMA = "ikimonobiyori-answer-plan/1"


def load_policy(path=None):
    return yamlcache.load((path or PLAN_PATH))


def _d(x):
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])


# ---- 要素ごとの点 ----

def distance_of(c, pol):
    """(km, 見積もりか)。座標がなければ都道府県の見積もり(plan.yaml)。それもなければ (None, False)。"""
    km = c.get("distance_km")
    if km is not None:
        return km, False
    origin = c.get("_origin")
    if origin and origin not in pol["distance"]["estimate_origins"]:     # 段階57 第8部: 新しい出発地
        from . import origins
        home = (origins.lookup(origin) or {}).get("prefecture")
        return (pol["distance"]["same_prefecture_km"], True) if home and c.get("prefecture") == home else (None, False)
    est = (pol["distance"].get("estimate_km_by_prefecture") or {}).get(c.get("prefecture"))
    return (est, True) if est is not None else (None, False)


def outlook_of(c, d, pol, subject=None):
    """対象日 d の見込みの区分(in_peak/toward/late/early/unknown/past)。例年の窓と現況の段から、コードだけで決める。"""
    o = pol["outlook"]
    if subject == "birds":                                 # 野鳥は「見頃」がない。公園の記録(park_birds)が今季のものか、この時期の集計かで区分する
        pb = c.get("park_birds") or []
        if any(x.get("kind") == "recent" and not x.get("older") for x in pb):
            return "in_peak"
        return "toward" if pb else "unknown"
    cur = c.get("current") or {}
    st = cur.get("state")
    rel = c.get("relation")
    if rel == "after_peak" and st in (o.get("after_window_current") or {}) and _fresh_official(cur, d, o):
        return o["after_window_current"][st]                  # 段階62 第4部: 公式の新しい現況を、例年の時期より優先する
    if c.get("avoid") == "past" or rel == "after_peak" or st == "見頃過ぎ":
        return "past"
    typ = next((t for t in c.get("typical") or [] if t.get("start") and t.get("end")), None)
    if st == "青葉":
        return "early"
    if typ:
        s, e = O.window_dates(typ["start"], typ["end"], d)
        if d < s:
            return "toward" if (s - d).days <= o["toward_days"] else "early"
        if (e - d).days <= o["late_days"]:
            if st in ("色づき始め", "見頃前") and _fresh_official(cur, d, o):     # 段階62 第4部: 公式の新しい「色づき始め」を「終盤」にしない
                return o["after_window_current"][st]
            return "late"
        if st in ("色づき始め", "見頃前"):
            return "toward"
        return "in_peak"
    # 例年の窓がない: 現況だけが根拠。古い現況で先の週を言わない
    if st in ("色づき始め", "見頃前"):
        return "toward" if _gap_ok(cur, d, o) else "unknown"
    if st == "見頃" and rel == "in_peak":
        return "in_peak" if _gap_ok(cur, d, o) else "unknown"
    return "unknown"


def _fresh_official(cur, d, o):
    """段階62 第4部: 公式の現況で、状態の日付が対象日の after_window_max_gap_days 日以内か。"""
    sd = cur.get("state_date")
    return bool(o.get("after_window_max_gap_days")) and cur.get("source_class") == "official" and bool(sd) and 0 <= (d - _d(sd)).days <= o["after_window_max_gap_days"]


def _gap_ok(cur, d, o):
    sd = cur.get("state_date")
    return bool(sd) and (d - _d(sd)).days <= o["state_only_max_gap_days"]


def freshness_points(c, pol, subject=None):
    f = pol["freshness"]
    cur = c.get("current")
    if subject == "birds":                                   # 野鳥は、公園の記録の新しい日付で見る
        ds = [x["date"] for x in c.get("park_birds") or [] if x.get("kind") == "recent" and x.get("date")]
        if ds:
            age = (_d(c["_today"]) - _d(max(ds))).days if c.get("_today") else None
            if age is not None:
                for limit, pts in f["by_age_days"]:
                    if age <= limit:
                        return pts
                return f["older"]
    if not cur:
        return f["no_current"]
    if not cur.get("state_date") or cur.get("age_days") is None:
        return f["undated"]
    for limit, pts in f["by_age_days"]:
        if cur["age_days"] <= limit:
            return pts
    return f["older"]


def _lightup_active(fest, dates, d_year):
    """対象日のどれかがライトアップの期間内か。行に「M/D〜M/D」があればその期間、なければまつりの期間。"""
    line = fest.get("lightup_line")
    if not line:
        return False
    m = re.search(r"(\d+)/(\d+)\s*[〜～~-]\s*(\d+)/(\d+)", line)
    if m:
        s = date(d_year, int(m.group(1)), int(m.group(2)))
        e = date(d_year, int(m.group(3)), int(m.group(4)))
        return any(s <= x <= e for x in dates)
    return _fest_active(fest, dates)


def _fest_active(fest, dates):
    if not fest.get("start") or not fest.get("end"):
        return False
    s, e = _d(fest["start"]), _d(fest["end"])
    return any(s <= x <= e for x in dates)


_MOUNTAIN_NAMES = None


def mountain_names():
    """登山地点(data/sites.yaml の kind: mountain)の名前。"""
    global _MOUNTAIN_NAMES
    if _MOUNTAIN_NAMES is None:
        import yaml
        from .paths import DATA_FILES_DIR
        doc = yamlcache.load((DATA_FILES_DIR / "sites.yaml")) or {}
        rows = doc.get("sites") if isinstance(doc, dict) else doc
        _MOUNTAIN_NAMES = frozenset(r["name"] for r in rows or [] if isinstance(r, dict) and r.get("kind") == "mountain" and r.get("name"))
    return _MOUNTAIN_NAMES


def spot_kind_of(c, pol):
    """段階62 第3部: 地点の種類(mountain=登山・山岳 / park=公園・庭園・湖畔・施設 / None=分からない)。
    名所の spot_kind が先。なければ、括弧を除いた名前(空白で区切った語のどれか)が登山地点の名前と一致すれば mountain。"""
    if c.get("spot_kind"):
        return c["spot_kind"]
    name = re.sub(pol["aims"]["name_strip_re"], " ", c.get("name") or "")
    words = set(name.split()) | {name.replace(" ", "")}
    return "mountain" if words & mountain_names() else None


def aim_of(c, km, lightup, outlook, pol):
    a = pol["aims"]
    if lightup and outlook in a["night_outlooks"]:
        return "night"
    name = c.get("name") or ""
    elev = c.get("elevation_m")
    kind = spot_kind_of(c, pol)
    if kind == "mountain" or (kind != "park" and re.search(a["trek_name_re"], name)):     # 段階62 第3部: 登山・山岳は近場にしない
        return "trek"
    if km is not None and km >= a["far_min_km"]:                  # 遠い名所は、標高が高くても「歩く」ではなく「遠出」
        return "far"
    if elev is not None and elev >= a["trek_min_elevation_m"] and kind != "park":         # 公園・湖畔は標高だけで山歩きにしない
        return "trek"
    if km is None:
        return "other"
    if km <= a["near_max_km"]:
        return "near"
    return "drive"


def _dup_key(name, pol):
    n = re.sub(r"\s+", "", name or "")
    for p in pol["duplicate"]["strip_prefixes"]:
        if n.startswith(p) and len(n) > len(p):
            n = n[len(p):]
    return n


def cluster_key(c):
    return c.get("city") or c.get("area") or c.get("name")


def has_current(c):
    """今年の現況として使えるか。状態が読めない記録(「記載なし」など)・記号だけの記録は現況に数えない(段階57 第7部)。"""
    cur = c.get("current")
    if not cur or cur.get("symbol_only") or cur.get("source_class") == "secondary":      # 段階58 第9部: 紹介サイトの現況は採用理由にしない(現況なしとして扱い、参考の 1 行にする)
        return False
    return cur.get("state") != O.load_policy()["unknown_state"]


def has_state_record(c):
    """状態が読める記録があるか(公式・紹介サイトを問わない)。今年の情報の有無に使う。"""
    cur = c.get("current")
    return bool(cur) and not cur.get("symbol_only") and cur.get("state") != O.load_policy()["unknown_state"]


def has_this_year(c, year):
    """今年(今のシーズン)の情報があるか: 状態が読める今年の日付の記録、または今年の行事。「例年の時期」だけでは数えない(段階58 第3部)。"""
    cur = c.get("current")
    if has_state_record(c):
        d = cur.get("state_date")
        if d is None or str(d)[:4] == str(year):
            return True
    for f in c.get("festivals") or []:
        if str(f.get("start") or "")[:4] == str(year) or str(f.get("end") or "")[:4] == str(year):
            return True
    for e in c.get("events") or []:
        if str(e.get("start") or "")[:4] == str(year):
            return True
    return bool(c.get("park_birds")) and any(b.get("kind") == "recent" for b in c["park_birds"])


def score_candidate(c, dates, pol, subject=None):
    """1 候補の評価。点数・内訳・見込み・狙い・距離を返す(並べ替えと理由の記録に使う)。"""
    dates = [_d(x) for x in dates]
    d = dates[0]
    out = outlook_of(c, d, pol, subject)
    km, est = distance_of(c, pol)
    fests = c.get("festivals") or []
    fest_on = any(_fest_active(f, dates) for f in fests)
    light_on = any(_lightup_active(f, dates, d.year) for f in fests)
    aim = aim_of(c, km, light_on, out, pol)
    dw = pol["distance"][aim]
    dist_pts = 0 if km is None else dw["weight"] * max(0, 1 - km / dw["ref_km"])
    b = pol["bonus"]
    cur = c.get("current")
    src = 0
    if cur:
        src = b["source_official"] if cur.get("source_class") == "official" else b["source_secondary"]
    parts = {
        "outlook": pol["outlook"]["points"][out],
        "freshness": freshness_points(c, pol, subject),
        "distance": round(dist_pts, 1),
        "festival": b["festival_active"] if fest_on else 0,
        "lightup": b["lightup_active"] if light_on else 0,
        "practical": b["practical"] if c.get("practical") else 0,
        "source": src,
    }
    if not has_this_year(c, dates[0].year):                   # 段階58 第3部
        parts["no_this_year"] = -pol["this_year"]["penalty"]
    if subject == "birds" and not cur:                       # 段階57 第4部: 公式の観察の記録がない公園は大きく減点する
        parts["no_official"] = -pol["birds_no_current"]["penalty"]
    return {"outlook": out, "aim": aim, "distance_km": km, "distance_estimated": est, "score": round(sum(parts.values()), 1), "breakdown": parts,
            "festival_active": fest_on, "lightup_active": light_on}


# ---- 計画 ----

def refine_rule(word, pol=None):
    """追質問の語 → 選び直しの条件。語を含む表の項目(長い順)。ないときは ValueError(推測しない)。"""
    pol = pol or load_policy()
    words = pol["refine"]["words"]
    hit = next((k for k in sorted(words, key=len, reverse=True) if k in (word or "")), None)
    if hit is None:
        raise ValueError(f"選び直しの条件が分からない: {word}(使える語: {'・'.join(words)})")
    return words[hit]


def _refine_reject(rows, status, rule, pol, reject):
    """条件に合わない候補を外す。近場で 1 件もなければ、距離の分かる候補を近い順に残す。→ 緩めたか。"""
    alive = [r for r in rows if r["name"] not in status]
    if rule.get("lightup"):
        keep = [r for r in alive if r.get("lightup_active")]
    else:
        keep = [r for r in alive if r["aim"] in rule["aims"]]
    relaxed = False
    if not keep and not rule.get("lightup") and "near" in (rule.get("aims") or []):
        keep = sorted([r for r in alive if r["distance_km"] is not None], key=lambda r: (r["distance_km"], r["name"]))[: pol["refine"]["nearest_fallback"]]
        relaxed = bool(keep)
    names = {r["name"] for r in keep}
    for r in alive:
        if r["name"] not in names:
            reject(r, "refine_excluded")
    return relaxed


def build(facts_doc, subject, policy=None, overrides=None, refine=None):
    """facts.json の 1 対象(subjects.<subject>)から計画を作る。同じ入力なら同じ出力。refine: 追質問の語(段階57 第5部)。"""
    pol = policy or load_policy()
    sub = facts_doc["subjects"][subject]
    dates = [_d(x) for x in facts_doc["dates"]]
    cands = sub.get("candidates") or []
    oo = pol["outlook"]
    rs = pol["reasons"]
    rows = []
    for c in cands:
        r = score_candidate(dict(c, _today=facts_doc.get("now"), _origin=facts_doc.get("origin")), dates, pol, subject)
        r.update({"subject": subject, "id": c.get("id"), "name": c["name"], "cluster": cluster_key(c), "current_state": (c.get("current") or {}).get("state"),
                  "current_date": (c.get("current") or {}).get("state_date"),
                  "current_age_days": (c.get("current") or {}).get("age_days") if not (c.get("current") or {}).get("symbol_only") else None,
                  "stale": bool(c.get("current")) and (c["current"].get("freshness") == "stale"),
                  "target_age_days": _target_age(c, dates[0], facts_doc.get("now")),
                  "has_current": has_current(c), "has_state": has_state_record(c), "this_year": has_this_year(c, dates[0].year), "typical_line": c.get("typical_line"), "closed": bool(c.get("closed_on")) and all(x.get("closed") for x in c["closed_on"]),
                  "practical": [p["text"] for p in c.get("practical") or []][:1],
                  "festivals": [{"name": f["name"], "period_line": f.get("period_line"), "lightup_line": f.get("lightup_line")} for f in c.get("festivals") or []]})
        rows.append(r)
    for c in sub.get("avoid") or []:                                     # facts が「避けたほうがよい」に分けたもの(見頃過ぎ)
        r = score_candidate(dict(c, relation="after_peak", _origin=facts_doc.get("origin")), dates, pol, subject)
        r.update({"subject": subject, "id": c.get("id"), "name": c["name"], "cluster": cluster_key(c), "outlook": "past", "has_current": bool(c.get("current")),
                  "stale": False, "closed": False, "practical": [], "festivals": [], "current_state": (c.get("current") or {}).get("state"),
                  "current_date": (c.get("current") or {}).get("state_date")})
        rows.append(r)
    status = {}                                                            # 名所 → (code, detail)

    def reject(r, code, **kw):
        status.setdefault(r["name"], {"code": code, "label": rs[code], **kw})

    seen_dup = {}
    for r in sorted(rows, key=lambda x: (-x["score"], len(x["name"]), x["name"])):       # 点数の高い順(同点は短い名前)に、同じ名所の別の書き方を外す
        k = _dup_key(r["name"], pol)
        if k in seen_dup:
            reject(r, "duplicate_spot", same_as=seen_dup[k])
        else:
            seen_dup[k] = r["name"]
    day_max = pol["aims"]["day_trip_max_km"]
    for r in rows:
        if r["name"] in status:
            continue
        if r["outlook"] == "past":
            reject(r, "past_expected")
        elif r["distance_km"] is not None and r["distance_km"] > day_max:
            reject(r, "too_far")
        elif r["closed"]:
            reject(r, "closed_that_day")
        elif r["aim"] == "other":
            reject(r, "no_aim")
        elif r["score"] + (pol["this_year"]["penalty"] if r.get("this_year") is False else 0) < pol["selection"]["min_score"]:      # 今年の情報の減点は下で別に扱う
            reject(r, "no_current" if not r["has_current"] else ("stale_current" if r["stale"] else "no_current"))
    relaxed = _refine_reject(rows, status, refine_rule(refine, pol), pol, reject) if refine else False
    no_year = []
    if any(r.get("this_year") and r["name"] not in status for r in rows):  # 段階58 第3部: 今年の情報がない候補は今回のおすすめの対象から外す(別枠に 1 行)。今年の情報のある候補が 1 つもないときは例年の時期で答える(明記の文つき)
        for r in rows:
            if r.get("this_year") is False and (status.get(r["name"]) or {}).get("code") in (None, "no_current", "stale_current"):
                status.setdefault(r["name"], {"code": "no_this_year", "label": rs["no_this_year"]})
                no_year.append(r)
    for c in sub.get("nearby_out_of_region") or []:
        rows.append({"id": c.get("id"), "name": c["name"], "score": 0, "outlook": "unknown", "aim": "other", "distance_km": c.get("distance_km"),
                     "distance_estimated": False, "breakdown": {}, "cluster": cluster_key(c), "has_current": bool(c.get("current")), "stale": False,
                     "closed": False, "practical": [], "festivals": [], "current_state": None, "current_date": None,
                     "festival_active": False, "lightup_active": False})
        status[c["name"]] = {"code": "out_of_range", "label": rs["out_of_range"]}
    ok = [r for r in rows if r["name"] not in status]
    order = pol["aims"]["order"]
    sections = []
    near_by_distance = pol["aims"].get("near_sort") == "distance"
    for aim in order:
        if aim == "near" and near_by_distance:            # 段階60 第3部: 近場の節は、見込みの区分が同じなら出発地に近い順(点数・根拠の強さより距離)
            members = sorted([r for r in ok if r["aim"] == aim],
                             key=lambda x: (-outlook_rank(x, pol), x["distance_km"] if x["distance_km"] is not None else float("inf"), -x["score"], x["name"]))
        else:
            members = sorted([r for r in ok if r["aim"] == aim], key=lambda x: (-x["score"], x["name"]))
        top = members[: pol["aims"]["section_max"]]
        for i, r in enumerate(members):
            if i >= len(top):
                reject(r, "same_aim_has_better", better=top[-1]["name"])
        if top:
            sections.append({"aim": aim, "label": pol["aims"]["labels"][aim], "items": [_item(r, oo) for r in top]})
    # 全体の今回のおすすめ: 節の1位から、見込みの高い順(同じなら点数)。狙いと地域が重ならないように
    firsts = [s["items"][0] for s in sections]
    key = lambda it: rank_key(it, pol)
    chosen, used_cl = [], set()
    by_aim = {it["aim"]: it for it in firsts}
    want = [by_aim[a] for a in pol["selection"]["pick_aims"] if a in by_aim]   # まず、近場・歩く・遠出の各1位(あれば)
    for it in sorted(want, key=key) + sorted([f for f in firsts if f not in want], key=key):
        if len(chosen) < pol["selection"]["picks"] and it["cluster"] not in used_cl:
            chosen.append(it); used_cl.add(it["cluster"])
    if len(chosen) < pol["selection"]["picks"]:                           # 狙いが足りないときは、節の2位以降から
        rest = [it for s in sections for it in s["items"][1:]]
        for it in sorted(rest, key=key):
            if len(chosen) < pol["selection"]["picks"] and it["cluster"] not in used_cl:
                chosen.append(it); used_cl.add(it["cluster"])
    # 段階57 第12部: 利用できるなら、今回のおすすめの min_with_current 件は今年の現況がある候補にする(いちばん下の現況なしの候補から入れ替える)
    pool = sorted([it for s in sections for it in s["items"] if it["has_current"] and it["name"] not in {c["name"] for c in chosen}], key=key)
    while sum(1 for c in chosen if c["has_current"]) < pol["selection"]["min_with_current"] and pool and any(not c["has_current"] for c in chosen):
        out_ = sorted([c for c in chosen if not c["has_current"]], key=key)[-1]
        rest_cl = {c["cluster"] for c in chosen if c is not out_}
        cand = next((p for p in pool if p["cluster"] not in rest_cl), None)
        if cand is None:
            break
        pool.remove(cand)
        chosen[chosen.index(out_)] = cand
    chosen = ensure_near_pick(chosen, sections, pol)          # 段階60 第3部: 近場の候補があれば、今回のおすすめに少なくとも 1 件
    chosen_names = {i["name"] for i in chosen}
    for s in sections:
        for it in s["items"]:
            if it["name"] not in chosen_names:
                it["in_section_only"] = True
    # 節に入ったが今回のおすすめにならなかった名所は不採用の一覧には入れない(節の中で紹介してよい)。同じ地域の重なりだけ理由を残す
    for s in sections:
        for it in s["items"]:
            if it["name"] not in chosen_names and any(it["cluster"] == ch["cluster"] and ch["aim"] != it["aim"] for ch in chosen):
                it["same_area_as_pick"] = True
    if subject == "birds":                                   # 段階57 第4部: 記録のない公園を上位にしない。選ぶときは明記の文を添える
        chosen = sorted(chosen, key=lambda it: (not it["has_current"],) + key(it))
        picks = [dict(it, rank=i + 1, **({} if it["has_state"] else {"note": pol["birds_no_current"]["note"]})) for i, it in enumerate(chosen)]
    else:
        picks = [dict(weaken(it, pol), rank=i + 1, **({} if it["has_state"] else {"note": pol["evidence"]["no_current_note"]}))       # 段階62 第3部: 古い現況は上位に置かない
                 for i, it in enumerate(sorted(chosen, key=lambda it: (is_old_record(it, pol),) + key(it)))]
    ranking = []
    for r in sorted(rows, key=lambda x: (-x["score"], x["name"])):
        st = status.get(r["name"])
        where = "pick" if r["name"] in chosen_names else ("section" if any(r["name"] == it["name"] for s in sections for it in s["items"]) else "not_adopted")
        ranking.append({"rank": len(ranking) + 1, "name": r["name"], "id": r["id"], "score": r["score"], "breakdown": r["breakdown"], "outlook": r["outlook"],
                        "outlook_label": oo["labels"][r["outlook"]], "aim": r["aim"], "distance_km": r["distance_km"], "distance_estimated": r["distance_estimated"],
                        "current_state": r["current_state"], "current_date": r["current_date"], "where": where,
                        "reason": st["code"] if st else None, "reason_label": st["label"] if st else None, "reason_detail": {k: v for k, v in (st or {}).items() if k not in ("code", "label")}})
    return {"schema": SCHEMA, "subject": subject, "dates": [x.isoformat() for x in dates], "origin": facts_doc.get("origin"), "now": facts_doc.get("now"),
            "origin_line": (facts_doc.get("lines") or {}).get("origin_line"),
            "use_headings": len(sections) >= pol["aims"]["min_sections_for_headings"],
            "sections": sections, "picks": picks, "ranking": ranking, "overrides": list(overrides or []),
            "no_this_year": [{"name": r["name"], "typical_line": r.get("typical_line")} for r in sorted(no_year, key=lambda x: (-x["score"], x["name"]))[: pol["this_year"]["max_lines"]]],
            **({"refine": refine, "refine_relaxed": relaxed} if refine else {})}


def ensure_near_pick(chosen, sections, pol):
    """今回のおすすめに、出発地から near_max_km 以内の候補が selection.min_near 件ない(近場の節に候補がある)とき、
    近場の節の上から、いちばん順位の低いおすすめと入れ替える(同じ地域は重ねない。現況のある候補の件数は減らさない)。"""
    want = pol["selection"].get("min_near") or 0
    lim = pol["aims"]["near_max_km"]
    is_near = lambda it: it.get("distance_km") is not None and it["distance_km"] <= lim
    near = next((s["items"] for s in sections if s["aim"] == "near"), [])
    chosen = list(chosen)
    key = lambda it: rank_key(it, pol)
    for cand in near:
        if sum(1 for c in chosen if is_near(c)) >= want:
            break
        if cand in chosen or not is_near(cand):
            continue
        outs = sorted([c for c in chosen if not is_near(c) and (cand["has_current"] or not c["has_current"]
                       or sum(1 for x in chosen if x["has_current"]) > pol["selection"]["min_with_current"])], key=key)
        out_ = next((c for c in reversed(outs) if cand["cluster"] not in {x["cluster"] for x in chosen if x is not c}), None)
        if out_ is None:
            continue
        chosen[chosen.index(out_)] = cand
    return chosen


def evidence_level(it, pol):
    """根拠の強さ: 2 = 今年の新しい現況 / 1 = 現況が古い(または日付なし) / 0 = 現況なし(例年の窓だけ)。"""
    if not it.get("has_current"):
        return 0
    age = it.get("current_age_days")
    return 2 if age is not None and age <= pol["evidence"]["fresh_max_age_days"] else 1


def outlook_rank(it, pol):
    """見込みの区分の順位。現況がなく例年の窓だけの候補は typical_only_rank_cap までにする(段階57 第12部)。"""
    rank = pol["outlook"]["rank"][it["outlook"]]
    if not it.get("has_state", it.get("has_current")):
        rank = min(rank, pol["evidence"]["typical_only_rank_cap"])
    return rank


def rank_key(it, pol):
    """見込みの区分 → 根拠の強さ → 現況の日付の新しさ → 点数 → 名前(段階57 第12部)。"""
    rank = outlook_rank(it, pol)
    return (-rank, -evidence_level(it, pol), tuple(-ord(ch) for ch in (it.get("current_date") or "")), -it["score"], it["name"])


def _target_age(c, d, now=None):
    """段階62 第3部: 現況の日付が、対象日(先の日なら今日)の何日前か(状態が読める記録だけ)。なければ None。
    先の週の質問では、今日までの記録がいちばん新しいので、今日から数える(対象日が今日なら同じ)。"""
    cur = c.get("current") or {}
    if not has_state_record(c) or not cur.get("state_date"):
        return None
    ref = min(d, _d(str(now)[:10])) if now else d
    return (ref - _d(cur["state_date"])).days


def is_old_record(it, pol):
    age = it.get("target_age_days")
    return age is not None and age >= pol["evidence"]["old_record_days"]


def weaken(it, pol):
    """古い現況の候補: 「○日前の記録です」を添え、見込みを弱い言い方にする(old_record_phrases にある区分だけ)。"""
    if not is_old_record(it, pol) or it.get("subject") == "birds":
        return it
    ev = pol["evidence"]
    out = dict(it, old_record=True, old_record_note=ev["old_record_note"].format(n=it["target_age_days"]))
    if it.get("phrase") and it["outlook"] in ev["old_record_phrases"]:
        out["phrase"] = ev["old_record_phrases"][it["outlook"]]
    return out


def _item(r, oo):
    return {"name": r["name"], "id": r["id"], "aim": r["aim"], "score": r["score"], "breakdown": r["breakdown"], "outlook": r["outlook"],
            "outlook_label": oo["labels"][r["outlook"]], "cluster": r["cluster"], "has_current": r["has_current"], "has_state": r.get("has_state", r["has_current"]), "subject": r.get("subject"),
            "current_age_days": r.get("current_age_days"), "target_age_days": r.get("target_age_days"),
            "phrase": None if r.get("subject") == "birds" else (oo["phrases_typical_only"].get(r["outlook"], oo["phrases"][r["outlook"]]) if not r["has_current"] else oo["phrases"][r["outlook"]]),
            "distance_km": r["distance_km"], "distance_estimated": r["distance_estimated"], "current_state": r["current_state"],
            "distance_text": f"約{int(round(r['distance_km']))}km" if r["distance_km"] is not None and not r["distance_estimated"] else None,
            "current_date": r["current_date"], "festivals": r["festivals"], "practical": r["practical"]}


def build_all(facts_doc, policy=None, overrides=None, refine=None):
    """複数の対象(紅葉・花・野鳥)の質問(総合)。対象ごとの計画を作り、全体の今回のおすすめは各対象の1位から(足りなければ点数の高い順)。"""
    pol = policy or load_policy()
    subs = {sj: build(facts_doc, sj, pol, refine=refine) for sj in facts_doc["subjects"]}
    oo = pol["outlook"]
    n = pol["selection"]["picks"]
    firsts = [dict(pl["picks"][0], subject=sj) for sj, pl in subs.items() if pl["picks"]]
    key = lambda it: rank_key(it, pol)
    picks, used = [], set()
    for it in sorted(firsts, key=key):
        if len(picks) < n and it["name"] not in used:
            picks.append(it); used.add(it["name"])
    rest = [dict(it, subject=sj) for sj, pl in subs.items() for it in pl["picks"][1:]]
    for it in sorted(rest, key=key):
        if len(picks) < n and it["name"] not in used:
            picks.append(it); used.add(it["name"])
    picks = [dict(it, rank=i + 1) for i, it in enumerate(sorted(picks, key=lambda it: (is_old_record(it, pol),) + key(it)))]      # 段階62 第3部
    segs = [{"heading": pol["segment_headings"][sj], "key": sj, "subject": sj} for sj in subs]     # 段階57 第3部: 対象別の節(それぞれに今回のおすすめ)で答えるときの見出し
    return {"schema": SCHEMA, "subject": "all", "dates": next(iter(subs.values()))["dates"], "origin": facts_doc.get("origin"), "now": facts_doc.get("now"),
            "use_headings": False, "subjects": subs, "sections": [], "picks": picks, "segments": segs, **({"refine": refine} if refine else {}),
            "ranking": [dict(r, subject=sj) for sj, pl in subs.items() for r in pl["ranking"]], "overrides": list(overrides or [])}


# ---- 複数の都県の指定(段階62 第2部) ----

def _all_picks(plan):
    """計画のすべての採用(全体・対象別・期間別・エリア別)→ 名所の名前の一覧(重複なし)。"""
    out = [p["name"] for p in plan.get("picks") or []]
    for sub in (plan.get("subjects") or {}).values():
        out += [p["name"] for p in sub.get("picks") or []]
    for seg in plan.get("segments") or []:
        if seg.get("plan"):
            out += _all_picks(seg["plan"])
    return list(dict.fromkeys(out))


def attach_region_parts(plan, facts_doc, policy=None):
    """「東京か神奈川で」のような都県の OR の質問 → plan["region_parts"] = [{name, prefectures, picks}](地域ごとの節)。
    答えは地域の名前に漏らさず触れる(area_names に足す。検査器 area_missing)。地域が 1 つのときは何もしない。"""
    from . import observations as O
    q = facts_doc.get("region")
    multi = O.resolve_multi(q, O.load_policy()) if q else None
    if not multi:
        return plan
    pref_of = {}
    for sub in (facts_doc.get("subjects") or {}).values():
        for c in sub.get("candidates") or []:
            pref_of.setdefault(c["name"], c.get("prefecture"))
    for per in facts_doc.get("periods") or []:
        for sub in (per.get("subjects") or {}).values():
            for c in sub.get("candidates") or []:
                pref_of.setdefault(c["name"], c.get("prefecture"))
    names = _all_picks(plan)
    parts = []
    for part in multi["parts"]:
        mine = [n for n in names if pref_of.get(n) in part["prefectures"]]
        parts.append({"name": part["query"], "prefectures": part["prefectures"], "picks": mine})
    plan["region_parts"] = parts
    plan["region_name"] = multi["name"]
    plan["area_names"] = list(dict.fromkeys(list(plan.get("area_names") or []) + [p["name"] for p in parts]))
    return plan


# ---- 日付の既定(段階58 第9部) ----

def default_periods(question, now, policy=None):
    """質問の文に日付の指定がないときの期間。→ {"periods": [[今週末], [来週末]] か [[今週末]], "defaulted": 真偽}。
    指定があるときは defaulted=False(呼び出し側の日付を使う)。今日が土日なら今日と明日。計画段階の質問(「探しています」)は両方。"""
    from . import sources as S
    pol = policy or load_policy()
    cfg = pol["dates_default"]
    q = question or ""
    if any(w in q for w in cfg["date_words"]) or any(re.search(p, q) for p in cfg.get("date_patterns") or []):
        return {"periods": None, "defaulted": False}
    wk1 = S.next_weekend(now)
    if any(w in q for w in cfg["plan_words"]):
        wk2 = [wk1[-1] + timedelta(days=6), wk1[-1] + timedelta(days=7)]
        return {"periods": [wk1, wk2], "defaulted": True}
    return {"periods": [wk1], "defaulted": True}


# ---- 見頃を狙う週(段階58 第7部) ----

def target_weekend(typ, today):
    """例年の見頃の窓のまん中を含む週末(まん中に近い土曜)。→ (土, 日) か None。窓がない・もう過ぎているときは None。"""
    if not typ or not typ.get("start") or not typ.get("end"):
        return None
    s, e = O.window_dates(typ["start"], typ["end"], today)
    mid = s + (e - s) / 2
    sat = mid + timedelta(days=(5 - mid.weekday()) % 7)
    prev = sat - timedelta(days=7)
    if abs((mid - prev).days) < abs((sat - mid).days) and prev >= s:
        sat = prev
    if sat < today:
        return None
    return sat, sat + timedelta(days=1)


def add_target_dates(mat):
    """検査の材料に、見頃を狙う週の日付を足す(例年の見頃の窓からコードが計算した値)。"""
    now = mat.facts.get("now")
    if not now:
        return
    today = _d(now)
    for c in mat.region_candidates:
        typ = next((t for t in c.get("typical") or [] if t.get("start") and t.get("end") and not t.get("event_derived")), None)
        w = target_weekend(typ, today)
        if w:
            mat.dates |= {(w[0].month, w[0].day), (w[1].month, w[1].day)}


def target_week_line(c, today, pol=None):
    """現況がない・古い地点の「見頃を狙うなら○週末」(根拠のラベルと、今年の現況が分からないことを同じ行に書く。言い切らない)。"""
    pol = pol or load_policy()
    if has_current(c) and (c["current"].get("age_days") or 0) <= pol["evidence"]["fresh_max_age_days"]:
        return None
    typ = next((t for t in c.get("typical") or [] if t.get("start") and t.get("end") and not t.get("event_derived")), None)
    w = target_weekend(typ, today)
    if not w:
        return None
    t = pol["target_week"]
    label = t["class_official"] if typ.get("source_class") == "official" else t["class_secondary"]
    return t["line"].format(s=f"{w[0].month}/{w[0].day}", e=f"{w[1].month}/{w[1].day}", publisher=typ.get("publisher") or "", label=label)


# ---- 事前取得の対象(段階57 第9部) ----

def refresh_targets(facts_doc, plan, seen=(), policy=None):
    """計画の上位候補のうち、現況が古い・ないものの読むページ(同じ日に読んだページは除く。最大 max_pages)。取得はエージェントの道具で行う(このコードは通信しない)。"""
    pol = policy or load_policy()
    cfg = pol["refresh"]
    first = _d(facts_doc["dates"][0])
    subjects = facts_doc["subjects"]
    out, used = [], set(seen)
    names = [(p.get("subject") or plan.get("subject"), p["name"]) for p in plan.get("picks") or []]
    names += [(plan.get("subject"), it["name"]) for s in plan.get("sections") or [] for it in s["items"]]
    done = set()
    for sj, name in names:
        if (sj, name) in done or sj not in subjects:
            continue
        done.add((sj, name))
        c = next((x for x in subjects[sj].get("candidates") or [] if x["name"] == name), None)
        if not c:
            continue
        cur = c.get("current")
        sd = (cur or {}).get("state_date")
        stale = (not cur) or (sd is None) or (first - _d(sd)).days >= cfg["stale_days"]
        if not stale:
            continue
        for pg in c.get("pages") or []:
            u = pg.get("url")
            if u and u not in used and len(out) < cfg["max_pages"]:
                used.add(u)
                out.append({"name": name, "subject": sj, "url": u, "publisher": pg.get("publisher"), "source_class": pg.get("source_class"),
                            "reason": "no_current" if not cur else "stale", "current_date": sd})
    return out


# ---- 期間別の節(段階57 第9部) ----

def period_heading(dates, pol):
    """期間の見出し(「11/7・11/8」)。"""
    return pol["period_heading"].format(days="・".join(f"{_d(x).month}/{_d(x).day}" for x in dates))


def build_periods(facts_doc, overrides=None, policy=None, area_rows=None):
    """facts.json の periods(期間ごとの subjects)から、期間ごとの計画を作る。答えは期間別の節で、それぞれに今回のおすすめ。"""
    pol = policy or load_policy()
    segs, picks, ranking = [], [], []
    for per in facts_doc["periods"]:
        sub_doc = {**facts_doc, "subjects": per["subjects"], "dates": per["dates"]}
        subs = list(per["subjects"])
        if area_rows:                                                    # 段階58 第9部: 期間ごとの、エリア別の計画
            pl = build_areas(sub_doc, area_rows, subs[0], pol, overrides)
        else:
            pl = build_all(sub_doc, pol, overrides) if len(subs) > 1 else build(sub_doc, subs[0], pol, overrides)
        segs.append({"heading": period_heading(per["dates"], pol), "key": per["dates"][0], "plan": pl})
        picks += [dict(p, period=per["dates"][0]) for p in pl["picks"] if p["name"] not in {x["name"] for x in picks}]
        ranking += pl["ranking"]
    return {"schema": SCHEMA, "subject": "periods", "dates": facts_doc["dates"], "origin": facts_doc.get("origin"), "now": facts_doc.get("now"),
            "use_headings": False, "sections": [], "picks": picks, "ranking": ranking, "segments": segs, "overrides": list(overrides or []),
            "origin_line": (facts_doc.get("lines") or {}).get("origin_line"), **({"area_names": [a["name"] for a in area_rows]} if area_rows else {})}


# ---- エリア別の節(段階58 第1部・第9部) ----

def build_areas(facts_doc, area_rows, subject, policy=None, overrides=None):
    """エリアごとの計画。各エリアのおすすめは picks_per_area 件まで。全体の今回のおすすめは、エリアが分散するように選ぶ。"""
    from . import areas as AR
    pol = policy or load_policy()
    n_each = pol["areas"]["picks_per_area"]
    sub = facts_doc["subjects"][subject]
    segs, ranking, overall = [], [], []
    for a in area_rows:
        members = AR.members(a, sub.get("candidates") or [])
        doc = {**facts_doc, "subjects": {subject: {**sub, "candidates": members, "avoid": [], "nearby_out_of_region": []}}}
        pl = build(doc, subject, pol, overrides)
        pl["picks"] = [dict(p, rank=i + 1) for i, p in enumerate(pl["picks"][:n_each])]
        segs.append({"heading": a["name"], "key": a["name"], "plan": pl, "area": a["name"]})
        ranking += pl["ranking"]
    key = lambda it: rank_key(it, pol)
    firsts = sorted([s["plan"]["picks"][0] for s in segs if s["plan"]["picks"]], key=key)
    seen = set()
    for it in firsts:
        if it["name"] not in seen and len(overall) < pol["selection"]["picks"]:
            overall.append(it)
            seen.add(it["name"])
    for s in segs:
        for it in s["plan"]["picks"][1:]:
            if it["name"] not in seen and len(overall) < pol["selection"]["picks"]:
                overall.append(it)
                seen.add(it["name"])
    return {"schema": SCHEMA, "subject": "areas", "area_subject": subject, "dates": facts_doc["dates"], "origin": facts_doc.get("origin"), "now": facts_doc.get("now"),
            "use_headings": False, "sections": [], "picks": [dict(p, rank=i + 1) for i, p in enumerate(overall)], "ranking": ranking, "segments": segs, "overrides": list(overrides or []),
            "area_names": [a["name"] for a in area_rows], "origin_line": (facts_doc.get("lines") or {}).get("origin_line")}


def area_errors(text, plan):
    """質問に挙がったエリアは、どれも漏らさず触れる(段階58 第9部)。"""
    return [{"code": "area_missing", "detail": n} for n in plan.get("area_names") or [] if n not in text]


# ---- 対象別の節(段階57 第3部) ----

def _heading_of(line):
    return re.sub(r"^[#■◆▼【\s]+|[】\s:：]+$", "", line)


def segment_plan(plan, seg):
    """節の計画(対象別は subjects の対象、期間別は節が持つ計画)。"""
    return seg.get("plan") or (plan.get("subjects") or {}).get(seg.get("subject"))


def split_segments(text, plan):
    """答えを対象別(期間別)の節に分ける。見出しの行が 2 つ以上あるときだけ → [{"seg", "plan", "text"}]。なければ None(節に分けない答え)。"""
    segs = (plan or {}).get("segments") or []
    if len(segs) < 2:
        return None
    by_head = {s["heading"]: s for s in segs}
    lines = text.splitlines()
    marks = [(i, by_head[_heading_of(l)]) for i, l in enumerate(lines) if _heading_of(l) in by_head]
    if len(marks) < 2:
        return None
    out = []
    for j, (i, s) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(lines)
        out.append({"seg": s, "plan": segment_plan(plan, s), "text": "\n".join(lines[i + 1:end])})
    return out


def lead_text(text, plan):
    """最初の節の見出しの前(全体の冒頭)。"""
    by_head = {s["heading"] for s in (plan or {}).get("segments") or []}
    out = []
    for l in text.splitlines():
        if _heading_of(l) in by_head:
            break
        out.append(l)
    return "\n".join(out)


# ---- 上書き・説明 ----

def add_override(plan, name, reason, replace=None, at=None):
    """計画にない名所を答えに足す・差し替えるときの理由の記録。理由が空なら受け付けない。"""
    if not (reason or "").strip():
        raise ValueError("--reason が要る(計画にない名所を足す理由を書く)")
    if replace and replace not in {p["name"] for p in plan["picks"]}:
        raise ValueError(f"差し替え先「{replace}」は計画の今回のおすすめにない")
    plan["overrides"] = [o for o in plan["overrides"] if o["name"] != name] + [{"name": name, "reason": reason.strip(), "replace": replace, "at": at}]
    return plan


def explain(plan, name):
    """名所の順位・点数の内訳・不採用の理由。名前の一部でも探せる。"""
    hits = [r for r in plan["ranking"] if name in r["name"] or r["name"] in name]
    exact = [r for r in hits if r["name"] == name]
    return exact or hits


# ---- 答えとの照合(ask_verify から呼ぶ) ----

def outlook_conflicts(text, plan, names_of, pol=None):
    """名所を1つだけ書いた文に、その名所の見込みと食い違う言い回しがないか(見頃の終了日を過ぎた名所に「終盤の可能性」など)。"""
    pol = pol or load_policy()
    conf = pol["outlook"].get("conflicts") or {}
    rank = [(r["name"], r.get("outlook")) for r in plan.get("ranking") or []]
    amb = {n for n in {x for x, _ in rank} if len({o for m, o in rank if m == n}) > 1}      # 対象によって見込みが違う名所は判定しない
    rank = [(n, o) for n, o in rank if n not in amb]
    errs, seen = [], set()
    for unit in re.split(r"[。\n]", text):
        if not unit.strip():
            continue
        hits = [(n, o) for n, o in rank if any(f in unit for f in names_of(n))]
        names = {n for n, _ in hits}
        if len(names) != 1:
            continue
        n, o = hits[0]
        for ph in conf.get(o, []):
            if ph in unit and (n, ph) not in seen:
                seen.add((n, ph))
                errs.append({"code": "outlook_conflict", "detail": f"「{n}」は{pol['outlook']['labels'][o]}なのに「{ph}」と書いている"})
    return errs


def plan_errors(text, plan, mat, blocks, names_of):
    """答えの ①②③ の段が、計画の「今回のおすすめ」と合っているか。計画にない名所は、理由の記録(overrides)がなければ不合格。
    names_of(name) → その名所の短い呼び名の一覧。"""
    errs = []
    if plan.get("subject") == "areas":                                       # エリア別の計画: 各エリアのおすすめ全部
        plan = {**plan, "picks": [p for s in plan["segments"] for p in s["plan"]["picks"]]}
    cands = [r["name"] for r in plan["ranking"]]
    over = {o["name"]: o for o in plan.get("overrides") or []}
    pick_names = [p["name"] for p in plan["picks"]]
    replaced = {o["replace"] for o in over.values() if o.get("replace")}
    shown = []
    for b in blocks:
        head = re.split(r"[:：]", b, maxsplit=1)[0]
        hit = next((n for n in cands + list(over) if any(f in head for f in names_of(n))), None)
        if hit is None:
            continue
        shown.append(hit)
        if hit not in pick_names and hit not in over:
            errs.append({"code": "plan_unplanned_spot", "detail": f"「{hit}」は計画の今回のおすすめにない(足す理由を ask plan --override --reason で記録する)"})
    for n in pick_names:
        if n not in shown and n not in replaced:
            errs.append({"code": "plan_pick_missing", "detail": f"計画の今回のおすすめ「{n}」が答えの①②③にない"})
    errs += outlook_conflicts(text, plan, names_of)
    origin = plan.get("origin")
    if origin and origin not in load_policy()["distance"]["estimate_origins"]:     # 段階57 第8部: 新しい出発地は、各おすすめに距離の目安を添える
        for p in plan["picks"]:
            blk = next((b for b in blocks if any(f in re.split(r"[:：]", b, maxsplit=1)[0] for f in names_of(p["name"]))), None)
            if blk is not None and p.get("distance_text") and p["distance_text"] not in blk:
                errs.append({"code": "origin_km_missing", "detail": f"「{p['name']}」: {p['distance_text']}"})
    this_y = str(plan.get("now") or "")[:4]
    for b in blocks:                                                         # 段階58 第3部: 古い年の記事だけをおすすめの根拠にしない
        years = re.findall(r"(20\d\d)年", b)
        if years and this_y and all(y < this_y for y in years) and not re.search(r"\d{1,2}/\d{1,2}時点", b):
            errs.append({"code": "old_year_basis", "detail": b.splitlines()[0][:30]})
    for p in plan["picks"]:                                                  # 段階57 第4部: 明記の文が要るおすすめ
        if not p.get("note"):
            continue
        blk = next((b for b in blocks if any(f in re.split(r"[:：]", b, maxsplit=1)[0] for f in names_of(p["name"]))), None)
        ok_words = [p["note"]] + load_policy()["evidence"]["note_ok_words"]
        if blk is not None and not any(w in blk for w in ok_words):
            errs.append({"code": "pick_note_missing", "detail": f"「{p['name']}」: {p['note']}"})
    return errs
