"""実行設定(ikimonobiyori/config.yaml)の読み込み。"""
from pathlib import Path

import yaml

from .paths import CONFIG_PATH  # noqa: E402  (パッケージの中。段階12)


def load_config(path=None):
    return yaml.safe_load(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
