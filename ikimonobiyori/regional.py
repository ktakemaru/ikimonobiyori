"""地域を指定した花の答え(段階32。通信しない・書き込まない)。
聞かれた地域(都道府県)を必須の絞り込みにして、確度の段階つきでおすすめを出す。
- 地域: 名所カタログの tags.prefecture で判定する(座標からの推測はしない)。距離(出発地・250 km)は、地域の指定がないときだけ使う。
- 確度: 公式の現況 / 今年のイベント期間つき / 例年の時期のみ(答えでは日本語。記号は出さない)。
- 見頃を過ぎたもの・状態を読み取れなかったものはおすすめに入れない(語彙は方針 data/regional/policy.yaml)。
値・語・文は方針に置き、ここには持たない(CLAUDE.md 規則 1)。既存の答え(answer.py)は変えない。"""
import re
import unicodedata
from urllib.parse import urlparse
from datetime import date, timedelta
from pathlib import Path

import yaml

from . import catalog as catalog_mod
from . import sources as S
from .answer import FRESHNESS_ORDER, URL_RE, day_label, time_label  # noqa: F401  (URL_RE は自己検査で使う)

POLICY_PATH = Path(__file__).resolve().parent / "data" / "regional" / "policy.yaml"
SUBJECT = "flowers"


def load_policy(path=None):
    return yaml.safe_load(Path(path or POLICY_PATH).read_text(encoding="utf-8"))


def _val(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


# ---- 状態の語 → 段階 ----

def bunzaki_stage(raw, rp):
    """「N分咲き」(全角数字・範囲も)→ 段階の id。範囲は小さい方の数で判定(見頃と言い切るのは下限が good_min 以上のときだけ)。読めなければ None。"""
    cfg = rp["bunzaki"]
    nums = []
    for m in re.finditer(cfg["pattern"], unicodedata.normalize("NFKC", raw or "")):
        nums += [int(g) for g in m.groups() if g]
    if not nums or max(nums) > cfg["max"]:
        return None
    return cfg["at_or_above_stage"] if min(nums) >= cfg["good_min"] else cfg["below_stage"]


def is_partial_variety(raw, rp):
    """品種名・区画名だけについて「見頃」と言っている文か(園全体の見頃にしない)。"""
    cfg = rp["partial_variety"]
    s = unicodedata.normalize("NFKC", raw or "")
    if not any(w in s for w in cfg["peak_words"]):
        return False
    return bool(re.search(unicodedata.normalize("NFKC", cfg["quoted_pattern"]), raw or "")) or any(w in s for w in cfg["partial_words"])


def vocab_stage(raw, rp):
    """公式の状態の語 → 段階の id。表にない語は None(推測しない)。完全一致(前後の空白だけ除く)。
    完全一致しなければ「N分咲き」を読む(品種名だけの「見頃」の文は読まない)。"""
    s = (raw or "").strip()
    for st, words in rp["state_vocabulary"]["words"].items():
        if s in words:
            return st
    if is_partial_variety(s, rp):
        return None
    return bunzaki_stage(s, rp)


def row_stage(row, rp):
    """記録の段階(台帳の notation.map)があればそれ、なければ語彙表。→ (段階の id or None, 由来 'ledger'|'vocabulary'|None)。"""
    if row.get("stage"):
        return row["stage"], "ledger"
    st = vocab_stage(row.get("official_state"), rp)
    return st, ("vocabulary" if st else None)


def group_of(stage, rp):
    for g, ids in rp["stage_groups"].items():
        if stage in ids:
            return g
    return None


# ---- 通年の花カレンダー(段階33 1-4): 対象の日から旬の花の種類を選ぶ ----

def seasonal_kinds(entries, dates, rp):
    """承認した名所の flower_windows(種類ごとの例年の時期)のうち、対象の日にかかる種類 → {種類: {start, end, n}}。
    start・end は、その種類の例年の時期の中で最も早い始まり・最も遅い終わり(名所のカタログの値。出典つき)。花の種類の表は持たない(カタログが正本)。"""
    out = {}
    for e in entries:
        for w in e.get("flower_windows") or []:
            if window_hits(w, dates):
                o = out.setdefault(w["kind"], {"start": w["start"], "end": w["end"], "ids": set()})
                o["start"], o["end"] = min(o["start"], w["start"]), max(o["end"], w["end"])
                o["ids"].add(e["id"])
    return {k: {"start": v["start"], "end": v["end"], "n": len(v["ids"])} for k, v in sorted(out.items())}


def few_kinds(kinds, region, entries, rp):
    """旬の種類のうち、指定地域内の登録(tags.flower_kinds に持つ承認した名所)が calendar.min_entries 未満の種類。"""
    need = _val(rp["calendar"]["min_entries"])
    res = []
    for k in kinds:
        n = sum(1 for e in entries if k in ((e.get("tags") or {}).get("flower_kinds") or []) and (region is None or S.in_region(e, region)))
        if n < need:
            res.append(k)
    return res


# ---- 行 → 花の種類 ----

def row_kind(registry, row):
    """要約の行(summarize の rows)の花の種類(台帳の covers の同じ地点・書き方の flower_kind)。なければ None。"""
    src = S.sources_by_id(registry).get(row["source"]) or {}
    for c in src.get("covers") or []:
        if c.get("site", c.get("name")) == row.get("site", row.get("name")) and c.get("label") == row.get("label"):
            return c.get("flower_kind")
    return None


# ---- 例年の時期・今年のイベント ----

def _md_range(year, tw):
    """例年の時期(MM-DD の start・end)→ year 年の (始まり, 終わり)。年をまたぐ(start > end)ときは終わりが翌年。"""
    s = S._md_date(year, tw["start"])
    e = S._md_date(year, tw["end"])
    return (s, e) if s <= e else (s, S._md_date(year + 1, tw["end"]))


def window_hits(tw, dates):
    """例年の時期が対象のどれかの日を含むか(年をまたぐ時期は前年始まりも見る)。"""
    for d in dates:
        for y in (d.year - 1, d.year):
            s, e = _md_range(y, tw)
            if s <= d <= e:
                return True
    return False


def window_start_after(tw, d):
    """d の日以後で最も近い始まりの日。"""
    return S.next_window_start(d, tw)


def host_allowed(url, hosts):
    """URL のホストが承認した通信先(またはそのサブドメイン)か。"""
    from urllib.parse import urlparse
    h = urlparse(url or "").hostname or ""
    return any(h == x or h.endswith("." + x) for x in hosts)


def kind_windows(entry, kind):
    """名所の花の種類ごとの例年の時期(flower_windows)。なければ、種類が 1 つだけの名所は typical_window。"""
    wins = [w for w in entry.get("flower_windows") or [] if w["kind"] == kind]
    if wins:
        return wins
    kinds = (entry.get("tags") or {}).get("flower_kinds") or []
    tw = entry.get("typical_window")
    if tw and len(kinds) == 1 and kinds[0] == kind:
        return [{"kind": kind, **tw}]
    return []


def is_secondary(v):
    """出所の区分が紹介サイトなど(secondary)か(段階34。旧い印 unapproved_host も同じに扱う)。値は捨てずに使い、出所を添える。"""
    return v.get("source_class") == "secondary" or bool(v.get("unapproved_host"))


def event_hits(entry, kind, dates):
    """今年の(確認できた)イベント期間が対象の日を含むもの。前年以前・未確認の期間は使わない(例年の時期の根拠にだけなる)。"""
    out = []
    for ev in entry.get("events") or []:
        if ev["kind"] != kind or not (ev.get("verified") or is_secondary(ev)):    # 紹介サイトなど(secondary)の値も使う(段階34。出所の区分は item に残る)
            continue
        s, e = date.fromisoformat(ev["start"]), date.fromisoformat(ev["end"])
        if ev["year"] != s.year or not any(d.year == ev["year"] and s <= d <= e for d in dates):
            continue
        out.append(ev)
    return out


def record_events(rows, dates):
    """今日読んだ記録の中の、期間が対象の日にかかるイベント(承認した情報源を今日読んだ事実。年つき)。→ [イベントの辞書]"""
    out = []
    for r in rows:
        if r.get("event") and r.get("event_hits_dates"):
            out.append({"name": r.get("label") or "", "start": r["event"][0], "end": r["event"][1], "source_url": r.get("url"), "from_record": True})
    return out


def _mmdd(d):
    return f"{d.month}/{d.day}"


def _mmdd_str(md):
    m, dd = md.split("-")
    return f"{int(m)}/{int(dd)}"


# ---- 1 つの名所・1 つの花の種類の評価 ----

def when_text(row, on, rp, policy):
    """公式の状態の日付の書き方(地点ごとに 1 つ)。現地の日付があれば『○/○時点』、なければ更新日、どちらもなければ『日付の記載なし』。"""
    t = rp["text"]
    if row.get("basis_date"):
        d = date.fromisoformat(row["basis_date"])
        if row.get("freshness_basis") == "updated_date":
            return t["when_updated"].format(md=_mmdd(d))
        return t["when_observed"].format(md=_mmdd(d))
    return t["when_unknown"]


def _best_row(rows):
    """同じ名所・同じ種類の複数行から 1 つ(状態の日付が新しい → 段階が進んでいる)。"""
    return sorted(rows, key=lambda r: (r.get("basis_date") or "", r.get("order") or 0), reverse=True)[0]


def evaluate_kind(entry, kind, rows, dates, rp, policy, on):
    """→ {kind, tier, group, ...} か None(その種類では何も言えない = 例年の時期の外で、今年の情報もない)。
    group: recommend / early / past / unreadable / upcoming。tier: official_status / event_period / typical_only。"""
    usable = [r for r in rows if r["freshness"]["class"] in rp["usable_freshness"] and r.get("official_state") is not None
              and r.get("state_kind") != "no_info"]
    if usable:
        r = _best_row(usable)
        st, origin = row_stage(r, rp)
        g = group_of(st, rp)
        item = {"kind": kind, "tier": "official_status", "row": r, "stage": st, "stage_label": r.get("stage_label"),
                "state": r["official_state"], "when": when_text(r, on, rp, policy), "url": r.get("url")}
        if g is None and is_partial_variety(r["official_state"], rp):      # 品種名だけの「見頃」: 園全体の見頃にしない
            return {**item, "group": "partial"}
        if g is None:                                   # 「ブラウンがメイン」「咲いています」など、段階にできない語
            return {**item, "group": "unreadable"}
        return {**item, "group": g}
    hits = record_events(rows, dates) or event_hits(entry, kind, dates)
    wins = kind_windows(entry, kind)
    in_win = [w for w in wins if window_hits(w, dates)]
    in_win_ok = in_win                                                            # 紹介サイトなど(secondary)の時期も使う(段階34)
    if hits and in_win_ok:
        ev = hits[0]
        return {"kind": kind, "tier": "event_period", "group": "recommend", "event": ev, "window": in_win_ok[0]}
    if in_win:
        return {"kind": kind, "tier": "typical_only", "group": "recommend", "window": in_win[0]}
    within = _val(rp["later"]["within_days"])
    # 来週以降(段階33): 今年のイベント期間(確認できたもの)が対象の最初の日から within 日以内に始まる → 例年の時期が within 日以内に始まる
    evs = [ev for ev in entry.get("events") or [] if ev["kind"] == kind and (ev.get("verified") or is_secondary(ev))
           and ev["year"] == date.fromisoformat(ev["start"]).year and 0 < (date.fromisoformat(ev["start"]) - min(dates)).days <= within]
    if evs:
        return {"kind": kind, "tier": "event_period", "group": "upcoming", "event": sorted(evs, key=lambda x: x["start"])[0]}
    near = [w for w in wins if 0 < (window_start_after(w, min(dates)) - min(dates)).days <= within]
    if near:
        return {"kind": kind, "tier": "typical_only", "group": "upcoming", "window": near[0]}
    return None


def evaluate_site(entry, kinds, rows, dates, rp, policy, on, registry):
    """名所 1 件 → {entry, items: [種類ごとの評価], group, rank}。group は名所の区分(おすすめ > これから > 状態不明 > 見頃過ぎ)。"""
    mine = [k for k in kinds if k in ((entry.get("tags") or {}).get("flower_kinds") or [])]
    items = []
    for k in mine:
        krows = [r for r in rows if row_kind(registry, r) == k]
        it = evaluate_kind(entry, k, krows, dates, rp, policy, on)
        if it:
            items.append(it)
    if not items:
        return None
    for g in ("recommend", "early", "partial", "unreadable", "upcoming", "past"):
        sel = [i for i in items if i["group"] == g]
        if sel:
            rank = min(rp["tiers"][i["tier"]]["rank"] for i in sel)
            return {"entry": entry, "items": sel, "group": g, "rank": rank}
    return None


# ---- 候補の集め方 ----

def _rows_by_site(part, policy):
    out = {}
    for r in part["summary"]["rows"]:
        # 現況のページと、まつり・イベントのページの行(表示が古い可能性・食い違いのないもの)
        if r.get("kind") in ("status_page", "event_page") and not r["stale_display_suspect"] and not r["conflict"] and r.get("site"):
            out.setdefault(r["site"], []).append(r)
    return out


def collect(part, entries, kinds, dates, rp, policy, on):
    rows = _rows_by_site(part, policy)
    out = []
    for e in entries:
        ev = evaluate_site(e, kinds, rows.get(e["id"], []), dates, rp, policy, on, part["registry"])
        if ev:
            out.append(ev)
    return out


def _sort_key(ev):
    r = [i for i in ev["items"] if "row" in i]
    basis = (r[0]["row"].get("basis_date") or "") if r else ""
    return (ev["rank"], tuple(-ord(c) for c in basis), ev["entry"]["name"])


# ---- 文 ----

def city_kind(entry, items):
    city = (entry.get("tags") or {}).get("city")
    kinds = "・".join(dict.fromkeys(i["kind"] for i in items))
    return f"{city}・{kinds}" if city else kinds


def source_url(entry, item=None):
    if item and item.get("url"):
        return item["url"]
    if item and item.get("event"):
        return item["event"]["source_url"]
    if item and item.get("window"):
        return item["window"]["source_url"]
    return (entry.get("official_status_url") or (entry.get("sources") or [{}])[0].get("url"))


def secondary_note(v, rp):
    """紹介サイトなど(secondary)の値に添える出所の一言(段階34)。公式の値には何も付けない。"""
    if not is_secondary(v):
        return ""
    host = v.get("source_host") or urlparse(v.get("source_url") or "").hostname or ""
    return rp["text"]["secondary_note"].format(host=host)


def item_lines(ev, rp, policy, on):
    """おすすめ 1 名所の行(種類ごとに確度が違えば、同じ行に『/』でつなぐ)。"""
    t = rp["text"]
    e = ev["entry"]
    parts = []
    for it in ev["items"]:
        if it["tier"] == "official_status":
            lab = it.get("stage_label")
            key = "item_official_mapped" if lab and lab != it["state"] else "item_official"
            parts.append(t[key].format(name="{name}", city_kind="{ck}", state=it["state"], stage=lab or "", when=it["when"], url=source_url(e, it)))
        elif it["tier"] == "event_period":
            ev_ = it["event"]
            parts.append(t["item_event"].format(name="{name}", city_kind="{ck}", event=ev_["name"], start=_mmdd(date.fromisoformat(ev_["start"])),
                                                end=_mmdd(date.fromisoformat(ev_["end"])), url=source_url(e, it)) + secondary_note(ev_, rp))
        else:
            w = it["window"]
            parts.append(t["item_typical"].format(name="{name}", city_kind="{ck}", start=_mmdd_str(w["start"]), end=_mmdd_str(w["end"]), url=source_url(e, it))
                         + secondary_note(w, rp))
    ck = city_kind(e, ev["items"])
    first = parts[0].replace("{name}", f"**{e['name']}**").replace("{ck}", ck)
    rest = [p.split(" — ", 1)[1] for p in parts[1:]]
    return first + "".join(" ／ " + p for p in rest)


def _simple_line(ev, key, rp, policy, on):
    t = rp["text"]
    e = ev["entry"]
    it = ev["items"][0]
    ck = city_kind(e, ev["items"])
    if "row" in it:
        return t[key].format(name=e["name"], city_kind=ck, state=it["state"], when=it["when"])
    if "event" in it:
        evn = it["event"]
        return t["early_event"].format(name=e["name"], city_kind=ck, event=evn["name"], start=_mmdd(date.fromisoformat(evn["start"])),
                                       end=_mmdd(date.fromisoformat(evn["end"])))
    w = it["window"]
    return t[key].format(name=e["name"], city_kind=ck, start=_mmdd_str(w["start"]))


def attach_ref(line, ev, resolve, stats):
    if not resolve:
        return line
    n = resolve(SUBJECT, ev["entry"]["name"])
    if n is None:
        return line
    stats["attached"] = stats.get("attached", 0) + 1
    return line + f"（参照数 {n}）"


# ---- 答え ----

def forbidden_found(text, rp):
    body = URL_RE.sub(" ", text)
    return [t for t in rp["forbidden_terms"] if t in body]


def compose(*, region, kinds, dates, now, part, nearby_part=None, origin=None, resolve=None, policy=None, seasonal=False):
    """→ 答えの文字列。region は regions.yaml の地域(None なら距離で絞る)。part は answer_parts の flowers の部品(地域・花の種類で絞ったもの)。
    nearby_part は地域を絞らない部品(指定地域内の候補が少ないときの近隣。範囲内だけ使う)。"""
    rp = load_policy()
    policy = policy or S.load_policy()
    t = rp["text"]
    on = now.date()
    entries_all = catalog_mod.approved_entries(part.get("catalog") or {})
    cpol = catalog_mod.load_policy()
    origin = catalog_mod.resolve_origin(cpol, origin)
    rl = cpol["range_limit"]
    stats = {}

    def keep(e, in_region):
        if not S.site_filter(e, region=region if in_region else None, flower_kind=kinds):
            return False
        if region is None:                                   # 地域の指定がないときだけ距離で絞る
            pt = e.get("point")
            rg = catalog_mod.range_from(cpol, pt, origin) if pt else None
            return bool(rg and rg["status"] != "out_of_range")
        return True

    here = [e for e in entries_all if keep(e, True)]
    evs = collect(part, here, kinds, dates, rp, policy, on)
    by = lambda g: sorted([x for x in evs if x["group"] == g], key=_sort_key)
    rec = by("recommend")
    top_max, top_min = _val(policy["recommend"]["top_max"]), _val(policy["recommend"]["top_min"])
    rec_shown = rec[:top_max]
    days = "・".join(day_label(d) for d in dates)
    kinds_txt = "・".join(kinds)
    region_name = region["name"] if region else "近場"
    lines = [t["title"].format(days=days, kinds=kinds_txt, region=region_name), ""]
    if region is None:
        lines += [t["origin_line"].format(origin=origin, max_km=rl["max_km"], edge_km=_val(rl["edge_min_km"])), ""]

    # 近隣(県外): 指定地域内のおすすめが少ないときだけ
    near_shown = []
    if region is not None and nearby_part is not None and len(rec_shown) < top_min:
        others = [e for e in catalog_mod.approved_entries(nearby_part.get("catalog") or {})
                  if S.site_filter(e, flower_kind=kinds) and not S.in_region(e, region) and e.get("point")
                  and catalog_mod.range_from(cpol, e["point"], origin)["status"] != "out_of_range"]
        nev = [x for x in collect(nearby_part, others, kinds, dates, rp, policy, on) if x["group"] == "recommend"]
        near_shown = sorted(nev, key=_sort_key)[:_val(rp["nearby"]["max_items"])]

    # 結論(先頭の 1〜2 文)
    if rec_shown:
        names = "、".join(f"{x['entry']['name']}({rp['tiers'][min(x['items'], key=lambda i: rp['tiers'][i['tier']]['rank'])['tier']]['label']})"
                          for x in rec_shown[:top_min])
        key = "conclusion_some" if region else "conclusion_no_region"
        lines.append(t[key].format(region=region_name, days=days, names=names))
    elif not here:
        lines.append(t["no_sites_in_region"].format(region=region_name, kinds=kinds_txt))
        lines.append(t["add_hint"].format(region=region_name))
    else:
        lines.append(t["conclusion_none"].format(region=region_name, days=days, kinds=kinds_txt))
    if not rec_shown and near_shown:
        lines.append(t["conclusion_none_nearby"])
    lines.append("")

    h = t["headings"]
    if rec_shown:
        lines.append(f"## {h['recommend']}")
        for i, x in enumerate(rec_shown, 1):
            lines.append(f"{i}. " + attach_ref(item_lines(x, rp, policy, on), x, resolve, stats))
        lines.append("")
    # 来週以降に見頃を迎えそうなもの(段階33): 公式の現況が見頃前 → 今年のイベント期間が始まる → 例年の時期が始まる(例年の時期のみ)。最大 later.max_items 件
    later = [("early_official", x) for x in by("early")]
    later += [("early_event" if "event" in x["items"][0] else "early_window", x) for x in by("upcoming")]
    later = later[:_val(rp["later"]["max_items"])]
    if later:
        lines.append(f"## {h['early']}")
        lines += ["- " + _simple_line(x, k if k != "early_event" else "early_event", rp, policy, on) for k, x in later]
        lines.append("")
    unr = by("unreadable")
    if unr:
        lines.append(f"## {h['unreadable']}")
        lines += ["- " + _simple_line(x, "unreadable_official", rp, policy, on) for x in unr]
        lines.append("")
    past = by("past")[:_val(rp["past_peak_max_items"])]
    if past:
        lines.append(f"## {h['past']}")
        lines += ["- " + _simple_line(x, "past_official", rp, policy, on) for x in past]
        lines.append("")
    if near_shown:
        lines.append(f"## {h['nearby']}")
        for i, x in enumerate(near_shown, 1):
            pt = x["entry"]["point"]
            km = catalog_mod.range_from(cpol, pt, origin)["km"]
            lines.append(f"{i}. " + attach_ref(item_lines(x, rp, policy, on), x, resolve, stats)
                         + "。" + t["nearby_note"].format(origin=origin, km=km))
        lines.append("")

    # 公式の現況を読めなかった名所(おすすめ・ほかの欄に出ていない、時期にかかる名所だけ)
    shown_ids = {x["entry"]["id"] for x in evs}
    unread = []
    srcs = S.sources_by_id(part["registry"])
    for e in here:
        if e["id"] in shown_ids:                                       # 答えのどこかに出ている名所は重ねない
            continue
        # 時期にかかる(例年の時期に入る・今年のイベントがかかる・時期の記載がない)名所だけ
        mine = [k for k in kinds if k in ((e.get("tags") or {}).get("flower_kinds") or [])]
        relevant = any(window_hits(w, dates) or event_hits(e, k, dates) for k in mine for w in kind_windows(e, k)) or \
            any(not kind_windows(e, k) for k in mine)
        if not relevant:
            continue
        sids = [s for s in e.get("status_sources") or [] if s in srcs]
        approved = [s for s in sids if S.is_approved(srcs[s]) and srcs[s]["kind"] == "status_page"]
        url = srcs[sids[0]]["url"] if sids else (e.get("official_status_url") or (e.get("sources") or [{}])[0].get("url"))
        ck = city_kind(e, [{"kind": k} for k in mine])
        unread.append("- " + t["unread_approved" if approved else "unread_other"].format(name=e["name"], city_kind=ck, url=url))
    if unread:
        lines += [f"## {h['unread']}"] + list(dict.fromkeys(unread)) + [""]

    # 注意
    notes = []
    if any(i["tier"] == "typical_only" for x in rec_shown + near_shown for i in x["items"]):
        notes.append(t["note_weak"])
    if any(i["tier"] == "event_period" for x in rec_shown + near_shown for i in x["items"]):
        notes.append(t["note_event"])
    if rec_shown or near_shown:
        notes.append(t["note_hours"])
    for x in rec_shown:
        tn = (x["entry"].get("tags") or {}).get("traffic_note")
        if tn:
            notes.append(f"{x['entry']['name']}: {tn}")
    for m in (part.get("care_manners") or []):
        notes.append(m)
    if notes:
        lines += [f"## {h['notes']}"] + [f"- {n}" for n in dict.fromkeys(notes)] + [""]
    if stats.get("attached"):
        lines += [t["reference_legend"], ""]
    few = few_kinds(kinds, region, entries_all, rp) if seasonal else []
    partial = by("partial")
    if partial:        # 品種名だけの「見頃」は、答えの末尾に 1 行だけ
        names = "、".join(t["partial_item"].format(name=x["entry"]["name"], state=x["items"][0]["state"], when=x["items"][0]["when"]) for x in partial)
        lines += [t["partial_line"].format(items=names), ""]
    if few:        # 旬の種類に指定地域内の登録が少ないときの末尾 1 行
        lines += [t["calendar_few"].format(region=region_name, kinds="・".join(few)), ""]
    text = "\n".join(lines).rstrip() + "\n"
    bad = forbidden_found(text, rp)
    if bad:
        raise ValueError(f"答えの本文に出してはいけない語: {bad}")
    return text


def cli(a):
    """sources regional の本体。同じ日に読んだ記録(flowers)だけを使う。通信しない・書き込まない。"""
    import sys
    from . import guide
    from .profiles import load_profiles
    policy, now = S.load_policy(), S.parse_now(a.now)
    dates = [date.fromisoformat(x) for x in a.date] if a.date else S.next_weekend(now)
    region = None
    if a.region:
        region = S.resolve_region(a.region, S.load_regions())
        if region is None:
            print(f"地域の呼び名が data/regions.yaml にない: {a.region}", file=sys.stderr)
            return 2
    kinds = list(a.flower_kind or [])
    seasonal = not kinds
    if seasonal:        # 花の種類の指定がなければ、対象の日から旬の種類を選ぶ(名所のカタログの flower_windows)
        kinds = list(seasonal_kinds(catalog_mod.approved_entries(catalog_mod.load_catalog(SUBJECT)), dates, load_policy()))
        if not kinds:
            print("対象の日が例年の時期にかかる花の種類が名所の一覧にありません。--flower-kind で種類を指定してください", file=sys.stderr)
            return 2
    part = S.answer_parts([SUBJECT], policy=policy, now=now, dates=dates, region=region, flower_kind=kinds)[0]
    near = S.answer_parts([SUBJECT], policy=policy, now=now, dates=dates, region=None, flower_kind=kinds)[0] if region else None
    part["care_manners"] = (load_profiles()[SUBJECT].get("care") or {}).get("manners")
    resolve = guide.reference_resolver(guide.load_policy())
    print(compose(region=region, kinds=kinds, dates=dates, now=now, part=part, nearby_part=near, origin=a.origin, resolve=resolve, policy=policy, seasonal=seasonal), end="")
    return 0
