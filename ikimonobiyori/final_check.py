"""段階69 第1部: 最終メッセージの検査(`ask final-check`)。通信しない。

エージェントが利用者に送る**最終メッセージ全体**(ask answer の出力と、前後に添えた文のすべて)を受け取り、
送ってはいけない文(作業メモ・作業の事情・提案・質問・候補 0 件の答えに付いた案内)をコードが消して、送ってよい文だけを返す。
- ask answer の出力にある文は、作業の語を含まない限り残す(案内は offers.yaml の条件を満たしてコードが出したもの)。
  ただし候補が 0 件の答えに付いた案内(表・写真つきのページ)は消す。
- ask answer の出力にない文(エージェントが足した文)は、提案・質問の語や文末の質問があれば消す。
- 消したあと本文が空なら、ask answer の出力をそのまま返す(空にしない)。
- 消した文はデータ置き場の logs/answers.jsonl に残す(答えには出さない)。
語と値は data/ask/final_check.yaml。"""
import json
import re
from datetime import datetime, timedelta

from . import yamlcache
from .paths import DATA_FILES_DIR, data_path

CONFIG = DATA_FILES_DIR / "ask" / "final_check.yaml"
NL = "\n"
_SENT = re.compile(r"[^。！!]+[。！!]?")


def cfg():
    return yamlcache.load(CONFIG)


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def remember_answer(text, question, now, env=None):
    """ask answer の答えを覚える(最終メッセージの検査で、答えの本文と添えた文を見分けるため)。"""
    p = data_path(cfg()["last_answer_file"], env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"saved_at": now.isoformat(), "question": question, "text": text}, ensure_ascii=False, indent=1), encoding="utf-8")


def load_answer(now=None, env=None):
    """直前の ask answer の答えの本文(有効期間の中だけ)。なければ None。"""
    try:
        doc = json.loads(data_path(cfg()["last_answer_file"], env).read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(doc["saved_at"])
    except (OSError, ValueError, KeyError):
        return None
    if now is not None:
        try:
            if now - saved > timedelta(hours=cfg()["last_answer_valid_hours"]) or now < saved - timedelta(hours=cfg()["last_answer_valid_hours"]):
                return None
        except TypeError:
            pass
    return doc.get("text")


def _has(words, s):
    return any(w in s for w in words)


def _is_zero(answer, c):
    return bool(answer) and _has(c["zero_words"], answer)


def _is_question(s, c):
    t = s.strip()
    return any(t.endswith(e) for e in c["question_ends"])


def check(message, answer=None, c=None):
    """→ {text, removed: [消した文], fallback: 答えに戻したか}。"""
    c = c or cfg()
    answer = answer or ""
    ans_lines = {_norm(l) for l in answer.splitlines() if l.strip()}
    ans_sents = {_norm(s) for l in answer.splitlines() for s in _SENT.findall(l) if s.strip()}
    zero = _is_zero(answer, c) or (not answer and _is_zero(message, c))
    out, removed = [], []
    skip_block = False
    for line in (message or "").splitlines():
        st = line.strip()
        if skip_block:
            if not st:
                skip_block = False
                out.append(line)
            else:
                removed.append(st)
            continue
        if st and _has(c["block_heads"], st) and _norm(st) not in ans_lines:
            removed.append(st)
            skip_block = True
            continue
        if not st or re.match(r"^https?://", st):
            out.append(line)
            continue
        in_answer = _norm(st) in ans_lines
        parts = _SENT.findall(line) or [line]
        kept = []
        for p in parts:
            ps = p.strip()
            if not ps:
                kept.append(p)
                continue
            from_answer = in_answer or _norm(ps) in ans_sents
            bad = _has(c["work_words"], ps)
            if not bad and zero and _has(c["zero_offer_words"], ps):
                bad = True
            if not bad and not from_answer and (_has(c["offer_words"], ps) or _is_question(ps, c) or _has(c["zero_offer_words"], ps)):
                bad = True
            if bad:
                removed.append(ps)
            else:
                kept.append(p)
        new = "".join(kept)
        if not new.strip() or re.fullmatch(r"\s*([*・\-]|[①-⑳]|\d+\.)\s*", new):
            continue
        out.append(new.rstrip())
    text = _tidy(NL.join(out))
    fallback = False
    if not _body(text).strip():
        text = answer if answer.strip() else (message or "")
        fallback = True
    return {"text": text.rstrip(NL) + NL, "removed": removed, "fallback": fallback}


def _body(text):
    """出典の見出しと URL を除いた本文。"""
    lines = []
    for l in text.splitlines():
        if l.strip() == "出典":
            break
        if not re.match(r"^\s*https?://", l):
            lines.append(l)
    return NL.join(lines)


def _tidy(text):
    """空行の連続を 1 つに、先頭・末尾の空行を消す。見出しだけ残った節(次が空行か終わり)は消す。"""
    lines = text.splitlines()
    out = []
    for i, l in enumerate(lines):
        if not l.strip() and (not out or not out[-1].strip()):
            continue
        out.append(l)
    while out and not out[-1].strip():
        out.pop()
    res = []
    for i, l in enumerate(out):
        if re.match(r"^#{1,4}\s", l):
            rest = []
            for x in out[i + 1:]:
                if re.match(r"^#{1,4}\s", x):
                    break
                rest.append(x)
            if not any(x.strip() for x in rest):
                continue
        res.append(l)
    while res and not res[-1].strip():
        res.pop()
    return NL.join(res)


def log_removed(removed, now, question=None, env=None):
    if not removed:
        return
    p = data_path(cfg()["log_file"], env)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="") as f:
        f.write(json.dumps({"at": now.isoformat(), "kind": "final_check", "question": (question or "")[:80], "removed": removed}, ensure_ascii=False) + NL)


def run(message, *, answer=None, now=None, env=None):
    """最終メッセージ → 送ってよい文(必ず空でない)。answer を省くと、直前の ask answer の答えを使う。"""
    now = now or datetime.now().astimezone()
    if answer is None:
        answer = load_answer(now, env)
    r = check(message, answer)
    try:
        log_removed(r["removed"], now, env=env)
    except OSError:
        pass
    return r
