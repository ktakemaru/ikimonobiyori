"""会話の比較表(段階58 第5部)。履歴の計画(直近 5 件・24 時間。データ置き場)から、コードで表を作る。通信しない。手で表を作らない(記録とずれるため)。

値は計画に載った名所の最新の事実(O.facts)から取り直す。履歴が 2 件以上あるときだけ作れる。"""
import json
from datetime import datetime, timedelta

from . import answer_plan as AP
from . import observations as O
from .paths import data_path


def cfg():
    return AP.load_policy()["compare"]


def history_path(env=None):
    return data_path(cfg()["file"], env)


def load_history(now, env=None):
    """有効期間内の履歴(新しい順)。"""
    try:
        rows = json.loads(history_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    keep = []
    for r in rows:
        try:
            saved = datetime.fromisoformat(r["saved_at"])
        except (KeyError, ValueError):
            continue
        if saved <= now and now - saved <= timedelta(hours=cfg()["valid_hours"]):
            keep.append(r)
    return keep[: cfg()["max_plans"]]


def _rows_of(plan):
    """計画のおすすめ → [(対象, 名所)]。"""
    out = []
    subject = plan.get("subject")
    if subject == "areas":
        return [(plan["area_subject"], p["name"]) for s in plan["segments"] for p in s["plan"]["picks"]]
    if subject == "periods":
        for s in plan["segments"]:
            pl = s["plan"]
            if pl.get("subject") == "areas":
                out += [(pl["area_subject"], p["name"]) for x in pl["segments"] for p in x["plan"]["picks"]]
            elif pl.get("subject") == "all":
                out += [(sj, p["name"]) for sj, sp in pl["subjects"].items() for p in sp["picks"]]
            else:
                out += [(pl["subject"], p["name"]) for p in pl["picks"]]
        return out
    if subject == "all":
        return [(sj, p["name"]) for sj, sp in plan["subjects"].items() for p in sp["picks"]]
    return [(subject, p["name"]) for p in plan.get("picks") or []]


def remember(plan, now, env=None):
    """計画を履歴に足す(直近 max_plans 件)。"""
    entry = {"saved_at": now.isoformat(), "dates": plan.get("dates"), "origin": plan.get("origin"), "rows": _rows_of(plan), "lines": plan.get("picks_lines") or []}
    rows = [entry] + load_history(now, env)
    p = history_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows[: cfg()["max_plans"]], ensure_ascii=False, indent=0), encoding="utf-8")


def can_compare(now, env=None, pending=0):
    """比較表を作れるか。pending: これから履歴に足す計画の数。"""
    return len(load_history(now, env)) + pending >= cfg()["min_plans"]


def table(now, env=None, facts_fn=None, dates=None):
    """→ (Markdown の表, 出典の URL の一覧)。履歴が 2 件未満なら (None, [])。facts_fn(subject, dates) → O.facts の形(テスト用)。"""
    hist = load_history(now, env)
    if len(hist) < cfg()["min_plans"]:
        return None, []
    rows, seen = [], set()
    for h in hist:
        for sj, name in h["rows"]:
            if (sj, name) not in seen:
                seen.add((sj, name))
                rows.append((sj, name, h))
    labels = cfg()["headers"]
    out = ["| " + " | ".join(labels) + " |", "|" + "---|" * len(labels)]
    urls = []
    cache = {}
    for sj, name, h in rows:
        ds = tuple(h.get("dates") or [])
        key = (sj, ds, h.get("origin"))
        if key not in cache:
            dates_ = [datetime.fromisoformat(x).date() for x in ds]
            cache[key] = facts_fn(sj, dates_) if facts_fn else O.facts(sj, region=O.load_policy()["all_range_words"][0], dates=dates_, now=now, origin=h.get("origin"), env=env)
        fact = next((c for c in (cache[key].get("candidates") or []) + (cache[key].get("avoid") or []) if c["name"] == name), None)
        if not fact:
            continue
        cur = fact.get("current")
        if AP.has_current(fact):
            when = f"({O._md(cur['state_date'])}時点)" if cur.get("state_date") else ""
            state = (cur.get("display") or cur["state_raw"]).rstrip("。") + when
            if cur.get("url") and cur["url"] not in urls:
                urls.append(cur["url"])
        else:
            state = cfg()["no_current"]
        pol = AP.load_policy()
        r = AP.score_candidate(dict(fact, _origin=h.get("origin")), [datetime.fromisoformat(x).date() for x in ds], pol, sj)
        outlook = pol["outlook"]["labels"][r["outlook"]]
        typical = (fact.get("typical_line") or cfg()["no_typical"]).replace("|", "/")
        out.append(f"| {name} | {state} | {typical} | {outlook} |")
    return "\n".join(out) + "\n", urls
