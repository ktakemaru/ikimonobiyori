"""段階81 第2部: 新しい形(ガイド)の答えの写真つきの単独 HTML ページ。

- 材料は直前の `ask verify --brief` が合格させた最終の文(logs/last_guide_answer.json)と、その資料(ask brief)だけ。
  今までの形の計画を作り直さない(答えと違う場所・順・現況がページに出ないように)。文は書き換えない(太字の印だけ外す)。
- 写真は、最終の文に出る名所の種(資料の作業フォルダの facts.json の樹種・花の種類・公園の鳥)と、文に名前の出る種だけ。
  その場所で撮られた写真ではない(注記を出す)。撮影者・ライセンスは answer_page と同じ表示。
- 写真の取得は確認なしで行う(承認B。上限・間隔・許可ホストは guide_photos の方針のまま)。テスト中・許可されない環境はキャッシュだけ。
語は data/ask/season_place.yaml の page・guide_page。"""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .park_page import esc, link, safe_url

URL_RE = re.compile(r"https?://[^\s<>\"]+")


def cfg():
    from . import season_place as SP
    return SP.cfg()["guide_page"]


def load_last(now, env=None):
    """直前のガイドの最終の文 {saved_at, brief, question, text}(有効期間は page.valid_hours)。なければ None。"""
    from . import answer_page as APG
    from . import guide_verify as GV
    try:
        doc = json.loads(GV.last_guide_path(env).read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(doc["saved_at"])
    except (OSError, ValueError, KeyError):
        return None
    if not doc.get("text") or now < saved or now - saved > timedelta(hours=APG.cfg()["valid_hours"]):
        return None
    return doc


def newest(now, env=None):
    """ガイドの最終の文が、今までの形の直前の答え(ask/last_answer.json)・計画(ask/last_plan.json)より新しければ、その文。"""
    from . import answer_page as APG
    from . import ask
    g = load_last(now, env)
    if not g:
        return None
    others = [d.get("saved_at") for d in (APG.load_last(now, env), ask.load_last_plan(now, env)) if d and d.get("saved_at")]
    if any(datetime.fromisoformat(s) > datetime.fromisoformat(g["saved_at"]) for s in others):
        return None
    return g


def _body_text(text):
    """出典の節より前の本文(種の名前を探す範囲)。"""
    c = cfg()
    lines = []
    for ln in (text or "").splitlines():
        if ln.strip() in c["stop_headings"]:
            break
        lines.append(ln)
    return "\n".join(lines)


def _facts_candidates(bid, env=None):
    from . import guide_brief as GB
    p = GB.brief_dir(env) / f"{bid}.work" / "facts.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [(sj, c) for sj, sub in (doc.get("subjects") or {}).items() for c in (sub or {}).get("candidates") or []]


def species(doc, env=None):
    """最終の文 → 写真に載せる種 [(和名, テーマ)](文に出た順。重複なし。最大 page.max_species)。"""
    from . import ask, guide_photos
    from .plan_page import species_of
    from . import answer_page as APG
    c = cfg()
    pp = ask.load_policy()["plan_page"]
    text = _body_text(doc.get("text"))
    found = []                                                        # (文の中の位置, 和名, テーマ)
    for sj, cand in _facts_candidates(doc.get("brief"), env):        # 文に出る名所の種(樹種・花の種類・公園の鳥)
        pos = text.find(cand.get("name") or "\0")
        if pos < 0:
            continue
        for i, n in enumerate(species_of(cand, sj, pp)):
            found.append((pos + i / 100, n, c["subject_themes"].get(sj)))
    table = guide_photos.load_table(env) if env else guide_photos.load_table()
    themes = _table_themes(env)
    words = {**{n: n for n in table}, **(c.get("aliases") or {}), **(pp.get("photo_aliases") or {})}
    rest = text
    for w in sorted(words, key=len, reverse=True):                    # 文に名前の出る種(長い語から。「河津桜」の中の「桜」は数えない)
        if len(w) < c["min_word_chars"] or w in (pp.get("skip_names") or []):
            continue
        for m in re.finditer(re.escape(w), rest):
            n = words[w]
            found.append((m.start(), n, themes.get(n) or c["alias_themes"].get(w)))
        rest = rest.replace(w, "\0" * len(w))
    if not found:                                                     # 紅葉の答えで樹種の分からない名所だけ: 代表的な紅葉の木(その場所の写真ではない。注記は page.photo_note)
        from . import guide_brief as GB
        try:
            subjects = GB.load(doc.get("brief"), env).get("subjects") or []
        except (OSError, ValueError, TypeError):
            subjects = []
        for sj in subjects:
            for i, n in enumerate((c.get("subject_fallback") or {}).get(sj) or []):
                found.append((i, n, c["subject_themes"].get(sj)))
    out, seen = [], set()
    for _pos, n, th in sorted(found, key=lambda x: x[0]):
        if n and n not in seen and n not in (pp.get("skip_names") or []):
            seen.add(n)
            out.append((n, th))
    return out[: APG.cfg()["max_species"]]


def _table_themes(env=None):
    """{和名: テーマ}(どの対応表にあるか)。"""
    from . import guide, guide_photos
    ph = guide_photos.photos_policy()
    out = {}
    for theme, t in (ph.get("themes") or {}).items():
        f = t.get("table_file")
        if not f:
            continue
        for path in (guide.GUIDE_DIR / f, guide_photos.export_dir(env) / f):
            for r in guide_photos._read_table(path):
                out.setdefault(r["name"], theme)
    return out


def ensure_photos(names_themes, env=None, http_get=None, http_bytes=None):
    """キャッシュにない種の写真を、テーマごとに確認なしで補う(承認B)。許可されない環境は取りに行かない。→ {ran, requests, results}"""
    from . import guide, guide_photos
    policy = guide.load_policy()
    hg, hb, closer = guide_photos._ensure_http(policy, http_get, http_bytes)
    if hg is None:
        return {"ran": False, "reason": closer, "requests": 0, "results": {}}
    total = {"ran": True, "requests": 0, "results": {}}
    try:
        by = {}
        for n, th in names_themes:
            by.setdefault(th or cfg()["default_theme"], []).append(n)
        left = policy["photos"]["max_requests_per_run"]["value"]
        for th, ns in by.items():
            if left <= 0:
                break
            r = guide_photos.ensure(ns, theme=th, policy=policy, http_get=hg, http_bytes=hb, phenology=True, max_requests=left, env=env)
            total["requests"] += r["requests"]
            left -= r["requests"]
            total["results"].update(r["results"])
            if r["status"] != "ok":
                break
    finally:
        if closer is not None and hasattr(closer, "close"):
            closer.close()
    if total["requests"]:
        guide_photos._log_requests(total["requests"], "guide_answer_page")
    return total


def clean_text(text):
    """太字の印(**)だけ外す(文は変えない)。"""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")


def make(doc, now, env=None, fetch=True, http_get=None, http_bytes=None):
    """直前のガイドの答えのページを作ってデータ置き場に書く。→ {path, line, species, photos, fetched}"""
    from . import answer_page as APG
    from . import ask, guide, guide_page, guide_photos, plan_page
    sp = species(doc, env)
    fetched = ensure_photos(sp, env, http_get, http_bytes) if fetch and sp else {"ran": False, "requests": 0, "results": {}}
    pol = guide.load_policy()
    gp = pol["photos"]
    pp = ask.load_policy()["plan_page"]
    table = guide_photos.load_table(env) if env else guide_photos.load_table()

    def photo_for(name):
        row = table.get(name)
        if not row:
            return None
        return guide_photos.load_photo(row["taxon_id"], env) if env else guide_photos.load_photo(row["taxon_id"])

    def credit(meta):
        return plan_page.author_credit(meta, gp, guide_page.state_text(meta, pol) if meta.get("rule") else None)
    page_doc = {"route": "guide", "question": doc.get("question"), "text": clean_text(doc.get("text")), "species": [n for n, _ in sp]}
    mx = pp["max_embed_bytes"]
    html_text, _lines, shown = APG.build(page_doc, photo_for=photo_for, photo_credit=credit, csp=pp["csp"],
                                         max_bytes=mx["value"] if isinstance(mx, dict) else mx, linkify=True)
    out = (guide_photos.page_dir(env) if env else guide_photos.page_dir()) / cfg()["file"].format(brief=doc.get("brief") or "x", date=now.date().isoformat())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8", newline="\n")
    path = str(Path(out).resolve())
    return {"path": path, "line": pp["reply_line"].format(path=path), "species": [{"name": n, "photo": x} for n, x in shown],
            "photos": sum(1 for _n, x in shown if x), "fetched": fetched}


def linkify(escaped):
    """エスケープ済みの文の中の URL をリンクにする(http・https だけ)。"""
    def rep(m):
        u = m.group(0).replace("&amp;", "&")
        return link(u, u) if safe_url(u) else m.group(0)
    return URL_RE.sub(rep, escaped)


__all__ = ["load_last", "newest", "species", "make", "esc"]
