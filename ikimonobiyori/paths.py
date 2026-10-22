"""ファイルの場所を1か所にまとめる(段階12)。読むファイルはすべてこのパッケージの中、書き込み先は IKIMONOBIYORI_DATA_DIR の下。
- 読むもの: profiles/・data/・config.yaml・schemas/(パッケージ自身の場所 Path(__file__).parent からの相対)
- 書くもの: キャッシュ・未解析の応答・部品。基準は環境変数 IKIMONOBIYORI_DATA_DIR。未設定なら、パッケージの親フォルダの
  runtime/ikimonobiyori(biyori-hub の中で動かしていたときと同じ場所。単独のリポジトリでは <リポジトリ>/runtime/ikimonobiyori)。
  config.yaml の cache.dir・cache.unparsed_dir・compose.component_dir は、この基準からの相対パス。
  vendor から動かすときは、呼び出し側が IKIMONOBIYORI_DATA_DIR を必ず渡す(vendor の中に書かない)。"""
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
PROFILE_DIR = PKG / "profiles"
DATA_FILES_DIR = PKG / "data"
SITES_PATH = DATA_FILES_DIR / "sites.yaml"
CONFIG_PATH = PKG / "config.yaml"
SCHEMA_DIR = PKG / "schemas"
PROFILE_SCHEMA_PATH = SCHEMA_DIR / "ikimono-profile.schema.json"
CATALOG_DIR = DATA_FILES_DIR / "catalog"                      # 名所カタログ(段階13。v0 の判定は使わない)
CATALOG_POLICY_PATH = CATALOG_DIR / "policy.yaml"
CATALOG_SCHEMA_PATH = SCHEMA_DIR / "site-catalog.schema.json"
JMA_PHENOLOGY_DEF_PATH = DATA_FILES_DIR / "jma_phenology.yaml"   # 気象庁 生物季節観測の CSV の読み方(段階13)。CSV そのものはパッケージの外(コマンドで明示)
BACKTEST_PLAN_PATH = DATA_FILES_DIR / "backtest_plan.yaml"          # 紅葉の答え合わせの計画と判定の基準(段階14。結果を見る前に決めた値。変えない)
SOURCES_DIR = DATA_FILES_DIR / "sources"                      # 現況を発信する公式ページの台帳(段階15。docs/design.md §0)
SOURCES_POLICY_PATH = SOURCES_DIR / "policy.yaml"
SOURCES_SCHEMA_PATH = SCHEMA_DIR / "status-sources.schema.json"
DEFAULT_DATA_DIR = PKG.parent / "runtime" / "ikimonobiyori"      # パッケージの外を指すのはここだけ(未設定のときの書き込み先の既定)
ENV_DATA_DIR = "IKIMONOBIYORI_DATA_DIR"


def data_dir(env=None):
    """書き込み先の基準。IKIMONOBIYORI_DATA_DIR(空なら未設定と同じ)→ 既定。"""
    v = (os.environ if env is None else env).get(ENV_DATA_DIR)
    return Path(v) if v else DEFAULT_DATA_DIR


def data_path(rel, env=None):
    """config.yaml の相対パス(cache.dir など)→ 書き込み先の絶対パス。"""
    return data_dir(env) / rel
