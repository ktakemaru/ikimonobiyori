"""市区町村の代表点(座標)だけを Wikidata から読む小さなコード(段階23 フェーズ2 の 6。docs/stage23-decisions.md)。

- 決定(ユーザー承認 2026-10-25): ホストは www.wikidata.org だけ(config.yaml の live.allowed_hosts_by_subject.guide_places)。
  読むのは、日本語版ウィキペディアの記事名(「神川町」「港区 (東京都)」など)に結びつく項目の、座標(P625)と日本語の説明だけ。
  データは CC0。座標の数字と項目の id だけを返し、応答の本文はどこにも保存しない。キャッシュもしない。
- 項目の日本語の説明に、指定した都道府県の名前がないときは「確認できない」とし、座標を使わない(同じ名前の別の市町村を取らない。推測しない)。
- 通信は biyori-hub の計測フックの下だけ(呼び出し側 guide.py の places-fetch が BIYORI_ALLOW_LIVE=1・--max-requests・BIYORI_REQ_LOG を確かめる)。
  リクエストの間は config.yaml の live.min_interval_s(2 秒)以上空ける。HTTP 429 などの 4xx/5xx が返ったら、そこで止める(残りは読まない)。
- 応答の形が想定と違うときは ParseError で止める(推測で補わない)。"""
import json
import time
from http import HTTPStatus
from urllib.parse import urlencode

from . import ParseError

API = "https://www.wikidata.org/w/api.php"
COORD_PROP = "P625"          # 座標(coordinate location)
SITE = "jawiki"
LANG = "ja"


def entities_url(titles):
    """記事名の一覧 → wbgetentities の URL(座標・説明・日本語版の記事名だけを頼む)。"""
    q = {"action": "wbgetentities", "sites": SITE, "titles": "|".join(titles), "props": "claims|descriptions|sitelinks",
         "sitefilter": SITE, "languages": LANG, "format": "json", "redirects": "yes"}
    return API + "?" + urlencode(q)


def _coord(entity):
    claims = entity.get("claims")
    if not isinstance(claims, dict):
        raise ParseError("claims がない")
    for c in claims.get(COORD_PROP) or []:
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(v, dict) and isinstance(v.get("latitude"), (int, float)) and isinstance(v.get("longitude"), (int, float)):
            return float(v["latitude"]), float(v["longitude"])
    return None


def parse_entities(doc):
    """wbgetentities の応答 → {記事名: {"qid", "lat", "lon", "description"}}。記事のない名前は入らない。座標のない項目は lat・lon が None。"""
    if not isinstance(doc, dict) or not isinstance(doc.get("entities"), dict):
        raise ParseError("entities がない")
    out = {}
    for qid, ent in doc["entities"].items():
        if not isinstance(ent, dict):
            raise ParseError(f"{qid}: 項目が辞書でない")
        if "missing" in ent:
            continue
        title = ((ent.get("sitelinks") or {}).get(SITE) or {}).get("title")
        if not isinstance(title, str):
            raise ParseError(f"{qid}: 日本語版の記事名がない")
        desc = ((ent.get("descriptions") or {}).get(LANG) or {}).get("value")
        pt = _coord(ent)
        out[title] = {"qid": ent.get("id", qid), "lat": pt[0] if pt else None, "lon": pt[1] if pt else None,
                      "description": desc if isinstance(desc, str) else None}
    return out


def read_points(titles, *, http_get, cfg, max_requests, batch, sleep=time.sleep):
    """記事名の一覧を batch 件ずつ読む。→ ({記事名: 結果}, 報告 {"requests", "status", "stopped"})。
    4xx/5xx(429 を含む)ならそこで止める。max_requests に達したら残りは読まない。"""
    got, rep = {}, {"requests": 0, "status": "ok", "stopped": None}
    gap = cfg["live"]["min_interval_s"]
    for i in range(0, len(titles), batch):
        if rep["requests"] >= max_requests:
            rep["stopped"] = f"--max-requests {max_requests} に達したため、残り {len(titles) - i} 件は読まない"
            break
        if rep["requests"]:
            sleep(gap)
        status, body, _ = http_get(entities_url(titles[i:i + batch]))
        rep["requests"] += 1
        if status != HTTPStatus.OK:
            rep["status"], rep["stopped"] = f"HTTP {status}", f"HTTP {status} のため止めた(残りは読まない)"
            break
        try:
            got.update(parse_entities(json.loads(body)))
        except (ValueError, ParseError) as ex:
            rep["status"], rep["stopped"] = "parse_error", f"応答の形が想定と違う: {ex}"
            break
    return got, rep
