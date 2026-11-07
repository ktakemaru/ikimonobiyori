"""気象庁 生物季節観測の「平年の目安」(段階61 第1部)。通信しない。
累年値の CSV(気象庁のファイルそのもの。cp932)から、地点 × 種目ごとに、決めた期間の観測日の平均・最早・最遅を計算し、
小さな表(ikimonobiyori/data/jma_normals/normals.yaml。出典と加工の明記つき)にする。原データの CSV はリポジトリに置かない(再取得できる)。
値と文は data/jma_normals/policy.yaml。CSV の読み方は jma_phenology.parse_text を使う(形が違えば ParseError で止める)。

  python -X utf8 -m ikimonobiyori.jma_normals build --raw-dir <CSV のフォルダ> --retrieved-on YYYY-MM-DD --out ikimonobiyori/data/jma_normals/normals.yaml
  python -X utf8 -m ikimonobiyori.jma_normals lines --question 東京の紅葉は、平年はいつ頃?
"""
import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import jma_phenology as J
from .fetch import ParseError
from .paths import DATA_FILES_DIR

DIR = DATA_FILES_DIR / "jma_normals"
POLICY_PATH = DIR / "policy.yaml"
NORMALS_PATH = DIR / "normals.yaml"
REF_YEAR = 2001          # 月日を数えるための閏年でない基準の年(値ではなく暦の基準)
_cache = {}


def policy(path=None):
    p = Path(path or POLICY_PATH)
    if p not in _cache:
        _cache[p] = yaml.safe_load(p.read_text(encoding="utf-8"))
    return _cache[p]


def _offset(d, season_year):
    """観測日 → 季節の年の 1/1 からの日数(閏日は 2/28 に寄せる。前年は負、翌年は 365 以上)。"""
    m, dd = d.month, min(d.day, 28) if d.month == 2 and d.day == 29 else d.day
    base = (date(REF_YEAR, m, dd) - date(REF_YEAR, 1, 1)).days
    return base + (d.year - season_year) * (date(REF_YEAR + 1, 1, 1) - date(REF_YEAR, 1, 1)).days


def _md(offset):
    """日数 → 'MM-DD'(年は付けない)。"""
    year_days = (date(REF_YEAR + 1, 1, 1) - date(REF_YEAR, 1, 1)).days
    d = date(REF_YEAR, 1, 1) + timedelta(days=offset % year_days)
    return f"{d.month:02d}-{d.day:02d}"


def _round(x):
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def phrase(md, pol=None):
    """'12-03' → '12月上旬'。"""
    pol = pol or policy()
    m, d = (int(x) for x in md.split("-"))
    label = next(t["label"] for t in pol["thirds"] if d <= t["until"])
    return f"{m}月{label}"


def jp_md(md):
    m, d = (int(x) for x in md.split("-"))
    return f"{m}月{d}日"


def compute(rows, phen, pol=None):
    """parse_text の行(1 種目)→ 地点ごとの平年の目安の一覧。期間・リマーク・データ点数の下限は方針の値。"""
    pol = pol or policy()
    lo, hi = pol["period"]["from"], pol["period"]["to"]
    stations = {s["station_no"]: s["name"] for s in pol["stations"]}
    out = []
    for no, name in stations.items():
        mine = [r for r in rows if r["station_no"] == no and r["status"] == J.OBSERVED]
        if not mine:
            continue
        years_all = sorted(int(r["year"]) for r in mine)
        use = [r for r in mine if lo <= int(r["year"]) <= hi and r["rm"] in pol["stat_rm"]]
        if len(use) < pol["min_points"]:
            continue
        offs = [_offset(date.fromisoformat(r["date"]), int(r["year"])) for r in use]
        used_years = sorted(int(r["year"]) for r in use)
        mean = _md(_round(sum(offs) / len(offs)))
        out.append({"station": name, "station_no": no, "phenomenon": phen["key"], "name": phen["name"], "label": phen["label"],
                    "kind": phen["kind"], "observing": bool(phen["observing"]),
                    "mean": mean, "mean_phrase": phrase(mean, pol), "earliest": _md(min(offs)), "latest": _md(max(offs)),
                    "period": {"from": used_years[0], "to": used_years[-1]}, "points": len(use),
                    "observed_years": {"first": years_all[0], "last": years_all[-1]}})
    return out


def build(raw_dir, retrieved_on, pol=None):
    """CSV のフォルダ → 表の辞書(出典・加工の明記つき)。見つからない種目は missing に残す(推測で補わない)。"""
    pol = pol or policy()
    layout = pol["layout"]
    entries, missing = [], []
    for phen in pol["phenomena"]:
        p = Path(raw_dir) / f"{phen['code']}.csv"
        if not p.is_file():
            missing.append(phen["key"])
            continue
        rows, _ = J.parse_text(p.read_bytes().decode(pol["encoding"]), phen, layout)
        entries += compute(rows, phen, pol)
    src = pol["source"]
    return {"schema": "ikimono-jma-normals/1",
            "source": {"name": src["name"], "url": src["page"], "retrieved_on": retrieved_on, "license": src["license"]},
            "processing": (f"{src['name']}をもとに、イキモノビヨリが平均等を計算(加工)。地点・種目ごとに "
                           f"{pol['period']['from']}〜{pol['period']['to']}年の観測日(統計に使うリマークのものだけ)の平均・最早・最遅を、"
                           "年を付けない月日で示す。観測期間とデータ点数を併記。気象庁が作成した値(平年値)ではない"),
            "period": dict(pol["period"]), "entries": entries, "missing": missing}


def dump(doc, out):
    head = ("# 段階61 第1部: 気象庁の生物季節観測の平年の目安(ikimonobiyori.jma_normals build が作る。手で書き換えない)\n"
            f"# 出典: {doc['source']['name']}({doc['source']['url']})、取得日 {doc['source']['retrieved_on']}\n"
            "# 加工: 気象庁の観測値をもとに、イキモノビヨリが平均等を計算(公共データ利用規約 第1.0版。気象庁が作成したものではない)\n")
    Path(out).write_text(head + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")


def load(path=None):
    p = Path(path or NORMALS_PATH)
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None


def match(question, pol=None):
    """質問の文 → 平年の目安を出す種目の key の一覧(平年・いつ頃などの語と、種目の語が両方あるときだけ)。"""
    pol = pol or policy()
    q = question or ""
    if not any(w in q for w in pol["ask_words"]):
        return []
    keys = []
    for ph in pol["phenomena"]:
        if any(s in q for s in ph.get("skip") or []):
            continue
        if any(w in q for w in ph.get("words") or []):
            keys.append(ph["key"])
    return keys


def stations_in(question, pol=None):
    pol = pol or policy()
    q = question or ""
    hit = [s["name"] for s in pol["stations"] if s["name"] in q]
    return hit or list(pol["default_stations"])


def line(entry, pol=None):
    pol = pol or policy()
    t = pol["text"]
    vals = {"station": entry["station"], "label": entry["label"], "phrase": entry["mean_phrase"], "from": entry["period"]["from"],
            "to": entry["period"]["to"], "points": entry["points"], "earliest": jp_md(entry["earliest"]), "latest": jp_md(entry["latest"]),
            "first": entry["observed_years"]["first"], "last": entry["observed_years"]["last"]}
    s = t["observing"].format(**vals) if entry["observing"] else t["ended"].format(**vals)
    phen = next((p for p in pol["phenomena"] if p["key"] == entry["phenomenon"]), {})
    if not entry["observing"]:
        s += t["ended_note"]
    elif phen.get("mountain_note"):
        s += t["mountain_note"]
    return s


def lines_for(question, doc=None, pol=None):
    """質問の文 → (行の一覧, 出典の行)。当たらなければ ([], None)。"""
    pol = pol or policy()
    doc = doc if doc is not None else load()
    keys = match(question, pol)
    if not keys or not doc:
        return [], None
    sts = stations_in(question, pol)
    out = []
    for st in sts:
        for k in keys:
            e = next((x for x in doc["entries"] if x["station"] == st and x["phenomenon"] == k), None)
            if e:
                out.append(line(e, pol))
    out = out[: pol["max_lines"]]
    return out, (pol["text"]["source_line"] if out else None)


def skeleton_lines(subjects, origin=None, doc=None, pol=None):
    """計画の答えに添える行(対象 → 種目は方針の skeleton_subjects。地点は出発地と同じ名前の地点、なければ skeleton_station)。→ (行の一覧, 出典の行)。"""
    pol = pol or policy()
    doc = doc if doc is not None else load()
    if not doc:
        return [], None
    names = {s["name"] for s in pol["stations"]}
    st = origin if origin in names else pol["skeleton_station"]
    out = []
    for sj in subjects or []:
        for k in (pol.get("skeleton_subjects") or {}).get(sj) or []:
            e = next((x for x in doc["entries"] if x["station"] == st and x["phenomenon"] == k), None)
            if e and line(e, pol) not in out:
                out.append(line(e, pol))
    return out, (pol["text"]["source_line"] if out else None)


def used_in(text, doc=None, pol=None):
    """答えの文に出た平年の目安の行(検査で根拠として扱う)。"""
    pol = pol or policy()
    doc = doc if doc is not None else load()
    return [ln for ln in (line(e, pol) for e in (doc or {}).get("entries") or []) if ln in (text or "")]


def answer_errors(text, pol=None):
    """検査: 観測を終えた種目の行(「過去の観測」)に「今年の」などを書かない。平年の目安の行があるのに出典の行がない。"""
    pol = pol or policy()
    t = pol["text"]
    ended_labels = [p["label"] for p in pol["phenomena"] if not p["observing"]]
    marker = t["ended"].split("{first}")[0].split("}")[-1]       # 「気象庁の過去の観測(」
    errs = []
    for ln in (text or "").splitlines():
        if any(lb in ln for lb in ended_labels) and (marker in ln or "過去の観測" in ln):
            for w in t["forbidden_for_ended"]:
                if w in ln:
                    errs.append({"code": "ended_phenology_this_year", "detail": ln[:40]})
                    break
    if re.search(r"平年は.{1,8}ごろ|過去の観測\(", text or "") and "イキモノビヨリが計算" in t["source_line"] and t["source_line"] not in (text or ""):
        errs.append({"code": "jma_normal_source_missing", "detail": "気象庁の出典と加工の行"})
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ikimonobiyori.jma_normals")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="CSV のフォルダから平年の目安の表を作る(通信しない)")
    b.add_argument("--raw-dir", required=True)
    b.add_argument("--retrieved-on", required=True, help="CSV を取得した日 YYYY-MM-DD")
    b.add_argument("--out", required=True)
    s = sub.add_parser("lines", help="質問の文 → 平年の目安の行")
    s.add_argument("--question", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        try:
            doc = build(a.raw_dir, a.retrieved_on)
        except ParseError as ex:
            print(f"読めませんでした: {ex}", file=sys.stderr)
            return 1
        dump(doc, a.out)
        print(f"→ {a.out}({len(doc['entries'])} 件。見つからなかった種目: {', '.join(doc['missing']) or 'なし'})")
        return 0
    ls, src = lines_for(a.question)
    for x in ls:
        print(x)
    if src:
        print(src)
    return 0 if ls else 2


if __name__ == "__main__":
    sys.exit(main())
