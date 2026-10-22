#!/usr/bin/env python3
"""イキモノビヨリの CLI(manifest の command)。

  # オフライン(入力 JSON = フィクスチャ形式 ikimono-inputs/1)
  python -X utf8 ikimonobiyori/main.py --request REQ.json --inputs INPUTS.json --now ISO8601 [--out FILE]
  # 紅葉の入力をキャッシュから(通信しない)
  python -X utf8 ikimonobiyori/main.py --request REQ.json --cache-only --now ISO8601 [--sites m001,m002]
  # 紅葉の入力を Open-Meteo から(実通信。段階6b-1。野鳥の実通信は 6b-2 で別途承認)
  BIYORI_ALLOW_LIVE=1 BIYORI_REQ_LOG=... (計測フック) python -X utf8 ikimonobiyori/main.py --request REQ.json --live --max-requests N --now ISO8601 [--sites m001,m002]
  # 6b で行う問い合わせの一覧(通信なし)
  python -X utf8 ikimonobiyori/main.py --request REQ.json --plan-queries --now ISO8601

--live は BIYORI_ALLOW_LIVE=1、明示的な --max-requests、計測フックが有効(環境変数 BIYORI_REQ_LOG)のすべてが必要。
通信先は config.yaml の live.allowed_hosts(api.open-meteo.com のみ)。--now は必須(オフセットつき)。同じ入力・同じ now なら同じ出力。"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))      # スクリプトとして起動されたとき、パッケージとして import するため(パッケージの親フォルダ)

from ikimonobiyori import engine, livegate, paths, profiles  # noqa: E402  (livegate はハブのものではなく自分の写し。段階12)
from ikimonobiyori.config import load_config  # noqa: E402
from ikimonobiyori.fetch import ParseError, birds_live, live as livemod  # noqa: E402
from ikimonobiyori.fetch.cache import Cache  # noqa: E402


def main(argv=None, http_get=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--request", required=True)
    ap.add_argument("--inputs")
    ap.add_argument("--now", required=True)
    ap.add_argument("--plan-queries", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--cache-only", action="store_true")
    ap.add_argument("--max-requests", type=int)
    ap.add_argument("--sites", help="地点 ID をカンマ区切り(例: m001,m002)。省略時は紅葉の対象日の全カタログ地点")
    ap.add_argument("--site-set", choices=["mountains", "catalog", "both"], default="mountains",
                    help="紅葉の地点の集合(段階14b)。mountains = 山の 76 地点(既定・今まで通り)/ catalog = 名所カタログの承認済み / both = 両方")
    ap.add_argument("--area", help="野鳥の場所 ID(bird_areas の approved のもの。省略時は先頭。all = approved の全部)")
    ap.add_argument("--dates-limit", type=int, help="野鳥: 先頭から何日分だけ処理するか(例: 1)")
    ap.add_argument("--shape-check", action="store_true", help="野鳥: 形の確認(1日分・1年分の窓を1リクエストだけ)。応答の形を --shape-out に保存して終わる")
    ap.add_argument("--shape-out")
    ap.add_argument("--density-survey", action="store_true", help="野鳥のデータ密度の調査(段階6c)。--live と --max-requests が必要。結果は --survey-out")
    ap.add_argument("--per-year", action="store_true", help="野鳥: 年の複数指定ではなく1年ずつ取る従来の方式(検証用。既定は複数指定)")
    ap.add_argument("--survey-out")
    ap.add_argument("--survey-file", help="調査の定義 YAML(省略時 density_survey.yaml。段階5a: window_survey.yaml)")
    ap.add_argument("--cache-dir")
    ap.add_argument("--profiles", default=None)
    ap.add_argument("--out")
    ap.add_argument("--inputs-out", help="取得した入力(ikimono-inputs/1。気温の応答そのもの)の保存先。独立検査・記録フィクスチャ用")
    a = ap.parse_args(argv)
    now = datetime.fromisoformat(a.now)
    if now.tzinfo is None:
        print("--now にはオフセットが必要です", file=sys.stderr)
        return 2
    cfg = load_config()
    request = json.loads(Path(a.request).read_text(encoding="utf-8"))
    profs = profiles.load_profiles(a.profiles)
    sites, sites_doc = profiles.load_sites()
    if a.site_set != "mountains":                              # 名所カタログ(承認済みだけ)。既定の 76 地点の動作は変えない(段階14b)
        from ikimonobiyori import catalog
        cat = catalog.catalog_sites(catalog.load_catalog("autumn_leaves"))
        sites = cat if a.site_set == "catalog" else {**sites, **cat}
    all_approved = [x for x in (sites_doc.get("bird_areas") or []) if x.get("status") == "approved"]      # 候補(candidate)は問い合わせの対象にしない
    approved_areas = [x for x in all_approved if x.get("active") is not False]                          # 既定の問い合わせ(--area 省略・all)は active だけ。active: false は --area ID で明示したときだけ
    report = None
    if a.density_survey:
        from ikimonobiyori import survey
        if not (a.live or a.cache_only):
            print("--density-survey は --live か --cache-only が必要です", file=sys.stderr)
            return 2
        if a.live:
            if (http_get is None and not livegate.live_allowed()) or a.max_requests is None or a.max_requests < 1:
                print((livegate.refusal() if http_get is None else None) or "--live は BIYORI_ALLOW_LIVE=1 と明示的な --max-requests が必要です", file=sys.stderr)
                return 4
            if http_get is None and not os.environ.get("BIYORI_REQ_LOG"):
                print("--live は計測フック(BIYORI_REQ_LOG)が有効なときだけ実行します", file=sys.stderr)
                return 4
        cdir = Path(a.cache_dir) if a.cache_dir else paths.data_path(cfg["cache"]["dir"])
        try:
            res = survey.run_density_survey(survey.load_survey(Path(a.survey_file) if a.survey_file else None), now, cfg=cfg, cache=Cache(cdir), http_get=http_get, live=a.live,
                                            cache_only=a.cache_only, max_requests=a.max_requests, unparsed_dir=paths.data_path(cfg["cache"]["unparsed_dir"]))
        except ParseError as e:
            print(f"応答を読めないため中止: {e}", file=sys.stderr)
            return 6
        except livemod.LiveError as e:
            print(f"通信を中止: {e}", file=sys.stderr)
            return 5
        Path(a.survey_out or "density_survey.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"requests": res["requests"], "cache_hits": res["cache_hits"], "places": len(res["places"])}, ensure_ascii=False))
        return 0
    if a.plan_queries:
        result = engine.plan_queries(request, profs, approved_areas, sites, today=now.date())
    elif a.live or a.cache_only:
        if a.live:
            if http_get is None and not livegate.live_allowed():       # 偽の http_get を注入したテストは実通信にならない。本物の通信は常にゲートを通る
                print(livegate.refusal(), file=sys.stderr)
                return 4
            if a.max_requests is None or a.max_requests < 1:
                print("--live は明示的な --max-requests (1 以上)が必要です", file=sys.stderr)
                return 4
            if http_get is None and not os.environ.get("BIYORI_REQ_LOG"):
                print("--live は計測フック(BIYORI_REQ_LOG)が有効なときだけ実行します(許可リスト・上限の強制のため)", file=sys.stderr)
                return 4
        interests = request.get("interests") or []
        want_aut, want_birds = "autumn_leaves" in interests, "birds" in interests
        if not (want_aut or want_birds):
            print("--live / --cache-only は紅葉(autumn_leaves)か野鳥(birds)だけです", file=sys.stderr)
            return 2
        if a.live and want_aut and want_birds:
            print("--live は対象を1つずつ(紅葉と野鳥を同時に実通信しない。許可ホストが違う)", file=sys.stderr)
            return 2
        cdir = Path(a.cache_dir) if a.cache_dir else paths.data_path(cfg["cache"]["dir"])          # 書き込み先は IKIMONOBIYORI_DATA_DIR の下(段階12)
        unparsed = paths.data_path(cfg["cache"]["unparsed_dir"])
        inputs, reports = {"schema": "ikimono-inputs/1", "synthetic": False, "fetched_at": now.isoformat(timespec="seconds")}, []
        try:
            if want_aut:
                site_ids = [x.strip() for x in a.sites.split(",")] if a.sites else sorted(sites)
                unknown = [x for x in site_ids if x not in sites]
                if unknown:
                    print(f"カタログにない地点: {unknown}", file=sys.stderr)
                    return 2
                prof = profs["autumn_leaves"]
                dates = [d for d in engine.request_dates(request) if engine.in_season(prof, d)]
                if dates:
                    i2, r2 = livemod.fetch_temperatures(site_ids, sites, prof, dates, now.date(), now, cache=Cache(cdir), cfg=cfg, http_get=http_get,
                                                        live=a.live, cache_only=a.cache_only, max_requests=a.max_requests, unparsed_dir=unparsed)
                    inputs.update(temperatures=i2["temperatures"], temperatures_meta=i2["temperatures_meta"], site_ids=site_ids,
                                  fetched_at=i2["fetched_at"])
                    reports.append(r2)
            if want_birds:
                prof = profs["birds"]
                if a.area == "all":                                  # 承認済み(approved)の全ての場所。リクエスト上限は全体で共有する
                    areas = list(approved_areas)
                else:
                    area_id = a.area or (approved_areas[0]["id"] if approved_areas else None)
                    areas = [x for x in all_approved if x["id"] == area_id]
                if not areas:
                    print(f"承認済み(approved)の野鳥の場所がない: {a.area}", file=sys.stderr)
                    return 2
                dates = [d for d in engine.request_dates(request) if engine.in_season(prof, d)]
                if a.dates_limit:
                    dates = dates[: a.dates_limit]
                birds_all, used, fetched_all = [], 0, []
                for k, area in enumerate(areas):
                    left = None if a.max_requests is None else max(a.max_requests - used, 0)
                    if a.live and k > 0 and used > 0:
                        time.sleep(cfg["live"]["min_interval_s"])          # 場所の間でも間隔を空ける
                    if a.live and left == 0:
                        reports.append({"requests": 0, "cache_hits": 0, "misses": [], "warnings": [f"{area['name']}: --max-requests {a.max_requests} に達したため取得しない"],
                                        "rate_headers": {}, "shape": None, "truncated": []})
                        continue
                    i2, r2 = birds_live.fetch_bird_counts(area, dates, prof, now, cache=Cache(cdir), cfg=cfg, http_get=http_get, live=a.live,
                                                          cache_only=a.cache_only, max_requests=left, unparsed_dir=unparsed,
                                                          shape_check=a.shape_check, per_year=a.per_year)
                    if a.shape_check:
                        Path(a.shape_out or "shape.json").write_text(json.dumps(r2["shape"], ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
                        print(json.dumps({"requests": r2["requests"], "rate_headers": r2["rate_headers"], "shape_out": a.shape_out}, ensure_ascii=False))
                        return 0
                    used += r2["requests"]
                    birds_all += i2["birds"]
                    fetched_all.append(i2["fetched_at"])
                    reports.append(r2)
                inputs["birds"] = birds_all
                inputs["fetched_at"] = max([inputs["fetched_at"]] + fetched_all) if want_aut else max(fetched_all or [now.isoformat(timespec="seconds")])
        except ParseError as e:
            print(f"応答を読めないため中止: {e}", file=sys.stderr)
            return 6
        except livemod.LiveError as e:
            print(f"通信を中止: {e}", file=sys.stderr)
            return 5
        if a.inputs_out:
            Path(a.inputs_out).write_text(json.dumps(inputs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        result = engine.run(request, profiles=profs, sites=sites, inputs=inputs, now=now)
        d = result["diagnostics"]
        n_req, n_hit = sum(r["requests"] for r in reports), sum(r["cache_hits"] for r in reports)
        d["api_calls"], d["cache_hit"], d["cache_hits"] = n_req, (n_req == 0 and n_hit > 0), n_hit
        for r in reports:
            d["warnings"] += r["warnings"]
            if r.get("rate_headers"):
                d["rate_limit_headers"] = r["rate_headers"]
    else:
        if not a.inputs:
            print("--inputs か --cache-only か --live が必要です", file=sys.stderr)
            return 2
        inputs = json.loads(Path(a.inputs).read_text(encoding="utf-8"))
        result = engine.run(request, profiles=profs, sites=sites, inputs=inputs, now=now)
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
