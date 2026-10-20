"""気象庁 生物季節観測の累年値ファイル(CSV)の正規化(段階13。通信しない)。答え合わせ(docs/validation-plan.md)の正解側のデータを作る。
CSV の読み方の定義は data/jma_phenology.yaml にあり、コードに値を持たない。形が想定と違えば ParseError で止める(推測で補わない)。
元のファイルは読むだけ。書き込むのは、コマンドで明示した --out だけ(既定の書き込み先は持たない)。

  python -X utf8 -m ikimonobiyori.jma_phenology normalize --raw-dir data/jma_phenology/raw --out data/jma_phenology/normalized.csv
  python -X utf8 -m ikimonobiyori.jma_phenology summary --normalized data/jma_phenology/normalized.csv --region 関東甲信
"""
import argparse
import csv
import io
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

from .fetch import ParseError
from .paths import JMA_PHENOLOGY_DEF_PATH

COLUMNS = ["station_no", "station_name", "phenomenon_code", "phenomenon", "year", "date", "status", "rm", "cross_year",
           "lat", "lon", "elevation_m"]
OBSERVED, NO_VALUE = "observed", "no_value"
ATTRIBUTION = ("気象庁「生物季節観測累年値」({page})を加工して作成(イキモノビヨリ ikimonobiyori.jma_phenology)。"
               "公共データ利用規約(第1.0版)(https://www.digital.go.jp/resources/open_data/public_data_license_v1.0)")
SOURCE_LINE = "出典:気象庁ホームページ「生物季節観測累年値」({page})"
PROCESS_NOTE = "加工の内容: 地点×年の表を行に並べ替え、月日を日付にし、値 0 を no_value にした(詳しくは data/jma_phenology/README.md)"
COMMENT = "#"      # 正規化した CSV の冒頭の出典の行の印(read_csv は読み飛ばす)


def load_definition(path=None):
    return yaml.safe_load(Path(path or JMA_PHENOLOGY_DEF_PATH).read_text(encoding="utf-8"))


def _mmdd(v):
    """'1108' → (11, 8)。'0' は None。数字でない・月日として読めない値は ParseError。"""
    if not v.isdigit():
        raise ParseError(f"値が数字でない: {v!r}")
    n = int(v)
    if n == 0:
        return None
    m, d = divmod(n, 100)
    return m, d


def resolve_date(year, mmdd, phen):
    """列の年(季節の年)と月日 → (日付, 隣の年か)。cross_year_months の月は、spring なら前年、autumn なら翌年(定義の推測を参照)。"""
    m, d = mmdd
    shift = 0
    if m in phen["cross_year_months"]:
        shift = -1 if phen["season"] == "spring" else 1
    try:
        return date(year + shift, m, d), shift != 0
    except ValueError:
        raise ParseError(f"{year} 年の列の値 {m:02d}{d:02d} は日付として読めない") from None


def parse_text(text, phen, layout, stations=None):
    """CSV の本文 → (行のリスト, 情報)。行は COLUMNS の辞書。年は「値のある最後の年」までに限る(それより後の列は未来の年か未集計)。"""
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) <= layout["header_row"] + 1:
        raise ParseError("行が足りない")
    title, header = rows[layout["title_row"]], rows[layout["header_row"]]
    if title[0].strip().lstrip("0") != phen["code"].lstrip("0") or title[1].strip() != phen["name"]:
        raise ParseError(f"1行目が想定と違う: {title[:2]!r}(想定 {phen['code']},{phen['name']})")
    nst, nsum = len(layout["station_columns"]), len(layout["summary_columns"])
    if header[:nst] != layout["station_columns"] or header[-nsum:] != layout["summary_columns"]:
        raise ParseError(f"見出しの行が想定と違う: {header[:nst]!r} … {header[-nsum:]!r}")
    year_cols = header[nst:-nsum]
    if not year_cols or len(year_cols) % 2:
        raise ParseError("年の列が (年, rm) の組になっていない")
    years = []
    for i in range(0, len(year_cols), 2):
        if not year_cols[i].isdigit():
            raise ParseError(f"年の列名が年でない: {year_cols[i]!r}")
        years.append((nst + i, int(year_cols[i])))
    if [y for _, y in years] != list(range(years[0][1], years[0][1] + len(years))):
        raise ParseError("年の列が1年ずつ並んでいない")
    st_meta = {s["station_no"]: s for s in stations or []}
    cells, last = [], None
    for r in rows[layout["header_row"] + 1:]:
        if not any(c.strip() for c in r):
            continue
        if len(r) != len(header):
            raise ParseError(f"列の数が見出しと違う: 地点 {r[:1]!r}({len(r)} 列、見出しは {len(header)} 列)")
        no, name = r[0].strip(), r[1].replace("　", " ").strip()
        if not no.isdigit():
            raise ParseError(f"地点の番号が数字でない: {no!r}")
        for col, y in years:
            v, rm = r[col].strip(), r[col + 1].strip()
            mmdd = _mmdd(v)
            if mmdd is None:
                if rm != layout["no_value"]:
                    raise ParseError(f"値なしなのに rm がある: 地点 {no} {y} 年 rm={rm!r}")
                cells.append((no, name, y, None, rm, False))
                continue
            if not rm.isdigit():
                raise ParseError(f"rm が数字でない: 地点 {no} {y} 年 rm={rm!r}")
            d, cross = resolve_date(y, mmdd, phen)
            cells.append((no, name, y, d, rm, cross))
            last = y if last is None else max(last, y)
    out = []
    for no, name, y, d, rm, cross in cells:
        if last is None or y > last:
            continue
        m = st_meta.get(no, {})
        out.append({"station_no": no, "station_name": name, "phenomenon_code": phen["code"], "phenomenon": phen["key"], "year": y,
                    "date": d.isoformat() if d else "", "status": OBSERVED if d else NO_VALUE, "rm": rm if d else "",
                    "cross_year": "1" if cross else "0",
                    "lat": _blank(m.get("lat")), "lon": _blank(m.get("lon")), "elevation_m": _blank(m.get("elevation_m"))})
    info = {"code": phen["code"], "phenomenon": phen["key"], "first_year": years[0][1], "last_year_with_value": last,
            "header_last_year": years[-1][1], "stations": len({c[0] for c in cells}), "rows": len(out)}
    return out, info


def _blank(v):
    return "" if v is None else v


def normalize(raw_dir, definition=None):
    """raw_dir の NNN.csv(定義の現象ごと)→ (行のリスト, 情報のリスト, 見つからなかった現象)。ファイルは読むだけ。"""
    df = definition or load_definition()
    rows, infos, missing = [], [], []
    for phen in df["phenomena"]:
        p = Path(raw_dir) / f"{phen['code']}.csv"
        if not p.is_file():
            missing.append(phen["key"])
            continue
        text = p.read_bytes().decode(df["encoding"])
        r, info = parse_text(text, phen, df["layout"], df.get("stations"))
        info["file"] = p.name
        rows += r
        infos.append(info)
    rows.sort(key=lambda x: (x["phenomenon_code"], x["station_no"], x["year"]))
    return rows, infos, missing


def attribution_lines(definition):
    """正規化した CSV の冒頭に書く出典と加工したことの記載(docs/data-sources.md §1.5)。日時を含めない(同じ入力なら同じファイル)。"""
    page = definition["source_page"]
    return [SOURCE_LINE.format(page=page), ATTRIBUTION.format(page=page), PROCESS_NOTE]


def write_csv(rows, out, header_lines=()):
    """header_lines は '# ' を付けて CSV の見出しの前に書く。"""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        for line in header_lines:
            f.write(f"{COMMENT} {line}\n")
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith(COMMENT)))


def summarize(rows, station_nos=None):
    """地点 × 現象ごとの件数。→ {(地点番号, 地点名, 現象): {"years": 年数, "observed": n, "no_value": n, "first": 年, "last": 年}}。
    first / last は値のある最初・最後の年(なければ None)。station_nos を渡せばその地点だけ。"""
    acc = defaultdict(lambda: {"years": 0, "observed": 0, "no_value": 0, "first": None, "last": None})
    for r in rows:
        if station_nos is not None and r["station_no"] not in station_nos:
            continue
        a = acc[(r["station_no"], r["station_name"], r["phenomenon"])]
        a["years"] += 1
        y = int(r["year"])
        if r["status"] == OBSERVED:
            a["observed"] += 1
            a["first"] = y if a["first"] is None else min(a["first"], y)
            a["last"] = y if a["last"] is None else max(a["last"], y)
        else:
            a["no_value"] += 1
    return dict(acc)


def region_station_nos(definition, region, *, include_islands=True):
    return {s["station_no"] for s in definition.get("stations") or [] if s["region"] == region and (include_islands or not s.get("island"))}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ikimonobiyori.jma_phenology")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("normalize", help="raw の CSV を正規化して --out に書く(通信しない)")
    n.add_argument("--raw-dir", required=True)
    n.add_argument("--out", required=True)
    s = sub.add_parser("summary", help="正規化した CSV の件数のまとめ(地点 × 現象)")
    s.add_argument("--normalized", required=True)
    s.add_argument("--region")
    a = ap.parse_args(argv)
    df = load_definition()
    if a.cmd == "normalize":
        rows, infos, missing = normalize(a.raw_dir, df)
        write_csv(rows, a.out, attribution_lines(df))
        for i in infos:
            print(f"{i['file']} {i['phenomenon']}: 地点 {i['stations']}、{i['first_year']}〜{i['last_year_with_value']} 年、{i['rows']} 行")
        if missing:
            print("見つからなかった現象: " + ", ".join(missing))
        print(f"→ {a.out}({len(rows)} 行)。出典: " + ATTRIBUTION.format(page=df["source_page"]))
        return 0
    rows = read_csv(a.normalized)
    nos = region_station_nos(df, a.region) if a.region else None
    print("地点\t現象\t年数\t値あり\t値なし\t最初\t最後")
    for (no, name, ph), v in sorted(summarize(rows, nos).items()):
        print(f"{no} {name}\t{ph}\t{v['years']}\t{v['observed']}\t{v['no_value']}\t{v['first'] or ''}\t{v['last'] or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
