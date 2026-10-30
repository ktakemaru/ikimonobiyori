"""野鳥の案内ページの代表写真の、表・キャッシュ・コマンド(段階29。docs/stage29-decisions.md)。通信そのものは fetch/inat_photos.py。

  python -X utf8 -m ikimonobiyori.guide photos-build-table --live --max-requests N [--theme 野鳥]
  python -X utf8 -m ikimonobiyori.guide photos-fetch --live --max-requests N
  python -X utf8 -m ikimonobiyori.guide photos-clear

- 表 data/guide/bird_taxa.yaml は事実だけ(和名 → 学名・taxon id・確認日)。画像・写真の URL・撮影者名は含まない(コミットしてよい)。
  photos-build-table の書き込み先は IKIMONOBIYORI_DATA_DIR の下の guide/export/(見直して data/guide/ に写す。既存の build と同じ流れ)。
- 写真(画像・撮影者の表記・ライセンス・写真のページの URL)のキャッシュは IKIMONOBIYORI_DATA_DIR の下の guide/photos/ だけ(コミットしない)。
- 通信は --live・BIYORI_ALLOW_LIVE=1・明示的な --max-requests・計測フック(BIYORI_REQ_LOG)がそろったときだけ(places-fetch と同じ)。
  1 回の実行の上限は policy の photos.max_requests_per_run。"""
import json
import os
import sys

import yaml

from . import guide, livegate
from .config import load_config
from .fetch import inat_photos


def photos_policy(policy=None):
    return (policy or guide.load_policy())["photos"]


def table_path(policy=None):
    return guide.GUIDE_DIR / photos_policy(policy)["table_file"]


def export_dir(env=None):
    return guide.guide_dir(env) / "export"


def cache_dir(env=None, policy=None):
    return guide.guide_dir(env) / photos_policy(policy)["cache_dir"]


def page_dir(env=None, policy=None):
    return guide.guide_dir(env) / photos_policy(policy)["page_dir"]


# ---- 表(和名 → 学名・taxon id・確認日) ----

def _read_table(path):
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(doc.get("taxa") or [])


def load_table(env=None, include_runtime=True, policy=None):
    """{和名: {name, scientific, taxon_id, checked_on}}。data/guide/ の表が先(同じ和名は上書きしない)。手元の書き出し(export/)も読む。"""
    ph = photos_policy(policy)
    rows = {r["name"]: r for r in _read_table(table_path(policy))}
    if include_runtime:
        for r in _read_table(export_dir(env) / ph["table_file"]):
            rows.setdefault(r["name"], r)
    return rows


def table_text(rows, policy=None):
    ph = photos_policy(policy)
    head = ("# 野鳥の種の対応表(段階29)。和名 → 学名 / iNaturalist の taxon id / 確認日。事実だけで、画像・写真の URL・撮影者名は含まない。\n"
            "# guide photos-build-table が作る(手で直さない)。和名が日本語の一般名と完全に一致し、ランクが species・鳥類で、候補がちょうど 1 件のものだけ。\n")
    taxa = [{k: r[k] for k in ("name", "scientific", "taxon_id", "checked_on")} for r in sorted(rows.values(), key=lambda r: r["name"])]
    return head + yaml.safe_dump({"schema": ph["table_schema"], "taxa": taxa}, allow_unicode=True, sort_keys=False, width=200)


def load_rejected(env=None, policy=None):
    p = export_dir(env) / photos_policy(policy)["rejected_file"]
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def species_names(entries, themes, policy=None):
    """答えに出る種名(独立した発行元 2 件以上が言う種名)の和名の一覧。承認済みの名所の shown な種名と、承認済みの種類の説明の名前。範囲の外の名所は含めない。"""
    out = set()
    for e in entries:
        if e["theme"] not in themes or not guide.approved(e):
            continue
        if e.get("scope", "place") == "kind":
            out.add(e["name"])
        elif e["range"]["status"] != "out_of_range":
            out |= {k["kind"] for k in e["kinds"] if k["shown"]}
    return sorted(out)


# ---- キャッシュ ----

def _meta_path(taxon_id, env=None, policy=None):
    return cache_dir(env, policy) / f"{int(taxon_id)}.json"


def has_cache(taxon_id, env=None, policy=None):
    mp = _meta_path(taxon_id, env, policy)
    if not mp.is_file():
        return False
    meta = json.loads(mp.read_text(encoding="utf-8"))
    return (cache_dir(env, policy) / f"{int(taxon_id)}.{meta['image_type']}").is_file()


def save_photo(item, env=None, policy=None):
    d = cache_dir(env, policy)
    d.mkdir(parents=True, exist_ok=True)
    tid = int(item["meta"]["taxon_id"])
    (d / f"{tid}.{item['ext']}").write_bytes(item["data"])
    _meta_path(tid, env, policy).write_text(json.dumps(item["meta"], ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline="\n")


def load_photo(taxon_id, env=None, policy=None):
    """→ (メタデータ, 画像のバイト列) か None。"""
    if not has_cache(taxon_id, env, policy):
        return None
    meta = json.loads(_meta_path(taxon_id, env, policy).read_text(encoding="utf-8"))
    return meta, (cache_dir(env, policy) / f"{int(taxon_id)}.{meta['image_type']}").read_bytes()


def clear_cache(env=None, policy=None):
    """写真のキャッシュだけを消す(ほかは消さない)。→ 消したファイルの数。"""
    d = cache_dir(env, policy)
    n = 0
    if d.is_dir():
        for f in d.iterdir():
            if f.is_file():
                f.unlink()
                n += 1
        if not any(d.iterdir()):
            d.rmdir()
    return n


# ---- コマンド ----

def _gate(a, http_get, name):
    """--live の条件(places-fetch と同じ)。満たさなければ (終了コード, None)、満たせば (None, 1 回の実行で使える上限)。"""
    if not a.live:
        print(f"{name} は --live が必要です", file=sys.stderr)
        return 2, None
    if http_get is None and not livegate.live_allowed():
        print(livegate.refusal(), file=sys.stderr)
        return 2, None
    if a.max_requests is None or a.max_requests < 1:
        print("--live は明示的な --max-requests (1 以上)が必要です", file=sys.stderr)
        return 2, None
    if http_get is None and not os.environ.get("BIYORI_REQ_LOG"):
        print("--live は計測フック(BIYORI_REQ_LOG)が有効なときだけ実行します", file=sys.stderr)
        return 2, None
    return None, min(a.max_requests, photos_policy()["max_requests_per_run"]["value"])


def _getters(http_get, http_bytes):
    cfg = load_config()
    if http_get is not None:
        return None, http_get, http_bytes
    from .fetch.live import SessionGetter
    t = cfg["live"]["request_timeout"]
    g = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"])
    return g, g, g.get_bytes


def _log_requests(n, kind, env=None):
    guide._append_jsonl(guide.guide_dir(env) / "photos_requests.jsonl", [{"at": guide.clock_now().isoformat(), "kind": kind, "requests": n}])


def build_table_cmd(a, http_get=None):
    err, left = _gate(a, http_get, "photos-build-table")
    if err:
        return err
    policy = guide.load_policy()
    ph = policy["photos"]
    themes, kinds = guide.themes_for_words([a.theme], policy)
    if themes is None:
        print(f"言い換えの表にない言葉: {kinds}", file=sys.stderr)
        return 1
    table, rejected = load_table(), load_rejected()
    names = [n for n in species_names(guide.build()[0], themes, policy) if n not in table and n not in rejected]
    getter, hg, _ = _getters(http_get, None)
    try:
        entered, no, rep = inat_photos.build_table(names, http_get=hg, ph=ph, max_requests=left)
    finally:
        if getter is not None:
            getter.close()
    for r in entered:
        table[r["name"]] = r
    rejected.update(no)
    out = export_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / ph["table_file"]).write_text(table_text(table, policy), encoding="utf-8", newline="\n")
    (out / ph["rejected_file"]).write_text(json.dumps(rejected, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline="\n")
    _log_requests(rep["requests"], "build-table")
    guide._dump({"asked": len(names), "entered": [r["name"] for r in entered], "not_entered": no, "table_size": len(table), "report": rep,
                 "export": str(out / ph["table_file"])})
    return 0 if rep["status"] == "ok" else 1


def fetch_cmd(a, http_get=None, http_bytes=None):
    err, left = _gate(a, http_get or http_bytes, "photos-fetch")
    if err:
        return err
    policy = guide.load_policy()
    ph = policy["photos"]
    rows = sorted(load_table().values(), key=lambda r: r["name"])
    getter, hg, hb = _getters(http_get, http_bytes)
    try:
        got, unused, rep = inat_photos.fetch_photos(rows, http_get=hg, http_bytes=hb, ph=ph, max_requests=left, has_cache=lambda t: has_cache(t))
    finally:
        if getter is not None:
            getter.close()
    for item in got:
        save_photo(item)
    _log_requests(rep["requests"], "fetch")
    guide._dump({"table_size": len(rows), "saved": [i["row"]["name"] for i in got], "not_used": unused, "report": rep, "cache": str(cache_dir())})
    return 0 if rep["status"] == "ok" else 1


def clear_cmd(a):
    n = clear_cache()
    guide._dump({"removed": n, "cache": str(cache_dir())})
    return 0
