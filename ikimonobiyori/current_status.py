"""聞かれた名所の今年の現況を、場所ごと・出どころごとに資料に並べる(指示書 docs/current-status-instructions.md 第 2〜6 部)。

- 第 2 部: 記録の任意の項目 part(どのあたりか。ページ・利用者の言葉を短くそのまま)。part のある記録・利用者の記録は、
  順位・候補の current_state に使わない(observations.read_records の既定で外す)。資料の事実と、聞かれた名所の節にだけ出す。
- 第 3 部: 出どころの区分 user(利用者が現地で確認した記録。URL なし)。決まった言い方で事実にし、見ていない所(unseen)を「確認していない」と出す。
- 第 4 部: 聞かれた名所に「新しい」今年の現況が 1 件も無ければ、research.targets に kind: current_status の対象を出す。
- 第 5 部: 同じ場所で 14 日以内に状態の語が違う事実を「ばらつき」として並べる(消さない)。
- 照合(第 2・3・5・6 部の決まり)は guide_verify から current_status_errors を呼ぶ。
値と語は data/ask/guide_mode.yaml の current_status。新しい値を作らない(今ある記録を指すだけ)。通信しない。"""
import json
import re
from datetime import date, datetime, timedelta

from .paths import data_path

NL = "\n"


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def cfg(c=None):
    if c is None:
        from . import guide_brief as GB
        c = GB.cfg()
    return c.get("current_status") or {}


def on(c=None, part=None):
    C = cfg(c)
    if not C.get("enabled"):
        return False
    return True if part is None else bool((C.get(part) or {}).get("enabled"))


def _md(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None
    return f"{d.month}/{d.day}"


def _jp_md(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None
    return f"{d.month}月{d.day}日"


# ---- 聞かれた名所 ----

def _base(name):
    return re.split(r"[(（]", name or "")[0].strip()


def asked_places(question, cands, c):
    """質問が名前を挙げた山(guide_brief._asked_mountains)と、質問の場所の語と名前が同じ候補。→ [{name, names, site_ref, cands, subjects}]。
    今ある読み取りの範囲だけ(新しい読み取りを足さない)。地域・エリアだけの質問は対象にしない。"""
    from . import guide_brief as GB
    from . import observations as O
    from . import research as RS
    ix = GB._place_index()
    out = []
    by_ref = {}
    for n, ref in ix["mountains"].items():
        by_ref.setdefault(ref, set()).add(n)
    for ref in GB._asked_mountains(question, ix):
        ids = {eid for g in GB._mountain_groups(ref, ix) for eid in g}
        rows = [r for r in cands if (r.get("place_id") or "").split(":", 1)[-1] in ids]
        names = set(by_ref.get(ref) or ()) | {_base(n) for n in by_ref.get(ref) or ()}
        for r in rows:
            names |= {r.get("name"), *(r.get("merged_from") or [])}
        base = sorted({_base(n) for n in by_ref.get(ref) or () if _base(n)}, key=len)
        out.append({"name": base[0] if base else sorted(names)[0], "names": sorted(x for x in names if x), "site_ref": ref,
                    "ids": sorted(ids), "cands": rows})
    words = RS.question_places(question)
    taken = {O._key(n) for p in out for n in p["names"]}
    for r in cands:
        k = O._key(r.get("name"))
        if k and k not in taken and any(O._key(w) == k for w in words):
            out.append({"name": r["name"], "names": sorted({r["name"], *(r.get("merged_from") or [])}), "site_ref": None,
                        "ids": [(r.get("place_id") or "").split(":", 1)[-1]] if r.get("place_id") else [], "cands": [r]})
            taken.add(k)
    return out


def _subjects(cond, policy):
    s = [x for x in (cond.get("subjects") or []) if x in policy["subjects"]]
    return s or list(policy["subjects"])


def _matches(rec, place, policy):
    from . import observations as O
    if rec.get("spot") and rec["spot"] in place["ids"]:
        return True
    k = O._key(rec.get("name"))
    return bool(k) and any(O._key(n) == k for n in place["names"])


def _this_year(rec, now):
    from . import observations as O
    sd = O.state_date_of(rec)
    y = (sd or rec.get("read_at") or "")[:4]
    return y == str(now.year)


def place_records(place, cond, now, env=None, policy=None):
    """聞かれた名所の今年の現況の記録(part のある記録・利用者の記録も)。状態のない記録(名所の登録・行事)は除く。"""
    from . import observations as O
    policy = policy or O.load_policy()
    out = []
    for sj in _subjects(cond, policy):
        for r in O.read_records(sj, env, policy, include_detail=True):
            if not r.get("state") or r.get("event") or not _matches(r, place, policy) or not _this_year(r, now):
                continue
            out.append({**r, "subject": r.get("subject") or sj})
    return out


# ---- 資料に足す事実 ----

def _fact_content(rec, place, C):
    L = C["lines"]
    st = rec.get("state")
    pub = rec.get("publisher") or ""
    where = place["name"] + (f"の{rec['part']}" if rec.get("part") else "")
    from . import observations as O
    sd = O.state_date_of(rec)
    if rec.get("source_class") == "user":
        return L["user"].format(date=_jp_md(sd) or L["no_date"], where=where, state=st)
    label = f"{place['name']}({rec['part']})" if rec.get("part") else f"{place['name']}({L['whole']})"
    if sd:
        return L["dated"].format(label=label, state=st, md=_md(sd), publisher=pub)
    return L["undated"].format(label=label, state=st, publisher=pub)


def _existing_current(F_rows, place):
    names = set(place["names"])
    return [f for f in F_rows if f.get("kind") == "current" and f.get("place") in names]


def add_facts(F, question, cond, cands, now, env, c):
    """聞かれた名所の記録を事実に足し(既にある 1 件は指すだけ)、→ {places: [...]}(資料の current_status の元)。"""
    from . import observations as O
    C = cfg(c)
    policy = O.load_policy()
    places = asked_places(question, cands, c)
    out = []
    for p in places:
        recs = place_records(p, cond, now, env, policy)
        have = _existing_current(F.rows, p)
        rows = []
        for f in have:
            rows.append({"fact": f["id"], "part": None, "state": (f.get("fields") or {}).get("state"), "state_date": f.get("observed"),
                         "publisher": f.get("source"), "source_class": f.get("source_class"), "url": f.get("url"),
                         "state_norm": (f.get("fields") or {}).get("state_norm"), "subject": None})
        recs.sort(key=lambda r: (O.state_date_of(r) or "", r.get("read_at") or ""), reverse=True)
        seen = set()
        newest = []
        for r in recs:                                      # 同じ発信元・同じ場所・同じ区分は、いちばん新しい発信だけ(古い発信は記録に残る)
            k = (r.get("publisher") or r.get("url"), r.get("part") or None, r.get("source_class"), r.get("subject"))
            if k not in seen:
                seen.add(k)
                newest.append(r)
        for r in newest:
            sd = O.state_date_of(r)
            same = next((x for x in rows if not r.get("part") and r.get("source_class") != "user" and x["url"] == r.get("url")
                         and (x["state_date"] or None) == (sd or None) and (x["state"] or "") in (r.get("state") or "")), None)
            if same:
                continue
            fr = F.add("current", _fact_content(r, p, C), place=p["name"], source=r.get("publisher") or (C["lines"]["user_source"] if r.get("source_class") == "user" else None),
                       url=r.get("url"), source_class=r.get("source_class"), observed=sd, read_at=r.get("read_at"),
                       extra={"state": r.get("state"), "state_norm": r.get("state_norm"), "part": r.get("part"),
                              **({"unseen": r["unseen"]} if r.get("unseen") else {}),
                              "freshness": O.freshness(r, now.date(), r["subject"], policy)["label"] if sd else C["lines"]["fresh_unknown"]})
            if fr is None:
                continue
            if r.get("source_class") == "user":
                fr["source_class"] = "user"
            rows.append({"fact": fr["id"], "part": r.get("part"), "state": r.get("state"), "state_date": sd,
                         "publisher": fr.get("source"), "source_class": fr.get("source_class"), "url": r.get("url"),   # 区分は資料の事実と同じ(ホストで決まる)
                         "state_norm": r.get("state_norm"), "subject": r["subject"],
                         **({"unseen": r["unseen"]} if r.get("unseen") else {})})
        rows.sort(key=lambda x: (x.get("state_date") or ""), reverse=True)
        out.append({"place": p, "rows": rows})
    return out


def _fresh(row, now, policy, subjects):
    from . import observations as O
    sd = row.get("state_date")
    if not sd or row.get("source_class") == "user":       # 利用者の記録は、調べるかどうかの数に入れない(発信元の現況は調べる。仮置き)
        return False
    try:
        age = (now.date() - date.fromisoformat(str(sd)[:10])).days
    except ValueError:
        return False
    sj = row.get("subject") or (subjects[0] if subjects else None)
    lim = (policy["freshness"]["fresh_days"] or {}).get(sj)
    if lim is None:
        lim = min(policy["freshness"]["fresh_days"].values())
    return age <= lim


# ---- 第 5 部: ばらつき ----

def _differs(a, b, unknown):
    if a.get("source_class") == "user" or b.get("source_class") == "user":
        return False                                           # 利用者の言葉は比べずに並べるだけ
    na, nb = a.get("state_norm") or unknown, b.get("state_norm") or unknown
    if na == unknown and nb == unknown:
        return False                                           # 辞書に無い言い方どうしは比べない
    if na != unknown and nb != unknown:
        return na != nb
    return (a.get("state") or "") != (b.get("state") or "")      # 片方だけ辞書に無い: 原文が違えば違うものとして並べる(仮置き)


def _within(a, b, days):
    try:
        da, db = date.fromisoformat(str(a["state_date"])[:10]), date.fromisoformat(str(b["state_date"])[:10])
    except (TypeError, ValueError, KeyError):
        return False
    return abs((da - db).days) <= days


def _latest_per_source(rows):
    """同じ発信元(発行元か URL)・同じ場所・同じ区分の記録は、状態の日付がいちばん新しい 1 件だけ(同じ発信元の古い発信と新しい発信を、ばらつきにしない)。"""
    best = {}
    for r in rows:
        if not r.get("state_date"):
            continue
        k = (r.get("publisher") or r.get("url"), r.get("part") or None, r.get("source_class"))
        if k not in best or str(r["state_date"]) > str(best[k]["state_date"]):
            best[k] = r
    keep = {id(r) for r in best.values()}
    return [r for r in rows if id(r) in keep]


def spread(rows, C, unknown):
    S = C.get("spread") or {}
    days = _v(S.get("window_days"))
    groups = {}
    dated = _latest_per_source(rows)
    for i, a in enumerate(dated):
        for b in dated[i + 1:]:
            same_part = (a.get("part") or None) == (b.get("part") or None)
            whole_vs_part = bool(a.get("part")) != bool(b.get("part"))
            if not (same_part or whole_vs_part) or not _within(a, b, days) or not _differs(a, b, unknown):
                continue
            part = a.get("part") or b.get("part")
            g = groups.setdefault(part, {"part": part, "facts": [], "whole_vs_part": False})
            for x in (a, b):
                if x["fact"] not in g["facts"]:
                    g["facts"].append(x["fact"])
            g["whole_vs_part"] = g["whole_vs_part"] or whole_vs_part
    for g in groups.values():                                  # 同じ場所の利用者の記録も並べる(消さない。比べはしない)
        for r in rows:
            if r.get("source_class") == "user" and (r.get("part") or None) == g["part"] and r["fact"] not in g["facts"]:
                g.setdefault("user_facts", []).append(r["fact"])
    return list(groups.values())


# ---- 資料の項目 ----

def build_block(blocks, question, cond, now, env, c):
    """→ 資料の current_status({places: [...], line, whole_note})。聞かれた名所が無ければ places は空。"""
    from . import observations as O
    C = cfg(c)
    policy = O.load_policy()
    unknown = policy["unknown_state"]
    out = []
    for b in blocks:
        p, rows = b["place"], b["rows"]
        unseen = []
        for r in rows:
            for w in r.get("unseen") or []:
                unseen.append({"words": w, "date": r.get("state_date"), "fact": r["fact"]})
        sp = spread(rows, C, unknown) if on(c, "spread") else []
        searched = searched_for(question, p["name"], now, env, c)
        out.append({"name": p["name"], "site_ref": p["site_ref"], "candidates": [r["name"] for r in p["cands"]],
                    "current_parts": [{k: r.get(k) for k in ("part", "state", "state_date", "publisher", "source_class", "url", "fact")} for r in rows],
                    "unseen": unseen, "spread": sp,
                    "fresh": any(_fresh(r, now, policy, _subjects(cond, policy)) for r in rows),
                    "searched": searched})
    return {"places": out, "spread_line": (C.get("spread") or {}).get("line") if any(x["spread"] for x in out) else None}


def research_targets(block, cond, now, c):
    """第 4 部: 聞かれた名所に「新しい」今年の現況が 1 件も無く、まだ調べていなければ、調べる対象。"""
    if not on(c, "research"):
        return []
    R = cfg(c)["research"]
    if cond.get("route") not in (R.get("routes") or []):
        return []
    label = "・".join((R.get("subject_words") or {}).get(s, s) for s in (cond.get("subjects") or [])) or None
    out = []
    for p in block["places"]:
        if p["fresh"] or p["searched"]:
            continue
        out.append({"what": label, "where": p["name"], "why": R["why"].format(where=p["name"]), "kind": "current_status",
                    "search_words": R["search_words"].format(where=p["name"], what=label or "", year=now.year).strip(),
                    "max_searches": _v(R["max_searches_per_place"]), "max_pages": _v(R["max_pages_per_place"])})
    return out


def missing_lines(block, c):
    L = cfg(c)["lines"]
    return [L["searched_none"].format(where=p["name"]) for p in block["places"] if (p.get("searched") or {}).get("found") is False]


# ---- 調べた印(第 4・6 部) ----

def _searched_path(env=None):
    from . import research as RS
    return RS.rdir(env) / "current_searched.jsonl"


def note_searched(bid, place, *, found, reason=None, env=None, now=None):
    from . import guide_brief as GB
    doc = GB.load(bid, env)
    from . import observations as O
    now = now or O.clock_now()
    row = {"at": now.isoformat(timespec="seconds"), "brief": bid, "question": doc.get("question"), "place": place,
           "found": bool(found), **({"reason": str(reason)[:80]} if reason else {})}
    p = _searched_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(row, ensure_ascii=False) + NL)
    return row


def _searched_rows(env=None):
    try:
        return [json.loads(l) for l in _searched_path(env).read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def searched_for(question, place, now, env=None, c=None):
    """同じ質問・同じ名所を research.once_hours の中に調べた印(最後のもの)。→ {at, found, reason?} か None。"""
    from . import guide_brief as GB
    hours = (c or GB.cfg())["research"]["once_hours"]
    hit = None
    for r in _searched_rows(env):
        if r.get("question") != question or r.get("place") != place:
            continue
        try:
            at = datetime.fromisoformat(r["at"])
        except (KeyError, ValueError):
            continue
        if timedelta(0) <= now - at <= timedelta(hours=hours) or (at > now and (at - now) <= timedelta(hours=hours)):
            hit = {"at": r["at"], "found": r.get("found"), **({"reason": r["reason"]} if r.get("reason") else {})}
    return hit


def searched_by_brief(bid, env=None):
    return {r.get("place") for r in _searched_rows(env) if r.get("brief") == bid}


# ---- 資料の Markdown ----

def md_lines(doc, fact_md, c=None):
    C = cfg(c)
    blk = doc.get("current_status") or {}
    places = [p for p in blk.get("places") or [] if p.get("current_parts") or p.get("unseen") or p.get("searched")]
    if not places:
        return []
    S = C["section"]
    L = C["lines"]
    fx = {f["id"]: f for f in doc.get("facts") or []}
    out = [S["heading"], "", S["lead"], ""]
    for p in places:
        out.append(f"### {p['name']}")
        for r in p["current_parts"]:
            if r.get("fact") in fx:
                out.append(fact_md(fx[r["fact"]]))
        for u in p.get("unseen") or []:
            out.append(L["unseen"].format(words=u["words"], date=_jp_md(u.get("date")) or L["no_date"], fact=u["fact"]))
        for g in p.get("spread") or []:
            ids = "・".join(g["facts"] + (g.get("user_facts") or []))
            out.append(L["spread_row"].format(part=g["part"] or L["whole"], ids=ids) + (L["whole_note"] if g.get("whole_vs_part") else ""))
        s = p.get("searched")
        if s:
            out.append(L["searched_found"].format(at=s["at"][:16]) if s.get("found") else L["searched_none_md"].format(at=s["at"][:16]))
        out.append("")
    if blk.get("spread_line"):
        out += [L["spread_lead"].format(line=blk["spread_line"]), ""]
    return out


def research_step_lines(bid, c=None):
    R = cfg(c)["research"]
    return [x.format(id=bid, searches=_v(R["max_searches_per_place"]), pages=_v(R["max_pages_per_place"])) for x in R["step_lines"]]


# ---- 照合(guide_verify から) ----

def verify_cfg(c, brief):
    """利用者の記録がある資料だけ、決まった言い方(「現地で確認した記録では」)を内部の言葉の照合から外す。ほかの資料は c のまま。"""
    C = cfg(c)
    blk = brief.get("current_status")
    if not C.get("enabled") or not isinstance(blk, dict):
        return c
    if not any(r.get("source_class") == "user" for p in blk.get("places") or [] for r in p.get("current_parts") or []):
        return c
    return {**c, "internal_word_allowed_phrases": list(c.get("internal_word_allowed_phrases") or []) + list((C.get("verify") or {}).get("allowed_phrases") or [])}


def _has(words, text):
    return any(w and w in text for w in words or [])


def current_status_errors(sents, body, brief, c, env=None, err=None):
    """第 2・3・5・6 部の照合。資料に current_status があるときだけ(古い資料・切った設定では何もしない)。"""
    C = cfg(c)
    blk = brief.get("current_status")
    if not C.get("enabled") or not isinstance(blk, dict):
        return []
    V = C.get("verify") or {}
    out = []
    fx = {f["id"]: f for f in brief.get("facts") or []}
    status_words = list(c.get("state_words") or []) + list(V.get("extra_state_words") or [])
    honest = list(c.get("honest_words") or []) + list(V.get("unseen_ok_words") or [])
    for p in blk.get("places") or []:
        parts = {r["fact"]: r for r in p.get("current_parts") or []}
        part_words = sorted({r["part"] for r in parts.values() if r.get("part")}, key=len, reverse=True)
        unseen_words = [u["words"] for u in p.get("unseen") or []]
        for s in sents:
            text = s["clean"]
            cited = [parts[i] for i in s["ids"] if i in parts]
            st = _has(status_words, text)
            # 第 2 部: ある場所の記録を、別の場所・名所全体の状態として書いた文
            for r in cited:
                if r.get("part") and st and r["part"] not in text:
                    out.append(err("part_widened", s, f"{r['part']}の記録({r['fact']})を、場所を書かずに状態として書いている",
                                   f"「{r['part']}では…」と場所を書く。名所全体や別の場所の状態にしない"))
            mention = [w for w in part_words if w in text]
            if mention and st and cited and not any(r.get("part") in mention for r in cited):
                out.append(err("part_mismatch", s, f"{'・'.join(mention)}の状態の根拠が、その場所の記録ではない",
                               f"{'・'.join(mention)}の記録の印を付ける(名所全体の表示・別の場所の記録で、その場所の状態を書かない)"))
            # 第 3 部: 利用者の記録は日付と「公式ではない」を同じ文に
            for r in cited:
                if r.get("source_class") == "user":
                    md = _md(r.get("state_date"))
                    jp = _jp_md(r.get("state_date"))
                    if not ((md and md in text) or (jp and jp in text)) or not _has(V.get("user_words"), text):
                        out.append(err("user_record_unlabeled", s, f"現地で確認した記録({r['fact']})に、日付か「公式の発表ではない」ことが無い",
                                       C["lines"]["user_fix"]))
            # 第 3 部: 見ていない所
            for w in unseen_words:
                if w in text and (st or _has(V.get("unseen_state_words"), text)) and not _has(honest, text):
                    backed = any(w in (fx.get(i, {}).get("content") or "") and fx.get(i, {}).get("source_class") != "user" for i in s["ids"])
                    if not backed:
                        out.append(err("unseen_place_state", s, f"「{w}」は現地で確認していない所",
                                       f"「{w}は確認していません」と書く(別の発信元の記録があれば、その印を付けて書く)"))
        # 第 5 部: ばらつきを隠した答え
        all_ids = [i for s in sents for i in s["ids"]]
        for g in p.get("spread") or []:
            if not any(i in all_ids for i in g["facts"]):
                continue
            left = [i for i in g["facts"] if i not in all_ids]
            if left or not _has(V.get("spread_words"), body):
                out.append(err("spread_hidden", None, f"{g['part'] or C['lines']['whole']}は発信元で状態にばらつきがある({'・'.join(g['facts'])})",
                               f"「{blk.get('spread_line') or ''}」を入れ、{'・'.join(left or g['facts'])}も発信元と日付を添えて並べる"))
    # 第 6 部: 手順を飛ばした答え
    if on(c, "steps"):
        bid = brief.get("id")
        done = searched_by_brief(bid, env) if bid else set()
        for t in (brief.get("research") or {}).get("targets") or []:
            if t.get("kind") == "current_status" and t.get("where") not in done:
                out.append(err("current_research_skipped", None, f"「{t['where']}」の今年の現況を調べる対象があるのに、調べた印が無い",
                               C["lines"]["skipped_fix"].format(id=bid, where=t["where"])))
        names = {n for p in blk.get("places") or [] for n in [p["name"], *(p.get("candidates") or [])]}
        recorded = _recorded_urls(brief, env)
        for pg in (brief.get("auto_refresh") or {}).get("pages") or []:
            if pg.get("result") == "changed" and pg.get("name") in names and pg.get("url") not in recorded:
                pl = next((p["name"] for p in blk.get("places") or [] if pg["name"] in [p["name"], *(p.get("candidates") or [])]), pg["name"])
                if pl in done:
                    continue
                out.append(err("refresh_not_recorded", None, f"「{pg['name']}」のページが読み直しで変わっているのに、記録が無い",
                               C["lines"]["refresh_fix"].format(id=bid, where=pl)))
    return out


def _recorded_urls(brief, env=None):
    """資料を作った時刻より後に記録した URL(読み直したページを記録したか)。"""
    from . import observations as O
    try:
        t0 = datetime.fromisoformat(brief.get("now"))
    except (TypeError, ValueError):
        return set()
    out = set()
    pol = O.load_policy()
    for sj in pol["subjects"]:
        for r in O.read_records(sj, env, pol, include_detail=True):
            try:
                if datetime.fromisoformat(r["read_at"]) >= t0 and r.get("url"):
                    out.add(r["url"])
            except (KeyError, ValueError):
                continue
    return out
