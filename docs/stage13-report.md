# 段階13「調べて決める」報告書

作業指示書: `biyori-hub_stage13_instructions.md`(2026-10-21)。ブランチ `stage13`(main の `add784e` から)。判断の記録は `docs/stage13-decisions.md`。

## フェーズ 0: 現状の確認(読むだけ)

確認日時: 2026-10-21

### 0-1. リポジトリの状態
- HEAD: `add784e`(main)。作業ツリーはきれい(未コミットの変更なし)。ブランチ `stage13` を作成。
- テストの基準値: **`Ran 138 tests` / `OK`**。
  - 注意: この PC の既定の `python`(3.13.15)には `jsonschema`・`PyYAML` が入っておらず、そのままでは 7 モジュールすべてが import エラー(`FAILED (errors=7)`)。
    パッケージを入れる通信は許可の範囲外なので、biyori-hub の既存の仮想環境 `C:\biyori-hub\.venv-hub`(Python 3.13.15、`requirements.txt` と同じ版の jsonschema 4.26.0 など)でテストを実行した(判断 D-01)。以降のテストの件数はすべてこの環境での値。

### 0-2. プロファイル(`ikimonobiyori/profiles/*.yaml`)
| profile_id | status | category | method.kind | care.location_precision | 備考 |
|---|---|---|---|---|---|
| autumn_leaves | implemented | seasonal_progression | temperature_progression | exact | params: start 8 / advance 6 / strong 5 ℃、mean_window_days 7、progress_shape linear(すべて provisional) |
| birds | implemented | observation_record | observation_frequency | area_10km | params: window_weeks 1、history_years 5、min_total_observations 30、maybe_min_relative_frequency 0.05 など |
| cherry_blossom | skeleton | seasonal_progression | gdd_accumulation | exact | |
| higanbana | skeleton | (骨組み) | | | |
| sunflower | skeleton | (骨組み) | | | |
| fireflies | skeleton | occurrence_event | event_occurrence | area_1km | |
| bioluminescence | skeleton | (骨組み) | | | |

共通の項目: `profile_id, name, category, validated, status, interests, season{months, months_source, note, out_of_season_rule}, method{kind, description, params[], band_map}, data_sources, confidence, care{location_precision, do_not_disclose_exact_location, manners}, known_limits`。
実装済みの2つはさらに `scale, stage_order, band_policy, phenology_labels`(紅葉)、`score_explain`(野鳥)、`pairing_hint`(紅葉)。
スキーマ `ikimonobiyori/schemas/ikimono-profile.schema.json` は `additionalProperties: true`。biyori-hub の `hub/validate.py:67` はこの ikimono 自身のスキーマでプロファイルを検証する(ハブ側に別の写しはない)。

### 0-3. `ikimonobiyori/data/sites.yaml`
- `schema: ikimono-sites/1`。`copied_from`: yamabiyori `mountain_weather_core.py` の `MOUNTAINS`(commit `de66f10`)を 2026-10-14 に一度だけ複製。
- `sites`: **76 地点、すべて `kind: mountain`**(関東甲信 63・北陸信越 6・東北南部 6・伊豆 1)。項目は `id, name, lat, lon, elevation_m, region, kind, site_ref`。
- **座標・標高が何を表すか**: ファイルの中に「山頂」と明記した記述はない。ただし `kind: mountain`、名前が山名(谷川岳・八ヶ岳(赤岳)・高尾山…)、標高が山頂の標高と一致する値(高尾山 599 m、谷川岳 1977 m、赤岳 2899 m、富士山 3776 m。範囲 599〜3776 m)なので、**山頂の座標と標高と読める(推測。ファイルの中の記述からの読み取り)**。紅葉プロファイルの `known_limits` に「気温は Open-Meteo の格子の標高のもので、山頂の標高とは異なり」とあり、既存の文書も山頂として扱っている。
- `bird_areas`: 3 件(karuizawa〔`active: false`, sparse_records〕・kasai・yatsu)。項目は `id, name, lat, lon(小数1桁に丸めた値), radius_km 10, location_precision: area_10km, status: approved, provisional: true, note` など。

### 0-4. Open-Meteo への問い合わせの作り方(段階14の前提)
- 問い合わせ URL を作るのは **`ikimonobiyori/fetch/open_meteo.py:13-16` の `daily_query()`** だけ。渡す引数は `latitude, longitude, daily=temperature_2m_min, past_days, forecast_days, timezone=Asia/Tokyo` で、**`elevation` は渡していない**。エンドポイントは `https://api.open-meteo.com/v1/forecast`(`open_meteo.py:10`)。
- 呼び出し元は `ikimonobiyori/fetch/live.py:200`(`open_meteo.daily_query(lat=s["lat"], lon=s["lon"], past_days=past, forecast_days=ahead)`)。地点の `elevation_m` は使っていない(`grep elevation` で fetch/ に該当なし)。
- 記録済みのフィクスチャ `tests/fixtures/recorded_open_meteo_2026-10-14.json` の `temperatures_meta.*.url` で、実際に送られた URL を確認した。例(高尾山 m029):
  `https://api.open-meteo.com/v1/forecast?latitude=35.6253&longitude=139.2436&daily=temperature_2m_min&past_days=3&forecast_days=5&timezone=Asia%2FTokyo` — `elevation` なし。
- 応答の `elevation`(Open-Meteo が気温の計算に使った標高)と、カタログの山頂の標高の比較:

  | 地点 | カタログ elevation_m | 応答 elevation | 差 | 応答の座標 |
  |---|---|---|---|---|
  | 高尾山 m029 | 599 | 598.0 | −1 | 35.65, 139.25 |
  | 谷川岳 m001 | 1977 | 1920.0 | −57 | 36.85, 138.9375 |
  | 八ヶ岳(赤岳) m002 | 2899 | 2599.0 | −300 | 36.0, 138.375 |

  → 今の v0 の気温は、**Open-Meteo が自分の標高データで決めた標高**のもので、山頂とも「見る場所」とも一致しない(赤岳は 300 m 低い)。Open-Meteo の `elevation` 引数の仕様はフェーズ 1 で公式文書を読んで `docs/data-sources.md` に記録する。

### 0-5. ゴールデンテスト
- 場所: `tests/test_golden.py`(テスト)、`tests/golden.py`(作り方と比較の規則)、`tests/fixtures/golden/`(7 件: g1_synthetic_autumn / g1_synthetic_birds / g1_synthetic_both / g2_recorded_autumn / g4_child_autumn_leaves / g4_child_birds / g4_composed)。
- 現在すべて通る(上の 138 件に含まれる)。

## フェーズ 1: 設計とデータ源の文書化

- `docs/design.md`: 付録 A をもとに、役割の分担・共通の枠組み・時期の5つの型・対象別の仕様・名所カタログ(1件の形・承認の流れ・76 地点との関係)・検証方針・段階計画を整理。付録 A にない事実は足していない。
- `docs/data-sources.md`: データ源ごとの使いみち・取り方・利用条件・出典表示・確認日・確認した URL。読んだのは 11 ページ(上限 30)。
  - 気象庁: 公共データ利用規約(第1.0版)に準拠。規約は「複製、公衆送信、翻訳・変形等の翻案等、自由に利用できます」「商用利用も可能」、CC BY 4.0 と互換。出典と加工したことの記載が要る。**public に置けると読めるが、要約経由でしか読めず、はっきりとは確認できなかった → 置かない(D-03)**。付録 B の「自動巡回は控える」の記述は、読んだ範囲では見つからなかった(要目視)。フォーマットの PDF は本文を取り出せなかった(要目視)。
  - CSV の入口は `https://www.data.jma.go.jp/sakura/data/download_ruinenchi.html`(index.html からリンク)。対象の CSV は `ruinenchi/015.csv`(かえで紅葉)・`016`(かえで落葉)・`013`(いちょう黄葉)・`014`(いちょう落葉)・`004`(さくら開花)・`005`(さくら満開)・`001`(うめ開花)。
  - Open-Meteo: 無料 API は非商用のみ、600/分・5,000/時・10,000/日・300,000/月。データは CC BY 4.0。**2 週を超える期間・10 を超える変数は 1 リクエストでも複数 call と数える**(端数あり)。過去データには「Generated using Copernicus Climate Change Service information 2022.」の表示も要る。`elevation` は既定で 90 m の標高データ、指定可、`nan` で格子平均。
  - iNaturalist: 規約・推奨手順とも **HTTP 403 で読めなかった → 要目視(ユーザー)**。既存の扱いを変えない。
  - 環境省の報道発表(109419)は、いきものログによる生物季節の試行調査の発表で、植生図・ライセンスの記述はなかった。
- README に2つの文書へのリンクを追加。

## フェーズ 2: 名所カタログと時期の型のスキーマ

- スキーマ `ikimonobiyori/schemas/site-catalog.schema.json`(`ikimono-site-catalog/1`)。置き場所はパッケージの中(D-06)。
  - 必須: `id, name, subjects, timing_type, kind, location_precision, status, sources`(出典 URL が1つ以上)。`status: approved` なら `approved_at` も必須。
  - `timing_type`: temperature / calendar / managed / frequency / episodic。`kind`: point / area / river / coast。`location_precision`: exact / area_1km / area_10km。`status`: candidate / approved / retired。
  - `typical_window` は `start`・`end`(MM-DD。年またぎは start > end)・`source_url` がすべて必須 = 出典のない例年値は通らない。
  - `site_ref` は `yamabiyori:` / `hoshibiyori:` / `ikimonobiyori:` + id。`public_venue{source_url}`(公式の観賞会場)、`sensitive`(希少種)、`example`(実在しない例)を追加。
- 方針 `ikimonobiyori/data/catalog/policy.yaml`: 位置の粗さの下限(既定 exact、野鳥・ホタル area_10km)、公開会場の例外はホタルだけ、希少種は area_10km 以上、座標の桁の上限(area_10km は小数1桁、area_1km は2桁)。(D-07〜D-09)
- 検査器 `ikimonobiyori/catalog.py`: `python -X utf8 -m ikimonobiyori.catalog check [--catalog-dir] [--profiles-dir] [--policy]`。スキーマ+スキーマで見られない規則(未知の対象、ファイル名と subject の不一致、id の重複、位置の下限、座標の桁、存在しない日付、例の approved)。プロファイルは ikimono-profile/1 + `timing_type` の有無。
  - `usable_description(entry)`: approved で approved_at と sources がそろい、例でないときだけ解説を返す。`approved_entries(doc)`: 提案に使ってよい件。**v0 のエンジンはどちらも使わない**(テストで確認)。
- プロファイル 7 つに `timing_type` を追加(紅葉・桜・ホタル temperature、野鳥 frequency、彼岸花 calendar、ひまわり managed、夜光虫 episodic)。プロファイルのスキーマに任意項目として追加(項目の追加のみ)。ハブの `hub/validate.py` は ikimono 自身のスキーマで検証するので、ハブ側の変更は要らない。
- 例: `ikimonobiyori/data/catalog/autumn_leaves.yaml` に `status: candidate`・`example: true` の2件(座標・例年値・URL は example.org の例)。
- テスト `tests/test_catalog.py`(21 件): 正しい例が通る/出典のない例年値・存在しない日付・未知の timing_type 等・出典なし・approved_at なし・例の approved・野鳥とホタルの細かすぎる位置・座標の桁・公開会場の例外・希少種・複数対象・未知の対象・重複などがすべて拒否される。
- テスト: 138 → **159 件 OK**。ゴールデンは変わらず通る。`ikimonobiyori.catalog check` は全ファイル OK。
