"""段階64 第3部: 日付を聞いていない「いつ・どこ」の質問の答え(時期と場所)。通信しない・書き込まない。

「藤が有名な場所と時期を教えて」「ニッコウキスゲはいつどこへ行けばいい?」のように、種や花の名前と「いつ・どこ」を聞く質問に、
名所カタログ(data/catalog/*.yaml)・ガイドのカタログ(data/guide/catalog.yaml)・読んだ事実の記録(ask record の kind と typical)から、
時期の早い順の名所の一覧を作る。**今の日付で候補を絞らない**(時期の外でも名所を出し、次の時期を 1 文で書く)。
範囲(出発地から 250km 前後)の外と、都県の指定の外は出さない。事実は記録・カタログの値だけ(一般知識から作らない)。
語と文は data/ask/season_place.yaml。"""
import re
from datetime import date
from urllib.parse import urlparse

from . import yamlcache
from .paths import DATA_FILES_DIR

CONFIG = DATA_FILES_DIR / "ask" / "season_place.yaml"
NL = chr(10)


def cfg():
    return yamlcache.load(CONFIG)


# ---- 質問 → 種 ----

def _catalog_kinds():
    """名所カタログ・ガイドのカタログにある種の語(長い順)。"""
    out = set()
    for e in _flower_entries():
        out |= set((e.get("tags") or {}).get("flower_kinds") or [])
        out |= {w.get("kind") for w in e.get("flower_windows") or [] if w.get("kind")}
    for e in _guide_entries():
        out |= {k.get("kind") for k in e.get("kinds") or [] if k.get("kind")}
    return sorted((k for k in out if k and len(k) >= 2), key=len, reverse=True)


def _sp_doc(sp):
    return {"name": sp["name"], "match": list(sp["match"]), "words": list(sp.get("words") or sp["match"]), "includes": list(sp.get("includes") or [])}


def resolve_all(question, c=None):
    """質問の文 → 種の一覧(質問に出た順。「菜の花や桜」は 2 つ)。ほかの語の中の語(「冬桜」の中の「桜」)は数えない。
    別名の表(長い語から)→ カタログの種の語がそのまま質問にある、の順。推測で結びつけない。"""
    c = c or cfg()
    q = question or ""
    hits = []
    for sp in c["species"]:
        for w in sorted(sp["words"], key=len, reverse=True):
            for m in re.finditer(re.escape(w), q):
                hits.append((m.start(), m.end(), sp))
    keep = []
    for a, b, sp in sorted(hits, key=lambda x: (x[0], -(x[1] - x[0]))):
        if any(a >= a2 and b <= b2 and (a, b) != (a2, b2) for a2, b2, _ in hits):
            continue                                                      # もっと長い語の中にある
        if sp["name"] not in [x["name"] for x in keep]:
            keep.append(_sp_doc(sp))
    if keep:
        return keep
    for k in _catalog_kinds():
        if k in q:
            return [{"name": k, "match": [k], "words": [k], "includes": []}]
    return []


def resolve_species(question, c=None):
    """質問の文 → 最初の種 {name, match, words, includes} か None。"""
    got = resolve_all(question, c)
    return got[0] if got else None


def is_season_place(question, c=None):
    """日付を聞いていない「いつ・どこ」の質問か(種の名前があり、時期と場所の言い方があり、日付の語がない)。"""
    c = c or cfg()
    q = question or ""
    if any(re.search(w, q) for w in c["date_words"]):
        return False
    if not any(re.search(p, q) for p in c["patterns"]):
        return False
    return resolve_species(q, c) is not None


# ---- 名所の材料 ----

def _flower_entries():
    from . import catalog as CM
    out = []
    for sj in ("flowers", "birds", "wintering_birds"):
        try:
            doc = CM.load_catalog(sj)
        except (OSError, ValueError, KeyError):
            continue
        out += [dict(e, _subject=sj) for e in doc.get("entries") or [] if not e.get("example") and e.get("status") == "approved"]
    return out


def _guide_entries():
    try:
        doc = yamlcache.load(DATA_FILES_DIR / "guide" / "catalog.yaml")
    except OSError:
        return []
    return [e for e in doc.get("entries") or [] if e.get("scope") == "place" and e.get("prefecture")
            and (e.get("approval") or {}).get("state") in ("provisional", "approved")]


def _matches(text, match, sp=None, c=None):
    """種の語に当たるか。ほかの種の、より長い語に当たる語(梅の質問の「蝋梅」)は外す(その種が includes にあるときは含める)。"""
    if not text or not any(m in text for m in match):
        return False
    if sp is None:
        return True
    c = c or cfg()
    best = max(len(m) for m in match if m in text)
    inc = set(sp.get("includes") or [])
    for other in c["species"]:
        if other["name"] == sp["name"] or other["name"] in inc:
            continue
        if any(m2 in text and len(m2) > best for m2 in other["match"]):
            return False
    return True


def _name_matches(name, match, sp, c):
    """名所の名前で当てるのは 2 字以上の語だけ(「桜木」「藤沢」のような地名に当てない)。"""
    return _matches(name, [m for m in match if len(m) >= 2], sp, c)


def _third(md, thirds):
    m, d = int(md[:2]), int(md[3:])
    for name, (a, b) in thirds.items():
        if a <= d <= b:
            return f"{m}月{name}"
    return f"{m}月"


def window_text(start, end, thirds):
    from . import observations as O
    if O.is_year_round({"start": start, "end": end}):                  # 段階72 第6部 2: 通年
        return cfg()["text"]["year_round"]
    a, b = _third(start, thirds), _third(end, thirds)
    return a if a == b else f"{a}〜{b}"


def _km(point, city, origin, cat_pol):
    """(km, 見積もりか)。座標 → 市区町村の代表点 → (None, False)。"""
    from . import catalog as CM
    from . import origins
    if point and point.get("lat") is not None:
        return CM.range_from(cat_pol, point, origin)["km"], False
    p = origins.municipal_point(city) if city else None
    if p:
        return CM.range_from(cat_pol, p, origin)["km"], True
    return None, False


def _publisher(url, entry=None):
    """段階67 第1部 4: 発行元の名前(「二宮町」)。ドメインは出さない。分からなければ空。"""
    from . import publisher as P
    title = next((s.get("title") for s in (entry or {}).get("sources") or [] if s.get("url") == url), None) if entry else None
    return P.name(url, entry, title) or ""


def _official(url, approved):
    """段階67 第1部 3(承認欄 C): 通信先の承認(approved)か、町・市・県・国の自身のページなら「公式」と表示する。"""
    from . import publisher as P
    return bool(approved) or bool(url and P.shows_official(url))       # 段階69 第6部: 観光協会・公園の管理者・施設の運営者も


def gather(sp, origin, c=None, env=None):
    """種 → 名所の行の一覧(範囲・都県の絞り込みの前)。同じ名所は 1 行(カタログが先)。"""
    from . import catalog as CM
    from . import observations as O
    c = c or cfg()
    cat_pol = CM.load_policy()
    opol = O.load_policy()
    thirds = c["text"]["thirds"]
    match = list(sp["match"]) + list(sp.get("includes") or [])
    rows = {}

    def key(name):
        return re.sub(r"[\s()（）・]", "", name or "")

    from . import publisher as P
    for e in _flower_entries():
        t = e.get("tags") or {}
        kinds = [k for k in (t.get("flower_kinds") or []) if _matches(k, match, sp, c)]
        wins = [w for w in e.get("flower_windows") or [] if _matches(w.get("kind"), match, sp, c)
                and not O.event_derived(w, e.get("events"), opol, e.get("name")) and not P.unused_source(w.get("source_url"))]
        if not kinds and not wins and not _name_matches(e.get("name"), match, sp, c):
            continue
        km, est = _km(e.get("point"), t.get("city"), origin, cat_pol)
        # 段階79 第1部 2: 時期の違う種(桜山公園の冬桜 11月〜・河津桜 2月〜)は種ごとの行にし、行にはその時期に当たる種だけを書く。
        # 時期の窓のない種(上野恩賜公園の寒桜)は、窓のある種の行に混ぜない(窓が 1 つもないときだけ、時期なしの行に入れる)
        spans = {}
        for x in wins:
            spans.setdefault((x.get("start"), x.get("end")), []).append(x)
        for i, ws in enumerate(spans.values() if spans else [[None]]):
            w = ws[0]
            row_kinds = sorted({x["kind"] for x in ws}) if w else sorted(set(kinds))
            _catalog_row(rows, (key(e["name"]) if i == 0 else key(e["name"]) + "|" + str(w.get("start"))), e, t, km, est, w, row_kinds, thirds, P)
    for e in _guide_entries():
        kinds = [k["kind"] for k in e.get("kinds") or [] if _matches(k.get("kind"), match, sp, c)]
        if not kinds:
            continue
        s = e.get("season") or {}
        if isinstance(s, str):
            s = {"text": s}
        win = s.get("window") if isinstance(s.get("window"), dict) else {}
        if not win.get("start") and s.get("text"):                        # 窓のない時期の文(「11月中旬〜12月中旬」)は、読める形だけ窓にする(推測しない)
            pw = O.parse_typical(s["text"], opol)
            win = {"start": pw[0], "end": pw[1]} if pw else {}
        by = ((e.get("range") or {}).get("by_origin") or {}).get(origin) or {}
        km, est = (by.get("km"), False) if by.get("km") is not None else _km(None, e.get("municipality"), origin, cat_pol)
        if by.get("status") == "out_of_range":
            km = by.get("km")
        srcs = [x for x in e.get("sources") or [] if not P.unused_source(x.get("url"))]          # 段階69 第4部 1
        if not srcs:
            continue
        if s.get("from_url") and P.unused_source(s.get("from_url")):
            s, win = {}, {}
        if _season_of_other_kind(s.get("text"), kinds, e.get("kinds")):   # 段階78 の追記: 「梅は1月上旬から…」を桜の時期にしない
            s, win = {}, {}
        src = next((x for x in srcs if x.get("url") == s.get("from_url")), srcs[0])
        rows.setdefault(key(e["name"]), {
            "name": e["name"], "prefecture": e.get("prefecture"), "city": e.get("municipality"), "km": km, "km_estimated": est,
            "kinds": kinds, "start": win.get("start"), "end": win.get("end"), "season": s.get("text") if s.get("shown", True) else None,
            "url": src.get("url"), "official": src.get("class") in ("A", "B"), "publisher": _publisher(src.get("url"), {"tags": {"prefecture": e.get("prefecture"), "city": e.get("municipality")}, "sources": [{"url": src.get("url"), "title": src.get("title")}]}), "care": None, "from": "guide", "subject": e.get("theme")})
    for r in _records(match, env, sp, c):
        k = key(r["name"])
        if k in rows:
            if _other_kind(r, rows[k], sp):                             # 段階79 第1部 2: 同じ名所のほかの種の時期は、その種の行にする(行の種と時期を混ぜない)
                k2 = k + "|" + r["kinds"][0]
                if r.get("season") and k2 not in rows:
                    rows[k2] = {**r, "km": rows[k]["km"], "km_estimated": rows[k]["km_estimated"]}
                continue
            if not rows[k]["season"] and r.get("season"):
                rows[k].update(season=r["season"], start=r["start"], end=r["end"], url=r["url"], official=r["official"], publisher=r.get("publisher") or "")
            continue
        km, est = _km(None, r.get("city"), origin, cat_pol)
        rows[k] = {**r, "km": km, "km_estimated": est}
    return list(rows.values())



def _catalog_row(rows, k, e, t, km, est, w, kinds, thirds, P):
    """名所カタログの 1 行(段階79 第1部 2 で gather から分けた。中身は今までと同じ)。"""
    rows.setdefault(k, {
            "name": e["name"], "prefecture": t.get("prefecture"), "city": t.get("city"), "km": km, "km_estimated": est,
            "kinds": kinds,
            "start": w["start"] if w else None, "end": w["end"] if w else None,
            "season": window_text(w["start"], w["end"], thirds) if w else None,
            "url": w["source_url"] if w else next((s.get("url") for s in e.get("sources") or [] if not P.unused_source(s.get("url"))), None),
            "official": bool(w) and _official(w["source_url"], not (w.get("source_class") == "secondary" or w.get("unapproved_host"))),
            "publisher": _publisher(w["source_url"], e) if w else "",
            "care": t.get("care_note"), "from": "catalog", "subject": e["_subject"],
            "annual_events": list(e.get("annual_events") or [])})



def _other_kind(rec, row, sp):
    """記録の種と行の種が、どちらも種の名前そのもの(「桜」)でなく、重ならないとき True(上野恩賜公園の寒桜の行に、ソメイヨシノの時期を入れない)。"""
    general = {(sp or {}).get("name")}
    a, b = set(rec.get("kinds") or []), set(row.get("kinds") or [])
    if not a or not b or a & b or a & general or b & general:
        return False
    return True

def _season_of_other_kind(text, kinds, entry_kinds):
    """ガイドの記録の時期の文が、名所のほかの種の名前で始まる(「梅は1月上旬から…」「梅の見頃は…」)のに、
    聞かれた種(kinds)の名前を含まないとき True(本人の指示 2026-11-11。その時期は聞かれた種の時期ではない)。"""
    if not text:
        return False
    others = [k.get("kind") for k in entry_kinds or [] if isinstance(k, dict) and k.get("kind") and k.get("kind") not in kinds]
    return any(text.startswith(o) for o in others) and not any(k in text for k in kinds)


def _old_year(r, season, c=None):
    """段階72 第6部 1: 出典が古い年の記載(記録の source_year が読んだ年より前)なら、年を明記する(「2014年の記載では、7月上旬まで」)。"""
    y = r.get("source_year")
    if not season or not y:
        return season
    try:
        read_year = int(str(r.get("read_at") or "")[:4])
    except ValueError:
        return season
    if int(y) >= read_year:
        return season
    return (c or cfg())["text"]["old_year_season"].format(year=int(y), season=season)


def _records(match, env=None, sp=None, c=None):
    """読んだ事実の記録(花・野鳥)のうち、種(kind)が当たり、例年の時期(typical)があるもの。"""
    from . import observations as O
    from . import publisher as P
    opol = O.load_policy()
    thirds = cfg()["text"]["thirds"]
    out = []
    for sj in ("flowers", "birds"):
        try:
            rows = O.read_records(sj, env, opol)
        except (OSError, ValueError, KeyError):
            continue
        for r in rows:
            if not _matches(r.get("kind") or "", match, sp, c) or not r.get("name") or P.unused_source(r.get("url")):
                continue
            win = O.parse_typical(r.get("typical"), opol) if r.get("typical") else None
            seen = window_text(win[0], win[1], thirds) if win else O.end_only_text(O.split_peak(r.get("typical"), opol)[0])   # 段階69 第7部: 「7月上旬まで」
            peak = O.peak_text(r.get("typical"), opol)
            season = seen
            if peak:                                  # 段階81 第1部 2: 見られる期間と、数が多い時期を分けて書く
                T = cfg()["text"]
                season = T["season_peak"].format(season=seen, peak=peak) if seen else T["peak_only"].format(peak=peak)
            out.append({"name": r["name"], "prefecture": r.get("prefecture"), "city": r.get("city"), "kinds": [r["kind"]],
                        "start": win[0] if win else None, "end": win[1] if win else None, "peak": peak,
                        "season": _old_year(r, season, c),
                        "url": r.get("url"), "official": _official(r.get("url"), r.get("source_class") == "official"),
                        "publisher": P.clean(r.get("publisher")) or _publisher(r.get("url")), "care": None, "from": "record", "subject": sj})
    return out


def select(rows, origin, prefectures=None, c=None, by_distance=False):
    """範囲(出発地から max_km)・都県の指定で絞る。→ (使う行, 範囲外で外した数)"""
    from . import catalog as CM
    c = c or cfg()
    max_km = CM.load_policy()["range_limit"]["max_km"]
    ok_pref = set(c["unknown_distance_prefectures"])
    keep, out = [], 0
    for r in rows:
        if prefectures and r.get("prefecture") not in prefectures:
            continue
        if r["km"] is not None:
            if r["km"] > max_km:
                out += 1
                continue
        elif r.get("prefecture") not in ok_pref:
            out += 1
            continue
        keep.append(r)

    def sk(r):
        km = r["km"] if r["km"] is not None else 9999
        return (km, r["name"]) if by_distance else (r["start"] is None, r["start"] or "", km, r["name"])
    if by_distance:
        return sorted(keep, key=sk)[: c["max_items"]], out
    # 段階67 第3部 8: 時期が分かる名所のあとに、時期が分からない名所を最大 max_unknown_items 件(名所カタログ・毎年の行事のある名所を先に)
    known = sorted([r for r in keep if r["start"] and r["season"]], key=sk)[: c["max_items"]]
    unknown = sorted([r for r in keep if not (r["start"] and r["season"])],
                     key=lambda r: (r.get("from") != "catalog", not r.get("annual_events"), r["km"] if r["km"] is not None else 9999, r["name"]))
    return known + unknown[: c.get("max_unknown_items", c["max_items"])], out


# ---- 文 ----

def _month_of(md):
    return int(md[:2])


def months_of(start, end):
    """「MM-DD」の始まり・終わり → その期間にかかる月(年をまたぐ期間は 12 月から 1 月へ続ける)。"""
    a, b = int(start[:2]), int(end[:2])
    out = [a]
    while out[-1] != b:
        out.append(out[-1] % 12 + 1)
    return out


def month_span(rows):
    """名所の行の例年の時期 → (始まりの月, 終わりの月)。どの名所の時期も含む、いちばん短い月の幅(年をまたいでよい。
    12〜1月の名所と 3〜4月の名所があれば 12月〜4月)。全部の月にかかるなら (1, 12)。時期のある行がなければ None。
    段階78 の追記(本人の指示 2026-11-11): 新しい形の資料と今までの形の答えで同じ計算を使う。"""
    wins = [r for r in rows if r.get("start") and r.get("end")]
    if not wins:
        return None
    have = set()
    for r in wins:
        have |= set(months_of(r["start"], r["end"]))
    if len(have) == 12:
        return 1, 12
    best = None                                     # いちばん長い「かからない月」の並びのすぐあとが始まり
    for m in range(1, 13):
        if m in have:
            continue
        n, x = 0, m
        while x not in have:
            n, x = n + 1, x % 12 + 1
        if best is None or n > best[0]:
            best = (n, x)
    start = best[1]
    end = start
    for k in range(12):
        x = (start - 1 + k) % 12 + 1
        if x in have:
            end = x
    return start, end


def _in_window(today, start, end):
    md = today.strftime("%m-%d")
    return start <= md <= end if start <= end else (md >= start or md <= end)


def _next_month(today, rows):
    best = None
    for r in rows:
        if not r["start"]:
            continue
        s = date(today.year, _month_of(r["start"]), int(r["start"][3:]))
        if s < today:
            s = date(today.year + 1, s.month, s.day)
        if best is None or s < best:
            best = s
    return best.month if best else None


def _species_part(sp, rows, n_out, *, today, origin, region, prefectures, table, c):
    """1 つの種の節 → (行, 出典の URL, 紹介サイトを含むか)。"""
    t = c["text"]
    is_bird = sp["name"] in c.get("bird_species", [])
    lines, urls, any_secondary = [], [], False
    if not rows:
        if prefectures:
            lines.append(t["region_none"].format(region=region, name=sp["name"]))
        elif n_out:
            lines.append(t["out_of_range"].format(origin=origin))
        else:
            lines.append(t["none"].format(name=sp["name"]))
        return lines, urls, False
    wins = [r for r in rows if r["start"] and r["end"] and r.get("season")]   # 段階78 の追記 4: 時期を書く名所だけ(資料の側と同じ)
    if is_bird:                                                           # 鳥は場所ごとに時期が違う(通年・秋〜春)。月の幅の 1 文にしない
        lines.append(t["lead_birds"].format(name=sp["name"]))
    elif wins:
        ma, mb = month_span(wins)                                         # 段階78 の追記 4: 年をまたぐ時期も(資料の側と同じ計算)
        a, b = f"{ma}月", f"{mb}月"
        lines.append(t["lead_one"].format(name=sp["name"], start=a) if a == b else t["lead"].format(name=sp["name"], start=a, end=b))
        if any(_in_window(today, r["start"], r["end"]) for r in wins):
            lines.append(t["in_season"])
        else:
            nm = _next_month(today, wins)
            if nm:
                lines.append(t["off_season"].format(month=nm))
    if table:
        lines += [""] + list(t["table_head"])
    for r in rows:
        where = (r.get("prefecture") or "") + (r.get("city") or "")
        km = t["km"].format(km=r["km"]) if r["km"] is not None else ""
        if table:
            lines.append(t["table_row"].format(name=r["name"], where=where, season=r["season"] or "分かりません", km=km.strip() or "—"))
        else:
            lines += ["", t["head"].format(name=r["name"], where=where, km=km)]
            if r["season"]:
                pub = r.get("publisher") if r.get("publisher") is not None else _publisher(r["url"])
                stext = re.sub(r"^例年(の時期は|は)?", "", r["season"]).strip() or r["season"]        # 段階69 第4部 2: 「例年の時期: 例年…」にしない
                if r["official"]:
                    ln = t["typical"].format(text=stext, publisher=pub) if pub else t["typical_nopub"].format(text=stext)
                else:
                    ln = t["typical_secondary"].format(text=stext, publisher=pub) if pub else t["typical_secondary_nopub"].format(text=stext)
            else:
                ln = t["typical_unknown"]
            if is_bird:
                for a, b in (t.get("bird_label") or {}).items():
                    ln = ln.replace(a, b)
            lines.append(ln)
            if not r["season"]:
                for ev in r.get("annual_events") or []:              # 段階67 第3部 8: 公式の「毎年」の行事の期間(例年の見頃ではない。年を書かない)
                    lines.append(t["annual_event"].format(name=ev["name"], text=ev["text"], publisher=ev["publisher"]))
                    if ev.get("source_url") and ev["source_url"] not in urls:
                        urls.append(ev["source_url"])
            if r["kinds"]:
                lines.append(t["kinds"].format(kinds="・".join(r["kinds"])))
            if r.get("care"):
                lines.append(t["care"].format(care=r["care"]))
        if r["url"] and r["url"] not in urls:
            urls.append(r["url"])
        any_secondary = any_secondary or (bool(r["season"]) and not r["official"])     # 段階67: 時期を書かない行は紹介サイトの注記の対象にしない
    return lines, urls, any_secondary


def place_filter(question, c=None):
    """段階69 第3部: 質問の場所(エリア辞書の名前・別名、または「○○市で」の市区町村)→ {label, cities} か None。"""
    from . import areas as AR
    c = c or cfg()
    q = question or ""
    a, n = AR.find_in(q)                                  # 段階80 の追記2: 「南伊豆」「伊豆市」の「伊豆」はエリアにしない
    if a:
        return {"label": n, "cities": list(a.get("cities") or [])}
    m = re.search(c["place_filter"]["city_re"], q)
    if m:
        city = re.sub(r"^.+?[都道府県](?=.{2,})", "", m.group(1))      # 段階78: 「神奈川県松田町」は町の名前で絞る(記録の city は「松田町」)
        return {"label": city, "cities": [city]}
    return None


def _in_cities(r, cities):
    city = r.get("city") or ""
    return any(ct and (city.startswith(ct) or ct in re.split(r"[・、]", city)) for ct in cities)


def compose(question, *, today, origin, region=None, prefectures=None, env=None, species=None, max_items=None, place=None):
    """→ {text, spots, species, species_all, needs_research}。種が 2 つ以上なら種ごとの節。必ず空でない文。
    species: 種の一覧を渡すとき(知識の答えの最後の短い一覧など)。max_items: 1 つの種の名所の上限(既定は設定の max_items)。"""
    c = cfg()
    t = c["text"]
    sps = species if species is not None else resolve_all(question, c)
    if not sps:
        return None
    table = any(w in (question or "") for w in t["table_words"])
    head = [t["origin_line"].format(origin=origin)]
    body, urls, any_secondary, all_rows, missing = [], [], False, [], []
    birds_only = all(sp["name"] in c.get("bird_species", []) for sp in sps)
    pf = c["place_filter"]
    research = []
    for sp in sps:
        is_bird = sp["name"] in c.get("bird_species", [])
        rows, n_out = select(gather(sp, origin, c, env), origin, prefectures, c, by_distance=is_bird)
        if max_items is not None:
            rows = rows[:max_items]
        place_none = None
        if place and place.get("cities"):                                # 段階69 第3部: 質問の場所で絞る。なければ 1 文と、ほかの場所の名所
            own = [r for r in rows if _in_cities(r, place["cities"])]
            if own:
                rows = own
            else:
                place_none = pf["none"].format(place=place["label"], name=sp["name"])
                rows = rows[: pf["max_other_items"]]
                research.append({"what": sp["name"], "where": place["label"], "search": pf["search"].format(place=place["label"], name=sp["name"])})
        if not rows and not place_none:
            research.append({"what": sp["name"], "where": (place or {}).get("label") or region,
                             "search": pf["search"].format(place=(place or {}).get("label") or region, name=sp["name"]) if ((place or {}).get("label") or region)
                             else pf["search_noplace"].format(name=sp["name"])})
        part, u, sec = _species_part(sp, rows, n_out, today=today, origin=origin, region=region, prefectures=prefectures, table=table, c=c)
        if place_none:
            part = [place_none] + ([""] + [pf["others_heading"].format(name=sp["name"])] + part if rows else [])
        if len(sps) > 1:
            body += ["", t["species_heading"].format(name=sp["name"])]
        elif body:
            body.append("")
        body += part
        urls += [x for x in u if x not in urls]
        any_secondary = any_secondary or sec
        all_rows += rows
        if not rows:
            missing.append(sp["name"])
    if all_rows and all(r.get("km") is None for r in all_rows):          # 段階72 第6部 1: 座標(距離)がない名所だけなら、距離の 1 文を出さない
        head = []
    if len(sps) == 1:
        lines = body[:1] + body[1:2] if body and not all_rows else []
        if all_rows:                                                      # 1 種: 冒頭の 1〜2 文のあとに距離の 1 文
            lead = [x for x in body[:2] if x and not x.startswith(("**", "|", "・"))]
            rest = body[len(lead):]
            lines = lead + head + rest
    else:
        lines = head + body
    while lines and not lines[0].strip():                               # 段階72 第6部 1: 距離の 1 文を出さないとき、先頭の空行を残さない
        lines.pop(0)
    if all_rows:
        lines.append("")
        lines.append(confidence_text(sps, c))
        if any_secondary:
            lines.append(t["secondary_note"])
    if urls:
        lines += ["", t["sources_heading"]] + urls
    return {"text": NL.join(lines) + NL, "spots": all_rows, "species": sps[0], "species_all": [x["name"] for x in sps],
            "missing": missing, "needs_research": bool(missing or research), "research": research}


# ---- 段階69 第2部 3: 種と日付の質問 ----

def is_species_dated(question, c=None):
    """種の名前があり、日付の語があり、テーマの総称(紅葉・花・野鳥など)が種の語の外にない質問。"""
    c = c or cfg()
    q = question or ""
    if not any(re.search(w, q) for w in c["date_words"]):
        return False
    sps = resolve_all(q, c)
    if not sps:
        return False
    rest = q
    for w in sorted({w for sp in c["species"] for w in sp["words"]} | {k for sp in sps for k in sp["words"]}, key=len, reverse=True):
        rest = rest.replace(w, " ")
    return not any(g in rest for g in c["dated"]["generic_words"])


def _days(on):
    return "・".join(f"{d.month}/{d.day}" for d in on)


def _near(d, start, end, near):
    from datetime import timedelta
    return any(_in_window(d + timedelta(days=k), start, end) for k in range(-near, near + 1))


def species_records(sp, on, env=None, c=None, records=None, vc_rows=None, today=None):
    """野鳥: 公園の観察記録・承認済みの施設の発信のうち、その種の名があるもの(古さの上限の内)。→ [(日付, 名所, 発行元, URL)]"""
    from . import observations as O
    from . import visitor_centers as VC
    c = c or cfg()
    dc = c["dated"]
    today = today or on[0]
    words = list(sp["match"]) + list(sp.get("words") or [])
    out = []
    rows = records if records is not None else O.read_records("birds", env)
    for r in rows:
        if r.get("source_class") != "official":
            continue
        text = " ".join(r.get("species") or []) + " " + (r.get("state") or "")
        if not any(w in text for w in words):
            continue
        sd = O.state_date_of(r)
        if not sd:
            continue
        if 0 <= (today - date.fromisoformat(sd)).days <= dc["record_max_age_days"]:
            out.append((sd, r.get("name") or r.get("publisher") or "", r.get("publisher") or "", r.get("url")))
    try:
        vrows = vc_rows if vc_rows is not None else VC.fact_rows(today, subjects=None, env=env)
    except (OSError, ValueError, KeyError):
        vrows = []
    for v in vrows:
        if not any(w in " ".join(v.get("species") or []) + " " + (v.get("state") or "") for w in words):
            continue
        if v.get("date") and 0 <= (today - date.fromisoformat(v["date"])).days <= dc["record_max_age_days"]:
            out.append((v["date"], v["name"], v["name"], v.get("url")))
    seen, uniq = set(), []
    for x in sorted(out, key=lambda x: x[0], reverse=True):              # 同じ名所は最新の 1 行
        k = re.sub(r"[(（].*$", "", x[1]).strip()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    return uniq[: dc["record_max_lines"]]


def _dated_parts(sps, on, *, today, origin, region=None, prefectures=None, env=None, records=None, vc_rows=None, c=None, headings=None):
    """種ごとの、その日に時期が合う名所と時期の外の 1 行。→ (行, 出典の URL, 名所の行, 名所がなかった種, 紹介サイトを含むか, 時期が合う名所の行)"""
    c = c or cfg()
    t, dc = c["text"], c["dated"]
    days = _days(on)
    headings = len(sps) > 1 if headings is None else headings
    lines, urls, all_rows, missing, any_secondary, fit_rows = [], [], [], [], False, []
    for sp in sps:
        is_bird = sp["name"] in c.get("bird_species", [])
        rows, n_out = select(gather(sp, origin, c, env), origin, prefectures, c, by_distance=is_bird)
        fit = [r for r in rows if not (r["start"] and r["end"]) or any(_near(d, r["start"], r["end"], dc["near_days"]) for d in on)]
        off = [r for r in rows if r not in fit]
        if headings:
            lines += ["", t["species_heading"].format(name=sp["name"])]
        part, u, sec = _species_part(sp, fit, n_out if not off else 0, today=on[0], origin=origin, region=region, prefectures=prefectures,
                                     table=False, c=c)
        if fit:
            lead = dc["lead_birds"] if is_bird else dc["lead_in"]
            drop = {t["in_season"], t["lead_birds"].format(name=sp["name"])}
            part = [lead.format(name=sp["name"], days=days)] + [x for x in part if x not in drop and not x.startswith(sp["name"] + "は、例年")
                                                               and not x.startswith("今は時期の外")]
        elif off:
            nm = _next_month(on[0], off)
            part = [dc["lead_off"].format(name=sp["name"], days=days, month=nm)] if nm else []
        lines += part
        items = [dc["off_item"].format(name=r["name"], season=re.sub(r"^例年", "", r["season"])) for r in off if r["season"]]
        if items:
            lines += ["", dc["off_line"].format(items="、".join(items))]
            for r in off:
                if r["url"] and r["url"] not in urls:
                    urls.append(r["url"])
        urls += [x for x in u if x not in urls]
        any_secondary = any_secondary or sec or any(not r["official"] for r in off if r["season"])
        all_rows += fit + off
        fit_rows += fit
        if not fit and not off:
            missing.append(sp["name"])
        if is_bird:
            recs = species_records(sp, on, env, c, records=records, vc_rows=vc_rows, today=today)
            if recs:
                lines += ["", dc["records_heading"].format(name=sp["name"])]
                for sd, name, pub, url in recs:
                    d = date.fromisoformat(sd)
                    lines.append(dc["record_line"].format(name=re.sub(r"[(（].*$", "", name).strip() or name, month=d.month, day=d.day,
                                                          species=sp["name"], publisher=pub))
                    if url and url not in urls:
                        urls.append(url)
    return lines, urls, all_rows, missing, any_secondary, fit_rows


def compose_dated(question, *, today, on, origin, region=None, prefectures=None, env=None, records=None, vc_rows=None):
    """種と日付の質問 → {text, spots, species_all, missing, needs_research}。その日に時期が合う名所を先に、合わないものは「時期の外」の 1 行。"""
    c = cfg()
    t, dc = c["text"], c["dated"]
    sps = resolve_all(question, c)
    if not sps:
        return None
    days = _days(on)
    lines = [dc["title"].format(days=days, name="・".join(sp["name"] for sp in sps)), dc["date_line"].format(days=days),
             t["origin_line"].format(origin=origin)]
    part, urls, all_rows, missing, any_secondary, _fit = _dated_parts(sps, on, today=today, origin=origin, region=region, prefectures=prefectures,
                                                                env=env, records=records, vc_rows=vc_rows, c=c)
    lines += part
    if all_rows:
        lines += ["", confidence_text(sps, c)]
        if any_secondary:
            lines.append(t["secondary_note"])
    if urls:
        lines += ["", t["sources_heading"]] + urls
    return {"text": NL.join(lines) + NL, "spots": all_rows, "species": sps[0], "species_all": [x["name"] for x in sps],
            "missing": missing, "needs_research": bool(missing)}


def grass_species_in(question, c=None):
    """段階70 第1部: 質問に出たススキ・草紅葉の種(grass_species の中だけ。質問に出た順)。"""
    c = c or cfg()
    grass = set(c.get("grass_species") or [])
    return [sp for sp in resolve_all(question, c) if sp["name"] in grass]


def grass_tail(question, *, today, on, origin, prefectures=None, env=None):
    """段階70 第1部: 秋のお出かけの答え(計画の型。紅葉の候補)に足す、ススキ・草紅葉の名所の節。今年の様子の記録はないので、
    「今回のおすすめ」には入れず別の節に例年の時期の事実だけ。→ (行, 出典の URL)。
    質問にススキ・草紅葉の語か秋のお出かけの語(grass_tail.autumn_words)があり、対象の日が秋の月のときだけ。
    質問に名前の出た種は、時期の外でも「時期の外」の 1 行を書く。名前の出ていない種は、その日に時期が合う名所があるときだけ。"""
    c = cfg()
    g = c["grass_tail"]
    q = question or ""
    named = grass_species_in(q, c)
    if not named and not any(w in q for w in g["autumn_words"]):
        return [], []
    if not on or not any(d.month in c["season_months"][g["season"]] for d in on):
        return [], []
    names = [sp["name"] for sp in named]
    sps = named + [_sp_by_name(n, c) for n in c.get("grass_species") or [] if n not in names]
    blocks, urls, used, sec = [], [], [], False
    for sp in sps:
        part, u, rows, _missing, s2, fit = _dated_parts([sp], on, today=today, origin=origin, prefectures=prefectures, env=env, c=c,
                                                        headings=False)
        if not rows or (sp["name"] not in names and not fit):
            continue
        body = []
        for x in part:                                                    # 先頭と連続の空行は除く
            if x.strip() or (body and body[-1].strip()):
                body.append(x)
        while body and not body[-1].strip():
            body.pop()
        blocks.append(body)
        urls += [x for x in u if x not in urls]
        used.append(sp)
        sec = sec or s2
    if not blocks:
        return [], []
    lines = [g["heading"].format(names="・".join(sp["name"] for sp in used))]
    for k, b in enumerate(blocks):
        lines += ([""] if k else []) + b
    lines += ["", confidence_text(used, c)]
    if sec:
        lines.append(c["text"]["secondary_note"])
    return lines, urls


def confidence_text(sps, c=None):
    """確かさの文(対象ごと。段階69 第4部 2)。"""
    c = c or cfg()
    t = c["text"]
    if all(sp["name"] in c.get("bird_species", []) for sp in sps):
        return t["confidence_birds"]
    if all(sp["name"] in c.get("insect_species", []) for sp in sps):
        return t["confidence_insects"]
    if all(sp["name"] in c.get("grass_species", []) for sp in sps):
        return t["confidence_grass"]
    return t["confidence"]


# ---- 段階64 第4部: 知識の答えの最後の短い一覧・季節の種 ----

def season_of(question, c=None):
    """質問に最初に出た季節の語(冬・春・夏・秋)。なければ None。"""
    c = c or cfg()
    q = question or ""
    for w in sorted({w for sp in c["species"] for w in sp["words"]}, key=len, reverse=True):
        q = q.replace(w, "　" * len(w))                                  # 種の名前の中の字(「冬桜」の「冬」)は季節の語にしない
    hits = [(q.find(k), k) for k in (c.get("season_species") or {}) if k in q]
    return min(hits)[1] if hits else None


def season_species_names(question, c=None):
    """季節で絞った質問の、その季節の種の名前(質問の種に含まれるものだけ。「冬から春の桜」→ 冬桜・寒桜・河津桜)。"""
    c = c or cfg()
    season = season_of(question, c)
    if not season:
        return []
    names = list(c["season_species"][season])
    asked = resolve_all(question, c)
    if not asked:
        return names
    allowed = {n for sp in asked for n in [sp["name"]] + list(sp.get("includes") or [])}
    return [n for n in names if n in allowed and n != next((sp["name"] for sp in asked if sp.get("includes")), None)] or \
        [n for n in names if n in allowed]


def _sp_by_name(name, c):
    sp = next((x for x in c["species"] if x["name"] == name), None)
    return _sp_doc(sp) if sp else {"name": name, "match": [name], "words": [name], "includes": []}


def knowledge_tail(question, *, today, origin, prefectures=None, env=None):
    """知識の答えの最後に付ける「いつ・どこで」の短い一覧(最大 max_items 件)。→ (行, 出典の URL)。名所がなければ ([], [])。"""
    c = cfg()
    kt = c["knowledge_tail"]
    t = c["text"]
    names = season_species_names(question, c)
    sps = [_sp_by_name(n, c) for n in names] if names else resolve_all(question, c)
    rows = []
    for sp in sps:
        got, _ = select(gather(sp, origin, c, env), origin, prefectures, c)
        rows += [dict(r, _kind=sp["name"]) for r in got if r["name"] not in {x["name"] for x in rows}]
    if not rows:
        return [], []
    season = season_of(question, c)
    first = min((int(r["start"][:2]) for r in rows if r["start"]), default=1)
    if season:                                                            # 季節の始まりの月から数える(冬なら 11 月 → 12 月 → 1 月 …)
        first = c["season_months"][season][0]
    off = lambda r: ((int(r["start"][:2]) - first) % 12, r["start"][3:]) if r["start"] else (99, "")
    rows = sorted(rows, key=lambda r: (off(r), r["km"] if r["km"] is not None else 9999))[: kt["max_items"]]
    lines = [kt["heading"]]
    urls = []
    for r in rows:
        where = (r.get("prefecture") or "") + (r.get("city") or "")
        km = t["km"].format(km=r["km"]) if r["km"] is not None else ""
        fmt = kt["line"] if r["season"] else kt["line_unknown"]
        lines.append(fmt.format(name=r["name"], where=where, km=km, season=r["season"], kind="・".join(r["kinds"]) or r["_kind"]))
        if r["url"] and r["url"] not in urls:
            urls.append(r["url"])
    return lines, urls


# ---- 段階64 第4部 4: 町の名前で聞く場所の質問 ----

def _all_entries():
    """名所カタログ(花・紅葉・野鳥・冬鳥)とガイドのカタログの名所 → [{name, prefecture, city, kinds, windows, url, official, subject}]"""
    from . import catalog as CM
    out = []
    for sj in ("flowers", "autumn_leaves", "birds", "wintering_birds"):
        try:
            doc = CM.load_catalog(sj)
        except (OSError, ValueError, KeyError):
            continue
        for e in doc.get("entries") or []:
            if e.get("example") or e.get("status") != "approved":
                continue
            t = e.get("tags") or {}
            out.append({"name": e["name"], "prefecture": t.get("prefecture"), "city": t.get("city"), "point": e.get("point"),
                        "kinds": list(t.get("flower_kinds") or []) or ([{"autumn_leaves": "紅葉"}.get(sj)] if sj == "autumn_leaves" else []),
                        "windows": e.get("flower_windows") or ([dict(e["typical_window"], kind="紅葉")] if e.get("typical_window") else []),
                        "events": e.get("events"), "url": ((e.get("sources") or [{}])[0]).get("url"), "subject": sj})
    for e in _guide_entries():
        s = e.get("season") or {}
        s = {"text": s} if isinstance(s, str) else s
        out.append({"name": e["name"], "prefecture": e.get("prefecture"), "city": e.get("municipality"), "point": None,
                    "kinds": [k["kind"] for k in e.get("kinds") or [] if k.get("shown", True)][:4] or [e.get("theme")],
                    "season_text": s.get("text"), "url": ((e.get("sources") or [{}])[0]).get("url"), "subject": e.get("theme"),
                    "range_km": (((e.get("range") or {}).get("by_origin") or {}).get("横浜") or {}).get("km")})
    return out


def resolve_town(question, c=None):
    """質問の文 → 名所のある市区町村の名前(「松田」→ 松田町)。2 字以上の語だけ。当たりがなければ None。"""
    c = c or cfg()
    q = question or ""
    sfx = c["town"]["suffixes"]
    cities = sorted({e["city"] for e in _all_entries() if e.get("city")}, key=len, reverse=True)
    for city in cities:
        for part in re.split(r"[・、]", city):
            stem = re.sub("(" + "|".join(sfx) + ")$", "", part)
            if len(stem) >= 2 and (part in q or stem in q):
                return part
    return None


def is_town_question(question, c=None):
    c = c or cfg()
    q = question or ""
    if resolve_all(q, c):
        return False
    return any(re.search(p, q) for p in c["town"]["patterns"]) and resolve_town(q, c) is not None


def compose_town(question, *, origin, env=None):
    """町の名前の質問 → {text, spots, town}。名所の名前・見どころ・例年の時期・距離・出典(カタログの値だけ)。"""
    from . import catalog as CM
    from . import observations as O
    c = cfg()
    tc, t = c["town"], c["text"]
    town = resolve_town(question, c)
    if not town:
        return None
    cat_pol = CM.load_policy()
    opol = O.load_policy()
    thirds = t["thirds"]
    rows, seen = [], set()
    for e in _all_entries():
        if not e.get("city") or town not in re.split(r"[・、]", e["city"]):
            continue
        k = re.sub(r"[\s()（）・]", "", e["name"])
        if k in seen:
            for r in rows:
                if re.sub(r"[\s()（）・]", "", r["name"]) == k:
                    r["kinds"] = list(dict.fromkeys(r["kinds"] + [x for x in e["kinds"] if x]))
            continue
        seen.add(k)
        km, _est = _km(e.get("point"), e.get("city"), origin, cat_pol)
        seasons = []
        for w in e.get("windows") or []:
            if w.get("start") and w.get("end") and not O.event_derived(w, e.get("events"), opol, e["name"]):
                seasons.append((w["start"], window_text(w["start"], w["end"], thirds), w.get("kind")))
        if e.get("season_text"):
            seasons.append(("", e["season_text"], "・".join(e["kinds"][:2])))
        rows.append({"name": e["name"], "prefecture": e["prefecture"], "city": e["city"], "km": km, "kinds": [x for x in e["kinds"] if x],
                     "seasons": seasons, "url": e.get("url")})
    if not rows:
        return {"text": tc["none"].format(town=town) + NL, "spots": [], "town": town, "needs_research": True}
    rows = sorted(rows, key=lambda r: (min((s[0] for s in r["seasons"] if s[0]), default="99"), r["name"]))[: tc["max_items"]]
    lines = [tc["lead"].format(town=town), t["origin_line"].format(origin=origin)]
    urls = []
    for r in rows:
        where = (r.get("prefecture") or "") + (r.get("city") or "")
        km = t["km"].format(km=r["km"]) if r["km"] is not None else ""
        lines += ["", tc["head"].format(name=r["name"], where=where, km=km)]
        if r["kinds"]:
            lines.append(tc["line_kind"].format(kinds="・".join(r["kinds"])))
        for _s, text, kind in r["seasons"]:
            lines.append(tc["line_season"].format(season=text, kind=kind or "・".join(r["kinds"][:1])))
        if r["url"] and r["url"] not in urls:
            urls.append(r["url"])
    lines += ["", t["confidence"]]
    if urls:
        lines += ["", t["sources_heading"]] + urls
    return {"text": NL.join(lines) + NL, "spots": rows, "town": town, "needs_research": False}
