"""答えの下書きを組み立てる(段階17 フェーズ1。通信しない・書き込まない)。
同じ日に読んだ記録の答えの材料(sources.summarize)と、候補の絞り込み(sources.candidates)→ 使う人向けの Markdown。
- 結論(今回のおすすめ)を先に、根拠 → 注意 → 公式の現況を読めていない名所 の順。同じ名所は 1 か所にだけ出す。
- 内部用語(data/sources/policy.yaml の answer.forbidden_terms)を本文に出さない(テストが確かめる)。
- 日付は地点ごとに 1 つ(「10/22時点」)。言い回し・見出し・件数は方針(policy.yaml の answer・recommend)から読み、コードに持たない。
エージェントは、この下書きを土台にして答える(公式の状態は原文の表記のまま)。"""
import re
from datetime import date

from . import catalog as catalog_mod
from .sources import forecast_day_status, item_disagreements, item_note, last_third_start, primary_for, usable_status_row

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


def _md(d, on):
    x = date.fromisoformat(d)
    return f"{x.month}/{x.day}" if x.year == on.year else f"{x.year}/{x.month}/{x.day}"


def as_of(row, on, policy):
    """日付の書き方(段階20)。本文に「○/○現在」(現地の状態の日付)があれば「10/22時点」、更新日だけなら「公式の更新日は10/22」
    (「時点」と書かない)。両方あって方針の日数より離れているときは両方書く。年が違えば年も書く。年のない日付には方針の注記を添える。
    日付がなければ None。"""
    ans = policy["answer"]
    d, no_year = basis_date(row)
    if not d:
        return None
    suffix = ans["year_unknown_suffix"] if no_year else ""
    if row.get("freshness_basis") == "updated_date" or (row.get("freshness_basis") is None and not row.get("official_observed")):
        return ans["updated_only"].format(md=_md(d, on)) + suffix
    out = f"{_md(d, on)}時点" + suffix
    obs, upd = row.get("official_observed"), row.get("official_updated")
    if obs and upd and abs((date.fromisoformat(upd) - date.fromisoformat(obs)).days) > _val(ans["date_gap_days"]):
        out += "、" + ans["also_updated"].format(md=_md(upd, on)) + (ans["year_unknown_suffix"] if row.get("year_inferred") else "")
    return out


LABEL_PREFIX_RE = re.compile(r"^【[^】]*】")


TOKEN_SPLIT_RE = re.compile(r"[、,・/／\s()（）]+")


def place_name(row, names, multi=frozenset()):
    """名所の名前。同じ名所に地点の書き方が複数ある(戦場ヶ原と小田代原など)ときは、公式の地点の書き方を添えて区別する。
    地点の書き方のうち、名所の名前にすでに入っている語は足さない(「中禅寺湖・いろは坂(…)・中禅寺湖、華厳滝」のように重ねない。段階21)。"""
    n = names.get(row.get("site")) or row.get("name") or row.get("label")
    if row.get("site") in multi and row.get("label"):
        have = {t for t in TOKEN_SPLIT_RE.split(n) if t}
        extra = [t for t in TOKEN_SPLIT_RE.split(LABEL_PREFIX_RE.sub("", row["label"])) if t and t not in have]
        if extra:
            n += "・" + "・".join(extra)
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


def day_statuses(row, dates, policy):
    """対象の日ごとの、見頃予測の扱い(sources.forecast_day_status。見頃予測がなければ全部 None)。"""
    return {d: forecast_day_status(row, d, policy) for d in dates}


def forecast_dropped(row, dates, policy):
    """公式の見頃予測が、対象のどの日にも使えない(すべて予測の時期を過ぎていて、残す条件も満たさない)。おすすめから外す(段階20・21)。"""
    st = day_statuses(row, dates, policy).values()
    return bool(row.get("forecast_window")) and all(s == "drop" for s in st)


def forecast_late(row, dates, policy):
    """予測の時期を過ぎているが残す行(どの日も予測の終わりまでに入らず、少なくとも 1 日は残す条件を満たす)。順位は後ろ(段階21)。"""
    st = list(day_statuses(row, dates, policy).values())
    return bool(row.get("forecast_window")) and "current" not in st and "keep" in st


def day_text(ds):
    """日のリスト → 「11/1(日)」を「・」でつないだもの。"""
    return "・".join(f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})" for d in ds)


def day_note(ds, dates, sentence, policy):
    """日ごとの注意の文。すべての日に当てはまるときは日を省き、一部の日だけなら先頭に日を書く(段階21)。"""
    if len(ds) == len(dates):
        return sentence
    return policy["answer"]["day_prefix"].format(days=day_text(ds)) + sentence


def forecast_notes(row, dates, on, policy):
    """おすすめの行に添える、見頃予測まわりの注意の文のリスト(段階21)。
    ①対象の日が予測の最後の旬に入る日だけ「終盤の可能性があります」 ②予測の時期を過ぎても残した日に、決まった文(状態の段階で二通り)。"""
    ans, notes, fw = policy["answer"], [], row.get("forecast_window")
    if not fw:
        return notes
    end = date.fromisoformat(fw[1])
    start = last_third_start(end, policy)
    late = [d for d in dates if start <= d <= end]
    if late:
        notes.append(day_note(late, dates, ans["forecast_last_third"], policy))
    st = day_statuses(row, dates, policy)
    kept = [d for d in dates if st[d] == "keep"]
    if kept:
        pp = ans["past_forecast"]
        d0, _ = basis_date(row)
        md = _md(d0, on)
        updated_only = row.get("freshness_basis") == "updated_date" or (row.get("freshness_basis") is None and not row.get("official_observed"))
        when = (pp["when_updated"] if updated_only else pp["when_observed"]).format(md=md)
        sentence = pp["sentences"][pp["sentence_by_order"][str(row["order"])]].format(
            forecast=row.get("official_forecast"), when=when, state=row.get("official_state"))
        notes.append(day_note(kept, dates, sentence, policy))
    return notes


def state_text(row, policy=None, with_parts=False):
    """公式の状態。部位ごとに状態が違う地点(official_parts)は、1 つにまとめず、本文の部位ごとの状態を原文のまま(段階20)。
    状態の欄の記号もあるとき(日塩もみじラインの「◎」など)は、with_parts(根拠の欄)のときだけ、本文の部位ごとの状態を添える(段階21)。"""
    parts, st, lb = row.get("official_parts"), row.get("official_state"), row.get("stage_label")
    body = None
    if parts:
        label = policy["answer"]["parts_label" if st is None else "parts_with_state"] if policy else "公式の状態は部位ごと"
        body = f"{label}: " + "、".join(f"{x['part']}「{x['state']}」" for x in parts)
        if st is None:
            return body
    if st is None:
        return None
    text = f"公式「{st}」" + (f"({lb})" if lb and lb != st else "")
    return f"{text}、{body}" if body and with_parts else text


def site_items(p, dates, policy):
    """1 つの対象の部品 → {名所 id: (主項目の行, 補助の項目の行のリスト)}(同じ名所に公式の項目が複数あるとき。段階22 A-1)。
    選び方は提案と同じ sources.primary_for。答えは対象の日が複数でも 1 行なので、最初の対象の日で選ぶ。"""
    groups = {}
    for r in p["summary"]["rows"]:
        if usable_status_row(r) and r.get("site") and r.get("official_state") is not None and r.get("state_kind") != "no_info":
            groups.setdefault(r["site"], []).append(r)
    return {sid: primary_for(rows, min(dates), p.get("registry"), policy) for sid, rows in groups.items()}


def is_secondary(r, items):
    """同じ名所の補助の項目(主項目でない行)か。おすすめ・外した名所の判定には主項目だけを使う。"""
    got = items.get(r.get("site"))
    return got is not None and r is not got[0] and r in got[1]


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
    # 提案(proposals)と同じ判定(段階18)。見頃予測が対象の日より前に終わる地点は外す(段階20。名前は compose が 1 行で書く)
    # 見頃予測が対象のどの日にも使えない地点は外す。予測を過ぎても残す地点(公式の状態が新しい)は、順位を予測がかかる地点より後ろにする(段階21)
    items = {id(p): site_items(p, dates, policy) for p in subject_parts}
    usable = [(p, r) for p in subject_parts for r in p["summary"]["rows"]
              if usable_status_row(r) and not is_secondary(r, items[id(p)]) and not forecast_dropped(r, dates, policy)]
    out, seen = [], set(exclude)

    def add(p, r, reason):
        if place_key(p, r) not in seen and len(out) < top_max:
            seen.add(place_key(p, r))
            out.append((p, r, reason))

    if not forecast_only:
        for p, r in sorted((x for x in usable if x[1]["in_scope"] and (orders is None or x[1]["order"] in orders)),
                           key=lambda x: (forecast_late(x[1], dates, policy), rank.get(x[1]["freshness"]["class"], len(rank)), -(x[1]["order"] or 0))):
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


def left_out(subject_parts, policy, dates, chosen, *, orders=None):
    """おすすめに入れなかった地点の名前(段階20)。→ (見頃予測が対象の日より前に終わるため外した名前, ほかの候補の名前)。
    外した名前は、予測の時期を過ぎたために外した地点(公式の状態が◎・◯・△で、状態が古い・日付が分からないもの。▼・✕は書かない。段階22 A-2)。ほかの候補は、公式の見頃予測が対象の日にかかるのに選ばなかったもの。"""
    keys = {place_key(p, r) for p, r, _ in chosen}
    ended, others = {}, {}
    for p in subject_parts:
        items = site_items(p, dates, policy)
        for r in p["summary"]["rows"]:
            if not usable_status_row(r) or place_key(p, r) in keys or is_secondary(r, items):
                continue
            if forecast_dropped(r, dates, policy):
                # 予測の時期を過ぎたために外した名所だけ(状態が古い・日付が分からないため残せなかったものを含む)。
                # ▼・✕(案B で残す段階でないもの)・段階の分からない書き方は、もともと候補ではないので書かない(段階22 A-2)
                if str(r.get("order")) in policy["answer"]["past_forecast"]["sentence_by_order"]:
                    ended.setdefault(place_key(p, r), (p, r))
            elif r["forecast_hits_dates"] and r.get("official_state") is not None and r.get("state_kind") != "no_info":
                others.setdefault(place_key(p, r), (p, r))
    for k in ended:
        others.pop(k, None)
    return list(ended.values()), list(others.values())


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
    bits = [x for x in (state_text(row, policy, with_parts=True), as_of(row, on, policy)) if x]
    if row.get("official_forecast"):
        bits.append(f"見頃予測「{row['official_forecast']}」")
    if row.get("event"):
        bits.append(f"期間 {row['event'][0]}〜{row['event'][1]}")
    return f"- {place_name(row, names, multi)}: " + "、".join(bits) + (f" — {row['url']}" if row.get("url") else "")


def compose(subject_parts, *, now, dates, policy, scope_note=None, simple_read=None, record_failed=False, early=False, late=False, unread_reasons=None,
            record_gaps=None, origin=None):
    """subject_parts: [{subject, name, summary, candidates, catalog, care?}](対象ごと)→ 答えの下書き(Markdown の文字列)。
    scope_note は扱える範囲が質問の一部だけのときの 1 行(冒頭に出す)。simple_read は要約で読んだ(簡易な読み取り。
    省略すると、使う記録に read_by: summary があるかで決める)、record_failed は読んだ事実を記録できなかったとき(答えの最後に 1 行)。
    early・late は質問の型③(始まり・終わりも含める。おすすめを段階ごとの見出しに分ける)。
    unread_reasons は {情報源 id: 理由}(読む予定の情報源を読まなかった理由。答えの『読めていない名所』に 1 行で添える)。
    record_gaps は読んだ地点の数より今日の記録が少ない情報源 [{source, publisher, read, recorded}](『注意』の先頭に警告。段階20)。
    origin は出発地(省略すると名所カタログの方針の default_origin = 横浜。段階23 の続き)。冒頭に 1 行で書き、名所の代表点から出発地までの
    距離で範囲を判定する: 範囲の外はおすすめに入れず『注意』に、範囲の端はおすすめの理由に添える。"""
    ans = policy["answer"]
    unread_reasons = unread_reasons or {}
    if simple_read is None:
        simple_read = any(r.get("read_by") == "summary" for p in subject_parts for r in p["summary"]["rows"])
    on = now.date()
    names, entries = {}, {}
    for p in subject_parts:
        for e in catalog_mod.approved_entries(p.get("catalog") or {}):
            names[e["id"]], entries[e["id"]] = e["name"], e
    title = "・".join(p["name"] for p in subject_parts)
    cpol = catalog_mod.load_policy()
    origin = catalog_mod.resolve_origin(cpol, origin)
    rl = cpol["range_limit"]
    lines = [f"**{'・'.join(day_label(d) for d in dates)}の{title}**({time_label(now)}に公式ページを読んだ結果)", ""]
    ranges = {}                                                        # (対象, 名所) → 出発地から見た範囲(代表点のある名所だけ)
    for p in subject_parts:
        for r in p["summary"]["rows"]:
            pt = (entries.get(r.get("site")) or {}).get("point")
            if pt and (p["subject"], r["site"]) not in ranges:
                ranges[(p["subject"], r["site"])] = catalog_mod.range_from(cpol, pt, origin)
    far = {k for k, v in ranges.items() if v["status"] == "out_of_range"}
    near_parts = {id(p): {**p, "summary": {**p["summary"], "rows": [r for r in p["summary"]["rows"] if (p["subject"], r.get("site")) not in far]}}
                  for p in subject_parts}
    if scope_note:
        lines += [scope_note, ""]
    if simple_read and ans.get("simple_read_note"):
        lines += [ans["simple_read_note"], ""]
    # 出発地の 1 行(段階23 の続き)。冒頭の注記(扱える範囲・簡易な読み取り)のあと、おすすめの前
    lines += [ans["origin_line"].format(origin=origin, max_km=rl["max_km"], edge_km=_val(rl["edge_min_km"])), ""]

    multi = {p["subject"]: multi_label_sites(p["summary"]["rows"]) for p in subject_parts}
    ahead = (min(dates) - on).days >= _val(ans["ahead_min_days"])           # 来週末など、対象の日が先
    # 対象が複数のときは対象ごとに選ぶ(1 つの対象がおすすめを埋めてしまわないように)
    # 範囲の外(出発地から)の名所はおすすめに入れない(段階23 の続き)。選ぶのは範囲内・範囲の端の行だけ
    per_subject = [(p, [(h, [(p, r, why) for _, r, why in g]) for h, g in recommend_groups([near_parts[id(p)]], policy, dates, early=early, late=late, ahead=ahead)])
                   for p in subject_parts]
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
                bits = [x for x in (state_text(r, policy), as_of(r, on, policy)) if x]
                rg = ranges.get((p_["subject"], r.get("site")))
                if rg and rg["status"] == "edge":
                    reason += "。" + ans["edge_note"].format(origin=origin, km=rg["km"])
                lines.append(f"{i}. **{place_name(r, names, multi[p_['subject']])}** — " + "、".join(bits) + f"。{reason}"
                             + "".join(f"。{n}" for n in forecast_notes(r, dates, on, policy)))
        mine = [c for c in chosen if c[0] is p]
        orders = None if not (early or late) else set(policy["stage_scope"]["default"]) | (set(policy["stage_scope"]["early"]) if early else set()) | (set(policy["stage_scope"]["late"]) if late else set())
        ended, others = left_out([near_parts[id(p)]], policy, dates, mine, orders=orders)
        if ended:
            lines.append(ans["forecast_ended"].format(names="、".join(dict.fromkeys(place_name(r, names, multi[p["subject"]]) for _, r in ended))))
        if others:
            lines.append(ans["other_candidates"].format(names="、".join(dict.fromkeys(place_name(r, names, multi[p["subject"]]) for _, r in others))))
    lines.append("")

    lines.append(f"## {ans['headings']['evidence']}")
    shown = set()
    no_state = {}                                                      # 状態が書かれていない発信(谷川岳など)→ 人が開く URL
    for p in subject_parts:
        for r in p["summary"]["rows"]:
            if r.get("kind") == "status_page" and r.get("official_state") is None and not r.get("event") and not r.get("official_parts"):
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
        for sid, (main, others) in site_items(p, dates, policy).items():     # 主項目と補助の項目で見頃予測の扱いが食い違うとき 1 行(段階22 A-1 ③)
            for o in item_disagreements(main, others, min(dates), policy):
                lines.append(f"- {names.get(sid, sid)}: {item_note(main, o, min(dates), policy)}")
    lines.append("")

    notes = [f"- {ans['record_gap'].format(publisher=g['publisher'], read=g['read'], recorded=g['recorded'])}" for g in record_gaps or []]
    for p in subject_parts:
        for r in p["summary"]["rows"]:
            if r["stale_display_suspect"]:
                notes.append(f"- {place_name(r, names, multi[p['subject']])}: {state_text(r, policy)}、{as_of(r, on, policy)}。{ans['stale_display']} — {r.get('url')}")
            elif r["conflict"]:
                notes.append(f"- {place_name(r, names, multi[p['subject']])}: {ans['conflict']} — {r.get('url')}")
        for (subj, sid) in sorted(k for k in far if k[0] == p["subject"]):
            notes.append(f"- {names.get(sid, sid)}: " + ans["out_of_range_note"].format(origin=origin, km=ranges[(subj, sid)]["km"]))
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
        human, refs, planned, planned_src = {}, {}, {}, {}
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
                    planned_src.setdefault(s_, h["id"])
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
            if sid in planned_src and sid not in human:                # 読む予定だったのに記録がない: 理由を 1 行で(段階20)
                why = unread_reasons.get(planned_src[sid])
                bits.append(ans["unread_reason"].format(reason=why) if why else ans["unread_reason_unknown"])
            if sid in refs:
                bits.append(f"{ans['reference_link']}: {refs[sid]}")
            unread.append(f"- {row['name']}{tag}: " + "、".join(bits))
    if unread:
        lines += [f"## {ans['headings']['unread']}"] + unread + [""]
    if record_failed and ans.get("record_failed_note"):
        lines.append(ans["record_failed_note"])
    return "\n".join(lines).rstrip() + "\n"


def work_memo(policy, *, record_failed=False):
    """作業メモ(答えには含めない。答えの後ろに分けて出す。段階20)。実装・記録の報告はここに書く。なければ None。"""
    ans = policy["answer"]
    notes = [ans["record_failed_note"]] if record_failed and ans.get("record_failed_note") else []
    if not notes:
        return None
    return chr(10).join(["---", f"## {ans['work_memo_heading']}"] + [f"- {n}" for n in notes]) + chr(10)


def forbidden_found(text, policy):
    """答えの本文(URL を除く)に出ている内部用語。→ リスト(空 = 合格)。英字の語は単語の区切りで探す(大文字・小文字は区別しない)。"""
    body = URL_RE.sub(" ", text)
    out = []
    for t in policy["answer"]["forbidden_terms"]:
        pat = rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])" if t.isascii() else re.escape(t)
        if re.search(pat, body, flags=re.IGNORECASE):
            out.append(t)
    return out
