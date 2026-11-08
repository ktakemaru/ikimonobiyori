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
NL = "\n"
def _stages():
    from . import answer_gates as AG                     # 段階63a 第6部: フォールバックの順は答えの仕様から
    return {i + 1: name for i, name in enumerate(AG.contract()["fallback"])}


STAGES = _stages()


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
    from . import season_place as SP
    from . import highlights as HL
    if kind not in ("event", "normal", "difference") and defaulted and HL.is_highlights_question(q):   # 段階65 第4部: 日付のない場所の質問(「日光の見どころ」)
        route = "highlights"
    elif (kind not in ("event", "normal", "difference", "chat") or (kind == "normal" and any(w in q for w in SP.cfg().get("over_normal_words") or [])))             and SP.is_season_place(q):                   # 段階65 第2部: 「梅の名所と時期」は平年の目安ではなく、名所と例年の時期    # 段階64 第3部: 日付を聞いていない「いつ・どこ」(種の名前で引く)
        route = "season_place"
    elif kind not in ("event", "normal") and defaulted and SP.is_town_question(q):      # 段階64 第4部 4: 町の名前で聞く場所の質問(「松田で有名なところ」)
        route = "town"
    elif wild and kind != "event":                       # 野草・高山植物の語は、知識の言い方(「教えて」)でも野草の経路(段階40)
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
        write_log(res, now, env)
    except OSError:
        pass
    try:                                                 # 段階64 第4部 3: 計画の型でない答えは、写真つきページのために覚える
        from . import answer_page as APG
        APG.remember(res, now, env)
    except (OSError, KeyError, TypeError):
        pass
    try:
        Path(workdir).mkdir(parents=True, exist_ok=True)
        (Path(workdir) / "final.txt").write_text(res["text"], encoding="utf-8")
        (Path(workdir) / "answer.json").write_text(json.dumps({k: v for k, v in res.items() if k != "text"}, ensure_ascii=False, indent=1, default=str),
                                                   encoding="utf-8")
    except OSError:
        pass
    return res


def log_row(res, now):
    """答えごとの記録の 1 行(段階63a 第5部): 状態・4つの検査の結果・落ちた理由・警告・フォールバックの段・外した候補の数・かかった時間。"""
    from . import answer_gates as AG
    errs = res.get("errors") or []
    checks = [{"id": g, "result": "FAIL" if any(e.get("gate") == g for e in errs) else "PASS",
               "codes": sorted({e["code"] for e in errs if e.get("gate") == g})} for g in AG.GATES]
    return {"at": now.isoformat(), "question": (res.get("question") or "")[:80], "route": res.get("route"), "status": res.get("status"),
            "stage": res.get("stage"), "stage_name": STAGES.get(res.get("stage")), "checks": checks,
            "failed": sorted({e["code"] for e in errs}), "warnings": sorted({w["code"] for w in res.get("warnings") or []}),
            "removed_candidates": len(res.get("removed") or []), "removed_lines": len(res.get("removed_lines") or []),
            "elapsed_s": res.get("elapsed_s"), "refresh_pages": len(res.get("refresh_pages") or [])}


def write_log(res, now, env=None):
    p = _log_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(log_row(res, now), ensure_ascii=False) + NL)


def read_log(env=None):
    try:
        return [json.loads(l) for l in _log_path(env).read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def report(rows):
    """記録の集計: よく落ちる検査・よく出る警告・フォールバックの段と状態の割合・かかった時間。→ 文字列"""
    from collections import Counter
    n = len(rows)
    if not n:
        return "記録がまだありません。" + NL
    fail, warn, stage, status = Counter(), Counter(), Counter(), Counter()
    for r in rows:
        fail.update(r.get("failed") or [])
        warn.update(r.get("warnings") or [])
        stage[r.get("stage_name") or str(r.get("stage"))] += 1
        status[r.get("status")] += 1
    el = sorted(r["elapsed_s"] for r in rows if isinstance(r.get("elapsed_s"), (int, float)))
    out = [f"答えの数: {n}"]
    out.append("フォールバックの段: " + "、".join(f"{k} {v}件({v * 100 // n}%)" for k, v in stage.most_common()))
    out.append("状態: " + "、".join(f"{k} {v}件({v * 100 // n}%)" for k, v in status.most_common()))
    if el:
        out.append(f"かかった時間: 中央 {el[len(el) // 2]} 秒、最大 {el[-1]} 秒")
    out.append("よく落ちる検査: " + ("、".join(f"{k} {v}" for k, v in fail.most_common(10)) or "なし"))
    out.append("よく出る警告: " + ("、".join(f"{k} {v}" for k, v in warn.most_common(10)) or "なし"))
    return NL.join(out) + NL


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
    res.update(answer_from_facts(facts_doc, plan_doc, cond["defaulted_date"], polished=polished, gaz=gaz, policy=pol, warnings=res["warnings"],
                                 over_budget=lambda: (time.monotonic() - t0) > cfg(pol)["budget_s"]["value"], workdir=workdir,
                                 names=ask.polish_names(facts_doc)))
    try:
        res["refresh_pages"] = AP.refresh_targets(facts_doc, plan_doc, now=now, env=env)
    except (KeyError, ValueError, TypeError):
        res["refresh_pages"] = []


def answer_from_facts(facts_doc, plan_doc, defaulted=False, *, polished=None, gaz=(), policy=None, warnings=None, over_budget=None, workdir=None,
                      names=()):
    """材料(facts)と計画 → 答え(段 1〜4。必ず空でない)。ask answer の計画の経路と、総当たりのテストが同じこれを使う。
    → {text, stage, status, errors, warnings, removed, removed_lines, by_candidate}"""
    from . import polish as PL
    pol = policy or AP.load_policy()
    over = over_budget or (lambda: False)
    out = {"errors": [], "warnings": list(warnings or []), "removed": [], "removed_lines": []}
    offers = OF.texts(plan_doc.get("offers"))
    skeleton, plan_doc, shortened = fit_length(facts_doc, plan_doc, offers, defaulted)
    if shortened:
        out["warnings"].append({"code": "too_long", "detail": "字数の上限に収めるため候補を減らした: " + "・".join(shortened)})
    if workdir is not None:
        (Path(workdir) / "skeleton.txt").write_text(skeleton, encoding="utf-8")
        (Path(workdir) / "skeleton_facts.json").write_text(json.dumps(PL.skeleton_facts(skeleton, names), ensure_ascii=False, indent=0), encoding="utf-8")
    if polished and not over():                                           # 段 1: 整えた文章
        fr = PL.check_structured(skeleton, polished, names)               # 第4部: 骨組みの事実(構造化)との照合。事実の行は骨組みの文のまま
        g = gate_check(polished, facts_doc, plan_doc, gaz, offers)
        if fr["ok"] and g["ok"]:
            return {**out, "text": g["text"], "stage": 1, "status": STATUS_PASS, "warnings": out["warnings"] + g["warnings"]}
        out["warnings"] += [{"code": e["code"], "detail": e.get("detail", ""), "where": "polished"} for e in fr["errors"]] +                            [{**e, "where": "polished"} for e in g["errors"]]
    g = gate_check(skeleton, facts_doc, plan_doc, gaz, offers)            # 段 2: 骨組み
    if g["ok"]:
        return {**out, "text": g["text"], "stage": 2, "status": STATUS_PASS, "warnings": out["warnings"] + g["warnings"]}
    out["errors"] = g["errors"]
    out["warnings"] += g["warnings"]
    if not over():                                                        # 段 3: 部分回答(第3部: 問題を候補ごと・主張ごとに外す)
        got = partial_answer(facts_doc, plan_doc, g, offers, defaulted, gaz)
        if got:
            return {**out, **got}
    return {**out, "text": minimal_answer(facts_doc, plan_doc, pol), "stage": 4, "status": STATUS_DEGRADED}   # 段 4: 最低限の答え


def partial_answer(facts_doc, plan_doc, g, offers, defaulted, gaz, max_rounds=3):
    """問題のある候補を計画から外し(候補ごと)、候補に結びつかない文の誤りはその行だけ外す(主張ごと)。外して直らない・全部の候補が外れたら None。
    → {text, stage: 3, status, removed, removed_lines, by_candidate}。危険な案内(安全の検査)を外したら BLOCKED。"""
    from . import answer_gates as AG
    from . import skeleton as SK
    removed, removed_lines, by_cand = set(), [], {}
    blocked = any(e.get("gate") == "safety" for e in g["errors"])
    text, errors, plan = g["text"], g["errors"], plan_doc
    for _ in range(max_rounds):
        loc = AG.localize(errors, text, plan)
        if loc["general"]:
            return None                                                   # どの候補・文に当たるか分からない誤り: 外しても直らない
        if loc["by_candidate"]:
            for n, es in loc["by_candidate"].items():
                by_cand.setdefault(n, []).extend({"code": e["code"], "gate": e.get("gate")} for e in es)
            removed |= set(loc["by_candidate"])
            plan = drop_picks(plan, removed)
            if not SK._flat_picks(plan):
                return None
            r = gate_check(SK.compose(facts_doc, plan, offers, defaulted_date=defaulted), facts_doc, plan, gaz, offers)
        else:
            src = text.splitlines()
            removed_lines += [src[i] for i in sorted(loc["by_line"]) if i < len(src)]
            r = gate_check(AG.drop_lines(text, set(loc["by_line"])), facts_doc, plan, gaz, offers)
        if r["ok"]:
            return {"text": r["text"], "stage": 3, "status": STATUS_BLOCKED if blocked else STATUS_DEGRADED, "removed": sorted(removed),
                    "removed_lines": removed_lines, "by_candidate": by_cand}
        blocked = blocked or any(e.get("gate") == "safety" for e in r["errors"])
        text, errors = r["text"], r["errors"]
    return None



def _season_place_route(res, cond, now, env):
    """段階64 第3部: 時期と場所の答え(名所カタログ・ガイドのカタログ・記録から。今の日付で絞らない)。"""
    from . import answer_gates as AG
    from . import observations as O
    from . import season_place as SP
    prefs = None
    if cond.get("region"):
        reg = O.resolve(cond["region"], cond["origin"], O.load_policy())
        prefs = reg.get("prefectures") or None
    got = SP.compose(cond["question"], today=now.date(), origin=cond["origin"], region=cond.get("region"), prefectures=prefs, env=env)
    text, _removed = AG.delete_bad_sentences(got["text"], offers=[])
    errs = [e for e in V.generic_check(text)["errors"] if e["code"] not in ("too_few_candidates", "ask_back_only")]
    res["season_place"] = {"species": got["species_all"], "spots": [r["name"] for r in got["spots"]], "missing": got["missing"]}
    if not got["spots"]:
        res.update(text=text, stage=4, status=STATUS_DEGRADED, needs_research=True, research_kind="season_place")
    elif got["needs_research"]:                                           # 一部の種に名所の記録がない(その種は 1 文で書いた)
        res.update(text=text, stage=3, status=STATUS_DEGRADED, needs_research=True, research_kind="season_place", errors=errs)
    elif errs:
        res.update(text=text, stage=3, status=STATUS_DEGRADED, errors=errs)
    else:
        res.update(text=text, stage=2, status=STATUS_PASS)


def _with_knowledge_tail(text, cond, now, env):
    """知識の答えの、出典の見出しの前に「いつ・どこで」の短い一覧(名所カタログ・ガイドのカタログ・記録から。最大 5 件)を足す。出典も足す。"""
    from . import observations as O
    from . import season_place as SP
    prefs = None
    if cond.get("region"):
        prefs = O.resolve(cond["region"], cond["origin"], O.load_policy()).get("prefectures") or None
    try:
        tail, urls = SP.knowledge_tail(cond["question"], today=now.date(), origin=cond["origin"], prefectures=prefs, env=env)
    except (KeyError, ValueError, TypeError, OSError):
        return text
    if not tail:
        return text
    head = SP.cfg()["text"]["sources_heading"]
    lines = text.rstrip(NL).split(NL)
    i = next((k for k, l in enumerate(lines) if l.strip() == head), len(lines))
    body, src = lines[:i], lines[i + 1:] if i < len(lines) else []
    while body and not body[-1].strip():
        body.pop()
    src = src + [u for u in urls if u not in src]
    from . import intent
    note = intent.cfg().get("secondary_note")
    j = next((k for k, l in enumerate(body) if note and l.strip() == note), None)   # 確かさの補足(紹介サイトの記載)は最後に
    if j is not None:
        rest = [l for l in body[j:] if l.strip()]
        body = body[:j]
        while body and not body[-1].strip():
            body.pop()
        out = body + [""] + tail + [""] + rest + ["", head] + src
    else:
        out = body + [""] + tail + ["", head] + src
    return NL.join(out) + NL


def _other_route(res, cond, now, env, pol):
    """知識・違い・雑談・平年・行事・野草・ガイド型(facts を持たない経路)。"""
    from . import intent
    q = cond["question"]
    today = now.date()
    text = None
    if cond["route"] == "season_place":
        _season_place_route(res, cond, now, env)
        return
    if cond["route"] == "highlights":
        from . import answer_gates as AG
        from . import highlights as HL
        got = HL.compose(q, today=today, env=env)
        text, _removed = AG.delete_bad_sentences(got["text"], offers=[])
        res["highlights"] = {"places": got["places"], "cards": got["cards"], "spots": got["spots"]}
        if got["needs_research"]:
            res.update(text=text, stage=4, status=STATUS_DEGRADED, needs_research=True, research_kind="knowledge")
        else:
            res.update(text=text, stage=2, status=STATUS_PASS)
        return
    if cond["route"] == "town":
        from . import answer_gates as AG
        from . import season_place as SP
        got = SP.compose_town(q, origin=cond["origin"], env=env)
        text, _removed = AG.delete_bad_sentences(got["text"], offers=[])
        res["town"] = {"town": got["town"], "spots": [r["name"] for r in got["spots"]]}
        if got["needs_research"]:
            res.update(text=text, stage=4, status=STATUS_DEGRADED, needs_research=True, research_kind="season_place")
        else:
            res.update(text=text, stage=2, status=STATUS_PASS)
        return
    if cond["route"] in ("knowledge", "difference", "chat", "normal", "event"):
        text = intent.compose(q, today=today)
        if text is not None:
            errs = intent.check_event(text, today) if cond["route"] == "event" else intent.check(text, intent.cards_for(q))
            if not errs:
                if cond["route"] in ("knowledge", "chat"):
                    text = _with_knowledge_tail(text, cond, now, env)       # 段階64 第4部: いつ・どこ は最後に短く
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
        from . import answer_gates as AG
        text = AG.strip_old_list(text)                                    # 段階64 第2部 4: 古い一覧の形を答えに出さない
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
    if res.get("needs_research") and res.get("research_kind") == "season_place":
        err.write("名所の記録が足りません: 公式ページ(なければ紹介サイト)の本文を読み、ask record で kind(種)と typical(例年の時期)を記録してから、"
                  "もう一度 ask answer を実行します(最大3ページ。検索の要約は記録しない)\n")
    elif res.get("needs_research"):
        err.write("資料が足りません: 公的な解説を読んで ask knowledge add で記録すると、次は資料から答えられます\n")
