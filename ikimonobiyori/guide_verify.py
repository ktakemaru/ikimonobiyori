"""段階75 第3部: 裏を取る(`ask verify <答えのファイル> --brief <資料のid>`)。通信しない・決定的。

AI がガイドとして書いた答えの下書きを、資料(guide_brief.py の briefs/<id>.json)と照らす。
- 下書きの形: 腐りやすい事実を含む文の終わりに根拠の印 [F012](確かめた事実)・[K034](知識カード)。最後に場所の一覧
  ([場所] の見出しのあとに「記録: 名前、名前」「知識: 名前(都県)、…」)。
- 印のある文: 印の id が資料にあり、文の中の日付・月・旬・時刻・料金・電話・URL・(今の)状態の語が、印の事実の値と合う。
  今の状態として書いた文の根拠が、今年の現況の事実であること(行事・例年の目安を今の状態にしない)。行事と期間・通行止めなどは、
  行事・施設・安全の事実かカードが根拠であること。
- 印のない文: 日付・時刻・金額・電話・URL、今の語と一緒の状態の語、行事の語と期間、通行止め・閉鎖・規制、
  記録にある場所の名前と月の表現が同じ文にあるもの、があれば不合格(場所の名前を含まない季節の説明は合格)。
- 場所の一覧: 記録の場所は辞書(名所カタログ・エリア・山・未確認の名所・資料の候補)にあること。知識で添えた場所は 3 か所まで・
  範囲の内の都県・「確かめていない」と分かる書き方。添えた場所は未確認の名所として記録する(ask record-unverified と同じ)。
- 今までの検査の部品: 使わない情報源・内部の言葉・作業の事情・最後の質問・引用(ask_verify.py)。範囲の外の都県。聞かれた場所のすり替え。
合格: 印と場所の一覧を取り除き、確かめた出典(名前・日付・公式かどうか)を並べた最終の文。不合格: 文ごとの理由と直し方。
書き直しは 2 回まで。3 回目も不合格なら、今の ask answer の答え(資料の fallback)を出す(必ず答えが出る)。
値と語は data/ask/guide_mode.yaml。"""
import json
import re
from datetime import date, datetime

from . import guide_brief as GB
from .paths import data_path

NL = "\n"


def cfg():
    return GB.cfg()


# ---- 下書きを分ける ----

def parse_draft(text, c=None):
    """下書き → {body: 本文の行, record: [名前], knowledge: [(名前, 都県, 市町村)], has_places: 一覧があるか}。"""
    c = c or cfg()
    d = c["draft"]
    lines = (text or "").splitlines()
    i = next((k for k, l in enumerate(lines) if l.strip() == d["places_heading"]), None)
    body = lines if i is None else lines[:i]
    rec, kn = [], []
    for l in ([] if i is None else lines[i + 1:]):
        s = l.strip()
        for key, out in ((d["places_record"], rec), (d["places_knowledge"], kn)):
            if s.startswith(key):
                for n in re.split(r"[、,，]", s[len(key):]):
                    n = n.strip()
                    if n and n not in ("なし", "(なし)"):
                        out.append(n)
    know = []
    for n in kn:
        m = re.match(r"^(.+?)[(（]([^)）・、]+)(?:[・、]([^)）]+))?[)）]$", n)
        know.append((m.group(1).strip(), m.group(2).strip(), (m.group(3) or "").strip() or None) if m else (n, None, None))
    return {"body": body, "record": rec, "knowledge": know, "has_places": i is not None}


def sentences(body, c=None):
    """本文の行 → [{line, text(印つき), clean(印なし), ids}]。行の頭の印は前の文のもの(「…です。[F001]」)。"""
    c = c or cfg()
    mre = re.compile(c["draft"]["marker_re"])
    out = []
    for ln, line in enumerate(body, 1):
        if not line.strip():
            continue
        segs = re.findall(r"[^。！？!?]+[。！？!?]?", line)
        cur = []
        for s in segs:
            m = re.match(r"^\s*((?:\[[FK]\d{3,}\]\s*)+)(.*)$", s)
            if m and (cur or out):
                if cur:
                    cur[-1] = cur[-1] + m.group(1)
                else:                                    # 行の頭の印は前の行の最後の文のもの
                    prev = out[-1]
                    prev["text"] += m.group(1).strip()
                    prev["ids"] = mre.findall(prev["text"])
                s = m.group(2)
            if s.strip():
                cur.append(s)
        for s in cur:
            ids = mre.findall(s)
            clean = re.sub(r"\s*" + c["draft"]["marker_re"], "", s).strip()
            if clean:
                out.append({"line": ln, "text": s.strip(), "clean": clean, "ids": ids})
    return out


def strip_markers(body, c=None):
    c = c or cfg()
    return NL.join(re.sub(r"\s*" + c["draft"]["marker_re"], "", l) for l in body).strip(NL) + NL


# ---- 照らす ----

def _jun_of(md):
    try:
        mo, d = (int(x) for x in md.split("/"))
    except ValueError:
        return None
    return f"{mo}月" + ("上旬" if d <= 10 else "中旬" if d <= 20 else "下旬")


def _union(rows):
    u = {k: set() for k in ("dates", "years", "months", "jun", "times", "money", "phones", "urls", "states", "people")}
    for r in rows:
        for k, v in (r.get("values") or {}).items():
            if k in u:
                u[k] |= set(v)
        if r.get("url"):
            u["urls"].add(r["url"])
    u["months"] |= {d.split("/")[0] for d in u["dates"]}
    u["jun"] |= {j for j in (_jun_of(d) for d in u["dates"]) if j}
    return u


def _err(code, s, detail, fix):
    return {"code": code, "line": s["line"] if s else 0, "sentence": (s or {}).get("clean", "")[:120], "detail": detail, "fix": fix}


def _now_state(s, v, c):
    return bool(v["states"]) and GB.has_any(c["now_words"], s) and not GB.has_any(c.get("honest_words") or [], s)


def _event_period(s, v, c):
    return GB.has_any(c["event_words"], s) and (bool(v["dates"] or v["months"] or v["jun"]) or GB.has_any(c["period_words"], s))


def check_marked(s, brief, c, allowed=()):
    facts = {f["id"]: f for f in brief.get("facts") or []}
    cards = {k["id"]: k for k in brief.get("cards") or []}
    errs = []
    rows = []
    for i in s["ids"]:
        r = facts.get(i) or cards.get(i)
        if r is None:
            errs.append(_err("unknown_id", s, f"印 [{i}] は資料にない", "資料にある id の印に直すか、その事実を書かない"))
        else:
            rows.append(r)
    if not rows:
        return errs
    v = GB.values(_without_allowed(s["clean"], allowed, keep_point=True), c)   # 今週末・来週末・対象の日の日付は印の事実と照らさない(段階76。「時点」の日付は照らす)
    u = _union(rows)
    for key, label in (("dates", "日付"), ("times", "時刻"), ("money", "料金"), ("phones", "電話"), ("urls", "URL"), ("people", "人数")):
        bad = [x for x in v[key] if x not in u[key]]
        if bad:
            errs.append(_err("value_mismatch", s, f"{label} {'・'.join(bad)} が印の事実({'・'.join(s['ids'])})にない",
                             f"印の事実にある{label}だけを書く(事実の値: {'・'.join(sorted(u[key])) or 'なし'})"))
    bad = [x for x in v["months"] if x not in u["months"]]
    if bad:
        errs.append(_err("month_mismatch", s, f"{'・'.join(m + '月' for m in bad)} が印の事実にない", "印の事実にある月だけを書く"))
    bad = [x for x in v["jun"] if x not in u["jun"]]
    if bad:
        errs.append(_err("month_mismatch", s, f"{'・'.join(bad)} が印の事実にない", "印の事実にある時期だけを書く"))
    typical_talk = GB.has_any(c.get("typical_words") or [], s["clean"]) and all(r.get("kind") in ("typical", None) or r["id"].startswith("K") for r in rows)
    if _now_state(s["clean"], v, c) and not typical_talk:
        cur = [r for r in rows if r.get("kind") == "current"]
        if not cur:
            kinds = "・".join(sorted({r.get("kind_label") or "知識カード" for r in rows}))
            errs.append(_err("now_state_not_current", s, f"今の状態の文の根拠が今年の現況ではない({kinds})",
                             "今年の現況の事実の印を付ける。なければ「今年の状況は確かめられていません」と書く(行事の期間・例年の目安を今の状態にしない)"))
        else:
            us = _union(cur)["states"]
            bad = [x for x in v["states"] if x not in us]
            if bad and not GB.has_any(c["stale_as_target"]["hedge_words"], s["clean"]):     # 段階77: 見込みの文の状態の語は今の状態ではない
                errs.append(_err("state_mismatch", s, f"状態の語 {'・'.join(bad)} が今年の現況の事実({'・'.join(r['id'] for r in cur)})にない",
                                 f"事実の状態の語のまま書く(事実: {'・'.join(r['content'][:40] for r in cur)})"))
    err = _stale_as_target(s, v, rows, brief, c)
    if err:
        errs.append(err)
    if _event_period(s["clean"], v, c) and not any(r.get("kind") in ("event", "facility") or r["id"].startswith("K") for r in rows):
        errs.append(_err("event_not_event_fact", s, "行事と期間の文の根拠が行事の事実ではない", "行事の事実の印を付ける。なければ行事を書かない"))
    if GB.has_any(c["closure_words"], s["clean"]) and not any(r.get("kind") in ("safety", "facility", "event") or r["id"].startswith("K") for r in rows):
        errs.append(_err("closure_not_fact", s, "通行止め・規制・休園の文の根拠が安全・施設の事実ではない", "安全・規制か施設の事実の印を付ける。なければ書かない"))
    return errs


def _without_allowed(text, allowed_dates, keep_point=False):
    """印なしで書いてよい日付(「11/14」「11月14日」「11月14日・15日」)を文から除く(月の表現として数えない)。
    keep_point: 「○/○時点」「○/○現在」の日付は除かない(印の事実の日付と照らす)。"""
    tail = r"(?!\s*(?:時点|現在))" if keep_point else ""
    for md in allowed_dates:
        mo, d = md.split("/")
        text = re.sub(rf"(?<!\d){mo}月{d}日(?:[・、と]\d{{1,2}}日)*{tail}|(?<![\d/]){mo}/{d}(?![\d/]){tail}", " ", text)
    return text


def _target_first(brief):
    d = brief.get("dates") or {}
    xs = sorted(x for p in d.get("periods") or [] for x in p)
    return xs[0] if xs else None


def _stale_as_target(s, v, rows, brief, c):
    """段階77 第1部 1: 対象の日より前の現況を、対象の日の状態として言い切る文。時点を示した報告と見込みの言い回しは通す。"""
    first = _target_first(brief)
    t = c["stale_as_target"]
    if not first or not v["states"]:
        return None
    old = [r for r in rows if r.get("kind") == "current" and r.get("observed") and str(r["observed"])[:10] < first]
    if not old:
        return None
    text = s["clean"]
    target_md = {m for m in (_md(x) for p in (brief.get("dates") or {}).get("periods") or [] for x in p) if m}
    says_target = GB.has_any(t["target_words"], text) or any(
        re.search(rf"(?<!\d){md.split('/')[0]}月{md.split('/')[1]}日|(?<![\d/]){md}(?![\d/])", text) for md in target_md)
    if not says_target or GB.has_any(t["hedge_words"], text) or GB.has_any(t["point_words"], text):
        return None
    when = "・".join(sorted({_md(r["observed"]) for r in old if _md(r["observed"])}))
    return _err("stale_as_target", s, f"{when}時点の状態を、対象の日({_md(first)}〜)の状態として言い切っている",
                f"「{when}時点では…でした」と時点を書くか、「…の見込みです」「…かもしれません」と見込みで書く")


def check_unmarked(s, places, c, allowed_dates=()):
    if s["text"].lstrip().startswith("#"):              # 見出しの行は照らさない(内容は本文の文で照らす)
        return []
    v = GB.values(_without_allowed(s["clean"], allowed_dates), c)
    v["dates"] = [d for d in v["dates"] if d not in set(allowed_dates)]      # 質問の対象の日・今日・今週末・来週末の日付は書いてよい
    errs = []
    hit = [p for p in places if p and p in s["clean"]]
    for key, label in (("dates", "日付"), ("times", "時刻"), ("money", "金額"), ("phones", "電話番号"), ("urls", "URL")):
        if v[key]:
            errs.append(_err("unmarked_value", s, f"印のない文に{label}({'・'.join(v[key])})",
                             "確かめた事実の印 [F…] を付ける。資料にない値なら書かない"))
    if _now_state(s["clean"], v, c):
        errs.append(_err("unmarked_now_state", s, f"印のない文に今の状態({'・'.join(v['states'])})",
                         "今年の現況の事実の印を付ける。なければ「今年の状況は確かめられていません」と書く"))
    if _event_period(s["clean"], v, c):
        errs.append(_err("unmarked_event", s, "印のない文に行事と期間", "行事の事実の印を付ける。なければ行事の名前・期間を書かない"))
    if GB.has_any(c["closure_words"], s["clean"]):
        errs.append(_err("unmarked_closure", s, "印のない文に通行止め・閉鎖・規制", "安全・規制の事実の印を付ける。なければ書かない"))
    now_state = _now_state(s["clean"], v, c)
    if v["states"] and hit and not now_state and not GB.has_any(c.get("honest_words") or [], s["clean"]):
        errs.append(_err("unmarked_place_state", s, f"印のない文に、記録にある場所({'・'.join(hit[:3])})の状態({'・'.join(v['states'])})",
                         "その場所の今年の現況の事実の印を付ける。なければ「今年の状況は確かめられていません」と書く"))
    if (v["months"] or v["jun"]) and not v["dates"]:
        if hit:
            errs.append(_err("unmarked_place_month", s, f"印のない文に、記録にある場所({'・'.join(hit[:3])})と月の表現",
                             "その名所の例年の時期は、事実の印を付けて書く。種や環境の一般的な季節の説明なら、場所の名前を入れない"))
    return errs


def _site_names():
    from . import yamlcache
    from .paths import SITES_PATH
    out = set()
    for s in (yamlcache.load(SITES_PATH) or {}).get("sites") or []:
        n = s.get("name") or ""
        out |= {n, re.sub(r"[(（].*$", "", n)}
    return {x for x in out if x}


def _known_place(name, brief, env=None):
    from . import place_guard as PG
    from . import unverified as U
    if PG.is_known(name, env):
        return True
    n = PG._norm(name)
    pool = {r["name"] for r in brief.get("candidates") or []} | {f.get("place") for f in brief.get("facts") or [] if f.get("place")}
    pool |= {k.get("place") for k in brief.get("cards") or [] if k.get("place")}
    pool |= _site_names() | {r.get("name") for r in U.load(env)}
    pool = {PG._norm(x) for x in pool if x}
    if n in pool or any(n and (n in x or x in n) for x in pool if len(x) >= len(n) - 2 and x):
        return True
    bare = re.sub(r"[(（][^)）]*[)）]", "", name).strip()
    texts = [f.get("content") or "" for f in brief.get("facts") or []] + [x for k in brief.get("cards") or [] for x in k.get("facts") or []]
    for t in texts:
        if name in t or (bare and bare in t):
            return True
    return False


def check_places(parsed, sents, brief, c, env=None):
    from . import unverified as U
    errs = []
    if not parsed["has_places"]:
        errs.append(_err("places_list_missing", None, f"下書きの最後に {c['draft']['places_heading']} の一覧がない",
                         f"{c['draft']['places_heading']} の見出しのあとに「{c['draft']['places_record']} 名前、…」「{c['draft']['places_knowledge']} 名前(都県)、…」を書く"))
    for n in parsed["record"]:
        if not _known_place(n, brief, env):
            errs.append(_err("unknown_record_place", None, f"記録の場所「{n}」が辞書にない",
                             f"自分の知識で添えた場所なら「{c['draft']['places_knowledge']}」に都県つきで書き、確かめていないと分かる書き方にする"))
    kp = c["knowledge_places"]
    if len(parsed["knowledge"]) > kp["max"]:
        errs.append(_err("too_many_knowledge_places", None, f"知識で添えた場所が {len(parsed['knowledge'])} か所(上限 {kp['max']})",
                         f"{kp['max']} か所までに減らす"))
    for name, pref, city in parsed["knowledge"]:
        if not pref:
            errs.append(_err("knowledge_place_no_prefecture", None, f"知識で添えた場所「{name}」に都県がない", "「名前(都県)」の形で書く"))
            continue
        bad = U.validate({"name": name, "prefecture": pref, **({"city": city} if city else {})})
        if bad:
            errs.append(_err("knowledge_place_invalid", None, f"知識で添えた場所「{name}({pref})」: {'・'.join(bad)}", "範囲の内の場所だけを書く"))
        where = [s for s in sents if name in s["clean"]]
        if where and not any(GB.has_any(kp["unverified_words"], s["clean"]) for s in where):
            errs.append(_err("knowledge_place_not_marked", where[0], f"知識で添えた場所「{name}」が、確かめていないと分かる書き方になっていない",
                             "同じ文に「今年の状況は確かめていません」などを書く"))
    return errs


def _in_range_prefs():
    from . import unverified as U
    return U.in_range_prefectures()


_PREF_RE = re.compile(r"(北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|新潟県|富山県|石川県|福井県|山梨県|"
                      r"長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|"
                      r"愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県)")


def common_errors(final_body, question, c):
    """今までの検査の部品(使わない情報源・内部の言葉・作業の事情・最後の質問・引用)+ 範囲の外の都県 + 内部の言葉(この形の語)+ 場所のすり替え。"""
    from . import ask_verify as V
    from . import place_guard as PG
    from . import publisher as P
    rules = V.load_rules()
    errs = []
    for e in V.term_errors(final_body, rules):
        errs.append({"code": e["code"], "line": e.get("line", 0), "sentence": "", "detail": e.get("detail", ""), "fix": "その語・文を書かない"})
    skip = set(c.get("skip_reused_codes") or [])
    for e in V.internal_word_errors(final_body, rules) + V.process_excuse_errors(final_body, rules) + V.source_rule_errors(final_body, rules) + \
            V.quote_errors(final_body, rules):
        if e["code"] in skip:
            continue
        errs.append({"code": e["code"], "line": 0, "sentence": "", "detail": e.get("detail", ""), "fix": "その文を書かない(質問・作業の事情・使わない情報源・長い引用)"})
    for ln, line in enumerate(final_body.splitlines(), 1):          # 段階76 第5部 4: 読む人への問いかけだけを止める(案内の文は止めない)
        for sent in re.findall(r"[^。！？!?]+[。！？!?]?", line):
            if re.search(c["question_re"], sent.strip()):
                errs.append({"code": "question_in_answer", "line": ln, "sentence": sent.strip()[:80], "detail": "読む人への問いかけ",
                             "fix": "問いかけの文を書かない(答えの最後にも途中にも)"})
    for ln, line in enumerate(final_body.splitlines(), 1):          # 段階76 第5部 2: 公式でない出典の長い断りを文中に入れない
        for w in c.get("long_disclaimers") or []:
            if w in line:
                errs.append({"code": "long_disclaimer", "line": ln, "sentence": line[:80], "detail": f"文中の長い断り「{w}」",
                             "fix": "「紹介サイトによると」のように短く書く(公式かどうかは最後の出典で分かる)"})
    if P.unused_in_text(final_body):
        errs.append({"code": "unused_source", "line": 0, "sentence": "", "detail": "使わない情報源の名前がある", "fix": "その情報源を書かない"})
    for w in c.get("guide_internal_words") or []:
        pat = rf"(?<![A-Za-z0-9_]){re.escape(w)}(?![A-Za-z0-9_])" if w.isascii() else re.escape(w)
        for ln, line in enumerate(final_body.splitlines(), 1):
            if re.search(pat, line):
                errs.append({"code": "internal_word", "line": ln, "sentence": line[:80], "detail": f"内部の言葉「{w}」", "fix": "利用者の語に言い換える"})
    rng = _in_range_prefs()
    for p in sorted(set(_PREF_RE.findall(final_body))):
        if p not in rng:
            errs.append({"code": "out_of_range", "line": 0, "sentence": "", "detail": f"範囲の外の都道府県「{p}」", "fix": "範囲の外の場所を書かない"})
    try:
        qp = PG.candidates(question)
    except (KeyError, TypeError, ValueError):
        qp = []
    nb = PG._norm(final_body)
    for p in qp:
        if PG._norm(p) not in nb:
            errs.append({"code": "place_swap", "line": 0, "sentence": "", "detail": f"聞かれた場所「{p}」の話になっていない", "fix": f"「{p}」について書く(記録が少なければ、そのことを正直に書く)"})
    return errs


def final_sources(cited, c):
    f = c["final"]
    out, seen = [], set()
    for r in cited:
        key = r.get("url")
        if not key or key in seen:                       # 段階76 第5部 1: URL のない出典は出さない
            continue
        seen.add(key)
        if r["id"].startswith("K"):
            note = f["card_note"].format(date=_md(r.get("checked_on")) or "日付不明")
        else:
            d = _md(r.get("observed")) or _md(r.get("read_at"))
            note = f["fact_note"].format(date=d) if d else None
        cls = f["official"] if r.get("source_class") == "official" else f["not_official"]
        name = r.get("source") or _ledger_name(r.get("url")) or _domain(r.get("url"))   # 段階77: 台帳の発行元の名前、なければドメイン名
        out.append("・" + name + "(" + "、".join(x for x in (note, cls) if x) + ")" + (" " + r["url"] if r.get("url") else ""))
    return out


def _ledger_name(url):
    """台帳(情報源・施設)とガイドの発行元の表にある、URL のホストの発行元の名前。なければ None(台帳には足さない)。"""
    from . import publisher as P
    try:
        return P.name(url) if url else None
    except (OSError, KeyError, TypeError, ValueError):
        return None


def _domain(url):
    from . import publisher as P
    return P.host_of(url) if url else ""


def _md(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None
    return f"{d.month}/{d.day}"


def allowed_dates(brief):
    """印なしで書いてよい日付(今日・今週末・来週末・質問の対象の日)。"""
    d = brief.get("dates") or {}
    isos = [d.get("today")] + list(d.get("this_weekend") or []) + list(d.get("next_weekend") or []) + [x for p in d.get("periods") or [] for x in p]
    return sorted({m for m in (_md(x) for x in isos if x) if m})


_places_cache = None


def _dictionary_places():
    """名所カタログ・観察の名所・エリア・山の名前(2 字以上。市町村・都県の名前は除く)。"""
    global _places_cache
    if _places_cache is None:
        from . import areas as AR
        from . import ask
        names = set(ask.place_names()) | _site_names()
        for a in AR.load()["areas"]:
            names |= {a["name"], *(a.get("aliases") or [])}
        _places_cache = {n for n in names if isinstance(n, str) and len(n) >= 2 and not n.endswith(("市", "町", "村", "区", "県", "都"))}
    return _places_cache


def record_place_names(parsed, brief):
    """記録にある場所の名前(下書きの記録の一覧・資料の候補と事実の場所・辞書の名前)。長い順。"""
    names = set(parsed["record"]) | {r["name"] for r in brief.get("candidates") or []} | {f["place"] for f in brief.get("facts") or [] if f.get("place")}
    names |= _dictionary_places()
    return sorted({n for n in names if n}, key=lambda x: (-len(x), x))


def check(draft, brief, c=None, env=None):
    """下書き + 資料 → {ok, errors, final, checked, marked, cited, warnings}。決定的(記録を書かない)。"""
    c = c or cfg()
    parsed = parse_draft(draft, c)
    sents = sentences(parsed["body"], c)
    rec_places = record_place_names(parsed, brief)
    allowed = allowed_dates(brief)
    errs = []
    marked = 0
    cited_ids = []
    for s in sents:
        if s["ids"]:
            marked += 1
            errs += check_marked(s, brief, c, [d for d in allowed if d != _md((brief.get("dates") or {}).get("today"))])
            cited_ids += [i for i in s["ids"] if i not in cited_ids]
        else:
            errs += check_unmarked(s, rec_places, c, allowed)
    errs += check_places(parsed, sents, brief, c, env)
    body = strip_markers(parsed["body"], c)
    errs += common_errors(body, brief.get("question") or "", c)
    by = {r["id"]: r for r in (brief.get("facts") or []) + (brief.get("cards") or [])}
    cited = [by[i] for i in cited_ids if i in by]
    src = final_sources(cited, c)
    final = body.rstrip(NL) + NL + ((NL + c["final"]["sources_heading"] + NL + NL.join(src) + NL) if src else "")
    warns = []
    n = len(body.strip())
    if n < c["length"]["min"] or n > c["length"]["max"]:
        warns.append(f"長さ {n} 字(目安 {c['length']['min']}〜{c['length']['max']} 字)")
    return {"ok": not errs, "errors": errs, "final": final, "checked": len(sents), "marked": marked, "cited": cited_ids, "warnings": warns,
            "knowledge_places": parsed["knowledge"]}


# ---- 書き直しの回数・記録・最終の文 ----

def _state_path(bid, env=None):
    return GB.brief_dir(env) / f"{bid}.verify.json"


def _attempts(bid, env=None):
    try:
        return json.loads(_state_path(bid, env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"attempts": 0, "history": []}


def last_guide_path(env=None):
    return data_path("logs/last_guide_answer.json", env)


def remember_final(text, question, bid, now, env=None):
    """合格した最終の文を覚える(ask final-check と Stop フックが、この文と一致するときだけ受け入れる)。"""
    from . import final_check as FC
    FC.remember_answer(text, question, now, env)
    p = last_guide_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"saved_at": now.isoformat(), "brief": bid, "question": question, "text": text}, ensure_ascii=False, indent=1), encoding="utf-8")


def load_final(now=None, env=None):
    from . import final_check as FC
    try:
        doc = json.loads(last_guide_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if now is not None:
        try:
            from datetime import timedelta
            if abs(now - datetime.fromisoformat(doc["saved_at"])) > timedelta(hours=FC.cfg()["last_answer_valid_hours"]):
                return None
        except (KeyError, ValueError, TypeError):
            return None
    return doc.get("text")


def accepts(message, now=None, env=None):
    """送るメッセージが、ask verify が出した最終の文と一致するか(空白の違いは見ない)。"""
    t = load_final(now, env)
    return bool(t) and re.sub(r"\s+", "", t) == re.sub(r"\s+", "", message or "")


def _log(row, env=None):
    p = data_path("logs/answers.jsonl", env)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(row, ensure_ascii=False) + NL)


def run(draft, bid, *, now, env=None):
    """→ {status: PASS / FAIL / FALLBACK, text(PASS・FALLBACK は送る文), errors, attempt, rewrites}。"""
    c = cfg()
    brief = GB.load(bid, env)
    st = _attempts(bid, env)
    st["attempts"] += 1
    r = check(draft, brief, c, env)
    rewrites = st["attempts"] - 1
    if r["ok"]:
        status, text = "PASS", r["final"]
    elif rewrites >= c["rewrites"]["max"]:
        status, text = "FALLBACK", (brief.get("fallback") or {}).get("text") or ""
    else:
        status, text = "FAIL", None
    st["history"].append({"attempt": st["attempts"], "status": status, "errors": [e["code"] for e in r["errors"]]})
    p = _state_path(bid, env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    if status in ("PASS", "FALLBACK") and text:
        (GB.brief_dir(env) / f"{bid}.final.txt").write_text(text, encoding="utf-8")
        remember_final(text, brief.get("question"), bid, now, env)
    if status == "PASS" and r["knowledge_places"]:
        from . import unverified as U
        batch = [{"name": n, "prefecture": p_, **({"city": ci} if ci else {}), "theme": c["knowledge_places"]["theme_default"]}
                 for n, p_, ci in r["knowledge_places"] if p_]
        try:
            U.record(batch, env, now)
        except (OSError, ValueError):
            pass
    try:
        _log({"at": now.isoformat(), "kind": "guide", "form": "guide", "brief": bid, "question": (brief.get("question") or "")[:80],
              "result": status, "checked": r["checked"], "marked": r["marked"], "cited": len(r["cited"]), "rewrites": rewrites,
              "failed": sorted({e["code"] for e in r["errors"]})}, env)
    except OSError:
        pass
    return {"status": status, "text": text, "errors": r["errors"], "warnings": r["warnings"], "attempt": st["attempts"], "rewrites": rewrites,
            "checked": r["checked"], "marked": r["marked"]}


def report(res):
    """不合格の理由(直し方つき)。内部の言葉はここに出てよい(答えの文には出さない)。"""
    out = [f"{res['status']}(照らした文 {res['checked']}・印のある文 {res['marked']}・{res['attempt']} 回目)"]
    for e in res["errors"]:
        where = f"{e['line']}行目 " if e.get("line") else ""
        out.append(f"NG [{e['code']}] {where}{e['detail']}" + (f"\n   文: {e['sentence']}" if e.get("sentence") else "") + f"\n   直し方: {e['fix']}")
    for w in res.get("warnings") or []:
        out.append(f"注意: {w}")
    return NL.join(out) + NL
