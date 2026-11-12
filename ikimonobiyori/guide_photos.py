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
import re
import os
import sys

import yaml

from . import yamlcache
from . import guide, livegate
from .config import load_config
from .fetch import commons_photos, inat_photos
from .fetch.live import LiveError


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
    doc = yamlcache.load(path) or {}
    return list(doc.get("taxa") or [])


def load_sources(env=None, include_runtime=True, policy=None):
    """{和名: 出どころ}(表の sources の欄。ユーザー指定の学名など)。"""
    ph = photos_policy(policy)
    out = {}
    paths_ = [table_path(policy)] + ([export_dir(env) / ph["table_file"]] if include_runtime else [])
    for p in paths_:
        if p.is_file():
            for k, v in ((yamlcache.load(p) or {}).get("sources") or {}).items():
                out.setdefault(k, v)
    return out


def table_files(policy=None):
    """対応表のファイル名(野鳥の既定 + テーマごとの表。段階39)。"""
    ph = photos_policy(policy)
    names = [ph["table_file"]] + [t["table_file"] for t in (ph.get("themes") or {}).values() if t.get("table_file")]
    return list(dict.fromkeys(names))


def load_table(env=None, include_runtime=True, policy=None):
    """{和名: {name, scientific, taxon_id, checked_on}}。data/guide/ の表が先(同じ和名は上書きしない)。手元の書き出し(export/)も読む。
    野鳥の表(bird_taxa.yaml)に加え、テーマごとの表(花・野草。段階39)も合わせて読む。"""
    rows = {}
    for f in table_files(policy):
        for r in _read_table(table_path(policy) if f == photos_policy(policy)["table_file"] else guide.GUIDE_DIR / f):
            rows.setdefault(r["name"], r)
    if include_runtime:
        for f in table_files(policy):
            for r in _read_table(export_dir(env) / f):
                rows.setdefault(r["name"], r)
    return rows


def table_text(rows, policy=None, theme=None):
    ph = photos_policy(policy)
    head = (f"# {theme or '野鳥'}の種の対応表(段階29・39)。和名 → 学名 / iNaturalist の taxon id / 確認日。事実だけで、画像・写真の URL・撮影者名は含まない。\n"
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


def phenology_cfg(theme, policy=None):
    """段階53: 花の写真の規則（開花 ＞ つぼみ）を当てるテーマなら方針の phenology、そうでなければ None。"""
    pp = photos_policy(policy).get("phenology")
    return pp if pp and theme in pp["themes"] else None


def stale_for_rule(taxon_id, pp, env=None, policy=None):
    """キャッシュの写真が新しい規則の版で評価されていないか。"""
    mp = _meta_path(taxon_id, env, policy)
    if not mp.is_file():
        return False
    return json.loads(mp.read_text(encoding="utf-8")).get("rule") != pp["rule_version"]["value"]


def archive_rejected(taxon_id, pp, reason, env=None, policy=None):
    """新しい規則で外れた写真を、消さずに rejected/ へ移して「不採用」の印を付ける。"""
    d = cache_dir(env, policy)
    mp = _meta_path(taxon_id, env, policy)
    meta = json.loads(mp.read_text(encoding="utf-8"))
    out = d / pp["rejected_dir"]
    out.mkdir(parents=True, exist_ok=True)
    tag = re.sub(r"[^0-9A-Za-z_-]", "_", str(meta.get("photo_id") or meta.get("source") or "x"))[:40]       # 段階54: 取得した値をファイル名に使うときは無害化する
    stem = f"{int(taxon_id)}-{tag}"
    img = d / f"{int(taxon_id)}.{meta['image_type']}"
    if img.is_file():
        (out / f"{stem}.{meta['image_type']}").write_bytes(img.read_bytes())
    meta["rejected_by_rule"] = pp["rule_version"]["value"]
    meta["rejected_reason"] = reason
    (out / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline="\n")


def stamp_unknown(taxon_id, pp, env=None, policy=None):
    """新しい規則で良い写真が見つからない種: 今の写真を「状態: 不明」として残し、評価済みの印を付ける（毎回探し直さない）。"""
    mp = _meta_path(taxon_id, env, policy)
    meta = json.loads(mp.read_text(encoding="utf-8"))
    meta.setdefault("state", pp["unknown_label"])
    meta["rule"] = pp["rule_version"]["value"]
    mp.write_text(json.dumps(meta, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline="\n")


def load_photo(taxon_id, env=None, policy=None):
    """→ (メタデータ, 画像のバイト列) か None。段階82: 点検で不可にした写真は使わない(点検済みで可 > 未点検)。"""
    if not has_cache(taxon_id, env, policy):
        return None
    meta = json.loads(_meta_path(taxon_id, env, policy).read_text(encoding="utf-8"))
    chk = load_checks(env, policy).get(str(int(taxon_id)))
    if chk and chk.get("verdict") == "ng" and chk.get("photo_page") == meta.get("photo_page"):
        return None
    return meta, (cache_dir(env, policy) / f"{int(taxon_id)}.{meta['image_type']}").read_bytes()


# ---- 段階82 第4部: 写真の点検(目で見た判定の記録・不可の写真の控えと除外・取り直し) ----

NL_ = chr(10)


def check_path(env=None, policy=None):
    return export_dir(env) / photos_policy(policy)["check_file"]


def load_checks(env=None, policy=None):
    p = check_path(env, policy)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except ValueError:
        return {}


def _save_json(p, doc):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline=NL_)


def load_commons_denied(env=None, policy=None):
    p = export_dir(env) / photos_policy(policy)["commons_deny_file"]
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []
    except ValueError:
        return []


def cached_photos(env=None, policy=None):
    """キャッシュにある写真の一覧 [{taxon_id, name, path, meta, check}](和名の順)。check はこの写真の点検の記録(なければ None = 未点検)。"""
    d = cache_dir(env, policy)
    checks = load_checks(env, policy)
    out = []
    for mp in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
            tid = int(meta["taxon_id"])
        except (ValueError, KeyError, TypeError, OSError):
            continue
        img = d / f"{tid}.{meta.get('image_type')}"
        if not img.is_file():
            continue
        c = checks.get(str(tid))
        out.append({"taxon_id": tid, "name": meta.get("name"), "path": str(img), "meta": meta,
                    "check": c if c and c.get("photo_page") == meta.get("photo_page") else None})
    return sorted(out, key=lambda r: (r["name"] or "", r["taxon_id"]))


def commons_title(meta):
    from urllib.parse import unquote
    return unquote("File:" + (meta.get("photo_page") or "").rsplit("File:", 1)[-1]).replace("_", " ")


def checked_ok(taxon_id, env=None, policy=None):
    """今のキャッシュの写真が、点検済みで可か(点検の記録の元のページが今の写真と同じ)。"""
    mp = _meta_path(taxon_id, env, policy)
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    c = load_checks(env, policy).get(str(int(taxon_id)))
    return bool(c and c.get("verdict") == "ok" and c.get("photo_page") == meta.get("photo_page"))


def set_check(taxon_id, verdict, reason=None, *, today, env=None, policy=None):
    """写真を見て点検した結果を残す。verdict は ok / ng。ng のときは写真を消さずに控え(check_archive_dir)へ写し、
    iNaturalist の写真なら写真の id を、Commons ならファイル名を、次に選ばない一覧に入れてから、キャッシュから外す(次の取得で別の候補)。
    → 点検の記録の行。"""
    if verdict not in ("ok", "ng"):
        raise ValueError("verdict は ok か ng")
    pol = photos_policy(policy)
    meta = json.loads(_meta_path(taxon_id, env, policy).read_text(encoding="utf-8"))
    key = str(int(taxon_id))
    checks = load_checks(env, policy)
    old = checks.get(key)
    row = {"name": meta.get("name"), "checked_on": today.isoformat(), "verdict": verdict, "reason": reason,
           "photo_page": meta.get("photo_page"), "source": meta.get("source") or "inaturalist",
           "history": ((old or {}).get("history") or []) + ([{k: v for k, v in old.items() if k != "history"}] if old else [])}
    checks[key] = row
    _save_json(check_path(env, policy), checks)
    if verdict == "ng":
        d = cache_dir(env, policy)
        out = d / pol["check_archive_dir"]
        out.mkdir(parents=True, exist_ok=True)
        tag = re.sub(r"[^0-9A-Za-z_-]", "_", str(meta.get("photo_id") or (meta.get("photo_page") or "x").rsplit("/", 1)[-1]))[:60]
        img = d / f"{int(taxon_id)}.{meta['image_type']}"
        if img.is_file():
            (out / f"{int(taxon_id)}-{tag}.{meta['image_type']}").write_bytes(img.read_bytes())
        (out / f"{int(taxon_id)}-{tag}.json").write_text(json.dumps({**meta, "check": {k: v for k, v in row.items() if k != "history"}},
                                                                    ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline=NL_)
        if meta.get("source"):
            den = load_commons_denied(env, policy)
            t = commons_title(meta)
            if t not in den:
                _save_json(export_dir(env) / pol["commons_deny_file"], sorted(den + [t]))
        elif meta.get("photo_id") is not None:
            skip = load_skip_photos(env, policy)
            skip.setdefault(int(taxon_id), set()).add(int(meta["photo_id"]))
            _save_json(skip_photo_path(env, policy), {str(k): sorted(v) for k, v in skip.items()})
        _remove_cache(taxon_id, env, policy)
        none = load_none(env, policy)                     # 取り直せるように、取れなかった印を外す
        if meta.get("name") in none:
            none.pop(meta["name"])
            _save_none(none, env, policy)
    return row


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


# ---- 段階39: 確認なしの自動取得(承認B 2026-11-03)。キャッシュにない種だけ補う ----

def add_to_table(new_rows, theme="野鳥", env=None, policy=None):
    """表づくりで入った行（和名 → 学名・taxon id・確認日。事実だけ）を、テーマの表の手元の書き出し（export/）に足す。次の実行で探し直さないため。"""
    policy = policy or guide.load_policy()
    th = theme_cfg(theme, policy)
    exp = export_dir(env) / th["table_file"]
    cur = {r["name"]: r for r in _read_table(exp)}
    for e in new_rows:
        cur[e["name"]] = {k: e[k] for k in ("name", "scientific", "taxon_id", "checked_on") if k in e}
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(table_text(cur, policy, theme), encoding="utf-8", newline="\n")


def _none_path(env=None, policy=None):
    return export_dir(env) / photos_policy(policy)["none_file"]


def load_none(env=None, policy=None):
    """写真が取れなかった種の負のキャッシュ {和名: {"on": 日付, "reason": 理由}}。同じ実行・次の数回の実行で探し直さない。"""
    p = _none_path(env, policy)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _save_none(rows, env=None, policy=None):
    p = _none_path(env, policy)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8", newline="\n")


def none_active(entry, today, policy=None):
    """負のキャッシュが有効か(記録の日から negative_cache_days 日以内)。"""
    from datetime import date as _d
    days = photos_policy(policy)["negative_cache_days"]["value"]
    try:
        return (today - _d.fromisoformat(entry["on"])).days < days
    except (KeyError, ValueError):
        return False


def theme_cfg(theme, policy=None):
    ph = photos_policy(policy)
    th = (ph.get("themes") or {}).get(theme or "野鳥")
    if th is None:
        raise ValueError(f"写真のテーマは {sorted((ph.get('themes') or {}))} のどれか: {theme}")
    return th


def ensure(names, *, theme="野鳥", env=None, policy=None, http_get, http_bytes, max_requests=None, today=None, sleep=None, phenology=False):
    """和名の一覧 → 写真のキャッシュにないものだけ補う(対応表にない種は表を作る。iNaturalist で取れなければ Commons)。
    取れなかった種は負のキャッシュに残し、次の数回の実行で探し直さない。上限(max_requests)に達したら残りは次の実行で。
    通信の許可・上限・間隔・記録は呼び出し側が http_get / http_bytes を netbudget で包んで渡す。
    → {"results": {和名: "cached"|"saved"|"none"|"pending"|"skipped"}, "requests", "saved", "status", "stopped"}。"""
    import time as _t
    from datetime import date as _d
    policy = policy or guide.load_policy()
    ph = policy["photos"]
    th = theme_cfg(theme, policy)
    pht = {**ph, "class_name": th["class_name"], "ranks": th.get("ranks") or [ph["rank"]]}
    pht["commons"] = {**ph["commons"], "deny_titles": frozenset(load_commons_denied(env, policy))}   # 段階82 第4部: 点検で不可にしたファイルは選ばない
    today = today or _d.today()
    sleep = sleep or _t.sleep
    table = load_table(env, policy=policy)
    review = load_review(env, policy)
    none = load_none(env, policy)

    def has(t):
        return has_cache(t, env, policy)

    pp = phenology_cfg(theme, policy) if phenology else None      # 段階53: 実際の取得（コマンド・ページ）が True にする。花の写真は 開花 ＞ つぼみ
    result, need_search, rows, reeval = {}, [], [], []
    for n in dict.fromkeys(names):
        if inat_photos.skipped(n, ph):
            result[n] = "skipped"
        elif n in table:
            r = table[n]
            if has(r["taxon_id"]):
                result[n] = "cached"
                if pp and stale_for_rule(r["taxon_id"], pp, env, policy) and not checked_ok(r["taxon_id"], env, policy):   # 段階53: 古い規則の写真は再評価する(段階82: 点検済みで可の写真は置き換えない)
                    reeval.append(r)
            elif str(r["taxon_id"]) in review or (n in none and none_active(none[n], today, policy)):
                result[n] = "none"
            elif int(r["taxon_id"]) >= ph["phenology"]["pseudo_taxon_min"]["value"]:
                result[n] = "none"                       # 段階81: 学名で Commons から取った種(仮の id)は iNaturalist で探さない(学名の Commons で取り直す)
            else:
                rows.append(r)
        elif n in none and none_active(none[n], today, policy):
            result[n] = "none"
        else:
            need_search.append(n)
    left = max_requests if max_requests is not None else ph["max_requests_per_run"]["value"]
    used = 0
    rep = {"saved": [], "status": "ok", "stopped": None}
    new_rows = []
    todo, unused = [], {}
    try:
        if need_search and left >= 1:
            entered, rejected, r1 = inat_photos.build_table(need_search, http_get=http_get, ph=pht, max_requests=left, sleep=sleep)
            used += r1["requests"]
            left -= r1["requests"]
            new_rows = entered
            rows += [{k: e[k] for k in ("name", "scientific", "taxon_id")} for e in entered]
            for n, why in rejected.items():
                none[n] = {"on": today.isoformat(), "reason": why}
                result[n] = "none"
            for n in r1["not_started"]:
                result[n] = "pending"
            if r1["status"] != "ok":
                rep["status"], rep["stopped"] = r1["status"], r1["stopped"]
        else:
            for n in need_search:
                result[n] = "pending"
        if new_rows:                                                      # 表(事実だけ)は手元の書き出しに足す
            add_to_table(new_rows, theme, env, policy)
        todo = [r for r in rows if not has(r["taxon_id"]) and str(r["taxon_id"]) not in review]
        unused = {}
        reg = [r for r in todo if commons_photos.regional(r, pht["commons"])]   # 段階82 第4部 4.3: 地域で種が分かれる鳥は、日本・東アジアの Commons の写真だけ
        todo = [r for r in todo if r not in reg]
        for r in reg:
            if left < 3 or rep["status"] != "ok":
                result[r["name"]] = "pending"
                continue
            sci = ((ph.get("scientific_names") or {}).get("value") or {}).get(r["name"]) or r["scientific"]
            g4, un4, r4 = commons_photos.fetch_commons_season({**r, "scientific": sci}, http_get=http_get, http_bytes=http_bytes, ph=pht,
                                                              max_requests=left, today=today, sleep=sleep, season=False, pp=pp,
                                                              on_got=lambda it: save_photo(it, env, policy))
            used += r4["requests"]
            left -= r4["requests"]
            if g4:
                result[r["name"]] = "saved"
                rep["saved"].append(r["name"])
            else:
                result[r["name"]] = "none"
                none[r["name"]] = {"on": today.isoformat(), "reason": un4.get(r["name"]) or "日本・東アジアの写真がない"}
            if r4["status"] != "ok":
                rep["status"], rep["stopped"] = r4["status"], r4["stopped"]
        nf = set(((pp or {}).get("non_flower_species") or {}).get("value") or [])
        if todo and left >= 2 and rep["status"] == "ok" and nf & {r["name"] for r in todo}:     # 段階82: 見どころが花でない種は開花の規則なし
            g5, un5, r5 = _fetch_for_theme([r for r in todo if r["name"] in nf], None, http_get=http_get, http_bytes=http_bytes, pht=pht, left=left,
                                           has=has, skip=load_skip_photos(env, policy), sleep=sleep, today=today)
            used += r5["requests"]
            left -= r5["requests"]
            for item in g5:
                save_photo(item, env, policy)
                result[item["row"]["name"]] = "saved"
            rep["saved"] += [i["row"]["name"] for i in g5]
            todo = [r for r in todo if r["name"] not in nf or r["name"] in un5]
        if todo and left >= 2 and rep["status"] == "ok":
            got, unused, r2 = _fetch_for_theme(todo, pp, http_get=http_get, http_bytes=http_bytes, pht=pht, left=left, has=has,
                                               skip=load_skip_photos(env, policy), sleep=sleep, today=today)
            used += r2["requests"]
            left -= r2["requests"]
            for item in got:
                save_photo(item, env, policy)
                result[item["row"]["name"]] = "saved"
            rep["saved"] += [i["row"]["name"] for i in got]
            for n in r2["not_started"]:
                result[n] = "pending"
            if r2["status"] != "ok":
                rep["status"], rep["stopped"] = r2["status"], r2["stopped"]
            cm = ph["commons"]                                           # iNaturalist に使える写真がない種だけ Commons(承認済み。学名で探す)。上限の範囲で
            nocache = [r for r in todo if r["name"] in unused and not has(r["taxon_id"]) and f"commons:{r['taxon_id']}" not in review]
            if nocache and rep["status"] == "ok" and left >= 1:
                got3, _un, _r3 = commons_photos.fetch_commons(nocache, http_get=http_get, http_bytes=http_bytes, ph=pht,
                                                              max_requests=min(cm["ensure_max_requests"]["value"], left), has_cache=has,
                                                              on_got=lambda it: save_photo(_state_unknown(it, pp), env, policy), sleep=sleep)
                for item in got3:
                    result[item["row"]["name"]] = "saved"
                rep["saved"] += [i["row"]["name"] for i in got3]
    except LiveError as ex:                                       # 上限・許可ホストの外: そこで止める（取れていない種は次の実行で。ページは作る）
        rep["status"], rep["stopped"] = "stopped", str(ex)[:200]
    for r in todo:
        st = result.get(r["name"])
        if st in ("saved", "pending"):
            continue
        if has(r["taxon_id"]):
            result[r["name"]] = "saved"
        elif r["name"] in unused:                                     # 取りに行って使える写真がなかった種だけ負のキャッシュ(上限で取りに行けなかった種は次の実行で)
            none[r["name"]] = {"on": today.isoformat(), "reason": unused[r["name"]]}
            result[r["name"]] = "none"
        else:
            result[r["name"]] = "pending"
    if reeval and pp and rep["status"] == "ok" and left >= 2:            # 段階53: 古い規則のキャッシュの再評価（開花 ＞ つぼみの写真があれば置き換え、なければ「不明」の印）
        try:
            used += _reevaluate(reeval, pp, result, http_get, http_bytes, pht, left, env, policy, today, sleep, rep)
            left -= 0
        except LiveError as ex:
            rep["status"], rep["stopped"] = "stopped", str(ex)[:200]
    if rep["status"] == "ok":                                         # 段階52: 取れなかった種のうち学名の対応がある種は、学名で Commons のファイルを探す
        try:
            used += _scientific_fallback(result, none, table, theme, pht, ph, env, policy, today, sleep, http_get, http_bytes,
                                         max(0, left), rep, pp=pp)
        except LiveError as ex:
            rep["status"], rep["stopped"] = "stopped", str(ex)[:200]
    _save_none(none, env, policy)
    return {"results": result, "requests": used, **rep}


def _state_unknown(item, pp):
    """Wikidata の代表画像（P18）は状態を判定できない: 花の規則のテーマでは「不明」として残す。"""
    if pp:
        item["meta"].setdefault("state", pp["unknown_label"])
        item["meta"]["rule"] = pp["rule_version"]["value"]
    return item


def _fetch_for_theme(todo, pp, *, http_get, http_bytes, pht, left, has, skip, sleep, today):
    """写真を取る。花・野草（pp あり）は 開花 ＞ つぼみ の写真を先に、見つからない種は代表写真を「不明」として。→ fetch_photos と同じ形。"""
    if not pp:
        return inat_photos.fetch_photos(todo, http_get=http_get, http_bytes=http_bytes, ph=pht, max_requests=left, has_cache=has, skip_photos=skip, sleep=sleep)
    got, unused, rep = inat_photos.fetch_phenology(todo, http_get=http_get, http_bytes=http_bytes, ph=pht, max_requests=left, has_cache=has,
                                                   today=today, sleep=sleep, skip_photos=skip)
    rest = [r for r in todo if r["name"] in unused]
    if rep["status"] == "ok" and rest and left - rep["requests"] >= 2:
        g2, un2, r2 = inat_photos.fetch_photos(rest, http_get=http_get, http_bytes=http_bytes, ph=pht, max_requests=left - rep["requests"], has_cache=has,
                                               skip_photos=skip, sleep=sleep)
        for it in g2:
            it["meta"]["state"] = pp["unknown_label"]
            it["meta"]["rule"] = pp["rule_version"]["value"]
        got += g2
        unused = {**{k: v for k, v in unused.items() if k not in {i["row"]["name"] for i in g2}}, **un2}
        rep["requests"] += r2["requests"]
        rep["not_started"] = list(rep["not_started"]) + list(r2["not_started"])
        if r2["status"] != "ok":
            rep["status"], rep["stopped"] = r2["status"], r2["stopped"]
    return got, unused, rep


def _reevaluate(rows, pp, result, http_get, http_bytes, pht, left, env, policy, today, sleep, rep):
    """→ 使ったリクエスト数。iNaturalist の taxon がある種は観察の注釈で、仮の id の種（学名で Commons から取った種）は Commons の語の判定で探し直す。"""
    sci = (pht.get("scientific_names") or {}).get("value") or {}
    pseudo_min = pp["pseudo_taxon_min"]["value"]
    real = [r for r in rows if r["taxon_id"] < pseudo_min]
    fake = [r for r in rows if r["taxon_id"] >= pseudo_min]
    used = 0
    got, unused = [], {}
    if real:
        got, unused, r = inat_photos.fetch_phenology(real, http_get=http_get, http_bytes=http_bytes, ph=pht, max_requests=left, has_cache=lambda _t: False,
                                                     today=today, sleep=sleep, skip_photos=load_skip_photos(env, policy))
        used += r["requests"]
        if r["status"] != "ok":
            rep["status"], rep["stopped"] = r["status"], r["stopped"]
    for row in fake + [r for r in real if r["name"] in unused and r["name"] in sci]:      # iNaturalist に開花・つぼみがない種も、学名の対応があれば Commons で探す
        if rep["status"] != "ok" or left - used < 3:
            break
        row = {**row, "scientific": sci.get(row["name"]) or row["scientific"]}
        g, _un, r2 = commons_photos.fetch_commons_season(row, http_get=http_get, http_bytes=http_bytes, ph=pht, max_requests=left - used, today=today,
                                                         sleep=sleep, season=False, pp=pp)
        used += r2["requests"]
        got += [it for it in g if it["meta"].get("state") in ("開花", "つぼみ")]
        if r2["status"] != "ok":
            rep["status"], rep["stopped"] = r2["status"], r2["stopped"]
    for it in got:
        tid = it["row"]["taxon_id"]
        archive_rejected(tid, pp, "新しい規則（開花 ＞ つぼみ）で、開花またはつぼみの写真に置き換えた", env, policy)
        save_photo(it, env, policy)
        result[it["row"]["name"]] = "saved"
        rep["saved"].append(it["row"]["name"])
    done = {it["row"]["name"] for it in got}
    for row in rows:
        if row["name"] not in done and has_cache(row["taxon_id"], env, policy):
            stamp_unknown(row["taxon_id"], pp, env, policy)
    return used


def _scientific_fallback(result, none, table, theme, pht, ph, env, policy, today, sleep, http_get, http_bytes, left, rep, pp=None):
    """→ 使ったリクエスト数。results が none の種のうち policy photos.scientific_names にある種を、学名で Commons から探して保存する(1 種 3 リクエスト)。"""
    import zlib
    sci = (ph.get("scientific_names") or {}).get("value") or {}
    used = 0
    for n in [k for k, v in result.items() if v == "none" and k in sci]:
        if left - used < 3:
            break
        row = dict(table[n]) if n in table else {"name": n, "scientific": sci[n], "taxon_id": 9_000_000_000 + zlib.crc32(sci[n].encode("utf-8"))}
        row = {**row, "name": n, "scientific": sci[n]}                 # 検索と「学名の記載」の確認は、対応表(指示書の学名)の学名を使う
        if has_cache(row["taxon_id"], env, policy):
            result[n] = "saved"
            none.pop(n, None)
            continue
        got, _un, r = commons_photos.fetch_commons_season(row, http_get=http_get, http_bytes=http_bytes, ph=pht, max_requests=left - used,
                                                          today=today, sleep=sleep, on_got=lambda it: save_photo(it, env, policy), season=False, pp=pp)
        used += r["requests"]
        if got:
            result[n] = "saved"
            none.pop(n, None)
            rep["saved"].append(n)
            if n not in table:
                add_to_table([{**{k: row[k] for k in ("name", "scientific", "taxon_id")}, "checked_on": today.isoformat()}], theme, env, policy)
        if r["status"] != "ok":
            rep["status"], rep["stopped"] = r["status"], r["stopped"]
            break
    return used


def _ensure_http(policy=None, http_get=None, http_bytes=None):
    """netbudget で包んだ (http_get, http_bytes, 閉じるもの)。許可されない環境(テスト中など)は (None, None, 理由)。"""
    from . import netbudget
    if http_get is not None:
        return http_get, http_bytes, None
    why = netbudget.refusal()
    if why:
        return None, None, why
    cfg = load_config()
    from .fetch.live import SessionGetter
    t = cfg["live"]["request_timeout"]
    g = SessionGetter(user_agent=cfg["live"]["user_agent"], connect_s=t["connect_s"], read_s=t["read_s"])
    ph = photos_policy(policy)
    hs = cfg["live"]["allowed_hosts_by_subject"]
    b = netbudget.Budget("photos", list(hs["guide_photos"]) + list(hs["guide_photos_commons"]) + list(hs["guide_places"]),
                         ph["max_requests_per_run"]["value"], ph["min_interval_s"]["value"])
    return b(g), b(g.get_bytes), g


def ensure_cmd(a, http_get=None, http_bytes=None):
    """guide photos-ensure --names <和名> ... [--theme 野鳥|花|野草]: キャッシュにない種だけ補う。確認なしで実行する(承認B)。"""
    policy = guide.load_policy()
    hg, hb, closer = _ensure_http(policy, http_get, http_bytes)
    if hg is None:
        guide._dump({"ran": False, "reason": closer})                   # テスト中・許可されない環境: 失敗にせず、キャッシュだけで続ける
        return 0
    try:
        res = ensure(a.names, theme=a.theme, policy=policy, http_get=hg, http_bytes=hb, phenology=True,
                     max_requests=min(a.max_requests or 10 ** 9, policy["photos"]["max_requests_per_run"]["value"]))
    finally:
        if closer is not None and hasattr(closer, "close"):
            closer.close()
    _log_requests(res["requests"], "ensure")
    guide._dump({"ran": True, **res})
    return 0 if res["status"] == "ok" else 1


def prefetch_cmd(a, http_get=None, http_bytes=None, sleep=None):
    """guide photos-prefetch --theme 野鳥|花 [--all]: policy の一覧(photos.prefetch)の種を、1 回 80 件以内に分けて、実行の間に間隔をあけて取る。"""
    import time as _t
    policy = guide.load_policy()
    ph = policy["photos"]
    names = list((ph.get("prefetch") or {}).get(a.theme) or [])
    if not names:
        print(f"prefetch の一覧がない: {a.theme}", file=sys.stderr)
        return 2
    sleep = sleep or _t.sleep
    total = {"requests": 0, "runs": 0, "saved": [], "status": "ok"}
    pending = names
    while pending:
        hg, hb, closer = _ensure_http(policy, http_get, http_bytes)
        if hg is None:
            guide._dump({"ran": False, "reason": closer})
            return 0
        try:
            res = ensure(pending, theme=a.theme, policy=policy, http_get=hg, http_bytes=hb, phenology=True, max_requests=ph["max_requests_per_run"]["value"], sleep=sleep)
        finally:
            if closer is not None and hasattr(closer, "close"):
                closer.close()
        _log_requests(res["requests"], "prefetch")
        total["requests"] += res["requests"]
        total["runs"] += 1
        total["saved"] += res["saved"]
        pending = [n for n, st in res["results"].items() if st == "pending"]
        if res["status"] != "ok":
            total["status"] = res["status"]
            break
        if not a.all or res["requests"] == 0:
            break
        sleep(ph["prefetch_gap_s"]["value"])
    total["pending"] = pending
    total["names"] = len(names)
    guide._dump(total)
    return 0 if total["status"] == "ok" else 1


def photo_theme_for(word, policy=None):
    """質問の言葉 → 写真のテーマ(野鳥・花)。鳥のテーマ(野鳥・冬鳥)なら野鳥、ほかは花。"""
    policy = policy or guide.load_policy()
    if word in (policy.get("wildflower") or {}).get("words", []):      # 段階41: 野草・高山植物
        return "野草"
    themes, _kinds = guide.themes_for_words([word], policy)
    if themes and "紅葉" in themes:                                     # 段階57: 紅葉は樹種の写真(photos.themes の 紅葉)。花の表に入れない
        return "紅葉"
    return "野鳥" if themes and themes & {"野鳥", "冬鳥"} else "花"


def ensure_for_page(names, word, policy=None, http_get=None, http_bytes=None, env=None):
    """ページに出す種の写真を、キャッシュにないものだけ確認なしで補う(段階39 A-3)。許可されない環境(テスト中など)・通信できないときは、
    止めずにキャッシュだけで続ける。1 回の上限(policy の photos.max_requests_per_run)に達した残りは、次の実行で続きを取る。→ ensure の結果か None。"""
    policy = policy or guide.load_policy()
    hg, hb, closer = _ensure_http(policy, http_get, http_bytes)
    if hg is None:
        return None
    try:
        res = ensure(names, theme=photo_theme_for(word, policy), env=env, policy=policy, http_get=hg, http_bytes=hb, phenology=True)
    except OSError:
        return None
    finally:
        if closer is not None and hasattr(closer, "close"):
            closer.close()
    _log_requests(res["requests"], "ensure-page", env)
    return res
