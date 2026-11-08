"""一発コマンド `ask answer`(段階63a 第1部。段階63 第2部の作り直し)。通信しない。

質問の文 → 意図・対象・地域・出発地・日付を決め、記録から材料(facts)・計画・骨組みを作り、検査とフォールバックを通して、
**必ず空でない答えの本文**を返す。状態は PASS(必須の検査に合格)/ DEGRADED(一部の候補・主張を外した、未確認を明記した)/
BLOCKED(危険な案内を外した)。

フォールバックの順(上から試し、最初に出せたものを答えにする。data/ask/plan.yaml の answer_run):
  1 整えた文章(書き手が整えた文章を渡したときだけ。骨組みとの事実の一致と、必須の検査に合格)
  2 コードが作った骨組みの文章
  3 部分回答(問題のある候補・主張を外した骨組み)
  4 最低限の答え(確認できた範囲・確認できなかったこと・確認の方法。事実は facts の値だけ)
事実(日付・数値・場所名・出典)はコードが作り、コードが照合する。フォールバックでも一般知識から事実を作らない。
読み直しが要るページ(有効期間を過ぎた現況のページ。最大 3)は答えの本文には書かず、結果の refresh_pages に出す(読むのはエージェントの道具)。"""
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import answer_plan as AP
from . import ask_verify as V
from . import offers as OF
from . import origins
from . import sources as S
from .paths import data_path

STATUS_PASS, STATUS_DEGRADED, STATUS_BLOCKED = "PASS", "DEGRADED", "BLOCKED"
STAGES = {1: "polished", 2: "skeleton", 3: "partial", 4: "minimal"}


def cfg(policy=None):
    return (policy or AP.load_policy())["answer_run"]


# ---- 質問の文 → 条件 ----

def _weekend_of(d):
    sat = d + timedelta(days=(5 - d.weekday()) % 7)
    return [sat, sat + timedelta(days=1)]


def resolve_dates(question, now):
    """質問の文 → (期間の一覧 [[date, ...], ...], 日付の指定がなかったか)。期間が 2 つの質問(「今週末と来週末」)は 2 つ。"""
    q = question or ""
    today = now.date()
    wk1 = S.next_weekend(now)
    wk2 = [wk1[-1] + timedelta(days=6), wk1[-1] + timedelta(days=7)]
    if "今週末" in q and "来週末" in q:
        return [wk1, wk2], False
    for word, ds in (("明後日", [today + timedelta(days=2)]), ("明日", [today + timedelta(days=1)]), ("今日", [today]),
                     ("来週末", wk2), ("今週末", wk1), ("来週", _weekend_of(today + timedelta(days=7))), ("週末", wk1), ("今週", wk1)):
        if word in q:
            return [ds], False
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", q)
    md = re.search(r"(?<!\d)(\d{1,2})\s*(?:/|月)\s*(\d{1,2})\s*日?", q)
    if m or md:
        y, mo, d = (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (today.year, int(md.group(1)), int(md.group(2)))
        try:
            got = date(y, mo, d)
        except ValueError:
            got = None
        if got is not None:
            if not m and got < today - timedelta(days=60):          # 年のない日付は、近い先の日
                got = date(y + 1, mo, d)
            return [[got]], False
    dp = AP.default_periods(q, now)
    return (dp["periods"] or [wk1]), True


def _theme_words():
    from . import guide
    pol = guide.load_policy()
    return pol["words"], (pol.get("wildflower") or {}).get("words") or []


def resolve_topics(question, policy=None):
    """質問の文 → (ask の対象の一覧, ガイド型のテーマの語, 野草の質問か)。語はガイドの言葉の表から(長い語から)。"""
    c = cfg(policy)
    words, wild = _theme_words()
    q = question or ""
    if any(w in q for w in wild):
        return [], None, True
    subjects, guide_word = [], None
    rest = q
    for w in sorted(words, key=len, reverse=True):
        if w not in rest:
            continue
        rest = rest.replace(w, " ")
        v = words[w]
        themes = (v.get("themes") if isinstance(v, dict) else v) or []
        for t in themes:
            sj = c["subject_by_theme"].get(t)
            if sj and sj not in subjects:
                subjects.append(sj)
            if t in c["guide_only_themes"] and guide_word is None:
                guide_word = w
    order = ["autumn_leaves", "flowers", "birds"]
    return sorted(subjects, key=order.index), guide_word, False


def resolve_region(question):
    """質問の文 → 地域の呼び名(地域の辞書 data/regions.yaml の名前・別名。複数は「か」で 1 つの地域)。出発地(「○○から」)の語は除く。"""
    q = question or ""
    hits = []
    taken = []
    names = []
    for r in S.load_regions()["regions"]:
        names += [(n, r["name"]) for n in [r["name"], *(r.get("aliases") or [])]]
    for n, name in sorted(names, key=lambda x: -len(x[0])):
        for m in re.finditer(re.escape(n), q):
            span = (m.start(), m.end())
            if any(a < span[1] and span[0] < b for a, b in taken):
                continue
            if re.match(r"\s*(駅)?(から|発)", q[span[1]:]):                  # 出発地
                continue
            taken.append(span)
            if name not in [h[1] for h in hits]:
                hits.append((span[0], name, n))
    hits.sort()
    if not hits:
        return None
    return "か".join(h[2] for h in hits) if len(hits) > 1 else hits[0][2]


def resolve_refine(question, policy=None):
    words = (policy or AP.load_policy())["refine"]["words"]
    return next((k for k in sorted(words, key=len, reverse=True) if k in (question or "")), None)


def resolve(question, now, policy=None):
    """質問の文 → 答えの条件(経路・対象・地域・出発地・期間など)。"""
    from . import areas as AR
    from . import intent
    kind = intent.classify(question)
    subjects, guide_word, wild = resolve_topics(question, policy)
    periods, defaulted = resolve_dates(question, now)
    origin = origins.choose(question)
    area_names = [n for n in AR.from_question(question) if AR.resolve(n)]
    region = None if area_names else resolve_region(question)
    c = cfg(policy)
    q = question or ""
    if kind == "knowledge" and not any(w in q for w in c["knowledge_words"]) and             (region or area_names or not defaulted or any(w in q for w in c["plan_words"])):
        kind = "plan"                                    # 「神奈川と東京で紅葉の見ごろを教えて」は場所・時期の質問
    if wild and kind != "event":                         # 野草・高山植物の語は、知識の言い方(「教えて」)でも野草の経路(段階40)
        route = "wildflower"
    elif kind in ("knowledge", "difference", "chat", "normal", "event"):
        route = kind
    elif guide_word and not subjects:
        route = "guide"
    else:
        route = "plan"
    return {"question": question, "intent": kind, "route": route, "subjects": subjects or list(_default_subjects()), "guide_word": guide_word,
            "region": region, "area_names": area_names, "origin": origin["origin"], "origin_source": origin["source"],
            "periods": [[d.isoformat() for d in ds] for ds in periods], "defaulted_date": defaulted, "refine": resolve_refine(question, policy)}


def _default_subjects():
    from . import ask
    return ask.load_policy()["default_subjects"]


# ---- 最低限の答え(段 4) ----

def _days(dates):
    return "・".join(f"{date.fromisoformat(str(x)[:10]).month}/{date.fromisoformat(str(x)[:10]).day}" for x in dates)


def minimal_answer(facts_doc, plan_doc=None, policy=None):
    """確認できた範囲・確認できなかったこと・確認の方法(事実は facts の値だけ。出典はその行の事実から)。必ず空でない。"""
    from . import skeleton as SK
    pol = policy or AP.load_policy()
    m = cfg(pol)["minimal"]
    t = pol["skeleton"]
    days = _days(facts_doc.get("dates") or [])
    by = {}
    for sj, sub in (facts_doc.get("subjects") or {}).items():
        for c in sub.get("candidates") or []:
            by.setdefault(c["name"], (sj, c))
    names = [p["name"] for p in SK._flat_picks(plan_doc or {})] if plan_doc else []
    if not names:                                                   # 計画がない: 今の状態の記録がある候補から(距離の近い順)
        rows = sorted((v for v in by.values() if AP.has_state_record(v[1])), key=lambda v: v[1].get("distance_km") or 9999)
        names = [v[1]["name"] for v in rows]
    seen, shown, unknown, urls = set(), [], [], []
    today = date.fromisoformat(str(facts_doc.get("now"))[:10]) if facts_doc.get("now") else None
    for n in names:
        if n in seen or n not in by or len(shown) >= m["max_items"]:
            continue
        seen.add(n)
        sj, c = by[n]
        if AP.has_state_record(c):
            shown.append(m["item"].format(name=n, state=SK.current_line(c, t, {}, today).rstrip("。")))
            u = (c.get("current") or {}).get("url")
            if u and u not in urls:
                urls.append(u)
        else:
            unknown.append(n)
    lines = [m["lead"].format(days=days) if shown else m["lead_none"].format(days=days)]
    ol = (facts_doc.get("lines") or {}).get("origin_line")
    if ol and shown:
        lines.append(ol)
    if shown:
        lines += [""] + shown
    if unknown:
        lines += ["", m["unknown_heading"], m["unknown_line"].format(names="、".join(unknown))]
    lines += ["", m["how_heading"], m["how_line"]]
    if urls:
        lines += ["", t["sources_heading"]] + urls
    return "\n".join(lines) + "\n"


# ---- 検査(段階63a 第2部) ----

def gate_check(text, facts_doc, plan_doc, gaz, offers=None):
    """段階63a 第2部: 自動修正 → 必須の 4 つの検査(answer_gates.py・data/ask/answer_contract.json)。
    → {ok, text(自動修正した文), errors(4つの検査の不合格。gate つき), warnings, fixed}"""
    from . import answer_gates as AG
    r = AG.run(text, facts_doc, plan_doc, gaz, offers)
    return {"ok": r["ok"], "text": r["text"], "errors": AG.errors_of(r), "warnings": r["warnings"], "fixed": r["fixed"]}


def fit_length(facts_doc, plan_doc, offers, defaulted, max_drop=None):
    """骨組みが字数の上限(答えの仕様の length)を超えたら、点数の低い候補から減らして作り直す。→ (骨組み, 計画, 外した候補)"""
    from . import answer_gates as AG
    from . import skeleton as SK
    text = SK.compose(facts_doc, plan_doc, offers, defaulted_date=defaulted)
    dropped = []
    while len(text) > AG.length_limit(plan_doc, text):
        picks = SK._flat_picks(plan_doc)
        if len(picks) <= 1 or (max_drop is not None and len(dropped) >= max_drop):
            break
        worst = min(picks, key=lambda x: (x.get("score") is None, x.get("score") or 0, -(x.get("rank") or 0)))
        dropped.append(worst["name"])
        plan_doc = drop_picks(plan_doc, {worst["name"]})
        text = SK.compose(facts_doc, plan_doc, offers, defaulted_date=defaulted)
    return text, plan_doc, dropped


def _candidates_with_errors(text, facts_doc, plan_doc, errs):
    """誤りの行・詳細に名前が出る、今回のおすすめの候補。"""
    from . import skeleton as SK
    lines = text.splitlines()
    names = [p["name"] for p in SK._flat_picks(plan_doc)]
    bad = set()
    for e in errs:
        where = (lines[e["line"]] if isinstance(e.get("line"), int) and e["line"] < len(lines) else "") + " " + (e.get("detail") or "")
        for n in names:
            if any(f in V._n(where) for f in V.short_names(n)):
                bad.add(n)
    return bad


def drop_picks(plan_doc, names):
    """計画から、外す候補を除く(節・期間・エリアの中も)。→ 新しい計画。"""
    plan = json.loads(json.dumps(plan_doc, ensure_ascii=False))

    def walk(p):
        if not isinstance(p, dict):
            return
        if "picks" in p:
            p["picks"] = [x for x in p.get("picks") or [] if x.get("name") not in names]
        for s in p.get("sections") or []:
            s["items"] = [x for x in s.get("items") or [] if x.get("name") not in names]
        for s in p.get("segments") or []:
            walk(s.get("plan"))
        for sub in (p.get("subjects") or {}).values():
            walk(sub)
        if p.get("region_parts"):
            for rp in p["region_parts"]:
                rp["picks"] = [x for x in rp.get("picks") or [] if x not in names]
    walk(plan)
    return plan


# ---- 本体 ----

class Result(dict):
    pass


def _log_path(env=None):
    return data_path("logs/answers.jsonl", env)


def run(question, *, now=None, env=None, workdir=None, polished=None, obs_kw=None, clock=None, policy=None):
    """質問の文 → Result(text・status・stage・route・errors・warnings・removed・elapsed_s・refresh_pages・workdir など)。"""
    from . import ask
    t0 = time.monotonic()
    pol = policy or AP.load_policy()
    now = now or ask._clock()
    if workdir is None:                                  # 質問ごとに別の作業フォルダ(同じ秒・同じ --now の質問で記録を混ぜない)
        import uuid
        workdir = data_path(ask.load_policy()["work_dir"], env) / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
    cond = resolve(question, now, pol)
    res = Result(question=question, route=cond["route"], cond=cond, workdir=str(workdir), status=STATUS_PASS, stage=None, errors=[], warnings=[],
                 removed=[], refresh_pages=[], needs_research=False)
    try:
        if cond["route"] == "plan":
            _plan_route(res, cond, now, env, workdir, polished, obs_kw, clock, pol, t0)
        else:
            _other_route(res, cond, now, env, pol)
    except Exception as ex:                              # どの段でも止めない(答えを空にしない)。コードの不具合として記録に残す
        res["warnings"].append({"code": "internal_error", "detail": f"{type(ex).__name__}: {str(ex)[:160]}"})
        if not res.get("text"):
            res["text"] = _last_resort(cond, now, pol)
            res["stage"], res["status"] = 4, STATUS_DEGRADED
    if not (res.get("text") or "").strip():
        res["text"], res["stage"], res["status"] = _last_resort(cond, now, pol), 4, STATUS_DEGRADED
    res["elapsed_s"] = round(time.monotonic() - t0, 2)
    res["stage_name"] = STAGES.get(res["stage"])
    try:
        Path(workdir).mkdir(parents=True, exist_ok=True)
        (Path(workdir) / "final.txt").write_text(res["text"], encoding="utf-8")
        (Path(workdir) / "answer.json").write_text(json.dumps({k: v for k, v in res.items() if k != "text"}, ensure_ascii=False, indent=1, default=str),
                                                   encoding="utf-8")
    except OSError:
        pass
    return res


def _last_resort(cond, now, pol):
    """材料も作れなかったときの最低限の答え(日付と確認の方法だけ。事実を作らない)。"""
    m = cfg(pol)["minimal"]
    days = _days([d for ds in cond["periods"] for d in ds]) if cond.get("periods") else _days([now.date().isoformat()])
    return "\n".join([m["lead_none"].format(days=days), "", m["how_heading"], m["how_line"]]) + "\n"


def _plan_route(res, cond, now, env, workdir, polished, obs_kw, clock, pol, t0):
    from . import ask
    from . import skeleton as SK
    f = ask.Flow(workdir, now=now, env=env, clock=clock, obs_kw=obs_kw)
    periods = [[date.fromisoformat(x) for x in ds] for ds in cond["periods"]]
    dates = periods[0]
    region = cond["region"] if cond["region"] is not None else ask.load_policy().get("default_region")
    subjects = cond["subjects"]
    f.prepare(subjects, region, [d for ds in periods for d in ds], cond["origin"])
    facts_doc = f.facts(subjects, region, dates, cond["origin"], periods=periods if len(periods) > 1 else None)
    if cond["area_names"]:
        plan_doc = f.area_plan(cond["area_names"])
    else:
        try:
            plan_doc = f.plan(refine=cond["refine"]) if cond["refine"] else f.plan()
        except ValueError:
            plan_doc = f.plan()
    f.save_calls()
    gaz = sorted(set(ask.place_names()))
    offers = OF.texts(plan_doc.get("offers"))
    skeleton, plan_doc, shortened = fit_length(facts_doc, plan_doc, offers, cond["defaulted_date"])
    if shortened:
        res["warnings"].append({"code": "too_long", "detail": "字数の上限に収めるため候補を減らした: " + "・".join(shortened)})
    (Path(workdir) / "skeleton.txt").write_text(skeleton, encoding="utf-8")
    try:
        res["refresh_pages"] = AP.refresh_targets(facts_doc, plan_doc, now=now, env=env)
    except (KeyError, ValueError, TypeError):
        res["refresh_pages"] = []
    over_budget = (time.monotonic() - t0) > cfg(pol)["budget_s"]["value"]
    if polished and not over_budget:                                      # 段 1: 整えた文章
        from . import polish as PL
        fr = PL.check(skeleton, polished, ask.polish_names(facts_doc))
        g = gate_check(polished, facts_doc, plan_doc, gaz, offers)
        if fr["ok"] and g["ok"]:
            res.update(text=g["text"], stage=1, status=STATUS_PASS, warnings=res["warnings"] + g["warnings"])
            return
        res["warnings"] += [{"code": e["code"], "detail": e.get("detail", ""), "where": "polished"} for e in fr["errors"]] +                            [{**e, "where": "polished"} for e in g["errors"]]
    g = gate_check(skeleton, facts_doc, plan_doc, gaz, offers)            # 段 2: 骨組み
    if g["ok"]:
        res.update(text=g["text"], stage=2, status=STATUS_PASS, warnings=res["warnings"] + g["warnings"])
        return
    res["errors"] = g["errors"]
    res["warnings"] += g["warnings"]
    bad = _candidates_with_errors(skeleton, facts_doc, plan_doc, g["errors"]) if not over_budget else set()
    if bad:                                                               # 段 3: 部分回答(問題のある候補を外す)
        part_plan = drop_picks(plan_doc, bad)
        part = SK.compose(facts_doc, part_plan, offers, defaulted_date=cond["defaulted_date"])
        g3 = gate_check(part, facts_doc, part_plan, gaz, offers)
        if g3["ok"] and SK._flat_picks(part_plan):
            blocked = any(e.get("gate") == "safety" for e in g["errors"])
            res.update(text=g3["text"], stage=3, status=STATUS_BLOCKED if blocked else STATUS_DEGRADED, removed=sorted(bad))
            return
    res.update(text=minimal_answer(facts_doc, plan_doc, pol), stage=4, status=STATUS_DEGRADED)   # 段 4: 最低限の答え


def _other_route(res, cond, now, env, pol):
    """知識・違い・雑談・平年・行事・野草・ガイド型(facts を持たない経路)。"""
    from . import intent
    q = cond["question"]
    today = now.date()
    text = None
    if cond["route"] in ("knowledge", "difference", "chat", "normal", "event"):
        text = intent.compose(q, today=today)
        if text is not None:
            errs = intent.check_event(text, today) if cond["route"] == "event" else intent.check(text, intent.cards_for(q))
            if not errs:
                res.update(text=text, stage=2, status=STATUS_PASS)
                return
            res["errors"] = [{"code": e["code"], "detail": e.get("detail", "")} for e in errs]
            text = None
        if cond["route"] == "event":
            res.update(text=intent.event_none_line(q) + "\n", stage=4, status=STATUS_DEGRADED)
            return
        res["needs_research"] = True                                     # 先に調べてカードに記録すると、次は資料から答えられる
        if cond["guide_word"] or resolve_topics(q, pol)[0]:
            cond = {**cond, "route": "guide", "guide_word": cond["guide_word"] or _first_guide_word(q)}
    if cond["route"] == "wildflower":
        from . import wildflower as WF
        d = [date.fromisoformat(x) for ds in cond["periods"] for x in ds][0]
        text = WF.overview(month=None, date_=d.isoformat())["text"]
    elif cond["route"] == "guide" and cond.get("guide_word"):
        text = _guide_text(cond["guide_word"], [date.fromisoformat(x) for ds in cond["periods"] for x in ds][0], cond["origin"])
    if text:
        r = V.generic_check(text)
        errs = [e for e in r["errors"] if e["code"] not in ("too_few_candidates", "ask_back_only")]
        if not errs:
            res.update(text=text, stage=2, status=STATUS_PASS if not res["needs_research"] else STATUS_DEGRADED)
            return
        stripped = V.generic_strip(text, {"errors": errs})
        if stripped.strip() and not [e for e in V.generic_check(stripped)["errors"] if e["code"] not in ("too_few_candidates", "ask_back_only")]:
            res.update(text=stripped, stage=3, status=STATUS_DEGRADED, errors=errs)
            return
    m = cfg(pol)
    topic = (cond.get("guide_word") or _first_guide_word(q) or q.strip().rstrip("?？。"))[:20]
    res.update(text="\n".join([m["knowledge_none"].format(topic=topic), "", m["minimal"]["how_heading"], m["knowledge_how"]]) + "\n",
               stage=4, status=STATUS_DEGRADED, needs_research=True)


def _first_guide_word(q):
    words, _ = _theme_words()
    return next((w for w in sorted(words, key=len, reverse=True) if w in (q or "")), None)


def _guide_text(word, on, origin):
    from . import guide
    pol = guide.load_policy()
    got = guide.theme_of(word, pol)
    if not got:
        return None
    entries = guide.build()[0]
    found = guide.find(entries, themes=set(got["themes"]), kinds=got.get("kinds") or [], on=on, policy=pol, origin=origin)
    _o, line = guide.origin_line_for(origin)
    text = guide.render_brief(found, pol, origin_line=line, on=on, themes=set(got["themes"]))
    return None if guide.forbidden_in_answer(text, pol) else text


# ---- CLI(ask.py から呼ぶ) ----

def print_result(res, out, err, as_json=False):
    if as_json:
        out.write(json.dumps({k: v for k, v in res.items()}, ensure_ascii=False, indent=1, default=str) + "\n")
        return
    out.write(res["text"])
    err.write(f"状態: {res['status']}(段 {res['stage']}: {res.get('stage_name')})・{res['elapsed_s']}秒・作業フォルダ {res['workdir']}\n")
    for p in res.get("refresh_pages") or []:
        err.write(f"読むページ: {p['url']}({p['name']}。最後に読んだのは {p.get('last_read') or 'まだ'})\n")
    if res.get("needs_research"):
        err.write("資料が足りません: 公的な解説を読んで ask knowledge add で記録すると、次は資料から答えられます\n")
