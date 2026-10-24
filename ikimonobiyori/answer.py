"""答えの下書きを組み立てる(段階17 フェーズ1。通信しない・書き込まない)。
同じ日に読んだ記録の答えの材料(sources.summarize)と、候補の絞り込み(sources.candidates)→ 使う人向けの Markdown。
- 結論(今回のおすすめ)を先に、根拠 → 注意 → 公式の現況を読めていない名所 の順。同じ名所は 1 か所にだけ出す。
- 内部用語(data/sources/policy.yaml の answer.forbidden_terms)を本文に出さない(テストが確かめる)。
- 日付は地点ごとに 1 つ(「10/22時点」)。言い回し・見出し・件数は方針(policy.yaml の answer・recommend)から読み、コードに持たない。
エージェントは、この下書きを土台にして答える(公式の状態は原文の表記のまま)。"""
import re
from datetime import date

from . import catalog as catalog_mod
from .sources import usable_status_row

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


def forecast_distance(row, dates):
    """公式の見頃予測の時期の真ん中と、対象の日の真ん中との日数(近いほど小さい)。見頃予測がなければ None。"""
    fw = row.get("forecast_window")
    if not fw:
        return None
    s_, e_ = date.fromisoformat(fw[0]), date.fromisoformat(fw[1])
    lo, hi = min(dates), max(dates)
    return abs(((s_ - lo) + (e_ - hi)).days) / 2                    # (予測の真ん中 − 対象の真ん中)の絶対値


def forecast_past(row, dates):
    """公式の見頃予測が、対象の最初の日より前に終わっている(見ごろを過ぎている見込み)。"""
    fw = row.get("forecast_window")
    return bool(fw) and fw[1] < min(dates).isoformat()


def state_text(row):
    st, lb = row.get("official_state"), row.get("stage_label")
    if st is None:
        return None
    return f"公式「{st}」" + (f"({lb})" if lb and lb != st else "")


def place_key(p, r):
    return (p["subject"], r.get("site") or r.get("name") or r.get("label"))


def pick(subject_parts, policy, dates, *, orders=None, forecast=True, fallback=True, forecast_only=False, exclude=frozenset()):
    """おすすめを選ぶ。→ [(対象の部品, 行, 理由)]。
    順: 範囲に入る段階(orders を渡すとその共通の順番だけ。既定は見ごろ・最盛)で新しいもの(公式の見頃予測が対象の日より前に終わるものは後ろへ)
    → 公式の見頃予測が対象の日にかかるもの(forecast) → (足りなければ)段階のない公式の最新の記載(fallback)。
    forecast_only は見頃予測が対象の日にかかるものだけ(対象の日が先のときの見出し)。今の段階に関わらず(「まだ」でも)、
    予測の時期の真ん中が対象の日に近い順(段階17b、ユーザーの指示)。情報なしの書き方の地点は入れない。
    表示が古い可能性・食い違いのある地点は選ばない。同じ名所は 1 回だけ(exclude はほかの見出しで選んだ名所)。"""
    ans, top_max = policy["answer"], _val(policy["recommend"]["top_max"])
    rank = {c: i for i, c in enumerate(FRESHNESS_ORDER)}
    usable = [(p, r) for p in subject_parts for r in p["summary"]["rows"] if usable_status_row(r)]   # 提案(proposals)と同じ判定(段階18)
    out, seen = [], set(exclude)

    def add(p, r, reason):
        if place_key(p, r) not in seen and len(out) < top_max:
            seen.add(place_key(p, r))
            out.append((p, r, reason))

    if not forecast_only:
        for p, r in sorted((x for x in usable if x[1]["in_scope"] and (orders is None or x[1]["order"] in orders)),
                           key=lambda x: (forecast_past(x[1], dates), rank.get(x[1]["freshness"]["class"], len(rank)), -(x[1]["order"] or 0))):
            add(p, r, ans["reasons"]["in_scope"].format(stage=r["stage_label"]))
    # 公式の見頃予測で選ぶのは、公式の状態が段階の分かる語のとき(「現在、情報がありません」のような情報なしの書き方では選ばない)
    if forecast_only:
        for p, r in sorted((x for x in usable if x[1]["forecast_hits_dates"] and x[1].get("official_state") is not None
                            and x[1].get("state_kind") != "no_info"),
                           key=lambda x: forecast_distance(x[1], dates)):
            add(p, r, ans["reasons"]["forecast"].format(forecast=r["official_forecast"]))
    elif forecast:
        for p, r in sorted((x for x in usable if x[1]["forecast_hits_dates"] and x[1]["stage"] is not None and not x[1]["in_scope"]),
                           key=lambda x: (x[1]["order"] is None, x[1]["order"] in set(policy["stage_scope"]["late"]), -(x[1]["order"] or 0))):
            add(p, r, ans["reasons"]["forecast"].format(forecast=r["official_forecast"]))
    if fallback and len(out) < _val(policy["recommend"]["top_min"]):
        for p, r in usable:
            if r["stage"] is None and r.get("official_state") and r.get("state_kind") != "no_info" and r["freshness"]["class"] in FRESHNESS_ORDER[:2]:
                add(p, r, ans["reasons"]["latest"])
    return out


def recommend_groups(parts, policy, dates, *, early, late, ahead):
    """1 つの対象のおすすめを見出しごとに。→ [(見出し or None, [(部品, 行, 理由)])]。
    early・late のときは段階ごとの見出し(見ごろ〜最盛/始まり/終わりかけ)。ahead(対象の日が先)のときは、
    公式の見頃予測が対象の日にかかる地点の見出しを別に足す(今は「まだ」でも)。"""
    sh, sc = policy["answer"]["stage_headings"], policy["stage_scope"]
    groups, taken = [], set()
    if early or late:
        for key, on in (("default", True), ("early", early), ("late", late)):
            if on:
                g = pick(parts, policy, dates, orders=set(sc[key]), forecast=False, fallback=False, exclude=taken)
                groups.append((sh[key], g))
                taken |= {place_key(p, r) for p, r, _ in g}
        if not any(g for _, g in groups):
            groups.append((None, pick(parts, policy, dates, orders=set(sc["default"]), exclude=taken)))
    else:
        g = pick(parts, policy, dates, forecast=not ahead)
        groups.append((sh["default"] if ahead else None, g))
        taken |= {place_key(p, r) for p, r, _ in g}
    if ahead:
        ga = pick(parts, policy, dates, forecast_only=True, fallback=False, exclude=taken)
        if ga:
            groups.append((sh["ahead"], ga))
        elif not (early or late):
            groups = [(None, g) for _, g in groups]          # 見頃予測の見出しがなければ「見ごろ〜最盛」の小見出しも出さない
    return [(h, g) for h, g in groups if g or h is None]


def _line(row, on, names, policy, multi):
    bits = [x for x in (state_text(row), as_of(row, on, policy)) if x]
    if row.get("official_forecast"):
        bits.append(f"見頃予測「{row['official_forecast']}」")
    if row.get("event"):
        bits.append(f"期間 {row['event'][0]}〜{row['event'][1]}")
    return f"- {place_name(row, names, multi)}: " + "、".join(bits) + (f" — {row['url']}" if row.get("url") else "")


def compose(subject_parts, *, now, dates, policy, scope_note=None, simple_read=None, record_failed=False, early=False, late=False):
    """subject_parts: [{subject, name, summary, candidates, catalog, care?}](対象ごと)→ 答えの下書き(Markdown の文字列)。
    scope_note は扱える範囲が質問の一部だけのときの 1 行(冒頭に出す)。simple_read は要約で読んだ(簡易な読み取り。
    省略すると、使う記録に read_by: summary があるかで決める)、record_failed は読んだ事実を記録できなかったとき(答えの最後に 1 行)。
    early・late は質問の型③(始まり・終わりも含める。おすすめを段階ごとの見出しに分ける)。"""
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
    ahead = (min(dates) - on).days >= _val(ans["ahead_min_days"])           # 来週末など、対象の日が先
    # 対象が複数のときは対象ごとに選ぶ(1 つの対象がおすすめを埋めてしまわないように)
    per_subject = [(p, recommend_groups([p], policy, dates, early=early, late=late, ahead=ahead)) for p in subject_parts]
    chosen = [c for _, gs in per_subject for _, g in gs for c in g]
    lines.append(f"## {ans['headings']['recommend']}")
    if not chosen:
        lines.append(ans["none_found"])
    multi_subject = len(subject_parts) > 1
    for p, gs in per_subject:
        if multi_subject:
            lines.append(f"### {p['name']}")
            if not any(g for _, g in gs):
                lines.append(ans["none_found"])
                continue
        for head, g in gs:
            if not g:
                continue
            if head:
                lines.append(f"**{head}**" if multi_subject else f"### {head}")
            for i, (p_, r, reason) in enumerate(g, 1):
                bits = [x for x in (state_text(r), as_of(r, on, policy)) if x]
                lines.append(f"{i}. **{place_name(r, names, multi[p_['subject']])}** — " + "、".join(bits) + f"。{reason}")
    lines.append("")

    lines.append(f"## {ans['headings']['evidence']}")
    shown = set()
    no_state = {}                                                      # 状態が書かれていない発信(谷川岳など)→ 人が開く URL
    for p in subject_parts:
        for r in p["summary"]["rows"]:
            if r.get("kind") == "status_page" and r.get("official_state") is None and not r.get("event"):
                no_state.setdefault((p["subject"], r.get("site") or r.get("name")), (place_name(r, names), r.get("url")))
        rows = [r for r in p["summary"]["rows"] if not r["stale_display_suspect"] and not r["conflict"]
                and (p["subject"], r.get("site") or r.get("name")) not in no_state]
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
        for u in p["candidates"].get("upcoming_windows") or []:
            d = date.fromisoformat(u["next_start"])
            if (d - min(dates)).days <= _val(ans["upcoming_within_days"]):     # 近いうちに例年の時期が来る名所だけ
                notes.append(f"- {u['name']}: " + ans["upcoming"].format(month=d.month, day=d.day))
        for m in p.get("care") or []:
            notes.append(f"- {m}")
    if notes:
        lines += [f"## {ans['headings']['notes']}"] + list(dict.fromkeys(notes)) + [""]

    unread = []
    for p in subject_parts:
        c = p["candidates"]
        human, refs, planned = {}, {}, {}
        for h in c.get("human_urls") or []:
            for s_ in h["sites"]:
                human.setdefault(s_, h["url"])
        for h in c.get("reference_links") or []:
            for s_ in h["sites"]:
                refs.setdefault(s_, h["url"])
        for h in c.get("read_plan") or []:
            if h["kind"] == "status_page":
                for s_ in h["sites"]:
                    planned.setdefault(s_, h["url"])
        tag = f"({p['name']})" if len(subject_parts) > 1 else ""
        for (subj, key), (nm, url) in no_state.items():
            if subj == p["subject"] and (subj, key) not in shown:
                shown.add((subj, key))
                unread.append(f"- {nm}{tag}: {ans['no_state']}、{ans['human_url']}: {url}")
        for row in c.get("sites") or []:
            sid = row["site"]
            if (p["subject"], sid) in shown:
                continue
            # 承認待ち・現況の情報源なし、または読む予定だったが今日の記録がない(読めなかった)名所
            if sid not in human and sid not in (c.get("no_status_source") or []) and sid not in planned:
                continue
            shown.add((p["subject"], sid))
            bits = []
            tw = row.get("typical_window")
            if tw:
                bits.append(ans["typical_window"].format(start=tw["start"].replace("-", "/"), end=tw["end"].replace("-", "/")))
            url = human.get(sid) or (planned.get(sid) if sid not in (c.get("no_status_source") or []) else None)
            bits.append(f"{ans['human_url']}: {url}" if url else ans["unread_no_url"])
            if sid in refs:
                bits.append(f"{ans['reference_link']}: {refs[sid]}")
            unread.append(f"- {row['name']}{tag}: " + "、".join(bits))
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
