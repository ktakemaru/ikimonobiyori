"""提案の出力が変わらないこと(ゴールデン)を確かめるための部品。通信はしない。
ゴールデンは tests/fixtures/golden/ にある。biyori-hub の中で動いていたとき(段階12 フェーズ1の開始時。biyori-hub の c172548 より前の出力)に記録したもの。
  G1 合成の入力(synthetic_inputs.json)→ engine.run(紅葉+野鳥 / 紅葉だけ / 野鳥だけ)
  G2 記録済みの Open-Meteo の入力(recorded_open_meteo)→ engine.run(紅葉)。野鳥の記録(iNaturalist)は利用条件の目視が済むまでこのリポジトリに置かない
  G4 adapter と同じ子プロセスの経路: main.py --cache-only(キャッシュは一時フォルダに、偽の応答から作る)→ 部品 → compose
比較: 時刻と request_id は固定(置き換え不要)。子プロセスの経路だけ、絶対パスを <ROOT>/<TMP> に、agent.commit を <COMMIT> に置き換え、
diagnostics.runtime_s は比べない。JSON の値で比べる(キーの順序は無視)。"""
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import helpers
from helpers import FIXTURES, ROOT
from ikimonobiyori import compose, engine, profiles
from ikimonobiyori.config import load_config
from ikimonobiyori import main as imain

GOLDEN_DIR = FIXTURES / "golden"
JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 15, 6, 0, tzinfo=JST)
G4_NOW = datetime(2026, 10, 14, 22, 0, tzinfo=JST)
G4_SITES = "m029,m001,m002"
BIRD_SPECIES = [("Parus minor", "シジュウカラ", 40), ("Corvus macrorhynchos", "ハシブトガラス", 20), ("Zosterops japonicus", "メジロ", 14),
                ("Passer montanus", "スズメ", 6), ("Phasianus versicolor", "キジ", 4)]       # 合成(架空の件数)


def request(interests, rid="golden"):
    return {"schema": "biyori-request/1", "request_id": rid, "intent": "weekend_outing",
            "time_range": {"start": "2026-10-17T00:00:00+09:00", "end": "2026-10-18T23:59:00+09:00"},
            "origin": {"name": "x", "lat": 35.0, "lon": 139.0}, "interests": list(interests)}


def recorded_open_meteo():
    om = json.loads((FIXTURES / "recorded_open_meteo_2026-10-14.json").read_text(encoding="utf-8"))
    inputs = {"schema": "ikimono-inputs/1", "synthetic": False, "fetched_at": om["fetched_at"], "temperatures": om["temperatures"],
              "temperatures_meta": om["temperatures_meta"], "site_ids": sorted(om["temperatures"])}
    return om, inputs


def build_inproc():
    """G1・G2 → {名前: 文書}。"""
    profs, (sites, _) = profiles.load_profiles(), profiles.load_sites()
    run = lambda req, inputs: engine.run(req, profiles=profs, sites=sites, inputs=inputs, now=NOW)
    syn = json.loads((FIXTURES / "synthetic_inputs.json").read_text(encoding="utf-8"))
    return {"g1_synthetic_both": run(request(["autumn_leaves", "birds"]), syn),
            "g1_synthetic_autumn": run(request(["autumn_leaves"]), syn),
            "g1_synthetic_birds": run(request(["birds"]), syn),
            "g2_recorded_autumn": run(request(["autumn_leaves"]), recorded_open_meteo()[1])}


def _om_http(om):
    """記録済みの Open-Meteo の応答を、URL の緯度(記録の URL の先頭のパラメータ)で選んで返す偽の http_get(2 値)。"""
    def get(url):
        for sid, meta in om["temperatures_meta"].items():
            if meta["url"].split("?")[1].split("&")[0] in url:
                return 200, json.dumps(om["temperatures"][sid])
        raise AssertionError(f"記録にない URL: {url}")
    return get


def _birds_http(url):
    results = [{"count": c, "taxon": {"id": 1000 + i, "name": s, "preferred_common_name": ja, "rank": "species", "iconic_taxon_name": "Aves"}}
               for i, (s, ja, c) in enumerate(BIRD_SPECIES)]
    return 200, json.dumps({"total_results": len(results), "page": 1, "per_page": 200, "results": results}), {}


def seed_cache(cache_dir, work):
    """main.py を偽の http_get で(プロセス内で)動かし、一時フォルダのキャッシュを作る。通信しない。"""
    om, _ = recorded_open_meteo()
    for subject, http in (("autumn_leaves", _om_http(om)), ("birds", _birds_http)):
        req = Path(work) / f"seed-{subject}.json"
        req.write_text(json.dumps(request([subject], rid=f"g4-{subject}")), encoding="utf-8")
        argv = ["--request", str(req), "--live", "--max-requests", "20", "--now", G4_NOW.isoformat(), "--cache-dir", str(cache_dir),
                "--out", str(Path(work) / f"seed-{subject}.out.json"), "--inputs-out", str(Path(work) / f"seed-{subject}.in.json")]
        if subject == "autumn_leaves":
            argv += ["--sites", G4_SITES]
        rc = imain.main(argv, http_get=http, clock=lambda: G4_NOW)       # 段階36: 取得時刻は受け取った時刻(clock)。記録したときと同じ時刻を返す時計
        if rc != 0:
            raise RuntimeError(f"キャッシュの準備に失敗: {subject} rc={rc}")


def g4_cmd(python, main_py, req, out, inp, cache_dir=None, subject="autumn_leaves"):
    """adapter(biyori-hub の adapters/ikimonobiyori_run.py)が組み立てるのと同じ形の、--cache-only の子プロセスの引数配列。"""
    cmd = [python, "-X", "utf8", str(main_py), "--request", str(req), "--cache-only", "--max-requests", "20", "--now", G4_NOW.isoformat(timespec="seconds"),
           "--out", str(out), "--inputs-out", str(inp)]
    if subject == "autumn_leaves":
        cmd += ["--sites", G4_SITES]
    if cache_dir is not None:
        cmd += ["--cache-dir", str(cache_dir)]
    return cmd


def build_g4(launch, *, python=sys.executable, main_py=None, data_dir_env=False):
    """G4 → {名前: 文書}。launch(cmd, extra_env) が子プロセスを起動して終了コードを返す。
    data_dir_env=True なら、キャッシュの場所を --cache-dir ではなく IKIMONOBIYORI_DATA_DIR(<data>/cache)で渡す。"""
    cfg = load_config()
    work = Path(tempfile.mkdtemp(prefix="ikimono-g4-"))
    data = work / "data"
    cache_dir = data / "cache"
    seed_cache(cache_dir, work)
    out = {}
    for subject in ("autumn_leaves", "birds"):
        req = work / f"seed-{subject}.json"
        o, i = work / f"child-{subject}.out.json", work / f"child-{subject}.in.json"
        cmd = g4_cmd(python, main_py or ROOT / "ikimonobiyori" / "main.py", req, o, i, cache_dir=None if data_dir_env else cache_dir, subject=subject)
        rc = launch(cmd, {"IKIMONOBIYORI_DATA_DIR": str(data)} if data_dir_env else {})
        if rc != 0:
            raise RuntimeError(f"G4 の子プロセスが失敗: {subject} rc={rc}")
        out[f"g4_child_{subject}"] = json.loads(o.read_text(encoding="utf-8"))
    comp_dir = work / "components"
    for subject in ("autumn_leaves", "birds"):
        compose.update_component(subject, out[f"g4_child_{subject}"], G4_NOW, directory=comp_dir)
    out["g4_composed"] = compose.compose(G4_NOW, directory=comp_dir, ttl_s=cfg["compose"]["ttl_s"])
    return {k: normalize(v, work) for k, v in out.items()}


def normalize(doc, tmp=None):
    s = json.dumps(doc, ensure_ascii=False)
    for path, tag in ((tmp, "<TMP>"), (ROOT, "<ROOT>")):
        if path is not None:
            for form in (str(path), str(path).replace("\\", "\\\\"), Path(path).as_posix()):
                s = s.replace(form, tag)
    d = json.loads(s)
    if isinstance(d.get("agent"), dict) and d["agent"].get("commit") is not None:
        d["agent"]["commit"] = "<COMMIT>"
    (d.get("diagnostics") or {}).pop("runtime_s", None)
    return d


def load_golden():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(GOLDEN_DIR.glob("*.json"))}


def diff(a, b, path=""):
    """最初の違い(の場所)。同じなら None。"""
    if type(a) is not type(b):
        return f"{path}: 型 {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        if set(a) != set(b):
            return f"{path}: キー {sorted(set(a) ^ set(b))}"
        for k in a:
            r = diff(a[k], b[k], f"{path}.{k}")
            if r:
                return r
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: 長さ {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            r = diff(x, y, f"{path}[{i}]")
            if r:
                return r
        return None
    return None if a == b else f"{path}: {a!r} != {b!r}"
