"""テストが起動する子プロセスの通信を禁止する(PYTHONPATH にこのフォルダを足した子プロセスだけで有効)。
tests/nonet.py はプロセス内のソケット禁止なので子プロセスに及ばない。5b で子プロセスから実通信が走ったための再発防止。"""
import socket


def _blocked(*a, **k):
    raise AssertionError("テストの子プロセスで通信が試みられた(禁止)")


socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
