"""段階85 第3部: 取りこぼしの点検(ask audit)。通信しない。

記録にある種・テーマ(名所カタログ・ガイドのカタログ・読んだ事実の記録・行事)ごとに、代表的な質問を作って資料(ask brief と同じ build。
読み直しはしない)を作り、その種・その月・その場所に当たる記録のうち、資料に入らなかったものを数えて、理由を分ける:
  上限で外れた(件数の枠)/時期の読み取りに失敗/種の名前が結びつかない/場所が結びつかない/規約・承認のため出せない/取り下げ済み/そのほか。
質問の型(指示書 段階85 3.1):
  species: 「(種)はいつどこで見られますか?」(日付の指定なし。範囲の中の、その種の名所すべてが対象)
  month:   「(月)の週末、(種)を見たい」(その月の中ごろの週末。例年の時期がその日に当たる名所と、その週末の行事が対象)
  place:   「(都県)で見られる花は?」(その都県の、花の名所が対象)
「資料に入った」とは、候補・確かめた事実・知識カードのどこかに名所の名前(空白・括弧を除いて)が出ること。
値と語は data/ask/guide_mode.yaml の audit。"""
import json
import re
import shutil
import time
import unicodedata
from datetime import date, datetime, timedelta

NL = "\n"
REASONS = ("limit", "no_season", "season_parse", "species_link", "place_link", "terms", "retired", "other")


def cfg():
    from . import guide_brief as GB
    return GB.cfg()["audit"]


def _origin():
    from . import ask
    return cfg().get("origin") or ask.load_policy()["default_origin"]


def key(name):
    return re.sub(r"[\s()（）・「」『』]", "", unicodedata.normalize("NFKC", name or ""))


# ---- 記録の側(期待する名所) ----

def _raw_records(subject, env=None):
    """記録のファイルの行(読むときの絞り込みの前)。"""
    from . import observations as O
    p = O.log_path(subject, env)
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def _alias_hit(text, sp):
    """種の語(別名の読み替えのあと)が文字として含まれるか(種の名前の結びつきの点検用。ほかの種の長い語の除外はしない)。"""
    from . import species_alias
    if not text:
        return False
    t, _ = species_alias.normalize(text)
    words = [sp["name"]] + list(sp.get("match") or [])
    return any(w and (w in t or w in text) for w in words)


def expected(sp, origin, env=None):
    """種 → {key: {name, prefecture, km, start, end, season, why}}(範囲の中で、資料に入ってよい名所)と、
    資料に入れない理由がもともと決まっている名所 {key: (name, reason)}(場所が結びつかない・規約・取り下げ・名前が結びつかない)。"""
    from . import observations as O
    from . import season_place as SP
    c = SP.cfg()
    big = dict(c, max_items=10 ** 6, max_unknown_items=10 ** 6)
    rows = SP.gather(sp, origin, c, env)
    linked = {key(r["name"]): r for r in rows}
    sel, _n = SP.select(rows, origin, None, big)
    keep = {key(r["name"]): r for r in sel}
    exp, fixed = {}, {}
    for k, r in keep.items():
        exp[k] = r
    from . import catalog as CM
    max_km = CM.load_policy()["range_limit"]["max_km"]
    for k, r in linked.items():
        if k in keep:
            continue
        if r.get("km") is None:
            fixed[k] = (r["name"], "place_link")              # 座標・市町村の代表点がなく、範囲を決められない
        # km > max_km は範囲の外(数えない)
    # 記録のファイルにあって、読むときに外れたもの(承認待ちの情報源・使わない情報源)と、種の名前が結びつかないもの
    pol = O.load_policy()
    for subj in ("flowers", "birds"):
        usable = {key(r.get("name")) for r in O.read_records(subj, env, pol, include_themes=True) if r.get("name")}
        for r in _raw_records(subj, env):
            nm = r.get("name")
            if not nm or not r.get("typical") or not _alias_hit(r.get("kind") or "", sp):
                continue
            k = key(nm)
            if k in linked or k in fixed:
                continue
            if k not in usable:
                fixed[k] = (nm, "terms")
            elif not SP._matches(r.get("kind") or "", list(sp["match"]) + list(sp.get("includes") or []), sp, c):
                fixed[k] = (nm, "species_link")
    for e in SP._flower_entries():
        t = e.get("tags") or {}
        k = key(e.get("name"))
        if k in linked or k in fixed:
            continue
        texts = list(t.get("flower_kinds") or []) + [w.get("kind") for w in e.get("flower_windows") or []]
        if any(_alias_hit(x, sp) for x in texts if x):
            fixed[k] = (e["name"], "species_link")
    _ = max_km
    return exp, fixed


def _in_window(day, start, end):
    md = day.strftime("%m-%d")
    if not start or not end:
        return False
    return start <= md <= end if start <= end else (md >= start or md <= end)


# ---- 資料の側 ----

def brief_keys(doc):
    """資料に出る名所の名前(比べる形)の集まりと、本文(部分一致を見るため)。"""
    names = set()
    for r in doc.get("candidates") or []:
        for n in [r.get("name"), *(r.get("merged_from") or [])]:
            if n:
                names.add(key(n))
    blob = []
    for f in doc.get("facts") or []:
        if f.get("place"):
            names.add(key(f["place"]))
        blob.append(f.get("content") or "")
    for k in doc.get("cards") or []:
        if k.get("place"):
            names.add(key(k["place"]))
        blob.append(" ".join(k.get("facts") or []))
    return names, key(" ".join(blob))


def present(k, names, blob):
    return k in names or (len(k) >= 3 and k in blob)


def _species_cap(doc, sp_name, c):
    """資料の、その種の名所の候補の数が枠に達しているか。"""
    from . import guide_brief as GB
    from . import season_place as SP
    n = sum(1 for r in doc.get("candidates") or [] if r.get("basis") in ("species", "typical", "current", "town") or r.get("rank") is not None)
    if doc.get("route") == "species_dated":              # 日付つきの種の質問は、今までの答えの経路の枠(season_place の max_items)で名所が選ばれる
        n_sp = sum(1 for r in doc.get("candidates") or [] if r.get("basis") == "species")
        return n_sp >= SP.cfg()["max_items"]
    return n >= GB.cfg()["species_rows"]["max_known"]


def classify(k, row, doc, sp, day=None):
    """資料に入らなかった名所の理由。"""
    if day is not None and not (row.get("start") and row.get("end")):
        return "season_parse"                            # 時期の文はあるが、月日の窓に読めない(その月に当たるか決められない)
    if day is None and not row.get("season"):
        return "no_season"                               # 例年の時期の記録がない、または出さない(紹介サイト 1 件だけの時期。段階23)。時期の分かる名所が多いときは資料に入れない決まり
    if _species_cap(doc, sp["name"], cfg()):
        return "limit"
    return "other"


# ---- 質問を作る ----

def month_of_rows(rows, n):
    """名所の時期の窓に多く当たる月(中ごろの日で数える)。多い順に n か月。"""
    cnt = {}
    for r in rows:
        for m in range(1, 13):
            if _in_window(date(2026, m, 15), r.get("start"), r.get("end")):
                cnt[m] = cnt.get(m, 0) + 1
    return [m for m, _ in sorted(cnt.items(), key=lambda x: (-x[1], x[0]))[:n]]


def questions(species=None, kinds=("species", "month", "place"), env=None):
    """→ [{kind, question, species, month?, prefecture?}]"""
    from . import season_place as SP
    C = cfg()
    out = []
    sps = [s for s in SP.cfg()["species"] if not species or s["name"] in species]
    origin = _origin()
    for sp in sps:
        if "species" in kinds:
            out.append({"kind": "species", "question": C["q_species"].format(sp=sp["name"]), "species": sp["name"]})
        if "month" in kinds:
            exp, _f = expected(sp, origin, env)
            for m in month_of_rows(exp.values(), C["months_per_species"]["value"] if isinstance(C["months_per_species"], dict) else C["months_per_species"]):
                out.append({"kind": "month", "question": C["q_month"].format(month=m, sp=sp["name"]), "species": sp["name"], "month": m})
    if "place" in kinds and not species:
        for pref in C["prefectures"]:
            out.append({"kind": "place", "question": C["q_place"].format(pref=pref), "prefecture": pref})
    return out


# ---- 1 問を点検する ----

def _mid_weekend(m, now):
    from .answer_run import month_weekend
    return month_weekend(f"{m}月の週末", now.date())


def check_one(q, *, now, env=None):
    from . import guide_brief as GB
    from . import season_place as SP
    C = cfg()
    t0 = time.monotonic()
    doc = GB.build(q["question"], now=now, env=env)
    try:
        shutil.rmtree(GB.brief_dir(env) / f"{doc['id']}.work", ignore_errors=True)
    except OSError:
        pass
    names, blob = brief_keys(doc)
    misses = []
    if q["kind"] in ("species", "month"):
        sp = next(s for s in SP.cfg()["species"] if s["name"] == q["species"])
        exp, fixed = expected(sp, _origin(), env)
        day = None
        if q["kind"] == "month":
            wk = _mid_weekend(q["month"], now)
            day = wk[0] if wk else None
            mw = f"{q['month']}月"
            exp = {k: r for k, r in exp.items() if day and (_in_window(day, r.get("start"), r.get("end")) or _in_window(wk[1], r.get("start"), r.get("end"))
                                                         or (not r.get("start") and mw in (r.get("season") or "")))}
        for k, r in exp.items():
            if not present(k, names, blob):
                misses.append({"name": r["name"], "reason": classify(k, r, doc, sp, day), "season": r.get("season"), "from": r.get("from")})
        for k, (nm, why) in fixed.items():
            if not present(k, names, blob) and q["kind"] == "species":
                misses.append({"name": nm, "reason": why, "season": None, "from": "fixed"})
        n_exp = len(exp) + (len(fixed) if q["kind"] == "species" else 0)
    else:
        from datetime import date as _date
        days = [_date.fromisoformat(x) for p in (doc.get("dates") or {}).get("periods") or [] for x in p]
        rows = _place_rows(q["prefecture"], env, days)
        for k, r in rows.items():
            if not present(k, names, blob):
                misses.append({"name": r["name"], "reason": "limit" if len(doc.get("candidates") or []) >= (C["place_cap"]["value"] if isinstance(C["place_cap"], dict) else C["place_cap"]) else "other",
                               "season": r.get("season"), "from": r.get("from")})
        n_exp = len(rows)
    return {**q, "brief": doc["id"], "route": doc.get("route"), "expected": n_exp, "missing": misses, "elapsed_s": round(time.monotonic() - t0, 1)}


def _place_rows(pref, env=None, days=None):
    """都県 → その都県の花の名所(名所カタログ・種の名所の行)のうち、対象の日(日付の指定がない質問は今週末)に例年の時期が当たるもの。
    花でない種(鳥・ホタルなど。audit.place_skip_species)は数えない。"""
    from . import season_place as SP
    skip = set(SP.cfg().get("bird_species") or []) | set(cfg().get("place_skip_species") or [])
    out = {}
    for sp in SP.cfg()["species"]:
        if sp["name"] in skip:
            continue
        for r in SP.gather(sp, _origin(), SP.cfg(), env):
            if r.get("prefecture") != pref or not (r.get("start") and r.get("end")):
                continue
            if days and not any(_in_window(d, r["start"], r["end"]) for d in days):
                continue
            out.setdefault(key(r["name"]), r)
    return out


# ---- まとめ ----

def run(qs, *, now, env=None, progress=None):
    res = []
    for i, q in enumerate(qs):
        try:
            r = check_one(q, now=now, env=env)
        except Exception as ex:                          # 1 問の失敗で点検を止めない(理由を残す)
            r = {**q, "error": f"{type(ex).__name__}: {str(ex)[:120]}", "expected": 0, "missing": []}
        res.append(r)
        if progress:
            progress(i + 1, len(qs), r)
    return res


def table(results):
    """理由ごとの件数(質問の型ごと)。"""
    t = {}
    for r in results:
        for m in r.get("missing") or []:
            t.setdefault(m["reason"], {}).setdefault(r["kind"], 0)
            t[m["reason"]][r["kind"]] += 1
    return t


def render(results, c=None):
    c = c or cfg()
    L = c["labels"]
    t = table(results)
    kinds = ("species", "month", "place")
    n_q = {k: sum(1 for r in results if r["kind"] == k) for k in kinds}
    n_e = {k: sum(r.get("expected") or 0 for r in results if r["kind"] == k) for k in kinds}
    out = ["| 理由 | " + " | ".join(f"{L['kinds'][k]}({n_q[k]}問・対象 {n_e[k]})" for k in kinds) + " | 計 |", "|---|" + "---|" * (len(kinds) + 1)]
    for rs in REASONS:
        row = t.get(rs) or {}
        out.append(f"| {L['reasons'][rs]} | " + " | ".join(str(row.get(k, 0)) for k in kinds) + f" | {sum(row.values())} |")
    errs = [r for r in results if r.get("error")]
    out.append("")
    if errs:
        out.append(f"点検できなかった質問 {len(errs)}: " + "、".join(f"{r['question']}({r['error']})" for r in errs))
        out.append("")
    out.append(c["list_heading"])
    out.append("")
    shown = 0
    for r in results:
        ms = [m for m in r.get("missing") or [] if m["reason"] not in ("limit", "terms")]
        if not ms:
            continue
        out.append(f"- {r['question']}(資料 {r.get('brief')}): " + "、".join(f"{m['name']}[{L['reasons'][m['reason']]}]" for m in ms))
        shown += 1
    if not shown:
        out.append("(なし)")
    return NL.join(out) + NL


__all__ = ["questions", "run", "render", "table", "check_one", "expected"]
