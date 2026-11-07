"""計画から答えの骨組みを組み立てる(段階58 第9部)。通信しない。事実は facts の値だけで、決まり文・出典もここで入れる。

書き手(エージェント)は、この骨組みの文を、事実を足さず変えずに自然な日本語へ整えるだけでよい。事実の追加・差し替えは ask plan --override を通す。
骨組みそのものが検査に通ることを目標にする(初回の不合格 0 件)。文はすべて data/ask/plan.yaml の skeleton。"""
import re
from datetime import date

from . import answer_plan as AP
from .ask_verify import candidate_urls, load_rules

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def _md(iso):
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.month}/{d.day}"


def cfg():
    return AP.load_policy()["skeleton"]


def _no_long_quote(line, max_chars):
    """「」の中が長い原文は書かない(丸ごとの転載を避ける。事実は年などの残りの部分で示す)。"""
    def rep(m):
        return m.group(0) if len(m.group(1)) <= max_chars else ""
    return re.sub(r"(?:では)?「([^」]+)」", rep, line).replace("()", "")


def current_line(c, t, phr):
    """今の状況の文。第三者サイトの現況は採用理由にせず参考の 1 行にとどめる。記号だけで読めないものは断定しない。"""
    cur = c.get("current")
    if not AP.has_current(c) or not (cur.get("display") or cur.get("state_raw")):
        return t["no_current_fest"] if c.get("festivals") else t["no_current"]
    state = cur.get("display") or cur["state_raw"]
    state = re.sub(r"[。\s]+$", "", state)
    when = _md(cur["state_date"]) if cur.get("state_date") else None
    who = cur.get("publisher") or ""
    if cur.get("source_class") == "secondary":
        return t["secondary"].format(state=state, md=when or "", publisher=who) if when else t["secondary_nodate"].format(state=state, publisher=who)
    if cur.get("reference_only") and when:
        return t["reference"].format(state=state, md=when, publisher=who)
    return t["current"].format(state=state, md=when, publisher=who) if when else t["current_nodate"].format(state=state, publisher=who)


def season_text(c, sj, t, max_quote):
    if sj == "birds":
        recent = [b["name"] for b in c.get("park_birds") or [] if b.get("kind") == "recent"][: t["max_birds"]]
        if recent:
            return t["birds"].format(names="・".join(recent))
        line = c.get("season_line") or t["birds_unknown"]
        if "iNaturalist" in line and t["not_official"] not in line:
            line = line.rstrip("。") + "(" + t["not_official"] + "。" + t["inat_scope"] + ")"
        return _no_long_quote(line, max_quote)
    return _no_long_quote(c.get("typical_line") or t["typical_unknown"], max_quote)


def pick_block(p, i, c, sj, t, max_quote):
    head = f"{CIRCLED[i]} {p['name']}"
    if c.get("city"):
        head += f"({c['city']})"
    if p.get("distance_text"):
        head += f" {p['distance_text']}"
    bits = [current_line(c, t, p)]
    bits.append(season_text(c, sj, t, max_quote))
    if p.get("phrase"):
        bits.append(p["phrase"])
    if p.get("note") and p["note"] not in " ".join(bits) and "確認できていません" not in bits[0]:
        bits.append(p["note"])
    body = "。".join(x.rstrip("。") for x in bits if x) + "。"
    lines = [f"{head}: {body}"]
    for e in c.get("closed_on") or []:
        if e.get("closed") and e.get("line"):
            lines.append(f"・{e['line']}")
    for f in c.get("festivals") or []:
        if f.get("period_line"):
            lines.append(f"・{f['period_line']}")
    if c.get("practical"):
        lines.append(f"・{c['practical'][0]['text']}")
    return lines


def _used_urls(c, sj):
    """本文に出た候補の事実の出どころ。"""
    out = set()
    cur = c.get("current")
    if cur and cur.get("url"):
        out.add(cur["url"])
    for t in c.get("typical") or []:
        if t.get("url") and (c.get("typical_line") or "") and (t.get("text") or "") in (c.get("typical_line") or ""):
            out.add(t["url"])
    for k in ("practical", "festivals"):
        for x in (c.get(k) or [])[:1 if k == "practical" else None]:
            if x.get("url"):
                out.add(x["url"])
    if sj == "birds":
        recent = [b for b in c.get("park_birds") or [] if b.get("kind") == "recent"]
        for b in recent:
            if b.get("url") and "inaturalist" not in b["url"]:
                out.add(b["url"])
        inat = c.get("inat") or {}
        if not recent and "iNaturalist" in (c.get("season_line") or ""):
            u = inat.get("source_url") or inat.get("site_url")
            if u:
                out.add(u)
    return out


def _subject_part(facts_subject, pl, sj, t, max_quote, urls, mentioned):
    cands = {c["name"]: c for c in facts_subject.get("candidates") or []}
    out = [t["picks_heading"]]
    picks = pl.get("picks") or []
    by_name = {p["name"]: p for p in picks}
    used = []
    if pl.get("use_headings"):
        for s in pl.get("sections") or []:
            names = [it["name"] for it in s["items"] if it["name"] in by_name]
            if not names:
                continue
            out.append(s["label"])
            for n in names:
                used.append(n)
                c = cands.get(n) or {"name": n}
                out += pick_block(by_name[n], len(used) - 1, c, sj, t, max_quote)
                urls |= _used_urls(c, sj)
                mentioned.append(c)
    for p in picks:
        if p["name"] in used:
            continue
        used.append(p["name"])
        c = cands.get(p["name"]) or {"name": p["name"]}
        out += pick_block(p, len(used) - 1, c, sj, t, max_quote)
        urls |= _used_urls(c, sj)
        mentioned.append(c)
    return out


def lead_for(picks_flat, t):
    """冒頭の文(いちばん弱い確かさに合わせる)。"""
    if not picks_flat:
        return t["lead_none"]
    if not any(p.get("has_current") for p in picks_flat):
        return t["lead_no_current"]
    if any(not p.get("has_current") for p in picks_flat):
        return t["lead_mixed"]
    if any(p.get("outlook") in ("toward", "unknown", "early", "late") for p in picks_flat):
        return t["lead_toward"]
    return t["lead_ok"]


def dates_line(facts, t, defaulted=False):
    ds = facts.get("dates") or []
    if not ds:
        return None
    days = "・".join(_md(x) for x in ds)
    return t["dates_default"].format(days=days) if defaulted else t["dates"].format(days=days)


def _flat_picks(plan):
    if plan.get("segments") and plan["segments"][0].get("plan"):
        return [p for s in plan["segments"] for p in s["plan"]["picks"]]
    return list(plan.get("picks") or [])


def compose(facts, plan, offers=(), defaulted_date=False, extra_lines=()):
    """facts.json と計画 → 骨組みの答え(文字列)。"""
    t = cfg()
    max_quote = load_rules()["stage51"]["max_quote_chars"]
    max_quote = max_quote["value"] if isinstance(max_quote, dict) else max_quote
    lines = []
    flat = _flat_picks(plan)
    lines.append(lead_for(flat, t))
    d = dates_line(facts, t, defaulted_date)
    if d:
        lines.append(d)
    ol = (facts.get("lines") or {}).get("origin_line")
    if ol:
        lines.append(ol)
    lines += list(extra_lines)
    urls, mentioned = set(), []
    segs = plan.get("segments") or []
    if plan.get("subject") == "areas":                                 # エリア別(段階58)。候補のないエリアも 1 行書く
        sj = plan["area_subject"]
        for line in plan.get("area_unknown") or []:
            lines.append(line)
        for s in segs:
            pl = s["plan"]
            lines += ["", s["heading"]]
            if pl["picks"]:
                lines.append(lead_for(pl["picks"], t))
                lines += _subject_part(facts["subjects"][sj], pl, sj, t, max_quote, urls, mentioned)
            else:
                lines.append(t["area_none"].format(name=s["heading"]))
    elif segs and segs[0].get("plan"):                                 # 期間別
        for s, per in zip(segs, facts.get("periods") or []):
            pl = s["plan"]
            sj = pl.get("subject")
            lines += ["", s["heading"], lead_for(pl.get("picks") or [], t)]
            if sj == "all":
                for ss in pl["segments"]:
                    lines += _subject_part(per["subjects"][ss["subject"]], pl["subjects"][ss["subject"]], ss["subject"], t, max_quote, urls, mentioned)
            else:
                lines += _subject_part(per["subjects"][sj], pl, sj, t, max_quote, urls, mentioned)
    elif segs:                                                         # 対象別
        for s in segs:
            pl = plan["subjects"][s["subject"]]
            lines += ["", s["heading"], lead_for(pl.get("picks") or [], t)]
            lines += _subject_part(facts["subjects"][s["subject"]], pl, s["subject"], t, max_quote, urls, mentioned)
    else:
        lines.append("")
        lines += _subject_part(facts["subjects"][plan["subject"]], plan, plan["subject"], t, max_quote, urls, mentioned)
    if len(flat) < load_rules()["min_candidates"]:
        lines += ["", t["few"].format(n=len(flat))]
    conf = []
    if not any(c.get("practical") for c in mentioned):
        conf.append(load_rules()["stage51"]["practical_fallback"] + "。")
    if any((c.get("current") or {}).get("source_class") == "secondary" for c in mentioned):
        conf.append(t["secondary_note"])
    if conf:
        lines += ["", t["confidence_heading"]] + conf
    opener = (facts.get("lines") or {}).get("open_urls")
    if urls:
        lines += ["", t["sources_heading"]] + sorted(urls)
    if opener:
        lines += ["", opener]
    for o in offers or []:
        lines += ["", o]
    return "\n".join(lines) + "\n"
