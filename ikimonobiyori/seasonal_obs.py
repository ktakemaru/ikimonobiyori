"""段階83 第2部: 例年この時期の観察記録(iNaturalist の観察記録の集計。地域の組 × 週 × 分類)。

- 問い合わせ: /observations/species_counts(place_id = 地域の組の都県、week = ISO の週、d1/d2 = 過去の完全な年、研究用グレード・栽培と飼育を除く)。
  植物は開花の注釈(term_id/term_value_id)のある記録を別に数える。分類ごとの記録の合計は /observations/histogram(week_of_year)で 1 地域 1 分類 1 回。
- 持つのは集計値だけ(種の学名・和名・記録の数・合計)。座標・観察者・写真・観察の id は保存しない(絶対ルール7)。
- 保存先は IKIMONOBIYORI_DATA_DIR の下の inat_seasonal/<地域>/w<週>.json と totals.json。束(1 地域 × 数週)ごとに保存し、途中で止まっても続きから取れる。
- 有効期間(ttl_days)を過ぎたものは status / ask warm に出る。取り直しは fetch(BIYORI_ALLOW_LIVE=1・--live・--max-requests)。
- 値はすべて data/observations/seasonal.yaml。テストは通信しない(http_get を差し替える)。"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from . import yamlcache
from .fetch import ParseError
from .paths import data_path

HERE = Path(__file__).resolve().parent
POLICY = HERE / "data" / "observations" / "seasonal.yaml"
BASE = "https://api.inaturalist.org/v1"
JA_RE = re.compile(r"[぀-ヿ一-鿿]")
_CACHE = {}


def load_policy():
    if "p" not in _CACHE:
        _CACHE["p"] = yamlcache.load(POLICY)
    return _CACHE["p"]


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def display_name(ja, p=None):
    """和名 → 答えに書く名前(「ツワブキ(広義)」「クズ (広義)」の広義の印と空白を外す)。"""
    p = p or load_policy()
    return re.sub(p["name_strip_re"], "", ja or "").strip() or None


def years_for(now, p=None):
    """取得の日 → 対象の年(前の年までの完全な年)。"""
    p = p or load_policy()
    n = _v(p["years"]["count"])
    return list(range(now.year - n, now.year))


def week_of(d, p=None):
    """日付 → ISO の週(1〜weeks.count。第53週は最後の週にまとめる)。"""
    p = p or load_policy()
    return min(d.isocalendar()[1], _v(p["weeks"]["count"]))


def window_weeks(w, p=None):
    p = p or load_policy()
    n, k = _v(p["weeks"]["count"]), _v(p["weeks"]["window"])
    return [((w - 1 + i) % n) + 1 for i in range(-k, k + 1)]


def region(rid_or_name, p=None):
    p = p or load_policy()
    return next((r for r in p["regions"] if rid_or_name in (r["id"], r["name"])), None)


def region_label(reg):
    """答えに書く地域の名前(段階84: 新潟・南東北の組は 新潟・福島 の集計)。"""
    return reg.get("label") or reg["name"]


def _cat(cid, p):
    return next(c for c in p["categories"] if c["id"] == cid)


def subcategories(p=None):
    """段階84 第1部 D: 分けた分類 → {子の id: (親の id, 子の定義)}。"""
    p = p or load_policy()
    return {s["id"]: (parent, s) for parent, subs in (p.get("subcategories") or {}).items() for s in subs}


def category_label(cid, p=None):
    p = p or load_policy()
    sub = subcategories(p).get(cid)
    if sub:
        return sub[1]["label"]
    return _cat(cid, p)["label"]


def _iconic_to_cat(p):
    return {t: c["id"] for c in p["categories"] for t in c["iconic_taxa"]}


# ---- 問い合わせ(通信しない) ----

def _common(reg, years, p):
    return {"place_id": ",".join(str(x) for x in reg["place_ids"]), "quality_grade": p["quality_grade"], "captive": p["captive"],
            "d1": f"{years[0]}-01-01", "d2": f"{years[-1]}-12-31"}


def week_queries(reg, week, years, p=None):
    """1 地域 1 週の問い合わせ → [(名前, URL)]。名前は "group:<n>" か "flowering"。"""
    p = p or load_policy()
    out = []
    for i, g in enumerate(p["query_groups"]):
        taxa = [t for cid in g["categories"] for t in _cat(cid, p)["iconic_taxa"]]
        q = {**_common(reg, years, p), "week": week, "iconic_taxa": ",".join(taxa), "per_page": _v(g["per_page"]), "locale": p["locale"]}
        out.append((f"group:{i}", f"{BASE}/observations/species_counts?{urlencode(q)}"))
    fl = p["flowering"]
    q = {**_common(reg, years, p), "week": week, "iconic_taxa": ",".join(_cat(fl["category"], p)["iconic_taxa"]),
         "term_id": fl["term_id"], "term_value_id": fl["term_value_id"], "per_page": _v(fl["per_page"]), "locale": p["locale"]}
    out.append(("flowering", f"{BASE}/observations/species_counts?{urlencode(q)}"))
    return out


def totals_queries(reg, years, p=None):
    """1 地域の分類ごとの記録の合計(週ごと)→ [(分類, URL)]。"""
    p = p or load_policy()
    out = []
    for c in p["categories"]:
        q = {**_common(reg, years, p), "iconic_taxa": ",".join(c["iconic_taxa"]), "date_field": "observed", "interval": "week_of_year"}
        out.append((c["id"], f"{BASE}/observations/histogram?{urlencode(q)}"))
    return out


# ---- 応答の読み取り(形が違えば ParseError) ----

def parse_counts(resp):
    """species_counts → [{taxon_id, sci, ja, iconic, count}](和名は日本語の文字を含むときだけ。ほかの項目は捨てる)。"""
    if not isinstance(resp, dict) or not isinstance(resp.get("results"), list):
        raise ParseError("species_counts: results (配列) がない")
    rows = []
    for i, r in enumerate(resp["results"]):
        if not isinstance(r, dict) or not isinstance(r.get("count"), int) or isinstance(r.get("count"), bool):
            raise ParseError(f"species_counts: results[{i}].count (整数) がない")
        t = r.get("taxon")
        if not isinstance(t, dict) or not isinstance(t.get("name"), str):
            raise ParseError(f"species_counts: results[{i}].taxon.name (文字列) がない")
        cn = t.get("preferred_common_name")
        rows.append({"taxon_id": t.get("id"), "sci": t["name"], "ja": cn if isinstance(cn, str) and JA_RE.search(cn) else None,
                     "iconic": t.get("iconic_taxon_name"), "count": r["count"]})
    return rows


def parse_histogram(resp):
    """histogram(week_of_year)→ {週(int): 数}。"""
    try:
        w = resp["results"]["week_of_year"]
    except (KeyError, TypeError):
        raise ParseError("histogram: results.week_of_year がない") from None
    if not isinstance(w, dict):
        raise ParseError("histogram: week_of_year (辞書) がない")
    out = {}
    for k, v in w.items():
        if not str(k).isdigit() or not isinstance(v, int) or isinstance(v, bool):
            raise ParseError(f"histogram: week_of_year[{k}] (整数) がない")
        out[int(k)] = v
    return out


def split_by_category(rows, cats, p):
    """まとめて取った種を分類に分ける(記録の多い順のまま上位 top_n)。分類の分からない種は捨てる。"""
    m = _iconic_to_cat(p)
    top = _v(p["top_n"])
    out = {c: [] for c in cats}
    for r in rows:
        c = m.get(r.get("iconic"))
        if c in out and len(out[c]) < top:
            out[c].append({k: r[k] for k in ("taxon_id", "sci", "ja", "count")})
    return out


# ---- 保存 ----

def _dir(rid, env=None, p=None):
    p = p or load_policy()
    return data_path(f"{p['store_dir']}/{rid}", env)


def week_path(rid, week, env=None):
    return _dir(rid, env) / f"w{week:02d}.json"


def totals_path(rid, env=None):
    return _dir(rid, env) / "totals.json"


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def fresh(obj, now, p=None, reg=None):
    """有効期間の内で、対象の年が同じ。段階84: 保存した place_ids が今の地域の組と違うか、地域の組を変えた時刻(changed_at)より前に取った保存は取り直す。"""
    p = p or load_policy()
    try:
        at = datetime.fromisoformat(obj["fetched_at"])
    except (KeyError, TypeError, ValueError):
        return False
    if reg is not None and "place_ids" in obj and list(obj["place_ids"]) != list(reg["place_ids"]):
        return False
    if reg is not None and reg.get("changed_at") and at < datetime.fromisoformat(str(reg["changed_at"])):
        return False                                      # 地域の組を変える前に取った保存
    return now - at <= timedelta(days=_v(p["ttl_days"])) and obj.get("years") == years_for(now, p)


def status(now, env=None, p=None):
    """→ {regions: {地域: {weeks_ok, weeks_missing:[...], totals_ok}}, missing: 取り直しの要る(地域, 週|"totals")の数}。"""
    p = p or load_policy()
    out, missing = {}, 0
    n = _v(p["weeks"]["count"])
    for r in p["regions"]:
        miss = [w for w in range(1, n + 1) if not fresh(_read(week_path(r["id"], w, env)) or {}, now, p, r)]
        tot = fresh(_read(totals_path(r["id"], env)) or {}, now, p, r)
        out[r["id"]] = {"name": r["name"], "weeks_ok": n - len(miss), "weeks_missing": miss, "totals_ok": tot}
        missing += len(miss) + (0 if tot else 1)
    return {"regions": out, "missing": missing}


# ---- 取得(http_get は (status, 本文, ヘッダー) を返す関数) ----

def _get_json(get, url, now, env, kind):
    st, body, _h = get(url)
    if st != 200:
        raise ParseError(f"{kind}: HTTP {st}")
    try:
        return json.loads(body)
    except ValueError:
        _unparsed(url, st, body, now, env, "JSON ではない")
        raise ParseError(f"{kind}: JSON ではない") from None


def _unparsed(url, st, body, now, env, why):
    from .fetch.live import _save_unparsed
    return _save_unparsed(data_path("unparsed/inat_seasonal", env), url, st, body, now, why)


def fetch_week(rid, week, now, get, env=None, p=None):
    p = p or load_policy()
    reg = region(rid, p)
    years = years_for(now, p)
    cats = {}
    flowering = []
    for name, url in week_queries(reg, week, years, p):
        j = _get_json(get, url, now, env, name)
        try:
            rows = parse_counts(j)
        except ParseError as e:
            _unparsed(url, 200, json.dumps(j, ensure_ascii=False), now, env, str(e))
            raise
        if name == "flowering":
            flowering = [{k: r[k] for k in ("taxon_id", "sci", "ja", "count")} for r in rows]
        else:
            g = p["query_groups"][int(name.split(":")[1])]
            cats.update(split_by_category(rows, g["categories"], p))
    obj = {"region": rid, "place_ids": list(reg["place_ids"]), "week": week, "years": years, "fetched_at": now.isoformat(),
           "categories": cats, "flowering": flowering}
    _write(week_path(rid, week, env), obj)
    return obj


def fetch_totals(rid, now, get, env=None, p=None):
    p = p or load_policy()
    reg = region(rid, p)
    years = years_for(now, p)
    tot = {}
    for cid, url in totals_queries(reg, years, p):
        j = _get_json(get, url, now, env, f"histogram:{cid}")
        try:
            tot[cid] = {str(k): v for k, v in sorted(parse_histogram(j).items())}
        except ParseError as e:
            _unparsed(url, 200, json.dumps(j, ensure_ascii=False), now, env, str(e))
            raise
    obj = {"region": rid, "place_ids": list(reg["place_ids"]), "years": years, "fetched_at": now.isoformat(), "totals": tot}
    _write(totals_path(rid, env), obj)
    return obj


def _week_order(now, p):
    """取る順: 今の週から先へ(季節の順)。"""
    n = _v(p["weeks"]["count"])
    w0 = week_of(now.date() if isinstance(now, datetime) else now, p)
    return [((w0 - 1 + i) % n) + 1 for i in range(n)]


def plan_fetch(now, env=None, regions=None, weeks=None, p=None):
    """取り直しの要る仕事の一覧 → [(地域, 週 | "totals")]。週の順(週ごとに全地域)。"""
    p = p or load_policy()
    rids = regions or [r["id"] for r in p["regions"]]
    order = weeks or _week_order(now, p)
    jobs = [(rid, "totals") for rid in rids if not fresh(_read(totals_path(rid, env)) or {}, now, p, region(rid, p))]
    for w in order:
        for rid in rids:
            if not fresh(_read(week_path(rid, w, env)) or {}, now, p, region(rid, p)):
                jobs.append((rid, w))
    return jobs


def run_fetch(now, get, budget_left, env=None, regions=None, weeks=None, p=None, log=None):
    """上限の内で取れるだけ取る。1 つの仕事(1 地域 1 週 = 3 回、合計 = 5 回)を途中で切らない。→ {done, errors, left_jobs}。"""
    p = p or load_policy()
    jobs = plan_fetch(now, env, regions, weeks, p)
    per_week = len(p["query_groups"]) + 1
    per_tot = len(p["categories"])
    done, errors = [], []
    for rid, w in jobs:
        need = per_tot if w == "totals" else per_week
        if budget_left() < need:
            break
        try:
            if w == "totals":
                fetch_totals(rid, now, get, env, p)
            else:
                fetch_week(rid, w, now, get, env, p)
            done.append([rid, w])
            if log:
                log(f"{rid} {w}")
        except (ParseError, OSError) as e:
            errors.append({"region": rid, "week": w, "error": str(e)})
            break
    return {"done": done, "errors": errors, "left_jobs": len(plan_fetch(now, env, regions, weeks, p))}


# ---- 段階84 第1部 D: 虫の種の祖先(トンボ・チョウ・そのほか に分ける) ----

def taxa_path(env=None, p=None):
    p = p or load_policy()
    return data_path(f"{p['store_dir']}/{p['taxa_lookup']['file']}", env)


def load_taxa_groups(env=None, p=None):
    """→ {taxon_id(str): 子の分類の id}(祖先の表。なければ空)。"""
    return dict(((_read(taxa_path(env, p)) or {}).get("groups") or {}))


def _sub_of(ancestors, parent, p):
    subs = (p.get("subcategories") or {}).get(parent) or []
    for s in subs:
        if s.get("ancestor_taxon_id") is not None and s["ancestor_taxon_id"] in ancestors:
            return s["id"]
    return next(s["id"] for s in subs if s.get("ancestor_taxon_id") is None)


def missing_taxa(env=None, p=None):
    """保存した集計の、分けた分類(虫)の種のうち、祖先の表にない taxon_id(数の順)。"""
    p = p or load_policy()
    known = load_taxa_groups(env, p)
    parents = set((p.get("subcategories") or {}).keys())
    ids = set()
    root = data_path(p["store_dir"], env)
    if root.is_dir():
        for f in root.glob("*/w*.json"):
            for cid, rows in ((_read(f) or {}).get("categories") or {}).items():
                if cid in parents:
                    ids |= {r["taxon_id"] for r in rows if isinstance(r.get("taxon_id"), int) and str(r["taxon_id"]) not in known}
    return sorted(ids)


def parse_taxa(resp):
    """/v1/taxa/{ids} → {taxon_id: [祖先の id]}(形が違えば ParseError)。"""
    if not isinstance(resp, dict) or not isinstance(resp.get("results"), list):
        raise ParseError("taxa: results (配列) がない")
    out = {}
    for i, r in enumerate(resp["results"]):
        if not isinstance(r, dict) or not isinstance(r.get("id"), int) or not isinstance(r.get("ancestor_ids"), list):
            raise ParseError(f"taxa: results[{i}].id / ancestor_ids がない")
        out[r["id"]] = [a for a in r["ancestor_ids"] if isinstance(a, int)]
    return out


def run_taxa(now, get, budget_left, env=None, p=None):
    """祖先の表にない虫の種を、上限の内で引く(1 回 per_request 件)。→ {done, errors, left}。"""
    p = p or load_policy()
    per = _v(p["taxa_lookup"]["per_request"])
    ids = missing_taxa(env, p)
    groups = load_taxa_groups(env, p)
    done, errors = 0, []
    parent = next(iter((p.get("subcategories") or {}).keys()))
    for i in range(0, len(ids), per):
        if budget_left() < 1:
            break
        chunk = ids[i:i + per]
        url = f"{BASE}/taxa/{','.join(str(x) for x in chunk)}?{urlencode({'locale': p['locale'], 'per_page': per})}"
        try:
            anc = parse_taxa(_get_json(get, url, now, env, "taxa"))
        except (ParseError, OSError) as e:
            errors.append(str(e))
            break
        for tid in chunk:
            if tid in anc:
                groups[str(tid)] = _sub_of(anc[tid], parent, p)
        done += len(chunk)
        _write(taxa_path(env, p), {"fetched_at": now.isoformat(), "groups": dict(sorted(groups.items(), key=lambda kv: int(kv[0])))})
    return {"done": done, "errors": errors, "left": len(missing_taxa(env, p))}


# ---- 資料の材料(通信しない) ----

def _annual(rid, env, p):
    """地域の種ごとの年の記録(保存した全部の週の数の合計 ÷ 年数)。"""
    n = _v(p["weeks"]["count"])
    tot = {}
    years = None
    for w in range(1, n + 1):
        o = _read(week_path(rid, w, env))
        if not o:
            continue
        years = years or o.get("years")
        for cid, rows in (o.get("categories") or {}).items():
            for r in rows:
                tot[(cid, r["sci"])] = tot.get((cid, r["sci"]), 0) + r["count"]
    k = len(years or []) or _v(p["years"]["count"])
    return {key: v / k for key, v in tot.items()}


def species_window(rid, d, env=None, p=None):
    """対象の日 d の週と前後の週の集計 → {weeks, years, fetched_at, categories: {分類: [{name, sci, count, flower, flower_usable}]}, totals}。
    和名のない種・年の記録が min_per_year に満たない種は除く。なければ None。"""
    p = p or load_policy()
    ws = window_weeks(week_of(d, p), p)
    objs = [o for o in (_read(week_path(rid, w, env)) for w in ws) if o]
    if not objs:
        return None
    annual = _annual(rid, env, p)
    min_y = _v(p["min_per_year"])
    fmin = _v(p["flowering_min_count"])
    flower = {}
    for o in objs:
        for r in o.get("flowering") or []:
            flower[r["sci"]] = flower.get(r["sci"], 0) + r["count"]
    cats = {}
    for c in p["categories"]:
        acc = {}
        for o in objs:
            for r in (o.get("categories") or {}).get(c["id"]) or []:
                if not r.get("ja") or display_name(r["ja"], p) in (p.get("exclude_names") or []):
                    continue
                a = acc.setdefault(r["sci"], {"name": display_name(r["ja"], p), "sci": r["sci"], "taxon_id": r.get("taxon_id"), "count": 0})
                a["count"] += r["count"]
        rows = [a for a in acc.values() if annual.get((c["id"], a["sci"]), 0) >= min_y]
        for a in rows:
            if c["id"] == p["flowering"]["category"]:
                a["flower"] = flower.get(a["sci"], 0)
                a["flower_usable"] = a["flower"] >= fmin
        rows.sort(key=lambda a: (-a["count"], a["name"]))
        cats[c["id"]] = rows
    groups = load_taxa_groups(env, p)
    subs_ok = {}
    if groups:                                            # 段階84 第1部 D: 祖先の表があれば、虫を トンボ・チョウ・そのほか に分ける
        for parent, subs in (p.get("subcategories") or {}).items():
            rows = cats.get(parent) or []
            for s in subs:
                cats[s["id"]] = [a for a in rows if groups.get(str(a.get("taxon_id"))) == s["id"]]
            subs_ok[parent] = all(str(a.get("taxon_id")) in groups for a in rows)
    tot_obj = _read(totals_path(rid, env)) or {}
    totals = {cid: sum((tot_obj.get("totals") or {}).get(cid, {}).get(str(w), 0) for w in ws) for cid in (tot_obj.get("totals") or {})}
    return {"weeks": ws, "years": objs[0].get("years"), "fetched_at": min(o.get("fetched_at") or "" for o in objs),
            "complete": len(objs) == len(ws), "categories": cats, "totals": totals, "subcategories_complete": subs_ok}


def weeks_text(d, ws, p=None):
    """週の並び → 「11/2〜11/22ごろ」(対象の日の年の ISO の週の月曜〜日曜)。"""
    y = d.year
    first, last = ws[0], ws[-1]
    try:
        a = date.fromisocalendar(y if first <= last or first < ws[1] else y - 1, first, 1)
        b = date.fromisocalendar(y if first <= last or last >= ws[1] else y + 1, last, 7)
    except ValueError:
        return None
    return f"{a.month}/{a.day}〜{b.month}/{b.day}ごろ"


def vocabulary(env=None, p=None):
    """保存した集計にある和名の全部(ask verify が、資料の節にない種の名前を見つけるのに使う)。"""
    p = p or load_policy()
    names = set()
    root = data_path(p["store_dir"], env)
    if not root.is_dir():
        return names
    for f in root.glob("*/w*.json"):
        o = _read(f) or {}
        for rows in (o.get("categories") or {}).values():
            names |= {display_name(r["ja"], p) for r in rows if r.get("ja")}
    return names



_VOCAB = {}


def species_in_question(question, env=None, p=None):
    """段階84 第1部 C: 質問の文にある、集計の和名(種の名前の辞書)→ [名前](長い名前から。前後がカタカナの一致は数えない。
    分類の語(トンボ・チョウ など)は種にしない)。集計がなければ空。"""
    p = p or load_policy()
    D = p["species_dictionary"]
    key = str(data_path(p["store_dir"], env))
    if key not in _VOCAB:
        cw = {w for ws in p["brief"]["category_words"].values() for w in ws}
        _VOCAB[key] = sorted((n for n in vocabulary(env, p) if n and re.fullmatch(D["name_re"], n) and len(n) >= _v(D["min_len"]) and n not in cw),
                             key=lambda n: (-len(n), n))
    q = question or ""
    out, used = [], []
    for n in _VOCAB[key]:
        for m in re.finditer(r"(?<![ァ-ヶー])" + re.escape(n) + r"(?![ァ-ヶー])", q):
            if not any(a <= m.start() and m.end() <= b for a, b in used):
                used.append((m.start(), m.end()))
                if n not in out:
                    out.append(n)
    return out


# ---- CLI ----

def main(argv=None, http_get=None, clock=None):
    from . import sources as S
    ap = argparse.ArgumentParser(prog="seasonal_obs", description="例年この時期の観察記録(iNaturalist の集計。段階83)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status")
    st.add_argument("--now")
    f = sub.add_parser("fetch")
    f.add_argument("--live", action="store_true")
    f.add_argument("--max-requests", type=int)
    f.add_argument("--region", action="append")
    f.add_argument("--weeks", help="例: 45-48 か 6,7,8")
    f.add_argument("--now")
    t = sub.add_parser("taxa", help="段階84: 虫の種の祖先を引く(トンボ・チョウ・そのほか に分ける)")
    t.add_argument("--live", action="store_true")
    t.add_argument("--max-requests", type=int)
    t.add_argument("--now")
    w = sub.add_parser("window")
    w.add_argument("--region", required=True)
    w.add_argument("--date", required=True)
    a = ap.parse_args(argv)
    p = load_policy()
    now = S.parse_now(a.now) if getattr(a, "now", None) else datetime.now().astimezone().replace(microsecond=0)
    if a.cmd == "status":
        s = status(now)
        print(json.dumps({"missing": s["missing"], "regions": {k: {**v, "weeks_missing": len(v["weeks_missing"])} for k, v in s["regions"].items()}},
                         ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "window":
        print(json.dumps(species_window(a.region, date.fromisoformat(a.date)), ensure_ascii=False, indent=1))
        return 0
    if not a.live or not a.max_requests or a.max_requests < 1:
        print("--live と --max-requests (1 以上)が必要です", file=sys.stderr)
        return 4
    weeks = None
    if getattr(a, "weeks", None):
        weeks = []
        for part in a.weeks.split(","):
            lo, _, hi = part.partition("-")
            weeks += list(range(int(lo), int(hi or lo) + 1))
    budget = None
    if http_get is None:
        from . import livegate, netbudget
        from .config import load_config
        from .fetch.live import default_http_get
        if not livegate.live_allowed():
            print(livegate.refusal(), file=sys.stderr)
            return 4
        cfg = load_config()
        budget = netbudget.Budget("inat_seasonal", cfg["live"]["allowed_hosts_by_subject"]["birds"],
                                  min(a.max_requests, _v(p["max_requests_per_run"])), _v(p["min_interval_s"]))
        get = budget(lambda u: default_http_get(u, user_agent=cfg["live"]["user_agent"], timeout=cfg["live"]["timeout_s"]))
        left = budget.left
    else:
        used = [0]

        def get(u):
            used[0] += 1
            return http_get(u)

        def left():
            return a.max_requests - used[0]
    if a.cmd == "taxa":
        out = run_taxa(now, get, left, p=p)
        out["requests"] = budget.used if budget else a.max_requests - left()
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 5 if out["errors"] else 0
    out = run_fetch(now, get, left, regions=a.region, weeks=weeks, p=p)
    out["requests"] = budget.used if budget else a.max_requests - left()
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 5 if out["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
