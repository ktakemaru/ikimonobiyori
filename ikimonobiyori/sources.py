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
from .paths import SOURCES_DIR, SOURCES_POLICY_PATH, SOURCES_SCHEMA_PATH, data_path

APPROVED = "approved"
USABLE_TERMS = "no_prohibition_found"
READABLE_OK = "ok"
V0_ID_PARTS = ("agent", "subject", "date", "site")        # v0 の提案の id の形: ikimonobiyori:<subject>:<日付>:<名所>
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


def make_record(*, registry, policy, source_id, read_at, state, updated=None, site=None, name=None, label=None, year_inferred=None,
                method=None, forecast=None, event_start=None, event_end=None):
    """読んだ結果 1 件 → 記録(段階はコードが決める)。検査は validate_record。
    method は読み方(agent_summary / code / user_verified。既定は方針の default_method)、forecast は公式の見頃予測の原文、
    event_start・event_end はまつり・ライトアップの期間(YYYY-MM-DD)。"""
    src = sources_by_id(registry).get(source_id)
    stage = normalize_state(src, state)[0] if src else None
    rec = {"schema": policy["record"]["schema"], "subject": registry["subject"], "source_id": source_id,
           "official_state": state, "stage": stage, "official_updated": updated, "read_at": read_at,
           "url": src["url"] if src else None, "method": method or policy["record"]["default_method"]}
    for k, v in (("site", site), ("name", name), ("label", label), ("updated_year_inferred", year_inferred),
                 ("official_forecast", forecast), ("event_start", event_start), ("event_end", event_end)):
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
    if any(k in rec for k in rp["erroneous_fields"]):
        if rec.get("erroneous") is not True or not rec.get("erroneous_reason") or not catalog_mod.valid_date(rec.get("corrected_on") or ""):
            errs.append("誤りの印は erroneous: true・erroneous_reason・corrected_on(YYYY-MM-DD)をそろえて付ける")
    if "updated_year_inferred" in rec and not isinstance(rec["updated_year_inferred"], bool):
        errs.append("updated_year_inferred は真偽値")
    elif rec.get("official_updated") is not None and (src.get("notation") or {}).get("year_shown") is False and rec.get("updated_year_inferred") is not True:
        errs.append(f"情報源 {src['id']} の日付には年がない(notation.year_shown: false)。年を補った更新日には updated_year_inferred: true が要る")
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


def _read_all(subject, env=None):
    p = log_path(subject, env)
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def read_records(subject, env=None, include_erroneous=False):
    """記録を読む。誤りの印(erroneous: true)の付いた記録は、include_erroneous を明示しない限り使わない(段階16 A-1)。"""
    return [r for r in _read_all(subject, env) if include_erroneous or r.get("erroneous") is not True]


def records_on(subject, day, env=None):
    """day(date)に読んだ記録だけ(読んだ時刻のオフセットでの暦日)。誤りの印の付いたものは除く。記録の再利用は同じ日のうちだけ(段階16 A-2)。"""
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
    p = log_path(subject, env)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(tmp, p)
    return n


def _key(rec):
    return tuple(rec.get(k) for k in ("source_id", "site", "name", "label", "official_state", "official_updated",
                                      "official_forecast", "event_start", "event_end", "method"))


def append_records(records, *, registry, policy, env=None):
    """検査に通った記録を追記する。同じ事実(情報源・名所・状態・公式の更新日)がもうあれば足さない。
    1 件でも検査に落ちたら何も書かない。→ (書いた件数, 重複で足さなかった件数)。"""
    bad = [(i, e) for i, r in enumerate(records) for e in validate_record(r, registry=registry, policy=policy)]
    if bad:
        raise ValueError("; ".join(f"[{i}] {e}" for i, e in bad))
    if any(r.get("erroneous") is True for r in records):
        raise ValueError("誤りの印の付いた記録は足さない(印は mark_erroneous で付ける)")
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

def summarize(records, *, registry, catalog_doc, policy, on, dates):
    """on(date)に読んだ記録(呼び出し側が records_on で絞る)→ 地点ごとの答えの材料。通信しない。
    - 段階・新しさ(年を補った更新日は「新しさ不明」)・表示が古い可能性(段階16 A-3)
    - 公式の見頃予測の日の範囲と、対象の日にかかるか(段階16 A-8)
    - まつり・ライトアップの期間が対象の日にかかるか"""
    srcs = sources_by_id(registry)
    entries = {e["id"]: e for e in catalog_mod.approved_entries(catalog_doc or {})}
    rows, clash = [], conflicts(records)
    for r in sorted(latest_by_place(records), key=lambda r: (r["source_id"], r.get("site") or "", r.get("name") or "", r.get("label") or "")):
        src = srcs.get(r["source_id"]) or {}
        up = date.fromisoformat(r["official_updated"]) if r.get("official_updated") else None
        fw = forecast_window(r.get("official_forecast"), parse_now(r["read_at"]).year, policy)
        ev = (date.fromisoformat(r["event_start"]), date.fromisoformat(r["event_end"])) if r.get("event_start") else None
        rows.append({"source": r["source_id"], "kind": src.get("kind"), "site": r.get("site"), "name": r.get("name"), "label": r.get("label"),
                     "official_state": r.get("official_state"), "stage": r.get("stage"), "stage_label": stage_label(policy, r["subject"], r.get("stage")),
                     "official_updated": r.get("official_updated"), "year_inferred": year_unknown(src, r),
                     "freshness": freshness(up, on, policy, year_unknown(src, r)),
                     "stale_display_suspect": stale_display_suspect(r, entries.get(r.get("site")), policy, src),
                     "official_forecast": r.get("official_forecast"),
                     "forecast_window": [d.isoformat() for d in fw] if fw else None, "forecast_hits_dates": overlaps(fw, dates),
                     "event": [d.isoformat() for d in ev] if ev else None, "event_hits_dates": overlaps(ev, dates),
                     "method": r.get("method", policy["record"]["default_method"]), "read_at": r["read_at"], "url": r.get("url"),
                     "conflict": clash.get(_place(r))})
    return {"on": on.isoformat(), "dates": [d.isoformat() for d in dates], "rows": rows,
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
    n = sub.add_parser("normalize", help="公式の状態 → 共通の段階")
    n.add_argument("--source", required=True)
    n.add_argument("--state", required=True)
    r = sub.add_parser("record", help="読んだ結果(事実だけ)を記録に追記する(IKIMONOBIYORI_DATA_DIR の下)")
    r.add_argument("--read-at", required=True, help="読んだ時刻。ISO 8601(オフセット必須)")
    r.add_argument("--batch", required=True,
                   help="JSON の配列: [{source, site|name, label?, state, updated?, year_inferred?, method?, forecast?, event_start?, event_end?}]")
    lg = sub.add_parser("log", help="記録を表示する(誤りの印の付いた記録は --include-erroneous のときだけ)")
    lg.add_argument("--source")
    lg.add_argument("--include-erroneous", action="store_true")
    me = sub.add_parser("mark-erroneous", help="記録に誤りの印を付ける(消さない。IKIMONOBIYORI_DATA_DIR の下)")
    me.add_argument("--match", required=True, help='JSON の辞書(例: {"source_id": "...", "name": "湖尻", "official_state": "色づきはじめ"})')
    me.add_argument("--reason", required=True)
    me.add_argument("--corrected-on", required=True, help="YYYY-MM-DD")
    sm = sub.add_parser("summary", help="同じ日に読んだ記録から、答えの材料(段階・新しさ・見頃予測・期間)を出す(通信しない・書き込まない)")
    sm.add_argument("--now", required=True, help="ISO 8601(オフセット必須)。この暦日に読んだ記録だけを使う")
    sm.add_argument("--date", action="append", help="対象の日(省略すると次の土日)")
    rd = sub.add_parser("read", help="reader: code の情報源をコードで 1 回読む(段階16 A-4。--live・--max-requests・計測フックが要る)")
    rd.add_argument("--source", action="append", required=True)
    rd.add_argument("--now", required=True, help="読んだ時刻として記録する時刻。ISO 8601(オフセット必須)")
    rd.add_argument("--live", action="store_true")
    rd.add_argument("--max-requests", type=int)
    rd.add_argument("--record", action="store_true", help="読めた事実を記録に足す(IKIMONOBIYORI_DATA_DIR の下)")
    v = sub.add_parser("v0", help="v0 の出力(biyori-proposal/1)から名所ごとの補助の推定を取り出す(通信しない)")
    v.add_argument("--proposal", required=True)
    v.add_argument("--date", action="append")
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
                            year_inferred=it.get("year_inferred"), method=it.get("method"), forecast=it.get("forecast"),
                            event_start=it.get("event_start"), event_end=it.get("event_end")) for it in items]
        try:
            written, dup = append_records(recs, registry=registry, policy=policy)
        except ValueError as ex:
            print(f"記録しなかった: {ex}", file=sys.stderr)
            return 1
        rows, by_id = [], sources_by_id(registry)
        for rc in recs:
            up = date.fromisoformat(rc["official_updated"]) if rc.get("official_updated") else None
            rows.append({"source": rc["source_id"], "where": rc.get("site") or rc.get("name"), "state": rc["official_state"],
                         "stage": rc["stage"], "stage_label": stage_label(policy, a.subject, rc["stage"]), "updated": rc.get("official_updated"),
                         "freshness": freshness(up, read_at.date(), policy, year_unknown(by_id.get(rc["source_id"]), rc))})
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
        _dump([r for r in read_records(a.subject, include_erroneous=a.include_erroneous) if not a.source or r["source_id"] == a.source])
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
                        policy=policy, on=now.date(), dates=dates))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
