"""生き物の質問に答える手順(段階37。単体で完結する。通信は計測フックの下の iNaturalist の取り直しだけ)。

biyori-hub の concierge_skill/ask.py(段階H8〜H10)が行っていた生き物の手順を、イキモノビヨリの中に移した
(指示書 docs/stage37-H11-instructions.md 2-1)。単体で聞いても、ハブ経由で聞いても、同じコマンド・同じ記録の置き場所を使う。

  python -X utf8 -m ikimonobiyori.ask prepare [--out-dir DIR] [--subject S ...] [--region 語] [--when 明日|今日|今週末|YYYY-MM-DD[,..]] [--origin 横浜] [--now ISO]
  python -X utf8 -m ikimonobiyori.ask inat-refresh --out-dir DIR [--now ISO]     (計測フックの下だけ。呼ぶのは biyori-hub など計測フックを持つ側)
  python -X utf8 -m ikimonobiyori.ask record --out-dir DIR --batch reads.json
  python -X utf8 -m ikimonobiyori.ask facts --out-dir DIR [--fetch-log fetch_log.json]   (対象・地域・日は prepare の値を使う)
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

from . import ask_verify as V
from . import livegate, netbudget
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
        self.call("record", submitted=len(batch), written=out.get("written"), duplicates=out.get("duplicates"),
                  rejected=len(out.get("rejected") or []))
        return out

    # 3. 材料
    def facts(self, subjects, region, dates, origin=None, fetch_log=None, plan_doc=None):
        origin = origin or self.policy["default_origin"]
        plan_doc = plan_doc if plan_doc is not None else self._load("plan.json", None)
        subj = {s: O.facts(s, region=region, dates=dates, now=self.now, origin=origin, env=self.env, **self.obs_kw) for s in subjects}
        rnd = this_round(self._load("records.json", []), fetch_log or {}, plan_doc)
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
                         "scope": self.policy["scope_line"].format(labels="・".join(labels[s] for s in subjects))},
               "inat_refresh": inat, "notes": self.notes}
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
        rows, need_search, seen = [], [], []
        for c in park_page.parks(facts_doc, self.policy["park_page"]):
            for b in c["park_birds"]:
                if b["name"] in seen:
                    continue
                seen.append(b["name"])
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
        out = {"ran": True, **rep_, "net": b.summary(),
               "species": [{"name": n, "taxon_id": found.get(n), "photo": bool(found.get(n) and has(found[n]))} for n in seen]}
        self._save("photos.json", out)
        self.call("photos", requests=b.used, saved=len(rep_["saved"]), status=rep_["status"])
        return out

    # 3c. 写真つきの公園ページ(段階38)
    def page(self, gazetteer=()):
        from . import guide, guide_photos, park_page
        from . import profiles as P
        facts_doc = self._load("facts.json", None)
        if facts_doc is None:
            raise ValueError("facts.json がない(先に facts を実行する)")
        gp = guide.load_policy()["photos"]
        table = guide_photos.load_table(self.env) if self.env else guide_photos.load_table()
        pinfo = {x["name"]: x.get("taxon_id") for x in (self._load("photos.json", {}) or {}).get("species") or []}

        def photo_for(b):
            tid = b.get("taxon_id") or pinfo.get(b["name"]) or (table.get(b["name"]) or {}).get("taxon_id")
            if not tid:
                return None
            return guide_photos.load_photo(tid, self.env) if self.env else guide_photos.load_photo(tid)
        care = P.load_profiles()["birds"]["care"]["manners"]
        html_text, lines, shown = park_page.build(facts_doc, policy=self.policy["park_page"], photo_for=photo_for, author_re=gp["html"]["author_re"],
                                                  commons_source_id=gp["commons"]["source_id"], now=self.now, care=care)
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

    # 4. 検査
    def verify(self, text, gazetteer=(), reply=False):
        facts_doc = self._load("facts.json", None)
        if facts_doc is None:
            raise ValueError("facts.json がない(先に facts を実行する)")
        gaz = sorted(set(place_names()) | set(gazetteer))
        if reply:                                     # 段階38: 利用者への返事の全文(答えの本文 + ページの場所の 1 行)
            r = V.reply_check(text, facts_doc, gazetteer=gaz, page_line=(self._load("page.json", {}) or {}).get("line"))
            self._save("check_reply.json", r)
            final = text if r["ok"] else V.strip(r["checked_text"], r)
            (self.workdir / "final_reply.txt").write_text(final, encoding="utf-8")
            self.call("verify", reply=True, ok=r["ok"], errors=len(V.report_lines(r)))
            return r, final
        r = V.check(text, facts_doc, gazetteer=gaz)
        self._save("check.json", r)
        final = text if r["ok"] else V.strip(text, r)
        (self.workdir / "final.txt").write_text(final, encoding="utf-8")
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
            p.add_argument("--fetch-log", help="読んだ・読めなかったページ {read:[{url,publisher}], failed:[{url,reason}]}")
    p = sub.add_parser("inat-refresh")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--now")
    p = sub.add_parser("record")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--batch", required=True)
    p = sub.add_parser("photos", help="公園ごとの鳥の写真のうち、手元にないものを取りに行く(段階38。上限の範囲)")
    p.add_argument("--out-dir", required=True)
    p = sub.add_parser("page", help="公園ごとに見られる鳥の写真つきページ(段階38)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--open", action="store_true", help="手元のブラウザで開く")
    p = sub.add_parser("verify")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--reply", action="store_true", help="利用者への返事の全文を検査する(答えの本文の外の文も。ページの場所の 1 行は外す)")
    p.add_argument("--gazetteer", action="append", default=[], help="地名の一覧(JSON の文字列の配列)。名所カタログの名前に足す")
    a = ap.parse_args(argv)
    pol = load_policy()
    out_dir = a.out_dir
    params = {}
    if out_dir and Path(out_dir, "params.json").exists():
        params = json.loads(Path(out_dir, "params.json").read_text(encoding="utf-8"))
    now = S.parse_now(a.now) if getattr(a, "now", None) else (S.parse_now(params["now"]) if params.get("now") and a.step != "prepare" else None)
    if out_dir is None:
        t = now or _clock()
        out_dir = str(data_path(pol["work_dir"]) / t.strftime("%Y%m%d-%H%M%S"))
    flow = Flow(out_dir, now=now)
    try:
        if a.step in ("prepare", "facts"):
            subjects = a.subject or params.get("subjects") or pol["default_subjects"]
            region = a.region if a.region is not None else params.get("region")
            origin = a.origin or params.get("origin")
            dates = parse_dates(a.when, flow.now) if a.when else ([date.fromisoformat(x) for x in params["dates"]] if params.get("dates")
                                                                  else parse_dates(None, flow.now))
            if a.step == "prepare":
                _out(flow.prepare(subjects, region, dates, origin))
                return 0
            log = json.loads(Path(a.fetch_log).read_text(encoding="utf-8")) if a.fetch_log else {}
            _out(flow.facts(subjects, region, dates, origin, fetch_log=log))
            return 0
        if a.step == "inat-refresh":
            out = flow.inat_refresh(http_get=http_get)
            _out(out)
            return 0
        if a.step == "record":
            out = flow.record(a.batch)
            _out(out)
            return 1 if out.get("rejected") else 0
        if a.step == "photos":
            _out(flow.photos())
            return 0
        if a.step == "page":
            doc = flow.page()
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
