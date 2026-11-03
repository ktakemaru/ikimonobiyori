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
from .fetch import commons_photos, inat_photos


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


def load_sources(env=None, include_runtime=True, policy=None):
    """{和名: 出どころ}(表の sources の欄。ユーザー指定の学名など)。"""
    ph = photos_policy(policy)
    out = {}
    paths_ = [table_path(policy)] + ([export_dir(env) / ph["table_file"]] if include_runtime else [])
    for p in paths_:
        if p.is_file():
            for k, v in ((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("sources") or {}).items():
                out.setdefault(k, v)
    return out


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
            "# guide photos-build-table が作る(手で直さない)。和名が日本語の一般名と完全に一致し、ランクが species・鳥類で、候補がちょうど 1 件のもの(候補が複数のときは、種が 1 件でほかがその下位のもの)。\n"
            "# sources の欄にある和名は、ユーザー指定の学名(iNaturalist で学名・ランク・鳥類が一致したもの)。\n")
    ordered = sorted(rows.values(), key=lambda r: r["name"])
    taxa = [{k: r[k] for k in ("name", "scientific", "taxon_id", "checked_on")} for r in ordered]
    doc = {"schema": ph["table_schema"], "taxa": taxa}
    srcs = {r["name"]: r["source"] for r in ordered if r.get("source")}
    if srcs:                                                     # 出どころの欄(行の項目ではなく別の欄。行は事実の 4 項目のまま)
        doc["sources"] = srcs
    return head + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200)


def load_rejected(env=None, policy=None):
    p = export_dir(env) / photos_policy(policy)["rejected_file"]
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def review_path(env=None, policy=None):
    return export_dir(env) / photos_policy(policy)["review_file"]


def load_review(env=None, policy=None):
    """目で見て写真を使わないと決めた種 {taxon_id(文字列): 理由}。手元の書き出しで、コミットしない。"""
    p = review_path(env, policy)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def exclude_photo(taxon_id, reason, env=None, policy=None, source=None):
    """写真を目で見て使わないと決めた種: 理由を残し、キャッシュの写真を消す(取り直さない)。
    source="commons" のときは Commons の写真だけを使わない(iNaturalist の写真は別。キーは commons:<id>)。"""
    key = (f"{source}:" if source else "") + str(int(taxon_id))
    rv = load_review(env, policy)
    rv[key] = reason
    review_path(env, policy).parent.mkdir(parents=True, exist_ok=True)
    review_path(env, policy).write_text(json.dumps(rv, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline="\n")
    return _remove_cache(taxon_id, env, policy)


def _remove_cache(taxon_id, env=None, policy=None):
    d = cache_dir(env, policy)
    n = 0
    for f in d.glob(f"{int(taxon_id)}.*") if d.is_dir() else []:
        f.unlink()
        n += 1
    return n


def skip_photo_path(env=None, policy=None):
    return export_dir(env) / photos_policy(policy)["skip_photo_file"]


def load_skip_photos(env=None, policy=None):
    """目で見て使わないと決めた iNaturalist の写真 {taxon_id: {photo_id, ...}}(種は残し、別の写真を選び直す)。"""
    p = skip_photo_path(env, policy)
    raw = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    return {int(k): {int(x) for x in v} for k, v in raw.items()}


def exclude_inat_photo(taxon_id, env=None, policy=None):
    """キャッシュにある iNaturalist の写真だけを使わないと決める(種は残す。次の photos-fetch が別の候補を選ぶ)。→ 除いた写真の id。"""
    meta = json.loads(_meta_path(taxon_id, env, policy).read_text(encoding="utf-8"))
    if meta.get("source") or meta.get("photo_id") is None:
        raise ValueError("iNaturalist の写真ではない")
    skip = load_skip_photos(env, policy)
    skip.setdefault(int(taxon_id), set()).add(int(meta["photo_id"]))
    skip_photo_path(env, policy).parent.mkdir(parents=True, exist_ok=True)
    skip_photo_path(env, policy).write_text(json.dumps({str(k): sorted(v) for k, v in skip.items()}, sort_keys=True, indent=1), encoding="utf-8", newline="\n")
    _remove_cache(taxon_id, env, policy)
    return meta["photo_id"]


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

def _gate(a, http_get, name, cap=None):
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
    # 段階38(利用者の決定 2026-11-01): 計測フック(BIYORI_REQ_LOG)がなければ、自前の上限(netbudget。_getters が包む)の下で取る
    return None, min(a.max_requests, (cap or photos_policy()["max_requests_per_run"])["value"])


def _only(a):
    """--only の和名(なければ空 = 全部)。"""
    v = getattr(a, "only", None)
    return set(v) if isinstance(v, (list, tuple)) else set()


def _getters(http_get, http_bytes, budget_kind="photos"):
    cfg = load_config()
    if http_get is not None:
        return None, http_get, http_bytes
    from . import netbudget
    from .fetch.live import SessionGetter
    t = cfg["live"]["request_timeout"]
    g = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"])
    ph = photos_policy()
    hs = cfg["live"]["allowed_hosts_by_subject"]
    if budget_kind == "commons":                                 # 段階38: 実通信は自前の上限(上限・間隔・許可ホスト・記録)で包む
        b = netbudget.Budget("photos_commons", hs["guide_photos_commons"] + hs["guide_places"], ph["commons"]["max_requests_per_run"]["value"],
                             ph["commons"]["min_interval_s"]["value"])
    else:
        b = netbudget.Budget("photos", hs["guide_photos"], ph["max_requests_per_run"]["value"], ph["min_interval_s"]["value"])
    return g, b(g), b(g.get_bytes)


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
    if getattr(a, "recheck", False) is True:                             # 条件を変えたとき: 前に入らなかった和名も調べ直す(種を特定しない語は inat_photos.skipped が除く)
        rejected = {}
    names = [n for n in species_names(guide.build()[0], themes, policy) if n not in table and n not in rejected]
    named = None
    if getattr(a, "named", False) is True:                               # ユーザー指定の学名の種だけ(学名で検索)
        named = {n: sci for n, sci in ph["named_scientific"].items() if n not in table}
        names = list(named)
    getter, hg, _ = _getters(http_get, None)
    try:
        entered, no, rep = inat_photos.build_table(names, http_get=hg, ph=ph, max_requests=left, named=named)
    finally:
        if getter is not None:
            getter.close()
    for r in entered:
        table[r["name"]] = r
    for n, src in load_sources().items():                        # 出どころの欄は、書き出すときに行へ戻して sources の欄に書く
        if n in table and "source" not in table[n]:
            table[n] = {**table[n], "source": src}
    rejected.update(no)
    out = export_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / ph["table_file"]).write_text(table_text(table, policy), encoding="utf-8", newline="\n")
    (out / ph["rejected_file"]).write_text(json.dumps(rejected, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline="\n")
    _log_requests(rep["requests"], "build-table")
    multi = {**(json.loads((out / ph["multi_file"]).read_text(encoding="utf-8")) if (out / ph["multi_file"]).is_file() else {}), **rep["multi_candidate"]}
    (out / ph["multi_file"]).write_text(json.dumps(multi, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline="\n")
    guide._dump({"asked": len(names), "entered": [r["name"] for r in entered], "not_entered": no, "table_size": len(table), "report": rep,
                 "export": str(out / ph["table_file"])})
    return 0 if rep["status"] == "ok" else 1


def fetch_cmd(a, http_get=None, http_bytes=None):
    err, left = _gate(a, http_get or http_bytes, "photos-fetch")
    if err:
        return err
    policy = guide.load_policy()
    ph = policy["photos"]
    review = load_review()
    only = _only(a)
    rows = sorted((r for r in load_table().values() if str(r["taxon_id"]) not in review and (not only or r["name"] in only)), key=lambda r: r["name"])
    getter, hg, hb = _getters(http_get, http_bytes)
    try:
        got, unused, rep = inat_photos.fetch_photos(rows, http_get=hg, http_bytes=hb, ph=ph, max_requests=left, has_cache=lambda t: has_cache(t),
                                                    skip_photos=load_skip_photos())
    finally:
        if getter is not None:
            getter.close()
    for item in got:
        save_photo(item)
    _log_requests(rep["requests"], "fetch")
    guide._dump({"table_size": len(rows), "saved": [i["row"]["name"] for i in got], "not_used": unused, "report": rep, "cache": str(cache_dir())})
    return 0 if rep["status"] == "ok" else 1


def commons_cmd(a, http_get=None, http_bytes=None):
    """photos-commons: 写真のない種(キャッシュにない種)だけ、Wikimedia Commons から取る。1 種ずつ順番に。"""
    policy = guide.load_policy()
    ph = policy["photos"]
    err, left = _gate(a, http_get or http_bytes, "photos-commons", ph["commons"]["max_requests_per_run"])
    if err:
        return err
    review = load_review()
    only = _only(a)
    rows = sorted((r for r in load_table().values() if (not only or r["name"] in only)), key=lambda r: r["name"])
    skip = {r["taxon_id"] for r in rows if f"commons:{r['taxon_id']}" in review}
    getter, hg, hb = _getters(http_get, http_bytes, "commons")
    try:
        got, unused, rep = commons_photos.fetch_commons(rows, http_get=hg, http_bytes=hb, ph=ph, max_requests=left,
                                                        has_cache=lambda t: has_cache(t), skip=skip, on_got=save_photo)
    finally:
        if getter is not None:
            getter.close()
    _log_requests(rep["requests"], "commons")
    guide._dump({"table_size": len(rows), "saved": [i["row"]["name"] for i in got], "not_used": unused, "report": rep, "cache": str(cache_dir())})
    return 0 if rep["status"] == "ok" else 1


def commons_season_cmd(a, http_get=None, http_bytes=None):
    """photos-commons-season: 指定の種(--only)について、Commons で冬羽(季節の語のある)の写真を探して取る。成功したときだけキャッシュを置き換える(段階31)。"""
    policy = guide.load_policy()
    ph = policy["photos"]
    err, left = _gate(a, http_get or http_bytes, "photos-commons-season", ph["commons"]["max_requests_per_run"])
    if err:
        return err
    only = _only(a)
    if not only:
        print("photos-commons-season は --only で種を指定してください", file=sys.stderr)
        return 2
    rows = [r for n, r in sorted(load_table().items()) if n in only]
    getter, hg, hb = _getters(http_get, http_bytes, "commons")
    saved, unused, reps, used = [], {}, [], 0
    try:
        for row in rows:
            got, un, rep = commons_photos.fetch_commons_season(row, http_get=hg, http_bytes=hb, ph=ph, max_requests=left - used, on_got=save_photo, wait_first=bool(reps))
            used += rep["requests"]
            saved += [i["row"]["name"] for i in got]
            unused.update(un)
            reps.append({row["name"]: rep})
            if rep["status"] != "ok" or rep["stopped"]:
                break
    finally:
        if getter is not None:
            getter.close()
    _log_requests(used, "commons-season")
    guide._dump({"saved": saved, "not_used": unused, "reports": reps, "requests": used, "cache": str(cache_dir())})
    return 0 if all(next(iter(r.values()))["status"] == "ok" for r in reps) else 1


def clear_cmd(a):
    n = clear_cache()
    guide._dump({"removed": n, "cache": str(cache_dir())})
    return 0
