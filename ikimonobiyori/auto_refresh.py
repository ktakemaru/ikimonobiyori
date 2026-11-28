"""段階85 第1部: 資料(ask brief)を作るときの、現況のページの自動の読み直し。

段階77 で答えの既定を新しい形(ask brief → 書く → ask verify)に切り替えたあと、`ask brief` は今までの答えの経路を
quiet で動かして材料を作るが、その経路が出す「読むページ」(有効期間を過ぎた現況のページ。refresh_pages)を資料に入れていなかった。
今までの形では、エージェントが標準エラーの「読むページ」を読んで記録していたが、新しい形の手順にはその段がない。そのため、
質問のたびの読み直しが起きず、現況が古いままになっていた(2026-11-15 の答えの現況が 11/6〜9 のまま)。

ここでは、資料に入る候補の承認済みの情報源のページ(有効期間切れ。候補の順位の高いものから)を、コードが読み直す:
- 上限: 1 つの質問で max_pages ページ・合わせて max_seconds 秒(data/ask/guide_mode.yaml の auto_refresh)。超えた分は読まない。
- 取得は今ある仕組みと同じ: 宣言済みの台帳の URL だけ(新しい通信先を足さない)・robots.txt を先に読む・同じホストへ間隔をあける・
  netlog/requests.jsonl に記録(netbudget)・取得のキャッシュ(page_cache)に読んだ時刻。テスト中は通信しない(http_get を渡したときだけ)。
- 台帳で reader: code の情報源(日光市観光協会・箱根町観光協会)は、決まった形で状態を読み(fetch/status_pages)、記録に足す。
- ほかのページは、本文から状態を推測しない(規則 11)。前回の記録の原文(状態の語と日付の書き方)がページにそのまま残っていれば
  「変わっていない」として最後に確かめた時刻だけを更新する(段階63b と同じ)。残っていなければ「変わった」として、
  読み直した本文の控えの場所を資料に出す(エージェントが本文で確かめて ask record し、資料を作り直す)。
- 通信できないとき(オフライン・失敗)は、黙って古い記録で続け、資料の「足りないもの」に読み直せなかったことを書く。
本文はデータ置き場の auto_refresh/pages の下に、変わったページの分だけ控える(次に読み直すと上書き。答えには出さない)。"""
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from .paths import data_path

NL = "\n"


def cfg():
    from . import guide_brief as GB
    return GB.cfg()["auto_refresh"]


def _v(x):
    return x["value"] if isinstance(x, dict) else x


def norm(s):
    """比べるための形(全角・半角の違い・空白の違いを見ない)。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", s or ""))


def url_key(url):
    """URL を比べる形(パーセント符号の大文字・小文字の違いを見ない)。"""
    from urllib.parse import unquote
    return unquote(url or "").strip().rstrip("/")


def approved_status_urls():
    """台帳(data/sources/*.yaml)で承認済みの、現況のページ(status_page)の URL(比べる形)。新しい通信先を足さないため、読み直しはこの中だけ。"""
    from . import sources as S
    out = set()
    for subj in LEDGERS:
        try:
            reg = S.load_registry(subj)
        except (OSError, ValueError):
            continue
        for src in (reg or {}).get("sources") or []:
            if src.get("kind") == "status_page" and S.is_approved(src) and src.get("url"):
                out.add(url_key(src["url"]))
    return out


LEDGERS = ("autumn_leaves", "flowers", "birds", "wintering_birds")


def _code_source(url):
    """台帳で reader: code の承認済みの情報源(URL が同じもの)。→ (registry, src) か (None, None)。"""
    from . import sources as S
    for subj in LEDGERS:
        try:
            reg = S.load_registry(subj)
        except (OSError, ValueError, KeyError):
            continue
        for src in (reg or {}).get("sources") or []:
            if url_key(src.get("url")) == url_key(url) and src.get("reader") == "code" and S.is_approved(src):
                return reg, src
    return None, None


def _latest_records(subject, url, env=None):
    """その URL から記録した、名所ごとの最新の現況の記録(状態の原文があるもの)。"""
    from . import observations as O
    rows = [r for r in O.read_records(subject, env) if r.get("url") == url and (r.get("state") or "").strip()]
    last = {}
    for r in rows:
        k = r.get("spot") or r.get("name")
        if k and (k not in last or (r.get("read_at") or "") >= (last[k].get("read_at") or "")):
            last[k] = r
    return list(last.values())


def unchanged(text, records):
    """前回の記録の原文(状態の語と、日付の書き方)が、読み直した本文にそのまま残っているか。記録がなければ False(分からない)。"""
    if not records:
        return False
    body = norm(text)
    for r in records:
        for k in ("state", "state_date_text"):
            v = norm(r.get(k))
            if v and v not in body:
                return False
    return True


_A_RE = re.compile(r"<a\s[^>]*href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def follow_link(html, base):
    """施設のページの中の、決まった語(auto_refresh.vc_follow_words)を文字に含む最初のリンク(同じホストだけ)。なければ None。"""
    from urllib.parse import urljoin
    words = cfg().get("vc_follow_words") or []
    host = (urlsplit(base).hostname or "").lower()
    links = [(re.sub(r"<[^>]+>", "", m.group(2)), urljoin(base, m.group(1).strip())) for m in _A_RE.finditer(html or "")]
    for w in words:                                      # 語の並びの順(紅葉情報が先)。同じ語ならページの上にあるもの
        for label, u in links:
            if w in label and (urlsplit(u).hostname or "").lower() == host and urlsplit(u).scheme in ("http", "https"):
                return u
    return None


def _date_forms(iso):
    """記録の日付(YYYY-MM-DD)の、ページでの書き方の候補(比べる形)。"""
    from datetime import date as _date
    d = _date.fromisoformat(str(iso)[:10])
    forms = [f"{d.month}/{d.day}", f"{d.month:02d}/{d.day:02d}", f"{d.month}月{d.day}日", f"{d.year}.{d.month}.{d.day}",
             f"{d.year}.{d.month:02d}.{d.day:02d}", f"{d.year}/{d.month}/{d.day}", f"{d.year}/{d.month:02d}/{d.day:02d}", f"{d.year}-{d.month:02d}-{d.day:02d}"]
    return [norm(x) for x in forms]


def vc_unchanged(text, center, env=None):
    """施設の情報ページの本文に、その施設の最新の記録の状態の語と日付(どれかの書き方)がそのまま残っているか。記録がなければ False。"""
    from . import visitor_centers as VC
    mine = [r for r in VC.read_reports(env) if r.get("center") == center and r.get("date")]
    if not mine:
        return False
    r = max(mine, key=lambda x: str(x["date"]))
    body = norm(text)
    if r.get("state") and norm(r["state"]) not in body:
        return False
    return any(f in body for f in _date_forms(r["date"]))


def _resubmit(records):
    """同じ記録を出し直す形(記録の側で重複として扱われ、最後に確かめた時刻だけが新しくなる)。"""
    from . import observations as O
    return [{k: r[k] for k in O.FIELDS if r.get(k) is not None} for r in records]


def _code_batch(reads, src, subject):
    """reader: code で読んだ地点 → 観察の記録の形(state・state_date・出典)。"""
    out = []
    for it in reads:
        r = {"subject": subject, "state": it["state"], "state_date": it["updated"], "url": src["url"], "publisher": src.get("publisher"),
             "source_class": "official", "basis": "page"}
        if it.get("site"):
            r["spot"] = it["site"]
        elif it.get("name"):
            r["name"] = it["name"]
        else:
            continue
        if it.get("observed_md"):
            r["state_date_text"] = it["observed_md"] + "現在"
        out.append(r)
    return out


def _alt_pages():
    """画像の説明(alt)も控えに入れるページ(台帳の id で指定。auto_refresh.alt_text)の URL(比べる形)。"""
    from . import brief_refresh as BR
    ids = set((cfg().get("alt_text") or {}).get("source_ids") or [])
    return {url_key(s["url"]) for s in BR.ledger_pages() if s["id"] in ids}


def with_alt(text, html):
    """指定したページの控え: 本文から途中で切れた写しを外し、画像の説明の全文を後ろに足す。控えの長さの上限では、本文の側を削る。"""
    from . import research as RS
    X = cfg()["alt_text"]
    alts = RS.image_alts(html, _v(X["min_chars"]))
    if not alts:
        return text[: _v(cfg()["max_text_chars"])]
    block = NL + NL + X["heading"] + NL + NL.join("- " + a for a in alts)
    mx = _v(cfg()["max_text_chars"])
    block = block[:block.rfind(NL, 0, mx) if len(block) > mx else len(block)]      # 説明は行の区切りで切る(途中の文を残さない)
    return RS.drop_truncated(text, alts, _v(X["truncated_min_chars"]))[: max(mx - len(block), 0)] + block


def _text_path(url, env=None):
    return data_path(cfg()["dir"], env) / "pages" / (hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".txt")


def _getter(env=None):
    """本物の取得(requests)。→ (get(url) → (status, bytes, headers), close)。"""
    from .config import load_config
    from .fetch.live import SessionGetter
    C = cfg()
    live = load_config().get("live") or {}
    sg = SessionGetter(user_agent=live.get("user_agent") or "ikimonobiyori", connect_s=_v(C["connect_s"]), read_s=_v(C["read_s"]))
    return (lambda u: sg.get_bytes(u, _v(C["max_bytes"]))), sg.close


def run(targets, *, now, env=None, http_get=None, clock=time.monotonic, sleep=time.sleep):
    """読み直す。targets: [{url, name, subject, kind, publisher, current_date, last_read}](順位の高いものから)。
    → {pages: [{url, name, subject, result(code_read/unchanged/changed/failed/skipped), detail, text_path?, written?}], elapsed_s, requests}"""
    from . import netbudget as NB
    from . import observations as O
    from . import page_cache as PC
    from . import research as RS
    from .fetch.status_pages import read_source
    from .config import load_config
    C = cfg()
    t0 = clock()
    out = {"pages": [], "elapsed_s": 0.0, "requests": 0, "refused": None}
    if not targets:
        return out
    if http_get is None:
        ref = NB.refusal(env)
        if ref:
            out["refused"] = ref
            for t in targets[: _v(C["max_pages"])]:
                out["pages"].append({**_brief_row(t), "result": "failed", "detail": f"通信しない({ref})"})
            return out
    close = None
    if http_get is None:
        http_get, close = _getter(env)
    hosts = sorted({(urlsplit(t["url"]).hostname or "").lower() for t in targets if t.get("url")})
    budget = NB.Budget("auto_refresh", hosts, _v(C["max_requests"]), _v(C["min_interval_s"]), env=env, clock=clock, sleep=sleep)
    g = budget(http_get)
    notes = []
    try:
        for i, t in enumerate(targets):
            row = _brief_row(t)
            if i >= _v(C["max_pages"]) or clock() - t0 > _v(C["max_seconds"]):
                out["pages"].append({**row, "result": "skipped", "detail": "上限"})
                continue
            url = t["url"]
            try:
                reg, src = _code_source(url)
                if src is not None:
                    def g_text(u):
                        st, body, _h = g(u)
                        return st, (body.decode("utf-8", errors="replace") if isinstance(body, bytes) else (body or ""))
                    reads, rep = read_source(src, http_get=g_text, cfg=load_config(), on=now.date(), max_requests=_v(C["max_requests_per_page"]))
                    if not reads:
                        out["pages"].append({**row, "result": "failed", "detail": rep.get("status")})
                        notes.append({"url": url, "ok": False, "kind": t.get("kind"), "reason": "auto_refresh"})
                        continue
                    res = O.record(_code_batch(reads, src, reg["subject"]), env=env, now=now)
                    out["pages"].append({**row, "result": "code_read", "detail": f"{len(reads)} 地点", "written": len(res.get("written") or [])
                                         if isinstance(res.get("written"), list) else res.get("written")})
                    notes.append({"url": url, "ok": True, "kind": t.get("kind"), "reason": "auto_refresh"})
                    continue
                p = urlsplit(url)
                rs, rbody, _h = g(urlunsplit((p.scheme, p.netloc, "/robots.txt", "", "")))
                rtxt = rbody.decode("utf-8", errors="replace") if isinstance(rbody, bytes) else (rbody or "")
                if rs == 200 and not RS.robots_allows(rtxt, url):
                    out["pages"].append({**row, "result": "failed", "detail": "robots.txt が拒否"})
                    continue
                if rs not in (200, 404, 410):
                    out["pages"].append({**row, "result": "failed", "detail": f"robots.txt を確かめられない(HTTP {rs})"})
                    continue
                st, body, headers = g(url)
                if st != 200:
                    out["pages"].append({**row, "result": "failed", "detail": f"HTTP {st}"})
                    notes.append({"url": url, "ok": False, "kind": t.get("kind"), "reason": "auto_refresh"})
                    continue
                ctype = (headers or {}).get("Content-Type") or (headers or {}).get("content-type") or ""
                raw = body if isinstance(body, bytes) else (body or "").encode("utf-8")
                html = raw.decode(RS._charset(ctype, raw), errors="replace")
                text = RS.html_text(html)
                alt_page = url_key(url) in _alt_pages()
                if alt_page:                             # 台帳で指定したページだけ: 画像の説明(alt)の全文も控えに入れる
                    text = with_alt(text, html)
                if t.get("center") and not vc_unchanged(text, t["center"], env):   # 施設のトップに見出しだけがあるとき: 決まった語のリンクを 1 つだけたどる
                    link = follow_link(html, url)
                    if link and budget.left() > 0 and clock() - t0 <= _v(C["max_seconds"]):
                        st2, body2, h2 = g(link)
                        if st2 == 200:
                            raw2 = body2 if isinstance(body2, bytes) else (body2 or "").encode("utf-8")
                            ct2 = (h2 or {}).get("Content-Type") or (h2 or {}).get("content-type") or ""
                            text = text + NL + NL + "----- " + link + " -----" + NL + RS.html_text(raw2.decode(RS._charset(ct2, raw2), errors="replace"))
                if t.get("center"):                      # 本人の判断(2026-11-15 の 1): 施設の情報ページ。前回の記録(状態の語と日付)が残っていれば変わっていない
                    if vc_unchanged(text, t["center"], env):
                        out["pages"].append({**row, "result": "unchanged", "detail": "前回の記録の状態の語と日付がそのまま"})
                        notes.append({"url": url, "ok": True, "kind": "visitor_center", "reason": "auto_refresh_unchanged"})
                        continue
                    tp = _text_path(url, env)
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    tp.write_text(text[: _v(C["max_text_chars"])], encoding="utf-8")
                    out["pages"].append({**row, "result": "changed", "detail": "前回の記録の状態の語か日付がページにない", "text_path": str(tp)})
                    continue                             # 読んだ時刻は残さない(記録するまで、次の質問でも読み直す)
                recs = _latest_records(t.get("subject"), url, env)
                if unchanged(text, recs):
                    O.record(_resubmit(recs), env=env, now=now)
                    out["pages"].append({**row, "result": "unchanged", "detail": f"記録 {len(recs)} 件の原文がそのまま"})
                    notes.append({"url": url, "ok": True, "kind": t.get("kind"), "reason": "auto_refresh_unchanged"})
                    continue
                tp = _text_path(url, env)
                tp.parent.mkdir(parents=True, exist_ok=True)
                tp.write_text(text[: _v(C["max_text_chars"])], encoding="utf-8")
                out["pages"].append({**row, "result": "changed", "detail": "前回の記録の原文がページにない", "text_path": str(tp),
                                     **({"alt_text": True} if alt_page else {})})
            except Exception as ex:                       # 通信の失敗・上限は、古い記録のまま続ける
                out["pages"].append({**row, "result": "failed", "detail": f"{type(ex).__name__}"})
    finally:
        if close:
            close()
        out["requests"] = budget.used
        out["elapsed_s"] = round(clock() - t0, 2)
        try:
            PC.note(notes, now, env)
        except OSError:
            pass
    return out


def _brief_row(t):
    return {"url": t.get("url"), "name": t.get("name"), "subject": t.get("subject"), "publisher": t.get("publisher"),
            "current_date": t.get("current_date"), **({"center": t["center"]} if t.get("center") else {})}


def needs_rebuild(result):
    """記録が変わった(新しい記録を書いた)ときだけ、資料を作り直す。"""
    return any(p.get("result") == "code_read" and p.get("written") for p in result.get("pages") or [])


__all__ = ["run", "unchanged", "needs_rebuild", "norm"]
