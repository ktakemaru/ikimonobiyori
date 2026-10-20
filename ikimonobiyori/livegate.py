"""実通信(--live)の許可の判定(段階12。biyori-hub の hub/livegate.py と同じ判定を自分で持つ。標準ライブラリだけ)。
- BIYORI_ALLOW_LIVE=1 が要る(その実行のときだけ設定する)。
- BIYORI_UNDER_TEST=1(テスト中)なら、環境変数 BIYORI_ALLOW_LIVE の値に関わらず常に拒否する。
  env を引数で渡されても、親プロセス(os.environ)が UNDER_TEST なら拒否する(テストが環境を上書きしても通らない)。
判定が hub/livegate.py と同じであることは、ハブ側のテストが両方に同じ環境を与えて確かめる。"""
import os


def under_test(env=None):
    return os.environ.get("BIYORI_UNDER_TEST") == "1" or (env or {}).get("BIYORI_UNDER_TEST") == "1"


def live_allowed(env=None):
    e = os.environ if env is None else env
    return e.get("BIYORI_ALLOW_LIVE") == "1" and not under_test(env)


def refusal(env=None):
    """拒否の理由(メッセージ)。許可されているなら None。"""
    if under_test(env):
        return "テスト中(BIYORI_UNDER_TEST=1)は --live を常に拒否します。BIYORI_ALLOW_LIVE=1 があっても実行しません"
    if (os.environ if env is None else env).get("BIYORI_ALLOW_LIVE") != "1":
        return "--live は BIYORI_ALLOW_LIVE=1 がないと実行しません"
    return None
