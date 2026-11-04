"""同じ YAML を何度も読み直さないための小さな入れ物(段階46: テストの時間を減らす)。
PyYAML の safe_load は大きいファイルで 0.3 秒ほどかかり、1 回の処理で何百回も呼ばれていた。
(パス, 更新時刻, 大きさ)ごとに 1 回だけ読み、呼ぶたびに deepcopy を返す(呼び出し側が書き換えても、次の呼び出しに影響しない。
読み直した場合と同じ値)。ファイルが変わった(更新時刻・大きさが違う)ら、読み直す。"""
import copy
from pathlib import Path

import yaml

_CACHE = {}


def load(path):
    p = Path(path)
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key not in _CACHE:
        for k in [k for k in _CACHE if k[0] == key[0]]:
            del _CACHE[k]
        _CACHE[key] = yaml.safe_load(p.read_text(encoding="utf-8"))
    return copy.deepcopy(_CACHE[key])
