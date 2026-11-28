"""見つけた公式ページを覚えて、広く探すときに最初に読む(指示書 open-question-breadth の続き 第1部。本人の返事 1・7、2026-11-28)。

- 置き場はデータ置き場の research/pending_sources.jsonl(台帳ではない。答えの材料を絞らない。承認の欄は "pending" のまま)。
  本人が一覧を見て、台帳に入れる id をチャットで伝えたときだけ、台帳に approved で書く(この部品は台帳を書かない)。
- 残す(add): 発行元と公式と判断した理由・URL・何が書いてあるか・日付の持ち方・更新のしかた・場所・見つけた日ときっかけの質問。
  同じ URL(月ごとに変わる URL は変わらない部分 url_template)が既にあれば、行を増やさず、最後に読めた日だけを更新する。
- 最初に読む(pick): 聞かれた対象と範囲(出発地から片道の範囲。catalog の range_limit)に合う行を、近い順・最後に読めた日が新しい順に、
  最大 research.pending_first.max_reads 件。月ごとに URL が変わる行は、対象の日の月の URL を組み立てる。
- 読んだ印(seen): 最後に読めた日を更新し、research/pending_reads.jsonl に 1 行(資料の id・URL)。一覧から読んだ回数を数えるため。
- この一覧に載っていることで、確かさの区分を上げない(記録の区分は今までどおり URL のホストで決まる)。
値は data/ask/guide_mode.yaml の research.pending_first。"""
import hashlib
import json
import os
import re
from datetime import date, datetime
from urllib.parse import urlparse, unquote

NL = "\n"


def cfg():
    from . import research as RS
    return RS.cfg()["pending_first"]


def _v(x):
    return x["value"] if isinstance(x, dict) and "value" in x else x


def path(env=None):
    from . import research as RS
    return RS.rdir(env) / "pending_sources.jsonl"


def reads_path(env=None):
    from . import research as RS
    return RS.rdir(env) / "pending_reads.jsonl"


def key_of(row):
    """同じページかを決める鍵: 月ごとに変わる URL は変わらない部分(url_template)、ほかは URL(末尾の / を除く)。"""
    k = row.get("url_template") or row.get("url") or ""
    return k.rstrip("/")


def id_of(row):
    return row.get("id") or ("ps-" + hashlib.sha1(key_of(row).encode("utf-8")).hexdigest()[:8])


def rows(env=None):
    """全行(id を付けて)。読めない行は飛ばす。"""
    p = path(env)
    if not p.exists():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append({**r, "id": id_of(r)})
    return out


def _raw_lines(env=None):
    p = path(env)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def _write_lines(lines, env=None):
    p = path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(l + NL for l in lines), encoding="utf-8", newline="")
    os.replace(tmp, p)


def _find_line(lines, key):
    for i, l in enumerate(lines):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if isinstance(r, dict) and key_of(r) == key:
            return i, r
    return None, None


def build_url(row, when):
    """月ごとに URL が変わる行は、対象の日の月の URL を組み立てる。組み立てられなければ変わらない部分のページ(start_url)か URL。"""
    t = row.get("url_template")
    if _template_ok(t) and when is not None:
        return (t.replace("{yyyy}", f"{when.year:04d}").replace("{ry}", str(when.year - REIWA_BASE))   # {ry}: 令和の年(神奈川県の r811 = 令和8年11月)
                .replace("{mm}", f"{when.month:02d}"))
    return row.get("start_url") or row.get("url")


REIWA_BASE = 2018                                          # 令和元年 = 2019 年(暦。閾値ではない)


def _template_ok(t):
    return bool(t) and ("{yyyy}" in t or "{ry}" in t) and "{mm}" in t


def _template_re(t):
    return ("^" + re.escape(t).replace(re.escape("{yyyy}"), r"\d{4}").replace(re.escape("{ry}"), r"\d{1,2}")
            .replace(re.escape("{mm}"), r"\d{2}") + "/?$")


def in_ledger(url):
    """台帳(data/sources/*.yaml と observations の承認待ちの情報源)に、このページの URL そのものの項目があれば、その id。
    範囲(同じホストのパスの下)に入るだけのページは「台帳にまだ無い」と数える(三溪園の色づき情報・くりはま花の国のブログ)。"""
    from . import observations as O
    u = urlparse(url or "")
    host, p = O._bare_host(u.hostname), unquote(u.path or "/").rstrip("/") or "/"
    for h, lp, _st, _ledger, sid in O._ledger_urls():
        if h == host and (lp.rstrip("/") or "/") == p:
            return sid or True
    return None


def in_ledger_approved(url):
    """本人の返事(2026-11-28 の続きの 3): 台帳に、このページの URL そのものの項目が approved であるか。"""
    from . import observations as O
    u = urlparse(url or "")
    host, p = O._bare_host(u.hostname), unquote(u.path or "/").rstrip("/") or "/"
    return any(h == host and (lp.rstrip("/") or "/") == p and st == "approved" for h, lp, st, _l, _i in O._ledger_urls())


def not_auto_read(url):
    """台帳で承認済みなのに、資料の自動の読み直しでは読まれないページか(現況のページでない・どの名所からも届かない)。
    本人の決定(2026-11-28 の直す案 5): 承認済みの行は、自動で読み直せるときだけ「最初に読む」から外す。"""
    from . import auto_refresh as AU
    from . import brief_refresh as BR
    from . import sources as S
    k = AU.url_key(url)
    for ledger in AU.LEDGERS:
        try:
            reg = S.load_registry(ledger)
        except (OSError, ValueError):
            continue
        for src in (reg or {}).get("sources") or []:
            if AU.url_key(src.get("url")) == k and S.is_approved(src):
                return src.get("kind") != "status_page" or k not in BR.reachable_urls()
    return False


def check(item):
    """→ 理由の一覧(空なら残してよい)。"""
    from . import observations as O
    C = cfg()
    errs = []
    if not isinstance(item, dict):
        return ["JSON のオブジェクトではない"]
    url = item.get("url") or ""
    host = (urlparse(url).hostname or "").lower()
    if not url.startswith(("https://", "http://")) or not host:
        errs.append("url は http(s) のページ")
    pol = O.load_policy()
    if host and (O._sns_host(host, pol) or O._blocked_host(host, pol)):
        errs.append("SNS・読まないホストのページは残さない")
    from . import current_status as CS
    if host and any(host == b or host.endswith("." + b) for b in CS.open_blocked_domains()):
        errs.append("使わない出典のホストのページは残さない")
    for k in ("publisher", "official_reason", "content", "question"):
        if not str(item.get(k) or "").strip():
            errs.append(f"{k} が要る")
    if item.get("publisher_kind") not in C["publisher_kinds"]:
        errs.append(f"publisher_kind は {C['publisher_kinds']} のどれか(発行元がその場所の運営者などだと、ページの中身から確かめられたときだけ残す)")
    if item.get("subject") not in C["subjects"]:
        errs.append(f"subject は {C['subjects']} のどれか")
    if item.get("date_style") not in C["date_styles"]:
        errs.append(f"date_style は {list(C['date_styles'])} のどれか")
    if item.get("update_style") not in C["update_styles"]:
        errs.append(f"update_style は {list(C['update_styles'])} のどれか")
    if item.get("update_style") == "monthly_url":
        t = item.get("url_template") or ""
        if not _template_ok(t):
            errs.append("月ごとに URL が変わるページは url_template({yyyy} か {ry}(令和の年)と {mm} を含む変わらない部分)が要る")
        elif url and not re.match(_template_re(t), url):
            errs.append("url が url_template の形に合わない")
    pl = item.get("place") or {}
    if not isinstance(pl, dict) or not pl.get("name") or not pl.get("prefecture"):
        errs.append("place に name と prefecture が要る(分かれば city・lat・lon)")
    elif (pl.get("lat") is None) != (pl.get("lon") is None):
        errs.append("place の lat と lon は両方か、どちらも無し")
    if url and in_ledger(url):
        errs.append(f"台帳にすでにある({in_ledger(url)})")
    return errs


FIELDS = ("publisher", "publisher_kind", "official_reason", "url", "url_template", "start_url", "subject", "content", "kinds",
          "date_style", "update_style", "place", "note")


def add(items, *, brief=None, question=None, env=None, now=None):
    """候補を残す。→ {added, updated, rejected: [{index, errors}], ids}。同じ鍵の行があれば last_read_at だけを更新する。"""
    now = now or datetime.now().astimezone().replace(microsecond=0)
    lines = _raw_lines(env)
    added, updated, rejected, ids = 0, 0, [], []
    for i, it in enumerate(items or []):
        if isinstance(it, dict) and question and not it.get("question"):
            it = {**it, "question": question}
        key = key_of(it) if isinstance(it, dict) else ""
        j, old = _find_line(lines, key) if key else (None, None)
        if old is not None:                               # 同じページ: 行を増やさず、最後に読めた日だけ
            lines[j] = json.dumps({**old, "last_read_at": now.isoformat()}, ensure_ascii=False)
            updated += 1
            ids.append(id_of(old))
            continue
        errs = check(it)
        if errs:
            rejected.append({"index": i, "errors": errs})
            continue
        row = {k: it[k] for k in FIELDS if it.get(k) not in (None, "", [])}
        row.update(id=id_of(row), found_at=now.isoformat(), last_read_at=now.isoformat(), question=str(it["question"])[:80],
                   brief=brief or it.get("brief"), approval="pending")
        lines.append(json.dumps(row, ensure_ascii=False))
        added += 1
        ids.append(row["id"])
    if added or updated:
        _write_lines(lines, env)
    return {"added": added, "updated": updated, "rejected": rejected, "ids": ids}


def after_record(records, *, env=None, now=None):
    """本人の返事 6(2026-11-28): ask record で書けた今年の現況(状態・今年の状態の日付・URL あり・利用者の記録でない)のページについて、
    (a) 公式の区分のホスト(資料と同じ GB._source_class)で、台帳にも一覧にも無ければ、一覧に自動で残す(運営者の欄は「未確認」。確かめたことにしない)。
    (b) 公式の区分に無いホストなら、案内の 1 行(hints)を返す(自動では残さない)。一覧に載っていることで確かさの区分は上げない。
    → {"added": [id...], "hints": [文...]}"""
    from . import guide_brief as GB
    from . import current_status as CS
    from . import observations as O
    now = now or datetime.now().astimezone().replace(microsecond=0)
    C = cfg()
    A = C["auto"]
    lines = _raw_lines(env)
    keys = {key_of(json.loads(l)) for l in lines if l.strip().startswith("{")}
    blocked = CS.open_blocked_domains()
    added, hints, done = [], [], set()
    for r in records or []:
        url = r.get("url")
        if not url or url in done or not r.get("state") or r.get("source_class") == "user" or r.get("event"):
            continue
        sd = O.state_date_of(r)
        if not sd or str(sd)[:4] != str(now.year):
            continue
        done.add(url)
        host = (urlparse(url).hostname or "").lower()
        if any(host == b or host.endswith("." + b) for b in blocked) or in_ledger(url) or url.rstrip("/") in keys:
            continue
        if GB._source_class(url, r.get("source_class")) != "official":
            hints.append(A["hint"].format(url=url))
            continue
        row = {"publisher": r.get("publisher") or host, "publisher_kind": A["unverified"], "official_reason": A["reason"], "url": url,
               "subject": r.get("subject"), "content": (f"{r.get('kind') or ''} {r.get('state') or ''}").strip()[:80], "kinds": [r["kind"]] if r.get("kind") else [],
               "date_style": A["unverified"], "update_style": A["unverified"],
               "place": {k: v for k, v in {"name": r.get("name") or r.get("spot"), "prefecture": r.get("prefecture"), "city": r.get("city")}.items() if v},
               "auto": True, "operator_checked": False}
        row.update(id=id_of(row), found_at=now.isoformat(), last_read_at=now.isoformat(), question=A["question"], brief=None, approval="pending")
        lines.append(json.dumps(row, ensure_ascii=False))
        keys.add(key_of(row))
        added.append(row["id"])
    if added:
        _write_lines(lines, env)
    return {"added": added, "hints": hints}


def seen(ref, *, brief=None, env=None, now=None):
    """一覧のページを読めた印(ref は id か URL)。→ {id, url} か None(一覧に無い)。"""
    now = now or datetime.now().astimezone().replace(microsecond=0)
    lines = _raw_lines(env)
    hit = None
    for j, l in enumerate(lines):
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if not isinstance(r, dict):
            continue
        t = r.get("url_template")
        if ref in (id_of(r), r.get("url"), r.get("start_url")) or key_of(r) == (ref or "").rstrip("/") or (t and re.match(_template_re(t), ref or "")):
            hit = (j, r)
            break
    if hit is None:
        return None
    j, r = hit
    lines[j] = json.dumps({**r, "last_read_at": now.isoformat()}, ensure_ascii=False)
    _write_lines(lines, env)
    p = reads_path(env)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="") as f:
        f.write(json.dumps({"at": now.isoformat(), "brief": brief, "id": id_of(r), "url": ref}, ensure_ascii=False) + NL)
    return {"id": id_of(r), "url": ref}


def reads_by_brief(bid, env=None):
    p = reads_path(env)
    if not p.exists() or not bid:
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("brief") == bid:
            out.append(r)
    return out


def _km(row, origin):
    """出発地からの直線の距離と範囲の区分。→ (km か None, status か None)。座標 → 市区町村の代表点の順。"""
    from . import catalog as CM
    from . import origins
    pl = row.get("place") or {}
    pt = {"lat": pl["lat"], "lon": pl["lon"]} if pl.get("lat") is not None else None
    if pt is None and pl.get("city"):
        pt = origins.municipal_point(pl["city"])
    if pt is None:
        return None, None
    try:
        rg = CM.range_from(CM.load_policy(), pt, origin)
    except (KeyError, TypeError, ValueError, StopIteration):
        return None, None
    return rg["km"], rg["status"]


def _name_hit(row, places):
    pl = row.get("place") or {}
    text = " ".join(str(x or "") for x in (pl.get("name"), pl.get("city"), pl.get("area"), row.get("content")))
    return any(p and (p in text or (pl.get("name") and pl["name"] in p)) for p in places)


def pick(subjects, *, origin=None, when=None, places=None, species_words=None, env=None, limit=None, wide=False, current_names=None):
    """最初に読むページ。subjects: 聞かれた対象。places: 名指しの質問の名所(あれば、その名所に合う行だけ)。
    species_words: 種を挙げた質問の語(行に kinds があり、どれも合わない行は外す)。→ [{id, url, publisher, name, km, last_read_at}]。"""
    from . import observations as O
    C = cfg()
    limit = _v(C["max_reads"]) if limit is None else limit
    prefs = set((O.load_policy()["record"].get("range_check") or {}).get("prefectures") or [])
    out = []
    for r in rows(env):
        if r.get("subject") not in (subjects or []):      # 1-1 の項目の無い古い行(subject なし)は選ばない
            continue
        if (r.get("approval") not in (None, "pending") or in_ledger_approved(r.get("url"))) and not not_auto_read(r.get("url")):
            continue                                      # 台帳に approved で入った行は、自動で読み直せるので、最初に読む一覧に出さない
        if places and not _name_hit(r, places):
            continue
        kinds = r.get("kinds") or []
        if species_words and kinds and not any(w in k or k in w for w in species_words for k in kinds):
            continue
        km, status = _km(r, origin)
        if status == "out_of_range":
            continue
        if status is None and (r.get("place") or {}).get("prefecture") not in prefs:
            continue
        out.append({"id": r["id"], "url": build_url(r, when), "publisher": r.get("publisher"), "name": (r.get("place") or {}).get("name"),
                    "km": km, "last_read_at": r.get("last_read_at") or r.get("found_at") or "", "update_style": r.get("update_style"),
                    "start_url": r.get("start_url"), "prefecture": (r.get("place") or {}).get("prefecture"),
                    "has_current": bool(current_names) and _name_hit(r, current_names), "unverified": r.get("operator_checked") is False})
    out.sort(key=lambda x: x["last_read_at"], reverse=True)
    out.sort(key=lambda x: x["km"] if x["km"] is not None else float("inf"))
    if not wide:
        return out[:limit]
    # 本人の返事 3(2026-11-28): 範囲が wide(「遠くても」)のときは、今年の現況がある場所を先に、そのうえで都県が重ならないように(同じ都県は wide_max_same_prefecture まで)
    out.sort(key=lambda x: not x["has_current"])
    cap, seen, got = _v(C["wide_max_same_prefecture"]), {}, []
    for x in out:
        k = x.get("prefecture") or ""
        if seen.get(k, 0) >= cap:
            continue
        seen[k] = seen.get(k, 0) + 1
        got.append(x)
    return got[:limit]


def attach(targets, cond, now, env=None, species_words=None, wide=False, current_names=None):
    """調べる対象(広く探す・名指しの今年の現況)に read_first を付ける。全体で最大 max_reads 件(同じページは 1 回)。"""
    tg = [t for t in targets or [] if t.get("kind") in ("open_breadth", "current_status")]
    if not tg:
        return targets
    C = cfg()
    left = _v(C["max_reads"])
    used = set()
    subjects = [s for s in (cond.get("subjects") or []) if s in C["subjects"]] or list(C["subjects"])
    when = now.date()
    for ds in cond.get("periods") or []:                  # 対象の日(質問の期間の最初の日)。無ければ今日
        try:
            when = date.fromisoformat(str(ds[0])[:10])
            break
        except (TypeError, ValueError, IndexError):
            continue
    for t in tg:
        if left <= 0:
            t["read_first"] = []
            continue
        places = [t["where"]] if t.get("kind") == "current_status" else None
        cap = min(left, t.get("max_pages") or left)          # 名指しの名所 1 つの取得の上限(4)より多くは選ばない
        got = [x for x in pick(subjects, origin=cond.get("origin"), when=when, places=places, species_words=species_words, env=env, limit=cap + len(used),
                               wide=wide and t.get("kind") == "open_breadth", current_names=current_names)
               if x["id"] not in used][:cap]
        used.update(x["id"] for x in got)
        left -= len(got)
        t["read_first"] = got
    return targets


def step_lines(bid, target):
    """資料の節「調べる」の、最初に読むページの手順(read_first が無ければ空)。"""
    C = cfg()
    rf = target.get("read_first") or []
    if not rf:
        return []
    out = [x.format(id=bid, n=len(rf), max=_v(C["max_reads"]), pages=target.get("max_pages") or "") for x in C["step_lines"]]
    for x in rf:
        km = f"直線で約{int(x['km'])}km、" if x.get("km") is not None else ""
        extra = f"。読めなければ {x['start_url']} から辿る" if x.get("update_style") == "monthly_url" and x.get("start_url") else ""
        out.append(C["row"].format(id=x["id"], name=x.get("name") or "", publisher=x.get("publisher") or "", url=x["url"], km=km,
                                   last=(x.get("last_read_at") or "")[:10]) + extra + (C["auto"]["row_mark"] if x.get("unverified") else ""))
    return out + [""]
