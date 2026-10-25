"""ガイド型の質問(「どこで・いつごろ・どんな種類?」)の名所の蓄積(段階23。docs/stage23-decisions.md)。

現況型の質問(「今どうなっている?」)は、これまでどおり sources.py(公式の台帳・同じ日の記録)で答える。ここは使わない。
流れ: 集める(record-candidate・import-seed)→ まとめる(build。独立した出どころの数で段階を決める)→ 仮承認(規則)→ 見直し(review・reject)→ 答える(find)。

- 検索・取得はエージェント(スキルの手順)が行う。ここは、エージェントが渡した**事実の項目だけ**(名所・所在・種類・例年の時期・出どころの URL)を受け取り、
  形・長さ・出どころの区分を検査して記録する。ページの本文は受け取らない・保存しない。読んだ時刻はコードが時計から入れる(モデルが書いた時刻は使わない)。
- 書き込み先は IKIMONOBIYORI_DATA_DIR の下の guide/ だけ。リポジトリの data/guide/ は人(エージェント)が見直して置く写し(export の出力を写す)。
- 値(区分の表・段階の規則・上限)は data/guide/policy.yaml から読み、コードに持たない。
- 範囲(東京・横浜から 250 km)は、市区町村の代表点(Wikidata の座標。fetch/wikidata.py)で判定する。代表点がなければ「範囲は未確認」(推測で座標を作らない)。

  python -X utf8 -m ikimonobiyori.guide theme <言葉>
  python -X utf8 -m ikimonobiyori.guide record-candidate --batch items.json
  python -X utf8 -m ikimonobiyori.guide import-seed --file docs/seeds/stage23-seeds.md
  python -X utf8 -m ikimonobiyori.guide find --word 冬桜 [--date 2026-11-15] [--prefecture 埼玉県] [--region 富士山周辺]
  python -X utf8 -m ikimonobiyori.guide reject <id> --reason ...
"""
import argparse
import calendar
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from . import catalog as catalog_mod
from . import livegate
from .config import load_config
from .paths import DATA_FILES_DIR, data_path

GUIDE_DIR = DATA_FILES_DIR / "guide"
POLICY_PATH = GUIDE_DIR / "policy.yaml"
RECORDS_PATH = GUIDE_DIR / "records.jsonl"            # 見直して置いた候補の記録(事実だけ)。export の出力を写す
PLACES_PATH = GUIDE_DIR / "places.yaml"               # 市区町村の代表点(Wikidata)。export の出力を写す
REVIEWS_PATH = GUIDE_DIR / "reviews.yaml"             # ユーザーの見直し(外した・承認した)。ユーザーが確かめて置く
CATALOG_PATH = GUIDE_DIR / "catalog.yaml"             # build の結果(仮承認・承認した名所)。records と places から作り直せる(テストが一致を確かめる)
CANDIDATES_PATH = GUIDE_DIR / "candidates.yaml"       # build の結果(候補のまま・外したもの。理由つき)
SEASON_RE = re.compile(r"^\s*(\d{1,2})月(上旬|初旬|中旬|下旬|末|頃|ごろ)?\s*$")
THIRD_ALIASES = {"初旬": "上旬", "末": "下旬", "頃": None, "ごろ": None}
LEAP_YEAR = catalog_mod.LEAP_YEAR
ID_HEX = 10                                            # 名所の id の長さ(sha1 の先頭の 16 進の桁数。閾値ではない)


# ---- 読み込み・時計 ----

def load_policy(path=None):
    return yaml.safe_load(Path(path or POLICY_PATH).read_text(encoding="utf-8"))


def val(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def clock_now():
    """パソコンの時計(オフセットつき)。読んだ時刻・見直しの時刻はここからだけ入れる(段階23 フェーズ6。モデルが書いた時刻は使わない)。"""
    return datetime.now().astimezone().replace(microsecond=0)


def guide_dir(env=None):
    return data_path(load_policy()["record"]["dir"], env)


def _jsonl(path):
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _append_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


# ---- 出どころの区分と発行元 ----

def host_of(url):
    h = (urlsplit(url).hostname or "").lower()
    return h[len("www."):] if h.startswith("www.") else h


def _suffix_match(host, suffix):
    return host == suffix or host.endswith("." + suffix)


def registrable(host, policy):
    """公開接尾辞の 1 つ下まで(rurubu.jp と kids.rurubu.jp は rurubu.jp)。表にない接尾辞は最後の 2 つ。"""
    labels = host.split(".")
    best = max((s for s in policy["public_suffixes"] if _suffix_match(host, s)), key=len, default=None)
    n = (best.count(".") + 1) if best else 1
    return ".".join(labels[-(n + 1):])


def classify(url, policy):
    """URL → (区分 A〜D, 発行元)。ホストの表(後ろが一致する最長のもの)→ 公的なドメインの PDF は B → 表にないホストは default_class。
    発行元は表の publisher、なければ公開接尾辞の 1 つ下まで(1 つのホストに多くの個人がいる場所はパスの最初の部分まで)。"""
    host = host_of(url)
    row = max((r for r in policy["hosts"] if _suffix_match(host, r["suffix"])), key=lambda r: len(r["suffix"]), default=None)
    cls = row["class"] if row else policy["default_class"]
    if urlsplit(url).path.lower().endswith(".pdf"):
        for suf, c in policy["pdf_class_by_suffix"].items():
            if _suffix_match(host, suf) and cls == "A":
                cls = c
    pub = (row or {}).get("publisher")
    if not pub:
        pub = registrable(host, policy)
        if any(_suffix_match(host, p) for p in policy["path_platforms"]):
            first = [s for s in urlsplit(url).path.split("/") if s][:1]
            pub = "/".join([pub] + first)
    return cls, pub


def unreadable(url, policy):
    host = host_of(url)
    return any(_suffix_match(host, h) for h in policy["unreadable_hosts"])


# ---- 例年の時期 ----

def _md(month, third, policy, end):
    thirds = load_sources_thirds()
    if third is None:
        day = calendar.monthrange(LEAP_YEAR, month)[1] if end else 1
    else:
        t = thirds[third]
        day = (t["last"] or calendar.monthrange(LEAP_YEAR, month)[1]) if end else t["first"]
    return f"{month:02d}-{day:02d}"


def load_sources_thirds():
    from .sources import load_policy as sp
    return sp()["month_thirds"]["items"]


def parse_point(text):
    """「10月下旬」「2月末」「1月」→ (月, 旬 or None)。読めなければ None。"""
    m = SEASON_RE.match(str(text or ""))
    if not m:
        return None
    month, t = int(m.group(1)), m.group(2)
    if not calendar.JANUARY <= month <= calendar.DECEMBER:
        return None
    return month, THIRD_ALIASES.get(t, t)


def season_window(season, policy=None):
    """例年の時期 {text, from, to} → ("MM-DD", "MM-DD")(年をまたいでよい)、{year_round: true} → "year_round"、読めなければ None。"""
    if not season:
        return None
    if season.get("year_round") is True:
        return "year_round"
    a, b = parse_point(season.get("from")), parse_point(season.get("to") or season.get("from"))
    if not a or not b:
        return None
    return _md(a[0], a[1], policy, False), _md(b[0], b[1], policy, True)


def in_window(md, window):
    if window == "year_round":
        return True
    s, e = window
    return s <= md <= e if s <= e else (md >= s or md <= e)


def windows_overlap(w1, w2):
    if "year_round" in (w1, w2):
        return True
    return in_window(w1[0], w2) or in_window(w2[0], w1)


def days_until_start(d, window):
    """d から例年の時期の始まりまでの日数(すでに時期の中なら 0、通年なら 0)。"""
    if window == "year_round" or in_window(f"{d.month:02d}-{d.day:02d}", window):
        return 0
    m, dd = (int(x) for x in window[0].split("-"))
    for y in (d.year, d.year + 1):
        try:
            s = date(y, m, dd)
        except ValueError:
            s = date(y, m, dd - 1)
        if s >= d:
            return (s - d).days
    return None


# ---- 候補の記録 ----

def norm_name(s):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


def entry_id(theme, prefecture, name):
    h = hashlib.sha1(f"{theme}|{prefecture}|{norm_name(name)}".encode("utf-8")).hexdigest()
    return "g-" + h[:ID_HEX]


def validate_item(item, policy):
    """エージェントが渡した 1 件(事実の項目だけ)→ エラーのリスト。"""
    rp, errs = policy["record"], []
    extra = sorted(set(item) - set(rp["input_fields"]))
    if extra:
        errs.append(f"受け取れない項目(本文・時刻などは渡さない): {extra}")
    for k in ("theme", "name", "prefecture", "url"):
        if not isinstance(item.get(k), str) or not item.get(k).strip():
            errs.append(f"{k} がない")
    if errs:
        return errs
    if item["theme"] not in policy["themes"]:
        errs.append(f"theme={item['theme']} は {policy['themes']} のどれでもない")
    lim = {k: val(rp[f"max_{k}_chars"]) for k in ("name", "kind", "note", "title", "season", "state")}
    for k in ("name", "prefecture", "municipality"):
        if item.get(k) is not None and (not isinstance(item[k], str) or len(item[k]) > lim["name"]):
            errs.append(f"{k} は {lim['name']} 文字以内")
    for k in ("note", "title"):
        if item.get(k) is not None and (not isinstance(item[k], str) or len(item[k]) > lim[k]):
            errs.append(f"{k} は {lim[k]} 文字以内(本文を写さない)")
    kinds = item.get("kinds") or []
    if not isinstance(kinds, list) or len(kinds) > val(rp["max_kinds"]) or not all(isinstance(k, str) and 0 < len(k) <= lim["kind"] for k in kinds):
        errs.append(f"kinds は {val(rp['max_kinds'])} 個以内の、{lim['kind']} 文字以内の名前の配列")
    url = item["url"]
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
        errs.append(f"url が http(s) の URL でない: {url}")
    elif unreadable(url, policy):
        errs.append(f"SNS などの読まないホスト: {host_of(url)}")
    if item.get("copies_of") is not None and urlsplit(str(item["copies_of"])).scheme not in ("http", "https"):
        errs.append("copies_of は書き写し元の URL")
    se = item.get("season")
    if se is not None:
        if not isinstance(se, dict) or set(se) - {"text", "from", "to", "year_round"} or not isinstance(se.get("text"), str) \
                or len(se["text"]) > lim["season"]:
            errs.append(f"season は {{text(≦{lim['season']} 文字), from, to}} か {{text, year_round: true}}")
        elif season_window(se, policy) is None:
            errs.append(f"season の from・to が「10月下旬」「2月末」「1月」の形でない: {se}")
    st = item.get("status")
    if st is not None:
        if not isinstance(st, dict) or set(st) != {"state", "date"} or not isinstance(st["state"], str) or len(st["state"]) > lim["state"] \
                or not catalog_mod.valid_date(st["date"]):
            errs.append(f"status は {{state(≦{lim['state']} 文字の原文), date(YYYY-MM-DD)}}")
    acc = item.get("access")
    if acc is not None and (not isinstance(acc, list) or not set(acc) <= set(rp["access_values"])):
        errs.append(f"access は {rp['access_values']} の配列")
    if item.get("origin", "search") not in rp["origins"]:
        errs.append(f"origin は {rp['origins']} のどれか")
    return errs


def make_candidate(item, policy, now):
    """1 件 → 記録。読んだ時刻(read_at)・区分・発行元・読み方はコードが入れる。"""
    cls, pub = classify(item["url"], policy)
    rec = {"schema": policy["record"]["schema"], **{k: v for k, v in item.items() if v is not None},
           "origin": item.get("origin", "search"), "read_at": now.isoformat(), "read_by": policy["record"]["read_by"],
           "host": host_of(item["url"]), "publisher": pub, "class": cls}
    return rec


def _cand_key(r):
    return (r["theme"], r["prefecture"], norm_name(r["name"]), r["url"])


def record_candidates(items, *, policy=None, now=None, env=None):
    """候補を記録する(IKIMONOBIYORI_DATA_DIR の下の guide/candidates.jsonl)。1 件でも検査に落ちたら何も書かない。
    同じ名所・同じ URL の記録がもうあれば足さない。→ (書いた件数, 重複の件数, 書いた記録)"""
    policy = policy or load_policy()
    bad = [(i, e) for i, it in enumerate(items) for e in validate_item(it, policy)]
    if bad:
        raise ValueError("; ".join(f"[{i}] {e}" for i, e in bad))
    now = now or clock_now()
    seen = {_cand_key(r) for r in all_records(env)}
    new = []
    for it in items:
        r = make_candidate(it, policy, now)
        if _cand_key(r) not in seen:
            seen.add(_cand_key(r))
            new.append(r)
    if new:
        _append_jsonl(guide_dir(env) / "candidates.jsonl", new)
    return len(new), len(items) - len(new), new


def all_records(env=None, include_runtime=True):
    """見直して置いた記録(data/guide/records.jsonl)+ 手元の記録(IKIMONOBIYORI_DATA_DIR の下)。同じ名所・同じ URL は先のもの。"""
    out, seen = [], set()
    rows = _jsonl(RECORDS_PATH) + (_jsonl(guide_dir(env) / "candidates.jsonl") if include_runtime else [])
    for r in rows:
        if _cand_key(r) not in seen:
            seen.add(_cand_key(r))
            out.append(r)
    return out


# ---- 市区町村の代表点 ----

def load_places(env=None, include_runtime=True):
    """{(都道府県, 市区町村): 代表点の辞書}。data/guide/places.yaml + 手元の guide/places.jsonl(あと勝ち)。"""
    rows = (yaml.safe_load(PLACES_PATH.read_text(encoding="utf-8")) or {}).get("places", []) if PLACES_PATH.is_file() else []
    if include_runtime:
        rows = rows + _jsonl(guide_dir(env) / "places.jsonl")
    return {(r["prefecture"], r["municipality"]): r for r in rows}


def place_range(rec_or_entry, places, catalog_policy, policy):
    """→ {"status": in_range / out_of_range / pending, "km": 10 km 単位, "from": 起点, "qid"}。代表点がなければ pending(推測しない)。"""
    p = places.get((rec_or_entry.get("prefecture"), rec_or_entry.get("municipality")))
    if not p or p.get("lat") is None:
        return {"status": "pending"}
    km, origin = catalog_mod.nearest_origin_km(catalog_policy, p)
    step = val(policy["distance_step_km"])
    return {"status": "in_range" if km <= catalog_policy["range_limit"]["max_km"] else "out_of_range",
            "km": int(round(km / step) * step), "from": origin, "qid": p.get("qid")}


def places_needed(records, places):
    return sorted({(r["prefecture"], r["municipality"]) for r in records if r.get("municipality")} - set(places))


def place_titles(prefecture, municipality):
    """記事名の候補(先に試すもの → 次に試すもの)。同じ名前の市区町村がある記事は「名前 (都道府県)」。"""
    short = prefecture[:-1] if prefecture.endswith(("県", "府", "都")) and prefecture != "北海道" else prefecture
    return [municipality, f"{municipality} ({prefecture})", f"{municipality} ({short})"]


def accept_point(hit, prefecture):
    """Wikidata の項目を、その都道府県の市区町村と確かめられたときだけ使う(日本語の説明に都道府県の名前がある)。"""
    return bool(hit and hit.get("lat") is not None and prefecture in (hit.get("description") or ""))


# ---- 独立した出どころの数え方 ----

def independent_groups(sources):
    """出どころ → 独立したまとまり(同じ発行元・互いに書き写した記事は 1 つ)。→ [[出どころ, ...], ...]"""
    parent = list(range(len(sources)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    by_pub, by_url = {}, {}
    for i, s in enumerate(sources):
        by_pub.setdefault(s["publisher"], []).append(i)
        by_url.setdefault(s["url"], []).append(i)
    for ids in list(by_pub.values()) + list(by_url.values()):
        for j in ids[1:]:
            union(ids[0], j)
    pubs = {s["publisher"]: i for i, s in enumerate(sources)}
    for i, s in enumerate(sources):
        c = s.get("copies_of")
        if c:
            for j in by_url.get(c, []):
                union(i, j)
            cp = (s.get("copies_of_publisher"))
            if cp in pubs:
                union(i, pubs[cp])
    groups = {}
    for i in range(len(sources)):
        groups.setdefault(find(i), []).append(sources[i])
    return list(groups.values())


def tier_of(sources, groups, visits, policy):
    """信頼の段階(D-02 / フェーズ2 の 4)。verified → curated → reference の順に見る。"""
    t = policy["tiers"]
    if visits or any(s.get("status") and s["class"] in t["verified"]["status_classes"] for s in sources):
        return "verified"
    if len(groups) >= val(t["curated"]["min_independent"]) and any(s["class"] in t["curated"]["needs_class_any"] for s in sources):
        return "curated"
    return "reference"


# ---- まとめる ----

CLASS_RANK = "ABCD"


def _best(sources):
    return sorted(sources, key=lambda s: (CLASS_RANK.index(s["class"]), s["read_at"], s["url"]))


def load_reviews(env=None, include_runtime=True):
    """{名所 id: 最後の見直し {"state": rejected / approved, "at", "by", "reason"}}。data/guide/reviews.yaml + 手元の guide/reviews.jsonl(あと勝ち)。"""
    rows = (yaml.safe_load(REVIEWS_PATH.read_text(encoding="utf-8")) or {}).get("reviews", []) if REVIEWS_PATH.is_file() else []
    if include_runtime:
        rows = rows + _jsonl(guide_dir(env) / "reviews.jsonl")
    out = {}
    for r in rows:
        out[r["id"]] = r
    return out


def build_entries(records, places, policy, catalog_policy, reviews=None):
    """候補の記録 → 名所ごとの 1 件(テーマ・都道府県・名前が同じものをまとめる)。段階・実在・範囲・承認をコードが決める。決まった並び。"""
    reviews = reviews or {}
    by = {}
    for r in records:
        by.setdefault(entry_id(r["theme"], r["prefecture"], r["name"]), []).append(r)
    show_min = val(policy["show_fact_min_independent"])
    out = []
    for eid, rows in sorted(by.items()):
        srcs = []
        for r in sorted(rows, key=lambda x: (x["read_at"], x["url"])):
            s = {k: r[k] for k in ("url", "host", "publisher", "class", "read_at", "origin") if k in r}
            for k in ("title", "copies_of", "status", "seed_id", "note"):
                if r.get(k):
                    s[k] = r[k]
            if r.get("copies_of"):
                s["copies_of_publisher"] = classify(r["copies_of"], policy)[1]
            s["_kinds"], s["_season"], s["_access"] = r.get("kinds") or [], r.get("season"), r.get("access") or []
            srcs.append(s)
        groups = independent_groups(srcs)
        gid = {id(s): n for n, g in enumerate(groups) for s in g}
        kind_groups = {}
        for s in srcs:
            for k in s["_kinds"]:
                kind_groups.setdefault(k, set()).add(gid[id(s)])
        kinds = [{"kind": k, "independent_sources": len(g), "shown": len(g) >= show_min}
                 for k, g in sorted(kind_groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
        seasons = [(s, season_window(s["_season"], policy)) for s in _best(srcs) if s["_season"]]
        seasons = [(s, w) for s, w in seasons if w]
        season = None
        if seasons:
            s0, w0 = seasons[0]
            agree = {gid[id(s)] for s, w in seasons if windows_overlap(w, w0)}
            season = {"text": s0["_season"]["text"], "window": w0 if w0 == "year_round" else {"start": w0[0], "end": w0[1]},
                      "independent_sources": len(agree), "shown": len(agree) >= show_min, "from_url": s0["url"],
                      "other_texts": sorted({s["_season"]["text"] for s, _ in seasons[1:] if s["_season"]["text"] != s0["_season"]["text"]})}
        visits = [v for v in [reviews.get(eid)] if v and v.get("state") == "visited"]
        tier = tier_of(srcs, groups, visits, policy)
        exists = any(s["class"] in policy["existence_classes"] for s in srcs)
        muni = next((r.get("municipality") for r in sorted(rows, key=lambda x: (CLASS_RANK.index(x["class"]), x["read_at"])) if r.get("municipality")), None)
        rng = place_range({"prefecture": rows[0]["prefecture"], "municipality": muni}, places, catalog_policy, policy)
        reasons = []
        if tier == "reference":
            reasons.append(f"独立した出どころが {len(groups)} 件" + ("(個人の発信だけ)" if not exists else ""))
        if not exists:
            reasons.append("実在を、自治体・公園・観光協会・メディアの出どころで確認できていない")
        if rng["status"] == "pending":
            reasons.append("範囲は未確認(市区町村の代表点がない)")
        elif rng["status"] == "out_of_range":
            reasons.append(f"範囲の外(約 {rng['km']} km)")
        last = max(s["read_at"] for s in srcs)
        rv = reviews.get(eid)
        if rv and rv.get("state") == "rejected":
            approval = {"state": "rejected", "at": rv["at"], "by": "user", "reason": rv.get("reason")}
        elif not reasons:
            approval = ({"state": "approved", "at": rv["at"], "by": "user"} if rv and rv.get("state") == "approved"
                        else {"state": "provisional", "at": last[:len(date.min.isoformat())], "by": "auto-rule"})
        else:
            approval = {"state": "candidate", "reasons": reasons}
        status = sorted((s for s in srcs if s.get("status")), key=lambda s: s["status"]["date"], reverse=True)
        acc = sorted({a for s in srcs for a in s["_access"]})
        e = {"id": eid, "theme": rows[0]["theme"], "name": sorted(rows, key=lambda x: (CLASS_RANK.index(x["class"]), x["read_at"]))[0]["name"],
             "prefecture": rows[0]["prefecture"], "municipality": muni, "kinds": kinds, "season": season,
             "tier": tier, "independent_sources": len(groups), "classes": sorted({s["class"] for s in srcs}),
             "exists_confirmed": exists, "range": rng, "approval": approval,
             "sources": [{k: v for k, v in s.items() if not k.startswith("_") and k != "copies_of_publisher"} for s in srcs]}
        if acc:
            e["access"] = acc
        if status:
            e["latest_status"] = {**status[0]["status"], "url": status[0]["url"], "class": status[0]["class"]}
        out.append(e)
    return out


def approved(entry):
    return entry["approval"]["state"] in ("provisional", "approved")


# ---- 探す(ガイドの答えの材料) ----

def theme_of(word, policy):
    """質問の言葉 → {themes, kinds}。表にない言葉は None(推測しない)。"""
    return (policy.get("words") or {}).get((word or "").strip())


def kind_match(entry, kinds):
    if not kinds:
        return True
    names = [k["kind"] for k in entry["kinds"]]
    return any(q in n or n in q for q in kinds for n in names)


def find(entries, *, themes, kinds=None, on=None, prefectures=None, municipalities=None, names=None, policy=None):
    """→ {"recommend": おすすめにできる名所(承認・範囲内・時期が合う), "upcoming": これから(時期の始まりが近い),
    "other_season": 承認済みだが時期の外, "reference": 参考(段階が参考・候補のまま), "out_of_range": 範囲の外(名指しのときだけ答えに使う)}。"""
    policy = policy or load_policy()
    up_days = val(policy["upcoming_days"])
    out = {k: [] for k in ("recommend", "upcoming", "other_season", "reference", "out_of_range")}
    order = policy["tiers"]["order"]
    for e in entries:
        if e["theme"] not in themes or e["approval"]["state"] == "rejected" or not kind_match(e, kinds):
            continue
        if prefectures and e["prefecture"] not in prefectures:
            continue
        if municipalities and e.get("municipality") not in municipalities:
            continue
        if names and not any(norm_name(n) in norm_name(e["name"]) for n in names):
            continue
        if e["range"]["status"] == "out_of_range":
            out["out_of_range"].append(e)
            continue
        if not approved(e):
            out["reference"].append(e)
            continue
        w = (e["season"] or {}).get("window")
        w = w if w in (None, "year_round") else (w["start"], w["end"])
        if on is None or w is None:
            out["recommend"].append(e)
        elif in_window(f"{on.month:02d}-{on.day:02d}", w):
            out["recommend"].append(e)
        elif (days_until_start(on, w) or 0) <= up_days:
            out["upcoming"].append(e)
        else:
            out["other_season"].append(e)
    rank = lambda e: (order.index(e["tier"]), -e["independent_sources"], e["name"])
    for k in out:
        out[k].sort(key=rank)
    out["upcoming"].sort(key=lambda e: (days_until_start(on, _w(e)) if on else 0, rank(e)))
    return out


def _w(e):
    w = (e["season"] or {}).get("window")
    return w if w in (None, "year_round") else (w["start"], w["end"])


# ---- 見直し(外す・承認する・行って確認した) ----

def review(entry_id_, state, *, reason=None, env=None, now=None):
    """見直しを記録する(IKIMONOBIYORI_DATA_DIR の下の guide/reviews.jsonl)。外した名所(rejected)は、同じ候補が再び仮承認されない。"""
    if state not in ("rejected", "approved", "visited"):
        raise ValueError(f"state は rejected / approved / visited: {state}")
    if not re.fullmatch(r"g-[0-9a-f]+", entry_id_ or ""):
        raise ValueError(f"名所の id の形でない: {entry_id_}")
    row = {"id": entry_id_, "state": state, "at": (now or clock_now()).isoformat(), "by": "user"}
    if reason:
        row["reason"] = reason
    _append_jsonl(guide_dir(env) / "reviews.jsonl", [row])
    return row


# ---- 回数の記録(検索・取得) ----

def log_request(kind, phase, text, *, question=None, env=None, policy=None, now=None):
    """検索(search)・取得(fetch)を 1 回ずつ数える(エージェントの道具は計測フックの外なので、ここで数える)。
    上限(方針の budget)に達していたら書かずに ValueError(その回は使わない)。→ 記録した行と、その段階の合計。"""
    policy = policy or load_policy()
    budget = policy["budget"]
    if kind not in ("search", "fetch") or phase not in ("collect", "trial", "answer"):
        raise ValueError("kind は search / fetch、phase は collect / trial / answer")
    rows = _jsonl(guide_dir(env) / "requests.jsonl")
    used = sum(1 for r in rows if r["kind"] == kind and r["phase"] == phase)
    if used >= budget[phase][kind]:
        raise ValueError(f"{phase} の {kind} は上限 {budget[phase][kind]} 回に達した")
    if question:
        q_used = sum(1 for r in rows if r["kind"] == kind and r.get("question") == question)
        if q_used >= budget["answer"][kind]:
            raise ValueError(f"質問 {question} の {kind} は 1 質問あたりの上限 {budget['answer'][kind]} 回に達した")
    row = {"kind": kind, "phase": phase, "at": (now or clock_now()).isoformat(), "text": (text or "")[:val(policy["record"]["max_title_chars"])]}
    if question:
        row["question"] = question
    _append_jsonl(guide_dir(env) / "requests.jsonl", [row])
    return row, used + 1


def usage(env=None, policy=None):
    policy = policy or load_policy()
    rows = _jsonl(guide_dir(env) / "requests.jsonl")
    out = {}
    for ph, lim in policy["budget"].items():
        if not isinstance(lim, dict) or ph == "answer":
            continue
        out[ph] = {k: {"used": sum(1 for r in rows if r["kind"] == k and r["phase"] == ph), "limit": v} for k, v in lim.items()}
    qs = {}
    for r in rows:
        if r.get("question"):
            qs.setdefault(r["question"], {"search": 0, "fetch": 0})[r["kind"]] += 1
    out["by_question"] = qs
    pl = _jsonl(guide_dir(env) / "places_requests.jsonl")
    out["places"] = {"used": sum(r["requests"] for r in pl), "limit": policy["budget"]["places_requests"]}
    return out


def record_unanswered(question, *, env=None, policy=None, now=None):
    """答えられなかった質問の文だけを記録する(時刻はコードの時計。コミットしない場所)。"""
    policy = policy or load_policy()
    q = (question or "").strip()
    if not q or len(q) > val(policy["max_question_chars"]):
        raise ValueError(f"質問の文は 1〜{val(policy['max_question_chars'])} 文字")
    row = {"question": q, "at": (now or clock_now()).isoformat()}
    _append_jsonl(guide_dir(env) / policy["unanswered_file"], [row])
    return row


# ---- 付録A(種)の取り込み ----

SEED_HEAD_RE = re.compile(r"^##\s+(A-\d+)\.")
URL_RE = re.compile(r"https?://[^\s/|]+[^\s|]*")


def parse_seed(text):
    """docs/seeds/stage23-seeds.md の表 → 行の辞書のリスト(節・ID・列の名前 → 値)。表のない節は読まない。"""
    rows, sec, head = [], None, None
    for ln in text.splitlines():
        m = SEED_HEAD_RE.match(ln)
        if m:
            sec, head = m.group(1), None
            continue
        if not ln.startswith("|"):
            head = None if not ln.strip() else head
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if head is None:
            head = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append({"section": sec, **dict(zip(head, cells))})
    return rows


def seed_items(rows, mapping):
    """種の表の行 → record-candidate の項目(URL ごとに 1 件)。mapping は data/guide/seed_map.yaml(節ごとのテーマ・ID ごとの所在・種類・時期)。
    種類・時期は表の行のもの(付録A の行は、その行の出どころの URL をまとめたもの。D-06)。区分・独立の数はコードが計算し直す。"""
    items, skipped = [], []
    for r in rows:
        sid = r.get("ID")
        m = (mapping.get("rows") or {}).get(sid)
        if not m:
            skipped.append(sid)
            continue
        urls = URL_RE.findall(r.get("出どころのURL", ""))
        for u in urls:
            it = {"theme": m["theme"], "name": m["name"], "prefecture": m["prefecture"], "url": u, "origin": "seed", "seed_id": sid}
            for k in ("municipality", "kinds", "season", "note", "access"):
                if m.get(k) is not None:
                    it[k] = m[k]
            items.append(it)
    return items, skipped


# ---- 書き出し(見直して data/guide/ に写す) ----

def export(entries, records, places, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    cat = [e for e in entries if approved(e)]
    rest = [e for e in entries if not approved(e)]
    head = "# build の結果(python -X utf8 -m ikimonobiyori.guide build)。手で直さない(records.jsonl・places.yaml・reviews.yaml から作り直す)\n"
    (out_dir / "catalog.yaml").write_text(head + yaml.safe_dump({"schema": "ikimono-guide-catalog/1", "entries": cat}, allow_unicode=True,
                                                                sort_keys=False, width=200), encoding="utf-8", newline="\n")
    (out_dir / "candidates.yaml").write_text(head + yaml.safe_dump({"schema": "ikimono-guide-catalog/1", "entries": rest}, allow_unicode=True,
                                                                   sort_keys=False, width=200), encoding="utf-8", newline="\n")
    with (out_dir / "records.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in sorted(records, key=lambda r: (r["theme"], r["prefecture"], norm_name(r["name"]), r["url"])):
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    pl = sorted(places.values(), key=lambda p: (p["prefecture"], p["municipality"]))
    (out_dir / "places.yaml").write_text("# 市区町村の代表点(Wikidata の座標。CC0)。guide places-fetch の結果。推定で足さない\n" +
                                         yaml.safe_dump({"places": pl}, allow_unicode=True, sort_keys=False, width=200),
                                         encoding="utf-8", newline="\n")
    return {"catalog": len(cat), "candidates": len(rest), "records": len(records), "places": len(pl)}


def build(env=None, include_runtime=True):
    policy = load_policy()
    recs = all_records(env, include_runtime)
    places = load_places(env, include_runtime)
    return build_entries(recs, places, policy, catalog_mod.load_policy(), load_reviews(env, include_runtime)), recs, places


def committed_entries():
    """data/guide/catalog.yaml + candidates.yaml(見直して置いたもの)。"""
    out = []
    for p in (CATALOG_PATH, CANDIDATES_PATH):
        if p.is_file():
            out += (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("entries") or []
    return out


# ---- 見直しの一覧(Markdown) ----

def review_markdown(entries, policy):
    labels = policy["tiers"]["labels"]
    state_label = {"provisional": "仮承認", "approved": "承認", "candidate": "候補", "rejected": "外した"}
    lines = []
    for th in policy["themes"]:
        es = [e for e in entries if e["theme"] == th]
        if not es:
            continue
        es.sort(key=lambda e: (0 if approved(e) else 1, policy["tiers"]["order"].index(e["tier"]), -e["independent_sources"], e["name"]))
        lines += [f"## {th}({sum(approved(e) for e in es)} 件 仮承認 / {len(es)} 件)", "",
                  "| 名所 | 所在 | 種類 | 例年の時期 | 段階 | 独立した出どころ | 区分 | 状態 | 理由 | id |", "|---|---|---|---|---|---|---|---|---|---|"]
        for e in es:
            kinds = "・".join(k["kind"] for k in e["kinds"] if k["shown"]) or "—"
            se = e["season"]
            stext = (se["text"] + ("" if se["shown"] else "(1件のみ)")) if se else "—"
            rng = e["range"]
            where = f"{e['prefecture']}{e.get('municipality') or ''}" + (f"(約{rng['km']}km)" if rng.get("km") is not None else "")
            why = "; ".join(e["approval"].get("reasons") or []) or ("外した: " + (e["approval"].get("reason") or "") if e["approval"]["state"] == "rejected" else "規則を満たす")
            lines.append(f"| {e['name']} | {where} | {kinds} | {stext} | {labels[e['tier']]} | {e['independent_sources']} | {''.join(e['classes'])} | "
                         f"{state_label[e['approval']['state']]} | {why} | `{e['id']}` |")
        lines.append("")
    return "\n".join(lines)


# ---- 現況の記録の未来の時刻(段階23 フェーズ6) ----

def future_status_records(env=None, now=None):
    """status_log の記録のうち、読んだ時刻がパソコンの時計より後のもの(書き換えない。一覧にするだけ)。"""
    from . import sources
    now = now or clock_now()
    out = []
    for p in sorted(data_path(load_config()["status_log"]["dir"], env).glob("*.jsonl")):
        for r in _jsonl(p):
            if sources.parse_now(r["read_at"]) > now:
                out.append({"subject": p.stem, "source_id": r.get("source_id"), "label": r.get("label"), "read_at": r["read_at"]})
    return out


# ---- CLI ----

def _dump(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def _places_fetch(a, http_get):
    from .fetch import wikidata
    if not a.live:
        print("places-fetch は --live が必要です", file=sys.stderr)
        return 2
    if http_get is None and not livegate.live_allowed():
        print(livegate.refusal(), file=sys.stderr)
        return 2
    if a.max_requests is None or a.max_requests < 1:
        print("--live は明示的な --max-requests (1 以上)が必要です", file=sys.stderr)
        return 2
    if http_get is None and not os.environ.get("BIYORI_REQ_LOG"):
        print("--live は計測フック(BIYORI_REQ_LOG)が有効なときだけ実行します", file=sys.stderr)
        return 2
    policy, cfg = load_policy(), load_config()
    used = usage(policy=policy)["places"]["used"]
    left = min(a.max_requests, policy["budget"]["places_requests"] - used)
    if left < 1:
        print(f"市区町村の代表点の通信は上限 {policy['budget']['places_requests']} 回に達した", file=sys.stderr)
        return 2
    need = places_needed(all_records(), load_places())
    getter = None
    if http_get is None:
        from .fetch.live import SessionGetter
        t = cfg["live"]["request_timeout"]
        getter = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"])
    batch = cfg["live"]["wikidata"]["titles_per_request"]
    places_dec = val(policy["places_decimals"])
    found, reps, now = {}, [], clock_now()
    try:
        pending = list(need)
        for attempt in range(len(place_titles("x県", "x"))):
            if not pending or left < 1:
                break
            titles = sorted({place_titles(p, m)[attempt] for p, m in pending})
            got, rep = wikidata.read_points(titles, http_get=http_get or getter, cfg=cfg, max_requests=left, batch=batch)
            reps.append(rep)
            left -= rep["requests"]
            nxt = []
            for p, m in pending:
                hit = got.get(place_titles(p, m)[attempt])
                if accept_point(hit, p):
                    found[(p, m)] = {"prefecture": p, "municipality": m, "title": place_titles(p, m)[attempt], "qid": hit["qid"],
                                     "lat": round(hit["lat"], places_dec), "lon": round(hit["lon"], places_dec), "read_at": now.isoformat(), "source": "wikidata"}
                else:
                    nxt.append((p, m))
            pending = nxt
            if rep["status"] != "ok":
                break
    finally:
        if getter is not None:
            getter.close()
    if found:
        _append_jsonl(guide_dir() / "places.jsonl", list(found.values()))
    _append_jsonl(guide_dir() / "places_requests.jsonl", [{"at": now.isoformat(), "requests": sum(r["requests"] for r in reps)}])
    _dump({"needed": len(need), "found": len(found), "not_found": [f"{p}{m}" for p, m in need if (p, m) not in found], "reports": reps})
    return 0 if all(r["status"] == "ok" for r in reps) else 1


def main(argv=None, http_get=None):
    ap = argparse.ArgumentParser(prog="python -m ikimonobiyori.guide")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("theme", help="質問の言葉 → テーマ・種類(方針の words)")
    t.add_argument("word")
    rc = sub.add_parser("record-candidate", help="検索・取得で見つけた事実(名所・所在・種類・例年の時期・URL)を候補として記録する")
    rc.add_argument("--batch", required=True, help="JSON の配列: [{theme, name, prefecture, municipality?, kinds?, season?{text,from,to}|{text,year_round}, url, "
                                                   "title?, note?, copies_of?, status?{state,date}, access?, origin?(search/fetch/seed/user)}]")
    rc.add_argument("--read-at", help="渡しても使わない(読んだ時刻はコードが時計から入れる。段階23)")
    sd = sub.add_parser("import-seed", help="付録A(docs/seeds/stage23-seeds.md)を候補として取り込む")
    sd.add_argument("--file", required=True)
    sd.add_argument("--map", default=str(GUIDE_DIR / "seed_map.yaml"))
    sub.add_parser("places-needed", help="代表点がまだない市区町村")
    pf = sub.add_parser("places-fetch", help="市区町村の代表点を Wikidata から読む(--live・--max-requests・計測フックが要る)")
    pf.add_argument("--live", action="store_true")
    pf.add_argument("--max-requests", type=int)
    b = sub.add_parser("build", help="候補をまとめ、段階・承認を決めて書き出す(IKIMONOBIYORI_DATA_DIR の下の guide/export/)")
    b.add_argument("--committed-only", action="store_true", help="手元の記録を使わない(data/guide/ だけ)")
    sub.add_parser("review", help="見直しの一覧(Markdown)を標準出力に出す")
    f = sub.add_parser("find", help="ガイドの答えの材料(おすすめ・これから・参考)を出す(通信しない)")
    f.add_argument("--word", action="append", help="質問の言葉(方針の words。複数可)")
    f.add_argument("--theme", action="append")
    f.add_argument("--kind", action="append")
    f.add_argument("--date", help="対象の日(YYYY-MM-DD。省略すると時期で絞らない)")
    f.add_argument("--prefecture", action="append")
    f.add_argument("--region", help="地域の呼び名(方針 region_municipalities か data/regions.yaml の都道府県)")
    f.add_argument("--name", action="append", help="名所の名前(名指しの質問)")
    f.add_argument("--committed-only", action="store_true")
    for name in ("reject", "approve", "visited"):
        p = sub.add_parser(name, help={"reject": "仮承認・候補を外す(同じ候補は再び仮承認されない)", "approve": "承認する(ユーザーの見直し)",
                                       "visited": "ユーザーが行って確認した(確認済みになる)"}[name])
        p.add_argument("id")
        p.add_argument("--reason")
    lr = sub.add_parser("log-request", help="検索・取得を 1 回数える(上限に達していたら終了コード 3)")
    lr.add_argument("--kind", required=True, choices=["search", "fetch"])
    lr.add_argument("--phase", required=True, choices=["collect", "trial", "answer"])
    lr.add_argument("--text", required=True, help="検索の言葉・取得の URL")
    lr.add_argument("--question", help="質問の番号など(1 質問あたりの上限を数える)")
    sub.add_parser("usage", help="検索・取得・代表点の通信の回数")
    un = sub.add_parser("unanswered", help="答えられなかった質問の文を記録する(時刻はコードの時計)")
    un.add_argument("--question", required=True)
    sub.add_parser("future-records", help="現況の記録(status_log)のうち、読んだ時刻が未来のもの(書き換えない)")
    a = ap.parse_args(argv)
    policy = load_policy()

    if a.cmd == "theme":
        got = theme_of(a.word, policy)
        _dump({"word": a.word, **(got or {"themes": None})})
        return 0 if got else 1
    if a.cmd == "record-candidate":
        if a.read_at:
            print("警告: --read-at は使わない(読んだ時刻はコードがパソコンの時計から入れる)", file=sys.stderr)
        items = json.loads(Path(a.batch).read_text(encoding="utf-8"))
        try:
            n, dup, new = record_candidates(items, policy=policy)
        except ValueError as ex:
            print(f"記録しなかった: {ex}", file=sys.stderr)
            return 1
        _dump({"written": n, "duplicates": dup, "rows": [{k: r[k] for k in ("name", "host", "class", "publisher", "read_at")} for r in new]})
        return 0
    if a.cmd == "import-seed":
        rows = parse_seed(Path(a.file).read_text(encoding="utf-8"))
        mapping = yaml.safe_load(Path(a.map).read_text(encoding="utf-8"))
        items, skipped = seed_items(rows, mapping)
        try:
            n, dup, _ = record_candidates(items, policy=policy)
        except ValueError as ex:
            print(f"取り込まなかった: {ex}", file=sys.stderr)
            return 1
        _dump({"rows": len(rows), "items": len(items), "written": n, "duplicates": dup, "skipped_rows": skipped})
        return 0
    if a.cmd == "places-needed":
        _dump([f"{p} {m}" for p, m in places_needed(all_records(), load_places())])
        return 0
    if a.cmd == "places-fetch":
        return _places_fetch(a, http_get)
    if a.cmd == "build":
        entries, recs, places = build(include_runtime=not a.committed_only)
        _dump(export(entries, recs, places, guide_dir() / "export"))
        return 0
    if a.cmd == "review":
        print(review_markdown(build()[0], policy))
        return 0
    if a.cmd == "find":
        themes, kinds = set(a.theme or []), list(a.kind or [])
        for w in a.word or []:
            got = theme_of(w, policy)
            if got is None:
                _dump({"word": w, "themes": None, "note": "言い換えの表にない言葉(推測で結びつけない)"})
                return 1
            themes |= set(got["themes"])
            kinds += got.get("kinds") or []
        munis, prefs = None, a.prefecture
        if a.region:
            rm = (policy.get("region_municipalities") or {}).get(a.region)
            if rm:
                munis = rm["municipalities"]
            else:
                from . import sources
                reg = sources.resolve_region(a.region, sources.load_regions())
                if reg is None or not reg["match"].get("prefectures"):
                    print(f"地域の呼び名を市区町村・都道府県に結びつけられない: {a.region}", file=sys.stderr)
                    return 2
                prefs = reg["match"]["prefectures"]
        entries = committed_entries() if a.committed_only else build()[0]
        got = find(entries, themes=themes, kinds=kinds, on=date.fromisoformat(a.date) if a.date else None, prefectures=prefs,
                   municipalities=munis, names=a.name, policy=policy)
        _dump({"themes": sorted(themes), "kinds": kinds, "date": a.date, **{k: v for k, v in got.items()},
               "counts": {k: len(v) for k, v in got.items()}})
        return 0
    if a.cmd in ("reject", "approve", "visited"):
        try:
            row = review(a.id, {"reject": "rejected", "approve": "approved", "visited": "visited"}[a.cmd], reason=a.reason)
        except ValueError as ex:
            print(ex, file=sys.stderr)
            return 1
        _dump(row)
        return 0
    if a.cmd == "log-request":
        try:
            row, n = log_request(a.kind, a.phase, a.text, question=a.question, policy=policy)
        except ValueError as ex:
            print(f"数えなかった(使わない): {ex}", file=sys.stderr)
            return 3
        _dump({**row, "used_in_phase": n})
        return 0
    if a.cmd == "usage":
        _dump(usage(policy=policy))
        return 0
    if a.cmd == "unanswered":
        try:
            _dump(record_unanswered(a.question, policy=policy))
        except ValueError as ex:
            print(ex, file=sys.stderr)
            return 1
        return 0
    if a.cmd == "future-records":
        _dump(future_status_records())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
