"""記録の置き場所を 1 か所にまとめる移行(段階37。1 回だけ実行する。指示書 docs/stage37-H11-instructions.md 2-2)。

以前は記録が 2 か所に分かれていた(単体: <リポジトリ>/runtime/ikimonobiyori、biyori-hub 経由: <ハブ>/runtime-data/ikimonobiyori)。
元のフォルダの中身を、新しい置き場所(IKIMONOBIYORI_DATA_DIR。無ければ Windows は %LOCALAPPDATA%\\ikimonobiyori)へ
**コピーして合わせる**。元のフォルダは読むだけで、消さない・書き換えない(戻せるように残す)。

  python -X utf8 -m ikimonobiyori.migrate_data --dry-run [--from DIR ...]
  python -X utf8 -m ikimonobiyori.migrate_data [--from DIR ...]

--from を省くと、以前の既定(<リポジトリ>/runtime/ikimonobiyori)だけ。ハブのフォルダは --from で明示する(このパッケージは外を指さない)。
合わせ方:
- 観察の記録(observations/<対象>.jsonl): 同じ名所・同じ状態の語・同じ状態の日付(と同じ例年の時期・行事)は 1 件にまとめる
  (最初に読んだ記録を残し、あとの読んだ時刻は observations/<対象>.confirmed.json の「最後に確かめた日時」にする。observations.record と同じ規則)。
- ほかの JSON Lines(現況の記録 status_log/ など): 中身が同じ行を 1 行にまとめる(並びは、新しい置き場所 → 元のフォルダの順に最初に出た順)。
- 区域の集計の索引(observations/inat_index.json)・最後に確かめた日時: 区域・記録ごとに合わせる(新しいほう)。
- それ以外のファイル(キャッシュ・部品など): 無ければコピー。同じ中身なら何もしない。違えば更新時刻の新しいほうを残す。"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from . import observations as O
from .paths import LEGACY_DATA_DIR, data_dir


def _jsonl(path):
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"_raw": line})
    return out


def _canon(r):
    return json.dumps(r, ensure_ascii=False, sort_keys=True)


def _obs_key(r):
    if "_raw" in r or not r.get("read_at"):
        return "raw:" + _canon(r)
    if not r.get("state_date"):
        r = {**r, "state_date_from_text": O.state_date_from_text(r.get("state"), r["read_at"])}
    return O.dup_key_text(r)


def plan(sources, target):
    """→ (操作の一覧, 集計)。書き込まない。"""
    target = Path(target)
    files = {}                                     # 相対パス → [元のファイル(新しい置き場所が先)]
    for root in [target] + [Path(s) for s in sources]:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file():
                files.setdefault(p.relative_to(root).as_posix(), []).append(p)
    ops, stats = [], {"sources": [str(s) for s in sources], "target": str(target), "files_seen": 0, "copied": 0, "unchanged": 0,
                      "replaced_by_newer": 0, "kept_target_newer": 0, "jsonl": {}, "observations": {}}
    confirmed_extra = {}
    for rel, ps in sorted(files.items()):
        src = [p for p in ps if not _is_under(p, target)]
        tgt = target / rel
        stats["files_seen"] += len(src)
        if not src:
            continue
        if rel.startswith("observations/") and rel.endswith(".jsonl"):
            subject = Path(rel).stem
            seen, rows, dup, conf = {}, [], 0, {}
            n_in = 0
            for p in ps:
                for r in _jsonl(p):
                    n_in += 1
                    k = _obs_key(r)
                    if k in seen:
                        dup += 1
                        ra = r.get("read_at") or ""
                        first = seen[k]
                        if ra and ra != first.get("read_at") and ra > (conf.get(k, {}).get("last_confirmed_at") or ""):
                            conf[k] = {"last_confirmed_at": ra, "url": r.get("url")}
                        continue
                    seen[k] = r
                    rows.append(r)
            rows.sort(key=lambda r: r.get("read_at") or "")
            ops.append(("write_jsonl", tgt, rows))
            confirmed_extra[subject] = conf
            stats["observations"][rel] = {"lines_in": n_in, "written": len(rows), "merged_duplicates": dup,
                                          "target_before": len(_jsonl(tgt)) if tgt.is_file() else 0}
        elif rel.endswith(".jsonl"):
            seen, rows, dup, n_in = set(), [], 0, 0
            for p in ps:
                for r in _jsonl(p):
                    n_in += 1
                    c = _canon(r)
                    if c in seen:
                        dup += 1
                        continue
                    seen.add(c)
                    rows.append(r)
            ops.append(("write_jsonl", tgt, rows))
            stats["jsonl"][rel] = {"lines_in": n_in, "written": len(rows), "merged_duplicates": dup,
                                   "target_before": len(_jsonl(tgt)) if tgt.is_file() else 0}
        elif rel == "observations/inat_index.json" or (rel.startswith("observations/") and rel.endswith(".confirmed.json")):
            ops.append(("merge_json", tgt, ps))
        else:
            newest = max(src, key=lambda p: p.stat().st_mtime)
            if not tgt.is_file():
                ops.append(("copy", tgt, newest))
                stats["copied"] += 1
            elif all(p.read_bytes() == tgt.read_bytes() for p in src):
                stats["unchanged"] += 1
            elif newest.stat().st_mtime > tgt.stat().st_mtime and newest.read_bytes() != tgt.read_bytes():
                ops.append(("copy", tgt, newest))
                stats["replaced_by_newer"] += 1
            else:
                stats["kept_target_newer"] += 1
    for subject, conf in confirmed_extra.items():
        if conf:
            ops.append(("merge_confirmed", target / "observations" / f"{subject}.confirmed.json", conf))
    stats["observations_total"] = {k: sum(v[k] for v in stats["observations"].values()) for k in ("lines_in", "written", "merged_duplicates")}
    stats["jsonl_total"] = {k: sum(v[k] for v in stats["jsonl"].values()) for k in ("lines_in", "written", "merged_duplicates")}
    return ops, stats


def _is_under(p, root):
    try:
        Path(p).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def _read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _merge_index(docs):
    areas = {}
    for d in docs:
        for a, ents in ((d or {}).get("areas") or {}).items():
            have = areas.setdefault(a, [])
            for e in ents if isinstance(ents, list) else [ents]:
                if e not in have:
                    have.append(e)
    for a in areas:
        areas[a].sort(key=lambda e: (e.get("fetched_at") or "") if isinstance(e, dict) else "")
    return {"schema": "ikimono-inat-index/1", "areas": areas}


def _merge_confirmed(docs):
    out = {}
    for d in docs:
        for k, v in (d or {}).items():
            if isinstance(v, dict) and (v.get("last_confirmed_at") or "") > (out.get(k, {}).get("last_confirmed_at") or ""):
                out[k] = v
    return out


def apply(ops):
    for kind, tgt, x in ops:
        tgt.parent.mkdir(parents=True, exist_ok=True)
        if kind == "copy":
            shutil.copy2(x, tgt)
        elif kind == "write_jsonl":
            tmp = tgt.with_name("." + tgt.name + ".tmp")
            tmp.write_text("".join((r["_raw"] if "_raw" in r else json.dumps(r, ensure_ascii=False)) + "\n" for r in x), encoding="utf-8", newline="\n")
            tmp.replace(tgt)
        elif kind == "merge_json":
            docs = [_read_json(p) for p in x]
            doc = _merge_index(docs) if tgt.name == "inat_index.json" else _merge_confirmed(docs)
            tgt.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        elif kind == "merge_confirmed":
            doc = _merge_confirmed([_read_json(tgt), x])
            tgt.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="migrate_data", description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="sources", action="append", help="元のフォルダ(複数可。省略時は以前の既定 <リポジトリ>/runtime/ikimonobiyori)")
    ap.add_argument("--dry-run", action="store_true", help="書き込まずに、合わせた結果の件数だけを出す")
    a = ap.parse_args(argv)
    target = data_dir()
    sources = [Path(s) for s in (a.sources or [str(LEGACY_DATA_DIR)])]
    bad = [str(s) for s in sources if _is_under(s, target) or _is_under(target, s)]
    if bad:
        print(f"元のフォルダと新しい置き場所が重なっています: {bad}", file=sys.stderr)
        return 2
    ops, stats = plan(sources, target)
    stats["dry_run"] = a.dry_run
    stats["operations"] = len(ops)
    if not a.dry_run:
        apply(ops)
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
