"""段階78 第5部: 足りなかったことの記録(通信しない)。

`ask verify --brief` に合格した答えの中の「確かめられていません」「分かっていません」に当たる文と、資料の「足りないもの」を、
データ置き場の logs/gaps.jsonl に貯める(質問・対象・場所・日時)。`ask gaps` で、対象×場所ごとに回数をまとめて出す。
次のデータ集めは、この一覧から始める。語は data/ask/guide_mode.yaml の gaps。"""
import json
import re

from .paths import data_path

NL = "\n"


def cfg():
    from . import guide_brief as GB
    return GB.cfg()["gaps"]


def path(env=None):
    return data_path(cfg()["file"], env)


def _targets(brief):
    from . import guide_materials as GM
    sps = GM.species_names(brief.get("question") or "")
    if sps:
        return sps
    subj = [s for s in brief.get("subjects") or [] if s]
    return subj or [None]


def _places(brief):
    from . import place_guard as PG
    q = brief.get("question") or ""
    out = list(brief.get("areas") or [])
    if brief.get("region") and brief["region"] not in out:
        out.append(brief["region"])
    try:
        out += [p for p in PG.candidates(q) if p not in out]
    except (KeyError, TypeError, ValueError):
        pass
    return out or [None]


def rows_for(final_text, brief, now):
    """合格した答え + 資料 → 記録の行。"""
    C = cfg()
    words = C["answer_words"]
    rows = []
    body = (final_text or "").split(NL + C["sources_heading"] + NL)[0]
    sents = [s.strip() for line in body.splitlines() for s in re.findall(r"[^。！？!?]+[。！？!?]?", line) if s.strip()]
    texts = [("answer", s) for s in sents if any(w in s for w in words)]
    texts += [("missing", m) for m in brief.get("missing") or [] if not re.search(C["skip_missing_re"], m)]
    if not texts:
        return []
    tg, pl = _targets(brief), _places(brief)
    for kind, t in texts:
        rows.append({"at": now.isoformat(), "question": (brief.get("question") or "")[:80], "brief": brief.get("id"),
                     "targets": tg, "places": pl, "kind": kind, "text": t[: C["max_chars"]]})
    return rows


def append(final_text, brief, now, env=None):
    rows = rows_for(final_text, brief, now)
    if not rows:
        return 0
    p = path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + NL)
    return len(rows)


def summary(env=None):
    """対象×場所ごとの回数(多い順)。→ [{target, place, count, questions, examples}]"""
    p = path(env)
    if not p.exists():
        return []
    agg = {}
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(l)
        except ValueError:
            continue
        for t in r.get("targets") or [None]:
            for pl in r.get("places") or [None]:
                k = (t or "(対象なし)", pl or "(場所なし)")
                a = agg.setdefault(k, {"target": k[0], "place": k[1], "count": 0, "questions": [], "examples": []})
                a["count"] += 1
                if r.get("question") and r["question"] not in a["questions"]:
                    a["questions"].append(r["question"])
                if r.get("text") and r["text"] not in a["examples"] and len(a["examples"]) < 3:
                    a["examples"].append(r["text"])
    return sorted(agg.values(), key=lambda a: (-a["count"], a["target"], a["place"]))


def render(rows):
    if not rows:
        return "足りなかったことの記録はまだありません。" + NL
    L = ["| 対象 | 場所 | 回数 | 質問の例 | 文の例 |", "|---|---|---|---|---|"]
    for a in rows:
        L.append(f"| {a['target']} | {a['place']} | {a['count']} | {' / '.join(a['questions'][:2])} | {' / '.join(a['examples'][:2])} |")
    return NL.join(L) + NL
