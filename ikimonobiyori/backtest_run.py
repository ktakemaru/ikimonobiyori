"""紅葉の答え合わせ(段階14)の実行。docs/validation-plan.md、docs/stage14-decisions.md。

  python -X utf8 -m ikimonobiyori.backtest_run plan   --now ISO8601
  BIYORI_ALLOW_LIVE=1 BIYORI_REQ_LOG=<絶対パス> BIYORI_REQ_MAX=N BIYORI_ALLOW_HOSTS=archive-api.open-meteo.com PYTHONPATH=<biyori-hub>/hub/measure
      python -X utf8 -m ikimonobiyori.backtest_run fetch --now ISO8601 --live --max-requests N [--limit K]
  python -X utf8 -m ikimonobiyori.backtest_run fetch --now ISO8601 --cache-only      # 通信しない(キャッシュにあるかの確認)
  python -X utf8 -m ikimonobiyori.backtest_run judge --now ISO8601 --normalized data/jma_phenology/normalized.csv --out-dir <出力先>   # 通信しない

fetch --live は BIYORI_ALLOW_LIVE=1・明示的な --max-requests・計測フック(BIYORI_REQ_LOG)が要る(main.py と同じ。このリポジトリ単独で実通信しない)。
問い合わせは決まった順(地点 → 年 → 標高の扱い)で先頭から --limit 件まで。キャッシュにあるものは通信しない。
書き込み先は IKIMONOBIYORI_DATA_DIR の下(キャッシュ・読めなかった応答・取得の記録 backtest/fetch_log.jsonl・結果 backtest/)。"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from ikimonobiyori import backtest, jma_phenology, livegate, paths, profiles  # noqa: E402
from ikimonobiyori.config import load_config  # noqa: E402
from ikimonobiyori.fetch import ParseError, archive_live  # noqa: E402
from ikimonobiyori.fetch.cache import Cache  # noqa: E402
from ikimonobiyori.fetch.live import LiveError  # noqa: E402


def _requests(plan):
    profile = profiles.load_profiles()["autumn_leaves"]
    stations = jma_phenology.load_definition()["stations"]
    return backtest.build_requests(plan, stations, profile), profile, stations


def main(argv=None, http_get=None, sleep=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="問い合わせの一覧と通信量の見積もり(通信しない)")
    f = sub.add_parser("fetch", help="過去の気温の取得(--live か --cache-only)")
    j = sub.add_parser("judge", help="キャッシュの気温と生物季節観測から集計・判定(通信しない)")
    for s in (p, f, j):
        s.add_argument("--now", required=True)
        s.add_argument("--cache-dir")
    f.add_argument("--live", action="store_true")
    f.add_argument("--cache-only", action="store_true")
    f.add_argument("--max-requests", type=int)
    f.add_argument("--limit", type=int, help="先頭から何件までを対象にするか(例: 1)")
    j.add_argument("--normalized", required=True)
    j.add_argument("--out-dir")
    a = ap.parse_args(argv)
    now = datetime.fromisoformat(a.now)
    if now.tzinfo is None:
        print("--now にはオフセットが必要です", file=sys.stderr)
        return 2
    cfg = load_config()
    plan = backtest.load_plan()
    reqs, profile, stations = _requests(plan)
    cache = Cache(a.cache_dir or paths.data_path(cfg["cache"]["dir"]))
    ttl = cfg["cache"]["ttl_s"]["open_meteo_archive"]
    cost = plan["cost"]

    if a.cmd == "plan":
        cached = sum(1 for r in reqs if cache.get(r["url"], r["params"], now=now, ttl_s=ttl)[0] is not None)
        todo = len(reqs) - cached
        print(json.dumps({"requests": len(reqs), "cached": cached, "to_fetch": todo,
                          "worst_case_calls": round(todo * cost["worst_case_calls_per_request"], 1), "daily_call_cap": cost["daily_call_cap"]}, ensure_ascii=False))
        return 0

    if a.cmd == "fetch":
        if a.live == a.cache_only:
            print("--live か --cache-only のどちらか一方が必要です", file=sys.stderr)
            return 2
        if a.live:
            if http_get is None and not livegate.live_allowed():
                print(livegate.refusal(), file=sys.stderr)
                return 4
            if a.max_requests is None or a.max_requests < 1:
                print("--live は明示的な --max-requests (1 以上)が必要です", file=sys.stderr)
                return 4
            if http_get is None and not os.environ.get("BIYORI_REQ_LOG"):
                print("--live は計測フック(BIYORI_REQ_LOG)が有効なときだけ実行します(許可リスト・上限の強制のため)", file=sys.stderr)
                return 4
        target = reqs[:a.limit] if a.limit else reqs
        todo = [r for r in target if cache.get(r["url"], r["params"], now=now, ttl_s=ttl)[0] is None]
        if a.live:
            sendable = min(len(todo), a.max_requests)
            est = sendable * cost["worst_case_calls_per_request"]
            if est > cost["daily_call_cap"]:
                print(f"今回送る見込み {sendable} 件の最悪の call {est:.0f} が上限 {cost['daily_call_cap']} を超える。--max-requests を減らして分けてください", file=sys.stderr)
                return 4
        log_path = paths.data_path("backtest") / "fetch_log.jsonl"

        def log(rec):
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        kw = {"sleep": sleep} if sleep else {}
        try:
            series, rep = archive_live.fetch_archive(target, cache=cache, cfg=cfg, now=now, http_get=http_get, live=a.live, cache_only=a.cache_only,
                                                     max_requests=a.max_requests, unparsed_dir=paths.data_path(cfg["cache"]["unparsed_dir"]), log=log, **kw)
        except (LiveError, ParseError) as e:
            print(f"中止: {e}", file=sys.stderr)
            return 3
        print(json.dumps({"selected": len(target), "got": len(series), "requests": rep["requests"], "cache_hits": rep["cache_hits"],
                          "not_fetched": len(rep["misses"]), "first_not_fetched": rep["misses"][:1], "warnings": rep["warnings"][:1]}, ensure_ascii=False))
        return 0

    # judge(通信しない)
    series, missing = {}, []
    for r in reqs:
        body, _ = archive_live.load_cached(r, cache, now=now, ttl_s=ttl, allow_expired=True)
        if body is None:
            missing.append(r["id"])
            continue
        try:
            series[r["id"]] = archive_live.check_shape(body, r)
        except ParseError as e:
            print(f"キャッシュの応答を読めない: {r['id']}: {e}", file=sys.stderr)
            return 3
    if missing:
        print(f"気温が揃っていない({len(missing)} 件): {missing[:5]}…。fetch で取得してから判定する(予測なしと取り違えない)", file=sys.stderr)
        return 3
    res = backtest.evaluate(plan, stations, profile, series, jma_phenology.read_csv(a.normalized))
    out_dir = Path(a.out_dir) if a.out_dir else paths.data_path("backtest")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    (out_dir / "result.md").write_text(backtest.result_markdown(res), encoding="utf-8", newline="\n")
    j_ = res["modes"][res["decisive_mode"]]["judge"]
    print(json.dumps({"passed": res["passed"], "reasons": j_["reasons"], "out_dir": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
