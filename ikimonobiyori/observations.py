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
from . import closures
from . import sources as S
from .paths import DATA_FILES_DIR, data_path

OBS_DIR = DATA_FILES_DIR / "observations"
POLICY_PATH = OBS_DIR / "policy.yaml"
SPOTS_PATH = OBS_DIR / "spots.yaml"
BIRD_AREAS_PATH = OBS_DIR / "bird_areas.yaml"                  # 段階35: 観察の記録用の野鳥の区域(sites.yaml の bird_areas とは別)
CATALOG_SUBJECTS = {"autumn_leaves": "autumn_leaves", "flowers": "flowers", "birds": "birds"}
KANJI_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def load_policy(path=None):
    return yaml.safe_load(Path(path or POLICY_PATH).read_text(encoding="utf-8"))


def load_spots(path=None):
    return yaml.safe_load(Path(path or SPOTS_PATH).read_text(encoding="utf-8"))


def load_obs_bird_areas(path=None):
    p = Path(path or BIRD_AREAS_PATH)
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("bird_areas") or [] if p.exists() else []


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
    for ph in policy.get("not_state_phrases") or []:            # 段階37: 「例年の見頃」「見頃予想」のような時期を表す語の中の「見頃」は今の状態として読まない
        text = text.replace(unicodedata.normalize("NFKC", ph), " ")
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
    sp = rec.get("species")                     # 段階38: 野鳥の記録に書かれた鳥の名前(書かれたとおり)。任意
    if sp is not None and (not isinstance(sp, list) or not all(isinstance(x, str) and x.strip() and len(x) <= _v(policy["record"]["max_raw_chars"]) for x in sp)):
        errs.append("species は鳥の名前(文字列)の配列")
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


FIELDS = ("subject", "spot", "name", "city", "prefecture", "area", "kind", "state", "state_date", "state_date_text", "typical", "event", "url", "publisher",
          "source_class", "species")


STATE_DATE_RES = (re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})\s*(?:現在|時点)"), re.compile(r"(\d{1,2})月(\d{1,2})日\s*(?:現在|時点)"))


DAY_ONLY_RE = re.compile(r"(?<![\d/月])(\d{1,2})日\s*(?:現在|時点)")        # 段階37: 「01日現在」のように月がない書き方


def _day_only(day, ra):
    """月のない「D日」→ 読んだ日以前でいちばん近いその日(11/1 に読んだ「01日」→ 11/1、「31日」→ 10/31)。"""
    y, m = ra.year, ra.month
    for _ in range(13):
        if day <= calendar.monthrange(y, m)[1]:
            d = date(y, m, day)
            if d <= ra:
                return d
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return None


def state_date_from_text(text, read_at, with_kind=False):
    """状態の原文に書かれた「10/25現在」「10月8日現在」→ YYYY-MM-DD(年は読んだ日から。読んだ日より後なら前の年)。
    段階37: 月のない「01日現在」は、読んだ日以前でいちばん近いその日(種類 day_only)。なければ None。
    with_kind=True なら (日付, 種類 "month_day" / "day_only")。"""
    t = unicodedata.normalize("NFKC", text or "")
    ra = date.fromisoformat(str(read_at)[:10])
    out = (None, None)
    for rx in STATE_DATE_RES:
        m = rx.search(t)
        if m:
            try:
                d = date(ra.year, int(m.group(1)), int(m.group(2)))
            except ValueError:
                d = None
            if d is not None and d > ra:
                d = date(ra.year - 1, d.month, d.day)
            out = (d.isoformat() if d else None, "month_day")
            break
    else:
        m = DAY_ONLY_RE.search(t)
        if m and 1 <= int(m.group(1)) <= 31:
            d = _day_only(int(m.group(1)), ra)
            out = (d.isoformat() if d else None, "day_only")
    return out if with_kind else out[0]


def make_record(rec, policy, read_at):
    """検査に通った読んだ事実 → 記録の 1 行(原文は 80 字まで。正規化した語・読んだ時刻はコードが入れる)。"""
    mx = _v(policy["record"]["max_raw_chars"])
    out = {k: rec.get(k) for k in FIELDS if rec.get(k) is not None}
    out["state"] = str(rec["state"])[:mx]
    if out.get("typical"):
        out["typical"] = str(out["typical"])[:mx]
    out["state_norm"] = normalize(rec["subject"], out["state"], policy)
    out.setdefault("state_date", None)
    if out.get("state_date_text"):
        out["state_date_text"] = str(out["state_date_text"])[:mx]
    if not out["state_date"]:                    # 段階37: 月のない「01日現在」(状態の原文か state_date_text)は、読んだ日以前でいちばん近いその日として補い、印を残す
        d, kind = state_date_from_text(out.get("state_date_text") or out["state"], read_at.isoformat(), with_kind=True)
        if d and (kind == "day_only" or out.get("state_date_text")):
            out["state_date"] = d
            out["state_date_inferred"] = policy["state_date_inferred"][kind]
    out["host"] = urlparse(rec["url"]).hostname
    out["read_at"] = read_at.isoformat()
    return out


def confirmed_path(subject, env=None, policy=None):
    """段階37: 同じ事実を読み直したときの「最後に確かめた日時」(記録の行は書き換えず、別のファイルに持つ)。"""
    policy = policy or load_policy()
    return data_path(policy["record"]["dir"], env) / f"{subject}.confirmed.json"


def read_confirmed(subject, env=None, policy=None):
    try:
        return json.loads(confirmed_path(subject, env, policy).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def read_records(subject, env=None, policy=None):
    p = log_path(subject, env, policy)
    if not p.exists():
        return []
    policy = policy or load_policy()
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    conf = read_confirmed(subject, env, policy)
    for r in rows:                              # 正規化は読むたびに今の方針でやり直す(語の表を直したら古い記録にも効く。原文は残っている)
        r["state_norm"] = normalize(r.get("subject") or subject, r.get("state"), policy)
        if not r.get("state_date"):             # 段階35: 状態の日付が欄になくても、原文の「10/25現在」を状態の日付として使う(記録のファイルは書き換えない)
            r["state_date_from_text"] = state_date_from_text(r.get("state"), r["read_at"])
        c = conf.get(dup_key_text(r))
        if c and c.get("last_confirmed_at", "") > r["read_at"]:
            r["last_confirmed_at"] = c["last_confirmed_at"]
    return rows


def _dup_key(r):
    """段階37: 同じ名所・同じ状態の語・同じ状態の日付(と同じ例年の時期・行事)の記録は、URL や読んだ日が違っても新しい記録に数えない。"""
    ev = r.get("event")
    return [r.get("spot") or _key(r.get("name")), unicodedata.normalize("NFKC", r.get("state") or "").strip(), state_date_of(r),
            r.get("typical"), json.dumps(ev, ensure_ascii=False, sort_keys=True) if ev else None, r.get("area"), r.get("prefecture")]


def dup_key_text(r):
    return json.dumps(_dup_key(r), ensure_ascii=False)


def record(batch, *, env=None, policy=None, now=None):
    """読んだ事実の配列を記録に追記する。→ {written, duplicates, rejected: [{index, errors}]}。ホストでは拒否しない。"""
    policy = policy or load_policy()
    read_at = now or clock_now()
    written, dup, rejected = [], 0, []
    by_subject = {}
    by_url = {}                                  # 段階35: ページごとの新しい記録・重複の数(窓口の「読み直しました」の根拠)
    for i, rec in enumerate(batch):
        errs = validate(rec, policy) if isinstance(rec, dict) else ["記録は JSON のオブジェクト"]
        if errs:
            rejected.append({"index": i, "errors": errs})
            continue
        by_subject.setdefault(rec["subject"], []).append(make_record(rec, policy, read_at))
    for subject, rows in by_subject.items():
        have = {dup_key_text(r) for r in read_records(subject, env, policy)}
        conf = read_confirmed(subject, env, policy)
        conf_changed = False
        p = log_path(subject, env, policy)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="") as f:
            for r in rows:
                if not r.get("state_date"):        # 重複の判定は、読むときと同じく原文の「10/25現在」も状態の日付として扱う(記録の行には入れない)
                    k = dup_key_text({**r, "state_date_from_text": state_date_from_text(r.get("state"), r["read_at"])})
                else:
                    k = dup_key_text(r)
                u = by_url.setdefault(r["url"], {"url": r["url"], "publisher": r.get("publisher"), "source_class": r["source_class"],
                                                  "written": 0, "duplicates": 0})
                if k in have:
                    dup += 1
                    u["duplicates"] += 1
                    conf.setdefault(k, {}).update(last_confirmed_at=r["read_at"], url=r["url"])   # 段階37: 新しい記録にせず、最後に確かめた日時だけ更新する
                    conf_changed = True
                    continue
                have.add(k)
                u["written"] += 1
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                written.append(r)
        if conf_changed:
            confirmed_path(subject, env, policy).write_text(json.dumps(conf, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"written": len(written), "duplicates": dup, "rejected": rejected, "by_url": list(by_url.values()), "records": written}


# ---- 候補(名所の一覧 + 既存の名所カタログ) ----

def event_derived(w, events, policy=None):
    """例年の時期として置かれた期間が、行事の期間を写したものか(段階35)。
    同じ月日の行事がある、または注記に「行事の期間」を表す語(policy の typical.event_note_words)がある → True。"""
    words = ((policy or {}).get("typical") or {}).get("event_note_words") or ["期間", "フェスタ", "フェスティバル", "まつり", "祭", "開放"]
    for ev in events or []:
        if ev.get("start") and ev.get("end") and str(ev["start"])[5:] == w.get("start") and str(ev["end"])[5:] == w.get("end"):
            return True
    return any(x in (w.get("note") or "") for x in words)


def _typical_from_catalog(e, policy=None):
    out = []
    tw = e.get("typical_window")
    if tw:
        out.append({"text": tw.get("note") or f"{int(tw['start'][:2])}/{int(tw['start'][3:])}〜{int(tw['end'][:2])}/{int(tw['end'][3:])}",
                    "start": tw["start"], "end": tw["end"], "url": tw.get("source_url"), "publisher": urlparse(tw.get("source_url") or "").hostname,
                    "year": None, "source_class": "official"})
    for w in e.get("flower_windows") or []:
        out.append({"text": f"{int(w['start'][:2])}/{int(w['start'][3:])}〜{int(w['end'][:2])}/{int(w['end'][3:])}", "kind": w["kind"],
                    "start": w["start"], "end": w["end"], "url": w["source_url"], "publisher": urlparse(w["source_url"]).hostname,
                    "year": w.get("source_year"), "source_class": "secondary" if (w.get("source_class") == "secondary" or w.get("unapproved_host")) else "official",
                    "event_derived": event_derived(w, e.get("events"), policy)})
    return out


def _events_from_catalog(e):
    return [{"name": v["name"], "kind": v.get("kind"), "start": v["start"], "end": v["end"], "url": v["source_url"],
             "publisher": urlparse(v["source_url"]).hostname,
             "source_class": "secondary" if (v.get("source_class") == "secondary" or v.get("unapproved_host")) else "official"}
            for v in e.get("events") or []]


def _from_catalog(e, subject, policy=None):
    t = e.get("tags") or {}
    return {"id": e["id"], "subject": subject, "name": e["name"], "prefecture": t.get("prefecture"), "city": t.get("city"),
            "area": t.get("area"), "point": e.get("point"), "elevation_m": (e.get("point") or {}).get("elevation_m"),
            "typical": _typical_from_catalog(e, policy), "events": _events_from_catalog(e),
            "pages": [{"url": s["url"], "publisher": s.get("title") or urlparse(s["url"]).hostname, "source_class": "official"} for s in e.get("sources") or []],
            "flower_kinds": t.get("flower_kinds") or [], "from_catalog": True}


def _from_spot(s, policy, catalog_by_id):
    typ = []
    for t in s.get("typical") or []:
        w = parse_typical(t["text"], policy)
        x = {**t, "start": w[0] if w else None, "end": w[1] if w else None}
        x["event_derived"] = bool(t.get("event_derived")) or (bool(w) and event_derived(x, s.get("events"), {"typical": {"event_note_words": []}}))
        typ.append(x)
    c = {"id": s["id"], "subject": s["subject"], "name": s["name"], "aliases": s.get("aliases") or [], "prefecture": s.get("prefecture"),
         "city": s.get("city"), "area": s.get("area"), "point": None, "elevation_m": s.get("elevation_m"), "elevation_note": s.get("elevation_note"),
         "typical": typ, "events": list(s.get("events") or []), "pages": list(s.get("pages") or []), "search": s.get("search"),
         "hours": s.get("hours"), "closed": s.get("closed"), "birds_note": s.get("birds_note"), "flower_kinds": s.get("flower_kinds") or [],
         "season_birds": list(s.get("season_birds") or []), "bird_area": s.get("bird_area")}
    pa = park_area(s, policy)                    # 段階38: 探鳥地ごとの範囲があれば、その範囲で集計する(半径10kmの区域をやめる)
    if pa:
        c["bird_area"] = pa["id"]
        c["bird_range"] = {k: pa[k] for k in ("radius_km", "location_precision")}
        c["bird_area_fallback"] = s.get("bird_area")
    ref = catalog_by_id.get(s.get("catalog_ref"))
    if ref:
        cat = _from_catalog(ref, s["subject"], policy)
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
    out += [_from_catalog(e, subject, policy) for e in cat_entries if e["id"] not in used]
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

def state_date_of(rec):
    """状態の日付(欄の値。なければ原文に書かれた日付)。どちらもなければ None。"""
    return rec.get("state_date") or rec.get("state_date_from_text")


def basis_date(rec):
    """新しさの基準の日(段階35): 状態の日付。状態の日付がない記録だけ、読んだ日。"""
    sd = state_date_of(rec)
    if sd:
        return date.fromisoformat(sd)
    return date.fromisoformat(max(rec["read_at"], rec.get("last_confirmed_at") or "")[:10])   # 段階37: 読み直して同じ事実なら、最後に確かめた日


def freshness(rec, today, subject, policy):
    if rec is None:
        return {"class": "none", "label": policy["freshness"]["labels"]["none"], "age_days": None}
    f = policy["freshness"]
    age = (today - basis_date(rec)).days
    cls = "fresh" if age <= f["fresh_days"][subject] else "stale" if age <= f["stale_days"] else "very_stale"
    return {"class": cls, "label": f["labels"][cls], "age_days": age, "basis": "state_date" if state_date_of(rec) else "read_at",
            "basis_date": basis_date(rec).isoformat()}


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
    out = {"schema": "ikimono-observations-plan/1", "subject": subject, "region": reg["name"], "dates": [d.isoformat() for d in dates],
           "now": now.isoformat(), "needs_fetch": bool(items), "summary_pages": summary, "items": items, "fresh": fresh,
           "limits": policy["fetch_limits"]}
    if subject == "birds":                          # 段階36(決定2): iNaturalist の集計が古い・対象の日が期間外の区域(取り直しは inat-refresh)
        out["inat_refresh"] = inat_refresh_plan(cands, dates[0], now, origin=origin, env=env, policy=policy, cat_pol=cat_pol)
    return out


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


def _md(iso):
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.month}/{d.day}"


# ---- 野鳥: この時期に見られる鳥(段階35) ----

def regional_seasonality(prefecture, d, now, env=None, profile=None, cfg=None):
    """段階38: 地域全体の季節らしさ(キャッシュにあるものだけ。通信しない)。→ {name, fetched_at, by_sci: {学名: {lift, count, seasonal}}} か None。"""
    from . import profiles as P
    from .config import load_config
    from .fetch import inaturalist
    from .fetch.cache import Cache
    from .methods import observation_frequency as obsfreq
    rid = region_area_id(prefecture)
    if not rid:
        return None
    profile = profile or P.load_profiles()["birds"]
    cfg = cfg or load_config()
    area = _rounded(_area_by_id(rid), profile)
    cache = Cache(data_path(cfg["cache"]["dir"], env))
    found = _inat_aggregation(area, d, now, cache=cache, profile=profile, cfg=cfg, env=env)
    base = _baseline_entry(area, d, now, cache=cache, profile=profile, cfg=cfg) if found else None
    if not found or base is None:
        return None
    pb = load_policy()["park_birds"]
    win_rows = inaturalist.parse_species_counts(json.loads(found["entries"][0]["body"]))[0]
    con_rows = inaturalist.parse_species_counts(json.loads(found["entries"][1]["body"]))[0] if len(found["entries"]) > 1 else None
    yrows = inaturalist.parse_species_counts(json.loads(base["body"]))[0]
    ranked = obsfreq.seasonal_rank([win_rows], [yrows], lift_min=_v(pb["seasonality"]["lift_min"]), min_count=_v(pb["regional_min_window_count"]))
    cmin = _v(pb["contrast"]["contrast_min"])
    con = obsfreq.seasonal_rank([win_rows], [con_rows], lift_min=cmin, min_count=_v(pb["regional_min_window_count"])) if con_rows is not None else []
    cby = {s["name"]: s for s in con}
    by = {}
    for s in ranked:
        c = cby.get(s["name"]) or {}
        cl = c.get("lift")                          # None = 反対の季節に記録がない
        seasonal = s["seasonal"] and (con_rows is None or cl is None or cl >= cmin)
        by[s["name"]] = {"lift": s["lift"], "contrast_lift": cl, "count": s["count"], "seasonal": seasonal}
    return {"name": prefecture, "area": area["name"], "fetched_at": min([e["fetched_at"] for e in found["entries"]] + [base["fetched_at"]]),
            "by_sci": by}


def inat_season(area_id, d, now, env=None, sites_doc=None, profile=None, cfg=None, prefecture=None):
    """iNaturalist の過去の記録(キャッシュにあるものだけ。通信しない。古くても使い、取得時刻を添える)から、
    対象の日の前後の相対頻度の上位の種。→ {area, radius_km, years, window_weeks, total, species, fetched_at, url} か None。"""
    from . import profiles as P
    from .config import load_config
    from .engine import round_coord
    from .fetch import birds_live
    from .fetch.cache import Cache
    from .methods import observation_frequency as obsfreq
    from .paths import data_path as dp
    from .profiles import param
    if not area_id:
        return None
    area = _area_by_id(area_id, sites_doc)
    if not area or area.get("lat") is None:
        return None
    profile = profile or P.load_profiles()["birds"]
    cfg = cfg or load_config()
    prec = area.get("location_precision") or profile["care"]["location_precision"]
    area = dict(area, lat=round_coord(area["lat"], prec), lon=round_coord(area["lon"], prec))
    cache = Cache(dp(cfg["cache"]["dir"], env))
    found = _inat_aggregation(area, d, now, cache=cache, profile=profile, cfg=cfg, env=env)
    if found is None:
        return None
    from .fetch import inaturalist
    rows = [inaturalist.parse_species_counts(json.loads(e["body"]))[0] for e in found["entries"]]
    fetched = [e["fetched_at"] for e in found["entries"]]
    url = found["entries"][0]["url"]
    park = area.get("scope") == "park"
    pbp = load_policy()["park_birds"]
    res = obsfreq.relative_frequencies(rows, min_total=_v(pbp["min_total"]) if park else param(profile, "min_total_observations"),
                                       top_n=param(profile, "top_species"))
    if not res["enough"]:
        return {"area": area["name"], "enough": False, "total": res["total"], "fetched_at": min(fetched), "url": url, "center": found["center"], "target": d.isoformat()}
    years = param(profile, "history_years")
    out = {"area": area["name"], "radius_km": area["radius_km"], "years": years, "window_weeks": param(profile, "window_weeks"),
           "center": found["center"], "target": d.isoformat(), "total": res["total"], "enough": True, "fetched_at": min(fetched), "url": url, "publisher": "iNaturalist",
           "site_url": "https://www.inaturalist.org/",       # 段階35: 答えの出典に並べる、人が開くページ(問い合わせの URL は長く、API のため)
           "scope": area.get("scope") or "area",
           **({"months": birds_live.park_queries(area, date.fromisoformat(found["center"]), profile, cfg["live"]["inaturalist"]["per_page"],
                                                 _park_half_days())[2], "all_years": True} if park else {}),
           "species": [{"name": sp["common_name"] or sp["name"], "scientific_name": sp["name"], "count": sp["count"], "taxon_id": sp.get("taxon_id"),
                        "relative_frequency": round(sp["relative_frequency"], 3)} for sp in res["species"]]}
    # 段階38: 一年の記録(分母)がキャッシュにあれば、季節らしさの順の一覧を足す(通信しない)
    reg = regional_seasonality(prefecture, d, now, env=env, profile=profile, cfg=cfg) if prefecture else None
    if reg:                                       # 段階38(採点の後): 季節らしさは地域全体の記録で。公園の記録は「どの鳥か」だけ
        from .methods.observation_frequency import merge_counts
        merged, _t = merge_counts(rows)
        items = []
        for sci, m in merged.items():
            r = reg["by_sci"].get(sci) or {}
            cl = r.get("contrast_lift")
            items.append({"name": m["common_name"] or sci, "scientific_name": sci, "taxon_id": m["taxon_id"], "count": m["count"], "year_count": None,
                          "lift": round(r["lift"], 2) if r.get("lift") is not None else None, "seasonal": bool(r.get("seasonal")), "basis": "region",
                          "contrast_lift": round(cl, 2) if cl is not None else None})
        big = float("inf")
        seas = sorted([x for x in items if x["seasonal"]], key=lambda x: (-(x["contrast_lift"] if x["contrast_lift"] is not None else big), -x["lift"],
                                                                            -x["count"], x["scientific_name"]))
        rest = sorted([x for x in items if not x["seasonal"]], key=lambda x: (-x["count"], x["scientific_name"]))
        out["seasonal"] = seas + rest
        out["region"] = {"name": reg["name"], "area": reg["area"], "fetched_at": reg["fetched_at"]}
        return out
    base = _baseline_entry(area, date.fromisoformat(found["center"]), now, cache=cache, profile=profile, cfg=cfg)
    if base is not None:
        pb = load_policy()["park_birds"]["seasonality"]
        yrows = inaturalist.parse_species_counts(json.loads(base["body"]))[0]
        ranked = obsfreq.seasonal_rank(rows, [yrows], lift_min=_v(pb["lift_min"]), min_count=_v(pb["min_window_count"]))
        out["baseline_fetched_at"] = base["fetched_at"]
        out["seasonal"] = [{"name": s["common_name"] or s["name"], "scientific_name": s["name"], "taxon_id": s["taxon_id"], "count": s["count"],
                            "year_count": s["year_count"], "lift": round(s["lift"], 2) if s["lift"] is not None else None, "seasonal": s["seasonal"]}
                           for s in ranked]
    return out


def _baseline_entry(area, center, now, *, cache, profile, cfg):
    """一年の記録(分母)のキャッシュ(古くても使う)。なければ None。area は丸めた座標。"""
    from .fetch import birds_live
    q = _baseline_q(area, center, profile, cfg)
    e, _st = cache.get(q["url"], q["params"], now=now, ttl_s=0, allow_expired=True)
    return e


def _baseline_q(area, center, profile, cfg):
    from .fetch import birds_live
    if area.get("scope") == "park":
        return birds_live.park_queries(area, center, profile, cfg["live"]["inaturalist"]["per_page"], _park_half_days())[1]
    return birds_live.baseline_query(area, center, profile, cfg["live"]["inaturalist"]["per_page"])


def season_birds(c, rows, dates, policy):
    """この時期に見られる鳥の材料(出典と年つき): 名所の一覧に書き写した紹介(season_birds)と、前の年の同じ時期の観察の記録。"""
    d = dates[0]
    w = _v(policy["birds"]["season_window_days"])
    out = [dict(x, kind="page") for x in c.get("season_birds") or []]
    for r in rows:
        sd = state_date_of(r)
        if not sd:
            continue
        x = date.fromisoformat(sd)
        if x.year >= d.year:
            continue
        try:
            same = date(d.year, x.month, x.day)
        except ValueError:
            continue
        if abs((same - d).days) <= w:
            out.append({"kind": "past_record", "text": r["state"], "date": sd, "year": x.year, "url": r["url"],
                        "publisher": r.get("publisher"), "source_class": r["source_class"]})
    return out


def season_line(f, policy):
    """この時期に見られる鳥の 1 文(決定論)。材料がなければ、そう書く。"""
    lab = policy["birds"]["season_labels"]
    inat = f.get("inat")
    if inat and inat.get("enough") and inat.get("months"):          # 段階38: 公園ごとの範囲
        top = _v(policy["park_birds"]["sea_top_n"])
        months = policy["park_birds"]["months_label"].format(months="・".join(str(m) for m in inat["months"]))
        seas = [x["name"] for x in inat.get("seasonal") or [] if x["seasonal"]][:top]
        if seas:
            return lab["inat_park"].format(months=months, area=inat["area"], radius=inat["radius_km"], fetched=_md(inat["fetched_at"]), names="・".join(seas),
                                           region=(inat.get("region") or {}).get("name") or inat["area"])
        return lab["inat_park_plain"].format(months=months, area=inat["area"], radius=inat["radius_km"], fetched=_md(inat["fetched_at"]),
                                             names="・".join(sp["name"] for sp in inat["species"]))
    if inat and inat.get("enough") and inat.get("seasonal") and any(x["seasonal"] for x in inat["seasonal"]):    # 段階38: 季節らしさの順
        top = _v(policy["park_birds"]["sea_top_n"])
        names = "・".join([x["name"] for x in inat["seasonal"] if x["seasonal"]][:top])
        return lab["inat_seasonal"].format(years=inat["years"], weeks=inat["window_weeks"], radius=inat["radius_km"], area=inat["area"],
                                           names=names, fetched=_md(inat["fetched_at"]), center=_md(inat["center"]))
    if inat and inat.get("enough"):
        names = "・".join(sp["name"] for sp in inat["species"])
        key = "inat" if not inat.get("center") or inat["center"] == inat.get("target") else "inat_other_center"     # 段階36: 前回の集計の中心の日が対象の日と違うとき
        return lab[key].format(years=inat["years"], weeks=inat["window_weeks"], radius=inat["radius_km"], area=inat["area"],
                               names=names, fetched=_md(inat["fetched_at"]), center=_md(inat["center"]) if inat.get("center") else "")
    pr = [x for x in f.get("season_birds") or [] if x["kind"] == "past_record"]
    if pr:
        x = sorted(pr, key=lambda x: x["date"], reverse=True)[0]
        return lab["past_record"].format(year=x["year"], md=_md(x["date"]), publisher=x.get("publisher") or "", text=x["text"])
    pg = [x for x in f.get("season_birds") or [] if x["kind"] == "page"]
    if pg:
        x = pg[0]
        return lab["page"].format(publisher=x.get("publisher") or "", text=x["text"])
    return lab["unknown"]


# ---- 野鳥: iNaturalist の集計の取り直し(段階36。利用者の決定 2026-11-01) ----

def _inat_policy(policy=None):
    return (policy or load_policy())["inat_refresh"]


def inat_index_path(env=None, policy=None):
    return data_path(_inat_policy(policy)["index_file"], env)


def read_inat_index(env=None, policy=None):
    """取り直した集計の索引(区域 ID → [{center, window_days, fetched_at, requests}])。無ければ {}。"""
    p = inat_index_path(env, policy)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("areas") or {}
    except ValueError:
        return {}


def _write_inat_index(idx, env=None, policy=None):
    p = inat_index_path(env, policy)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("." + p.name + ".tmp")
    tmp.write_text(json.dumps({"schema": "ikimono-inat-index/1", "areas": idx}, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(p)


PARK_AREA_PREFIX = "park:"
REGION_AREA_PREFIX = "region:"


def region_area_id(prefecture, policy=None):
    ra = ((policy or load_policy())["park_birds"].get("regional_areas") or {}).get(prefecture)
    return ra["id"] if ra else None
_PARK_AREAS = {}                                 # 段階38: 候補を作ったときの探鳥地ごとの範囲(id → 区域)。名所の一覧を差し替えたテストでも引けるように


def park_area(s, policy=None):
    """名所の bird_range(中心と半径)→ 区域 {id, name, lat, lon, radius_km, location_precision}。なければ None。
    座標は方針の location_precision に丸める(絶対ルール7)。半径の既定は方針の値。"""
    from .engine import round_coord
    br = s.get("bird_range") or {}
    if br.get("lat") is None or br.get("lon") is None:
        return None
    rp = ((policy or load_policy()).get("park_birds") or {}).get("range") or {}
    prec = rp.get("location_precision")
    a = {"id": PARK_AREA_PREFIX + s["id"], "name": s["name"], "lat": round_coord(float(br["lat"]), prec), "lon": round_coord(float(br["lon"]), prec),
         "radius_km": br.get("radius_km") if br.get("radius_km") is not None else _v(rp["default_radius_km"]),
         "location_precision": prec, "status": "approved", "active": False, "scope": "park"}
    _PARK_AREAS[a["id"]] = a
    return a


def _area_by_id(area_id, sites_doc=None):
    from . import profiles as P
    if area_id and area_id.startswith(REGION_AREA_PREFIX):            # 段階38: 季節らしさを決める地域全体の区域
        ra = next((a for a in (load_policy()["park_birds"].get("regional_areas") or {}).values() if a["id"] == area_id), None)
        return dict(ra, scope="park", status="approved", active=False) if ra else None
    if area_id and area_id.startswith(PARK_AREA_PREFIX):
        if area_id not in _PARK_AREAS:
            for s in load_spots().get("spots") or []:
                if s.get("subject") == "birds":
                    park_area(s)
        return _PARK_AREAS.get(area_id)
    sites_doc = sites_doc or P.load_sites()[1]
    return next((a for a in (sites_doc.get("bird_areas") or []) + load_obs_bird_areas() if a["id"] == area_id), None)


def _rounded(area, profile):
    from .engine import round_coord
    prec = area.get("location_precision") or profile["care"]["location_precision"]
    return dict(area, lat=round_coord(area["lat"], prec), lon=round_coord(area["lon"], prec))


def contrast_months(months, policy=None):
    c = (policy or load_policy())["park_birds"]["contrast"]
    return list(c["winter"]) if set(months) & set(c["summer"]) else list(c["summer"])


def _park_half_days(policy=None):
    return _v((policy or load_policy())["park_birds"]["window"]["half_days"])


def _inat_queries(area, d, profile, cfg):
    from .fetch import birds_live
    if area.get("scope") == "park":              # 段階38: 公園ごとの範囲は、対象の日の前後にかかる月の、すべての年の記録(1 リクエスト)
        win, _y, months = birds_live.park_queries(area, d, profile, cfg["live"]["inaturalist"]["per_page"], _park_half_days())
        if area["id"].startswith(REGION_AREA_PREFIX):  # 地域全体は、反対の季節の月の記録も(季節らしさの比べ)
            return [win, birds_live.contrast_query(area, profile, cfg["live"]["inaturalist"]["per_page"], contrast_months(months))]
        return [win]
    return [q for _d, _k, q in birds_live.bird_queries(area, [d], profile, cfg["live"]["inaturalist"]["per_page"])]


def _inat_aggregation(area, d, now, *, cache, profile, cfg, env=None):
    """対象の日 d に使える集計(キャッシュにあるものだけ。通信しない)。→ {center, entries} か None。
    ①対象の日そのものの問い合わせ ②索引にある集計のうち、その期間(中心の日の前後 window_weeks 週)が d を含むもの(取得の新しい順)。"""
    from .profiles import param

    def entries_for(center):
        out = []
        for q in _inat_queries(area, center, profile, cfg):
            e, _st = cache.get(q["url"], q["params"], now=now, ttl_s=0, allow_expired=True)
            if e is None:
                return None
            out.append(e)
        return out
    ex = entries_for(d)
    if ex:
        return {"center": d.isoformat(), "entries": ex}
    span = param(profile, "window_weeks") * 7
    for it in sorted(read_inat_index(env).get(area["id"]) or [], key=lambda x: x["fetched_at"], reverse=True):
        c = date.fromisoformat(it["center"])
        if abs((d - c).days) <= span:
            ex = entries_for(c)
            if ex:
                return {"center": it["center"], "entries": ex}
    for k in range(1, span + 1):                 # 段階37: 索引ができる前(段階36より前)に取った集計も、期間(前後 window_weeks 週)が d を含めば使う(近い日から)
        for c in (d - timedelta(days=k), d + timedelta(days=k)):
            ex = entries_for(c)
            if ex:
                return {"center": c.isoformat(), "entries": ex}
    return None


def inat_status(area_id, d, now, *, env=None, policy=None, sites_doc=None, profile=None, cfg=None):
    """区域の集計の状態(通信しない)。state: fresh / stale(取得が max_age_days より古い)/
    out_of_period(前回の集計の期間から対象の日が外れた)/ none(対象の日に使える集計がない)。"""
    from . import profiles as P
    from .config import load_config
    from .fetch.cache import Cache
    policy = policy or load_policy()
    area = _area_by_id(area_id, sites_doc)
    if not area or area.get("lat") is None:
        return None
    profile = profile or P.load_profiles()["birds"]
    cfg = cfg or load_config()
    area = _rounded(area, profile)
    cache = Cache(data_path(cfg["cache"]["dir"], env))
    found = _inat_aggregation(area, d, now, cache=cache, profile=profile, cfg=cfg, env=env)
    out = {"area": area_id, "name": area["name"], "requests": len(_inat_queries(area, d, profile, cfg)),
           "center": None, "fetched_at": None, "age_days": None}
    if area.get("scope") == "park":              # 段階38: 公園ごとの範囲は、一年の記録(分母)も要る(古ければ 1 リクエスト足す)
        out["baseline_needed"] = _baseline_needed(area, d, now, cache=cache, profile=profile, cfg=cfg, policy=policy)
        out["requests"] += 1 if out["baseline_needed"] else 0
    if found is None:
        out["state"] = "out_of_period" if read_inat_index(env, policy).get(area_id) else "none"
        return out
    oldest = min(datetime.fromisoformat(e["fetched_at"]) for e in found["entries"])
    age = (now - oldest).total_seconds() / 86400
    out.update(center=found["center"], fetched_at=oldest.isoformat(timespec="seconds"), age_days=round(age, 2))
    out["state"] = "stale" if age > _v(_inat_policy(policy)["max_age_days"]) else "fresh"
    if out["state"] == "fresh" and out.get("baseline_needed"):
        out["state"] = "stale"                   # 窓は新しいが、一年の記録(分母)がない・古い
        out["requests"] = 1
        out["baseline_only"] = True
    return out


def _baseline_needed(area, d, now, *, cache, profile, cfg, policy=None):
    e = _baseline_entry(area, d, now, cache=cache, profile=profile, cfg=cfg)
    if e is None:
        return True
    age = (now - datetime.fromisoformat(e["fetched_at"])).total_seconds() / 86400
    return age > _v((policy or load_policy())["park_birds"]["baseline_max_age_days"])


def inat_refresh_plan(cands, d, now, *, origin=None, env=None, policy=None, cat_pol=None):
    """候補の名所の区域のうち、取り直す区域(1 回の質問の上限の中で、取る順)。通信しない。
    順: 対象の日に使える集計がない区域 → 古い区域。同じなら出発地から近い名所の区域。上限に収まらない区域は deferred(古い集計を日付つきで使う)。"""
    policy = policy or load_policy()
    cat_pol = cat_pol or catalog_mod.load_policy()
    origin = origin or cat_pol["range_limit"]["default_origin"]
    limit = _v(_inat_policy(policy)["max_requests_per_question"])
    near = {}
    for c in cands:
        a = c.get("bird_area")
        if a:
            dk = _distance(c, origin, cat_pol)
            near[a] = min(near.get(a, float("inf")), dk if dk is not None else float("inf"))
            rid = region_area_id(c.get("prefecture"), policy) if a.startswith(PARK_AREA_PREFIX) else None
            if rid:
                near[rid] = -1.0                          # 段階38: 季節らしさを決める地域全体の区域を先に
    sts = [x for x in (inat_status(a, d, now, env=env, policy=policy) for a in sorted(near)) if x]
    rank = {"none": 0, "out_of_period": 0, "stale": 1}
    todo = sorted([x for x in sts if x["state"] != "fresh"], key=lambda x: (not x["area"].startswith(REGION_AREA_PREFIX), rank[x["state"]], near[x["area"]], x["area"]))
    used, areas, deferred = 0, [], []
    for x in todo:
        if used + x["requests"] <= limit:
            used += x["requests"]
            areas.append(x)
        else:
            deferred.append(x)
    return {"needed": bool(areas), "date": d.isoformat(), "max_requests": limit, "planned_requests": used,
            "areas": areas, "deferred": deferred, "fresh": [x for x in sts if x["state"] == "fresh"]}


def inat_refresh(area_ids, d, now, *, max_requests, env=None, policy=None, http_get=None, sleep=None, clock=None, budget=None):
    """区域の集計を iNaturalist から取り直す(実通信。計測フックの下で。--max-requests 必須・1 回の質問の上限を超えない)。
    上限に収まらない区域は取らない(古い集計を日付つきで使う)。取れた集計を索引に書く。通信の失敗は記録して残りを止める。
    → {requests, max_requests, fetched, deferred, errors}"""
    import time
    from . import profiles as P
    from .config import load_config
    from .fetch import ParseError, birds_live
    from .fetch.cache import Cache
    from .fetch.live import LiveError
    from .profiles import param
    policy = policy or load_policy()
    if max_requests is None or max_requests < 1:
        raise ValueError("--max-requests (1 以上)が必要")
    max_requests = min(max_requests, _v(_inat_policy(policy)["max_requests_per_question"]))
    profile, cfg = P.load_profiles()["birds"], load_config()
    cache = Cache(data_path(cfg["cache"]["dir"], env))
    unparsed = data_path(cfg["cache"]["unparsed_dir"], env)
    sleep = sleep or time.sleep
    idx = read_inat_index(env, policy)
    out = {"requests": 0, "max_requests": max_requests, "fetched": [], "deferred": [], "errors": []}
    if budget is not None:                                             # 段階38: 単体の上限(上限・間隔・許可ホスト・記録)で包む
        http_get = budget(http_get or (lambda u: birds_live.default_http_get(u, user_agent=cfg["live"]["user_agent"], timeout=cfg["live"]["timeout_s"])))
    for aid in area_ids:
        area = _area_by_id(aid)
        if not area or area.get("lat") is None:
            out["errors"].append({"area": aid, "error": "unknown_area"})
            continue
        area = _rounded(area, profile)
        qs = _inat_queries(area, d, profile, cfg)
        need_base = area.get("scope") == "park" and _baseline_needed(area, d, now, cache=cache, profile=profile, cfg=cfg, policy=policy)
        have = all(cache.get(q["url"], q["params"], now=now, ttl_s=_v(_inat_policy(policy)["max_age_days"]) * 86400)[0] for q in qs)
        n_need = (0 if have else len(qs)) + (1 if need_base else 0)
        left = max_requests - out["requests"]
        if n_need > left:
            out["deferred"].append({"area": aid, "requests": n_need, "reason": "max_requests"})
            continue
        if out["requests"] > 0 and n_need:
            sleep(cfg["live"]["min_interval_s"])                      # 区域の間でも間隔を空ける
        try:
            if have:
                rep = {"requests": 0, "cache_hits": len(qs), "warnings": []}
            elif area.get("scope") == "park":            # 段階38: 公園ごとの範囲の問い合わせ(1 リクエスト)
                for q in qs:
                    birds_live.fetch_baseline(area, d, profile, now, cache=cache, cfg=cfg, unparsed_dir=unparsed, clock=clock, q=q,
                                              http_get=http_get or (lambda u: birds_live.default_http_get(u, user_agent=cfg["live"]["user_agent"], timeout=cfg["live"]["timeout_s"])))
                rep = {"requests": len(qs), "cache_hits": 0, "warnings": []}
            else:
                _inputs, rep = birds_live.fetch_bird_counts(area, [d], profile, now, cache=cache, cfg=cfg, http_get=http_get, live=True,
                                                            max_requests=left, unparsed_dir=unparsed, sleep=sleep, clock=clock)
            if need_base:
                if rep["requests"]:
                    sleep(cfg["live"]["min_interval_s"])
                birds_live.fetch_baseline(area, d, profile, now, cache=cache, cfg=cfg, unparsed_dir=unparsed, clock=clock, q=_baseline_q(area, d, profile, cfg),
                                          http_get=http_get or (lambda u: birds_live.default_http_get(u, user_agent=cfg["live"]["user_agent"], timeout=cfg["live"]["timeout_s"])))
                rep = {**rep, "requests": rep["requests"] + 1}
        except (LiveError, ParseError) as e:
            out["errors"].append({"area": aid, "error": str(e)})
            break                                                      # 同じ通信先の残りは止める
        out["requests"] += rep["requests"]
        got = [cache.get(q["url"], q["params"], now=now, ttl_s=0, allow_expired=True)[0] for q in qs]
        if any(e is None for e in got):
            out["errors"].append({"area": aid, "error": "incomplete", "warnings": rep["warnings"]})
            continue
        ent = {"center": d.isoformat(), "window_days": param(profile, "window_weeks") * 7,
               "fetched_at": min(e["fetched_at"] for e in got), "requests": rep["requests"]}
        idx[aid] = [x for x in idx.get(aid) or [] if x["center"] != ent["center"]] + [ent]
        out["fetched"].append({"area": aid, "requests": rep["requests"], "cache_hits": rep["cache_hits"], "fetched_at": ent["fetched_at"]})
    if out["fetched"]:
        _write_inat_index(idx, env, policy)
    return out


# ---- 野鳥: 公園ごとに見られる鳥(段階38。指示書 3-1) ----

BIRD_TAXA_PATH = DATA_FILES_DIR / "guide" / "bird_taxa.yaml"


def known_bird_names(extra=()):
    """記録の原文から鳥の名前を拾うための和名の辞書: data/guide/bird_taxa.yaml の和名 + extra(その公園の集計の和名など)。"""
    names = set(x for x in extra if x)
    if BIRD_TAXA_PATH.exists():
        for r in (yaml.safe_load(BIRD_TAXA_PATH.read_text(encoding="utf-8")) or {}).get("taxa") or []:
            if r.get("name"):
                names.add(r["name"])
    return names


def bird_names_in(text, names, min_len=2):
    """原文に書かれた鳥の名前(辞書にあるものだけ。長い名前を先に。「アオサギ」の中の「サギ」は拾わない)。出てきた順。"""
    t = unicodedata.normalize("NFKC", text or "")
    hits = []
    for n in sorted({x for x in names if len(x) >= min_len}, key=lambda x: (-len(x), x)):
        i = t.find(n)
        while i >= 0:
            hits.append((i, n))
            t = t[:i] + "\uffff" * len(n) + t[i + len(n):]
            i = t.find(n)
    seen, out = set(), []
    for _i, n in sorted(hits):
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def park_birds(f, rows, dates, policy, taxa_names=None):
    """公園ごとの「見られる鳥」(決定論)。材料の順: ①最近の記録 ②この時期の記録(iNaturalist。季節らしさの順。一年中多い鳥は後ろ)
    ③前の年の同じ時期の記録 ④公園の紹介。→ (鳥の一覧, 範囲の注意)。鳥ごとに 和名・材料の種類・日付か集計の期間・出典・なぜ今か。"""
    pb = policy["park_birds"]
    why, kl = pb["why"], pb["kind_labels"]
    d = dates[0]
    inat = f.get("inat") or {}
    inat_names = [x["name"] for x in (inat.get("seasonal") or inat.get("species") or [])]
    names = known_bird_names(inat_names) if taxa_names is None else set(taxa_names) | set(inat_names)
    by_sci = {x["name"]: x for x in (inat.get("seasonal") or inat.get("species") or [])}
    minl = _v(pb["name_min_len"])
    recent_w = _v(pb["recent_days"])
    out, seen = [], set()

    def add(item):
        if item["name"] in seen:
            return
        seen.add(item["name"])
        x = by_sci.get(item["name"]) or {}
        item.setdefault("scientific_name", x.get("scientific_name"))
        item.setdefault("taxon_id", x.get("taxon_id"))
        if x.get("contrast_lift") is not None and item["kind"] == "season":
            item["contrast_lift"] = x["contrast_lift"]
        item["kind_label"] = kl[item["kind"]]
        out.append(item)
    dated = []
    for r in rows:
        sd = state_date_of(r)
        if not sd:
            continue
        dated.append((sd, r))
    for sd, r in sorted(dated, key=lambda x: (x[0], x[1]["read_at"]), reverse=True):        # ① 最近の記録(新しい順)
        gap = (d - date.fromisoformat(sd)).days
        if not (0 <= gap <= recent_w):
            continue
        for n in list(r.get("species") or []) + bird_names_in(r.get("state"), names, minl):
            add({"name": n, "kind": "recent", "date": sd, "publisher": r.get("publisher") or r.get("host"), "url": r["url"],
                 "source_class": r["source_class"], "why": why["recent"].format(md=_md(sd), publisher=r.get("publisher") or r.get("host") or "")})
    if inat.get("enough"):                                                                    # ② この時期の記録
        period = pb["inat_period_park"].format(months=pb["months_label"].format(months="・".join(str(m) for m in inat["months"]))) if inat.get("months") \
            else pb["inat_period"].format(center=_md(inat["center"]), weeks=inat["window_weeks"], years=inat["years"])
        base = {"kind": "season", "date": str(inat["fetched_at"])[:10], "period": period, "publisher": "iNaturalist", "url": inat.get("site_url"),
                "source_class": "secondary"}
        if inat.get("seasonal"):
            strong = _v(pb["seasonality"]["lift_strong"])
            for x in inat["seasonal"]:
                lmin = _v(pb["seasonality"]["lift_min"])
                if x.get("basis") == "region":
                    rn = inat["region"]["name"]
                    w = (why["region_strong"] if x["lift"] >= strong else why["region"]).format(region=rn) if x["seasonal"] else why["region_year_round"]
                elif x["seasonal"]:
                    w = why["seasonal_strong"] if x["lift"] >= strong else why["seasonal"]
                elif x["lift"] is not None and x["lift"] >= lmin:
                    w = why["window_only"]           # 割合は高いが記録が少ない(季節らしさを決めない)
                else:
                    w = why["year_round"]
                add({**base, "name": x["name"], "scientific_name": x["scientific_name"], "taxon_id": x["taxon_id"], "lift": x["lift"],
                     "count": x["count"], "seasonal": x["seasonal"], "why": w})
        else:
            for x in inat.get("species") or []:
                add({**base, "name": x["name"], "scientific_name": x["scientific_name"], "taxon_id": x.get("taxon_id"), "count": x["count"],
                     "seasonal": None, "why": why["window_only"]})
    for x in f.get("season_birds") or []:                                                     # ③ 前の年の同じ時期 ④ 公園の紹介
        if x["kind"] == "past_record":
            for n in bird_names_in(x["text"], names, minl):
                add({"name": n, "kind": "last_year", "date": x["date"], "publisher": x.get("publisher"), "url": x["url"],
                     "source_class": x["source_class"], "why": why["last_year"].format(year=x["year"], md=_md(x["date"]), publisher=x.get("publisher") or "")})
    for x in f.get("season_birds") or []:
        if x["kind"] == "page":
            for n in bird_names_in(x.get("text"), names, minl):
                add({"name": n, "kind": "page", "date": x.get("checked_on"), "publisher": x.get("publisher"), "url": x.get("url"),
                     "source_class": x.get("source_class") or "official", "why": why["page"].format(publisher=x.get("publisher") or "")})
    # 一年中多い鳥(季節らしさが低い)は後ろ。最近の記録は先頭のまま
    rank = {"recent": 0, "season": 1, "last_year": 2, "page": 3}
    out.sort(key=lambda x: (rank[x["kind"]], 0 if x["kind"] != "season" or x.get("seasonal") in (True, None) else 1))
    rec = [x for x in out if x["kind"] == "recent"][:_v(pb["max_recent"])]
    out = (rec + [x for x in out if x["kind"] != "recent"])[:_v(pb["max_species"])]
    warn = []
    top = _v(pb["sea_top_n"])
    if not (f.get("bird_range") or {}).get("coastal"):
        sea = [x["name"] for x in out[:top] if x["name"] in set(pb["sea_birds"])]
        if sea:
            warn.append({"spot": f["name"], "sea_birds": sea, "note": "内陸の名所の上位に海の鳥(範囲が広すぎる合図)"})
    return out, warn


def closed_on(c, dates):
    """休園日の原文を対象の日と照らす(段階35。closures)。→ [{date, closed, facility, text, line, url}]。原文がなければ []。"""
    cl = c.get("closed")
    if not cl or not cl.get("text"):
        return []
    out = []
    for d in dates:
        ev = closures.evaluate(cl["text"], d)
        if not ev.get("facility"):
            ev["facility"] = cl.get("facility") or c.get("name")
        ev["line"] = closures.line(ev, cl.get("open_note"))
        ev["url"] = cl.get("url")
        out.append(ev)
    return out


def last_year_records(rows, dates, policy):
    """前の年の同じ時期(前後 typical.last_year_window_days 日)の状態の記録。新しい年・近い日の順(段階36。決定1の代わりの材料)。"""
    d = dates[0]
    w = _v(policy["typical"]["last_year_window_days"])
    out = []
    for r in rows:
        sd = state_date_of(r)
        if not sd:
            continue
        x = date.fromisoformat(sd)
        if x.year >= d.year:
            continue
        try:
            same = date(d.year, x.month, x.day)
        except ValueError:
            continue
        if abs((same - d).days) <= w:
            out.append({"state": r["state"], "state_norm": r.get("state_norm"), "date": sd, "year": x.year, "url": r["url"],
                        "publisher": r.get("publisher") or r.get("host"), "source_class": r["source_class"], "_gap": abs((same - d).days)})
    out.sort(key=lambda x: (-x["year"], x["_gap"], x["date"]))
    for x in out:
        x.pop("_gap")
    return out


def typical_line(typ, c, dates, policy, last_year=None):
    """例年の時期の 1 文の材料(段階35)。例年の時期が分からないときは「分かりません」と明言し、
    代わりに今年の行事の期間か、前の年の同じ時期の記録を添える(段階36。決定1)。"""
    lab = policy["typical_labels"]
    if typ:
        return lab["known"].format(text=typ["text"])
    evs = [e for e in c.get("events") or [] if e.get("start") and e.get("end")]
    evs = sorted(evs, key=lambda e: (not any(date.fromisoformat(e["start"]) <= d <= date.fromisoformat(e["end"]) for d in dates), e["start"]))
    if evs:
        e = evs[0]
        return lab["unknown_with_event"].format(name=e["name"], start=_md(e["start"]), end=_md(e["end"]))
    if last_year:
        x = last_year[0]
        return lab["unknown_with_last_year"].format(year=x["year"], md=_md(x["date"]), publisher=x.get("publisher") or "", text=x["state"])
    return lab["unknown"]


def fact_for(c, rows, dates, today, subject, policy, origin, cat_pol):
    d = dates[0]
    cur = best_record(rows)
    fr = freshness(cur, today, subject, policy)
    rec_events = [{"name": r["event"]["name"], "start": r["event"].get("start"), "end": r["event"].get("end"), "url": r["url"],
                   "publisher": r.get("publisher"), "source_class": r["source_class"]} for r in rows if r.get("event")]
    rec_ev_md = {(str(e["start"])[5:], str(e["end"])[5:]) for e in rec_events if e.get("start") and e.get("end")}
    for t in c.get("typical") or []:                 # 段階35: 記録から読んだ今年の行事と同じ月日の「例年の時期」も、行事の期間とみなす
        if (t.get("start"), t.get("end")) in rec_ev_md:
            t["event_derived"] = True
    real_typ = [t for t in c.get("typical") or [] if not t.get("event_derived")]
    typ = next((t for t in real_typ if t.get("start")), None)
    not_typ = (policy.get("typical") or {}).get("record_not_typical_words") or []
    typ_row = next((r for r in sorted(rows, key=lambda r: r["read_at"], reverse=True)
                    if r.get("typical") and not any(w in r["typical"] for w in not_typ)), None)
    if typ is None and typ_row:
        w = parse_typical(typ_row["typical"], policy)
        if w:                                    # 段階35: 出所は、その「例年の見頃」を書いた記録の発行元(名所の最新の記録の発行元ではない)
            typ = {"text": typ_row["typical"], "start": w[0], "end": w[1], "publisher": typ_row.get("publisher") or typ_row.get("host"),
                   "url": typ_row["url"], "source_class": typ_row["source_class"]}
    rel = _relation(cur, typ, d, policy)
    evs = _event_hits(c, dates)
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
    elif evs and subject == "flowers" and st in (None, policy["unknown_state"], *start_states):
        tier = 2                                 # 段階35: 例年の時期が分からなくても、対象の日に行事がある花の名所
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
    out = {"id": c["id"], "name": c["name"], "city": c.get("city"), "prefecture": c.get("prefecture"), "area": c.get("area"),
            "elevation_m": c.get("elevation_m"), "elevation_note": c.get("elevation_note"),
            "current": current, "current_unknown": cur is None,
            "history": [{"state": r["state_norm"], "state_raw": r["state"], "state_date": r.get("state_date"), "publisher": r.get("publisher"),
                         "url": r["url"], "source_class": r["source_class"]} for r in sorted(rows, key=lambda r: (basis_date(r), r["read_at"]), reverse=True)[1:4]],
            "typical": [{k: t.get(k) for k in ("text", "kind", "start", "end", "publisher", "url", "year", "source_class")} for t in real_typ]
                       + ([] if not typ or typ in real_typ else [typ]),
            "event_periods_not_typical": [{k: t.get(k) for k in ("text", "kind", "start", "end", "publisher", "url", "year")}
                                          for t in c.get("typical") or [] if t.get("event_derived")],
            "typical_line": typical_line(typ, {"events": list(c.get("events") or []) + rec_events}, dates, policy,
                                         last_year=last_year_records(rows, dates, policy)) if subject != "birds" else None,
            # 段階36(決定1): 例年の時期が分からない候補の印と代わりの材料。候補からは外さない
            "typical_unknown": subject != "birds" and typ is None,
            "typical_alternatives": None if subject == "birds" or typ is not None else {
                "events": [{k: e.get(k) for k in ("name", "start", "end", "url", "publisher", "source_class")}
                           for e in list(c.get("events") or []) + rec_events if e.get("start") and e.get("end")],
                "last_year": last_year_records(rows, dates, policy),
                "event_periods_not_typical": [{k: t.get(k) for k in ("text", "start", "end", "publisher", "url", "year")}
                                              for t in c.get("typical") or [] if t.get("event_derived")]},
            "typical_from_records": [{"text": r["typical"], "publisher": r.get("publisher"), "url": r["url"], "source_class": r["source_class"],
                                      "read_at": r["read_at"]} for r in rows if r.get("typical")],
            "events": evs, "relation": rel, "relation_label": policy["relation_labels"][rel],
            "distance_km": dist, "reasons": reasons, "tier": tier, "evidence": ev_rank, "reference_count": len(pubs), "publishers": pubs,
            "avoid": avoid, "hours": c.get("hours"), "closed": c.get("closed"), "birds_note": c.get("birds_note"),
            "closed_on": closed_on(c, dates),
            "flower_kinds": c.get("flower_kinds") or [], "pages": c.get("pages") or [], "_order": order_map.get(st, -1) if st else -1}
    if subject == "birds":
        out["season_birds"] = season_birds(c, rows, dates, policy)
        out["bird_area"] = c.get("bird_area")
        out["bird_range"] = c.get("bird_range")
        out["_rows"] = rows
    return out


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
    range_warnings = []
    if subject == "birds":
        inat_cache = {}
        for f in all_f:
            a = f.get("bird_area")
            k = (a, f.get("prefecture"))
            if a and k not in inat_cache:
                inat_cache[k] = inat_season(a, dates[0], now, env, prefecture=f.get("prefecture"))
            f["inat"] = inat_cache.get(k) if a else None
            f["season_line"] = season_line(f, policy)
            f["season_unknown"] = f["season_line"] == policy["birds"]["season_labels"]["unknown"]      # 段階36(決定1): 野鳥の R4 の「分からない」の印
            if f["inat"] and f["inat"].get("enough"):
                f["reasons"].append("inat_season")
            for k in ("relation", "relation_label"):          # 野鳥には「例年の見頃」の関係を出さない(この時期に見られる鳥で書く)
                f[k] = None
            f["park_birds"], w = park_birds(f, f.get("_rows") or [], dates, policy)       # 段階38: 公園ごとに見られる鳥
            dated = sorted([r for r in f.get("_rows") or [] if state_date_of(r)], key=lambda r: (state_date_of(r), r["read_at"]), reverse=True)
            f["latest_dated"] = {"state_raw": dated[0]["state"], "state_date": state_date_of(dated[0]), "url": dated[0]["url"],
                                 "publisher": dated[0].get("publisher") or dated[0].get("host"), "source_class": dated[0]["source_class"],
                                 "recent": 0 <= (dates[0] - date.fromisoformat(state_date_of(dated[0]))).days <= _v(policy["park_birds"]["recent_days"])} if dated else None
            range_warnings.extend(w)
    if subject == "birds":                            # 段階38: 公園ごとの鳥の材料(最近の記録・この時期の記録)がある名所を先に(同じなら今の並び)
        rec_f.sort(key=lambda f: 0 if any(x["kind"] in ("recent", "season") for x in f.get("park_birds") or []) else 1)
    for f in all_f:
        f["reason_labels"] = [policy["reason_labels"][r] for r in f["reasons"]]
        if f["avoid"]:
            f["avoid_label"] = policy["avoid_reasons"][f["avoid"]]
        f.pop("_order", None)
        f.pop("_rows", None)
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
            "source_urls": srcs, **({"range_warnings": range_warnings} if subject == "birds" else {})}


def self_check(text, policy=None):
    policy = policy or load_policy()
    return [w for w in policy["forbidden_terms"] if w in text]


# ---- CLI ----

def _dates(a, now):
    if a.date:
        return [date.fromisoformat(x) for x in a.date]
    return S.next_weekend(now)


def _inat_refresh_cli(a, http_get=None, clock=None):
    import os
    from . import livegate
    if a.max_requests is None or a.max_requests < 1:
        print("--max-requests (1 以上)が必要です", file=sys.stderr)
        return 4
    budget = None
    if http_get is None:                                   # 偽の http_get を注入したテストは実通信にならない。本物の通信は常にゲートを通る
        if not livegate.live_allowed():
            print(livegate.refusal(), file=sys.stderr)
            return 4
        # 段階38(利用者の決定 2026-11-01): 計測フック(BIYORI_REQ_LOG)がなければ、自前の上限(netbudget)の下で取る
        from . import netbudget
        from .config import load_config
        budget = netbudget.Budget("inat_counts", load_config()["live"]["allowed_hosts_by_subject"]["birds"],
                                  min(a.max_requests, _v(_inat_policy()["max_requests_per_question"])),
                                  load_policy()["fetch_limits"]["same_host_interval_s"])
    now = S.parse_now(a.now)
    dates = _dates(a, now)
    pl = None
    if a.area:
        ids = a.area
    else:
        pl = plan("birds", region=a.region, dates=dates, now=now, origin=a.origin)["inat_refresh"]
        ids = [x["area"] for x in pl["areas"]]
    out = inat_refresh(ids, dates[0], now, max_requests=a.max_requests, http_get=http_get, clock=clock, budget=budget) if ids else \
        {"requests": 0, "max_requests": a.max_requests, "fetched": [], "deferred": [], "errors": []}
    if pl is not None:
        out["planned"] = pl
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 5 if out["errors"] else 0


def main(argv=None, http_get=None, clock=None):
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
    ir = sub.add_parser("inat-refresh", help="野鳥の区域の iNaturalist の集計を取り直す(段階36。実通信。BIYORI_ALLOW_LIVE=1・計測フック・--max-requests が必要)")
    ir.add_argument("--region")
    ir.add_argument("--date", action="append")
    ir.add_argument("--now", required=True)
    ir.add_argument("--origin")
    ir.add_argument("--max-requests", type=int, required=True)
    ir.add_argument("--area", action="append", help="区域 ID(省略時は refresh --plan の inat_refresh.areas の順)")
    a = ap.parse_args(argv)
    if a.cmd == "inat-refresh":
        return _inat_refresh_cli(a, http_get=http_get, clock=clock)
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
