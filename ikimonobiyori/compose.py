"""スナップショットの合成(段階6c)。ikimonobiyori は「最新の提案 JSON 1件」しか持たないため、紅葉と野鳥を別々に更新すると片方が消える。
対象ごと(紅葉・野鳥)の更新結果を「部品(component)」として保持し、1つの biyori-proposal/1 に合成する。通信しない。

- 部品: <IKIMONOBIYORI_DATA_DIR>/components/<subject>.json(既定は runtime/ikimonobiyori/components。最新の更新結果。その対象の提案・data_as_of・警告・最後の失敗)
- 合成: TTL(対象ごと、config.yaml の compose.ttl_s)内の部品の提案だけを含める。古い部品は含めず、理由を警告に出す(他の対象は続ける)。
  更新に失敗した対象は、前回の結果が TTL 内なら使い(警告つき)、超えていれば含めない。
- **部品の時刻(generated_at) = 入力データの fetched_at の最も古いもの**(5d)。エンジンを動かした時刻は built_at。鮮度(TTL)の判定も部品の時刻で行うので、キャッシュからの組み直しで古いデータが新しく見えない。
- トップレベルの generated_at は合成した時刻。提案ごとの details.component には部品の識別子(subject)と取得時刻(generated_at・saved_at)だけを持たせる。data_as_of の一覧は部品全体のものをトップレベルに1か所だけ置く(提案ごとに複製しない。5b-3で修正: 紅葉のスナップショットが5.1MBになっていた原因)。
- 窓口(ハブ)は、合成したスナップショットを snapshots/ikimonobiyori/<UTC>.json として、これまでどおり読む。"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__

SUBJECTS = ("autumn_leaves", "birds")
SUBJECT_JA = {"autumn_leaves": "紅葉", "birds": "野鳥"}
SCHEMA = "ikimono-component/1"
JST = timezone(timedelta(hours=9))


def _path(directory, subject):
    return Path(directory) / f"{subject}.json"


def _atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def data_time(data_as_of, fallback):
    """入力データの取得時刻 = data_as_of の fetched_at のうち**最も古いもの**(安全側)。取れなければ fallback(エンジンを動かした時刻)。
    部品の時刻・鮮度の判定には、エンジンを動かした時刻でなくこの時刻を使う(5d: キャッシュからの組み直しで鮮度が新しく見えるのを防ぐ)。"""
    ts = []
    for x in data_as_of or []:
        f = x.get("fetched_at") if isinstance(x, dict) else None
        if isinstance(f, str):
            try:
                ts.append(datetime.fromisoformat(f))
            except ValueError:
                pass
    return min(ts).isoformat(timespec="seconds") if ts else fallback


def normalize_component(c):
    """旧形式の部品(built_at がない = generated_at がエンジンを動かした時刻)を、データの取得時刻に読み替える。"""
    if c is not None and "built_at" not in c:
        c["built_at"] = c.get("generated_at")
        if c.get("generated_at"):
            c["generated_at"] = data_time(c.get("data_as_of"), c["generated_at"])
    return c


def load_component(directory, subject):
    p = _path(directory, subject)
    return normalize_component(json.loads(p.read_text(encoding="utf-8"))) if p.is_file() else None


def update_component(subject, doc, now, *, directory):
    """その対象の更新結果(提案 JSON)を部品として保存する。他の対象の部品には触れない。
    doc の提案のうち、この対象(subject.profile_id == subject)のものだけを部品に入れる。"""
    props = [p for p in doc.get("proposals", []) if (p.get("subject") or {}).get("profile_id") == subject]
    comp = {"schema": SCHEMA, "subject": subject, "saved_at": now.isoformat(timespec="seconds"),
            "generated_at": data_time(doc.get("data_as_of"), doc["generated_at"]), "built_at": doc["generated_at"],
            "status": doc["status"], "status_reason": doc.get("status_reason"),
            "data_as_of": doc.get("data_as_of", []), "proposals": props,
            "warnings": list((doc.get("diagnostics") or {}).get("warnings", [])), "last_failure": None}
    _atomic(_path(directory, subject), comp)
    return comp


def record_failure(subject, reason, now, *, directory):
    """更新に失敗したことを記録する。前回の部品(提案)は消さない(最後の成功を隠さない)。"""
    comp = load_component(directory, subject) or {"schema": SCHEMA, "subject": subject, "saved_at": None, "generated_at": None, "built_at": None, "status": None,
                                                   "status_reason": None, "data_as_of": [], "proposals": [], "warnings": [], "last_failure": None}
    comp["last_failure"] = {"at": now.isoformat(timespec="seconds"), "reason": reason}
    _atomic(_path(directory, subject), comp)
    return comp


def _latest_fetch(asof):
    """通信が終わった時刻(段階6): 入力データの fetched_at のうち最も新しいもの(なければ None)。合成の時刻(generated_at)とは別。"""
    ts = [datetime.fromisoformat(a["fetched_at"]) for a in asof if a.get("fetched_at")]
    return max(ts).isoformat(timespec="seconds") if ts else None


def compose(now, *, directory, ttl_s, request_id="composed"):
    """部品 → 1つの biyori-proposal/1。ttl_s: {subject: 秒}。決定論(now は外から)。"""
    if now.tzinfo is None:
        raise ValueError("now にオフセットが必要")
    proposals, asof, warnings, states = [], [], [], {}
    degraded = []
    for sub in SUBJECTS:
        ja, c = SUBJECT_JA[sub], load_component(directory, sub)
        if c is None or not c.get("generated_at"):
            states[sub] = {"state": "missing"}
            warnings.append(f"{ja}: まだ更新されていないため提案に含めていない(他の対象は続ける)")
            degraded.append("component_missing")
            continue
        age = (now - datetime.fromisoformat(c["generated_at"])).total_seconds()
        st = {"state": "fresh", "generated_at": c["generated_at"], "saved_at": c["saved_at"], "age_h": round(age / 3600.0, 2)}
        lf = c.get("last_failure")
        if age > ttl_s[sub]:
            st["state"] = "stale"
            warnings.append(f"{ja}: {st['age_h']}時間前の結果が有効期間({ttl_s[sub] / 3600:g}時間)を超えたため提案に含めていない(他の対象は続ける)")
            degraded.append("component_stale")
            if lf:
                warnings.append(f"{ja}: 直近の更新にも失敗している({lf['reason']}、{lf['at']})")
            states[sub] = st
            continue
        if lf and (c["saved_at"] is None or lf["at"] > c["saved_at"]):
            st["state"] = "fresh_after_failure"
            warnings.append(f"{ja}: 直近の更新に失敗({lf['reason']}、{lf['at']})。有効期間内の前回の結果({st['age_h']}時間前)を使っている")
            degraded.append("component_update_failed")
        if c.get("status") != "ok":
            degraded.append("component_partial")
        for p in c["proposals"]:
            q = dict(p)
            q["details"] = dict(p.get("details") or {}, component={"subject": sub, "generated_at": c["generated_at"], "saved_at": c["saved_at"]})
            proposals.append(q)
        asof += c["data_as_of"]
        warnings += c["warnings"]
        states[sub] = st
    doc = {
        "schema": "biyori-proposal/1", "request_id": request_id, "agent": {"id": "ikimonobiyori", "version": __version__, "commit": None},
        "status": "ok", "generated_at": now.isoformat(timespec="seconds"), "data_as_of": asof,
        "proposals": sorted(proposals, key=lambda x: x["id"]),
        "diagnostics": {"api_calls": None, "cache_hit": None, "runtime_s": None, "warnings": warnings,
                        "fetch_finished_at": _latest_fetch(asof)},
        "details": {"composed": True, "components": states},
    }
    from . import profiles as _ip
    _, sites_doc = _ip.load_sites()
    line = bird_areas_line(sites_doc)
    if line and "birds" in states and states["birds"].get("state", "").startswith("fresh"):
        doc["details"]["display_lines"] = [line]                    # 窓口が最終文にそのまま出す補足(決定論。LLM は触らない)
    if degraded:
        doc["status"], doc["status_reason"] = "partial", degraded[0]
    if not proposals and not any(s["state"].startswith("fresh") for s in states.values()):
        doc["status"], doc["status_reason"] = "partial", "no_fresh_component"
    return doc


def bird_areas_line(sites_doc):
    """野鳥の『記録が十分な場所』の1行。bird_areas の active から機械的に作る(決定論)。active でない場所があれば『それ以外は記録が少ない』と添える。
    実測値(件数)は書かない(場所固有の実測は sites.yaml の inactive_source と、場所ごとの警告に持つ)。"""
    areas = [a for a in (sites_doc.get("bird_areas") or []) if a.get("status") == "approved"]
    active = [a["name"] for a in areas if a.get("active") is not False]
    sparse = [a for a in areas if a.get("active") is False and a.get("inactive_reason") == "sparse_records"]
    if not active:
        return None
    line = "野鳥は、記録が十分な場所（" + "、".join(active) + "）だけを対象にしています。"
    if sparse:
        line += "それ以外の場所は記録が少ないため対象にしていません。"
    return line


def write_snapshot(doc, snapshots_dir, now, *, keep_last):
    """合成したスナップショットを snapshots/ikimonobiyori/<UTC時刻>.json に原子的に書く。保持数を超えた古いものを消す。"""
    d = Path(snapshots_dir) / "ikimonobiyori"
    dest = d / (now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    _atomic(dest, doc)
    files = sorted(p for p in d.glob("*.json") if not p.name.startswith("."))
    for p in files[: max(0, len(files) - keep_last)]:
        p.unlink()
    return dest
