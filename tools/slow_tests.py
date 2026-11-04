"""全テストを実行して、テストごとの所要時間を測る(段階46)。使い方: python -X utf8 tools/slow_tests.py [tests のフォルダ] [上位の件数]
期待値は検査しない(unittest の結果をそのまま出す)。最後に、遅い順の上位と、モジュールごとの合計を出す。"""
import sys, time, unittest
from collections import defaultdict
from pathlib import Path

root = Path(__file__).resolve().parent.parent
tests_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "tests"
top = int(sys.argv[2]) if len(sys.argv) > 2 else 10


class Timed(unittest.TextTestResult):
    def startTest(self, test):
        self._t0 = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.times.append((time.perf_counter() - self._t0, test.id()))
        super().stopTest(test)


Timed.times = []
sys.path.insert(0, str(root))
sys.path.insert(0, str(tests_dir))
suite = unittest.defaultTestLoader.discover(str(tests_dir), top_level_dir=str(tests_dir))
t0 = time.perf_counter()
res = unittest.TextTestRunner(resultclass=Timed, verbosity=0, stream=sys.stderr).run(suite)
print(f"\n合計 {time.perf_counter() - t0:.1f} 秒, {res.testsRun} 件, 失敗 {len(res.failures)}, エラー {len(res.errors)}")
print(f"\n遅い順の上位 {top} 件:")
for sec, name in sorted(Timed.times, reverse=True)[:top]:
    print(f"  {sec:8.1f} 秒  {name}")
mods = defaultdict(float)
for sec, name in Timed.times:
    mods[name.split(".")[0]] += sec
print("\nモジュールごとの合計(上位):")
for name, sec in sorted(mods.items(), key=lambda x: -x[1])[:10]:
    print(f"  {sec:8.1f} 秒  {name}")
sys.exit(0 if res.wasSuccessful() else 1)
