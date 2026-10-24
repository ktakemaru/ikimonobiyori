"""答えの下書きを組み立てる(段階17 フェーズ1。通信しない・書き込まない)。
同じ日に読んだ記録の答えの材料(sources.summarize)と、候補の絞り込み(sources.candidates)→ 使う人向けの Markdown。
- 結論(今回のおすすめ)を先に、根拠 → 注意 → 公式の現況を読めていない名所 の順。同じ名所は 1 か所にだけ出す。
- 内部用語(data/sources/policy.yaml の answer.forbidden_terms)を本文に出さない(テストが確かめる)。
- 日付は地点ごとに 1 つ(「10/22時点」)。言い回し・見出し・件数は方針(policy.yaml の answer・recommend)から読み、コードに持たない。
エージェントは、この下書きを土台にして答える(公式の状態は原文の表記のまま)。"""
import re
from datetime import date

from . import catalog as catalog_mod

URL_RE = re.compile(r"https?://\S+")
WEEKDAYS = "月火水木金土日"
# おすすめの並び: 新しさの区分の順(新しいものから)
FRESHNESS_ORDER = ("fresh", "somewhat_old", "year_unknown", "old", "unknown")


def _val(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def day_label(d):
    return f"{d.year}年{d.month}月{d.day}日({WEEKDAYS[d.weekday()]})"


def time_label(t):
    off = t.strftime("%z")
    return f"{t.year}年{t.month}月{t.day}日 {t:%H:%M}({off[:3]}:{off[3:]})"


def basis_date(row):
    """新しさの基準にした日付(現地の状態の日付があればそれ、なければ最終更新日)。→ (日付の文字列 or None, 年がないか)。"""
    if "basis_date" in row:
        return row["basis_date"], bool(row.get("basis_year_unknown"))
    return row.get("official_updated"), bool(row.get("year_inferred"))


def as_of(row, on, policy):
    """「10/22時点」。年が違えば年も書く。年のない日付には方針の注記を添える。日付がなければ None。"""
    d, no_year = basis_date(row)
    if not d:
        return None
    x = date.fromisoformat(d)
    s = f"{x.month}/{x.day}時点" if x.year == on.year else f"{x.year}/{x.month}/{x.day}時点"
    return s + (policy["answer"]["year_unknown_suffix"] if no_year else "")


LABEL_PREFIX_RE = re.compile(r"^【[^】]*】")


def place_name(row, names, multi=frozenset()):
    """名所の名前。同じ名所に地点の書き方が複数ある(戦場ヶ原と小田代原など)ときは、公式の地点の書き方を添えて区別する。"""
    n = names.get(row.get("site")) or row.get("name") or row.get("label")
    if row.get("site") in multi and row.get("label"):
        n += f"・{LABEL_PREFIX_RE.sub('', row['label'])}"
    return n


def multi_label_sites(rows):
    seen, multi = set(), set()
    for r in rows:
        if r.get("site"):
            (multi if r["site"] in seen else seen).add(r["site"])
    return frozenset(multi)


def forecast_past(row, dates):
    """公式の見頃予測が、対象の最初の日より前に終わっている(見ごろを過ぎている見込み)。"""
    fw = row.get("forecast_window")
    return bool(fw) and fw[1] < min(dates).isoformat()


def state_text(row):
    st, lb = row.get("official_state"), row.get("stage_label")
    if st is None:
        return None
    return f"公式「{st}」" + (f"({lb})" if lb and lb != st else "")


def pick(subject_parts, policy, dates):
    """おすすめを選ぶ。→ [(対象の部品, 行, 理由)]。
    順: 範囲に入る段階(既定は見ごろ・最盛)で新しいもの(公式の見頃予測が対象の日より前に終わるものは後ろへ)
    → 公式の見頃予測が対象の日にかかるもの → (足りなければ)段階のない公式の最新の記載。
    表示が古い可能性・食い違いのある地点は選ばない。同じ名所は 1 回だけ。"""
    ans, top_max = policy["answer"], _val(policy["recommend"]["top_max"])
    rank = {c: i for i, c in enumerate(FRESHNESS_ORDER)}
    usable = [(p, r) for p in subject_parts for r in p["summary"]["rows"]
              if r.get("kind") == "status_page" and not r["stale_display_suspect"] and not r["conflict"]]
    out, seen = [], set()

    def add(p, r, reason):
        k = (p["subject"], r.get("site") or r.get("name") or r.get("label"))
        if k not in seen and len(out) < top_max:
            seen.add(k)
            out.append((p, r, reason))

    for p, r in sorted((x for x in usable if x[1]["in_scope"]),
                       key=lambda x: (forecast_past(x[1], dates), rank.get(x[1]["freshness"]["class"], len(rank)), -(x[1]["order"] or 0))):
        add(p, r, ans["reasons"]["in_scope"].format(stage=r["stage_label"]))
    for p, r in sorted((x for x in usable if x[1]["forecast_hits_dates"] and not x[1]["in_scope"]),
                       key=lambda x: -(x[1]["order"] or 0)):
        add(p, r, ans["reasons"]["forecast"].format(forecast=r["official_forecast"]))
    if len(out) < _val(policy["recommend"]["top_min"]):
        for p, r in usable:
            if r["stage"] is None and r.get("official_state") and r["freshness"]["class"] in FRESHNESS_ORDER[:2]:
                add(p, r, ans["reasons"]["latest"])
    return out


def _line(row, on, names, policy, multi):
    bits = [x for x in (state_text(row), as_of(row, on, policy)) if x]
    if row.get("official_forecast"):
        bits.append(f"見頃予測「{row['official_forecast']}」")
    if row.get("event"):
        bits.append(f"期間 {row['event'][0]}〜{row['event'][1]}")
    return f"- {place_name(row, names, multi)}: " + "、".join(bits) + (f" — {row['url']}" if row.get("url") else "")


def compose(subject_parts, *, now, dates, policy, scope_note=None, simple_read=None, record_failed=False):
    """subject_parts: [{subject, name, summary, candidates, catalog, care?}](対象ごと)→ 答えの下書き(Markdown の文字列)。
    scope_note は扱える範囲が質問の一部だけのときの 1 行(冒頭に出す)。simple_read は要約で読んだ(簡易な読み取り。
    省略すると、使う記録に read_by: summary があるかで決める)、record_failed は読んだ事実を記録できなかったとき(答えの最後に 1 行)。"""
    ans = policy["answer"]
    if simple_read is None:
        simple_read = any(r.get("read_by") == "summary" for p in subject_parts for r in p["summary"]["rows"])
    on = now.date()
    names, entries = {}, {}
    for p in subject_parts:
        for e in catalog_mod.approved_entries(p.get("catalog") or {}):
            names[e["id"]], entries[e["id"]] = e["name"], e
    title = "・".join(p["name"] for p in subject_parts)
    lines = [f"**{'・'.join(day_label(d) for d in dates)}の{title}**({time_label(now)}に公式ページを読んだ結果)", ""]
    if scope_note:
        lines += [scope_note, ""]
    if simple_read and ans.get("simple_read_note"):
        lines += [ans["simple_read_note"], ""]

    multi = {p["subject"]: multi_label_sites(p["summary"]["rows"]) for p in subject_parts}
    # 対象が複数のときは対象ごとに選ぶ(1 つの対象がおすすめを埋めてしまわないように)
    groups = [(p, pick([p], policy, dates)) for p in subject_parts] if len(subject_parts) > 1 else [(None, pick(subject_parts, policy, dates))]
    chosen = [c for _, g in groups for c in g]
    lines.append(f"## {ans['headings']['recommend']}")
    if not chosen:
        lines.append(ans["none_found"])
    for head, g in groups:
        if head is not None:
            lines.append(f"### {head['name']}")
            if not g:
                lines.append(ans["none_found"])
        for i, (p, r, reason) in enumerate(g, 1):
            bits = [x for x in (state_text(r), as_of(r, on, policy)) if x]
            lines.append(f"{i}. **{place_name(r, names, multi[p['subject']])}** — " + "、".join(bits) + f"。{reason}")
    lines.append("")

    lines.append(f"## {ans['headings']['evidence']}")
    shown = set()
    for p in subject_parts:
        rows = [r for r in p["summary"]["rows"] if not r["stale_display_suspect"] and not r["conflict"]]
        if not rows:
            continue
        if len(subject_parts) > 1:
            lines.append(f"### {p['name']}")
        late = set(policy["stage_scope"]["late"])          # 根拠の並び: 範囲に入るもの → 始まり・前 → 終わり(段階のないものは最後)
        for r in sorted(rows, key=lambda r: (not r["in_scope"], r["order"] is None, r["order"] in late, -(r["order"] or 0),
                                             place_name(r, names, multi[p["subject"]]))):
            lines.append(_line(r, on, names, policy, multi[p["subject"]]))
            shown.add((p["subject"], r.get("site")))
    lines.append("")

    notes = []
    for p in subject_parts:
        for r in p["summary"]["rows"]:
            if r["stale_display_suspect"]:
                notes.append(f"- {place_name(r, names, multi[p['subject']])}: {state_text(r)}、{as_of(r, on, policy)}。{ans['stale_display']} — {r.get('url')}")
            elif r["conflict"]:
                notes.append(f"- {place_name(r, names, multi[p['subject']])}: {ans['conflict']} — {r.get('url')}")
        for p_, r, _ in chosen:
            if p_ is p:
                tn = (entries.get(r.get("site")) or {}).get("tags", {}).get("traffic_note")
                if tn:
                    notes.append(f"- {place_name(r, names)}: {tn}")
        tide_sites = [r.get("site") for _, r, _ in [c for c in chosen if c[0] is p]] +                      [r.get("site") for r in p["summary"]["rows"]] + [row["site"] for row in (p["candidates"].get("sites") or [])]
        for sid in dict.fromkeys(x for x in tide_sites if x):
            for u in (entries.get(sid) or {}).get("related_urls") or []:
                if u["kind"] == "tide_table":
                    notes.append(f"- {names[sid]}: {ans['tide_note']} — {u['url']}")
        for m in p.get("care") or []:
            notes.append(f"- {m}")
    if notes:
        lines += [f"## {ans['headings']['notes']}"] + list(dict.fromkeys(notes)) + [""]

    unread = []
    for p in subject_parts:
        c = p["candidates"]
        human = {}
        for h in c.get("human_urls") or []:
            for s in h["sites"]:
                human.setdefault(s, h["url"])
        for row in c.get("sites") or []:
            if (p["subject"], row["site"]) in shown:
                continue
            if row["site"] not in human and row["site"] not in (c.get("no_status_source") or []):
                continue
            shown.add((p["subject"], row["site"]))
            bits = []
            tw = row.get("typical_window")
            if tw:
                bits.append(ans["typical_window"].format(start=tw["start"].replace("-", "/"), end=tw["end"].replace("-", "/")))
            bits.append(f"{ans['human_url']}: {human[row['site']]}" if row["site"] in human else ans["unread_no_url"])
            unread.append(f"- {row['name']}" + (f"({p['name']})" if len(subject_parts) > 1 else "") + ": " + "、".join(bits))
    if unread:
        lines += [f"## {ans['headings']['unread']}"] + unread + [""]
    if record_failed and ans.get("record_failed_note"):
        lines.append(ans["record_failed_note"])
    return "\n".join(lines).rstrip() + "\n"


def forbidden_found(text, policy):
    """答えの本文(URL を除く)に出ている内部用語。→ リスト(空 = 合格)。英字の語は単語の区切りで探す(大文字・小文字は区別しない)。"""
    body = URL_RE.sub(" ", text)
    out = []
    for t in policy["answer"]["forbidden_terms"]:
        pat = rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])" if t.isascii() else re.escape(t)
        if re.search(pat, body, flags=re.IGNORECASE):
            out.append(t)
    return out
