"""公式ページが分かったら必ず読む(段階58 第2部)。通信しない。読むのはエージェントの道具で、ここは「読むページ」「辿るリンク」「お知らせの行」を決める。

reader(url) → {"status": 200, "html": 本文, "links": [{url, text}]} を外から渡す(テストは合成)。取得の失敗(拒否・404・証明書)は回避せず、失敗として返す。"""
import re
from urllib.parse import urlparse

from . import answer_plan as AP


def cfg():
    return AP.load_policy()["official_pages"]


def is_official(url):
    host = (urlparse(url or "").hostname or "").lower()
    c = cfg()
    if host in c["excluded_hosts"] or any(host.endswith("." + x) for x in c["excluded_hosts"]):
        return False
    return any(host.endswith(s) for s in c["suffixes"]) or any(w in host for w in c["host_words"])


def plan_reads(rows, seen=()):
    """検索の結果や計画に出た URL のうち、公式のものを読む順に(同じ日に読んだページは除く)。"""
    out = []
    for r in rows:
        u = r.get("url")
        if u and u not in seen and u not in out and is_official(u):
            out.append(u)
    return out[: cfg()["max_pages"]]


def follow_links(page_url, links):
    """読んだページから、同じサイトの関連ページへ 1 階層だけ(お知らせ・紅葉情報・イベント・開園情報など)。"""
    c = cfg()
    host = urlparse(page_url).hostname
    out = []
    for l in links or []:
        u = l.get("url") or ""
        if urlparse(u).hostname != host or u in out or u == page_url:
            continue
        if any(w in (l.get("text") or "") for w in c["follow_words"]):
            out.append(u)
    return out


def read_all(rows, reader, seen=()):
    """公式のページを読み、関連ページを 1 階層辿る(全体で max_pages まで)。→ {"read": [...], "failed": [...], "pages": {url: 応答}}。"""
    c = cfg()
    queue = plan_reads(rows, seen)
    done, read, failed, pages = set(seen), [], [], {}
    first = list(queue)
    while queue and len(read) + len(failed) < c["max_pages"]:
        u = queue.pop(0)
        if u in done:
            continue
        done.add(u)
        res = reader(u) or {}
        if res.get("status") != 200:
            failed.append({"url": u, "reason": res.get("reason") or f"HTTP {res.get('status')}"})
            continue
        read.append({"url": u})
        pages[u] = res
        if u in first:
            queue += [x for x in follow_links(u, res.get("links")) if x not in done]
    return {"read": read, "failed": failed, "pages": pages}


def notice_kind(text):
    """開園日・閉鎖・規制・変更のお知らせか(語で判定)。"""
    return any(w in (text or "") for w in cfg()["notice_words"])


def notice_lines(candidates):
    """答えの「行く前に確認すること」の行(日付つき。文章の転載はしない。記録の notice だけ)。"""
    out = []
    for c in candidates:
        for n in c.get("notices") or []:
            d = n.get("date")
            md = f"{int(d[5:7])}/{int(d[8:10])}" if d else ""
            out.append({"line": cfg()["notice_line"].format(name=c["name"], text=n["text"], md=md), "url": n.get("url")})
    return out
