"""公式の現況ページを、決まった形だけ読む小さなコード(段階16 A-4。日光市観光協会の紅葉状況・箱根町観光協会の紅葉情報の 2 つだけ)。

- 決定(ユーザー承認 2026-10-23): 承認済みの情報源を、答えるときに 1 回だけ読むコードは可。巡回・本文の保存はしない(docs/stage16-decisions.md D-10)。
- 通信は既存の実通信と同じく biyori-hub の計測フックの下だけ(呼び出し側 sources.py の read が BIYORI_ALLOW_LIVE=1・--max-requests・BIYORI_REQ_LOG を確かめる)。
  許可ホストは config.yaml の live.allowed_hosts_by_subject.autumn_leaves_status(www.nikko-kankou.org・www.hakone.or.jp)だけ。
- 先に robots.txt を読み、そのページを読んでよいときだけページを読む(読めない・拒否なら読まない)。
- 読み取ったものから残すのは事実だけ(地点・状態・更新日・見頃予測)。HTML・本文はどこにも保存しない(読めなかった応答も保存しない。
  段階15 までの _unparsed/ の保存はここでは使わない)。キャッシュもしない(答えるときに 1 回だけ読む)。
- 形が想定と違って読めないときは、推測で補わず「読めなかった」と返す(呼び出し側は要約で読む手順に戻る)。
- 地点は台帳の covers[].label で探す(全角・半角の違いは NFKC でそろえて比べる)。紹介文・見どころの文から状態を取らない(段階16 A-1・A-2)。"""
import re
import unicodedata
from datetime import date
from html.parser import HTMLParser
from http import HTTPStatus
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from .live import LiveError

SUBJECT_HOSTS = "autumn_leaves_status"
SKIP_TAGS = ("script", "style", "noscript", "template")
NIKKO_FIELDS = {"state": "現在の状況", "updated": "最終更新日", "forecast": "見頃予測"}
NIKKO_DATE_RE = re.compile(r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
NIKKO_OBSERVED_RE = re.compile(r"^(?P<m>\d{1,2})/(?P<d>\d{1,2})現在")
HAKONE_DATE_RE = re.compile(r"(?P<m>\d{1,2})/(?P<d>\d{1,2})現在")
HAKONE_ICON_RE = re.compile(r"(?P<icon>icon_lev\d+)\.\w+$")


def norm(s):
    """比べるための正規化(NFKC。全角の括弧・コロン・空白をそろえ、前後の空白を除く)。値そのものは原文のまま残す。"""
    return unicodedata.normalize("NFKC", s or "").strip()


def label_key(s):
    """地点の書き方を比べるときは、空白の有無・数も無視する(段階16 の実通信で、日光の「【足尾】CAMP THE 銀山平」だけ見つからなかった。原因は未確認)。"""
    return "".join(norm(s).split())


class _Tokens(HTMLParser):
    """HTML → [("text", 文字列) / ("img", 画像のファイル名)] の並び。script・style などの中は読まない。属性は img の src だけ見る。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "img" and not self._skip:
            src = dict(attrs).get("src") or ""
            self.out.append(("img", urlsplit(src).path.rsplit("/", 1)[-1]))

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        t = data.strip()
        if t and not self._skip:
            self.out.append(("text", t))


def tokens(html):
    p = _Tokens()
    p.feed(html)
    p.close()
    return p.out


def _label_at(tok, labels):
    """テキストの断片が、台帳の地点の書き方(label)のどれかか。NFKC で同じか、label のあとに括弧の注記が続くもの(「鬼怒川温泉 丸山(鬼怒川温泉ロープウェイ)」)。"""
    if tok[0] != "text":
        return None
    t = label_key(tok[1])
    for lb in labels:
        n = label_key(lb)
        if t == n or t.startswith(n + "("):
            return lb
    return None


def _blocks(toks, labels):
    """地点の書き方が出るたびに、次の地点の書き方の手前までを 1 つの塊にする。→ [(label, 塊の断片)]。同じ地点が何度出てもすべて返す(目次・見どころなど)。"""
    starts = [(i, lb) for i, t in enumerate(toks) if (lb := _label_at(t, labels))]
    return [(lb, toks[i + 1:(starts[k + 1][0] if k + 1 < len(starts) else len(toks))]) for k, (i, lb) in enumerate(starts)]


def _field(block, heading):
    """「見出し:値」(同じ断片)か「見出し」「値」(次の断片)の値を、原文のまま返す。なければ None。"""
    texts = [t[1] for t in block if t[0] == "text"]
    for k, raw in enumerate(texts):
        n = norm(raw)
        if n.startswith(norm(heading)):
            rest = n[len(norm(heading)):].lstrip(":").strip()
            if rest:
                cut = raw.find("：") if "：" in raw else raw.find(":")
                return raw[cut + 1:].strip() if cut >= 0 else rest
            return texts[k + 1].strip() if k + 1 < len(texts) else None
    return None


def _pick(cands, label, diag):
    """同じ地点の候補が複数あるとき: 1 つならそれ。中身が同じならその 1 つ。違えば推測で選ばず、読めなかったとする。"""
    uniq = {tuple(sorted(c.items())) for c in cands}
    if len(uniq) == 1:
        return cands[0]
    if cands:
        diag["ambiguous"].append(label)
    return None


def _body_head(block):
    """地点の塊の、本文(見出しつきの欄とその値を除いたテキスト)の最初の断片。なければ None。"""
    texts = [t[1] for t in block if t[0] == "text"]
    heads = [norm(h) for h in NIKKO_FIELDS.values()]
    skip = set()
    for k, raw in enumerate(texts):
        n = norm(raw)
        h = next((h for h in heads if n.startswith(h)), None)
        if h is not None:
            skip.add(k)
            if not n[len(h):].lstrip(":").strip():
                skip.add(k + 1)                                        # 見出しと値が別の断片
    return next((raw for k, raw in enumerate(texts) if k not in skip), None)


def _observed_md(block):
    """本文の先頭が「M/D現在」(年なし)なら "MM-DD"(状態の観察日。段階20、ユーザーの指示 2026-10-25)。
    「10/18山頂 終盤・中腹 見ごろ…」のように書き出しが違うものは取らない(日付は更新日だけ)。状態は本文から取らない。"""
    m = NIKKO_OBSERVED_RE.match(norm(_body_head(block) or ""))
    return f"{int(m['m']):02d}-{int(m['d']):02d}" if m else None


def parse_nikko(html, covers):
    """日光市観光協会の紅葉状況。地点ごとの「現在の状況:記号」「最終更新日:YYYY年M月D日」「見頃予測:…」と、本文の先頭の「M/D現在」。
    → (items, diag)。items: [{label, state, updated, forecast?, observed_md?}](cover の site/name は呼び出し側が付ける)。
    状態は「現在の状況」の欄の原文だけ(紹介文から状態を取らない)。「M/D現在」の年は呼び出し側の記録で、同じ地点の更新日から補う。"""
    labels = [c["label"] for c in covers]
    diag = {"labels_seen": 0, "ambiguous": [], "missing": [], "no_fields": []}
    found = {}
    for lb, block in _blocks(tokens(html), labels):
        diag["labels_seen"] += 1
        st, up, fc = (_field(block, NIKKO_FIELDS[k]) for k in ("state", "updated", "forecast"))
        if st is None or up is None:
            continue                                                  # 目次・画像の説明など(値のない出現)
        m = NIKKO_DATE_RE.search(norm(up))
        if not m:
            diag["no_fields"].append(lb)
            continue
        item = {"label": lb, "state": st, "updated": date(int(m["y"]), int(m["m"]), int(m["d"])).isoformat()}
        if fc:
            item["forecast"] = fc
        md = _observed_md(block)
        if md:
            item["observed_md"] = md
        found.setdefault(lb, []).append(item)
    items = [it for lb in labels if lb in found and (it := _pick(found[lb], lb, diag))]
    diag["missing"] = [lb for lb in labels if lb not in found]
    return items, diag


def _past_date(m, d, on):
    """年のない「M/D」→ 読んだ日 on に近い過去の日付(on より後になるなら前の年)。"""
    y = on.year if (m, d) <= (on.month, on.day) else on.year - 1
    return date(y, m, d)


def parse_hakone(html, covers, notation, on):
    """箱根町観光協会の紅葉情報。地点ごとに「地点名」「M/D現在」「状態の語」と状態のアイコン(icon_levN)。
    地点の塊の中に「M/D現在」とアイコンの両方があるものだけを読む(見どころの紹介文には状態のアイコンがない。段階16 A-1 の読み違いを防ぐ)。
    状態は、アイコン(台帳の notation.icons で語に直す)と、塊の中に単独で出る台帳の語(notation.map のキー)が食い違えば読めなかったとする。
    年がないので、読んだ日 on に近い過去の日付として年を補う(year_inferred)。→ (items, diag)"""
    labels = [c["label"] for c in covers]
    words = set((notation.get("map") or {})) | set(notation.get("no_info") or [])
    icons = notation.get("icons") or {}
    diag = {"labels_seen": 0, "ambiguous": [], "missing": [], "no_fields": [], "unknown_icons": []}
    found = {}
    for lb, block in _blocks(tokens(html), labels):
        diag["labels_seen"] += 1
        di = next((k for k, t in enumerate(block) if t[0] == "text" and HAKONE_DATE_RE.search(norm(t[1]))), None)
        if di is None:
            continue                                                  # 見どころ・目次など(日付のない出現)
        icon = next((m["icon"] for t in block[di:] if t[0] == "img" and (m := HAKONE_ICON_RE.search(t[1]))), None)
        if icon is None:
            diag["no_fields"].append(lb)                              # 日付はあるが状態のアイコンがない → 状態の欄ではないかもしれないので読まない
            continue
        if icon not in icons:
            diag["unknown_icons"].append(icon)                        # 台帳にないアイコン(lev3 など)は推測しない
            continue
        said = {norm(t[1]) for t in block if t[0] == "text" and norm(t[1]) in {norm(w) for w in words}}
        if said and said != {norm(icons[icon])}:
            diag["ambiguous"].append(lb)
            continue
        m = HAKONE_DATE_RE.search(norm(block[di][1]))
        item = {"label": lb, "state": icons[icon], "updated": _past_date(int(m["m"]), int(m["d"]), on).isoformat(),
                "year_inferred": True, "icon": icon}
        found.setdefault(lb, []).append(item)
    items = [it for lb in labels if lb in found and (it := _pick(found[lb], lb, diag))]
    diag["missing"] = [lb for lb in labels if lb not in found]
    return items, diag


PARSERS = {"nikko-kankou-autumn-leaves": "nikko", "hakone-kankou-koyo": "hakone"}


def robots_url(url):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "/robots.txt", "", ""))


def read_source(src, *, http_get, cfg, on, max_requests):
    """承認済みの情報源 1 件を読む(robots.txt → ページ)。→ (reads, report)。
    reads は sources record の batch の形([{source, site|name, label, state, updated, year_inferred?, forecast?, observed_md?, method: code}])。
    読めなかったとき(robots.txt が拒否・HTTP の非 200・形が違う)は reads が空で、report.status に理由。本文は返さない・残さない。"""
    sid = src["id"]
    if sid not in PARSERS:
        raise ValueError(f"{sid} はコードで読む情報源ではない(読めるのは {sorted(PARSERS)} だけ)")
    allowed = set(cfg["live"]["allowed_hosts_by_subject"][SUBJECT_HOSTS])
    rep = {"source": sid, "requests": 0, "status": None, "diag": None}
    ua = cfg["live"]["user_agent"]

    def get(u):
        host = urlsplit(u).netloc
        if host not in allowed:
            raise LiveError(f"許可リスト外のホストには送らない: {host}")
        if rep["requests"] >= max_requests:
            raise LiveError(f"--max-requests {max_requests} に達した")
        rep["requests"] += 1
        res = http_get(u)
        return res[0], res[1]

    st, body = get(robots_url(src["url"]))
    if st != HTTPStatus.OK:
        rep["status"] = f"robots.txt を確かめられない(HTTP {st})。安全側で読まない"
        return [], rep
    rp = RobotFileParser()
    rp.parse(body.splitlines())
    if not rp.can_fetch(ua, src["url"]):
        rep["status"] = "robots.txt が拒否している。読まない(台帳の readable.status を refused に直すことを提案)"
        return [], rep
    st, html = get(src["url"])
    if st != HTTPStatus.OK:
        rep["status"] = f"HTTP {st}。読まない(要約で読む手順に戻る)"
        return [], rep
    covers = src["covers"]
    if PARSERS[sid] == "nikko":
        items, diag = parse_nikko(html, covers)
    else:
        items, diag = parse_hakone(html, covers, src.get("notation") or {}, on)
    rep["diag"] = diag
    by_label = {c["label"]: c for c in covers}
    reads = []
    for it in items:
        c = by_label[it["label"]]
        r = {"source": sid, ("site" if "site" in c else "name"): c.get("site") or c.get("name"), "label": it["label"],
             "state": it["state"], "updated": it["updated"], "method": "code"}
        for k in ("year_inferred", "forecast", "observed_md"):
            if k in it:
                r[k] = it[k]
        reads.append(r)
    rep["status"] = "ok" if reads else "形が想定と違い、地点を 1 つも読めなかった(要約で読む手順に戻る)"
    return reads, rep
