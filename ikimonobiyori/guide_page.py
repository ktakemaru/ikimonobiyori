"""野鳥の案内の写真つき HTML ページ(段階29。docs/stage29-decisions.md)。

- 文はすべて `guide find --text` と同じ部品(guide.answer_parts)から作る。新しい事実を足さない。選び方も find と同じ。
  足すのは見た目(カード・写真・リンク)だけ。写真は「種の代表写真」で、その場所で撮られたものではない(ページの末尾に 1 文)。
- 安全: すべての文字を html.escape する。JavaScript を入れない。CSP(default-src 'none'; img-src data:; style-src 'unsafe-inline')。
  写真は data URI で埋め込む(外部の画像 URL を img に書かない)。リンクは http・https のものだけ、rel="noopener noreferrer"。
  リンクにするのは、記録されていて退役していない出どころの URL だけ。
- 通信しない。写真は guide photos-fetch がキャッシュに置いたものだけを読む(ないものは「写真なし」。代わりの絵や別の鳥の写真は入れない)。
- 書き込み先は IKIMONOBIYORI_DATA_DIR の下(既定)。--out で指すのは、そこの下かリポジトリの外だけ(リポジトリの追跡ファイルを実行で変えない)。"""
import base64
import html
import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from . import guide, guide_photos, paths

MIME = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
CSS = """
:root { color-scheme: light; --fg: #1d2a24; --muted: #51605a; --bg: #f6f7f4; --card: #ffffff; --line: #c9d1cb; --accent: #1f5f4a; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif; color: var(--fg); background: var(--bg); line-height: 1.7; }
main { max-width: 64rem; margin: 0 auto; padding: 1rem; }
h1 { font-size: 1.6rem; margin: 0.5rem 0; }
h2 { font-size: 1.25rem; margin: 2rem 0 0.75rem; border-bottom: 2px solid var(--accent); padding-bottom: 0.25rem; }
h3 { font-size: 1.05rem; margin: 0 0 0.25rem; }
.meta, .where, .note, .legend, figcaption { color: var(--muted); font-size: 0.9rem; margin: 0.25rem 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: 0.75rem; padding: 0; list-style: none; margin: 0; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 0.5rem; padding: 0.75rem; }
.card img { display: block; width: 100%; height: auto; border-radius: 0.25rem; }
.badge { display: inline-block; border: 1px solid var(--accent); color: var(--accent); border-radius: 0.25rem; padding: 0 0.4rem; font-size: 0.8rem; margin-right: 0.25rem; }
.nophoto { border: 1px dashed var(--line); color: var(--muted); font-size: 0.85rem; padding: 0.5rem; text-align: center; }
.thumbs { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.4rem 0; padding: 0; list-style: none; }
.thumbs figure { margin: 0; width: 4.5rem; }
.thumbs img { width: 4.5rem; height: auto; }
ul.links { margin: 0.25rem 0 0; padding-left: 1.2rem; font-size: 0.9rem; }
a { color: var(--accent); }
@media (max-width: 30rem) { main { padding: 0.5rem; } .grid { grid-template-columns: 1fr; } h1 { font-size: 1.35rem; } }
@media print { body { background: #fff; } .card { break-inside: avoid; } a { color: inherit; } }
"""


def esc(x):
    return html.escape(str(x), quote=True)


def safe_url(url, policy):
    """リンクにしてよい URL(http・https のみ。空白・制御文字を含まない)なら、そのまま。そうでなければ None。"""
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 for c in url):
        return None
    parts = urlsplit(url)
    return url if parts.scheme.lower() in policy["photos"]["html"]["link_schemes"] and parts.netloc else None


def link(url, text, policy):
    u = safe_url(url, policy)
    return f'<a href="{esc(u)}" rel="noopener noreferrer">{esc(text)}</a>' if u else esc(text)


def source_links(entry, retired_urls, policy):
    """記録されていて退役していない出どころの URL だけ → [(URL, 表示名)]。同じ URL は 1 回。"""
    out, seen = [], set()
    for s in entry.get("sources") or []:
        u = s.get("url")
        if u in seen or u in retired_urls or not safe_url(u, policy):
            continue
        seen.add(u)
        out.append((u, s.get("publisher") or s.get("host") or urlsplit(u).hostname))
    return out


def data_uri(meta, data):
    return f"data:{MIME[meta['image_type']]};base64," + base64.b64encode(data).decode("ascii")


def species_in(parts, section_key="recommend"):
    """欄の行に出る種名(表示してよい種名)→ 出てくる名所の数の多い順・和名順。"""
    count = {}
    for sec in parts["sections"]:
        if sec["key"] != section_key:
            continue
        for r in sec["rows"]:
            for k in r["entry"]["kinds"]:
                if k["shown"]:
                    count[k["kind"]] = count.get(k["kind"], 0) + 1
    return sorted(count, key=lambda n: (-count[n], n))


def build_page(parts, *, policy, now, kind_notes=(), photo_for=lambda name: None, retired_urls=frozenset(), in_table=lambda name: True):
    """答えの部品(guide.answer_parts)→ 単独の HTML(文字列)。photo_for(和名) → (メタデータ, バイト列) か None。
    in_table(和名) が偽の種(対応表にない語)はカードにせず、「そのほか: …」の 1 行(文字だけ)にまとめる。"""
    h = policy["photos"]["html"]
    used = {}                                                   # 和名 → (メタデータ, バイト列)(ページに載せた写真)

    def photo(name):
        if name not in used:
            used[name] = photo_for(name)
        return used[name]

    notes_by_name = {e["name"]: e for e in kind_notes if e.get("scope") == "kind"}

    def species_card(name):
        got = photo(name)
        note = notes_by_name.get(name)
        se = (note or {}).get("season")
        season = h["season"].format(text=se["text"]) if se and se["shown"] else h["season_unknown"]
        if got:
            fig = f'<img src="{esc(data_uri(*got))}" alt="{esc(name)}" loading="lazy">'
        else:
            fig = f'<div class="nophoto">{esc(h["no_photo"])}</div>'
        return f'<li class="card">{fig}<h3>{esc(name)}</h3><p class="note">{esc(season)}</p></li>'

    def place_card(row, sec):
        e = row["entry"]
        name = esc(row["name"])
        title = f'{esc(row["index"])}. {name}' if row["index"] else name
        thumbs = []
        for k in e["kinds"]:
            if k["shown"] and photo(k["kind"]):
                meta, data = photo(k["kind"])
                thumbs.append(f'<li><figure><img src="{esc(data_uri(meta, data))}" alt="{esc(k["kind"])}" loading="lazy">'
                              f'<figcaption>{esc(k["kind"])}</figcaption></figure></li>')
        links = [f"<li>{link(u, label, policy)}</li>" for u, label in source_links(e, retired_urls, policy)]
        return (f'<li class="card"><h3>{title}</h3>'
                f'<p class="where"><span class="badge">{esc(sec["heading"])}</span>{esc(row["where"])}</p>'
                f'<p class="body">{esc(row["body"])}</p>'
                + (f'<ul class="thumbs">{"".join(thumbs)}</ul>' if thumbs else "")
                + (f'<p class="note">{esc(h["sources"])}</p><ul class="links">{"".join(links)}</ul>' if links else "")
                + "</li>")

    body = [f'<h1>{esc(h["title"])}</h1>', f'<p class="meta">{esc(h["created"].format(at=now.isoformat(timespec="minutes")))}</p>']
    if parts["origin_line"]:
        body.append(f'<p class="meta">{esc(parts["origin_line"])}</p>')
    if parts["legend"]:
        body.append(f'<p class="legend">{esc(parts["legend"])}</p>')
    all_names = species_in(parts)
    names = [n for n in all_names if in_table(n)]
    rest = [n for n in all_names if not in_table(n)]
    if names or rest:
        body.append(f'<h2>{esc(h["headings"]["birds"])}</h2>')
    if names:
        body.append(f'<ul class="grid">{"".join(species_card(n) for n in names)}</ul>')
    if rest:
        body.append(f'<p class="note">{esc(h["others"].format(names=h["others_sep"].join(rest)))}</p>')
    for sec in parts["sections"]:
        if sec["key"] == "recommend":
            body.append(f'<h2>{esc(h["headings"]["places"])}</h2>')
        else:
            body.append(f'<h2>{esc(sec["heading"])}</h2>')
        if sec["rows"]:
            body.append(f'<ul class="grid">{"".join(place_card(r, sec) for r in sec["rows"])}</ul>')
        else:
            body.append(f'<p class="note">{esc(sec["none"])}</p>')
    if parts["notes"]:
        body.append(f'<h2>{esc(parts["notes_heading"])}</h2><ul>{"".join(f"<li>{esc(n)}</li>" for n in parts["notes"])}</ul>')
    shown = {n: v for n, v in used.items() if v}
    body.append(f'<h2>{esc(h["headings"]["credits"])}</h2><p class="note">{esc(h["photo_note"])}</p>')
    if shown:
        items = []
        for n in sorted(shown):
            meta = shown[n][0]
            items.append(f'<li>{esc(h["credit_line"].format(name=n, attribution=meta["attribution"], license=meta["license"]))}'
                         f' ({link(meta["photo_page"], h["photo_link"], policy)})</li>')
        body.append(f'<ul class="note">{"".join(items)}</ul>')
    body.append(f'<p class="note">{esc(h["credit"])}</p>')
    return ("<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f'<meta http-equiv="Content-Security-Policy" content="{esc(h["csp"])}">\n'
            f"<title>{esc(h['title'])}</title>\n<style>{CSS}</style>\n</head>\n<body>\n<main>\n" + "\n".join(body) + "\n</main>\n</body>\n</html>\n")


def out_path_ok(path):
    """書いてよい場所か: IKIMONOBIYORI_DATA_DIR の下か、リポジトリの外。"""
    p = path.resolve()
    for base in (paths.data_dir().resolve(),):
        if base == p or base in p.parents:
            return True
    repo = paths.PKG.parent.resolve()
    return not (repo == p or repo in p.parents)


def page_cmd(a, now=None):
    policy = guide.load_policy()
    ph = policy["photos"]
    themes, kinds = guide.themes_for_words([a.theme], policy)
    if themes is None:
        print(f"言い換えの表にない言葉(推測で結びつけない): {kinds}", file=sys.stderr)
        return 1
    now = now or guide.clock_now()
    on = date.fromisoformat(a.date) if a.date else now.date()
    entries = guide.build()[0]
    found = guide.find(entries, themes=themes, kinds=kinds, on=on, policy=policy, origin=a.origin)
    origin, line = guide.origin_line_for(a.origin)
    parts = guide.answer_parts(found, policy, origin_line=line, themes=themes)
    text = guide.render_answer(found, policy, origin_line=line, themes=themes)
    bad = guide.forbidden_in_answer(text, policy)
    if bad:
        print(f"答えに内部用語が出ている: {bad}", file=sys.stderr)
        return 1
    table = guide_photos.load_table()

    def photo_for(name):
        row = table.get(name)
        return guide_photos.load_photo(row["taxon_id"]) if row else None

    out = Path(a.out) if a.out else guide_photos.page_dir() / ph["page_file"]
    if not out_path_ok(out):
        print("書き込み先は IKIMONOBIYORI_DATA_DIR の下かリポジトリの外だけです(リポジトリの追跡ファイルを実行で変えません)", file=sys.stderr)
        return 2
    page = build_page(parts, policy=policy, now=now, kind_notes=found.get("kind_notes") or [], photo_for=photo_for,
                      retired_urls=set(guide.load_retired(policy)["urls"]), in_table=lambda n: n in table)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    print(str(out.resolve()))
    if a.open:
        if hasattr(os, "startfile"):
            os.startfile(str(out.resolve()))
        else:
            import webbrowser
            webbrowser.open(out.resolve().as_uri())
    return 0
