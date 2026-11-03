"""野草・高山植物の写真つきページ(段階41。利用者の決定 2026-11-03)。

- 内容は wildflower.query(guide wildflower)の結果だけ。文(結論の 1 文・注意)は query が作ったものを変えない。足すのは見た目(カード・写真・リンク)だけ。
- 写真は種の代表写真(その場所で撮られたものではない)。保護が必要な種は、場所が分かる写真を避けるため、取得も掲載もしない（名前だけの行）。
  写真が取れない種は「写真なし」と書かず、名前だけの行。手描きの図は使わない。
- 通信しない部分(build)と、キャッシュにない種だけ確認なしで補う部分(承認B。cmd の中の ensure)を分ける。文言は policy の wildflower.page。"""
import os
from datetime import date
from pathlib import Path

from . import guide, guide_page, guide_photos, wildflower
from .guide_page import esc, link
from .photo_pool import PhotoPool


def photo_names(r):
    return [f["name"] for f in r["flowers"] if not f["protected"]]


def build(r, *, policy, now, photo_for):
    """query の結果 → 単独の HTML。photo_for(和名) → (メタデータ, バイト列) か None。"""
    h = policy["photos"]["html"]
    w = policy["wildflower"]["page"]
    pool = PhotoPool(h["max_embed_bytes"]["value"])
    used = {}

    def photo(f):
        n = f["name"]
        if f["protected"]:
            return None
        if n not in used:
            got = photo_for(n)
            used[n] = got if got and pool.fits(got[1]) else None
        return used[n]

    place = (r["site"]["name"] + "（" + r["area"] + "）") if r["site"] else r["area"]
    body = [f'<h1>{esc(w["title"].format(place=place, month=r["month"]))}</h1>', f'<p class="lead">{esc(r.get("conclusion") or r["text"])}</p>',
            f'<p class="meta">{esc(guide_page.created_text(now, h))}</p>']
    cards, bare = [], []
    for f in r["flowers"]:
        got = photo(f)
        if not got:
            bare.append(f)
            continue
        cards.append((f, got))

    def facts(f):
        out = [w["bloom"].format(text=wildflower_bloom_text(f))]
        e = f["elevation_m"]
        if e and e[0] is not None:
            out.append(w["elev_lo"].format(lo=e[0]) if e[1] is None else w["elev"].format(lo=e[0], hi=e[1]))
        if f["tip"]:
            out.append(f["tip"])
        out.append(f'{f["grade_label"]}（{w["sources_n"].format(n=f["source_count"])}）')
        return out

    def links(f):
        li = "".join(f"<li>{link(s['url'], s['publisher'], policy)}（{esc(w['read_on'].format(d=s['read_on']))}）</li>" for s in f["sources"])
        return f'<ul class="links">{li}</ul>'

    def card(f, got):
        meta = got[0]
        cr = h["photo_credit"].format(author=guide_page.short_author(meta, policy), license=meta["license"])
        return (f'<li class="card">{pool.tag(meta, got[1], f["name"])}<h3>{esc(f["name"])}</h3>'
                + f'<ul class="facts">{"".join(f"<li>{esc(x)}</li>" for x in facts(f))}</ul>'
                + (f'<p class="note">{esc(w["caution"].format(text=f["caution"]))}</p>' if f["caution"] else "")
                + (f'<p class="note">{esc(f["note"])}</p>' if f["note"] else "")
                + f'<span class="credit">{esc(cr)}</span>' + links(f) + "</li>")
    if cards:
        body.append(f'<h2>{esc(w["heading_now"])}</h2><ul class="grid">{"".join(card(f, g) for f, g in cards)}</ul>')
    if bare:
        body.append(f'<h2>{esc(w["heading_bare"])}</h2><ul class="grid">'
                    + "".join(f'<li class="card"><h3>{esc(f["name"])}</h3><ul class="facts">{"".join(f"<li>{esc(x)}</li>" for x in facts(f))}</ul>'
                              + (f'<p class="note">{esc(w["caution"].format(text=f["caution"]))}</p>' if f["caution"] else "")
                              + (f'<p class="note">{esc(w["protected_line"])}</p>' if f["protected"] else "") + links(f) + "</li>" for f in bare) + "</ul>")
    if not r["flowers"]:
        body.append(f'<p class="note">{esc(r["text"])}</p>')
    if r["upcoming"]:
        body.append(f'<h2>{esc(w["heading_next"])}</h2><p class="note">{esc(h["others_sep"].join(u["name"] for u in r["upcoming"]))}</p>')
    body.append(f'<h2>{esc(w["heading_notes"])}</h2><ul>{"".join(f"<li>{esc(c)}</li>" for c in r["caveats"] + [r["season_note"]])}</ul>')
    shown = {n: v for n, v in used.items() if v}
    body.append(f'<p class="note">{esc(h["photo_note"])}</p>')
    if shown:
        items = []
        for n in sorted(shown):
            meta = shown[n][0]
            commons = meta.get("source") == policy["photos"]["commons"]["source_id"]
            items.append(f'<li>{esc(h["credit_line"].format(name=n, attribution=meta["attribution"], license=meta["license"]))} '
                         f'({link(meta["photo_page"], h["photo_link_commons"] if commons else h["photo_link"], policy)})</li>')
        body.append(f'<details class="credits"><summary>{esc(h["credits_summary"])}</summary><ul class="note">{"".join(items)}</ul></details>')
    body.append(f'<p class="note">{esc(h["credit"])}</p><p class="lead">{esc(w["next_question"])}</p>')
    title = w["title"].format(place=place, month=r["month"])
    return page_html(title, body, h, pool)


def page_html(title, body, h, pool):
    return ("<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f'<meta http-equiv="Content-Security-Policy" content="{esc(h["csp"])}">\n<title>{esc(title)}</title>\n<style>{guide_page.CSS}\n{pool.css()}</style>\n</head>\n<body>\n<main>\n'
            + "\n".join(body) + "\n</main>\n</body>\n</html>\n")


def build_overview(r, *, policy, now, photo_for):
    """山域も地点も指定がない質問のページ: 先頭に結論、データのある地点・山域の例年の見ごろを種ごとのカードで並べ、末尾に好みの質問を 1 つ置く。"""
    h = policy["photos"]["html"]
    w = policy["wildflower"]["page"]
    pool = PhotoPool(h["max_embed_bytes"]["value"])
    used = {}

    def photo(e):
        n = e["name"]
        if e["protected"]:
            return None
        if n not in used:
            got = photo_for(n)
            used[n] = got if got and pool.fits(got[1]) else None
        return used[n]

    def facts(e):
        f = e["flower"]
        out = [w["place_bloom"].format(place=pl["place"], text=pl["bloom_text"]) for pl in e["places"]]
        el = f["elevation_m"]
        if el and el[0] is not None:
            out.append(w["elev_lo"].format(lo=el[0]) if el[1] is None else w["elev"].format(lo=el[0], hi=el[1]))
        if f["tip"]:
            out.append(f["tip"])
        out.append(f'{f["grade_label"]}（{w["sources_n"].format(n=f["source_count"])}）')
        return out

    def links(e):
        li = "".join(f"<li>{link(s['url'], s['publisher'], policy)}（{esc(w['read_on'].format(d=s['read_on']))}）</li>" for s in e["sources"])
        return f'<ul class="links">{li}</ul>'

    def body_of(e):
        f = e["flower"]
        return (f'<h3>{esc(e["name"])}</h3><ul class="facts">{"".join(f"<li>{esc(x)}</li>" for x in facts(e))}</ul>'
                + (f'<p class="note">{esc(w["caution"].format(text=f["caution"]))}</p>' if f["caution"] else "")
                + (f'<p class="note">{esc(w["protected_line"])}</p>' if e["protected"] else ""))

    def card(e, got):
        meta = got[0]
        cr = h["photo_credit"].format(author=guide_page.short_author(meta, policy), license=meta["license"])
        return f'<li class="card">{pool.tag(meta, got[1], e["name"])}{body_of(e)}<span class="credit">{esc(cr)}</span>{links(e)}</li>'
    title = w["title_overview"]
    body = [f'<h1>{esc(title)}</h1>', f'<p class="lead">{esc(r["conclusion"])}</p>', f'<p class="meta">{esc(guide_page.created_text(now, h))}</p>']
    for section, heading in (("alpine", w["heading_alpine"]), ("lowland", w["heading_lowland"])):
        cards, bare = [], []
        for e in (x for x in r["species"] if x["section"] == section):
            got = photo(e)
            (cards.append(card(e, got)) if got else bare.append(e))
        if cards:
            body.append(f'<h2>{esc(heading)}</h2><ul class="grid">{"".join(cards)}</ul>')
        if bare and section == "alpine":
            body.append(f'<h2>{esc(w["heading_bare"])}</h2><ul class="grid">' + "".join(f'<li class="card">{body_of(e)}{links(e)}</li>' for e in bare) + "</ul>")
        elif bare:
            rows = "".join(f'<li>{esc(e["name"])}（{esc(w["bare_sep"].join(w["place_bloom"].format(place=pl["place"], text=pl["bloom_text"]) for pl in e["places"]))}）'
                           + (esc(w["protected_line"]) if e["protected"] else "") + "</li>" for e in bare)
            body.append(f'<h2>{esc(w["heading_lowland_bare"])}</h2><ul class="note">{rows}</ul>')
    body.append(f'<h2>{esc(w["heading_notes"])}</h2><ul>{"".join(f"<li>{esc(c)}</li>" for c in r["caveats"] + [r["season_note"]])}</ul>')
    shown = {n: v for n, v in used.items() if v}
    body.append(f'<p class="note">{esc(h["photo_note"])}</p>')
    if shown:
        items = []
        for n in sorted(shown):
            meta = shown[n][0]
            commons = meta.get("source") == policy["photos"]["commons"]["source_id"]
            items.append(f'<li>{esc(h["credit_line"].format(name=n, attribution=meta["attribution"], license=meta["license"]))} '
                         f'({link(meta["photo_page"], h["photo_link_commons"] if commons else h["photo_link"], policy)})</li>')
        body.append(f'<details class="credits"><summary>{esc(h["credits_summary"])}</summary><ul class="note">{"".join(items)}</ul></details>')
    body.append(f'<p class="note">{esc(h["credit"])}</p><p class="lead">{esc(w["next_question_overview"])}</p>')
    return page_html(title, body, h, pool)


def overview_photo_names(r):
    """写真を補う種: 高山の花と、いまの月に見られる山麓の野草（保護が必要な種を除く）。ほかは手元にあるものだけ使う。"""
    return [e["name"] for e in r["species"] if not e["protected"] and (e["section"] == "alpine" or e["active_now"])]


def self_check(html_text):
    """ページの文を、答えと同じ作業・開発の言葉の検査（generic_check）に通す。候補の数の決まりは当てない。→ 落ちた項目のリスト"""
    import re
    from . import ask_verify
    plain = re.sub(r"<style.*?</style>|<[^>]+>", "\n", html_text, flags=re.S)
    res = ask_verify.generic_check(plain)
    return [e for e in res["errors"] if e["code"] not in ("ask_back_only", "too_few_candidates")]


def wildflower_bloom_text(f):
    (m1, t1), (m2, t2) = wildflower.parse_bloom(f["bloom"])
    names = {v: k for k, v in guide.load_policy()["wildflower"]["tens"].items()}
    prec = f["bloom_precision"] == "decade"
    a = f"{m1}月" + (names[t1] if prec else "")
    b = f"{m2}月" + (names[t2] if prec else "")
    return a if a == b else f"{a}〜{b}"


def page_cmd(a, now=None):
    policy = guide.load_policy()
    ph = policy["photos"]
    now = now or guide.clock_now()
    on = date.fromisoformat(a.date) if a.date else now.date()
    overview = not a.site and not a.area
    try:
        r = (wildflower.overview(month=a.month, date_=a.date, today=on) if overview
             else wildflower.query(site=a.site, area=a.area, month=a.month, date_=a.date, today=on, with_photo=False))
    except ValueError as ex:
        print(str(ex), file=__import__("sys").stderr)
        return 2
    if getattr(a, "ensure_photos", True) and (overview or r["flowers"]):
        guide_photos.ensure_for_page(overview_photo_names(r) if overview else photo_names(r), "野草", policy)
    table = guide_photos.load_table()

    def photo_for(name):
        row = table.get(name)
        return guide_photos.load_photo(row["taxon_id"]) if row else None
    out = Path(a.out) if a.out else guide_photos.page_dir() / policy["wildflower"]["page"]["file"]
    if not guide_page.out_path_ok(out):
        print("書き込み先は IKIMONOBIYORI_DATA_DIR の下かリポジトリの外だけです", file=__import__("sys").stderr)
        return 2
    page = (build_overview if overview else build)(r, policy=policy, now=now, photo_for=photo_for)
    bad = self_check(page)
    if bad:
        print("ページの文が検査に通りません: " + ", ".join(f"{e['detail']}" for e in bad), file=__import__("sys").stderr)
        return 2
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
