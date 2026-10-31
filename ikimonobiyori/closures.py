"""休園日・休館日の規則の原文を読み、対象の日が休みかをコードで照らす(段階35。通信しない・決定論)。

読める書き方:
  - 「毎月第1・3月曜」「第2・第4火曜日」(第N X曜。毎月は省略可)
  - 「毎週月曜」「月曜日」(毎週 X曜)
  - 「(祝日の場合は翌日)」「(祝日の場合は翌平日)」: 規則の日が祝日なら、その日は開いていて、翌日(祝日・休日でない最初の日)が休み
  - 「(祝日の場合は開園)」: 規則の日が祝日なら開いている(振替なし)
  - 「12月29日～1月3日」「12/29〜1/3」(年をまたいでよい)
読めない規則(「年末年始」「臨時休園あり」など)は、照らせないものとして原文を添える(推測しない)。
祝日は内閣府の「国民の祝日」の規則(固定日・ハッピーマンデー・春分/秋分の近似式・振替休日・国民の休日)で計算する。"""
import re
import unicodedata
from datetime import date, timedelta

WEEKDAYS = "月火水木金土日"
KANJI = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


def _nth_weekday(y, m, wd, n):
    """y 年 m 月の第 n の曜日 wd(0=月)。なければ None。"""
    d = date(y, m, 1)
    d += timedelta(days=(wd - d.weekday()) % 7)
    d += timedelta(weeks=n - 1)
    return d if d.month == m else None


def _equinox(y, base):
    return int(base + 0.242194 * (y - 1980)) - int((y - 1980) / 4)


def _base_holidays(y):
    """その年の国民の祝日(振替・国民の休日の前)。→ {date: 名前}。1980〜2099 年を想定。"""
    h = {date(y, 1, 1): "元日", _nth_weekday(y, 1, 0, 2): "成人の日", date(y, 2, 11): "建国記念の日",
         date(y, 2, 23): "天皇誕生日", date(y, 3, _equinox(y, 20.8431)): "春分の日", date(y, 4, 29): "昭和の日",
         date(y, 5, 3): "憲法記念日", date(y, 5, 4): "みどりの日", date(y, 5, 5): "こどもの日",
         _nth_weekday(y, 7, 0, 3): "海の日", date(y, 8, 11): "山の日", _nth_weekday(y, 9, 0, 3): "敬老の日",
         date(y, 9, _equinox(y, 23.2488)): "秋分の日", _nth_weekday(y, 10, 0, 2): "スポーツの日",
         date(y, 11, 3): "文化の日", date(y, 11, 23): "勤労感謝の日"}
    return h


def holidays(y):
    """→ {date: 名前}(振替休日・国民の休日を含む)。"""
    h = dict(_base_holidays(y))
    for d in sorted(list(h)):                          # 振替休日: 日曜の祝日 → 次の祝日でない日
        if d.weekday() == 6:
            x = d + timedelta(days=1)
            while x in h:
                x += timedelta(days=1)
            h[x] = "振替休日"
    for d in sorted(list(h)):                          # 国民の休日: 祝日にはさまれた平日
        x = d + timedelta(days=2)
        mid = d + timedelta(days=1)
        if x in h and mid not in h and mid.weekday() != 6:
            h[mid] = "国民の休日"
    return h


def is_holiday(d):
    return d in holidays(d.year)


def _n(s):
    return unicodedata.normalize("NFKC", s or "").replace("〜", "~").replace("～", "~")


def _nums(s):
    out = []
    for x in re.split(r"[・,、第]", s):
        x = x.strip()
        if not x:
            continue
        if x.isdigit():
            out.append(int(x))
        elif x in KANJI:
            out.append(KANJI[x])
    return out


def parse(text):
    """原文 → {facility, rules: [...], unread: [読めなかった部分]}。"""
    t = _n(text)
    m = re.match(r"^\s*([^、。:()]+?)は(?=.*(曜|月\d|/))", t)
    facility = m.group(1).strip() if m else None
    rules = []
    shift = "next_day" if re.search(r"祝(日|休日)[^)]*の場合は翌(日|平日)", t) else \
            "open" if re.search(r"祝(日|休日)[^)]*の場合は(開園|開館|営業)", t) else None
    for mm in re.finditer(r"(毎月)?第((?:\d|[一二三四五])(?:\s*[・,、]\s*第?(?:\d|[一二三四五]))*)\s*([月火水木金土日])曜", t):
        rules.append({"kind": "nth_weekday", "nth": _nums(mm.group(2)), "weekday": WEEKDAYS.index(mm.group(3)), "holiday": shift})
    t2 = re.sub(r"(毎月)?第((?:\d|[一二三四五])(?:\s*[・,、]\s*第?(?:\d|[一二三四五]))*)\s*([月火水木金土日])曜", " ", t)
    for mm in re.finditer(r"(毎週)\s*([月火水木金土日])曜", t2):
        rules.append({"kind": "weekly", "weekday": WEEKDAYS.index(mm.group(2)), "holiday": shift})
    for mm in re.finditer(r"(\d{1,2})月(\d{1,2})日?\s*[~から\-]\s*(?:翌年)?(\d{1,2})月(\d{1,2})日", t):
        rules.append({"kind": "range", "start": (int(mm.group(1)), int(mm.group(2))), "end": (int(mm.group(3)), int(mm.group(4)))})
    for mm in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})\s*[~\-]\s*(\d{1,2})/(\d{1,2})(?![\d/])", t):
        rules.append({"kind": "range", "start": (int(mm.group(1)), int(mm.group(2))), "end": (int(mm.group(3)), int(mm.group(4)))})
    unread = [w for w in ("年末年始", "臨時", "不定休", "点検", "天候") if w in t]
    return {"facility": facility, "rules": rules, "unread": unread}


def _in_range(d, r):
    s = date(d.year, *r["start"])
    e = date(d.year, *r["end"])
    if e < s:                                          # 年をまたぐ(12/29〜1/3)
        return d >= s or d <= e
    return s <= d <= e


def _next_open_day(d):
    x = d + timedelta(days=1)
    while is_holiday(x):
        x += timedelta(days=1)
    return x


def _weekday_rule_days(d, r):
    """対象の日 d の前後で、規則が休みにする日の集合(祝日の扱いを含む)。"""
    out = set()
    months = {(d.year, d.month)}
    prev = d - timedelta(days=7)
    months.add((prev.year, prev.month))
    for y, m in months:
        if r["kind"] == "nth_weekday":
            days = [x for x in (_nth_weekday(y, m, r["weekday"], n) for n in r["nth"]) if x]
        else:
            first = date(y, m, 1)
            first += timedelta(days=(r["weekday"] - first.weekday()) % 7)
            days = [first + timedelta(weeks=k) for k in range(6) if (first + timedelta(weeks=k)).month == m]
        for x in days:
            if is_holiday(x) and r["holiday"] == "next_day":
                out.add(_next_open_day(x))
            elif is_holiday(x) and r["holiday"] == "open":
                continue
            else:
                out.add(x)
    return out


def evaluate(text, d):
    """→ {date, closed: True/False/None, facility, text, read: bool, reason}。
    closed=None は照らせない(規則が読めない・読めない部分がかかりうる)。"""
    p = parse(text)
    res = {"date": d.isoformat(), "facility": p["facility"], "text": text, "read": bool(p["rules"]), "closed": None, "reason": None,
           "holiday": holidays(d.year).get(d)}
    if not p["rules"]:
        res["reason"] = "unread"
        return res
    for r in p["rules"]:
        if r["kind"] == "range" and _in_range(d, r):
            res.update(closed=True, reason="range")
            return res
        if r["kind"] in ("nth_weekday", "weekly") and d in _weekday_rule_days(d, r):
            res.update(closed=True, reason=r["kind"] + ("_shifted" if d.weekday() != r["weekday"] else ""))
            return res
    if p["unread"] and (d.month in (12, 1) or "年末年始" not in p["unread"]):
        res["reason"] = "unread_part"
        return res
    res.update(closed=False, reason="no_rule_applies")
    return res


def line(ev, open_note=None):
    """照らした結果 → 答えにそのまま使える 1 文。"""
    d = date.fromisoformat(ev["date"])
    md = f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]}{'・' + ev['holiday'] if ev.get('holiday') else ''})"
    who = ev.get("facility") or "この施設"
    if ev["closed"] is True:
        return f"{md}は{who}が休みです" + (f"({open_note})" if open_note else "") + "。"
    if ev["closed"] is False:
        return f"{md}は{who}の休みの日ではありません(休みの規則: 「{ev['text']}」)。"
    return f"{md}が休みかは規則から読めません(原文: 「{ev['text']}」)。"
