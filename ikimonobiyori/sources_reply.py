"""段階85 第2部(本人の判断 B): 「出典を見せて」「URL を教えて」と言われたときの、直前の答えの URL つきの出典(ask source-urls)。通信しない。

会話の答えの出典は名前と日付だけ(ask verify が出す)。URL つきの出典は、コードがここで出す(AI が書き写さない)。
出した文は覚えて、Stop フックはその文と一致するときだけ通す(空白・リンクの書き方の違いは見ない)。値と語は data/ask/guide_mode.yaml の sources_reply。"""
import json
from datetime import datetime

from .paths import data_path

NL = "\n"


def cfg():
    from . import guide_brief as GB
    return GB.cfg()["sources_reply"]


def _path(env=None):
    return data_path(cfg()["file"], env)


def _classic_sources(text, heading):
    """今までの形の答え(ask answer)の出典の節の行(URL つき)。"""
    lines, on = [], False
    for ln in (text or "").splitlines():
        t = ln.strip().lstrip("#").strip().strip("*").strip()
        if t in (heading, heading + ":", heading + "："):
            on = True
            continue
        if on and ln.strip():
            if ln.lstrip().startswith("#"):
                break
            lines.append(ln.rstrip())
    return lines


def reply(now, env=None):
    """→ 利用者に送る文(直前の答えの URL つきの出典)。覚えて、フックで受け入れる。"""
    from . import final_check as FC
    from . import guide_verify as GV
    C = cfg()
    heading = GV.cfg()["final"]["sources_heading"]
    last = FC.load_answer(now, env)
    lines = None
    try:
        g = json.loads(GV.last_guide_path(env).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        g = None
    if last is not None and g and g.get("text") == last:
        lines = list(g.get("sources_full") or [])
        if not lines:                                    # 段階85 より前に覚えた答え(URL つきの出典が本文にある)
            lines = _classic_sources(g.get("full_text") or g.get("text"), heading)
    elif last is not None:
        lines = _classic_sources(last, heading)
    if last is None:
        text = C["no_answer"]
    elif not lines:
        text = C["none"]
    else:
        text = NL.join([C["heading"]] + lines)
    p = _path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"saved_at": now.isoformat(), "text": text}, ensure_ascii=False, indent=1), encoding="utf-8")
    return text


def accepts(message, now=None, env=None):
    """送るメッセージが、ask source-urls が出した文と一致するか。"""
    from .guide_answer_page import loose
    try:
        doc = json.loads(_path(env).read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(doc["saved_at"])
    except (OSError, ValueError, KeyError):
        return False
    from . import final_check as FC
    from datetime import timedelta
    if now is not None and abs(now - saved) > timedelta(hours=FC.cfg()["last_answer_valid_hours"]):
        return False
    return bool(doc.get("text")) and loose(doc["text"]) == loose(message)


__all__ = ["reply", "accepts"]
