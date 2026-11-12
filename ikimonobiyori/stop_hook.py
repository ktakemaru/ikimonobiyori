"""段階72 第1部: 送る前の検査を Claude Code の Stop フックで強制する。通信しない。

エージェントが応答を終えようとするとき(Stop フック)、直前の応答の文(入力の `last_assistant_message`)と、
会話の記録(`transcript_path` の JSONL。この回の利用者の文と、使った道具)を見て、次のどれかがあれば終了を止め、
エージェントへの次の手順を理由として返す(`{"decision": "block", "reason": ...}`):
- 最終メッセージに、送ってはいけない文(作業メモ・作業の事情・提案・利用者への質問)がある(`ask final-check` と同じ規則)
- `ask answer` が調べる対象・読むページを出したのに、調べずに(検索・取得・記録をせずに)終えようとしている
- `ask answer` を実行したのに、最終メッセージを `ask final-check` に通していない
- 生き物・お出かけの質問に、道具を使わずに(`ask answer` を実行せずに)答えようとしている
止めない(検査しない)とき: 利用者が「イキモノビヨリを使わずに」と言った回、仕組み・開発についての質問の回、
この回に `ask answer` を実行しておらず生き物の質問でもない回(開発の作業など)、同じ回で上限の回数だけ止めたあと、
入力・記録が読めないとき(フックの失敗で応答全体を止めない。失敗したら通す)。
語と値は data/ask/final_check.yaml の `stop_hook`。"""
import hashlib
import json
import re
import sys
from datetime import datetime

from . import final_check as FC
from .paths import data_path

NL = "\n"


def cfg():
    return FC.cfg()["stop_hook"]


# ---- 会話の記録(JSONL)から、この回の利用者の文と道具の呼び出しを取り出す ----

def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return NL.join(b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _result_text(block):
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return NL.join(x.get("text") or "" for x in c if isinstance(x, dict))
    return ""


def _is_prompt(entry, c):
    """利用者が打った文か(道具の結果・コマンドの記録・メタの行・このフックの理由の文は除く)。"""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    t = _text_of(content).strip()
    if not t:
        return False
    if any(t.startswith(p) for p in c["not_prompt_prefixes"]):
        return False
    return c["reason_marker"] not in t


def read_turn(lines, c=None):
    """JSONL の行 → {prompt: この回の利用者の文, calls: [{name, input, result}]}(この回 = 最後の利用者の文のあと)。"""
    c = c or cfg()
    entries = []
    for l in lines:
        l = l.strip()
        if not l:
            continue
        try:
            entries.append(json.loads(l))
        except ValueError:
            continue
    start = None
    for i, e in enumerate(entries):
        if _is_prompt(e, c):
            start = i
    if start is None:
        return {"prompt": "", "calls": []}
    prompt = _text_of(entries[start]["message"]["content"]).strip()
    calls, by_id = [], {}
    for e in entries[start + 1:]:
        if e.get("isSidechain"):
            continue
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if e.get("type") == "assistant" and b.get("type") == "tool_use":
                call = {"name": b.get("name") or "", "input": b.get("input") or {}, "result": ""}
                calls.append(call)
                by_id[b.get("id")] = call
            elif e.get("type") == "user" and b.get("type") == "tool_result" and b.get("tool_use_id") in by_id:
                by_id[b["tool_use_id"]]["result"] = _result_text(b)
    return {"prompt": prompt, "calls": calls}


def _cmd(call):
    inp = call.get("input") or {}
    return str(inp.get("command") or inp.get("prompt") or inp.get("query") or inp.get("url") or "")


def _matches(call, patterns):
    return any(re.search(p, _cmd(call)) for p in patterns)


# ---- 判定 ----

def exempt(prompt, c=None):
    """検査しない回か(→ 理由の語。検査するなら None)。"""
    c = c or cfg()
    p = prompt or ""
    for w in c["skip_words"]:
        if w in p:
            return "skip_word"
    for w in c["mechanism_words"]:
        if w in p:
            return "mechanism"
    return None


def _is_research(call, c):
    if call.get("name") in c["research_tools"]:
        return True
    return _matches(call, c["record_patterns"])


def _decide_guide(msg, calls, at, c, guide_ok, page_ok=None):
    """段階75: ガイドの形の回。ask verify --brief が合格(または今の形の答え)を出し、最終メッセージがその文と一致するときだけ通す。
    段階81 の続き 1: この回に ask verify のあとで写真つきのページを作り(ask page)、最終メッセージが ask page-reply の案内の文と一致するときも通す。"""
    after = calls[at + 1:]
    verifies = [i for i, k in enumerate(after) if _matches(k, c["guide_verify_patterns"])]
    if not verifies:
        return {"block": True, "why": "guide_no_verify", "reasons": [c["reasons"]["guide_no_verify"]]}
    pages = [i for i, k in enumerate(after) if _matches(k, c.get("page_patterns") or [])]
    if msg.strip() and page_ok and pages and pages[-1] > verifies[-1] and page_ok(msg):
        return {"block": False, "reasons": [], "why": "guide_page"}
    if msg.strip() and not (guide_ok(msg) if guide_ok else False):
        return {"block": True, "why": "guide_mismatch", "reasons": [c["reasons"]["guide_mismatch"]]}
    return {"block": False, "reasons": [], "why": "guide_checked"}


def decide(payload, turn, answer=None, c=None, guide_ok=None, page_ok=None):
    """→ {"block": bool, "reasons": [エージェントへの次の手順], "why": 判定の語}。
    guide_ok(段階75): 最終メッセージが ask verify --brief の最終の文と一致するかを返す関数。
    page_ok(段階81 の続き): 最終メッセージが ask page-reply の案内の文と一致するかを返す関数。"""
    c = c or cfg()
    msg = payload.get("last_assistant_message") or ""
    prompt, calls = turn.get("prompt") or "", turn.get("calls") or []
    ex = exempt(prompt, c)
    if ex:
        return {"block": False, "reasons": [], "why": ex}
    answers = [i for i, k in enumerate(calls) if _matches(k, c["answer_patterns"])]
    briefs = [i for i, k in enumerate(calls) if _matches(k, c.get("brief_patterns") or [])]
    if briefs and (not answers or briefs[-1] > answers[-1]):        # 段階75: ガイドの形(ask brief → 書く → ask verify --brief)
        return _decide_guide(msg, calls, briefs[-1], c, guide_ok, page_ok)
    if not answers:
        if not calls and any(w in prompt for w in c["ikimono_words"]) and msg.strip():
            from . import guide_brief as GB                  # 段階77: 新しい形が既定のときは、新しい形の手順を案内する
            key = "no_ask_answer_guide" if GB.answer_form() == "guide" and c["reasons"].get("no_ask_answer_guide") else "no_ask_answer"
            return {"block": True, "why": "no_ask_answer", "reasons": [c["reasons"][key]]}
        return {"block": False, "reasons": [], "why": "not_ikimono_turn"}
    reasons = []
    last = answers[-1]
    after = calls[last + 1:]
    res = calls[last].get("result") or ""
    if len(answers) == 1 and any(w in res for w in c["research_marks"]) and not any(_is_research(k, c) for k in after):
        reasons.append(c["reasons"]["research"])
    r = FC.check(msg, answer)
    if r["removed"]:
        shown = "」「".join(s[:c["quote_chars"]] for s in r["removed"][:c["quote_max"]])
        reasons.append(c["reasons"]["removed"].format(sentences=shown))
    if not any(_matches(k, c["final_check_patterns"]) for k in after) and msg.strip():
        reasons.append(c["reasons"]["no_final_check"])
    return {"block": bool(reasons), "reasons": reasons, "why": "checked"}


# ---- 止めた回数(同じ回で上限まで。無限の繰り返しを防ぐ) ----

def _key(payload, prompt):
    return (payload.get("session_id") or "") + ":" + hashlib.sha1((prompt or "").encode("utf-8")).hexdigest()[:16]


def _state_path(env=None):
    return data_path(cfg()["state_file"], env)


def blocks_so_far(key, env=None):
    try:
        return int(json.loads(_state_path(env).read_text(encoding="utf-8")).get(key, 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def note_block(key, env=None):
    p = _state_path(env)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            doc = {}
    except (OSError, ValueError):
        doc = {}
    doc[key] = int(doc.get(key, 0)) + 1
    keep = cfg()["state_keep"]
    if len(doc) > keep:                                  # 古い回の数を捨てる(ファイルを大きくしない)
        doc = dict(list(doc.items())[-keep:])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def run(payload, *, env=None, now=None):
    """Stop フックの入力(dict) → 出力の dict(止めるとき {"decision": "block", "reason"})か None(通す)。"""
    c = cfg()
    lines = []
    tp = payload.get("transcript_path")
    if tp:
        try:
            with open(tp, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            lines = []
    turn = read_turn(lines, c)
    if not turn["prompt"] and not lines:
        return None                                      # 記録が読めない: 通す
    key = _key(payload, turn["prompt"])
    if blocks_so_far(key, env) >= c["max_blocks_per_turn"]:
        return None
    t = now or datetime.now().astimezone()
    answer = FC.load_answer(t, env)
    from . import guide_verify as GV
    from . import guide_answer_page as GAP
    d = decide(payload, turn, answer, c, guide_ok=lambda m: GV.accepts(m, t, env), page_ok=lambda m: GAP.accepts_reply(m, t, env))
    if not d["block"]:
        return None
    note_block(key, env)
    reason = c["reason_marker"] + " " + " ".join(d["reasons"])
    return {"decision": "block", "reason": reason}


def to_output(out, mode=None):
    """段階74: run() の判定 → フックが標準出力に書く JSON(stop_hook.output。block / feedback)。"""
    mode = mode or cfg().get("output") or "block"
    if mode == "feedback":
        return {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": out["reason"]}}
    return out


def main(stdin=None, stdout=None):
    """フックの入口。どんな失敗でも終了コード 0 で通す(応答全体を止めない)。"""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        raw = stdin.buffer.read().decode("utf-8") if hasattr(stdin, "buffer") else stdin.read()
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            return 0
        out = run(payload)
        if out:
            stdout.write(json.dumps(to_output(out), ensure_ascii=False))
            stdout.flush()
    except Exception:                                    # 失敗したら通す
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
