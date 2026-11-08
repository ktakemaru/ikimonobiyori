"""博物館などの行事・展示の台帳(段階61 第2部)。通信しない。台帳は data/facility_events/events.yaml、値と文は policy.yaml。
行事は現況ではない(色づき・開花・飛来の状況の代わりにしない)。年つきの日付で、書かれた曜日が暦と合うものだけを使う。
答えに出すのは、施設が承認(approval.status: approved)されているときだけ。承認待ちの施設の行事は出さない(承認は本人が行う)。"""
import re
import unicodedata
from datetime import date
from pathlib import Path


from . import yamlcache
from .paths import DATA_FILES_DIR

DIR = DATA_FILES_DIR / "facility_events"


def policy(path=None):
    return yamlcache.load(Path(path or DIR / "policy.yaml"))


def load(path=None):
    return yamlcache.load(Path(path or DIR / "events.yaml"))


def _wd(iso, pol):
    return pol["weekdays"][date.fromisoformat(iso).weekday()]


def validate(doc, pol=None):
    """→ エラーの一覧。曜日が暦と合わない・年のない日付・台帳にない施設・種類が一覧にない。"""
    pol = pol or policy()
    errs = []
    ids = {f["id"] for f in doc.get("facilities") or []}
    for f in doc.get("facilities") or []:
        if (f.get("approval") or {}).get("status") not in ("pending", "approved", "revoked"):
            errs.append(f"{f.get('id')}: approval.status がない")
    for e in doc.get("events") or []:
        t = e.get("title")
        if e.get("facility") not in ids:
            errs.append(f"{t}: 台帳にない施設")
        if e.get("kind") not in pol["kinds"]:
            errs.append(f"{t}: 種類は {pol['kinds']} のどれか")
        for k, wk in (("date", "weekday_text"), ("deadline", "deadline_weekday_text")):
            if e.get(k):
                try:
                    w = _wd(e[k], pol)
                except ValueError:
                    errs.append(f"{t}: {k} は年つきの日付(YYYY-MM-DD)")
                    continue
                if e.get(wk) and not str(e[wk]).startswith(w):
                    errs.append(f"{t}: {k} の曜日 {e[wk]} が暦({w})と合わない")
        if e.get("kind") == "展示" and not (e.get("start") and e.get("end")):
            errs.append(f"{t}: 展示は会期(start・end)が要る")
        if e.get("kind") != "展示" and not e.get("date") and not (e.get("start") and e.get("end")):     # 段階62 第6部: 数日にわたる行事は会期
            errs.append(f"{t}: 日付がない")
    return errs


def _approved(doc):
    return {f["id"]: f for f in doc.get("facilities") or [] if (f.get("approval") or {}).get("status") == "approved"}


def match(question, pol=None):
    """質問の文 → 行事の話題の一覧。行事の語(観察会・講座など)がなければ空。"""
    pol = pol or policy()
    q = question or ""
    if not any(w in q for w in pol["ask_words"]):
        return []
    tps = [k for k, ws in pol["topic_words"].items() if any(w in q for w in ws)]
    return tps or list(pol["topic_words"])


def _md_ja(iso):
    d = date.fromisoformat(iso)
    return f"{d.year}年{d.month}月{d.day}日"


def line(e, fac, pol=None):
    pol = pol or policy()
    if e["kind"] != "展示" and not e.get("date") and e.get("start") and e.get("end"):
        return pol["line_period"].format(facility=fac["name"], kind=e["kind"], title=e["title"], start=_md_ja(e["start"]), sw=_wd(e["start"], pol),
                                         end=_md_ja(e["end"]), ew=_wd(e["end"], pol), place=(e["place"] + "。") if e.get("place") else "")
    if e["kind"] == "展示":
        return pol["line_exhibition"].format(facility=fac["name"], kind=e.get("label") or e["kind"], title=e["title"],
                                             start=_md_ja(e["start"]), end=_md_ja(e["end"]))
    extra = []
    if e.get("deadline"):
        extra.append(pol["deadline"].format(date=_md_ja(e["deadline"]), weekday=_wd(e["deadline"], pol)))
    if e.get("capacity"):
        extra.append(pol["capacity"].format(n=e["capacity"]))
    if e.get("target"):
        extra.append(pol["target"].format(target=e["target"]))
    return pol["line_event"].format(facility=fac["name"], kind=e["kind"], title=e["title"], date=_md_ja(e["date"]), weekday=_wd(e["date"], pol),
                                    time=" " + e["time"] if e.get("time") else "", place=(e["place"] + "。") if e.get("place") else "",
                                    extra="、".join(extra) + ("。" if extra else ""))


def period_of(question, today, pol=None):
    """段階62 第6部: 質問の期間の語 → (始まり, 終わり)。「12月」のような月も。なければ None(今日以降すべて)。"""
    import calendar
    from datetime import timedelta
    pol = pol or policy()
    q = question or ""
    key = next((v for k, v in pol.get("period_words", {}).items() if k in q), None)
    if key == "today":
        return today, today
    if key == "tomorrow":
        return today + timedelta(days=1), today + timedelta(days=1)
    if key in ("this_weekend", "next_weekend"):
        from . import sources as S
        from datetime import datetime
        wk = S.next_weekend(datetime(today.year, today.month, today.day))
        wk = [d.date() if hasattr(d, "date") and not isinstance(d, date) else d for d in wk]
        if key == "next_weekend":
            wk = [d + timedelta(days=7) for d in wk]
        return min(wk), max(wk)
    if key in ("this_month", "next_month"):
        y, m = today.year, today.month
        if key == "next_month":
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return (today if key == "this_month" else date(y, m, 1)), date(y, m, calendar.monthrange(y, m)[1])
    mm = re.search(pol.get("month_re") or r"$^", q)
    if mm and 1 <= int(mm.group(1)) <= 12:
        m = int(mm.group(1))
        y = today.year if m >= today.month else today.year + 1
        return max(today, date(y, m, 1)), date(y, m, calendar.monthrange(y, m)[1])
    return None


def lines_for(question, today, doc=None, pol=None, prefecture=None):
    """質問の文 → (行の一覧, 出典の URL)。承認済みの施設の、今日以降の行事・会期中かこれからの展示だけ。曜日が合わないものは出さない。"""
    pol = pol or policy()
    if doc is None:                                                        # 段階62 第6部: 行事の台帳と記録済みの行事をまとめた索引
        from . import event_index as EI
        doc = EI.build(today, pol=pol)
    tps = match(question, pol)
    if not tps or validate(doc, pol):
        return [], []
    if prefecture is None:                                                      # 段階62 第6部: 「神奈川・東京」のように複数の都県も
        prefs = [p for k, ps in pol["regions"].items() if k in (question or "") for p in ps]
    else:
        prefs = [prefecture] if isinstance(prefecture, str) else list(prefecture)
    win = period_of(question, today, pol)
    facs = _approved(doc)
    out, urls = [], []
    for e in sorted(doc.get("events") or [], key=lambda x: (x.get("date") or x.get("start") or "", x.get("title") or "")):
        fac = facs.get(e["facility"])
        if not fac or (prefs and fac.get("prefecture") not in prefs):
            continue
        if not set(e.get("topics") or []) & set(tps):
            continue
        last = e.get("end") or e.get("date")
        if date.fromisoformat(last) < today:
            continue
        first = e.get("date") or e.get("start")
        if win and (date.fromisoformat(last) < win[0] or date.fromisoformat(first) > win[1]):
            continue
        out.append(line(e, fac, pol))
        urls.append(e["url"])
    return out, sorted(set(urls))


_URL = re.compile(r"https?://[^\s)）」』、,]+")
_DATE_Y = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日(?:\(([月火水木金土日])\))?")
_DATE_NOY = re.compile(r"(?<![\d年])\d{1,2}月\d{1,2}日|(?<![\d/])\d{1,2}/\d{1,2}(?![\d/])")
_TIME = re.compile(r"\d{1,2}時(?:\d{1,2}分)?")
_SPLIT = r"[\s、。,:「」()]"


def _nz(s):
    return unicodedata.normalize("NFKC", str(s or ""))


def _fmt_re(template, key, group):
    """方針の文(「定員{n}人」)→ 値を取り出す正規表現。"""
    return re.compile(re.escape(_nz(template)).replace(re.escape("{" + key + "}"), group))


def _blob(e, fac):
    vals = [fac.get("name")] + [v for k, v in e.items() if isinstance(v, (str, int)) and not isinstance(v, bool) and k != "url"]
    vals += [_md_ja(e[k]) for k in ("date", "deadline", "start", "end") if e.get(k)]
    return _nz(" ".join(str(v) for v in vals if v is not None))


def _line_errors(line, e, pol):
    errs = []
    allowed = {e[k] for k in ("date", "deadline", "start", "end") if e.get(k)}
    found = set()
    for m in _DATE_Y.finditer(line):
        iso = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        found.add(iso)
        if iso not in allowed:
            errs.append({"code": "event_date_mismatch", "detail": f"{e['title']}: {m.group(0)}"})
            continue
        if m.group(4) and m.group(4) != _wd(iso, pol):
            errs.append({"code": "event_weekday_mismatch", "detail": f"{e['title']}: {m.group(0)}(暦は{_wd(iso, pol)})"})
        if not m.group(4) and iso in {e.get("date"), e.get("deadline")} | ({e.get("start"), e.get("end")} if e["kind"] != "展示" and not e.get("date") else set()):
            errs.append({"code": "event_weekday_missing", "detail": f"{e['title']}: {m.group(0)}"})
    for m in _DATE_NOY.finditer(line):
        errs.append({"code": "event_date_no_year", "detail": f"{e['title']}: {m.group(0)}"})
    need = [e["start"], e["end"]] if (e["kind"] == "展示" or not e.get("date")) else [e["date"]]
    for iso in need:
        if iso not in found:
            errs.append({"code": "event_date_missing", "detail": f"{e['title']}: {_md_ja(iso)}"})
    times = set(_TIME.findall(_nz(e.get("time"))))
    for tm in _TIME.findall(line):
        if tm not in times:
            errs.append({"code": "event_time_mismatch", "detail": f"{e['title']}: {tm}"})
    for m in _fmt_re(pol["capacity"], "n", r"(\d+)").finditer(line):
        if m.group(1) != str(e.get("capacity")):
            errs.append({"code": "event_capacity_mismatch", "detail": f"{e['title']}: {m.group(0)}"})
    for m in _fmt_re(pol["target"], "target", r"([^。、]+)").finditer(line):
        if m.group(1) != _nz(e.get("target")):
            errs.append({"code": "event_target_mismatch", "detail": f"{e['title']}: {m.group(0)}"})
    return errs


def answer_errors(text, today, doc=None, pol=None):
    """行事の答えの検査(知識カードの検査の代わり)。→ [{"code", "detail"}]。
    (a) 出る行事は台帳の承認済みの施設のもので、会期(開催日)が today 以降 (b) 日付は台帳と一致・年つき・曜日が暦と一致、時刻・定員・対象も台帳の値
    (c) 出典の URL はその行事の URL (d) 台帳にない数字・行事の名前・施設の名前・URL がない。"""
    pol = pol or policy()
    doc = doc if doc is not None else load()
    t = _nz(text)
    body = _URL.sub(" ", t)
    lines = body.splitlines()
    facs = {f["id"]: f for f in doc.get("facilities") or []}
    approved = _approved(doc)
    errs, shown = [], []
    for e in doc.get("events") or []:
        rows = [ln for ln in lines if _nz(e.get("title")) in ln]
        if not rows:
            continue
        fac = facs.get(e.get("facility")) or {}
        if e.get("facility") not in approved:
            errs.append({"code": "event_not_approved", "detail": e["title"]})
            continue
        if validate({"facilities": [fac], "events": [e]}, pol):
            errs.append({"code": "event_invalid_in_ledger", "detail": e["title"]})
            continue
        if date.fromisoformat(e.get("end") or e["date"]) < today:
            errs.append({"code": "event_past", "detail": e["title"]})
            continue
        shown.append((e, fac))
        for ln in rows:
            errs += _line_errors(ln, e, pol)
    titles = {_nz(e.get("title")) for e in doc.get("events") or []}
    for q in re.findall(r"「([^」]+)」", body):
        if q not in titles:
            errs.append({"code": "event_not_in_ledger", "detail": q})
    if not shown:
        if not errs:
            errs.append({"code": "event_none", "detail": "台帳の行事が答えにない"})
        return errs
    blob = " ".join(_blob(e, fac) for e, fac in shown)
    nums = set(re.findall(r"\d+", blob))
    for n in sorted(set(re.findall(r"\d+", body)) - nums):
        errs.append({"code": "event_fact_not_in_ledger", "detail": n})
    names = {w for w in re.split(_SPLIT, blob) if w}
    sfx = (pol.get("answer_check") or {}).get("name_suffixes") or []
    if sfx:
        for m in re.finditer(rf"[^\s、。,:「」()]*(?:{'|'.join(map(re.escape, sfx))})", body):
            if not any(m.group(0).endswith(w) and any(w.endswith(s) for s in sfx) for w in names):
                errs.append({"code": "event_fact_not_in_ledger", "detail": m.group(0)})
    urls = set(_URL.findall(t))
    own = {e["url"] for e, _ in shown}
    for u in sorted(urls - own):
        errs.append({"code": "event_source_unknown", "detail": u})
    for u in sorted(own - urls):
        errs.append({"code": "event_source_missing", "detail": u})
    return errs


def pending_facilities(doc=None):
    doc = doc if doc is not None else load()
    return [f["name"] for f in doc.get("facilities") or [] if (f.get("approval") or {}).get("status") != "approved"]
