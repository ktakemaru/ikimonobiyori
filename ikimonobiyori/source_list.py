"""段階62 第1部 5: 利用者向けの情報源の一覧(`ask sources`)。通信しない・書き込まない。
種類別(施設の発信・今の様子を読む公式ページ・行事・観察会・知識・気象庁の平年の目安)に、件数と代表的な名称を出す。
答えに使っているもの(承認済み)だけを数える。確認中(承認待ち)の件数は、利用者が「承認」について聞いたときだけ(with_review)。
文と語は ask/policy.yaml の source_list。内部用語を出さない(ask_verify.internal_word_errors で検査する)。"""
from pathlib import Path

import yaml

from . import facility_events as FE
from . import jma_normals as JN
from . import knowledge as K
from . import visitor_centers as VC

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "data" / "sources"
POLICY = HERE / "data" / "ask" / "policy.yaml"


def policy(path=None):
    return yaml.safe_load(Path(path or POLICY).read_text(encoding="utf-8"))["source_list"]


def _status(x):
    return ((x or {}).get("approval") or {}).get("status")


def _names(rows, key, n):
    out = []
    for r in rows:
        v = r.get(key)
        if v and v not in out:
            out.append(v)
    return out[:n], max(0, len(out) - n)


def counts(env=None, sources_dir=None, centers=None, events=None, cards=None, normals=None):
    """→ {kind: {"used": [行], "review": 件数}}。kind は policy の kinds の順。"""
    sd = Path(sources_dir or SOURCES)
    out = {}
    cs = centers if centers is not None else (VC.load_centers() or [])
    out["centers"] = {"used": [c for c in cs if _status(c) == "approved"], "review": sum(1 for c in cs if _status(c) == "pending"), "key": "name"}
    for subj in ("autumn_leaves", "flowers", "birds", "wintering_birds"):
        p = sd / f"{subj}.yaml"
        rows = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("sources") or [] if p.exists() else []
        out[subj] = {"used": [r for r in rows if _status(r) == "approved" and r.get("kind") != "reference_link"],
                     "review": sum(1 for r in rows if _status(r) == "pending"), "key": "publisher"}
    ev = events if events is not None else FE.load()
    facs = ev.get("facilities") or []
    facs = list(facs.values()) if isinstance(facs, dict) else facs
    out["events"] = {"used": [f for f in facs if _status(f) == "approved"], "review": sum(1 for f in facs if _status(f) == "pending"), "key": "name"}
    cd = cards if cards is not None else K.load_shown(env)
    out["knowledge"] = {"used": list(cd), "review": None, "key": None}
    nd = normals if normals is not None else (JN.load() or {})
    ents = nd.get("entries") or []
    out["normals"] = {"used": ents, "review": None, "key": None, "stations": len({e.get("station") for e in ents})}
    return out


def text(with_review=False, pol=None, **kw):
    """→ 利用者向けの文(行の一覧を改行でつないだもの)。"""
    pol = pol or policy()
    c = counts(**kw)
    n = pol["max_names"]["value"]
    lines = [pol["heading"]]
    for kind in pol["kinds"]:
        x = c[kind]
        label = pol["labels"][kind]
        if kind == "knowledge":
            lines.append(pol["line_count"].format(label=label, n=len(x["used"]), unit=pol["units"][kind]))
            continue
        if kind == "normals":
            lines.append(pol["line_normals"].format(label=label, n=len(x["used"]), stations=x["stations"]))
            continue
        names, rest = _names(x["used"], x["key"], n)
        more = pol["more"].format(n=rest) if rest else ""
        if names:
            lines.append(pol["line_named"].format(label=label, n=len(x["used"]), unit=pol["units"].get(kind, pol["units"]["default"]),
                                                  names=pol["names_sep"].join(names), more=more))
        else:
            lines.append(pol["line_count"].format(label=label, n=0, unit=pol["units"].get(kind, pol["units"]["default"])))
    lines.append(pol["note"])
    if with_review:
        lines += ["", pol["review_heading"]]
        for kind in pol["kinds"]:
            r = c[kind]["review"]
            if r:
                lines.append(pol["review_line"].format(label=pol["labels"][kind], n=r, unit=pol["units"].get(kind, pol["units"]["default"])))
        lines.append(pol["review_note"])
    return "\n".join(lines) + "\n"


def explain(word, pol=None):
    """段階62 第1部 4: 「台帳ってなに?」「承認って?」の説明(利用者の語)。語が含まれる説明を返す。なければ一覧の見出しの文。"""
    pol = pol or policy()
    for k, v in pol["explain"].items():
        if k in (word or ""):
            return v
    return pol["heading"]
