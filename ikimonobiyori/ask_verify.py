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

import yaml

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
    return {f for f in forms if len(f) >= 2}


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
                out += [cur.get("state") or "", cur.get("state_raw") or ""]
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


def check(text, facts, rules=None, gazetteer=()):
    """→ {ok, sentences: [{line, text, errors}], answer_errors: [...], candidates_mentioned}。"""
    rules = rules or load_rules()
    mat = Material(facts, rules, gazetteer)
    sents = []
    for line, s in split_sentences(text):
        sents.append({"line": line, "text": s, "errors": check_sentence(s, mat)})
    answer_errors = []
    mentioned = []
    for c in mat.region_candidates:
        if any(f in _n(text) for f in short_names(c["name"])) and c["name"] not in mentioned:
            mentioned.append(c["name"])
    need = min(rules["min_candidates"], len(mat.region_candidates))
    if len(mentioned) < need:
        answer_errors.append({"code": "too_few_candidates", "detail": f"地域の候補 {len(mentioned)} 件(必要 {need} 件)"})
    bird_names = {f for c in mat.spots if c.get("_subject") == "birds" for f in short_names(c.get("name") or "")}
    only_birds = set((facts.get("subjects") or {})) == {"birds"}
    for blk in candidate_blocks(text):                          # 評価表 R4: 各候補(①②…の段)に例年の見頃(または昨年の記録)。野鳥は「この時期に見られる鳥」
        is_bird = only_birds or any(f in _n(blk) for f in bird_names)
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
    for w, mx in (rules.get("max_repeats") or {}).items():       # 段階38: 「公式ではない」は補足に1回まとめる
        if text.count(w) > mx:
            answer_errors.append({"code": "repeated_phrase", "detail": f"「{w}」が {text.count(w)} 回(まとめて {mx} 回まで)"})
    if len(text) > rules["max_chars"]:
        answer_errors.append({"code": "too_long", "detail": f"{len(text)} 字(目安 {rules['max_chars']} 字)"})
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


def reply_check(text, facts, rules=None, gazetteer=(), page_line=None):
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
    r = check(body, facts, rules, gazetteer)
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
