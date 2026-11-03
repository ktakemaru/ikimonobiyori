"""iNaturalist API v1 の応答パーサーと問い合わせの組み立て(通信しない)。

応答の形(想定。公式ドキュメントでの確認は 6b の最初の実応答で行う。docs/ikimonobiyori-research.md §1):
  /observations/species_counts → {"total_results": N, "page": 1, "per_page": M,
        "results": [{"count": 12, "taxon": {"id": 1, "name": "Parus minor", "preferred_common_name": "...", "iconic_taxon_name": "Aves"}}]}
  /observations → {"total_results": N, "results": [{"id": 1, "observed_on": "2025-10-12", ...}]}
形が違えば ParseError(推測で補わない)。"""
from datetime import date, timedelta
from urllib.parse import urlencode

from . import ParseError

BASE = "https://api.inaturalist.org/v1"
LOCALE = "ja"


def species_counts_query(*, lat, lng, radius_km, center, year, window_weeks, iconic_taxa, quality_grade, per_page=None,
                         locale=LOCALE):
    """locale=ja を付ける(日本語名を返させる。非公式のパラメータ。docs/ikimonobiyori-research.md §14)。対象日(center の月日)の前後 window_weeks 週を、過去の year 年について問い合わせる条件。戻り値: {"endpoint", "params", "url"}。"""
    try:
        c = date(year, center.month, center.day)
    except ValueError:                       # 2/29 など
        c = date(year, center.month, center.day - 1)
    span = timedelta(days=window_weeks * 7)
    params = {"lat": lat, "lng": lng, "radius": radius_km, "d1": (c - span).isoformat(), "d2": (c + span).isoformat(),
              "iconic_taxa": iconic_taxa, "quality_grade": quality_grade}
    if per_page is not None:
        params["per_page"] = per_page
    if locale:
        params["locale"] = locale
    return {"endpoint": "/observations/species_counts", "params": params,
            "url": f"{BASE}/observations/species_counts?{urlencode(params)}"}


def parse_species_counts(resp):
    """→ (rows, total_results)。rows = [{"taxon_id", "name", "common_name", "count"}]。"""
    if not isinstance(resp, dict) or not isinstance(resp.get("results"), list):
        raise ParseError("species_counts: results (配列) がない")
    rows = []
    for i, r in enumerate(resp["results"]):
        if not isinstance(r, dict) or not isinstance(r.get("count"), int) or isinstance(r.get("count"), bool):
            raise ParseError(f"species_counts: results[{i}].count (整数) がない")
        t = r.get("taxon")
        if not isinstance(t, dict) or not isinstance(t.get("name"), str):
            raise ParseError(f"species_counts: results[{i}].taxon.name (文字列) がない")
        rows.append({"taxon_id": t.get("id"), "name": t["name"], "common_name": t.get("preferred_common_name"),
                     "count": r["count"]})
    total = resp.get("total_results")
    return rows, total if isinstance(total, int) else None


def parse_latest_observed(resp):
    """/observations の応答から、最も新しい observed_on (YYYY-MM-DD)。無ければ None(出典側の最終更新日の代わり)。"""
    if not isinstance(resp, dict) or not isinstance(resp.get("results"), list):
        raise ParseError("observations: results (配列) がない")
    days = []
    for r in resp["results"]:
        d = r.get("observed_on") if isinstance(r, dict) else None
        if isinstance(d, str):
            date.fromisoformat(d)                 # 形式が違えば ValueError
            days.append(d)
    return max(days) if days else None


def observations_total_query(*, lat, lng, radius_km, months, iconic_taxa, quality_grade, per_page):
    """/observations の観察総数(total_results)を取る問い合わせ。年は限らず months(月)だけで絞る。結果の項目は使わない(per_page は 0 か 1)。"""
    params = {"lat": lat, "lng": lng, "radius": radius_km, "month": ",".join(str(m) for m in months), "iconic_taxa": iconic_taxa,
              "quality_grade": quality_grade, "per_page": per_page}
    return {"endpoint": "/observations", "params": params, "url": f"{BASE}/observations?{urlencode(params)}"}


def species_counts_months_query(*, lat, lng, radius_km, months, iconic_taxa, quality_grade, per_page, locale=None):
    params = {"lat": lat, "lng": lng, "radius": radius_km, "month": ",".join(str(m) for m in months), "iconic_taxa": iconic_taxa,
              "quality_grade": quality_grade, "per_page": per_page}
    if locale:
        params["locale"] = locale
    return {"endpoint": "/observations/species_counts", "params": params, "url": f"{BASE}/observations/species_counts?{urlencode(params)}"}


def parse_observations_total(resp):
    """→ (total_results, 返ってきた results の件数)。results の中身(観察者・写真など)は読まない・保存しない。"""
    if not isinstance(resp, dict) or isinstance(resp.get("total_results"), bool) or not isinstance(resp.get("total_results"), int):
        raise ParseError("observations: total_results (整数) がない")
    r = resp.get("results")
    return resp["total_results"], (len(r) if isinstance(r, list) else 0)


def observations_window_query(*, lat, lng, radius_km, years, month, days, iconic_taxa, quality_grade, per_page, endpoint="/observations", locale=None):
    """窓(前後N日)×複数年を1リクエストで取る条件(year/month/day の複数指定)。非公式の書き方の可能性あり(docs/ikimonobiyori-research.md §14)。"""
    params = {"lat": lat, "lng": lng, "radius": radius_km, "year": ",".join(str(y) for y in years), "month": month,
              "day": ",".join(str(d) for d in days), "iconic_taxa": iconic_taxa, "quality_grade": quality_grade, "per_page": per_page}
    if locale:
        params["locale"] = locale
    return {"endpoint": endpoint, "params": params, "url": f"{BASE}{endpoint}?{urlencode(params)}"}


def species_counts_years_query(*, lat, lng, radius_km, years, iconic_taxa, quality_grade, per_page, locale=LOCALE):
    """段階38: 季節らしさの分母(その場所の一年の記録)。窓の問い合わせと同じ過去の年を、月日で絞らずに 1 リクエストで取る条件。"""
    params = {"lat": lat, "lng": lng, "radius": radius_km, "year": ",".join(str(y) for y in years), "iconic_taxa": iconic_taxa,
              "quality_grade": quality_grade, "per_page": per_page}
    if locale:
        params["locale"] = locale
    return {"endpoint": "/observations/species_counts", "params": params, "url": f"{BASE}/observations/species_counts?{urlencode(params)}"}
