"""段階55 第2部: ビジターセンター・自然観察施設の情報源の台帳。通信しない・書き込まない。

ビジターセンターは、レンジャーや解説員が常駐し、今見られる花・鳥・紅葉の様子を日付つきで発信していることが多い。
台帳 data/visitor_centers/centers.yaml の施設ごとに、公式サイト・最新の自然情報のページ・更新頻度・形式・更新の季節・規約メモ・範囲を持つ。
- 使うもの: 日付・状態の語（短い語句。30字以内）・種名（1語ずつ。1施設・1日付につき最大10種）・URL・開館時間と休館日。
- 使わないもの: 記事・お便りの文章（保存・転載・要約・言い換えのどれもしない。公式サイトの文章でも同じ）。SNS。第三者サイトに掲載された形。
- 新しく足す施設の情報源は、すべて承認待ち（pending）。承認は本人が行う。承認待ちは答えの材料にしない。
- 「転載禁止の明示あり」の施設は、台帳の規約メモに書き、承認の判断材料にする（短い語・日付・URL だけの利用は、本人の判断）。
- 更新が止まる施設（例: 八島は10月末で終了）は、今シーズン最後の日付を超えたら今年の情報として使わない（年つきの日付で判定。season.py）。
値（上限・語）は data/visitor_centers/policy.yaml。"""
import re
from datetime import date
from urllib.parse import urlparse

import yaml

from . import season
from .paths import DATA_FILES_DIR

DIR = DATA_FILES_DIR / "visitor_centers"
POLICY_PATH = DIR / "policy.yaml"
CENTERS_PATH = DIR / "centers.yaml"


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def load_policy(path=None):
    return yaml.safe_load((path or POLICY_PATH).read_text(encoding="utf-8"))


def load_centers(path=None):
    doc = yaml.safe_load((path or CENTERS_PATH).read_text(encoding="utf-8")) or {}
    return doc.get("centers") or []


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
    body = rep.get("state") or ""
    if rep.get("species"):
        sep = p["line"]["species_sep"]
        sp = sep.join(rep["species"])
        body = f"{body}{p['line']['species_open']}{sp}{p['line']['species_close']}" if body else sp
    return head + body
