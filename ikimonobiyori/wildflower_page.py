"""野草・高山植物の写真つきページ(段階41。利用者の決定 2026-11-03)。

- 内容は wildflower.query(guide wildflower)の結果だけ。文(結論の 1 文・注意)は query が作ったものを変えない。足すのは見た目(カード・写真・リンク)だけ。
- 写真は種の代表写真(その場所で撮られたものではない)。保護が必要な種は、場所が分かる写真を避けるため、取得も掲載もしない（名前だけの行）。
  写真が取れない種は「写真なし」と書かず、名前だけの行。手描きの図は使わない。
- 通信しない部分(build)と、キャッシュにない種だけ確認なしで補う部分(承認B。cmd の中の ensure)を分ける。文言は policy の wildflower.page。"""
import os
from datetime import date
from pathlib import Path

from . import guide, guide_page, guide_photos, plan_page, wildflower
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
        cr = plan_page.with_caption_note(meta, h["photo_credit"].format(author=guide_page.short_author(meta, policy), license=meta["license"]), h)
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
    body.append(f'<p class="note">{esc(h["credit"])}</p>')
    title = w["title"].format(place=place, month=r["month"])
    return page_html(title, body, h, pool)


def page_html(title, body, h, pool):
    return ("<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f'<meta http-equiv="Content-Security-Policy" content="{esc(h["csp"])}">\n<title>{esc(title)}</title>\n<style>{guide_page.CSS}\n{pool.css()}</style>\n</head>\n<body>\n<main>\n'
            + "\n".join(body) + "\n</main>\n</body>\n</html>\n")


state_text = guide_page.state_text


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
        cr = plan_page.with_caption_note(meta, h["photo_credit"].format(author=guide_page.short_author(meta, policy), license=meta["license"]), h)
        return f'<li class="card">{pool.tag(meta, got[1], e["name"])}{body_of(e)}<span class="credit">{esc(cr)}</span>{links(e)}</li>'   # 段階81 の追記: 状態は出さない
    kind = r.get("kind")
    if kind == "mountain":
        title = w["title_mountain"].format(place=r["area"])
    elif kind == "zukan":
        title = r["title"]
    elif r.get("focus") == "alpine":
        title = w["title_alpine"]
    else:
        title = w["title_overview"]
    body = [f'<h1>{esc(title)}</h1>', f'<p class="lead">{esc(r["conclusion"])}</p>', f'<p class="meta">{esc(guide_page.created_text(now, h))}</p>']
    if r.get("nav"):
        body.append(r["nav"])
    species_block = ""
    if r.get("focus") == "alpine" and kind not in ("mountain", "zukan"):         # 段階52: 種ごとの花期（wildflower_species）。月の記載がない種に月を足さない
        from . import wildflower_species as WS
        ans = [WS.species_answer(n, month=r["month"]) for n in WS.names()]
        if not any(a["in_season"] for a in ans):
            body.append(f'<p class="lead">{esc(w["species_not_now"].format(month=r["month"]))}</p>')
        rows = "".join(f'<li><b>{esc(a["name"])}</b> {esc("".join(a["bloom_lines"]))}</li>' for a in ans)
        species_block = f'<h2>{esc(w["heading_species"])}</h2><p class="note">{esc(w["species_lead"])}</p><ul class="note">{rows}</ul>'
    species = r["species"]
    if kind in ("mountain", "zukan"):
        groups = [(r["heading"] if kind == "zukan" else w["heading_mountain"], list(species), "cards")]
    else:
        # 段階44: 質問が「高山植物」のとき（focus=alpine）は、高山・亜高山・高原の花に写真の枠を先に割り当て、山麓〜山地の野草は写真なしの短い一覧にする。
        # 「いま」の月に見られる花は、その月の花を先に写真つきで出す（山麓でも写真つきカード）。同じ種は 1 回だけ載せる。
        focus_alpine = r.get("focus") == "alpine"
        order = {"alpine": 0, "subalpine": 1, "lowland": 2}
        rank = lambda e: (order[e["tier"]], -e["flower"]["source_count"], e["name"])
        now_list = sorted((e for e in species if e["active_now"] and not e["protected"]), key=rank)
        taken = {id(e) for e in now_list}
        rest = [e for e in species if id(e) not in taken]
        tiers = {t: [e for e in rest if e["tier"] == t] for t in order}
        groups = []
        if now_list:
            groups.append((w["heading_now_month"].format(month=r["month"]), now_list, "cards"))
        groups.append((w["heading_alpine"], tiers["alpine"], "cards"))
        groups.append((w["heading_subalpine"], tiers["subalpine"], "cards"))
        groups.append((w["heading_lowland_list"] if focus_alpine else w["heading_lowland"], tiers["lowland"], "list" if focus_alpine else "cards"))
        # 写真の枠の割り当て順: いま見られる高山・亜高山 → 高山 → 亜高山 → いま見られる山麓 → (山麓の残りは focus でなければ手元にあるものだけ)
        prio = ([e for e in now_list if e["tier"] != "lowland"] + tiers["alpine"] + tiers["subalpine"] + [e for e in now_list if e["tier"] == "lowland"]
                + ([] if focus_alpine else tiers["lowland"]))
        if focus_alpine:                                      # 段階53: 種ごとの花期を載せる高山植物（wildflower_species）を写真の枠の先頭に（1 ページの上限で名前だけの行に回らないように）
            from . import wildflower_species as WS
            featured = set(WS.names())
            prio = sorted(prio, key=lambda e: e["name"] not in featured)
        for e in prio:
            gotten = photo(e)
            if gotten:
                pool.tag(gotten[0], gotten[1], e["name"])      # 枠を先に確定する（カードの並びとは別）
    done = set()
    for heading, items, mode in groups:
        if not items:
            continue
        cards, bare = [], []
        for e in items:
            got = photo(e) if (mode == "cards" and e["name"] not in done) else None
            done.add(e["name"])
            (cards.append(card(e, got)) if got else bare.append(e))
        if cards:
            body.append(f'<h2>{esc(heading)}</h2><ul class="grid">{"".join(cards)}</ul>')
        high = [e for e in bare if kind not in ("mountain", "zukan") and e["tier"] != "lowland" and mode == "cards"]
        low = [e for e in bare if e not in high]
        if high:
            body.append(f'<h2>{esc(w["heading_bare"])}</h2><ul class="grid">' + "".join(f'<li class="card">{body_of(e)}{links(e)}</li>' for e in high) + "</ul>")
        if low:
            rows = "".join(f'<li>{esc(e["name"])}（{esc(w["bare_sep"].join(w["place_bloom"].format(place=pl["place"], text=pl["bloom_text"]) for pl in e["places"]))}）'
                           + (esc(w["protected_line"]) if e["protected"] else "") + "</li>" for e in low)
            body.append(f'<h2>{esc(heading if mode == "list" else w["heading_lowland_bare"])}</h2><ul class="note">{rows}</ul>')
    if species_block:
        body.append(species_block)
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
    body.append(f'<p class="note">{esc(h["credit"])}</p>')
    return page_html(title, body, h, pool)


def zukan_pages(r, *, policy, photo_for):
    """図鑑の形: 季節（高山は月・旬、山麓〜山地は春夏秋冬）ごとにページを分け、あふれたら同じ季節の次のページに回す。
    → [{file, title, label, entries}]（ファイル名は拡張子なし）。写真は縮小せず、1 ページの埋め込みの上限（photos.html.max_embed_bytes）で分ける。"""
    z = policy["wildflower"]["zukan"]
    names = {v: k for k, v in policy["wildflower"]["tens"].items()}
    groups, order = {}, []

    def add(key, label, fname, e):
        if key not in groups:
            groups[key] = {"label": label, "base": fname, "entries": []}
            order.append(key)
        groups[key]["entries"].append(e)
    seasons = z["seasons"]
    for e in r["species"]:
        bloom = e["places"][0]["bloom"]
        m, t = wildflower.parse_bloom(bloom)[0]
        if e["section"] == "alpine":
            prec = any(c in str(bloom) for c in policy["wildflower"]["tens"])
            label = f"{m}月" + (names[t] if prec else "")
            key = ("alpine", m, t if prec else -1)
            add(key, z["alpine_label"] + "・" + label, z["files"]["alpine"].format(key=f"{m:02d}" + (str(t) if prec else "")), e)
        else:
            season = next(k for k, ms in seasons.items() if m in ms)
            idx = list(seasons).index(season)
            add(("lowland", idx), z["lowland_label"] + "・" + season, z["files"]["lowland"].format(key=str(idx + 1)), e)
    order.sort(key=lambda k: (0 if k[0] == "alpine" else 1, k[1:]))
    budget = policy["photos"]["html"]["max_embed_bytes"]["value"]
    pages = []
    for key in order:
        g = groups[key]
        cur, pool, n = [], PhotoPool(budget), 1

        def flush(last=False):
            nonlocal cur, pool, n
            if cur or last:
                pages.append({"file": g["base"] + ("" if n == 1 else f"-{n}"), "label": g["label"], "part": n, "entries": cur, "group": key})
            cur, pool, n = [], PhotoPool(budget), n + 1
        for e in g["entries"]:
            got = None if e["protected"] else photo_for(e["name"])
            if got and not pool.fits(got[1]) and cur:
                flush()
            if got:
                pool.tag(got[0], got[1], e["name"])
            cur.append(e)
        flush(last=True)
    return pages


def zukan_nav(pages, here, policy):
    w = policy["wildflower"]["page"]
    firsts, seen = [], set()
    for pg in pages:
        if pg["group"] not in seen:
            seen.add(pg["group"])
            firsts.append(pg)
    items = []
    for pg in firsts:
        label = esc(pg["label"])
        if pg["group"] == here["group"]:
            parts = [x for x in pages if x["group"] == pg["group"]]
            sub = "".join(f' <a href="{esc(x["file"])}.html">{x["part"]}</a>' if x is not here else f" <b>{x['part']}</b>" for x in parts) if len(parts) > 1 else ""
            items.append(f"<li><b>{label}</b>{esc(w['zukan_here'])}{sub}</li>")
        else:
            items.append(f'<li><a href="{esc(pg["file"])}.html">{label}</a></li>')
    return f'<nav><p class="note">{esc(w["zukan_nav"])}</p><ul class="note">{"".join(items)}</ul></nav>'


def build_zukan(r, *, policy, now, photo_for):
    """→ [(ファイル名 .html, HTML)]。各ページの先頭に、ほかの季節のページへの案内を置く。"""
    w = policy["wildflower"]["page"]
    pages = zukan_pages(r, policy=policy, photo_for=photo_for)
    out = []
    for pg in pages:
        label = pg["label"] if pg["part"] == 1 and sum(1 for x in pages if x["group"] == pg["group"]) == 1 else w["zukan_part"].format(label=pg["label"], n=pg["part"])
        rr = dict(r, kind="zukan", species=pg["entries"], title=w["title_zukan"].format(label=label), heading=pg["label"], nav=zukan_nav(pages, pg, policy),
                  conclusion=w["zukan_lead"].format(label=pg["label"], count=len(pg["entries"])))
        out.append((pg["file"] + ".html", build_overview(rr, policy=policy, now=now, photo_for=photo_for)))
    return out


def overview_photo_names(r, focus=None):
    """写真を補う種（保護が必要な種を除く）: 高山・亜高山・高原の花と、いまの月に見られる花。質問が高山植物のとき（focus=alpine）は、
    それ以外の山麓〜山地の野草には補わない。focus でないときも、手元にある写真だけは使う。"""
    return [e["name"] for e in r["species"] if not e["protected"] and (e["tier"] != "lowland" or e["active_now"])]


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


def page_mode(a):
    """質問の型 → ページの切り方。zukan: 全部を図鑑の形で（季節ごとに複数ページ）/ now: 月で選ぶ（山・山域の指定なし）または月つきの山 /
    mountain: 山・山域で選ぶ（月の指定なし。見ごろの早い順）。"""
    if getattr(a, "zukan", False):
        return "zukan"
    if not a.site and not a.area:
        return "now"
    if not a.month and not a.date:
        return "mountain"
    return "place_month"


def page_cmd(a, now=None):
    import sys
    policy = guide.load_policy()
    now = now or guide.clock_now()
    on = date.fromisoformat(a.date) if a.date else now.date()
    mode = page_mode(a)
    try:
        if mode == "zukan":
            r = wildflower.overview(month=a.month, date_=a.date, today=on)
        elif mode == "now":
            r = wildflower.overview(month=a.month, date_=a.date, today=on)
            if getattr(a, "alpine", False):                # 質問に「高山植物」とあるとき: 高山・亜高山・高原の花を主役にする（段階44）
                r["focus"] = "alpine"
        elif mode == "mountain":
            r = wildflower.overview(today=on, area=a.area, site=a.site)
        else:
            r = wildflower.query(site=a.site, area=a.area, month=a.month, date_=a.date, today=on, with_photo=False)
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        return 2
    if getattr(a, "ensure_photos", True):
        if mode in ("zukan", "mountain"):
            names = [e["name"] for e in r["species"] if not e["protected"]]
        elif mode == "now":
            names = overview_photo_names(r)
        else:
            names = photo_names(r) if r["flowers"] else []
        if names:
            guide_photos.ensure_for_page(names, "野草", policy)
    table = guide_photos.load_table()

    def photo_for(name):
        row = table.get(name)
        return guide_photos.load_photo(row["taxon_id"]) if row else None
    fname = policy["wildflower"]["page"]["file"]
    if mode == "zukan":
        outdir = Path(a.out) if a.out else guide_photos.page_dir()
        if not guide_page.out_path_ok(outdir / "x"):
            print("書き込み先は IKIMONOBIYORI_DATA_DIR の下かリポジトリの外だけです", file=sys.stderr)
            return 2
        pages = build_zukan(r, policy=policy, now=now, photo_for=photo_for)
        outs = [(outdir / f, h) for f, h in pages]
    else:
        out = Path(a.out) if a.out else guide_photos.page_dir() / fname
        if not guide_page.out_path_ok(out):
            print("書き込み先は IKIMONOBIYORI_DATA_DIR の下かリポジトリの外だけです", file=sys.stderr)
            return 2
        builder = build if mode == "place_month" else build_overview
        outs = [(out, builder(r, policy=policy, now=now, photo_for=photo_for))]
    for _o, page in outs:
        bad = self_check(page)
        if bad:
            print("ページの文が検査に通りません: " + ", ".join(f"{e['detail']}" for e in bad), file=sys.stderr)
            return 2
    if mode == "zukan":                                    # 前の実行の古いページ（分け方が変わると残る）を消す
        for old in outdir.glob(policy["wildflower"]["zukan"]["clean_glob"]):
            old.unlink()
    for o, page in outs:
        o.parent.mkdir(parents=True, exist_ok=True)
        with open(o, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(page)
        print(str(o.resolve()))
    if a.open:
        first = outs[0][0].resolve()
        if hasattr(os, "startfile"):
            os.startfile(str(first))
        else:
            import webbrowser
            webbrowser.open(first.as_uri())
    return 0
