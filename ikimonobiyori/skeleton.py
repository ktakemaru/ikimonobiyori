"""計画から答えの骨組みを組み立てる(段階58 第9部)。通信しない。事実は facts の値だけで、決まり文・出典もここで入れる。

書き手(エージェント)は、この骨組みの文を、事実を足さず変えずに自然な日本語へ整えるだけでよい。事実の追加・差し替えは ask plan --override を通す。
骨組みそのものが検査に通ることを目標にする(初回の不合格 0 件)。文はすべて data/ask/plan.yaml の skeleton。"""
import re
from datetime import date

from . import answer_plan as AP
from . import knowledge as K
from . import official_pages as OP
from .ask_verify import load_rules, source_map

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


def _stale_display(cur, today):
    """古い表示が残ることのある発行元の状態は、今日から見て日付が離れていれば参考として書く(段階52 の規則を、同じ名所の別の記録にも当てる)。"""
    cfg_ = load_rules()["stage51"]["stale_display"]
    if not today or not cur.get("state_date") or not any(p in (cur.get("publisher") or "") for p in cfg_["publishers"]["value"]):
        return False
    return (today - date.fromisoformat(str(cur["state_date"])[:10])).days >= cfg_["min_gap_days"]["value"]


def current_line(c, t, phr, today=None, sj=None):
    """今の状況の文。第三者サイトの現況は採用理由にせず参考の 1 行にとどめる。記号だけで読めないものは断定しない。
    段階63a: まつりのある候補の「色づき状況は確認できていません」は紅葉だけ(花・野鳥に「色づき」を書かない。段階58 第10部の対象別の定型文)。"""
    cur = c.get("current")
    if not AP.has_state_record(c) or not (cur.get("display") or cur.get("state_raw")):
        return t["no_current_fest"] if c.get("festivals") and sj in (None, "autumn_leaves") else t["no_current"]
    state = cur.get("display") or cur["state_raw"]
    state = re.sub(r"[。\s]+$", "", state)
    when = _md(cur["state_date"]) if cur.get("state_date") else None
    who = cur.get("publisher") or ""
    if cur.get("source_class") == "secondary":
        return t["secondary"].format(state=state, md=when or "", publisher=who) if when else t["secondary_nodate"].format(state=state, publisher=who)
    if (cur.get("reference_only") or _stale_display(cur, today)) and when:
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


def pick_block(p, i, c, sj, t, max_quote, today=None):
    """段階64 第7部 2(本人の判断 2026-11-08): 1 行目に名所名と距離、その下に箇条で事実(今の状況・例年の時期・見込み・行事・行く前の注意)。1 つの箇条に 1 つの事実。"""
    head = f"{CIRCLED[i]} {p['name']}"
    if c.get("city"):
        head += f"({c['city']})"
    if p.get("distance_text"):
        head += f" {p['distance_text']}"
    bits = [current_line(c, t, p, today, sj)]
    if p.get("old_record_note"):                                     # 段階62 第3部: 対象日の数日前の記録
        bits.append(p["old_record_note"])
    bits.append(season_text(c, sj, t, max_quote))
    if p.get("phrase"):
        bits.append(p["phrase"])
    if p.get("note") and p["note"] not in " ".join(bits) and "確認できていません" not in bits[0]:
        bits.append(p["note"])
    lines = [head] + [f"・{x.rstrip('。')}" for x in bits if x]
    for e in c.get("closed_on") or []:
        if e.get("closed") and e.get("line"):
            lines.append(f"・{e['line']}")
    for f in c.get("festivals") or []:
        if f.get("period_line"):
            lines.append(f"・{f['period_line']}")
    if c.get("practical"):
        lines.append(f"・{c['practical'][0]['text']}")
    if today and sj != "birds":
        tw = AP.target_week_line(c, today)
        if tw:
            lines.append(f"・{tw}")
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


def _subject_part(facts_subject, pl, sj, t, max_quote, urls, mentioned, today=None):
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
                out += pick_block(by_name[n], len(used) - 1, c, sj, t, max_quote, today)
                urls |= _used_urls(c, sj)
                mentioned.append(c)
    for p in picks:
        if p["name"] in used:
            continue
        used.append(p["name"])
        c = cands.get(p["name"]) or {"name": p["name"]}
        out += pick_block(p, len(used) - 1, c, sj, t, max_quote, today)
        urls |= _used_urls(c, sj)
        mentioned.append(c)
    if pl.get("fill_skipped") and picks:                                 # 段階64 第1部: 遠い候補で埋めなかったときは、件数の決まり文(段階58)
        out.append(t["few"].format(n=len(picks)))
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
        out = []
        for s in plan["segments"]:
            out += _flat_picks(s["plan"]) if s["plan"].get("subject") == "areas" else s["plan"]["picks"]
        return out
    return list(plan.get("picks") or [])


def _no_this_year(plan, facts, t, max_quote):
    """別枠「今年の情報が確認できていない候補」(事実だけを 1 行ずつ)。"""
    rows = list(plan.get("no_this_year") or [])
    for s in plan.get("segments") or []:
        rows += (s.get("plan") or (plan.get("subjects") or {}).get(s.get("subject")) or {}).get("no_this_year") or []
    ty = AP.load_policy()["this_year"]
    out, seen = [], set()
    for r in rows:
        if r["name"] in seen:
            continue
        seen.add(r["name"])
        typ = _no_long_quote(r.get("typical_line") or "", max_quote)
        known = typ and not typ.startswith(t["typical_unknown"])
        out.append("・" + (ty["line"].format(name=r["name"], typical=typ) if known else ty["line_no_typical"].format(name=r["name"])))
    return out[: ty["max_lines"]]


def vc_lines(facts, mentioned, t, prefectures=()):
    """facts の visitor_centers(承認済み・季節内・14日以内。コードが選んだもの)のうち、答えに出た名所の地域に当たる施設だけ。
    施設 → 地域の語は方針 skeleton.visitor_center_places(名所の名前・市区町村・地域のどれかに語が含まれれば当たり)。
    段階65 第6部 1: 質問で都県・エリアを指定したとき(prefectures)は、その都県の承認済みの施設の発信も出す。"""
    places = t.get("visitor_center_places") or {}
    words = " ".join(str(c.get(k) or "") for c in mentioned for k in ("name", "city", "area"))
    pref_of = {}
    if prefectures:
        from . import visitor_centers as VC
        pref_of = {c["id"]: c.get("prefecture") for c in VC.load_centers()}
    return [r for r in facts.get("visitor_centers") or [] if any(w in words for w in places.get(r.get("center")) or [])
            or (prefectures and pref_of.get(r.get("center")) in prefectures)]


def avoid_lines(facts, t):
    """段階65 第6部 2: 公式の現況が見頃過ぎの名所(facts の avoid)→ [(行, URL)]。状態は原文(記号は凡例の語に)と日付。"""
    from . import observations as O
    opol = O.load_policy()
    out, seen = [], set()
    for sub in (facts.get("subjects") or {}).values():
        for c in sub.get("avoid") or []:
            cur = c.get("current") or {}
            raw, sd = cur.get("state_raw") or cur.get("state"), cur.get("state_date")
            if not raw or not sd or cur.get("source_class") != "official" or c["name"] in seen:
                continue
            disp, sym_only = O.state_display(raw, cur.get("publisher"), opol)
            if sym_only or not disp:
                continue
            seen.add(c["name"])
            out.append((t["avoid_line"].format(name=c["name"], state=disp.strip(), md=_md(sd), publisher=cur.get("publisher") or ""), cur.get("url")))
    return out[: t["avoid_max_lines"]]


def asked_prefectures(facts):
    """段階65 第6部 1: 質問で地域を指定したとき(既定の全範囲でないとき)、その地域の候補の都県。指定がなければ空。"""
    from . import ask
    reg = facts.get("region")
    if not reg or reg == ask.load_policy().get("default_region"):
        return set()
    return {c.get("prefecture") for sub in (facts.get("subjects") or {}).values() for c in sub.get("candidates") or [] if c.get("prefecture")}


def compose(facts, plan, offers=(), defaulted_date=False, extra_lines=(), cards=None, places=(), env=None):
    """facts.json と計画 → 骨組みの答え(文字列)。cards: 知識カード(省くとデータ置き場)。places: 質問の場所の語(ガイドの目の選び方に足す)。"""
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
    for rp in plan.get("region_parts") or []:                          # 段階62 第2部: 地域ごとの行(候補がない地域も書く)
        lines.append(t["region_part"].format(name=rp["name"], names=t["region_names_sep"].join(rp["picks"])) if rp["picks"]
                     else t["region_part_few"].format(name=rp["name"], n=0))
    urls, mentioned = set(), []
    segs = plan.get("segments") or []
    today = date.fromisoformat(str(facts.get("now"))[:10]) if facts.get("now") else None
    if plan.get("subject") == "areas":                                 # エリア別(段階58)。候補のないエリアも 1 行書く
        sj = plan["area_subject"]
        for line in plan.get("area_unknown") or []:
            lines.append(line)
        for s in segs:
            pl = s["plan"]
            lines += ["", s["heading"]]
            if pl["picks"]:
                lines.append(lead_for(pl["picks"], t))
                lines += _subject_part(facts["subjects"][sj], pl, sj, t, max_quote, urls, mentioned, today)
            else:
                lines.append(t["area_none"].format(name=s["heading"]))
    elif segs and segs[0].get("plan"):                                 # 期間別
        for s, per in zip(segs, facts.get("periods") or []):
            pl = s["plan"]
            sj = pl.get("subject")
            lines += ["", s["heading"]]
            if sj == "areas":
                sj2 = pl["area_subject"]
                for x in pl["segments"]:
                    lines += ["", x["heading"]]
                    if x["plan"]["picks"]:
                        lines.append(lead_for(x["plan"]["picks"], t))
                        lines += _subject_part(per["subjects"][sj2], x["plan"], sj2, t, max_quote, urls, mentioned, today)
                    else:
                        lines.append(t["area_none"].format(name=x["heading"]))
                continue
            lines.append(lead_for(pl.get("picks") or [], t))
            if sj == "all":
                for ss in pl["segments"]:
                    lines += _subject_part(per["subjects"][ss["subject"]], pl["subjects"][ss["subject"]], ss["subject"], t, max_quote, urls, mentioned, today)
            else:
                lines += _subject_part(per["subjects"][sj], pl, sj, t, max_quote, urls, mentioned, today)
    elif segs:                                                         # 対象別
        for s in segs:
            pl = plan["subjects"][s["subject"]]
            lines += ["", s["heading"], lead_for(pl.get("picks") or [], t)]
            lines += _subject_part(facts["subjects"][s["subject"]], pl, s["subject"], t, max_quote, urls, mentioned, today)
    else:
        lines.append("")
        lines += _subject_part(facts["subjects"][plan["subject"]], plan, plan["subject"], t, max_quote, urls, mentioned, today)
    if len(flat) < load_rules()["min_candidates"]:
        lines += ["", t["few"].format(n=len(flat))]
    from . import jma_normals as JN                                    # 段階61 第1部: 街の標本木の平年の目安(気象庁の観測値をもとに計算。山地の見頃とは別)
    jn, jn_src = JN.skeleton_lines(list((facts.get("subjects") or {}).keys()), facts.get("origin"))
    if jn:
        lines += [""] + jn
    ny = _no_this_year(plan, facts, t, max_quote)
    if ny:
        lines += ["", t["no_this_year_heading"]] + ny
    av = avoid_lines(facts, t) if asked_prefectures(facts) else []
    if av:
        lines += ["", t["avoid_heading"]] + [x[0] for x in av]
        urls |= {x[1] for x in av if x[1]}
    notices = OP.notice_lines(mentioned)
    month = int(str(facts["dates"][0])[5:7]) if facts.get("dates") else None
    prefs = asked_prefectures(facts)
    names = list(places) + [c.get("name") for c in mentioned if c.get("name")] + [c.get("city") for c in mentioned if c.get("city")]
    if prefs:                                                          # 段階65 第6部 1: 地域を指定した質問は、名所のエリアの語でもガイドの目を選ぶ
        names += [c.get("area") for c in mentioned if c.get("area")]
    chosen = K.select(names, month=month, cards=cards, env=env)
    eye, before_k, card_urls = K.split_lines(chosen)
    vc = vc_lines(facts, mentioned, t, prefs)                                # 段階60 第8部: 質問の場所の承認済み施設の発信(段階55 の 1 行)
    if vc:
        lines += [""] + [x for row in vc for x in ([" ".join(row["sentences"])] if row.get("sentences") else [row["line"]]) + [row.get("hours_line")] if x]     # 段階62 第5部: 状態と種名は別の文
        urls |= {row["url"] for row in vc if row.get("url")}
    if eye:
        lines += [""] + eye
    if notices or before_k:
        lines += ["", t["before_heading"]] + list(dict.fromkeys([n["line"] for n in notices] + before_k))   # 期間別で同じ名所が 2 回出ても 1 行
        urls |= {n["url"] for n in notices if n.get("url")}
    urls |= set(card_urls)
    conf = []
    if not any(c.get("practical") for c in mentioned):
        conf.append(load_rules()["stage51"]["practical_fallback"] + "。")
    if any((c.get("current") or {}).get("source_class") == "secondary" for c in mentioned):
        conf.append(t["secondary_note"])
    taken = sorted({str(f["taken_on"])[:10] for c in mentioned for f in c.get("festivals") or [] if f.get("taken_on") and f.get("period_line")})
    if taken and today and t.get("festival_checked"):                   # 段階63a 第9部: まつり・行事の期間を確かめた日(いちばん古いもの)
        d0 = date.fromisoformat(taken[0])
        age = (today - d0).days
        conf.append((t["festival_checked"] if age <= t["festival_checked_max_days"] else t["festival_checked_old"]).format(md=_md(taken[0]), days=age))
    if conf:
        lines += ["", t["confidence_heading"]] + conf
    opener = (facts.get("lines") or {}).get("open_urls")
    # 段階63a(衝突1): 出典は「本文の事実 → 出典」の対応表(検査器と同じ source_map)から決める。本文に出た候補の今の状態のページは足し、
    # 対応表にない URL(今年の情報が確認できていない候補の欄に名前だけ出た候補の現況のページなど)は載せない
    m = source_map("\n".join(lines) + "\n", facts, plan)
    urls = {u for u in urls if u.rstrip("/") in m["allowed"]}
    have = {u.rstrip("/") for u in urls}
    urls |= {u for u in m["required"] if u not in have}
    if urls or jn_src:
        lines += ["", t["sources_heading"]] + ([jn_src] if jn_src else []) + sorted(urls)
    if opener:
        lines += ["", opener]
    for o in offers or []:
        lines += ["", o]
    return "\n".join(lines) + "\n"
