"""直前の答え(計画)から作る、紅葉・花・野鳥・総合の写真つきの単独 HTML ページ(段階57 第2部)。

- 材料は答えと同じ facts.json と answer_plan.json(ask plan)。新しい事実を足さない。順位・節は計画のまま。
- 写真は「種の代表写真」だけ(紅葉は樹種、花は花の種、野鳥は記録の種)。地点そのものの写真は使わない(段階53 の決定)。SVG・手書きの図は使わない。
- 安全: すべての文字を html.escape。JavaScript なし。CSP。写真は data URI。リンクは http・https だけ。
- 通信しない。写真はキャッシュ(guide_photos)にあるものだけ。文はすべて data/ask/policy.yaml の plan_page から作る。"""
from datetime import date
from urllib.parse import urlsplit

from .park_page import CSS, CIRCLED, WEEKDAYS, _v, esc, link, safe_url, short_author
from .photo_pool import PhotoPool

SUBJECT_WORD = {"autumn_leaves": "紅葉", "flowers": "花", "birds": "野鳥"}


def species_of(c, subject, cfg):
    """候補の、写真に載せる種名(重複なし。別名は丸める)。樹種が不明な地点は空(写真なし)。"""
    if subject == "autumn_leaves":
        raw = c.get("tree_species") or []
    elif subject == "flowers":
        raw = c.get("flower_kinds") or []
    else:
        raw = [b["name"] for b in c.get("park_birds") or []]
    alias, skip = cfg.get("photo_aliases") or {}, set(cfg.get("skip_names") or [])
    out = []
    for n in raw:
        n = alias.get(n, n)
        if n and n not in skip and n not in out:
            out.append(n)
    return out[: _v(cfg["max_species_per_spot"])]


def plan_subjects(plan):
    """計画 → [(対象, 対象の計画)]。総合(all)は対象ごと。"""
    return list((plan.get("subjects") or {}).items()) if plan.get("subject") == "all" else [(plan["subject"], plan)]


def has_photo_candidates(facts, plan, cfg):
    """今回のおすすめに、写真の候補(種名)が 1 つ以上あるか(案内の条件)。"""
    for sj, pl in plan_subjects(plan):
        cands = {c["name"]: c for c in (facts["subjects"].get(sj) or {}).get("candidates") or []}
        if any(species_of(cands.get(p["name"]) or {}, sj, cfg) for p in pl.get("picks") or []):
            return True
    return False


def species_by_subject(facts, plan, cfg):
    """{対象: [種名]}(計画の節に載る名所の分だけ)。写真の取得に使う。"""
    out = {}
    for sj, pl in plan_subjects(plan):
        cands = {c["name"]: c for c in (facts["subjects"].get(sj) or {}).get("candidates") or []}
        for it in [i for s in pl.get("sections") or [] for i in s["items"]] + list(pl.get("picks") or []):
            for n in species_of(cands.get(it["name"]) or {}, sj, cfg):
                if n not in out.setdefault(sj, []):
                    out[sj].append(n)
    return out


def _lead_of(answer, heading):
    """答えの文章の冒頭(「今回のおすすめ」の見出しの前)。"""
    if not answer:
        return None
    out = []
    for line in str(answer).splitlines():
        if heading in line:
            break
        if line.strip():
            out.append(line.strip())
    return "".join(out) or None


def _md(iso):
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.month}/{d.day}"


def _region_label(facts):
    """段階62 第2部: ページの題名の地域(質問の地域。登録済みの全範囲のときは出さない)。"""
    from . import observations as O
    r = facts.get("region")
    pol = O.load_policy()
    if not r or r in (pol.get("all_range_words") or []) or r == pol.get("all_range_name"):
        return None
    reg = O.resolve(r, facts.get("origin"), pol)
    return reg["name"] if reg.get("resolved") else None


def build(facts, plan, *, policy, photo_for, photo_credit, now, answer=None):
    """→ (HTML, 検査用の文の一覧, 載せた種 {名所: [(種名, 写真あり)]})。photo_for(和名) → (メタ, バイト列) か None。
    photo_credit(メタ) → 表示の文字列(撮影者・ライセンス)。元のページのリンクは answer_page.photo_card が付ける。"""
    t = policy["text"]
    lines = []

    def say(s):
        lines.append(s)
        return esc(s)
    dates = [date.fromisoformat(x) for x in facts.get("dates") or []]
    dtxt = "・".join(f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})" for d in dates)
    subs = plan_subjects(plan)
    labels = "・".join(t["subject_labels"][sj] for sj, _ in subs)
    pool = PhotoPool(_v(policy["max_embed_bytes"]))
    region = plan.get("region_name") or _region_label(facts)
    title = t["title_region"].format(dates=dtxt, region=region, labels=labels) if region and t.get("title_region") else t["title"].format(dates=dtxt, labels=labels)
    body = [f"<h1>{say(title)}</h1>"]
    picks = plan.get("picks") or []
    lead = _lead_of(answer, t["picks_heading"]) or t["conclusion"].format(dates=dtxt, names=t["names_sep"].join(p["name"] for p in picks))
    body.append(f'<p class="lead">{say(lead)}</p>')
    if facts.get("origin"):
        body.append(f'<p class="meta">{say(t["origin"].format(origin=facts["origin"]))}</p>')
    body.append(f'<p class="note">{say(t["photo_note"])}</p>')
    body.append(f"<h2>{say(t['picks_heading'])}</h2>")
    body.append('<ul class="park-facts">' + "".join(f"<li>{say((CIRCLED[i] if i < len(CIRCLED) else str(i + 1)) + ' ' + p['name'])}</li>" for i, p in enumerate(picks)) + "</ul>")
    shown = {}
    multi = len(subs) > 1

    def card(it, sj, cands):
        c = cands.get(it["name"]) or {}
        head = it["name"] + (f"({c['city']})" if c.get("city") else "")
        out = [f"<h3>{say(head)}</h3>"]
        pf = []
        cur = c.get("current")
        if cur and cur.get("state_raw") and not cur.get("symbol_only"):
            when = _md(cur["state_date"]) if cur.get("state_date") else None
            pf.append(say(t["current"].format(state=cur.get("display") or cur["state_raw"], md=when, publisher=cur.get("publisher") or "") if when else
                          t["current_nodate"].format(state=cur.get("display") or cur["state_raw"], publisher=cur.get("publisher") or "")))
        else:
            pf.append(say(t["no_current"]))
        if it.get("phrase"):
            pf.append(say(it["phrase"] + "。"))
        if it.get("note"):
            pf.append(say(it["note"] + "。"))
        for f in c.get("festivals") or []:                       # まつりの期間は現況と別の行
            if f.get("period_line"):
                pf.append(say(f["period_line"]))
        for p in (c.get("practical") or [])[:1]:
            pf.append(say(t["practical"].format(text=p["text"])))
        urls = []
        for u in [(cur or {}).get("url")] + [p.get("url") for p in c.get("practical") or []] + [f.get("url") for f in c.get("festivals") or []]:
            if u and safe_url(u) and u not in urls:
                urls.append(u)
        if urls:
            lines.extend(urls)
            pf.append(esc(t["sources"]) + " " + " ".join(link(u, urlsplit(u).hostname) for u in urls))
        out.append('<ul class="park-facts">' + "".join(f"<li>{x}</li>" for x in pf) + "</ul>")
        cards, nophoto = [], []
        from . import answer_page as APG
        for name in species_of(c, sj, policy):
            got, rep = APG.photo_with_representative(name, photo_for)   # 段階81 の追記: 総称の種は代表の写真(説明に「写真は○○」)
            img = pool.tag(got[0], got[1], name) if got else None
            if img is None:                                      # 写真が取れなかった種は枠を出さず、名前だけの行(手描きの図にしない)
                nophoto.append(name)
                shown.setdefault(it["name"], []).append((name, False))
                continue
            cards.append(APG.photo_card(name, got, rep, img, photo_credit, say))
            shown.setdefault(it["name"], []).append((name, True))
        if cards:
            out.append('<ul class="birds">' + "".join(cards) + "</ul>")
        if nophoto:
            out.append(f'<p class="note">{say(t["no_photo_names"].format(names=t["names_sep"].join(nophoto)))}</p>')
        return "".join(out)

    for sj, pl in subs:
        cands = {c["name"]: c for c in (facts["subjects"].get(sj) or {}).get("candidates") or []}
        if multi:
            body.append(f"<h2>{say(t['subject_labels'][sj])}</h2>")
        for sec in pl.get("sections") or []:
            tag = "h3" if multi else "h2"
            body.append(f"<section><{tag}>{say(sec['label'])}</{tag}>")
            for it in sec["items"]:
                body.append(card(it, sj, cands))
            body.append("</section>")
    body.append(f'<p class="note">{say(t["footer"])}</p>')
    page = ("<!DOCTYPE html>\n<html lang=\"ja\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f'<meta http-equiv="Content-Security-Policy" content="{esc(policy["csp"])}">\n'
            f"<title>{esc(title)}</title>\n<style>{CSS}\n{pool.css()}</style>\n</head>\n<body>\n<main>\n"
            + "\n".join(body) + "\n</main>\n</body>\n</html>\n")
    return page, lines, shown


def author_credit(meta, gp, state_line=None):
    """写真の下の 1 行(撮影者・ライセンス)。段階81 の追記から、呼び出し側は状態を渡さない(state_line は互換のため残す)。"""
    text = gp["html"]["photo_credit"].format(author=short_author(meta, gp["html"]["author_re"]), license=meta["license"])
    return text + (" " + state_line if state_line else "")
