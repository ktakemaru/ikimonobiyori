"""段階72 第1部: Claude Code の Stop フックの入口(.claude/settings.json の hooks.Stop から起動)。
本体は ikimonobiyori/stop_hook.py。どんな失敗でも終了コード 0 で通す(応答全体を止めない)。"""
import sys
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ikimonobiyori import stop_hook
except Exception:                                        # 読み込めないときは通す
    sys.exit(0)

if __name__ == "__main__":
    sys.exit(stop_hook.main())
