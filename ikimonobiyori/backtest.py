"""紅葉の答え合わせ(段階14 の準備。docs/validation-plan.md)のうち、通信しない部分: 判定・比べ方・集計・レポート。純粋・決定論。
- 予測日: v0 と同じ判定(methods/temperature_progression の mean_tmin・stage_for、閾値はプロファイルから)を過去の各日に当てはめ、
  段階が初めて target_stage(既定 peak = 見頃)になった日。
- 比べ方: 予測日 − 観測日(日数。正 = 予測が遅い)。中央値・ばらつき・地点ごと・年ごと。
- 許容の日数(±N 日)は呼び出し側が渡す。合格基準はここでは決めない(ユーザーが結果を見る前に決める)。
実通信(Open-Meteo の過去の気温の取得)は段階14 で、ユーザーの承認の後に書く。ここには問い合わせの組み立て(通信しない)だけを置く。"""
import statistics
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

from .methods.temperature_progression import mean_tmin, stage_for
from .profiles import param

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"   # https://open-meteo.com/en/docs/historical-weather-api(config.yaml の許可ホストには未登録。段階14 で承認が要る)


def archive_query(*, lat, lon, start_date, end_date, elevation=None, daily="temperature_2m_min", timezone="Asia/Tokyo"):
    """Historical API の問い合わせ(通信しない)。elevation を渡すと、その標高でダウンスケールする(None なら渡さない = Open-Meteo の 90 m 標高データ)。"""
    params = {"latitude": lat, "longitude": lon, "start_date": start_date, "end_date": end_date, "daily": daily, "timezone": timezone}
    if elevation is not None:
        params["elevation"] = elevation
    return {"endpoint": "/v1/archive", "params": params, "url": f"{ARCHIVE_URL}?{urlencode(params)}"}


def season_range(profile, year):
    """プロファイルの season.months の最初の月の1日 〜 最後の月の末日(その年)。"""
    months = profile["season"]["months"]
    first = date(year, min(months), 1)
    nxt = date(year + 1, 1, 1) if max(months) == 12 else date(year, max(months) + 1, 1)
    return first, nxt - timedelta(days=1)


def fetch_range(profile, year):
    """予測に要る気温の範囲: 季節の最初の日の (mean_window_days − 1) 日前 〜 季節の最後の日。"""
    first, last = season_range(profile, year)
    return first - timedelta(days=param(profile, "mean_window_days") - 1), last


def predict(series, profile, year, *, target_stage="peak"):
    """→ {"date": 段階が初めて target_stage になった日 or None, "first": 段階ごとの最初の日, "days": 判定した日数, "missing_days": 平均が出せなかった日数}。
    平均が出せない日(欠損)は飛ばして数える(0 で埋めない)。"""
    start, adv, win = param(profile, "start_min_temp_c"), param(profile, "advance_min_temp_c"), param(profile, "mean_window_days")
    first, last = season_range(profile, year)
    seen, missing, n = {}, 0, 0
    d = first
    while d <= last:
        n += 1
        st = stage_for(mean_tmin(series, d, win), start=start, advance=adv)
        if st is None:
            missing += 1
        elif st not in seen:
            seen[st] = d
        d += timedelta(days=1)
    hit = seen.get(target_stage)
    return {"date": hit.isoformat() if hit else None, "first": {k: v.isoformat() for k, v in seen.items()}, "days": n, "missing_days": missing}


def pair(station, year, predicted, observed):
    """1 件の比較。差 = 予測 − 観測(日数)。どちらかが None なら差も None。"""
    diff = None
    if predicted and observed:
        diff = (date.fromisoformat(predicted) - date.fromisoformat(observed)).days
    return {"station": station, "year": year, "predicted": predicted, "observed": observed, "diff_days": diff}


def _stats(diffs, tolerances):
    if not diffs:
        return {"n": 0, "median": None, "mean": None, "stdev": None, "mad": None, "min": None, "max": None, "quartiles": None,
                "within": {str(t): None for t in tolerances}}
    med = statistics.median(diffs)
    return {"n": len(diffs), "median": med, "mean": statistics.fmean(diffs),
            "stdev": statistics.stdev(diffs) if len(diffs) > 1 else None,
            "mad": statistics.median([abs(x - med) for x in diffs]),
            "min": min(diffs), "max": max(diffs),
            "quartiles": statistics.quantiles(diffs, n=4, method="inclusive") if len(diffs) > 1 else None,
            "within": {str(t): sum(abs(x) <= t for x in diffs) / len(diffs) for t in tolerances}}


def aggregate(pairs, tolerances=()):
    """差の分布。全体・地点ごと・年ごと。予測なし(季節の中で target_stage に入らなかった)・観測なしは別に数える。"""
    by_station, by_year = defaultdict(list), defaultdict(list)
    diffs = []
    no_pred = [p for p in pairs if p["observed"] and not p["predicted"]]
    no_obs = [p for p in pairs if not p["observed"]]
    for p in pairs:
        if p["diff_days"] is None:
            continue
        diffs.append(p["diff_days"])
        by_station[p["station"]].append(p["diff_days"])
        by_year[p["year"]].append(p["diff_days"])
    return {"overall": _stats(diffs, tolerances),
            "by_station": {k: _stats(v, tolerances) for k, v in sorted(by_station.items())},
            "by_year": {k: _stats(v, tolerances) for k, v in sorted(by_year.items())},
            "no_prediction": len(no_pred), "no_observation": len(no_obs), "pairs": len(pairs), "tolerances": list(tolerances)}


def _fmt(x):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.1f}"
    return str(x)


def _pct(x):
    return "—" if x is None else f"{x:.0%}"


def report_markdown(agg, *, title, notes=()):
    """集計 → Markdown(差 = 予測 − 観測。正 = 予測が遅い)。判定(合格/不合格)は書かない。"""
    tol = [str(t) for t in agg["tolerances"]]
    head = "| 区分 | n | 中央値 | 平均 | 標準偏差 | MAD | 最小 | 最大 | " + " | ".join(f"±{t}日以内" for t in tol) + " |"
    sep = "|---" * (8 + len(tol)) + "|"

    def row(label, s):
        return (f"| {label} | {s['n']} | {_fmt(s['median'])} | {_fmt(s['mean'])} | {_fmt(s['stdev'])} | {_fmt(s['mad'])} | "
                f"{_fmt(s['min'])} | {_fmt(s['max'])} | " + " | ".join(_pct(s["within"][t]) for t in tol) + " |")
    lines = [f"# {title}", "", "差 = 予測日 − 観測日(日数。正は予測が遅い)。合格・不合格の判定はしない(基準は結果を見る前にユーザーが決める)。", ""]
    lines += [f"- {n}" for n in notes]
    lines += [f"- 比較した組: {agg['overall']['n']} / 全 {agg['pairs']}(予測なし {agg['no_prediction']}、観測なし {agg['no_observation']})", "",
              "## 全体", "", head, sep, row("全体", agg["overall"]), "", "## 地点ごと", "", head, sep]
    lines += [row(k, s) for k, s in agg["by_station"].items()]
    lines += ["", "## 年ごと", "", head, sep]
    lines += [row(str(k), s) for k, s in agg["by_year"].items()]
    return "\n".join(lines) + "\n"


def observed_dates(rows, phenomenon, station_nos=None, years=None, rm=None):
    """正規化した生物季節観測の行 → {(地点番号, 年): 観測日}。rm を渡せばその rm の値だけ(rm の意味は未確認。分けて集計するため)。"""
    out = {}
    for r in rows:
        if r["phenomenon"] != phenomenon or r["status"] != "observed":
            continue
        if station_nos is not None and r["station_no"] not in station_nos:
            continue
        y = int(r["year"])
        if years is not None and y not in years:
            continue
        if rm is not None and r["rm"] not in rm:
            continue
        out[(r["station_no"], y)] = r["date"]
    return out
