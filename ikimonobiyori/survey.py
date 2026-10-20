"""野鳥のデータ密度の調査(段階6c)。閾値・窓・半径・bird_areas は変えず、場所ごとの観察総数を測るだけ。

- 場所ごとに /observations の total_results(= 条件に合う観察の件数)を取る。per_page=1: 返る観察 1 件の中身(観察者・写真など)は読まず捨てる。
  (per_page=0 を先に試して 4xx なら 1 に切り替える案があったが、計測フックが 4xx で即中止するため、通信前に per_page=1 に決める)
- 最後に軽井沢周辺の species_counts で、日本語名(locale=ja)が取れるかを確かめる(per_page=10)。
- 座標は丸めた値だけ。順番に・間隔 min_interval_s 以上・200 以外は即中止(再試行しない)・上限超過は即中止。"""
import json
import time
from http import HTTPStatus
from urllib.parse import urlsplit

import yaml

from .fetch import ParseError, inaturalist
from .fetch.live import LiveError, _save_unparsed, default_http_get
from .paths import DATA_FILES_DIR

SURVEY_PATH = DATA_FILES_DIR / "density_survey.yaml"
SOURCE = "iNaturalist API"


def load_survey(path=None):
    return yaml.safe_load((path or SURVEY_PATH).read_text(encoding="utf-8"))


def window_queries(survey):
    """window_survey.yaml → [(kind, place, query, spec)]。"""
    c, places, out = survey["conditions"], {p["id"]: p for p in survey["places"]}, []
    for spec in survey["queries"]:
        pl = places[spec["place"]]
        ep = "/observations" if spec["kind"] == "total" else "/observations/species_counts"
        q = inaturalist.observations_window_query(lat=pl["lat"], lng=pl["lon"], radius_km=c["radius_km"], years=c["years"], month=c["month"],
                                                  days=spec.get("days", c["days"]), iconic_taxa=c["iconic_taxa"], quality_grade=c["quality_grade"],
                                                  per_page=spec.get("per_page", 1), endpoint=ep, locale=spec.get("locale"))
        out.append((spec["kind"], pl, q, spec))
    return out


def planned_queries(survey, per_page_total=1):
    if survey.get("schema") == "ikimono-window-survey/1":
        return window_queries(survey)
    c = survey["conditions"]
    qs = []
    for pl in survey["places"]:
        qs.append(("total", pl, inaturalist.observations_total_query(lat=pl["lat"], lng=pl["lon"], radius_km=c["radius_km"], months=c["months"],
                                                                     iconic_taxa=c["iconic_taxa"], quality_grade=c["quality_grade"],
                                                                     per_page=per_page_total)))
    lc = survey["locale_check"]
    pl = next(p for p in survey["places"] if p["id"] == lc["place"])
    qs.append(("locale", pl, inaturalist.species_counts_months_query(
        lat=pl["lat"], lng=pl["lon"], radius_km=c["radius_km"], months=c["months"], iconic_taxa=c["iconic_taxa"],
        quality_grade=c["quality_grade"], per_page=lc["per_page"], locale=lc["locale"])))
    return [(k, p, q, {}) for k, p, q in qs]


def run_density_survey(survey, now, *, cfg, cache, http_get=None, live=False, cache_only=False, max_requests=None, unparsed_dir=None,
                       sleep=time.sleep):
    """→ results(dict)。cache は ikimonobiyori.fetch.cache.Cache。"""
    if live and cache_only:
        raise ValueError("--live と --cache-only は同時に指定できない")
    if not live and not cache_only:
        raise ValueError("--live か --cache-only のどちらかが必要")
    if live and (max_requests is None or max_requests < 1):
        raise ValueError("--live は明示的な --max-requests が必要")
    allowed = set(cfg["live"]["allowed_hosts_by_subject"]["birds"])
    ttl = cfg["cache"]["ttl_s"]["inaturalist_species_counts"]
    out = {"requests": 0, "cache_hits": 0, "places": [], "locale": None, "warnings": [], "rate_headers": {},
           "conditions": survey["conditions"], "ran_at": now.isoformat(timespec="seconds")}
    last = None
    out["items"], out["gate"] = [], None
    for kind, pl, q, spec in planned_queries(survey):
        entry, _ = cache.get(q["url"], q["params"], now=now, ttl_s=ttl)
        if entry is not None:
            out["cache_hits"] += 1
            body, fetched_at = entry["body"], entry["fetched_at"]
        elif cache_only:
            out["warnings"].append(f"{pl['name']} ({kind}): キャッシュなし")
            continue
        else:
            host = urlsplit(q["url"]).netloc
            if host not in allowed:
                raise LiveError(f"許可リスト外のホストには送らない: {host}")
            if out["requests"] >= max_requests:
                out["warnings"].append(f"{pl['name']} ({kind}): --max-requests {max_requests} に達したため取得しない")
                continue
            if last is not None:
                wait = cfg["live"]["min_interval_s"] - (time.monotonic() - last)
                if wait > 0:
                    sleep(wait)
            out["requests"] += 1
            last = time.monotonic()
            res = (http_get or (lambda u: default_http_get(u, user_agent=cfg["live"]["user_agent"], timeout=cfg["live"]["timeout_s"])))(q["url"])
            status, raw = res[0], res[1]
            headers = res[2] if len(res) > 2 else {}
            out["rate_headers"] = {k: v for k, v in headers.items() if k.lower().startswith(("x-ratelimit", "retry-after"))} or out["rate_headers"]
            if status != HTTPStatus.OK:
                raise LiveError(f"HTTP {status}: {pl['name']} ({kind})。再試行せず中止する")
            try:
                parsed = json.loads(raw)
                if kind == "total":
                    inaturalist.parse_observations_total(parsed)
                else:
                    inaturalist.parse_species_counts(parsed)
            except (ValueError, ParseError, AttributeError) as e:
                saved = _save_unparsed(unparsed_dir, q["url"], status, raw, now, str(e))
                raise ParseError(f"{pl['name']} ({kind}): 応答を読めない: {e}(実応答を保存: {saved})") from e
            if kind == "total":                                   # 観察者・写真などを含みうる results は保存しない。件数だけ
                total, n = inaturalist.parse_observations_total(parsed)
                body = json.dumps({"total_results": total, "page": parsed.get("page"), "per_page": parsed.get("per_page"), "returned": n})
            else:
                from .fetch.birds_live import minimize_species_counts
                body = json.dumps(minimize_species_counts(parsed)[0], ensure_ascii=False)
            fetched_at = now.isoformat(timespec="seconds")
            cache.put(url=q["url"], params=q["params"], body=body, source=SOURCE, fetched_at=fetched_at)
        r = json.loads(body)
        if kind == "total":
            out["items"].append({"role": spec.get("role"), "id": pl["id"], "name": pl["name"], "lat": pl["lat"], "lon": pl["lon"], "total_results": r["total_results"],
                                 "days": q["params"].get("day"), "years": q["params"].get("year"), "url": q["url"], "fetched_at": fetched_at})
            if "expect_total" in spec:
                ok = r["total_results"] == spec["expect_total"]
                out["gate"] = {"expected": spec["expect_total"], "actual": r["total_results"], "match": ok}
                if not ok:
                    out["warnings"].append(f"{pl['name']}: 同値性の確認が一致しない(期待 {spec['expect_total']}、実測 {r['total_results']})。残りは実行せず中止")
                    break
            out["places"].append({"id": pl["id"], "name": pl["name"], "lat": pl["lat"], "lon": pl["lon"], "total_results": r["total_results"],
                                  "returned": r["returned"], "per_page": r["per_page"], "url": q["url"], "fetched_at": fetched_at})
        else:
            rows, total = inaturalist.parse_species_counts(r)
            out["locale"] = {"role": spec.get("role"), "place": pl["name"], "url": q["url"], "total_results": total, "returned": len(rows), "fetched_at": fetched_at,
                             "names": [{"scientific": x["name"], "common_name": x["common_name"], "count": x["count"]} for x in rows]}
    return out
