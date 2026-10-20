"""応答のキャッシュ層。キー = URL と並べ替えたパラメータの sha256。保存するのは応答本文・fetched_at・出典名・URL。
有効期間(TTL)は設定(ikimonobiyori/config.yaml)で持つ。保存先は <IKIMONOBIYORI_DATA_DIR>/cache/(既定 runtime/ikimonobiyori/cache/。snapshots/ は最終出力用)。
書き込みは一時ファイルからの置き換え(原子的)。通信はしない。"""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

SCHEMA = "ikimono-cache/1"


def cache_key(url, params=None):
    """URL とパラメータ(並べ替える)の sha256。クエリ文字列の順序の違いで別のキーにならない。"""
    canon = json.dumps({"url": url, "params": sorted((str(k), str(v)) for k, v in (params or {}).items())},
                       ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


class Cache:
    def __init__(self, directory):
        self.dir = Path(directory)

    def path(self, key):
        return self.dir / f"{key}.json"

    def put(self, *, url, params, body, source, fetched_at):
        """fetched_at はオフセットつき ISO 8601 の文字列。body は応答本文(文字列)。"""
        datetime.fromisoformat(fetched_at)
        key = cache_key(url, params)
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f".{key}.tmp"
        tmp.write_text(json.dumps({"schema": SCHEMA, "key": key, "url": url, "params": params or {}, "source": source,
                                   "fetched_at": fetched_at, "body": body}, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8", newline="\n")
        os.replace(tmp, self.path(key))
        return key

    def get(self, url, params, *, now, ttl_s, allow_expired=False):
        """→ (entry, state)。state: 'fresh' / 'expired' / 'miss'。期限切れは allow_expired=True のときだけ entry を返す。"""
        p = self.path(cache_key(url, params))
        if not p.is_file():
            return None, "miss"
        try:
            e = json.loads(p.read_text(encoding="utf-8"))
            age = (now - datetime.fromisoformat(e["fetched_at"])).total_seconds()
        except (ValueError, KeyError):
            return None, "miss"
        if age <= ttl_s:
            return e, "fresh"
        return (e if allow_expired else None), "expired"
