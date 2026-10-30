"""紅葉の入力(Open-Meteo の日別最低気温)を、キャッシュ → (許可されたときだけ)通信で集める。

- 通信は http_get(url) → (status, 本文) を外から注入できる(テストでは偽物)。紅葉の実通信は、取得の開始から終了まで 1 つの requests.Session(同じホストへの接続を使い回す。段階7c)。
  Session は session_factory で差し替えられる(テストでは偽物)。計測フックは requests.Session.request を数えるので、記録の via は "requests"。
  野鳥(birds_live / survey)は従来どおり default_http_get = urllib(変えない)。
- 通信しない --cache-only、通信する --live(呼び出し側が BIYORI_ALLOW_LIVE=1・--max-requests・計測フックを確認する)。
- 200 以外・読めない応答は即中止。ただし 502/503/504(一時的なサーバー障害。段階9b)だけは、live.retry.http の回数・待ち・Retry-After の規則で再試行する(429・500・その他は即中止)。
  通信エラー(応答が返らない)は、live.retry の回数・待ちで再試行する(再試行も 1 リクエスト)。読めない応答(ParseError)は実応答を _unparsed/ に保存して止める。
- 許可ホスト(config.yaml の live.allowed_hosts)以外の URL は送らない。"""
import json
import time
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit

from ..profiles import param
from . import ParseError, open_meteo
from .cache import Cache, cache_key

SOURCE = "Open-Meteo forecast API"


class LiveError(RuntimeError):
    """通信の中止(HTTP 200 以外、許可外ホストなど)。再試行しない。"""


def default_http_get(url, *, user_agent, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers.items())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace"), dict(e.headers.items())


class SessionGetter:
    """requests.Session を 1 つ持つ http_get(url) → (status, 本文, ヘッダー)。最初の通信のときに作り、close() で必ず閉じる(接続の使い回し)。
    タイムアウトは (connect, read) の 2 値(config.yaml の live.request_timeout)。HTTP の非 200 も例外にせず status で返す(再試行しない)。
    接続の切断・TLS・タイムアウトは requests.RequestException(= OSError)として上がり、_get_with_retry が通信エラーとして再試行する。"""

    def __init__(self, *, user_agent, connect_s, read_s, session_factory=None):
        self.headers = {"User-Agent": user_agent}
        self.timeout = (connect_s, read_s)
        self._factory = session_factory
        self.session = None

    def __call__(self, url):
        if self.session is None:
            if self._factory is not None:
                self.session = self._factory()
            else:
                import requests
                self.session = requests.Session()
        r = self.session.get(url, headers=self.headers, timeout=self.timeout)
        return r.status_code, r.content.decode("utf-8", errors="replace"), dict(r.headers.items())

    def get_bytes(self, url, max_bytes):
        """画像など、本文をバイト列のまま取る(段階29。fetch/inat_photos.py)。リダイレクトは追わない(行き先が許可外になりうる)。
        max_bytes を超えたら読むのをやめ、超えた分まで含むバイト列を返す(呼び出し側が大きすぎるとして捨てる)。→ (status, バイト列, ヘッダー)。"""
        if self.session is None:
            if self._factory is not None:
                self.session = self._factory()
            else:
                import requests
                self.session = requests.Session()
        r = self.session.get(url, headers=self.headers, timeout=self.timeout, stream=True, allow_redirects=False)
        try:
            data = b""
            for chunk in r.iter_content(chunk_size=None):
                data += chunk
                if len(data) > max_bytes:
                    break
        finally:
            r.close()
        return r.status_code, data, dict(r.headers.items())

    def close(self):
        s, self.session = self.session, None
        if s is not None:
            s.close()


def parse_retry_after(value, now):
    """Retry-After ヘッダ(秒数 または HTTP 日付)→ 待つ秒数(0 以上)。読めなければ None。HTTP 日付は now(タイムゾーンつき)との差。"""
    if value is None:
        return None
    v = str(value).strip()
    if v.isdigit():
        return int(v)
    try:
        dt = parsedate_to_datetime(v)
    except (TypeError, ValueError, IndexError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ref = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return max(0, int(round((dt - ref).total_seconds())))


def _header(headers, name):
    for k, v in (headers or {}).items():
        if str(k).lower() == name:
            return v
    return None


def _http_retry_plan(res, rep, attempt, http, now):
    """HTTP の応答 res(status, body, headers)を再試行するか。→ (待ち秒, None) または (None, 再試行しない理由 または None=対象外)。
    対象は http.statuses(502/503/504)だけ。回数は 1 リクエストあたり len(wait_s)、実行全体は max_total_per_run。Retry-After があれば min(値, retry_after_max_s)、超える指定は再試行しない。"""
    waits = list(http.get("wait_s") or [])[:http.get("max_retries", 0)]
    if res[0] not in set(http.get("statuses") or []):
        return None, None
    if attempt >= len(waits):
        return None, f"再試行を使い切った({len(waits)}回)"
    if sum(rep["http_retries"].values()) >= http.get("max_total_per_run", 0):
        return None, f"実行全体の再試行の上限 {http.get('max_total_per_run')} 回に達した"
    wait = waits[attempt]
    ra = parse_retry_after(_header(res[2] if len(res) > 2 else None, "retry-after"), now)
    if ra is not None:
        cap = http["retry_after_max_s"]
        if ra > cap:
            return None, f"Retry-After {ra} 秒が上限 {cap} 秒を超えるため再試行しない"
        wait = ra
    return wait, None


def _get_with_retry(get, url, rep, max_requests, site, sid, *, retry, sleep, now=None):
    """1 リクエストを送る。通信エラー(接続・TLS・タイムアウトなど。HTTP の応答が返らなかった場合)は live.retry の回数・待ちで再試行する。
    HTTP の 502/503/504 だけ、live.retry.http の規則で再試行する(429・500・その他の非 200 は再試行せず返す。呼び出し側が中止する)。
    再試行も 1 リクエストと数える(rep['requests'] と --max-requests)。再試行を使い切った・上限に達したときは、
    通信エラーはそのまま上げ、HTTP は最後の応答を返す(rep['http_stop_reason'] に理由を残す)。retry が無い設定は再試行なし。"""
    retry = retry or {}
    waits = list(retry.get("wait_s") or [])[:retry.get("max_retries", 0)]
    http = retry.get("http") or {}
    now = now or datetime.now(timezone.utc)
    attempt = net_attempt = 0
    while True:
        rep["requests"] += 1
        try:
            res = get(url)
        except urllib.error.HTTPError:
            raise
        except OSError as e:                                            # URLError・TimeoutError・ConnectionError・ssl.SSLError はすべて OSError
            if net_attempt >= len(waits) or rep["requests"] >= max_requests:
                raise
            rep["warnings"].append(f"{site['name']}({sid}): 通信エラー({type(e).__name__})のため {waits[net_attempt]:g} 秒後に再試行({net_attempt + 1}/{len(waits)}回目)")
            sleep(waits[net_attempt])
            net_attempt += 1
            continue
        if res[0] == HTTPStatus.OK or not http:
            if res[0] == HTTPStatus.OK and attempt:
                rep["http_recovered"].append({"status": rep["http_last_status"], "retries": attempt, "site": sid})
            return res
        wait, why = _http_retry_plan(res, rep, attempt, http, now)
        if wait is None:
            if why:
                rep["http_stop_reason"] = why
            return res
        if rep["requests"] >= max_requests:
            rep["http_stop_reason"] = f"--max-requests {max_requests} に達したため再試行しない"
            return res
        rep["http_retries"][str(res[0])] = rep["http_retries"].get(str(res[0]), 0) + 1
        rep["http_last_status"] = res[0]
        rep["warnings"].append(f"{site['name']}({sid}): HTTP {res[0]} のため {wait:g} 秒後に再試行({attempt + 1}/{len(http.get('wait_s') or [])}回目)")
        sleep(wait)
        attempt += 1


def needed_days(profile, dates, today, limits):
    """対象日の平均に必要な範囲: (対象日の最小 − (平均日数 − 1)) 〜 対象日の最大 を覆う past_days / forecast_days。"""
    win = param(profile, "mean_window_days")
    first, last = min(dates) - timedelta(days=win - 1), max(dates)
    past = max(0, (today - first).days)
    ahead = max(0, (last - today).days) + 1
    warnings = []
    if past > limits["max_past_days"]:
        warnings.append(f"必要な過去日数 {past} が上限 {limits['max_past_days']} を超えるため切り詰める")
        past = limits["max_past_days"]
    if ahead > limits["max_forecast_days"]:
        warnings.append(f"必要な予報日数 {ahead} が上限 {limits['max_forecast_days']} を超えるため切り詰める")
        ahead = limits["max_forecast_days"]
    return past, ahead, warnings


def fetch_temperatures(site_ids, sites, profile, dates, today, now, *, cache, cfg, http_get=None, live=False,
                       cache_only=False, max_requests=None, unparsed_dir=None, sleep=time.sleep, session_factory=None):
    """→ (inputs, report)。inputs は engine.run の入力(ikimono-inputs/1)。report は requests / cache_hits / misses / warnings。
    http_get を渡さないときは、この呼び出しの間 1 つの Session を共有し、終わったら(例外でも)閉じる。"""
    getter = None
    if http_get is None:
        t = cfg["live"]["request_timeout"]
        getter = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"], session_factory=session_factory)
    try:
        return _fetch_temperatures(site_ids, sites, profile, dates, today, now, cache=cache, cfg=cfg, http_get=http_get or getter, live=live,
                                   cache_only=cache_only, max_requests=max_requests, unparsed_dir=unparsed_dir, sleep=sleep)
    finally:
        if getter is not None:
            getter.close()


def _fetch_temperatures(site_ids, sites, profile, dates, today, now, *, cache, cfg, http_get, live, cache_only, max_requests, unparsed_dir, sleep):
    if live and cache_only:
        raise ValueError("--live と --cache-only は同時に指定できない")
    if not live and not cache_only:
        raise ValueError("--live か --cache-only のどちらかが必要")
    if live and (max_requests is None or max_requests < 1):
        raise ValueError("--live は明示的な --max-requests が必要")
    ttl = cfg["cache"]["ttl_s"]["open_meteo_forecast"]
    allowed = set(cfg["live"]["allowed_hosts"])
    past, ahead, warnings = needed_days(profile, dates, today, cfg["live"]["open_meteo"])
    temps, meta = {}, {}
    rep = {"requests": 0, "cache_hits": 0, "misses": [], "warnings": warnings, "query": {"past_days": past, "forecast_days": ahead},
           "http_retries": {}, "http_recovered": [], "http_last_status": None}
    for sid in site_ids:
        s = sites[sid]
        q = open_meteo.daily_query(lat=s["lat"], lon=s["lon"], past_days=past, forecast_days=ahead)
        entry, state = cache.get(q["url"], q["params"], now=now, ttl_s=ttl)
        if entry is not None:
            rep["cache_hits"] += 1
            body, fetched_at, from_cache = entry["body"], entry["fetched_at"], True
        elif cache_only:
            rep["misses"].append(sid)
            rep["warnings"].append(f"{s['name']}({sid}): キャッシュなし({'期限切れ' if state == 'expired' else '未取得'})。--cache-only なので通信しない")
            continue
        else:
            host = urlsplit(q["url"]).netloc
            if host not in allowed:
                raise LiveError(f"許可リスト外のホストには送らない: {host}")
            if rep["requests"] >= max_requests:
                rep["misses"].append(sid)
                rep["warnings"].append(f"{s['name']}({sid}): --max-requests {max_requests} に達したため取得しない")
                continue
            res = _get_with_retry(http_get, q["url"], rep, max_requests, s, sid, retry=cfg["live"].get("retry"), sleep=sleep, now=now)
            status, body = res[0], res[1]
            if status != HTTPStatus.OK:
                why = rep.get("http_stop_reason")
                raise LiveError(f"HTTP {status}: {s['name']}({sid})。" + (f"再試行して中止する({why})" if why else "再試行せず中止する"))
            try:
                open_meteo.parse_daily_tmin(json.loads(body))
            except (ValueError, ParseError) as e:                       # JSON でない・形が想定と違う
                saved = _save_unparsed(unparsed_dir, q["url"], status, body, now, str(e))
                raise ParseError(f"{s['name']}({sid}): 応答を読めない: {e}(実応答を保存: {saved})") from e
            fetched_at = now.isoformat(timespec="seconds")
            cache.put(url=q["url"], params=q["params"], body=body, source=SOURCE, fetched_at=fetched_at)
            from_cache = False
        temps[sid] = json.loads(body)
        meta[sid] = {"fetched_at": fetched_at, "url": q["url"], "source": SOURCE, "from_cache": from_cache}
    fetched = max((m["fetched_at"] for m in meta.values()), default=now.isoformat(timespec="seconds"))
    inputs = {"schema": "ikimono-inputs/1", "synthetic": False, "fetched_at": fetched, "temperatures": temps, "temperatures_meta": meta}
    return inputs, rep


def _save_unparsed(directory, url, status, body, now, error):
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{now.strftime('%Y%m%dT%H%M%S')}-{cache_key(url)}.json"
    p.write_text(json.dumps({"url": url, "status": status, "error": error, "body": body}, ensure_ascii=False, indent=1) + "\n",
                 encoding="utf-8", newline="\n")
    return str(p)
