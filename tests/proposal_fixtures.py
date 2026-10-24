"""提案(段階18)のテスト用の合成データ。対象ごとに、合成の情報源の一覧・名所カタログ・読んだ結果の記録を作る(実在の名所・公式ページの本文ではない)。
ゴールデン(tests/fixtures/proposals/<対象>.json)はこのデータから作った出力を、意図した形か目で確かめて置いたもの(作り直さない)。"""
from datetime import date, datetime, timedelta, timezone

import helpers  # noqa: F401  (通信禁止・パス)
from ikimonobiyori import sources

JST = timezone(timedelta(hours=9))
POLICY = sources.load_policy()
NOW = datetime(2026, 10, 24, 13, 54, tzinfo=JST)
DATES = [date(2026, 10, 31), date(2026, 11, 1)]


def src(sid, subject, covers, smap, year_shown=True, date_basis=None, kind="status_page", approved=True):
    nt = {"style": "word", "map": smap, "updated": "per_item", "year_shown": year_shown}
    if date_basis:
        nt["date_basis"] = date_basis
    return {"id": sid, "publisher": f"試験の発信元({subject})", "publisher_kind": "municipality", "url": f"https://{subject.replace('_', '-')}.example.org/{sid}",
            "kind": kind, "covers": covers, "notation": nt,
            "readable": {"status": "ok", "checked_on": "2026-10-23", "robots": "allows"}, "terms": {"status": "no_prohibition_found"},
            "approval": ({"status": "approved", "approved_by": "user", "approved_on": "2026-10-23"} if approved
                         else {"status": "pending", "reason": "試験"})}


def site(sid, subject, name, tw, status_sources, lat=35.5, lon=139.5, precision="exact", **tags):
    return {"id": sid, "name": name, "subjects": [subject], "timing_type": "calendar", "kind": "point",
            "point": {"lat": lat, "lon": lon, "elevation_m": None}, "location_precision": precision, "status": "approved",
            "approved_at": "2026-10-22", "sources": [{"url": f"https://example.org/{sid}", "title": "試験の出典", "checked_on": "2026-10-22"}],
            "status_sources": list(status_sources), "tags": {"prefecture": "東京都", **tags},
            "typical_window": {"start": tw[0], "end": tw[1], "source_url": f"https://example.org/{sid}/tw"}}


def scenario(subject):
    """→ (情報源の一覧, 名所カタログ, 記録のリスト)。"""
    mk = lambda reg, **kw: sources.make_record(registry=reg, policy=POLICY, read_at=NOW.isoformat(), **kw)  # noqa: E731
    if subject == "autumn_leaves":
        smap = {"まだ": "not_yet", "色づき始め": "starting", "見ごろ": "good", "真っ盛り": "peak", "落葉": "fading"}
        reg = {"schema": "ikimono-status-sources/1", "subject": subject, "sources": [
            src("al-main", subject, [{"site": "s-al-1", "label": "試験の谷・木々"}, {"site": "s-al-1", "label": "試験の谷・草紅葉"},
                                     {"site": "s-al-2", "label": "試験の湖"}, {"site": "s-al-3", "label": "試験の峠"},
                                     {"name": "試験の外の滝", "label": "試験の外の滝"}], smap),
            src("al-noyear", subject, [{"site": "s-al-4", "label": "試験の庭"}], smap, year_shown=False, date_basis="observed_date")]}
        cat = {"schema": "ikimono-site-catalog/1", "subject": subject, "entries": [
            site("s-al-1", subject, "試験の谷", ("10-11", "11-10"), ["al-main"], traffic_note="紅葉期は試験の道が混みやすい"),
            site("s-al-2", subject, "試験の湖", ("10-11", "11-10"), ["al-main"]),
            site("s-al-3", subject, "試験の峠", ("10-01", "10-31"), ["al-main"]),
            site("s-al-4", subject, "試験の庭", ("10-21", "11-20"), ["al-noyear"]),
            site("s-al-5", subject, "試験の高原", ("10-11", "11-10"), [])]}
        recs = [mk(reg, source_id="al-main", site="s-al-1", label="試験の谷・木々", state="見ごろ", updated="2026-10-22", forecast="10月中旬～11月上旬"),
                mk(reg, source_id="al-main", site="s-al-1", label="試験の谷・草紅葉", state="真っ盛り", updated="2026-10-23"),
                mk(reg, source_id="al-main", site="s-al-2", label="試験の湖", state="まだ", updated="2026-10-20"),
                mk(reg, source_id="al-main", site="s-al-3", label="試験の峠", state="落葉", updated="2026-09-20"),
                mk(reg, source_id="al-main", name="試験の外の滝", label="試験の外の滝", state="見ごろ", updated="2026-10-22"),
                mk(reg, source_id="al-noyear", site="s-al-4", label="試験の庭", state="色づき始め", observed_md="10-21")]
        return reg, cat, recs
    if subject == "wintering_birds":
        smap = {"飛来前": "not_arrived", "初飛来": "arriving", "増加中": "increasing"}
        reg = {"schema": "ikimono-status-sources/1", "subject": subject, "sources": [
            src("wb-a", subject, [{"site": "s-wb-1", "label": "試験の沼"}, {"site": "s-wb-2", "label": "試験の池"}], smap)]}
        cat = {"schema": "ikimono-site-catalog/1", "subject": subject, "entries": [
            site("s-wb-1", subject, "試験の沼", ("10-01", "03-31"), ["wb-a"], lat=36.12345, lon=139.98765, precision="area_1km"),
            site("s-wb-2", subject, "試験の池", ("11-01", "03-15"), ["wb-a"], lat=36.5, lon=140.25, precision="area_1km")]}
        recs = [mk(reg, source_id="wb-a", site="s-wb-1", label="試験の沼", state="初飛来", observed="2026-10-23", updated="2026-10-23"),
                mk(reg, source_id="wb-a", site="s-wb-2", label="試験の池", state="飛来前", updated="2026-10-20")]
        return reg, cat, recs
    if subject == "flowers":
        smap = {"つぼみ": "bud", "咲き始め": "starting", "見頃": "good", "満開": "full", "散り始め": "falling"}
        reg = {"schema": "ikimono-status-sources/1", "subject": subject, "sources": [
            src("fl-a", subject, [{"site": "s-fl-1", "label": "試験の花畑"}, {"site": "s-fl-2", "label": "試験の園"}], smap)]}
        cat = {"schema": "ikimono-site-catalog/1", "subject": subject, "entries": [
            site("s-fl-1", subject, "試験の花畑", ("10-01", "11-15"), ["fl-a"]),
            site("s-fl-2", subject, "試験の園", ("10-15", "11-30"), ["fl-a"])]}
        recs = [mk(reg, source_id="fl-a", site="s-fl-1", label="試験の花畑", state="見頃", updated="2026-10-23"),
                mk(reg, source_id="fl-a", site="s-fl-2", label="試験の園", state="つぼみ", updated="2026-10-23", forecast="11月上旬")]
        return reg, cat, recs
    if subject == "birds":
        smap = {"少ない": "few", "増えている": "increasing", "多い": "many", "減っている": "decreasing"}
        reg = {"schema": "ikimono-status-sources/1", "subject": subject, "sources": [
            src("bd-a", subject, [{"site": "s-bd-1", "label": "試験の干潟"}, {"site": "s-bd-2", "label": "試験の森"}], smap)]}
        cat = {"schema": "ikimono-site-catalog/1", "subject": subject, "entries": [
            site("s-bd-1", subject, "試験の干潟", ("01-01", "12-31"), ["bd-a"], lat=35.61234, lon=139.94321, precision="area_1km"),
            site("s-bd-2", subject, "試験の森", ("01-01", "12-31"), ["bd-a"], lat=35.7, lon=139.3, precision="area_1km")]}
        recs = [mk(reg, source_id="bd-a", site="s-bd-1", label="試験の干潟", state="多い", updated="2026-10-22", method="code"),
                mk(reg, source_id="bd-a", site="s-bd-2", label="試験の森", state="少ない", updated="2026-10-12")]
        return reg, cat, recs
    raise KeyError(subject)


SUBJECTS = ("autumn_leaves", "wintering_birds", "flowers", "birds")


def part(subject, recs=None, dates=DATES, early=False, late=False, profile_name=None):
    reg, cat, rs = scenario(subject)
    recs = rs if recs is None else recs
    return {"subject": subject, "name": profile_name or subject, "catalog": cat, "registry": reg,
            "summary": sources.summarize(recs, registry=reg, catalog_doc=cat, policy=POLICY, on=NOW.date(), dates=dates, early=early, late=late),
            "candidates": sources.candidates(cat, reg, dates, POLICY), "care": None}
