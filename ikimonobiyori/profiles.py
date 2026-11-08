"""プロファイル(YAML)と地点カタログの読み込み。閾値はここ経由でだけ取り出す。"""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from . import yamlcache
from .paths import PROFILE_DIR, PROFILE_SCHEMA_PATH as SCHEMA_PATH, SITES_PATH  # noqa: E402,F401  (パッケージの中。段階12)


class ProfileError(ValueError):
    pass


_VALIDATED = {}


def validate_profile(doc):
    """スキーマの誤りの一覧。同じスキーマ・同じ中身の検査は 1 回の実行で 1 回だけ行う(段階63b 第1部。結果は同じ)。"""
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")

    def run():
        v = Draft202012Validator(json.loads(schema_text))
        return ["/".join(map(str, e.path)) + ": " + e.message[:120] for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path))]
    try:
        key = (schema_text, json.dumps(doc, sort_keys=True, ensure_ascii=False))
    except (TypeError, ValueError):                     # JSON にできない値(数と文字のキーが混ざるなど)は毎回検査する
        return run()
    if key not in _VALIDATED:
        _VALIDATED[key] = run()
    return list(_VALIDATED[key])


def load_profiles(directory=None):
    """{profile_id: profile}。スキーマに通らないものは ProfileError。"""
    out = {}
    for p in sorted(Path(directory or PROFILE_DIR).glob("*.yaml")):
        doc = yamlcache.load(p)
        errs = validate_profile(doc)
        if errs:
            raise ProfileError(f"{p.name}: {errs[0]}")
        out[doc["profile_id"]] = doc
    return out


def param(profile, name):
    """method.params から値を取る。無ければ ProfileError(コード側に既定値を持たない)。"""
    for q in profile["method"].get("params") or []:
        if q["name"] == name:
            return q["value"]
    raise ProfileError(f"{profile['profile_id']}: パラメータ {name} がない")


def provisional_params(profile):
    return [{"name": q["name"], "value": q["value"], "unit": q.get("unit"), "source": q.get("source"), "reason": q.get("reason")}
            for q in profile["method"].get("params") or [] if q.get("provisional")]


def load_sites(path=None):
    doc = yamlcache.load(Path(path or SITES_PATH))
    return {s["id"]: s for s in doc["sites"]}, doc
