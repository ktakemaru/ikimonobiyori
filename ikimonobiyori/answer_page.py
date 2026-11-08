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
    """ページに写真を載せる種(答えの型ごと)。季節で絞った知識の質問は、その季節の種だけ。"""
    from . import season_place as SP
    q = doc.get("question") or ""
    if doc.get("route") in ("knowledge", "chat"):
        names = SP.season_species_names(q) or [x["name"] for x in SP.resolve_all(q)]
    elif doc.get("route") == "season_place":
        names = list((doc.get("season_place") or {}).get("species") or [])
    else:
        names = []
    return names[: cfg()["max_species"]]


def title_of(doc):
    c = cfg()
    sp = species_for(doc)
    fmt = c["title"].get(doc.get("route"))
    if not fmt or (("{species}" in fmt) and not sp):
        return c["title_fallback"].format(question=(doc.get("question") or "").strip())
    return fmt.format(species="・".join(sp), town=(doc.get("town") or {}).get("town") or "")


def body_html(text, say):
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
            items.append(say(line.lstrip("・- ").strip()))
        elif line.startswith("|"):
            if not re.fullmatch(r"\|[-|\s]+\|", line):
                items.append(say(" ".join(x.strip() for x in line.strip("|").split("|"))))
        else:
            flush()
            out.append(f"<p>{say(line)}</p>")
    flush()
    return "\n".join(out)


def build(doc, *, photo_for, photo_credit, csp, max_bytes):
    """→ (HTML, 検査用の文の一覧, 載せた種 [(種名, 写真あり)])。photo_for(和名) → (メタ, バイト列) か None。"""
    c = cfg()
    lines = []

    def say(s):
        lines.append(s)
        return esc(s)
    title = title_of(doc)
    body = [f"<h1>{say(title)}</h1>"]
    pool = PhotoPool(max_bytes)
    shown, cards, nophoto = [], [], []
    for name in species_for(doc):
        got = photo_for(name)
        img = pool.tag(got[0], got[1], name) if got else None
        if img is None:                                        # 写真が取れなかった種は名前だけの行(手描きの図にしない)
            nophoto.append(name)
            shown.append((name, False))
            continue
        cards.append(f'<li class="bird">{img}<h3>{say(name)}</h3><p class="credit">{esc(photo_credit(got[0]))}</p></li>')
        shown.append((name, True))
    text_html = body_html(doc.get("text") or "", say)
    if cards or nophoto:                                       # 写真は本文の前(本文の最後は出典)
        body.append(f"<h2>{say(c['photo_heading'])}</h2>")
        body.append(f'<p class="note">{say(c["photo_note"])}</p>')
        if cards:
            body.append('<ul class="birds">' + "".join(cards) + "</ul>")
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
        return plan_page.author_credit(meta, gp, guide_page.state_text(meta, pol) if meta.get("rule") else None)
    mx = pp["max_embed_bytes"]
    html_text, _lines, shown = build(doc, photo_for=photo_for, photo_credit=credit, csp=pp["csp"], max_bytes=mx["value"] if isinstance(mx, dict) else mx)
    out = (guide_photos.page_dir(env) if env else guide_photos.page_dir()) / cfg()["file"].format(kind=doc.get("route"), date=now.date().isoformat())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8", newline="\n")
    path = str(Path(out).resolve())
    return {"path": path, "line": pp["reply_line"].format(path=path), "species": [{"name": n, "photo": x} for n, x in shown]}
