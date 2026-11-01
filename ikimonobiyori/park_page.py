"""公園ごとに「見られる鳥」を写真つきで見せる単独の HTML ページ(段階38。指示書 docs/stage38-instructions.md 3-3)。

- 材料は文章の答えと同じ facts.json(`ikimonobiyori.ask facts`)の野鳥の候補(park_birds)だけ。新しい事実を足さない。
- 公園ごとの節に、その公園の鳥を並べる。各鳥: 写真(無ければ「写真なし」)・和名・なぜ今か・材料の日付と出典。
  写真には撮影者名・ライセンスを表示し、写真のページ(iNaturalist または Commons)へリンクする。
- 各公園の節に、対象の日の開園・休み(closed_on)、最近の記録の日付、公園のページへのリンク。
- ページに 1 回だけ「写真は種の代表写真で、その公園で撮られたものではありません」。
- 安全: すべての文字を html.escape。JavaScript なし。CSP。写真は data URI で埋め込む(1 枚の HTML で開ける)。リンクは http・https だけ。
- 通信しない。写真はキャッシュ(guide_photos)にあるものだけ。文はすべて data/ask/policy.yaml の park_page から作る。
- 検査用の文の一覧(check_lines)も返す(撮影者名・ライセンスの表記は写真の情報なので検査に入れない)。"""
import base64
import html
from datetime import date
from urllib.parse import urlsplit

MIME = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
WEEKDAYS = "月火水木金土日"
CSS = """
:root { color-scheme: light; --fg: #1d2a24; --muted: #51605a; --faint: #6b7872; --bg: #f6f7f4; --card: #ffffff; --line: #c9d1cb; --accent: #1f5f4a; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif; color: var(--fg); background: var(--bg); line-height: 1.65; }
main { max-width: 64rem; margin: 0 auto; padding: 1rem; }
h1 { font-size: 1.55rem; margin: 0.5rem 0; }
h2 { font-size: 1.25rem; margin: 2rem 0 0.5rem; border-bottom: 2px solid var(--accent); padding-bottom: 0.25rem; }
.meta, .note { color: var(--muted); font-size: 0.9rem; margin: 0.2rem 0; }
.park-facts { margin: 0.3rem 0 0.6rem; padding-left: 1.2rem; font-size: 0.95rem; }
.birds { display: grid; grid-template-columns: repeat(auto-fill, minmax(11.5rem, 1fr)); gap: 0.7rem; padding: 0; margin: 0; list-style: none; }
.bird { background: var(--card); border: 1px solid var(--line); border-radius: 0.5rem; padding: 0.55rem; }
.bird img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; border-radius: 0.3rem; background: #e7ebe8; }
.nophoto { display: flex; align-items: center; justify-content: center; aspect-ratio: 4 / 3; border: 1px dashed var(--line); border-radius: 0.3rem; color: var(--muted); font-size: 0.85rem; }
.bird h3 { font-size: 1.05rem; margin: 0.35rem 0 0.1rem; }
.why { margin: 0; font-size: 0.9rem; }
.src { margin: 0.15rem 0 0; color: var(--muted); font-size: 0.8rem; }
.credit { margin: 0.25rem 0 0; color: var(--faint); font-size: 0.72rem; line-height: 1.3; overflow-wrap: anywhere; }
a { color: var(--accent); }
@media (max-width: 30rem) { main { padding: 0.6rem; } .birds { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.5rem; } h1 { font-size: 1.3rem; } }
@media print { body { background: #fff; } .bird { break-inside: avoid; } }
"""
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def esc(x):
    return html.escape(str(x), quote=True)


def safe_url(url):
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
        return None
    p = urlsplit(url)
    return url if p.scheme.lower() in ("http", "https") and p.netloc else None


def link(url, text):
    u = safe_url(url)
    return f'<a href="{esc(u)}" rel="noopener noreferrer">{esc(text)}</a>' if u else esc(text)


def _md(iso):
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.month}/{d.day}"


def short_author(meta, author_re):
    import re
    a = html.unescape(meta.get("attribution") or "")            # 応答の表記が文字参照(&amp; など)を含むことがある。表示のときにもう一度だけ escape する
    m = re.match(author_re, a)
    return m.group(1) if m else a


def parks(facts, policy):
    """ページに載せる公園(野鳥の候補のうち、鳥の一覧があるもの。答えと同じ順。上限は policy の max_parks)。"""
    b = (facts.get("subjects") or {}).get("birds") or {}
    out = [c for c in b.get("candidates") or [] if c.get("park_birds")]
    return out[: policy["max_parks"]["value"]]


def build(facts, *, policy, photo_for, author_re, commons_source_id, now, care=()):
    """facts.json → (HTML, 検査用の文の一覧, 載せた鳥 {公園: [(和名, 写真あり)]})。photo_for(鳥) → (メタデータ, バイト列) か None。"""
    t = policy["text"]
    lines = []

    def say(s):
        lines.append(s)
        return esc(s)
    dates = [date.fromisoformat(x) for x in facts.get("dates") or []]
    dtxt = "・".join(f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})" for d in dates)
    body = [f"<h1>{say(t['title'].format(dates=dtxt))}</h1>"]
    if facts.get("origin"):
        body.append(f'<p class="meta">{say(t["origin"].format(origin=facts["origin"]))}</p>')
    body.append(f'<p class="note">{say(t["photo_note"])}</p>')
    shown = {}
    for i, c in enumerate(parks(facts, policy)):
        head = f"{CIRCLED[i] if i < len(CIRCLED) else str(i + 1) + '.'} {c['name']}" + (f"({c['city']})" if c.get("city") else "")
        body.append(f"<section><h2>{say(head)}</h2>")
        pf = []
        cur = c.get("latest_dated") or c.get("current")         # 日付のある最新の記録(なければ今の状態)
        if cur:
            when = _md(cur["state_date"]) if cur.get("state_date") else None
            if when and cur.get("recent") is False:              # 最近ではない記録は「以前の記録」として年を付ける
                pf.append(say(t["older"].format(text=cur["state_raw"], publisher=cur.get("publisher") or "", year=cur["state_date"][:4], md=when)))
            else:
                pf.append(say(t["recent"].format(text=cur["state_raw"], publisher=cur.get("publisher") or "", md=when) if when else
                              t["recent_nodate"].format(text=cur["state_raw"], publisher=cur.get("publisher") or "")))
        for e in c.get("closed_on") or []:
            if e.get("line"):
                pf.append(say(e["line"]))
        if c.get("hours") and c["hours"].get("text"):
            pf.append(say(t["hours"].format(text=c["hours"]["text"])))
        pg = next((p for p in c.get("pages") or [] if safe_url(p.get("url"))), None)
        if pg:
            lines.append(pg["url"])
            pf.append(esc(t["park_link"]) + link(pg["url"], pg.get("publisher") or urlsplit(pg["url"]).hostname))
        if pf:
            body.append('<ul class="park-facts">' + "".join(f"<li>{x}</li>" for x in pf) + "</ul>")
        cards = []
        for b in c["park_birds"]:
            got = photo_for(b)
            if got:
                meta, data = got
                img = f'<img src="data:{MIME[meta["image_type"]]};base64,{base64.b64encode(data).decode("ascii")}" alt="{esc(b["name"])}">'
                commons = meta.get("source") == commons_source_id
                credit = (f'<p class="credit">{esc(t["credit"].format(author=short_author(meta, author_re), license=meta["license"]))} '
                          f'{link(meta.get("photo_page"), t["photo_link_commons"] if commons else t["photo_link"])}</p>')
            else:
                img = f'<div class="nophoto">{esc(t["no_photo"])}</div>'
                credit = ""
            when = b.get("period") or (_md(b["date"]) if b.get("date") else "")
            src = t["source"].format(kind=b["kind_label"], when=when, publisher=b.get("publisher") or "") if when else \
                t["source_nodate"].format(kind=b["kind_label"], publisher=b.get("publisher") or "")
            cards.append(f'<li class="bird">{img}<h3>{say(b["name"])}</h3><p class="why">{say(b["why"])}</p><p class="src">{say(src)}</p>{credit}</li>')
            shown.setdefault(c["name"], []).append((b["name"], bool(got)))
        body.append('<ul class="birds">' + "".join(cards) + "</ul></section>")
    if care:
        body.append(f'<h2>{say(t["care_heading"])}</h2><ul class="park-facts">' + "".join(f"<li>{say(m)}</li>" for m in care) + "</ul>")
    body.append(f'<p class="note">{say(t["footer"])}</p>')
    page = ("<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f'<meta http-equiv="Content-Security-Policy" content="{esc(policy["csp"])}">\n'
            f"<title>{esc(t['title'].format(dates=dtxt))}</title>\n<style>{CSS}</style>\n</head>\n<body>\n<main>\n"
            + "\n".join(body) + "\n</main>\n</body>\n</html>\n")
    return page, lines, shown
