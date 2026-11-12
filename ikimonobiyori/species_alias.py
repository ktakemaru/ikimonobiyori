"""段階82 第1部: 質問の種の名前の読み替え(ひらがな・カタカナ・漢字を同じ種に)。通信しない・書き込まない。

本人の判断(2026-11-12): 種の名前は、ひらがな・カタカナ・漢字のどれで書かれても同じ種として扱う。資料・ページの題・答えでは、
認識した種の名前(カタカナ)を使う。語と表は data/ask/species_alias.yaml。

- 種の名前(カタカナ)の一覧: 名所カタログ・ガイドのカタログの種の語、写真の対応表(リポジトリの表)、野草の花期の表、
  写真つきページの書き方の表の値、season_place.yaml の species の語。
- カタカナの名前のひらがな表記は機械的に作る(字数の下限と作らない語は設定)。漢字は設定の表(種の名前が一覧にあるものだけ)。
- season_place.yaml の species の語にすでにある書き方(「あじさい」「梅」)は、その表で引けるので書き換えない(今までの答えを変えない)。
- もっと長い既知の語の一部(「椿寒桜」の椿)は書き換えない。短いひらがなの語は前後の字を確かめる(short_ok)。"""
import re
from functools import lru_cache

from . import yamlcache
from .paths import DATA_FILES_DIR

PATH = DATA_FILES_DIR / "ask" / "species_alias.yaml"
_KATA = re.compile(r"^[ァ-ヶー]+$")
_HIRA = re.compile(r"^[ぁ-ゖー]+$")


def cfg():
    return yamlcache.load(PATH)


def to_hiragana(s):
    return "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in s or "")


@lru_cache(maxsize=1)
def _sources():
    from . import season_place as SP
    from . import guide_photos
    names = set(SP._catalog_kinds())
    try:
        names |= set(guide_photos.load_table(include_runtime=False))
    except (OSError, ValueError, KeyError):
        pass
    try:
        from . import wildflower_species as WS
        names |= set(WS.names())
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    sc = SP.cfg()
    names |= set(((sc.get("guide_page") or {}).get("aliases") or {}).values())
    table_words = set()
    for sp in sc.get("species") or []:
        table_words |= set(sp.get("words") or []) | {sp["name"]}
    names |= {w for w in table_words if _KATA.match(w)}
    return frozenset(n for n in names if n), frozenset(table_words)


def canonical_names():
    """種の名前(カタカナだけの語)の一覧。"""
    names, _tw = _sources()
    return sorted(n for n in names if _KATA.match(n))


@lru_cache(maxsize=1)
def alias_table():
    """{書き方: 種の名前(カタカナ)}。season_place.yaml の species の語にある書き方は入れない(その表で引ける)。"""
    c = cfg()
    names, table_words = _sources()
    kata = {n for n in names if _KATA.match(n)}
    out = {}
    mn = c["min_generated_hiragana_chars"]
    skip = set(c.get("no_generate") or [])
    for n in sorted(kata):
        h = to_hiragana(n)
        if h != n and len(h) >= mn and h not in skip and h not in table_words:
            out.setdefault(h, n)
    for k, v in (c.get("kanji") or {}).items():
        if v in kata and k not in table_words:
            out[k] = v
    return out


@lru_cache(maxsize=1)
def table_hiragana():
    """season_place.yaml の species の語のうち、ひらがなだけの書き方 → 種の名前(写真つきページの書き方の表でカタカナにする)。"""
    from . import season_place as SP
    sc = SP.cfg()
    al = (sc.get("guide_page") or {}).get("aliases") or {}
    out = {}
    for sp in sc.get("species") or []:
        name = al.get(sp["name"], sp["name"])
        for w in sp.get("words") or []:
            if _HIRA.match(w) and w != name:
                out.setdefault(w, name)
    return out


def short_ok(text, a, b, c=None):
    """text[a:b] の短いひらがなの語が、種の名前として読める位置か(前後の字・除く形)。短くない語・ひらがなでない語は常に True。"""
    c = c or cfg()
    g = c["short_guard"]
    w = text[a:b]
    if w in (g.get("katakana_prefix_words") or []) and b < len(text) and _KATA.match(text[b]):
        return False                                   # 「コケモモ」「コケリンドウ」のコケは苔ではない
    if len(w) > g["max_chars"] or not _HIRA.match(w):
        return True
    ok = g["ok_neighbors"]
    prev = text[a - 1] if a > 0 else ""
    nxt = text[b] if b < len(text) else ""
    if (prev and _HIRA.match(prev) and prev not in ok) or (nxt and _HIRA.match(nxt) and nxt not in ok):
        return False
    if prev and re.match(r"[一-龥々]", prev):            # 送り仮名(「大きく」の「きく」)は種の名前にしない
        return False
    for p in g.get("exclude_re") or []:
        for m in re.finditer(p, text):
            if m.start() <= a and b <= m.end():
                return False
    return True


def normalize(text):
    """質問の文の種の名前を、認識した種の名前(カタカナ)に書き換える。書き換えるものがなければ元のまま。
    返り値は (書き換えた文, [(元の書き方, 種の名前), ...])。"""
    t = text or ""
    table = alias_table()
    if not t or not table:
        return t, []
    _names, table_words = _sources()
    known = set(table) | set(_names) | set(table_words)
    hits = []
    for w in sorted(known, key=len, reverse=True):
        if not w:
            continue
        for m in re.finditer(re.escape(w), t):
            hits.append((m.start(), m.end(), w))
    taken, keep = [], []
    for a, b, w in sorted(hits, key=lambda x: (-(x[1] - x[0]), x[0])):
        if any(a < b2 and a2 < b for a2, b2, _ in taken):
            continue                                   # もっと長い既知の語の一部
        taken.append((a, b, w))
        if w in table and short_ok(t, a, b):
            keep.append((a, b, w))
    if not keep:
        return t, []
    out, pos, changed = [], 0, []
    for a, b, w in sorted(keep):
        out += [t[pos:a], table[w]]
        pos = b
        if (w, table[w]) not in changed:
            changed.append((w, table[w]))
    out.append(t[pos:])
    return "".join(out), changed


@lru_cache(maxsize=1)
def word_groups():
    """{種の名前: その種の書き方の集合}。season_place.yaml の species の名前と語、カタカナの名前とそのひらがな・漢字の書き方。
    段階82 第2部(種の特徴の文の照合)で、文の中の種と、カードがその種の話かを見る。"""
    from . import season_place as SP
    groups, owner = {}, {}
    for sp in SP.cfg().get("species") or []:
        ws = set(sp.get("words") or []) | set(sp.get("match") or []) | {sp["name"]}
        groups.setdefault(sp["name"], set()).update(ws)
        for w in ws:
            owner.setdefault(w, sp["name"])
    for n in sorted(_sources()[0]):                     # カタログの種の語(漢字の「椿寒桜」も、ほかの種の一部として数えないように)
        if n in owner:
            continue
        groups.setdefault(n, set()).add(n)
        owner[n] = n
    for w, n in alias_table().items():
        name = owner.get(n, n)
        groups.setdefault(name, set()).add(w)
    return {k: frozenset(v) for k, v in groups.items()}


def species_in(text):
    """文の中の種の名前(もっと長い語の一部は数えない。短いひらがなの語は前後の字を見る)→ [種の名前](出た順)。"""
    t = text or ""
    pairs = sorted(((w, n) for n, ws in word_groups().items() for w in ws if w), key=lambda x: -len(x[0]))
    taken, found = [], []
    for w, n in pairs:
        for m in re.finditer(re.escape(w), t):
            a, b = m.start(), m.end()
            if any(a < b2 and a2 < b for a2, b2 in taken) or not short_ok(t, a, b):
                continue
            taken.append((a, b))
            found.append((a, n))
    return list(dict.fromkeys(n for _a, n in sorted(found)))
