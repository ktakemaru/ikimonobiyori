"""現地の情報の答えを biyori-proposal/1 で出す(段階18。docs/proposal-mapping.md)。通信しない・LLM を使わない・書き込まない。
読むのはエージェント(読んだ事実は記録に残す)。ここは、同じ日に読んだ記録・名所カタログ・情報源の一覧から、決まった規則で提案を組み立てるだけ。
- 材料は answer と同じ(sources.answer_parts → summarize の行)。使える行の判定も answer と同じ(sources.usable_status_row)。
- go は出さない(上限 maybe)。新しさは band を変えず、known_limits と evidence に書く。
- 値(段階の対応・日数・文言)は data/sources/policy.yaml の proposals から読み、コードに持たない。
- 同じ入力・同じ記録・同じ now なら同じ出力(並びは表示の都合の固定の規則。価値の判断はしない)。"""
from datetime import date

from . import __version__
from . import catalog as catalog_mod
from .engine import AGENT_ID, SCHEMA, day_window, round_coord
from . import guide
from .sources import forecast_day_status, item_disagreements, item_note, primary_for, usable_status_row, val

ID_KIND = "status"             # 提案の id の 2 つ目。気温の推定(engine)の id と区別する(段階18 の確認、ユーザー 2026-10-24)
YEAR_FREE_DATE = "{m}/{d}"       # 年のない公式の日付の書き方(原文の形。答えの「○/○時点」と同じ)


def _date(s):
    return date.fromisoformat(s) if s else None


def official_date_text(value, year_known):
    """公式の日付 → 原文の形の文字列。年のある日付は YYYY-MM-DD、年のない(補った)日付は M/D。"""
    if not value:
        return None
    if year_known:
        return value
    d = date.fromisoformat(value)
    return YEAR_FREE_DATE.format(m=d.month, d=d.day)


def updated_year_known(row):
    return not row.get("year_inferred")


def observed_year_known(row):
    return row.get("observed_year_inferred") is not True


def forecast_hits(row, d):
    fw = row.get("forecast_window")
    return bool(fw) and fw[0] <= d.isoformat() <= fw[1]


def decide(row, d, *, policy, on, scope):
    """1 行・1 日 → (band, known_limits に足す鍵のリスト)。docs/proposal-mapping.md の「band の決め方」。"""
    pp = policy["proposals"]
    order, keys = row.get("order"), []
    beyond = (d - on).days > val(policy["horizon_days"])
    hit = forecast_hits(row, d)
    fw = row.get("forecast_window")
    if beyond:
        keys.append("beyond_horizon")
        band = "maybe" if hit else "no"
    elif forecast_day_status(row, d, policy) == "drop":     # 見頃予測がその日より前に終わり、残す条件も満たさない: answer がおすすめから外すのと同じ(段階20・21)
        band = "no"
    elif order is not None and (order in scope or order in val(pp["maybe_orders"])):
        band = "maybe"
    elif hit:
        band = "maybe"
    elif order is None and row["freshness"]["class"] in pp["no_stage_maybe_freshness"]:
        band = "maybe"
    else:
        band = "no"
    if order is None:
        keys.append("no_stage")
    if band == "maybe" and forecast_day_status(row, d, policy) == "keep":
        keys.append("forecast_past")                          # 予測の時期は過ぎているが公式の状態が新しいので残した(段階21)
    return band, keys


def row_limits(row, *, policy, on):
    """行の新しさ・年・読み方からの known_limits の文(決まった文だけ)。"""
    pp, kl = policy["proposals"], policy["proposals"]["known_limits"]
    out = []
    age = row["freshness"].get("age_days")
    read_age = (on - date.fromisoformat(row["read_at"][:10])).days
    if (age is not None and age >= val(pp["old_official_days"])) or read_age >= val(pp["old_read_days"]):
        out.append(kl["old"])
    if row.get("basis_year_unknown"):
        out.append(kl["year_unknown"])
    if row.get("official_observed") and row.get("observed_year_inferred") == policy["freshness"]["observed_year_from_update_mark"]:
        out.append(kl["year_inferred"])
    if row.get("read_by") == "summary":
        out.append(policy["answer"]["simple_read_note"])
    return out


def too_old(row, dates, policy):
    """公式の日付(新しさの基準の日付)が対象の最初の日より方針の日数以上前 → その日数。使える記録なら None。"""
    b = _date(row.get("basis_date"))
    if b is None:
        return None
    days = (min(dates) - b).days
    return days if days >= val(policy["proposals"]["exclude_official_days_before_target"]) else None


def observation(row, source_name):
    """details.observations の 1 件(行の事実と、補った年の印)。"""
    return {"source": row["source"], "publisher": source_name, "label": row.get("label"), "official_state": row.get("official_state"),
            "stage": row.get("stage"), "stage_label": row.get("stage_label"), "order": row.get("order"),
            "official_updated": official_date_text(row.get("official_updated"), updated_year_known(row)),
            "official_observed": official_date_text(row.get("official_observed"), observed_year_known(row)),
            "updated_year_inferred": bool(row.get("official_updated")) and bool(row.get("year_inferred")),
            "observed_year_inferred": (row.get("observed_year_inferred") or False) if row.get("official_observed") else False,
            "freshness_basis": row.get("freshness_basis"), "freshness": row["freshness"]["label"], "freshness_class": row["freshness"]["class"],
            "freshness_age_days": row["freshness"].get("age_days"), "read_by": row.get("read_by"), "read_at": row["read_at"],
            "official_forecast": row.get("official_forecast"), "forecast_window": row.get("forecast_window"), "url": row.get("url")}


def row_evidence(row, d, source_name, policy):
    """行の evidence(照合が要る値: 公式の状態の原文・公式の日付の原文・新しさ・読み方。見頃予測があればその原文と、かかるか)。"""
    pp = policy["proposals"]
    where = f"{source_name}({row['label']})" if row.get("label") else source_name
    up_known = updated_year_known(row)
    official = {"source": where, "source_type": "official_notice", "url": row.get("url"),
                "last_updated": row.get("official_updated") if up_known else None}
    derived = {"source": pp["evidence_source"], "source_type": "model_derived", "url": None, "last_updated": None}
    ev = [{"metric": "official_state", "value": row.get("official_state"), "unit": None, "valid_time": None, **official}]
    if row.get("official_updated"):
        ev.append({"metric": "official_updated", "value": official_date_text(row["official_updated"], up_known), "unit": None, "valid_time": None, **official})
    if row.get("official_observed"):
        ev.append({"metric": "official_observed", "value": official_date_text(row["official_observed"], observed_year_known(row)),
                   "unit": None, "valid_time": None, **official})
    if row.get("official_forecast"):
        ev.append({"metric": "official_forecast", "value": row["official_forecast"], "unit": None, "valid_time": None, **official})
        ev.append({"metric": "forecast_hits_target_date", "value": forecast_hits(row, d), "unit": None, "valid_time": None, **derived})
    ev.append({"metric": "freshness", "value": row["freshness"]["label"], "unit": None, "valid_time": None, **derived})
    ev.append({"metric": "read_by", "value": pp["read_by_labels"].get(row.get("read_by")), "unit": None, "valid_time": None, **derived})
    return ev


def place_of(entry, profile, catalog_policy):
    """名所カタログの件 → place。位置の粗さはカタログとプロファイルの粗い方で、座標もその粗さに丸める。"""
    care = profile.get("care") or {}
    precs = [p for p in (entry.get("location_precision"), care.get("location_precision")) if p]
    prec = max(precs, key=lambda p: catalog_mod.coarseness(catalog_policy, p)) if precs else None
    pt = entry["point"]
    pl = {"name": entry["name"], "lat": round_coord(pt["lat"], prec), "lon": round_coord(pt["lon"], prec),
          "elevation_m": pt.get("elevation_m"), "region": (entry.get("tags") or {}).get("prefecture"),
          "location_precision": prec, "site_ref": f"{AGENT_ID}:{entry['id']}"}
    if entry.get("sources"):
        pl["sources"] = entry["sources"]
    return pl


def care_of(entry, profile):
    """マナー(プロファイル → カタログ)と交通の注意(カタログの tags.traffic_note)。重複なし。"""
    care = profile.get("care") or {}
    items = list(care.get("manners") or []) + list(entry.get("manners") or [])
    tn = (entry.get("tags") or {}).get("traffic_note")
    if tn:
        items.append(tn)
    return {"manners": list(dict.fromkeys(items)), "do_not_disclose_exact_location": bool(care.get("do_not_disclose_exact_location"))}


def _sort_key(band, row, policy):
    rank = {c: i for i, c in enumerate(policy["proposals"]["freshness_order"])}
    order = row.get("order")
    return (band != "maybe", order is None, -(order if order is not None else 0), rank.get(row["freshness"]["class"], len(rank)))


def subject_proposals(part, profile, *, policy, catalog_policy, now, dates, scope, warn):
    """1 つの対象の部品(sources.answer_parts の 1 件)→ 提案のリスト。提案にならない名所は warn(重複は呼び出し側が除く)に書く。"""
    pp, wt = policy["proposals"], policy["proposals"]["warnings"]
    on = now.date()
    entries = {e["id"]: e for e in catalog_mod.approved_entries(part["catalog"] or {})}
    names = {k: e["name"] for k, e in entries.items()}
    publishers = {s["id"]: s.get("publisher") for s in (part.get("registry") or {}).get("sources") or []}
    by_site, outside, no_state = {}, [], []
    for r in part["summary"]["rows"]:
        if r.get("kind") != "status_page":
            continue
        nm = names.get(r.get("site")) or r.get("name") or r.get("label")
        if r["stale_display_suspect"]:
            warn(r.get("site") or nm, wt["stale_display"].format(name=nm))
            continue
        if r["conflict"]:
            warn(r.get("site") or nm, wt["conflict"].format(name=nm))
            continue
        if not usable_status_row(r) or r.get("official_state") is None or r.get("state_kind") == "no_info":
            no_state.append((r.get("site") or nm, wt["no_state"].format(name=nm, url=r.get("url"))))
            continue
        if r.get("site") not in entries:
            outside.append(nm)
            continue
        days = too_old(r, dates, policy)
        if days is not None:
            warn(r["site"], wt["too_old"].format(name=nm, date=official_date_text(r["basis_date"], not r.get("basis_year_unknown")),
                                                 days=val(pp["exclude_official_days_before_target"])))
            continue
        by_site.setdefault(r["site"], []).append(r)
    for key, text in no_state:                       # 同じ名所に状態の分かる行があれば(提案になる)、「現況なし」とは書かない
        if key not in by_site:
            warn(key, text)
    if outside:
        warn(("outside", part["subject"]), wt["outside_catalog"].format(subject=part["name"], names="、".join(dict.fromkeys(outside))))

    gresolve = guide.reference_resolver(guide.load_policy())          # 参照数(段階24)。ガイドのカタログに同じ場所があるときだけ details に入れる
    refs = {}
    for h in part["candidates"].get("reference_links") or []:
        for s_ in h["sites"]:
            refs.setdefault(s_, []).append({"url": h["url"], "id": h["id"]})
    out = []
    for sid, rows in by_site.items():
        entry = entries[sid]
        for d in dates:
            # 主項目は答えと同じ選び方(sources.primary_for。段階22 A-1)。band・案B の判定は主項目に対して行う。
            # これまでは行ごとの band で並べて先頭を代表にしていたため、同じ条件の行では地点の書き方の順で先のものが代表になっていた
            main, others = primary_for(rows, d, part.get("registry"), policy)
            decided = [(r, *decide(r, d, policy=policy, on=on, scope=scope)) for r in [main] + others]
            rep, band, keys = decided[0]
            disagree = item_disagreements(main, others, d, policy)
            limits = list(pp["known_limits"]["common"])
            for r, _, k in decided:
                limits += row_limits(r, policy=policy, on=on)
            limits += [pp["known_limits"][k] for k in keys]
            ev = [e for r, _, _ in decided for e in row_evidence(r, d, publishers.get(r["source"]) or r["source"], policy)]
            tw = entry.get("typical_window")
            if tw:
                ev.append({"metric": "typical_window", "value": f"{tw['start'].replace('-', '/')}〜{tw['end'].replace('-', '/')}", "unit": None,
                           "valid_time": None, "source": entry["name"], "source_type": "static_reference", "url": tw.get("source_url"), "last_updated": None})
            stage_map = pp["phenology_stage_by_order"]
            p = {"id": f"{AGENT_ID}:{ID_KIND}:{part['subject']}:{d.isoformat()}:{sid}",
                 "title": f"{entry['name']} {d.isoformat()} {profile['name']}",
                 "subject": {"category": profile["category"], "name": profile["name"], "profile_id": profile["profile_id"]}}
            if rep.get("order") is not None:
                p["phenology_stage"] = stage_map[rep["order"]]
            p.update({
                "place": place_of(entry, profile, catalog_policy),
                "time_window": day_window(d),
                "suitability": {"band": band, "score": ({"value": rep["order"], "scale": pp["score_scale"], "go_threshold": None}
                                                       if rep.get("order") is not None else None)},
                "evidence": ev,
                "constraints": [],
                "uncertainty": {"lead_days": (d - on).days, "reliable_up_to_days": None,
                                "confidence": {"value": None, "scale": None, "method": pp["confidence_method"], "validated": False},
                                "known_limits": list(dict.fromkeys(limits))},
                "care": care_of(entry, profile),
                "native_ref": None,
                "details": {"profile_id": profile["profile_id"], "site_id": sid, "kind": "official_status",
                            "observations": [observation(r, publishers.get(r["source"]) or r["source"]) for r, _, _ in decided],
                            "representative_source": rep["source"], "representative_label": rep.get("label"),
                            # 補助の項目(主でない項目。隠さない。段階22 A-1 ③)と、見頃予測の扱いが主項目と食い違う補助の項目の文
                            **({"secondary_items": [secondary_item(r, d, policy) for r in others]} if others else {}),
                            **({"item_notes": [item_note(main, r, d, policy) for r in disagree]} if disagree else {}),
                            "official_status": {"stage": rep.get("stage"), "stage_label": rep.get("stage_label"), "order": rep.get("order"),
                                                "official_state": rep.get("official_state")},
                            "reference_links": refs.get(sid, []),
                            **({"reference_count": n_ref} if (n_ref := gresolve(part["subject"], entry["name"])) is not None else {}),
                            **({"catalog_site_ref": entry["site_ref"]} if entry.get("site_ref") else {}),
                            **({"site_details": entry["site_details"]} if entry.get("site_details") else {})},
            })
            out.append((_sort_key(band, rep, policy), sid, d.isoformat(), p))
    return [p for *_, p in sorted(out, key=lambda x: x[:3])]


def secondary_item(row, d, policy):
    """補助の項目(details.secondary_items の 1 件): 地点の書き方・状態・観察日・更新日・見頃予測と、その日の見頃予測の扱い。"""
    return {"label": row.get("label"), "official_state": row.get("official_state"), "stage": row.get("stage"),
            "official_observed": official_date_text(row.get("official_observed"), observed_year_known(row)),
            "official_updated": official_date_text(row.get("official_updated"), updated_year_known(row)),
            "official_forecast": row.get("official_forecast"), "forecast_status": forecast_day_status(row, d, policy)}


def unread_warnings(part, proposed_sites, warn, policy):
    """例年の時期の候補(candidates の sites)のうち、提案にならなかった名所 → 「現況なし」の警告。参考リンクも警告に。"""
    wt = policy["proposals"]["warnings"]
    c = part["candidates"]
    human, planned = {}, {}
    for h in c.get("human_urls") or []:
        for s_ in h["sites"]:
            human.setdefault(s_, h["url"])
    for h in c.get("read_plan") or []:
        if h["kind"] == "status_page":
            for s_ in h["sites"]:
                planned.setdefault(s_, h["url"])
    no_src = set(c.get("no_status_source") or [])
    for row in c.get("sites") or []:
        sid = row["site"]
        if sid in proposed_sites:
            continue
        if sid in planned and sid not in no_src:
            warn(sid, wt["not_read"].format(name=row["name"]))
        elif sid in human:
            warn(sid, wt["human_url"].format(name=row["name"], url=human[sid]))
        elif sid in no_src:
            warn(sid, wt["no_status_source"].format(name=row["name"]))
    for h in c.get("reference_links") or []:
        for s_ in h["sites"]:
            if s_ not in proposed_sites:
                nm = next((r["name"] for r in c.get("sites") or [] if r["site"] == s_), s_)
                warn(("ref", s_, h["url"]), wt["reference_link"].format(name=nm, url=h["url"]))


def build(parts, profiles, *, policy, catalog_policy, now, dates, early=False, late=False, request_id=None):
    """対象ごとの部品(sources.answer_parts)→ biyori-proposal/1 の文書(辞書)。"""
    from .sources import scope_orders
    scope = scope_orders(policy, early=early, late=late)
    warnings, seen = [], set()

    def warn(key, text):
        if key not in seen:
            seen.add(key)
            warnings.append(text)

    proposals, unread = [], 0
    for part in parts:
        before = len(warnings)
        ps = subject_proposals(part, profiles[part["subject"]], policy=policy, catalog_policy=catalog_policy, now=now, dates=dates, scope=scope,
                               warn=lambda k, t, s=part["subject"]: warn((s, k), t))
        unread_warnings(part, {p["details"]["site_id"] for p in ps}, lambda k, t, s=part["subject"]: warn((s, k), t), policy)
        unread += len(warnings) - before
        proposals += ps
    sources_used = {}
    for p in proposals:
        for o in p["details"]["observations"]:
            k = (o["publisher"], o["read_at"], o["source"])
            cur = sources_used.setdefault(k, {"source": o["publisher"], "source_type": "official_notice", "run_time": None,
                                              "fetched_at": o["read_at"], "last_updated": None, "url": None, "_dates": set()})
            if not o["updated_year_inferred"] and o["official_updated"]:
                cur["_dates"].add(o["official_updated"])
    regs = {s["id"]: s for part in parts for s in (part.get("registry") or {}).get("sources") or []}
    data_as_of = []
    for (pub, read_at, sid), v in sorted(sources_used.items()):
        v["url"] = (regs.get(sid) or {}).get("url")
        ds = v.pop("_dates")
        v["last_updated"] = max(ds) if ds else None
        data_as_of.append(v)
    subjects = [p["subject"] for p in parts]
    doc = {"schema": SCHEMA,
           "request_id": request_id or f"{AGENT_ID}-official-status:{'+'.join(subjects)}:{'+'.join(d.isoformat() for d in dates)}",
           "agent": {"id": AGENT_ID, "version": __version__, "commit": None},
           "status": "ok", "generated_at": now.isoformat(timespec="seconds"),
           "data_as_of": data_as_of, "proposals": proposals,
           "diagnostics": {"api_calls": 0, "cache_hit": None, "runtime_s": None, "warnings": warnings}}
    if not proposals:
        doc["status"], doc["status_reason"] = "partial", "no_official_status_today"
    elif unread:
        doc["status"], doc["status_reason"] = "partial", "some_places_without_official_status"
    return doc
