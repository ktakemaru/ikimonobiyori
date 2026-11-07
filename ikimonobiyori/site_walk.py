"""段階60 第5部: 施設のサイトを深さ 3 まで辿り、発行物の PDF を拾う(通信しない)。

ページの取得はエージェントの道具(WebFetch など)で行い、読んだページのリンク(href と文字)をここに渡す。
ここが決めるのは: どのページを次に読むか(同じサイトの中だけ・深さの上限・robots.txt で拒否されたパスは読まない・
優先リンク語とページ送り・サイトマップ)と、PDF の判定と、発行物台帳への記録(本文は保存しない)。
値は data/knowledge/policy.yaml の site_walk。CLAUDE.md の「スクレイピングのコードを書き足さない」に合わせ、このモジュールは通信しない。
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

from . import pdf_text as PT
from .paths import data_path


def cfg():
    return PT.policy()["site_walk"]


def _host(url):
    return (urlparse(url).hostname or "").lower()


def _norm(url):
    return urldefrag(url)[0]


def state_path(facility, env=None):
    return Path(data_path(cfg()["dir"], env)) / f"{facility}.json"


def load(facility, env=None):
    p = state_path(facility, env)
    if not p.exists():
        raise ValueError(f"{facility}: 辿りの状態がない(先に start を実行する)")
    return json.loads(p.read_text(encoding="utf-8"))


def save(st, env=None):
    p = state_path(st["facility"], env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def start(facility, url, extra_hosts=(), env=None):
    """辿りを始める。同じサイト(開始ページのホスト)と、同じ運営主体の文書置き場(extra_hosts)だけを辿る。"""
    url = _norm(url)
    st = {"facility": facility, "start": url, "hosts": sorted({_host(url), *[h.lower() for h in extra_hosts]}),
          "queue": [{"url": url, "depth": 0, "why": "start"}], "visited": {}, "pdfs": [], "disallow": [], "sitemaps": []}
    save(st, env)
    return st


def parse_robots(text):
    """robots.txt の User-agent: * の Disallow と、Sitemap の行。"""
    disallow, sitemaps, applies = [], [], False
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            applies = v == "*"
        elif k == "disallow" and applies and v:
            disallow.append(v)
        elif k == "sitemap" and v:
            sitemaps.append(v)
    return disallow, sitemaps


def set_robots(st, text):
    st["disallow"], st["sitemaps"] = parse_robots(text)
    for sm in st["sitemaps"]:
        if _host(sm) in st["hosts"]:
            _enqueue(st, _norm(sm), 1, "sitemap")
    return st


def allowed(st, url):
    """同じサイト(または同じ運営主体の文書置き場)で、robots.txt で拒否されていない。"""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or _host(url) not in st["hosts"]:
        return False
    path = u.path or "/"
    return not any(path.startswith(d) for d in st["disallow"])


def is_pdf(url):
    u = urlparse(url)
    return bool(re.search(cfg()["pdf_url_re"], u.path + ("?" + u.query if u.query else ""), re.I))


def _priority(href, text, c):
    t = f"{text or ''} {href}"
    return any(w in t for w in c["priority_words"])


def _pager(href, text, c):
    return any(w in (text or "") for w in c["pager_words"]) or bool(re.search(c["pager_url_re"], href))


def _enqueue(st, url, depth, why):
    if url in st["visited"] or any(q["url"] == url for q in st["queue"]):
        return
    st["queue"].append({"url": url, "depth": depth, "why": why})


def _add_pdf(st, url, text, found_on):
    if any(p["url"] == url for p in st["pdfs"]):
        return
    st["pdfs"].append({"url": url, "text": (text or "").strip()[:80], "found_on": found_on, "allowed": allowed(st, url)})


def add_page(st, url, links, status=200):
    """読んだページ(またはその結果)を渡す。links は [{"href", "text"}]。次に読むページと PDF を拾う。"""
    url = _norm(url)
    c = cfg()
    item = next((q for q in st["queue"] if q["url"] == url), None)
    depth = item["depth"] if item else 0
    st["queue"] = [q for q in st["queue"] if q["url"] != url]
    st["visited"][url] = {"depth": depth, "status": status}
    if status != 200:
        return st
    for ln in links or []:
        href = _norm(urljoin(url, ln.get("href") or ""))
        text = ln.get("text") or ""
        if is_pdf(href):
            _add_pdf(st, href, text, url)
            continue
        if not allowed(st, href):
            continue
        if _pager(href, text, c):
            _enqueue(st, href, depth, "pager")              # ページ送りは同じ深さ(一覧の続き)
        elif depth + 1 <= c["max_depth"] and _priority(href, text, c):
            _enqueue(st, href, depth + 1, "priority")
    return st


def add_sitemap(st, xml_text):
    """サイトマップ(sitemap.xml)の <loc> から、優先語を含む URL と PDF を拾う(深さ 1 として扱う)。"""
    c = cfg()
    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text or ""):
        loc = _norm(loc)
        if is_pdf(loc):
            _add_pdf(st, loc, "", "sitemap")
        elif allowed(st, loc) and (_priority(loc, "", c) or loc.endswith(".xml")):
            _enqueue(st, loc, 1, "sitemap")
    return st


def next_urls(st, n=None):
    """次に読むページ(浅い順。上限の枚数まで)。robots.txt で拒否されたもの・深さの上限を超えるものは出さない。"""
    c = cfg()
    left = c["max_pages"] - len(st["visited"])
    if left <= 0:
        return []
    qs = sorted([q for q in st["queue"] if allowed(st, q["url"]) and q["depth"] <= c["max_depth"]],
                key=lambda q: (q["depth"], q["why"] != "priority", q["url"]))
    return qs[: min(left, n) if n else left]


YM_RES = [(re.compile(r"(20\d{2})年\s*(\d{1,2})月"), lambda m: f"{m.group(1)}-{int(m.group(2)):02d}"),
          (re.compile(r"令和\s*(\d{1,2})年\s*(\d{1,2})月"), lambda m: f"{2018 + int(m.group(1))}-{int(m.group(2)):02d}"),
          (re.compile(r"令和\s*(\d{1,2})年"), lambda m: str(2018 + int(m.group(1)))),
          (re.compile(r"(20\d{2})年"), lambda m: m.group(1)),
          (re.compile(r"(?<!\d)(20\d{2})[-_.]?(0[1-9]|1[0-2])(?!\d)"), lambda m: f"{m.group(1)}-{m.group(2)}")]


def published_of(text, url):
    """発行年月(年つきのときだけ)。リンクの文字 → ファイル名の順に読む。年が読めなければ None(最新号の判定に使わない)。"""
    for src in (text or "", Path(urlparse(url).path).name):
        for rx, fmt in YM_RES:
            m = rx.search(src)
            if m:
                return fmt(m)
    return None


def record_pdfs(st, env=None, taken_on=None):
    """見つけた PDF を発行物台帳に記録する(同じ URL は足さない。読み取りの状況は「PDF 未読」から)。"""
    have = {r.get("url") for r in PT.load_publications(env)}
    out = []
    for p in st["pdfs"]:
        if p["url"] in have or not p["allowed"]:
            continue
        row = PT.record_publication({"facility": st["facility"], "title": p["text"] or Path(urlparse(p["url"]).path).name,
                                     "issue": None, "published": published_of(p["text"], p["url"]), "url": p["url"],
                                     "format": "pdf", "taken_on": taken_on or date.today().isoformat()}, env=env)
        out.append(row)
    return out


def summary(st, env=None):
    """辿った深さ・ページ数・見つけた PDF の数・読めた割合(台帳の読み取りの状況から)・最新号(年つき)。"""
    rows = {r.get("url"): r for r in PT.load_publications(env)}
    unread = PT.policy()["pdf"]["unread_label"]
    urls = [p["url"] for p in st["pdfs"] if p["allowed"]]
    read = [u for u in urls if u in rows and rows[u].get("status") not in (None, unread)]
    return {"facility": st["facility"], "pages": len(st["visited"]), "max_depth": max([v["depth"] for v in st["visited"].values()], default=0),
            "pdfs": len(urls), "pdfs_read": len(read), "read_ratio": (len(read) / len(urls)) if urls else None,
            "latest": PT.latest_issue([rows[u] for u in urls if u in rows])}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="site_walk", description="施設のサイトを深さ 3 まで辿る手順(通信しない。ページはエージェントが読む)")
    sub = ap.add_subparsers(dest="step", required=True)
    p = sub.add_parser("start")
    p.add_argument("--facility", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--extra-host", action="append", default=[], help="同じ運営主体の文書置き場のホスト")
    for name, hlp in (("robots", "robots.txt の本文のファイル"), ("sitemap", "sitemap.xml の本文のファイル")):
        p = sub.add_parser(name)
        p.add_argument("--facility", required=True)
        p.add_argument("--text", required=True, help=hlp)
    p = sub.add_parser("add")
    p.add_argument("--facility", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--links", help="[{href,text}] の JSON ファイル")
    p.add_argument("--status", type=int, default=200)
    p = sub.add_parser("next")
    p.add_argument("--facility", required=True)
    p.add_argument("-n", type=int)
    p = sub.add_parser("pdfs")
    p.add_argument("--facility", required=True)
    p.add_argument("--taken-on")
    p = sub.add_parser("summary")
    p.add_argument("--facility", required=True)
    a = ap.parse_args(argv)

    def out(d):
        sys.stdout.write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")

    try:
        if a.step == "start":
            out(start(a.facility, a.url, a.extra_host)["queue"])
            return 0
        st = load(a.facility)
        if a.step == "next":
            out(next_urls(st, a.n))
            return 0
        if a.step == "summary":
            out(summary(st))
            return 0
        if a.step == "robots":
            set_robots(st, Path(a.text).read_text(encoding="utf-8"))
        elif a.step == "sitemap":
            add_sitemap(st, Path(a.text).read_text(encoding="utf-8"))
        elif a.step == "add":
            add_page(st, a.url, json.loads(Path(a.links).read_text(encoding="utf-8")) if a.links else [], a.status)
        elif a.step == "pdfs":
            out(record_pdfs(st, taken_on=a.taken_on))
            save(st)
            return 0
        save(st)
        out(next_urls(st))
        return 0
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
