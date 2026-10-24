"""公式のスポットのページの、地図の埋め込みの座標だけを読む小さなコード(段階19 の続き。docs/stage19-decisions.md D-17)。

- 決定(ユーザー承認 2026-10-24): 日光市観光協会・箱根町観光協会のスポットのページから、地図の埋め込み(iframe の src)の座標の数字の組だけを読む。
  この 2 つは、コードで読む承認が済んでいるホスト(config.yaml の live.allowed_hosts_by_subject.autumn_leaves_status)。ほかのホストは足さない。
- 読むのは iframe の src(または data-src)の URL の数字の組だけ: q=緯度,経度(ll・center・query も同じ。座標でない q は読まない)、
  または pb= の中の !2d経度!3d緯度。**HTML・本文はどこにも保存しない**(返すのも数字・読めた方法・状態だけ)。キャッシュもしない。
- 数字が見つからないページは「座標なし」とし、推測しない。地図が複数あって座標が食い違うときは「複数」とし、選ばない。
  日本の範囲(config.yaml の live.spot_coords)に入らない数字は読まない。
- 通信は biyori-hub の計測フックの下だけ(呼び出し側 sources.py の spot-coords が BIYORI_ALLOW_LIVE=1・--max-requests・BIYORI_REQ_LOG を確かめる)。
  先に robots.txt(ホストごとに 1 回)を読み、読んでよいページだけを読む。リクエストの間は config.yaml の live.min_interval_s(2 秒)以上空ける。
  HTTP 429 などの 4xx/5xx が返ったら、そこで止める(残りは読まない)。"""
import re
import time
from html.parser import HTMLParser
from http import HTTPStatus
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.robotparser import RobotFileParser

from .live import LiveError
from .status_pages import SUBJECT_HOSTS, robots_url

MAP_HOSTS = ("www.google.com", "google.com", "maps.google.com", "www.google.co.jp", "maps.google.co.jp")      # 地図の埋め込みの配信元(iframe の src のホスト)
PAIR_KEYS = ("q", "query", "ll", "center")                                                                        # 「緯度,経度」が入りうるパラメータ(優先順)
PAIR_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
PB_RE = re.compile(r"!2d(-?\d+(?:\.\d+)?)!3d(-?\d+(?:\.\d+)?)")


class _Frames(HTMLParser):
    """iframe の src・data-src だけを集める。それ以外の属性・本文は見ない(保存もしない)。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag == "iframe":
            a = dict(attrs)
            for k in ("src", "data-src", "data-lazy-src"):
                if a.get(k):
                    self.urls.append(a[k])


def frame_urls(html):
    p = _Frames()
    p.feed(html)
    p.close()
    return p.urls


def pair_from_url(url, bounds):
    """地図の埋め込みの URL → (緯度, 経度, 読んだ方法)か None。地図の配信元でない URL・座標でない q(住所の文字列)・範囲外の数字は None。"""
    sp = urlsplit(url if "//" in url else "https:" + url)
    if sp.netloc not in MAP_HOSTS or ("maps" not in sp.path and "maps" not in sp.netloc):
        return None
    qs = parse_qs(sp.query)
    cands = []
    for k in PAIR_KEYS:
        for v in qs.get(k, []):
            m = PAIR_RE.match(unquote(v))
            if m:
                cands.append((float(m[1]), float(m[2]), k))
    for v in qs.get("pb", []):
        m = PB_RE.search(unquote(v))
        if m:
            cands.append((float(m[2]), float(m[1]), "pb"))                      # !2d は経度、!3d は緯度
    for lat, lon, how in cands:
        if bounds["lat"][0] <= lat <= bounds["lat"][1] and bounds["lon"][0] <= lon <= bounds["lon"][1]:
            return lat, lon, how
    return None


def parse_page(html, bounds):
    """ページの HTML → 結果の辞書(数字・読んだ方法・状態だけ)。
    status: ok(数字の組が 1 つ。または全部同じ)/ no_coordinates(地図の埋め込みがない・座標がない)/ ambiguous(座標の違う地図が複数。選ばない)。"""
    frames = frame_urls(html)
    found = [p for u in frames if (p := pair_from_url(u, bounds))]
    pairs = {(lat, lon) for lat, lon, _ in found}
    res = {"frames": len(frames), "frames_with_coordinates": len(found)}
    if not pairs:
        return {**res, "status": "no_coordinates"}
    if len(pairs) > 1:
        return {**res, "status": "ambiguous", "candidates": sorted(pairs)}
    lat, lon = next(iter(pairs))
    return {**res, "status": "ok", "lat": lat, "lon": lon, "pattern": found[0][2]}


def read_spots(urls, *, http_get, cfg, max_requests, sleep=time.sleep, progress=None):
    """スポットのページ(許可ホストだけ)の座標を読む。→ {requests, results: [{url, status, ...}], stopped}。
    ホストごとに robots.txt を先に 1 回読む(読めない・拒否ならそのホストのページは読まない)。リクエストの間は live.min_interval_s 以上空ける。
    4xx/5xx(429 を含む)が返ったら、残りを読まずに止める(stopped に理由)。許可外のホストは、1 件も送らずに ValueError。
    progress は結果が 1 件できるたびに呼ばれる(計測フックが途中で中止しても、読めた分を失わないため。数字・状態だけを渡す)。"""
    allowed = set(cfg["live"]["allowed_hosts_by_subject"][SUBJECT_HOSTS])
    bad = sorted({urlsplit(u).netloc for u in urls} - allowed)
    if bad:
        raise ValueError(f"許可リスト外のホストは読まない: {bad}(読めるのは {sorted(allowed)} だけ)")
    bounds, gap, ua = cfg["live"]["spot_coords"], cfg["live"]["min_interval_s"], cfg["live"]["user_agent"]
    rep = {"requests": 0, "results": [], "stopped": None}
    robots, last = {}, [None]

    def get(u):
        if rep["requests"] >= max_requests:
            raise LiveError(f"--max-requests {max_requests} に達した")
        if last[0] is not None:
            sleep(gap)
        last[0] = u
        rep["requests"] += 1
        res = http_get(u)
        return res[0], res[1]

    for u in urls:
        host = urlsplit(u).netloc
        try:
            if host not in robots:
                st, body = get(robots_url(u))
                if st != HTTPStatus.OK:
                    robots[host] = f"robots.txt を確かめられない(HTTP {st})。安全側で読まない"
                    if st >= HTTPStatus.BAD_REQUEST and st != HTTPStatus.NOT_FOUND:
                        rep["stopped"] = f"HTTP {st}(robots.txt)。残りを読まない"
                        break
                else:
                    rp = RobotFileParser()
                    rp.parse(body.splitlines())
                    robots[host] = rp
            if isinstance(robots[host], str):
                rep["results"].append({"url": u, "status": "not_read", "reason": robots[host]})
                progress and progress(rep["results"][-1])
                continue
            if not robots[host].can_fetch(ua, u):
                rep["results"].append({"url": u, "status": "not_read", "reason": "robots.txt が拒否している。読まない"})
                progress and progress(rep["results"][-1])
                continue
            st, html = get(u)
        except LiveError as e:
            rep["stopped"] = str(e)
            break
        if st != HTTPStatus.OK:
            rep["results"].append({"url": u, "status": f"http_{int(st)}"})
            progress and progress(rep["results"][-1])
            if st >= HTTPStatus.BAD_REQUEST:
                rep["stopped"] = f"HTTP {int(st)}。残りを読まない"
                break
            continue
        rep["results"].append({"url": u, **parse_page(html, bounds)})                  # HTML は、ここで捨てる(返さない・残さない)
        progress and progress(rep["results"][-1])
    return rep
