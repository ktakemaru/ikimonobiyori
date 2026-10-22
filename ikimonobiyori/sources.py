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
  python -X utf8 -m ikimonobiyori.sources log [--source ID]
"""
import argparse
import calendar
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from jsonschema import Draft202012Validator

from . import catalog as catalog_mod
from .config import load_config
from .paths import CATALOG_DIR, SOURCES_DIR, SOURCES_POLICY_PATH, SOURCES_SCHEMA_PATH, data_path

APPROVED = "approved"
USABLE_TERMS = "no_prohibition_found"
READABLE_OK = "ok"
ROBOTS_BLOCKING = ("disallows", "ai_agents_blocked")      # 仮承認しない robots.txt の判定(安全側。docs/stage15-decisions.md)


# ---- 読み込み ----

def load_policy(path=None):
    return yaml.safe_load(Path(path or SOURCES_POLICY_PATH).read_text(encoding="utf-8"))


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
    """→ [(ファイル, エラーのリスト)]。"""
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
    if s in (nt.get("map") or {}):
        return nt["map"][s], "mapped"
    if s in (nt.get("no_info") or []):
        return None, "no_info"
    return None, "unknown"


# ---- 新しさ ----

def freshness(updated, on, policy):
    """公式の更新日(date か None)から on(date)までの日数で分ける。→ {age_days, class, label}。
    更新日が on より後なら ValueError(年の補い方の誤りなど。推測で直さない)。"""
    fr = policy["freshness"]
    if updated is None:
        return {"age_days": None, "class": "unknown", "label": fr["labels"]["unknown"]}
    age = (on - updated).days
    if age < 0:
        raise ValueError(f"公式の更新日 {updated} が {on} より後")
    cls = "fresh" if age <= val(fr["fresh_max_days"]) else "somewhat_old" if age <= val(fr["somewhat_old_max_days"]) else "old"
    return {"age_days": age, "class": cls, "label": fr["labels"][cls]}


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


def candidates(catalog_doc, registry, dates, policy):
    """名所カタログ(承認済み)から候補を絞り、読む情報源を 1 回ずつにまとめる。→ 辞書(JSON にできる)。"""
    margin = val(policy["candidates"]["window_margin_days"])
    srcs = sources_by_id(registry)
    sites, out_of_season = [], []
    for e in catalog_mod.approved_entries(catalog_doc or {}):
        tw = e.get("typical_window")
        if tw:
            dist = min(days_from_window(d, tw) for d in dates)
            season = "in_window" if dist == 0 else "near" if dist <= margin else "out"
        else:
            dist, season = None, "no_window"
        row = {"site": e["id"], "name": e["name"], "season": season, "days_from_window": dist,
               "typical_window": {k: tw[k] for k in ("start", "end", "source_url") if k in tw} if tw else None,
               "official_status_url": e.get("official_status_url"),
               "sources": [{"id": sid, "kind": srcs[sid]["kind"], "approval": srcs[sid]["approval"]["status"],
                            "readable": srcs[sid]["readable"]["status"], "url": srcs[sid]["url"]}
                           for sid in e.get("status_sources") or [] if sid in srcs]}
        (out_of_season if season == "out" else sites).append(row)
    plan, human = {}, {}
    for row in sites:
        for s in row["sources"]:
            bucket = plan if s["approval"] == APPROVED else human
            bucket.setdefault(s["id"], {"id": s["id"], "kind": s["kind"], "url": s["url"], "sites": []})["sites"].append(row["site"])
    no_status = [r["site"] for r in sites if not any(s["approval"] == APPROVED and s["kind"] == "status_page" for s in r["sources"])]
    return {"dates": [d.isoformat() for d in dates], "window_margin_days": margin,
            "sites": sites,
            # 例年の時期から外れた名所。読む情報源(read_plan)がこの名所も伝えていれば、ついでに分かる公式の現況を示せる(現況が主。段階15)
            "out_of_season": [{"site": r["site"], "name": r["name"], "days_from_window": r["days_from_window"],
                               "covered_by_read_plan": [s["id"] for s in r["sources"] if s["id"] in plan]} for r in out_of_season],
            "read_plan": sorted(plan.values(), key=lambda x: (x["kind"] != "status_page", x["id"])),
            "human_urls": sorted(human.values(), key=lambda x: x["id"]),
            "no_status_source": no_status}


# ---- 記録(JSON Lines) ----

def log_path(subject, env=None):
    return data_path(load_config()["status_log"]["dir"], env) / f"{subject}.jsonl"


def make_record(*, registry, policy, source_id, read_at, state, updated=None, site=None, name=None, label=None, year_inferred=None):
    """読んだ結果 1 件 → 記録(段階はコードが決める)。検査は validate_record。"""
    src = sources_by_id(registry).get(source_id)
    stage = normalize_state(src, state)[0] if src else None
    rec = {"schema": policy["record"]["schema"], "subject": registry["subject"], "source_id": source_id,
           "official_state": state, "stage": stage, "official_updated": updated, "read_at": read_at,
           "url": src["url"] if src else None}
    for k, v in (("site", site), ("name", name), ("label", label), ("updated_year_inferred", year_inferred)):
        if v is not None:
            rec[k] = v
    return rec


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
    if "updated_year_inferred" in rec and not isinstance(rec["updated_year_inferred"], bool):
        errs.append("updated_year_inferred は真偽値")
    try:
        ra = parse_now(rec["read_at"])
    except (TypeError, ValueError) as ex:
        return errs + [f"read_at: {ex}"]
    up = rec.get("official_updated")
    if up is not None:
        if not catalog_mod.valid_date(up):
            errs.append(f"official_updated={up} は日付でない")
        elif date.fromisoformat(up) > ra.date():
            errs.append(f"official_updated={up} が読んだ日 {ra.date()} より後")
    return errs


def read_records(subject, env=None):
    p = log_path(subject, env)
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _key(rec):
    return tuple(rec.get(k) for k in ("source_id", "site", "name", "label", "official_state", "official_updated"))


def append_records(records, *, registry, policy, env=None):
    """検査に通った記録を追記する。同じ事実(情報源・名所・状態・公式の更新日)がもうあれば足さない。
    1 件でも検査に落ちたら何も書かない。→ (書いた件数, 重複で足さなかった件数)。"""
    bad = [(i, e) for i, r in enumerate(records) for e in validate_record(r, registry=registry, policy=policy)]
    if bad:
        raise ValueError("; ".join(f"[{i}] {e}" for i, e in bad))
    seen = {_key(r) for r in read_records(registry["subject"], env)}
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


# ---- CLI ----

def _dump(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ikimonobiyori.sources")
    ap.add_argument("--subject", default="autumn_leaves")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="台帳を検査する(通信しない・書き込まない)")
    c.add_argument("--sources-dir")
    c.add_argument("--catalog-dir")
    w = sub.add_parser("weekend", help="対象の日の候補と、読む情報源の一覧(通信しない・書き込まない)")
    w.add_argument("--now", required=True, help="ISO 8601(オフセット必須)")
    w.add_argument("--date", action="append", help="対象の日(YYYY-MM-DD。省略すると次の土日)")
    n = sub.add_parser("normalize", help="公式の状態 → 共通の段階")
    n.add_argument("--source", required=True)
    n.add_argument("--state", required=True)
    r = sub.add_parser("record", help="読んだ結果(事実だけ)を記録に追記する(IKIMONOBIYORI_DATA_DIR の下)")
    r.add_argument("--read-at", required=True, help="読んだ時刻。ISO 8601(オフセット必須)")
    r.add_argument("--batch", required=True, help="JSON の配列: [{source, site|name, label?, state, updated?, year_inferred?}]")
    lg = sub.add_parser("log", help="記録を表示する")
    lg.add_argument("--source")
    a = ap.parse_args(argv)

    if a.cmd == "check":
        bad = 0
        for p, errs in check_all(a.sources_dir, a.catalog_dir):
            for e in errs:
                print(f"NG  {p.parent.name}/{p.name}: {e}")
            if not errs:
                print(f"OK  {p.parent.name}/{p.name}")
            bad += bool(errs)
        return 1 if bad else 0
    policy, registry = load_policy(), load_registry(a.subject)
    if registry is None:
        print(f"台帳がない: {a.subject}", file=sys.stderr)
        return 2
    if a.cmd == "weekend":
        now = parse_now(a.now)
        dates = [date.fromisoformat(x) for x in a.date] if a.date else next_weekend(now)
        _dump({"now": now.isoformat(), **candidates(catalog_mod.load_catalog(a.subject), registry, dates, policy)})
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
                            year_inferred=it.get("year_inferred")) for it in items]
        try:
            written, dup = append_records(recs, registry=registry, policy=policy)
        except ValueError as ex:
            print(f"記録しなかった: {ex}", file=sys.stderr)
            return 1
        rows = []
        for rc in recs:
            up = date.fromisoformat(rc["official_updated"]) if rc.get("official_updated") else None
            rows.append({"source": rc["source_id"], "where": rc.get("site") or rc.get("name"), "state": rc["official_state"],
                         "stage": rc["stage"], "stage_label": stage_label(policy, a.subject, rc["stage"]), "updated": rc.get("official_updated"),
                         "freshness": freshness(up, read_at.date(), policy)})
        _dump({"written": written, "duplicates": dup, "path": str(log_path(a.subject)), "rows": rows})
        return 0
    if a.cmd == "log":
        _dump([r for r in read_records(a.subject) if not a.source or r["source_id"] == a.source])
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
