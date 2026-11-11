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
    from . import answer_page as APG
    return species_all(doc, env)[: APG.cfg()["max_species"]]


def species_all(doc, env=None):
    """最終の文 → 文に出る種 [(和名, テーマ)](文に出た順。重複なし。上限なし)。"""
    return [(n, th) for n, th, _w in _found(doc, env)]


def species_words(doc, env=None):
    """段階81 の続き 4: {和名: [文の中で見つけた語]}(写真を、その語が出る段落のそばに置くため)。
    名所の記録から足した種(文に種の名前がない)は、和名そのものだけ。"""
    out = {}
    for n, _th, w in _found(doc, env, all_hits=True):
        ws = out.setdefault(n, [n])
        if w and w not in ws:
            ws.append(w)
    return out


def _found(doc, env=None, all_hits=False):
    """→ [(和名, テーマ, 文の中の語)](文に出た順。all_hits が偽なら和名の重複なし)。"""
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
            found.append((pos + i / 100, n, c["subject_themes"].get(sj), None))
    table = guide_photos.load_table(env) if env else guide_photos.load_table()
    themes = _table_themes(env)
    reps = APG.cfg().get("representatives") or {}                     # 段階81 の追記: 総称の種(ツツジ・バラなど)も文から探す(写真は代表の種)
    words = {**{n: n for n in reps}, **{n: n for n in table}, **(c.get("aliases") or {}), **(pp.get("photo_aliases") or {})}
    rest = text
    for w in sorted(words, key=len, reverse=True):                    # 文に名前の出る種(長い語から。「河津桜」の中の「桜」は数えない)
        if len(w) < c["min_word_chars"] or w in (pp.get("skip_names") or []):
            continue
        for m in re.finditer(re.escape(w), rest):
            n = words[w]
            found.append((m.start(), n, themes.get(n) or c["alias_themes"].get(w), w))
        rest = rest.replace(w, "\0" * len(w))
    if not found:                                                     # 紅葉の答えで樹種の分からない名所だけ: 代表的な紅葉の木(その場所の写真ではない。注記は page.photo_note)
        from . import guide_brief as GB
        try:
            subjects = GB.load(doc.get("brief"), env).get("subjects") or []
        except (OSError, ValueError, TypeError):
            subjects = []
        for sj in subjects:
            for i, n in enumerate((c.get("subject_fallback") or {}).get(sj) or []):
                found.append((i, n, c["subject_themes"].get(sj), None))
    out, seen = [], set()
    for _pos, n, th, w in sorted(found, key=lambda x: x[0]):
        if n and (all_hits or n not in seen) and n not in (pp.get("skip_names") or []):
            seen.add(n)
            out.append((n, th, w))
    return out


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
    sp_all = species_all(doc, env)
    sp = sp_all[: APG.cfg()["max_species"]]
    table0 = guide_photos.load_table(env) if env else guide_photos.load_table()
    want = [((APG.representative(n) or {}).get("name") if n not in table0 and APG.representative(n) else n, th) for n, th in sp]   # 総称の種は代表の種の写真を補う
    fetched = ensure_photos(want, env, http_get, http_bytes) if fetch and sp else {"ran": False, "requests": 0, "results": {}}
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
        return plan_page.author_credit(meta, gp)                 # 状態(開花など)は出さない(段階81 の追記)
    title = title_for(doc, env)
    page_doc = {"route": "guide", "question": doc.get("question"), "text": doc.get("text"), "species": [n for n, _ in sp_all],
                "markdown": True, "title": title, "species_words": species_words(doc, env), "stop_headings": cfg()["stop_headings"]}
    mx = pp["max_embed_bytes"]
    html_text, _lines, shown = APG.build(page_doc, photo_for=photo_for, photo_credit=credit, csp=pp["csp"],
                                         max_bytes=mx["value"] if isinstance(mx, dict) else mx, linkify=True)
    out = (guide_photos.page_dir(env) if env else guide_photos.page_dir()) / cfg()["file"].format(brief=doc.get("brief") or "x", date=now.date().isoformat())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8", newline="\n")
    path = str(Path(out).resolve())
    remember_page(doc, title, path, now, env)
    return {"path": path, "title": title, "line": pp["reply_line"].format(path=path), "species": [{"name": n, "photo": x} for n, x in shown],
            "photos": sum(1 for _n, x in shown if x), "fetched": fetched}


# ---- 段階81 の続き 5: ページの題(資料から決める。AI に書かせない) ----

def _longest_in(text, names):
    hits = [n for n in names if n and len(n) >= cfg()["min_word_chars"] and n in text]
    return max(hits, key=len) if hits else None


def _themes_in(text, t, env=None):
    """質問の文に出るテーマの語(長い語から、重ならないように。文に出た順)。テーマの語の一覧は 1 字の語も見る。"""
    from . import guide_photos
    table = guide_photos.load_table(env) if env else guide_photos.load_table()
    mc = cfg()["min_word_chars"]
    words = set(t["theme_words"]) | {w for w in list(cfg().get("aliases") or {}) + list(table) if len(w) >= mc}
    rest, found = text, []
    for w in sorted(words, key=len, reverse=True):
        for m in re.finditer(re.escape(w), rest):
            found.append((m.start(), w))
        rest = rest.replace(w, "\0" * len(w))
    return [w for _p, w in sorted(found)]


def _place_of(q, brief, t, env=None):
    """質問の文の場所: 候補の名所(括弧の前の名前も)・名所の辞書の最長の名前。なければ文頭の地名らしい語(日付・テーマの語は除く)。"""
    names = []
    for x in brief.get("candidates") or []:
        if isinstance(x, dict) and x.get("name"):
            names += [x["name"], re.split(r"[(（]", x["name"])[0]]
    place = _longest_in(q, names)
    if not place:
        from . import ask
        place = _longest_in(q, ask.place_names())
    if not place:
        m = re.match(t["lead_place_re"], q)
        w = m.group(1) if m else None
        if w and not any(d in w for d in t["date_words"]) and not _themes_in(w, t, env):
            place = w
    return place


def title_for(doc, env=None):
    """資料(質問の文・候補の名所・対象・出発地・質問の型)から、ページの題を決める(語と形は guide_page.title)。
    既定の形は「<出発地から> <場所> <日付の語>の<テーマ>の<見どころ・おすすめなど>」(ないものは省く)。字数の上限を超えたら質問の文。"""
    from . import guide_brief as GB
    t = cfg()["title"]
    q = (doc.get("question") or "").strip()
    try:
        brief = GB.load(doc.get("brief"), env) or {}
    except (OSError, ValueError, TypeError):
        brief = {}
    q = (brief.get("question") or q).strip()
    place = _place_of(q, brief, t, env)
    rest = q.replace(place, "") if place else q
    origin = brief.get("origin") if brief.get("origin_source") in t["origin_sources"] and brief.get("origin") in rest else None
    if origin:
        rest = rest.replace(origin, "")
    date = next((w for w in t["date_words"] if w in rest), None)
    topic = next((w for w in t["topic_words"] if w in rest), None)
    themes = _themes_in(rest, t, env)
    subs = brief.get("subjects") or []
    theme = themes[0] if themes else (t["subject_words"].get(subs[0]) if len(subs) == 1 and not place else None)   # 場所の質問に聞かれていないテーマを足さない
    fmt = t["by_kind"].get(brief.get("intent")) or t["by_kind"].get(brief.get("route"))
    title = None
    if fmt and ("{theme" not in fmt or theme) and ("{themes}" not in fmt or len(themes) >= 2) and ("{place_no}" not in fmt or place or theme):
        event = next((w for w in t["event_words"] if w in rest), t["event_words"][-1])
        title = fmt.format(place_sp=(place + " ") if place else "", place_no=(place + "の") if place else "", theme=theme or "",
                           theme_no=(theme + "の") if theme else "", themes="と".join(themes),
                           themes_dot=("・".join(themes) + "の") if themes else ((theme + "の") if theme else ""), event=event).strip()
    if not title:
        head = " ".join(x for x in ((t["origin_fmt"].format(origin=origin) if origin else None), place) if x)
        if theme and any(w in rest for w in t["seen_words"]):
            tail = (date if date == t["date_words"][-1] else "") + t["seen_fmt"].format(theme=theme)
            joint = "で" if place else " "
        else:
            tail = "の".join(x for x in (date, theme if theme != topic else None, topic or t["default_topic"]) if x)
            joint = " " if (date or not place) else "の"             # 「高尾山 今週末の見どころ」「八ヶ岳の見どころ」
        title = (head + joint + tail) if head else tail
    return title if len(title) <= t["max_chars"] else (q or title)


# ---- 段階81 の続き 1: ページを頼まれたときの最後の文(決まった短い案内 + ページのリンク) ----

def last_page_path(env=None):
    from .paths import data_path
    return data_path(cfg()["reply"]["last_file"], env)


def remember_page(doc, title, path, now, env=None):
    """ページを、合格した最終の文(doc)から作ったことを覚える(案内の文を受け入れる条件)。"""
    p = last_page_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"saved_at": now.isoformat(), "brief": doc.get("brief"), "final_saved_at": doc.get("saved_at"),
                             "title": title, "path": path, "reply": None}, ensure_ascii=False, indent=1), encoding="utf-8")


def _load_page(now, env=None):
    """直前のページの記録。合格した最終の文(いま有効なもの)から作ったものだけ。なければ None。"""
    try:
        d = json.loads(last_page_path(env).read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(d["saved_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    g = load_last(now, env)
    if not g or g.get("brief") != d.get("brief") or g.get("saved_at") != d.get("final_saved_at"):
        return None                                      # ページのあとに別の答えを作った・最終の文が古い
    if now < saved or saved < datetime.fromisoformat(g["saved_at"]):
        return None
    return d


class ReplyError(ValueError):
    pass


def page_reply(url, now, env=None):
    """→ 利用者に送る最後の文(決まった案内 + リンク)。url を省くとページのファイルの場所。覚えて、検査で受け入れる。"""
    r = cfg()["reply"]
    d = _load_page(now, env)
    if d is None:
        raise ReplyError(r["no_page"])
    if url:
        url = url.strip()
        if not re.fullmatch(r["url_re"], url):
            raise ReplyError(r["bad_url"])
    text = r["text"].format(title=d["title"], url=url or d["path"])
    d["reply"] = text
    last_page_path(env).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return text


def accepts_reply(message, now=None, env=None):
    """送るメッセージが、ask page-reply が出した案内の文と一致するか(空白の違いは見ない)。"""
    d = _load_page(now or datetime.now().astimezone(), env)
    t = (d or {}).get("reply")
    return bool(t) and re.sub(r"\s+", "", t) == re.sub(r"\s+", "", message or "")


def linkify(escaped):
    """エスケープ済みの文の中の URL をリンクにする(http・https だけ)。"""
    def rep(m):
        u = m.group(0).replace("&amp;", "&")
        return link(u, u) if safe_url(u) else m.group(0)
    return URL_RE.sub(rep, escaped)


__all__ = ["load_last", "newest", "species", "make", "esc", "title_for", "page_reply", "accepts_reply"]
