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
import unicodedata
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


def _town_candidates(F, cands, towns, cond, c, label=None, areas=()):
    """段階80 の追記: 質問の市区町村の名所を候補と事実に足し、ほかの市区町村の候補(既定の出発地の近くの名所など)と、その事実を外す。
    label: 広い地域の名前で聞かれたとき(「伊豆」)の地域の名前(候補の理由に出す。段階80 の追記2)。"""
    from . import guide_materials as GM
    T = c["town_candidates"]
    have = {r["name"] for r in cands}
    for town in towns:
        for s in _subject_spots(GM.town_spots(town, cond.get("origin")), cond, c):
            loc = f"{s.get('prefecture') or ''}{s.get('city') or ''}"
            for text, kind in s["seasons"]:
                if any(f.get("place") == s["name"] and f.get("url") == s.get("url") and f["kind"] == "typical" for f in F.rows):
                    continue                              # 同じ名所・同じ出典の例年の時期がもうある(読んだ事実の記録の行)
                F.add("typical", f"{s['name']}({loc}): " + ("" if text.startswith("例年") else "例年 ") + f"{text}" + (f"({kind})" if kind else "") + (T["tentative_note"] if s["tentative"] else ""),
                      place=s["name"], source=s.get("publisher"), url=s.get("url"), source_class=s.get("source_class"),
                      extra={"_pref": s.get("prefecture"), "_city": s.get("city")})
            if s["name"] in have:
                continue
            have.add(s["name"])
            cands.append({"subject": None, "rank": None, "name": s["name"], "chosen": False, "basis": "town",
                          "group": _group_of(s.get("prefecture"), c), "prefecture": s.get("prefecture"), "city": s.get("city"),
                          "theme": "・".join(s["kinds"][:3]) or None,
                          "reasons": [T["label"].format(town=label or town)] + ([T["tentative_label"]] if s["tentative"] else [])})
    keep = [r for r in cands if GM.in_town(r["name"], r.get("city"), towns) or (areas and _in_areas(r, areas))]
    kept = {r["name"] for r in keep}
    dropped = {r["name"] for r in cands} - kept
    words = list(kept) + towns + [re.sub(r"(市|町|村|区)$", "", t) for t in towns] + ([label] if label else [])

    def stays(f):
        pl = f.get("place")
        if pl:
            return not (pl in dropped or re.sub(r"\(.*$", "", pl) in dropped)
        return any(w and w in (f.get("content") or "") for w in words)      # 場所の欄のない行(コードの答えの行)は、その市区町村の話だけ
    F.rows[:] = [f for f in F.rows if stays(f)]
    for i, f in enumerate(F.rows):                        # 番号を振り直す(このあと足す事実と重ならないように)
        f["id"] = f"F{i + 1:03d}"
    return keep, dropped


def _subject_spots(spots, cond, c):
    """段階80 の追記2: 市区町村の名所を、質問の対象(紅葉・花・野鳥。既定の全部のときは絞らない)と、聞かれた種の名前で絞る。"""
    from . import ask
    from . import guide_materials as GM
    T = c["town_candidates"]
    subs = set(cond.get("subjects") or [])
    if subs and subs != set(ask.load_policy()["default_subjects"]):
        spots = [s for s in spots if T["subject_of"].get(s.get("subject")) in subs]
    sps = GM.species_names(cond.get("question") or "")
    if sps:
        spots = [s for s in spots if species_hit(sps, " ".join([s["name"], *(s.get("kinds") or [])]), c)]
    return spots


def _question_areas(question, cond):
    """段階80 の追記3(本人の判断 2026-11-11): 質問に挙げたエリア(「秩父」「日光」「伊豆」「富士」、「〜のエリア」の形の area_names)→ エリアの一覧。
    出発地として挙げた名前(「秩父から」「秩父発」)は除く(出発地の質問は今までどおり)。"""
    from . import areas as AR
    if cond.get("area_names"):
        return [a for a in (AR.resolve(n) for n in cond["area_names"]) if a and a.get("cities")]
    a, n = AR.find_in(question)
    if not a or not a.get("cities") or re.search(re.escape(n) + r"\s*(駅)?(から|発)", question or ""):
        return []
    return [a]


def _in_areas(r, areas):
    """候補がエリアの内か(市区町村が一致、または名所の辞書の座標がエリアの半径の内。areas.members と同じ)。"""
    from . import areas as AR
    from . import guide_materials as GM
    info = GM.place_info(r["name"])
    row = {"city": r.get("city") or info.get("city"), "point": r.get("point") or info.get("point")}
    return any(AR.members(a, [row]) or GM.in_town(r["name"], row["city"], list(a["cities"])) for a in areas)


def _tentative_targets(question, towns, label, cands, targets, c):
    """段階80 の追記2(本人の判断 2026-11-11): 市区町村(地域)の候補が、検索で集めた仮の名所だけ(か 0 件)なら、公式ページを調べる対象にする。
    公式で確かめて記録すると、その名所は仮でなくなる(guide_materials.town_spots)。"""
    from . import guide_materials as GM
    T = c["town_candidates"]
    if any(T["tentative_label"] not in (r.get("reasons") or []) for r in cands):
        return []
    where = label or "・".join(towns)
    if any(t.get("where") == where for t in targets):
        return []
    why = (T["tentative_why"] if cands else T["none_why"]).format(where=where)
    return [{"what": "、".join(GM.species_names(question)) or None, "where": where, "why": why}]


def _main_name(name, city):
    """名前の主な部分(段階80 の追記5): 括弧の中・空白・「の」を除き、都道府県と市区町村の名前(末尾の 市・町・村・区 を除いた形も)が頭にあれば除き、
    種の別名(臘梅・蝋梅)を種の名前(ロウバイ)にそろえる。"""
    from . import guide_materials as GM
    from . import season_place as SP
    n = re.sub(r"[(（][^)）]*[)）]", "", name or "")
    n = re.sub(r"[\s・]", "", n)
    n = re.sub(r"^(東京都|北海道|(京都|大阪)府|.{2,3}県)", "", n)
    for part in GM._city_parts(city):
        for x in sorted({part, re.sub(r"(市|町|村|区)$", "", part)}, key=len, reverse=True):
            if len(x) >= 2 and n.startswith(x) and len(n) > len(x):
                n = n[len(x):]
                break
    for sp in SP.cfg()["species"]:
        for w in sorted(set(sp.get("words") or []) - {sp["name"]}, key=len, reverse=True):
            if len(w) >= 2:
                n = n.replace(w, sp["name"])
    return n.replace("の", "")


def _cand_species(r):
    from . import guide_materials as GM
    return frozenset(GM.species_names(r["name"]) + GM.species_names(r.get("theme") or ""))


def _months(text):
    """例年の時期の文 → 月の集合(「12月下旬〜2月下旬」「12/21〜2/28」→ {12, 1, 2})。月がなければ空。"""
    ms = [int(a or b) for a, b in re.findall(r"(\d{1,2})月|(\d{1,2})/\d{1,2}", text or "")]
    ms = [m for m in ms if 1 <= m <= 12]
    if not ms:
        return set()
    lo, hi = ms[0], ms[-1]
    return set(range(lo, hi + 1)) if lo <= hi else set(range(lo, 13)) | set(range(1, hi + 1))


def same_place(a, b, c=None):
    """段階80 の追記5(本人の判断 2026-11-12): 2 つの候補が同じ場所か。同じ市区町村・同じ種(種が分かること)で、
    両方に座標があれば merge_same.max_m 以内、なければ名前の主な部分が同じ。"""
    from . import catalog as CM
    from . import guide_materials as GM
    c = c or cfg()
    ca, cb = set(GM._city_parts(a.get("city"))), set(GM._city_parts(b.get("city")))
    if not ca or not (ca & cb):
        return False
    sa, sb = _cand_species(a), _cand_species(b)
    if not sa or sa != sb:
        return False
    pa = a.get("point") or GM.place_info(a["name"]).get("point")
    pb = b.get("point") or GM.place_info(b["name"]).get("point")
    if pa and pb and pa.get("lat") is not None and pb.get("lat") is not None:
        r = CM.load_policy()["range_limit"]["earth_radius_km"]
        return CM.distance_km(pa["lat"], pa["lon"], pb["lat"], pb["lon"], r) * 1000 <= c["merge_same"]["max_m"]
    ma, mb = _main_name(a["name"], a.get("city")), _main_name(b["name"], b.get("city"))
    return bool(ma) and ma == mb


def merge_same_candidates(cands, F, c):
    """名前の形が違う同じ場所の候補を 1 つにまとめる(段階80 の追記5)。→ (候補, まとめた組, まとめなかった組(事実の食い違い))。
    表に出す名前は公式の出典の事実を持つ候補の名前(なければ先の候補)。事実は両方の候補のものを残し、場所を表に出す名前にそろえる。
    例年の時期の月が重ならない事実の組は食い違いとしてまとめない。記録そのものは変えない。"""
    out, merges, conflicts, used = [], [], [], set()
    for i, r in enumerate(cands):
        if i in used:
            continue
        group = [i] + [j for j in range(i + 1, len(cands)) if j not in used and same_place(r, cands[j], c)]
        if len(group) == 1:
            out.append(r)
            continue
        names = [cands[j]["name"] for j in group]
        typ = {n: [_months(f["content"]) for f in F.rows if f.get("place") == n and f["kind"] == "typical"] for n in names}
        bad = [(x, y) for k, x in enumerate(names) for y in names[k + 1:]
               if typ[x] and typ[y] and not any(mx & my for mx in typ[x] for my in typ[y] if mx and my) and any(typ[x]) and any(typ[y])]
        if bad:
            conflicts.append({"names": names, "reason": c["merge_same"]["conflict_reason"]})
            out.append(r)
            continue
        used.update(group)
        official = [n for n in names if any(f.get("place") == n and f.get("source_class") == "official" for f in F.rows)]
        main = official[0] if official else names[0]
        keep = dict(cands[group[names.index(main)]])
        keep["merged_from"] = list(dict.fromkeys(list(keep.get("merged_from") or []) + [n for n in names if n != main]))
        for j in group:                                   # 種・理由・現況はまとめた候補のものも残す
            o = cands[j]
            keep["reasons"] = list(dict.fromkeys(list(keep.get("reasons") or []) + list(o.get("reasons") or [])))
            for k, v in o.items():
                if keep.get(k) in (None, "", []) and v not in (None, "", []):
                    keep[k] = v
        keep["chosen"] = any(cands[j].get("chosen") for j in group)
        for f in F.rows:
            if f.get("place") in names and f.get("place") != main:
                f["place"] = main
        merges.append({"name": main, "merged_from": keep["merged_from"]})
        out.append(keep)
    return out, merges, conflicts


def _ledger_pending(url):
    """台帳で承認待ちの情報源のページか(情報源の URL の範囲で判定する。observations._ledger_gated と同じ。段階80 D)。"""
    from . import observations as O
    try:
        return O.ledger_status_in_range(url) == "pending"
    except (OSError, ValueError, KeyError):
        return False


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
        if kind == "current" and url and _ledger_pending(url) and _source_class(url, source_class) == "official":   # 段階78 第1部 7: 承認待ちの一覧の下の記事(/hanadayori/76765/ など。observations._ledger_gated と同じ)
            return None
        if url or source:
            from . import guide_materials as GM
            source = GM.source_name(url, source, prefecture=(extra or {}).get("_pref"), city=(extra or {}).get("_city")) or (
                None if source and GM._HOSTISH.match(str(source)) else source)
        if extra:
            extra = {k: v for k, v in extra.items() if not k.startswith("_")} or None
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
        F.add("current", f"{name}: {st}({md}時点、{cur.get('publisher')})" if md else          # 段階79 第1部 5: 日付のない発信は、いつの記録か分からないと書く
              F.c["current_undated"].format(name=name, state=st, publisher=cur.get("publisher")),
              place=name, source=cur.get("publisher"), url=cur.get("url"), source_class=cur.get("source_class"),
              observed=cur.get("state_date"), read_at=cur.get("read_at"),
              extra={"state": cur.get("state_raw") or cur.get("state"), "state_norm": cur.get("state"),
                     "freshness": cur.get("freshness_label")})
    for t in c_row.get("typical") or []:
        if t.get("text"):
            F.add("typical", f"{name}: 例年 {t.get('text_thirds') or t['text']}", place=name, source=t.get("publisher"), url=t.get("url"),   # 段階81 第1部 1: 旬で書く
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


def _plan_facts(F, work, cands, picks, extra):
    """計画の作業フォルダの facts.json → 候補の事実(F に足す)。→ 発行元の名前 → URL。"""
    fpath = Path(work) / "facts.json"
    known_pubs = {}
    if not fpath.exists():
        return known_pubs
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
    return known_pubs


def _area_plan(F, question, cond, now, env, work, c, clock, obs_kw, known_pubs):
    """段階78 第2部 1: エリア・山域を聞く質問(見どころの経路)で、そのエリアの名所の計画(紅葉・花・野鳥の今年の現況と例年の時期)を作り、
    候補と事実を足す。→ 候補の行。"""
    from . import answer_run as AR
    ds = (cond.get("periods") or [[]])[0]
    try:
        d = date.fromisoformat(ds[0])
        when = f"{d.month}月{d.day}日"
    except (IndexError, TypeError, ValueError):
        when = "今週末"
    area = (cond.get("area_names") or [""])[0]
    sub = Path(work) / "area"
    try:
        AR.run(c["area_plan_question"].format(date=when, area=area), now=now, env=env, workdir=sub, quiet=True, clock=clock, obs_kw=obs_kw)
    except (OSError, ValueError, KeyError, TypeError):
        return []
    rows, picks, extra = _candidates(sub, c)
    rows = rows[: c["area_plan_max"]]
    known_pubs.update(_plan_facts(F, sub, rows, picks, {"no_this_year": []}))
    for r in rows:
        r["reasons"] = list(r.get("reasons") or []) + [f"{area}の名所"]
    return rows


def _species_facts(F, sprows, cands, cond, c):
    """種の名所の一覧 → 候補(例年の目安)と事実。"""
    from . import guide_materials as GM
    R = c["species_rows"]
    have = {r["name"] for r in cands}
    for r in sprows:
        loc = f"{r.get('prefecture') or ''}{r.get('city') or ''}"
        kinds = "・".join(r.get("kinds") or [])
        if r.get("season") in (c["research"].get("year_round_words") or []):     # 段階82 第3部 1: 季節のない名所
            body = f"{r['name']}({loc}): {r['species']}は{r['season']}(季節を問わない見どころ)"
            for k, lab in (("notice", "見どころ"), ("best_conditions", "特によいとされる条件")):
                if r.get(k):
                    body += f"。{lab}: {r[k]}"
        elif r.get("season"):
            body = f"{r['name']}({loc}): {r['species']}の例年の時期 {r['season']}" + (f"(見られる種: {kinds})" if kinds else "")
        else:
            body = f"{r['name']}({loc}): {r['species']}" + (f"(見られる種: {kinds})" if kinds else "") + "。例年の時期の記載なし"
        if r.get("note"):
            body += f"。{r['note']}"
        F.add("typical", body, place=r["name"], source=r.get("publisher"), url=r.get("url"),
              source_class="official" if r.get("official") else ("secondary" if r.get("url") else None),
              extra={"_pref": r.get("prefecture"), "_city": r.get("city")})
        sec = r.get("secondary_season")
        if sec:                                            # 段階82 の続き(本人の判断 2026-11-13 の 2): 公式より長い紹介サイトの時期は、区別して公式のあとに
            F.add("typical", R["secondary_line"].format(name=r["name"], loc=loc, species=r["species"], season=sec["season"]), place=r["name"],
                  source=sec.get("publisher"), url=sec.get("url"), source_class="secondary", extra={"_pref": r.get("prefecture"), "_city": r.get("city")})
        if r.get("care"):
            F.add("facility", f"{r['name']}: 行く前に: {r['care']}", place=r["name"])
        if r.get("closed_period"):                         # 段階82 第3部 1: 行けない時期(冬期閉鎖など)は安全・規制の事実として
            F.add("safety", f"{r['name']}: 行けない時期: {r['closed_period']}", place=r["name"], source=r.get("publisher"), url=r.get("url"),
                  source_class="official" if r.get("official") else None)
        if r["name"] in have:
            continue
        have.add(r["name"])
        km, label = GM.distance_text(r["name"], r.get("km"), cond.get("origin"), estimated=bool(r.get("km_estimated")),
                                     prefecture=r.get("prefecture"), city=r.get("city"), c=c)
        cands.append({"subject": None, "rank": None, "name": r["name"], "chosen": False, "basis": "species", "group": _group_of(r.get("prefecture"), c),
                      "prefecture": r.get("prefecture"), "city": r.get("city"), "distance_km": km, "distance_text": label,
                      "theme": r["species"], "season": r.get("season"), "note": r.get("note"),
                      "reasons": [R["label"]] + ([r["note"]] if r.get("note") else [])})


def _species_leads(F, sprows, now, c):
    """日付の指定がない種の質問: コードの答えから写した全体の目安の文(「桜は、例年1月〜3月が目安です。」・「今は時期の外で…」)を、
    資料に入った名所の時期から作った文に置き換える(コードの答えの名所は資料の名所より少ないので、時期の幅が食い違う)。"""
    from . import guide_materials as GM
    from . import season_place as SP
    t = SP.cfg()["text"]
    today = now.date() if hasattr(now, "date") else now
    placed = {f["place"] for f in F.rows if f.get("place") and f["kind"] == "typical"}
    rows = [r for r in sprows if r["name"] in placed]            # 事実として資料に入った名所だけ(出典が使えない名所の時期を混ぜない)
    yr = set(c["research"].get("year_round_words") or [])
    if sprows and all(r.get("season") in yr for r in sprows):    # 段階82 第3部 1: 季節のない名所だけの種(苔)は、全体の目安の文を作らない
        return
    for sp, lines in GM.species_leads(rows or [dict(r, start=None, end=None) for r in sprows], today, c).items():
        lead_re = re.compile("^" + re.escape(sp) + "は、例年.+が目安です。$")
        old_lead = [f for f in F.rows if lead_re.match(f["content"])]
        old_when = [f for f in F.rows if f["content"] == t["in_season"] or re.match("^" + re.escape(t["off_season"]).replace(r"\{month\}", r"\d+") + "$", f["content"])]
        for olds, new in ((old_lead, lines[0]), (old_when, lines[1] if len(lines) > 1 else "")):
            if new is None or (not new and not olds):
                continue
            if not new:                                  # 時期の分かる名所がない: 「今は時期の外で…」も書かない(行を外して番号を振り直す)
                F.rows[:] = [f for f in F.rows if f not in olds[:1]]
                for i, f in enumerate(F.rows):
                    f["id"] = f"F{i + 1:03d}"
                continue
            if olds:
                for f in olds[:1]:
                    f["content"], f["values"] = new, values(new, c)
            else:
                F.add("typical", new)


def _place_records(F, question, cands, cond, c, env=None):
    """段階78 第4部: 利用者が挙げた場所(「南伊豆」「松田町」)の、読んだ事実の記録のうち種と例年の時期のあるもの → 候補と事実。
    その場で調べて記録した名所が、作り直した資料に入るように。今年の現況は入れない(例年の時期・注意だけ)。"""
    from . import guide_materials as GM
    from . import observations as O
    from . import research as RS
    places = RS.question_places(question)
    if not places:
        return
    have = {r["name"] for r in cands}
    for sj in ("flowers", "birds"):
        try:
            rows = O.read_records(sj, env)
        except (OSError, ValueError, KeyError):
            continue
        for r in rows:
            if not r.get("name") or not (r.get("typical") or r.get("notice")) or (r.get("typical") and not r.get("kind")):
                continue                                  # 段階80 F: 「行く前に」だけの記録(種なし)も入れる
            city = r.get("city") or ""
            if not any(p in city or p in r["name"] for p in places):
                continue
            loc = f"{r.get('prefecture') or ''}{city}"
            if r.get("typical"):
                F.add("typical", f"{r['name']}({loc}): {r['kind']} {r['typical']}", place=r["name"], source=r.get("publisher"), url=r.get("url"),
                      source_class=r.get("source_class"), extra={"_pref": r.get("prefecture"), "_city": city})
            if r.get("notice"):
                F.add("facility", f"{r['name']}: 行く前に: {r['notice']}", place=r["name"], source=r.get("publisher"), url=r.get("url"),
                      source_class=r.get("source_class"))
            if r["name"] in have or not r.get("typical"):
                continue                                  # 「行く前に」だけの記録は候補にしない(事実だけ)
            have.add(r["name"])
            km, label = GM.distance_text(r["name"], None, cond.get("origin"), prefecture=r.get("prefecture"), city=city, c=c)
            cands.append({"subject": sj, "rank": None, "name": r["name"], "chosen": False, "basis": "species", "group": _group_of(r.get("prefecture"), c),
                          "prefecture": r.get("prefecture"), "city": city, "distance_km": km, "distance_text": label, "theme": r["kind"],
                          "reasons": [c["species_rows"]["label"]]})


def _line_facts(F, text, c, known_pubs, skip_blocks=False, skip_names=()):
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
        if skip_names and ((ctx and ctx in skip_names) or any(n in s for n in skip_names)):
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
    """質問の語と対象 → テーマの語(カードを引く語)。
    段階80 E(提案1): 種の名前を含む別の語(芝桜・秋桜など。species_blob_exclude_re)は、質問の語として数えない(芝桜の質問で桜のテーマにしない)。"""
    out = []
    q = re.sub(c.get("species_blob_exclude_re") or r"(?!)", "", question or "")
    for t in c["card_themes"]:
        if t.get("subject") in (subjects or []) or any(w in q for w in t.get("question_words") or []):
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


def _plain_general_card(card, c):
    """段階80 A: 場所に結びつかない一般の話のカード(場所の欄が「桜一般」やテーマの語そのもので、ほかの場所の名前を添えていない)。"""
    pl = card.get("place") or ""
    words = {w for t in c["card_themes"] for w in t["words"]} | set(c.get("general_place_words") or [])
    plain = pl.endswith(c.get("species_card_place_suffix") or "一般") or pl in words
    return plain and _general_card(card, c) and (card.get("where") or pl) == pl


def _card_species(card):
    """一般の話のカードの種(場所の欄・題名の種の語。「桜一般」→ 桜、「冬桜」→ 冬桜)。分からなければ空。"""
    from . import season_place as SP
    for text in (card.get("place"), card.get("subject"), card.get("title")):
        got = [x["name"] for x in SP.resolve_all(text or "")]
        if got:
            return set(got)
    return set()


def _drop_unrelated_general(cards, question, cands, F, c, subjects=()):
    """段階81 第1部 3(本人の会話 2026-11-12): 場所を聞く質問(「秩父で見られる花は?」)では、
    その場所の候補にも質問にもない種の「一般の話」のカード(冬桜・バラの解説)を資料に入れない。種の分からない一般の話は残す。"""
    from . import season_place as SP
    blob = " ".join([question or ""] + [str(r.get("theme") or "") + " " + str(r.get("name") or "") for r in cands]
                    + [f["content"] for f in F.rows if f["kind"] == "typical"])
    have = {x["name"] for x in SP.resolve_all(blob)}
    kinds = set(SP._catalog_kinds()) | {w for sp in SP.cfg()["species"] for w in sp["words"]}
    rest = blob
    for k in sorted(kinds, key=len, reverse=True):          # 長い語から(「芝桜」の中の「桜」は数えない)
        if k in rest:
            have.add(k)
            rest = rest.replace(k, " ")
    have |= {x["name"] for k in list(have) for x in SP.resolve_all(k)}
    subject_words = [w for t in c["card_themes"] if t.get("subject") in (subjects or []) and t.get("subject") not in (c.get("species_drop_subjects") or [])
                     for w in t["words"]]                 # 紅葉・野鳥の質問は、候補が名所(種でない)なので、その対象の話(イチョウ・カエデ・カモ)は残す
    keep = []
    for k in cards:
        if k.get("link") == c["card_links"]["theme"]:
            sp = _card_species(k)
            blob = " ".join([k.get("title") or "", k.get("place") or "", k.get("subject") or ""])
            if sp and not sp & have and not any(w in blob for w in subject_words):
                continue
        keep.append(k)
    return [{**k, "id": f"K{i + 1:03d}"} for i, k in enumerate(keep)]


def _place_extra_ok(question, res, cands, towns, F, c, subjects=()):
    """段階81 第1部 3: 場所を聞く質問で、語りの材料を足すときに使ってよいカードか。
    一般の話は候補・質問の種のものだけ(_drop_unrelated_general と同じ判定)。場所の話は、質問の場所・市区町村・候補の名所に結びつくものだけ。"""
    from . import knowledge as K
    names = [n for n in list(_question_places(question, res)) + list(towns or []) + [r["name"] for r in cands]
             + [n for r in cands for n in r.get("merged_from") or []] if n and len(n) >= 2]

    def ok(r):
        if _general_card(r, c):
            k = {**r, "link": c["card_links"]["theme"]}
            return bool(_drop_unrelated_general([k], question, cands, F, c, subjects))
        return any(K.place_match(r, n) for n in names)
    return ok


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
        topics = _event_topics(event_texts, c)          # 段階77 の判断 3: 行事の対象(地質・野鳥など)まで絞る。地名の一致だけでは入れない
        push([r for r in _place_cards(shown, names, c) if _card_topic_hit(r, topics)],
             L["place"], c["place_cards_max"])
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
    route = res.get("route") or (res.get("cond") or {}).get("route")
    if route not in (c.get("species_card_skip_routes") or []):
        push(_species_cards(question, shown, c, route), L["species"], c["species_cards_max"])   # 段階79 第3部: 種のカード(「<種>一般」)
    try:                                                  # 質問の話題のカード(種の名前で引けたもの以外は一般の話として扱う)
        push([r for r in intent.cards_for(question) if _general_card(r, c) and not _excluded_topic(r, question, c)], L["theme"], c["species_cards_max"])
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
            hit = sum(1 for w in tw if species_hit([w], blob, c))      # 段階80 E(提案1): 桜の語で芝桜のカードを引かない
            if hit:
                theme.append((-hit, r.get("title") or "", r))
        push([r for _h, _t, r in sorted(theme, key=lambda x: (x[0], x[1]))], L["theme"])
    return _card_rows(out, c)


def _species_cards(question, shown, c, route=None):
    """種の名前(梅・桜など)に当たるカードを、場所の欄が「<種>一般」のものを先に、聞かれた種ごとに順に 1 枚ずつ並べる
    (「梅と桜の見分け方」で桜のカードだけにならないように)。
    段階79 第4部の追記: 主題か場所の欄で種に当たるものを、題名だけで当たるもの(「ロウバイ(梅の仲間ではない)」)より先に。
    質問の経路に合う語りの種類(違いの質問なら「見分け方」。guide_mode.yaml の species_card_prefer)の文が多いものを先に。"""
    prefer = (c.get("species_card_prefer") or {}).get(route or "")
    from . import season_place as SP
    try:
        sps = SP.resolve_all(question)
    except (KeyError, TypeError, ValueError):
        return []
    groups = []
    for sp in sps:
        words = [w for w in list(sp.get("match") or []) + list(sp.get("includes") or []) + list(sp.get("words") or [])]
        g = [r for r in shown if species_hit(words, " ".join([r.get("title") or "", r.get("subject") or "", r.get("place") or ""]), c)]
        g.sort(key=lambda r: (not str(r.get("place") or "").endswith(c["species_card_place_suffix"]),
                              not species_hit(words, " ".join([r.get("subject") or "", r.get("place") or ""]), c),
                              -sum(1 for n in (r.get("narrative") or []) if prefer and n == prefer),
                              r.get("title") or ""))
        groups.append(g)
    out, seen = [], set()
    for i in range(max((len(g) for g in groups), default=0)):
        for g in groups:
            if i < len(g) and (g[i].get("title"), g[i].get("place")) not in seen:
                seen.add((g[i].get("title"), g[i].get("place")))
                out.append(g[i])
    return out


def _excluded_topic(card, question, c):
    """段階80 E(提案1): カードの題名・主題・場所の欄に、種の名前を含む別の語(芝桜・秋桜・梅雨など)があり、その語が質問にないか
    (桜の質問に芝桜のカードを一般の話として入れない)。"""
    ex = c.get("species_blob_exclude_re")
    if not ex:
        return False
    head = " ".join([card.get("title") or "", card.get("subject") or "", card.get("place") or ""])
    return any(m.group(0) not in (question or "") for m in re.finditer(ex, head))


def species_hit(words, blob, c=None):
    """段階79 第3部: 種の名前が文にあるか。別の語の一部(「梅雨」の梅)は数えない(guide_mode.yaml の species_blob_exclude_re)。"""
    c = c or cfg()
    ws = [w for w in words if w]
    # 聞かれた種の名前そのものに当たる語(「芝桜」の質問の芝桜)は外さない(段階79 第4部の追記)
    b = re.sub(c.get("species_blob_exclude_re") or r"(?!)", lambda m: m.group(0) if any(m.group(0) in w for w in ws) else "", blob or "")
    return any(w in b for w in ws)


def _narrative(cards, question, cond, cands, sprows, months, c, extra_ok=None):
    """段階78 第3部 1: 語りの材料。少なければ、候補の場所・種・テーマに結びつくカードを足す(cards に追記。id は続きの番号)。"""
    from . import guide_materials as GM
    from . import guide_narrative as GN
    from . import knowledge as K
    N = c["narrative"]
    spw = GM.species_match_words(question)

    def pool():                                           # 種の質問は、その種の話のカードだけを材料にする(関係のない種の話で語らない)
        if not spw:
            return cards
        return [k for k in cards if species_hit(spw, " ".join([k.get("title") or "", k.get("place") or ""] + list(k.get("facts") or [])), c)]
    mat = GN.materials(pool(), N)
    if len(mat["items"]) >= N["min_items"] or cond.get("route") in N["skip_routes"] or cond.get("intent") == "event":
        return mat
    try:
        shown = K.load_shown()
    except (OSError, ValueError):
        return mat
    names = [r["name"] for r in cands if r.get("chosen")][:5] + [r["name"] for r in sprows][:5] + list(_question_places(question, {"cond": cond}))
    words = GM.species_match_words(question) + _theme_words(question, cond.get("subjects") or [], c)
    for r in GN.extra_cards(shown, cards, names, words, months, N, require_words=spw):
        if extra_ok and not extra_ok(r):                  # 段階81 第1部 3: 場所を聞く質問では、聞かれていない場所・種の話を足さない
            continue
        src = r.get("source") or {}
        facts = [seireki(x) for x in r.get("facts") or []]
        cards.append({"id": f"K{len(cards) + 1:03d}", "title": r.get("title"), "category": r.get("category"), "place": r.get("place"),
                      "link": c["card_links"]["theme"] if _general_card(r, c) else c["card_links"]["place"], "narrative": r.get("narrative"), "where": _where(r),
                      "facts": facts, "months": (r.get("condition") or {}).get("months"), "confidence": r.get("confidence"),
                      "source": src.get("name"), "url": src.get("url"), "checked_on": src.get("checked_on"),
                      "source_class": _source_class(src.get("url")), "values": values(" ".join(facts), c),
                     **({"contrasts": r["contrasts"]} if r.get("contrasts") else {})})   # 段階82 の続き: 2 つの種の見分け方(照合が読む)
    return GN.materials(pool(), N)


def _event_topics(event_texts, c):
    """行事の本文 → 行事の対象の語の組(地質・野鳥など。event_topics の語が行事の本文にあるもの)。"""
    blob = " ".join(event_texts or [])
    return [t for t in c["event_topics"] if any(w in blob for w in t["event_words"])]


def _card_topic_hit(card, topics):
    blob = " ".join([card.get("title") or "", card.get("subject") or "", card.get("category") or ""])     # 事実の文の語では選ばない(何の話かで選ぶ)
    return any(any(w in blob for w in t["card_words"]) for t in topics)


def _where(card):
    """段階79 第1部 4: カードの場所に、どこの話か(都県と市区町村)を付けた語。"""
    from . import guide_narrative as GN
    try:
        return GN.place_label(card)
    except (OSError, ValueError, KeyError, TypeError):
        return card.get("place")


def _card_rows(out, c):
    rows = []
    for i, (r, link) in enumerate(out, 1):
        src = r.get("source") or {}
        facts = [seireki(x) for x in r.get("facts") or []]
        rows.append({"id": f"K{i:03d}", "title": r.get("title"), "category": r.get("category"), "place": r.get("place"), "link": link,
                     "narrative": r.get("narrative"), "where": _where(r),
                     "facts": facts, "months": (r.get("condition") or {}).get("months"), "confidence": r.get("confidence"),
                     "source": src.get("name"), "url": src.get("url"), "checked_on": src.get("checked_on"),
                     "source_class": _source_class(src.get("url")), "values": values(" ".join(facts), c),
                     **({"contrasts": r["contrasts"]} if r.get("contrasts") else {})})   # 段階82 の続き: 2 つの種の見分け方(照合が読む)
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
        by = (rng.get("by_origin") or {}).get(origin)
        if by is None and origin and rng.get("from") != origin:     # 段階80 C(提案8): 出発地の距離がないときは、既定の出発地の距離を使わず出し直す
            from . import guide_materials as GM
            by = GM.straight_range(e["name"], origin, prefecture=e.get("prefecture"), city=e.get("municipality"))[0] or {"km": None}
        by = by or rng
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


def bird_highlights(question, cond, res, months, cands, c):
    """段階79 第2部: 範囲の指定がない野鳥の質問 → 季節の目玉がある観察地(最大 max 件。地域の組と目玉の種類が偏らないように)。
    → [{name, prefecture, city, group, theme, label, cards}]。範囲・場所・種の指定がある質問、野鳥以外の質問は []。"""
    from . import guide_materials as GM
    from . import knowledge as K
    H = c.get("bird_highlights") or {}
    if not H.get("sites") or (cond.get("subjects") or []) != ["birds"]:
        return []
    qp = [x for x in _question_places(question, res) if not _general_card({"place": x}, c)]     # 「渡り鳥は…」はテーマの語で場所ではない
    if cond.get("region") or cond.get("area_names") or GM.species_match_words(question) or qp:
        return []
    try:
        shown = [r for r in K.load_shown() if not r.get("retired")]
    except (OSError, ValueError):
        return []
    pri = {k: i for i, k in enumerate(c.get("brief_category_order") or K.cfg()["category_priority"])}
    months = sorted({(m - 1 + d) % 12 + 1 for m in months for d in range(H.get("months_ahead", 0) + 1)})   # この季節(対象の月と、そのすぐあと)
    rows = []
    for s in H["sites"]:
        cs = [r for r in shown if r.get("place") == s["card_place"] and not isinstance(r.get("closure"), dict)]
        ms = {m for r in cs for m in (r.get("condition") or {}).get("months") or []}
        if not cs or not ms & set(months):
            continue                                       # その場所のカードの月が対象の月に当たらない(季節の外)
        cs = [r for r in cs if not (r.get("condition") or {}).get("months") or set(r["condition"]["months"]) & set(months)]
        cs.sort(key=lambda r: (pri.get(r.get("category"), len(pri)), r.get("title") or ""))
        rows.append({**s, "group": _group_of(s["prefecture"], c), "cards": cs[: H.get("cards_per_site", 2)]})
    have = {r["name"] for r in cands if r.get("chosen")}
    rows = [r for r in rows if r["name"] not in have]
    groups = []
    for r in rows:
        if r["group"] not in groups:
            groups.append(r["group"])
    out, seen_t = [], set()
    while len(out) < min(H["max"], len(rows)):
        took = False
        for g in groups:
            pool = [r for r in rows if r["group"] == g and r not in out]
            if not pool or len(out) >= H["max"]:
                continue
            pick = next((r for r in pool if r["theme"] not in seen_t), pool[0])
            out.append(pick)
            seen_t.add(pick["theme"])
            took = True
        if not took:
            break
    return out if len(out) >= H.get("min", 1) else []


def _add_highlight_cards(cards, hl, c):
    """観察地の目玉のカードを資料のカードに足す(すでにあるカードは足さない)。"""
    seen = {k.get("title") for k in cards}
    add = []
    for h in hl:
        for r in h["cards"]:
            if r.get("title") not in seen:
                seen.add(r.get("title"))
                add.append((r, c["card_links"]["place"]))
    if not add:
        return cards
    rows = _card_rows(add, c)
    for i, k in enumerate(rows, len(cards) + 1):
        k["id"] = f"K{i:03d}"
    return cards + rows


def _highlight_materials(mat, cards, hl, c):
    """語りの材料に、観察地ごとの目玉の文を 1 点ずつ足す(種類「観察地の目玉」。カードの文のうち、その他でない文を先に)。"""
    from . import guide_narrative as GN
    N = c["narrative"]
    by_title = {k.get("title"): k for k in cards}
    items = list(mat.get("items") or [])
    have = {(i.get("card"), i.get("text")) for i in items}
    for h in hl:
        birds = [w for w in re.split(r"[・()（）とな冬のど\s]+", h.get("label") or "") if len(w) >= 2]
        best = None
        for title in [k.get("title") for k in h["cards"]]:
            k = by_title.get(title)
            if not k:
                continue
            for text, kind in zip(k.get("facts") or [], GN.kinds_of(k, N)):
                if re.search(N["not_material_re"], text) or (k.get("id"), text) in have:
                    continue
                score = (-sum(1 for w in birds if w in text), kind == N["other"])      # 目玉の鳥の名前がある文を先に、続けて語りの種類のある文
                if best is None or score < best[0]:
                    best = (score, k, text)
        if best:
            items.append({"kind": c["bird_highlights"]["material_kind"], "card": best[1].get("id"), "title": best[1].get("title"),
                          "place": f"{h['name']}・{h['prefecture']}{h['city']}", "text": best[2]})
    return {**mat, "items": items}


def _alt_filter(typ, question, cond, cands, clos, c):
    """段階78 第1部 4: 例年の目安の候補(遠くの代わりの行き先)を添えるか。
    種を聞く質問: 聞かれた種の候補だけ(ほかの種の行き先は付けない)。場所を聞く質問: その場所が今は楽しめない
    (対象の日が冬季閉鎖の時期に当たる・その場所の候補がない)ときだけ。そのほか(「今週末の紅葉」「今見られる花」)は今までどおり。"""
    from . import guide_materials as GM
    if cond.get("route") == "unknown_place":           # 段階80 A(提案4): 辞書にない地名は、別の場所の候補に置き換えない(調べる対象にする)
        return []
    words = GM.species_match_words(question)
    if words:
        return [t for t in typ if any(w in " ".join([t.get("theme") or "", *(t.get("kinds") or []), t.get("name") or ""]) for w in words)]
    if cond.get("route") in (c.get("alt_place_routes") or []) or cond.get("area_names"):
        closed = any(hit for _card, hit in clos)
        has_now = any(r.get("current_state") or r.get("basis") == "current" for r in cands)
        return typ if (not has_now and (closed or not cands)) else []
    return typ


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
                         "distance_km": r.get("distance_km"), "distance_estimated": bool(r.get("distance_estimated")),
                         "score": r.get("score"), "breakdown": r.get("breakdown"),
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
    if (res.get("route") or (res.get("cond") or {}).get("route")) == "unknown_place":    # 段階80 A(提案4)
        line = cfg()["unknown_place_missing"]
        try:
            unk = PG.unknown_places(question)
        except (KeyError, TypeError, ValueError):
            unk = []
        out += [line.format(name=p) for p in unk]
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
    from . import species_alias
    asked = question
    question, renamed = species_alias.normalize(question)   # 段階82 第1部: 資料・題・答えは認識した種の名前(カタカナ)で
    work = brief_dir(env) / f"{bid}.work"
    if work.exists():
        shutil.rmtree(work)                              # 同じ資料の作り直し(前回の作業の残りで結果を変えない)
    res = AR.run(question, now=now, env=env, workdir=work, quiet=True, clock=clock, obs_kw=obs_kw)
    cond = res.get("cond") or {}
    pending = _pending_urls()
    F = _Facts(c, pending)
    cands, picks, extra = _candidates(work, c)
    fpath = work / "facts.json"
    known_pubs = _plan_facts(F, work, cands, picks, extra)
    if (cond.get("route") in (c.get("alt_place_routes") or [])) and cond.get("area_names") and not cands:
        cands += _area_plan(F, question, cond, now, env, work, c, clock, obs_kw, known_pubs)   # 段階78 第2部 1: エリア・山域の名所の計画
    from . import guide_materials as GM
    sprows = GM.species_rows(question, cond, env, c)           # 段階78 第2部 2・3: 種の名所の一覧
    _line_facts(F, res.get("text") or "", c, known_pubs, skip_blocks=bool(cands),
                skip_names={r["name"] for r in sprows} | {r["merged_from"] for r in sprows if r.get("merged_from")}
                | set(getattr(sprows, "dropped", ()) or ()))
    _species_facts(F, sprows, cands, cond, c)
    if sprows and cond.get("defaulted_date") and (c["species_rows"].get("spread") or {}):
        _species_leads(F, sprows, now, c)                       # 段階78 の追記: 全体の目安を資料に入った名所の時期から
    _place_records(F, question, cands, cond, c, env)          # 段階78 第4部: 質問の場所の記録(その場で調べた名所を含む)
    if prev:
        try:
            pb = load(prev, env)
            for f in [x for x in pb.get("facts", []) if not (c.get("prev_one_level") and x.get("inherited"))][: c["max_prev_facts"]]:
                row = F.add(f["kind"], f["content"], place=f.get("place"), source=f.get("source"), url=f.get("url"),
                      source_class=f.get("source_class"), observed=f.get("observed"), read_at=f.get("read_at"), extra=f.get("fields"))
                if row:
                    row["inherited"] = True
        except (OSError, ValueError, KeyError):
            pb = None
    else:
        pb = None
    months = _target_months(cond, now)
    scope = (json.loads(fpath.read_text(encoding="utf-8")).get("scope") if fpath.exists() else None) or AR_scope(question, cond)
    typ = typical_candidates(cond, now, scope, {r["name"] for r in cands}, c, pending)
    names = [r["name"] for r in cands] + _question_places(question, res)
    clos = closures_for(names, months, c)
    typ = _alt_filter(typ, question, cond, cands, clos, c)       # 段階78 第1部 4: 関係のない代わりの行き先を付けない
    for t in typ:
        F.add("typical", f"{t['name']}({t['prefecture']}{t.get('municipality') or ''}): 例年 {t['text']}"
              + (f"({'・'.join(t['kinds'])})" if t["kinds"] else ""), place=t["name"], source=t.get("publisher"), url=t["url"],
              source_class=t["source_class"], extra={"_pref": t["prefecture"], "_city": t.get("municipality")})
        cands.append({"subject": None, "rank": None, "name": t["name"], "chosen": False, "basis": "typical", "group": t["group"],
                      "prefecture": t["prefecture"], "city": t.get("municipality"), "distance_km": t.get("km"), "theme": t.get("theme"),
                      "reasons": [c["typical_candidates"]["label"]]})
    hl = bird_highlights(question, cond, res, months, cands, c)         # 段階79 第2部: 季節の目玉がある観察地
    for h in hl:
        cands.append({"subject": "birds", "rank": None, "name": h["name"], "chosen": False, "basis": "highlight", "group": h["group"],
                      "prefecture": h["prefecture"], "city": h["city"], "theme": h["label"], "highlight_cards": [k.get("title") for k in h["cards"]],
                      "reasons": [c["bird_highlights"]["label"]]})
    from . import guide_materials as GM
    q_areas = _question_areas(question, cond)              # 段階80 の追記3(本人の判断 2026-11-11): エリアの質問は、そのエリアの名所だけ
    area_label = "・".join(a["name"] for a in q_areas) or None
    if q_areas:
        towns = list(dict.fromkeys(ct for a in q_areas for ct in a["cities"]))
    else:
        towns = [] if (cond.get("area_names") or cond.get("region")) else GM.question_towns(question)
    if towns:                                             # 段階80 の追記(本人の判断 2026-11-11): 市区町村の名前の質問は、その市区町村の名所を候補にする
        cands, dropped = _town_candidates(F, cands, towns, cond, c, label=area_label, areas=q_areas)
        if extra and extra.get("no_this_year"):
            extra = {**extra, "no_this_year": [n for n in extra["no_this_year"] if n not in dropped]}
        if extra and dropped:
            extra = {**extra, "origin_line": None}
    for r in cands:
        if not r.get("prefecture") or not r.get("city"):      # 段階80 E(提案11): 場所の欄が空の候補は、名所の辞書の都県・市町村で補う
            info = GM.place_info(r["name"])
            r["prefecture"] = r.get("prefecture") or info.get("prefecture")
            r["city"] = r.get("city") or info.get("city")
        r.setdefault("basis", "current" if r.get("current_state") else "typical")
        r.setdefault("group", _group_of(r.get("prefecture"), c))
        if "distance_text" not in r:                          # 段階78 第1部 2・3: 直線と明記。見積もりの距離は出さない。東京湾の向こう側は数字なし
            km, label = GM.distance_text(r["name"], r.get("distance_km"), cond.get("origin"), estimated=bool(r.get("distance_estimated")),
                                         prefecture=r.get("prefecture"), city=r.get("city"), c=c)
            r["distance_km"], r["distance_text"] = km, label
    cands, merges, merge_conflicts = merge_same_candidates(cands, F, c)    # 段階80 の追記5(本人の判断 2026-11-12): 名前の形が違う同じ場所を 1 つに
    names = [r["name"] for r in cands] + [n for r in cands for n in r.get("merged_from") or []] + _question_places(question, res)
    for card, hit in closures_for(names, months, c):
        cl = card["closure"]
        note = c["closure_note"]["in_period"] if hit else c["closure_note"]["out_period"]
        season_txt = (cl.get("season") or {}).get("text")
        F.add("safety", f"{card.get('place')}: {cl.get('name')}" + (f"({cl.get('section')})" if cl.get("section") else "")
              + f" 例年の冬季閉鎖 {cl.get('typical')}" + (f"。{season_txt}" if season_txt else "") + f"。{note}",
              place=card.get("place"), source=(card.get("source") or {}).get("name"), url=(card.get("source") or {}).get("url"),
              source_class="official", extra={"in_target": hit})
    cards = _cards(_card_question(question), res, c, cand_names=[n for r in cands if r.get("chosen") or r.get("basis") == "town" for n in [r["name"], *(r.get("merged_from") or [])]], months=months,
                   event_texts=[f["content"] for f in F.rows if f["kind"] == "event"])
    if pb:
        seen = {k["title"] for k in cards}
        for k in pb.get("cards") or []:
            if k["title"] not in seen and len(cards) < c["max_cards"]:
                cards.append({**k, "id": f"K{len(cards) + 1:03d}"})
    if hl:
        cards = _add_highlight_cards(cards, hl, c)
    if towns:                                             # 段階80 の追記: 市区町村の質問では、ほかの場所の話のカードを一般の話として使わない
        cards = [{**k, "id": f"K{i + 1:03d}"} for i, k in enumerate(k for k in cards if k.get("link") != c["card_links"]["theme"] or _plain_general_card(k, c))]
    extra_ok = None
    if towns or q_areas or cond.get("region") or cond.get("area_names"):   # 段階81 第1部 3: 場所を聞く質問では、候補にない種の一般の話を入れない
        cards = _drop_unrelated_general(cards, question, cands, F, c, cond.get("subjects") or [])
        extra_ok = _place_extra_ok(question, res, cands, towns, F, c, cond.get("subjects") or [])
    if (res.get("route") or cond.get("route")) == "unknown_place":   # 段階80 A(提案4): 辞書にない地名の質問では、ほかの場所の話のカードを使わない(一般の話だけ)
        cards = [{**k, "id": f"K{i + 1:03d}"} for i, k in enumerate(k for k in cards if _plain_general_card(k, c))]
    cards = _theme_card_filter(cards, question)              # 段階82 第3部 2: テーマ(苔など)の質問は、そのテーマの話のカードだけ
    if _asked_themes(question):
        prev_ok = extra_ok
        extra_ok = lambda r, _p=prev_ok: (_p is None or _p(r)) and bool(_theme_card_filter([r], question))   # 語りの材料で足すカードも同じ
    open_q = is_open_question(question, cond, towns, q_areas, c)
    if open_q and not _asked_themes(question):           # 段階83 第3部 3.3: 場所や種を決めない質問は、暦のカードが主な材料(先に入れる)
        cards += calendar_cards(question, cond, cands, months, c, open_q, start=len(cards), have_titles=[k.get("title") for k in cards])
    mat = _narrative(cards, question, cond, cands, sprows, months, c, extra_ok=extra_ok)     # 段階78 第3部 1: 語りの材料
    if not open_q and not _asked_themes(question):       # ほかの質問は、場所の話・種の話の材料を先に作ってから暦を 2 点まで足す
        cal = calendar_cards(question, cond, cands, months, c, open_q, start=len(cards), have_titles=[k.get("title") for k in cards])
        if cal:
            from . import guide_narrative as GN
            N = c["narrative"]
            cards += cal
            extra_items = []
            for k in cal:
                for text, kind in zip(k.get("facts") or [], GN.kinds_of(k, N)):
                    if kind in N["kinds"]:
                        extra_items.append({"kind": kind, "card": k["id"], "title": k["title"], "place": k.get("where"), "text": text})
                        break
            order = {kd: i for i, kd in enumerate(N["kinds"])}
            items = sorted(list(mat.get("items") or []) + extra_items, key=lambda x: order.get(x["kind"], len(order)))
            mat = {**mat, "items": items, "missing": [kd for kd in (mat.get("missing") or []) if not any(i["kind"] == kd for i in items)]}
    tale = tale_cards(question, cond, cands, sprows, c, start=len(cards))      # 段階83 第4部: 小話(1 点まで)
    if tale:
        cards += tale
        mat = {**mat, "items": list(mat.get("items") or []) + [{"kind": c["tale"]["kind"], "card": k["id"], "title": k["title"],
                                                               "place": k.get("where") or k.get("place"), "text": k["facts"][0]} for k in tale]}
    if hl:
        mat = _highlight_materials(mat, cards, hl, c)
    from . import research as RS
    targets = [] if cond.get("route") in c["species_rows"]["routes_skip"] else RS.needs(question, cond, sprows, cands, cards, F.rows, c)   # 段階78 第4部 1
    if towns and cond.get("route") not in c["species_rows"]["routes_skip"]:
        targets += _tentative_targets(question, towns, area_label, cands, targets, c)
    researched = RS.already_researched(question, now, env)   # 段階82 第3部 4: 同じ質問で調べるのは 1 回だけ
    if researched:
        targets = []
    no_trait = _species_without_cards(question, cards)   # 段階82 第2部 1: 聞かれた種の話のカードが 0 枚なら、公的な解説を調べる
    T = c["species_traits"]
    if not researched:
        targets += [{"what": sp, "where": None, "why": T["research_why"].format(sp=sp), "kind": "species_card"}
                    for sp in no_trait if not any(t.get("what") == sp and t.get("kind") == "species_card" for t in targets)]
    sobs = seasonal_rows(question, {**cond, "_towns": towns}, cands, now, env, c)     # 段階83 第2部: 例年この時期の観察記録
    doc = {
        "schema": "ikimonobiyori-guide-brief/1", "id": bid, "question": question, "now": now.isoformat(),
        **({"asked": asked, "species_renamed": [list(x) for x in renamed]} if renamed else {}),
        "previous": {"id": prev, "question": (pb or {}).get("question")} if prev else None,
        "dates": _dates_block(cond, now), "intent": cond.get("intent"), "route": res.get("route") or cond.get("route"),
        "scope": "region" if cond.get("region") else "areas" if cond.get("area_names") else (scope or "default"),
        "region": cond.get("region"), "areas": cond.get("area_names"), "subjects": cond.get("subjects"),
        "origin": cond.get("origin"), "origin_source": cond.get("origin_source"),
        "candidates": cands, "candidates_note": (extra or {}).get("origin_line"),
        "candidate_merges": merges, "candidate_merge_conflicts": merge_conflicts,
        "facts": F.rows, "seasonal_obs": sobs, "cards": cards, "narrative": mat,
        "missing": _missing(question, res, cands, F.rows, cards, extra)
        + ([c["town_candidates"]["none_missing"].format(where=area_label or "・".join(towns))] if towns and not cands else [])
        + [c["species_traits"]["missing_line"].format(sp=sp) for sp in no_trait]
        + ([c["research"]["done_line"]] if researched else [])
        + [f"調べる: {t['why']}" for t in targets],
        "research": {"targets": targets},
        **({"photos": fp} if (fp := form_photos(question, env)) else {}),
        "rules": list(c["rules"]),
        "fallback": {"text": res.get("text") or "", "stage": res.get("stage"), "status": res.get("status")},
    }
    return doc


def _card_row(r, cid, link, c, where=None):
    src = r.get("source") or {}
    facts = [seireki(x) for x in r.get("facts") or []]
    return {"id": cid, "title": r.get("title"), "category": r.get("category"), "place": r.get("place"), "link": link,
            "narrative": r.get("narrative"), "where": where or _where(r), "facts": facts, "months": (r.get("condition") or {}).get("months"),
            "confidence": r.get("confidence"), "source": src.get("name"), "url": src.get("url"), "checked_on": src.get("checked_on"),
            "source_class": _source_class(src.get("url")), "values": values(" ".join(facts), c)}


def word_hit(w, text, c=None):
    """段階83: 語が文にあるか。都県の名前(「神奈川」の「川」)と、カタカナ語の途中(「カワセミ」の「セミ」)の一致は数えない。"""
    c = c or cfg()
    t = re.sub(c["calendar"]["place_names_re"], "", text or "")
    if re.fullmatch(r"[ァ-ヶー]+", w):
        return bool(re.search(r"(?<![ァ-ヶー])" + re.escape(w) + r"(?![ァ-ヶー])", t))
    return w in t


def is_open_question(question, cond, towns=(), areas=(), c=None):
    """段階83 第3部: 場所や種を決めない質問(「今の見頃のものを教えて」「近くの公園で何が見られる?」「冬の雑木林の楽しみ方を教えて」)。"""
    c = c or cfg()
    from . import guide_materials as GM
    C = c["calendar"]
    if (cond.get("route") or "") in C["skip_routes"] or towns or areas or cond.get("area_names"):
        return False
    if GM.species_match_words(question):
        return False
    return any(w in question for w in C["open_words"]) or any(word_hit(w, question, c) for ws in C["env_words"].values() for w in ws)


def question_environments(question, cands=(), c=None):
    """質問(なければ選んだ候補の名前)の語 → 季節の暦の環境の一覧。"""
    c = c or cfg()
    C = c["calendar"]

    def envs(text):
        out, rest = [], re.sub(C["place_names_re"], "", text or "")
        for env, ws in C["env_words"].items():
            hit = next((w for w in ws if word_hit(w, rest, c)), None)
            if hit:
                out.append(env)
                rest = rest.replace(hit, "")
        return out
    got = envs(question)
    if got:
        return got
    names = " ".join(r["name"] for r in cands if r.get("chosen"))
    return envs(names)


def _calendar_months(question, months, c):
    qm = question_month(question, c)
    if qm:
        return [qm]
    for season, ms in c["calendar"]["season_months"].items():
        if f"{season}の" in question:
            return list(ms)
    return list(months or [])


def calendar_cards(question, cond, cands, months, c, open_q, start=0, shown=None, have_titles=()):
    """段階83 第3部: 対象の月・環境に合う季節の暦のカード(場所や種を決めない質問は max_cards_open、ほかは max_cards)。"""
    from . import knowledge as K
    C = c["calendar"]
    if (cond.get("route") or "") in C["skip_routes"]:
        return []
    try:
        rows = [r for r in (shown if shown is not None else K.calendar_pool()) if r.get("calendar")]
    except (OSError, ValueError):
        return []
    rows = [r for r in rows if r.get("title") not in set(have_titles or ())]      # 資料にすでにあるカードは足さない
    ms = _calendar_months(question, months, c)
    envs = question_environments(question, cands, c)
    if not envs and not open_q:
        return []
    hits = [r for r in rows if set((r["calendar"].get("months") or [])) & set(ms) and (not envs or r["calendar"].get("environment") in envs)]
    want = [t for cid in seasonal_categories(question, cond) for t in (C.get("category_targets") or {}).get(cid, [])]
    from . import seasonal_obs as SO
    if want and len(seasonal_categories(question, cond)) < len(SO.load_policy()["categories"]):   # 段階83: 虫・鳥など種類を聞く質問は、その対象の暦だけ
        hits = [r for r in hits if r["calendar"].get("target") in want]
    autumn = [t for w, ts in (C.get("word_targets") or {}).items() if w in question for t in ts]
    if autumn:                                             # 紅葉の質問は木の葉や実の暦だけ
        hits = [r for r in hits if r["calendar"].get("target") in autumn]
    order = {e: i for i, e in enumerate(envs or C["environments"])}
    hits.sort(key=lambda r: (order.get(r["calendar"].get("environment"), len(order)), r.get("title") or ""))
    picked, seen_env = [], {}
    limit = C["max_cards_open"] if open_q else C["max_cards"]
    for r in hits:                                     # 同じ環境ばかりにしない(環境ごとに順に 1 枚ずつ)
        seen_env.setdefault(r["calendar"].get("environment"), []).append(r)
    while len(picked) < limit and any(seen_env.values()):
        for env in sorted(seen_env, key=lambda e: order.get(e, len(order))):
            if seen_env[env] and len(picked) < limit:
                picked.append(seen_env[env].pop(0))
    return [_card_row(r, f"K{start + i + 1:03d}", C["link"], c, where=(r["calendar"].get("where") or r["calendar"].get("environment")))
            for i, r in enumerate(picked)]


def tale_cards(question, cond, cands, sprows, c, start=0, shown=None):
    """段階83 第4部: 小話のカード(質問・選んだ候補・種の名所の種と場所の名前に当たるもの。1 枚まで)。"""
    from . import knowledge as K
    T = c["tale"]
    if (cond.get("route") or "") in T["skip_routes"]:
        return []
    try:
        rows = [r for r in (shown if shown is not None else K.load_shown(include_special=True)) if r.get("tale")]
    except (OSError, ValueError):
        return []
    words = [question] + [r["name"] for r in cands if r.get("chosen")][:3]
    from . import guide_materials as GM
    spw = GM.species_match_words(question)
    best = []
    for r in rows:
        allnames = [n for n in [r.get("subject"), r.get("place"), *(r.get("subject_aliases") or []), *(r.get("place_aliases") or [])] if n]
        names = [n for n in allnames if len(n) >= 2]
        score = sum(3 if n in question else 1 for n in names if any(n in w for w in words))
        if not score and spw and species_hit(spw, question, c) and species_hit(spw, " ".join(allnames), c):   # 「桜」「梅」(1 文字の種。梅雨は数えない)
            score = 3
        if score:
            best.append((-score, r.get("title") or "", r))
    best.sort(key=lambda x: x[:2])
    return [_card_row(r, f"K{start + i + 1:03d}", T["link"], c) for i, (_s, _t, r) in enumerate(best[: T["max_cards"]])]


def _seasonal_region(cond, cands, c):
    """段階83 第2部: 観察記録の集計の地域の組。場所を挙げた質問(エリア・地域・市区町村)は候補(選んだもの → すべて)の都県で多い組、
    場所を挙げない質問と候補のないときは出発地の都県の組(候補の名所の都県に引っぱられない)。"""
    from collections import Counter
    if not (cond.get("area_names") or cond.get("region") or cond.get("_towns")):
        return _group_of(_origin_pref(cond.get("origin")), c)
    for pool in ([r for r in cands if r.get("chosen")], cands):
        groups = Counter(g for g in (_group_of(r.get("prefecture"), c) for r in pool) if g)
        if groups:
            return groups.most_common(1)[0][0]
    return _group_of(_origin_pref(cond.get("origin")), c)


def question_month(question, c=None):
    """段階83: 質問の「2月の」「5月に」のような月(1〜12)。なければ None。"""
    c = c or cfg()
    m = re.search(c["calendar"]["month_re"], question or "")
    if not m:
        return None
    v = int(unicodedata.normalize("NFKC", m.group(1)))
    return v if 1 <= v <= 12 else None


def _seasonal_date(cond, now, question=None):
    """観察記録の対象の日。質問に月があれば、その月(今月より前なら来年)の中ほどの日。なければ質問の対象の日。"""
    qm = question_month(question) if question else None
    if qm:
        y = now.year + (1 if qm < now.month else 0)
        return date(y, qm, cfg()["calendar"]["month_mid_day"])
    for per in cond.get("periods") or []:
        for d in per or []:
            try:
                return date.fromisoformat(str(d)[:10])
            except ValueError:
                continue
    return now.date()


def seasonal_categories(question, cond, sp=None):
    """質問の語 → 観察記録の分類の一覧。分類の語がなければすべて。紅葉だけの質問・種や名所を決めた経路では空。"""
    from . import seasonal_obs as SO
    sp = sp or SO.load_policy()
    B = sp["brief"]
    if (cond.get("route") or "") in (B.get("skip_routes") or []):
        return []
    hit = [cid for cid, ws in B["category_words"].items() if any(word_hit(w, question) for w in ws)]
    if hit:
        return hit
    if (cond.get("subjects") or []) == ["autumn_leaves"] or ("紅葉" in question and not hit):
        return []
    return [x["id"] for x in sp["categories"]]


def seasonal_rows(question, cond, cands, now, env, c):
    """段階83 第2部: 資料の節「例年この時期の観察記録」の行(分類ごとに 1 行、[O001]…)。集計がなければ空。"""
    from . import seasonal_obs as SO
    sp = SO.load_policy()
    cats = seasonal_categories(question, cond, sp)
    if not cats:
        return []
    envs = question_environments(question, (), c)
    gname = next((sp["brief"]["env_regions"][e] for e in envs if e in (sp["brief"].get("env_regions") or {})), None)         if not (cond.get("area_names") or cond.get("region") or cond.get("_towns")) else None
    gname = gname or _seasonal_region(cond, cands, c)
    reg = SO.region(gname, sp) if gname else None
    if not reg:
        return []
    d = _seasonal_date(cond, now, question)
    asked = [ms for season, ms in c["calendar"]["season_months"].items() if f"{season}の" in question]
    if asked and not any(d.month in ms for ms in asked):     # 「冬の雑木林」を 11 月に聞かれたとき: 対象の日の記録は聞かれた季節の話ではない
        return []
    win = SO.species_window(reg["id"], d, env, sp)
    if not win:
        return []
    B = sp["brief"]
    n = SO._v(B["max_per_category"])
    years = win.get("years") or []
    ytxt = f"過去{len(years)}年({years[0]}〜{years[-1]}年)" if years else ""
    wtxt = SO.weeks_text(d, win["weeks"], sp) or ""
    from . import guide_materials as GM
    spw = GM.species_match_words(question)
    if spw:                                                # 種を挙げた質問: その種を含む分類だけ(なければ入れない)
        cats = [cid for cid in cats if any(species_hit(spw, r["name"], c) for r in win["categories"].get(cid) or [])]
    out = []
    for cid in cats:
        rows = (win["categories"].get(cid) or [])[:n]
        if not rows:
            continue
        label = next(x["label"] for x in sp["categories"] if x["id"] == cid)
        items = [B["species_item"].format(name=r["name"], count=r["count"],
                                          flower=B["flower_part"].format(n=r["flower"]) if r.get("flower_usable") else "") for r in rows]
        content = B["line"].format(region=reg["name"], label=label, weeks=wtxt, years=ytxt, species="、".join(items))
        out.append({"id": f"O{len(out) + 1:03d}", "kind": "seasonal_obs", "kind_label": B["kind_label"], "category": cid,
                    "region": reg["name"], "content": content, "species": [r["name"] for r in rows],
                    "flowering": [r["name"] for r in rows if r.get("flower_usable")],
                    "values": values(content, c), "source": B["source_name"], "source_class": None, "url": B["source_url"],
                    "fetched_at": win.get("fetched_at"), "complete": win.get("complete")})
    return out


def form_photos(question, env=None):
    """段階82 の続き(本人の判断 2026-11-13 の 5): 聞かれた種の、季節の姿の写真(写真の対応表の「チングルマ(綿毛)」のような
    「種の名前(姿)」の項目)のうち、点検で可の写真があるもの → [{name, species, word}]。答えに姿の語(綿毛)を書くと、ページに載る。"""
    from . import guide_materials as GM
    from . import guide_photos as GPh
    sps = set(GM.species_names(question))
    if not sps:
        return []
    out = []
    try:
        table = GPh.load_table(env) if env else GPh.load_table()
    except (OSError, ValueError):
        return []
    for n, r in table.items():
        m = re.match(r"^(.+?)\((.+)\)$", n)
        if m and m.group(1) in sps and GPh.checked_ok(r["taxon_id"], env) and GPh.load_photo(r["taxon_id"], env):
            out.append({"name": n, "species": m.group(1), "word": m.group(2)})
    return out


def _card_question(question):
    """段階82 第1部 6: カードを引く文。質問の種の名前が漢字・ひらがな(「紫陽花」「すいせん」)のとき、カタカナの名前を後ろに添える
    (カードは種の語をカタカナで探すので、書き方でカードが減らないように)。"""
    from . import season_place as SP
    from . import species_alias as SA
    al = (SP.cfg().get("guide_page") or {}).get("aliases") or {}
    groups = SA.word_groups()
    q = question
    for n in SA.species_in(question):
        k = al.get(n, n)
        if k in q or not re.fullmatch(cfg()["species_word_re"], k):   # カタカナ 3 字以上の名前だけ(ウメ・フジは今までどおり)
            continue
        for w in sorted(groups.get(n, {n}), key=len, reverse=True):   # 漢字・ひらがなの書き方をカタカナの名前に置き換える(「彼岸花」の「花」で花の一般の話を引かない)
            if w and w != k and w in q:
                # 場所の名前の一部(「本埜白鳥の郷」「犀川白鳥湖」)は置き換えない: 前が漢字・カタカナの字か、後ろが場所の語のもの
                q = re.sub(r"(?<![一-龥々ァ-ヶー])" + re.escape(w) + r"(?!の郷|湖|沼|橋|公苑|公園|池)", k, q)
                break
    return q


def _asked_themes(question):
    from . import knowledge as K
    from . import species_alias as SA
    tc = K.themes_cfg()
    return [t for t in tc["themes"] if t["name"] in (tc.get("species_themes") or []) and t["name"] in SA.species_in(question)]


def _theme_card_filter(cards, question):
    """段階82 第3部 2: 質問にテーマ(themes.yaml の species_themes。苔)があるとき、テーマの語を含むのにそのテーマの話ではないカード
    (「コケや海藻の芽を食べる」が 1 行だけのミユビシギのカード)を落とす。テーマの語を含まないカードはそのまま。"""
    from . import knowledge as K
    tc = K.themes_cfg()
    asked = _asked_themes(question)
    if not asked:
        return cards
    keep = []
    for k in cards:
        blob = " ".join([k.get("title") or "", k.get("subject") or ""] + list(k.get("facts") or []))
        if any(any(w in blob for w in t["words"]) and t["name"] not in (k.get("themes") or K.themes_of(k, tc)) for t in asked):
            continue
        keep.append(k)
    return [{**k, "id": f"K{i + 1:03d}"} for i, k in enumerate(keep)]


def _species_without_cards(question, cards):
    """段階82 第2部: 質問の種のうち、その種の書き方が題・主題・事実に出るカードが 1 枚もないもの(仲間の総称は除く)。"""
    from . import species_alias as SA
    groups = SA.word_groups()
    skip = set(cfg()["species_traits"].get("group_words") or [])
    out = []
    for sp in SA.species_in(question):
        if sp in skip:
            continue
        ws = groups.get(sp, {sp})
        if not any(any(w in " ".join([k.get("title") or "", k.get("subject") or ""] + list(k.get("facts") or [])) for w in ws) for k in cards or []):
            out.append(sp)
    return out


def _dist(r):
    if r.get("distance_text"):
        return r["distance_text"]
    return f"直線で約{r['distance_km']}km" if r.get("distance_km") is not None else "距離は未計算"


def _loc(r):
    """段階80 E(提案11): 候補の場所の書き方(都県と市町村)。名所の名前が都県・市町村の名前で始まるときは重ねない
    (「埼玉県立自然の博物館(埼玉県…)」→「埼玉県立自然の博物館(長瀞町…)」)。"""
    name = r.get("name") or ""
    pref, city = r.get("prefecture") or "", r.get("city") or ""
    pref_stem = re.sub(r"(都|道|府|県)$", "", pref)
    city_stem = re.sub(r"(市|町|村|区)$", "", city)
    if pref and name.startswith(pref_stem):
        pref = ""
    if city and city_stem and name.startswith(city_stem):
        city = ""
    return f"{pref}{city}"


def render_md(doc):
    L = [f"# ガイドの資料 {doc['id']}", "", f"- 質問: {doc['question']}"]
    if doc.get("species_renamed"):                       # 段階82 第1部: 種の名前の読み替え
        L.append("- 種の名前: " + "・".join(f"{a} → {b}" for a, b in doc["species_renamed"]) + "(答えでは右の名前を使う)")
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
                tag = "種の名所" if r.get("basis") == "species" else "季節の目玉" if r.get("basis") == "highlight" else "例年の目安"
                L.append(f"- [{tag}・{r.get('group') or ''}] {r['name']}({_loc(r)} {_dist(r)})"
                         + (f"・{r['theme']}" if r.get("theme") else "") + (f"・{r['note']}" if r.get("note") else ""))
                continue
            L.append(f"{r['rank']}. [{r.get('subject') or ''}{'・今年の現況あり' if r.get('basis') == 'current' else '・例年の目安'}] {r['name']}({_loc(r)} {_dist(r)}・点 {r.get('score')}・"
                     f"{'選んだ' if r['chosen'] else '選ばなかった: ' + (r.get('not_chosen_reason') or '点数が下')}) {why}")
        L.append("")
    L += ["## 確かめた事実", ""]
    for f in doc["facts"]:
        src = f"{f.get('source') or '出典名なし'}・{'公式' if f.get('source_class') == 'official' else 'その他' if f.get('source_class') else '区分なし'}"
        when = "・".join(x for x in (f"観測 {f['observed']}" if f.get("observed") else "", f"取得 {f['read_at'][:10]}" if f.get("read_at") else "") if x)
        L.append(f"- [{f['id']}] {f['kind_label']}: {f['content']}({src}{'・' + when if when else ''}){' ' + f['url'] if f.get('url') else ''}")
    if not doc["facts"]:
        L.append("(なし)")
    if doc.get("seasonal_obs"):                            # 段階83 第2部
        from . import seasonal_obs as SO
        B = SO.load_policy()["brief"]
        L += ["", B["heading"], "", f"({B['source_name']}。{B['note']})"]
        L += [f"- [{r['id']}] {r['content']}" for r in doc["seasonal_obs"]]
    L += ["", "## 知識カード", ""]
    for k in doc["cards"]:
        L.append(f"- [{k['id']}] {k['title']}({k.get('link') or ''}・{k.get('category') or ''}・{k.get('where') or k.get('place') or ''}・{k.get('source')}・{k.get('checked_on')}に確認)")
        L += [f"  - {x}" for x in k["facts"]]
    if not doc["cards"]:
        L.append("(なし)")
    if doc.get("narrative") is not None:
        from . import guide_narrative as GN
        L += [""] + GN.render(doc["narrative"])
    if doc.get("photos"):                                   # 段階82 の続き: 種の季節の姿の写真(ページに載る)
        P = cfg()["form_photos"]
        L += ["", P["heading"], ""] + [P["line"].format(**p) for p in doc["photos"]]
    L += ["", "## 足りないもの", ""] + [f"- {x}" for x in doc["missing"] or ["(なし)"]]
    if (doc.get("research") or {}).get("targets"):
        from . import research as RS
        L += [""] + RS.lines_for(doc["id"], doc["research"]["targets"])
    L += ["", "## 決まり", ""] + [f"- {x}" for x in doc["rules"]]
    return NL.join(L) + NL


def save(doc, env=None):
    d = brief_dir(env)
    d.mkdir(parents=True, exist_ok=True)
    jp, mp = d / f"{doc['id']}.json", d / f"{doc['id']}.md"
    jp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    mp.write_text(render_md(doc), encoding="utf-8")
    return jp, mp
