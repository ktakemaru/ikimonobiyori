"""「今日の準備」(段階63b 第3部)。通信しない。

承認済みの情報源のうち、最後に読んでから有効期間(data/ask/plan.yaml の page_cache.ttl_hours)を過ぎたものを、
優先順(紅葉・花・野鳥の現況 → 施設の発信 → 行事 → 実用情報)の一覧にする。読むのはエージェントの道具で、読んだ事実は
既存の `ask record`(施設の発信は `ask vc-record`)で記録する(記録すると取得のキャッシュに読んだ時刻が残る)。
記録する事実がなかったページ・読めなかったページは `ask warm --mark <URL> [--failed <理由>]` で読んだ時刻だけを残す。
答えは作らない。ふだんの質問は、ここで読んだ記録(有効期間の中)だけで答え、読み直しは上限(refresh.max_pages)まで。"""
from . import page_cache as PC
from . import yamlcache
from .paths import DATA_FILES_DIR

SUBJECT_ORDER = ("autumn_leaves", "flowers", "birds", "wintering_birds")
KIND_ORDER = ("status", "birds", "visitor_center", "event", "practical")
HOW = {"status": "ask record --batch", "birds": "ask record --batch", "visitor_center": "ask vc-record --batch",
       "event": "ask record --batch(行事の名前と期間)", "practical": "ask record --batch(実用情報 practical)"}


def _ledger_rows():
    out = []
    for sj in SUBJECT_ORDER:
        f = DATA_FILES_DIR / "sources" / f"{sj}.yaml"
        if not f.exists():
            continue
        for e in (yamlcache.load(f) or {}).get("sources") or []:
            if not isinstance(e, dict) or not e.get("url") or (e.get("approval") or {}).get("status") != "approved":
                continue
            kind = PC.LEDGER_KIND.get(e.get("kind"))
            if kind in (None, "reference"):
                continue
            if kind == "status" and sj in ("birds", "wintering_birds"):
                kind = "birds"
            out.append({"kind": kind, "subject": sj, "id": e.get("id"), "publisher": e.get("publisher"), "url": e["url"],
                        "reader": e.get("reader")})
    return out


def _center_rows(today):
    from . import visitor_centers as VC
    return [{"kind": "visitor_center", "subject": None, "id": c["id"], "publisher": c.get("name"), "url": c.get("info_url") or c.get("site_url")}
            for c in VC.approved_centers(today) if c.get("info_url") or c.get("site_url")]


def _event_rows():
    from . import facility_events as FE
    return [{"kind": "event", "subject": None, "id": f["id"], "publisher": f.get("name"), "url": f.get("events_url") or f.get("site_url")}
            for f in FE._approved(FE.load()).values() if f.get("events_url") or f.get("site_url")]


def targets(now, env=None, reads=None, policy=None):
    """有効期間を過ぎた(または読んだことのない)承認済みの情報源の一覧。→ [{order, kind, subject, id, publisher, url, last_read, ttl_hours, record_with}]"""
    reads = PC.last_reads(now, env, policy) if reads is None else reads
    rows = _ledger_rows() + _center_rows(now.date()) + _event_rows()
    out, seen = [], set()
    for r in sorted(rows, key=lambda r: (KIND_ORDER.index(r["kind"]), SUBJECT_ORDER.index(r["subject"]) if r["subject"] in SUBJECT_ORDER else 0)):
        if r["url"] in seen or PC.is_fresh(r["url"], r["kind"], now, reads, policy):
            continue
        seen.add(r["url"])
        t = reads.get(r["url"])
        out.append({**{k: v for k, v in r.items() if v is not None}, "order": len(out) + 1, "last_read": t.isoformat() if t else None,
                    "ttl_hours": PC.ttl(r["kind"], policy).total_seconds() / 3600, "record_with": HOW[r["kind"]]})
    return out


def mark(urls, now, env=None, failed=None):
    """読んだ(読めなかった)時刻だけを取得のキャッシュに残す(記録する事実がなかったページ)。"""
    return PC.note([{"url": u, "ok": not failed, **({"reason": str(failed)[:80]} if failed else {})} for u in urls], now, env)
