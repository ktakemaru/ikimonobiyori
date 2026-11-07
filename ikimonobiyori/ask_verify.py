"""自然な文章の答えの検査器(段階37。biyori-hub の concierge_skill/verify_text.py(段階H8〜H10)から生き物の部分を移した。
通信しない・LLM なし)。

答えの文(モデルが書いた自然な文章)を、集めた事実(`python -X utf8 -m ikimonobiyori.ask facts` の facts.json)と突き合わせる:
- 文中の日付(M/D・M月D日)・旬(N月上旬など)・数字・URL・地名・状態の語が、事実にあるか
- 利用者への確認・実行の依頼や、答えを止める言い方(R10)、内部用語・開発の言葉(段階37)がないか
- 指定の地域の候補が 3 件以上出ているか(答え全体)
通らない文だけを取り除いた答え(strip)も作る。事実の列挙だけの答えには落とさない。
語の一覧は data/ask/policy.yaml の answer_check。評価表は docs/ask-rubric.md。"""
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from . import answer_plan as AP
from . import offers as OF
from .paths import DATA_FILES_DIR

CONFIG = DATA_FILES_DIR / "ask" / "policy.yaml"
URL_RE = re.compile(r"https?://[^\s)）」』、,]+")
DATE_SLASH = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])")
DATE_KANJI = re.compile(r"(\d{1,2})月(\d{1,2})日")
THIRD_RE = re.compile(r"(\d{1,2})月(上旬|中旬|下旬)")
ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def load_rules(path=None):
    return yaml.safe_load(Path(path or CONFIG).read_text(encoding="utf-8"))["answer_check"]


def _n(s):
    return unicodedata.normalize("NFKC", s or "").replace("〜", "~").replace("～", "~")


def _strings(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            _strings(v, out)
    elif isinstance(o, list):
        for v in o:
            _strings(v, out)
    elif isinstance(o, str):
        out.append(o)
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        out.append(str(o))
    return out


def _spots(facts):
    """facts.json の名所(候補・避けたほうがよい場所・県外・代わりの目的)。"""
    out = []
    for subj in (facts.get("subjects") or {}).values():
        for key in ("candidates", "avoid", "nearby_out_of_region"):
            for c in subj.get(key) or []:
                out.append({**c, "_group": key, "_subject": subj.get("subject")})
        for a in subj.get("alternatives") or []:
            out.append({**a, "_group": "alternatives", "_subject": "flowers"})
    return out


def short_names(name):
    """名所の名前と、答えで使われやすい短い形(かっこの中・外、空白で区切った最後の部分、『の紅葉』を外した形)。"""
    n = _n(name)
    forms = {n}
    m = re.match(r"^(.*?)\((.*?)\)(.*)$", n)
    if m:
        forms |= {m.group(1).strip() + m.group(3).strip(), m.group(2).strip(), m.group(1).strip()}
    for f in list(forms):
        parts = f.split()
        if len(parts) > 1:
            forms |= {parts[-1], "".join(parts)}
        for suf in ("の紅葉", "公園", "温泉"):
            if f.endswith(suf) and len(f) > len(suf) + 1 and suf == "の紅葉":
                forms.add(f[: -len(suf)])
    forms |= {re.sub(r"[「」『』]", "", f) for f in forms}
    return {f for f in forms if len(f) >= 2 and not _only_generic(f)}


_GENERIC = None


def _only_generic(form):
    """段階54: 『菊花展』『まつり』『紅葉』のような一般的な語だけの形は、名所の短い呼び名にしない（別の名所と取り違える）。固有の部分（三溪園・川崎大師など）を含む形だけ使う。"""
    global _GENERIC
    if _GENERIC is None:
        _GENERIC = sorted({_n(w) for w in load_rules().get("generic_name_words", [])}, key=len, reverse=True)
    rest = _n(form)
    for w in _GENERIC:
        rest = rest.replace(w, "")
    return not re.sub(r"[\s0-9・、,]", "", rest)


def prefix_of(name):
    m = re.match(r"^(.*?)\((.*?)\)(.*)$", _n(name))
    return m.group(1).strip() if m and m.group(1).strip() and m.group(2).strip() else None


def strict_names(name, shared=frozenset()):
    """段階52: short_names から、同じ地域名を持つ別の名所がある、かっこの前の形（「箱根(芦ノ湖)」「箱根(湯本)」の「箱根」）を除く。別の名所を取り違えない。"""
    p = prefix_of(name)
    return short_names(name) - ({p} if p in shared else set())


def shared_prefixes(mat):
    from collections import Counter
    cnt = Counter(prefix_of(c["name"]) for c in mat.region_candidates)
    return frozenset(p for p, n in cnt.items() if p and n > 1)


class Material:
    def __init__(self, facts, rules, gazetteer=()):
        self.facts = facts
        self.rules = rules
        strs = _strings(facts, [])
        self.blob = _n("\n".join(strs))
        self.urls = set(URL_RE.findall("\n".join(strs)))
        self.dates = set()
        for y, m, d in ISO_RE.findall(self.blob):
            self.dates.add((int(m), int(d)))
        for m, d in DATE_SLASH.findall(self.blob):
            self.dates.add((int(m), int(d)))
        for m, d in DATE_KANJI.findall(self.blob):
            self.dates.add((int(m), int(d)))
        self.thirds = {(int(m), t) for m, t in THIRD_RE.findall(self.blob)}
        self.months = {m for m, _ in self.dates} | {m for m, _ in self.thirds}
        self.numbers = set(NUM_RE.findall(self.blob))
        for s in _spots(facts):                                  # 段階57 第8部: 距離の目安(約○km)は、コードが計算した値の丸め
            if isinstance(s.get("distance_km"), (int, float)):
                self.numbers.add(str(int(round(s["distance_km"]))))
        self.spots = _spots(facts)
        self.names = {}
        for s in self.spots:
            for f in short_names(s.get("name") or ""):
                self.names.setdefault(f, []).append(s)
        self.gazetteer = {_n(g) for g in gazetteer if len(_n(g)) >= rules["min_place_len"]}
        region_c = [s for s in self.spots if s["_group"] == "candidates"]
        self.region_candidates = region_c

    def spots_in(self, sentence):
        t = _n(sentence)
        hit = []
        for f, ss in sorted(self.names.items(), key=lambda kv: -len(kv[0])):
            if f in t:
                for s in ss:
                    if s not in hit:
                        hit.append(s)
        return hit

    def states_of(self, spots):
        out = []
        for s in spots:
            cur = s.get("current")
            if cur:
                out += [cur.get("state") or "", cur.get("state_raw") or "", cur.get("display") or ""]
            for h in s.get("history") or []:
                out += [h.get("state") or "", h.get("state_raw") or ""]
        return [_n(x) for x in out if x]

    def all_states(self):
        return self.states_of(self.spots)


def split_sentences(text):
    """→ [(行番号, 文)]。行の中を「。」で分ける(句点を残す)。"""
    out = []
    for i, line in enumerate(text.splitlines()):
        parts = re.findall(r"[^。]+。?", line)
        for p in parts:
            if p.strip():
                out.append((i, p))
    return out


def check_sentence(s, mat):
    """1 文の検査 → [{code, detail}]。"""
    r = mat.rules
    t = _n(re.sub(r"[①-⑳]", " ", s))
    t = re.sub(r"^\s*\d{1,2}[.)]\s", " ", t)                        # 「1. 」のような番号
    errs = []
    for w in r["forbidden_phrases"]:
        if _n(w) in t:
            errs.append({"code": "forbidden_phrase", "detail": w})
    t_nourl = URL_RE.sub(" ", t)                                  # 段階H9: URL の中の語(パスの observations など)は内部用語として数えない
    for w in r["internal_terms"]:
        if re.search(r"(?<![A-Za-z])" + re.escape(_n(w)) + r"(?![A-Za-z])", t_nourl, re.IGNORECASE):
            errs.append({"code": "internal_term", "detail": w})
    for pat in r.get("dev_terms") or []:                        # 段階37: 開発・作業の言葉(テスト・コード・作業メモ・スキル・コマンド など)
        if re.search(pat, t_nourl):
            errs.append({"code": "dev_term", "detail": pat})
    urls = URL_RE.findall(s)
    for u in urls:
        if u.rstrip("/") not in {x.rstrip("/") for x in mat.urls}:
            errs.append({"code": "unknown_url", "detail": u})
    body = URL_RE.sub(" ", t)
    used = set()
    for m, d in DATE_SLASH.findall(body):
        used.add((int(m), int(d)))
        if (int(m), int(d)) not in mat.dates:
            errs.append({"code": "unknown_date", "detail": f"{m}/{d}"})
    for m, d in DATE_KANJI.findall(body):
        if (int(m), int(d)) not in mat.dates:
            errs.append({"code": "unknown_date", "detail": f"{m}月{d}日"})
    # 旬: 「11月中旬」は、同じ月の旬が事実にあれば通す(「11月中旬～12月上旬」のような範囲の書き方の一部を含む)
    for m, th in THIRD_RE.findall(body):
        if (int(m), th) not in mat.thirds and not _third_in_ranges(int(m), th, mat):
            errs.append({"code": "unknown_period", "detail": f"{m}月{th}"})
    # 数字(日付・旬・URL・丸数字以外)
    rest = DATE_SLASH.sub(" ", DATE_KANJI.sub(" ", THIRD_RE.sub(" ", body)))
    rest = re.sub(r"(\d{1,2})月", " ", rest)
    rest = re.sub(r"(\d{4})年", lambda m: " " if m.group(1) in mat.numbers or int(m.group(1)) in r["years_ok"] else m.group(0), rest)
    rest = re.sub(r"(\d{1,2})日", lambda m: " ", rest)
    for num in NUM_RE.findall(rest):
        tail = rest[rest.find(num) + len(num): rest.find(num) + len(num) + 3]
        if num in mat.numbers:
            continue
        if num.isdigit() and int(num) <= r["small_count_max"] and any(tail.startswith(c) for c in r["counters"]):
            continue
        errs.append({"code": "unknown_number", "detail": num})
    # 地名: 地名の辞書にある語が、事実の文字列のどこにもない
    for g in mat.gazetteer:
        if g in body and g not in mat.blob and not any(g in f for f in mat.names):
            errs.append({"code": "unknown_place", "detail": g})
    # 状態の語: 文中の名所の状態(なければ、どこかの記録の状態)にあること
    spots = mat.spots_in(s)
    pool = mat.states_of(spots) if spots else mat.all_states()
    for w in r["state_words"]:
        if _n(w) in body and not any(_n(w) in x for x in pool):
            if not (spots and any(_n(w) in (tt.get("text") or "") for sp in spots for tt in sp.get("typical") or [])):
                errs.append({"code": "unknown_state", "detail": w})
    for pat in r["peak_claims"]:
        if re.search(pat, body):
            peaks = [sp for sp in (spots or mat.spots) if (sp.get("current") or {}).get("state") == "見頃"]
            if not peaks:
                errs.append({"code": "unsupported_peak_claim", "detail": pat})
            elif re.search(r["now_peak_claim"], body) and not any((sp.get("current") or {}).get("freshness") == "fresh" for sp in peaks):
                errs.append({"code": "old_record_as_now", "detail": "古い記録で「いま見頃」と書いている"})
    return errs


def _third_in_ranges(m, th, mat):
    order = ["上旬", "中旬", "下旬"]
    for t in re.findall(r"(\d{1,2})月(上旬|中旬|下旬)\s*~\s*(?:(\d{1,2})月)?(上旬|中旬|下旬)", mat.blob):
        m1, t1, m2, t2 = int(t[0]), t[1], int(t[2] or t[0]), t[3]
        a, b = (m1, order.index(t1)), (m2, order.index(t2))
        if a <= (m, order.index(th)) <= b:
            return True
    return False


def source_rule_errors(text, rules, blob=None):
    """段階57 第10部: 使わない種類のホスト・語(本文にも出典にも)／事実にない電話番号／英語の出典の見出し。blob: 取得した事実の文字列(なければ番号はすべて不合格)。"""
    from . import observations as O
    pol = O.load_policy()
    errs = []
    low = text.lower()
    for w in list(O._v(pol["record"]["not_read_hosts"])) + list(O._v(pol.get("not_read_words") or {"value": []})) + (rules.get("extra_blocked_words") or []):
        if w.lower() in low:
            errs.append({"code": "blocked_source", "detail": w})
    for m in re.finditer(rules["phone_re"], _n(text)):
        if blob is None or m.group(0) not in blob:
            errs.append({"code": "phone_not_from_official", "detail": m.group(0)})
    for u in URL_RE.findall(text):                              # 段階58 第4部: SNS は出典に使わない
        host = (urlsplit(u).hostname or "").lower()
        if any(host == s or host.endswith("." + s) for s in rules.get("sns_hosts") or []):
            errs.append({"code": "sns_source", "detail": host})
    for line in text.splitlines():
        if re.match(rules["english_sources_re"], line):
            errs.append({"code": "sources_heading", "detail": line.strip()})
    return errs


def knowledge_errors(text, facts):
    """段階59 第4部: 「ガイドの目」の行は、カードの事実と出典のとおり。facts.knowledge_cards(テスト)がなければデータ置き場のカード。"""
    if "ガイドの目:" not in text:
        return []
    from . import knowledge as K
    return K.answer_errors(text, facts.get("knowledge_cards"))


def subject_word_errors(text, facts, rules):
    """段階58 第10部: 鳥の答えに「咲き具合」「色づき」、花・紅葉の答えに「飛来」を書かない(対象別の定型文)。対象が 1 つの答えだけ。"""
    subs = list(facts.get("subjects") or {})
    if len(subs) != 1:
        return []
    return [{"code": "subject_wrong_word", "detail": w} for w in (rules.get("subject_wrong_words") or {}).get(subs[0], []) if w in text]


def quote_errors(text, rules):
    """段階58 第10部: 引用符で長い原文を写さない(長い引用は 1 か所まで)。"""
    mn, mx = val_of(rules["long_quote_min"]), val_of(rules["max_long_quotes"])
    long_q = [q for q in re.findall(r"「([^」]+)」", URL_RE.sub(" ", text)) if len(q) >= mn]
    return [{"code": "quote_repeated", "detail": long_q[0][:20]}] if len(long_q) > mx else []


def not_tried_errors(text, facts):
    """段階58 第2部: 取得を試みる前に「読めていません」と書かない。この回の読めなかったページ(fetch.failed)があるときだけ書ける。"""
    if (facts.get("fetch") or {}).get("failed"):
        return []
    phrases = AP.load_policy()["official_pages"]["not_tried_phrases"]
    return [{"code": "official_not_tried", "detail": p} for p in phrases if p in text]


def question_errors(text, rules):
    """段階57 第13部: 好み・優先・選択を尋ねる文を答えに入れない。例外(答えの代わりの聞き返しだけ)は generic_check(clarify=True)。"""
    out = []
    for _i, s in split_sentences(URL_RE.sub(" ", text)):
        if re.search(rules["ask_sentence_re"], _n(s).strip()):
            out.append({"code": "question_in_answer", "detail": s.strip()[:40]})
    return out


def process_excuse_errors(text, rules):
    """段階57 第9部: 作業の事情の文・「ご希望なら調べます」型。調べられるものは答えの前に調べる。"""
    out = []
    for _i, s in split_sentences(URL_RE.sub(" ", text)):
        for p in rules.get("process_excuse_phrases") or []:
            if p in s:
                out.append({"code": "process_excuse", "detail": s.strip()[:40]})
                break
    return out


def stage57_text_errors(text, facts, mat, rules):
    """段階57 第4部: 記号のまま・対象の日でない日の開園時間・観察の記録があるのに「見つかっていません」。答えの決まり(practical_rules)の印があるときだけ。"""
    if not (facts.get("lines") or {}).get("practical_rules"):
        return []
    from . import observations as O
    pol = O.load_policy()
    errs = []
    body = URL_RE.sub(" ", text)
    for m in re.finditer(rules["bare_symbol_re"], body):
        errs.append({"code": "state_symbol_raw", "detail": m.group(0)})
    days = set()
    for x in facts.get("dates") or []:
        days.add((int(x[5:7]), int(x[8:10])))
    for m in re.finditer(pol["practical_other_day"]["pattern"], _n(body).replace("~", "〜")):
        if (int(m.group(1)), int(m.group(2))) not in days:
            errs.append({"code": "practical_other_day", "detail": m.group(0)[:30]})
    unknown = pol["birds"]["season_labels"]["unknown"]
    for b in candidate_blocks(text):
        if unknown in b and any((s.get("current") or s.get("latest_dated")) for s in mat.spots_in(b)):
            errs.append({"code": "season_contradiction", "detail": b.splitlines()[0][:30]})
    return errs


def offer_errors(text, allowed, doc=None):
    """段階57 第1部: 提案らしい文は、案内の一覧(data/ask/offers.yaml)にあり条件を満たすものだけ。allowed: 今使ってよい案内の文。"""
    doc = doc or OF.load()
    ok = {_n(a).strip() for a in allowed or []}
    errs = []
    for _i, s in split_sentences(URL_RE.sub(" ", text)):
        t = _n(s).strip()
        if t not in ok and any(_n(p) in t for p in doc["offer_phrases"]):
            errs.append({"code": "offer_not_allowed", "detail": s.strip()[:40]})
    return errs


def _with_cards(text, facts):
    """答えに「ガイドの目」や知識の行があるとき、カードの事実・出典 URL を検査の材料に足す(カードが根拠)。"""
    from . import knowledge as K
    cards = facts.get("knowledge_cards")
    rows = cards if cards is not None else K.load_shown()
    used = [r for r in rows if (K.line_for(r) in text) or (K.cfg()["before_line"].format(facts="。".join(x.rstrip("。") for x in r["facts"][: K.cfg()["max_facts_in_answer"]]), source=r["source"]["name"]) in text)]
    from . import jma_normals as JN                             # 段階61 第1部: 平年の目安の行(気象庁の観測値をもとに計算)も根拠に足す
    jn = JN.used_in(text)
    if jn:
        used = used + [{"title": "", "facts": jn, "source": {"name": JN.policy()["source"]["name"], "url": JN.policy()["source"]["page"]}}]
    if not used:
        return facts
    return {**facts, "knowledge_used": [{"facts": r["facts"], "source": r["source"], "line": K.line_for(r) if r.get("title") else ""} for r in used]}


def check(text, facts, rules=None, gazetteer=(), plan=None, offers=None):
    """→ {ok, sentences: [{line, text, errors}], answer_errors: [...], candidates_mentioned}。offers: 今使ってよい案内の文(省くと計画のもの)。"""
    rules = rules or load_rules()
    facts = _with_cards(text, facts)
    mat = Material(facts, rules, gazetteer)
    AP.add_target_dates(mat)                                    # 段階58 第7部: 見頃を狙う週(コードの計算)の日付は事実として通す
    sents = []
    for line, s in split_sentences(text):
        sents.append({"line": line, "text": s, "errors": check_sentence(s, mat)})
    answer_errors = []
    mentioned = []
    segs = AP.split_segments(text, plan)                        # 段階57 第3部: 対象別(期間別)の節があれば、節ごとに数える
    mat.seg_text = {s["seg"].get("subject"): _n(s["text"]) for s in segs if s["seg"].get("subject")} if segs else None
    for c in mat.region_candidates:
        if any(f in _n(text) for f in short_names(c["name"])) and c["name"] not in mentioned:
            mentioned.append(c["name"])
    need = min(rules["min_candidates"], len(mat.region_candidates))
    if plan:                                                    # 段階57 第5部・段階58 第9部: 計画に残った(利用できる)件数まで
        need = min(need, len(plan.get("picks") or []))
    if len(mentioned) < need:
        answer_errors.append({"code": "too_few_candidates", "detail": f"地域の候補 {len(mentioned)} 件(必要 {need} 件)"})
    bird_names = {f for c in mat.spots if c.get("_subject") == "birds" for f in short_names(c.get("name") or "")}
    only_birds = set((facts.get("subjects") or {})) == {"birds"}
    blocks = [(b, s["seg"].get("subject") == "birds" or (s["seg"].get("subject") is None and None)) for s in segs for b in candidate_blocks(s["text"])] if segs else [(b, None) for b in candidate_blocks(text)]
    for blk, seg_bird in blocks:                                # 評価表 R4: 各候補(①②…の段)に例年の見頃(または昨年の記録)。野鳥は「この時期に見られる鳥」
        is_bird = seg_bird if seg_bird is not None else (only_birds or any(f in _n(blk) for f in bird_names))
        words = rules.get("birds_typical_words", []) if is_bird else rules["typical_words"]
        if not any(w in blk for w in words):
            answer_errors.append({"code": "no_season_birds_in_candidate" if is_bird else "no_typical_in_candidate", "detail": blk.splitlines()[0][:30]})
        if is_bird and not only_birds and any(w in blk for w in rules.get("birds_forbidden", [])):
            answer_errors.append({"code": "birds_typical_phrase", "detail": blk.splitlines()[0][:30]})
    if only_birds:
        for w in rules.get("birds_forbidden", []):
            if w in text:
                answer_errors.append({"code": "birds_typical_phrase", "detail": w})
    answer_errors += reread_errors(text, facts, rules) + closed_errors(text, mat, rules) + typical_unknown_errors(text, mat, rules)
    answer_errors += stage51_errors(text, facts, mat, rules, plan=plan, segs=segs)
    answer_errors += restricted_source_errors(facts)
    if plan and segs:                                                        # 段階57 第3部: 節ごとに、計画の今回のおすすめと照合する
        for s in segs:
            answer_errors += [{**e, "detail": f"{s['seg']['heading']}: {e['detail']}"} for e in AP.plan_errors(s["text"], s["plan"], mat, candidate_blocks(s["text"]), short_names)]
    elif plan and plan.get("subject") == "areas":                            # 段階58: エリアが 1 つだけの答え
        for seg in plan["segments"]:
            answer_errors += AP.plan_errors(text, seg["plan"], mat, candidate_blocks(text), short_names)
    elif plan:                                                               # 段階56: 答えの採用と計画の照合
        answer_errors += AP.plan_errors(text, plan, mat, candidate_blocks(text), short_names)
    answer_errors += visitor_center_errors(text, facts)
    answer_errors += stage57_text_errors(text, facts, mat, rules)
    answer_errors += process_excuse_errors(text, rules)
    answer_errors += question_errors(text, rules)
    answer_errors += not_tried_errors(text, facts)
    answer_errors += subject_word_errors(text, facts, rules) + quote_errors(text, rules)
    answer_errors += knowledge_errors(text, facts)
    from . import jma_normals as JN
    answer_errors += JN.answer_errors(text)
    answer_errors += source_rule_errors(text, rules, mat.blob)
    if (facts.get("lines") or {}).get("origin_line") and facts.get("origin") and facts["origin"] not in text:     # 段階57 第8部: 使った出発地を書く
        answer_errors.append({"code": "origin_missing", "detail": facts["lines"]["origin_line"]})
    answer_errors += offer_errors(text, offers if offers is not None else OF.texts((plan or {}).get("offers")))
    if plan:
        answer_errors += AP.area_errors(text, plan)
    n_seg = len(segs) if segs else 1                             # 段階57 第3部: 節が複数の答えは、上限を節の数だけ広げる(1 節あたりの量は同じ)
    for w, mx in (rules.get("max_repeats") or {}).items():       # 段階38: 「公式ではない」は補足に1回まとめる
        if text.count(w) > mx * n_seg:
            answer_errors.append({"code": "repeated_phrase", "detail": f"「{w}」が {text.count(w)} 回(まとめて {mx * n_seg} 回まで)"})
    if len(text) > rules["max_chars"] * n_seg:
        answer_errors.append({"code": "too_long", "detail": f"{len(text)} 字(目安 {rules['max_chars'] * n_seg} 字)"})
    ok = not answer_errors and all(not x["errors"] for x in sents)
    return {"ok": ok, "sentences": sents, "answer_errors": answer_errors, "candidates_mentioned": mentioned}


def reread_errors(text, facts, rules):
    """段階H9(穴1): 「読み直しました」は、この回の record で新しい記録が増えたときだけ、決まった文(lines.fetch)で書く。
    記録が古い名所があるのに、読みに行かずに答えたら落とす(fetch_skipped)。"""
    rnd = facts.get("this_round") or {}
    errs = []
    fixed = {_n(x) for line in (facts.get("lines") or {}).get("fetch") or [] for x in re.findall(r"[^。]+。?", line)}
    for _i, sent in split_sentences(text):
        if any(w in sent for w in rules.get("reread_words", [])):
            if not rnd.get("new_records"):
                errs.append({"code": "reread_without_new_records", "detail": sent.strip()[:40]})
            elif _n(sent.strip()) not in fixed:
                errs.append({"code": "reread_not_from_record", "detail": sent.strip()[:40]})
    if rnd.get("needs_fetch") and not rnd.get("attempted"):
        errs.append({"code": "fetch_skipped", "detail": "記録が古い名所があるのに、この回は読みに行っていない"})
    return errs


def visitor_center_errors(text, facts):
    """段階55 第5部: 「○○発信、○/○時点」の形で施設の発信を書けるのは、承認済みで、facts の visitor_centers にある施設だけ。承認待ち・取り消し・季節外の施設は使わない。"""
    from . import visitor_centers as VC
    allowed = {r["name"] for r in facts.get("visitor_centers") or []}
    errs = []
    names = {c["name"] for c in VC.load_centers()}
    for n in sorted(names - allowed):
        if n + "発信" in text:
            errs.append({"code": "visitor_center_not_approved", "detail": f"{n}は承認済みで季節内の施設ではない"})
    for r in facts.get("visitor_centers") or []:                          # 段階56b: 施設ごとの使う項目。除いた項目が答えに出たら落とす
        if not r.get("allowed_fields") or not r.get("name"):
            continue
        for line in text.splitlines():
            if r["name"] + "発信" not in line:
                continue
            body = re.sub(r"\(https?://[^)]*\)|https?://\S+", "", line)
            if "species" not in r["allowed_fields"]:
                leaked = [s for s in r.get("withheld_species") or [] if s and s in body]
                if leaked or re.search(r"発信、\d+/\d+時点[:：][^。]*?[（(][^）)]+[）)]", body):
                    errs.append({"code": "visitor_center_field_not_allowed", "detail": f"{r['name']}: 種名は使わない施設（{('・'.join(leaked) or '括弧の種名')}）"})
        if "hours" not in r["allowed_fields"] and r.get("withheld_hours") and r["withheld_hours"] in text:
            errs.append({"code": "visitor_center_field_not_allowed", "detail": f"{r['name']}: 開館時間・休館日は使わない施設"})
    for m in re.finditer(r"([^\s、。「」（）()]{2,24}?(?:ビジターセンター|自然観察の森|自然観察公園|自然学習センター))発信", text):
        if m.group(1) not in allowed and m.group(1) not in names:
            errs.append({"code": "visitor_center_not_approved", "detail": f"{m.group(1)}は台帳にない施設"})
    return errs


def restricted_source_errors(facts):
    """段階54 第1部: 山と溪谷オンライン由来の事実が、規則(状態の語は30字以内・文章でない・安全情報を含まない)を満たさないときは落とす。
    承認待ちの間はそもそも材料に入らない(observations.read_records)ので、ここは念のための二重の検査。"""
    from . import observations as O
    pol = O.load_policy()
    errs = []
    for c in _spots(facts):
        cur = c.get("current") or {}
        rec = {"url": cur.get("url"), "state": cur.get("state_raw") or cur.get("state"), "state_date_text": None}
        bad = O.restricted_errors(rec, pol)
        if bad:
            errs.append({"code": "restricted_source", "detail": f"{c.get('name')}: {bad[0]}"})
    return errs


def section_headings():
    """狙い別の節の見出し(data/ask/plan.yaml の aims.labels)。"""
    return set(AP.load_policy()["aims"]["labels"].values())


def lead_errors(lines, cfg, facts, mat, kind=""):
    """② 冒頭と「今回のおすすめ」の照合(lines: 答え、または節の行)。→ [エラー], (冒頭, おすすめの文)。"""
    errs = []
    heads = [i for i, l in enumerate(lines) if cfg["lead_heading"] in l]
    if not heads:
        return errs, ("", "")
    h = heads[0]
    picks = []
    heads_ = section_headings()
    rest_ = lines[h + 1:]
    for j, l in enumerate(rest_):
        if re.match(cfg["lead_pick_re"], l):
            picks.append(l)
        elif picks and l.strip() in heads_:                              # 段階56: 狙い別の節の見出しを挟んでも、おすすめの続きとして数える
            continue
        elif picks and not l.strip() and next((x.strip() for x in rest_[j + 1:] if x.strip()), "") in heads_:
            continue
        elif picks:
            break
    lead, pick_text = "\n".join(lines[:h]), "\n".join(picks)
    if picks and lead.strip():
        errs += lead_vs_picks(lead, kind + "\n" + pick_text if kind else pick_text, len(picks), cfg, facts, mat)
    return errs, (lead, pick_text)


def lead_vs_picks(lead, pick_text, n, cfg, facts, mat):
    errs = []
    for kw in cfg["lead_kind_words"]:
        if kw in lead and kw not in pick_text:
            errs.append({"code": "lead_mismatch", "detail": f"冒頭に「{kw}」とあるが、今回のおすすめの{n}件にない"})
    if (facts.get("lines") or {}).get("practical_rules") and any(p in pick_text for p in cfg["pick_hedge_phrases"]):     # 段階52: 冒頭の確かさを、おすすめのいちばん弱いものに合わせる
        if any(p in lead for p in cfg["lead_assertive_phrases"]) or not any(w in lead for w in cfg["lead_hedge_words"]):
            errs.append({"code": "lead_too_assertive", "detail": lead.strip().splitlines()[-1][:40]})
    for c in mat.region_candidates:
        names = short_names(c["name"])
        if any(f in lead for f in names) and not any(f in pick_text for f in names):
            errs.append({"code": "lead_mismatch", "detail": f"冒頭の「{c['name']}」が今回のおすすめにない"})
    return errs


def stage51_errors(text, facts, mat, rules, plan=None, segs=None):
    """段階51(2026-11-06 の試用で見つかった 5 点)。facts の lines.answer_rules が印と同じときだけ当てる（ask facts が付ける）。
    ① 作業の報告を答えに出さない ② 冒頭の要約と「今回のおすすめ」の食い違い ③ iNaturalist の傾向は公式ではない・傾向の範囲を書く
    ④ 本文で使った事実の出典を出典リストに出す ⑤ 見込みを言い切らない・公式の文を丸ごと転載しない。"""
    cfg = rules.get("stage51")
    if not cfg or (facts.get("lines") or {}).get("answer_rules") != cfg["flag"]:
        return []
    errs = []
    norm = _n(text)
    sents = split_sentences(text)
    for _i, s in sents:                                                      # ① 作業の報告
        if any(p in s for p in cfg["work_report_phrases"]):
            errs.append({"code": "work_report", "detail": s.strip()[:40]})
    lines = text.splitlines()                                               # ② 冒頭とおすすめ
    if segs:                                                                # 段階57 第3部: 節ごとの冒頭とおすすめ。全体の冒頭は全部のおすすめと照合する
        union = []
        flat = []
        for s in segs:                                                       # 段階58: 期間の中のエリア別の節も、エリアごとに照合する
            sub_ = AP.split_segments(s["text"], s["plan"]) if (s.get("plan") or {}).get("subject") == "areas" else None
            flat += sub_ or [s]
        for s in flat:
            e, (_lead, pick_text) = lead_errors(s["text"].splitlines(), cfg, facts, mat, kind=s["seg"]["heading"])
            errs += [{**x, "detail": f"{s['seg']['heading']}: {x['detail']}"} for x in e]
            union.append(s["seg"]["heading"] + "\n" + pick_text)
        top = AP.lead_text(text, plan)
        if top.strip() and any(union):
            errs += lead_vs_picks(top, "\n".join(union), sum(len(u.splitlines()) for u in union), cfg, facts, mat)
    else:
        errs += lead_errors(lines, cfg, facts, mat)[0]
    for s in lines:                                                          # ③ iNaturalist（かっこの中の「。」で文が切れるので、行ごとに見る）
        if cfg["inat_word"] in s:
            if cfg["inat_label"] not in s:
                errs.append({"code": "inat_unlabeled", "detail": s.strip()[:40]})
            if cfg["inat_trend"] in s and not any(w in s for w in cfg["inat_scope_words"]):
                errs.append({"code": "inat_scope_missing", "detail": s.strip()[:40]})
    urls = {u.rstrip("/") for u in URL_RE.findall(text)}                    # ④ 出典
    for c in mentioned_cands(mat, norm):
        if True:
            u = ((c.get("current") or {}).get("url") or "").rstrip("/")
            if u and u not in urls:
                errs.append({"code": "source_missing", "detail": f"{c['name']}: {u}"})
    if cfg["inat_word"] in text:
        site = {(((c.get("inat") or {}).get("source_url") or (c.get("inat") or {}).get("site_url")) or "").rstrip("/") for c in mat.spots} - {""}
        if site and not (site & urls):
            errs.append({"code": "source_missing", "detail": f"{cfg['inat_word']}: {sorted(site)[0]}"})
    for _i, s in sents:                                                      # ⑤ 見込み・転載
        if any(p in s for p in cfg["assertive_phrases"]):
            errs.append({"code": "assertive_forecast", "detail": s.strip()[:40]})

    for s in lines:                                                          # 段階52: 状態の日付は 1 つ(範囲にしない)
        if re.search(cfg["date_range_re"], s):
            errs.append({"code": "date_range", "detail": s.strip()[:40]})
    for c in mat.region_candidates:                                          # 段階52: 古い表示が残ることのある発行元の状態は参考として書く
        if (c.get("current") or {}).get("reference_only"):
            for s in lines:
                if any(f in _n(s) for f in strict_names(c["name"], shared_prefixes(mat))) and (c["current"].get("state") and cfg["reference_word"] not in s) and                         any(w in s for w in ("色づき", "見ごろ", "見頃", "真っ盛り", "まだまだ")):
                    errs.append({"code": "stale_state_asserted", "detail": f"{c['name']}: {s.strip()[:30]}"})
                    break
    if (facts.get("lines") or {}).get("practical_rules"):                  # 段階52: 出典リストは本文で使った事実の出どころだけ
        allowed = set()
        for c in mentioned_cands(mat, norm):
            allowed |= candidate_urls(c)
        if cfg["inat_word"] in text:
            allowed |= {(((c.get("inat") or {}).get("source_url") or (c.get("inat") or {}).get("site_url")) or "").rstrip("/") for c in mat.spots}
        allowed |= {u.rstrip("/") for u in ((facts.get("lines") or {}).get("open_urls") or "").split() if u.startswith("http")}
        allowed |= {(r.get("url") or "").rstrip("/") for r in facts.get("visitor_centers") or [] if r.get("name") and r["name"] in text}      # 段階55: 本文に書いた施設の発信の URL
        allowed |= {(k["source"].get("url") or "").rstrip("/") for k in facts.get("knowledge_used") or []}                                   # 段階59: 知識カードの出典
        for u in sorted(urls - allowed - {""}):
            errs.append({"code": "source_unused", "detail": u[:60]})
    if (facts.get("lines") or {}).get("practical_rules"):                  # 段階53: まつりの期間は主催者が設定した日程。現況（色づき状況）とは別の行にする
        for c in mentioned_cands(mat, norm):
            if not c.get("festivals"):
                continue
            for s in lines:
                if any(w in s for w in ("主催者が設定した期間", "まつり期間中")) and any(w in s for w in cfg["festival_state_words"]):
                    errs.append({"code": "festival_mixed_with_state", "detail": s.strip()[:40]})
                    break
            if not c.get("current") and cfg["festival_no_state"] not in text:
                errs.append({"code": "festival_no_state_missing", "detail": c["name"]})
    # 段階52: 実用情報（読めた公式ページの 1 行）。出た候補に実用情報があるなら 1 つは書く。1 件もなければ決まった一文だけを確かさの欄に書く
    mentioned = mentioned_cands(mat, norm)
    have = [pr["text"] for c in mentioned for pr in c.get("practical") or []]
    if not (facts.get("lines") or {}).get("practical_rules"):
        pass
    elif have:
        if not any(_n(h) in norm for h in have):
            errs.append({"code": "practical_missing", "detail": have[0][:30]})
    elif cfg.get("practical_fallback") and cfg["practical_fallback"] not in text and mentioned:
        errs.append({"code": "practical_fallback_missing", "detail": cfg["practical_fallback"][:20]})
    for s in lines:                                                          # 公式の文の丸ごとの転載（「」の中が長い。行ごとに見る）
        for q in re.findall(cfg["quote_re"], s):
            if len(q) > val_of(cfg["max_quote_chars"]):
                errs.append({"code": "long_quote", "detail": q[:30]})
    return errs


def mentioned_cands(mat, norm):
    """本文に出た候補。対象別の節の答えでは、その対象の節に出た候補だけ(同じ名所が紅葉と野鳥の両方にあっても取り違えない。段階57 第3部)。"""
    seg = getattr(mat, "seg_text", None) or {}
    return [c for c in mat.region_candidates if any(f in seg.get(c.get("_subject"), norm) for f in strict_names(c["name"], shared_prefixes(mat)))]


def candidate_urls(c):
    """候補の事実の出どころ（今の状態・履歴・例年の時期・実用情報・行事）の URL。"""
    out = set()
    for k in ("current",):
        out.add(((c.get(k) or {}).get("url") or "").rstrip("/"))
    for k in ("history", "typical", "typical_from_records", "practical", "events", "festivals", "notices"):
        out |= {((x or {}).get("url") or "").rstrip("/") for x in c.get(k) or [] if isinstance(x, dict)}
    return out - {""}


def val_of(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def closed_errors(text, mat, rules):
    """段階H9(穴2): 対象の日が休みの名所(closed_on の closed が true)を答えに書いたら、休みを言い切る文が要る。"""
    errs = []
    sents = [s for _i, s in split_sentences(text)]
    for c in mat.spots:
        hits = [e for e in c.get("closed_on") or [] if e.get("closed") is True]
        if not hits or not any(f in _n(text) for f in short_names(c.get("name") or "")):
            continue
        for e in hits:
            who = _n(e.get("facility") or c.get("name") or "")
            ok = any(who in _n(s) and any(w in s for w in rules.get("closed_words", [])) for s in sents)
            if not ok:
                errs.append({"code": "closed_not_stated", "detail": f"{c.get('name')}: {e.get('line') or e.get('date')}"})
    return errs


def _alternative_names(spot):
    """例年の時期が分からない候補の代わりの材料(今年の行事の名前)。前の年の記録があるか。"""
    alt = spot.get("typical_alternatives") or {}
    return [_n(e.get("name") or "") for e in alt.get("events") or [] if e.get("name")], bool(alt.get("last_year"))


def answer_units(text):
    """答えを段に分ける(空行で区切った段。①②…の候補の段はさらに候補ごと)。"""
    out = []
    for para in re.split(r"\n\s*\n", text):
        blocks = candidate_blocks(para)
        rest = [ln for ln in para.splitlines() if not any(ln in b.splitlines() for b in blocks)]
        out += blocks + ([chr(10).join(rest)] if any(x.strip() for x in rest) else [])
    return out


def typical_unknown_errors(text, mat, rules):
    """段階H10(利用者の決定 2026-11-01。評価表 R4 の読み方 (b)): 「例年の時期は分かりません」と書いた段に、
    その候補の代わりの材料(今年の行事の期間・前の年の記録)が材料にあるなら、それを添えていること。
    代わりの材料が材料にない候補は「分かりません」の明言だけでよい。"""
    phrases = rules.get("typical_unknown_phrases", [])
    words = rules.get("typical_alt_words", [])
    try:
        this_year = int(str(mat.facts.get("now") or "")[:4])
    except ValueError:
        this_year = None
    errs = []
    for unit in answer_units(text):
        if not any(p in unit for p in phrases):
            continue
        need = []
        for spot in mat.spots_in(unit):
            if not spot.get("typical_unknown"):
                continue
            names, last_year = _alternative_names(spot)
            if names or last_year:
                need.append((spot, names, last_year))
        if not need:
            continue
        u = _n(unit)
        past_year = this_year is not None and any(int(y) < this_year for y in re.findall(r"(20\d\d)年", u))
        for spot, names, last_year in need:
            ok = any(w in unit for w in words) or any(nm and nm in u for nm in names) or (last_year and past_year)
            if not ok:
                errs.append({"code": "typical_unknown_without_alternative", "detail": f"{spot.get('name')}: 例年の時期が分からないときは、今年の行事の期間か前の年の記録を添える"})
    return errs


def candidate_blocks(text):
    """「①」「②」…で始まる行から、次の番号・空行・見出しまでを 1 つの候補の段とする。"""
    out, cur = [], None
    for line in text.splitlines():
        if re.match(r"^\s*[①-⑳]", line):
            if cur:
                out.append(chr(10).join(cur))
            cur = [line]
        elif cur is not None and line.strip() and re.match(r"^\s*[・*\-]", line):
            cur.append(line)
        else:
            if cur:
                out.append(chr(10).join(cur))
            cur = None
    if cur:
        out.append(chr(10).join(cur))
    return out


def strip(text, result):
    """通らない文だけを取り除いた答え(行の中の残りの文は残す。空になった行は消す)。"""
    bad = {(x["line"], x["text"]) for x in result["sentences"] if x["errors"]}
    out = []
    for i, line in enumerate(text.splitlines()):
        parts = re.findall(r"[^。]+。?", line) or [line]
        kept = [p for p in parts if (i, p) not in bad]
        if not kept and parts and line.strip():
            continue
        new = "".join(kept)
        if re.fullmatch(r"\s*([*・\-]|[①-⑳]|\d+\.)\s*", new):
            continue
        out.append(new)
    return "\n".join(out).rstrip() + "\n"


def report_lines(result):
    out = []
    for x in result["sentences"]:
        for e in x["errors"]:
            out.append(f"NG  [{e['code']}] {x['line'] + 1}行目: {e['detail']} … {x['text'].strip()[:40]}")
    for e in result["answer_errors"]:
        out.append(f"NG  [{e['code']}] (全体): {e['detail']}")
    return out


def load_facts(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def reply_check(text, facts, rules=None, gazetteer=(), page_line=None, offers=None):
    """段階38(指示書 3-4): 利用者への返事の全文の検査。答えの検査(check)に加えて、答えの本文の外に付け足した
    作業・開発の説明(reply_terms)を落とす。ページの場所の 1 行(page_line。ask page が書いた行と同じもの)だけは検査から外す。"""
    rules = rules or load_rules()
    kept, skipped = [], False
    for line in text.splitlines():
        if page_line and line.strip() == page_line.strip() and not skipped:
            skipped = True
            continue
        kept.append(line)
    body = "\n".join(kept) + ("\n" if text.endswith("\n") else "")
    r = check(body, facts, rules, gazetteer, offers=offers)
    for x in r["sentences"]:
        t = URL_RE.sub(" ", _n(x["text"]))
        for pat in rules.get("reply_terms") or []:
            if re.search(pat, t):
                x["errors"].append({"code": "reply_dev_term", "detail": pat})
    r["ok"] = not r["answer_errors"] and all(not x["errors"] for x in r["sentences"])
    r["page_line_found"] = skipped
    r["checked_text"] = body
    return r


def page_check(lines, facts, rules=None, gazetteer=()):
    """段階38(指示書 3-3): 写真つきページの文(撮影者名・ライセンスの表記を除く)を、答えと同じ 1 文ずつの検査に通す。
    答え全体の決まり(字数・候補の数・候補の段の書き方)はページには当てない。→ {ok, sentences}"""
    rules = rules or load_rules()
    mat = Material(facts, rules, gazetteer)
    sents = []
    for i, line in enumerate(lines):
        if URL_RE.fullmatch(line.strip()):
            errs = [] if line.strip().rstrip("/") in {u.rstrip("/") for u in mat.urls} else [{"code": "unknown_url", "detail": line.strip()}]
            sents.append({"line": i, "text": line, "errors": errs})
            continue
        for _j, sen in split_sentences(line):
            sents.append({"line": i, "text": sen, "errors": check_sentence(sen, mat)})
    return {"ok": all(not x["errors"] for x in sents), "sentences": sents, "answer_errors": []}


def generic_check(text, rules=None, offers=None, clarify=False):
    """段階39 B-1: facts を持たない経路(桜・梅などの guide find の出力、検索だけで答える経路、ページ)の答えの検査。
    すべての経路が、出す前にこれか check を通す。落とすもの: 作業・開発の言葉(dev_terms・internal_terms・reply_terms)、作業の経過の文(forbidden_phrases)、
    検査・記録の事情(process_phrases)、聞き返しだけで終わる答え(候補が min_candidates 件未満で、お答えできない旨もない)。
    → {"ok", "errors": [{"code", "detail", "line"}]}。URL は検査から外す(出典の URL に語が含まれるため)。"""
    rules = rules or load_rules()
    g = rules["generic"]
    errs = []
    if clarify:                                             # 段階57 第13部の例外: 対象・場所・日付のいずれも特定できず、答えの代わりに聞き返す 1 文だけ
        n = len([l for l in text.splitlines() if l.strip()])
        q = question_errors(text, rules)
        if n == 1 and len(q) == 1:
            return {"ok": True, "errors": [], "candidates": 0}
        return {"ok": False, "errors": [{"code": "clarify_not_one_sentence", "detail": "聞き返しは 1 文だけ", "line": 0}], "candidates": 0}
    errs += term_errors(text, rules)
    for pat in g["typos"]:                                  # 出力の項目名の誤字(「出どろ」など)
        if pat in text:
            errs.append({"code": "typo", "detail": pat, "line": 0})
    errs += [{**e, "line": 0} for e in process_excuse_errors(text, rules) + source_rule_errors(text, rules) + question_errors(text, rules) + quote_errors(text, rules)]
    from . import jma_normals as JN                         # 段階61 第1部: 観測を終えた種目に「今年の」を書かない・出典と加工の行
    errs += [{**e, "line": 0} for e in JN.answer_errors(text)]
    errs += [{**e, "line": 0} for e in offer_errors(text, OF.all_texts() if offers is None else offers)]      # 段階57 第1部: 一覧にない提案の文(テーマが分かるときは条件も見る)
    n_cand = sum(1 for line in text.splitlines() if any(re.search(m, line) for m in g["candidate_markers"]))
    if n_cand < g["min_candidates"] and not any(w in text for w in g["unanswerable_ok"]):
        asks = any(w in text for w in g["ask_words"])
        errs.append({"code": "ask_back_only" if asks else "too_few_candidates",
                     "detail": f"候補が {n_cand} 件(下限 {g['min_candidates']})。聞き返しだけで終えず、見つかった範囲の候補と出どころを出す" if asks else f"候補が {n_cand} 件(下限 {g['min_candidates']})"})
    return {"ok": not errs, "errors": errs, "candidates": n_cand}


def term_errors(text, rules=None):
    """行ごとの作業・開発の言葉(dev_terms・internal_terms・reply_terms)・作業の経過の文(forbidden_phrases)・検査や記録の事情(process_phrases)。
    generic_check と行事の答えの検査(intent.check_event)が使う。URL は検査から外す。"""
    rules = rules or load_rules()
    g = rules["generic"]
    errs = []
    for i, line in enumerate(text.splitlines()):
        t = URL_RE.sub(" ", _n(line))
        for code, key in (("forbidden_phrase", "forbidden_phrases"), ("process_phrase", None)):
            pats = rules.get(key) if key else g["process_phrases"]
            for ph in pats or []:
                if ph in t:
                    errs.append({"code": code, "detail": ph, "line": i + 1})
        for key in ("dev_terms", "reply_terms"):
            for pat in rules.get(key) or []:
                if re.search(pat, t):
                    errs.append({"code": "dev_term", "detail": pat, "line": i + 1})
        for term in rules.get("internal_terms") or []:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])" if term.isascii() else re.escape(term), t, flags=re.IGNORECASE):
                errs.append({"code": "internal_term", "detail": term, "line": i + 1})
    return errs


def generic_strip(text, result):
    """generic_check が落とした行を除いた答え(利用者に見せない文を出さない)。"""
    bad = {e["line"] for e in result["errors"] if e.get("line")}
    return "\n".join(l for i, l in enumerate(text.splitlines(), 1) if i not in bad) + "\n"
