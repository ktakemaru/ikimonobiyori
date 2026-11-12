"""段階78 第4部: その場で調べる(本人の判断 2026-11-11)。

資料が薄いとき(聞かれた種の名所が 0〜1 件・聞かれた場所に名所もカードもない・利用者が挙げた場所の記録がない)に、
`ask brief` が資料に「調べる」の指示を入れる(needs)。AI は公式ページの URL を探し(検索は行き先探しだけ)、
`ask research fetch <URL> --brief <id>` で本文を読み、確かめた名所と例年の時期だけを `ask research record` で記録してから、
資料を作り直して答える。

決まり:
- 読むのは「公式」の発行元のページだけ(自治体・観光協会・公園管理者・施設運営者(指定管理者を含む)・国や県の機関。発行元の区分は
  guide_brief._source_class と同じ)。使わない情報源(予想・転載・SNS)は読まない。
- 取得はコードが行う: robots.txt を先に読み、拒否なら読まない/同じホストへ 1 秒以上/1 つの質問で 3 ページ・2 分まで/
  同じ URL は 7 日のあいだ控えを使う/実行ごとの記録を netlog/requests.jsonl に(netbudget と同じ)。テスト中は通信しない。
- 記録してよいのは名所の名前・都県と市町村・見られる種・例年の時期・行く前の注意・出典だけ(今年の現況は記録しない)。
  記録には「その場で調べた」印(research: {at, brief, question})。`ask research list` で一覧にできる。
- 今年の現況を出している公式ページは、データ置き場の research/pending_sources.jsonl に承認待ちの候補として残す
  (リポジトリの台帳は実行で書き換えない。本人の見直しのあとに台帳へ移す)。
値は data/ask/guide_mode.yaml の research。"""
import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from .paths import data_path

NL = "\n"


def cfg():
    from . import guide_brief as GB
    return GB.cfg()["research"]


def rdir(env=None):
    return data_path(cfg()["dir"], env)


# ---- いつ動くか ----

def needs(question, cond, sprows, cands, cards, facts, c=None):
    """資料が薄いか。→ [{what, where, why}](空なら調べない)。"""
    from . import guide_materials as GM
    from . import place_guard as PG
    from . import season_place as SP
    R = (c or {}).get("research") or cfg()
    out = []
    sps = GM.species_names(question)
    place = SP.place_filter(question)
    for sp in sps:
        rows = [r for r in sprows if r["species"] == sp and (not place or r.get("in_place"))]
        if len(rows) < R["min_species_rows"]:
            out.append({"what": sp, "where": (place or {}).get("label"), "why": f"{sp}の名所が{len(rows)}件"})
    try:
        qplaces = [p for p in PG.candidates(question) if len(p) >= 2]
    except (KeyError, TypeError, ValueError):
        qplaces = []
    if place and place.get("label") and place["label"] not in qplaces:
        qplaces.append(place["label"])
    for p in question_places(question):
        if p not in qplaces and not any(p in q or q in p for q in qplaces):
            qplaces.append(p)
    for p in qplaces:
        if any(o["where"] == p for o in out):
            continue
        in_area = bool(place and p == place.get("label") and place.get("cities"))     # 段階80 の追記2: エリア(「伊豆半島」)はその市区町村の候補も数える
        n_c = sum(1 for r in cands if p in (r.get("name") or "") or p in (r.get("city") or "")
                  or (in_area and any((r.get("city") or "").startswith(x) for x in place["cities"])))
        n_f = sum(1 for f in facts if p in (f.get("content") or "") and f.get("url"))     # 段階80 A: 出どころのない行(「まだ見つかっていません」)は事実に数えない
        n_k = sum(1 for k in cards if p in " ".join([k.get("place") or "", k.get("title") or ""]))
        if n_c == 0 and n_k == 0 and n_f == 0:
            out.append({"what": "、".join(sps) or None, "where": p, "why": f"「{p}」の名所・カード・事実がない"})
    return out


_MUNIS = None


def _municipalities():
    """名所カタログ・観察の名所・ガイドのカタログ・出発地の辞書・記録にある市区町村の名前。"""
    global _MUNIS
    if _MUNIS is None:
        from . import guide_materials as GM
        from . import origins
        out = {v.get("city") for v in GM._index().values() if v.get("city")}
        try:
            out |= set(origins.places())
        except (OSError, ValueError, KeyError):
            pass
        _MUNIS = {re.sub(r"^(.+?[市郡])(.+[町村区])$", r"\2", m) for m in out if m} | {m for m in out if m}
    return _MUNIS


def question_places(question):
    """質問の文に利用者が挙げた場所の名前(市区町村の名前か略称「南伊豆」「河津」、名所・エリアの辞書の名前)。"""
    from . import guide_verify as GV
    q = question or ""
    munis = _municipalities()
    dic = GV._dictionary_places()
    out = []
    for m in re.finditer(r"([一-龥ァ-ヶー]{2,8}?)(市|町|村|区)?(?=で|の|は|にも|や|に|と|周辺|あたり|付近)", q):
        x, suf = m.group(1), m.group(2) or ""
        x = re.sub(r"^.*?(都|道|府|県)", "", x) or x
        hit = None
        if (x + suf) in munis:
            hit = x + suf
        elif not suf and any((x + s) in munis for s in ("市", "町", "村")):
            hit = x
        elif x in dic:
            hit = x
        if hit and hit not in out:
            out.append(hit)
    return out


def lines_for(bid, targets):
    """資料の Markdown の節「調べる」。"""
    R = cfg()
    if not targets:
        return []
    L = ["## 調べる(資料が薄い)", ""]
    L += [f"- {t.get('where') or ''}{'の' if t.get('where') and t.get('what') else ''}{t.get('what') or ''}: {t['why']}" for t in targets]
    L.append("")
    L += [x.format(id=bid) for x in R["step_lines"]]
    if any(t.get("kind") == "species_card" for t in targets):      # 段階82 第2部 1: 種の公的な解説
        from . import guide_brief as GB
        L += [x.format(id=bid) for x in GB.cfg()["species_traits"]["step_lines"]]
    return L + [""]


# ---- 取得 ----

class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "dd", "dt", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append(NL)

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append(NL)

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


class _Operator(HTMLParser):
    """段階80 B(提案9): ページの運営者の欄(<footer>・id/class に footer・copyright を含む要素・meta の author/copyright)の文字。"""

    def __init__(self, cls_re):
        super().__init__(convert_charrefs=True)
        self.cls_re, self.stack, self.out, self.skip = cls_re, [], [], 0

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta" and (a.get("name") or "").lower() in ("author", "copyright") and a.get("content"):
            self.out.append(a["content"])
            return
        if tag in _Text.SKIP:
            self.skip += 1
            return
        if self.stack and tag == self.stack[-1][0]:
            self.stack[-1][1] += 1
        elif tag == "footer" or re.search(self.cls_re, " ".join([a.get("id", ""), a.get("class", "")]), re.I):
            self.stack.append([tag, 1])

    def handle_endtag(self, tag):
        if tag in _Text.SKIP and self.skip:
            self.skip -= 1
            return
        if self.stack and tag == self.stack[-1][0]:
            self.stack[-1][1] -= 1
            if self.stack[-1][1] == 0:
                self.stack.pop()
                self.out.append(NL)

    def handle_data(self, data):
        if self.stack and not self.skip:
            self.out.append(data)


def operator_text(html, text=None):
    """運営者の欄の文字(フッター・著作権表示・運営者情報の行)。欄が見つからなければ空。"""
    R = cfg()
    out = []
    if html:
        p = _Operator(R["operator_class_re"])
        try:
            p.feed(html)
        except Exception:
            pass
        out.append("".join(p.out))
    for line in (text if text is not None else html_text(html or "")).splitlines():
        if re.search(R["operator_line_re"], line):
            out.append(line)
    return re.sub(r"\s+", " ", NL.join(x for x in out if x and x.strip())).strip()


def html_text(html):
    p = _Text()
    try:
        p.feed(html or "")
    except Exception:                                    # 壊れた HTML でも読めたところまで
        pass
    t = "".join(p.out)
    t = re.sub(r"[ \t　]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


def robots_allows(robots_txt, url, agent="*"):
    """robots.txt の Disallow(User-agent: * の組)にパスが当たらないか(読めないものは呼び出し側で拒否扱い)。"""
    path = urlsplit(url).path or "/"
    groups, cur, active = [], None, False
    for raw in (robots_txt or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if cur is None or cur["rules"]:
                cur = {"ua": [], "rules": []}
                groups.append(cur)
            cur["ua"].append(v.lower())
        elif k in ("allow", "disallow") and cur is not None:
            cur["rules"].append((k, v))
    rules = [r for g in groups if agent in g["ua"] for r in g["rules"]]
    best = None
    for k, v in rules:
        if v and path.startswith(v) and (best is None or len(v) > len(best[1])):
            best = (k, v)
    return best is None or best[0] == "allow"


def _state_path(bid, env=None):
    return rdir(env) / "questions" / f"{bid}.json"


def _brief_question(bid, env=None):
    from . import guide_brief as GB
    try:
        return (GB.load(bid, env) or {}).get("question")
    except (OSError, ValueError, TypeError):
        return None


def already_researched(question, now, env=None):
    """段階82 第3部 4: この質問(読み替えたあとの文)で、research.once_hours 時間以内に一度調べたか(ask research fetch を 1 回以上)。"""
    R = cfg()
    d = rdir(env) / "questions"
    if not question or not d.exists():
        return False
    for p in d.glob("*.json"):
        try:
            st = json.loads(p.read_text(encoding="utf-8"))
            at = datetime.fromisoformat(st.get("first_at") or "")
        except (OSError, ValueError, TypeError):
            continue
        if st.get("question") == question and 0 <= (now - at).total_seconds() <= R["once_hours"] * 3600:
            return True
    return False


def _load_state(bid, env=None):
    try:
        return json.loads(_state_path(bid, env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pages": [], "first_at": None}


def _save_state(bid, st, env=None):
    p = _state_path(bid, env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _cache_path(url, env=None):
    return rdir(env) / "pages" / (hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".json")


def allowed_page(url):
    """読んでよいページか。→ 理由(読んでよいなら None)。"""
    from . import guide_brief as GB
    from . import observations as O
    from . import publisher as P
    u = urlsplit(url or "")
    if u.scheme not in ("http", "https") or not u.hostname:
        return "http(s) の URL ではない"
    if P.unused_source(url):
        return "使わない情報源"
    pol = O.load_policy()
    if O._blocked_host(u.hostname, pol) or O._sns_host(u.hostname, pol):
        return "読まない対象(利用規約・SNS)"
    if GB._source_class(url) != "official":
        return "公式の発行元のページではない(自治体・観光協会・公園管理者・施設運営者・国や県の機関だけ)"
    return None


def _declared_ok(publisher):
    """発行元の名前が、公式に当たる形(観光協会・自治体・公園の管理者など)か。"""
    return bool(publisher) and bool(re.search(cfg()["declared_publisher_re"], publisher.strip()))


def _verified(text, publisher, operator=None):
    """発行元の名前がページの運営者の欄(フッター・著作権表示・運営者情報)にあるか(空白の違いは見ない)。
    段階80 B(提案9): 本文のどこかにあるだけでは通さない。運営者の欄が一つも見つからないページも読まない(本人の判断 2026-11-11)。
    text は使わない(呼び出しの形を変えないために残している)。"""
    if not publisher or not operator:
        return False
    return re.sub(r"\s+", "", publisher) in re.sub(r"\s+", "", operator)


def fetch(url, bid, *, env=None, now=None, http_get=None, clock=time.monotonic, sleep=time.sleep, publisher=None):
    """1 ページを読む。→ {ok, status, text, path, reason, from_cache}。テスト中は通信しない(http_get を渡したときだけ)。
    publisher: 公式の一覧にないホスト(観光協会の独自ドメインなど)のとき、発行元の名前(「湯河原温泉観光協会」)。
    名前が公式の形で、読んだ本文にその名前があるときだけ、公式のページとして読む(なければ本文を捨てて読まなかったことにする)。"""
    from . import netbudget as NB
    R = cfg()
    now = now or datetime.now().astimezone().replace(microsecond=0)
    why = allowed_page(url)
    declared = None
    if why and why.startswith("公式の発行元") and _declared_ok(publisher):
        declared, why = publisher.strip(), None
    if why:
        return {"ok": False, "reason": why + ("。観光協会などの独自のドメインなら --publisher に発行元の名前を渡す" if why.startswith("公式の発行元") else "")}
    cp = _cache_path(url, env)
    try:
        cached = json.loads(cp.read_text(encoding="utf-8"))
        if now - datetime.fromisoformat(cached["fetched_at"]) <= timedelta(days=R["cache_days"]):
            if declared and not _verified(cached["text"], declared, cached.get("operator", operator_text(None, cached["text"]))):
                return {"ok": False, "reason": f"ページの運営者の欄(フッター・著作権表示・運営者情報)に発行元の名前「{declared}」がない。公式のページとして読まない"}
            _note_page(bid, url, now, env, cached=True, publisher=declared)
            return {"ok": True, "status": cached.get("status"), "text": cached["text"], "path": str(cp), "from_cache": True}
    except (OSError, ValueError, KeyError):
        pass
    st = _load_state(bid, env)
    live_pages = [p for p in st["pages"] if not p.get("cached")]
    if len(live_pages) >= R["max_pages_per_question"]:
        return {"ok": False, "reason": f"1 つの質問の上限({R['max_pages_per_question']} ページ)に達した(この資料の番号で最初に取得した時刻 {st.get('first_at') or '不明'})。"
                                        "ここまでの記録で答える。別の質問なら資料を作り直して新しい番号で"}
    if st.get("first_at") and (now - datetime.fromisoformat(st["first_at"])).total_seconds() > R["max_seconds_per_question"]:
        return {"ok": False, "reason": f"1 つの質問の時間の上限({R['max_seconds_per_question']} 秒)を過ぎた(この資料の番号で最初に取得した時刻 {st['first_at']})。"
                                        "ここまでの記録で答える。別の質問なら資料を作り直して新しい番号で"}
    if http_get is None:
        ref = NB.refusal(env)
        if ref:
            return {"ok": False, "reason": f"通信しない({ref})"}
    host = urlsplit(url).hostname.lower()
    bare = host[4:] if host.startswith("www.") else host
    budget = NB.Budget("research", [bare, "www." + bare], R["max_requests_per_page"], R["min_interval_s"], env=env, clock=clock, sleep=sleep)
    getter = http_get
    closer = None
    if getter is None:
        from . import fetch as _f  # noqa: F401
        from .fetch.live import SessionGetter
        from .paths import DATA_FILES_DIR
        from . import yamlcache
        live = (yamlcache.load(DATA_FILES_DIR.parent / "config.yaml") or {}).get("live") or {}
        t = live.get("request_timeout") or {}
        sg = SessionGetter(user_agent=live.get("user_agent") or "ikimonobiyori", connect_s=t.get("connect_s", 10), read_s=t.get("read_s", 30))
        getter = lambda u: sg.get_bytes(u, R["max_bytes"])        # noqa: E731
        closer = sg.close
    g0 = budget(getter)

    def g(u):                                            # 同じサイト(www の有無・http/https の違いだけ)への転送は 1 回だけ追う
        res = g0(u)
        if res[0] in (301, 302, 303, 307, 308):
            loc = ((res[2] or {}).get("Location") or (res[2] or {}).get("location") or "")
            nu = urljoin(u, loc)
            nh = (urlsplit(nu).hostname or "").lower()
            if loc and urlsplit(nu).scheme in ("http", "https") and (nh[4:] if nh.startswith("www.") else nh) == bare:
                res = g0(nu)
        return res
    try:
        p = urlsplit(url)
        rs, rbody, _h = g(urlunsplit((p.scheme, p.netloc, "/robots.txt", "", "")))
        rtxt = rbody.decode("utf-8", errors="replace") if isinstance(rbody, bytes) else (rbody or "")
        if rs == 200 and not robots_allows(rtxt, url):
            return {"ok": False, "reason": "robots.txt が拒否している。読まない(人が開く URL にする)"}
        if rs not in (200, 404, 410):
            return {"ok": False, "reason": f"robots.txt を確かめられない(HTTP {rs})。安全側で読まない"}
        if not st.get("first_at"):
            st["first_at"] = now.isoformat()
        if not st.get("question"):                       # 段階82 第3部 4: 同じ質問で調べるのは 1 回だけ(資料を作り直したら調べる節を出さない)
            st["question"] = _brief_question(bid, env)
        status, body, headers = g(url)
    except Exception as ex:                              # 通信の失敗は理由を返す(答えは今の記録で)
        return {"ok": False, "reason": f"取得できなかった({type(ex).__name__})"}
    finally:
        if closer:
            closer()
    st["pages"].append({"url": url, "at": now.isoformat(), "status": status})
    _save_state(bid, st, env)
    if status != 200:
        return {"ok": False, "status": status, "reason": f"HTTP {status}"}
    ctype = (headers or {}).get("Content-Type") or (headers or {}).get("content-type") or ""
    raw = body if isinstance(body, bytes) else (body or "").encode("utf-8")
    if len(raw) > R["max_bytes"]:
        return {"ok": False, "reason": "大きすぎるページ"}
    if "pdf" in ctype.lower() or url.lower().endswith(".pdf"):
        text = _pdf_text(raw, env)
        op = operator_text(None, text)
    else:
        html = raw.decode(_charset(ctype, raw), errors="replace")
        text = html_text(html)
        op = operator_text(html, text)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps({"url": url, "fetched_at": now.isoformat(), "status": status, "text": text, "operator": op}, ensure_ascii=False), encoding="utf-8")
    if declared:
        if not _verified(text, declared, op):
            return {"ok": False, "reason": f"ページの運営者の欄(フッター・著作権表示・運営者情報)に発行元の名前「{declared}」がない。公式のページとして読まない"}
        st["pages"][-1]["publisher_verified"] = declared
        _save_state(bid, st, env)
    return {"ok": True, "status": status, "text": text, "path": str(cp), "from_cache": False}


def _charset(ctype, raw):
    m = re.search(r"charset=([\w-]+)", ctype or "", re.I) or re.search(rb"charset=[\"']?([\w-]+)", raw[:3000] or b"", re.I)
    cs = m.group(1) if m else "utf-8"
    cs = cs.decode("ascii", errors="ignore") if isinstance(cs, bytes) else cs
    try:
        "".encode(cs)
        return cs
    except LookupError:
        return "utf-8"


def _pdf_text(raw, env=None):
    import tempfile
    from . import pdf_text as PT
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir=str(rdir(env).parent) if rdir(env).parent.exists() else None) as f:
        f.write(raw)
        path = f.name
    try:
        return PT.extract_with_pdfminer(path) or ""
    except Exception:
        return ""
    finally:
        try:
            import os
            os.unlink(path)
        except OSError:
            pass


def _note_page(bid, url, now, env, cached=False, publisher=None):
    st = _load_state(bid, env)
    st["pages"].append({"url": url, "at": now.isoformat(), "cached": cached, **({"publisher_verified": publisher} if publisher else {})})
    _save_state(bid, st, env)


# ---- 記録 ----

def record(items, bid, *, question=None, env=None, now=None):
    """調べた名所(本文で確かめたもの)を記録する。→ {written, rejected: [{index, errors}], pending_sources}。
    items: [{subject(flowers/birds), name, prefecture, city, kind, typical, notice, url, publisher, current_status_page(bool)}]"""
    from . import observations as O
    R = cfg()
    now = now or datetime.now().astimezone().replace(microsecond=0)
    st = _load_state(bid, env)
    read_urls = {p["url"] for p in st["pages"]}
    verified = {p["url"]: p["publisher_verified"] for p in st["pages"] if p.get("publisher_verified")}
    ok, rejected, pend, src_index, cand = [], [], [], [], []
    for i, it in enumerate(items or []):
        errs = []
        if not isinstance(it, dict):
            rejected.append({"index": i, "errors": ["JSON のオブジェクトではない"]})
            continue
        bad = [k for k in R["forbidden_fields"] if it.get(k)]
        if bad:
            errs.append(f"今年の現況・実用情報は記録しない: {bad}")
        if it.get("url") not in read_urls:
            errs.append("この質問で ask research fetch で読んだページの URL ではない")
        elif allowed_page(it["url"]) and it["url"] not in verified:
            errs.append(allowed_page(it["url"]))
        elif it["url"] in verified and not it.get("publisher"):
            it = {**it, "publisher": verified[it["url"]]}
        if it.get("subject", "flowers") not in R["kinds"]:
            errs.append(f"subject は {R['kinds']} のどれか")
        if not it.get("name") or not it.get("kind"):
            errs.append("name と kind(見られる種)が要る")
        if it.get("typical") and re.search(R["event_period_re"], it["typical"]):
            errs.append("行事の期間(まつり・開催日)を例年の時期にしない。本文に「例年の見頃」などの記載があるときだけ typical に書く")
        if it.get("typical") and re.search(R["omitted_month_re"], it["typical"]):
            errs.append("例年の時期の範囲で後ろの月を省かない(「4月上旬〜下旬」ではなく「4月上旬〜4月下旬」)")
        if not it.get("typical"):                       # 名所の記録は種と例年の時期が要る(observations の決まり。notice は添えるだけ)
            errs.append("typical(例年の時期)が要る(notice は添えるだけ。「行く前に」だけなら ask record で basis: page)")
        if errs:
            rejected.append({"index": i, "errors": errs})
            continue
        rec = {k: it[k] for k in R["fields"] if it.get(k)}
        mark = {"at": now.isoformat(), "brief": bid, "question": (question or "")[:80]}
        if it["url"] in verified:                       # 本人の判断(2026-11-11): 独自ドメインを発行元の名前で読んだ記録には印を付ける
            mark["declared_publisher"] = verified[it["url"]]
        rec.update(subject=it.get("subject", "flowers"), source_class="official", basis="page", research=mark)
        ok.append(rec)
        src_index.append(i)
        cand.append({"url": it["url"], "publisher": it.get("publisher"), "name": it.get("name"), "kind": it.get("kind"),
                     "found_at": now.isoformat(), "brief": bid, "approval": "pending"} if it.get("current_status_page") else None)
    res = O.record(ok, env=env, now=now) if ok else {"written": 0, "rejected": []}
    bad_rows = set()
    for r in res.get("rejected") or []:
        bad_rows.add(r["index"])
        rejected.append({"index": src_index[r["index"]], "errors": r["errors"]})
    known = {x.get("url") for x in _pending_rows(env)}
    for j, x in enumerate(cand):                       # 記録が拒否された件・すでにある URL は、承認待ちの候補に足さない
        if x and j not in bad_rows and x["url"] not in known:
            pend.append(x)
            known.add(x["url"])
    if pend:
        p = rdir(env) / "pending_sources.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="") as f:
            for x in pend:
                f.write(json.dumps(x, ensure_ascii=False) + NL)
    return {"written": res.get("written", 0), "duplicates": res.get("duplicates", 0), "rejected": rejected, "pending_sources": len(pend)}


def listing(env=None):
    """その場で調べた記録の一覧(本人の見直し用)。"""
    from . import observations as O
    out = []
    for sj in cfg()["kinds"]:
        p = O.log_path(sj, env)
        if not p.exists():
            continue
        for l in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(l)
            except ValueError:
                continue
            if isinstance(r.get("research"), dict):
                out.append({"at": r["research"].get("at"), "subject": sj, "name": r.get("name"), "prefecture": r.get("prefecture"),
                            "city": r.get("city"), "kind": r.get("kind"), "typical": r.get("typical"), "notice": r.get("notice"),
                            "url": r.get("url"), "publisher": r.get("publisher"), "question": r["research"].get("question"),
                            "declared_publisher": r["research"].get("declared_publisher"),
                            "via": "独自ドメイン(本文の発行元の名前で確かめた)" if r["research"].get("declared_publisher") else "公式の一覧のホスト"})
    return {"records": sorted(out, key=lambda r: r.get("at") or ""), "pending_sources": _pending_rows(env)}


def _pending_rows(env=None):
    p = rdir(env) / "pending_sources.jsonl"
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out
