"""エリア名の質問(段階58 第1部・第9部)。通信しない。辞書は data/ask/areas.yaml(座標は Wikidata で確認した市町村の代表点だけ)。

「秩父・長瀞のエリア」「飯能あたり」「A・B、C〜D〜E、F周辺など」をエリアに分解し、エリア内の名所で計画を作る。"""
import re


from . import yamlcache
from . import catalog as C
from .paths import DATA_FILES_DIR

PATH = DATA_FILES_DIR / "ask" / "areas.yaml"
_doc = None


def load():
    global _doc
    if _doc is None:
        _doc = yamlcache.load(PATH)
    return _doc


def resolve(name):
    """エリア名 → 辞書の項目か None。完全一致(名前・別名)だけ(同名の別地域・似た名前を取り違えない)。"""
    n = (name or "").strip()
    for a in load()["areas"]:
        if n == a["name"] or n in (a.get("aliases") or []):
            return a
    return None


def _longer_towns(name):
    """name を含む、より長い市区町村の名前(と末尾の 市・町・村・区 を除いた形)。「伊豆」→ 南伊豆町・南伊豆・伊豆市・伊豆の国…
    記録にない名前は、辞書の not_within(「那須塩原」「北軽井沢」)で足す。"""
    from . import guide_materials as GM
    from . import research as RS
    extra = {x for a in load()["areas"] for x in a.get("not_within") or []}
    out = set()
    for m in set(GM._town_names()) | set(RS._municipalities()) | extra:
        for x in (m, re.sub(r"(市|町|村|区)$", "", m)):
            if name in x and x != name:
                out.add(x)
    return sorted(out, key=len, reverse=True)


def _known_names():
    from . import guide_materials as GM
    from . import research as RS
    return set(GM._town_names()) | set(RS._municipalities())


def _known_city(city, names):
    """市区町村の欄が、名所の記録・出発地の辞書で分かる市区町村の名前か(「横浜市中区」「伊東市・伊豆市」も)。"""
    from . import guide_materials as GM
    return bool(city) and any(p in names for p in GM._city_parts(city))


def mentioned(name, text):
    """段階80 の追記2: name が text に、より長い市区町村の名前の一部としてでなく出てくるか(「南伊豆」「伊豆市」の「伊豆」は数えない)。"""
    t = text or ""
    if not name or name not in t:
        return False
    for x in _longer_towns(name):
        t = t.replace(x, "_" * len(x))
    for m in re.finditer(re.escape(name), t):             # 前に漢字・カタカナが続く語(「試験伊豆」「中伊豆」)の一部は数えない(都道府県の名前のあとはよい)
        before = t[m.start() - 1] if m.start() else ""
        if not before or not re.match(r"[一-龥ァ-ヶー々]", before) or before in "都道府県":
            return True
    return False


def find_in(question):
    """段階80 の追記2: 質問の文にあるエリア(名前・別名。長い市区町村の名前の一部は除く)→ (エリア, 当たった名前) か (None, None)。"""
    for a in load()["areas"]:
        for n in sorted([a["name"], *(a.get("aliases") or [])], key=len, reverse=True):
            if mentioned(n, question):
                return a, n
    return None, None


def near_names(name):
    """確実に近い名前だけ(辞書の名前を含む・含まれる)。"""
    n = (name or "").strip()
    if len(n) < 2:
        return []
    return [a["name"] for a in load()["areas"] if a["name"] in n or n in a["name"]]


def split_names(text):
    d = load()
    out = []
    for w in re.split(d["split_re"], text or ""):
        w = re.sub(r"(のエリア|エリア|あたり|周辺|方面|の$)", "", w.strip())
        if len(w) >= 2 and w not in d["stop_words"] and w not in out:
            out.append(w)
    return out


def from_question(question):
    """質問の文 → エリア名の一覧。「○○のエリア」「○○あたり」「○○周辺」の形か、辞書の名前が 2 つ以上あるとき。ないときは []。"""
    q = re.sub(r"(で|の)?(紅葉|花|野鳥|おすすめ).*$", "", question or "")
    d = load()
    if re.search(d["question_re"], question or ""):
        names = split_names(q)
        for m in re.finditer(d["question_re"], question or ""):      # 段階69 第2部 5: 「今週末、富士山界隈で見られる花」の「富士山」
            w = m.group(1).split("、")[-1]
            for x in [w, re.sub(r"^(今週末|来週末|今日|明日|週末)の?", "", w)]:
                if resolve(x) and x not in names:
                    names.append(x)
        return [n for n in names if not (resolve(n) is None and any(resolve(m) and m in n for m in names if m != n))]
    names = split_names(q)
    return names if len([n for n in names if resolve(n)]) >= 2 else []


def members(area, candidates, policy=None):
    """エリアの名所(市区町村が一致、または中心から半径の内)。"""
    policy = policy or C.load_policy()
    r = policy["range_limit"]["earth_radius_km"]
    by_cities = area.get("membership") == "cities"       # 段階80 の追記4: 市区町村で決めるエリア(秩父・那須・伊豆・富士)
    subs = [a for a in load()["areas"] if a is not area and a.get("cities") and set(a["cities"]) <= set(area.get("cities") or [])] if by_cities else []
    names = None
    out = []
    for c in candidates:
        city = c.get("city") or ""
        if any(city.startswith(x) or x in re.split(r"[・、]", city) for x in area.get("cities") or []):
            out.append(c)
            continue
        if by_cities and city and names is None:
            names = _known_names()                        # 1 回の呼び出しで 1 回だけ読む
        if by_cities and _known_city(city, names or set()):
            continue                                      # 分かる市区町村の欄があれば、それだけで決める(分からない欄は半径で)
        p = c.get("point")
        if p and p.get("lat") is not None and any(
                C.distance_km(p["lat"], p["lon"], a["center"]["lat"], a["center"]["lon"], r) <= a["radius_km"] for a in [area, *subs]):
            out.append(c)
    return out


def describe(names):
    """エリア名の一覧 → {found: [項目], unknown: [文]}。"""
    L = load()["lines"]
    found, unknown = [], []
    for n in names:
        a = resolve(n)
        if a:
            if a not in found:
                found.append(a)
            continue
        line = L["unknown"].format(name=n)
        near = near_names(n)
        if near:
            line += L["near"].format(names="・".join(near))
        unknown.append(line)
    return {"found": found, "unknown": unknown}
