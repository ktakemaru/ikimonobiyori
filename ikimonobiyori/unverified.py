"""段階72 第5部(本人の判断 1。2026-11-10): 一般に知られた名所を「未確認」として添える。通信しない。

- 記録(`ask record-unverified`): 名前・都県(必須)・市町村(任意)・テーマ(花の種・紅葉など)・例年の月(任意)だけ。
  出典の欄は「一般に知られた名所(未確認)」。電話・日付・料金・本数などの項目は受け付けない。都県が範囲外なら受け付けない。
  置き場所はデータ置き場(公開リポジトリに入れない)。
- 答え: 記録で確かめた候補のあとに「ほかに知られている名所(今年の情報・出典は未確認)」の節で、名前・都県・例年の月を最大 5 件。
  「今回のおすすめ」にも出典の欄にも入れない。確かめ済み(verified)の印のあるもの・答えにすでに出ている名前は出さない。
- 確かめて格上げ: 公式ページで確かめて通常の名所として記録したら、`--verify` で「確かめ済み」の印を付ける。
語と値は data/ask/unverified.yaml。"""
import json
import re
from datetime import datetime

from . import yamlcache
from .paths import DATA_FILES_DIR, data_path

NL = "\n"
PATH = DATA_FILES_DIR / "ask" / "unverified.yaml"


def cfg():
    return yamlcache.load(PATH)


def _file(env=None):
    return data_path(cfg()["file"], env)


def load(env=None):
    try:
        lines = _file(env).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def _save(rows, env=None):
    p = _file(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + NL for r in rows), encoding="utf-8")


def in_range_prefectures():
    from . import coverage as CV
    return {p for p, _ in CV.range_prefectures()}


def _partial():
    from . import coverage as CV
    return CV.partial_prefectures()


def _city_in_range(city, prefecture):
    """市町村の代表点が分かれば、出発地(既定)から範囲の内か。分からなければ None。"""
    from . import catalog as C
    from . import origins
    pt = origins.municipal_point(city)
    if not pt:                                           # 地域の辞書の代表点(白河市など)
        for reg in yamlcache.load(DATA_FILES_DIR / "regions.yaml")["regions"]:
            pt = next(({"lat": x["lat"], "lon": x["lon"]} for x in reg.get("points") or [] if x.get("name") == city), None)
            if pt:
                break
    if not pt:
        return None
    pol = C.load_policy()
    o = origins.lookup(pol["range_limit"]["default_origin"])
    if not o:
        return None
    km = C.distance_km(o["lat"], o["lon"], pt["lat"], pt["lon"], pol["range_limit"]["earth_radius_km"])
    return km <= pol["range_limit"]["max_km"]


def validate(rec, c=None):
    c = c or cfg()
    errs = []
    if not isinstance(rec, dict):
        return ["1 件は JSON のオブジェクト"]
    extra = sorted(set(rec) - set(c["fields"]))
    if extra:
        errs.append(f"受け付けない項目: {', '.join(extra)}(名前・都県・市町村・テーマ・例年の月だけ)")
    for k in c["required"]:
        if not rec.get(k):
            errs.append(f"{k} がない")
    for k in ("name", "city", "theme"):
        v = rec.get(k)
        if v is not None and (not isinstance(v, str) or len(v) > c["max_chars"] or re.search(c["detail_re"], v)):
            errs.append(f"{k} は短い名前だけ(電話・日付・料金・本数などは書かない)")
    ms = rec.get("months")
    if ms is not None and (not isinstance(ms, list) or not all(isinstance(m, int) and 1 <= m <= len(c["month_names"]) for m in ms)):
        errs.append("months は月の数の一覧(1〜12)")
    pref = rec.get("prefecture")
    if pref and pref not in in_range_prefectures():
        errs.append(f"{pref} は範囲の外")
    elif pref and rec.get("city") and _city_in_range(rec["city"], pref) is False:
        errs.append(f"{rec['city']} は範囲の外")
    elif pref and pref in _partial() and not (rec.get("city") and _city_in_range(rec["city"], pref)):
        errs.append(f"{pref} は一部だけが範囲。範囲の内と確かめられる市町村(city)が要る")
    return errs


def record(batch, env=None, now=None):
    """→ {written, rejected: [{index, errors}]}。同じ名前・都県は置き換える(確かめ済みの印は残す)。"""
    c = cfg()
    now = now or datetime.now().astimezone()
    rows = load(env)
    written, rejected = 0, []
    for i, rec in enumerate(batch if isinstance(batch, list) else [batch]):
        errs = validate(rec, c)
        if errs:
            rejected.append({"index": i, "errors": errs})
            continue
        row = {k: rec[k] for k in c["fields"] if rec.get(k) is not None}
        row["source"] = c["source_label"]
        row["recorded_at"] = now.isoformat()
        old = next((r for r in rows if (r["name"], r["prefecture"]) == (row["name"], row["prefecture"])), None)
        if old:
            row.update({k: old[k] for k in ("verified", "verified_at") if k in old})
            rows[rows.index(old)] = row
        else:
            rows.append(row)
        written += 1
    _save(rows, env)
    return {"written": written, "rejected": rejected}


def verify(name, prefecture, env=None, now=None):
    """確かめて通常の名所として記録したものに「確かめ済み」の印を付ける。→ 付けたか。"""
    rows = load(env)
    hit = False
    for r in rows:
        if r["name"] == name and (not prefecture or r["prefecture"] == prefecture):
            r["verified"] = True
            r["verified_at"] = (now or datetime.now().astimezone()).isoformat()
            hit = True
    if hit:
        _save(rows, env)
    return hit


def _theme_hit(r, question, subjects, c):
    th = r.get("theme") or ""
    q = question or ""
    if th and th in q:
        return True
    words = [w for w, t in c["theme_words"].items() if t == th]
    if any(w in q for w in words):
        return True
    return any(c["subject_themes"].get(s) == th for s in subjects or []) and not any(w in q for w in c["theme_words"])


def _months_text(ms, c):
    if not ms:
        return ""
    names = c["month_names"]
    ms = sorted(set(ms), key=lambda m: m)
    return c["months_text"].format(months="・".join(names[m - 1] for m in ms))


def lines_for(question, subjects=(), text="", prefectures=None, env=None, rows=None, c=None):
    """答えに添える節の行(なければ [])。text: すでに出ている答え(同じ名前は出さない)。"""
    c = c or cfg()
    rows = load(env) if rows is None else rows
    inside = in_range_prefectures()
    out = []
    for r in rows:
        if r.get("verified") or r.get("prefecture") not in inside:
            continue
        if prefectures and r["prefecture"] not in prefectures:
            continue
        if r["name"] in (text or "") or not _theme_hit(r, question, subjects, c):
            continue
        line = c["line"].format(name=r["name"], prefecture=r["prefecture"], months=_months_text(r.get("months"), c))
        if line not in out:
            out.append(line)
        if len(out) >= c["max_items"]:
            break
    return ([c["heading"]] + out) if out else []


def attach(text, question, subjects=(), prefectures=None, env=None):
    """答えの文の、出典の見出しの前(なければ末尾)に節を入れる。"""
    add = lines_for(question, subjects, text, prefectures, env)
    if not add:
        return text
    lines = (text or "").rstrip(NL).split(NL)
    head = cfg()["sources_heading"]
    i = next((k for k, l in enumerate(lines) if l.strip() == head), len(lines))
    j = i
    while j > 0 and not lines[j - 1].strip():
        j -= 1
    rest = lines[i:]
    new = lines[:j] + [""] + add + ([""] + rest if rest else [])
    return NL.join(new).rstrip(NL) + NL
