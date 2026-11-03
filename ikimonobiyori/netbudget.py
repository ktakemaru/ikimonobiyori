"""単体で実通信するときの小さな上限(段階38。利用者の決定 2026-11-01。指示書 docs/stage38-instructions.md 2-1)。

イキモノビヨリが単体で(biyori-hub の計測フックなしで)iNaturalist の集計と写真を取りに行くときの安全弁:
- 1 回の実行の上限(集計は observations の inat_refresh.max_requests_per_question、写真は guide の photos.max_requests_per_run)。
  上限に達したら、送る前に止める(BudgetError)。
- 同じホストへの間隔は min_interval_s 以上(送る前に待つだけ)。
- 通信先は config.yaml の live.allowed_hosts_by_subject の宣言済みホストだけ(ほかは送る前に止める)。
- 実行ごとの記録(時刻・種類・ホスト・回数・状態コード。座標・本文・URL のクエリは残さない)を
  IKIMONOBIYORI_DATA_DIR の下の netlog/requests.jsonl に追記する。

ハブから呼ばれる(計測フック BIYORI_REQ_LOG がある)ときは、記録はハブの計測フックのもの(mode "hook")。
このとき BIYORI_ALLOW_LIVE=1 が要る(従来どおり)。上限・間隔・許可ホストの判定は、どちらのときもここでも行う。
テスト中(BIYORI_UNDER_TEST=1)は常に拒否する(livegate)。値はコードに持たず、呼び出し側が方針ファイルから渡す。"""
import json
import os
import time
from datetime import datetime
from urllib.parse import urlsplit

from . import livegate
from .fetch.live import LiveError
from .paths import data_path

LOG_FILE = "netlog/requests.jsonl"


class BudgetError(LiveError):
    """上限・許可ホストの外(送る前に止めた)。"""


def mode(env=None):
    """"hook"(計測フックがある)か "self"(単体)。"""
    e = os.environ if env is None else {**os.environ, **env}       # env は書き込み先などの差し替え。計測フックの有無は親の環境も見る
    return "hook" if e.get("BIYORI_REQ_LOG") else "self"


def refusal(env=None, *, need_allow=False):
    """単体の取得(ask の手順)を拒否する理由。許すなら None。
    テスト中は常に拒否。計測フックの下では BIYORI_ALLOW_LIVE=1 が要る(従来どおり)。
    単体(計測フックなし)では、ask の手順は利用者の決定(2026-11-01)で許す。need_allow=True(直接の --live コマンド)は BIYORI_ALLOW_LIVE=1 が要る。"""
    if livegate.under_test(env):
        return livegate.refusal(env)
    if mode(env) == "hook" or need_allow:
        return livegate.refusal(env)
    return None


def log_path(env=None):
    return data_path(LOG_FILE, env)


def read_log(env=None):
    p = log_path(env)
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


class Budget:
    """http_get を包む。budget(fn) → 同じ呼び方の関数(url, *rest)。
    kind: 記録の種類(inat_counts・photos など)。hosts: 許可ホスト。max_requests: この実行の上限。min_interval_s: 同じホストへの間隔。"""

    def __init__(self, kind, hosts, max_requests, min_interval_s, *, env=None, clock=time.monotonic, sleep=time.sleep, wall=None):
        if max_requests is None or max_requests < 1:
            raise ValueError("max_requests (1 以上)が必要")
        self.kind = kind
        self.hosts = {h.lower() for h in hosts}
        self.max_requests = int(max_requests)
        self.min_interval_s = float(min_interval_s)
        self.env = env
        self.clock = clock
        self.sleep = sleep
        self.wall = wall or (lambda: datetime.now().astimezone().replace(microsecond=0))
        self.mode = mode(env)
        self.used = 0
        self.last = {}
        self.run_id = self.wall().isoformat()
        self.entries = []

    def left(self):
        return self.max_requests - self.used

    def check(self, url):
        host = (urlsplit(url).hostname or "").lower()
        if host not in self.hosts:
            raise BudgetError(f"許可されていないホストには送らない: {host}")
        if self.used >= self.max_requests:
            raise BudgetError(f"1 回の実行の上限 {self.max_requests} に達したため送らない")
        return host

    def _log(self, host, status):
        row = {"at": self.wall().isoformat(), "run": self.run_id, "kind": self.kind, "mode": self.mode, "host": host,
               "n": self.used, "max": self.max_requests, "status": status}
        self.entries.append(row)
        if self.mode != "self":                       # ハブの計測フックの下では、記録はハブのもの
            return
        p = log_path(self.env)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def __call__(self, fn):
        def wrapped(url, *rest, **kw):
            host = self.check(url)
            prev = self.last.get(host)
            if prev is not None:
                wait = self.min_interval_s - (self.clock() - prev)
                if wait > 0:
                    self.sleep(wait)
            self.used += 1
            self.last[host] = self.clock()
            try:
                res = fn(url, *rest, **kw)
            except Exception:
                self._log(host, "error")
                raise
            self._log(host, res[0] if isinstance(res, tuple) and res else None)
            return res
        return wrapped

    def summary(self):
        return {"kind": self.kind, "mode": self.mode, "requests": self.used, "max_requests": self.max_requests,
                "hosts": sorted({e["host"] for e in self.entries}),
                "statuses": sorted({str(e["status"]) for e in self.entries})}
