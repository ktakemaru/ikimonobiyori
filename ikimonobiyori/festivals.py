"""まつり・イベント（段階53 第2部。通信しない・書き込まない）。
「紅葉まつり」「菊花展」などは、主催者が見頃を見込んで日程を設定していることが多く、見頃情報の一つになる。ただし期間は運営上の日程で、その時点の色づきを保証しない
ので、現況（色づき状況）とは別の行で出す。年つきの開催期間だけを持ち、今シーズンでないもの・年が読めないもの・日付に書かれた曜日が今年の暦と合わないものは使わない。"""
from datetime import date
from pathlib import Path

import yaml

from . import season, sources
from .paths import DATA_FILES_DIR

PATH = DATA_FILES_DIR / "observations" / "festivals.yaml"


def load(path=None):
    return yaml.safe_load(Path(path or PATH).read_text(encoding="utf-8"))


def _pol(policy=None):
    if policy is None:
        from .observations import load_policy
        policy = load_policy()
    return policy["festivals"]


def _md(d):
    return f"{d.month}/{d.day}"


def usable(f, today, policy=None, sources_policy=None):
    """→ (使える, 使わない理由のキー)。開始日・終了日が今シーズンの年か、書かれた日付の曜日が今年の暦と合うか。"""
    try:
        start, end = date.fromisoformat(str(f["start"])), date.fromisoformat(str(f["end"]))
    except (KeyError, TypeError, ValueError):
        return False, "year_missing"
    sp = sources_policy or sources.load_policy()
    year = season.season_start(today, sp).year
    if start.year != year or end.year not in (year, year + 1) or end < start:
        return False, "other_year"
    raw = " ".join(f.get("raw") or [])
    if raw and season.previous_year_by_weekday(raw, today, sp):
        return False, "weekday_mismatch"
    return True, None


def status(f, today):
    start, end = date.fromisoformat(str(f["start"])), date.fromisoformat(str(f["end"]))
    if today > end:
        return {"state": "ended", "days": 0}
    if today < start:
        d = (start - today).days
        return {"state": "starts_today" if d == 0 else "starts_in", "days": d}
    return {"state": "ongoing", "days": 0}


def festival_row(f, today, policy=None):
    """答えの材料の 1 件。→ dict（period_line・lightup_line・organizer_line は文）。使えないものは None。"""
    p = _pol(policy)
    ok, why = usable(f, today)
    if not ok:
        return None
    st = status(f, today)
    start, end = date.fromisoformat(str(f["start"])), date.fromisoformat(str(f["end"]))
    period = p["status_text"][st["state"]].format(start=_md(start), end=_md(end), days=st["days"])
    lu = f.get("lightup")
    lu_line = None
    if lu:
        hours = p["hours_fmt"].format(hours=lu["hours"]) if lu.get("hours") else ""
        note = p["note_fmt"].format(note=lu["note"]) if lu.get("note") else ""
        if lu.get("start") and lu.get("end"):
            lu_line = p["lightup_text"].format(start=_md(date.fromisoformat(str(lu["start"]))), end=_md(date.fromisoformat(str(lu["end"]))), hours=hours, note=note)
        else:
            lu_line = p["lightup_no_period"].format(hours=(lu.get("hours") or ""), note=note)
    return {"id": f["id"], "name": f["name"], "state": st["state"], "days": st["days"], "start": str(f["start"]), "end": str(f["end"]),
            "period_label": p["period_label"], "period_line": f"{p['period_label']}: {period}", "lightup_line": lu_line,
            "organizer": f["organizer"], "organizer_class": f["organizer_class"],
            "organizer_line": p["organizer_line"].format(organizer=f["organizer"], klass=p["class_labels"][f["organizer_class"]]),
            "contact": f.get("contact"), "venue": f.get("venue"), "url": f["url"], "publisher": f.get("publisher"), "published": f.get("published"),
            "taken_on": f.get("taken_on"), "source_class": f["organizer_class"], "no_state_line": p["no_state"]}


def for_spot(spot_id, today, doc=None, policy=None):
    """名所（候補の id）に結びついた、今シーズンのまつり。終了したものは含めない。"""
    doc = doc if doc is not None else load()
    out = []
    for f in doc.get("festivals") or []:
        if spot_id not in (f.get("spots") or []):
            continue
        row = festival_row(f, today, policy)
        if row and row["state"] != "ended":
            out.append(row)
    return out


def dropped(today, doc=None):
    """使わなかったまつり {id: 理由}（報告用）。"""
    doc = doc if doc is not None else load()
    return {f["id"]: usable(f, today)[1] for f in doc.get("festivals") or [] if not usable(f, today)[0]}


PRACTICAL_PATH = DATA_FILES_DIR / "observations" / "practical.yaml"


def practical_for(spot_id, today, doc=None):
    """段階53 第4部: 名所に結びついた、読めた公式ページの実用情報（期間つきのものは期間の中だけ）。→ [{text, url, publisher, taken_on}]"""
    doc = doc if doc is not None else load(PRACTICAL_PATH)
    out = []
    for it in doc.get("items") or []:
        if spot_id not in (it.get("spots") or []):
            continue
        if it.get("valid_from") and today < date.fromisoformat(str(it["valid_from"])):
            continue
        if it.get("valid_to") and today > date.fromisoformat(str(it["valid_to"])):
            continue
        out.append({"text": it["text"], "publisher": it.get("publisher"), "url": it["url"], "state_date": it.get("taken_on")})
    return out
