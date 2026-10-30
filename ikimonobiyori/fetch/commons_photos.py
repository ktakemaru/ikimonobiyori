"""iNaturalist に許可ライセンスの写真がない種の代表写真を、Wikimedia Commons から取る小さなコード(段階30。docs/stage30-report.md)。

- 承認(ユーザー 2026-10-31): 通信先は commons.wikimedia.org(API。読み取りだけ)と upload.wikimedia.org(画像の実体)。
  種の画像の名前を調べるためだけに、承認済みの www.wikidata.org(config.yaml の guide_places)も使う。CC BY-NC は使わない。
- 1 種ずつ順番に: (a) Wikidata で学名(P225)が表の学名と完全一致する分類群を探す(ちょうど 1 件のときだけ)→
  (b) その分類群の画像(P18)のファイル名を読む → (c) Commons の imageinfo でライセンス・作者・ファイルのページ・サムネイルの URL を読む →
  (d) サムネイルを upload.wikimedia.org から取る。条件を満たさなければ写真なし(別の写真や別の種で補わない)。
- ライセンスは policy の photos.commons.license_patterns のどれかに完全に合うものだけ(CC0・パブリックドメイン・CC BY・CC BY-SA)。NC・ND・不明は使わない。
  Restrictions(利用の制限の注記)があるものは使わない。作者の表記は HTML のタグを除いた文字だけ。
- 値(上限・間隔・ホスト・形式・ライセンスの形)はすべて data/guide/policy.yaml の photos から読む。コードに数値の閾値を書かない。
- 通信は呼び出し側(guide_photos.py)が --live・BIYORI_ALLOW_LIVE=1・--max-requests・計測フックを確かめたあとだけ。HTTP の非 200(429 を含む)ならそこで止める。
  応答の形が想定と違うときは ParseError で止める(推測で補わない)。応答の本文は保存しない(画像の実体とメタデータだけ)。リダイレクトは追わない。"""
import json
import re
import time
from datetime import date
from html.parser import HTMLParser
from http import HTTPStatus
from urllib.parse import urlencode, urlsplit

from . import ParseError
from .inat_photos import _wait, check_image


def search_url(scientific, cm):
    q = {"action": "query", "list": "search", "srsearch": cm["wikidata_search"].format(scientific=scientific), "srnamespace": cm["wikidata_namespace"],
         "srlimit": cm["wikidata_limit"]["value"], "format": "json", "formatversion": cm["formatversion"]}
    return cm["wikidata_api"] + "?" + urlencode(q)


def entity_url(qids, cm):
    """項目の id の一覧を 1 回の問い合わせにまとめる(Wikidata への回数を減らす)。"""
    q = {"action": "wbgetentities", "ids": "|".join(qids), "props": "claims", "format": "json"}
    return cm["wikidata_api"] + "?" + urlencode(q)


def imageinfo_url(filename, cm):
    q = {"action": "query", "titles": cm["file_prefix"] + filename, "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata",
         "iiurlwidth": cm["thumb_width"]["value"], "format": "json", "formatversion": cm["formatversion"]}
    return cm["commons_api"] + "?" + urlencode(q)


def parse_search(doc, cm):
    """Wikidata の検索の応答 → 項目の id の一覧。"""
    rows = (doc.get("query") or {}).get("search") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise ParseError("query.search がない")
    out = []
    for r in rows:
        t = r.get("title") if isinstance(r, dict) else None
        if not isinstance(t, str) or not re.fullmatch(cm["qid_pattern"], t):
            raise ParseError("項目の id の形が想定と違う")
        out.append(t)
    return out


def _values(entity, prop):
    """claims の prop → [(値, ランク)]。文字列の値だけ(ほかの形は ParseError)。deprecated は除く。"""
    out = []
    for c in (entity.get("claims") or {}).get(prop) or []:
        if not isinstance(c, dict):
            raise ParseError("claims の要素が辞書でない")
        rank = c.get("rank")
        if rank == "deprecated":
            continue
        snak = c.get("mainsnak") or {}
        if snak.get("snaktype") != "value":
            continue
        v = (snak.get("datavalue") or {}).get("value")
        if not isinstance(v, str):
            raise ParseError(f"{prop} の値が文字列でない")
        out.append((v, rank))
    return out


def parse_entity(doc, qid, cm):
    """wbgetentities の応答 → {"p225": [学名], "p18": [ファイル名(preferred が先)]}(項目 qid について)。"""
    ents = doc.get("entities") if isinstance(doc, dict) else None
    if not isinstance(ents, dict) or not isinstance(ents.get(qid), dict):
        raise ParseError("entities に項目がない")
    e = ents[qid]
    names = [v for v, _ in _values(e, cm["prop_scientific"])]
    files = _values(e, cm["prop_image"])
    files.sort(key=lambda x: x[1] != "preferred")                # preferred が先、あとは書かれた順(sort は安定)
    return {"p225": names, "p18": [v for v, _ in files]}


def _strip_tags(text):
    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.out = []

        def handle_data(self, d):
            self.out.append(d)
    p = P()
    p.feed(text)
    return " ".join("".join(p.out).split())


def parse_imageinfo(doc):
    """Commons の imageinfo の応答 → {"descriptionurl", "thumburl", "mime", "license_short", "artist", "restrictions"} か None(ページがない・画像情報がない)。"""
    pages = (doc.get("query") or {}).get("pages") if isinstance(doc, dict) else None
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
        raise ParseError("query.pages が 1 件でない")
    ii = pages[0].get("imageinfo")
    if not ii:
        return None
    if not isinstance(ii, list) or not isinstance(ii[0], dict):
        raise ParseError("imageinfo の形が想定と違う")
    i = ii[0]
    em = i.get("extmetadata") if isinstance(i.get("extmetadata"), dict) else {}

    def meta(k):
        v = (em.get(k) or {}).get("value") if isinstance(em.get(k), dict) else None
        return v if isinstance(v, str) else None
    return {"descriptionurl": i.get("descriptionurl") if isinstance(i.get("descriptionurl"), str) else None,
            "thumburl": i.get("thumburl") if isinstance(i.get("thumburl"), str) else None,
            "mime": i.get("mime") if isinstance(i.get("mime"), str) else None,
            "license_short": meta("LicenseShortName"), "artist": _strip_tags(meta("Artist") or ""), "restrictions": (meta("Restrictions") or "").strip()}


def usable(info, cm):
    """imageinfo → ({"image_url", "license", "author", "page"}, None) か (None, 使わない理由)。"""
    if not info:
        return None, "Commons に画像の情報がない"
    lic = (info["license_short"] or "").strip()
    if not any(re.fullmatch(p, lic) for p in cm["license_patterns"]):
        return None, f"ライセンスが許可外・不明({lic or 'なし'})"
    if info["restrictions"]:
        return None, "利用の制限の注記がある"
    if info["mime"] not in cm["mime_types"]:
        return None, f"形式が許可外({info['mime']})"
    page = urlsplit(info["descriptionurl"] or "")
    if page.scheme != "https" or page.hostname not in cm["page_hosts"]:
        return None, f"ファイルのページのホストが許可外({page.hostname})"
    thumb = urlsplit(info["thumburl"] or "")
    new_host = cm["thumb_host_rewrite"].get(thumb.hostname)
    if thumb.scheme == "https" and new_host and thumb.path.startswith(cm["thumb_path_prefix"]):
        thumb = urlsplit(f"https://{new_host}{thumb.path}")      # 承認済みのホストへ(パスは同じ・クエリは捨てる)
    if thumb.scheme != "https" or thumb.hostname not in cm["image_hosts"]:
        return None, f"サムネイルのホストが許可外({thumb.hostname})"
    author = info["artist"][:cm["author_max_chars"]["value"]]
    if not author:
        if not any(re.fullmatch(p, lic) for p in cm["no_author_ok_patterns"]):
            return None, "作者の表記がない"
        author = cm["author_unknown"]
    return {"image_url": thumb.geturl(), "license": lic, "author": author, "page": info["descriptionurl"]}, None


class _Stop(Exception):
    pass


def fetch_commons(rows, *, http_get, http_bytes, ph, max_requests, has_cache, today=None, sleep=time.sleep, skip=frozenset(), on_got=None):
    """表の種ごとに、Wikidata → Commons → 画像の順で写真を探す。has_cache(taxon_id) が真・skip(目で見て使わない)の種は飛ばす。
    1 種ずつ順番に。→ (取れた [{row, meta, data, ext}], 使わなかった {和名: 理由}, 報告)。HTTP の非 200 ならそこで止める。"""
    cm = ph["commons"]
    today = (today or date.today()).isoformat()
    gap = cm["min_interval_s"]["value"]                          # Wikimedia へは iNaturalist より広く空ける(429 を受けて)
    rep = {"requests": 0, "status": "ok", "stopped": None, "skipped_cached": [], "not_started": []}
    got, unused = [], {}
    todo = []
    for row in rows:
        (rep["skipped_cached"] if has_cache(row["taxon_id"]) or row["taxon_id"] in skip else todo).append(row)

    def call(fetch, *args):
        """1 リクエスト(間隔・上限・通信エラー・非 200 をここで扱う)。→ 応答。止めるときは _Stop。"""
        if rep["requests"] >= max_requests:
            rep["stopped"] = f"--max-requests {max_requests} に達したため止めた"
            raise _Stop
        _wait(rep, gap, sleep)
        rep["requests"] += 1
        try:
            status, body, _ = fetch(*args)
        except OSError as ex:                                    # 再試行せず、ここまでの結果を残して止める
            rep["status"], rep["stopped"] = "network_error", f"通信エラーのため止めた({type(ex).__name__})。ここまでの結果は残す。続きは再実行で"
            raise _Stop
        if status != HTTPStatus.OK:
            rep["status"], rep["stopped"] = f"HTTP {status}", f"HTTP {status} のため止めた(残りは読まない)"
            raise _Stop
        return body

    def js(body):
        try:
            return json.loads(body)
        except ValueError as ex:
            rep["status"], rep["stopped"] = "parse_error", f"応答の形が想定と違う: {ex}"
            raise _Stop

    for i, row in enumerate(todo):
        name = row["name"]
        try:
            try:
                ids = parse_search(js(call(http_get, search_url(row["scientific"], cm))), cm)
                found = []
                if ids:
                    doc = js(call(http_get, entity_url(ids, cm)))
                    for qid in ids:
                        ent = parse_entity(doc, qid, cm)
                        if row["scientific"] in ent["p225"]:     # 学名(P225)が完全一致する分類群だけ
                            found.append((qid, ent))
                if len(found) != 1:
                    unused[name] = f"Wikidata で学名が完全一致する分類群がちょうど 1 件でない({len(found)} 件)"
                    continue
                files = found[0][1]["p18"]
                if not files:
                    unused[name] = "Wikidata に画像(P18)がない"
                    continue
                info = parse_imageinfo(js(call(http_get, imageinfo_url(files[0], cm))))
                ok, why = usable(info, cm)
                if not ok:
                    unused[name] = why
                    continue
                body = call(lambda u: http_bytes(u, ph["max_image_bytes"]["value"]), ok["image_url"])
            except ParseError as ex:
                rep["status"], rep["stopped"] = "parse_error", f"応答の形が想定と違う: {ex}"
                raise _Stop
        except _Stop:
            if rep["status"] == "ok":                            # 上限に達しただけ(エラーではない)
                rep["not_started"] = [r["name"] for r in todo[i:]]
            else:
                rep["not_started"] = [r["name"] for r in todo[i + 1:]]
            break
        kind, why = check_image(body, ph)
        if not kind:
            unused[name] = f"写真を捨てた({why})"
            continue
        meta = {"name": name, "scientific": row["scientific"], "taxon_id": row["taxon_id"], "photo_id": None, "source": cm["source_id"],
                "license": ok["license"], "license_code": None, "attribution": ok["author"], "photo_page": ok["page"],
                "fetched_on": today, "image_type": kind}
        item = {"row": row, "meta": meta, "data": body, "ext": kind}
        got.append(item)
        if on_got:
            on_got(item)                                         # 取れたらすぐ保存する(あとの通信で中止されても失わない)
    return got, unused, rep
