"""段階62 第6部: 行事・観察会の索引(統合)。通信しない・書き込まない。
行事の台帳(data/facility_events/events.yaml。承認済みの施設)と、記録済みの行事(data/observations/festivals.yaml のうち、
主催・会場が承認済みの施設(data/visitor_centers/centers.yaml)のもの。年つき・曜日が今年の暦と合うもの)を、
種別(観察会・講座・まつり・展示・イベント)・地域(都県)・日付(年つき)・施設・出典の URL の 1 つの形にまとめる。
答えの行と検査(answer_errors)は facility_events の形をそのまま使う(行事の台帳の形に写す)。値と語は facility_events/policy.yaml の index。"""
import re
from datetime import date

from . import facility_events as FE
from . import festivals as FS
from . import visitor_centers as VC


def _pol(pol=None):
    return (pol or FE.policy())["index"]


def _kind_of(name, ip):
    bare = re.sub(ip["name_note_re"], "", name or "")                 # 「（横浜自然観察の森）」のような会場の注記は種別の判定に使わない
    for kind, words in ip["kind_words"].items():
        if any(w in bare for w in words):
            return kind
    return ip["kind_default"]


def _topics_of(f, center, ip, fp):
    text = " ".join(str(f.get(k) or "") for k in ("name", "venue", "notes")) + " " + (center.get("name") or "")
    tps = [k for k, ws in fp["topic_words"].items() if any(w in text for w in ws)]
    for k, ids in (ip.get("center_topics") or {}).items():
        if center.get("id") in ids and k not in tps:
            tps.append(k)
    return tps or list(ip["topics_default"])


def _center_for(f, centers):
    """記録の主催・会場・発行元の文に、承認済みの施設の名前(か、その前半「・」の前)が含まれれば、その施設。"""
    text = " ".join(str(f.get(k) or "") for k in ("organizer", "venue", "publisher"))
    for c in centers:
        names = {c["name"], c["name"].split("・")[0], c["name"].split("（")[0]}
        if any(n and (n in text or text.startswith(n)) for n in names):
            return c
    return None


def _wd_text(iso, fp):
    return fp["weekdays"][date.fromisoformat(iso).weekday()] + "曜"


def build(today, events=None, festivals_doc=None, centers=None, pol=None):
    """→ facility_events の形の索引 {"facilities": [...], "events": [...]}(承認済みの施設のものだけ。終わった行事は含まない)。"""
    fp = pol or FE.policy()
    ip = _pol(fp)
    doc = events if events is not None else FE.load()
    facs = [f for f in doc.get("facilities") or [] if (f.get("approval") or {}).get("status") == "approved"]
    ids = {f["id"] for f in facs}
    out_e = [dict(e, source="facility_events") for e in doc.get("events") or [] if e.get("facility") in ids
             and date.fromisoformat(e.get("end") or e.get("date")) >= today]
    cs = centers if centers is not None else [c for c in VC.load_centers() if (c.get("approval") or {}).get("status") == "approved"]
    fdoc = festivals_doc if festivals_doc is not None else FS.load()
    for f in fdoc.get("festivals") or []:
        if f.get("organizer_class") != "official":
            continue
        ok, _why = FS.usable(f, today)
        if not ok:
            continue
        end = date.fromisoformat(str(f["end"]))
        if end < today:
            continue
        c = _center_for(f, cs)
        if c is None:
            continue
        fid = "center:" + c["id"]
        if fid not in ids:
            facs.append({"id": fid, "name": c["name"], "prefecture": c.get("prefecture"), "site_url": c.get("site_url"),
                         "approval": {"status": "approved"}, "from_center": True})
            ids.add(fid)
        kind = _kind_of(f["name"], ip)
        e = {"facility": fid, "kind": kind, "title": f["name"], "topics": _topics_of(f, c, ip, fp), "url": f["url"], "source": "festivals",
             "place": f.get("venue")}
        if str(f["start"]) == str(f["end"]):
            e.update({"date": str(f["start"]), "weekday_text": _wd_text(str(f["start"]), fp)})
        else:
            e.update({"start": str(f["start"]), "end": str(f["end"])})
        out_e.append(e)
    return {"facilities": facs, "events": out_e}
