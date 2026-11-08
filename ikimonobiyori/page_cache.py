"""取得のキャッシュ(ページ単位。段階63b 第2部)。通信しない。

読み直しの判定を「ページに書かれた日付」から「最後に読んだ時刻」に変える。公式の現況ページは週 1〜2 回の更新が多いので、
昨日読んで内容が変わっていないページを、ページの日付が古いという理由で毎回読み直さない。

- 置き場所はデータ置き場の `cache/pages.jsonl`(リポジトリの外)。1 行 = 1 回の読み取り:
  URL・読んだ時刻・読めたか・種類・取り出した事実のハッシュ・事実の件数。**本文は保存しない**(山と溪谷オンライン・転載禁止の
  施設の決まりを守る。ハッシュは取り出した事実(状態・日付・例年の時期・行事・実用情報)から作る。本文のハッシュを持たないのは、
  本文を読むのがエージェントの道具で、このコードには本文が届かないため)。
- 最後に読んだ時刻は、このキャッシュに加えて、観察の記録の `read_at` と「最後に確かめた日時」(`*.confirmed.json`)、
  これまでの「今日読んだページ」(`ask/fetched_urls.json`。日付だけなので、その日の 0 時に読んだとみなす)からも取る。
- 種類ごとの有効期間は data/ask/plan.yaml の `page_cache.ttl_hours`。"""
import hashlib
import json
from datetime import datetime, timedelta

from . import answer_plan as AP
from .paths import data_path

KEEP = ("url", "read_at", "ok", "kind", "facts_hash", "n_facts", "reason")
FACT_FIELDS = ("subject", "spot", "name", "state", "state_date", "state_date_text", "typical", "event", "practical", "notice")


def cfg(policy=None):
    return (policy or AP.load_policy())["page_cache"]


def path(env=None, policy=None):
    return data_path(cfg(policy)["file"], env)


def facts_hash(rows):
    """取り出した事実(本文ではない)のハッシュ。同じ事実なら同じ値。"""
    keep = sorted(json.dumps({k: r.get(k) for k in FACT_FIELDS if r.get(k) is not None}, ensure_ascii=False, sort_keys=True) for r in rows)
    return hashlib.sha256("\n".join(keep).encode("utf-8")).hexdigest()[:32]


def note(entries, now, env=None, policy=None):
    """読んだ(読めなかった)ページを追記する。entries: [{url, ok, kind?, facts_hash?, n_facts?, reason?}]。決まった項目だけを書く(本文は書かない)。"""
    rows = []
    for e in entries:
        if not e.get("url"):
            continue
        r = {k: e.get(k) for k in KEEP if e.get(k) is not None}
        r["read_at"] = (e.get("read_at") or now.isoformat())
        r.setdefault("ok", True)
        rows.append(r)
    if not rows:
        return 0
    p = path(env, policy)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def entries_for_batch(batch, by_url):
    """record に渡した事実の配列とページごとの結果 → キャッシュの行(URL ごとに 1 行)。"""
    groups = {}
    for r in batch if isinstance(batch, list) else []:
        if isinstance(r, dict) and r.get("url"):
            groups.setdefault(r["url"], []).append(r)
    out = []
    for u in by_url or []:
        rows = groups.get(u["url"]) or []
        out.append({"url": u["url"], "ok": True, "facts_hash": facts_hash(rows), "n_facts": len(rows)})
    return out


def _ts(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def last_reads(now, env=None, policy=None):
    """{URL: 最後に読んだ時刻(datetime)}。キャッシュ・観察の記録・最後に確かめた日時・これまでの今日読んだページから。"""
    from . import observations as O
    out = {}

    def put(u, t):
        t = _ts(t) if isinstance(t, str) else t
        if not u or t is None:
            return
        if t.tzinfo is None and now.tzinfo is not None:
            t = t.replace(tzinfo=now.tzinfo)
        if t > now:                                            # 未来の時刻(時計の食い違い)は使わない
            return
        if u not in out or t > out[u]:
            out[u] = t
    try:
        for line in path(env, policy).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                put(r.get("url"), r.get("read_at"))
    except (OSError, ValueError):
        pass
    opol = O.load_policy()
    for subject in opol["subjects"]:
        p = O.log_path(subject, env, opol)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    put(r.get("url"), r.get("read_at"))
        for v in O.read_confirmed(subject, env, opol).values():
            put(v.get("url"), v.get("last_confirmed_at"))
    try:
        legacy = json.loads(data_path("ask/fetched_urls.json", env).read_text(encoding="utf-8"))
        for day, urls in (legacy or {}).items():
            for u in urls or []:
                put(u, datetime.fromisoformat(day + "T00:00:00").replace(tzinfo=now.tzinfo))
    except (OSError, ValueError, AttributeError):
        pass
    return out


def ttl(kind, policy=None):
    hours = cfg(policy)["ttl_hours"]
    v = hours.get(kind, hours["status"])
    return timedelta(hours=v["value"] if isinstance(v, dict) else v)


def is_fresh(url, kind, now, reads, policy=None):
    t = reads.get(url)
    return t is not None and now - t < ttl(kind, policy)


def fresh_urls(now, env=None, kind="status", policy=None, reads=None):
    """有効期間の中で読んだページの URL(種類の既定は現況。いちばん短い有効期間なので、読み残しを作らない)。"""
    reads = last_reads(now, env, policy) if reads is None else reads
    return {u for u in reads if is_fresh(u, kind, now, reads, policy)}


LEDGER_KIND = {"status_page": "status", "forecast_page": "status", "event_page": "event", "access_page": "practical", "reference_link": "reference"}
_REGISTRY = None


def registry_kinds():
    """台帳(data/sources/*.yaml。紹介サイトの台帳も)の情報源の種類と、まつりの一覧・行事の台帳の URL → {URL: 種類}。
    台帳の参考リンク(reference_link)は現況の情報源に数えない(段階17 の見直し)ので「reference」。"""
    global _REGISTRY
    if _REGISTRY is None:
        from . import yamlcache
        from .paths import DATA_FILES_DIR
        out = {}
        src = DATA_FILES_DIR / "sources"
        for f in sorted(list(src.glob("*.yaml")) + list((src / "secondary").glob("*.yaml"))):
            if f.name == "policy.yaml":
                continue
            for e in (yamlcache.load(f) or {}).get("sources") or []:
                if isinstance(e, dict) and e.get("url") and e.get("kind") in LEDGER_KIND:
                    out.setdefault(e["url"], LEDGER_KIND[e["kind"]])
        for f, key in ((DATA_FILES_DIR / "observations" / "festivals.yaml", "festivals"), (DATA_FILES_DIR / "facility_events" / "events.yaml", "events")):
            if f.exists():
                for e in (yamlcache.load(f) or {}).get(key) or []:
                    if isinstance(e, dict) and e.get("url"):
                        out[e["url"]] = "event"
        _REGISTRY = out
    return _REGISTRY


def page_kind(url, c, subject):
    """名所の事実の中での役割と台帳の種類 → ページの種類(行事・実用情報・参考・野鳥・現況)。
    その名所の現況・履歴を出したページは、台帳の種類に関わらず現況(野鳥は野鳥)。"""
    def urls(key):
        return {(x or {}).get("url") for x in c.get(key) or [] if isinstance(x, dict)}
    status = ({(c.get("current") or {}).get("url")} | urls("history")) - {None}
    own = "birds" if subject == "birds" else "status"
    if url in status:
        return own
    if url in urls("festivals") | urls("events"):
        return "event"
    if url in urls("practical"):
        return "practical"
    k = registry_kinds().get(url)
    if k and k != "status":
        return k
    return own


def candidate_last_read(c, reads):
    """名所の現況の記録を最後に読んだ(確かめた)時刻。"""
    cur = c.get("current") or {}
    ts = [t for t in (_ts(cur.get("read_at")), _ts(cur.get("last_confirmed_at")), reads.get(cur.get("url"))) if t is not None]
    return max(ts) if ts else None
