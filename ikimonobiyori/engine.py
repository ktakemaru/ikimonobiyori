"""イキモノビヨリ v0 のエンジン: 依頼 + 入力(フィクスチャ) + プロファイル → biyori-proposal/1。通信しない・時刻は外から注入・決定論。

規則(段階6a):
 1. validated=false のプロファイルは band の上限が maybe(go を出さない)
 2. confidence.method と validated を必ず入れる。確信度の数値は手法が出さないので null
 3. evidence に source_type・出典 URL・最終更新日(取れなければ null + 警告)
 4. phenology_stage を使う(紅葉)。期間外は提案を出さず not_applicable(out_of_season)。骨組みは not_applicable(profile_skeleton)
 5. 野鳥は location_precision(既定 area_10km)に合わせて座標を丸め、care.do_not_disclose_exact_location=true とマナーを付ける
 6. 閾値・係数はプロファイルの params からだけ読む(このファイルに数値の閾値を書かない)
窓の kind: どちらも calendar_day。紅葉の段階も野鳥の頻度も『日単位』の推定で、時刻による変化を持たない(粗い値)。
"""
from datetime import datetime, timedelta, timezone

from . import __version__
from .fetch import inaturalist, open_meteo
from .methods import observation_frequency as obsfreq
from .methods import temperature_progression as tprog
from .profiles import param, provisional_params

JST = timezone(timedelta(hours=9))
SCHEMA = "biyori-proposal/1"
AGENT_ID = "ikimonobiyori"
BIRDS_ATTRIBUTION = ("iNaturalist のコミュニティによる観察記録(API 経由の集計。https://www.inaturalist.org/)。"
                     "投稿コンテンツの既定ライセンスは CC BY-NC の可能性があるが、個別記録のライセンスは未確認(集計値のみを使用)")
COORD_DECIMALS = {"area_1km": 2, "area_10km": 1, "municipality": 1}      # 契約の location_precision → 丸める小数桁
OFFSET_DAY = timedelta(days=1)


def _dt(s):
    return datetime.fromisoformat(s)


def request_dates(request):
    a = _dt(request["time_range"]["start"]).astimezone(JST).date()
    b = _dt(request["time_range"]["end"]).astimezone(JST).date()
    out, d = [], a
    while d <= b:
        out.append(d)
        d += OFFSET_DAY
    return out


def round_coord(v, precision):
    n = COORD_DECIMALS.get(precision)
    return v if n is None else round(v, n)


def day_window(d):
    start = datetime(d.year, d.month, d.day, tzinfo=JST)
    return {"start": start.isoformat(timespec="seconds"), "end": (start + OFFSET_DAY).isoformat(timespec="seconds"),
            "kind": "calendar_day"}


def matching_profiles(request, profiles):
    want = set(request.get("interests") or [])
    return [p for pid, p in sorted(profiles.items()) if want & set(p["interests"])]


def in_season(profile, d):
    months = profile["season"].get("months")
    return months is not None and d.month in months


def plan_queries(request, profiles, areas, sites, *, today):
    """6b で行う問い合わせの一覧(通信しない)。野鳥: 場所×対象日×過去年。紅葉: 地点ごとに過去〜予報の日別気温。"""
    out = []
    dates = request_dates(request)
    b = profiles.get("birds")
    if b and "birds" in (request.get("interests") or []):
        for a in areas:
            for d in dates:
                for k in range(1, param(b, "history_years") + 1):
                    out.append(dict(kind="birds", area=a["name"], date=d.isoformat(), **inaturalist.species_counts_query(
                        lat=a["lat"], lng=a["lon"], radius_km=a.get("radius_km", param(b, "default_radius_km")), center=d,
                        year=d.year - k, window_weeks=param(b, "window_weeks"), iconic_taxa=param(b, "iconic_taxa"),
                        quality_grade=param(b, "quality_grade"))))
    al = profiles.get("autumn_leaves")
    if al and "autumn_leaves" in (request.get("interests") or []):
        for sid, s in sites.items():
            past = param(al, "mean_window_days")
            ahead = max((max(dates) - today).days + 1, 1)
            out.append(dict(kind="autumn_leaves", site=sid, **open_meteo.daily_query(lat=s["lat"], lon=s["lon"], past_days=past, forecast_days=ahead)))
    return out


def _evidence(metric, value, unit, *, source, source_type, url, last_updated, valid_time=None):
    return {"metric": metric, "value": value, "unit": unit, "valid_time": valid_time, "source": source,
            "source_type": source_type, "url": url, "last_updated": last_updated}


INSUFFICIENT_CODE = "insufficient_data"
INSUFFICIENT_PREFIX = f"[{INSUFFICIENT_CODE}] "      # 件数不足は失敗ではなく『結果』。警告のコード(原文はこの後ろにそのまま続く)


def birds_proposals(request, profile, inputs, dates, today, synthetic, warnings):
    out, asof = [], []
    precision = profile["care"]["location_precision"]
    min_total, top_n = param(profile, "min_total_observations"), param(profile, "top_species")
    maybe_min, max_band = param(profile, "maybe_min_relative_frequency"), profile["band_policy"]["max_band"]
    src = "iNaturalist API" + (" [SYNTHETIC fixture]" if synthetic else "")
    for blk in inputs.get("birds") or []:
        area = blk["area"]
        for q in blk["queries"]:
            d = datetime.fromisoformat(q["date"]).date()
            if d not in dates or not in_season(profile, d):
                continue
            rows_by_year = [inaturalist.parse_species_counts(r)[0] for _, r in sorted(q["years"].items())]
            res = obsfreq.relative_frequencies(rows_by_year, min_total=min_total, top_n=top_n)
            if q.get("years_covered"):                         # 年の複数指定(1応答が複数年分)のときは、応答の数ではなく対象の年数
                res["years"] = len(q["years_covered"])
            latest = inaturalist.parse_latest_observed(q["latest_observations"]) if q.get("latest_observations") is not None else None
            if latest is None:
                warnings.append(f"{area['name']} {q['date']}: 最終更新日(最新の観察日)が取れないため last_updated は null")
            if not res["enough"]:
                warnings.append(f"{INSUFFICIENT_PREFIX}{area['name']} {q['date']}: 観察記録の総数 {res['total']} が min_total_observations={min_total} 未満のため提案を出さない")
                continue
            # 出力に載せる出典 URL は、位置を丸めた座標で組む(care.do_not_disclose_exact_location: 正確な座標を出力に出さない)
            url = inaturalist.species_counts_query(lat=round_coord(area["lat"], precision), lng=round_coord(area["lon"], precision),
                                                   radius_km=area["radius_km"], center=d,
                                                   year=d.year - 1, window_weeks=param(profile, "window_weeks"),
                                                   iconic_taxa=param(profile, "iconic_taxa"), quality_grade=param(profile, "quality_grade"))["url"]
            if q.get("urls"):                                  # 実通信/キャッシュ由来: 実際の問い合わせ URL(最も新しい年の窓)と取得時刻(キャッシュの fetched_at)
                url = q["urls"][max(q["urls"])]
            asof.append({"source": src, "source_type": "observation", "run_time": None,
                         "fetched_at": max(q["fetched_at_by_year"].values()) if q.get("fetched_at_by_year") else inputs["fetched_at"],
                         "last_updated": latest, "url": url})
            for sp in res["species"]:
                name = sp["common_name"] or sp["name"]
                rf = sp["relative_frequency"]
                ev = lambda m, v, u: _evidence(m, v, u, source=src, source_type="observation", url=url, last_updated=latest)
                out.append({
                    "id": f"{AGENT_ID}:birds:{q['date']}:{area['name']}:{sp['name']}",
                    "title": f"{area['name']} {q['date']} {name}",
                    "subject": {"category": profile["category"], "name": name, "profile_id": profile["profile_id"]},
                    "place": {"name": area["name"], "area_id": area.get("id"), "lat": round_coord(area["lat"], precision), "lon": round_coord(area["lon"], precision),
                              "elevation_m": None, "region": None, "location_precision": precision},
                    "time_window": day_window(d),
                    "suitability": {"band": obsfreq.band_for(rf, maybe_min=maybe_min, max_band=max_band),
                                    "score": {"value": rf, "scale": profile["scale"]["name"], "go_threshold": None}},
                    "evidence": [ev("relative_frequency", rf, "ratio"), ev("species_observations", sp["count"], "observations"),
                                 ev("total_observations", res["total"], "observations"), ev("years_used", res["years"], "year"),
                                 ev("window_weeks", param(profile, "window_weeks"), "week")],
                    "constraints": [],
                    "uncertainty": {"lead_days": (d - today).days, "reliable_up_to_days": None,
                                    "confidence": {"value": None, "scale": None, "method": profile["confidence"]["method"],
                                                   "validated": profile["confidence"]["validated"]},
                                    "known_limits": list(profile["known_limits"])},
                    "care": {"manners": list(profile["care"]["manners"]),
                             "do_not_disclose_exact_location": profile["care"]["do_not_disclose_exact_location"]},
                    "native_ref": None,
                    "details": {"profile_id": profile["profile_id"], "taxon_name": sp["name"], "taxon_id": sp["taxon_id"],
                                "area_radius_km": area["radius_km"], "url_uses_rounded_center": True, "attribution": BIRDS_ATTRIBUTION,
                                "score_explain": profile["score_explain"].format(years=res["years"], weeks=param(profile, "window_weeks"), radius=area["radius_km"],
                                                                                 total=res["total"], name=name, count=sp["count"], rf=rf), "provisional_params": provisional_params(profile),
                                "synthetic": bool(synthetic)},
                })
    return out, asof


def autumn_proposals(request, profile, inputs, sites, dates, today, synthetic, warnings):
    out, asof = [], []
    start, advance = param(profile, "start_min_temp_c"), param(profile, "advance_min_temp_c")
    strong, win = param(profile, "strong_min_temp_c"), param(profile, "mean_window_days")
    max_band, bmap = profile["band_policy"]["max_band"], profile["method"]["band_map"]
    order = {"no": 0, "maybe": 1, "go": 2}
    src = "Open-Meteo forecast API" + (" [SYNTHETIC fixture]" if synthetic else "")
    only = inputs.get("site_ids")                              # 指定があればその地点だけ
    for sid, resp in sorted((inputs.get("temperatures") or {}).items()):
        if only is not None and sid not in only:
            continue
        site = sites.get(sid)
        if site is None:
            warnings.append(f"地点 {sid} がカタログにない")
            continue
        series = open_meteo.parse_daily_tmin(resp)
        meta = (inputs.get("temperatures_meta") or {}).get(sid)
        q = open_meteo.daily_query(lat=site["lat"], lon=site["lon"], past_days=win, forecast_days=1)
        if meta:                                           # 実通信/キャッシュ由来: 実際の問い合わせ URL と取得時刻(キャッシュの fetched_at)を使う
            q = {"url": meta["url"]}
        for d in dates:
            if not in_season(profile, d):
                continue
            m = tprog.mean_tmin(series, d, win)
            st = tprog.stage_for(m, start=start, advance=advance)
            if st is None:
                warnings.append(f"{site['name']} {d.isoformat()}: 日最低気温が{win}日分そろわないため提案を出さない(欠損を0で埋めない)")
                continue
            band = bmap[st]
            band = band if order[band] <= order[max_band] else max_band
            prog = tprog.progress(m, start=start, strong=strong)
            url = q["url"]
            ev = lambda metric, v, u: _evidence(metric, v, u, source=src, source_type="forecast", url=url, last_updated=None,
                                                valid_time=day_window(d)["start"])
            thr = "ikimonobiyori profile autumn_leaves (provisional)"
            out.append({
                "id": f"{AGENT_ID}:autumn_leaves:{d.isoformat()}:{sid}",
                "title": f"{site['name']} {d.isoformat()} 紅葉",
                "subject": {"category": profile["category"], "name": "紅葉", "profile_id": profile["profile_id"]},
                "phenology_stage": st,
                "place": {"name": site["name"], "lat": site["lat"], "lon": site["lon"], "elevation_m": site["elevation_m"],
                          "region": site["region"], "location_precision": site.get("location_precision") or profile["care"]["location_precision"],
                          **({"site_ref": site["site_ref"]} if site.get("site_ref") else {}),
                          **({"sources": site["sources"]} if site.get("sources") else {})},          # 名所カタログの地点(段階14b)だけ。76 地点は今まで通り
                "time_window": day_window(d),
                "suitability": {"band": band, "score": {"value": prog, "scale": profile["scale"]["name"], "go_threshold": None}},
                "evidence": [ev("min_temp_mean_window", m, "degC"), ev("min_temp_target_day", series.get(d.isoformat()), "degC"),
                             ev("mean_window_days", win, "day"),
                             {"metric": "start_min_temp_c", "value": start, "unit": "degC", "valid_time": None, "source": thr,
                              "source_type": "static_reference", "url": "https://www.hrr.mlit.go.jp/omachi/news/back/kisyahappyou/161024/161024omachikouyou.pdf",
                              "last_updated": None},
                             {"metric": "advance_min_temp_c", "value": advance, "unit": "degC", "valid_time": None, "source": thr,
                              "source_type": "static_reference", "url": "https://www.hrr.mlit.go.jp/omachi/news/back/kisyahappyou/161024/161024omachikouyou.pdf",
                              "last_updated": None}],
                "constraints": [],
                "uncertainty": {"lead_days": (d - today).days, "reliable_up_to_days": None,
                                "confidence": {"value": None, "scale": None, "method": profile["confidence"]["method"],
                                               "validated": profile["confidence"]["validated"]},
                                "known_limits": list(profile["known_limits"])},
                "care": {"manners": list(profile["care"]["manners"]),
                         "do_not_disclose_exact_location": profile["care"]["do_not_disclose_exact_location"]},
                "native_ref": None,
                "details": {"profile_id": profile["profile_id"], "site_id": sid, "provisional_params": provisional_params(profile),
                            "synthetic": bool(synthetic), **({"landmark": site["landmark"]} if site.get("landmark") else {})},
            })
        asof.append({"source": src, "source_type": "forecast", "run_time": None,
                     "fetched_at": meta["fetched_at"] if meta else inputs["fetched_at"], "last_updated": None, "url": q["url"]})
    return out, asof


def run(request, *, profiles, sites, inputs, now, request_id=None):
    """依頼 → biyori-proposal/1。now はオフセットつき datetime(外から注入)。"""
    if now.tzinfo is None:
        raise ValueError("now にオフセットが必要")
    today = now.astimezone(JST).date()
    dates = request_dates(request)
    synthetic = bool(inputs.get("synthetic"))
    warnings = []
    if synthetic:
        warnings.append("SYNTHETIC: 合成フィクスチャの入力から作った。実データではない")
    matched = matching_profiles(request, profiles)
    proposals, asof, reasons = [], [], []
    for p in matched:
        pid = p["profile_id"]
        if p["status"] == "skeleton":
            reasons.append("profile_skeleton")
            warnings.append(f"{pid}: プロファイルは骨組みのみ(判定ロジック未実装)")
            continue
        if not any(in_season(p, d) for d in dates):
            reasons.append("out_of_season")
            warnings.append(f"{pid}: 依頼の期間は対象の月({p['season']['months']})の外")
            continue
        if pid == "birds":
            a, b = birds_proposals(request, p, inputs, dates, today, synthetic, warnings)
        elif pid == "autumn_leaves":
            a, b = autumn_proposals(request, p, inputs, sites, dates, today, synthetic, warnings)
        else:
            reasons.append("profile_skeleton")
            warnings.append(f"{pid}: 実装がない")
            continue
        proposals += a
        asof += b
        if not a:
            # 野鳥で、入力は取れたが件数が足りないだけ(失敗ではない) → insufficient_data。入力そのものがない・取れない場合だけ no_input_data
            only_insufficient = pid == "birds" and bool(inputs.get("birds")) and any(w.startswith(INSUFFICIENT_PREFIX) for w in warnings)
            reasons.append(INSUFFICIENT_CODE if only_insufficient else "no_input_data")
    doc = {
        "schema": SCHEMA, "request_id": request_id or request["request_id"],
        "agent": {"id": AGENT_ID, "version": __version__, "commit": None},
        "status": "ok", "generated_at": now.isoformat(timespec="seconds"),
        "data_as_of": asof, "proposals": sorted(proposals, key=lambda x: x["id"]),
        "diagnostics": {"api_calls": 0, "cache_hit": None, "runtime_s": None, "warnings": warnings},
    }
    n_insufficient = sum(1 for w in warnings if w.startswith(INSUFFICIENT_PREFIX))
    if n_insufficient:
        doc["details"] = {"warning_codes": {INSUFFICIENT_CODE: n_insufficient}}
    real_reasons = [r for r in reasons if r != INSUFFICIENT_CODE]
    if not proposals:
        if not matched:
            doc["status"], doc["status_reason"] = "not_applicable", "no_matching_profile"
        elif "out_of_season" in reasons:
            doc["status"], doc["status_reason"] = "not_applicable", "out_of_season"
        elif "profile_skeleton" in reasons and "no_input_data" not in reasons:
            doc["status"], doc["status_reason"] = "not_applicable", "profile_skeleton"
        elif reasons and not real_reasons:
            pass                                       # 件数不足だけ(insufficient_data): 失敗ではなく結果。status は ok のまま、警告(コードつき・原文)で伝える
        else:
            doc["status"], doc["status_reason"] = "partial", "no_input_data"
    elif real_reasons or any("提案を出さない" in w and not w.startswith(INSUFFICIENT_PREFIX) for w in warnings):
        doc["status"], doc["status_reason"] = "partial", "some_subjects_not_applicable_or_missing_input"
    return doc
