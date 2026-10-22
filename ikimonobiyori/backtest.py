"""紅葉の答え合わせ(段階14 の準備。docs/validation-plan.md)のうち、通信しない部分: 判定・比べ方・集計・レポート。純粋・決定論。
- 予測日: v0 と同じ判定(methods/temperature_progression の mean_tmin・stage_for、閾値はプロファイルから)を過去の各日に当てはめ、
  段階が初めて target_stage(既定 peak = 見頃)になった日。
- 比べ方: 予測日 − 観測日(日数。正 = 予測が遅い)。中央値・ばらつき・地点ごと・年ごと。
- 許容の日数(±N 日)は呼び出し側が渡す。合格基準はここでは決めない(ユーザーが結果を見る前に決める)。
実通信(Open-Meteo の過去の気温の取得)は fetch/archive_live.py(段階14)。ここには問い合わせの組み立てと、集計・判定(通信しない)を置く。
判定の基準(±3 日・予測なしの上限・使う年・標高の扱いなど)は data/backtest_plan.yaml に書き、コードに値を持たない。"""
import statistics
from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

from .methods.temperature_progression import mean_tmin, stage_for
from .profiles import param

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"   # https://open-meteo.com/en/docs/historical-weather-api(config.yaml の allowed_hosts_by_subject.autumn_leaves_backtest だけ。段階14 でユーザー承認 2026-10-22)


def archive_query(*, lat, lon, start_date, end_date, elevation=None, daily="temperature_2m_min", timezone="Asia/Tokyo", models=None):
    """Historical API の問い合わせ(通信しない)。elevation を渡すと、その標高でダウンスケールする(None なら渡さない = Open-Meteo の 90 m 標高データ)。
    models を渡すと再解析のモデルを固定する(段階14 の計画は era5_land。None なら渡さない = Best match)。"""
    params = {"latitude": lat, "longitude": lon, "start_date": start_date, "end_date": end_date, "daily": daily, "timezone": timezone}
    if elevation is not None:
        params["elevation"] = elevation
    if models is not None:
        params["models"] = models
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
        return {"n": 0, "median": None, "mean": None, "mae": None, "stdev": None, "mad": None, "min": None, "max": None, "quartiles": None,
                "within": {str(t): None for t in tolerances}}
    med = statistics.median(diffs)
    return {"n": len(diffs), "median": med, "mean": statistics.fmean(diffs), "mae": statistics.fmean([abs(x) for x in diffs]),
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
    head = "| 区分 | n | 中央値 | 平均 | 標準偏差 | MAD | 最小 | 最大 | " + " | ".join(f"±{t}日以内" for t in tol) + " | 平均絶対誤差 |"
    sep = "|---" * (9 + len(tol)) + "|"

    def row(label, s):
        return (f"| {label} | {s['n']} | {_fmt(s['median'])} | {_fmt(s['mean'])} | {_fmt(s['stdev'])} | {_fmt(s['mad'])} | "
                f"{_fmt(s['min'])} | {_fmt(s['max'])} | " + " | ".join(_pct(s["within"][t]) for t in tol) + f" | {_fmt(s['mae'])} |")
    lines = [f"# {title}", "", "差 = 予測日 − 観測日(日数。正は予測が遅い)。合格・不合格の判定はしない(基準は結果を見る前にユーザーが決める)。", ""]
    lines += [f"- {n}" for n in notes]
    lines += [f"- 比較した組: {agg['overall']['n']} / 全 {agg['pairs']}(予測なし {agg['no_prediction']}、観測なし {agg['no_observation']})", "",
              "## 全体", "", head, sep, row("全体", agg["overall"]), "", "## 地点ごと", "", head, sep]
    lines += [row(k, s) for k, s in agg["by_station"].items()]
    lines += ["", "## 年ごと", "", head, sep]
    lines += [row(str(k), s) for k, s in agg["by_year"].items()]
    return "\n".join(lines) + "\n"


def _offset(year, iso):
    """季節の年の 1 月 1 日からの日数(年をまたいだ観測日は 365 を超える)。"""
    return (date.fromisoformat(iso) - date(year, 1, 1)).days


def climatology_pairs(observed, *, mode):
    """平年値法(基準線)の比較の組。各地点・年について、同じ地点の「その年を除いた」観測日の中央値を予測とする。
    mode は呼び出し側が必ず選ぶ(段階14 の前にユーザーが決める。docs/validation-plan.md §0):
      "leave_one_out" = その地点のその年以外のすべての年、"prior_only" = その年より前の年だけ。
    差 diff_days は中央値の日数 − 観測の日数(端数 0.5 がありうる)。predicted はその日付(切り捨て)。比べる年がなければ予測なし。"""
    if mode not in ("leave_one_out", "prior_only"):
        raise ValueError(f"mode は leave_one_out か prior_only: {mode!r}")
    by_station = defaultdict(dict)
    for (st, y), iso in observed.items():
        by_station[st][y] = _offset(y, iso)
    out = []
    for (st, y), iso in sorted(observed.items()):
        others = [v for yy, v in by_station[st].items() if yy != y and (mode == "leave_one_out" or yy < y)]
        if not others:
            out.append(pair(st, y, None, iso))
            continue
        med = statistics.median(others)
        pred = (date(y, 1, 1) + timedelta(days=int(med))).isoformat()
        out.append({"station": st, "year": y, "predicted": pred, "observed": iso, "diff_days": med - _offset(y, iso)})
    return out


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


# ---- 段階14: 計画・問い合わせの一覧・判定(通信しない。値は data/backtest_plan.yaml から) ----

def load_plan(path=None):
    from pathlib import Path

    import yaml

    from .paths import BACKTEST_PLAN_PATH
    return yaml.safe_load(Path(path or BACKTEST_PLAN_PATH).read_text(encoding="utf-8"))


def plan_years(plan):
    return list(range(plan["year_from"], plan["year_to"] + 1))


def build_requests(plan, stations, profile):
    """計画の各地点・年・標高の扱いに対する Historical API の問い合わせの一覧(通信しない)。決定論の並び: 地点(計画の順)→ 年 → 標高の扱い(計画の順)。
    stations は jma_phenology.yaml の stations(station_no・lat・lon・elevation_m)。座標・標高が null の地点は ValueError(推測で補わない)。
    各件: id・station_no・year・mode・url・params・expected_days・elevation(渡した標高 or None)。"""
    by_no = {s["station_no"]: s for s in stations}
    out = []
    for no in plan["station_nos"]:
        st = by_no[no]
        if st.get("lat") is None or st.get("lon") is None or st.get("elevation_m") is None:
            raise ValueError(f"地点 {no}({st.get('name')})の座標・標高が null")
        for year in plan_years(plan):
            first, last = fetch_range(profile, year)
            for mode in plan["elevation_modes"]:
                elev = st["elevation_m"] if mode == "with" else None
                q = archive_query(lat=st["lat"], lon=st["lon"], start_date=first.isoformat(), end_date=last.isoformat(), elevation=elev, models=plan["models"])
                out.append({"id": f"{no}-{year}-{mode}", "station_no": no, "year": year, "mode": mode, "url": q["url"], "params": q["params"],
                            "expected_days": (last - first).days + 1, "elevation": elev})
    return out


def v0_pairs(profile, series_by_id, observed, mode, stage):
    """観測のある各 (地点, 年) について、v0 と同じ判定で stage に初めて入った日を予測として比べる。
    気温の入力(series_by_id[id])がない組は KeyError(予測なしと取り違えない。推測で補わない)。→ 組のリスト(station・year・predicted・observed・diff_days)"""
    out = []
    for (no, year), obs in sorted(observed.items()):
        series = series_by_id[f"{no}-{year}-{mode}"]
        pred = predict(series, profile, year, target_stage=stage)
        out.append(pair(no, year, pred["first"].get(stage), obs))
    return out


def judge(plan, v0, clim):
    """決定事項(plan)どおりの合否。v0・clim は同じ観測の組から作った pair のリスト(clim は climatology_pairs の結果)。
    - 平均絶対誤差は、v0 も平年値法も差が出せる共通の組で比べる(観測がない組はそもそも組に入らない)。
    - 差(予測 − 観測)の中央値は、v0 が予測を出したすべての組で出す(参考に共通の組での値も返す)。
    - 予測なしの割合 = v0 の予測なし ÷ 観測のある組。
    合格 = 3 つの条件がすべて成り立つ。どれかの組が空なら不合格(理由 reasons に書く)。"""
    c = plan["pass_criteria"]
    clim_by = {(p["station"], p["year"]): p for p in clim}
    n_obs = sum(1 for p in v0 if p["observed"])
    no_pred = sum(1 for p in v0 if p["observed"] and not p["predicted"])
    all_diffs = [p["diff_days"] for p in v0 if p["diff_days"] is not None]
    common = [(p, clim_by[(p["station"], p["year"])]) for p in v0
              if p["diff_days"] is not None and clim_by.get((p["station"], p["year"]), {}).get("diff_days") is not None]
    mae_v0 = statistics.fmean([abs(a["diff_days"]) for a, _ in common]) if common else None
    mae_clim = statistics.fmean([abs(b["diff_days"]) for _, b in common]) if common else None
    median_all = statistics.median(all_diffs) if all_diffs else None
    median_common = statistics.median([a["diff_days"] for a, _ in common]) if common else None
    ratio = no_pred / n_obs if n_obs else None
    reasons = []
    mae_ok = mae_v0 is not None and mae_v0 < mae_clim
    if not mae_ok:
        reasons.append("平均絶対誤差が平年値法より小さくない" if mae_v0 is not None else "共通の組がない")
    median_ok = median_all is not None and abs(median_all) <= c["tolerance_days"]
    if not median_ok:
        reasons.append(f"差の中央値が ±{c['tolerance_days']} 日以内でない" if median_all is not None else "差の中央値が出せない")
    nopred_ok = ratio is not None and ratio <= c["max_no_prediction_ratio"]
    if not nopred_ok:
        reasons.append(f"予測なしの割合が {c['max_no_prediction_ratio']:.0%} を超える" if ratio is not None else "観測のある組がない")
    return {"passed": mae_ok and median_ok and nopred_ok, "reasons": reasons,
            "conditions": {"mae_v0_smaller_than_climatology": mae_ok, "median_within_tolerance": median_ok, "no_prediction_ratio_within_limit": nopred_ok},
            "mae_v0": mae_v0, "mae_climatology": mae_clim, "median_diff_all_v0_pairs": median_all, "median_diff_common_pairs": median_common,
            "pairs_with_observation": n_obs, "pairs_common": len(common), "pairs_v0_with_diff": len(all_diffs), "no_prediction": no_pred, "no_prediction_ratio": ratio,
            "criteria": dict(c)}


def evaluate(plan, stations, profile, series_by_id, rows):
    """正規化した生物季節観測の行と、取得済みの気温から、答え合わせの全結果(通信しない)。
    - 合否に使う: かえで紅葉 × 見頃(v0)× 標高あり。標高なしは同じ判定を参考に出す。
    - 参考: かえで紅葉 × 色づき始め、いちょう黄葉 × 見頃・色づき始め(いずれも標高あり)。
    - 平年値法は plan の年・地点の観測だけから作る(1953 年からの観測は使わない)。"""
    years, nos = set(plan_years(plan)), set(plan["station_nos"])
    obs = observed_dates(rows, plan["phenomenon"], station_nos=nos, years=years)
    obs_ref = observed_dates(rows, plan["reference_phenomenon"], station_nos=nos, years=years)
    clim = climatology_pairs(obs, mode=plan["climatology"]["mode"])
    names = {s["station_no"]: s["name"] for s in stations}
    all_pairs = len(nos) * len(years)
    out = {"plan": plan, "counts": {"all_pairs": all_pairs, "with_observation": len(obs), "without_observation": all_pairs - len(obs),
                                    "icho_with_observation": len(obs_ref)}, "station_names": names, "modes": {}, "reference": {}}
    tol = [plan["pass_criteria"]["tolerance_days"]]
    for mode in plan["elevation_modes"]:
        pairs = v0_pairs(profile, series_by_id, obs, mode, plan["target_stage"])
        out["modes"][mode] = {"judge": judge(plan, pairs, clim), "aggregate": aggregate(pairs, tol), "pairs": pairs,
                              "climatology_aggregate": aggregate(clim, tol)}
    dec = plan["decisive_elevation_mode"]
    out["decisive_mode"] = dec
    out["passed"] = out["modes"][dec]["judge"]["passed"]
    ref = {"kaede_early_bloom": (obs, plan["reference_stage"]), "icho_peak": (obs_ref, plan["target_stage"]), "icho_early_bloom": (obs_ref, plan["reference_stage"])}
    for name, (o, stage) in ref.items():
        pairs = v0_pairs(profile, series_by_id, o, dec, stage)
        out["reference"][name] = {"stage": stage, "aggregate": aggregate(pairs, tol), "pairs": pairs}
    return out


def result_markdown(res):
    """evaluate の結果 → Markdown(数字は計算結果そのまま)。"""
    plan, dec = res["plan"], res["decisive_mode"]
    n = res["counts"]
    lines = ["# 紅葉の答え合わせの結果(段階14)", "",
             f"**合否: {'合格' if res['passed'] else '不合格'}**(標高の扱い = {dec}。決定事項は docs/validation-plan.md §0 の追記)", "",
             f"- 組の数: 全体 {n['all_pairs']}(= {len(plan['station_nos'])} 地点 × {len(plan_years(plan))} 年)、観測あり {n['with_observation']}、観測なし {n['without_observation']}", ""]
    for mode, m in res["modes"].items():
        j = m["judge"]
        lines += [f"## かえで紅葉 × v0 {plan['target_stage']}(標高の扱い: {mode}{'・合否に使う' if mode == dec else '・参考'})", "",
                  f"- 共通の組: {j['pairs_common']} / 観測あり {j['pairs_with_observation']}(v0 が予測を出した組 {j['pairs_v0_with_diff']})",
                  f"- 平均絶対誤差(共通の組): v0 {_fmt(j['mae_v0'])} 日、平年値法 {_fmt(j['mae_climatology'])} 日",
                  f"- 差(予測 − 観測)の中央値: v0 の全組 {_fmt(j['median_diff_all_v0_pairs'])} 日(共通の組 {_fmt(j['median_diff_common_pairs'])} 日)",
                  f"- 予測なし: {j['no_prediction']} 組({_pct(j['no_prediction_ratio'])})",
                  "- 条件: " + "、".join(f"{k}={'○' if v else '×'}" for k, v in j["conditions"].items())
                  + ("" if j["passed"] else "。理由: " + "、".join(j["reasons"])), ""]
        lines += report_markdown(m["aggregate"], title=f"v0 {plan['target_stage']} × かえで紅葉 / {mode}(地点は番号)").split("\n")[2:]
        lines += ["", "平年値法(基準線。標高の扱いに関係なく同じ):", ""]
        lines += report_markdown(m["climatology_aggregate"], title="平年値法").split("\n")[2:]
    for name, r in res["reference"].items():
        lines += ["", *report_markdown(r["aggregate"], title=f"参考: {name}(v0 {r['stage']} / {dec})").split("\n")]
    return "\n".join(lines) + "\n"
