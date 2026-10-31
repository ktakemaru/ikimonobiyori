"""名所カタログ(花)の監査(段階32の続き。通信しない・書き込まない)。
紹介サイトなど(公式ではない)で読んだ値(flower_windows・events)を一覧にする。出所の区分(source_class: secondary と source_host。
旧い印 unapproved_host も同じ)のある値は、候補の根拠に使い、答えでは出所と日付を添える(段階34)。公式の通信先の外なのに区分がない値は
『区分の漏れ』として別に出す(出所の記録のため)。

  python -X utf8 -m ikimonobiyori.catalog_audit [--subject flowers] [--out <ファイル名>]
--out を付けると、結果をそのファイルにも書く(既定は画面のみ。--out は書き込み先を指定するので、リポジトリの docs/ などを自分で選ぶ)。
"""
import argparse
import json
import sys
from urllib.parse import urlparse

from . import catalog as catalog_mod
from . import regional

NEEDS = "公式ではない出所(答えでは出所と日付を添える)"


def audit(doc, hosts):
    """→ {needs_confirmation: [...], missing_mark: [...], bad_mark: [...]}。"""
    needs, missing, bad = [], [], []
    for e in doc.get("entries") or []:
        for field in ("flower_windows", "events"):
            for v in e.get(field) or []:
                host = urlparse(v["source_url"]).hostname or ""
                outside = not regional.host_allowed(v["source_url"], hosts)
                marked = regional.is_secondary(v)
                row = {"id": e["id"], "name": e["name"], "status": e.get("status"), "field": field, "kind": v["kind"],
                       "start": v["start"], "end": v["end"], "host": host, "source_url": v["source_url"]}
                if outside and not marked:
                    missing.append(row)
                elif marked and (not outside or v.get("source_host") != host):
                    bad.append(row)
                elif marked:
                    needs.append({**row, "action": NEEDS, "source_class": "secondary"})
    return {"needs_confirmation": needs, "missing_mark": missing, "bad_mark": bad}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="catalog_audit")
    ap.add_argument("--subject", default="flowers")
    ap.add_argument("--out", help="結果をこのファイルにも書く(既定は画面のみ)")
    a = ap.parse_args(argv)
    doc = catalog_mod.load_catalog(a.subject)
    hosts = regional.load_policy()["approved_hosts"]["hosts"]
    out = audit(doc, hosts)
    text = json.dumps(out, ensure_ascii=False, indent=1)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            f.write(text + chr(10))
    return 1 if out["missing_mark"] or out["bad_mark"] else 0


if __name__ == "__main__":
    sys.exit(main())
