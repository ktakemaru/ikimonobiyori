"""段階72 第2部: 名前を問う質問と、同じ名前の別のもの(名前の辞書 data/knowledge/names.yaml)。通信しない。

- 名前を問う質問(「枯れた茎に氷ができる。なんというの?」)を見分け、説明の語(clues)から名前を引く。
- 答え: 1 文目は辞書の答えの文(聞かれた対象に答え、同じ名前の別のものは区別のために短く添えるだけ)。
  続けて、その名前のカード(知識カードの subject)の事実と出典。カードがなければ辞書の文と出典 URL だけ。
- 同じ名前の別のもの(homonyms): 名前の語 → 意味の一覧(季節・月つき)。見どころの季節ごとの行に使う。"""
import re

from . import yamlcache
from .paths import DATA_FILES_DIR

PATH = DATA_FILES_DIR / "knowledge" / "names.yaml"
NL = "\n"


def cfg():
    return yamlcache.load(PATH)


def is_name_question(question, c=None):
    c = c or cfg()
    q = (question or "").strip()
    return any(re.search(p, q) for p in c["name_question_patterns"])


def lookup(question, c=None):
    """説明の語がすべて質問にある名前の項目(最初の 1 つ)。なければ None。"""
    c = c or cfg()
    q = question or ""
    for n in c["names"]:
        if any(all(w in q for w in clue) for clue in n["clues"]):
            return n
    return None


def homonym_senses(word, c=None):
    """名前の語 → 同じ名前の別のものの意味の一覧(なければ [])。"""
    c = c or cfg()
    for key, h in (c.get("homonyms") or {}).items():
        if word == key or word in (h.get("words") or []):
            return list(h.get("senses") or [])
    return []


def homonym_candidates(names):
    """段階72 第2部 3: 同じ形の名前の候補(辞書に載っていないもの)。names は (名前, 出どころ) の一覧。
    片仮名の名前と同じ読みの漢字の語・同じ名前が種と場所の両方にある、を拾う(追加は確かめたものだけ。ここは一覧だけ)。"""
    known = set()
    for h in (cfg().get("homonyms") or {}).values():
        known |= set(h.get("words") or [])
    by = {}
    for n, where in names:
        if n and n not in known:
            by.setdefault(n, set()).add(where)
    return sorted((n, sorted(w)) for n, w in by.items() if len(w) > 1)


def _cards(entry, cards):
    subs = set(entry.get("card_subjects") or [])
    return [r for r in cards if r.get("subject") in subs and not r.get("retired")]


def compose(question, cards=None, env=None):
    """名前の質問の答え。辞書に当たらなければ None。"""
    c = cfg()
    entry = lookup(question, c)
    if not entry:
        return None
    if cards is None:
        from . import knowledge as K
        cards = K.load_shown(env)
    lines = [entry["answer"]]
    use = _cards(entry, cards)
    urls = []
    for r in use:
        lines += ["", r["title"]] + ["・" + f.rstrip("。") + f"({r['source']['name']})" for f in r["facts"]]
        if r["source"].get("url"):
            urls.append(r["source"]["url"])
    if not urls and entry.get("source_url"):
        urls.append(entry["source_url"])
    link = compare_link(entry.get("homonym") or "", c)      # 段階72 第2部 6: 写真(ライセンスの明確なもの)がまだないときは、見比べられるページを案内する
    if link:
        lines += ["", link]
    lines += ["", "出典"] + list(dict.fromkeys(urls))
    return NL.join(lines) + NL


def compare_link(word, c=None):
    """写真で見比べられるページの 1 行(写真がないとき)。なければ None。"""
    c = c or cfg()
    for key, h in (c.get("homonyms") or {}).items():
        if word == key or word in (h.get("words") or []):
            p = (c.get("compare_pages") or {}).get(key)
            if p:
                return f"{p['label']}: {p['url']}"
    return None
