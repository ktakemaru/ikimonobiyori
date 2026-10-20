# イキモノビヨリ (ikimonobiyori)

「今週末、紅葉は見頃か」「この時期、この場所でよく見られる野鳥は」を、**公開データだけ**から決まった式で答える、自然観察向けの下調べツール。
〇〇ビヨリ(ヤマビヨリ・ホシビヨリなど)の仲間で、共通の契約 `biyori-proposal/1`(提案)をそのまま出力する。
個人・非商用の利用が前提で、**v0 は 紅葉 と 野鳥 だけが実装済み**(桜・彼岸花・ひまわり・ホタル・ホタルイカ・夜光虫のプロファイルは骨組みのみ。`not_applicable: profile_skeleton` を返す)。

> **v0 の判定はすべて未検証です(`validated: false`)。** `go`(行ける)は出さず、上限は `maybe`(行けるかもしれない)です。
> 紅葉の目安(最低気温 8℃・6℃)は非公式の言い伝えで、種・地域差が大きく、気象庁などの基準ではありません。確信度の数値は出力しません(`null`)。

## 何をするか

| 対象 | 入力 | 判定の方法 | 出力 |
|---|---|---|---|
| 紅葉 | Open-Meteo の日最低気温(山・山域の 76 地点) | 直近の日最低気温の平均から、色づき前/色づき始め/見頃を決める(`temperature_progression`) | 地点 × 日ごとの提案(段階 `phenology_stage`、`band`) |
| 野鳥 | iNaturalist の観察記録の集計(場所 × 対象日の前後 × 過去 5 年) | 種ごとの相対頻度 = 種の件数 ÷ 鳥類の観察記録の総数(`observation_frequency`)。記録が少ない場所は提案を出さない | 場所ごとの上位の種(相対頻度 0〜1。他のビヨリの点数とは比べない) |

- **数値はコードが作る**。閾値・係数・窓・年数はプロファイル `ikimonobiyori/profiles/*.yaml` の `method.params` にだけ書き、コードに直接書かない(テストが検査する)。各値に出典または理由と、暫定かどうか(`provisional`)を付ける。
- 野鳥は**場所を粗く丸める**(小数 1 桁 ≒ 10 km)。正確な座標、観察者、写真は保存も出力もしない。出力に「巣やねぐらに近づかない」などのマナー(`care`)を付ける。
- 時刻は ISO 8601(オフセットつき)。欠損は 0 で埋めず `null`。

## 出典と利用条件

- **Open-Meteo**(紅葉の気温): 非商用の無料枠(1 日 10,000 call)の範囲で使う。CC BY 4.0 の帰属表示:
  *Weather data by [Open-Meteo.com](https://open-meteo.com/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)*
  (`tests/fixtures/recorded_open_meteo_2026-10-14.json` は、2026-10-14 に取得した実際の応答の記録で、同じ帰属を付けている)。
- **iNaturalist**(野鳥の観察記録): 公開 API から集計値(種ごとの件数と分類名)だけを取る。**利用規約・API の推奨手順は、まだ人の目で確認していません**
  (二次的な要約のみ。`docs/ikimonobiyori-research.md` §12「要目視」)。投稿コンテンツの既定ライセンスは CC BY-NC の可能性があるが、個別記録のライセンスは未確認。
  そのためこのリポジトリには iNaturalist の実際の応答を置かず、テストは合成データ(`tests/fixtures/synthetic_*.json`)で行う。**確認が済むまで、用途を個人・非商用の下調べに限る。**
  通信するときの自主制限: 30 リクエスト/分以下(間隔 2 秒以上)、429・4xx・5xx で即中止、User-Agent にアプリ名を付ける。
- **地点カタログ**(`ikimonobiyori/data/sites.yaml`): [yamabiyori](https://github.com/ktakemaru/yamabiyori)(MIT)の山リスト(`MOUNTAINS`、commit `de66f10`)を一度だけ複製したもの。複製元は `copied_from` に記録。

## biyori-hub との関係

[biyori-hub](https://github.com/ktakemaru/biyori-hub) は、ヤマビヨリ・ホシビヨリと同じように、このリポジトリを**固定 commit で取り込み(`vendor.lock`)**、manifest 1 枚で窓口(コンシェルジュ)に登録する。

- このリポジトリは**ハブのコードもデータも参照しない**(テストが検査する)。ハブ側の `adapters/ikimonobiyori_run.py` が、取り込んだコードを子プロセスで起動し、提案を契約で検査し、部品を合成する。
- 契約 `biyori-proposal/1` の正本はハブの `schemas/` にある。`tests/contract/biyori-proposal.schema.json` はその**写し**(検査用。`tests/contract/README.md`)。
- 窓口の最終文・独立検査器・定期実行・計測フックはハブの仕事。窓口との統合のテストはハブ側にある。
- 書き込み先(キャッシュ・読めなかった応答・部品)は、環境変数 **`IKIMONOBIYORI_DATA_DIR`** で指定する(ハブは必ず渡す)。未設定なら `<リポジトリ>/runtime/ikimonobiyori/`(`.gitignore` 済み)。取り込んだコードのフォルダには何も書かない。

## 使い方

Python 3.13 で確認。

```
python -m pip install -r requirements.txt

# オフライン(入力 JSON = ikimono-inputs/1。tests/fixtures/synthetic_inputs.json は合成)
python -X utf8 ikimonobiyori/main.py --request REQ.json --inputs tests/fixtures/synthetic_inputs.json --now 2026-10-14T22:00:00+09:00

# 6b で行う問い合わせの一覧(通信なし)
python -X utf8 ikimonobiyori/main.py --request REQ.json --plan-queries --now 2026-10-14T22:00:00+09:00

# キャッシュだけから(通信しない)
python -X utf8 ikimonobiyori/main.py --request REQ.json --cache-only --now 2026-10-14T22:00:00+09:00
```

`REQ.json` は依頼 `biyori-request/1`(`interests` に `autumn_leaves` か `birds`)。`--now` は必須(オフセットつき)で、同じ入力・同じ `--now` なら同じ出力になる。

**実通信(`--live`)は、このリポジトリ単独では実行できない。** 次のすべてが要る: 環境変数 `BIYORI_ALLOW_LIVE=1`、明示的な `--max-requests`、
そして通信の記録・上限・許可ホストを強制する**計測フック**(環境変数 `BIYORI_REQ_LOG`。biyori-hub の `hub/measure/`)。
単独で使うための別の上限の仕組みは、まだ作っていない。`BIYORI_UNDER_TEST=1`(テスト中)なら、`BIYORI_ALLOW_LIVE` に関わらず常に拒否する。

## テスト

```
python -X utf8 -m unittest discover -s tests
```

通信は一切しない(ソケットは `tests/nonet.py` で禁止、子プロセスも禁止)。GitHub Actions(`.github/workflows/ci.yml`)が Linux と Windows で同じコマンドを実行する。

## ファイル構成

- `ikimonobiyori/` パッケージ。`engine.py`(依頼 + 入力 + プロファイル → 提案)、`methods/`(手法)、`fetch/`(パーサー・キャッシュ・取得層)、`compose.py`(紅葉と野鳥の部品の合成)、`main.py`(CLI)
  - `profiles/` 対象ごとのプロファイル(閾値・出典・マナー)、`data/` 地点カタログと調査の定義、`config.yaml` 取得層の運用値(許可ホスト・間隔・再試行・有効期間)、`schemas/` プロファイルのスキーマ
  - `paths.py` ファイルの場所(読むものはパッケージの中、書くものは `IKIMONOBIYORI_DATA_DIR` の下)、`livegate.py` 実通信の許可の判定
- `docs/` 調査・対応表・検証計画(設計の記録。biyori-hub の中にあったときの記述が残る)
- `tests/` テスト。`tests/fixtures/` は合成データと、Open-Meteo の記録、ゴールデン(`golden/`)

## ライセンス

[MIT](LICENSE)。データの出典は上記のとおり(Open-Meteo は CC BY 4.0、iNaturalist は未確認)。
