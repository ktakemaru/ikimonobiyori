"""同じ YAML を何度も読み直さないための、全モジュールの共通の読み込み口(段階46・段階63b 第1部)。

PyYAML の解析は大きいファイルで 0.3 秒ほどかかり、1 回の処理で何百回も呼ばれていた(段階63b の測定: ask facts で 1,264 回、ask verify で 1,418 回)。
- ファイルの中身(バイト列)ごとに 1 回だけ解析する。呼ぶたびにファイルを読み、中身が同じなら前の解析結果を使う
  (更新時刻の分解能に頼らないので、書き換えた直後でも古い値を返さない)。
- 解析は libyaml(`yaml.CSafeLoader`)があればそれを使い、なければ純 Python の `yaml.SafeLoader`(どちらも PyYAML の標準の機能)。
  結果が同じことは tests/test_stage63b.py が data 以下の全 YAML で確かめる。
- 呼ぶたびに新しい写しを返す(呼び出し側が書き換えても、次の呼び出しに影響しない。読み直した場合と同じ値)。
  写しは pickle の往復で作る(YAML の値は dict・list・文字列・数値・真偽・None だけなので deepcopy と同じ値。
  deepcopy は 1 回の ask facts で約 78 万回呼ばれ、いちばん重かった)。"""
import hashlib
import pickle
import time
from pathlib import Path

import yaml

LOADER = getattr(yaml, "CSafeLoader", None) or yaml.SafeLoader

_CACHE = {}


def parse(text):
    """YAML の文字列 → 値(safe_load と同じ。解析器は LOADER)。"""
    return yaml.load(text, Loader=LOADER)


_STAT = {}
SETTLED_S = 2.0            # 更新から 2 秒より前のファイルは、更新時刻と大きさが同じなら中身を読み直さない(書き換えた直後は中身で確かめる)


def load(path):
    """YAML のファイル → 値。ファイルがなければ FileNotFoundError(read_text と同じ)。"""
    p = Path(path)
    st = p.stat()
    sk = (st.st_mtime_ns, st.st_size)
    prev = _STAT.get(str(p))
    if prev and prev[0] == sk and time.time() - st.st_mtime > SETTLED_S and prev[1] in _CACHE:
        return pickle.loads(_CACHE[prev[1]])
    raw = p.read_bytes()
    key = (str(p), hashlib.blake2b(raw, digest_size=16).digest())
    if key not in _CACHE:
        for k in [k for k in _CACHE if k[0] == key[0]]:
            del _CACHE[k]
        _CACHE[key] = pickle.dumps(parse(raw.decode("utf-8")), protocol=pickle.HIGHEST_PROTOCOL)
    _STAT[str(p)] = (sk, key)
    return pickle.loads(_CACHE[key])
