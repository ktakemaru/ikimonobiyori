"""前シーズンの情報の判定(段階50)。通信しない・書き込まない。
東京都公園協会の紅葉情報は、シーズンが終わると「最終情報更新日：令和7年12月18日」の最終版のまま残る。
その日付が今シーズン(方針 season_check.season_start_month 以降の、直近のその月の1日以降)でなければ、今年の現況として使わない。"""
import re
from datetime import date

from .sources import load_policy, val

DATE_RE = re.compile(r"最終情報更新日\s*[:：]\s*(令和|平成)\s*(元|\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日")
WESTERN_RE = re.compile(r"最終情報更新日\s*[:：]\s*(\d{4})\s*年\s*(\d+)\s*月\s*(\d+)\s*日")


def parse_update_date(text, policy=None):
    """ページの本文から「最終情報更新日」を読む。→ date か None(書かれていない・読めない・存在しない日付)。推測しない。"""
    policy = policy or load_policy()
    m = DATE_RE.search(text or "")
    try:
        if m:
            era, n, mo, d = m.groups()
            base = val(policy["season_check"]["era_base_year"][era])
            return date(base + (1 if n == "元" else int(n)), int(mo), int(d))
        m = WESTERN_RE.search(text or "")
        if m:
            return date(*map(int, m.groups()))
    except ValueError:
        return None
    return None


def season_start(today, policy=None):
    """今シーズンの始まり = today 以前でいちばん近い、方針の月の1日。"""
    policy = policy or load_policy()
    month = val(policy["season_check"]["season_start_month"])
    year = today.year if today.month >= month else today.year - 1
    return date(year, month, 1)


def season_status(update, today, policy=None):
    """→ {"update_date", "current": True/False/None, "label", "note"}。
    update が None(日付が読めない)→ current は None(今シーズンと言い切らない)。today より後の日付も None(読み違いの疑い)。"""
    policy = policy or load_policy()
    lab = policy["season_check"]["labels"]
    if update is None or update > today:
        return {"update_date": None if update is None else update.isoformat(), "current": None, "label": None, "note": None}
    cur = update >= season_start(today, policy)
    note = None if cur else lab["note"].format(date=f"{update.year}年{update.month}月{update.day}日")
    return {"update_date": update.isoformat(), "current": cur, "label": None if cur else lab["previous_season"], "note": note}


def is_previous_season(update, today, policy=None):
    return season_status(update, today, policy)["current"] is False


# ---- 段階53: 日付と曜日の整合性（前年以前の情報を見分ける） ----
WD = "月火水木金土日"
RANGE_MARKS = "〜～~-−–ー"
TOKEN_RE = re.compile(
    r"(?P<full>(?:(?P<y>\d{4})\s*[年/]\s*)?(?P<mo>\d{1,2})\s*[月/]\s*(?P<d>\d{1,2})\s*日?(?:\s*[（(]\s*(?P<w>[月火水木金土日])(?:曜日?)?[）)]?)?)"
    r"|(?<=[" + RANGE_MARKS + r"])\s*(?P<d2>\d{1,2})\s*日\s*[（(]\s*(?P<w2>[月火水木金土日])(?:曜日?)?[）)]?")
GAP_RE = re.compile(r"^\s*(?:[" + RANGE_MARKS + r"]|から)\s*$")


def _tokens(text, base_year):
    """本文の日付を順に読み、年を決める。年つきの日付はその年。年のない日付は、直前の日付と範囲（〜）でつながっていれば直前の日付以後の最初の該当日の年
    （「2026年12月25日〜1月3日」の終わりは2027年）、そうでなければ base_year。月のない終わり（「10月23日（金）〜24日（土）」の24日）は直前の月。
    → [(原文, date か None, 曜日 か None)]。存在しない日付は date が None。"""
    out, prev = [], None
    for m in TOKEN_RE.finditer(text or ""):
        linked = prev is not None and prev["date"] is not None and GAP_RE.match(text[prev["end"]:m.start()] or "") is not None
        if m.group("full"):
            mo, d, w = int(m.group("mo")), int(m.group("d")), m.group("w")
            if m.group("y"):
                y = int(m.group("y"))
            elif linked:
                y = prev["date"].year + (1 if (mo, d) < (prev["date"].month, prev["date"].day) else 0)
            else:
                y = base_year
        else:
            if not linked:
                continue
            d, w = int(m.group("d2")), m.group("w2")
            mo, y = prev["date"].month, prev["date"].year
            if d < prev["date"].day:
                mo += 1
                if mo > 12:
                    mo, y = 1, y + 1
        try:
            dt = date(y, mo, d)
        except ValueError:
            dt = None
        tok = {"text": m.group(0).strip(), "date": dt, "weekday": w, "end": m.end()}
        out.append(tok)
        prev = tok
    return out


def weekday_check(text, year, policy=None):
    """「10/25(土)」「11月15日（土曜日）」「2026年12月25日（金）〜2027年1月3日（日）」のように日付と曜日が書かれている箇所が、その日付の年の暦と合うかを確かめる。
    年のない日付は year（今シーズンの年）の暦で、範囲の終わりは直前の日付以後の最初の該当日の年で照合する（年またぎ。段階55）。
    → {"checked": 件数, "mismatches": [原文の断片]}。曜日の書かれた日付がなければ checked は 0（判定しない）。存在しない日付は不一致にする。"""
    policy = policy or load_policy()
    names = val(policy["season_check"]["weekday_names"])
    checked, bad = 0, []
    for t in _tokens(text, year):
        if not t["weekday"]:
            continue
        checked += 1
        if t["date"] is None or names[t["date"].weekday()] != t["weekday"]:
            bad.append(t["text"])
    return {"checked": checked, "mismatches": bad}


def previous_year_by_weekday(text, today, policy=None):
    """今シーズンの暦と曜日が合わなければ前年以前の情報（True）。すべて合えば False。曜日の書かれた日付がなければ None（判定しない）。
    見出しが「2026」でも本文・meta の日付が古いまま残るサイトを落とす。"""
    r = weekday_check(text, season_start(today, policy).year, policy)
    if not r["checked"]:
        return None
    return bool(r["mismatches"])
