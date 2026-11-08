"""段階55 第2部: ビジターセンター・自然観察施設の情報源の台帳。通信しない・書き込まない。

ビジターセンターは、レンジャーや解説員が常駐し、今見られる花・鳥・紅葉の様子を日付つきで発信していることが多い。
台帳 data/visitor_centers/centers.yaml の施設ごとに、公式サイト・最新の自然情報のページ・更新頻度・形式・更新の季節・規約メモ・範囲を持つ。
- 使うもの: 日付・状態の語（短い語句。30字以内）・種名（1語ずつ。1施設・1日付につき最大10種）・URL・開館時間と休館日。
- 使わないもの: 記事・お便りの文章（保存・転載・要約・言い換えのどれもしない。公式サイトの文章でも同じ）。SNS。第三者サイトに掲載された形。
- 新しく足す施設の情報源は、すべて承認待ち（pending）。承認は本人が行う。承認待ちは答えの材料にしない。
- 「転載禁止の明示あり」の施設は、台帳の規約メモに書き、承認の判断材料にする（短い語・日付・URL だけの利用は、本人の判断）。
- 更新が止まる施設（例: 八島は10月末で終了）は、今シーズン最後の日付を超えたら今年の情報として使わない（年つきの日付で判定。season.py）。
値（上限・語）は data/visitor_centers/policy.yaml。"""
import json
from datetime import date
from urllib.parse import urlparse


from . import yamlcache
from . import season
from .paths import DATA_FILES_DIR, data_path

DIR = DATA_FILES_DIR / "visitor_centers"
POLICY_PATH = DIR / "policy.yaml"
CENTERS_PATH = DIR / "centers.yaml"


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def load_policy(path=None):
    return yamlcache.load((path or POLICY_PATH))


def load_centers(path=None):
    doc = yamlcache.load((path or CENTERS_PATH)) or {}
    return doc.get("centers") or []


def allowed_fields(c, policy=None):
    """施設ごとの『使う項目』。台帳に allowed_fields がなければ全項目（既存の挙動）。"""
    p = policy or load_policy()
    af = c.get("allowed_fields")
    return list(p["fields"]) if af is None else list(af)


def restricted(c, policy=None):
    return set(allowed_fields(c, policy)) != set((policy or load_policy())["fields"])


def _is_url(u):
    p = urlparse(u or "")
    return p.scheme in ("http", "https") and bool(p.hostname)


def validate_center(c, policy=None):
    """施設 1 件の検査。→ エラーの文の配列（空なら通る）。推測で補わない: 不明な項目は null で、必須の項目だけ求める。"""
    p = policy or load_policy()
    errs = []
    for k in p["required"]:
        if not c.get(k):
            errs.append(f"{k} がない")
    if c.get("class") and c["class"] not in p["classes"]:
        errs.append(f"class は {p['classes']} のどれか")
    if c.get("format") and c["format"] not in p["formats"]:
        errs.append(f"format は {p['formats']} のどれか")
    for k in ("site_url", "info_url"):
        if c.get(k) and not _is_url(c[k]):
            errs.append(f"{k} は http(s) の URL")
    ap = c.get("approval") or {}
    if ap.get("status") not in p["approval_statuses"]:
        errs.append(f"approval.status は {p['approval_statuses']} のどれか")
    if ap.get("status") == "approved" and not ap.get("approved_by"):
        errs.append("approved には approved_by（承認した人）が要る")
    t = c.get("terms") or {}
    if "reprint_banned" not in t:
        errs.append("terms.reprint_banned（転載禁止の明示の有無）が要る")
    if t.get("reprint_banned") and "転載禁止の明示あり" not in (t.get("note") or ""):
        errs.append("転載禁止の明示がある施設は terms.note に「転載禁止の明示あり」と書く")
    h = urlparse(c.get("info_url") or c.get("site_url") or "").hostname or ""
    if any(h == b or h.endswith("." + b) for b in p["excluded_hosts"]):
        errs.append("対象外のホスト（SNS・第三者サイト・読まない対象）")
    if c.get("allowed_fields") is not None:
        af = c["allowed_fields"]
        if not isinstance(af, list) or any(x not in p["fields"] for x in af):
            errs.append(f"allowed_fields は {p['fields']} の一部の配列")
        else:
            for k in p["required_fields"]:
                if k not in af:
                    errs.append(f"allowed_fields に {k} が要る（1行に必ず付く項目）")
    se = c.get("season_end")
    if se is not None:
        try:
            date.fromisoformat(str(se.get("last_issue")))
        except (AttributeError, TypeError, ValueError):
            errs.append("season_end.last_issue は年つきの日付（YYYY-MM-DD）")
    return errs


def validate_report(rep, policy=None):
    """施設から読んだ事実 1 件の検査: {center, date, state?, species?, url}。文章は受け付けない。"""
    p = policy or load_policy()
    errs = []
    if not rep.get("center"):
        errs.append("center がない")
    try:
        date.fromisoformat(str(rep.get("date")))
    except (TypeError, ValueError):
        errs.append("date は年つきの日付（YYYY-MM-DD）")
    if not _is_url(rep.get("url")):
        errs.append("url は http(s) の URL")
    mx = _v(p["max_state_chars"])
    st = rep.get("state")
    if st is not None:
        if not isinstance(st, str) or len(st) > mx:
            errs.append(f"state は {mx} 文字以内の語句")
        elif any(m in st for m in p["sentence_marks"]):
            errs.append("state は文章でなく語句だけ")
    sp = rep.get("species")
    if sp is not None:
        n = _v(p["max_species"])
        sm = _v(p["max_species_chars"])
        if not isinstance(sp, list) or len(sp) > n:
            errs.append(f"species は {n} 種までの配列")
        elif not all(isinstance(x, str) and x.strip() and len(x) <= sm and not any(m in x for m in p["sentence_marks"]) for x in sp):
            errs.append(f"species は 1 語ずつ（{sm} 文字以内）")
    for k in rep:
        if k not in p["report_fields"]:
            errs.append(f"{k} は受け付けない項目（文章は保存しない）")
    return errs


def season_open(c, today, sp=None):
    """更新の季節の判定。→ (使える, 理由キー)。
    season_end.last_issue（今シーズン最後の日付。年つき）が、前のシーズンなら今年の情報は未開始（previous_season）、今シーズン内で today より前なら終了（ended）。
    通年の施設（season_end なし）は常に使える。"""
    se = c.get("season_end")
    if not se:
        return True, None
    last = date.fromisoformat(str(se["last_issue"]))
    if last < season.season_start(today, sp):
        return False, "previous_season"
    if today > last:
        return False, "ended"
    return True, None


def usable_center(c, today, policy=None, sp=None):
    """答えの材料に使えるか。→ (使える, 理由キー)。承認待ち・取り消し・規則違反・季節外は使えない。"""
    p = policy or load_policy()
    if validate_center(c, p):
        return False, "invalid"
    if c.get("closed"):                                       # 段階62 第9部: 閉館した施設(宮ヶ瀬ビジターセンター)は使わない
        return False, "closed"
    st = (c.get("approval") or {}).get("status")
    if st != "approved":
        return False, "not_approved" if st == "pending" else "revoked"
    return season_open(c, today, sp)


def usable_report(rep, centers, today, policy=None, sp=None):
    """読んだ事実を答えに使えるか。承認済み・季節内の施設の、規則を満たす事実だけ。→ (使える, 理由キー)"""
    p = policy or load_policy()
    if validate_report(rep, p):
        return False, "invalid_report"
    c = next((x for x in centers if x.get("id") == rep.get("center")), None)
    if c is None:
        return False, "unknown_center"
    ok, why = usable_center(c, today, p, sp)
    if not ok:
        return False, why
    d = date.fromisoformat(str(rep["date"]))
    if d.year != season.season_start(today, sp).year and d < season.season_start(today, sp):
        return False, "previous_season"
    return True, None


def approved_centers(today, centers=None, policy=None):
    centers = load_centers() if centers is None else centers
    return [c for c in centers if usable_center(c, today, policy)[0]]


def pending_centers(centers=None):
    centers = load_centers() if centers is None else centers
    return [c for c in centers if (c.get("approval") or {}).get("status") == "pending"]


def report_line(c, rep, policy=None):
    """答えの 1 行: 「○○ビジターセンター発信、○/○時点: 状態の語（種名・種名）」。短い語・日付・URL だけで作る（文章は使わない）。"""
    p = policy or load_policy()
    d = date.fromisoformat(str(rep["date"]))
    head = p["line"]["head"].format(center=c["name"], month=d.month, day=d.day)
    af = allowed_fields(c, p)
    body = (rep.get("state") or "") if "state" in af else ""                 # 段階56b: 施設ごとの使う項目だけで作る
    if rep.get("species") and "species" in af:
        sep = p["line"]["species_sep"]
        sp = sep.join(rep["species"])
        body = f"{body}{p['line']['species_open']}{sp}{p['line']['species_close']}" if body else sp
    return head + body


def species_kind(name, policy=None):
    """段階62 第5部: 種名 → 区分(鳥・花・木・昆虫など)。分からなければ None(推測しない)。"""
    p = policy or load_policy()
    return next((k for k, names in (p.get("species_kinds") or {}).items() if name in (names or [])), None)


def report_sentences(c, rep, policy=None):
    """段階62 第5部: 答えの文(状態の語と種名を別の文に)。→ [文]。
    「箱根ビジターセンターは、11/6時点で「色づき始め」と発信しています。」「同じ発信に、ジョウビタキ(鳥)の名があります。」
    種名は、区分が分かるものだけ(残りは「ほか○種」)。種名を使わない施設(allowed_fields に species がない)は、種名の文を出さない。"""
    p = policy or load_policy()
    L = p["line"]
    d = date.fromisoformat(str(rep["date"]))
    af = allowed_fields(c, p)
    st = (rep.get("state") or "") if "state" in af else ""
    out = [L["sentence_state"].format(center=c["name"], month=d.month, day=d.day, state=st) if st
           else L["sentence_date_only"].format(center=c["name"], month=d.month, day=d.day)]
    if rep.get("species") and "species" in af:
        known = [(s, species_kind(s, p)) for s in rep["species"]]
        items = [L["species_item"].format(name=s, kind=k) for s, k in known if k]
        rest = sum(1 for _s, k in known if not k)
        if items:
            names = L["species_item_sep"].join(items) + (L["sentence_species_rest"].format(n=rest) if rest else "")
            out.append(L["sentence_species"].format(names=names))
    return out


# ---- 第5部: 読んだ事実の記録と、答えの材料 ----

def decode_html(raw, declared=None, fallbacks=("utf-8", "cp932")):
    """文字コードの宣言がないページのバイト列を、宣言 → UTF-8（厳密）→ CP932 の順で読む。→ (本文, 使った文字コード)。
    読めなければ ValueError（読めたことにしない）。台帳の encoding（例 cp932）は、このコードで読む側が使う。"""
    for enc in ([declared] if declared else []) + list(fallbacks):
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError("文字コードを判定できない")


def reports_path(env=None, policy=None):
    p = policy or load_policy()
    return data_path("visitor_centers/" + p["facts"]["file"], env)


def record_reports(batch, env=None, policy=None, centers=None):
    """読んだ事実（日付・状態の語・種名・URL）を記録に追記する。規則を満たさないものは記録しない。→ {written, duplicates, rejected: [{index, errors}]}
    記録はリポジトリの外（IKIMONOBIYORI_DATA_DIR の下）。承認待ちの施設の事実も記録はできる（答えには使わない）。"""
    p = policy or load_policy()
    centers = load_centers() if centers is None else centers
    ids = {c["id"] for c in centers}
    path = reports_path(env, p)
    have = set()
    if path.exists():
        have = {json.dumps(json.loads(l), sort_keys=True, ensure_ascii=False) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}
    out, rejected, dup = [], [], 0
    for i, rep in enumerate(batch):
        errs = validate_report(rep, p)
        if rep.get("center") not in ids:
            errs.append("center が台帳にない")
        else:
            af = allowed_fields(next(c for c in centers if c["id"] == rep["center"]), p)         # 段階56b: この施設で使わない項目は記録しない
            for k, v in rep.items():
                if v is not None and k in p["field_of"] and p["field_of"][k] not in af:
                    errs.append(f"{k} はこの施設では使わない項目（allowed_fields）")
        if errs:
            rejected.append({"index": i, "errors": errs})
            continue
        row = {k: rep[k] for k in p["report_fields"] if rep.get(k) is not None}
        key = json.dumps(row, sort_keys=True, ensure_ascii=False)
        if key in have:
            dup += 1
            continue
        have.add(key)
        out.append(row)
    if out:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"written": len(out), "duplicates": dup, "rejected": rejected}


def read_reports(env=None, policy=None):
    path = reports_path(env, policy)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def fact_rows(today, subjects=None, env=None, policy=None, centers=None, reports=None, sp=None):
    """答えの材料: 承認済み・季節内の施設の、いちばん新しい事実（max_age_days 以内）を 1 行にする。承認待ちの施設・古い事実・規則違反の事実は出さない。
    承認済みの施設がなければ空の配列（答えには何も出さない）。→ [{center, name, operator, class, date, line, url, hours, closed}]"""
    p = policy or load_policy()
    centers = load_centers() if centers is None else centers
    reports = read_reports(env, p) if reports is None else reports
    mx = _v(p["facts"]["max_age_days"])
    want = set(subjects or p["facts"]["subjects_default"])
    rows = []
    for c in centers:
        if not (set(c.get("subjects") or p["facts"]["subjects_default"]) & want):
            continue
        if not usable_center(c, today, p, sp)[0]:
            continue
        cand = []
        for r in reports:
            if r.get("center") != c["id"] or not usable_report(r, centers, today, p, sp)[0]:
                continue
            age = (today - date.fromisoformat(str(r["date"]))).days
            if 0 <= age <= mx:
                cand.append(r)
        if not cand:
            continue
        r = max(cand, key=lambda x: str(x["date"]))
        af = allowed_fields(c, p)
        hours = c.get("hours") if "hours" in af else None
        row = {"center": c["id"], "name": c["name"], "operator": c["operator"], "class": c["class"], "date": str(r["date"]),
               "line": report_line(c, r, p), "sentences": report_sentences(c, r, p), "state": r.get("state") if "state" in af else None,
               "species": list(r.get("species") or []) if "species" in af else [], "url": r["url"], "hours": hours,
               "hours_line": p["facts"]["hours_label"].format(hours=hours) if hours else None}
        if restricted(c, p):                                              # 段階56b: 使う項目を絞った施設だけ印を付ける（検査器が、除いた項目が答えに出たら落とす）
            row["allowed_fields"] = af
            row["withheld_species"] = list(r.get("species") or []) if "species" not in af else []
            row["withheld_hours"] = c.get("hours") if "hours" not in af else None
        rows.append(row)
    return rows
