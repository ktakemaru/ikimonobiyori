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
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from . import guide, guide_photos, paths

MIME = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
CSS = """
:root { color-scheme: light; --fg: #1d2a24; --muted: #51605a; --faint: #75827c; --bg: #f6f7f4; --card: #ffffff; --line: #c9d1cb; --accent: #1f5f4a; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Hiragino Sans", "Yu Gothic", "Meiryo", sans-serif; color: var(--fg); background: var(--bg); line-height: 1.7; }
main { max-width: 64rem; margin: 0 auto; padding: 1rem; }
h1 { font-size: 1.6rem; margin: 0.5rem 0; }
h2 { font-size: 1.25rem; margin: 2rem 0 0.75rem; border-bottom: 2px solid var(--accent); padding-bottom: 0.25rem; }
h3 { font-size: 1.05rem; margin: 0 0 0.25rem; }
.meta, .where, .note, .legend { color: var(--muted); font-size: 0.9rem; margin: 0.25rem 0; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: 0.75rem; padding: 0; list-style: none; margin: 0; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 0.5rem; padding: 0.75rem; }
.card img { display: block; width: 100%; height: auto; border-radius: 0.25rem; }
.badge { display: inline-block; border: 1px solid var(--accent); color: var(--accent); border-radius: 0.25rem; padding: 0 0.4rem; font-size: 0.8rem; margin-right: 0.25rem; }
.nophoto { border: 1px dashed var(--line); color: var(--muted); font-size: 0.85rem; padding: 0.5rem; text-align: center; }
.thumbs { display: flex; flex-wrap: wrap; gap: 0.6rem; margin: 0.5rem 0; padding: 0; list-style: none; }
.thumbs figure { margin: 0; width: 9.5rem; max-width: 100%; }
.thumbs img { width: 100%; height: auto; }
figcaption { margin: 0.15rem 0 0; font-size: 0.8rem; line-height: 1.35; }
figcaption .name { display: block; white-space: nowrap; word-break: keep-all; overflow-wrap: normal; }
.credit { display: block; color: var(--faint); font-size: 0.7rem; line-height: 1.3; overflow-wrap: anywhere; }
.facts { margin: 0.4rem 0 0; padding: 0; list-style: none; font-size: 0.92rem; }
.facts li { margin: 0.1rem 0; }
.faint { color: var(--faint); font-size: 0.75rem; margin: 0.35rem 0 0; }
ul.links { margin: 0.25rem 0 0; padding-left: 1.2rem; font-size: 0.9rem; }
details { margin: 0.35rem 0 0; font-size: 0.9rem; }
details summary { cursor: pointer; color: var(--muted); }
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


def source_links_numbered(entry, retired_urls, policy):
    """出どころのリンク [(URL, 表示名)]。同じ表示名が複数あるときは「東京都(1)」「東京都(2)」のように番号を付ける(見分けるため)。"""
    links = source_links(entry, retired_urls, policy)
    h = policy["photos"]["html"]
    total, seen, out = {}, {}, []
    for _, label in links:
        total[label] = total.get(label, 0) + 1
    for u, label in links:
        seen[label] = seen.get(label, 0) + 1
        out.append((u, h["link_dup"].format(label=label, i=seen[label]) if total[label] > 1 else label))
    return out


def short_author(meta, policy):
    """カードに添える撮影者名。iNaturalist の定型の表記(「(c) 名前, some rights reserved …」)は名前だけ、ほかは表記そのまま。"""
    a = meta["attribution"]
    m = re.match(policy["photos"]["html"]["author_re"], a)
    return m.group(1) if m else a


def season_state(note, month):
    """鳥の種の例年の時期(種類の説明 kind_notes の season。2 件以上の出どころが言うもの)と作成日の月 → "now"(今の月に重なる)・"out"(重ならない)・"unknown"(確認できていない)。"""
    se = (note or {}).get("season")
    if not se or not se.get("shown"):
        return "unknown"
    w = se.get("window")
    if se.get("year_round") is True:
        return "now"
    if not isinstance(w, dict) or not w.get("start") or not w.get("end"):
        return "unknown"
    return "now" if guide.windows_overlap((w["start"], w["end"]), (f"{month:02d}-01", f"{month:02d}-31")) else "out"


def created_text(now, h):
    return h["created"].format(y=now.year, m=now.month, d=now.day, h=now.hour, mi=now.minute)


def build_page(parts, *, policy, now, kind_notes=(), photo_for=lambda name: None, retired_urls=frozenset(), in_table=lambda name: True):
    """答えの部品(guide.answer_parts)→ 単独の HTML(文字列)。photo_for(和名) → (メタデータ, バイト列) か None。
    in_table(和名) が偽の種(対応表にない語)はカードにせず、「そのほか: …」の 1 行(文字だけ)にまとめる。
    鳥のカードは、時期が確認できて今(作成日の月)に合う鳥・時期の外の鳥・時期が未確認の鳥の 3 つのグループに分ける(段階31)。"""
    h = policy["photos"]["html"]
    used = {}                                                   # 和名 → (メタデータ, バイト列)(ページに載せた写真)

    def photo(name):
        if name not in used:
            used[name] = photo_for(name)
        return used[name]

    notes_by_name = {e["name"]: e for e in kind_notes if e.get("scope") == "kind"}

    def img(name, got):
        # data URI の画像には遅延読み込み(loading="lazy")を付けない: 利点がなく、ページ全体を撮る・印刷するときに下の欄の画像が空になりうる(段階31)
        return f'<img src="{esc(data_uri(*got))}" alt="{esc(name)}">'

    def credit(got):
        meta = got[0]
        return f'<span class="credit">{esc(h["photo_credit"].format(author=short_author(meta, policy), license=meta["license"]))}</span>'

    def species_card(name, with_season):
        got = photo(name)
        se = (notes_by_name.get(name) or {}).get("season")
        if got:
            fig = img(name, got)
        else:
            fig = f'<div class="nophoto">{esc(h["no_photo"])}</div>'
        season = f'<p class="note">{esc(h["season"].format(text=se["text"]))}</p>' if with_season and se and se.get("shown") else ""
        return f'<li class="card">{fig}<h3>{esc(name)}</h3>{season}' + (credit(got) if got else "") + "</li>"

    def bird_section(heading, names, with_season, note=None):
        names = sorted(names, key=lambda n: (season_state(notes_by_name.get(n), now.month) == "unknown"))     # 時期が確認できたものを先に(安定。あとは今の並び)
        out = [f'<h2>{esc(heading)}</h2>']
        if note:
            out.append(f'<p class="note">{esc(note)}</p>')
        out.append(f'<ul class="grid">{"".join(species_card(n, with_season) for n in names)}</ul>')
        return out

    def place_card(row, sec):
        e = row["entry"]
        f = row["fields"]
        name = esc(row["name"])
        title = f'{esc(row["index"])}. {name}' if row["index"] else name
        thumbs = []
        for k in e["kinds"]:                                    # 写真はどの欄のカードでも同じ: 確認できた種(shown)で、対応表と許可ライセンスの写真があるものだけ
            got = k["shown"] and photo(k["kind"])
            if got:
                thumbs.append(f'<li><figure>{img(k["kind"], got)}<figcaption><span class="name">{esc(k["kind"])}</span>{credit(got)}</figcaption></figure></li>')
        bits = policy["answer"]["bits"]
        facts = []
        if f["season"]:
            facts.append(bits["season"].format(text=f["season"]))
        if f["kinds"]:
            facts.append(h["row_birds"].format(text="・".join(f["kinds"])))
        d = f["distance"]
        if d:
            dist = bits["distance"].format(origin=d["origin"], km=d["km"]) + (h["row_edge"] if d["edge"] else "")
            facts.append(h["row_distance"].format(distance=dist, n=f["n"]))
        elif f["n"] is not None:
            facts.append(h["row_count"].format(n=f["n"]))
        links = source_links_numbered(e, retired_urls, policy)
        vis = h["links_visible"]["value"]
        li = [f"<li>{link(u, label, policy)}</li>" for u, label in links]
        link_html = ""
        if links:
            link_html = f'<p class="note">{esc(h["sources"])}</p><ul class="links">{"".join(li[:vis])}</ul>'
            if len(li) > vis:
                link_html += (f'<details class="more"><summary>{esc(h["links_more"].format(n=len(li) - vis))}</summary>'
                              f'<ul class="links">{"".join(li[vis:])}</ul></details>')
        return (f'<li class="card"><h3>{title}</h3>'
                f'<p class="where"><span class="badge">{esc(sec["heading"])}</span>{esc(row["where"])}</p>'
                + (f'<ul class="thumbs">{"".join(thumbs)}</ul>' if thumbs else "")
                + f'<ul class="facts">{"".join(f"<li>{esc(x)}</li>" for x in facts)}</ul>'
                + (f'<p class="faint">{esc(bits["classes"].format(text=f["classes"]))}</p>' if f["classes"] else "")
                + link_html
                + f'<p class="body" hidden>{esc(row["body"])}</p>'          # find --text と同じ 1 文。表示しない(既存テストが、本文がそのままの文字列で載ることを確かめている)
                + "</li>")

    body = [f'<h1>{esc(h["title"])}</h1>', f'<p class="meta">{esc(created_text(now, h))}</p>']
    if parts["origin_line"]:
        body.append(f'<p class="meta">{esc(parts["origin_line"])}</p>')
    if parts["legend"]:
        body.append(f'<p class="legend">{esc(parts["legend"])}</p>')
    all_names = species_in(parts)
    names = [n for n in all_names if in_table(n)]
    rest = [n for n in all_names if not in_table(n)]
    groups = {"now": [], "out": [], "unknown": []}
    for n in names:
        groups[season_state(notes_by_name.get(n), now.month)].append(n)
    if groups["now"]:                                           # 「いま」に入る鳥が 0 のときは、その欄を出さない
        body += bird_section(h["headings"]["birds"], groups["now"], True)
    if groups["out"]:
        body += bird_section(h["headings"]["birds_out"], groups["out"], True)
    if groups["unknown"]:
        body += bird_section(h["headings"]["birds_unknown"], groups["unknown"], False, note=h["birds_unknown_note"])
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
            commons = meta.get("source") == policy["photos"]["commons"]["source_id"]
            line = h["credit_line"].format(name=n, attribution=meta["attribution"], license=meta["license"])
            if commons:                                          # Commons の写真は出どころも書く(作者・ライセンス・ファイルのページ)
                line += "・" + h["credit_source"].format(source=policy["photos"]["commons"]["source_label"])
            items.append(f'<li>{esc(line)} ({link(meta["photo_page"], h["photo_link_commons"] if commons else h["photo_link"], policy)})</li>')
        body.append(f'<details class="credits"><summary>{esc(h["credits_summary"])}</summary><ul class="note">{"".join(items)}</ul></details>')   # 閉じた状態(open なし)
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
