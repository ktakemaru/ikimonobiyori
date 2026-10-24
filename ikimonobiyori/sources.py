"""現地の現況を発信する公式ページの台帳と、読んだ結果の記録(段階15。docs/design.md §0)。通信しない。
- 台帳 data/sources/<subject>.yaml(スキーマ schemas/status-sources.schema.json)の検査。名所カタログの status_sources と突き合わせる。
- 公式の状態の書き方(記号・語)→ 共通の段階の対応(台帳の notation.map)。見ていない書き方は推測しない(段階は None)。
- 「今週末のおすすめ」の候補の絞り込み(名所カタログの例年の時期)と、読む情報源の一覧。
- 読んだ結果の事実だけの記録(IKIMONOBIYORI_DATA_DIR の下の JSON Lines)。本文の写しを入れる欄は作らない。
ページの読み取りはエージェント(Claude Code / Codex)が行う。ここに取得・スクレイピングのコードは書かない。
値(段階・新しさの日数・候補の幅・記録の項目)は data/sources/policy.yaml から読み、コードに持たない。

  python -X utf8 -m ikimonobiyori.sources check
  python -X utf8 -m ikimonobiyori.sources weekend --now 2026-10-23T21:00:00+09:00 [--date 2026-10-24 ...]
  python -X utf8 -m ikimonobiyori.sources normalize --source nikko-kankou-autumn-leaves --state ◎
  python -X utf8 -m ikimonobiyori.sources record --read-at 2026-10-23T21:00:00+09:00 --batch reads.json
  python -X utf8 -m ikimonobiyori.sources log [--source ID] [--include-erroneous]
  python -X utf8 -m ikimonobiyori.sources summary --now 2026-10-23T21:00:00+09:00 [--date 2026-10-31 ...]
  python -X utf8 -m ikimonobiyori.sources mark-erroneous --match '{"name": "湖尻", ...}' --reason ... --corrected-on 2026-10-23
  python -X utf8 -m ikimonobiyori.sources supersede --match '{"name": "湖尻", ...}' --reason ... --on 2026-10-24
  python -X utf8 -m ikimonobiyori.sources v0 --proposal OUT.json [--date 2026-10-24 ...]
"""
import argparse
import calendar
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft202012Validator

from . import catalog as catalog_mod
from . import livegate
from .config import load_config
from .paths import REGIONS_PATH, SOURCES_DIR, SOURCES_POLICY_PATH, SOURCES_SCHEMA_PATH, data_path

APPROVED = "approved"
USABLE_TERMS = "no_prohibition_found"
READABLE_OK = "ok"
REFERENCE = "reference_link"                              # 参考リンク(段階17 の見直し。現況の情報源に数えない)
V0_ID_PARTS = ("agent", "subject", "date", "site")        # v0 の提案の id の形: ikimonobiyori:<subject>:<日付>:<名所>
ROBOTS_BLOCKING = ("disallows", "ai_agents_blocked")      # 仮承認しない robots.txt の判定(安全側。docs/stage15-decisions.md)


# ---- 読み込み ----

def load_policy(path=None, profiles_dir=None):
    """方針(data/sources/policy.yaml)。対象ごとの段階(stages)は、各プロファイルの stages を policy["stages"][<対象>] に置く(段階16 B-1。正本はプロファイル)。"""
    from .profiles import load_profiles
    pol = yaml.safe_load(Path(path or SOURCES_POLICY_PATH).read_text(encoding="utf-8"))
    pol["stages"] = {pid: prof["stages"] for pid, prof in load_profiles(profiles_dir).items() if prof.get("stages")}
    return pol


def stage_errors(policy):
    """各プロファイルの段階が、共通の順番(common_stages の order)に対応し、早い → 遅いに並んでいるか。→ エラーのリスト。"""
    common = [s["order"] for s in policy["common_stages"]["items"]]
    errs = []
    for subject, st in policy["stages"].items():
        orders = [s["order"] for s in st["items"]]
        if any(o not in common for o in orders):
            errs.append(f"{subject}: stages の order {orders} に共通の順番 {common} にないものがある")
        if orders != sorted(set(orders)):
            errs.append(f"{subject}: stages の order {orders} が早い → 遅いに並んでいない(または重複)")
        if len({s['id'] for s in st["items"]}) != len(st["items"]):
            errs.append(f"{subject}: stages の id が重複")
    return errs


def stage_order(policy, subject, stage):
    """対象の段階 id → 共通の順番(0 前・1 始まり・2 見ごろ・3 最盛・4 終わり)。なければ None。"""
    return next((s["order"] for s in policy["stages"][subject]["items"] if s["id"] == stage), None)


def scope_orders(policy, early=False, late=False):
    """質問の型③: 答えに含める共通の順番。既定は見ごろ・最盛。early で始まり、late で終わりを足す。"""
    sc = policy["stage_scope"]
    return sorted(set(sc["default"]) | (set(sc["early"]) if early else set()) | (set(sc["late"]) if late else set()))


def load_registry(subject, sources_dir=None):
    """本番の台帳(data/sources/<subject>.yaml)。なければ None。"""
    p = Path(sources_dir or SOURCES_DIR) / f"{subject}.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.is_file() else None


def val(x):
    """方針の値は {value, source, provisional} の形。値だけを取り出す。"""
    return x["value"] if isinstance(x, dict) and "value" in x else x


def stage_ids(policy, subject):
    return [s["id"] for s in policy["stages"][subject]["items"]]


def stage_label(policy, subject, stage):
    return next((s["label"] for s in policy["stages"][subject]["items"] if s["id"] == stage), None)


def sources_by_id(registry):
    return {s["id"]: s for s in (registry or {}).get("sources") or []}


def is_approved(src):
    return src.get("approval", {}).get("status") == APPROVED


# ---- 台帳の検査 ----

def schema_errors(doc):
    v = Draft202012Validator(json.loads(SOURCES_SCHEMA_PATH.read_text(encoding="utf-8")))
    return ["/".join(map(str, e.path)) + ": " + e.message[:160] for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path))]


def check_source(src, *, subject, policy, catalog_ids):
    """スキーマで見られない規則。→ エラーのリスト。src はスキーマに通っている前提。"""
    errs, sid = [], src["id"]
    stages = stage_ids(policy, subject)
    for raw, st in ((src.get("notation") or {}).get("map") or {}).items():
        if st not in stages:
            errs.append(f"{sid}: notation.map の {raw!r} → {st} は共通の段階にない({', '.join(stages)})")
    if src.get("reader") == "code":
        from .fetch import status_pages
        if sid not in status_pages.PARSERS:
            errs.append(f"{sid}: reader: code はコードの読み方がある情報源だけ({sorted(status_pages.PARSERS)})")
        hosts = load_config()["live"]["allowed_hosts_by_subject"].get(status_pages.SUBJECT_HOSTS) or []
        if urlsplit(src["url"]).netloc not in hosts:
            errs.append(f"{sid}: reader: code の url のホストが許可リスト(config.yaml の {status_pages.SUBJECT_HOSTS})にない")
    for c in src["covers"]:
        if "site" in c and c["site"] not in catalog_ids:
            errs.append(f"{sid}: covers の site={c['site']} が名所カタログの承認済みの件にない")
    rd, ap, terms = src["readable"], src["approval"], src["terms"]
    for k, v in (("readable.checked_on", rd.get("checked_on")), ("readable.observed_latest_update", rd.get("observed_latest_update")),
                 ("approval.approved_on", ap.get("approved_on"))):
        if v is not None and not catalog_mod.valid_date(v):
            errs.append(f"{sid}: {k}={v} は日付でない")
    if ap["status"] == APPROVED:
        if not ap.get("approved_by") or not ap.get("approved_on"):
            errs.append(f"{sid}: approved には approved_by と approved_on が要る")
        if rd["status"] != READABLE_OK:
            errs.append(f"{sid}: 読めていない(readable.status={rd['status']})情報源は承認できない")
        if rd.get("robots") in ROBOTS_BLOCKING:
            errs.append(f"{sid}: robots.txt が拒否している(readable.robots={rd['robots']})情報源は承認できない")
        if terms["status"] != USABLE_TERMS:
            errs.append(f"{sid}: 利用条件を確かめて禁止がない(terms.status={USABLE_TERMS})ものだけ承認できる(今は {terms['status']})")
    elif ap["status"] in ("pending", "revoked") and not ap.get("reason") and _fails_conditions(src):
        errs.append(f"{sid}: 承認の条件を満たさない pending・revoked には reason が要る")
    return errs


def _fails_conditions(src):
    rd = src["readable"]
    return rd["status"] != READABLE_OK or rd.get("robots") in ROBOTS_BLOCKING or src["terms"]["status"] != USABLE_TERMS


def check_registry(doc, *, name, catalog_doc, policy):
    """1ファイルの検査。name はファイル名の stem(= subject)。catalog_doc は同じ対象の名所カタログ(なければ None)。"""
    errs = schema_errors(doc)
    if errs:
        return errs
    subject = doc["subject"]
    if subject != name:
        errs.append(f"subject={subject} がファイル名 {name} と違う")
    if subject not in policy["stages"]:
        return errs + [f"subject={subject} の共通の段階が方針(policy.yaml の stages)にない"]
    entries = catalog_mod.approved_entries(catalog_doc or {})
    catalog_ids = {e["id"] for e in entries}
    seen = set()
    for src in doc["sources"]:
        if src["id"] in seen:
            errs.append(f"{src['id']}: id が重複")
        seen.add(src["id"])
        errs += check_source(src, subject=subject, policy=policy, catalog_ids=catalog_ids)
    # 名所カタログの status_sources と台帳の covers が一致すること(どちらから見ても同じ対応)
    covered = {}
    for src in doc["sources"]:
        for c in src["covers"]:
            if "site" in c:
                covered.setdefault(c["site"], set()).add(src["id"])
    for e in entries:
        listed = set(e.get("status_sources") or [])
        for sid in sorted(listed - seen):
            errs.append(f"カタログ {e['id']}: status_sources の {sid} が台帳にない")
        if listed & seen != covered.get(e["id"], set()):
            errs.append(f"カタログ {e['id']}: status_sources {sorted(listed & seen)} と、台帳でこの名所を covers に持つ情報源 {sorted(covered.get(e['id'], set()))} が違う")
    return errs


def check_all(sources_dir=None, catalog_dir=None, policy_path=None):
    """→ [(台帳のファイル, エラーのリスト)]。段階の並び(プロファイル)の検査は stage_errors(check コマンドが両方を出す)。"""
    policy = load_policy(policy_path)
    pol = Path(policy_path or SOURCES_POLICY_PATH).resolve()
    out = []
    for p in sorted(Path(sources_dir or SOURCES_DIR).glob("*.yaml")):
        if p.resolve() == pol:
            continue
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            out.append((p, ["YAML の最上位が辞書でない"]))
            continue
        out.append((p, check_registry(doc, name=p.stem, catalog_doc=catalog_mod.load_catalog(p.stem, catalog_dir), policy=policy)))
    return out


# ---- 状態の書き方 → 共通の段階 ----

def normalize_state(src, raw):
    """公式の状態(記号・語)→ (段階 or None, 区分)。区分: mapped(対応あり)/ no_info(情報なしの書き方)/ unknown(台帳にない書き方)。
    台帳にない書き方は推測で段階にしない(None。原文は記録に残す)。"""
    if raw is None:
        return None, "no_info"
    s = str(raw).strip()
    nt = src.get("notation") or {}
    s = (nt.get("icons") or {}).get(s, s)                 # アイコンの名前(箱根の icon_lev1 など。段階16 A-3)→ 公式の語
    if s in (nt.get("map") or {}):
        return nt["map"][s], "mapped"
    if s in (nt.get("no_info") or []):
        return None, "no_info"
    return None, "unknown"


# ---- 新しさ ----

def year_unknown(src, rec=None):
    """更新日の年が公式ページにない(台帳の notation.year_shown: false)か、記録で年を補った(updated_year_inferred)か。"""
    return (src or {}).get("notation", {}).get("year_shown") is False or bool((rec or {}).get("updated_year_inferred"))


def freshness(updated, on, policy, year_inferred=False):
    """公式の更新日(date か None)から on(date)までの日数で分ける。→ {age_days, class, label}。
    年を補った更新日(year_inferred)は日数で分けず「新しさ不明」(前年の日付かもしれない。ユーザーの見直し 2026-10-23)。
    更新日が on より後なら ValueError(年の補い方の誤りなど。推測で直さない)。"""
    fr = policy["freshness"]
    if updated is None:
        return {"age_days": None, "class": "unknown", "label": fr["labels"]["unknown"]}
    if year_inferred:
        return {"age_days": None, "class": "year_unknown", "label": fr["labels"]["year_unknown"]}
    age = (on - updated).days
    if age < 0:
        raise ValueError(f"公式の更新日 {updated} が {on} より後")
    cls = "fresh" if age <= val(fr["fresh_max_days"]) else "somewhat_old" if age <= val(fr["somewhat_old_max_days"]) else "old"
    return {"age_days": age, "class": cls, "label": fr["labels"][cls]}


# ---- 公式の見頃予測(段階16 A-8) ----

FORECAST_RE = re.compile(r"^\s*(\d{1,2})月(上旬|中旬|下旬)?\s*(?:[～〜~ー-]\s*(?:(\d{1,2})月)?(上旬|中旬|下旬)?)?")


def forecast_window(text, year, policy):
    """公式の見頃予測の原文(「10月下旬～11月上旬」「9月下旬」「11月上旬～11月下旬(場所や木によって異なります)」)→ (始まりの日, 終わりの日)。
    year は始まりの月の年。終わりの月が始まりより前なら翌年(12月〜1月など)。旬のない月は月の初日〜末日。読めなければ None(推測しない)。"""
    if not text:
        return None
    m = FORECAST_RE.match(str(text))
    if not m:
        return None
    thirds = policy["month_thirds"]["items"]
    m1, t1, m2, t2 = int(m.group(1)), m.group(2), m.group(3), m.group(4)
    if m2 is None and t2 is None and m.group(0).rstrip()[-1:] in "～〜~ー-":
        return None                                          # 「10月下旬～」のように終わりがない
    m2 = int(m2) if m2 else m1
    t2 = t2 if (t2 or m.group(3)) else t1
    if not (calendar.JANUARY <= m1 <= calendar.DECEMBER and calendar.JANUARY <= m2 <= calendar.DECEMBER):
        return None
    y2 = year + 1 if m2 < m1 else year
    first = thirds[t1]["first"] if t1 else 1
    last_day = calendar.monthrange(y2, m2)[1]
    last = (thirds[t2]["last"] or last_day) if t2 else last_day
    start, end = date(year, m1, first), date(y2, m2, min(last, last_day))
    return (start, end) if start <= end else None


def overlaps(window, dates):
    return window is not None and any(window[0] <= d <= window[1] for d in dates)


def stale_display_suspect(rec, entry, policy, src=None):
    """年のない更新日で「終わり」の段階なのに、その日付が名所カタログの例年の時期の始まりより前 → 前のシーズンの表示が残っている可能性(段階16 A-3。箱根の強羅)。
    カタログの件(entry)と例年の時期がないときは判定しない(False)。"""
    tw = (entry or {}).get("typical_window")
    up = rec.get("official_updated")
    if not tw or not up or not year_unknown(src, rec) or rec.get("stage") != stage_ids(policy, rec["subject"])[-1]:
        return False
    u = date.fromisoformat(up)
    start = _md_date(u.year, tw["start"])
    return u < start and tw["start"] <= tw["end"]


# ---- 対象の日と候補 ----

def parse_now(s):
    """ISO 8601(オフセット必須)。"""
    t = datetime.fromisoformat(s)
    if t.tzinfo is None:
        raise ValueError(f"時刻にオフセットがない: {s}")
    return t


def next_weekend(now):
    """次の土日(その場所の暦日)。土曜なら当日と翌日、日曜なら当日だけ、平日は次の土曜と日曜。"""
    d = now.date()
    wd = d.weekday()
    if wd == calendar.SUNDAY:
        return [d]
    sat = d + timedelta(days=(calendar.SATURDAY - wd))
    return [sat, sat + timedelta(days=1)]


def _md_date(year, md):
    m, d = (int(x) for x in md.split("-"))
    last = calendar.monthrange(year, m)[1]
    return date(year, m, min(d, last))                     # 02-29 は平年では 02-28


def days_from_window(d, tw):
    """d が例年の時期(MM-DD〜MM-DD。start > end は年をまたぐ)に入っていれば 0、外なら近い端までの日数。"""
    best = None
    for y in (d.year - 1, d.year, d.year + 1):
        s = _md_date(y, tw["start"])
        e = _md_date(y + 1 if tw["start"] > tw["end"] else y, tw["end"])
        dist = 0 if s <= d <= e else min(abs((d - s).days), abs((d - e).days))
        best = dist if best is None else min(best, dist)
    return best


# ---- 地域・条件・対象(段階16 B-3・B-4) ----

def load_regions(path=None):
    return yaml.safe_load(Path(path or REGIONS_PATH).read_text(encoding="utf-8"))


def resolve_region(query, regions_doc):
    """地域の呼び名(名前・別名に完全一致)→ 地域。なければ None(推測で近いものを選ばない)。"""
    q = (query or "").strip()
    return next((r for r in regions_doc["regions"] if q == r["name"] or q in (r.get("aliases") or [])), None)


def in_region(entry, region):
    t, m = entry.get("tags") or {}, region.get("match") or {}
    return t.get("prefecture") in (m.get("prefectures") or []) or t.get("area") in (m.get("areas") or [])


def site_filter(entry, *, region=None, terrain=None, access=None, flower_kind=None):
    """質問の型②・④: 地域(regions.yaml)・地形(tags.terrain のどれか)・行き方(tags.access のどれか)・花の種類(tags.flower_kinds のどれか。段階17)で絞る。
    tags のない項目は「分からない」ので外す。"""
    t = entry.get("tags") or {}
    if flower_kind and not set(flower_kind) & set(t.get("flower_kinds") or []):
        return False
    if region is not None and not in_region(entry, region):
        return False
    if terrain and not set(terrain) & set(t.get("terrain") or []):
        return False
    if access and not set(access) & set(t.get("access") or []):
        return False
    return True


def region_report(region, *, catalogs, catalog_policy):
    """地域について、対象ごとの名所カタログの件数と、範囲(東京・横浜から直線 max_km)の内外を代表点で示す(質問の型⑤)。
    status: in_range(代表点がすべて範囲内か、代表点がなく名所がある)/ partial(一部が範囲内)/ out_of_range(すべて範囲外)/ unknown"""
    rl = catalog_policy["range_limit"]
    pts = []
    for p in region.get("points") or []:
        km, origin = catalog_mod.nearest_origin_km(catalog_policy, p)
        pts.append({"name": p["name"], "prefecture": p.get("prefecture"), "km": round(km), "from": origin, "within": km <= rl["max_km"]})
    sites = {subj: [e["id"] for e in catalog_mod.approved_entries(doc or {}) if in_region(e, region)] for subj, doc in catalogs.items()}
    inside = [p for p in pts if p["within"]]
    if pts:
        status = "in_range" if len(inside) == len(pts) else "partial" if inside else "out_of_range"
    else:
        status = "in_range" if any(sites.values()) else "unknown"
    by_pref = {}
    for p in inside:
        by_pref.setdefault(p["prefecture"], []).append(p["name"])
    return {"region": region["name"], "status": status, "max_km": rl["max_km"], "points": pts, "within_points_by_prefecture": by_pref,
            "catalog_sites": sites, "note": region.get("note")}


def subjects_status(sources_dir=None, profiles_dir=None, catalog_dir=None, policy=None):
    """対象ごとに、この手順で答えられるか(台帳・名所カタログ・プロファイルの stages がそろっている = implemented)。
    → [{subject, name, implemented, missing, engine_status, unimplemented_answer?}]
    implemented は「見頃・おすすめの手順で答えられるか」。プロファイルの status(engine_status)は v0 の計算(エンジン)の状態で、別のもの
    (段階17: birds は engine_status が implemented なのに手順では答えられなかった。docs/stage17-decisions.md)。
    答えられない対象には、答え方の 1〜2 文(方針の unimplemented。近い対象が答えられるときだけ添える)。"""
    from .profiles import load_profiles
    profs = load_profiles(profiles_dir)
    out = []
    for pid, prof in profs.items():
        checks = (("stages", bool(prof.get("stages"))),
                  ("台帳", (Path(sources_dir or SOURCES_DIR) / f"{pid}.yaml").is_file()),
                  ("名所カタログ", bool(catalog_mod.approved_entries(catalog_mod.load_catalog(pid, catalog_dir) or {}))))
        missing = [k for k, ok in checks if not ok]
        out.append({"subject": pid, "name": prof["name"], "implemented": not missing, "missing": missing, "engine_status": prof.get("status")})
    ready = {r["subject"]: r["name"] for r in out if r["implemented"]}
    un = (policy or load_policy(profiles_dir=profiles_dir))["unimplemented"]
    for r in out:
        if not r["implemented"]:
            rel = (un.get("related") or {}).get(r["subject"])
            r["unimplemented_answer"] = un["text"].format(name=r["name"]) + (un["related_text"].format(related=ready[rel]) if rel in ready else "")
    return out


def topic_subjects(word, policy):
    """質問の話題(「野鳥」など。方針の topics)→ 答える対象のリスト。なければ None(推測で選ばない)。"""
    return (policy.get("topics") or {}).get("items", {}).get((word or "").strip())


def horizon(now, dates, policy):
    """質問の型①: 読んだ日から horizon_days より先の日。→ {days, beyond: [日付]}(先の日は公式の見頃予測と例年の時期だけで答える)"""
    days = val(policy["horizon_days"])
    return {"days": days, "beyond": [d.isoformat() for d in dates if (d - now.date()).days > days]}


def next_window_start(d, tw):
    """d の日以後で最も近い、例年の時期の始まりの日(今年か来年)。"""
    s = _md_date(d.year, tw["start"])
    return s if s >= d else _md_date(d.year + 1, tw["start"])


def candidates(catalog_doc, registry, dates, policy, *, region=None, terrain=None, access=None, flower_kind=None):
    """名所カタログ(承認済み)から候補を絞り、読む情報源を 1 回ずつにまとめる。→ 辞書(JSON にできる)。
    region(regions.yaml の地域)・terrain・access を渡すと、名所の tags で先に絞る(段階16 B-4)。"""
    margin = val(policy["candidates"]["window_margin_days"])
    srcs = sources_by_id(registry)
    sites, out_of_season = [], []
    for e in catalog_mod.approved_entries(catalog_doc or {}):
        if not site_filter(e, region=region, terrain=terrain, access=access, flower_kind=flower_kind):
            continue
        tw = e.get("typical_window")
        if tw:
            dist = min(days_from_window(d, tw) for d in dates)
            season = "in_window" if dist == 0 else "near" if dist <= margin else "out"
        else:
            dist, season = None, "no_window"
        row = {"site": e["id"], "name": e["name"], "season": season, "days_from_window": dist, "tags": e.get("tags"),
               "typical_window": {k: tw[k] for k in ("start", "end", "source_url") if k in tw} if tw else None,
               "official_status_url": e.get("official_status_url"),
               "sources": [{"id": sid, "kind": srcs[sid]["kind"], "approval": srcs[sid]["approval"]["status"],
                            "readable": srcs[sid]["readable"]["status"], "url": srcs[sid]["url"]}
                           for sid in e.get("status_sources") or [] if sid in srcs]}
        (out_of_season if season == "out" else sites).append(row)
    plan, human, refs = {}, {}, {}
    for row in sites:
        for s in row["sources"]:
            # 参考リンク(段階17 の見直し)は読む予定に入れず、現況の情報源に数えない。答えでは参考として URL だけ示す
            bucket = refs if s["kind"] == REFERENCE else plan if s["approval"] == APPROVED else human
            bucket.setdefault(s["id"], {"id": s["id"], "kind": s["kind"], "url": s["url"], "sites": []})["sites"].append(row["site"])
    if region is not None:
        # 地域を指定したときだけ: 例年の時期の外の名所も、承認済みの情報源を読む予定に入れる(段階16 の答え直しで見つけた穴。
        # 箱根は強羅だけが名所で、時期の外だと箱根のページを読まなかった)。答えでは out_of_season_sites の名所を「例年の時期の外」と明記する
        for row in out_of_season:
            for s in row["sources"]:
                if s["approval"] == APPROVED and s["kind"] != REFERENCE:
                    item = plan.setdefault(s["id"], {"id": s["id"], "kind": s["kind"], "url": s["url"], "sites": []})
                    item["sites"].append(row["site"])
                    item.setdefault("out_of_season_sites", []).append(row["site"])
    no_status =[r["site"] for r in sites if not any(s["approval"] == APPROVED and s["kind"] == "status_page" for s in r["sources"])]
    return {"dates": [d.isoformat() for d in dates], "window_margin_days": margin,
            "sites": sites,
            # 例年の時期から外れた名所。読む情報源(read_plan)がこの名所も伝えていれば、ついでに分かる公式の現況を示せる(現況が主。段階15)
            "out_of_season": [{"site": r["site"], "name": r["name"], "days_from_window": r["days_from_window"],
                               "covered_by_read_plan": [s["id"] for s in r["sources"] if s["id"] in plan]} for r in out_of_season],
            # 例年の時期がこれから来る名所(段階16 C: 季節の前でも「例年の始まりの時期」を答える)。next_start は対象の最初の日より後で最も近い始まり
            "upcoming_windows": [{"site": r["site"], "name": r["name"], "typical_window": r["typical_window"],
                                  "next_start": next_window_start(dates[0], r["typical_window"]).isoformat()}
                                 for r in out_of_season if r["typical_window"] and next_window_start(dates[0], r["typical_window"]) > dates[0]],
            "read_plan": sorted(plan.values(), key=lambda x: (x["kind"] != "status_page", x["id"])),
            "human_urls": sorted(human.values(), key=lambda x: x["id"]),
            "reference_links": sorted(refs.values(), key=lambda x: x["id"]),
            "no_status_source": no_status}


# ---- 一覧 → 今月の記事(段階17 修正⑥) ----

def era_year(year, policy):
    """西暦 → 和暦の年(方針の japanese_era。令和元年 = 2019)。"""
    return year - val(policy["japanese_era"]["first_year"]) + 1


def monthly_targets(src, on, policy):
    """follow: monthly_article の情報源で、一覧ページから探すリンクの文字列。→ [{year, month, link_text}](今月 → 先月の順)。
    今月の記事がまだなければ先月の記事(その日付で新しさが分かる)。どちらもなければ一覧の URL を人が開く URL として示す(手順)。"""
    fl = src.get("follow")
    if not fl:
        return []
    prev = (on.replace(day=1) - timedelta(days=1))
    return [{"year": d.year, "month": d.month, "link_text": fl["link_text"].format(era_year=era_year(d.year, policy), month=d.month)}
            for d in (on, prev)]


# ---- 記録(JSON Lines) ----

def log_path(subject, env=None):
    return data_path(load_config()["status_log"]["dir"], env) / f"{subject}.jsonl"


def make_record(*, registry, policy, source_id, read_at, state, updated=None, site=None, name=None, label=None, year_inferred=None,
                method=None, forecast=None, event_start=None, event_end=None, observed=None, observed_year_inferred=None, url=None,
                observed_md=None):
    """読んだ結果 1 件 → 記録(段階はコードが決める)。検査は validate_record。
    method は読み方(agent_summary / code / user_verified。既定は方針の default_method)、forecast は公式の見頃予測の原文、
    event_start・event_end はまつり・ライトアップの期間(YYYY-MM-DD)。
    observed は現地の状態の日付(「10/22現在」。段階17 修正⑤)、observed_year_inferred はその年を補ったとき。
    url は実際に読んだページ(一覧からたどった今月の記事など。情報源と同じホスト。省略すると情報源の url)。
    observed_md は年のない現地の状態の日付(「10/20現在」→ "10-20")。同じ地点の年つきの最終更新日(updated。年を補っていないもの)から年を補う
    (observed_year_from_update)。補えなければ読んだ日に近い過去の日付にして observed_year_inferred: true(新しさ不明)。
    freshness_basis(新しさの基準にした日付の種類)と read_by(読み方の区分)はコードが決める。"""
    src = sources_by_id(registry).get(source_id)
    stage = normalize_state(src, state)[0] if src else None
    method = method or policy["record"]["default_method"]
    if observed_md is not None and observed is None:
        m, d = (int(x) for x in observed_md.replace("/", "-").split("-"))
        got = observed_year_from_update(m, d, None if year_inferred else updated, policy)
        if got:
            observed, observed_year_inferred = got.isoformat(), policy["freshness"]["observed_year_from_update_mark"]
        else:
            observed, observed_year_inferred = past_date(m, d, parse_now(read_at).date()).isoformat(), True
    rec = {"schema": policy["record"]["schema"], "subject": registry["subject"], "source_id": source_id,
           "official_state": state, "stage": stage, "official_updated": updated, "read_at": read_at,
           "url": url or (src["url"] if src else None), "method": method, "read_by": policy["record"]["read_by"].get(method)}
    for k, v in (("site", site), ("name", name), ("label", label), ("updated_year_inferred", year_inferred),
                 ("official_forecast", forecast), ("event_start", event_start), ("event_end", event_end),
                 ("official_observed", observed), ("observed_year_inferred", observed_year_inferred)):
        if v is not None:
            rec[k] = v
    basis = freshness_basis(rec, src)
    if basis:
        rec["freshness_basis"] = basis
    return rec


def observed_year_from_update(month, day, updated, policy):
    """年のない「M/D現在」の年を、同じ地点の年つきの最終更新日(YYYY-MM-DD)から補う(段階17 の見直し、ユーザーの判断)。
    「現在」の日付が更新日以前で、方針の日数以内に収まる年を選ぶ(更新日の年か前の年)。収まらなければ None(推測しない)。"""
    if not updated:
        return None
    up = date.fromisoformat(updated)
    limit = val(policy["freshness"]["observed_year_from_update_max_days"])
    for y in (up.year, up.year - 1):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if d <= up and (up - d).days <= limit:
            return d
    return None


def past_date(month, day, on):
    """年のない M/D → on 以前で最も近い日付(前の年かもしれない。箱根の読み取りと同じ考え方)。"""
    d = _md_date(on.year, f"{month:02d}-{day:02d}")
    return d if d <= on else _md_date(on.year - 1, f"{month:02d}-{day:02d}")


def freshness_basis(rec, src):
    """新しさの基準にした日付の種類(段階17 修正⑤)。現地の状態の日付があれば observed_date、なければ最終更新日の updated_date。
    日付が 1 つだけの情報源は、台帳の notation.date_basis がその日付の種類(箱根の「M/D現在」は observed_date)。日付がなければ None。"""
    if rec.get("official_observed"):
        return "observed_date"
    if rec.get("official_updated"):
        return ((src or {}).get("notation") or {}).get("date_basis") or "updated_date"
    return None


def record_freshness(rec, src, on, policy):
    """記録の新しさ。→ (基準の日付の文字列 or None, 年が分からないか, freshness の辞書)。
    ①現地の状態の日付(年を補ったものは「新しさ不明」)、②なければ最終更新日(年のない情報源・年を補ったものは「新しさ不明」)。"""
    if rec.get("official_observed"):
        # 同じ地点の年つきの更新日から年を補ったもの(from_same_item_update_date)は年が分かるものとして扱う。true は年が分からない
        d, no_year = rec["official_observed"], rec.get("observed_year_inferred") is True
    else:
        d, no_year = rec.get("official_updated"), year_unknown(src, rec)
    return d, no_year, freshness(date.fromisoformat(d) if d else None, on, policy, no_year)


def validate_record(rec, *, registry, policy):
    """→ エラーのリスト(空 = 合格)。事実の項目だけ・承認済みの情報源だけ・段階はコードの対応と一致。"""
    errs = []
    rp = policy["record"]
    extra = sorted(set(rec) - set(rp["fields"]))
    if extra:
        errs.append(f"記録に入れられない項目: {extra}")
    for k in ("schema", "subject", "source_id", "read_at", "url"):
        if not rec.get(k):
            errs.append(f"{k} がない")
    if errs:
        return errs
    if rec["schema"] != rp["schema"] or rec["subject"] != registry["subject"]:
        errs.append(f"schema・subject が違う({rec['schema']}, {rec['subject']})")
    src = sources_by_id(registry).get(rec["source_id"])
    if src is None:
        return errs + [f"情報源 {rec['source_id']} が台帳にない"]
    if not is_approved(src):
        errs.append(f"情報源 {rec['source_id']} は承認されていない({src['approval']['status']})")
    if ("site" in rec) == ("name" in rec):
        errs.append("site と name のどちらか一方が要る")
    elif not any(c.get("site") == rec.get("site") if "site" in rec else c.get("name") == rec.get("name") for c in src["covers"]):
        errs.append(f"{rec.get('site') or rec.get('name')} は情報源 {src['id']} の covers にない")
    if urlsplit(rec["url"]).netloc != urlsplit(src["url"]).netloc:
        errs.append(f"url のホストが情報源と違う({rec['url']})")
    st = rec.get("official_state")
    if st is not None and (not isinstance(st, str) or len(st) > val(rp["max_state_chars"])):
        errs.append(f"official_state は {val(rp['max_state_chars'])} 文字以内の記号・語(本文を写さない)")
    if rec.get("label") is not None and len(rec["label"]) > val(rp["max_label_chars"]):
        errs.append(f"label は {val(rp['max_label_chars'])} 文字以内")
    if rec.get("stage") != normalize_state(src, st)[0]:
        errs.append(f"stage={rec.get('stage')} が台帳の対応({normalize_state(src, st)[0]})と違う")
    if rec.get("method", rp["default_method"]) not in rp["methods"]:
        errs.append(f"method={rec.get('method')} は {rp['methods']} のどれでもない")
    fc = rec.get("official_forecast")
    if fc is not None and (not isinstance(fc, str) or len(fc) > val(rp["max_forecast_chars"])):
        errs.append(f"official_forecast は {val(rp['max_forecast_chars'])} 文字以内の見頃予測の原文(本文を写さない)")
    ev = [rec.get(k) for k in ("event_start", "event_end")]
    if any(v is not None for v in ev):
        if not all(v is not None and catalog_mod.valid_date(v) for v in ev):
            errs.append(f"event_start・event_end は両方とも日付(YYYY-MM-DD)が要る({ev})")
        elif ev[0] > ev[1]:
            errs.append(f"event_start {ev[0]} が event_end {ev[1]} より後")
    if ("unmarked_on" in rec) != ("unmarked_reason" in rec) or ("unmarked_on" in rec and not catalog_mod.valid_date(rec["unmarked_on"] or "")):
        errs.append("印を外した記録は unmarked_on(YYYY-MM-DD)と unmarked_reason をそろえる")
    if "user_checked_on" in rec and not catalog_mod.valid_date(rec["user_checked_on"] or ""):
        errs.append("user_checked_on は YYYY-MM-DD")
    if any(k in rec for k in rp["erroneous_fields"]):
        if rec.get("erroneous") is not True or not rec.get("erroneous_reason") or not catalog_mod.valid_date(rec.get("corrected_on") or ""):
            errs.append("誤りの印は erroneous: true・erroneous_reason・corrected_on(YYYY-MM-DD)をそろえて付ける")
    if any(k in rec for k in rp["superseded_fields"]):
        if rec.get("superseded") is not True or not rec.get("superseded_reason") or not catalog_mod.valid_date(rec.get("superseded_on") or ""):
            errs.append("置き換えの印は superseded: true・superseded_reason・superseded_on(YYYY-MM-DD)をそろえて付ける")
        elif rec.get("erroneous") is True:
            errs.append("置き換えの印と誤りの印は同時に付けない(読み違いなら誤りの印だけ)")
    if "updated_year_inferred" in rec and not isinstance(rec["updated_year_inferred"], bool):
        errs.append("updated_year_inferred は真偽値")
    elif rec.get("official_updated") is not None and (src.get("notation") or {}).get("year_shown") is False and rec.get("updated_year_inferred") is not True:
        errs.append(f"情報源 {src['id']} の日付には年がない(notation.year_shown: false)。年を補った更新日には updated_year_inferred: true が要る")
    oyi, mark = rec.get("observed_year_inferred"), policy["freshness"]["observed_year_from_update_mark"]
    if "observed_year_inferred" in rec and not (isinstance(oyi, bool) or oyi == mark):
        errs.append(f"observed_year_inferred は真偽値か {mark}")
    elif oyi == mark:
        ob, up = rec.get("official_observed"), rec.get("official_updated")
        ok = bool(ob and up and catalog_mod.valid_date(ob) and catalog_mod.valid_date(up)) and rec.get("updated_year_inferred") is not True
        if ok:
            o, u = date.fromisoformat(ob), date.fromisoformat(up)
            ok = o <= u and (u - o).days <= val(policy["freshness"]["observed_year_from_update_max_days"])
        if not ok:
            errs.append(f"{mark} は、年つきの最終更新日があり、現地の日付がその日以前で方針の日数以内のときだけ")
    if "freshness_basis" in rec and rec["freshness_basis"] != freshness_basis(rec, src):
        errs.append(f"freshness_basis={rec['freshness_basis']} が日付の種類({freshness_basis(rec, src)})と違う")
    if "read_by" in rec and rec["read_by"] != rp["read_by"].get(rec.get("method", rp["default_method"])):
        errs.append(f"read_by={rec['read_by']} が読み方 method={rec.get('method')} と合わない")
    try:
        ra = parse_now(rec["read_at"])
    except (TypeError, ValueError) as ex:
        return errs + [f"read_at: {ex}"]
    for k in ("official_updated", "official_observed"):
        v = rec.get(k)
        if v is None:
            continue
        if not catalog_mod.valid_date(v):
            errs.append(f"{k}={v} は日付でない")
        elif date.fromisoformat(v) > ra.date():
            errs.append(f"{k}={v} が読んだ日 {ra.date()} より後")
    return errs


def _read_all(subject, env=None):
    p = log_path(subject, env)
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def read_records(subject, env=None, include_erroneous=False, include_superseded=False):
    """記録を読む。誤りの印(erroneous: true。段階16 A-1)・置き換えの印(superseded: true。段階17b)の付いた記録は、
    それぞれ include_erroneous・include_superseded を明示しない限り使わない。"""
    return [r for r in _read_all(subject, env)
            if (include_erroneous or r.get("erroneous") is not True) and (include_superseded or r.get("superseded") is not True)]


def records_on(subject, day, env=None):
    """day(date)に読んだ記録だけ(読んだ時刻のオフセットでの暦日)。誤りの印・置き換えの印の付いたものは除く。記録の再利用は同じ日のうちだけ(段階16 A-2)。"""
    return [r for r in read_records(subject, env) if parse_now(r["read_at"]).date() == day]


def latest_by_place(records):
    """同じ情報源・地点(site か name)・地点の書き方(label)ごとに、いちばん後に読んだ記録だけ。"""
    best = {}
    for r in records:
        k = _place(r)
        if k not in best or parse_now(r["read_at"]) >= parse_now(best[k]["read_at"]):
            best[k] = r
    return list(best.values())


def _place(r):
    return (r["source_id"], r.get("site"), r.get("name"), r.get("label"))


def conflicts(records):
    """同じ地点で、ユーザーが原文を確かめた記録(method: user_verified)と、ほかの読み方の記録の事実(状態・更新日)が食い違うもの。
    → {地点のキー: [{method, official_state, official_updated, read_at}]}。どちらが正しいかは推測で決めない(段階16 A-4 の実通信で見つかった)。"""
    by = {}
    for r in records:
        by.setdefault(_place(r), []).append(r)
    out = {}
    for k, rs in by.items():
        facts = {(r.get("official_state"), r.get("official_updated")) for r in rs}
        if len(facts) > 1 and any(r.get("method") == "user_verified" for r in rs):
            out[k] = [{"method": r.get("method"), "official_state": r.get("official_state"), "official_updated": r.get("official_updated"),
                       "read_at": r["read_at"]} for r in sorted(rs, key=lambda r: parse_now(r["read_at"]))]
    return out


def _rewrite(subject, rows, env=None):
    p = log_path(subject, env)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, p)


def _matching(subject, match, env=None):
    if not match:
        raise ValueError("どの記録かを match で指定する")
    rows = _read_all(subject, env)
    hit = [r for r in rows if all(r.get(k) == v for k, v in match.items())]
    if not hit:
        raise ValueError(f"一致する記録がない: {match}")
    return rows, hit


def unmark_erroneous(subject, match, *, reason, on, env=None):
    """誤りの印を外す(段階16 の見直し: 湖尻の「色づきはじめ、10/22現在」は正しかった)。印の項目は消し、外した日と理由を残す。→ 外した件数。"""
    if not reason or not catalog_mod.valid_date(on or ""):
        raise ValueError("reason と on(YYYY-MM-DD)が要る")
    rows, hit = _matching(subject, match, env)
    n = 0
    for r in hit:
        if r.get("erroneous") is True:
            for k in ("erroneous", "erroneous_reason", "corrected_on"):
                r.pop(k, None)
            r.update({"unmarked_on": on, "unmarked_reason": reason})
            n += 1
    _rewrite(subject, rows, env)
    return n


def amend_records(subject, match, updates, *, env=None, policy=None):
    """記録の読み方の項目だけを直す(方針の record.amendable_fields。method・method_note・user_checked_on)。事実の項目は直さない。→ 直した件数。"""
    policy = policy or load_policy()
    allowed = set(policy["record"]["amendable_fields"])
    bad = sorted(set(updates) - allowed)
    if bad:
        raise ValueError(f"直せない項目: {bad}(直せるのは {sorted(allowed)}。事実は誤りの印と新しい記録で直す)")
    if "method" in updates and updates["method"] not in policy["record"]["methods"]:
        raise ValueError(f"method={updates['method']} は {policy['record']['methods']} のどれでもない")
    if "user_checked_on" in updates and not catalog_mod.valid_date(updates["user_checked_on"] or ""):
        raise ValueError("user_checked_on は YYYY-MM-DD")
    rows, hit = _matching(subject, match, env)
    for r in hit:
        r.update(updates)
    _rewrite(subject, rows, env)
    return len(hit)


def supersede_records(subject, match, *, reason, on, env=None):
    """読み直して置き換えた記録に置き換えの印(superseded: true・superseded_on・superseded_reason)を付ける(消さない。段階17b)。
    読み違いではない置き換え(名所カタログに入ったので site で記録し直した、など)に使う。読み違いは mark_erroneous。
    誤りの印の付いた記録には付けない。1 件も一致しなければ ValueError。→ 印を付けた件数。"""
    if not reason or not catalog_mod.valid_date(on or ""):
        raise ValueError("reason と on(YYYY-MM-DD)が要る")
    rows, hit = _matching(subject, match, env)
    n = 0
    for r in hit:
        if r.get("superseded") is not True and r.get("erroneous") is not True:
            r.update({"superseded": True, "superseded_on": on, "superseded_reason": reason})
            n += 1
    _rewrite(subject, rows, env)
    return n


def erroneous_to_superseded(subject, match, *, reason, on, env=None):
    """読み違いではないのに誤りの印で置き換えた記録を、置き換えの印に付け替える(段階17b。湖尻の 10/24 の 1 件)。
    誤りの印の項目は消し、置き換えの印を付ける。match は誤りの印の付いた記録だけに当たること(当たらなければ ValueError)。→ 付け替えた件数。"""
    if not reason or not catalog_mod.valid_date(on or ""):
        raise ValueError("reason と on(YYYY-MM-DD)が要る")
    rows, hit = _matching(subject, {**match, "erroneous": True}, env)
    for r in hit:
        for k in ("erroneous", "erroneous_reason", "corrected_on"):
            r.pop(k, None)
        r.update({"superseded": True, "superseded_on": on, "superseded_reason": reason})
    _rewrite(subject, rows, env)
    return len(hit)


def mark_erroneous(subject, match, *, reason, corrected_on, env=None, policy=None):
    """match(項目 → 値)にすべて一致する記録に誤りの印を付ける(消さない。段階16 A-1)。→ 印を付けた件数。
    1 件も一致しなければ ValueError(取り違えを防ぐ)。すでに印のある記録はそのまま。ファイルは書き直す(一時ファイル → 置き換え)。"""
    if not reason or not catalog_mod.valid_date(corrected_on or ""):
        raise ValueError("reason と corrected_on(YYYY-MM-DD)が要る")
    if not match:
        raise ValueError("どの記録かを match で指定する")
    rows = _read_all(subject, env)
    hit = [r for r in rows if all(r.get(k) == v for k, v in match.items())]
    if not hit:
        raise ValueError(f"一致する記録がない: {match}")
    n = 0
    for r in hit:
        if r.get("erroneous") is not True:
            r.update({"erroneous": True, "erroneous_reason": reason, "corrected_on": corrected_on})
            n += 1
    _rewrite(subject, rows, env)
    return n


def _key(rec):
    # 年の補い方(updated_year_inferred・observed_year_inferred)が違えば別の事実として扱う(段階17 の見直し: 年を補い直した記録が重複扱いで落ちた)
    return tuple(rec.get(k) for k in ("source_id", "site", "name", "label", "official_state", "official_updated", "official_observed",
                                      "official_forecast", "event_start", "event_end", "method",
                                      "updated_year_inferred", "observed_year_inferred"))


def append_records(records, *, registry, policy, env=None):
    """検査に通った記録を追記する。同じ事実(情報源・名所・状態・公式の更新日)がもうあれば足さない。
    1 件でも検査に落ちたら何も書かない。→ (書いた件数, 重複で足さなかった件数)。"""
    bad = [(i, e) for i, r in enumerate(records) for e in validate_record(r, registry=registry, policy=policy)]
    if bad:
        raise ValueError("; ".join(f"[{i}] {e}" for i, e in bad))
    if any(r.get("erroneous") is True for r in records):
        raise ValueError("誤りの印の付いた記録は足さない(印は mark_erroneous で付ける)")
    if any(r.get("superseded") is True for r in records):
        raise ValueError("置き換えの印の付いた記録は足さない(印は supersede で付ける)")
    seen = {_key(r) for r in _read_all(registry["subject"], env)}
    new = []
    for r in records:
        if _key(r) not in seen:
            seen.add(_key(r))
            new.append(r)
    if new:
        p = log_path(registry["subject"], env)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return len(new), len(records) - len(new)


# ---- 答えの材料(同じ日に読んだ記録から) ----

def summarize(records, *, registry, catalog_doc, policy, on, dates, early=False, late=False):
    """on(date)に読んだ記録(呼び出し側が records_on で絞る)→ 地点ごとの答えの材料。通信しない。
    - 段階の共通の順番(order)と、質問の型③の範囲に入るか(in_scope。既定は見ごろ・最盛、early で始まり、late で終わりも)
    - 段階・新しさ(年を補った更新日は「新しさ不明」)・表示が古い可能性(段階16 A-3)
    - 公式の見頃予測の日の範囲と、対象の日にかかるか(段階16 A-8)
    - まつり・ライトアップの期間が対象の日にかかるか"""
    srcs = sources_by_id(registry)
    entries = {e["id"]: e for e in catalog_mod.approved_entries(catalog_doc or {})}
    rows, clash, scope = [], conflicts(records), scope_orders(policy, early=early, late=late)
    for r in sorted(latest_by_place(records), key=lambda r: (r["source_id"], r.get("site") or "", r.get("name") or "", r.get("label") or "")):
        src = srcs.get(r["source_id"]) or {}
        basis_d, basis_no_year, fresh = record_freshness(r, src, on, policy)
        fw = forecast_window(r.get("official_forecast"), parse_now(r["read_at"]).year, policy)
        ev = (date.fromisoformat(r["event_start"]), date.fromisoformat(r["event_end"])) if r.get("event_start") else None
        rows.append({"source": r["source_id"], "kind": src.get("kind"), "site": r.get("site"), "name": r.get("name"), "label": r.get("label"),
                     "official_state": r.get("official_state"), "state_kind": normalize_state(src, r.get("official_state"))[1],
                     "stage": r.get("stage"), "stage_label": stage_label(policy, r["subject"], r.get("stage")),
                     "order": stage_order(policy, r["subject"], r.get("stage")),
                     "in_scope": stage_order(policy, r["subject"], r.get("stage")) in scope,
                     "official_updated": r.get("official_updated"), "year_inferred": year_unknown(src, r),
                     "official_observed": r.get("official_observed"), "basis_date": basis_d, "basis_year_unknown": basis_no_year,
                     "freshness_basis": r.get("freshness_basis") or freshness_basis(r, src), "freshness": fresh,
                     "stale_display_suspect": stale_display_suspect(r, entries.get(r.get("site")), policy, src),
                     "official_forecast": r.get("official_forecast"),
                     "forecast_window": [d.isoformat() for d in fw] if fw else None, "forecast_hits_dates": overlaps(fw, dates),
                     "event": [d.isoformat() for d in ev] if ev else None, "event_hits_dates": overlaps(ev, dates),
                     "method": r.get("method", policy["record"]["default_method"]),
                     "read_by": r.get("read_by") or policy["record"]["read_by"].get(r.get("method", policy["record"]["default_method"])),
                     "read_at": r["read_at"], "url": r.get("url"),
                     "conflict": clash.get(_place(r))})
    common = {s["order"]: s["label"] for s in policy["common_stages"]["items"]}
    return {"on": on.isoformat(), "dates": [d.isoformat() for d in dates], "horizon": horizon(datetime.combine(on, datetime.min.time()), dates, policy),
            "scope": [{"order": o, "label": common[o]} for o in scope], "rows": rows,
            "forecast_hits": [x for x in rows if x["forecast_hits_dates"]],
            "events": [x for x in rows if x["event_hits_dates"]],
            "unparsed_forecasts": [x for x in rows if x["official_forecast"] and x["forecast_window"] is None],
            "conflicts": [x for x in rows if x["conflict"]]}


# ---- 補助の推定(v0 の出力を読むだけ。計算も通信もしない) ----

def v0_estimates(proposal_doc, *, subject, labels, policy, dates=None):
    """v0 の出力(biyori-proposal/1)から、名所ごと・日ごとの段階と band を取り出す。→ [{site, date, stage, stage_label, band, generated_at, label}]。
    名所カタログの件(id が ikimonobiyori:<subject>:<日付>:<名所>)だけ。補助の推定として、方針の書き方(aux_estimate.label)を必ず付ける。"""
    if proposal_doc.get("schema") != "biyori-proposal/1":
        raise ValueError(f"biyori-proposal/1 ではない: {proposal_doc.get('schema')!r}")
    want = {d.isoformat() for d in dates} if dates else None
    out = []
    for p in proposal_doc.get("proposals") or []:
        parts = p.get("id", "").split(":")
        if len(parts) != len(V0_ID_PARTS) or parts[:2] != ["ikimonobiyori", subject]:
            continue
        _, _, day, sid = parts
        if want is not None and day not in want:
            continue
        st = p.get("phenology_stage")
        out.append({"site": sid, "date": day, "stage": st, "stage_label": labels.get(st), "band": (p.get("suitability") or {}).get("band"),
                    "generated_at": proposal_doc.get("generated_at"), "label": policy["aux_estimate"]["label"]})
    return sorted(out, key=lambda r: (r["site"], r["date"]))


# ---- CLI ----

def _dump(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def read_live(source_ids, *, registry, policy, cfg, now, http_get, max_requests, record=False, env=None):
    """reader: code の承認済みの情報源を、robots.txt → ページの順に 1 回ずつ読む(段階16 A-4)。→ 結果の辞書。
    http_get は呼び出し側が渡す(本物の通信は main が計測フックとゲートを確かめてから)。record なら読めた事実を記録に足す(method: code)。"""
    from .fetch import status_pages
    srcs = sources_by_id(registry)
    out, left, reads_all = [], max_requests, []
    for sid in source_ids:
        src = srcs.get(sid)
        if src is None or src.get("reader") != "code" or not is_approved(src):
            out.append({"source": sid, "status": "コードで読む承認済みの情報源ではない。読まない", "requests": 0, "reads": []})
            continue
        if left < 1:
            out.append({"source": sid, "status": f"--max-requests {max_requests} に達したため読まない", "requests": 0, "reads": []})
            continue
        reads, rep = status_pages.read_source(src, http_get=http_get, cfg=cfg, on=now.date(), max_requests=left)
        left -= rep["requests"]
        out.append({**rep, "reads": reads})
        reads_all += reads
    res = {"read_at": now.isoformat(), "results": out}
    if record and reads_all:
        recs = [make_record(registry=registry, policy=policy, source_id=it["source"], read_at=now.isoformat(), state=it["state"], updated=it["updated"],
                            site=it.get("site"), name=it.get("name"), label=it["label"], year_inferred=it.get("year_inferred"),
                            method=it["method"], forecast=it.get("forecast")) for it in reads_all]
        written, dup = append_records(recs, registry=registry, policy=policy, env=env)
        res["recorded"] = {"written": written, "duplicates": dup, "path": str(log_path(registry["subject"], env))}
    return res


def cover_kind(registry, rec):
    """記録の地点(情報源の covers の同じ地点・書き方)の花の種類(段階17)。なければ None。"""
    src = sources_by_id(registry).get(rec["source_id"]) or {}
    for c in src.get("covers") or []:
        if c.get("site", c.get("name")) == rec.get("site", rec.get("name")) and c.get("label") == rec.get("label"):
            return c.get("flower_kind")
    return None


def answer_parts(subjects, *, policy, now, dates, early=False, late=False, region=None, terrain=None, access=None, flower_kind=None, env=None):
    """答えの下書き(answer.compose)に渡す、対象ごとの部品。同じ日に読んだ記録と、候補の絞り込み。
    flower_kind を渡すと、記録も候補もその花の種類だけにする(台帳の covers の flower_kind・名所の tags.flower_kinds)。"""
    from .profiles import load_profiles
    profs = load_profiles()
    parts = []
    for subj in subjects:
        registry, cat = load_registry(subj), catalog_mod.load_catalog(subj)
        care = profs[subj].get("care") or {}
        recs = records_on(subj, now.date(), env)
        if flower_kind:
            recs = [r for r in recs if cover_kind(registry, r) in flower_kind]
        if region is not None or terrain or access or flower_kind:
            # 地域・条件で絞ったときは、絞った名所の記録だけ。カタログ外の地点(tags がない)は、地域だけで絞ったときに限り、
            # その地点を伝えるページが絞った名所も伝えるなら残す(地形・行き方は分からないので外す)
            keep = {e["id"] for e in catalog_mod.approved_entries(cat or {})
                    if site_filter(e, region=region, terrain=terrain, access=access, flower_kind=flower_kind)}
            srcs = sources_by_id(registry)
            region_only = region is not None and not (terrain or access or flower_kind)
            recs = [r for r in recs if r.get("site") in keep] +                    [r for r in recs if "site" not in r and region_only
                    and any(c.get("site") in keep for c in (srcs.get(r["source_id"]) or {}).get("covers") or [])]
        parts.append({"subject": subj, "name": profs[subj]["name"], "catalog": cat,
                      "summary": summarize(recs, registry=registry, catalog_doc=cat, policy=policy,
                                           on=now.date(), dates=dates, early=early, late=late),
                      "candidates": candidates(cat, registry, dates, policy, region=region, terrain=terrain, access=access, flower_kind=flower_kind),
                      # 生き物に配慮が要る対象(位置を明かさない対象)だけ、マナーを添える
                      "care": care.get("manners") if care.get("do_not_disclose_exact_location") else None})
    return parts


def _answer_cli(a):
    from . import answer
    policy, now = load_policy(), parse_now(a.now)
    dates = [date.fromisoformat(x) for x in a.date] if a.date else next_weekend(now)
    ready = [s["subject"] for s in subjects_status() if s["implemented"]]
    subjects = ready if a.subjects == ["all"] else (a.subjects or [a.subject])
    bad = [s for s in subjects if s not in ready]
    if bad:
        print(f"この手順で答えられない対象: {bad}(subjects コマンドで確かめる)", file=sys.stderr)
        return 2
    region = None
    if a.region:
        region = resolve_region(a.region, load_regions())
        if region is None:
            print(f"地域の呼び名が data/regions.yaml にない: {a.region}", file=sys.stderr)
            return 2
    parts = answer_parts(subjects, policy=policy, now=now, dates=dates, early=a.early, late=a.late, region=region,
                         terrain=a.terrain, access=a.access, flower_kind=a.flower_kind)
    print(answer.compose(parts, now=now, dates=dates, policy=policy, scope_note=a.scope_note, record_failed=a.record_failed,
                         early=a.early, late=a.late), end="")
    return 0


def main(argv=None, http_get=None):
    ap = argparse.ArgumentParser(prog="python -m ikimonobiyori.sources")
    ap.add_argument("--subject", default="autumn_leaves")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="台帳を検査する(通信しない・書き込まない)")
    c.add_argument("--sources-dir")
    c.add_argument("--catalog-dir")
    w = sub.add_parser("weekend", help="対象の日の候補と、読む情報源の一覧(通信しない・書き込まない)")
    w.add_argument("--now", required=True, help="ISO 8601(オフセット必須)")
    w.add_argument("--date", action="append", help="対象の日(YYYY-MM-DD。省略すると次の土日)")
    w.add_argument("--region", help="地域の呼び名(data/regions.yaml の名前・別名)")
    w.add_argument("--terrain", action="append", help="地形(tags.terrain: mountain / highland / lake / urban / valley など。複数はどれか)")
    w.add_argument("--access", action="append", help="行き方(tags.access: ropeway / cable_car / walk_from_station / bus / car_only)")
    w.add_argument("--flower-kind", action="append", help="花の種類(名所の tags.flower_kinds。flowers。段階17)")
    rg = sub.add_parser("region", help="地域の呼び名 → 名所カタログの件と、範囲(250 km)の内外(通信しない)")
    rg.add_argument("name")
    sub.add_parser("subjects", help="この手順で答えられる対象(台帳・名所カタログ・段階がそろったもの)と、まだの対象")
    tp = sub.add_parser("topic", help="質問の話題(野鳥など)→ 答える対象(方針の topics。段階17)")
    tp.add_argument("word")
    n = sub.add_parser("normalize", help="公式の状態 → 共通の段階")
    n.add_argument("--source", required=True)
    n.add_argument("--state", required=True)
    r = sub.add_parser("record", help="読んだ結果(事実だけ)を記録に追記する(IKIMONOBIYORI_DATA_DIR の下)")
    r.add_argument("--read-at", required=True, help="読んだ時刻。ISO 8601(オフセット必須)")
    r.add_argument("--batch", required=True,
                   help="JSON の配列: [{source, site|name, label?, state, observed?, observed_md?(年のない M-D), observed_year_inferred?, updated?, year_inferred?, method?, "
                        "forecast?, event_start?, event_end?, url?}]")
    lg = sub.add_parser("log", help="記録を表示する(誤りの印・置き換えの印の付いた記録は --include-erroneous・--include-superseded のときだけ)")
    lg.add_argument("--source")
    lg.add_argument("--include-erroneous", action="store_true")
    lg.add_argument("--include-superseded", action="store_true")
    ss = sub.add_parser("supersede", help="読み直して置き換えた記録に置き換えの印を付ける(読み違いではないとき。消さない。段階17b)")
    ss.add_argument("--match", required=True)
    ss.add_argument("--reason", required=True)
    ss.add_argument("--on", required=True, help="置き換えた日 YYYY-MM-DD")
    ss.add_argument("--from-erroneous", action="store_true", help="読み違いではないのに誤りの印で置き換えた記録を、置き換えの印に付け替える")
    me = sub.add_parser("mark-erroneous", help="記録に誤りの印を付ける(消さない。IKIMONOBIYORI_DATA_DIR の下)")
    me.add_argument("--match", required=True, help='JSON の辞書(例: {"source_id": "...", "name": "湖尻", "official_state": "色づきはじめ"})')
    me.add_argument("--reason", required=True)
    me.add_argument("--corrected-on", required=True, help="YYYY-MM-DD")
    um = sub.add_parser("unmark-erroneous", help="誤りの印を外す(外した日と理由を残す)")
    um.add_argument("--match", required=True)
    um.add_argument("--reason", required=True)
    um.add_argument("--on", required=True, help="YYYY-MM-DD")
    am = sub.add_parser("amend", help="記録の読み方の項目(method・method_note・user_checked_on)だけを直す")
    am.add_argument("--match", required=True)
    am.add_argument("--set", required=True, help='JSON の辞書(例: {"method": "assistant_webfetch"})')
    sm = sub.add_parser("summary", help="同じ日に読んだ記録から、答えの材料(段階・新しさ・見頃予測・期間)を出す(通信しない・書き込まない)")
    sm.add_argument("--now", required=True, help="ISO 8601(オフセット必須)。この暦日に読んだ記録だけを使う")
    sm.add_argument("--date", action="append", help="対象の日(省略すると次の土日)")
    sm.add_argument("--early", action="store_true", help="質問の型③: 始まり(色づき始めなど)も含める")
    sm.add_argument("--late", action="store_true", help="質問の型③: 終わり(色褪せ・落葉など)も含める")
    rd = sub.add_parser("read", help="reader: code の情報源をコードで 1 回読む(段階16 A-4。--live・--max-requests・計測フックが要る)")
    rd.add_argument("--source", action="append", required=True)
    rd.add_argument("--now", required=True, help="読んだ時刻として記録する時刻。ISO 8601(オフセット必須)")
    rd.add_argument("--live", action="store_true")
    rd.add_argument("--max-requests", type=int)
    rd.add_argument("--record", action="store_true", help="読めた事実を記録に足す(IKIMONOBIYORI_DATA_DIR の下)")
    v = sub.add_parser("v0", help="v0 の出力(biyori-proposal/1)から名所ごとの補助の推定を取り出す(通信しない)")
    v.add_argument("--proposal", required=True)
    v.add_argument("--date", action="append")
    fo = sub.add_parser("follow", help="一覧ページから今月の記事をたどる情報源(瓢湖など)で、探すリンクの文字列を出す(段階17。通信しない)")
    fo.add_argument("--source", required=True)
    fo.add_argument("--now", required=True)
    an = sub.add_parser("answer", help="同じ日に読んだ記録から、答えの下書き(結論が先・内部用語なし)を出す(段階17。通信しない・書き込まない)")
    an.add_argument("--now", required=True, help="ISO 8601(オフセット必須)。この暦日に読んだ記録だけを使う")
    an.add_argument("--date", action="append", help="対象の日(省略すると次の土日)")
    an.add_argument("--subjects", action="append", help="対象(複数可。省略すると --subject の 1 つ。all で答えられる対象すべて)")
    an.add_argument("--scope-note", help="扱える範囲が質問の一部だけのときに冒頭に出す 1 行")
    an.add_argument("--early", action="store_true")
    an.add_argument("--late", action="store_true")
    an.add_argument("--region")
    an.add_argument("--terrain", action="append")
    an.add_argument("--access", action="append")
    an.add_argument("--flower-kind", action="append", help="花の種類(tags.flower_kinds。段階17)")
    an.add_argument("--record-failed", action="store_true", help="読んだ事実を記録できなかった(答えの最後に 1 行)")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        serr = stage_errors(load_policy())
        for e in serr:
            print(f"NG  段階の並び(profiles/*.yaml の stages): {e}")
        bad = int(bool(serr))
        for p, errs in check_all(a.sources_dir, a.catalog_dir):
            for e in errs:
                print(f"NG  {p.parent.name}/{p.name}: {e}")
            if not errs:
                print(f"OK  {p.parent.name}/{p.name}")
            bad += bool(errs)
        return 1 if bad else 0
    if a.cmd == "subjects":
        _dump(subjects_status())
        return 0
    if a.cmd == "topic":
        got = topic_subjects(a.word, load_policy())
        _dump({"topic": a.word, "subjects": got})
        return 0 if got else 1
    if a.cmd == "region":
        region = resolve_region(a.name, load_regions())
        if region is None:
            _dump({"region": a.name, "status": "unknown", "known": [r["name"] for r in load_regions()["regions"]]})
            return 1
        cats = {s["subject"]: catalog_mod.load_catalog(s["subject"]) for s in subjects_status() if s["implemented"]}
        _dump(region_report(region, catalogs=cats, catalog_policy=catalog_mod.load_policy()))
        return 0
    if a.cmd == "answer":
        return _answer_cli(a)
    policy, registry = load_policy(), load_registry(a.subject)
    if registry is None:
        print(f"台帳がない: {a.subject}", file=sys.stderr)
        return 2
    if a.cmd == "weekend":
        now = parse_now(a.now)
        dates = [date.fromisoformat(x) for x in a.date] if a.date else next_weekend(now)
        region = None
        if a.region:
            region = resolve_region(a.region, load_regions())
            if region is None:
                print(f"地域の呼び名が data/regions.yaml にない: {a.region}(region コマンドで確かめる)", file=sys.stderr)
                return 2
        _dump({"now": now.isoformat(), "subject": a.subject, "horizon": horizon(now, dates, policy),
               "filters": {"region": region and region["name"], "terrain": a.terrain, "access": a.access},
               **candidates(catalog_mod.load_catalog(a.subject), registry, dates, policy, region=region, terrain=a.terrain, access=a.access,
                            flower_kind=a.flower_kind)})
        return 0
    if a.cmd == "follow":
        src = sources_by_id(registry).get(a.source)
        if src is None or not src.get("follow"):
            print(f"一覧から記事をたどる情報源ではない: {a.source}", file=sys.stderr)
            return 2
        _dump({"source": a.source, "list_url": src["url"], "look_for": monthly_targets(src, parse_now(a.now).date(), policy),
               "if_missing": {"human_url": src["url"]}})
        return 0
    if a.cmd == "normalize":
        src = sources_by_id(registry).get(a.source)
        if src is None:
            print(f"情報源がない: {a.source}", file=sys.stderr)
            return 2
        stage, how = normalize_state(src, a.state)
        _dump({"source": a.source, "official_state": a.state, "stage": stage, "label": stage_label(policy, a.subject, stage), "how": how})
        return 0
    if a.cmd == "record":
        read_at = parse_now(a.read_at)
        items = json.loads(Path(a.batch).read_text(encoding="utf-8"))
        recs = [make_record(registry=registry, policy=policy, source_id=it.get("source"), read_at=read_at.isoformat(), state=it.get("state"),
                            updated=it.get("updated"), site=it.get("site"), name=it.get("name"), label=it.get("label"),
                            year_inferred=it.get("year_inferred"), method=it.get("method"), forecast=it.get("forecast"),
                            event_start=it.get("event_start"), event_end=it.get("event_end"), observed=it.get("observed"),
                            observed_year_inferred=it.get("observed_year_inferred"), url=it.get("url"),
                            observed_md=it.get("observed_md")) for it in items]
        try:
            written, dup = append_records(recs, registry=registry, policy=policy)
        except ValueError as ex:
            print(f"記録しなかった: {ex}", file=sys.stderr)
            return 1
        rows, by_id = [], sources_by_id(registry)
        for rc in recs:
            basis_d, _, fresh = record_freshness(rc, by_id.get(rc["source_id"]), read_at.date(), policy)
            rows.append({"source": rc["source_id"], "where": rc.get("site") or rc.get("name"), "state": rc["official_state"],
                         "stage": rc["stage"], "stage_label": stage_label(policy, a.subject, rc["stage"]), "updated": rc.get("official_updated"),
                         "observed": rc.get("official_observed"), "freshness_basis": rc.get("freshness_basis"), "basis_date": basis_d,
                         "freshness": fresh})
        _dump({"written": written, "duplicates": dup, "path": str(log_path(a.subject)), "rows": rows})
        return 0
    if a.cmd == "v0":
        from .profiles import load_profiles
        labels = load_profiles().get(a.subject, {}).get("phenology_labels") or {}
        doc = json.loads(Path(a.proposal).read_text(encoding="utf-8"))
        dates = [date.fromisoformat(x) for x in a.date] if a.date else None
        _dump(v0_estimates(doc, subject=a.subject, labels=labels, policy=policy, dates=dates))
        return 0
    if a.cmd == "log":
        _dump([r for r in read_records(a.subject, include_erroneous=a.include_erroneous, include_superseded=a.include_superseded)
               if not a.source or r["source_id"] == a.source])
        return 0
    if a.cmd in ("unmark-erroneous", "amend"):
        try:
            n = (unmark_erroneous(a.subject, json.loads(a.match), reason=a.reason, on=a.on) if a.cmd == "unmark-erroneous"
                 else amend_records(a.subject, json.loads(a.match), json.loads(a.set)))
        except ValueError as ex:
            print(f"直さなかった: {ex}", file=sys.stderr)
            return 1
        _dump({"changed": n, "path": str(log_path(a.subject))})
        return 0
    if a.cmd == "supersede":
        try:
            fn = erroneous_to_superseded if a.from_erroneous else supersede_records
            n = fn(a.subject, json.loads(a.match), reason=a.reason, on=a.on)
        except ValueError as ex:
            print(f"印を付けなかった: {ex}", file=sys.stderr)
            return 1
        _dump({"superseded": n, "path": str(log_path(a.subject))})
        return 0
    if a.cmd == "mark-erroneous":
        try:
            n = mark_erroneous(a.subject, json.loads(a.match), reason=a.reason, corrected_on=a.corrected_on)
        except ValueError as ex:
            print(f"印を付けなかった: {ex}", file=sys.stderr)
            return 1
        _dump({"marked": n, "path": str(log_path(a.subject))})
        return 0
    if a.cmd == "read":
        if not a.live:
            print("read は --live が必要です(読むのは答えるときに 1 回だけ。キャッシュはない)", file=sys.stderr)
            return 2
        if http_get is None and not livegate.live_allowed():           # 偽の http_get を注入したテストは実通信にならない。本物の通信は常にゲートを通る
            print(livegate.refusal(), file=sys.stderr)
            return 2
        if a.max_requests is None or a.max_requests < 1:
            print("--live は明示的な --max-requests (1 以上)が必要です", file=sys.stderr)
            return 2
        if http_get is None and not os.environ.get("BIYORI_REQ_LOG"):
            print("--live は計測フック(BIYORI_REQ_LOG)が有効なときだけ実行します(許可リスト・上限の強制のため)", file=sys.stderr)
            return 2
        cfg = load_config()
        getter = None
        if http_get is None:
            from .fetch.live import SessionGetter
            t = cfg["live"]["request_timeout"]
            getter = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"])
        try:
            res = read_live(a.source, registry=registry, policy=policy, cfg=cfg, now=parse_now(a.now), http_get=http_get or getter,
                            max_requests=a.max_requests, record=a.record)
        finally:
            if getter is not None:
                getter.close()
        _dump(res)
        return 0 if all(r.get("reads") for r in res["results"]) else 1
    if a.cmd == "summary":
        now = parse_now(a.now)
        dates = [date.fromisoformat(x) for x in a.date] if a.date else next_weekend(now)
        _dump(summarize(records_on(a.subject, now.date()), registry=registry, catalog_doc=catalog_mod.load_catalog(a.subject),
                        policy=policy, on=now.date(), dates=dates, early=a.early, late=a.late))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
