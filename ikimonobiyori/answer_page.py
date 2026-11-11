"""段階64 第4部 3: 答えの型(時期と場所・町の名前・知識)ごとの写真つきの単独 HTML ページ。通信しない。

- 材料は直前の `ask answer` の答えの本文と、答えの記録(種・名所)。新しい事実を足さない。文は書き換えない。
- 写真は種の代表写真だけ(guide_photos のキャッシュにあるもの)。季節で絞った質問(「冬から春の桜」)は、その季節の種だけ。
- 安全: すべての文字を html.escape。JavaScript なし。CSP。写真は data URI。リンクは http・https だけ。手書きの図を使わない。
語は data/ask/season_place.yaml の page。"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .park_page import CSS, esc, link, safe_url
from .paths import data_path
from .photo_pool import PhotoPool

URL_RE = re.compile(r"https?://\S+")


def cfg():
    from . import season_place as SP
    return SP.cfg()["page"]


def last_path(env=None):
    return data_path(cfg()["last_file"], env)


def remember(res, now, env=None):
    """ask answer の答え(計画の型以外)を、写真つきページのために覚える(データ置き場。有効期間は page.valid_hours)。"""
    if res.get("route") not in cfg()["routes"]:
        return
    p = last_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema": "ikimonobiyori-last-answer/1", "saved_at": now.isoformat(), "route": res["route"], "question": res.get("question"),
           "workdir": res.get("workdir"), "text": res.get("text"), "season_place": res.get("season_place"), "town": res.get("town")}
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def load_last(now, env=None):
    try:
        doc = json.loads(last_path(env).read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(doc["saved_at"])
    except (OSError, ValueError, KeyError):
        return None
    if now < saved or now - saved > timedelta(hours=cfg()["valid_hours"]):
        return None
    return doc


def species_for(doc):
    """ページに写真を載せる種(答えの型ごと。最大 page.max_species)。季節で絞った知識の質問は、その季節の種だけ。"""
    return species_all(doc)[: cfg()["max_species"]]


def species_over(doc):
    """上限(page.max_species)を超えて載せなかった種。"""
    return species_all(doc)[cfg()["max_species"]:]


def species_all(doc):
    from . import season_place as SP
    q = doc.get("question") or ""
    if doc.get("species") is not None:                    # 段階81 第2部: ガイドの答え(新しい形)は、文に出る種を呼び出し側が決める
        return list(doc["species"])
    if doc.get("route") in ("knowledge", "chat"):
        names = SP.season_species_names(q) or [x["name"] for x in SP.resolve_all(q)]
    elif doc.get("route") == "season_place":
        names = list((doc.get("season_place") or {}).get("species") or [])
    else:
        names = []
    return list(names)


def representative(name):
    """段階81 の追記: 総称の種(ツツジ・バラなど)の代表の種・品種 {name, label, reason}。なければ None。"""
    return (cfg().get("representatives") or {}).get(name)


def photo_with_representative(name, photo_for):
    """→ (写真 (メタ, バイト列) か None, 代表 {name, label} か None)。その名前の写真がなく、代表の写真があるときだけ代表。"""
    got = photo_for(name)
    if got:
        return got, None
    r = representative(name)
    if r:
        got = photo_for(r["name"])
        if got:
            return got, r
    return None, None


def photo_card(name, got, rep, img, photo_credit, say):
    """写真のカード: 見出しは種の名前、説明は(代表なら「写真は○○」)撮影者・ライセンスと元のページのリンク。状態(開花など)は出さない(段階81 の追記)。"""
    from . import guide
    c = cfg()
    meta = got[0]
    commons = meta.get("source") == guide.load_policy()["photos"]["commons"]["source_id"]
    cap = esc(photo_credit(meta))
    if rep:
        cap = esc(c["representative_caption"].format(label=rep["label"])) + "。" + cap
    if meta.get("photo_page"):
        cap += "(" + link(meta["photo_page"], c["photo_link_commons"] if commons else c["photo_link"]) + ")"
    return f'<li class="bird">{img}<h3>{say(name)}</h3><p class="credit">{cap}</p></li>'


def title_of(doc):
    c = cfg()
    sp = species_for(doc)
    fmt = c["title"].get(doc.get("route"))
    if not fmt or (("{species}" in fmt) and not sp):
        return c["title_fallback"].format(question=(doc.get("question") or "").strip())
    return fmt.format(species="・".join(sp), town=(doc.get("town") or {}).get("town") or "")


def body_html(text, say, linkify=False):
    """答えの本文 → HTML(見出し・箇条・段落・リンク)。文はそのまま(書き換えない)。"""
    c = cfg()
    out, items = [], []

    def flush():
        if items:
            out.append('<ul class="park-facts">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            items.clear()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        m = re.fullmatch(r"\*\*(.+?)\*\*(.*)", line)
        if m:
            flush()
            out.append(f"<h3>{say(m.group(1) + m.group(2))}</h3>")
        elif line in c["section_words"] or (len(line) <= 12 and not re.search(r"[。:：、(（]", line) and not URL_RE.match(line)):
            flush()
            out.append(f"<h2>{say(line)}</h2>")
        elif URL_RE.fullmatch(line):
            if safe_url(line):
                items.append(link(line, line))
        elif line.startswith(("・", "- ")):
            items.append(_linkify(say(line.lstrip("・- ").strip())) if linkify else say(line.lstrip("・- ").strip()))
        elif line.startswith("|"):
            if not re.fullmatch(r"\|[-|\s]+\|", line):
                items.append(say(" ".join(x.strip() for x in line.strip("|").split("|"))))
        else:
            flush()
            out.append(f"<p>{say(line)}</p>")
    flush()
    return "\n".join(out)


def _linkify(escaped):
    from .guide_answer_page import linkify
    return linkify(escaped)


_HEAD = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def md_blocks(text):
    """段階81 の続き 2: Markdown の答えの文 → 塊の一覧 [{kind: h2|h3|p|ul, texts: [文]}]。
    「## 見出し」は見出し、「- 」「・」は箇条、それ以外の行は段落。太字の印(**)は外す(文は書き換えない)。"""
    c = cfg()
    out, items = [], []

    def flush():
        if items:
            out.append({"kind": "ul", "texts": list(items)})
            items.clear()
    for raw in (text or "").splitlines():
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", raw.strip())
        if not line:
            flush()
            continue
        m = _HEAD.match(line)
        if m:
            flush()
            out.append({"kind": "h2" if len(m.group(1)) <= 2 else "h3", "texts": [m.group(2)]})
        elif line in c["section_words"]:
            flush()
            out.append({"kind": "h2", "texts": [line]})
        elif URL_RE.fullmatch(line):
            if safe_url(line):
                items.append(line)
        elif line.startswith(("・", "- ", "* ")):
            items.append(line.lstrip("・-* ").strip())
        else:
            flush()
            out.append({"kind": "p", "texts": [line]})
    flush()
    return out


def _block_html(b, say):
    if b["kind"] == "ul":
        return '<ul class="park-facts">' + "".join(f"<li>{_linkify(say(t))}</li>" for t in b["texts"]) + "</ul>"
    t = b["texts"][0]
    return f"<{b['kind']}>{_linkify(say(t)) if b['kind'] == 'p' else say(t)}</{b['kind']}>"


def build(doc, *, photo_for, photo_credit, csp, max_bytes, linkify=False):
    """→ (HTML, 検査用の文の一覧, 載せた種 [(種名, 写真あり)])。photo_for(和名) → (メタ, バイト列) か None。
    doc["markdown"] が真(ガイドの答え。段階81 の続き)なら、見出し・箇条を Markdown として読み、
    写真は種の名前が出る段落のすぐ後ろに置く(doc["species_words"] {種名: [文の中の語]})。どの段落にもない種の写真はまとめて本文の前。"""
    if doc.get("markdown"):
        return _build_md(doc, photo_for=photo_for, photo_credit=photo_credit, csp=csp, max_bytes=max_bytes)
    c = cfg()
    lines = []

    def say(s):
        lines.append(s)
        return esc(s)
    title = title_of(doc)
    body = [f"<h1>{say(title)}</h1>"]
    pool = PhotoPool(max_bytes)
    shown, cards, nophoto, over = [], [], [], list(species_over(doc))
    for name in species_for(doc):
        got, rep = photo_with_representative(name, photo_for)
        img = pool.tag(got[0], got[1], name) if got else None
        if img is None:                                        # 写真が取れなかった種は名前だけの行(手描きの図にしない)。埋め込む大きさの上限で載せなかった種は上限の行
            (over if got else nophoto).append(name)
            shown.append((name, False))
            continue
        cards.append(photo_card(name, got, rep, img, photo_credit, say))
        shown.append((name, True))
    text_html = body_html(doc.get("text") or "", say, linkify=linkify)
    if cards or nophoto or over:                               # 写真は本文の前(本文の最後は出典)
        body.append(f"<h2>{say(c['photo_heading'])}</h2>")
        body.append(f'<p class="note">{say(c["photo_note"])}</p>')
        if cards:
            body.append('<ul class="birds">' + "".join(cards) + "</ul>")
        if over:
            body.append(f'<p class="note">{say(c["over_limit_names"].format(names="・".join(over)))}</p>')
        if nophoto:
            body.append(f'<p class="note">{say(c["no_photo_names"].format(names="・".join(nophoto)))}</p>')
    body.append(text_html)
    body.append(f'<p class="note">{say(c["footer"])}</p>')
    page = ("<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f'<meta http-equiv="Content-Security-Policy" content="{esc(csp)}">\n'
            f"<title>{esc(title)}</title>\n<style>{CSS}\n{pool.css()}</style>\n</head>\n<body>\n<main>\n"
            + "\n".join(body) + "\n</main>\n</body>\n</html>\n")
    return page, lines, shown


def _cards_for(names, photo_for, photo_credit, pool, say, shown, nophoto, over):
    cards = []
    for name in names:
        got, rep = photo_with_representative(name, photo_for)
        img = pool.tag(got[0], got[1], name) if got else None
        if img is None:
            (over if got else nophoto).append(name)
            shown.append((name, False))
            continue
        cards.append(photo_card(name, got, rep, img, photo_credit, say))
        shown.append((name, True))
    return cards


def _build_md(doc, *, photo_for, photo_credit, csp, max_bytes):
    c = cfg()
    lines = []

    def say(s):
        lines.append(s)
        return esc(s)
    title = doc.get("title") or title_of(doc)
    names = species_for(doc)
    words = doc.get("species_words") or {}
    stops = set(doc.get("stop_headings") or ())
    blocks = md_blocks(doc.get("text") or "")
    placed, at = set(), {}                                      # 種 → その名前が最初に出る塊の番号(出典などの見出しより前だけ)
    for i, b in enumerate(blocks):
        if b["kind"] in ("h2", "h3") and b["texts"][0] in stops:
            break
        if b["kind"] in ("h2", "h3"):
            continue
        blob = "".join(b["texts"])
        for n in names:
            if n not in placed and any(w and w in blob for w in (words.get(n) or [n])):
                placed.add(n)
                at.setdefault(i, []).append(n)
    rest = [n for n in names if n not in placed]
    pool = PhotoPool(max_bytes)
    shown, nophoto, over = [], [], list(species_over(doc))
    body = [f"<h1>{say(title)}</h1>"]
    top_cards = _cards_for(rest, photo_for, photo_credit, pool, say, shown, nophoto, over)
    inline = {i: _cards_for(ns, photo_for, photo_credit, pool, say, shown, nophoto, over) for i, ns in at.items()}
    if top_cards or any(inline.values()) or nophoto or over:
        body.append(f'<p class="note">{say(c["photo_note"])}</p>')
    if top_cards:
        body.append(f"<h2>{say(c['photo_heading'])}</h2>")
        body.append('<ul class="birds">' + "".join(top_cards) + "</ul>")
    if over:
        body.append(f'<p class="note">{say(c["over_limit_names"].format(names="・".join(over)))}</p>')
    if nophoto:
        body.append(f'<p class="note">{say(c["no_photo_names"].format(names="・".join(nophoto)))}</p>')
    for i, b in enumerate(blocks):
        body.append(_block_html(b, say))
        if inline.get(i):
            body.append('<ul class="birds">' + "".join(inline[i]) + "</ul>")
    body.append(f'<p class="note">{say(c["footer"])}</p>')
    order = {n: k for k, n in enumerate(names)}
    shown.sort(key=lambda x: order.get(x[0], len(order)))
    return _page(title, body, csp, pool), lines, shown


def _page(title, body, csp, pool):
    return ("<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f'<meta http-equiv="Content-Security-Policy" content="{esc(csp)}">\n'
            f"<title>{esc(title)}</title>\n<style>{CSS}\n{pool.css()}</style>\n</head>\n<body>\n<main>\n"
            + "\n".join(body) + "\n</main>\n</body>\n</html>\n")


def make(doc, now, env=None):
    """直前の答えのページを作ってデータ置き場に書く。→ {path, line, species}"""
    from . import ask, guide, guide_page, guide_photos, plan_page
    pol = guide.load_policy()
    gp = pol["photos"]
    pp = ask.load_policy()["plan_page"]
    table = guide_photos.load_table(env) if env else guide_photos.load_table()
    alias = pp.get("photo_aliases") or {}

    def photo_for(name):
        row = table.get(alias.get(name, name)) or table.get(name)
        if not row:
            return None
        return guide_photos.load_photo(row["taxon_id"], env) if env else guide_photos.load_photo(row["taxon_id"])

    def credit(meta):
        return plan_page.author_credit(meta, gp)                 # 状態(開花など)は出さない(段階81 の追記)
    mx = pp["max_embed_bytes"]
    html_text, _lines, shown = build(doc, photo_for=photo_for, photo_credit=credit, csp=pp["csp"], max_bytes=mx["value"] if isinstance(mx, dict) else mx)
    out = (guide_photos.page_dir(env) if env else guide_photos.page_dir()) / cfg()["file"].format(kind=doc.get("route"), date=now.date().isoformat())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8", newline="\n")
    path = str(Path(out).resolve())
    return {"path": path, "line": pp["reply_line"].format(path=path), "species": [{"name": n, "photo": x} for n, x in shown]}
