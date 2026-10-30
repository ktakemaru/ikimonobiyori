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
import functools
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
from .profiles import load_profiles

GUIDE_DIR = DATA_FILES_DIR / "guide"
POLICY_PATH = GUIDE_DIR / "policy.yaml"
RECORDS_PATH = GUIDE_DIR / "records.jsonl"            # 見直して置いた候補の記録(事実だけ)。export の出力を写す
PLACES_PATH = GUIDE_DIR / "places.yaml"               # 市区町村の代表点(Wikidata)。export の出力を写す
REVIEWS_PATH = GUIDE_DIR / "reviews.yaml"             # ユーザーの見直し(外した・承認した)。ユーザーが確かめて置く
ANNOTATIONS_PATH = GUIDE_DIR / "annotations.jsonl"    # 既存の記録への追記の記録(段階26。guide annotate)。export の出力を写す
STATUS_ALIAS_PATH = GUIDE_DIR / "status_alias.yaml"    # 現況の名所 → ガイドの名所の対応表(段階26)。コードは表を読むだけ
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


def load_sources_answer():
    """答えの決まった文(data/sources/policy.yaml の answer)。出発地の 1 行は現況型の答えと同じ文を使う。"""
    from .sources import load_policy as sp
    return sp()["answer"]


@functools.lru_cache(maxsize=None)
def load_sources_thirds():
    """旬の分け方(data/sources/policy.yaml の month_thirds)。読み込みは 1 回だけ。"""
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


def entry_id(theme, prefecture, name, scope="place"):
    """名所(scope=place)はテーマ・都道府県・名前、種類の説明(scope=kind)はテーマ・名前から決まる id。"""
    key = f"{theme}|{prefecture}|{norm_name(name)}" if scope == "place" else f"kind|{theme}|{norm_name(name)}"
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return "g-" + h[:ID_HEX]


def validate_item(item, policy):
    """エージェントが渡した 1 件(事実の項目だけ)→ エラーのリスト。"""
    rp, errs = policy["record"], []
    extra = sorted(set(item) - set(rp["input_fields"]))
    if extra:
        errs.append(f"受け取れない項目(本文・時刻などは渡さない): {extra}")
    scope = item.get("scope", "place")
    if scope not in rp["scopes"]:
        errs.append(f"scope は {rp['scopes']} のどれか")
    for k in ("theme", "name", "url") + (("prefecture",) if scope == "place" else ()):
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
    cl = item.get("closure")
    if cl is not None and (not isinstance(cl, dict) or set(cl) - {"state", "since"} or not isinstance(cl.get("state"), str)
                           or len(cl["state"]) > lim["state"] or ("since" in cl and not catalog_mod.valid_date(cl["since"]))):
        errs.append(f"closure は {{state(≦{lim['state']} 文字の原文。「休園」など), since?(YYYY-MM-DD)}}")
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
    return (r.get("scope", "place"), r["theme"], r.get("prefecture"), norm_name(r["name"]), r["url"])


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


def all_records(env=None, include_runtime=True, annotated=True):
    """見直して置いた記録(data/guide/records.jsonl)+ 手元の記録(IKIMONOBIYORI_DATA_DIR の下)。同じ名所・同じ URL は先のもの。
    annotated なら、追記の記録(annotations.jsonl)を重ねた形(元の記録は変えない。出どころの URL・区分・発行元は追記で変わらない)。"""
    out, seen = [], set()
    rows = _jsonl(RECORDS_PATH) + (_jsonl(guide_dir(env) / "candidates.jsonl") if include_runtime else [])
    for r in rows:
        if _cand_key(r) not in seen:
            seen.add(_cand_key(r))
            out.append(r)
    return apply_annotations(out, all_annotations(env, include_runtime)) if annotated else out


def all_annotations(env=None, include_runtime=True):
    """追記の記録(data/guide/annotations.jsonl + 手元の guide/annotations.jsonl)。同じ内容は先のもの。"""
    name = load_policy()["annotation"]["file"]
    rows = _jsonl(ANNOTATIONS_PATH) + (_jsonl(guide_dir(env) / name) if include_runtime else [])
    out, seen = [], set()
    for a in rows:
        k = json.dumps({x: a.get(x) for x in a if x not in ("at",)}, ensure_ascii=False, sort_keys=True)
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out


def apply_annotations(records, annotations):
    """記録に追記を重ねる。市区町村は記録に無いときだけ入れる(あるものは変えない)。種名は足す(同じ名前は 1 つ)。時期は記録に無いときだけ入れる。
    出どころの URL・区分・発行元・読んだ時刻は変えない。"""
    by = {}
    for a in annotations:
        by.setdefault(_cand_key(a), []).append(a)
    out = []
    for r in records:
        anns = by.get(_cand_key(r))
        if not anns:
            out.append(r)
            continue
        r = dict(r)
        for a in anns:
            if a.get("municipality") and not r.get("municipality"):
                r["municipality"] = a["municipality"]
            if a.get("kinds"):
                r["kinds"] = list(dict.fromkeys(list(r.get("kinds") or []) + list(a["kinds"])))
            if a.get("season") and not r.get("season"):
                r["season"] = a["season"]
        out.append(r)
    return out


def validate_annotation(item, policy, existing_keys):
    """追記の 1 件 → エラーのリスト。対象は既存の記録(同じ名所・同じ URL)。追記できるのは市区町村・種名・時期だけ。"""
    ap = policy["annotation"]
    extra = sorted(set(item) - set(ap["input_fields"]))
    if extra:
        return [f"受け取れない項目(出どころの URL・区分・発行元などは変えられない): {extra}"]
    errs = []
    base = {k: v for k, v in item.items() if k != "summary"}
    if not any(item.get(f) for f in ap["fields"]):
        errs.append(f"追記する項目がない({ap['fields']} のどれか)")
    errs += validate_item(base, policy)
    s = item.get("summary")
    lim = val(ap["max_summary_chars"])
    if not isinstance(s, str) or not s.strip() or len(s) > lim:
        errs.append(f"summary(ページの記載の短い要約)が必要。{lim} 文字以内")
    if not errs and _cand_key(item) not in existing_keys:
        errs.append("対象の記録(同じ名所・同じ URL)がない。先に record-candidate で記録する")
    return errs


def annotate(items, *, policy=None, now=None, env=None):
    """既存の記録に事実を追記する(IKIMONOBIYORI_DATA_DIR の下の guide/annotations.jsonl)。1 件でも検査に落ちたら何も書かない。
    → (書いた件数, 書いた記録)。いつ(at。コードが時計から入れる)・何を・どのページの記載か(summary と URL)が残る。"""
    policy = policy or load_policy()
    existing = {_cand_key(r) for r in all_records(env, annotated=False)}
    bad = [(i, e) for i, it in enumerate(items) for e in validate_annotation(it, policy, existing)]
    if bad:
        raise ValueError("; ".join(f"[{i}] {e}" for i, e in bad))
    now = now or clock_now()
    new = [{"schema": policy["annotation"]["schema"], **{k: v for k, v in it.items() if v is not None}, "at": now.isoformat()} for it in items]
    _append_jsonl(guide_dir(env) / policy["annotation"]["file"], new)
    return len(new), new


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
    # 出発地ごとの距離と範囲(段階23 の続き。答えは出発地から測って書く。240〜250 km は範囲の端)
    by_origin = {n: {k: v for k, v in catalog_mod.range_from(catalog_policy, p, n).items() if k != "origin"}
                 for n in catalog_mod.origin_names(catalog_policy)}
    return {"status": "in_range" if km <= catalog_policy["range_limit"]["max_km"] else "out_of_range",
            "km": int(round(km / step) * step), "from": origin, "qid": p.get("qid"), "by_origin": by_origin}


def places_needed(records, places):
    return sorted({(r["prefecture"], r["municipality"]) for r in records if r.get("municipality") and r.get("scope", "place") == "place"} - set(places))


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


def curated_min(policy, theme=None):
    """定評にする独立した発行元の下限。テーマごとの上書き(min_independent_by_theme)があればそれ、なければ既定(段階24)。"""
    c = policy["tiers"]["curated"]
    return val((c.get("min_independent_by_theme") or {}).get(theme, c["min_independent"]))


def tier_of(sources, groups, visits, policy, theme=None):
    """信頼の段階(D-02 / フェーズ2 の 4)。verified → curated → reference の順に見る。"""
    t = policy["tiers"]
    if visits or any(s.get("status") and s["class"] in t["verified"]["status_classes"] for s in sources):
        return "verified"
    if len(groups) >= curated_min(policy, theme) and any(s["class"] in t["curated"]["needs_class_any"] for s in sources):
        return "curated"
    return "reference"


def _base_name(s):
    """名前の末尾のかっこ(「白鳥の郷公苑(三条市)」の所在)を除いて、比べる形にする。"""
    return norm_name(re.sub(r"[(（][^)）]*[)）]\s*$", "", s or ""))


def load_retired(policy, reviews=None, catalog_dir=None):
    """却下・退役した対象 → {"names": {基の名前: 理由}, "urls": {URL: 理由}}。名所カタログの retired と、見直しの rejected から作る(データを参照する)。"""
    g = policy.get("retired_guard") or {}
    names, urls = {}, {}
    for p in sorted(Path(catalog_dir or catalog_mod.CATALOG_DIR).glob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for e in doc.get("entries") or []:
            if e.get("status") in (g.get("catalog_status") or []):
                why = e.get("retired_reason") or "退役"
                names[_base_name(e["name"])] = why
                for src in e.get("sources") or []:
                    urls[src["url"]] = why
    for u in g.get("urls") or []:
        urls[u["url"]] = u["reason"]
    for rv in (reviews or {}).values():
        if rv.get("state") in (g.get("review_states") or []) and rv.get("name"):
            names[_base_name(rv["name"])] = rv.get("reason") or "却下"
    return {"names": names, "urls": urls}


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


def build_entries(records, places, policy, catalog_policy, reviews=None, retired=None):
    """候補の記録 → 名所ごとの 1 件(テーマ・都道府県・名前が同じものをまとめる)。段階・実在・範囲・承認をコードが決める。決まった並び。
    retired(load_retired の結果。省略すると名所カタログ・見直しから読む): 却下・退役した名前の名所は定評にしない。退役した出どころの URL は定評の件数に数えない(段階24)。"""
    reviews = reviews or {}
    retired = retired if retired is not None else load_retired(policy, reviews)
    # 区分・発行元は、読んだときではなく今の方針の表で決め直す(表に足したホストを、前に読んだ記録にも効かせる)
    records = [{**r, **dict(zip(("class", "publisher"), classify(r["url"], policy)))} for r in records]
    by = {}
    for r in records:
        by.setdefault(entry_id(r["theme"], r.get("prefecture"), r["name"], r.get("scope", "place")), []).append(r)
    show_min = val(policy["show_fact_min_independent"])
    out = []
    for eid, rows in sorted(by.items()):
        srcs = []
        for r in sorted(rows, key=lambda x: (x["read_at"], x["url"])):
            s = {k: r[k] for k in ("url", "host", "publisher", "class", "read_at", "origin") if k in r}
            for k in ("title", "copies_of", "status", "seed_id", "note", "closure"):
                if r.get(k):
                    s[k] = r[k]
            if r.get("copies_of"):
                s["copies_of_publisher"] = classify(r["copies_of"], policy)[1]
            s["_kinds"], s["_season"], s["_access"] = r.get("kinds") or [], r.get("season"), r.get("access") or []
            srcs.append(s)
        # 退役した出どころ(retired の URL)は、段階だけでなく、参照数・種名・時期の「表示してよい」の件数にも数えない(段階28b。記録と出どころの一覧には残す)
        live = [s for s in srcs if s["url"] not in retired["urls"]]
        groups = independent_groups(live)
        gid = {id(s): n for n, g in enumerate(groups) for s in g}
        kind_groups = {}
        for s in srcs:
            for k in s["_kinds"]:
                kind_groups.setdefault(k, set())
                if id(s) in gid:
                    kind_groups[k].add(gid[id(s)])
        kinds = [{"kind": k, "independent_sources": len(g), "shown": len(g) >= show_min}
                 for k, g in sorted(kind_groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
        seasons = [(s, season_window(s["_season"], policy)) for s in _best(srcs) if s["_season"]]
        seasons = [(s, w) for s, w in seasons if w]
        season = None
        if seasons:
            s0, w0 = seasons[0]
            agree = {gid[id(s)] for s, w in seasons if id(s) in gid and windows_overlap(w, w0)}
            season = {"text": s0["_season"]["text"], "window": w0 if w0 == "year_round" else {"start": w0[0], "end": w0[1]},
                      "independent_sources": len(agree), "shown": len(agree) >= show_min, "from_url": s0["url"],
                      "other_texts": sorted({s["_season"]["text"] for s, _ in seasons[1:] if s["_season"]["text"] != s0["_season"]["text"]})}
        visits = [v for v in [reviews.get(eid)] if v and v.get("state") == "visited"]
        rv_ = reviews.get(eid)
        # ユーザーが見直しで承認した場所は、名前の退役・却下の保証を外す(人の判断が自動の保証より先。出どころの URL の保証は残る。段階25)
        retired_name = None if (rv_ and rv_.get("state") == "approved") else retired["names"].get(_base_name(rows[0]["name"]))
        tier = tier_of(live, groups, visits, policy, rows[0]["theme"])
        if retired_name and tier == "curated":
            tier = "reference"                           # 却下・退役した対象は自動で定評にしない
        exists = any(s["class"] in policy["existence_classes"] for s in srcs)
        muni = next((r.get("municipality") for r in sorted(rows, key=lambda x: (CLASS_RANK.index(x["class"]), x["read_at"])) if r.get("municipality")), None)
        scope = rows[0].get("scope", "place")
        rng = (place_range({"prefecture": rows[0]["prefecture"], "municipality": muni}, places, catalog_policy, policy)
               if scope == "place" else {"status": "not_applicable"})
        reasons = []
        if scope == "kind":
            # 種類の説明は場所を持たない。独立した出どころ 2 件以上が言うことだけを答えに出す(フェーズ3 の 2。D-11)
            if len(groups) < show_min and tier != "verified":
                reasons.append(f"独立した出どころが {len(groups)} 件")
        elif tier == "reference":
            reasons.append(f"独立した出どころが {len(groups)} 件" + ("(個人の発信だけ)" if not exists else ""))
        if scope != "kind" and retired_name:
            reasons.append(f"却下・退役済み({retired_name})")
        if not exists:
            reasons.append("実在を、自治体・公園・観光協会・メディアの出どころで確認できていない")
        if rng["status"] == "pending":
            reasons.append("範囲は未確認(市区町村の代表点がない)")
        elif rng["status"] == "out_of_range":
            reasons.append(f"範囲の外(約 {rng['km']} km)")
        closed = [s for s in srcs if s.get("closure")]
        if closed:
            # 休園・閉園・立入禁止の記載が 1 件でもあれば仮承認しない(安全側。間違うと損が大きいもの。D-18)
            c0 = closed[0]["closure"]
            reasons.append(f"「{c0['state']}」の記載あり" + (f"({c0['since']} から)" if c0.get("since") else "") + f"(出どころ {len(closed)} 件)")
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
        e = {"id": eid, "scope": scope, "theme": rows[0]["theme"], "name": sorted(rows, key=lambda x: (CLASS_RANK.index(x["class"]), x["read_at"]))[0]["name"],
             "prefecture": rows[0].get("prefecture"), "municipality": muni, "kinds": kinds, "season": season,
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


def kind_match(entry, kinds, shown_only=False):
    """種類で絞る。shown_only なら、独立した出どころ 2 件以上が言う種類だけで見る(答えのおすすめに使う)。"""
    if not kinds:
        return True
    names = [k["kind"] for k in entry["kinds"] if k["shown"] or not shown_only]
    return any(q in n or n in q for q in kinds for n in names)


def find(entries, *, themes, kinds=None, on=None, prefectures=None, municipalities=None, names=None, policy=None, origin=None, catalog_policy=None):
    """→ {"recommend": おすすめにできる名所(承認・範囲内・時期が合う), "upcoming": これから(時期の始まりが近い),
    出発地(origin。省略すると横浜)から見て 250 km より先の名所は out_of_range。各名所に distance {origin, km, status}(240〜250 km は edge = 範囲の端)。
    "other_season": 承認済みだが時期の外, "no_season": 承認済みだが例年の時期が確かめられない, "reference": 参考(段階が参考・候補のまま), "out_of_range": 範囲の外(名指しのときだけ答えに使う)}。"""
    policy = policy or load_policy()
    cpol = catalog_policy or catalog_mod.load_policy()
    origin = catalog_mod.resolve_origin(cpol, origin)
    up_days = val(policy["upcoming_days"])
    out = {k: [] for k in ("recommend", "upcoming", "other_season", "no_season", "reference", "out_of_range", "kind_notes")}
    order = policy["tiers"]["order"]
    for e in entries:
        if e["theme"] not in themes or e["approval"]["state"] == "rejected":
            continue
        if e.get("scope") == "kind":
            if not kinds or any(q in e["name"] or e["name"] in q for q in kinds) or kind_match(e, kinds):
                out["kind_notes"].append(e)
            continue
        if not kind_match(e, kinds):
            continue
        if not kind_match(e, kinds, shown_only=True) and e["range"]["status"] != "out_of_range":
            out["reference"].append(e)                   # その種類を言う出どころが 1 件だけ(おすすめにしない。参考)
            continue
        if prefectures and e["prefecture"] not in prefectures:
            continue
        if municipalities and e.get("municipality") not in municipalities:
            continue
        if names and not any(norm_name(n) in norm_name(e["name"]) for n in names):
            continue
        dist = (e["range"].get("by_origin") or {}).get(origin)
        if dist:
            e = {**e, "distance": {"origin": origin, **dist}}             # 出発地から見た距離と範囲(in_range / edge / out_of_range)
        if e["range"]["status"] == "out_of_range" or (dist and dist["status"] == "out_of_range"):
            out["out_of_range"].append(e)                             # 出発地から 250 km より先(名指しの質問のときだけ答えに使う)
            continue
        if not approved(e):
            out["reference"].append(e)
            continue
        w = (e["season"] or {}).get("window")
        w = w if w in (None, "year_round") else (w["start"], w["end"])
        if on is None:
            out["recommend"].append(e)
        elif w is None or not (e["season"] or {}).get("shown"):
            default = (policy.get("season_default_by_theme") or {}).get(e["theme"])
            if default:                                  # 野鳥: 表示してよい時期の窓が無いときは通年が目安(段階27。ほかのテーマは時期不明のまま)
                one = (e["season"] or {}).get("text")
                a = policy["answer"]["season_default"]
                out["recommend"].append({**e, "season_default": a["with_text"].format(text=one) if one else a["plain"]})
            else:
                out["no_season"].append(e)               # 例年の時期が分からない・1 件だけ(対象の日に合うかを言わない)
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
    seen_urls = {}
    for r in rows:
        seen_urls[r.get("ID")] = URL_RE.findall(r.get("出どころのURL", ""))

    def add(sid, m, urls):
        for u in urls:
            it = {"theme": m["theme"], "name": m["name"], "url": u, "origin": "seed", "seed_id": sid}
            for k in ("scope", "prefecture", "municipality", "kinds", "season", "note", "access"):
                if m.get(k) is not None:
                    it[k] = m[k]
            items.append(it)

    for r in rows:
        sid = r.get("ID")
        m = (mapping.get("rows") or {}).get(sid)
        if not m:
            skipped.append(sid)
            continue
        urls = seen_urls[sid]
        if m.get("urls"):
            missing = [u for u in m["urls"] if u not in urls]
            if missing:
                raise ValueError(f"{sid}: 対応表の urls が付録A の行にない: {missing}")
            urls = m["urls"]
        add(sid, m, urls)
    for m in mapping.get("extra") or []:
        add(m["id"], m, m["urls"])
    return items, skipped


# ---- 書き出し(見直して data/guide/ に写す) ----

def export(entries, records, places, out_dir, policy=None, annotations=()):
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = policy or load_policy()
    records = [{**r, **dict(zip(("class", "publisher"), classify(r["url"], policy)))} for r in records]
    cat = [e for e in entries if approved(e)]
    rest = [e for e in entries if not approved(e)]
    head = "# build の結果(python -X utf8 -m ikimonobiyori.guide build)。手で直さない(records.jsonl・places.yaml・reviews.yaml から作り直す)\n"
    (out_dir / "catalog.yaml").write_text(head + yaml.safe_dump({"schema": "ikimono-guide-catalog/1", "entries": cat}, allow_unicode=True,
                                                                sort_keys=False, width=200), encoding="utf-8", newline="\n")
    (out_dir / "candidates.yaml").write_text(head + yaml.safe_dump({"schema": "ikimono-guide-catalog/1", "entries": rest}, allow_unicode=True,
                                                                   sort_keys=False, width=200), encoding="utf-8", newline="\n")
    with (out_dir / "records.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in sorted(records, key=lambda r: (r.get("scope", "place"), r["theme"], r.get("prefecture") or "", norm_name(r["name"]), r["url"])):
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with (out_dir / "annotations.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for a in annotations:
            f.write(json.dumps(a, ensure_ascii=False, sort_keys=True) + "\n")
    pl = sorted(places.values(), key=lambda p: (p["prefecture"], p["municipality"]))
    (out_dir / "places.yaml").write_text("# 市区町村の代表点(Wikidata の座標。CC0)。guide places-fetch の結果。推定で足さない\n" +
                                         yaml.safe_dump({"places": pl}, allow_unicode=True, sort_keys=False, width=200),
                                         encoding="utf-8", newline="\n")
    return {"catalog": len(cat), "candidates": len(rest), "records": len(records), "places": len(pl)}


def build(env=None, include_runtime=True):
    policy = load_policy()
    recs = all_records(env, include_runtime, annotated=False)                 # 書き出すのは元の記録(追記は annotations.jsonl に別に残す)
    places = load_places(env, include_runtime)
    return (build_entries(all_records(env, include_runtime), places, policy, catalog_mod.load_policy(), load_reviews(env, include_runtime)),
            recs, places)


def sources_mod_parse(s):
    """ISO 8601(オフセット必須)→ datetime(sources.parse_now と同じ)。"""
    from .sources import parse_now
    return parse_now(s)


def committed_entries(catalog_only=False):
    """data/guide/catalog.yaml + candidates.yaml(見直して置いたもの)。catalog_only なら catalog.yaml だけ。"""
    out = []
    for p in ((CATALOG_PATH,) if catalog_only else (CATALOG_PATH, CANDIDATES_PATH)):
        if p.is_file():
            out += (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("entries") or []
    return out


# ---- 参照数の表示(段階24) ----

def reference_counts(entries=None, policy=None):
    """ガイドのカタログの場所 → 参照数 {(テーマ, 基の名前): 独立した発行元の数}。承認(仮承認・承認)済みの場所だけ。"""
    entries = committed_entries(catalog_only=True) if entries is None else entries
    return {(e["theme"], _base_name(e["name"])): e["independent_sources"]
            for e in entries if e.get("scope", "place") == "place" and approved(e)}


def reference_count_for(counts, subject, name, policy):
    """現況の対象と名所の名前 → 参照数。ガイドのカタログに同じ場所がなければ None(推測や 1 の仮置きをしない)。"""
    theme = policy["reference_count"]["subject_theme"].get(subject)
    return counts.get((theme, _base_name(name)))


def load_status_alias(path=None):
    p = Path(path or STATUS_ALIAS_PATH)
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("aliases") or [] if p.is_file() else []


def check_status_alias(aliases, policy, guide_entries, status_catalogs):
    """対応表の検査 → エラーのリスト(空 = 合格)。status_catalogs: {対象: 現況の名所カタログ}。
    存在しない現況の id・ガイドの id、承認されていないガイドの名所、対象とテーマの食い違い、根拠の欠け、重複を落とす。"""
    errs, seen = [], set()
    by_id = {e["id"]: e for e in guide_entries}
    themes = policy["reference_count"]["subject_theme"]
    for i, a in enumerate(aliases):
        tag = f"aliases[{i}]"
        extra = sorted(set(a) - {"subject", "status_id", "guide_id", "basis"})
        if extra:
            errs.append(f"{tag}: 受け取れない項目 {extra}")
        subj, sid, gid = a.get("subject"), a.get("status_id"), a.get("guide_id")
        if subj not in themes:
            errs.append(f"{tag}: subject={subj} は対象の表(reference_count.subject_theme)にない")
            continue
        names = {e["id"]: e["name"] for e in catalog_mod.approved_entries(status_catalogs.get(subj) or {})}
        if sid not in names:
            errs.append(f"{tag}: 現況の名所 id が {subj} のカタログ(承認済み)にない: {sid}")
        g = by_id.get(gid)
        if g is None:
            errs.append(f"{tag}: ガイドの名所 id がない: {gid}")
        else:
            if g.get("scope", "place") != "place":
                errs.append(f"{tag}: ガイドの id が名所ではない: {gid}")
            if g["theme"] != themes[subj]:
                errs.append(f"{tag}: テーマが違う({subj} は {themes[subj]}、ガイドの {gid} は {g['theme']})")
            if not approved(g):
                errs.append(f"{tag}: ガイドの名所が承認されていない: {gid}")
        if not isinstance(a.get("basis"), str) or not a["basis"].strip():
            errs.append(f"{tag}: 根拠(basis)を 1 行で書く")
        if (subj, sid) in seen:
            errs.append(f"{tag}: 同じ現況の名所が重複: {subj} {sid}")
        seen.add((subj, sid))
    return errs


def reference_resolver(policy=None, aliases=None, entries=None, status_catalogs=None):
    """現況型の答え・提案の参照数を引く関数 (対象, 名所の名前) → 参照数 or None を作る。
    1. 名前が完全一致するガイドの名所(基の名前。段階24)  2. 対応表(status_alias.yaml)にある場所。どちらでもなければ None(推測しない)。"""
    policy = policy or load_policy()
    entries = committed_entries(catalog_only=True) if entries is None else entries
    counts = reference_counts(entries)
    aliases = load_status_alias() if aliases is None else aliases
    by_id = {e["id"]: e for e in entries}
    alias_by_name = {}
    for a in aliases:
        cat = (status_catalogs or {}).get(a["subject"]) if status_catalogs is not None else catalog_mod.load_catalog(a["subject"])
        names = {e["id"]: e["name"] for e in catalog_mod.approved_entries(cat or {})}
        g = by_id.get(a["guide_id"])
        if a["status_id"] in names and g is not None and approved(g):
            alias_by_name[(a["subject"], names[a["status_id"]])] = g["independent_sources"]

    def resolve(subject, name):
        n = reference_count_for(counts, subject, name, policy)
        return n if n is not None else alias_by_name.get((subject, name))
    return resolve


def count_suffix(n, policy):
    return policy["reference_count"]["suffix"].format(n=n) if n is not None else ""


def care_notes(themes, policy, profiles=None):
    """テーマ → 注意の行(プロファイルの care.manners の先頭から。括弧の出どころ注記は除く)。対応するプロファイルがないテーマは出さない。"""
    cfg = policy["answer"]["notes"]
    profiles = profiles if profiles is not None else load_profiles()
    lines = []
    for theme in sorted(themes):
        pid = cfg["profiles"].get(theme)
        manners = ((profiles.get(pid) or {}).get("care") or {}).get("manners") or []
        texts = [re.sub(r"[(（][^)）]*[)）]\s*$", "", m).strip() for m in manners[:cfg["max_manners"]]]
        if texts:
            lines.append(cfg["line"].format(theme=theme, text="。".join(texts) + "。"))
    return lines


def origin_line_for(origin_arg=None):
    """出発地の指定(省略すると横浜)→ (出発地, 答えの冒頭の 1 行)。guide find と guide page が同じ行を使う。"""
    cpol = catalog_mod.load_policy()
    origin = catalog_mod.resolve_origin(cpol, origin_arg)
    rl = cpol["range_limit"]
    return origin, load_sources_answer()["origin_line"].format(origin=origin, max_km=rl["max_km"], edge_km=val(rl["edge_min_km"]))


def themes_for_words(words, policy):
    """質問の言葉の並び → (テーマの集合, 種類の並び)。表にない言葉があれば (None, その言葉)。"""
    themes, kinds = set(), []
    for w in words:
        got = theme_of(w, policy)
        if got is None:
            return None, w
        themes |= set(got["themes"])
        kinds += got.get("kinds") or []
    return themes, kinds


def answer_parts(found, policy, origin_line=None, themes=None, show_out_of_range=False):
    """find の結果 → ガイド型の答えの部品(欄ごとの行)。文字(render_answer)と HTML(guide_page)が、同じ部品から同じ文を作る(段階29)。
    各行は {"entry", "index"(おすすめだけ 1 から), "name", "where", "body"(「 — 」の後ろ。参照数の文末つき), "line"(文字の答えの 1 行そのもの)}。"""
    a, labels, classes = policy["answer"], policy["tiers"]["labels"], policy["classes"]
    rc = policy["reference_count"]

    def row(e, i=None):
        where = f"{e.get('prefecture') or ''}{e.get('municipality') or ''}"
        bits = []
        se = e.get("season")
        if e.get("season_default"):
            bits.append(a["bits"]["season"].format(text=e["season_default"]))
        elif se and se["shown"]:
            bits.append(a["bits"]["season"].format(text=se["text"]))
        kinds = "・".join(k["kind"] for k in e["kinds"] if k["shown"])
        if kinds:
            bits.append(a["bits"]["kinds"].format(text=kinds))
        bits.append(a["bits"]["tier"].format(label=labels[e["tier"]]))
        bits.append(a["bits"]["classes"].format(text="・".join(classes[c] for c in e["classes"])))
        d = e.get("distance")
        if d:
            bits.append(a["bits"]["distance"].format(origin=d["origin"], km=d["km"]) + ("、" + a["bits"]["edge"] if d["status"] == "edge" else ""))
        head = a["place"].format(i=i, name=e["name"], where=where) if i else a["reference_item"].format(name=e["name"], where=where)
        body = "、".join(bits) + count_suffix(e["independent_sources"], policy)
        return {"entry": e, "index": i, "name": e["name"], "where": where, "body": body, "line": head + " — " + body}

    sections = []
    rec = found.get("recommend") or []
    sections.append({"key": "recommend", "heading": a["headings"]["recommend"], "numbered": True, "none": a["none_found"],
                     "rows": [row(e, i) for i, e in enumerate(rec, 1)]})
    for key in ("upcoming", "other_season", "no_season", "reference", "out_of_range"):
        es = found.get(key) or []
        if key == "out_of_range" and not show_out_of_range:
            continue
        if es:
            sections.append({"key": key, "heading": a["headings"][key], "numbered": False, "none": None, "rows": [row(e) for e in es]})
    notes = care_notes(themes, policy) if themes else []
    anyrow = any(sec["rows"] for sec in sections)
    return {"origin_line": origin_line, "sections": sections, "notes_heading": a["headings"]["notes"], "notes": notes,
            "legend": rc["legend"] if anyrow else None}


def render_answer(found, policy, origin_line=None, on=None, themes=None, show_out_of_range=False):
    """find の結果 → ガイド型の答え(コードが組み立てた文だけ)。各場所の行の文末に「（参照数 N）」、最後に凡例を 1 回。
    themes を渡すと「注意」(プロファイルのマナー)を凡例の前に付ける。show_out_of_range は名指しの質問のとき(範囲の外の名所を出す)。
    ここに出すのは、名所・所在・例年の時期(2 件以上の出どころが言うもの)・種類(同)・段階の日本語の呼び名・出どころの区分・距離だけ。"""
    parts = answer_parts(found, policy, origin_line, themes, show_out_of_range)
    lines = [origin_line, ""] if origin_line else []
    for sec in parts["sections"]:
        if sec["key"] != "recommend":
            lines.append("")
        lines.append(f"## {sec['heading']}")
        lines += [r["line"] for r in sec["rows"]] if sec["rows"] else [sec["none"]]
    if parts["notes"]:
        lines += ["", f"## {parts['notes_heading']}"] + [f"- {n}" for n in parts["notes"]]
    if parts["legend"]:
        lines += ["", parts["legend"]]
    return "\n".join(lines) + "\n"


def bird_status_line(title, today, *, count=None, species=None, unread=False, policy=None):
    """野鳥の現況(東京港野鳥公園のレンジャーブログ。要約の道具で読んだ結果)→ 答えの前に付ける 1 行(段階27 フェーズC)。
    title は最新の記事の題名「YYYY年M月D日の野鳥公園」。日付は題名からだけ取る。題名に日付がない・取得日(today)より未来なら使わない(確かめられなかった)。
    today からの日数が max_age_days より多ければ「最新の記事は○月○日です」。count は「30種」など書かれたとおり、species は種名の並び(書かれたとおり)。段階の語・多い少ないは推測しない。"""
    policy = policy or load_policy()
    cfg = policy["bird_status"]
    lines, parts = cfg["lines"], cfg["parts"]
    if unread:
        return {"state": "unread", "line": lines["unread"], "observed": None}
    m = re.search(cfg["title_re"], title or "")
    fm = {"fm": today.month, "fd": today.day}
    if not m:
        return {"state": "unconfirmed", "line": lines["unconfirmed"].format(**fm), "observed": None}
    try:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return {"state": "unconfirmed", "line": lines["unconfirmed"].format(**fm), "observed": None}
    if d > today:
        return {"state": "unconfirmed", "line": lines["unconfirmed"].format(**fm), "observed": None}
    state = "old" if (today - d).days > val(cfg["max_age_days"]) else "fresh"
    names = [str(x).strip() for x in (species or []) if str(x).strip()]
    line = lines[state].format(m=d.month, d=d.day, count=parts["count"].format(text=count.strip()) if count and count.strip() else "",
                              species=parts["species"].format(text="・".join(names)) if names else "", **fm)
    return {"state": state, "line": line, "observed": d.isoformat()}


def forbidden_in_answer(text, policy):
    """ガイド型の答えに出ている内部用語(空 = 合格)。英字の語は単語の区切りで探す。"""
    out = []
    for t in policy["answer"]["forbidden_terms"]:
        pat = rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])" if t.isascii() else re.escape(t)
        if re.search(pat, re.sub(r"https?://\S+", " ", text), flags=re.IGNORECASE):
            out.append(t)
    return out


# ---- 見直しの一覧(Markdown) ----

def _place_row(e, labels, state_label):
    kinds = "・".join(k["kind"] for k in e["kinds"] if k["shown"]) or "—"
    se = e["season"]
    stext = (se["text"] + ("" if se["shown"] else "(1件のみ)")) if se else "—"
    rng = e["range"]
    bo = rng.get("by_origin") or {}
    mark = {"edge": "・範囲の端", "out_of_range": "・範囲の外"}
    dist = "・".join(f"{n}から約{d['km']}km{mark.get(d['status'], '')}" for n, d in bo.items())
    where = f"{e['prefecture'] or ''}{e.get('municipality') or ''}" + (f"({dist})" if dist else "")
    why = "; ".join(e["approval"].get("reasons") or []) or ("外した: " + (e["approval"].get("reason") or "") if e["approval"]["state"] == "rejected" else "規則を満たす")
    return (f"| {e['name']} | {where} | {kinds} | {stext} | {labels[e['tier']]} | {e['independent_sources']} | {''.join(e['classes'])} | "
            f"{state_label[e['approval']['state']]} | {why} | `{e['id']}` |")


def _kind_row(e, labels, state_label):
    se = e["season"]
    stext = (se["text"] + ("" if se["shown"] else "(1件のみ)")) if se else "—"
    why = "; ".join(e["approval"].get("reasons") or []) or "規則を満たす"
    return (f"| {e['name']} | {stext} | {labels[e['tier']]} | {e['independent_sources']} | {''.join(e['classes'])} | "
            f"{state_label[e['approval']['state']]} | {why} | `{e['id']}` |")


PLACE_HEAD = ["| 名所 | 所在(東京・横浜からの距離) | 種類 | 例年の時期 | 段階 | 独立した出どころ | 区分 | 状態 | 理由 | id |", "|---|---|---|---|---|---|---|---|---|---|"]
KIND_HEAD = ["| 種類 | 時期 | 段階 | 独立した出どころ | 区分 | 状態 | 理由 | id |", "|---|---|---|---|---|---|---|---|"]


def review_markdown(entries, policy):
    """見直しの一覧(テーマごと。仮承認の表を先に、候補のままは折りたたむ)。"""
    labels = policy["tiers"]["labels"]
    state_label = {"provisional": "仮承認", "approved": "承認", "candidate": "候補", "rejected": "外した"}
    rank = lambda e: (policy["tiers"]["order"].index(e["tier"]), -e["independent_sources"], e["name"])
    lines = []
    for th in policy["themes"]:
        es = [e for e in entries if e["theme"] == th and e.get("scope", "place") == "place"]
        ks = [e for e in entries if e["theme"] == th and e.get("scope") == "kind"]
        if not es and not ks:
            continue
        ok, rest = sorted((e for e in es if approved(e)), key=rank), sorted((e for e in es if not approved(e)), key=rank)
        lines += [f"## {th}(名所: 仮承認 {len(ok)} 件・候補 {len(rest)} 件)", ""]
        if ok:
            lines += PLACE_HEAD + [_place_row(e, labels, state_label) for e in ok] + [""]
        if rest:
            lines += [f"<details><summary>候補のまま {len(rest)} 件(おすすめには出さない)</summary>", ""] + PLACE_HEAD +                      [_place_row(e, labels, state_label) for e in rest] + ["", "</details>", ""]
        if ks:
            kok, krest = sorted((e for e in ks if approved(e)), key=rank), sorted((e for e in ks if not approved(e)), key=rank)
            lines += [f"### {th}: 種類の説明(仮承認 {len(kok)} 件・候補 {len(krest)} 件)", ""]
            if kok:
                lines += KIND_HEAD + [_kind_row(e, labels, state_label) for e in kok] + [""]
            if krest:
                lines += [f"<details><summary>候補のまま {len(krest)} 件</summary>", ""] + KIND_HEAD +                          [_kind_row(e, labels, state_label) for e in krest] + ["", "</details>", ""]
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


def main(argv=None, http_get=None, http_bytes=None):
    ap = argparse.ArgumentParser(prog="python -m ikimonobiyori.guide")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("theme", help="質問の言葉 → テーマ・種類(方針の words)")
    t.add_argument("word")
    sub.add_parser("check-alias", help="現況の名所 → ガイドの名所の対応表(data/guide/status_alias.yaml)を検査する(通信しない)")
    an = sub.add_parser("annotate", help="既存の記録(同じ名所・同じ URL)に、後から分かった所在の市区町村・種名・時期を追記する(追記の記録が残る。段階26)")
    an.add_argument("--batch", required=True, help="追記の JSON(配列。各件は theme・name・prefecture・url と、municipality・kinds・season のどれか、summary)")
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
    pb = sub.add_parser("photos-build-table", help="野鳥の種の対応表(和名→学名・taxon id)を iNaturalist で作る(--live・--max-requests・計測フックが要る。段階29)")
    pb.add_argument("--live", action="store_true")
    pb.add_argument("--max-requests", type=int)
    pb.add_argument("--theme", default="野鳥", help="質問の言葉(方針の words。既定は野鳥)")
    ph_ = sub.add_parser("photos-fetch", help="表の種の代表写真を取ってキャッシュに置く(--live・--max-requests・計測フックが要る。段階29)")
    ph_.add_argument("--live", action="store_true")
    ph_.add_argument("--max-requests", type=int)
    sub.add_parser("photos-clear", help="写真のキャッシュだけを消す(ほかは消さない。段階29)")
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
    f.add_argument("--origin", help="出発地(data/catalog/policy.yaml の range_limit.origins。省略すると横浜)")
    f.add_argument("--committed-only", action="store_true")
    f.add_argument("--text", action="store_true", help="JSON ではなく、コードが組み立てたガイド型の答えの文を出す(参照数と凡例つき。段階24)")
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
    bs = sub.add_parser("bird-status", help="野鳥の現況(東京港野鳥公園のレンジャーブログ。要約の道具で読んだ結果)を答えの前に付ける 1 行にする(通信しない。段階27)")
    bs.add_argument("--title", help="最新の記事の題名(例: 2026年10月22日の野鳥公園)")
    bs.add_argument("--count", help="確認種数(書かれたとおり。例: 30種)")
    bs.add_argument("--species", nargs="*", help="種名(書かれたとおり)")
    bs.add_argument("--unread", action="store_true", help="読めなかったとき")
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
    if a.cmd == "check-alias":
        subjects = list(policy["reference_count"]["subject_theme"])
        errs = check_status_alias(load_status_alias(), policy, committed_entries(catalog_only=True),
                                  {s_: catalog_mod.load_catalog(s_) for s_ in subjects})
        _dump({"aliases": len(load_status_alias()), "errors": errs})
        return 1 if errs else 0
    if a.cmd == "annotate":
        items = json.loads(Path(a.batch).read_text(encoding="utf-8"))
        try:
            n, new = annotate(items, policy=policy)
        except ValueError as ex:
            print(f"追記しなかった: {ex}", file=sys.stderr)
            return 1
        _dump({"written": n, "rows": [{k: r.get(k) for k in ("name", "url", "municipality", "kinds", "season", "summary", "at")} for r in new]})
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
    if a.cmd in ("photos-build-table", "photos-fetch", "photos-clear"):
        from . import guide_photos
        if a.cmd == "photos-clear":
            return guide_photos.clear_cmd(a)
        if a.cmd == "photos-build-table":
            return guide_photos.build_table_cmd(a, http_get)
        return guide_photos.fetch_cmd(a, http_get, http_bytes)
    if a.cmd == "build":
        entries, recs, places = build(include_runtime=not a.committed_only)
        _dump(export(entries, recs, places, guide_dir() / "export", annotations=all_annotations(include_runtime=not a.committed_only)))
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
                   municipalities=munis, names=a.name, policy=policy, origin=a.origin)
        origin, line = origin_line_for(a.origin)
        if a.text:
            text = render_answer(got, policy, origin_line=line, themes=themes, show_out_of_range=bool(a.name))
            bad = forbidden_in_answer(text, policy)
            if bad:
                print(f"答えに内部用語が出ている: {bad}", file=sys.stderr)
                return 1
            print(text, end="")
            return 0
        _dump({"origin": origin, "origin_line": line, "themes": sorted(themes), "kinds": kinds, "date": a.date, **{k: v for k, v in got.items()},
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
    if a.cmd == "bird-status":
        got = bird_status_line(a.title, clock_now().date(), count=a.count, species=a.species, unread=a.unread, policy=policy)
        print(got["line"])
        return 0
    if a.cmd == "future-records":
        _dump(future_status_records())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
