"""出典の発行元の名前と「公式」の区分(段階67 第1部。承認欄 C・本人の判断 2026-11-09)。

- 公式かどうかの表示は、発行元の種類で決める: 町・市・県・国が自分で出しているページ(台帳の publisher_kind が municipality など、
  ドメインが *.lg.jp・*.go.jp・pref./city./town./village. のラベルを持つ .jp)は「公式」。
  通信先の承認(読むかどうか・source_class)とは別の項目で、source_class は変えない(候補の選び方はこれまでどおり)。
- 答えに出す発行元は名前にする。ドメインをそのまま出さない。名前が分からなければ None(呼び出し側は名前を書かない)。
値は data/ask/publisher.yaml。通信しない。"""
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from . import yamlcache

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "data" / "ask" / "publisher.yaml"
_HOSTISH = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def cfg():
    return yamlcache.load(PATH)


def host_of(url):
    h = (urlsplit(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def _suffix(host, s):
    return host == s or host.endswith("." + s)


def unused_source(url, state=False, c=None):
    """段階69 第4部 1: 答えに使わない出典か。state=True は今の状態の記録(山と溪谷オンラインは状態の語・日付・URL だけに使える)。"""
    u = (c or cfg())["unused_sources"]
    host = host_of(url)
    if not host:
        return False
    if any(_suffix(host, s) for s in u["unused"]):
        return True
    from . import observations as O
    restricted = (O.load_policy().get("record") or {}).get("restricted_sources") or {}
    hosts = (restricted.get("hosts") or {}).get("value") or []
    return not state and any(_suffix(host, s) for s in hosts)


def unused_in_text(text, c=None):
    """文に使わない出典のホスト(予想・転載)があるか(URL の行と文の両方)。"""
    u = (c or cfg())["unused_sources"]
    return any(h in (text or "") for h in u["unused"])


def strip_unused(text, c=None):
    """答えの文から、使わない出典(予想・転載)の URL の行と、そのホストを含む文を消す。→ (文, 消した行)"""
    out, removed = [], []
    for line in (text or "").splitlines():
        if unused_in_text(line, c):
            removed.append(line)
            continue
        out.append(line)
    res = "\n".join(out)
    return (res + "\n" if (text or "").endswith("\n") else res), removed


def official_domain(url, c=None):
    """自治体・国のドメインか(町・市・県・国の自身のページ)。"""
    c = (c or cfg())["official_publisher"]
    host = host_of(url)
    if not host:
        return False
    if any(_suffix(host, s) for s in c["suffixes"]):
        return True
    labels = host.split(".")
    return labels[-1] == "jp" and any(lb in c["labels"] for lb in labels[:-2])


@lru_cache(maxsize=1)
def _ledger_rows():
    """台帳の (ホスト, 発行元, 発行元の種類)。情報源の台帳(紹介サイトの台帳を除く)と施設台帳。"""
    rows = []
    for p in sorted((ROOT / "data" / "sources").glob("*.yaml")):
        if p.name == "policy.yaml":
            continue
        try:
            doc = yamlcache.load(p) or {}
        except (OSError, ValueError):
            continue
        for s in doc.get("sources") or []:
            if s.get("url") and s.get("publisher"):
                rows.append((host_of(s["url"]), s["publisher"], s.get("publisher_kind")))
    return tuple(rows)


def ledger_kind(url):
    host = host_of(url)
    return next((k for h, _, k in _ledger_rows() if h == host and k), None)


def party_kind(url, c=None):
    """段階69 第6部: 設定の表にあるホストの発行元の種類(観光協会・施設の運営者など)。なければ None。"""
    host = host_of(url)
    rows = [r for r in ((c or cfg()).get("party_publisher") or {}).get("hosts") or [] if host and _suffix(host, r["suffix"])]
    return max(rows, key=lambda r: len(r["suffix"]))["kind"] if rows else None


def is_official(url, publisher_kind=None, c=None):
    """町・市・県・国の自身のページか(段階67。承認欄 C)。"""
    c = c or cfg()
    kinds = set(c["official_publisher"]["kinds"])
    if publisher_kind in kinds or ledger_kind(url) in kinds:
        return True
    return official_domain(url, c)


def is_party(url, publisher_kind=None, c=None):
    """段階69 第6部(承認 3): 観光協会・公園の管理者・施設の運営者が、当事者として自分で出しているサイトか。"""
    c = c or cfg()
    kinds = set((c.get("party_publisher") or {}).get("kinds") or [])
    return bool(publisher_kind in kinds or ledger_kind(url) in kinds or party_kind(url, c) in kinds)


def shows_official(url, publisher_kind=None, c=None):
    """答えで「公式」と表示するか: 町・市・県・国の自身のページ(段階67)か、当事者のサイト(段階69 第6部)。表示だけの判定で、
    通信先の承認・source_class・候補の選び方には使わない。"""
    c = c or cfg()
    return is_official(url, publisher_kind, c) or is_party(url, publisher_kind, c)


def _guide_name(url):
    from . import guide
    pol = guide.load_policy()
    host = guide.host_of(url)
    row = max((r for r in pol["hosts"] if r.get("publisher") and guide._suffix_match(host, r["suffix"])), key=lambda r: len(r["suffix"]), default=None)
    return (row or {}).get("publisher")


def name(url, entry=None, title=None, c=None):
    """出典の発行元の名前(答えに出す語)。ドメインは返さない。分からなければ None。
    entry は名所(tags の city・prefecture を見る)、title は出典の題名(最初の語を使う)。"""
    if not url:
        return None
    c = c or cfg()
    g = _guide_name(url)
    if g:
        return g
    host = host_of(url)
    led = next((p for h, p, _ in _ledger_rows() if h == host), None)
    if led:
        return led
    tags = (entry or {}).get("tags") or entry or {}
    if official_domain(url, c):
        labels = host.split(".")
        for lb in labels[:-2]:
            key = c["name_from_label"].get(lb)
            if key and tags.get(key):
                return tags[key]
    t = (title or "").strip()
    if t:
        first = re.split(r"[\s　(（]", t, maxsplit=1)[0]
        if first and not _HOSTISH.match(first):
            return first
    return None


def clean(pub):
    """発行元の欄がドメインそのもの(town.ninomiya.kanagawa.jp など)なら None にする(答えにドメインを出さない)。"""
    if not pub:
        return None
    return None if _HOSTISH.match(str(pub).strip()) else pub
