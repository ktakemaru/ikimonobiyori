"""プロファイル(YAML)と地点カタログの読み込み。閾値はここ経由でだけ取り出す。"""
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .paths import PROFILE_DIR, PROFILE_SCHEMA_PATH as SCHEMA_PATH, SITES_PATH  # noqa: E402,F401  (パッケージの中。段階12)


class ProfileError(ValueError):
    pass


def validate_profile(doc):
    v = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    return ["/".join(map(str, e.path)) + ": " + e.message[:120] for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path))]


def load_profiles(directory=None):
    """{profile_id: profile}。スキーマに通らないものは ProfileError。"""
    out = {}
    for p in sorted(Path(directory or PROFILE_DIR).glob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
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
    doc = yaml.safe_load(Path(path or SITES_PATH).read_text(encoding="utf-8"))
    return {s["id"]: s for s in doc["sites"]}, doc
