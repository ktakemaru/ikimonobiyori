"""博物館などの行事・展示の台帳(段階61 第2部)。通信しない。台帳は data/facility_events/events.yaml、値と文は policy.yaml。
行事は現況ではない(色づき・開花・飛来の状況の代わりにしない)。年つきの日付で、書かれた曜日が暦と合うものだけを使う。
答えに出すのは、施設が承認(approval.status: approved)されているときだけ。承認待ちの施設の行事は出さない(承認は本人が行う)。"""
from datetime import date
from pathlib import Path

import yaml

from .paths import DATA_FILES_DIR

DIR = DATA_FILES_DIR / "facility_events"


def policy(path=None):
    return yaml.safe_load(Path(path or DIR / "policy.yaml").read_text(encoding="utf-8"))


def load(path=None):
    return yaml.safe_load(Path(path or DIR / "events.yaml").read_text(encoding="utf-8"))


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
        if e.get("kind") != "展示" and not e.get("date"):
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


def lines_for(question, today, doc=None, pol=None, prefecture=None):
    """質問の文 → (行の一覧, 出典の URL)。承認済みの施設の、今日以降の行事・会期中かこれからの展示だけ。曜日が合わないものは出さない。"""
    pol = pol or policy()
    doc = doc if doc is not None else load()
    tps = match(question, pol)
    if not tps or validate(doc, pol):
        return [], []
    if prefecture is None:
        prefecture = next((p for k, ps in pol["regions"].items() if k in (question or "") for p in ps), None)
    facs = _approved(doc)
    out, urls = [], []
    for e in doc.get("events") or []:
        fac = facs.get(e["facility"])
        if not fac or (prefecture and fac.get("prefecture") != prefecture):
            continue
        if not set(e.get("topics") or []) & set(tps):
            continue
        last = e.get("end") or e.get("date")
        if date.fromisoformat(last) < today:
            continue
        out.append(line(e, fac, pol))
        urls.append(e["url"])
    return out, sorted(set(urls))


def pending_facilities(doc=None):
    doc = doc if doc is not None else load()
    return [f["name"] for f in doc.get("facilities") or [] if (f.get("approval") or {}).get("status") != "approved"]
