"""取得層のテストが使う偽物と共通の値(通信しない)。biyori-hub の tests/test_ikimono_live.py の部品と同じ値。"""
import json
import tempfile
from datetime import datetime, timedelta, timezone

import helpers  # noqa: F401  (通信禁止)
from ikimonobiyori import profiles as ip
from ikimonobiyori.config import load_config
from ikimonobiyori.fetch import live

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 14, 22, 0, tzinfo=JST)
CFG = load_config()
PROFS = ip.load_profiles()
SITES, _ = ip.load_sites()
AUT = PROFS["autumn_leaves"]
DATES = [datetime(2026, 10, 17).date(), datetime(2026, 10, 18).date()]


def resp(base=5.0, start="2026-10-08", days=12):
    """Open-Meteo の日最低気温の応答の形(合成)。"""
    t0 = datetime.fromisoformat(start)
    return {"latitude": 0, "longitude": 0, "daily": {"time": [(t0 + timedelta(days=i)).date().isoformat() for i in range(days)],
                                                   "temperature_2m_min": [base + (i % 3) * 0.5 for i in range(days)]}}


class FakeHttp:
    def __init__(self, status=200, body=None):
        self.calls, self.status, self.body = [], status, body

    def __call__(self, url):
        self.calls.append(url)
        return self.status, self.body if self.body is not None else json.dumps(resp())


def fetch(cache, http, *, live_=True, cache_only=False, max_requests=10, sites=("m001", "m002", "m013"), now=NOW, unparsed=None):
    return live.fetch_temperatures(list(sites), SITES, AUT, DATES, now.date(), now, cache=cache, cfg=CFG, http_get=http, live=live_,
                                   cache_only=cache_only, max_requests=max_requests if live_ else None,
                                   unparsed_dir=unparsed or tempfile.mkdtemp(),
                                   clock=lambda: now)                  # 段階37: 取得時刻は応答を受け取った時刻。テストは時計を now に合わせる
