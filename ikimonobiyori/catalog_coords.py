"""花の名所の座標を Wikidata で照合して入れる(段階33 1-1)。
- 取得元は official_map(承認した通信先の公式の地図)と wikidata だけ。このコードが通信するのは wikidata(承認済みの places-fetch と同じホスト・同じ上限の仕組み)だけ。
- 名称(日本語版ウィキペディアの記事名)で引き、項目の日本語の説明にカタログの市区町村(区があれば区も)がある(都道府県は座標が県の範囲に入ることで確かめる)・曖昧さ回避でない・複数の別項目に一致しない・
  座標が県の範囲に入る、をすべて満たすときだけ座標を入れる。満たさないときは座標なし(理由を残す。推測しない)。
- 範囲・桁数・語は ikimonobiyori/data/regional/policy.yaml の coordinates(コードに数値を持たない)。
- 通信は `--live`・BIYORI_ALLOW_LIVE=1・--max-requests・計測フック(BIYORI_REQ_LOG)が要る(guide places-fetch と同じ)。
  結果は IKIMONOBIYORI_DATA_DIR の下(catalog_coords/result.json)に書く。`apply` が結果をカタログのテキストに挿入する(通信しない)。

  python -X utf8 -m ikimonobiyori.catalog_coords fetch --live --max-requests N
  python -X utf8 -m ikimonobiyori.catalog_coords apply
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import catalog as catalog_mod
from . import livegate, paths, regional
from .fetch import wikidata

RESULT_REL = "catalog_coords/result.json"
CATALOG_PATH = Path(__file__).resolve().parent / "data" / "catalog" / "flowers.yaml"


def candidate_titles(entry):
    """名所の名称 → 引く記事名の候補(名称そのもの・かっこより前)。重複なし。"""
    name = entry["name"]
    out = [name]
    base = re.split(r"[(（]", name)[0].strip()
    if base and base not in out:
        out.append(base)
    return out


def city_key(city):
    """所在の市区町村 → 説明に必要な語(『横浜市中区』なら『横浜市』。区のない市町村はそのまま)。"""
    m = re.match(r"^(.+?市)", city or "")
    return m.group(1) if m else (city or "")


def judge(entry, hits, cp):
    """→ (座標 {lat, lon, qid, title} or None, 理由)。hits は {記事名: 項目}。cp は方針の coordinates。"""
    tags = entry.get("tags") or {}
    pref, city = tags.get("prefecture"), tags.get("city")
    bounds = (cp["bounds_by_prefecture"] or {}).get(pref)
    if not bounds or not city:
        return None, "範囲または市区町村の指定がない"
    found = {t: h for t, h in hits.items() if h and h.get("lat") is not None}
    if not found:
        return None, "Wikidata に座標つきの項目がない"
    if len({h["qid"] for h in found.values()}) > 1:
        return None, "複数の項目に一致して絞れない"
    title, hit = next(iter(found.items()))
    desc = hit.get("description") or ""
    if any(w in desc for w in cp["ambiguous_description_words"]):
        return None, "曖昧さ回避の項目"
    key = city_key(city)
    ward = city[len(key):] if city.startswith(key) else ""
    if key not in desc or (ward and "区" in desc.replace(key, "") and ward not in desc):
        return None, f"所在が一致しない(項目の説明: {desc or 'なし'})"
    lat, lon = hit["lat"], hit["lon"]
    if not (bounds["lat"][0] <= lat <= bounds["lat"][1] and bounds["lon"][0] <= lon <= bounds["lon"][1]):
        return None, "座標が県の範囲の外"
    return {"lat": round(lat, cp["decimals"]), "lon": round(lon, cp["decimals"]), "qid": hit["qid"], "title": title}, "ok"


def targets(doc, cp):
    """座標を入れる対象: point がなく、範囲の定めのある県の名所(退役は除く)。"""
    return [e for e in doc.get("entries") or []
            if not e.get("point") and e.get("status") != "retired" and (e.get("tags") or {}).get("prefecture") in cp["bounds_by_prefecture"]]


def resolve(entries, got, cp):
    rows = []
    for e in entries:
        hits = {t: got.get(t) for t in candidate_titles(e)}
        pt, why = judge(e, hits, cp)
        rows.append({"id": e["id"], "name": e["name"], "point": pt, "reason": why})
    return rows


def insert_points(text, rows, checked_on):
    """カタログのテキストに、見つかった座標を kind の行の後ろへ挿入する。→ (新しいテキスト, 入れた数)。"""
    n = 0
    for r in rows:
        pt = r["point"]
        if not pt:
            continue
        pat = re.compile(rf"(^  - id: {re.escape(r['id'])}\n(?:(?!^  - id: ).*\n)*?    kind: \w+\n)", re.M)
        ins = (f"    point:\n      lat: {pt['lat']}\n      lon: {pt['lon']}\n      elevation_m: null\n"
               f"    coordinate_source:\n      kind: wikidata\n      qid: {pt['qid']}\n      title: {pt['title']}\n      checked_on: '{checked_on}'\n")
        new, k = pat.subn(lambda m: m.group(1) + ins, text, count=1)
        if k:
            text, n = new, n + 1
    return text, n


def result_path():
    return paths.data_path(RESULT_REL)


def _fetch(a, http_get=None):
    import time
    if not a.live:
        print("fetch は --live が必要です", file=sys.stderr)
        return 2
    if http_get is None and not livegate.live_allowed():
        print(livegate.refusal(), file=sys.stderr)
        return 2
    if a.max_requests is None or a.max_requests < 1:
        print("--live は明示的な --max-requests (1 以上)が必要です", file=sys.stderr)
        return 2
    if http_get is None and not os.environ.get("BIYORI_REQ_LOG"):
        print("--live は計測フック(BIYORI_REQ_LOG)が有効なときだけ実行します", file=sys.stderr)
        return 2
    import yaml
    cfg = yaml.safe_load((Path(__file__).resolve().parent / "config.yaml").read_text(encoding="utf-8"))
    cp = regional.load_policy()["coordinates"]
    doc = catalog_mod.load_catalog("flowers")
    ents = targets(doc, cp)
    titles = sorted({t for e in ents for t in candidate_titles(e)})
    getter = None
    if http_get is None:
        from .fetch.live import SessionGetter
        t = cfg["live"]["request_timeout"]
        getter = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"])
    try:
        got, rep = wikidata.read_points(titles, http_get=http_get or getter, cfg=cfg, max_requests=a.max_requests,
                                        batch=cfg["live"]["wikidata"]["titles_per_request"], sleep=time.sleep)
    finally:
        if getter is not None:
            getter.close()
    rows = resolve(ents, got, cp)
    out = {"read_at": paths_now(), "report": rep, "rows": rows}
    p = result_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"targets": len(ents), "found": sum(1 for r in rows if r["point"]), "report": rep, "result": str(p)}, ensure_ascii=False, indent=1))
    return 0 if rep["status"] == "ok" else 1


def paths_now():
    from datetime import datetime
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _apply(a):
    data = json.loads(result_path().read_text(encoding="utf-8"))
    text = CATALOG_PATH.read_text(encoding="utf-8")
    new, n = insert_points(text, data["rows"], data["read_at"][:10])
    CATALOG_PATH.write_text(new, encoding="utf-8", newline="")
    print(json.dumps({"inserted": n, "no_point": [{"id": r["id"], "name": r["name"], "reason": r["reason"]} for r in data["rows"] if not r["point"]]},
                     ensure_ascii=False, indent=1))
    return 0


def main(argv=None, http_get=None):
    ap = argparse.ArgumentParser(prog="catalog_coords")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--live", action="store_true")
    f.add_argument("--max-requests", type=int)
    sub.add_parser("apply")
    a = ap.parse_args(argv)
    return _fetch(a, http_get) if a.cmd == "fetch" else _apply(a)


if __name__ == "__main__":
    sys.exit(main())
