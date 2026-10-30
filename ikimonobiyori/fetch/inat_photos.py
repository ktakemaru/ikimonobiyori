"""野鳥の案内ページの代表写真を iNaturalist から取る小さなコード(段階29。docs/stage29-decisions.md)。

- 承認(ユーザー 2026-10-30、承認A): 通信先は api.inaturalist.org(種の検索と写真情報。読み取りだけ)と、写真の実体の配信元
  static.inaturalist.org・inaturalist-open-data.s3.amazonaws.com の 2 つだけ(config.yaml の live.allowed_hosts_by_subject.guide_photos)。
  応答に出てくるほかのホストの写真は取得しない。リダイレクトは追わない(行き先が許可外になりうるため)。
- 表づくり(build_table): 和名 → 学名・taxon id。**ランクが species / 日本語の一般名が和名と完全に一致 / 一致する候補がちょうど 1 件 / 鳥類(Aves)**
  のすべてを満たすときだけ入れる。あいまい一致・類似度は使わない。満たさないものは理由つきで返す。
- 写真(fetch_photos): taxon の既定の写真(default_photo)だけ。ライセンスが policy の licenses にあるときだけ。学名が表と一致しないものは使わない。
  画像は形式(JPEG/PNG/WebP)と大きさ(max_image_bytes)を確かめ、違うものは捨てる。撮影者の表記・ライセンス・写真のページの URL・取得日をメタデータに残す。
- 値(上限・間隔・ライセンス・ホスト・形式)はすべて data/guide/policy.yaml の photos から読む。コードに数値の閾値を書かない。
- 通信は呼び出し側(guide.py)が --live・BIYORI_ALLOW_LIVE=1・--max-requests・計測フックを確かめたあとだけ。HTTP の非 200(429 を含む)ならそこで止める。
  応答の形が想定と違うときは ParseError で止める(推測で補わない)。応答の本文は保存しない(写真の実体とメタデータだけ)。"""
import json
import re
import time
from datetime import date
from http import HTTPStatus
from urllib.parse import quote, urlencode, urlsplit

from . import ParseError


def search_url(name, ph):
    q = {"q": name, "locale": ph["locale"], "per_page": ph["search_per_page"]["value"], "all_names": "true"}
    return ph["api_base"] + "/taxa?" + urlencode(q)


def taxon_url(taxon_id, ph):
    return ph["api_base"] + "/taxa/" + quote(str(int(taxon_id))) + "?" + urlencode({"locale": ph["locale"]})


def _results(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get("results"), list):
        raise ParseError("results がない")
    for r in doc["results"]:
        if not isinstance(r, dict):
            raise ParseError("results の要素が辞書でない")
    return doc["results"]


def parse_search(doc):
    """taxa の検索の応答 → 候補の一覧 [{"taxon_id", "scientific", "rank", "common", "class_name"}]。"""
    out = []
    for r in _results(doc):
        tid = r.get("id")
        if not isinstance(tid, int) or isinstance(tid, bool):
            raise ParseError("taxon の id が整数でない")
        out.append({"taxon_id": tid, "scientific": r.get("name") if isinstance(r.get("name"), str) else None,
                    "rank": r.get("rank") if isinstance(r.get("rank"), str) else None,
                    "common": r.get("preferred_common_name") if isinstance(r.get("preferred_common_name"), str) else None,
                    "class_name": r.get("iconic_taxon_name") if isinstance(r.get("iconic_taxon_name"), str) else None,
                    "ja_names": [n["name"] for n in r.get("names") or [] if isinstance(n, dict) and n.get("locale") == "ja" and isinstance(n.get("name"), str)],
                    "ancestor_ids": [a for a in r.get("ancestor_ids") or [] if isinstance(a, int)]})
    return out


def _matches(name, c):
    """和名が候補の優先名か、応答の日本語の名前(names の locale が ja)のどれかと完全に一致するか。あいまい一致は使わない。"""
    return c["common"] == name or name in c["ja_names"]


def _under(c, species):
    """候補 c が種 species の下位(亜種など)か: 応答の ancestor_ids に種の id がある。"""
    return species["taxon_id"] in c["ancestor_ids"]


def decide(name, cands, ph):
    """和名と候補 → ({"name", "scientific", "taxon_id", "candidates"?}, None) か (None, 理由)。条件のどれかを満たさなければ表に入れない。
    和名に完全一致する候補が 2 件以上のときは、種(species)のランクの候補がちょうど 1 件で、ほかがその種の下位のときだけ、その種を採る
    (採ったときは一致した候補の一覧を candidates に付ける。報告用で、表には書かない)。"""
    if not cands:
        return None, "候補が 0 件"
    exact = [c for c in cands if _matches(name, c)]
    if not exact:
        return None, "日本語の一般名が和名と完全に一致する候補がない"
    if len(exact) > 1:
        species = [c for c in exact if c["rank"] == ph["rank"]]
        if len(species) != 1:
            return None, f"一致する候補が {len(exact)} 件(ちょうど 1 件でない。{ph['rank']} のランクの候補が {len(species)} 件)"
        others = [c for c in exact if c is not species[0]]
        if not all(_under(c, species[0]) for c in others):
            return None, f"一致する候補が {len(exact)} 件(ちょうど 1 件でない。ほかの候補が {ph['rank']} の下位と確かめられない)"
        c = species[0]
    else:
        c = exact[0]
    if c["rank"] != ph["rank"]:
        return None, f"ランクが {ph['rank']} でない({c['rank']})"
    if c["class_name"] != ph["class_name"]:
        return None, f"鳥類({ph['class_name']})でない({c['class_name']})"
    if not c["scientific"]:
        return None, "学名がない"
    row = {"name": name, "scientific": c["scientific"], "taxon_id": c["taxon_id"]}
    if len(exact) > 1:
        row["candidates"] = [{"common": x["common"], "scientific": x["scientific"], "rank": x["rank"], "taxon_id": x["taxon_id"]} for x in exact]
    return row, None


def skipped(name, ph):
    """種を特定しない語(「カモ類」・「シギ・チドリ」など)は対象外 → 理由。対象なら None。"""
    if name in ph["skip_names"]:
        return "種を特定しない語"
    if any(name.endswith(s) for s in ph["skip_name_suffixes"]):
        return "種を特定しない語(類)"
    if any(c in name for c in ph["skip_name_chars"]):
        return "複数をまとめた語"
    return None


def _wait(rep, gap, sleep):
    if rep["requests"]:
        sleep(gap)


def build_table(names, *, http_get, ph, max_requests, today=None, sleep=time.sleep):
    """和名の一覧を 1 件ずつ検索して表に入れるか決める。→ (入った [{name, scientific, taxon_id, checked_on}], 入らなかった {和名: 理由}, 報告)。
    max_requests に達したら残りは読まない(未着手として報告に残す)。HTTP の非 200 ならそこで止める。"""
    today = (today or date.today()).isoformat()
    gap = ph["min_interval_s"]["value"]
    rep = {"requests": 0, "status": "ok", "stopped": None, "not_started": [], "multi_candidate": {}}
    entered, rejected = [], {}
    todo = []
    for n in names:
        why = skipped(n, ph)
        if why:
            rejected[n] = why
        else:
            todo.append(n)
    for i, n in enumerate(todo):
        if rep["requests"] >= max_requests:
            rep["stopped"] = f"--max-requests {max_requests} に達したため、残り {len(todo) - i} 件は読まない"
            rep["not_started"] = todo[i:]
            break
        _wait(rep, gap, sleep)
        rep["requests"] += 1
        try:
            status, body, _ = http_get(search_url(n, ph))
        except OSError as ex:                                    # 接続・TLS・タイムアウト。再試行せず、ここまでの結果を残して止める(続きは再実行で)
            rep["status"], rep["stopped"] = "network_error", f"通信エラーのため止めた({type(ex).__name__})。ここまでの結果は残す。続きは再実行で"
            rep["not_started"] = todo[i:]
            break
        if status != HTTPStatus.OK:
            rep["status"], rep["stopped"] = f"HTTP {status}", f"HTTP {status} のため止めた(残りは読まない)"
            rep["not_started"] = todo[i + 1:]
            break
        try:
            row, why = decide(n, parse_search(json.loads(body)), ph)
        except (ValueError, ParseError) as ex:
            rep["status"], rep["stopped"] = "parse_error", f"応答の形が想定と違う: {ex}"
            rep["not_started"] = todo[i + 1:]
            break
        if row:
            if "candidates" in row:
                rep["multi_candidate"][n] = row.pop("candidates")
            entered.append({**row, "checked_on": today})
        else:
            rejected[n] = why
    return entered, rejected, rep


def parse_taxon(doc):
    """taxa/{id} の応答 → {"taxon_id", "scientific", "photo": {...} か None}。photo は default_photo の項目(ライセンス・撮影者の表記・URL)。"""
    rows = _results(doc)
    if len(rows) != 1:
        raise ParseError(f"results が 1 件でない({len(rows)})")
    r = rows[0]
    tid = r.get("id")
    if not isinstance(tid, int) or isinstance(tid, bool) or not isinstance(r.get("name"), str):
        raise ParseError("id・name がない")
    photos, seen = [], set()
    cands = [r.get("default_photo")] + [tp.get("photo") for tp in r.get("taxon_photos") or [] if isinstance(tp, dict)]
    for p in cands:                                              # 先頭から: 既定の写真 → taxon_photos の順
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if not isinstance(pid, int) or isinstance(pid, bool):
            raise ParseError("写真の id が整数でない")
        if pid in seen:
            continue
        seen.add(pid)
        photos.append({"photo_id": pid, "license_code": p.get("license_code") if isinstance(p.get("license_code"), str) else None,
                       "attribution": p.get("attribution") if isinstance(p.get("attribution"), str) else None,
                       "urls": {k: v for k, v in p.items() if k.endswith("_url") and isinstance(v, str)}})
    return {"taxon_id": tid, "scientific": r["name"], "photos": photos}


def _usable_one(p, ph):
    label = ph["licenses"].get((p["license_code"] or "").lower())
    if not label:
        return None, f"ライセンスが許可外・不明({p['license_code']})"
    if not p["attribution"]:
        return None, "撮影者の表記がない"
    url = p["urls"].get(ph["photo_size"])
    if not url:
        return None, f"{ph['photo_size']} がない"
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ph["image_hosts"]:
        return None, f"許可外のホストの写真({parts.hostname})"
    return {"image_url": url, "photo_id": p["photo_id"], "license": label, "license_code": p["license_code"].lower(),
            "attribution": p["attribution"]}, None


def usable_photo(row, taxon, ph):
    """表の 1 行と taxon の応答 → ({"image_url", ...}, None) か (None, 使わない理由)。
    既定の写真と taxon_photos を先頭から見て、使ってよいライセンス・ホストなどを満たす最初の 1 枚を選ぶ。"""
    if taxon["taxon_id"] != row["taxon_id"]:
        return None, "taxon の id が表と一致しない"
    if taxon["scientific"] != row["scientific"]:
        return None, f"学名が表と一致しない({taxon['scientific']})"
    if not taxon["photos"]:
        return None, "既定の写真がない"
    first = None
    for p in taxon["photos"]:
        ok, why = _usable_one(p, ph)
        if ok:
            return ok, None
        first = first or why
    return None, f"{first}(写真 {len(taxon['photos'])} 枚のどれも使えない)" if len(taxon["photos"]) > 1 else first


def sniff_image(data, ph):
    """画像の先頭のバイト列 → 形式の名前(jpeg・png・webp)か None。"""
    for kind, pat in ph["image_types"].items():
        if re.match(pat.encode("ascii"), data, re.S):
            return kind
    return None


def check_image(data, ph):
    """→ (形式, None) か (None, 捨てる理由)。"""
    if len(data) > ph["max_image_bytes"]["value"]:
        return None, "大きすぎる"
    kind = sniff_image(data, ph)
    if not kind:
        return None, "形式が JPEG・PNG・WebP でない"
    return kind, None


def fetch_photos(rows, *, http_get, http_bytes, ph, max_requests, has_cache, today=None, sleep=time.sleep):
    """表の種ごとに、写真情報(1 回)と写真の実体(1 回)を取る。has_cache(taxon_id) が真の種は取り直さない。
    → (取れた [{row, meta, data, ext}], 使わなかった {和名: 理由}, 報告)。HTTP の非 200 ならそこで止める。"""
    today = (today or date.today()).isoformat()
    gap = ph["min_interval_s"]["value"]
    rep = {"requests": 0, "status": "ok", "stopped": None, "skipped_cached": [], "not_started": []}
    got, unused = [], {}
    todo = []
    for row in rows:
        (rep["skipped_cached"] if has_cache(row["taxon_id"]) else todo).append(row)
    for i, row in enumerate(todo):
        if rep["requests"] + 1 >= max_requests:                 # この種は 2 回(情報と実体)要る
            rep["stopped"] = f"--max-requests {max_requests} に達したため、残り {len(todo) - i} 種は取らない"
            rep["not_started"] = [r["name"] for r in todo[i:]]
            break
        _wait(rep, gap, sleep)
        rep["requests"] += 1
        try:
            status, body, _ = http_get(taxon_url(row["taxon_id"], ph))
        except OSError as ex:
            rep["status"], rep["stopped"] = "network_error", f"通信エラーのため止めた({type(ex).__name__})。ここまでの結果は残す。続きは再実行で"
            rep["not_started"] = [r["name"] for r in todo[i:]]
            break
        if status != HTTPStatus.OK:
            rep["status"], rep["stopped"] = f"HTTP {status}", f"HTTP {status} のため止めた(残りは読まない)"
            rep["not_started"] = [r["name"] for r in todo[i + 1:]]
            break
        try:
            ok, why = usable_photo(row, parse_taxon(json.loads(body)), ph)
        except (ValueError, ParseError) as ex:
            rep["status"], rep["stopped"] = "parse_error", f"応答の形が想定と違う: {ex}"
            rep["not_started"] = [r["name"] for r in todo[i + 1:]]
            break
        if not ok:
            unused[row["name"]] = why
            continue
        sleep(gap)
        rep["requests"] += 1
        try:
            status, data, _ = http_bytes(ok["image_url"], ph["max_image_bytes"]["value"])
        except OSError as ex:
            rep["status"], rep["stopped"] = "network_error", f"通信エラーのため止めた({type(ex).__name__})。ここまでの結果は残す。続きは再実行で"
            rep["not_started"] = [r["name"] for r in todo[i:]]
            break
        if status != HTTPStatus.OK:
            if status in (HTTPStatus.TOO_MANY_REQUESTS,) or status >= HTTPStatus.INTERNAL_SERVER_ERROR:
                rep["status"], rep["stopped"] = f"HTTP {status}", f"HTTP {status} のため止めた(残りは読まない)"
                rep["not_started"] = [r["name"] for r in todo[i + 1:]]
                break
            unused[row["name"]] = f"写真の取得が HTTP {status}"
            continue
        kind, why = check_image(data, ph)
        if not kind:
            unused[row["name"]] = f"写真を捨てた({why})"
            continue
        meta = {"name": row["name"], "scientific": row["scientific"], "taxon_id": row["taxon_id"], "photo_id": ok["photo_id"],
                "license": ok["license"], "license_code": ok["license_code"], "attribution": ok["attribution"],
                "photo_page": ph["photo_page_url"].format(id=ok["photo_id"]), "fetched_on": today, "image_type": kind}
        got.append({"row": row, "meta": meta, "data": data, "ext": kind})
    return got, unused, rep
