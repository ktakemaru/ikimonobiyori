"""実行設定(ikimonobiyori/config.yaml)の読み込み。"""
from pathlib import Path


from . import yamlcache
from .paths import CONFIG_PATH  # noqa: E402  (パッケージの中。段階12)


def load_config(path=None):
    return yamlcache.load(Path(path or CONFIG_PATH))
