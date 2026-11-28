"""資料(ask brief)の自動の読み直しの対象を選ぶ(通信しない)。

台帳(data/sources/*.yaml)で承認済みの現況のページ(status_page)を、covers(名所の id か名前)で資料の候補に結ぶ。
以前は候補の pages(名所の一覧と名所カタログの sources)に URL があるページだけを読んでいたので、承認を covers と
status_sources にだけ書いたページは読まれなかった(2026-11-28)。
- 期限切れの判定はページごと(候補の今の現況を読んだばかりでも、ほかのページが古ければ読む)。
- 資料の経路(facts.json の有無)や、候補が「避ける」側かどうかに関係なく、資料の候補すべてを見る。
- 上限(max_pages)の枠は、質問が名前を挙げた場所 → 聞かれた花・種に合うページ → 候補の順、の順で使う。
今までの形の答え(ask answer)の読み直し(answer_plan.refresh_targets)は変えない。"""
import json
from datetime import date

from .paths import data_path

CANDIDATE_SUBJECTS = ("autumn_leaves", "flowers", "birds")
CATALOG_ONLY = ("wintering_birds",)                    # 観察の記録の候補を持たない名所カタログ(種の名所と時期の候補になる)
SUBJECT_LEDGERS = {"autumn_leaves": ("autumn_leaves",), "flowers": ("flowers",), "birds": ("birds", "wintering_birds"),
                   "wintering_birds": ("wintering_birds", "birds")}
RECORD_SUBJECT = {"wintering_birds": "birds"}


def ledger_pages():
    """台帳で承認済みの現況のページ。→ [{url, publisher, ledger, id, approved_on, covers, flower_kinds}]。"""
    from . import auto_refresh as AU
    from . import sources as S
    out = []
    for ledger in AU.LEDGERS:
        try:
            reg = S.load_registry(ledger)
        except (OSError, ValueError):
            continue
        for src in (reg or {}).get("sources") or []:
            if src.get("kind") == "status_page" and S.is_approved(src) and src.get("url"):
                out.append({"url": src["url"], "publisher": src.get("publisher"), "ledger": ledger, "id": src["id"],
                            "approved_on": (src.get("approval") or {}).get("approved_on") or "", "covers": src.get("covers") or [],
                            "flower_kinds": src.get("flower_kinds") or []})
    return out


def place_index():
    """名所(観察の記録の候補と、候補を持たないカタログ)→ [{subject, name, ids, keys, pages}]。"""
    from . import catalog as catalog_mod
    from . import observations as O
    out = []
    for subject in CANDIDATE_SUBJECTS:
        for c in O.all_candidates(subject):
            names = [c.get("name"), c.get("catalog_name"), *(c.get("aliases") or [])]
            out.append({"subject": subject, "name": c.get("name"), "ids": {x for x in (c.get("id"), c.get("catalog_ref"), *(c.get("merged") or [])) if x},
                        "keys": {O._key(n) for n in names if n}, "pages": [p.get("url") for p in c.get("pages") or []]})
    for subject in CATALOG_ONLY:
        for e in (catalog_mod.load_catalog(subject) or {}).get("entries") or []:
            if e.get("example") or e.get("status") in ("retired", "rejected"):
                continue
            out.append({"subject": subject, "name": e.get("name"), "ids": {e["id"]}, "keys": {O._key(e.get("name"))},
                        "pages": [s.get("url") for s in e.get("sources") or []]})
    return out


def pages_for(names, subject=None, *, index=None, ledger=None):
    """名所の名前(別の名前を含む)→ その名所の承認済みの現況のページ。[{…ledger_pages の項目, kinds}]。"""
    from . import auto_refresh as AU
    from . import observations as O
    index = place_index() if index is None else index
    ledger = ledger_pages() if ledger is None else ledger
    keys = {O._key(n) for n in names if n}
    allowed = SUBJECT_LEDGERS.get(subject)
    places = [p for p in index if p["keys"] & keys and (allowed is None or p["subject"] in allowed)]
    ids = {i for p in places for i in p["ids"]}
    all_keys = keys | {k for p in places for k in p["keys"]}
    own = {AU.url_key(u) for p in places for u in p["pages"] if u}
    out = []
    for src in ledger:
        if allowed is not None and src["ledger"] not in allowed:
            continue
        hits = [cv for cv in src["covers"] if (cv.get("site") and cv["site"] in ids) or (cv.get("name") and O._key(cv["name"]) in all_keys)]
        if not hits and AU.url_key(src["url"]) not in own:
            continue
        kinds = [cv["flower_kind"] for cv in hits if cv.get("flower_kind")] or list(src["flower_kinds"])
        out.append({**src, "kinds": kinds})
    return out


def reachable_urls():
    """どれかの名所から届く、承認済みの現況のページの URL(比べる形)。"""
    from . import auto_refresh as AU
    index, ledger = place_index(), ledger_pages()
    out = set()
    for p in index:
        out |= {AU.url_key(x["url"]) for x in pages_for([p["name"]], p["subject"], index=index, ledger=ledger)}
    return out


def _kind_rank(kinds, words):
    """聞かれた花・種との合い方: 0 合う(または種を聞いていない) / 1 ページの種類の記載がない / 2 合わない。"""
    if not words:
        return 0
    if not kinds:
        return 1
    return 0 if any(w in k or k in w for w in words for k in kinds) else 2


def _hold(question, pages, held, now, env, hours, directory):
    """同じ質問で資料を作り直すとき(読んで記録したあと)、1 回目に上限で外したページを足さない(読み直しがくり返されないように)。
    1 回目より後に台帳に足したページは、外した中に無いので読む。"""
    from datetime import datetime, timedelta
    p = data_path(directory, env) / "rounds.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    key = "".join((question or "").split())
    span = timedelta(hours=hours)
    prev = doc.get(key)
    if prev and timedelta(0) <= now - datetime.fromisoformat(prev["at"]) <= span:
        return [x for x in pages if x["url"] not in set(prev["held"])], False
    doc = {k: v for k, v in doc.items() if timedelta(0) <= now - datetime.fromisoformat(v["at"]) <= span}
    doc[key] = {"at": now.isoformat(), "held": [x["url"] for x in held]}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return pages, True


def targets(question, cands, *, now, env=None, asked_names=(), species_words=(), subjects=(), max_pages, hold_hours=None, directory="auto_refresh"):
    """資料の候補の、有効期間が切れた承認済みの現況のページ(読む順。最大 max_pages)。auto_refresh.run に渡す形。"""
    from . import auto_refresh as AU
    from . import observations as O
    from . import page_cache as PC
    index, ledger = place_index(), ledger_pages()
    reads = {}
    for u, t in PC.last_reads(now, env).items():
        k = AU.url_key(u)
        if k not in reads or t > reads[k]:
            reads[k] = t
    asked = {O._key(n) for n in asked_names if n}
    order = sorted(range(len(cands)), key=lambda i: (cands[i].get("rank") if cands[i].get("rank") is not None else len(cands) + i, i))
    best = {}
    for pos, i in enumerate(order):
        r = cands[i]
        names = [r.get("name"), *(r.get("merged_from") or [])]
        subject = r.get("subject") or (subjects[0] if len(subjects) == 1 else None)
        is_asked = any(O._key(n) in asked for n in names if n)
        for src in pages_for(names, subject, index=index, ledger=ledger):
            rank = _kind_rank(src["kinds"], species_words)
            if subject is None and species_words and src["ledger"] == "autumn_leaves" and (rank or not src["kinds"]):
                continue                              # 花・鳥を聞いた質問で、紅葉の台帳のページは読まない
            k = AU.url_key(src["url"])
            kind = "birds" if src["ledger"] in ("birds", "wintering_birds") else "status"
            if PC.is_fresh(k, kind, now, reads):
                continue
            try:
                newer = -date.fromisoformat(src["approved_on"]).toordinal()
            except ValueError:
                newer = 0
            key = (0 if is_asked else 1, rank, pos, newer, src["url"])
            if k in best and best[k][0] <= key:
                continue
            record_subject = RECORD_SUBJECT.get(src["ledger"], src["ledger"])
            dates = [O.state_date_of(x) for x in AU._latest_records(record_subject, src["url"], env)]
            dates = sorted(d for d in dates if d)
            t = reads.get(k)
            best[k] = (key, {"name": r.get("name"), "subject": record_subject, "url": src["url"], "publisher": src["publisher"],
                             "source_class": "official", "kind": kind, "reason": "expired" if t else "no_current",
                             "current_date": dates[-1] if dates else None, "last_read": t.isoformat() if t else None, "source_id": src["id"]})
    pages = [v for _k, v in sorted(best.values(), key=lambda x: x[0])]
    if hold_hours is not None:
        pages, _first = _hold(question, pages, pages[max_pages:], now, env, hold_hours, directory)
    return pages[:max_pages]


__all__ = ["ledger_pages", "place_index", "pages_for", "reachable_urls", "targets"]
