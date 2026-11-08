"""段階65 第3部: 承認の一覧(docs/sources-approval.md)を、台帳の実際の approval から作る(手で二重に管理しない)。

承認の状態の正本は台帳(施設 visitor_centers/centers.yaml・情報源 sources/*.yaml・行事 facility_events/events.yaml・
名所カタログ catalog/*.yaml)だけ。手で書いた推奨と規約メモは data/approval_notes.yaml に項目の id で置き、ここで引き継ぐ。
通信しない・書き込まない(出力は文字列。ファイルへの保存は呼び出し側)。承認の記入はしない。"""
import re
from pathlib import Path

from . import yamlcache
from .paths import DATA_FILES_DIR

NOTES = DATA_FILES_DIR / "approval_notes.yaml"
NL = "\n"


def _load(p):
    return yamlcache.load(Path(p)) or {}


def _status_of(ap):
    if isinstance(ap, dict):
        return ap.get("status") or "pending", ap.get("approved_by"), ap.get("approved_on") or ap.get("approved_at")
    return "pending", None, None


HIDDEN_HOSTS = ("yamakei-online",)                        # 段階55 第8部: 一覧に URL を書かない発行元


def _url(u):
    return "台帳に記載（山と溪谷オンラインの記事。ここには書かない）" if u and any(h in u for h in HIDDEN_HOSTS) else u


def _cell(x):
    s = "" if x is None else str(x)
    return s.replace("|", "／").replace(NL, " ").strip()


def collect(data_dir=None):
    """台帳の項目 → 行の一覧 {ledger, id, name, status, by, on, url, kind, reason, extra}。"""
    d = Path(data_dir or DATA_FILES_DIR)
    rows = []
    for c in (_load(d / "visitor_centers" / "centers.yaml").get("centers") or []):
        st, by, on = _status_of(c.get("approval"))
        rows.append({"ledger": "centers", "file": "visitor_centers/centers.yaml", "id": c["id"], "name": c.get("name"), "status": st, "by": by, "on": on,
                     "url": c.get("info_url") or c.get("site_url"), "kind": c.get("format"), "reason": (c.get("approval") or {}).get("reason"),
                     "operator": c.get("operator"), "last_update": c.get("last_update"), "terms": c.get("terms") or {}})
    for p in sorted((d / "sources").glob("**/*.yaml")):
        doc = _load(p)
        if not isinstance(doc, dict):
            continue
        rel = p.relative_to(d / "sources").as_posix()
        for s in doc.get("sources") or []:
            st, by, on = _status_of(s.get("approval"))
            rows.append({"ledger": "sources", "file": rel, "id": s["id"], "name": s.get("publisher"), "status": st, "by": by, "on": on,
                         "url": s.get("url"), "kind": s.get("kind"), "publisher_kind": s.get("publisher_kind"),
                         "reason": (s.get("approval") or {}).get("reason"), "readable": s.get("readable") or {}, "terms": s.get("terms") or {}})
    ev = _load(d / "facility_events" / "events.yaml")
    for f in ev.get("facilities") or []:
        st, by, on = _status_of(f.get("approval"))
        rows.append({"ledger": "events", "file": "facility_events/events.yaml", "id": f["id"], "name": f.get("name"), "status": st, "by": by, "on": on,
                     "url": f.get("events_url") or f.get("site_url"), "kind": None, "reason": (f.get("approval") or {}).get("reason"), "terms": f.get("terms") or {}})
    for p in sorted((d / "catalog").glob("*.yaml")):
        doc = _load(p)
        for e in (doc.get("entries") or []) if isinstance(doc, dict) else []:
            st = e.get("status") or "candidate"
            rows.append({"ledger": "catalog", "file": "catalog/" + p.name, "id": e["id"], "name": e.get("name"),
                         "status": {"candidate": "pending"}.get(st, st), "by": e.get("approved_by"), "on": e.get("approved_at"),
                         "url": next((s.get("url") for s in e.get("sources") or [] if s.get("url")), None), "kind": None, "reason": e.get("note"),
                         "entry": e})
    return rows


def _num(rows, ledger, status):
    return sum(1 for r in rows if r["ledger"] == ledger and r["status"] == status)


def render(rows=None, notes=None):
    """承認の一覧(Markdown)。同じ台帳と notes なら同じ文字列(決定論)。"""
    rows = collect() if rows is None else rows
    nt = _load(NOTES) if notes is None else notes
    cn, sn = nt.get("centers") or {}, nt.get("sources") or {}
    sec_notes = nt.get("catalog_secondary") or {}
    out = ["# 情報源の承認の一覧（台帳から作る。段階65 第3部）", "",
           "この一覧は、台帳の実際の承認（`approval`）から `python -X utf8 -m ikimonobiyori.ask sources --approval` が作る（手で書き換えない。"
           "推奨と規約メモは `ikimonobiyori/data/approval_notes.yaml` に項目の id で置く）。",
           "**承認は本人が行う**（Claude Code が記入するのは、本人がチャットの指示文で対象（id）と条件を明示したものだけ。`docs/operations.md` §2-0）。"
           "この表の推奨は参考で、承認とはみなさない。", ""]
    names = {"centers": "施設（visitor_centers/centers.yaml）", "sources": "現況の情報源（sources/）", "events": "行事・展示（facility_events/events.yaml）",
             "catalog": "名所カタログ（catalog/）"}
    out += ["## 集計", "", "| 台帳 | 承認済み | 承認待ち | 取り消し・引退 |", "|---|---|---|---|"]
    for lg in ("centers", "sources", "events", "catalog"):
        out.append(f"| {names[lg]} | {_num(rows, lg, 'approved')} | {_num(rows, lg, 'pending')} | "
                   f"{sum(1 for r in rows if r['ledger'] == lg and r['status'] not in ('approved', 'pending'))} |")
    out += ["", nt.get("criteria", "").rstrip(), ""]
    # ---- 承認待ち ----
    out += ["## 1. 承認待ち", ""]
    pc = [r for r in rows if r["ledger"] == "centers" and r["status"] == "pending"]
    out += [f"### 1-A. ビジターセンター・自然観察施設（承認待ち {len(pc)}件）",
            "承認の手順: 台帳の `approval.status` を `approved` にし、`approved_by` に承認した人を書く（docs/operations.md §2-2）。", "",
            "| 施設 | 運営主体 | 最新情報のページ | 更新頻度 | 形式 | 規約メモ（転載禁止の明示の有無） | 範囲内 | 承認した場合に使う内容 | 推奨と理由 |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in pc:
        n = cn.get(r["id"]) or {}
        out.append("| " + " | ".join(_cell(x) for x in [r["name"], n.get("operator") or r.get("operator"), n.get("page") or _url(r.get("url")), n.get("frequency"),
                                                         n.get("form") or r.get("kind"), n.get("terms") or (r.get("terms") or {}).get("note"), n.get("in_range"),
                                                         n.get("use"), n.get("recommendation") or "**保留**: 推奨の記入がない"]) + " |")
    ps = [r for r in rows if r["ledger"] == "sources" and r["status"] == "pending"]
    out += ["", f"### 1-B. 現況の情報源の台帳（承認待ち {len(ps)}件）",
            "承認の有無にかかわらず読んで記録してよい（段階34。区分は『公式ではない』などで出る）。承認は、台帳上の『公式の現況』扱いにするかどうかの判断。", "",
            "| 台帳 | 情報源 | 発行元の種類 | 最新情報のページ | 形式 | 読めた状態（確認日） | 推奨と理由 |", "|---|---|---|---|---|---|---|"]
    for r in ps:
        n = sn.get(r["id"]) or {}
        rd = r.get("readable") or {}
        read = n.get("read_state") or (f"{rd.get('status')}（{rd.get('checked_on')}）" if rd else "未確認")
        rec = n.get("recommendation") or ("**保留**: " + _cell(r.get("reason") or "推奨の記入がない"))
        out.append("| " + " | ".join(_cell(x) for x in [r["file"], f"{r['name']}（{r['id']}）", r.get("publisher_kind"), _url(r.get("url")), r.get("kind"), read, rec]) + " |")
    pe = [r for r in rows if r["ledger"] == "events" and r["status"] == "pending"]
    if pe:
        out += ["", f"### 1-C. 行事・展示の台帳（承認待ち {len(pe)}件）", "", "| 施設（id） | 行事のページ | 規約メモ | 理由 |", "|---|---|---|---|"]
        for r in pe:
            out.append("| " + " | ".join(_cell(x) for x in [f"{r['name']}（{r['id']}）", _url(r.get("url")), (r.get("terms") or {}).get("note"), r.get("reason")]) + " |")
    pk = [r for r in rows if r["ledger"] == "catalog" and r["status"] == "pending"]
    out += ["", f"### 1-D. 名所カタログの候補（status: candidate。{len(pk)}件）", "", "| 台帳 | 名所（id） | 出典 |", "|---|---|---|"]
    for r in pk:
        out.append("| " + " | ".join(_cell(x) for x in [r["file"], f"{r['name']}（{r['id']}）", _url(r.get("url"))]) + " |")
    # ---- 承認済み ----
    out += ["", "## 2. 承認済み", "", "承認した人: user = 本人、claude_code_provisional = 段階の指示で Claude Code が仮に承認したもの（本人の見直しの対象）。", ""]
    ac = [r for r in rows if r["ledger"] == "centers" and r["status"] == "approved"]
    out += [f"### 2-A. ビジターセンター・自然観察施設（承認済み {len(ac)}件）", "",
            "| 施設 | id | 承認した人・日 | 最新情報のページ | 規約メモ | 承認前の推奨 |", "|---|---|---|---|---|---|"]
    for r in ac:
        n = cn.get(r["id"]) or {}
        out.append("| " + " | ".join(_cell(x) for x in [r["name"], r["id"], f"{r['by']}（{r['on'] or '日付なし'}）", n.get("page") or _url(r.get("url")),
                                                         n.get("terms") or (r.get("terms") or {}).get("note"), n.get("recommendation") or "（承認前の推奨なし）"]) + " |")
    asr = [r for r in rows if r["ledger"] == "sources" and r["status"] == "approved"]
    out += ["", f"### 2-B. 現況の情報源の台帳（承認済み {len(asr)}件）", "", "| 台帳 | 情報源（id） | 承認した人・日 | 最新情報のページ |", "|---|---|---|---|"]
    for r in asr:
        out.append("| " + " | ".join(_cell(x) for x in [r["file"], f"{r['name']}（{r['id']}）", f"{r['by']}（{r['on'] or '日付なし'}）", _url(r.get("url"))]) + " |")
    ae = [r for r in rows if r["ledger"] == "events" and r["status"] == "approved"]
    out += ["", f"### 2-C. 行事・展示の台帳（承認済み {len(ae)}件）", "", "| 施設（id） | 承認した人・日 | 行事のページ |", "|---|---|---|"]
    for r in ae:
        out.append("| " + " | ".join(_cell(x) for x in [f"{r['name']}（{r['id']}）", f"{r['by']}（{r['on'] or '日付なし'}）", _url(r.get("url"))]) + " |")
    ak = [r for r in rows if r["ledger"] == "catalog" and r["status"] == "approved"]
    au = [r for r in ak if r["by"] == "user"]
    out += ["", f"### 2-D. 名所カタログ（承認済み {len(ak)}件。うち本人の承認 {len(au)}件を列挙）", "",
            "| 台帳 | 名所（id） | 承認した日 |", "|---|---|---|"]
    for r in au:
        out.append("| " + " | ".join(_cell(x) for x in [r["file"], f"{r['name']}（{r['id']}）", r["on"] or "日付なし"]) + " |")
    other = {}
    for r in ak:
        if r["by"] != "user":
            other.setdefault((r["file"], r["by"] or "記入なし（段階19 以前の承認）"), []).append(r)
    for (f, by), rs in sorted(other.items()):
        out.append(f"- {f}: 承認した人 {by} が {len(rs)}件")
    rv = [r for r in rows if r["status"] not in ("approved", "pending")]
    out += ["", f"## 3. 取り消し・引退（{len(rv)}件）", "", "| 台帳 | 項目（id） | 状態 |", "|---|---|---|"]
    for r in rv:
        out.append("| " + " | ".join(_cell(x) for x in [r["file"], f"{r['name']}（{r['id']}）", r["status"]]) + " |")
    # ---- 紹介サイト由来の名所の出典(第3部 3) ----
    sc = [r for r in rows if r["ledger"] == "catalog" and r["id"] in sec_notes]
    out += ["", "## 4. 紹介サイトなど由来の値を持つ名所の出典（段階64 第6部・段階65 第2部で足したもの）", "",
            "承認の記入はしていない。『区分』は、値の出典が施設・自治体自身の公式ページか、紹介サイトか。", "",
            "| 名所（id） | 出典 | 区分 | 規約の要約 |", "|---|---|---|---|"]
    for r in sc:
        for s in sec_notes[r["id"]]:
            out.append("| " + " | ".join(_cell(x) for x in [f"{r['name']}（{r['id']}）", s.get("url"), s.get("class"), s.get("terms")]) + " |")
    if nt.get("showakinen"):
        out += ["", "## 5. 国営昭和記念公園（showakinen-flower-information・showakinen-flower-information-flowers）の規約", "", nt["showakinen"].rstrip()]
    if nt.get("terms_stage67"):                                            # 段階67 第5部: 規約を読めていなかった出典(承認の記入はしない)
        out += ["", "## 6. 知識カード・名所の出典の規約の要約（段階67 第5部。2026-11-09 に読んだ。承認の記入はしていない）", "",
                "| 出典 | 読んだページ | 要約(2行以内) | 本人の判断 |", "|---|---|---|---|"]
        for x in nt["terms_stage67"]:
            out.append("| " + " | ".join(_cell(v) for v in [x.get("name"), x.get("url"), x.get("summary"), x.get("judgement") or "—"]) + " |")
    out += ["", nt.get("takao_mitake", "").rstrip(), "", nt.get("yamakei", "").rstrip(), ""]
    return NL.join(re.sub(r"[ \t]+$", "", l) for l in out)
