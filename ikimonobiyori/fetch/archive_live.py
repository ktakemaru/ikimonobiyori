"""紅葉の答え合わせ(段階14)の過去の気温(Open-Meteo Historical API)を、キャッシュ → (許可されたときだけ)通信で集める。

- 問い合わせの一覧は backtest.build_requests が作る(通信しない)。ここは 1 件ずつ、キャッシュ → 通信。
- 許可ホストは config.yaml の live.allowed_hosts_by_subject.autumn_leaves_backtest だけ(archive-api.open-meteo.com。ユーザー承認 2026-10-22)。
- 通信の部品(http_get・再試行・LiveError)は fetch/live.py と同じ。HTTP の非 200 は再試行せず即中止(429 を含む。押し切らない)。通信エラー(応答が返らない)だけ live.retry で再試行する。
- 間隔は config.yaml の live.min_interval_s 以上を空ける(最初の通信の前は空けない)。
- 応答は形を確かめてから保存する。想定と違えば ParseError で止め、実応答を _unparsed/ に保存する(推測で補わない)。
- 通信のたびに、状態・所要時間・レート制限の応答ヘッダーだけを log に追記する(座標・本文は残さない)。call の消費の見積もりを見直すための記録。"""
import json
import time
from http import HTTPStatus
from urllib.parse import urlsplit

from . import ParseError, open_meteo
from .live import LiveError, _get_with_retry, _save_unparsed

SOURCE = "Open-Meteo Historical Weather API"
SUBJECT = "autumn_leaves_backtest"
EXPECTED_DAILY_KEYS = {"time", open_meteo.DAILY_VAR}


def check_shape(resp, req):
    """応答の形が想定どおりか。違えば ParseError(最初の 1 リクエストで、モデル名・変数名・形を確かめるための検査)。
    想定: daily が time と temperature_2m_min だけ。日数が期間と同じ。elevation を渡したときは応答の elevation が同じ。timezone は渡したもの。"""
    if not isinstance(resp, dict):
        raise ParseError("応答が JSON のオブジェクトでない")
    if resp.get("error"):
        raise ParseError(f"Open-Meteo がエラーを返した: {resp.get('reason')!r}")
    tmin = open_meteo.parse_daily_tmin(resp)                                  # daily.time / daily.temperature_2m_min の形・数値
    keys = set(resp["daily"])
    if keys != EXPECTED_DAILY_KEYS:
        raise ParseError(f"daily の項目が想定と違う: {sorted(keys)}(想定 {sorted(EXPECTED_DAILY_KEYS)})")
    if len(tmin) != req["expected_days"]:
        raise ParseError(f"日数が期間と違う: {len(tmin)}(想定 {req['expected_days']})")
    first, last = req["params"]["start_date"], req["params"]["end_date"]
    times = resp["daily"]["time"]
    if times[0] != first or times[-1] != last:
        raise ParseError(f"期間が違う: {times[0]}〜{times[-1]}(想定 {first}〜{last})")
    if resp.get("timezone") != req["params"]["timezone"]:
        raise ParseError(f"timezone が違う: {resp.get('timezone')!r}")
    if req["elevation"] is not None:
        got = resp.get("elevation")
        if isinstance(got, bool) or not isinstance(got, (int, float)) or float(got) != float(req["elevation"]):
            raise ParseError(f"応答の elevation が渡した標高と違う: {got!r}(渡した {req['elevation']})")
    return tmin


def load_cached(req, cache, *, now, ttl_s, allow_expired=False):
    """キャッシュから 1 件(通信しない)。→ (応答の dict, entry) または (None, None)。"""
    entry, _ = cache.get(req["url"], req["params"], now=now, ttl_s=ttl_s, allow_expired=allow_expired)
    return (json.loads(entry["body"]), entry) if entry is not None else (None, None)


def _rate_headers(headers):
    return {k: v for k, v in (headers or {}).items() if any(w in str(k).lower() for w in ("ratelimit", "rate-limit", "retry-after", "limit", "remaining"))}


def fetch_archive(reqs, *, cache, cfg, now, http_get=None, live=False, cache_only=False, max_requests=None, unparsed_dir=None,
                  sleep=time.sleep, log=None, session_factory=None):
    """→ (series_by_id, report)。series_by_id は {id: {日付: 気温 or None}}(取得できた件だけ)。report は requests / cache_hits / misses / warnings / calls。
    http_get を渡さないときは、この呼び出しの間 1 つの Session を共有し、終わったら(例外でも)閉じる。
    log は 1 通信ごとに呼ぶ関数 log(dict)(状態・所要時間・レート制限ヘッダー・id)。"""
    getter = None
    if live and http_get is None:
        from .live import SessionGetter
        t = cfg["live"]["request_timeout"]
        getter = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"], session_factory=session_factory)
    try:
        return _fetch_archive(reqs, cache=cache, cfg=cfg, now=now, http_get=http_get or getter, live=live, cache_only=cache_only,
                              max_requests=max_requests, unparsed_dir=unparsed_dir, sleep=sleep, log=log)
    finally:
        if getter is not None:
            getter.close()


def _fetch_archive(reqs, *, cache, cfg, now, http_get, live, cache_only, max_requests, unparsed_dir, sleep, log):
    if live and cache_only:
        raise ValueError("--live と --cache-only は同時に指定できない")
    if not live and not cache_only:
        raise ValueError("--live か --cache-only のどちらかが必要")
    if live and (max_requests is None or max_requests < 1):
        raise ValueError("--live は明示的な --max-requests が必要")
    ttl = cfg["cache"]["ttl_s"]["open_meteo_archive"]
    allowed = set(cfg["live"]["allowed_hosts_by_subject"][SUBJECT])
    interval = cfg["live"]["min_interval_s"]
    retry = dict(cfg["live"].get("retry") or {})
    retry["http"] = {}                                                       # HTTP の非 200 は再試行しない(429 で押し切らない)
    out = {}
    rep = {"requests": 0, "cache_hits": 0, "misses": [], "warnings": [], "http_retries": {}, "http_recovered": [], "http_last_status": None}
    last_sent = None
    for req in reqs:
        rid = req["id"]
        body, from_cache = None, False
        entry, state = cache.get(req["url"], req["params"], now=now, ttl_s=ttl)
        if entry is not None:
            body, from_cache = entry["body"], True
            rep["cache_hits"] += 1
        elif cache_only:
            rep["misses"].append(rid)
            rep["warnings"].append(f"{rid}: キャッシュなし({'期限切れ' if state == 'expired' else '未取得'})。--cache-only なので通信しない")
            continue
        else:
            host = urlsplit(req["url"]).netloc
            if host not in allowed:
                raise LiveError(f"許可リスト外のホストには送らない: {host}")
            if rep["requests"] >= max_requests:
                rep["misses"].append(rid)
                rep["warnings"].append(f"{rid}: --max-requests {max_requests} に達したため取得しない")
                continue
            if last_sent is not None:
                wait = interval - (time.monotonic() - last_sent)
                if wait > 0:
                    sleep(wait)
            t0 = time.monotonic()
            res = _get_with_retry(http_get, req["url"], rep, max_requests, {"name": rid}, rid, retry=retry, sleep=sleep, now=now)
            last_sent = time.monotonic()
            status, body = res[0], res[1]
            if log is not None:
                log({"id": rid, "status": status, "elapsed_s": round(last_sent - t0, 2), "rate_headers": _rate_headers(res[2] if len(res) > 2 else None),
                     "fetched_at": now.isoformat(timespec="seconds")})
            if status != HTTPStatus.OK:
                raise LiveError(f"HTTP {status}: {rid}。再試行せず中止する" + ("(429: レート制限。押し切らない)" if status == HTTPStatus.TOO_MANY_REQUESTS else ""))
            try:
                check_shape(json.loads(body), req)
            except (ValueError, ParseError) as e:                             # JSON でない・形が想定と違う
                saved = _save_unparsed(unparsed_dir, req["url"], status, body, now, str(e))
                raise ParseError(f"{rid}: 応答を読めない: {e}(実応答を保存: {saved})") from e
            cache.put(url=req["url"], params=req["params"], body=body, source=SOURCE, fetched_at=now.isoformat(timespec="seconds"))
        if from_cache:
            try:
                check_shape(json.loads(body), req)                            # キャッシュも同じ検査を通す
            except (ValueError, ParseError) as e:
                raise ParseError(f"{rid}: キャッシュの応答を読めない: {e}") from e
        out[rid] = open_meteo.parse_daily_tmin(json.loads(body))
    return out, rep
