"""段階75 第1部: ガイドの資料(`ask brief`)。通信しない。

今の計画(ask answer と同じ材料・同じ候補の選び方)から、AI がガイドとして答えを書くための資料を 1 つにまとめる:
質問と日付・候補と順位・確かめた事実(F001…。照らす値を項目に分けて持つ)・知識カード(K001…)・足りないもの・決まり。
骨組み(skeleton)と整え(polish)は通さない。資料はデータ置き場の briefs/<id>.json と、人が読む briefs/<id>.md。
同じ質問・同じ now・同じ記録なら同じ資料(決定的。作業の時刻・作業フォルダの名前は資料に入れない)。
承認待ちの情報源の事実と、使わない情報源(予想・転載)の事実は入れない。
値と語は data/ask/guide_mode.yaml。照らす値の取り出し(values)は ask verify --brief(guide_verify.py)と同じ関数。"""
import hashlib
import json
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from . import yamlcache
from .paths import DATA_FILES_DIR, data_path

CONFIG = DATA_FILES_DIR / "ask" / "guide_mode.yaml"
NL = "\n"
URL_RE = re.compile(r"https?://[^\s)）」>]+")


def cfg():
    return yamlcache.load(CONFIG)


def answer_form(c=None):
    """答えの形の切り替え(classic / guide)。既定は今までの形。"""
    c = c or cfg()
    f = c.get("answer_form") or "classic"
    return f if f in (c.get("answer_forms") or ["classic"]) else "classic"


# ---- 照らす値の取り出し(資料と裏取りで同じ関数) ----

_Z2H = str.maketrans("０１２３４５６７８９：／－～", "0123456789:/-〜")


def _h(s):
    return (s or "").translate(_Z2H).replace("～", "〜")


def norm_state(w, c=None):
    c = c or cfg()
    for a, b in (c.get("state_norm") or {}).items():
        w = w.replace(a, b)
    return w


_ERA = {"令和": 2018, "平成": 1988, "昭和": 1925}


def seireki(text):
    """和暦の年(令和8年・平成27年度・令和元年)を西暦(2026年)にする(段階77 第1部 4)。"""
    def rep(m):
        n = 1 if m.group(2) == "元" else int(m.group(2))
        return f"{_ERA[m.group(1)] + n}年" + (m.group(3) or "")
    return re.sub(r"(令和|平成|昭和)(元|\d{1,2})年(度)?", rep, text or "")


def values(text, c=None):
    """文 → 照らす値 {dates: [M/D], years, months: [M], jun: [M月上旬…], times: [H:MM], money: [数], phones: [数字], urls, states}。
    和暦は西暦として読む(段階77)。"""
    c = c or cfg()
    raw = seireki(text or "")
    urls = sorted(set(URL_RE.findall(raw)))
    t = _h(URL_RE.sub(" ", raw))
    dates, years, months, jun, times, money, phones = set(), set(), set(), set(), set(), set(), set()
    for m in re.finditer(r"(?<!\d)(\d{3,4})-(\d{2,4})-(\d{4})(?!\d)|(?<!\d)0\d{1,4}-\d{1,4}-\d{3,4}(?!\d)", t):
        phones.add(re.sub(r"\D", "", m.group(0)))
    t2 = re.sub(r"(?<!\d)0\d{1,4}-\d{1,4}-\d{3,4}(?!\d)", " ", t)
    for m in re.finditer(r"(\d{4})-(\d{1,2})-(\d{1,2})", t2):
        years.add(m.group(1))
        dates.add(f"{int(m.group(2))}/{int(m.group(3))}")
        months.add(str(int(m.group(2))))
    t3 = re.sub(r"\d{4}-\d{1,2}-\d{1,2}(T[\d:+]+)?", " ", t2)
    for m in re.finditer(r"(\d{4})年", t3):
        years.add(m.group(1))
    for m in re.finditer(r"(?<![\d.])(\d{1,2})月(\d{1,2})日", t3):
        dates.add(f"{int(m.group(1))}/{int(m.group(2))}")
        months.add(str(int(m.group(1))))
    for m in re.finditer(r"(?<![\d./])(\d{1,2})/(\d{1,2})(?![\d/])", t3):
        mo, d = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            dates.add(f"{mo}/{d}")
            months.add(str(mo))
    for m in re.finditer(r"(?<![\d.])(\d{1,2})月(?!\d)", t3):
        months.add(str(int(m.group(1))))
    for m in re.finditer(r"(?<![\d./])(\d{1,2})\s*[〜~～\-ー]\s*(\d{1,2})月", t3):      # 段階77: 「11〜2月」の前の月も月として読む
        if 1 <= int(m.group(1)) <= 12:
            months.add(str(int(m.group(1))))
    for m in re.finditer(r"(?<![\d.])(\d{1,2})月(上旬|中旬|下旬)", t3):
        jun.add(f"{int(m.group(1))}月{m.group(2)}")
    for m in re.finditer(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", t3):
        times.add(f"{int(m.group(1))}:{m.group(2)}")
    for m in re.finditer(r"(?<![\d月/])(\d{1,2})時(?:(\d{1,2})分)?", t3):
        times.add(f"{int(m.group(1))}:{int(m.group(2) or 0):02d}")
    for m in re.finditer(r"([\d,]+)\s*円", t3):
        money.add(m.group(1).replace(",", ""))
    if "無料" in t3:
        money.add("無料")
    people = {m.group(1) for m in re.finditer(r"(?<![\d:])(\d+)\s*(?:人|名)(?!所|物)", t3)}
    states = sorted({norm_state(w, c) for w in c["state_words"] if w in t3})
    return {"dates": sorted(dates), "years": sorted(years), "months": sorted(months), "jun": sorted(jun), "times": sorted(times),
            "money": sorted(money), "phones": sorted(phones), "urls": urls, "states": states, "people": sorted(people)}


def has_any(words, s):
    return any(w in (s or "") for w in words)


# ---- 資料の材料 ----

def _md(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None
    return f"{d.month}/{d.day}"


def _pending_urls():
    """台帳で承認されていない情報源の URL(資料に入れない)。"""
    from . import sources as S
    out = set()
    for p in sorted((DATA_FILES_DIR / "sources").glob("*.yaml")):
        if p.name == "policy.yaml":
            continue
        try:
            doc = yamlcache.load(p) or {}
        except (OSError, ValueError):
            continue
        for s in doc.get("sources") or []:
            if s.get("url") and not S.is_approved(s):
                out.add(s["url"])
    return out


def _usable_url(url, pending):
    from . import publisher as P
    if not url:
        return True
    if url in pending:
        return False
    return not P.unused_source(url, state=True)


def _source_class(url, given=None):
    """発行元の区分。URL があれば、ホストだけで決める(記録ごとの区分の違いで、同じ発行元が答えによって分かれないように。段階77)。
    公式: 町・市・県・国のページ・当事者のサイト(publisher.shows_official)、台帳・施設・行事の一覧で class: official のホスト、
    承認済みの情報源のホスト、guide_mode.yaml の official_hosts。URL がなければ渡された区分。"""
    from . import publisher as P
    if not url:
        return given if given in ("official", "secondary") else None
    host_names()
    if P.host_of(url) in _approved_hosts():
        return "official"
    if url and (P.shows_official(url) or P.host_of(url) in _OFFICIAL_HOSTS or P.host_of(url) in set(cfg().get("official_hosts") or [])):
        return "official"
    return "secondary" if url else None


class _Facts:
    def __init__(self, c, pending):
        self.c, self.pending, self.rows, self.keys = c, pending, [], set()

    def add(self, kind, content, *, place=None, source=None, url=None, source_class=None, observed=None, read_at=None, extra=None):
        content = seireki(re.sub(r"\s+", " ", (content or "").strip()))
        if not content or not _usable_url(url, self.pending):
            return None
        key = (kind, content, url)
        if key in self.keys:
            return None
        self.keys.add(key)
        v = values(content + " " + " ".join(str(x) for x in (extra or {}).values() if x), self.c)
        row = {"id": f"F{len(self.rows) + 1:03d}", "kind": kind, "kind_label": self.c["kinds"][kind], "place": place, "content": content,
               "values": v, "source": source, "source_class": _source_class(url, source_class), "url": url,
               "observed": observed, "read_at": read_at}
        if extra:
            row["fields"] = extra
        self.rows.append(row)
        return row


def _candidate_facts(F, c_row, pick=None):
    name = c_row.get("name")
    cur = c_row.get("current") or {}
    if cur.get("state") or cur.get("state_raw"):
        md = _md(cur.get("state_date"))
        st = cur.get("display") or cur.get("state_raw") or cur.get("state")
        F.add("current", f"{name}: {st}" + (f"({md}時点、{cur.get('publisher')})" if md else f"({cur.get('publisher')}。日付なし)"),
              place=name, source=cur.get("publisher"), url=cur.get("url"), source_class=cur.get("source_class"),
              observed=cur.get("state_date"), read_at=cur.get("read_at"),
              extra={"state": cur.get("state_raw") or cur.get("state"), "state_norm": cur.get("state"),
                     "freshness": cur.get("freshness_label")})
    for t in c_row.get("typical") or []:
        if t.get("text"):
            F.add("typical", f"{name}: 例年 {t['text']}", place=name, source=t.get("publisher"), url=t.get("url"),
                  source_class=t.get("source_class"), extra={"year": t.get("year")})
    for fe in (pick or {}).get("festivals") or c_row.get("festivals") or []:
        if isinstance(fe, dict) and fe.get("name"):
            body = "。".join(x for x in (fe.get("period_line"), fe.get("lightup_line")) if x)
            F.add("event", f"{name}: {fe['name']}" + (f"({body})" if body else ""), place=name, source=fe.get("publisher"),
                  url=fe.get("url"), source_class=fe.get("source_class"))
    for ev in c_row.get("events") or []:
        if isinstance(ev, dict):
            txt = "・".join(str(ev[k]) for k in ("name", "period", "text", "start", "end") if ev.get(k))
            F.add("event", f"{name}: {txt}", place=name, source=ev.get("publisher"), url=ev.get("url"), source_class=ev.get("source_class"))
    for p in (c_row.get("practical") or []) + (c_row.get("notices") or []):
        if isinstance(p, dict):
            txt = p.get("text") or p.get("line") or p.get("value")
            kind = "safety" if has_any(F.c["closure_words"], txt or "") else "facility"
            F.add(kind, f"{name}: {txt}", place=name, source=p.get("publisher"), url=p.get("url"), source_class=p.get("source_class"))
        elif isinstance(p, str):
            F.add("facility", f"{name}: {p}", place=name)
    for k in ("hours", "closed"):
        v = c_row.get(k)
        if isinstance(v, dict) and (v.get("text") or v.get("line")):
            F.add("facility", f"{name}: {v.get('text') or v.get('line')}", place=name, source=v.get("publisher"), url=v.get("url"))
        elif isinstance(v, str) and v:
            F.add("facility", f"{name}: {v}", place=name)


def _line_kind(line, c):
    if has_any(c.get("not_current_words") or [], line):
        return "typical"
    for r in c["line_kinds"]:
        if has_any(r["words"], line):
            return r["kind"]
    return "other"


def _perishable(line, c):
    v = values(line, c)
    return any(v[k] for k in ("dates", "months", "times", "money", "phones", "states")) or has_any(c["event_words"] + c["closure_words"], line)


def split_body(text, heading):
    """答え → (本文の行, 出典の URL)。"""
    lines = (text or "").splitlines()
    i = next((k for k, l in enumerate(lines) if l.strip() == heading), len(lines))
    urls = [u for l in lines[i + 1:] for u in URL_RE.findall(l)]
    return lines[:i], urls


_HOSTS = None
_OFFICIAL_HOSTS = set()
_APPROVED = None


def _approved_hosts():
    """承認済みの情報源(台帳)のホスト。"""
    global _APPROVED
    if _APPROVED is None:
        from . import publisher as P
        from . import sources as S
        out = set()
        for p in sorted((DATA_FILES_DIR / "sources").glob("*.yaml")):
            if p.name == "policy.yaml":
                continue
            try:
                doc = yamlcache.load(p) or {}
            except (OSError, ValueError):
                continue
            for src in doc.get("sources") or []:
                if src.get("url") and S.is_approved(src) and src.get("publisher_kind") not in ("introduction", "secondary", "media"):
                    out.add(P.host_of(src["url"]))
        _APPROVED = out
    return _APPROVED


def host_names(env=None):
    """ホスト → 発行元・施設の名前(台帳・施設・行事・名所の一覧と、データ置き場の観察の記録から)。答えの行に URL を結びつけるため。"""
    global _HOSTS
    if _HOSTS is not None:
        return _HOSTS
    from . import publisher as P
    out = {}

    def walk(o):
        if isinstance(o, dict):
            us = [v for k, v in o.items() if isinstance(k, str) and k.endswith("url") and isinstance(v, str) and v.startswith("http")]
            for u in us:
                h = P.host_of(u)
                if o.get("class") == "official" or o.get("source_class") == "official":
                    _OFFICIAL_HOSTS.add(h)
                for k in ("publisher", "facility", "name", "organizer", "operator"):
                    v = o.get(k)
                    if isinstance(v, str) and len(v) >= 3 and not re.fullmatch(r"[a-z0-9_-]+", v):
                        out.setdefault(h, set()).add(v)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for rel in ("facility_events/events.yaml", "visitor_centers/centers.yaml", "observations/spots.yaml", "observations/festivals.yaml"):
        try:
            walk(yamlcache.load(DATA_FILES_DIR / rel))
        except (OSError, ValueError):
            pass
    for p in sorted((DATA_FILES_DIR / "sources").glob("*.yaml")):
        try:
            walk(yamlcache.load(p))
        except (OSError, ValueError):
            pass
    for p in sorted(data_path("observations", env).glob("*.jsonl")) if data_path("observations", env).exists() else []:
        try:
            for l in p.read_text(encoding="utf-8").splitlines():
                try:
                    walk(json.loads(l))
                except ValueError:
                    continue
        except OSError:
            pass
    try:                                                  # 知識カードの出典(発行元の名前と URL)
        from . import knowledge as K
        walk([r.get("source") for r in K.load(env)])
    except (OSError, ValueError):
        pass
    _HOSTS = out
    return out


def _official_name(name, c):
    return bool(name) and bool(re.search(c.get("official_name_re") or r"$^", name))


def _line_facts(F, text, c, known_pubs, skip_blocks=False):
    """コードの答え(4つの検査に通った文)の行のうち、腐りやすい値を含む行を事実にする。出典は行の中の発行元の名前から。
    skip_blocks: 計画の答えの候補の塊(①〜の行から空行まで)は、候補の事実(構造化)と重なるので入れない。
    見込み・選び方の文(line_skip_words)は事実ではないので入れない。"""
    from . import publisher as P
    body, urls = split_body(text, c["final"]["sources_heading"])
    by_name = dict(known_pubs)
    for u in urls:
        n = P.name(u)
        if n and n not in by_name:
            by_name[n] = u
    cls = {f["url"]: f["source_class"] for f in F.rows if f.get("url") and f.get("source_class")}
    hn = host_names()
    for u in urls:                                       # 台帳・施設・記録の名前(施設名・発行元)でも行と URL を結ぶ
        for n in sorted(hn.get(P.host_of(u)) or []):
            by_name.setdefault(n, u)
    in_block = False
    ctx = None
    for line in body:
        if not line.strip():
            in_block, ctx = False, None
        st = line.strip()
        mb = re.match(r"^[①-⑳]\s*(.+?)(?:\s+約\d+km)?$", st)       # 計画の答えの候補の行(「① 白鳥橋(長瀞) 約87km」)
        if mb:
            in_block, ctx = True, mb.group(1).strip()
            continue
        if in_block and skip_blocks and not line.lstrip().startswith("・"):
            in_block = False
        m = re.match(r"^\*\*(.+?)\*\*", st)                  # 名所の見出しの行(「**霧降高原 キスゲ平園地**(栃木県日光市) 約140km」)
        if m and not st.startswith("**" + m.group(1) + "**" + "の"):
            ctx = m.group(1)
        if st.startswith("#") or (m and st == f"**{m.group(1)}**"):
            continue
        s = re.sub(r"\*\*", "", st).lstrip("・-# ").strip()
        s = re.sub(r"^[①-⑳]\s*", "", s)
        if not s or s.startswith("http") or has_any(c.get("line_skip_words") or [], s):
            continue
        if not _perishable(s, c) and len(s) < c.get("min_plain_line_chars", 0):
            continue
        place = None
        if ctx and line.lstrip().startswith("・") and ctx not in s:
            s, place = f"{ctx}: {s}", ctx
        elif ctx and m:
            place = ctx
        hit = sorted((n for n in by_name if n and n in s), key=len, reverse=True)
        url = by_name[hit[0]] if hit else (URL_RE.findall(s) or [None])[0]
        if url is None and len(set(urls)) == 1:          # 出典が 1 つだけの答え
            url = urls[0]
            hit = [P.name(url)] if P.name(url) else []
        src = None
        pm = None if m else re.search(r"[(（]([^()（）\d]{2,30})[)）]\s*[。]?$", s)    # 行の終わりの括弧の発行元(名所の見出しの行の括弧は所在地)
        if pm and not has_any(c.get("not_publisher_words") or [], pm.group(1)) and re.search(c["publisher_name_re"], pm.group(1)):
            src = pm.group(1)
        if src is None:
            src = next((h for h in hit if h in known_pubs or re.search(c["publisher_name_re"], h)), None)
        if src is None and url:                          # URL のホストの台帳の名前(発行元らしいもの)
            src = next((h for h in sorted(hn.get(P.host_of(url)) or [], key=len) if re.search(c["publisher_name_re"], h)), None)
        kind = _line_kind(s, c) if _perishable(s, c) else "other"
        sc = cls.get(url) or (_source_class(url) if url else ("official" if _official_name(src, c) else None))
        F.add(kind, s, place=place, source=src, url=url, source_class=sc)


def _target_months(cond, now):
    ms = []
    for ds in cond.get("periods") or []:
        for x in ds:
            try:
                m = date.fromisoformat(x).month
            except (TypeError, ValueError):
                continue
            if m not in ms:
                ms.append(m)
    return ms or [now.month]


def _theme_words(question, subjects, c):
    """質問の語と対象 → テーマの語(カードを引く語)。"""
    out = []
    for t in c["card_themes"]:
        if t.get("subject") in (subjects or []) or any(w in (question or "") for w in t.get("question_words") or []):
            out += [w for w in t["words"] if w not in out]
    return out


def _is_closure(card):
    return isinstance(card.get("closure"), dict)


def _real_place(name):
    """名所・エリア・地域・出発地・山の辞書にある場所の名前か、場所の形の名前か(知識カードの場所の名前は数えない)。"""
    from . import areas as AR
    from . import guide_verify as GV
    from . import place_guard as PG
    if not name:
        return False
    if PG._norm(name) in PG.known_names() or AR.resolve(name) or name in GV._site_names():
        return True
    return bool(re.search(cfg()["place_suffix_re"], name))


def _real_or_asked(p, question):
    """場所の名前か(辞書にある・場所の形の名前・質問の場所らしい語)。"""
    from . import place_guard as PG
    try:
        asked = p in PG.candidates(question)
    except (KeyError, TypeError, ValueError):
        asked = False
    return _real_place(p) or asked


def _general_card(card, c):
    """一般の話(テーマ)のカードか: 場所の欄がテーマの語(冬桜・野鳥・紅葉・渡り鳥・カモなど)で、場所の名前でない。"""
    pl = card.get("place") or ""
    words = {w for t in c["card_themes"] for w in t["words"]} | set(c.get("general_place_words") or [])
    return any(w in pl for w in words) and not _real_place(pl)


def _broad_place(name):
    """都道府県・地域の呼び名(場所のカードを引くには広すぎる)。"""
    from . import sources as S
    if re.search(r"(都|道|府|県)$", name or ""):
        return True
    for r in S.load_regions()["regions"]:
        if name in [r["name"], *(r.get("aliases") or [])]:
            return True
    return False


def _place_cards(rows, places, c):
    """場所の名前に結びつくカード(分類の優先の順)。"""
    from . import knowledge as K
    pri = {k: i for i, k in enumerate(c.get("brief_category_order") or K.cfg()["category_priority"])}
    ps = [p for p in places if p and len(p) >= 2]
    hits = [r for r in rows if not _general_card(r, c) and any(K.place_match(r, p) for p in ps)]
    return sorted(hits, key=lambda r: (pri.get(r.get("category"), len(pri)), r.get("title") or ""))


def _cards(question, res, c, cand_names=(), months=(), event_texts=()):
    """知識カード(最大 max_cards 枚)。場所・種に結びつくカードを先に、続けてテーマと季節のカード。
    カードごとに結びつき(link): この場所の話 / この種の話 / 一般の話(テーマ)。冬季閉鎖のカードは事実の側に入れるので除く。"""
    from . import intent
    from . import knowledge as K
    L = c["card_links"]
    try:
        shown = [r for r in K.load_shown() if not _is_closure(r)]
    except (OSError, ValueError):
        shown = []
    out, seen = [], set()

    def push(rows, link, limit=None):
        n = 0
        for r in rows or []:
            t = r.get("title")
            if limit is not None and n >= limit:
                return
            if t and (t, r.get("place")) not in seen and len(out) < c["max_cards"]:
                seen.add((t, r.get("place")))
                out.append((r, link))
                n += 1
    event_q = (res.get("route") or (res.get("cond") or {}).get("route")) == "event" or (res.get("cond") or {}).get("intent") == "event"
    if event_q:                                           # 段階77 第1部 2: 行事の質問は、行事の場所・対象に直接結びつくカードだけ
        from . import guide_verify as GV
        names = sorted({n for n in GV._dictionary_places() for f in event_texts if n in f}, key=len, reverse=True)
        push([r for r in _place_cards(shown, names, c) if _real_place(r.get("place") or "")], L["place"], c["place_cards_max"])
        return _card_rows(out, c)
    themew = {w for t in c["card_themes"] for w in t["words"]}
    places = [p for p in _question_places(question, res) if len(p) >= 2 and not _broad_place(p) and not any(w in p for w in themew)]
    pc = _place_cards(shown, places, c)[: c["place_cards_max"]]
    def is_place(r):
        return _real_place(r.get("place") or "") or any(K.place_match(r, p) and _real_or_asked(p, question) for p in places)
    push([r for r in pc if is_place(r)], L["place"])
    push([r for r in pc if not is_place(r)], L["species"])     # 場所の欄が種・現象の名前(冬桜など)
    words = [w for w in re.findall(c["species_word_re"], question or "") if w not in c["not_species_words"]]
    if words:                                             # 質問の種・現象の名前(ニッコウキスゲ・カワセミ・冬桜)
        sp = [r for r in shown if any(w in " ".join([r.get("title") or "", r.get("subject") or "", r.get("place") or ""]
                                                     + list(r.get("facts") or [])) for w in words)]
        sp.sort(key=lambda r: (not any(w in (r.get("subject") or "") + (r.get("title") or "") for w in words), r.get("title") or ""))
        push(sp, L["species"], c["species_cards_max"])
    try:                                                  # 質問の話題のカード(種の名前で引けたもの以外は一般の話として扱う)
        push([r for r in intent.cards_for(question) if _general_card(r, c)], L["theme"], c["species_cards_max"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    if cand_names:                                        # 答えに選んだ候補の場所のカード(上から)
        push(_place_cards(shown, list(cand_names)[: c["cand_card_places"]], c), L["place"], c["cand_cards_max"])
    plan_like = (res.get("route") or (res.get("cond") or {}).get("route")) == "plan"
    tw = _theme_words(question, (res.get("cond") or {}).get("subjects") or [] if plan_like and not places else [], c)   # 場所・知識の質問は質問の語のテーマだけ
    if tw and len(out) < c["max_cards"]:
        theme = []
        for r in shown:
            if not _general_card(r, c):
                continue                                  # 特定の場所のカードは一般の話にしない
            ms = (r.get("condition") or {}).get("months") or []
            if ms and months and not set(ms) & set(months):
                continue
            blob = " ".join([r.get("title") or "", r.get("subject") or "", r.get("place") or ""] + list(r.get("facts") or []))
            hit = sum(1 for w in tw if w in blob)
            if hit:
                theme.append((-hit, r.get("title") or "", r))
        push([r for _h, _t, r in sorted(theme, key=lambda x: (x[0], x[1]))], L["theme"])
    return _card_rows(out, c)


def _card_rows(out, c):
    rows = []
    for i, (r, link) in enumerate(out, 1):
        src = r.get("source") or {}
        facts = [seireki(x) for x in r.get("facts") or []]
        rows.append({"id": f"K{i:03d}", "title": r.get("title"), "category": r.get("category"), "place": r.get("place"), "link": link,
                     "facts": facts, "months": (r.get("condition") or {}).get("months"), "confidence": r.get("confidence"),
                     "source": src.get("name"), "url": src.get("url"), "checked_on": src.get("checked_on"),
                     "source_class": _source_class(src.get("url")), "values": values(" ".join(facts), c)})
    return rows


# ---- 例年の目安の候補(段階76 第1部) と 冬季閉鎖(第4部) ----

def _group_of(pref, c):
    for g in c["region_groups"]:
        if pref in g["prefectures"]:
            return g["name"]
    return None


def _covers(window, mds):
    if not isinstance(window, dict) or not window.get("start") or not window.get("end"):
        return False
    s, t = window["start"], window["end"]
    return any((s <= md <= t) if s <= t else (md >= s or md <= t) for md in mds)


def _origin_pref(origin):
    from . import origins
    try:
        o = origins.lookup(origin) or {}
    except (KeyError, TypeError, ValueError):
        o = {}
    return o.get("prefecture") or "神奈川県"


def typical_candidates(cond, now, scope, existing, c, pending):
    """今年の現況はないが、例年の時期が対象の日に当たる名所(ガイドのカタログから)。
    範囲が広い(wide): 地域の組ごとに最大 per_group 件。そのほか: 出発地の地域の組の外から 1 組 1 件で far_total 件まで。"""
    from . import guide
    from . import publisher as P
    themes = [t for sj in cond.get("subjects") or [] for t in c["typical_themes"].get(sj) or []]
    if not themes:
        return []
    mds = [x[5:10] for ds in cond.get("periods") or [] for x in ds] or [now.strftime("%m-%d")]
    origin = cond.get("origin")
    try:
        entries = guide.build()[0]
    except (OSError, ValueError, KeyError):
        return []
    rows = []
    for e in entries:
        if not guide.approved(e) or e.get("scope") != "place" or e.get("theme") not in themes or not e.get("prefecture"):
            continue
        if e["name"] in existing:
            continue
        season = e.get("season") or {}
        if not _covers(season.get("window"), mds):
            continue
        rng = (e.get("range") or {})
        by = (rng.get("by_origin") or {}).get(origin) or rng
        if by.get("status") == "out_of_range":
            continue
        src = [x for x in e.get("sources") or [] if x.get("url") and not P.unused_source(x["url"]) and x["url"] not in pending]
        if not src:
            continue
        if season.get("from_url") and (P.unused_source(season["from_url"]) or season["from_url"] in pending):
            continue                                      # 例年の時期の出どころが使わない情報源
        best = sorted(src, key=lambda x: (x.get("class") or "Z", x["url"]))[0]
        kinds = [k["kind"] for k in e.get("kinds") or [] if k.get("shown")]
        rows.append({"name": e["name"], "prefecture": e["prefecture"], "municipality": e.get("municipality"),
                     "group": _group_of(e["prefecture"], c), "theme": e.get("theme"), "text": season.get("text"), "kinds": kinds,
                     "url": best["url"], "publisher": best.get("publisher"),
                     "source_class": "official" if best.get("class") in ("A", "B") else "secondary", "km": by.get("km")})
    rows.sort(key=lambda r: (r["group"] or "~", r["source_class"] != "official", r["km"] or 9999, r["name"]))
    own = _group_of(_origin_pref(origin), c)
    out, per = [], {}
    if scope == "wide":
        for r in rows:
            if r["group"] and per.get(r["group"], 0) < c["typical_candidates"]["per_group"]:
                per[r["group"]] = per.get(r["group"], 0) + 1
                out.append(r)
    else:
        far = sorted([r for r in rows if r["group"] and r["group"] != own],
                     key=lambda r: (r["source_class"] != "official", r["km"] or 9999, r["name"]))
        seen_g = set()
        for r in far:
            if r["group"] not in seen_g and len(out) < c["typical_candidates"]["far_total"]:
                seen_g.add(r["group"])
                out.append(r)
        themes_in = {r["theme"] for r in out}
        for r in sorted(far, key=lambda r: (r["theme"] in themes_in, r["source_class"] != "official", r["km"] or 9999, r["name"])):
            if r not in out and len(out) < c["typical_candidates"]["far_total"]:     # 段階77: 3 件まで埋める(別のテーマ(冬鳥の白鳥など)を先に)
                out.append(r)
    return out


def closures_for(names, months, c):
    """候補・質問の場所に結びつく冬季閉鎖のカード → [(カード, 対象の月に当たるか)]。"""
    from . import knowledge as K
    try:
        rows = [r for r in K.load() if _is_closure(r) and not r.get("retired")]
    except (OSError, ValueError):
        return []
    out = []
    for r in rows:
        keys = [r.get("place")] + list(r.get("place_aliases") or []) + list(r["closure"].get("areas") or [])
        keys = [k for k in keys if k and len(k) >= 2]
        if any(k in n or n in k for k in keys for n in names if n and len(n) >= 2):
            ms = r["closure"].get("typical_months") or []
            out.append((r, bool(set(ms) & set(months))))
    return out


def AR_scope(question, cond):
    from . import answer_plan as AP
    try:
        return AP.scope_of(question, cond.get("origin_source"), cond.get("refine"))
    except (KeyError, TypeError, ValueError):
        return None


def _question_places(question, res):
    from . import highlights as HL
    from . import place_guard as PG
    out = list((res.get("cond") or {}).get("area_names") or [])
    try:                                                  # 見どころの場所(質問に名前があるものだけ。「野鳥」の語から箱根にすり替えない)
        out += [p["name"] for p in HL.places(question) if p["name"] in (question or "") or
                (p.get("label") in (question or "") and _real_place(p.get("label")))]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        out += PG.candidates(question)
    except (KeyError, TypeError, ValueError):
        pass
    return [x for i, x in enumerate(out) if x and x not in out[:i]]


def _dates_block(cond, now):
    from . import sources as S
    wk1 = S.next_weekend(now)
    wk2 = [wk1[-1] + timedelta(days=6), wk1[-1] + timedelta(days=7)]
    return {"today": now.date().isoformat(), "this_weekend": [d.isoformat() for d in wk1], "next_weekend": [d.isoformat() for d in wk2],
            "periods": cond.get("periods"), "defaulted_date": cond.get("defaulted_date")}


def _plan_parts(plan, subject=None):
    """計画の中の (対象, 順位の並び, 選んだ候補, 今年の情報がない候補) を、節・期間・対象ごとに集める。"""
    out = []
    sj = plan.get("subject") if plan.get("subject") not in (None, "all", "areas", "periods") else subject
    if plan.get("ranking") or plan.get("picks"):
        out.append((sj, plan.get("ranking") or [], plan.get("picks") or [], plan.get("no_this_year") or []))
    for seg in plan.get("segments") or []:
        if isinstance(seg.get("plan"), dict):
            out += _plan_parts(seg["plan"], seg.get("subject") or sj)
    for k, sub in (plan.get("subjects") or {}).items():
        if isinstance(sub, dict):
            out += _plan_parts(sub, k)
    return out


def _candidates(workdir, c):
    """候補と順位(対象ごとに上位 max_candidates 件と、答えに選んだ候補すべて)。→ (行, 選んだ候補 {名前: pick}, 補足)"""
    from . import skeleton as SK
    p = Path(workdir) / "answer_plan.json"
    if not p.exists():
        return [], {}, None
    plan = json.loads(p.read_text(encoding="utf-8"))
    parts = _plan_parts(plan)
    picks = {x["name"]: x for x in SK._flat_picks(plan)}
    for _sj, _rk, pk, _ny in parts:
        for x in pk:
            if isinstance(x, dict) and x.get("name"):
                picks.setdefault(x["name"], x)
    rows, seen = [], set()
    for sj, rk, pk, _ny in parts:
        top = [r for r in rk if isinstance(r, dict) and r.get("name")]
        keep = top[: c["max_candidates"]] + [r for r in top[c["max_candidates"]:] if r["name"] in picks]
        if not top:
            keep = [{"rank": i + 1, **x} for i, x in enumerate(x for x in pk if isinstance(x, dict) and x.get("name"))]
        for r in keep:
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            px = picks.get(r["name"]) or {}
            rows.append({"subject": r.get("subject") or px.get("subject") or sj, "rank": r.get("rank"), "name": r["name"],
                         "chosen": r["name"] in picks, "aim": r.get("aim"),
                         "distance_km": r.get("distance_km"), "score": r.get("score"), "breakdown": r.get("breakdown"),
                         "outlook": r.get("outlook_label"), "phrase": px.get("phrase"), "current_state": r.get("current_state"),
                         "current_date": r.get("current_date"), "prefecture": px.get("prefecture"),
                         "not_chosen_reason": r.get("reason_label"), "reasons": list(px.get("reason_labels") or [])})
    no_year = []
    for _sj, _rk, _pk, ny in parts:
        no_year += [x.get("name") for x in ny if isinstance(x, dict) and x.get("name") and x.get("name") not in no_year]
    return rows, picks, {"no_this_year": no_year, "origin_line": plan.get("origin_line")}


def _missing(question, res, cands, facts, cards, extra):
    from . import place_guard as PG
    out = []
    for t in res.get("research_targets") or []:
        out.append(f"記録が足りない: {t.get('what')}" + (f"({t.get('where')})" if t.get("where") else ""))
    sp = res.get("season_place") or {}
    for m in sp.get("missing") or []:
        out.append(f"名所と例年の時期の記録がない種: {m}")
    for r in cands:
        if r["chosen"] and not r.get("current_state"):
            out.append(f"今年の現況がない候補: {r['name']}")
    if extra and extra.get("no_this_year"):
        out.append("今年の情報が確認できていない候補: " + "、".join(extra["no_this_year"]))
    if cands and not any(r.get("current_state") for r in cands):
        out.append("今年の現況の記録がある候補がない")
    try:
        qplaces = PG.candidates(question)
    except (KeyError, TypeError, ValueError):
        qplaces = []
    for p in qplaces:
        n = sum(1 for f in facts if p in f["content"])
        out.append(f"「{p}」についての確かめた事実は {n} 件")
    if not cards:
        out.append("この質問に結びつく知識カードがない")
    if not facts:
        out.append("確かめた事実がない(今年の状況・日付・行事は書けない)")
    if res.get("stage") in (3, 4):
        out.append("コードの答えも一部しか作れなかった(記録が少ない)")
    return out


def brief_id(question, now, prev=None):
    h = hashlib.sha1(json.dumps([question, now.isoformat(), prev or ""], ensure_ascii=False).encode("utf-8")).hexdigest()[:8]
    return f"b{now.strftime('%Y%m%d')}-{h}"


def brief_dir(env=None):
    return data_path(cfg()["brief_dir"], env)


def load(bid, env=None):
    return json.loads((brief_dir(env) / f"{bid}.json").read_text(encoding="utf-8"))


def build(question, *, now, env=None, prev=None, clock=None, obs_kw=None):
    """質問の文 → 資料(dict)。今の ask answer と同じ材料・同じ計画を、記録を残さずに(quiet)作る。"""
    from . import answer_run as AR
    c = cfg()
    bid = brief_id(question, now, prev)
    work = brief_dir(env) / f"{bid}.work"
    if work.exists():
        shutil.rmtree(work)                              # 同じ資料の作り直し(前回の作業の残りで結果を変えない)
    res = AR.run(question, now=now, env=env, workdir=work, quiet=True, clock=clock, obs_kw=obs_kw)
    cond = res.get("cond") or {}
    pending = _pending_urls()
    F = _Facts(c, pending)
    cands, picks, extra = _candidates(work, c)
    fpath = work / "facts.json"
    known_pubs = {}
    if fpath.exists():
        facts_doc = json.loads(fpath.read_text(encoding="utf-8"))
        by = {}
        for sj, sub in (facts_doc.get("subjects") or {}).items():
            for cr in sub.get("candidates") or []:
                by.setdefault(cr["name"], cr)
                cur = cr.get("current") or {}
                if cur.get("publisher") and cur.get("url"):
                    known_pubs.setdefault(cur["publisher"], cur["url"])
        for name in [r["name"] for r in cands] + list((extra or {}).get("no_this_year") or []):
            if name in by:
                _candidate_facts(F, by[name], picks.get(name))
    _line_facts(F, res.get("text") or "", c, known_pubs, skip_blocks=bool(cands))
    if prev:
        try:
            pb = load(prev, env)
            for f in pb.get("facts", [])[: c["max_prev_facts"]]:
                F.add(f["kind"], f["content"], place=f.get("place"), source=f.get("source"), url=f.get("url"),
                      source_class=f.get("source_class"), observed=f.get("observed"), read_at=f.get("read_at"), extra=f.get("fields"))
        except (OSError, ValueError, KeyError):
            pb = None
    else:
        pb = None
    months = _target_months(cond, now)
    scope = (json.loads(fpath.read_text(encoding="utf-8")).get("scope") if fpath.exists() else None) or AR_scope(question, cond)
    typ = typical_candidates(cond, now, scope, {r["name"] for r in cands}, c, pending)
    for t in typ:
        F.add("typical", f"{t['name']}({t['prefecture']}{t.get('municipality') or ''}): 例年 {t['text']}"
              + (f"({'・'.join(t['kinds'])})" if t["kinds"] else ""), place=t["name"], source=t.get("publisher"), url=t["url"],
              source_class=t["source_class"])
        cands.append({"subject": None, "rank": None, "name": t["name"], "chosen": False, "basis": "typical", "group": t["group"],
                      "prefecture": t["prefecture"], "distance_km": t.get("km"), "theme": t.get("theme"),
                      "reasons": [c["typical_candidates"]["label"]]})
    for r in cands:
        r.setdefault("basis", "current" if r.get("current_state") else "typical")
        r.setdefault("group", _group_of(r.get("prefecture"), c))
    names = [r["name"] for r in cands] + _question_places(question, res)
    for card, hit in closures_for(names, months, c):
        cl = card["closure"]
        note = c["closure_note"]["in_period"] if hit else c["closure_note"]["out_period"]
        season_txt = (cl.get("season") or {}).get("text")
        F.add("safety", f"{card.get('place')}: {cl.get('name')}" + (f"({cl.get('section')})" if cl.get("section") else "")
              + f" 例年の冬季閉鎖 {cl.get('typical')}" + (f"。{season_txt}" if season_txt else "") + f"。{note}",
              place=card.get("place"), source=(card.get("source") or {}).get("name"), url=(card.get("source") or {}).get("url"),
              source_class="official", extra={"in_target": hit})
    cards = _cards(question, res, c, cand_names=[r["name"] for r in cands if r.get("chosen")], months=months,
                   event_texts=[f["content"] for f in F.rows if f["kind"] == "event"])
    if pb:
        seen = {k["title"] for k in cards}
        for k in pb.get("cards") or []:
            if k["title"] not in seen and len(cards) < c["max_cards"]:
                cards.append({**k, "id": f"K{len(cards) + 1:03d}"})
    doc = {
        "schema": "ikimonobiyori-guide-brief/1", "id": bid, "question": question, "now": now.isoformat(),
        "previous": {"id": prev, "question": (pb or {}).get("question")} if prev else None,
        "dates": _dates_block(cond, now), "intent": cond.get("intent"), "route": res.get("route") or cond.get("route"),
        "scope": "region" if cond.get("region") else "areas" if cond.get("area_names") else (scope or "default"),
        "region": cond.get("region"), "areas": cond.get("area_names"), "subjects": cond.get("subjects"),
        "origin": cond.get("origin"), "origin_source": cond.get("origin_source"),
        "candidates": cands, "candidates_note": (extra or {}).get("origin_line"),
        "facts": F.rows, "cards": cards,
        "missing": _missing(question, res, cands, F.rows, cards, extra),
        "rules": list(c["rules"]),
        "fallback": {"text": res.get("text") or "", "stage": res.get("stage"), "status": res.get("status")},
    }
    return doc


def render_md(doc):
    L = [f"# ガイドの資料 {doc['id']}", "", f"- 質問: {doc['question']}"]
    if doc.get("previous"):
        L.append(f"- 前の質問: {doc['previous'].get('question')}(資料 {doc['previous'].get('id')})")
    d = doc["dates"]
    L += [f"- 今日: {d['today']} / 今週末: {'・'.join(d['this_weekend'])} / 来週末: {'・'.join(d['next_weekend'])}",
          f"- 対象の日: {' ; '.join('・'.join(p) for p in d.get('periods') or [])}" + ("(日付の指定なし・既定)" if d.get("defaulted_date") else ""),
          f"- 質問の型: {doc.get('intent')} / 経路: {doc.get('route')} / 範囲: {doc.get('scope')} {doc.get('region') or ''} {'・'.join(doc.get('areas') or [])}",
          f"- 出発地: {doc.get('origin')}", ""]
    if doc["candidates"]:
        L += ["## 候補と順位", ""]
        if doc.get("candidates_note"):
            L.append(doc["candidates_note"])
        for r in doc["candidates"]:
            why = "、".join(x for x in [r.get("outlook"), r.get("phrase"), *(r.get("reasons") or [])] if x)
            if r.get("rank") is None:
                L.append(f"- [例年の目安・{r.get('group') or ''}] {r['name']}({r.get('prefecture') or ''} 約{r.get('distance_km')}km)"
                         + (f"・{r['theme']}" if r.get("theme") else ""))
                continue
            L.append(f"{r['rank']}. [{r.get('subject') or ''}{'・今年の現況あり' if r.get('basis') == 'current' else '・例年の目安'}] {r['name']}({r.get('prefecture') or ''} 約{r.get('distance_km')}km・点 {r.get('score')}・"
                     f"{'選んだ' if r['chosen'] else '選ばなかった: ' + (r.get('not_chosen_reason') or '点数が下')}) {why}")
        L.append("")
    L += ["## 確かめた事実", ""]
    for f in doc["facts"]:
        src = f"{f.get('source') or '出典名なし'}・{'公式' if f.get('source_class') == 'official' else 'その他' if f.get('source_class') else '区分なし'}"
        when = "・".join(x for x in (f"観測 {f['observed']}" if f.get("observed") else "", f"取得 {f['read_at'][:10]}" if f.get("read_at") else "") if x)
        L.append(f"- [{f['id']}] {f['kind_label']}: {f['content']}({src}{'・' + when if when else ''}){' ' + f['url'] if f.get('url') else ''}")
    if not doc["facts"]:
        L.append("(なし)")
    L += ["", "## 知識カード", ""]
    for k in doc["cards"]:
        L.append(f"- [{k['id']}] {k['title']}({k.get('link') or ''}・{k.get('category') or ''}・{k.get('place') or ''}・{k.get('source')}・{k.get('checked_on')}に確認)")
        L += [f"  - {x}" for x in k["facts"]]
    if not doc["cards"]:
        L.append("(なし)")
    L += ["", "## 足りないもの", ""] + [f"- {x}" for x in doc["missing"] or ["(なし)"]]
    L += ["", "## 決まり", ""] + [f"- {x}" for x in doc["rules"]]
    return NL.join(L) + NL


def save(doc, env=None):
    d = brief_dir(env)
    d.mkdir(parents=True, exist_ok=True)
    jp, mp = d / f"{doc['id']}.json", d / f"{doc['id']}.md"
    jp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.write_text(render_md(doc), encoding="utf-8")
    return jp, mp
