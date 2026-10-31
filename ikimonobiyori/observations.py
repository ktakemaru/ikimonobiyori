"""観察の記録と、地域の質問の答えの材料(段階34。通信しない)。

利用者の決定(2026-11-01): 古いデータ・公式でない情報で答えを止めない。Web から読んだ事実(公式ページ・紹介サイト)を
1 件ずつ記録し(record)、記録が無い・古い名所と読むページを出し(refresh --plan)、名所ごとの今の状態・例年の見頃・
行事・対象日との関係・並び順を出す(facts)。どの記録も捨てない。新しさは確かさとして示す。

  python -X utf8 -m ikimonobiyori.observations record --batch <reads.json>
  python -X utf8 -m ikimonobiyori.observations refresh --plan --subject autumn_leaves --region 神奈川 --date 2026-11-02 --now <ISO>
  python -X utf8 -m ikimonobiyori.observations facts --subject autumn_leaves --region 神奈川 --date 2026-11-02 --now <ISO> [--origin 横浜]
  python -X utf8 -m ikimonobiyori.observations normalize --subject autumn_leaves --state "色づき始め"

値・語は data/observations/policy.yaml、名所は data/observations/spots.yaml と既存の名所カタログ(都道府県のタグ)。
書き込み先は IKIMONOBIYORI_DATA_DIR の下の observations/<対象>.jsonl だけ(CLAUDE.md 規則 8)。ホストの許可リストでは拒否しない。
"""
import argparse
import calendar
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import yaml

from . import catalog as catalog_mod
from . import sources as S
from .paths import DATA_FILES_DIR, data_path

OBS_DIR = DATA_FILES_DIR / "observations"
POLICY_PATH = OBS_DIR / "policy.yaml"
SPOTS_PATH = OBS_DIR / "spots.yaml"
CATALOG_SUBJECTS = {"autumn_leaves": "autumn_leaves", "flowers": "flowers", "birds": "birds"}
KANJI_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def load_policy(path=None):
    return yaml.safe_load(Path(path or POLICY_PATH).read_text(encoding="utf-8"))


def load_spots(path=None):
    return yaml.safe_load(Path(path or SPOTS_PATH).read_text(encoding="utf-8"))


def log_path(subject, env=None, policy=None):
    policy = policy or load_policy()
    return data_path(policy["record"]["dir"], env) / f"{subject}.jsonl"


def _key(s):
    """名前の照合用(全角・半角、空白、かっこの違いを無視)。"""
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s()（）「」『』・]", "", s)


# ---- 例年の見頃の原文 → 期間 ----

def _num(s):
    s = unicodedata.normalize("NFKC", s)
    if s.isdigit():
        return int(s)
    return KANJI_NUM.get(s)


def parse_typical(text, policy):
    """「11月中旬～12月上旬」「11月中旬」「11月20日頃」「10/15〜11/15」→ ("MM-DD", "MM-DD")。読めなければ None(推測しない)。"""
    if not text:
        return None
    t = unicodedata.normalize("NFKC", text).replace("〜", "~").replace("～", "~").replace("-", "~")
    thirds = policy["month_thirds"]
    parts = []
    for m, rest in re.findall(r"(\d{1,2})月(上旬|中旬|下旬|\d{1,2}日|)", t):
        mm = int(m)
        last = calendar.monthrange(2001, mm)[1]
        if rest in thirds:
            a, b = thirds[rest]
            parts.append((mm, a, mm, min(b, last)))
        elif rest:
            d = int(rest[:-1])
            if "頃" in t or "ごろ" in t:
                w = _v(policy["around_days"])
                c = date(2001, mm, d)
                lo, hi = c - timedelta(days=w), c + timedelta(days=w)
                parts.append((lo.month, lo.day, hi.month, hi.day))
            else:
                parts.append((mm, d, mm, d))
        else:
            parts.append((mm, 1, mm, last))
    if not parts:
        for a, b in re.findall(r"(\d{1,2})/(\d{1,2})", t):
            parts.append((int(a), int(b), int(a), int(b)))
    if not parts:
        return None
    s, e = parts[0], parts[-1]
    return f"{s[0]:02d}-{s[1]:02d}", f"{e[2]:02d}-{e[3]:02d}"


def window_dates(start_md, end_md, d):
    """対象の日 d の年で期間を日付に(年をまたぐ期間は end を翌年に)。"""
    s = date(d.year, int(start_md[:2]), int(start_md[3:]))
    e = date(d.year, int(end_md[:2]), int(end_md[3:]))
    if e < s:
        e = date(d.year + 1, e.month, e.day)
    return s, e


# ---- 状態の正規化 ----

def normalize(subject, raw, policy=None):
    """原文の状態 → 正規化した語(紅葉: 青葉/色づき始め/見頃/見頃過ぎ、花: 見頃前/見頃/見頃過ぎ)。読めなければ「状態不明」(原文は残す)。"""
    policy = policy or load_policy()
    st = policy["states"].get(subject) or {}
    unknown = policy["unknown_state"]
    text = unicodedata.normalize("NFKC", raw or "")
    if not text.strip():
        return unknown
    if subject == "flowers":
        m = re.search(unicodedata.normalize("NFKC", st["bloom_pattern"]), text)
        if m:
            n = _num(m.group(1))
            if n is not None:
                return "見頃" if n >= _v(st["peak_min_bu"]) else "見頃前"
        if any(w in text for w in ("見頃", "見ごろ", "満開")) and not any(w in text for w in ("過ぎ", "前")):
            if re.search(st["partial_quoted"], raw or "") or any(w in text for w in st["partial_words"]):
                return unknown                                  # 品種名・区画だけの「見頃」は園全体の見頃にしない
    for word, norm in st.get("words") or []:
        if unicodedata.normalize("NFKC", word) in text:
            return norm
    return unknown


# ---- 記録 ----

def clock_now():
    return S.read_time(None)


def validate(rec, policy):
    errs = []
    r = policy["record"]
    for k in r["required"]:
        if not rec.get(k):
            errs.append(f"{k} がない")
    if rec.get("source_class") and rec["source_class"] not in r["source_classes"]:
        errs.append(f"source_class は {r['source_classes']} のどれか")
    if rec.get("subject") not in policy["subjects"]:
        errs.append(f"subject は {policy['subjects']} のどれか")
    if not rec.get("spot") and not rec.get("name"):
        errs.append("spot(名所ID)か name(名前)が要る")
    u = urlparse(rec.get("url") or "")
    if rec.get("url") and (u.scheme not in ("http", "https") or not u.hostname):
        errs.append("url は http(s) の URL")
    for k in ("state_date",):
        v = rec.get(k)
        if v is not None:
            try:
                date.fromisoformat(v)
            except (TypeError, ValueError):
                errs.append(f"{k} は YYYY-MM-DD か null")
    ev = rec.get("event")
    if ev is not None:
        if not isinstance(ev, dict) or not ev.get("name"):
            errs.append("event は {name, start, end}")
        else:
            for k in ("start", "end"):
                if ev.get(k) is not None:
                    try:
                        date.fromisoformat(ev[k])
                    except (TypeError, ValueError):
                        errs.append(f"event.{k} は YYYY-MM-DD か null")
    return errs


FIELDS = ("subject", "spot", "name", "city", "prefecture", "area", "kind", "state", "state_date", "typical", "event", "url", "publisher", "source_class")


def make_record(rec, policy, read_at):
    """検査に通った読んだ事実 → 記録の 1 行(原文は 80 字まで。正規化した語・読んだ時刻はコードが入れる)。"""
    mx = _v(policy["record"]["max_raw_chars"])
    out = {k: rec.get(k) for k in FIELDS if rec.get(k) is not None}
    out["state"] = str(rec["state"])[:mx]
    if out.get("typical"):
        out["typical"] = str(out["typical"])[:mx]
    out["state_norm"] = normalize(rec["subject"], out["state"], policy)
    out.setdefault("state_date", None)
    out["host"] = urlparse(rec["url"]).hostname
    out["read_at"] = read_at.isoformat()
    return out


def read_records(subject, env=None, policy=None):
    p = log_path(subject, env, policy)
    if not p.exists():
        return []
    policy = policy or load_policy()
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:                              # 正規化は読むたびに今の方針でやり直す(語の表を直したら古い記録にも効く。原文は残っている)
        r["state_norm"] = normalize(r.get("subject") or subject, r.get("state"), policy)
    return rows


def _dup_key(r):
    return (r.get("spot") or _key(r.get("name")), r.get("url"), r.get("state"), r.get("state_date"), r["read_at"][:10], r.get("area"), r.get("prefecture"))


def record(batch, *, env=None, policy=None, now=None):
    """読んだ事実の配列を記録に追記する。→ {written, duplicates, rejected: [{index, errors}]}。ホストでは拒否しない。"""
    policy = policy or load_policy()
    read_at = now or clock_now()
    written, dup, rejected = [], 0, []
    by_subject = {}
    for i, rec in enumerate(batch):
        errs = validate(rec, policy) if isinstance(rec, dict) else ["記録は JSON のオブジェクト"]
        if errs:
            rejected.append({"index": i, "errors": errs})
            continue
        by_subject.setdefault(rec["subject"], []).append(make_record(rec, policy, read_at))
    for subject, rows in by_subject.items():
        have = {_dup_key(r) for r in read_records(subject, env, policy)}
        p = log_path(subject, env, policy)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="") as f:
            for r in rows:
                k = _dup_key(r)
                if k in have:
                    dup += 1
                    continue
                have.add(k)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                written.append(r)
    return {"written": len(written), "duplicates": dup, "rejected": rejected, "records": written}


# ---- 候補(名所の一覧 + 既存の名所カタログ) ----

def _typical_from_catalog(e):
    out = []
    tw = e.get("typical_window")
    if tw:
        out.append({"text": tw.get("note") or f"{int(tw['start'][:2])}/{int(tw['start'][3:])}〜{int(tw['end'][:2])}/{int(tw['end'][3:])}",
                    "start": tw["start"], "end": tw["end"], "url": tw.get("source_url"), "publisher": urlparse(tw.get("source_url") or "").hostname,
                    "year": None, "source_class": "official"})
    for w in e.get("flower_windows") or []:
        out.append({"text": f"{int(w['start'][:2])}/{int(w['start'][3:])}〜{int(w['end'][:2])}/{int(w['end'][3:])}", "kind": w["kind"],
                    "start": w["start"], "end": w["end"], "url": w["source_url"], "publisher": urlparse(w["source_url"]).hostname,
                    "year": w.get("source_year"), "source_class": "secondary" if (w.get("source_class") == "secondary" or w.get("unapproved_host")) else "official"})
    return out


def _events_from_catalog(e):
    return [{"name": v["name"], "kind": v.get("kind"), "start": v["start"], "end": v["end"], "url": v["source_url"],
             "publisher": urlparse(v["source_url"]).hostname,
             "source_class": "secondary" if (v.get("source_class") == "secondary" or v.get("unapproved_host")) else "official"}
            for v in e.get("events") or []]


def _from_catalog(e, subject):
    t = e.get("tags") or {}
    return {"id": e["id"], "subject": subject, "name": e["name"], "prefecture": t.get("prefecture"), "city": t.get("city"),
            "area": t.get("area"), "point": e.get("point"), "elevation_m": (e.get("point") or {}).get("elevation_m"),
            "typical": _typical_from_catalog(e), "events": _events_from_catalog(e),
            "pages": [{"url": s["url"], "publisher": s.get("title") or urlparse(s["url"]).hostname, "source_class": "official"} for s in e.get("sources") or []],
            "flower_kinds": t.get("flower_kinds") or [], "from_catalog": True}


def _from_spot(s, policy, catalog_by_id):
    typ = []
    for t in s.get("typical") or []:
        w = parse_typical(t["text"], policy)
        typ.append({**t, "start": w[0] if w else None, "end": w[1] if w else None})
    c = {"id": s["id"], "subject": s["subject"], "name": s["name"], "aliases": s.get("aliases") or [], "prefecture": s.get("prefecture"),
         "city": s.get("city"), "area": s.get("area"), "point": None, "elevation_m": s.get("elevation_m"), "elevation_note": s.get("elevation_note"),
         "typical": typ, "events": list(s.get("events") or []), "pages": list(s.get("pages") or []), "search": s.get("search"),
         "hours": s.get("hours"), "closed": s.get("closed"), "birds_note": s.get("birds_note"), "flower_kinds": s.get("flower_kinds") or []}
    ref = catalog_by_id.get(s.get("catalog_ref"))
    if ref:
        cat = _from_catalog(ref, s["subject"])
        c["catalog_ref"] = ref["id"]
        c["aliases"] = c["aliases"] + [ref["name"]]
        c["point"] = cat["point"]
        c["elevation_m"] = c["elevation_m"] if c["elevation_m"] is not None else cat["elevation_m"]
        seen = {(t.get("start"), t.get("end"), t.get("kind")) for t in c["typical"]}
        c["typical"] += [t for t in cat["typical"] if (t["start"], t["end"], t.get("kind")) not in seen]
        names = {ev["name"] for ev in c["events"]}
        c["events"] += [ev for ev in cat["events"] if ev["name"] not in names]
        urls = {p["url"] for p in c["pages"]}
        c["pages"] += [p for p in cat["pages"] if p["url"] not in urls]
        c["flower_kinds"] = c["flower_kinds"] or cat["flower_kinds"]
    return c


def all_candidates(subject, policy=None, spots_doc=None, catalogs=None):
    """対象の候補(名所の一覧 + 既存の名所カタログ。カタログの退役・却下の名所は除く)。"""
    policy = policy or load_policy()
    spots_doc = spots_doc if spots_doc is not None else load_spots()
    if catalogs is None:
        catalogs = {}
        cs = CATALOG_SUBJECTS.get(subject)
        if cs:
            catalogs[cs] = catalog_mod.load_catalog(cs)
    cat_entries = [e for doc in catalogs.values() for e in (doc.get("entries") or [])
                   if not e.get("example") and e.get("status") not in ("retired", "rejected")]
    by_id = {e["id"]: e for e in cat_entries}
    out = [_from_spot(s, policy, by_id) for s in spots_doc.get("spots") or [] if s["subject"] == subject]
    used = {c.get("catalog_ref") for c in out}
    out += [_from_catalog(e, subject) for e in cat_entries if e["id"] not in used]
    return out


def match_record(rec, cands):
    if rec.get("spot"):
        for c in cands:
            if rec["spot"] in (c["id"], c.get("catalog_ref")):
                return c
    k = _key(rec.get("name"))
    for c in cands:
        if k and k in [_key(n) for n in [c["name"], *(c.get("aliases") or [])]]:
            return c
    return None


# ---- 新しさ ----

def basis_date(rec):
    return date.fromisoformat(rec["state_date"]) if rec.get("state_date") else date.fromisoformat(rec["read_at"][:10])


def freshness(rec, today, subject, policy):
    if rec is None:
        return {"class": "none", "label": policy["freshness"]["labels"]["none"], "age_days": None}
    f = policy["freshness"]
    age = (today - basis_date(rec)).days
    cls = "fresh" if age <= f["fresh_days"][subject] else "stale" if age <= f["stale_days"] else "very_stale"
    return {"class": cls, "label": f["labels"][cls], "age_days": age, "basis": "state_date" if rec.get("state_date") else "read_at"}


def best_record(rows):
    """同じ名所の記録から 1 つ(状態の日付が新しい → 公式 → 読んだ時刻が新しい)。古い記録も捨てない(history に残る)。"""
    if not rows:
        return None
    return sorted(rows, key=lambda r: (basis_date(r), r.get("source_class") == "official", r["read_at"]), reverse=True)[0]


# ---- 地域 ----

def resolve(region_query, origin, policy, regions_doc=None):
    """地域の呼び名 → {name, prefectures, areas}。指定がなければ出発地の都道府県。"""
    regions_doc = regions_doc or S.load_regions()
    if region_query:
        r = S.resolve_region(region_query, regions_doc)
        if r is None:
            return {"name": region_query, "prefectures": [], "areas": [], "resolved": False}
        m = r.get("match") or {}
        return {"name": r["name"], "prefectures": m.get("prefectures") or [], "areas": m.get("areas") or [], "resolved": True}
    pref = policy["origin_home"].get(origin)
    return {"name": pref, "prefectures": [pref] if pref else [], "areas": [], "resolved": bool(pref), "from_origin": True}


def in_region(c, region):
    return c.get("prefecture") in region["prefectures"] or (c.get("area") in region["areas"])


# ---- refresh --plan ----

def plan(subject, *, region=None, dates, now, origin=None, env=None, policy=None, spots_doc=None, catalogs=None):
    """取りに行く対象。先頭に地域のまとめページ、続いて記録が無い・古い・かなり古い名所(新しいものは出ない)。"""
    policy = policy or load_policy()
    cat_pol = catalog_mod.load_policy()
    origin = origin or cat_pol["range_limit"]["default_origin"]
    reg = resolve(region, origin, policy)
    cands = [c for c in all_candidates(subject, policy, spots_doc, catalogs) if in_region(c, reg)]
    recs = read_records(subject, env, policy)
    today = now.date()
    items, fresh = [], []
    for c in cands:
        rows = [r for r in recs if match_record(r, [c])]
        b = best_record(rows)
        fr = freshness(b, today, subject, policy)
        if fr["class"] == "fresh":
            fresh.append(c["name"])
            continue
        items.append({"id": c["id"], "name": c["name"], "city": c.get("city"), "freshness": fr,
                      "last_state_date": b.get("state_date") if b else None,
                      "pages": [p for p in c.get("pages") or []],
                      "search": c.get("search") or policy["search_templates"][subject].format(name=c["name"], kind="・".join(c.get("flower_kinds") or []) or "")})
    prefs = sorted({c.get("prefecture") for c in cands if c.get("prefecture")} | set(reg["prefectures"]))
    summary = [] if not items else [p for pref in prefs for p in (policy["summary_pages"].get(subject) or {}).get(pref) or []]
    order = {"none": 0, "very_stale": 1, "stale": 2}
    items.sort(key=lambda x: (order[x["freshness"]["class"]], x["id"]))
    return {"schema": "ikimono-observations-plan/1", "subject": subject, "region": reg["name"], "dates": [d.isoformat() for d in dates],
            "now": now.isoformat(), "needs_fetch": bool(items), "summary_pages": summary, "items": items, "fresh": fresh,
            "limits": policy["fetch_limits"]}


# ---- facts ----

def _covers(t, d, pad=0):
    if not t.get("start") or not t.get("end"):
        return None
    s, e = window_dates(t["start"], t["end"], d)
    return s - timedelta(days=pad) <= d <= e + timedelta(days=pad)


def _relation(cur, typ, d, policy):
    lab = policy["relation_labels"]
    if cur and cur["state_norm"] == "見頃過ぎ":
        return "after_peak"
    if typ and typ.get("start"):
        s, e = window_dates(typ["start"], typ["end"], d)
        if d < s:
            return "before_peak"
        if d > e:
            return "after_peak"
        return "in_peak"
    if cur and cur["state_norm"] == "見頃":
        return "in_peak"
    return "unknown" if "unknown" in lab else None


def _event_hits(c, dates):
    out = []
    for ev in c.get("events") or []:
        if not ev.get("start") or not ev.get("end"):
            continue
        s, e = date.fromisoformat(ev["start"]), date.fromisoformat(ev["end"])
        if any(s <= d <= e for d in dates):
            out.append(ev)
    return out


def _distance(c, origin, cat_pol):
    p = c.get("point")
    if not p or p.get("lat") is None:
        return None
    return catalog_mod.range_from(cat_pol, p, origin)["km"]


def _publishers(c, rows):
    pubs = {(p.get("publisher") or urlparse(p.get("url") or "").hostname) for p in (c.get("typical") or []) + (c.get("pages") or [])}
    pubs |= {r.get("publisher") or r.get("host") for r in rows}
    return sorted(x for x in pubs if x)


def fact_for(c, rows, dates, today, subject, policy, origin, cat_pol):
    d = dates[0]
    cur = best_record(rows)
    fr = freshness(cur, today, subject, policy)
    typ = next((t for t in c.get("typical") or [] if t.get("start")), None)
    typ_rec = next((r.get("typical") for r in sorted(rows, key=lambda r: r["read_at"], reverse=True) if r.get("typical")), None)
    if typ is None and typ_rec:
        w = parse_typical(typ_rec, policy)
        if w:
            typ = {"text": typ_rec, "start": w[0], "end": w[1], "publisher": cur.get("publisher") if cur else None, "source_class": "secondary"}
    rel = _relation(cur, typ, d, policy)
    evs = _event_hits(c, dates)
    rec_events = [{"name": r["event"]["name"], "start": r["event"].get("start"), "end": r["event"].get("end"), "url": r["url"],
                   "publisher": r.get("publisher"), "source_class": r["source_class"]} for r in rows if r.get("event")]
    evs += [e for e in rec_events if e.get("start") and e.get("end") and any(date.fromisoformat(e["start"]) <= x <= date.fromisoformat(e["end"]) for x in dates)
            and e["name"] not in {v["name"] for v in evs}]
    near = _v(policy["order"]["near_days"])
    st = cur["state_norm"] if cur else None
    order_map = (policy["states"].get(subject) or {}).get("order") or {}
    covers = bool(typ) and _covers(typ, d)
    covers_near = bool(typ) and _covers(typ, d, near)
    start_states = {k for k, v in order_map.items() if v in (0, 1)} - {"青葉"} if subject == "autumn_leaves" else {k for k, v in order_map.items() if v == 0}
    if st == "見頃" or (covers and st in (None, policy["unknown_state"])):
        tier = 1
    elif st in start_states and covers_near:
        tier = 2
    else:
        tier = 3
    if fr["class"] == "fresh":
        ev_rank = "fresh_official" if cur["source_class"] == "official" else "fresh_secondary"
    elif cur is not None:
        ev_rank = "stale"
    else:
        ev_rank = "typical_only"
    avoid = None
    if st == "見頃過ぎ":
        avoid = "past"
    elif ((subject == "autumn_leaves" and st == "青葉") or (subject == "flowers" and st == "見頃前")) and typ and typ.get("start") \
            and not covers_near and rel == "before_peak":
        avoid = "too_early"
    elif typ and typ.get("start") and rel == "after_peak" and st is None:
        avoid = "past"
    dist = _distance(c, origin, cat_pol)
    reasons = []
    if st == "見頃" and fr["class"] == "fresh":
        reasons.append("peak_now")
    if st in start_states and rel in ("before_peak", "in_peak"):
        reasons.append("coming")
    if covers:
        reasons.append("typical_overlaps")
    if evs:
        reasons.append("event")
    current = None
    if cur:
        current = {"state": cur["state_norm"], "state_raw": cur["state"], "state_date": cur.get("state_date"), "read_at": cur["read_at"],
                   "publisher": cur.get("publisher") or cur.get("host"), "url": cur["url"], "source_class": cur["source_class"],
                   "freshness": fr["class"], "freshness_label": fr["label"], "age_days": fr["age_days"]}
    pubs = _publishers(c, rows)
    return {"id": c["id"], "name": c["name"], "city": c.get("city"), "prefecture": c.get("prefecture"), "area": c.get("area"),
            "elevation_m": c.get("elevation_m"), "elevation_note": c.get("elevation_note"),
            "current": current, "current_unknown": cur is None,
            "history": [{"state": r["state_norm"], "state_raw": r["state"], "state_date": r.get("state_date"), "publisher": r.get("publisher"),
                         "url": r["url"], "source_class": r["source_class"]} for r in sorted(rows, key=lambda r: (basis_date(r), r["read_at"]), reverse=True)[1:4]],
            "typical": [{k: t.get(k) for k in ("text", "kind", "start", "end", "publisher", "url", "year", "source_class")} for t in c.get("typical") or []]
                       + ([] if not typ or typ in (c.get("typical") or []) else [typ]),
            "events": evs, "relation": rel, "relation_label": policy["relation_labels"][rel],
            "distance_km": dist, "reasons": reasons, "tier": tier, "evidence": ev_rank, "reference_count": len(pubs), "publishers": pubs,
            "avoid": avoid, "hours": c.get("hours"), "closed": c.get("closed"), "birds_note": c.get("birds_note"),
            "flower_kinds": c.get("flower_kinds") or [], "pages": c.get("pages") or [], "_order": order_map.get(st, -1) if st else -1}


def facts(subject, *, region=None, dates, now, origin=None, env=None, policy=None, spots_doc=None, catalogs=None, with_alternatives=True):
    """地域の質問の答えの材料。記録が古くても空でも、例年の時期で候補を出す。"""
    policy = policy or load_policy()
    cat_pol = catalog_mod.load_policy()
    origin = origin or cat_pol["range_limit"]["default_origin"]
    reg = resolve(region, origin, policy)
    today = now.date()
    cands = all_candidates(subject, policy, spots_doc, catalogs)
    recs = read_records(subject, env, policy)
    by_c = {c["id"]: [] for c in cands}
    extra = {}
    for r in recs:
        c = match_record(r, cands)
        if c:
            by_c[c["id"]].append(r)
        else:                                   # 一覧にない名所の記録もカタログ外として残す
            k = _key(r.get("name"))
            extra.setdefault(k, {"id": "extra-" + k, "subject": subject, "name": r.get("name"), "city": r.get("city"),
                                 "prefecture": None, "area": None,
                                 "typical": [], "events": [], "pages": [], "outside_list": True, "rows": []})["rows"].append(r)
            x = extra[k]
            x["prefecture"] = x["prefecture"] or r.get("prefecture")
            x["area"] = x["area"] or r.get("area")
    all_f = [fact_for(c, by_c[c["id"]], dates, today, subject, policy, origin, cat_pol) for c in cands]
    for x in extra.values():
        if x["prefecture"] is None and x["area"] is None and reg["prefectures"] and not reg["areas"]:
            x["prefecture"] = reg["prefectures"][0]         # 都道府県だけの地域で、記録に場所の手がかりがないとき(従来どおり)
        f = fact_for(x, x["rows"], dates, today, subject, policy, origin, cat_pol)
        f["outside_list"] = True
        all_f.append(f)
    ev_rank = policy["order"]["evidence_rank"]

    def sort_key(f):
        return (f["tier"], ev_rank[f["evidence"]], -f["_order"] if f["tier"] == 3 else 0, -f["reference_count"],
                f["distance_km"] if f["distance_km"] is not None else float("inf"), f["id"])
    inreg = [f for f in all_f if in_region({"prefecture": f["prefecture"], "area": f["area"]}, reg)]
    rec_f = sorted([f for f in inreg if not f["avoid"]], key=sort_key)
    avoid = sorted([f for f in inreg if f["avoid"]], key=lambda f: (f["avoid"], f["id"]))
    nearby = []
    if len(rec_f) < _v(policy["min_candidates"]):
        rng = cat_pol["range_limit"]["max_km"]
        nearby = sorted([f for f in all_f if f not in inreg and not f["avoid"] and f["distance_km"] is not None and f["distance_km"] <= rng],
                        key=lambda f: (f["tier"], f["distance_km"]))[: _v(policy["min_candidates"])]
        for f in nearby:
            f["out_of_region"] = True
    with_rec = [f for f in inreg if f["current"]]
    max_order = max((f["_order"] for f in with_rec), default=-1)
    for f in rec_f:
        if f["current"] and f["_order"] == max_order and max_order > 0:
            f["reasons"].insert(0, "most_advanced")
    dk = [f for f in rec_f if f["distance_km"] is not None]
    for f in sorted(dk, key=lambda f: f["distance_km"])[:_v(policy["min_candidates"])]:
        f["reasons"].append("near")
    for f in all_f:
        f["reason_labels"] = [policy["reason_labels"][r] for r in f["reasons"]]
        if f["avoid"]:
            f["avoid_label"] = policy["avoid_reasons"][f["avoid"]]
        f.pop("_order", None)
    alts = []
    if with_alternatives and subject == "autumn_leaves":
        fl = facts("flowers", region=region, dates=dates, now=now, origin=origin, env=env, policy=policy, spots_doc=spots_doc,
                   catalogs=None if catalogs is None else {"flowers": catalogs.get("flowers", {"entries": []})}, with_alternatives=False)
        alts = [{"name": f["name"], "city": f["city"], "events": f["events"], "typical": f["typical"][:1], "current": f["current"]}
                for f in fl["candidates"] if f["events"]]
    states = {}
    for f in with_rec:
        states[f["current"]["state"]] = states.get(f["current"]["state"], 0) + 1
    srcs = sorted({u for f in inreg + nearby for u in ([f["current"]["url"]] if f["current"] else []) + [t["url"] for t in f["typical"] if t.get("url")]})
    as_of = sorted({f["current"]["state_date"] for f in with_rec if f["current"]["state_date"]})
    return {"schema": "ikimono-observations-facts/1", "subject": subject, "subject_label": policy["subject_labels"][subject],
            "region": reg["name"], "region_resolved": reg["resolved"], "origin": origin, "dates": [x.isoformat() for x in dates],
            "now": now.isoformat(), "candidates": rec_f, "avoid": avoid, "nearby_out_of_region": nearby, "alternatives": alts,
            "summary": {"candidate_count": len(rec_f), "with_record": len(with_rec), "states": states, "state_dates": as_of,
                        "any_fresh": any(f["current"]["freshness"] == "fresh" for f in with_rec),
                        "any_official": any(f["current"]["source_class"] == "official" for f in with_rec)},
            "source_urls": srcs}


def self_check(text, policy=None):
    policy = policy or load_policy()
    return [w for w in policy["forbidden_terms"] if w in text]


# ---- CLI ----

def _dates(a, now):
    if a.date:
        return [date.fromisoformat(x) for x in a.date]
    return S.next_weekend(now)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="observations")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="読んだ事実を記録に追記する(IKIMONOBIYORI_DATA_DIR の下。ホストでは拒否しない)")
    r.add_argument("--batch", required=True)
    for name in ("refresh", "plan", "facts"):
        p = sub.add_parser(name)
        p.add_argument("--subject", required=True)
        p.add_argument("--region")
        p.add_argument("--date", action="append")
        p.add_argument("--now", required=True)
        p.add_argument("--origin")
        if name == "refresh":
            p.add_argument("--plan", action="store_true", required=True, help="取りに行く対象を出す(読むのは窓口のエージェント)")
    n = sub.add_parser("normalize")
    n.add_argument("--subject", required=True)
    n.add_argument("--state", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "record":
        batch = json.loads(Path(a.batch).read_text(encoding="utf-8"))
        out = record(batch if isinstance(batch, list) else [batch])
        out.pop("records")
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 1 if out["rejected"] else 0
    if a.cmd == "normalize":
        print(normalize(a.subject, a.state))
        return 0
    now = S.parse_now(a.now)
    dates = _dates(a, now)
    if a.cmd in ("refresh", "plan"):
        out = plan(a.subject, region=a.region, dates=dates, now=now, origin=a.origin)
    else:
        out = facts(a.subject, region=a.region, dates=dates, now=now, origin=a.origin)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
