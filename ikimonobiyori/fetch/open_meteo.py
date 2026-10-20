"""Open-Meteo の日別最低気温の応答パーサーと問い合わせの組み立て(通信しない)。

応答の形(docs/ikimonobiyori-research.md §5。https://open-meteo.com/en/docs):
  {"latitude": .., "longitude": .., "daily": {"time": ["2026-10-01", ...], "temperature_2m_min": [8.1, null, ...]}}
欠損(null)は 0 で埋めず None のまま保つ。形が違えば ParseError。"""
from urllib.parse import urlencode

from . import ParseError

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VAR = "temperature_2m_min"


def daily_query(*, lat, lon, past_days, forecast_days):
    params = {"latitude": lat, "longitude": lon, "daily": DAILY_VAR, "past_days": past_days,
              "forecast_days": forecast_days, "timezone": "Asia/Tokyo"}
    return {"endpoint": "/v1/forecast", "params": params, "url": f"{FORECAST_URL}?{urlencode(params)}"}


def parse_daily_tmin(resp):
    """→ {"YYYY-MM-DD": float|None}"""
    d = resp.get("daily") if isinstance(resp, dict) else None
    if not isinstance(d, dict) or not isinstance(d.get("time"), list) or not isinstance(d.get(DAILY_VAR), list):
        raise ParseError(f"daily.time / daily.{DAILY_VAR} (配列) がない")
    if len(d["time"]) != len(d[DAILY_VAR]):
        raise ParseError("daily.time と daily.temperature_2m_min の長さが違う")
    out = {}
    for t, v in zip(d["time"], d[DAILY_VAR]):
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            raise ParseError(f"気温が数値でない: {v!r}")
        out[t] = v
    return out
