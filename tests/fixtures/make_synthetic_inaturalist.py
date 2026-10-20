"""tests/fixtures/synthetic_inaturalist_sparse.json を作る。**SYNTHETIC(合成)。実際の iNaturalist の応答ではない。**
応答の形は iNaturalist API v1 /observations/species_counts の形(ikimonobiyori/fetch/inaturalist.py のパーサーが読む形)。
場所・種・件数はすべて架空。記録の少ない場所(件数不足 = min_total_observations 未満)の入力を作る。
iNaturalist の実際の応答は、利用条件を目視で確認するまで、このリポジトリには置かない(biyori-hub 側の記録を使う)。
実行: python tests/fixtures/make_synthetic_inaturalist.py"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
YEARS = ["2025", "2024", "2023", "2022", "2021"]
# 年ごとの (学名, 和名, 件数)。架空の値。合計 = 9(プロファイルの min_total_observations=30 に満たない)
COUNTS = {
    "2025": [("Parus minor", "シジュウカラ", 2), ("Passer montanus", "スズメ", 1)],
    "2024": [("Parus minor", "シジュウカラ", 3), ("Zosterops japonicus", "メジロ", 1), ("Corvus macrorhynchos", "ハシブトガラス", 1)],
    "2023": [("Parus minor", "シジュウカラ", 1)],
    "2022": [],
    "2021": [],
}
AREA = {"name": "合成の里山(synthetic)", "lat": 35.7, "lon": 139.1, "radius_km": 10}
D_RANGE = {"2025": ("2025-10-10", "2025-10-24"), "2024": ("2024-10-10", "2024-10-24"), "2023": ("2023-10-10", "2023-10-24"),
           "2022": ("2022-10-10", "2022-10-24"), "2021": ("2021-10-10", "2021-10-24")}


def response(rows, per_page=200):
    results = [{"count": c, "taxon": {"id": 20000 + i, "name": sci, "preferred_common_name": ja, "rank": "species", "iconic_taxon_name": "Aves"}}
               for i, (sci, ja, c) in enumerate(rows)]
    return {"total_results": len(results), "page": 1, "per_page": per_page, "results": results}


def url(year, per_page=200):
    d1, d2 = D_RANGE[year]
    return (f"https://api.inaturalist.org/v1/observations/species_counts?lat={AREA['lat']}&lng={AREA['lon']}&radius={AREA['radius_km']}"
            f"&d1={d1}&d2={d2}&iconic_taxa=Aves&quality_grade=research&per_page={per_page}")


def main():
    fetched = "2026-10-14T23:13:54+09:00"
    shape_rows = COUNTS["2024"]
    doc = {
        "schema": "ikimono-synthetic-inaturalist/1",
        "recorded": False,
        "synthetic": True,
        "note": "SYNTHETIC: 合成フィクスチャ。実際の iNaturalist の応答ではない。場所・種・件数はすべて架空(記録が少ない場所の入力)",
        "shape_check": {"url": url("2024", 10), "status": 200, "fetched_at": fetched, "rate_headers": {},
                        "fields_seen": {"top": ["page", "per_page", "results", "total_results"], "result": ["count", "taxon"]},
                        "minimized": response(shape_rows, 10)},
        "inputs": {
            "schema": "ikimono-inputs/1", "synthetic": True, "fetched_at": "2026-10-14T23:13:54+09:00",
            "birds": [{"area": AREA, "queries": [{
                "date": "2026-10-17",
                "years": {y: response(COUNTS[y]) for y in YEARS},
                "urls": {y: url(y) for y in YEARS},
                "fetched_at_by_year": {y: fetched for y in YEARS},
                "latest_observations": None}]}]},
    }
    (HERE / "synthetic_inaturalist_sparse.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print("OK total", sum(c for rows in COUNTS.values() for _, _, c in rows))


if __name__ == "__main__":
    main()
