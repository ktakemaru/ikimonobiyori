"""観察頻度の手法(野鳥)。場所×半径×週の過去の観察記録から、種ごとの相対頻度を出す。純粋・決定論。

相対頻度(0〜1)= 種の件数 ÷ 鳥類の観察記録の総数(同条件・過去 N 年分の合計)。点数の尺度名はプロファイルの scale.name。"""


def merge_counts(per_year_rows):
    """年ごとの species_counts の行をまとめる。→ ({key: {"name", "common_name", "taxon_id", "count"}}, 総数)。key は学名。"""
    merged, total = {}, 0
    for rows in per_year_rows:
        for r in rows:
            m = merged.setdefault(r["name"], {"name": r["name"], "common_name": r.get("common_name"),
                                              "taxon_id": r.get("taxon_id"), "count": 0})
            m["count"] += r["count"]
            if not m["common_name"] and r.get("common_name"):
                m["common_name"] = r["common_name"]
            total += r["count"]
    return merged, total


def relative_frequencies(per_year_rows, *, min_total, top_n):
    """戻り値: {"total", "years", "species": [{"name","common_name","taxon_id","count","relative_frequency"}], "enough": bool}
    相対頻度の降順、同率は学名の昇順(決定論)。総数が min_total 未満なら enough=False(提案を出さない)。"""
    merged, total = merge_counts(per_year_rows)
    enough = total >= min_total and total > 0
    species = []
    if enough:
        for m in merged.values():
            species.append(dict(m, relative_frequency=m["count"] / total))
        species.sort(key=lambda s: (-s["relative_frequency"], s["name"]))
        species = species[:top_n]
    return {"total": total, "years": len(per_year_rows), "species": species, "enough": enough}


def band_for(relative_frequency, *, maybe_min, max_band):
    """相対頻度が maybe_min 以上なら maybe、未満なら no。max_band を超える band は出さない(go を出さない)。"""
    band = "maybe" if relative_frequency >= maybe_min else "no"
    order = {"no": 0, "maybe": 1, "go": 2}
    return band if order[band] <= order[max_band] else max_band
