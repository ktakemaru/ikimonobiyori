"""気温による紅葉の進行の手法。日最低気温の直近平均 M から段階と進み(0〜1)を決める。純粋・決定論。
閾値(start / advance / strong / 平均日数)は呼び出し側がプロファイルから渡す。欠損は 0 で埋めず、平均は None にする。"""
from datetime import date, timedelta


def mean_tmin(series, target, days):
    """target を含む直近 days 日の日最低気温の平均。1日でも欠損(キーなし・None)なら None(0 で埋めない)。"""
    vals = []
    for k in range(days):
        v = series.get((target - timedelta(days=k)).isoformat())
        if v is None:
            return None
        vals.append(v)
    return sum(vals) / len(vals)


def stage_for(m, *, start, advance):
    """M ≤ advance: peak / M ≤ start: early_bloom / それより高い: before_bud。M が None なら None。
    終盤(late)・落葉は判定しない(出典がない)。"""
    if m is None:
        return None
    if m <= advance:
        return "peak"
    if m <= start:
        return "early_bloom"
    return "before_bud"


def progress(m, *, start, strong):
    """線形補間の進み(0〜1)。start 以上で 0、strong 以下で 1。M が None なら None。"""
    if m is None:
        return None
    x = (start - m) / (start - strong)
    return min(1.0, max(0.0, x))


def to_date(s):
    return date.fromisoformat(s)
