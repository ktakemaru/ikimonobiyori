"""答えの「計画」をコードで作る(段階56。通信しない・書き込まない。ask.py の plan が作業フォルダに書く)。

目的: 答えに載せる候補の選び方を、その場の手の判断ではなく、再現できる式にする(2026-11-07 の調査: 段階55の答えの3件は手で選んでいた)。
入力は ask facts の出力(facts.json)、出力は計画(JSON): 狙い別の節・各節の採用と順位・全体の「今回のおすすめ」・不採用の一覧と理由コード。
点数の重み・区分・語は data/ask/plan.yaml(コードに数値を書かない)。理由コードは内部用で、答えには出さない。

  python -X utf8 -m ikimonobiyori.ask plan --out-dir DIR [--subject S] [--explain 名所] [--override 名所 --reason 理由 [--replace 計画の名所]]
"""
import re
from datetime import date

import yaml

from . import observations as O
from .paths import DATA_FILES_DIR

PLAN_PATH = DATA_FILES_DIR / "ask" / "plan.yaml"
SCHEMA = "ikimonobiyori-answer-plan/1"


def load_policy(path=None):
    return yaml.safe_load((path or PLAN_PATH).read_text(encoding="utf-8"))


def _d(x):
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])


# ---- 要素ごとの点 ----

def distance_of(c, pol):
    """(km, 見積もりか)。座標がなければ都道府県の見積もり(plan.yaml)。それもなければ (None, False)。"""
    km = c.get("distance_km")
    if km is not None:
        return km, False
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


def aim_of(c, km, lightup, outlook, pol):
    a = pol["aims"]
    if lightup and outlook in a["night_outlooks"]:
        return "night"
    name = c.get("name") or ""
    elev = c.get("elevation_m")
    if re.search(a["trek_name_re"], name):
        return "trek"
    if km is not None and km >= a["far_min_km"]:                  # 遠い名所は、標高が高くても「歩く」ではなく「遠出」
        return "far"
    if elev is not None and elev >= a["trek_min_elevation_m"]:
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
    return {"outlook": out, "aim": aim, "distance_km": km, "distance_estimated": est, "score": round(sum(parts.values()), 1), "breakdown": parts,
            "festival_active": fest_on, "lightup_active": light_on}


# ---- 計画 ----

def build(facts_doc, subject, policy=None, overrides=None):
    """facts.json の 1 対象(subjects.<subject>)から計画を作る。同じ入力なら同じ出力。"""
    pol = policy or load_policy()
    sub = facts_doc["subjects"][subject]
    dates = [_d(x) for x in facts_doc["dates"]]
    cands = sub.get("candidates") or []
    oo = pol["outlook"]
    rs = pol["reasons"]
    rows = []
    for c in cands:
        r = score_candidate(dict(c, _today=facts_doc.get("now")), dates, pol, subject)
        r.update({"subject": subject, "id": c.get("id"), "name": c["name"], "cluster": cluster_key(c), "current_state": (c.get("current") or {}).get("state"),
                  "current_date": (c.get("current") or {}).get("state_date"),
                  "stale": bool(c.get("current")) and (c["current"].get("freshness") == "stale"),
                  "has_current": bool(c.get("current")), "closed": bool(c.get("closed_on")) and all(x.get("closed") for x in c["closed_on"]),
                  "practical": [p["text"] for p in c.get("practical") or []][:1],
                  "festivals": [{"name": f["name"], "period_line": f.get("period_line"), "lightup_line": f.get("lightup_line")} for f in c.get("festivals") or []]})
        rows.append(r)
    for c in sub.get("avoid") or []:                                     # facts が「避けたほうがよい」に分けたもの(見頃過ぎ)
        r = score_candidate(dict(c, relation="after_peak"), dates, pol, subject)
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
        elif r["score"] < pol["selection"]["min_score"]:
            reject(r, "no_current" if not r["has_current"] else ("stale_current" if r["stale"] else "no_current"))
    for c in sub.get("nearby_out_of_region") or []:
        rows.append({"id": c.get("id"), "name": c["name"], "score": 0, "outlook": "unknown", "aim": "other", "distance_km": c.get("distance_km"),
                     "distance_estimated": False, "breakdown": {}, "cluster": cluster_key(c), "has_current": bool(c.get("current")), "stale": False,
                     "closed": False, "practical": [], "festivals": [], "current_state": None, "current_date": None,
                     "festival_active": False, "lightup_active": False})
        status[c["name"]] = {"code": "out_of_range", "label": rs["out_of_range"]}
    ok = [r for r in rows if r["name"] not in status]
    order = pol["aims"]["order"]
    sections = []
    for aim in order:
        members = sorted([r for r in ok if r["aim"] == aim], key=lambda x: (-x["score"], x["name"]))
        top = members[: pol["aims"]["section_max"]]
        for i, r in enumerate(members):
            if i >= len(top):
                reject(r, "same_aim_has_better", better=top[-1]["name"])
        if top:
            sections.append({"aim": aim, "label": pol["aims"]["labels"][aim], "items": [_item(r, oo) for r in top]})
    # 全体の今回のおすすめ: 節の1位から、見込みの高い順(同じなら点数)。狙いと地域が重ならないように
    firsts = [s["items"][0] for s in sections]
    key = lambda it: (-oo["rank"][it["outlook"]], -it["score"], it["name"])
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
    picks = [dict(it, rank=i + 1) for i, it in enumerate(sorted(chosen, key=key))]
    ranking = []
    for r in sorted(rows, key=lambda x: (-x["score"], x["name"])):
        st = status.get(r["name"])
        where = "pick" if r["name"] in chosen_names else ("section" if any(r["name"] == it["name"] for s in sections for it in s["items"]) else "not_adopted")
        ranking.append({"rank": len(ranking) + 1, "name": r["name"], "id": r["id"], "score": r["score"], "breakdown": r["breakdown"], "outlook": r["outlook"],
                        "outlook_label": oo["labels"][r["outlook"]], "aim": r["aim"], "distance_km": r["distance_km"], "distance_estimated": r["distance_estimated"],
                        "current_state": r["current_state"], "current_date": r["current_date"], "where": where,
                        "reason": st["code"] if st else None, "reason_label": st["label"] if st else None, "reason_detail": {k: v for k, v in (st or {}).items() if k not in ("code", "label")}})
    return {"schema": SCHEMA, "subject": subject, "dates": [x.isoformat() for x in dates], "origin": facts_doc.get("origin"), "now": facts_doc.get("now"),
            "use_headings": len(sections) >= pol["aims"]["min_sections_for_headings"],
            "sections": sections, "picks": picks, "ranking": ranking, "overrides": list(overrides or [])}


def _item(r, oo):
    return {"name": r["name"], "id": r["id"], "aim": r["aim"], "score": r["score"], "breakdown": r["breakdown"], "outlook": r["outlook"],
            "outlook_label": oo["labels"][r["outlook"]], "cluster": r["cluster"],
            "phrase": None if r.get("subject") == "birds" else (oo["phrases_typical_only"].get(r["outlook"], oo["phrases"][r["outlook"]]) if not r["has_current"] else oo["phrases"][r["outlook"]]),
            "distance_km": r["distance_km"], "distance_estimated": r["distance_estimated"], "current_state": r["current_state"],
            "current_date": r["current_date"], "festivals": r["festivals"], "practical": r["practical"]}


def build_all(facts_doc, policy=None, overrides=None):
    """複数の対象(紅葉・花・野鳥)の質問(総合)。対象ごとの計画を作り、全体の今回のおすすめは各対象の1位から(足りなければ点数の高い順)。"""
    pol = policy or load_policy()
    subs = {sj: build(facts_doc, sj, pol) for sj in facts_doc["subjects"]}
    oo = pol["outlook"]
    n = pol["selection"]["picks"]
    firsts = [dict(pl["picks"][0], subject=sj) for sj, pl in subs.items() if pl["picks"]]
    key = lambda it: (-oo["rank"][it["outlook"]], -it["score"], it["name"])
    picks, used = [], set()
    for it in sorted(firsts, key=key):
        if len(picks) < n and it["name"] not in used:
            picks.append(it); used.add(it["name"])
    rest = [dict(it, subject=sj) for sj, pl in subs.items() for it in pl["picks"][1:]]
    for it in sorted(rest, key=key):
        if len(picks) < n and it["name"] not in used:
            picks.append(it); used.add(it["name"])
    picks = [dict(it, rank=i + 1) for i, it in enumerate(sorted(picks, key=key))]
    return {"schema": SCHEMA, "subject": "all", "dates": next(iter(subs.values()))["dates"], "origin": facts_doc.get("origin"), "now": facts_doc.get("now"),
            "use_headings": False, "subjects": subs, "sections": [], "picks": picks,
            "ranking": [dict(r, subject=sj) for sj, pl in subs.items() for r in pl["ranking"]], "overrides": list(overrides or [])}


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
    return errs
