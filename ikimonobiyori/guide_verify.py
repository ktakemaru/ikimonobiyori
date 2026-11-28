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
from .guide_brief import URL_RE
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
            m = re.match(r"^\s*((?:\[[FKO]\d{3,}\]\s*)+)(.*)$", s)
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
    facts = {f["id"]: f for f in (brief.get("facts") or []) + (brief.get("seasonal_obs") or [])}
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
    typical_talk = GB.has_any(c.get("typical_words") or [], s["clean"]) and all(r.get("kind") in ("typical", "seasonal_obs", None) or r["id"].startswith("K") for r in rows)
    errs += seasonal_obs_errors(s, rows, c)                 # 段階83 第2部: 観察記録の印のある文
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


def _without_obs_phrases(text, c):
    """段階83 第2部: 「観察記録では」「過去5年の記録では」など、過去の観察の記録の言い方を除いた文(内部の言葉の照合用)。"""
    for ok in c.get("internal_word_allowed_phrases") or []:
        text = text.replace(ok, "")
    if c.get("internal_word_allowed_re"):
        text = re.sub(c["internal_word_allowed_re"], "", text)
    return text


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
    obs_body = _without_obs_phrases(final_body, c)      # 段階83 第2部: 「観察記録には…」は過去の観察の記録の話(内部の言葉の決まりで止めない)
    for e in V.internal_word_errors(obs_body, rules) + V.process_excuse_errors(final_body, rules) + V.source_rule_errors(final_body, rules) + \
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
    body_iw = obs_body
    for w in c.get("guide_internal_words") or []:
        pat = rf"(?<![A-Za-z0-9_]){re.escape(w)}(?![A-Za-z0-9_])" if w.isascii() else re.escape(w)
        for ln, line in enumerate(body_iw.splitlines(), 1):
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


def _seasonal_vocab():
    if "v" not in _SV:
        from . import seasonal_obs as SO
        _SV["v"] = SO.vocabulary()
    return _SV["v"]


_SV = {}


def seasonal_obs_errors(s, rows, c, vocab=None):
    """段階83 第2部: 観察記録の印([O…])のある文。記録の語(過去・例年・記録)があること、今年の状態の言い切りでないこと、
    書いた種の名前が印の行にあること(保存した集計の和名の中で、印の行と、いっしょに付けた印の事実・カードにないもの)。"""
    obs = [r for r in rows if r.get("kind") == "seasonal_obs"]
    if not obs:
        return []
    from . import seasonal_obs as SO
    V = SO.load_policy()["verify"]
    text = s["clean"]
    errs = []
    if not any(w in text for w in V["required_words"]):
        errs.append(_err("seasonal_obs_not_past", s, "観察記録の文に「過去」「例年」「記録」の語がない",
                         "「過去5年の観察記録では、この時期の○○で…の記録が多くなっています」のように、過去の記録の話として書く"))
    plain = text
    for w in V.get("period_words") or []:
        plain = plain.replace(w, "")
    if re.search(V["now_assert_re"], plain) or re.search(V["state_verbs_re"], text):
        errs.append(_err("seasonal_obs_now", s, "観察記録を今年の状態の言い切りにしている",
                         "今年の状態にしない(「今、…が咲いています」「今週末は…が見られます」と書かない)。過去の記録の傾向として書く"))
    allowed = {n for r in obs for n in r.get("species") or []}
    flowering = {n for r in obs for n in r.get("flowering") or []}
    if re.search(V["flower_words_re"], text):              # 指示書 2.2: 開花の注釈の少ない種を「咲く」と書かない
        nofl = sorted(n for n in allowed if n in text and n not in flowering and any(n in (r.get("species") or []) for r in obs if r.get("category") == "plants"))
        if nofl:
            errs.append(_err("seasonal_obs_flower", s, f"{'・'.join(nofl)} は開花の記録が少なく、咲いていると書けない",
                             "開花の注釈の数がある種だけ「花の記録が多い」と書く。ほかは「記録が多い」まで"))
    others = " ".join(r.get("content") or " ".join(r.get("facts") or []) for r in rows if r.get("kind") != "seasonal_obs")
    vocab = _seasonal_vocab() if vocab is None else vocab
    bad = sorted({n for n in vocab if len(n) >= 2 and n in text and n not in allowed and n not in others
                  and not any(n in a for a in allowed)})
    if bad:
        errs.append(_err("seasonal_obs_species", s, f"種の名前 {'・'.join(bad)} が印の観察記録の行にない",
                         "印の観察記録の行にある種の名前だけを書く"))
    return errs


_AS_OF_MD = __import__("re").compile(r"(\d{1,2})[/月](\d{1,2})日?(?:時点|現在)")


def fact_date(r):
    """事実の発信の日付(YYYY-MM-DD)。observed が無い事実(施設の発信など)は、事実の文の「11/27時点」「11月26日時点」から(年は読んだ日の年)。"""
    if r.get("observed"):
        return str(r["observed"])[:10]
    m = _AS_OF_MD.search(r.get("content") or "")
    y = str(r.get("read_at") or r.get("_year") or "")[:4]           # 読んだ時刻の無い事実(施設の発信)は資料の年
    if not m or not y.isdigit():
        return None
    return f"{y}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"


def _prefer_dated(cited):
    """同じ URL の出典が複数あるとき(カードと今年の現況の事実など)、発信の日付のある事実をその URL の代表にする(順番は最初に出た位置のまま)。
    第5部の試し(質問 4): 本文は「11月26日時点」なのに、同じ URL のカード(11/11 に確認)が先にあって出典が「11/11に確認」になった。"""
    def dated_fact(r):
        return str(r.get("id", "")).startswith("F") and bool(fact_date(r))
    best = {}
    for r in cited:
        u = r.get("url")
        if u and (u not in best or (dated_fact(r) and not dated_fact(best[u]))):
            best[u] = r
    out, seen = [], set()
    for r in cited:
        u = r.get("url")
        if not u:
            out.append(r)
        elif u not in seen:
            seen.add(u)
            out.append(best[u])
    return out


def date_basis_errors(sents, brief, c):
    """発信の日付がある事実の文に「いつの発信か分からない」と書く・日付の無い事実の文に「○/○時点」と書く(出典の「〜時点」「〜に確認」と食い違う)。"""
    D = c.get("date_basis") or {}
    if not D.get("enabled"):
        return []
    yr = str(brief.get("now") or "")[:4]
    by = {f["id"]: {**f, "_year": yr} for f in brief.get("facts") or []}
    out = []
    for s in sents:
        fs = [by[i] for i in s["ids"] if i in by and by[i].get("kind") == "current"]
        if not fs:
            continue
        text = s["clean"]
        if all(fact_date(f) for f in fs) and GB.has_any(D["undated_words"], text):
            out.append(_err("date_basis_mismatch", s, "発信の日付がある事実に、いつの発信か分からないと書いている", D["fix_dated"]))
        elif not any(fact_date(f) for f in fs) and re.search(D["as_of_re"], text):
            out.append(_err("date_basis_mismatch", s, "発信の日付が無い事実を「○/○時点」と書いている(読んだ日は発信の日付ではない)", D["fix_undated"]))
    return out


def upcoming_heading_errors(body, brief, c):
    """「これから」などの見出しの節に、対象の日がその時期の中に入る文(例年の時期・いちばん良い時期)を書いている。
    時期は文に書かれた月日だけで読む(observations.parse_typical。読めない文は照らさない)。"""
    U = c.get("upcoming_heading") or {}
    if not U.get("enabled"):
        return []
    from datetime import date as _date
    from . import observations as O
    per = ((brief.get("dates") or {}).get("periods") or [[]])
    days = [_date.fromisoformat(x[:10]) for x in (per[0] if per else []) if x]
    if not days:
        return []
    pol = O.load_policy()
    out, inside = [], False
    for ln, line in enumerate((body or "").splitlines(), 1):
        if line.lstrip().startswith("#"):
            inside = GB.has_any(U["words"], line)
            continue
        if not inside or not line.strip():
            continue
        w = O.parse_typical(re.sub(r"\[[A-Z]\d+\]", "", line), pol)
        if not w:
            continue
        if any(O.window_dates(w[0], w[1], d)[0] <= d <= O.window_dates(w[0], w[1], d)[1] for d in days):
            out.append({"code": "upcoming_heading_in_season", "line": ln, "sentence": line.strip()[:80],
                        "detail": "「これから」の節に、対象の日がもう時期の中に入るものを書いている", "fix": U["fix"]})
    return out


def weather_line(brief, body, c):
    """出かける日の答え(経路が weather_line.routes)の最後の 1 行。すでに本文にヤマビヨリの案内があれば足さない。イキモノビヨリ自身は天気を答えない。"""
    W = c.get("weather_line") or {}
    if not W.get("enabled") or (brief.get("route") or "") not in (W.get("routes") or []):
        return None
    if GB.has_any(W.get("skip_words") or [], body or ""):
        return None
    if W.get("skip_off_season") and brief.get("off_season"):     # 本人の返事 2(2026-11-28): 時期の外の答え(どの名所の例年の時期にも対象の日が入らない)には付けない
        return None
    return W["line"]


def final_sources(cited, c):
    f = c["final"]
    out, seen = [], set()
    for r in _prefer_dated(cited):
        key = r.get("url")
        if not key or key in seen:                       # 段階76 第5部 1: URL のない出典は出さない
            continue
        seen.add(key)
        if r.get("kind") == "seasonal_obs":               # 段階83 第2部: 観察記録の集計の出典は 1 行
            out.append("・" + r["source"] + " " + r["url"])
            continue
        if r["id"].startswith("K"):
            note = f["card_note"].format(date=_md(r.get("checked_on")) or "日付不明")
        else:
            d = _md(fact_date(r))                        # 指示書 open-question-breadth 第4部 2: 「〜時点」は発信の日付が分かるときだけ。読んだ日は「〜に確認」
            note = f["fact_note"].format(date=d) if d else (f["card_note"].format(date=_md(r.get("read_at"))) if _md(r.get("read_at")) else None)
        cls = f["official"] if r.get("source_class") == "official" else f["not_official"]
        from . import guide_materials as GM                # 段階78 第1部 5: ドメインのままの名前は使わず、台帳・自治体の名前で
        name = GM.source_name(r.get("url"), r.get("source")) or _ledger_name(r.get("url")) or _domain(r.get("url"))   # 段階77: 台帳の発行元の名前、なければドメイン名
        out.append("・" + name + "(" + "、".join(x for x in (note, cls) if x) + ")" + (" " + r["url"] if r.get("url") else ""))
    return out


def _source_label(r):
    from . import guide_materials as GM
    return GM.source_name(r.get("url"), r.get("source")) or _ledger_name(r.get("url")) or _domain(r.get("url"))


def short_sources(cited, c):
    """段階85 第2部(本人の判断 B): 会話の答えの出典は、名前と日付だけの 1 行(URL を出さない)。同じ発行元は 1 つにまとめ、日付は新しいほう。
    公式でないものだけ「紹介サイト」と添える。URL つきの出典は ask source-urls と写真つきのページで見られる。"""
    f = c["final"]
    S = f["short"]
    groups, seen = {}, set()
    for r in _prefer_dated(cited):
        key = r.get("url")
        if not key or key in seen:                       # URL のない出典は出さない(URL つきの出典と同じ範囲)
            continue
        seen.add(key)
        if r.get("kind") == "seasonal_obs":
            name, iso, how, off = S["seasonal_name"], None, None, True
        else:
            name = _source_label(r)
            if r["id"].startswith("K"):
                iso, how = r.get("checked_on"), "card"
            elif fact_date(r):
                iso, how = fact_date(r), "fact"
            else:
                iso, how = r.get("read_at"), "card"            # 指示書 open-question-breadth 第4部 2: 発信の日付が無い事実は、読んだ日を「〜に確認」で
            dated = bool(fact_date(r)) and not r["id"].startswith("K")
            off = r.get("source_class") != "secondary"        # 紹介サイトと分かるもの(secondary)だけに添える(区分のない知識カードは添えない)
        if r.get("kind") == "seasonal_obs":
            dated = False
        g = groups.setdefault(name, {"iso": None, "how": None, "official": off, "dated": False})
        g["official"] = g["official"] and off
        g["dated"] = g["dated"] or dated
        if iso and (g["iso"] is None or (how == "fact" and g["how"] == "card") or (how == g["how"] and str(iso)[:10] > str(g["iso"])[:10])):
            if not (how == "card" and g["how"] == "fact"):
                g["iso"], g["how"] = iso, how
    parts, dated_parts = [], []
    for name, g in groups.items():
        md = _md(g["iso"])
        note = [S["not_official"]] if not g["official"] else []
        if md:
            note.append((S["fact_note"] if g["how"] == "fact" else S["card_note"]).format(date=md))
        (dated_parts if g["dated"] else parts).append(name + ("(" + "・".join(note) + ")" if note else ""))
    if not parts and not dated_parts:
        return None
    mx = S["max_items"]["value"] if isinstance(S["max_items"], dict) else S["max_items"]
    room = max(mx - len(dated_parts), 0)                   # 指示書 open-question-breadth 第4部 3: 本文に日付つきで書いた発行元は「ほか」にまとめない(先に並べる)
    shown = dated_parts + parts[:room] + ([S["more"].format(n=len(parts) - room)] if len(parts) > room else [])
    return S["line"].format(items="、".join(shown))


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
    body = fix_bold(strip_markers(parsed["body"], c))      # 段階78 第1部 8: 太字の記号が文字のまま見えないように
    from . import current_status as CS
    errs += common_errors(body, brief.get("question") or "", CS.verify_cfg(c, brief))   # 指示書 current-status 第 3 部: 利用者の記録の決まった言い方を内部の言葉にしない
    errs += distance_errors(sents, brief, c)               # 段階78 第1部 3
    errs += edge_note_errors(body, c)                      # 段階78 第1部 1・第3部 3
    errs += narrative_errors(sents, brief, c)              # 段階78 第3部 3
    errs += trait_errors(sents, brief, c)                  # 段階82 第2部: 種の見分け方・特徴はカードにあることだけ
    errs += date_basis_errors(sents, brief, c)             # 指示書 open-question-breadth 第4部 2: 発信の日付の有無と、文の書き方の食い違い
    errs += upcoming_heading_errors(body, brief, c)        # 指示書 open-question-breadth 第4部 4: 「これから」の見出しに、今が時期のものを入れない
    errs += contrast_errors(sents, brief, c)               # 段階82 の続き: 2 つの種の見分け方のカードの組み合わせと逆の文
    errs += month_list_errors(sents, brief, c)             # 月別の花の一覧の事実を「例年」「見頃」にしない
    errs += general_talk_errors(sents, brief, c)           # 一般の話は上限まで(docs/guide-voice.md §1b)
    errs += CS.current_status_errors(sents, strip_markers(parsed["body"], c), brief, c, env, _err)
    by = {r["id"]: r for r in (brief.get("facts") or []) + (brief.get("seasonal_obs") or []) + (brief.get("cards") or [])}
    cited = [{**by[i], "_year": str(brief.get("now") or "")[:4]} for i in cited_ids if i in by]
    src = final_sources(cited, c)
    wl = weather_line(brief, body, c)                       # 指示書 open-question-breadth 第4部 6: 出かける日の答えの最後に、天気の一言
    if wl:
        body = body.rstrip(NL) + NL + NL + wl + NL
    final = body.rstrip(NL) + NL + ((NL + c["final"]["sources_heading"] + NL + NL.join(src) + NL) if src else "")
    short = short_sources(cited, c)                         # 段階85 第2部: 会話の答え(ask verify の出力)は名前と日付だけの出典
    chat = body.rstrip(NL) + NL + ((NL + short + NL) if short else "")
    warns = []
    n = len(body.strip())
    if n < c["length"]["min"] or n > c["length"]["max"]:
        warns.append(f"長さ {n} 字(目安 {c['length']['min']}〜{c['length']['max']} 字)")
    return {"ok": not errs, "errors": errs, "final": final, "final_chat": chat, "sources_full": src, "checked": len(sents), "marked": marked,
            "cited": cited_ids, "warnings": warns,
            "knowledge_places": parsed["knowledge"]}


# ---- 段階82 第2部: 種の見分け方・特徴の裏取り ----

def _trait_hits(text, c):
    T = c["species_traits"]
    n = len(T["words_re"])
    return ({i for i, p in enumerate(T["words_re"]) if re.search(p, text or "")}
            | {n + i for i, p in enumerate(T.get("clause_words_re") or []) if re.search(p, text or "")})


def _clause_species(clean, c):
    """段階84 第1部 B: 色・大きさの語(clause_words_re)のある節(読点・句点で区切る)の種の名前。"""
    from . import species_alias as SA
    out = []
    for part in re.split(r"[、。,]", clean):
        if any(re.search(p, part) for p in c["species_traits"].get("clause_words_re") or []):
            out += [n for n in SA.species_in(part) if n not in out]
    return out


def trait_errors(sents, brief, c):
    """種の名前と見分け・特徴の語が同じ文にあるとき、その種のその特徴を書いたカード(か事実)の印を求める。
    印がなければ trait_without_card。印の行に、その種の書き方と同じ種類の特徴の語が一緒に出てこなければ trait_wrong_card
    (ツバキのカードの印でサザンカの特徴を書く、を止める)。季節・環境の一般的な説明(特徴の語がない文)は照らさない。"""
    from . import species_alias as SA
    T = c["species_traits"]
    groups = SA.word_groups()
    ex = c.get("species_blob_exclude_re") or r"(?!)"
    by = {r["id"]: r for r in (brief.get("facts") or []) + (brief.get("cards") or [])}
    errs = []
    for s in sents:
        clean = re.sub(ex, "", s["clean"])
        sps = [n for n in SA.species_in(clean) if n not in (T.get("group_words") or [])]
        hits = _trait_hits(clean, c)
        if T.get("clause_form_re") and not re.search(T["clause_form_re"], re.sub(r"\s*\[[^\]]*\]\s*", "", clean).strip()):
            hits = {h for h in hits if h < len(T["words_re"])}    # 段階84 の続き B: 見分けを言い切る形でない文では、色・大きさの語を照らさない
        if hits and min(hits) >= len(T["words_re"]):        # 色・大きさの語だけの文: その語のある節の種だけを照らす
            sps = [n for n in _clause_species(clean, c) if n in sps] or sps   # 節に種がない(「白い大きな鳥がいたら、ハクチョウです」)なら文の種
        if not sps or not hits:
            continue
        rows = [by[i] for i in s["ids"] if i in by]
        if not rows:
            errs.append(_err(T["code"], s, f"{'・'.join(sps)}の見分け方・特徴の文に、カードの印がない", T["fix"]))
            continue
        clause_only = min(hits) >= len(T["words_re"])

        def backed(n):
            ws = groups.get(n, {n})
            for r in rows:
                head = (r.get("title") or "") + " " + (r.get("subject") or "")
                named = clause_only and any(w in head for w in ws)   # 段階84: 色・大きさの語は、題・主語でその種のカードなら、文に種の名前がなくてよい(「幼鳥は…白くなる」)
                for l in [r.get("title") or ""] + list(r.get("facts") or []) + [r.get("content") or ""]:
                    if l and (_trait_hits(l, c) & hits) and (named or any(w in l for w in ws)):
                        return True
            return False
        bad = [n for n in sps if not backed(n)]
        if bad:
            errs.append(_err(T["wrong_card_code"], s, f"印({'・'.join(s['ids'])})に、{'・'.join(bad)}のこの特徴が書かれていない", T["wrong_card_fix"]))
    return errs


def _mentions(text, names_by_side):
    """文の中の種の書き方の位置 → [(始まり, 終わり, 側)]。長い書き方の中の短い書き方(ソシンロウバイの中のロウバイ)は数えない。"""
    def script(ch):
        return "h" if "ぁ" <= ch <= "ゟ" else "k" if "゠" <= ch <= "ヿ" and ch != "・" else None
    hits = []
    for side, names in names_by_side.items():
        for n in names:
            for m in re.finditer(re.escape(n), text):
                if m.start() and script(n[0]) and script(text[m.start() - 1]) == script(n[0]):
                    continue                             # ひらがな・カタカナの長い語の一部(「ぶんごうめ」の「うめ」)は数えない
                hits.append((m.start(), m.end(), side))
    return [h for h in hits if not any(o[0] <= h[0] and h[1] <= o[1] and (o[1] - o[0]) > (h[1] - h[0]) for o in hits)]


def _attributed(clause, pos, ments, X, end=None):
    """特徴の語(pos の位置)が、節のどちらの側の種のことか。確かなときだけ側を返す(分からなければ None)。
    比べる相手の書き方(「ツバキより」「ツバキと違って」「ツバキのように」)は数えない。両方の側があれば、主語の印(は・が・も)のある側が 1 つのときだけ。"""
    if end is not None:                                  # 段階82 の続き(本人の判断 2026-11-13 の 3): 特徴の語のすぐ後ろに種の名前が続く形(「花ごと落ちるサザンカ」)
        for e in X["modifier_endings"]:                 # 連体の語尾だけ(「落ちる」の「る」)。「落ちるが」「大きく」「湿地に」のつなぎは数えない
            if clause.startswith(e, end):
                hit = [s for a, _b, s in ments if a == end + len(e)]
                if hit:
                    return hit[0]
    own = [(a, b, s) for a, b, s in ments if not re.match(X["compare_re"], clause[b:])]
    sides = {s for _a, _b, s in own}
    if not sides:
        return None
    if len({s for _a, _b, s in ments}) == 1:
        return sides.pop()
    # 節に両方の側の書き方がある: 特徴の語のすぐ前の主語の印(は・が・も)のある書き方の側。特徴の語のあとに、主語の印のない
    # もう一方の側の書き方(「小ぶりのロウバイより」)があれば決めない
    topics = [(a, s) for a, b, s in own if a < pos and re.match(X["topic_re"], clause[b:])]
    if not topics:
        return None
    who = max(topics)[1]
    after = [s for a, b, s in ments if a > pos and s != who and not re.match(X["topic_re"], clause[b:])]
    return None if after else who


def contrast_errors(sents, brief, c):
    """段階82 の続き(本人の判断 2026-11-13 の 1): 印のカードが 2 つの種を比べる見分け方のカード(項目 contrasts)のとき、
    文が「どちらの種が、どの特徴か」の組み合わせと逆なら trait_reversed(「サザンカは花ごと落ちます [K…]」)。
    確かなときだけ止める: 否定の形(落ちず・ではなく)・どちらの種のことか分からない節は照らさない。ほかの文の意味は照らさない。"""
    from . import species_alias as SA
    X = c["species_traits"]["contrast"]
    groups = SA.word_groups()
    by = {r["id"]: r for r in brief.get("cards") or []}
    errs = []
    for s in sents:
        items = [it for i in s["ids"] for it in (by.get(i) or {}).get("contrasts") or []]
        if not items:
            continue
        bad = None
        for clause in [x for x in re.split(X["split_re"], s["clean"]) if x]:
            for it in items:
                names = {side: sorted({w for n in it[side] for w in (groups.get(n) or frozenset()) | {n}}, key=len, reverse=True) for side in ("a", "b")}
                ments = _mentions(clause, names)
                if not ments:
                    continue
                for side in ("a", "b"):
                    rx = it.get(side + "_re")
                    if not rx:
                        continue
                    for m in re.finditer(rx, clause):
                        if re.match(X["negation_re"], clause[m.end():]):
                            continue                     # 否定の形(「花ごと落ちず」「花ごと落ちることはない」)は照らさない
                        who = _attributed(clause, m.start(), ments, X, end=m.end())
                        if who and who != side:
                            bad = bad or (it[who][0], m.group(0), it[side][0])
        if bad:
            errs.append(_err(X["code"], s, f"{bad[0]}に、{bad[2]}の特徴「{bad[1]}」を書いている(印のカードと逆)", X["fix"]))
    return errs


# ---- 段階78 ----

def _is_punct(ch):
    import unicodedata
    return bool(ch) and unicodedata.category(ch)[0] in "PS"


def fix_bold(text):
    """太字(**…**)が CommonMark で閉じない形(「**南沢あじさい山(…)**は」)を直す。
    閉じの ** の前が記号で後ろが文字のとき、末尾の括弧を外に出す(「**南沢あじさい山**(…)は」)。それでも閉じない形は記号を外す。
    開きの ** の後ろが記号で前が文字のときも同じ。"""
    out = []
    for line in (text or "").split(NL):
        def rep(m):
            inner, pre, post = m.group(1), line[m.start() - 1] if m.start() else "", line[m.end()] if m.end() < len(line) else ""
            close_bad = _is_punct(inner[-1:]) and post and not post.isspace() and not _is_punct(post)
            open_bad = _is_punct(inner[:1]) and pre and not pre.isspace() and not _is_punct(pre)
            if close_bad and not open_bad:
                mm = re.match(r"^(.*?[^(（\s])([(（][^()（）]*[)）])$", inner)
                if mm and not _is_punct(mm.group(1)[-1:]):
                    return f"**{mm.group(1)}**{mm.group(2)}"
            if close_bad or open_bad:
                return inner
            return m.group(0)
        out.append(re.sub(r"\*\*([^*\n]+?)\*\*", rep, line))
    return NL.join(out)


def distance_errors(sents, brief, c):
    """距離の書き方: 東京湾の向こう側の候補に距離の数字を書かない。ほかは「直線で約○km」(「直線」を付ける)。"""
    errs = []
    bay = [r["name"] for r in brief.get("candidates") or [] if r.get("distance_text") == c["distance"]["across_bay_label"]]
    I = c["distance"].get("island") or {}
    island = [r["name"] for r in brief.get("candidates") or [] if I.get("enabled") and r.get("city") in (I.get("municipalities") or [])]
    for s in sents:
        t = s["clean"]
        if not re.search(r"\d+\s*(?:km|キロ)", t):
            continue
        hit = [n for n in bay if n in t]
        isl = [n for n in island if n in t]
        if hit:
            errs.append(_err("bay_distance", s, f"東京湾の向こう側の「{hit[0]}」に距離の数字", "距離の数字を書かず「東京湾の向こう側」のように書く"))
        elif isl and not GB.has_any(I.get("words") or [], t):
            errs.append(_err("island_distance", s, f"船か飛行機が要る「{isl[0]}」に、直線の距離だけ", I["fix"]))
        elif "直線" not in t:
            errs.append(_err("straight_distance", s, "距離に「直線」がない", "「直線で約○km」と書く(道のりではない)"))
    return errs


def edge_note_errors(body, c):
    """答えの先頭・末尾の段落に、作業の説明(下書き・合格・送ります など)や英語の文がある。"""
    paras = [p for p in re.split(r"\n\s*\n", (body or "").strip()) if p.strip()]
    if not paras:
        return []
    errs = []
    for where, p in (("先頭", paras[0]), ("末尾", paras[-1])) if len(paras) > 1 else (("先頭", paras[0]),):
        txt = URL_RE.sub(" ", p)
        w = next((x for x in c.get("work_note_words") or [] if x in txt), None)
        if w:
            errs.append({"code": "work_note", "line": 0, "sentence": p[:80], "detail": f"{where}に作業の説明「{w}」", "fix": "作業の説明を書かない(答えだけを書く)"})
        if re.search(c["english_re"], txt):
            errs.append({"code": "english_note", "line": 0, "sentence": p[:80], "detail": f"{where}に英語の文", "fix": "英語のメモを書かない"})
    return errs


def narrative_errors(sents, brief, c):
    """資料に語りの材料が 2 点以上あるのに、答えが 1 点も使っていない(印で数える)。行事の質問・名前だけを聞く短い質問は除く。"""
    N = c.get("narrative") or {}
    mats = brief.get("narrative") or {}
    ids = {i for k in (mats.get("items") or []) for i in [k.get("card")] if i}
    if len(ids) < N.get("min_items_to_require", 2):
        return []
    if (brief.get("route") in (N.get("skip_routes") or [])) or brief.get("intent") == "event":
        return []
    used = {i for s in sents for i in s["ids"] if i in ids}
    if used:
        return []
    return [{"code": "no_narrative", "line": 0, "sentence": "", "detail": f"語りの材料({len(ids)} 点)を 1 つも使っていない",
             "fix": "「語りの材料」から、なぜ今・どこをどう見る などを 1〜3 点選んで、文にして印 [K…] を付ける"}]


def month_list_errors(sents, brief, c):
    """月別の花の一覧に名前が載るだけの事実(fields.month_list)の印の文は、「例年」「見頃」の話にしない。"""
    M = c.get("month_list") or {}
    ids = {f["id"] for f in brief.get("facts") or [] if (f.get("fields") or {}).get("month_list")}
    return [_err("month_list_as_typical", s, M["ng_why"], M["ng_fix"]) for s in sents
            if set(s["ids"]) & ids and any(w in s["clean"] for w in M.get("banned_words") or [])]


def general_talk_items(sents, brief, c):
    """一般の話(豆知識・小話)の数え方(docs/guide-voice.md §1b)。→ 数えた話ごとの文の一覧。
    数える文: 印が知識カードだけで、そのカードが「この場所の話」「季節の暦」「保全・マナー」でなく、文に安全・マナーの注意の語がない。
    同じカードの印の文が続くあいだは 1 つ。"""
    G = c.get("general_talk") or {}
    cards = {k["id"]: k for k in brief.get("cards") or []}
    out, prev = [], None
    for s in sents:
        ids = set(s["ids"])
        counted = bool(ids) and all(i in cards for i in ids) and not any(w in s["clean"] for w in G.get("safety_words") or [])             and any(cards[i].get("link") not in (G.get("exempt_links") or []) and cards[i].get("category") not in (G.get("exempt_categories") or []) for i in ids)
        if not counted:
            prev = None
            continue
        if ids == prev:
            out[-1].append(s)
        else:
            out.append([s])
        prev = ids
    return out


def general_talk_errors(sents, brief, c):
    """出かける日の答え(general_talk.routes)の一般の話は max まで。知識を聞く質問は数えない。"""
    G = c.get("general_talk") or {}
    if not G.get("enabled") or (brief.get("route") or "") not in (G.get("routes") or []):
        return []
    items = general_talk_items(sents, brief, c)
    mx = G["max"]["value"]
    if len(items) <= mx:
        return []
    return [_err("too_many_general_talk", items[mx][0], G["ng_why"].format(n=len(items), max=mx), G["ng_fix"].format(max=mx))]


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


def remember_final(text, question, bid, now, env=None, full_text=None, sources_full=None):
    """合格した最終の文を覚える(ask final-check と Stop フックが、この文と一致するときだけ受け入れる)。
    段階85 第2部: full_text は URL つきの出典の形(写真つきのページの材料)、sources_full は ask source-urls が出す URL つきの出典の行。"""
    from . import final_check as FC
    FC.remember_answer(text, question, now, env)
    p = last_guide_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"saved_at": now.isoformat(), "brief": bid, "question": question, "text": text}
    if full_text:
        doc["full_text"] = full_text
    if sources_full is not None:
        doc["sources_full"] = list(sources_full)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


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
    from .guide_answer_page import loose
    t = load_final(now, env)
    return bool(t) and loose(t) == loose(message)


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
        status, text = "PASS", r["final_chat"]             # 段階85 第2部: URL つきの形(r["final"])はページと ask source-urls に
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
        if status == "PASS":                             # 段階85 第2部: 写真つきのページと ask source-urls には URL つきの出典
            remember_final(text, brief.get("question"), bid, now, env, full_text=r["final"], sources_full=r["sources_full"])
        else:
            remember_final(text, brief.get("question"), bid, now, env)
    if status == "PASS":                                 # 段階78 第5部: 足りなかったことの記録
        try:
            from . import gaps as GP
            GP.append(text, brief, now, env)
        except (OSError, ValueError, KeyError):
            pass
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
