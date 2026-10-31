"""名所カタログ(data/catalog/<subject>.yaml)とプロファイルの検査器(段階13。docs/design.md §5)。通信しない・書き込まない。
形はスキーマ(schemas/site-catalog.schema.json)、方針(位置の粗さの下限・座標の桁)は data/catalog/policy.yaml から読む。コードに値を持たない。
v0 の判定(engine)はカタログを使わない。

  python -X utf8 -m ikimonobiyori.catalog check [--catalog-dir DIR] [--profiles-dir DIR]
"""
import argparse
import json
import math
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .paths import CATALOG_DIR, CATALOG_POLICY_PATH, CATALOG_SCHEMA_PATH, PROFILE_DIR
from .profiles import validate_profile

TIMING_TYPES = ("temperature", "calendar", "managed", "frequency", "episodic")
LEAP_YEAR = 2000          # MM-DD の妥当性を見るための閏年(02-29 を許す)。閾値ではない


def load_policy(path=None):
    return yaml.safe_load(Path(path or CATALOG_POLICY_PATH).read_text(encoding="utf-8"))


def schema_errors(doc):
    v = Draft202012Validator(json.loads(CATALOG_SCHEMA_PATH.read_text(encoding="utf-8")))
    return ["/".join(map(str, e.path)) + ": " + e.message[:160] for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path))]


def decimals(x):
    """座標の小数の桁数(末尾の 0 は数えない)。35.0 → 0、35.65 → 2。"""
    exp = Decimal(repr(x)).normalize().as_tuple().exponent
    return max(0, -exp)


def coarseness(policy, precision):
    return policy["precision_order"].index(precision)


def min_precision(policy, entry):
    """この件の位置の粗さの下限と、その理由。複数の対象を持つ件は、いちばん粗い下限。"""
    mins = policy["min_location_precision"]
    floor, why = mins["default"], "default"
    for s in entry["subjects"]:
        p = mins.get(s, mins["default"])
        if coarseness(policy, p) > coarseness(policy, floor):
            floor, why = p, s
    if entry.get("public_venue") and all(s in policy["public_venue_exception"] for s in entry["subjects"] if s in mins):
        floor, why = mins["default"], "public_venue"
    if entry.get("sensitive"):
        p = policy["sensitive_min_location_precision"]
        if coarseness(policy, p) > coarseness(policy, floor):
            floor, why = p, "sensitive"
    return floor, why


def distance_km(lat1, lon1, lat2, lon2, radius_km):
    """2 点の大円距離(球の近似)。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def nearest_origin_km(policy, pt):
    """方針の起点(東京・横浜)のうち近いほうまでの距離。方針に range_limit がなければ None。→ (km, 起点の名前)"""
    rl = policy.get("range_limit")
    if not rl:
        return None
    return min((distance_km(pt["lat"], pt["lon"], o["lat"], o["lon"], rl["earth_radius_km"]), o["name"]) for o in rl["origins"])


def origin_names(policy):
    return [o["name"] for o in policy["range_limit"]["origins"]]


def resolve_origin(policy, origin=None):
    """出発地の名前(省略すると方針の default_origin)。方針の origins にない名前は ValueError(推測しない)。"""
    name = origin or policy["range_limit"]["default_origin"]
    if name not in origin_names(policy):
        raise ValueError(f"出発地 {name} は {origin_names(policy)} のどれでもない")
    return name


def range_from(policy, pt, origin=None):
    """出発地から見た範囲(段階23 の続き)。→ {"origin", "km"(整数), "status": in_range / edge / out_of_range}。
    max_km より先は範囲の外、edge_min_km 以上 max_km 以下は範囲の端。"""
    rl = policy["range_limit"]
    name = resolve_origin(policy, origin)
    o = next(x for x in rl["origins"] if x["name"] == name)
    km = distance_km(pt["lat"], pt["lon"], o["lat"], o["lon"], rl["earth_radius_km"])
    edge = rl["edge_min_km"]["value"] if isinstance(rl["edge_min_km"], dict) else rl["edge_min_km"]
    status = "out_of_range" if km > rl["max_km"] else "edge" if km >= edge else "in_range"
    return {"origin": name, "km": int(round(km)), "status": status}


def valid_month_day(s):
    m, d = (int(x) for x in s.split("-"))
    try:
        date(LEAP_YEAR, m, d)
    except ValueError:
        return False
    return True


def valid_date(s):
    try:
        date.fromisoformat(s)
    except (TypeError, ValueError):
        return False
    return True


def check_entry(entry, *, subject, profile_ids, policy):
    """スキーマで見られない規則。→ エラーのリスト。entry はスキーマに通っている前提。"""
    errs = []
    eid = entry["id"]
    if subject not in entry["subjects"]:
        errs.append(f"{eid}: subjects にファイルの対象 {subject} がない")
    for s in entry["subjects"]:
        if s not in profile_ids:
            errs.append(f"{eid}: 未知の対象 {s}(プロファイルがない)")
    if any(s not in profile_ids for s in entry["subjects"]):
        return errs
    floor, why = min_precision(policy, entry)
    if coarseness(policy, entry["location_precision"]) < coarseness(policy, floor):
        errs.append(f"{eid}: 位置が細かすぎる(location_precision={entry['location_precision']}、下限={floor}〔{why}〕)")
    limit = policy["precision_decimals"][entry["location_precision"]]
    pt = entry.get("point")
    if pt and limit is not None:
        for k in ("lat", "lon"):
            if decimals(pt[k]) > limit:
                errs.append(f"{eid}: point.{k}={pt[k]} が {entry['location_precision']} より細かい(小数 {limit} 桁まで)")
    near = nearest_origin_km(policy, pt) if pt else None
    if near and near[0] > policy["range_limit"]["max_km"]:
        errs.append(f"{eid}: 範囲外(近い起点 {near[1]} から {near[0]:.0f} km。上限 {policy['range_limit']['max_km']} km)")
    tw = entry.get("typical_window")
    if tw:
        for k in ("start", "end"):
            if not valid_month_day(tw[k]):
                errs.append(f"{eid}: typical_window.{k}={tw[k]} は存在しない日付")
    for w in entry.get("flower_windows") or []:                       # 花の種類ごとの例年の時期(段階32)
        for k in ("start", "end"):
            if not valid_month_day(w[k]):
                errs.append(f"{eid}: flower_windows[{w['kind']}].{k}={w[k]} は存在しない日付")
    for ev in entry.get("events") or []:                              # 今年のイベント期間(段階32)
        for k in ("start", "end", "checked_on"):
            if not valid_date(ev[k]):
                errs.append(f"{eid}: events[{ev['name']}].{k}={ev[k]} は日付でない")
        if valid_date(ev["start"]) and valid_date(ev["end"]):
            if ev["start"] > ev["end"]:
                errs.append(f"{eid}: events[{ev['name']}] の start が end より後")
            if int(ev["start"][:4]) != ev["year"]:
                errs.append(f"{eid}: events[{ev['name']}] の year={ev['year']} が start の年と違う(前年の日付を今年として扱わない)")
        if ev["verified"] and ev["source_url"] not in [s["url"] for s in entry["sources"]] + [entry.get("official_status_url")] + [w["source_url"] for w in entry.get("flower_windows") or []]:
            errs.append(f"{eid}: events[{ev['name']}] は verified だが、出典 {ev['source_url']} がカタログの sources・flower_windows にない")
    for k in ("approved_at", "retired_at"):
        if k in entry and not valid_date(entry[k]):
            errs.append(f"{eid}: {k}={entry[k]} は日付でない")
    for i, src in enumerate(entry["sources"]):
        if "checked_on" in src and not valid_date(src["checked_on"]):
            errs.append(f"{eid}: sources[{i}].checked_on={src['checked_on']} は日付でない")
    if entry.get("example") and entry["status"] == "approved":
        errs.append(f"{eid}: 例(example: true)は approved にできない")
    return errs


def check_catalog(doc, *, name, profile_ids, policy):
    """1ファイルの検査。name はファイル名の stem(= subject)。→ エラーのリスト(空 = 合格)。"""
    errs = schema_errors(doc)
    if errs:
        return errs
    if doc["subject"] != name:
        errs.append(f"subject={doc['subject']} がファイル名 {name} と違う")
    if doc["subject"] not in profile_ids:
        errs.append(f"subject={doc['subject']} のプロファイルがない")
    seen = set()
    for e in doc["entries"]:
        if e["id"] in seen:
            errs.append(f"{e['id']}: id が重複")
        seen.add(e["id"])
        errs += check_entry(e, subject=doc["subject"], profile_ids=profile_ids, policy=policy)
    return errs


def check_profile(doc):
    """プロファイルの検査(ikimono-profile/1 + timing_type があること)。"""
    errs = validate_profile(doc)
    if not errs and doc.get("timing_type") not in TIMING_TYPES:
        errs.append(f"timing_type がない、または未知({doc.get('timing_type')!r})")
    return errs


def usable_description(entry):
    """提案に使ってよい解説。approved で approved_at と sources がそろい、例でないものだけ。それ以外は None。"""
    if entry.get("status") != "approved" or not entry.get("approved_at") or not entry.get("sources") or entry.get("example"):
        return None
    return entry.get("description")


def approved_entries(doc):
    """提案に使ってよい件(approved だけ。candidate・retired・例は使わない)。"""
    return [e for e in doc.get("entries") or [] if e.get("status") == "approved" and not e.get("example")]


def load_catalog(subject, catalog_dir=None):
    """本番のカタログ(data/catalog/<subject>.yaml)。なければ None。"""
    p = Path(catalog_dir or CATALOG_DIR) / f"{subject}.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.is_file() else None


def catalog_sites(doc):
    """承認済み(approved)で point のある件 → 地点の辞書 {id: site}(段階14b。sites.yaml の 76 地点と同じ形 + 名所の項目)。
    site_ref は名所カタログを指す(ikimonobiyori:<id>)。region はカタログにないので None。candidate・retired・例・point のない件は入れない。"""
    out = {}
    for e in approved_entries(doc or {}):
        pt = e.get("point")
        if not pt:
            continue
        out[e["id"]] = {"id": e["id"], "name": e["name"], "lat": pt["lat"], "lon": pt["lon"], "elevation_m": pt.get("elevation_m"),
                        "region": None, "kind": "catalog", "site_ref": f"ikimonobiyori:{e['id']}",
                        "location_precision": e["location_precision"],
                        "sources": [{k: v for k, v in src.items() if k in ("url", "title", "checked_on")} for src in e["sources"]],
                        "landmark": {"id": e["id"], "approved_at": e["approved_at"], "typical_window": e.get("typical_window"),
                                    "official_status_url": e.get("official_status_url"), "note": e.get("note")}}
    return out


def check_all(catalog_dir=None, profiles_dir=None, policy_path=None):
    """→ [(ファイル, エラーのリスト)]。"""
    out, ids = [], set()
    for p in sorted(Path(profiles_dir or PROFILE_DIR).glob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        errs = check_profile(doc) if isinstance(doc, dict) else ["YAML の最上位が辞書でない"]
        out.append((p, errs))
        if not errs:
            ids.add(doc["profile_id"])
    policy = load_policy(policy_path)
    pol_path = Path(policy_path or CATALOG_POLICY_PATH).resolve()
    for p in sorted(Path(catalog_dir or CATALOG_DIR).glob("*.yaml")):
        if p.resolve() == pol_path:
            continue
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        errs = check_catalog(doc, name=p.stem, profile_ids=ids, policy=policy) if isinstance(doc, dict) else ["YAML の最上位が辞書でない"]
        out.append((p, errs))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ikimonobiyori.catalog")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="カタログとプロファイルを検査する(通信しない・書き込まない)")
    c.add_argument("--catalog-dir")
    c.add_argument("--profiles-dir")
    c.add_argument("--policy")
    a = ap.parse_args(argv)
    bad = 0
    for p, errs in check_all(a.catalog_dir, a.profiles_dir, a.policy):
        if errs:
            bad += 1
            for e in errs:
                print(f"NG  {p.parent.name}/{p.name}: {e}")
        else:
            print(f"OK  {p.parent.name}/{p.name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
