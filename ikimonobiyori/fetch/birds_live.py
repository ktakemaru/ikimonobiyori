"""野鳥(iNaturalist species_counts)の入力を、キャッシュ → (許可されたときだけ)通信で集める。段階6b-2。

- 集計値だけを保存する: 種ごとの件数と分類名。写真・観察者の情報は取得しても保存しない(minimize_species_counts)。
- 問い合わせ・キャッシュ・出典 URL・ログには、丸めた座標(area_10km = 小数1桁)だけを使う。
- 1リクエストずつ順番に、間隔は min_interval_s 以上(30リクエスト/分以下)。200 以外・読めない応答は即中止(再試行しない)。
- 読めない応答(ParseError)は実応答を _unparsed/ に保存して止める。許可ホスト以外には送らない。"""
import json
import time
from datetime import datetime, timedelta
from http import HTTPStatus
from urllib.parse import urlsplit

from ..profiles import param
from . import ParseError, inaturalist
from .live import LiveError, _save_unparsed, default_http_get
from .live import received_at as _received_at

SOURCE_INAT = "iNaturalist API"
RATE_HEADER_PREFIXES = ("x-ratelimit", "retry-after")


def received_at(now, clock=None):
    """応答を受け取った時刻(オフセットつき ISO 8601)。clock は時刻を返す関数(テスト用)。既定は実際の時計を now と同じ時間帯で。
    段階36: 以前は判定の基準の時刻 now(--now)を入れていたため、--now に実際より後の時刻を渡すと取得時刻が未来になった。
    段階37: 紅葉の Open-Meteo(fetch/live.py)と同じ関数を使う。"""
    return _received_at(now, clock)


def minimize_species_counts(resp):
    """保存・キャッシュするのは集計値だけ。戻り値: (最小化した応答, 元の応答にあった項目名の一覧。形の記録用)"""
    seen = {"top": sorted(resp.keys()), "result": [], "taxon": []}
    out = {"total_results": resp.get("total_results"), "page": resp.get("page"), "per_page": resp.get("per_page"), "results": []}
    for r in resp.get("results", []):
        t = r.get("taxon") or {}
        seen["result"] = sorted(set(seen["result"]) | set(r.keys()))
        seen["taxon"] = sorted(set(seen["taxon"]) | set(t.keys()))
        out["results"].append({"count": r.get("count"),
                               "taxon": {k: t.get(k) for k in ("id", "name", "preferred_common_name", "rank", "iconic_taxon_name")}})
    return out, seen


def window_days_by_month(d, window_weeks):
    """対象日 d の前後 window_weeks 週の日付を月ごとにまとめる。→ [(月, [日, ...])](月をまたぐ窓は 2 つ)。"""
    span = window_weeks * 7
    by = {}
    for k in range(-span, span + 1):
        x = d + timedelta(days=k)
        by.setdefault(x.month, []).append(x.day)
    return sorted(by.items())


def bird_queries(area, dates, profile, per_page, per_year=False):
    """問い合わせの一覧(通信しない)。座標は area の丸めた値だけ。[(日付, 年またはキー, query)]。
    既定: 年の複数指定(year=過去N年, month, day=窓の日)で、1場所×1日×(窓がまたぐ月の数)リクエスト。キーは 'multi:<月>'。
    per_year=True: 従来の1年ずつ(1場所×1日×N年)。非公式の書き方なので、検証用に残す(docs/ikimonobiyori-research.md §14)。"""
    qs = []
    if not per_year:
        n = param(profile, "history_years")
        for d in dates:
            years = sorted(d.year - k for k in range(1, n + 1))
            for month, days in window_days_by_month(d, param(profile, "window_weeks")):
                qs.append((d, f"multi:{month}", inaturalist.observations_window_query(
                    lat=area["lat"], lng=area["lon"], radius_km=area["radius_km"], years=years, month=month, days=days,
                    iconic_taxa=param(profile, "iconic_taxa"), quality_grade=param(profile, "quality_grade"), per_page=per_page,
                    endpoint="/observations/species_counts", locale=inaturalist.LOCALE)))
        return qs
    for d in dates:
        for k in range(1, param(profile, "history_years") + 1):
            qs.append((d, d.year - k, inaturalist.species_counts_query(
                lat=area["lat"], lng=area["lon"], radius_km=area["radius_km"], center=d, year=d.year - k,
                window_weeks=param(profile, "window_weeks"), iconic_taxa=param(profile, "iconic_taxa"),
                quality_grade=param(profile, "quality_grade"), per_page=per_page)))
    return qs


def fetch_bird_counts(area, dates, profile, now, *, cache, cfg, http_get=None, live=False, cache_only=False, max_requests=None,
                      unparsed_dir=None, sleep=time.sleep, shape_check=False, per_year=False, clock=None):
    """→ (inputs, report)。inputs は engine.run の入力(ikimono-inputs/1)。
    段階36: 取得時刻(fetched_at)は応答を受け取った時刻(clock。既定は実際の時計)。now は判定の基準の時刻(キャッシュの期限など)で、取得時刻には使わない。
    shape_check=True: 1日分・1年分の窓を per_page を小さくして1リクエストだけ(形の確認)。report['shape'] に最小化した応答と元の項目名。"""
    if live and cache_only:
        raise ValueError("--live と --cache-only は同時に指定できない")
    if not live and not cache_only:
        raise ValueError("--live か --cache-only のどちらかが必要")
    if live and (max_requests is None or max_requests < 1):
        raise ValueError("--live は明示的な --max-requests が必要")
    from ..engine import round_coord
    prec = area.get("location_precision") or profile["care"]["location_precision"]
    # 入力がたとえ丸め前の座標でも、問い合わせ・キャッシュ・URL・ログには丸めた座標だけを使う
    area = dict(area, lat=round_coord(area["lat"], prec), lon=round_coord(area["lon"], prec))
    allowed = set(cfg["live"]["allowed_hosts_by_subject"]["birds"])
    ttl = cfg["cache"]["ttl_s"]["inaturalist_species_counts"]
    per_page = cfg["live"]["inaturalist"]["shape_check_per_page" if shape_check else "per_page"]
    qs = bird_queries(area, dates, profile, per_page, per_year=per_year)
    if shape_check:
        qs = qs[:1]
    rep = {"requests": 0, "cache_hits": 0, "misses": [], "warnings": [], "rate_headers": {}, "shape": None, "truncated": []}
    years, urls, fetched = {}, {}, {}
    last_request_at = None
    for d, year, q in qs:
        key = (d.isoformat(), str(year))
        lbl = f"{year}年" if isinstance(year, int) else "過去年の複数指定(" + str(year).split(":")[-1] + "月)"
        entry, state = cache.get(q["url"], q["params"], now=now, ttl_s=ttl)
        if entry is not None:
            rep["cache_hits"] += 1
            body, fetched_at = entry["body"], entry["fetched_at"]
        elif cache_only:
            rep["misses"].append(key)
            rep["warnings"].append(f"{area['name']} {key[0]} {lbl}: キャッシュなし。--cache-only なので通信しない")
            continue
        else:
            host = urlsplit(q["url"]).netloc
            if host not in allowed:
                raise LiveError(f"許可リスト外のホストには送らない: {host}")
            if rep["requests"] >= max_requests:
                rep["misses"].append(key)
                rep["warnings"].append(f"{area['name']} {key[0]} {lbl}: --max-requests {max_requests} に達したため取得しない")
                continue
            if last_request_at is not None:                           # 1リクエストずつ・間隔を空ける
                wait = cfg["live"]["min_interval_s"] - (time.monotonic() - last_request_at)
                if wait > 0:
                    sleep(wait)
            rep["requests"] += 1
            last_request_at = time.monotonic()
            res = (http_get or (lambda u: default_http_get(u, user_agent=cfg["live"]["user_agent"], timeout=cfg["live"]["timeout_s"])))(q["url"])
            status, raw = res[0], res[1]
            headers = res[2] if len(res) > 2 else {}
            rep["rate_headers"] = {k: v for k, v in headers.items() if k.lower().startswith(RATE_HEADER_PREFIXES)} or rep["rate_headers"]
            if status != HTTPStatus.OK:
                raise LiveError(f"HTTP {status}: {area['name']} {key[0]} {lbl}。再試行せず中止する")
            try:
                parsed = json.loads(raw)
                inaturalist.parse_species_counts(parsed)
            except (ValueError, ParseError, AttributeError) as e:
                saved = _save_unparsed(unparsed_dir, q["url"], status, raw, now, str(e))
                raise ParseError(f"{area['name']} {key[0]} {lbl}: 応答を読めない: {e}(実応答を保存: {saved})") from e
            mini, seen = minimize_species_counts(parsed)
            body = json.dumps(mini, ensure_ascii=False)
            fetched_at = received_at(now, clock)                       # 段階36: --now ではなく、応答を受け取った時刻
            cache.put(url=q["url"], params=q["params"], body=body, source=SOURCE_INAT, fetched_at=fetched_at)
            if shape_check:
                rep["shape"] = {"url": q["url"], "status": int(status), "fetched_at": fetched_at, "headers_seen": sorted(headers.keys()),
                                "rate_headers": rep["rate_headers"], "fields_seen": seen, "minimized": mini,
                                "bytes": len(raw.encode("utf-8"))}
        resp = json.loads(body)
        rows, total = inaturalist.parse_species_counts(resp)
        if total is not None and total > len(rows):
            rep["truncated"].append(key)
            rep["warnings"].append(f"{area['name']} {key[0]} {lbl}: 種数 {total} が per_page={per_page} を超えるため一部のみ(頻度の分母が小さく出る)")
        years.setdefault(key[0], {})[key[1]] = resp
        urls.setdefault(key[0], {})[key[1]] = q["url"]
        fetched.setdefault(key[0], {})[key[1]] = fetched_at
    ny = param(profile, "history_years")
    qlist = [{"date": d, "years": years[d], "urls": urls[d], "fetched_at_by_year": fetched[d], "latest_observations": None,
              "years_covered": [datetime.fromisoformat(d).year - k for k in range(1, ny + 1)]}
             for d in sorted(years)]
    allf = [f for d in fetched.values() for f in d.values()]
    inputs = {"schema": "ikimono-inputs/1", "synthetic": False,
              "fetched_at": max(allf) if allf else now.isoformat(timespec="seconds"),
              "birds": [{"area": {**({"id": area["id"]} if area.get("id") else {}), "name": area["name"], "lat": area["lat"], "lon": area["lon"], "radius_km": area["radius_km"]},
                         "queries": qlist}]}
    return inputs, rep
