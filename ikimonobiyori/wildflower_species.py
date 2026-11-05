"""種ごとの花期の答え(段階51。通信しない・書き込まない)。
`guide wildflower --species チングルマ [--month N | --date YYYY-MM-DD] [--json]`。山ごとの花暦(wildflower.py)とは別の層。
花期は「例年の目安」で、今年の開花状況とは混ぜない。月の記載がない種(ハクサンコザクラなど)に月を足さない。
2 つの紹介サイトで花期が食い違う種(コマクサ・ハクサンフウロ)は範囲で併記し、「紹介サイトで幅がある」と注記する。"""
import json
import re
from datetime import date

from . import guide, wildflower

SCHEMA_OUT = "ikimono-wildflower-species-answer/1"


def _pol():
    return guide.load_policy()["wildflower"]["species"]


def load():
    wp = guide.load_policy()["wildflower"]
    facts = wildflower._load(wp["facts_file"])
    sp = wildflower._load(wp["species_file"])
    return facts, sp


def names():
    return [s["name"] for s in load()[1]["species"]]


def bloom_text(bloom):
    tens = guide.load_policy()["wildflower"]["tens"]
    names_ = {v: k for k, v in tens.items()}
    (m1, t1), (m2, t2) = wildflower.parse_bloom(bloom, tens)
    prec = any(c in str(bloom) for c in tens)
    a = f"{m1}月" + (names_[t1] if prec else "")
    b = f"{m2}月" + (names_[t2] if prec else "")
    return a if a == b else f"{a}〜{b}"


def _pubs(src_keys, facts):
    p = _pol()
    out = []
    for k in src_keys:
        s = facts["sources"][k]
        pub = re.sub(r"[(（][^)）]*[)）]$", "", s["publisher"])            # 表示は発行元の名前だけ（末尾のかっこの補足を除く）
        tag = p["official_tag"] if s["class"] == "official" else p["secondary_tag"]
        out.append(p["pub_fmt"].format(publisher=pub, tag=tag))
    return p["pub_sep"].join(out)


def _src_rows(src_keys, facts):
    return [{"url": facts["sources"][k]["url"], "publisher": facts["sources"][k]["publisher"], "class": facts["sources"][k]["class"],
             "read_on": facts["sources"][k]["read_on"]} for k in src_keys]


def _where(item):
    p = _pol()
    parts = []
    if item.get("place"):
        parts.append(item["place"])
    e = item.get("elev")
    if e and e[0] is not None and e[1] is None:
        parts.append(p["elev_lo"].format(lo=e[0]))
    return (p["where_sep"].join(parts) + p["where_end"]) if parts else ""


def species_answer(name, month=None, date_=None, today=None):
    """→ {schema, name, month, items[], conflict, in_season(True/False/None), text}。種が一覧になければ ValueError。"""
    facts, data = load()
    p = _pol()
    sp = next((s for s in data["species"] if s["name"] == name), None)
    if sp is None:
        raise ValueError(p["unknown_species"].format(name=name))
    tens = guide.load_policy()["wildflower"]["tens"]
    if date_:
        month = date.fromisoformat(date_).month
    month = month or (today or date.today()).month
    items = sp["items"]
    main = [i for i in items if i.get("bloom") and not i.get("reference_only")]
    refs = [i for i in items if i.get("bloom") and i.get("reference_only")]
    nomo = [i for i in items if not i.get("bloom")]
    lines = []
    conflict = len({bloom_text(i["bloom"]) for i in main}) > 1
    if main and not conflict:
        pubs = _pubs([k for m in main for k in m["src"]], facts)
        lines.append(p["main"].format(name=name, span=bloom_text(main[0]["bloom"]), where=_where(main[0]), pubs=pubs))
    elif conflict:
        parts = [p["conflict_part"].format(span=bloom_text(i["bloom"]), pubs=_pubs(i["src"], facts)) for i in main]
        lines.append(p["main_conflict"].format(name=name, parts=p["parts_sep"].join(parts)))
    for i in refs:
        lines.append(p["reference"].format(place=i.get("place") or "", span=bloom_text(i["bloom"]), pubs=_pubs(i["src"], facts),
                                           note=(i.get("note") or "").rstrip("。")))
    for i in nomo:
        lines.append(p["no_month"].format(name=name, timing=i["timing"], pubs=_pubs(i["src"], facts)))
    months = sorted({m for i in main for m in wildflower._months(i["bloom"], tens)})
    if not months:
        in_season, now = None, p["now_unknown"]
    elif month in months:
        in_season, now = True, p["now_in"].format(month=month)
    else:
        in_season = False
        span = f"{months[0]}月〜{months[-1]}月" if months == list(range(months[0], months[-1] + 1)) else p["parts_sep"].join(f"{m}月" for m in months)
        now = p["now_out"].format(month=month, span=span)
    lines.append(now)
    lines.append(p["elevation_note"])
    return {"schema": SCHEMA_OUT, "name": name, "month": month, "conflict": conflict, "in_season": in_season,
            "items": [{"bloom": i.get("bloom"), "bloom_text": bloom_text(i["bloom"]) if i.get("bloom") else None, "timing": i.get("timing"),
                       "place": i.get("place"), "elevation_m": i.get("elev"), "reference_only": bool(i.get("reference_only")),
                       "sources": _src_rows(i["src"], facts), "note": i.get("note")} for i in items],
            "text": "".join(lines)}


def mountain_notes(site):
    """地点(mNNN)の山の記載。→ {site, name, notes[{text, sources[]}], text}。なければ ValueError。"""
    facts, data = load()
    p = _pol()
    m = next((x for x in data["mountain_notes"] if x["site"] == site), None)
    if m is None:
        raise ValueError(p["unknown_site"].format(site=site))
    notes = [{"text": n["text"], "sources": _src_rows(n.get("src") or [], facts)} for n in m["notes"]]
    lines = []
    for n in m["notes"]:
        pubs = _pubs(n.get("src") or [], facts)
        lines.append(n["text"] + (f"({pubs})" if pubs else "") + p["where_end"])
    return {"site": site, "name": m["name"], "notes": notes, "text": p["notes_title"].format(name=m["name"]) + ": " + "".join(lines)}


def species_cmd(a):
    if getattr(a, "notes", False):
        r = mountain_notes(a.site)
    else:
        r = species_answer(a.species, month=a.month, date_=a.date)
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else r["text"])
    return 0
