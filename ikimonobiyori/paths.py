"""ファイルの場所を1か所にまとめる(段階12)。読むファイルはすべてこのパッケージの中、書き込み先は IKIMONOBIYORI_DATA_DIR の下。
- 読むもの: profiles/・data/・config.yaml・schemas/(パッケージ自身の場所 Path(__file__).parent からの相対)
- 書くもの: キャッシュ・未解析の応答・部品・観察の記録。基準は環境変数 IKIMONOBIYORI_DATA_DIR。未設定なら、リポジトリにも
  実行用コピー(biyori-hub の runtime/)にも依存しない利用者ごとの 1 か所(段階37。利用者の承認 2026-11-01):
  Windows は %LOCALAPPDATA%\ikimonobiyori、それ以外は ~/.local/share/ikimonobiyori。
  以前の既定(<リポジトリ>/runtime/ikimonobiyori)と biyori-hub の runtime-data/ikimonobiyori の記録は migrate_data で写す。
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
REGIONS_PATH = DATA_FILES_DIR / "regions.yaml"                  # 地域の呼び名 → 名所カタログの条件・範囲の代表点(段階16 B-4)
LEGACY_DATA_DIR = PKG.parent / "runtime" / "ikimonobiyori"       # 段階36までの既定(移行の元。migrate_data だけが読む)
ENV_DATA_DIR = "IKIMONOBIYORI_DATA_DIR"
APP_DIR_NAME = "ikimonobiyori"


def default_data_dir(env=None, os_name=None, home=None):
    """IKIMONOBIYORI_DATA_DIR が無いときの書き込み先(段階37): Windows は %LOCALAPPDATA%\ikimonobiyori
    (LOCALAPPDATA が無ければ ~/AppData/Local/ikimonobiyori)、それ以外は ~/.local/share/ikimonobiyori。"""
    e = os.environ if env is None else env
    home = Path(home) if home else Path.home()
    if (os_name or os.name) == "nt":
        base = e.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / APP_DIR_NAME
    return home / ".local" / "share" / APP_DIR_NAME


def data_dir(env=None, os_name=None, home=None):
    """書き込み先の基準。IKIMONOBIYORI_DATA_DIR(空なら未設定と同じ)→ 利用者ごとの既定。"""
    v = (os.environ if env is None else env).get(ENV_DATA_DIR)
    return Path(v) if v else default_data_dir(env, os_name, home)


def data_path(rel, env=None):
    """config.yaml の相対パス(cache.dir など)→ 書き込み先の絶対パス。"""
    return data_dir(env) / rel
