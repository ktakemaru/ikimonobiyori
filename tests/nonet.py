"""テスト中のソケット通信を禁止する。import するだけで有効(プロセス全体)。通信が試みられたら AssertionError。"""
import os
import socket

_REAL = {"connect": socket.socket.connect, "connect_ex": socket.socket.connect_ex,
         "create_connection": socket.create_connection, "getaddrinfo": socket.getaddrinfo}


def _blocked(*a, **k):
    raise AssertionError("テスト中にネットワーク通信が試みられた(禁止)")


def block():
    socket.socket.connect = _blocked
    socket.socket.connect_ex = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked


block()


# 実通信の許可を、テストでは常に取り除く(子プロセスに引き継がれる)。ゲート(hub/livegate.py)は BIYORI_UNDER_TEST=1 なら常に拒否する
os.environ.pop("BIYORI_ALLOW_LIVE", None)
os.environ["BIYORI_UNDER_TEST"] = "1"
# テスト専用の時計(ikimonobiyori.sources.read_time。段階23)。このプロセスだけ。子プロセス(helpers.child_env)には渡さない = 子プロセスはふだんの実行と同じく、渡された時刻を使わない
os.environ["IKIMONOBIYORI_TEST_CLOCK"] = "1"
