"""生き物の質問に答える手順(段階37。単体で完結する。通信は計測フックの下の iNaturalist の取り直しだけ)。

biyori-hub の concierge_skill/ask.py(段階H8〜H10)が行っていた生き物の手順を、イキモノビヨリの中に移した
(指示書 docs/stage37-H11-instructions.md 2-1)。単体で聞いても、ハブ経由で聞いても、同じコマンド・同じ記録の置き場所を使う。

  python -X utf8 -m ikimonobiyori.ask prepare [--out-dir DIR] [--subject S ...] [--region 語] [--when 明日|今日|今週末|YYYY-MM-DD[,..]] [--origin 横浜] [--now ISO]
  python -X utf8 -m ikimonobiyori.ask inat-refresh --out-dir DIR [--now ISO]     (計測フックの下だけ。呼ぶのは biyori-hub など計測フックを持つ側)
  python -X utf8 -m ikimonobiyori.ask record --out-dir DIR --batch reads.json
  python -X utf8 -m ikimonobiyori.ask facts --out-dir DIR [--fetch-log fetch_log.json]   (対象・地域・日は prepare の値を使う)
  python -X utf8 -m ikimonobiyori.ask plan --out-dir DIR [--subject S] [--explain 名所] [--override 名所 --reason 理由 [--replace 計画の名所]]   (段階56。facts のあと、答えを書く前に)
  python -X utf8 -m ikimonobiyori.ask verify --out-dir DIR --text answer.txt [--gazetteer names.json ...]

作業フォルダ(--out-dir。省くと IKIMONOBIYORI_DATA_DIR の下の ask/<日時>)に plan.json・records.json・facts.json・check.json・
final.txt と、呼び出しの記録 calls.json を書く。記録そのもの(observations/)も IKIMONOBIYORI_DATA_DIR の下(CLAUDE.md 規則 8)。
値・語は data/ask/policy.yaml。"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from . import answer_plan as AP
from . import ask_verify as V
from . import livegate, netbudget
from . import offers as OF
from . import origins
from . import observations as O
from . import sources as S
from .paths import DATA_FILES_DIR, PKG, data_dir, data_path

POLICY_PATH = DATA_FILES_DIR / "ask" / "policy.yaml"


def load_policy(path=None):
    return yaml.safe_load(Path(path or POLICY_PATH).read_text(encoding="utf-8"))


def _clock():
    return O.clock_now()


def parse_dates(when, now):
    """「明日」「今日」「今週末」「YYYY-MM-DD」(複数はカンマ)→ [date]。"""
    today = now.date()
    w = (when or "weekend").strip()
    if w in ("tomorrow", "明日"):
        return [today + timedelta(days=1)]
    if w in ("today", "今日"):
        return [today]
    if w in ("weekend", "今週末"):
        return S.next_weekend(now)
    return [date.fromisoformat(x) for x in w.split(",")]


def _md(d):
    return f"{d.month}/{d.day}"


# ---- この回の記録の結果と「読み直しました」の行(段階H9。ハブから移した) ----

def this_round(records, log, plan_doc=None):
    """この回(同じ作業フォルダ)の記録の結果 → 新しい記録の数・新しい記録が増えたページ・読みに行ったが増えなかったページ。
    records: records.json(record の結果の履歴。by_url = ページごとの written・duplicates)。log: fetch_log(読めなかったページの URL にだけ使う)。
    段階37: 重複(同じ名所・同じ状態・同じ状態の日付)は written に入らないので、ここの数は本当に増えた件数。"""
    pages = {}
    for r in records or []:
        for u in r.get("by_url") or []:
            x = pages.setdefault(u["url"], {"url": u["url"], "publisher": u.get("publisher"), "written": 0, "duplicates": 0})
            x["written"] += u.get("written") or 0
            x["duplicates"] += u.get("duplicates") or 0
    new = [x for x in pages.values() if x["written"] > 0]
    nothing = [x for x in pages.values() if x["written"] == 0]
    tried = {x["url"] for x in pages.values()}
    new_pubs = [(x.get("publisher") or "") for x in new]
    for r in (log or {}).get("read") or []:              # 読んだと書いてあるが、記録に1件も出していないページ(新しい情報は取れなかった)
        p = r.get("publisher") or ""
        if p and any(q.startswith(p) or p.startswith(q) for q in new_pubs if q):
            continue                                      # 新しい記録が増えた発行元の一覧ページ(記録はその先のページで数えた)
        if r.get("url") and r["url"] not in tried:
            nothing.append({"url": r["url"], "publisher": r.get("publisher"), "written": 0, "duplicates": 0, "not_recorded": True})
            tried.add(r["url"])
    failed = [f for f in (log or {}).get("failed") or [] if f.get("url")]
    return {"record_calls": len(records or []), "new_records": sum(x["written"] for x in new), "pages_with_new": new,
            "pages_without_new": nothing, "failed": failed,
            "needs_fetch": bool((plan_doc or {}).get("needs_fetch")) if plan_doc is not None else None,
            "attempted": bool(records) or bool(nothing) or bool(failed)}


def _pubs(pages):
    out = []
    for x in pages:
        p = x.get("publisher") or x["url"]
        if p not in out:
            out.append(p)
    return out


def fetch_line(rnd, now, policy=None):
    """答えの最後の 1〜3 行(取りに行った結果)。この回の record で実際に新しい記録が増えたページの数・発行元だけから作る。"""
    L = (policy or load_policy())["fetch_lines"]
    md = _md(now)
    lines = []
    new = rnd.get("pages_with_new") or []
    if new:
        lines.append(L["new"].format(md=md, pubs="・".join(_pubs(new)), pages=len(new), n=rnd["new_records"]))
    nothing = rnd.get("pages_without_new") or []
    if nothing:
        lines.append((L["nothing_after_new"] if new else L["nothing"]).format(md=md, pubs="・".join(_pubs(nothing))))
    if not new and not nothing and not rnd.get("failed"):
        lines.append(L["fresh"] if rnd.get("needs_fetch") is False else L["none"])
    if rnd.get("failed"):
        lines.append(L["failed"] + " ".join(f["url"] for f in rnd["failed"]))
    return lines


def open_urls_line(rnd, policy=None):
    """段階51: 答えに書いてよい取得の結果は、読めなかったページを利用者が自分で開く 1 行だけ（なければ None）。
    「読み直し、新しい記録が N件増えました」「新しい情報は取れませんでした」のような作業の報告は答えに出さない（lines.fetch は作業の記録として残す）。"""
    L = (policy or load_policy())["fetch_lines"]
    failed = rnd.get("failed") or []
    return (L["failed"] + " ".join(f["url"] for f in failed)) if failed else None


# ---- 名所の名前の一覧(答えの検査器の地名の辞書) ----

def place_names():
    """名所カタログと観察の名所の一覧の名前・市区町村・地域。"""
    names = set()
    files = list((DATA_FILES_DIR / "catalog").glob("*.yaml")) + [O.SPOTS_PATH]
    for f in files:
        if not f.exists() or f.name == "policy.yaml":
            continue
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for e in (doc.get("entries") or []) + (doc.get("spots") or []):
            if not isinstance(e, dict) or e.get("example"):
                continue
            t = e.get("tags") or {}
            for v in (e.get("name"), e.get("city"), e.get("area"), t.get("city"), t.get("area")):
                if isinstance(v, str) and v:
                    names.add(v)
    return sorted(names)


def load_gazetteer_file(path):
    """--gazetteer のファイル(JSON の文字列の配列、または {"names": [...]})→ 名前の一覧。"""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    names = d.get("names") if isinstance(d, dict) else d
    return [x for x in names or [] if isinstance(x, str)]


# ---- 手順 ----

def mark_stale_display(subj, policy):
    """段階52: 古い表示が残ることのある発行元(箱根町観光協会)は、取得日と状態の日付が min_gap_days 以上離れたら、現況の断定に使わない印
    (current.reference_only)を付ける。日付つきの参考として出す。"""
    cfg = ((policy.get("answer_check") or {}).get("stage51") or {}).get("stale_display")
    if not cfg:
        return
    pubs, gap = cfg["publishers"]["value"], cfg["min_gap_days"]["value"]
    for s in subj.values():
        for c in s.get("candidates") or []:
            cur = c.get("current") or {}
            if not cur.get("state_date") or not cur.get("read_at"):
                continue
            if not any(p in (cur.get("publisher") or "") for p in pubs):
                continue
            days = (date.fromisoformat(cur["read_at"][:10]) - date.fromisoformat(cur["state_date"])).days
            if days >= gap:
                cur["reference_only"] = True
                cur["gap_days"] = days


def fetched_path(env=None):
    return data_path("ask/fetched_urls.json", env)


def fetched_today(now, env=None):
    """今日すでに読んだページの URL(同じ日に繰り返し取得しない。段階57 第5部)。"""
    try:
        return set(json.loads(fetched_path(env).read_text(encoding="utf-8")).get(now.date().isoformat()) or [])
    except (OSError, ValueError):
        return set()


def mark_fetched(urls, now, env=None):
    p = fetched_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    day = now.date().isoformat()
    p.write_text(json.dumps({day: sorted(fetched_today(now, env) | {u for u in urls if u})}, ensure_ascii=False, indent=0), encoding="utf-8")


def drop_fetched(doc, seen):
    """prepare の出力から、今日読んだページを除く。読むページがすべて今日読んだものの名所は、対象から外す(記録を使い回す)。"""
    if not seen:
        return doc
    for pl in doc["subjects"].values():
        pl["summary_pages"] = [p for p in pl.get("summary_pages") or [] if p.get("url") not in seen]
        kept = []
        for it in pl.get("items") or []:
            pages = it.get("pages") or []
            rest = [p for p in pages if p.get("url") not in seen]
            if pages and not rest:
                continue
            kept.append({**it, "pages": rest})
        pl["items"] = kept
        pl["needs_fetch"] = bool(pl["items"]) or bool(pl["summary_pages"])
    doc["summary_pages"] = [p for pl in doc["subjects"].values() for p in pl.get("summary_pages") or []]
    doc["needs_fetch"] = any(pl.get("needs_fetch") for pl in doc["subjects"].values())
    doc["already_read_today"] = sorted(seen)
    return doc


def _plan_cfg():
    return AP.load_policy()["last_plan"]


def last_plan_path(env=None):
    return data_path(_plan_cfg()["file"], env)


def _facts_subset(facts_doc, plan_doc):
    """計画に載る名所の事実だけ(直前の答えの写し。使った事実と出典)。"""
    names = {r["name"] for r in plan_doc.get("ranking") or [] if r.get("where") in ("pick", "section")} | {p["name"] for p in plan_doc.get("picks") or []}
    out = {k: v for k, v in facts_doc.items() if k != "subjects"}
    out["subjects"] = {s: {**v, "candidates": [c for c in v.get("candidates") or [] if c["name"] in names], "avoid": [], "nearby_out_of_region": [], "alternatives": []}
                       for s, v in facts_doc["subjects"].items()}
    out.pop("periods", None)
    return out


def save_last_plan(workdir, facts_doc, plan_doc, now, env=None):
    """直前の答えの計画を、データ置き場に保存する(有効期間は data/ask/plan.yaml の last_plan。リポジトリの外)。"""
    from . import compare
    compare.remember(plan_doc, now, env)                               # 段階58 第5部: 比較表の履歴
    p = last_plan_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema": "ikimonobiyori-last-plan/1", "saved_at": now.isoformat(), "workdir": str(workdir), "subject": plan_doc.get("subject"),
           "dates": plan_doc.get("dates"), "origin": plan_doc.get("origin"), "plan": plan_doc, "facts": _facts_subset(facts_doc, plan_doc), "answer": None}
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def update_last_plan_answer(workdir, text, env=None):
    p = last_plan_path(env)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if doc.get("workdir") == str(workdir):
        doc["answer"] = text
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def load_last_plan(now, env=None):
    """有効期間内の直前の計画。ない・古い・読めないときは None(別の内容を作らない)。"""
    try:
        doc = json.loads(last_plan_path(env).read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(doc["saved_at"])
    except (OSError, ValueError, KeyError):
        return None
    if now < saved or now - saved > timedelta(hours=_plan_cfg()["valid_hours"]):
        return None
    return doc


def restore_workdir(doc):
    """直前の計画の作業フォルダ。消えていれば写しから作り直す。→ フォルダのパス。"""
    wd = Path(doc["workdir"])
    wd.mkdir(parents=True, exist_ok=True)
    for name, key in (("facts.json", "facts"), ("answer_plan.json", "plan")):
        if not (wd / name).exists():
            (wd / name).write_text(json.dumps(doc[key], ensure_ascii=False, indent=1), encoding="utf-8")
    if doc.get("answer") and not (wd / "final.txt").exists():
        (wd / "final.txt").write_text(doc["answer"], encoding="utf-8")
    return wd


class PageUnsupported(Exception):
    """写真つきページに対応していない対象(段階57 第1部)。別のページを作らず、終了コード 2 で止める。"""


class Flow:
    """1 回の質問の手順。作業フォルダの calls.json に、手順ごとの呼び出しを順に追記する(別のコマンドで呼ばれても同じ質問の記録に足す)。"""

    def __init__(self, workdir, now=None, env=None, policy=None, clock=None, obs_kw=None):
        self.workdir = Path(workdir)
        self.obs_kw = obs_kw or {}                         # テスト用: observations の名所の一覧(spots_doc・catalogs)を差し替える
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.env = env
        self.policy = policy or load_policy()
        self.clock = clock or _clock
        self.now = now or self.clock()
        self.calls = self._load("calls.json", [])
        self.notes = []

    def _load(self, name, default):
        try:
            return json.loads((self.workdir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _save(self, name, doc):
        (self.workdir / name).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

    def call(self, step, **kw):
        self.calls.append({"step": step, "module": f"ikimonobiyori.ask", "code": str(PKG), "data_dir": str(data_dir(self.env)),
                           "at": self.clock().isoformat(timespec="seconds"), **kw})

    def save_calls(self):
        self._save("calls.json", self.calls)

    # 1. 取りに行く対象(+ 野鳥の集計の取り直しの対象)
    def prepare(self, subjects, region, dates, origin=None):
        origin = origin or self.policy["default_origin"]
        plans = {s: O.plan(s, region=region, dates=dates, now=self.now, origin=origin, env=self.env, **self.obs_kw) for s in subjects}
        self.call("prepare", subjects=list(subjects), region=region, dates=[d.isoformat() for d in dates], origin=origin,
                  needs_fetch={s: p.get("needs_fetch") for s, p in plans.items()})
        doc = {"schema": "ikimono-ask-plan/1", "subjects": plans, "needs_fetch": any(p.get("needs_fetch") for p in plans.values()),
               "now": self.now.isoformat(), "out_dir": str(self.workdir),
               "summary_pages": [p for pl in plans.values() for p in pl.get("summary_pages") or []],
               "limits": next(iter(plans.values()))["limits"] if plans else None}
        drop_fetched(doc, fetched_today(self.now, self.env))           # 段階57 第5部: 同じ日の同じページを読み直さない
        if "birds" in plans:
            doc["inat_refresh"] = self.inat_plan(plans["birds"].get("inat_refresh") or {})
        self._save("params.json", {"subjects": list(subjects), "region": region, "dates": [d.isoformat() for d in dates], "origin": origin,
                                   "now": self.now.isoformat()})
        self._save("plan.json", doc)
        return doc

    def inat_plan(self, ir):
        """野鳥の iNaturalist の集計の取り直しの対象(段階H10 の上限: 1 回の質問につき inat_refresh.max_requests)。
        新しければ calls に skipped: fresh を残す。古ければ、取り直す区域と上限を返す(取り直すのは inat-refresh。計測フックの下だけ)。"""
        if not ir.get("needed") or not ir.get("areas"):
            reason = "fresh" if ir else "no_plan"
            self.call("inat_refresh", skipped=reason, fresh=[x.get("area") for x in ir.get("fresh") or []])
            return {"ran": False, "reason": reason}
        limit = int(ir.get("max_requests") or 0)
        n = min(limit, sum(int(x.get("requests") or 0) for x in ir["areas"]))
        if n < 1:
            self.call("inat_refresh", skipped="no_budget")
            return {"ran": False, "reason": "no_budget"}
        return {"ran": False, "reason": "not_yet", "needed": True, "max_requests": n, "date": ir.get("date"),
                "areas": [x["area"] for x in ir["areas"]], "deferred": ir.get("deferred") or []}

    # 1b. 野鳥の集計の取り直し(計測フック・宣言済みホストの下だけ。CLAUDE.md 規則 6)
    def inat_refresh(self, http_get=None, sleep=None, clock=None):
        plan_doc = self._load("plan.json", {})
        ir = plan_doc.get("inat_refresh") or {}
        if not ir.get("needed"):
            return ir or {"ran": False, "reason": "no_plan"}
        if http_get is None:
            if livegate.under_test():
                self.call("inat_refresh", skipped="under_test")
                return self._inat_done(plan_doc, {"ran": False, "reason": "under_test"})
            why = netbudget.refusal()                # 段階38: 単体でも自前の上限で取りに行く。計測フックの下では BIYORI_ALLOW_LIVE=1 が要る(従来どおり)
            if why:
                self.call("inat_refresh", skipped="not_allowed")
                return self._inat_done(plan_doc, {"ran": False, "reason": "not_allowed"})
        n = ir["max_requests"]
        d = date.fromisoformat(ir.get("date") or self._load("params.json", {}).get("dates", [self.now.date().isoformat()])[0])
        budget = self.budget("inat_counts", O.load_policy()["inat_refresh"]["max_requests_per_question"]["value"], sleep=sleep)
        try:
            res = O.inat_refresh(ir["areas"], d, self.now, max_requests=n, env=self.env, http_get=http_get, sleep=sleep, clock=clock, budget=budget)
            rc = 5 if res.get("errors") else 0
        except Exception as e:                       # 失敗しても止めない(古い集計を日付つきで使う)
            res, rc = {"requests": None, "fetched": [], "deferred": [], "errors": [{"error": str(e)[:200]}]}, 5
        self.call("inat_refresh", max_requests=n, areas=ir["areas"], rc=rc, net=budget.summary())
        out = {"ran": True, "reason": "ran", "rc": rc, "max_requests": n, "requests": res.get("requests"), "fetched": res.get("fetched") or [],
               "deferred": (res.get("deferred") or []) + (ir.get("deferred") or []), "errors": res.get("errors") or [], "net": budget.summary()}
        self._save("inat_refresh.json", out)
        if rc != 0:
            self.notes.append("野鳥の集計の取り直しは失敗。古い集計を日付つきで使います")
        return self._inat_done(plan_doc, out)

    def budget(self, kind, max_requests, hosts=None, interval=None, sleep=None):
        """段階38: 単体の小さな上限(netbudget)。許可ホストは config.yaml の宣言済みホスト、間隔は同じホストへ 1 秒以上(方針)。"""
        from .config import load_config
        cfg = load_config()
        hosts = hosts or cfg["live"]["allowed_hosts_by_subject"]["birds"]
        gap = max(O.load_policy()["fetch_limits"]["same_host_interval_s"], interval or 0)
        kw = {"sleep": sleep} if sleep else {}
        return netbudget.Budget(kind, hosts, max_requests, gap, env=self.env, **kw)

    def _inat_done(self, plan_doc, out):
        plan_doc["inat_refresh"] = {**(plan_doc.get("inat_refresh") or {}), **out}
        self._save("plan.json", plan_doc)
        return out

    # 2. 記録
    def record(self, batch_path):
        """読んだ事実を記録し、結果(ページごとの新しい記録・重複の数 by_url)を records.json に追記する。
        答えの「読み直しました」は、この結果だけから作る。"""
        try:
            batch = json.loads(Path(batch_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ValueError(f"読んだ事実の JSON を読めない: {e}") from e
        batch = batch if isinstance(batch, list) else [batch]
        out = O.record(batch, env=self.env, now=self.clock())
        out.pop("records", None)
        hist = self._load("records.json", [])
        hist.append({"at": self.clock().isoformat(timespec="seconds"), "batch": str(batch_path), "submitted": len(batch),
                     "written": out.get("written"), "duplicates": out.get("duplicates"), "rejected": len(out.get("rejected") or []),
                     "by_url": out.get("by_url")})
        self._save("records.json", hist)
        mark_fetched([u.get("url") for u in out.get("by_url") or []], self.clock(), self.env)
        self.call("record", submitted=len(batch), written=out.get("written"), duplicates=out.get("duplicates"),
                  rejected=len(out.get("rejected") or []))
        return out

    # 3. 材料
    def facts(self, subjects, region, dates, origin=None, fetch_log=None, plan_doc=None, periods=None):
        origin = origin or self.policy["default_origin"]
        plan_doc = plan_doc if plan_doc is not None else self._load("plan.json", None)
        subj = {s: O.facts(s, region=region, dates=dates, now=self.now, origin=origin, env=self.env, **self.obs_kw) for s in subjects}
        mark_stale_display(subj, self.policy)
        rnd = this_round(self._load("records.json", []), fetch_log or {}, plan_doc)
        mark_fetched([r.get("url") for r in (fetch_log or {}).get("read") or []], self.now, self.env)
        inat = (plan_doc or {}).get("inat_refresh")
        if inat and inat.get("reason") == "not_yet":   # 取り直しの対象があったが、計測フックの下で取り直していない(単体で聞いたとき)
            self.call("inat_refresh", skipped="no_measure_hook", areas=inat.get("areas"))
            inat = {**inat, "reason": "no_measure_hook"}
        labels = O.load_policy()["subject_labels"]
        doc = {"schema": "ikimono-ask-facts/1", "now": self.now.isoformat(), "region": region, "origin": origin,
               "dates": [d.isoformat() for d in dates], "subjects": subj, "fetch": fetch_log or {},
               "summary_pages": [p for pl in ((plan_doc or {}).get("subjects") or {}).values() for p in pl.get("summary_pages") or []],
               "this_round": rnd,
               "lines": {"fetch": fetch_line(rnd, self.now, self.policy),
                         "origin_line": origins.line_for(origin),         # 段階57 第8部: 使った出発地の 1 文(答えに書く)
                         "practical_rules": True,                        # 段階52: 実用情報の決まり（出た候補の実用情報を書く／なければ決まった一文）を当てる印
                         "answer_rules": "stage51",                      # 段階51: 答えの検査の新しい決まりを当てる印（作業の報告を答えに出さない など）
                         "open_urls": open_urls_line(rnd, self.policy),   # 答えに出してよい唯一の取得の結果: 読めなかったページ（利用者が自分で開く）
                         "scope": self.policy["scope_line"].format(labels="・".join(labels[s] for s in subjects))},
               "inat_refresh": inat, "notes": self.notes}
        if periods:                                       # 段階57 第9部: 期間ごとの材料(同じ記録から。通信しない)
            doc["periods"] = []
            for ds in periods:
                psub = {s: O.facts(s, region=region, dates=ds, now=self.now, origin=origin, env=self.env, **self.obs_kw) for s in subjects}
                mark_stale_display(psub, self.policy)
                doc["periods"].append({"dates": [d.isoformat() for d in ds], "subjects": psub})
            doc["dates"] = [d.isoformat() for ds in periods for d in ds]
        from . import visitor_centers as VC               # 段階55 第5部: 承認済みのビジターセンター・自然観察施設の事実（なければキーごと出さない）
        vc = VC.fact_rows(self.now.date(), subjects=list(subjects), env=self.env)
        if vc:
            doc["visitor_centers"] = vc
        self._save("facts.json", doc)
        self.call("facts", subjects=list(subjects), new_records=rnd["new_records"], attempted=rnd["attempted"])
        return doc

    # 3b. 写真(段階38。公園ごとの鳥の写真のうち、手元にないものを取りに行く。上限の範囲。足りなければ「写真なし」で止めない)
    def photos(self, http_get=None, http_bytes=None, sleep=None):
        from . import guide, guide_photos, park_page
        from .config import load_config
        from .fetch import commons_photos, inat_photos
        from .fetch.live import LiveError
        facts_doc = self._load("facts.json", None)
        if facts_doc is None:
            raise ValueError("facts.json がない(先に facts を実行する)")
        if list(facts_doc.get("subjects") or {}) != ["birds"]:         # 段階57 第2部: 紅葉・花・総合は、計画に載る種の写真を補う
            return self.plan_photos(facts_doc, http_get, http_bytes)
        if http_get is None:
            why = "under_test" if livegate.under_test() else ("not_allowed" if netbudget.refusal() else None)
            if why:
                self.call("photos", skipped=why)
                out = {"ran": False, "reason": why}
                self._save("photos.json", out)
                return out
        ph = guide.load_policy()["photos"]
        cfg = load_config()
        table = guide_photos.load_table(self.env) if self.env else guide_photos.load_table()
        review = guide_photos.load_review(self.env) if self.env else guide_photos.load_review()
        from datetime import date as _date
        none_cache = guide_photos.load_none(self.env) if self.env else guide_photos.load_none()      # 段階39 A-3: 取れなかった種は探し直さない（負のキャッシュ）
        today = self.now.date() if hasattr(self.now, "date") else _date.today()
        rows, need_search, seen = [], [], []
        for c in park_page.parks(facts_doc, self.policy["park_page"]):
            for b in c["park_birds"]:
                if b["name"] in seen:
                    continue
                seen.append(b["name"])
                if b["name"] in none_cache and guide_photos.none_active(none_cache[b["name"]], today):
                    continue
                t = table.get(b["name"])
                tid = b.get("taxon_id") or (t or {}).get("taxon_id")
                sci = b.get("scientific_name") or (t or {}).get("scientific")
                if tid and sci:
                    rows.append({"name": b["name"], "scientific": sci, "taxon_id": int(tid)})
                elif not inat_photos.skipped(b["name"], ph):
                    need_search.append(b["name"])
        rows = [r for r in rows if str(r["taxon_id"]) not in review]
        has = (lambda t: guide_photos.has_cache(t, self.env)) if self.env else guide_photos.has_cache
        save = (lambda it: guide_photos.save_photo(it, self.env)) if self.env else guide_photos.save_photo
        getter = None
        if http_get is None:
            from .fetch.live import SessionGetter
            t = cfg["live"]["request_timeout"]
            getter = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"])
            http_get, http_bytes = getter, getter.get_bytes
        hosts = cfg["live"]["allowed_hosts_by_subject"]["guide_photos"]
        b = self.budget("photos", ph["max_requests_per_run"]["value"], hosts=hosts, interval=ph["min_interval_s"]["value"], sleep=sleep)
        hg, hb = b(http_get), b(http_bytes)
        kw = {"sleep": sleep} if sleep else {}
        rep_ = {"searched": [], "saved": [], "not_used": {}, "status": "ok"}
        try:
            if need_search:
                entered, _no, r1 = inat_photos.build_table(need_search, http_get=hg, ph=ph, max_requests=max(b.left(), 1), **kw)
                rows += [{k: e[k] for k in ("name", "scientific", "taxon_id")} for e in entered]
                rep_["searched"] = [e["name"] for e in entered]
                if entered:                                                                # 段階39: 表に入った行は手元の書き出しに残す（次の実行で探し直さない）
                    guide_photos.add_to_table(entered, "野鳥", self.env) if self.env else guide_photos.add_to_table(entered, "野鳥")
                if r1["status"] != "ok":
                    rep_["status"] = r1["status"]
            todo = [r for r in rows if not has(r["taxon_id"])]
            if todo and b.left() >= 2 and rep_["status"] == "ok":
                got, unused, r2 = inat_photos.fetch_photos(todo, http_get=hg, http_bytes=hb, ph=ph, max_requests=b.left(), has_cache=has,
                                                           skip_photos=guide_photos.load_skip_photos(self.env) if self.env else guide_photos.load_skip_photos(), **kw)
                for item in got:
                    save(item)
                rep_["saved"] += [i["row"]["name"] for i in got]
                rep_["not_used"].update(unused)
                rep_["status"] = r2["status"]
            # iNaturalist に使える写真がない種だけ、Commons(承認済みの通信先)から。少ない種数だけ
            cap = self.policy["net"]["page_photos_commons_max_species"]["value"]
            nocache = [r for r in rows if not has(r["taxon_id"]) and r["name"] in rep_["not_used"] and f"commons:{r['taxon_id']}" not in review][:cap]
            if nocache:
                cm = ph["commons"]
                hs = cfg["live"]["allowed_hosts_by_subject"]
                cb = self.budget("photos_commons", cm["max_requests_per_run"]["value"], hosts=hs["guide_photos_commons"] + hs["guide_places"],
                                 interval=cm["min_interval_s"]["value"], sleep=sleep)
                got, _un, _r3 = commons_photos.fetch_commons(nocache, http_get=cb(http_get), http_bytes=cb(http_bytes), ph=ph, max_requests=cb.left(),
                                                             has_cache=has, on_got=save, **kw)
                rep_["saved"] += [i["row"]["name"] for i in got]
                rep_["commons_net"] = cb.summary()
        except LiveError as e:                         # 上限・許可ホストの外: そこで止める(写真なしで出す)
            rep_["status"] = "stopped"
            rep_["error"] = str(e)[:200]
        finally:
            if getter is not None:
                getter.close()
        found = {r["name"]: r["taxon_id"] for r in rows}
        tried_none = [n for n in seen if n not in found and n in need_search and n not in rep_["searched"] and rep_["status"] == "ok"]             + [r["name"] for r in rows if not has(r["taxon_id"]) and r["name"] in rep_["not_used"]]
        if tried_none:                                                                  # 取りに行って使える写真がなかった種だけ記録する（上限・停止で届かなかった種は記録しない）
            nc = dict(none_cache)
            for n in tried_none:
                nc[n] = {"on": today.isoformat(), "reason": rep_["not_used"].get(n, "対応表に入らなかった")}
            guide_photos._save_none(nc, self.env) if self.env else guide_photos._save_none(nc)
        out = {"ran": True, **rep_, "net": b.summary(),
               "species": [{"name": n, "taxon_id": found.get(n), "photo": bool(found.get(n) and has(found[n]))} for n in seen]}
        self._save("photos.json", out)
        self.call("photos", requests=b.used, saved=len(rep_["saved"]), status=rep_["status"])
        return out

    def plan_photos(self, facts_doc, http_get=None, http_bytes=None):
        """計画に載る種のうち、写真のキャッシュにないものを、対象ごとに補う(確認なし。承認B。取れなければ名前だけの行)。"""
        from . import guide_photos, plan_page
        plan_doc = self._load("answer_plan.json", None)
        if plan_doc is None:
            raise ValueError("answer_plan.json がない(先に plan を実行する)")
        out = {"ran": False, "subjects": {}}
        for sj, names in plan_page.species_by_subject(facts_doc, plan_doc, self.policy["plan_page"]).items():
            res = guide_photos.ensure_for_page(names, plan_page.SUBJECT_WORD[sj], http_get=http_get, http_bytes=http_bytes, env=self.env)
            out["subjects"][sj] = {"names": names, "requests": (res or {}).get("requests"), "saved": (res or {}).get("saved"), "status": (res or {}).get("status")}
            out["ran"] = out["ran"] or res is not None
        self._save("photos.json", out)
        self.call("photos", subjects=list(out["subjects"]))
        return out

    def plan_page(self, facts_doc, gazetteer=(), answer_path=None):
        """紅葉・花・総合のページ: 直前の答えの計画から作る。計画がなければ作らない。"""
        from . import guide, guide_page, guide_photos, plan_page
        plan_doc = self._load("answer_plan.json", None)
        if plan_doc is None:
            raise PageUnsupported(OF.load()["messages"]["no_recent_plan"])
        pol = guide.load_policy()
        gp = pol["photos"]
        table = guide_photos.load_table(self.env) if self.env else guide_photos.load_table()

        def photo_for(name):
            row = table.get(name)
            if not row:
                return None
            return guide_photos.load_photo(row["taxon_id"], self.env) if self.env else guide_photos.load_photo(row["taxon_id"])

        def credit(meta):
            return plan_page.author_credit(meta, gp, guide_page.state_text(meta, pol) if meta.get("rule") else None)
        pp = self.policy["plan_page"]
        ap = Path(answer_path) if answer_path else next((self.workdir / n for n in ("final.txt", "answer.txt") if (self.workdir / n).is_file()), None)
        answer = ap.read_text(encoding="utf-8") if ap and ap.is_file() else None
        html_text, lines, shown = plan_page.build(facts_doc, plan_doc, policy=pp, photo_for=photo_for, photo_credit=credit, now=self.now, answer=answer)
        gaz = sorted(set(place_names()) | set(gazetteer))
        chk = V.page_check(lines, facts_doc, gazetteer=gaz)
        d0 = (facts_doc.get("dates") or [self.now.date().isoformat()])[0]
        out = (guide_photos.page_dir(self.env) if self.env else guide_photos.page_dir()) / pp["file"].format(date=d0)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_text, encoding="utf-8", newline="\n")
        line = pp["reply_line"].format(path=str(out.resolve()))
        doc = {"path": str(out.resolve()), "line": line, "ok": chk["ok"], "errors": V.report_lines(chk),
               "spots": {k: [{"name": n, "photo": x} for n, x in v] for k, v in shown.items()}}
        self._save("page.json", doc)
        self.call("page", ok=chk["ok"], spots=len(shown))
        return doc

    # 3c. 写真つきの公園ページ(段階38)
    def page(self, gazetteer=(), answer_path=None):
        from . import guide, guide_photos, park_page
        from . import profiles as P
        facts_doc = self._load("facts.json", None)
        if facts_doc is None:
            raise ValueError("facts.json がない(先に facts を実行する)")
        if not OF.ask_subjects_supported(list(facts_doc.get("subjects") or {})):      # 段階57 第1部: 未対応の対象で、別のページ(野鳥)を黙って作らない
            raise PageUnsupported(OF.unsupported_theme_message())
        if list(facts_doc["subjects"]) != ["birds"]:                  # 段階57 第2部: 紅葉・花・総合は直前の答えの計画から
            return self.plan_page(facts_doc, gazetteer=gazetteer, answer_path=answer_path)
        gp = guide.load_policy()["photos"]
        table = guide_photos.load_table(self.env) if self.env else guide_photos.load_table()
        pinfo = {x["name"]: x.get("taxon_id") for x in (self._load("photos.json", {}) or {}).get("species") or []}

        def photo_for(b):
            tid = b.get("taxon_id") or pinfo.get(b["name"]) or (table.get(b["name"]) or {}).get("taxon_id")
            if not tid:
                return None
            return guide_photos.load_photo(tid, self.env) if self.env else guide_photos.load_photo(tid)
        care = P.load_profiles()["birds"]["care"]["manners"]
        ap = Path(answer_path) if answer_path else next((self.workdir / n for n in ("final.txt", "answer.txt") if (self.workdir / n).is_file()), None)
        answer = ap.read_text(encoding="utf-8") if ap and ap.is_file() else None             # 答えの結論と順位をページの先頭に使う
        html_text, lines, shown = park_page.build(facts_doc, policy=self.policy["park_page"], photo_for=photo_for, author_re=gp["html"]["author_re"],
                                                  commons_source_id=gp["commons"]["source_id"], now=self.now, care=care, answer=answer)
        gaz = sorted(set(place_names()) | set(gazetteer))
        chk = V.page_check(lines, facts_doc, gazetteer=gaz)
        d0 = (facts_doc.get("dates") or [self.now.date().isoformat()])[0]
        out = (guide_photos.page_dir(self.env) if self.env else guide_photos.page_dir()) / self.policy["park_page"]["file"].format(date=d0)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_text, encoding="utf-8", newline="\n")
        line = self.policy["park_page"]["reply_line"].format(path=str(out.resolve()))
        doc = {"path": str(out.resolve()), "line": line, "ok": chk["ok"], "errors": V.report_lines(chk),
               "parks": [{"name": k, "birds": [{"name": n, "photo": x} for n, x in v]} for k, v in shown.items()]}
        self._save("page.json", doc)
        self.call("page", ok=chk["ok"], parks=len(shown))
        return doc

    def offers_now(self, facts_doc, plan_doc=None):
        """答えの末尾に付けてよい案内の一覧。写真の候補は、対象ごとの載せられる種名。"""
        from . import park_page, plan_page
        subs = list(facts_doc.get("subjects") or {})
        if subs == ["birds"]:
            has = any(c.get("park_birds") for c in park_page.parks(facts_doc, self.policy["park_page"]))
        else:
            has = bool(plan_doc) and plan_page.has_photo_candidates(facts_doc, plan_doc, self.policy["plan_page"])
        from . import compare
        return OF.available({"subject_supported": OF.ask_subjects_supported(subs), "plan": True, "photo_candidates": has,
                             "compare_history": compare.can_compare(self.now, self.env, pending=1)})

    # 3d. 答えの計画(段階56)。facts.json から、狙い別の節・今回のおすすめ・不採用の理由をコードで決める
    def area_plan(self, names, subject=None):
        """エリアごとの計画(段階58 第1部)。辞書にない名前は lines.area_unknown に 1 文で残す。"""
        from . import areas as AR
        facts_doc = self._load("facts.json", None)
        if facts_doc is None:
            raise ValueError("facts.json がない(先に facts を実行する)")
        subs = list(facts_doc["subjects"])
        sj = subject or subs[0]
        d = AR.describe(names)
        doc = AP.build_areas(facts_doc, d["found"], sj)
        doc["area_unknown"] = d["unknown"]
        doc["offers"] = []
        self._save("answer_plan.json", doc)
        save_last_plan(self.workdir, facts_doc, doc, self.now, self.env)
        self.call("plan", subject="areas", picks=len(doc["picks"]), sections=len(doc["segments"]), overrides=0)
        return doc

    def plan(self, subject=None, override=None, reason=None, replace=None, refine=None):
        facts_doc = self._load("facts.json", None)
        if facts_doc is None:
            raise ValueError("facts.json がない(先に facts を実行する)")
        subs = list(facts_doc["subjects"])
        if facts_doc.get("periods"):                                  # 段階57 第9部: 期間が 2 つ。期間ごとの計画
            doc = AP.build_periods(facts_doc)
            doc["offers"] = []
            self._save("answer_plan.json", doc)
            save_last_plan(self.workdir, facts_doc, doc, self.now, self.env)
            self.call("plan", subject="periods", picks=len(doc["picks"]), sections=len(doc["segments"]), overrides=0)
            return doc
        sj = subject or ("all" if len(subs) > 1 else subs[0])         # 対象が複数の質問(総合)は all
        old = self._load("answer_plan.json", None)
        keep = (old or {}).get("overrides") if old and old.get("subject") == sj else []
        refine = refine or (None if override is None else (old or {}).get("refine"))
        doc = AP.build_all(facts_doc, overrides=keep, refine=refine) if sj == "all" else AP.build(facts_doc, sj, overrides=keep, refine=refine)
        if override:
            AP.add_override(doc, override, reason, replace=replace, at=self.now.isoformat())
        doc["offers"] = self.offers_now(facts_doc, doc)               # 段階57 第1部: この答えの末尾に付けてよい案内(条件を満たすものだけ)
        self._save("answer_plan.json", doc)
        save_last_plan(self.workdir, facts_doc, doc, self.now, self.env)   # 段階57 第2部: 直前の答えの計画(ページ・追質問が引き継ぐ)
        self.call("plan", subject=sj, picks=len(doc["picks"]), sections=len(doc["sections"]), overrides=len(doc["overrides"]))
        return doc

    # 4. 検査
    def verify(self, text, gazetteer=(), reply=False):
        facts_doc = self._load("facts.json", None)
        if facts_doc is None:
            raise ValueError("facts.json がない(先に facts を実行する)")
        gaz = sorted(set(place_names()) | set(gazetteer))
        if reply:                                     # 段階38: 利用者への返事の全文(答えの本文 + ページの場所の 1 行)
            r = V.reply_check(text, facts_doc, gazetteer=gaz, page_line=(self._load("page.json", {}) or {}).get("line"),
                              offers=OF.texts((self._load("answer_plan.json", None) or {}).get("offers")))
            self._save("check_reply.json", r)
            final = text if r["ok"] else V.strip(r["checked_text"], r)
            (self.workdir / "final_reply.txt").write_text(final, encoding="utf-8")
            self.call("verify", reply=True, ok=r["ok"], errors=len(V.report_lines(r)))
            return r, final
        r = V.check(text, facts_doc, gazetteer=gaz, plan=self._load("answer_plan.json", None))
        self._save("check.json", r)
        final = text if r["ok"] else V.strip(text, r)
        (self.workdir / "final.txt").write_text(final, encoding="utf-8")
        update_last_plan_answer(self.workdir, final, self.env)
        self.call("verify", ok=r["ok"], errors=len(V.report_lines(r)))
        return r, final


def run(params, *, workdir, fetcher=None, now=None, env=None, clock=None, obs_kw=None):
    """手順をまとめて流す(テストのため)。fetcher(plan_doc) → (読んだ事実の配列, fetch_log)。
    記録が新しければ fetcher を呼ばない。同じ質問の中で取りに行くのは 1 回だけ。"""
    f = Flow(workdir, now=now, env=env, clock=clock, obs_kw=obs_kw)
    subjects, region, dates, origin = params["subjects"], params.get("region"), params["dates"], params.get("origin")
    p = f.prepare(subjects, region, dates, origin)
    log = {}
    if p["needs_fetch"] and fetcher is not None:
        reads, log = fetcher(p)
        if reads:
            bp = Path(workdir) / "reads.json"
            bp.write_text(json.dumps(reads, ensure_ascii=False), encoding="utf-8")
            f.record(bp)
    doc = f.facts(subjects, region, dates, origin, fetch_log=log, plan_doc=f._load("plan.json", p))
    f.save_calls()
    return f, doc


# ---- CLI ----

def _out(doc):
    sys.stdout.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")


def main(argv=None, http_get=None):
    ap = argparse.ArgumentParser(prog="ask", description="生き物の質問に答える手順(prepare → 読む → record → facts → 答えを書く → verify)")
    sub = ap.add_subparsers(dest="step", required=True)
    for name in ("prepare", "facts"):
        p = sub.add_parser(name)
        p.add_argument("--out-dir", required=(name != "prepare"))
        p.add_argument("--subject", action="append", choices=O.load_policy()["subjects"])
        p.add_argument("--region")
        p.add_argument("--when", help="明日 / 今日 / 今週末 / YYYY-MM-DD[,YYYY-MM-DD]")
        p.add_argument("--origin")
        p.add_argument("--now")
        if name == "facts":
            p.add_argument("--periods", help="期間が 2 つの質問(「今週末か来週末」): 2026-11-07,2026-11-08;2026-11-14,2026-11-15")
            p.add_argument("--fetch-log", help="読んだ・読めなかったページ {read:[{url,publisher}], failed:[{url,reason}]}")
    p = sub.add_parser("inat-refresh")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--now")
    p = sub.add_parser("record")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--batch", required=True)
    p = sub.add_parser("photos", help="答えに載る種の写真のうち、手元にないものを取りに行く(段階38・57。上限の範囲)")
    p.add_argument("--out-dir", help="作業フォルダ(省くと直前の計画)")
    p = sub.add_parser("page", help="直前の答えの写真つきページ(野鳥は公園ごと。紅葉・花・総合は計画から。段階38・57)")
    p.add_argument("--out-dir", help="作業フォルダ(省くと直前の計画。24時間より前・なければ作らない)")
    p.add_argument("--open", action="store_true", help="手元のブラウザで開く")
    p.add_argument("--answer", default=None, help="答えの文章のファイル(省略: 作業フォルダの final.txt か answer.txt)。ページの結論・順位に使う")
    p = sub.add_parser("plan", help="答えの計画(狙い別の節・今回のおすすめ・不採用の理由)をコードで作る(段階56)")
    p.add_argument("--out-dir", help="作業フォルダ(--refine のときは省くと直前の計画)")
    p.add_argument("--area", action="append", default=[], help="エリア名(複数可)。エリアごとの計画を作る(段階58)")
    p.add_argument("--area-question", help="質問の文からエリアを取り出して計画を作る(段階58)")
    p.add_argument("--refine", help="追質問の語(近場・山歩き・遠出・ライトアップなど)。同日の記録と計画だけで選び直す。通信しない(段階57)")
    p.add_argument("--subject", choices=list(O.load_policy()["subjects"]) + ["all"], help="省くと、対象が1つならそれ、複数なら all(総合)")
    p.add_argument("--explain", help="名所の順位・点数の内訳・不採用の理由を見る")
    p.add_argument("--override", help="計画にない名所を答えに足す(--reason が要る)")
    p.add_argument("--reason")
    p.add_argument("--replace", help="--override で差し替える計画の名所")
    p = sub.add_parser("verify")
    p.add_argument("--out-dir")
    p.add_argument("--text", required=True)
    p.add_argument("--generic", action="store_true", help="facts を持たない経路(桜・梅などの guide find の出力・検索だけの答え)の検査。--out-dir は不要(段階39 B-1)")
    p.add_argument("--reply", action="store_true", help="利用者への返事の全文を検査する(答えの本文の外の文も。ページの場所の 1 行は外す)")
    p.add_argument("--gazetteer", action="append", default=[], help="地名の一覧(JSON の文字列の配列)。名所カタログの名前に足す")
    p.add_argument("--clarify", action="store_true", help="--generic のとき: 対象・場所・日付のどれも特定できず、答えの代わりに聞き返す 1 文(段階57 第13部)")
    p.add_argument("--theme", help="--generic のとき: 答えのテーマの語。写真つきページに未対応のテーマなら、案内の文を不合格にする(段階57)")
    p = sub.add_parser("refresh", help="答えの前に読むページの一覧(計画の上位候補のうち現況が古い・ないもの。最大 8 ページ・同日は除く。読むのはエージェントの道具。段階57)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--plan", action="store_true", help="計画の上位候補から(既定)")
    p = sub.add_parser("place-alias", help="確かめた場所の別名を手元に足す(段階58。次回から使う)")
    p.add_argument("--add", required=True, help="別名")
    p.add_argument("--official", required=True, help="正式名称")
    p = sub.add_parser("compare", help="ここまでの候補の比較表をコードで作る(履歴の計画が 2 件以上のとき。段階58)")
    p = sub.add_parser("import-csv", help="公式の機械可読データの本文を記録にする(段階57。山梨県の紅葉状況 CSV。承認されるまで答えには出ない。本文は保存しない)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--csv", required=True, help="読んだ CSV の本文のファイル")
    p.add_argument("--csv-url", required=True, help="ページのリンクから辿った CSV の URL")
    p.add_argument("--updated", required=True, help="ページの更新日 YYYY-MM-DD")
    p = sub.add_parser("place", help="場所を指定した質問: 名所の一覧との照合と、場所ごとの事実。一覧にない場所は検索語を返す(段階57。通信しない)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--question", help="質問の文(場所名を取り出す)")
    p.add_argument("--name", action="append", default=[], help="場所名(複数可)")
    p.add_argument("--subject", default="autumn_leaves")
    p = sub.add_parser("origin", help="質問の文から出発地を決める(追質問だけ前の出発地を引き継ぐ。段階57)")
    p.add_argument("--question", help="質問の文")
    p.add_argument("--follow-up", action="store_true", help="直前の質問の追質問(同じ話題の続き)のとき")
    p.add_argument("--add", help="Wikidata で確かめた出発地を手元に足す(--lat --lon --qid)")
    p.add_argument("--lat", type=float)
    p.add_argument("--lon", type=float)
    p.add_argument("--qid")
    p.add_argument("--prefecture")
    p = sub.add_parser("unsupported", help="今できないことを頼まれたときの 1 行(と、条件を満たす別の案内)。段階57 第1部")
    p.add_argument("--what", required=True, help="今できないこと(例: 紅葉の写真つきページ)")
    p.add_argument("--out-dir", help="作業フォルダ(あれば、計画の案内を添える)")
    a = ap.parse_args(argv)
    pol = load_policy()
    out_dir = a.out_dir
    if (a.step in ("page", "photos") or (a.step == "plan" and a.refine)) and not out_dir:      # 段階57 第2部: 「写真つきのページにして」は直前の答えを引き継ぐ。なければ別の内容を作らない
        last = load_last_plan(_clock())
        if last is None:
            print(OF.load()["messages"]["no_recent_plan"], file=sys.stderr)
            return 2
        out_dir = str(restore_workdir(last))
    params = {}
    if out_dir and Path(out_dir, "params.json").exists():
        params = json.loads(Path(out_dir, "params.json").read_text(encoding="utf-8"))
    now = S.parse_now(a.now) if getattr(a, "now", None) else (S.parse_now(params["now"]) if params.get("now") and a.step != "prepare" else None)
    if out_dir is None:
        t = now or _clock()
        out_dir = str(data_path(pol["work_dir"]) / t.strftime("%Y%m%d-%H%M%S"))
    if a.step == "place-alias":
        from . import place_answer as PA
        PA.add_alias(a.add, a.official)
        return 0
    if a.step == "compare":                              # 段階58 第5部: 履歴がなければ作らない
        from . import compare
        text, urls = compare.table(_clock())
        if text is None:
            print(OF.load()["messages"]["no_recent_plan"], file=sys.stderr)
            return 2
        print(text + ("\n" + AP.load_policy()["compare"]["sources_heading"] + "\n" + "\n".join(urls) if urls else ""))
        return 0
    if a.step == "origin":                               # 段階57 第8部
        if a.add:
            if a.lat is None or a.lon is None or not a.qid:
                print("--lat --lon --qid が要ります", file=sys.stderr)
                return 2
            _out(origins.add_to_cache(a.add, a.lat, a.lon, a.qid, a.prefecture))
            return 0
        last = load_last_plan(_clock()) if a.follow_up else None
        _out(origins.choose(a.question, a.follow_up, (last or {}).get("origin")))
        return 0
    if a.step == "unsupported":                          # 段階57 第1部: 1 行の案内と、確実にできる別のことだけ
        plan = {}
        if a.out_dir and Path(a.out_dir, "answer_plan.json").exists():
            plan = json.loads(Path(a.out_dir, "answer_plan.json").read_text(encoding="utf-8"))
        print("\n".join(OF.unsupported_reply(a.what, plan.get("offers") or [])))
        return 0
    if a.step == "verify" and a.generic:                 # 段階39 B-1: facts を持たない経路。出す前に必ず通す。落ちた行は利用者に見せない
        text = Path(a.text).read_text(encoding="utf-8")
        offers_ok = None
        if a.theme:
            from . import guide as _G
            _pol = _G.load_policy()
            _themes, _ = _G.themes_for_words([a.theme], _pol)
            wf = a.theme in (_pol.get("wildflower") or {}).get("words", [])
            offers_ok = OF.all_texts() if wf or OF.guide_themes_supported(_themes) else []
        r = V.generic_check(text, offers=offers_ok, clarify=a.clarify)
        for e in r["errors"]:
            print(f"NG  [{e['code']}] {e.get('line') or '(全体)'}: {e['detail']}", file=sys.stderr)
        final = text if r["ok"] else V.generic_strip(text, r)
        fp = Path(a.text).with_name("final.txt")
        fp.write_text(final, encoding="utf-8")
        print(("合格: " if r["ok"] else "不合格(通らない行を除いた答えを書きました): ") + str(fp))
        return 0 if r["ok"] else 1
    flow = Flow(out_dir, now=now)
    try:
        if a.step in ("prepare", "facts"):
            subjects = a.subject or params.get("subjects") or pol["default_subjects"]
            region = a.region if a.region is not None else (params.get("region") or pol.get("default_region"))     # 指定がなければ登録済みの全範囲
            origin = a.origin or params.get("origin")
            dates = parse_dates(a.when, flow.now) if a.when else ([date.fromisoformat(x) for x in params["dates"]] if params.get("dates")
                                                                  else parse_dates(None, flow.now))
            if a.step == "prepare":
                _out(flow.prepare(subjects, region, dates, origin))
                return 0
            log = json.loads(Path(a.fetch_log).read_text(encoding="utf-8")) if a.fetch_log else {}
            periods = None
            if a.periods:
                periods = [[date.fromisoformat(x) for x in chunk.split(",")] for chunk in a.periods.split(";")]
                dates = periods[0]
            _out(flow.facts(subjects, region, dates, origin, fetch_log=log, periods=periods))
            return 0
        if a.step == "inat-refresh":
            out = flow.inat_refresh(http_get=http_get)
            _out(out)
            return 0
        if a.step == "record":
            out = flow.record(a.batch)
            _out(out)
            return 1 if out.get("rejected") else 0
        if a.step == "plan":
            if not a.out_dir and not a.refine:
                print("--out-dir が要ります(--refine のときだけ省けます)", file=sys.stderr)
                return 2
            if a.area or a.area_question:
                from . import areas as AR
                doc = flow.area_plan(a.area or AR.from_question(a.area_question), a.subject)
                _out(AP.explain(doc, a.explain) if a.explain else doc)
                return 0
            try:
                doc = flow.plan(subject=a.subject, override=a.override, reason=a.reason, replace=a.replace, refine=a.refine)
            except ValueError as ex:
                print(str(ex), file=sys.stderr)
                return 2
            _out(AP.explain(doc, a.explain) if a.explain else doc)
            return 0
        if a.step == "import-csv":
            from . import official_csv as CSV
            cfg = pol["official_csv"]["yamanashi"]
            recs = CSV.to_records(CSV.parse(Path(a.csv).read_text(encoding="utf-8")), csv_url=a.csv_url, updated=a.updated,
                                  prefecture=cfg["prefecture"], publisher=cfg["publisher"], label=cfg["label"])
            for r in recs:
                if r["name"] in cfg["spot_map"]:
                    r["spot"] = cfg["spot_map"][r["name"]]
            bp = Path(out_dir) / "reads_csv.json"
            bp.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
            out = flow.record(bp)
            _out({k: out.get(k) for k in ("written", "duplicates")} | {"rejected": len(out.get("rejected") or []), "submitted": len(recs)})
            return 1 if out.get("rejected") else 0
        if a.step == "place":
            from . import place_answer as PA
            facts_doc = flow._load("facts.json", None)
            if not facts_doc:
                print("先に facts を実行してください", file=sys.stderr)
                return 2
            names = a.name or PA.extract_names(a.question)
            res = PA.plan_for(names, a.subject, facts_doc)
            _out({"found": [{"query": x["query"], "name": x["candidate"]["name"], "section": x["section"]} for x in res["found"]], "missing": res["missing"]})
            return 0
        if a.step == "refresh":
            facts_doc = flow._load("facts.json", None)
            plan_doc = flow._load("answer_plan.json", None)
            if not facts_doc or not plan_doc:
                print("先に facts と plan を実行してください", file=sys.stderr)
                return 2
            _out({"pages": AP.refresh_targets(facts_doc, plan_doc, fetched_today(flow.now))})
            return 0
        if a.step == "photos":
            _out(flow.photos())
            return 0
        if a.step == "page":
            try:
                doc = flow.page(answer_path=a.answer)
            except PageUnsupported as ex:
                print(str(ex), file=sys.stderr)
                return 2
            for line in doc["errors"]:
                print(line, file=sys.stderr)
            print(doc["line"])
            if a.open:
                if hasattr(os, "startfile"):
                    os.startfile(doc["path"])
                else:
                    import webbrowser
                    webbrowser.open(Path(doc["path"]).as_uri())
            return 0 if doc["ok"] else 1
        if a.step == "verify":
            gaz = [n for g in a.gazetteer for n in load_gazetteer_file(g)]
            r, _final = flow.verify(Path(a.text).read_text(encoding="utf-8"), gaz, reply=a.reply)
            for line in V.report_lines(r):
                print(line, file=sys.stderr)
            name = "final_reply.txt" if a.reply else "final.txt"
            print(("合格: " if r["ok"] else "不合格(通らない文を除いた答えを書きました): ") + str(Path(out_dir) / name))
            return 0 if r["ok"] else 1
    finally:
        flow.save_calls()
    return 2


if __name__ == "__main__":
    sys.exit(main())
