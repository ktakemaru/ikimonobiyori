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

## フェーズ 3: 気象庁の生物季節観測の取り込み

### 取得
- `https://www.data.jma.go.jp/sakura/data/download_ruinenchi.html`(index.html からリンク)の `ruinenchi/NNN.csv` を **2026-10-21 07:46〜07:47(JST)に一度だけ**取得(ファイルごとに 6 秒あける。再試行・ループなし)。7 ファイルすべて HTTP 200。記録は `data/jma_phenology/raw/SOURCES.md`(URL・日時・SHA-256)。
- 対象: かえで紅葉 015・かえで落葉 016・いちょう黄葉 013・いちょう落葉 014・さくら開花 004・さくら満開 005・うめ開花 001。**足りないものはない**。
- `raw/*.csv` と `normalized.csv` は `.gitignore`(D-03)。`raw/SOURCES.md` と `data/jma_phenology/README.md`(出典・加工の内容)だけを追跡する。

### 中身の確認(パーサーを書く前に)
- 文字コード: **cp932(Shift_JIS)**、改行 CRLF(フォーマットの PDF の断片とも一致)。
- 1行目: `番号,現象名,…`(例 `15,かえでの紅葉`)。2行目(見出し): `番号,地点名,1953,rm,1954,rm,…,2031,rm,2032,e,平年値,rm,最早値,rm,最早年,最晩値,rm,最晩年`(170 列)。**2032 年の rm の列名だけ `e`**(誤記と思われる。パーサーは列名を見ずに組として読む)。
- データ行: 102 地点(7 ファイルで同じ地点・同じ並び)。地点は **3 桁の番号と地点名**(全角空白で埋めてある。例 `662,東京　　`)。番号は国際地点番号 47NNN の下 3 桁と読める(推測)。
- 値: **月日を整数で `MMDD`**(例 `1125`、`926`)。値なしは **`0`(rm も `0`)** だけで、**欠測・観測なし・観測終了・未来の年の区別は CSV からは分からない**。
- rm: 値があるときは 4・6・7・8・9 のどれか。**意味は未確認**(フォーマットの PDF を読めなかった。要目視)。年代や地点によって偏る(例: 関東甲信のかえで紅葉 2016〜2025 年は、東京・銚子が 9、他は 8)。標本木の種の違いなどを表す可能性があるが**推測**。答え合わせでは rm ごとに分けて集計する案(`docs/validation-plan.md`)。
- **年をまたぐ値**: かえで・いちょうの落葉の列に 1〜2 月の値(かえで落葉 114 件)、うめ・さくらの列に 12 月の値(うめ 70 件)がある。季節の年の列に入っていると読み、春は前年・秋は翌年の日付にした(**推測**。PDF の断片「2015」「2014 12 15」「2015」「1215」とも合う)。関東甲信の本州の地点のかえで紅葉(2016 年以降)には年またぎはない。
- 値のある最後の年は 7 ファイルとも 2025 年。2026〜2032 年の列はすべて値なし(未来の年)→ 正規化で落とした。
- **座標・標高は含まれていない** → 座標なしで正規化(列は空)。答え合わせには気象官署の緯度・経度・標高の一覧が別に要る(気象庁の地点の一覧など。段階13 では取りに行かない)。

### 正規化
- コード `ikimonobiyori/jma_phenology.py`(通信しない。書くのは `--out` に明示したファイルだけ)、読み方の定義 `ikimonobiyori/data/jma_phenology.yaml`(現象・年またぎの月・CSV の形・関東甲信の 15 地点)。形が違えば `ParseError`。
- 出力 `data/jma_phenology/normalized.csv`(追跡しない): 列 `station_no, station_name, phenomenon_code, phenomenon, year, date, status(observed/no_value), rm, cross_year, lat, lon, elevation_m`。**52,122 行**(102 地点 × 73 年 × 7 現象)。
- テスト `tests/test_jma_phenology.py`(11 件。cp932 の合成データをテストの中で作る): 値・値なし・年またぎ(秋の 1 月 → 翌年、春の 12 月 → 前年)・未来の年を落とす・形の違い 11 通りの ParseError・元のファイルを変えない・`--out` だけに書く・件数のまとめ。
- テスト: 159 → **170 件 OK**。

### 関東甲信の件数のまとめ(1953〜2025 年の 73 年。「値あり/値なし〔値のある最初–最後の年〕」)
地点は地点名から選んだ 15(本州 12 + 伊豆諸島 3。都道府県の対応は外部の資料で確認していない)。値なしには欠測・観測なし・観測終了が混ざる。

| 地点 | kaede_koyo | kaede_rakuyo | icho_koyo | icho_rakuyo | sakura_kaika | sakura_mankai | ume_kaika |
|---|---|---|---|---|---|---|---|
| 610 長野 | 73/0〔1953–2025〕 | 72/1〔1954–2025〕 | 72/1〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 |
| 615 宇都宮 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 72/1〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 |
| 618 松本 | 54/19〔1953–2006〕 | 53/20〔1953–2006〕 | 53/20〔1953–2006〕 | 54/19〔1953–2006〕 | 55/18〔1953–2007〕 | 55/18〔1953–2007〕 | 55/18〔1953–2007〕 |
| 624 前橋 | 68/5〔1953–2025〕 | 65/8〔1953–2023〕 | 68/5〔1953–2025〕 | 68/5〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 69/4〔1953–2025〕 |
| 626 熊谷 | 54/19〔1953–2025〕 | 52/21〔1953–2024〕 | 72/1〔1953–2025〕 | 71/2〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 |
| 629 水戸 | 62/11〔1953–2025〕 | 61/12〔1953–2025〕 | 70/3〔1953–2025〕 | 70/3〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 |
| 637 飯田 | 53/20〔1953–2005〕 | 53/20〔1953–2005〕 | 53/20〔1953–2005〕 | 53/20〔1953–2005〕 | 54/19〔1953–2006〕 | 54/19〔1953–2006〕 | 54/19〔1953–2006〕 |
| 638 甲府 | 63/10〔1953–2025〕 | 62/11〔1953–2025〕 | 68/5〔1954–2025〕 | 67/6〔1954–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 72/1〔1953–2025〕 |
| 648 銚子 | 22/51〔1999–2025〕 | 27/46〔1954–2025〕 | 33/40〔1955–2025〕 | 44/29〔1954–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 71/2〔1953–2025〕 |
| 662 東京 | 48/25〔1953–2025〕 | 47/26〔1954–2025〕 | 64/9〔1953–2025〕 | 67/6〔1954–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 64/9〔1954–2025〕 |
| 670 横浜 | 48/25〔1956–2025〕 | 49/24〔1956–2025〕 | 56/17〔1969–2025〕 | 58/15〔1966–2025〕 | 73/0〔1953–2025〕 | 73/0〔1953–2025〕 | 66/7〔1958–2025〕 |
| 672 館山 | 24/49〔1980–2005〕 | 24/49〔1980–2005〕 | 28/45〔1969–2005〕 | 29/44〔1969–2005〕 | 38/35〔1969–2006〕 | 38/35〔1969–2006〕 | 35/38〔1969–2006〕 |
| 675 大島(島) | 18/55〔1953–2008〕 | 22/51〔1954–2008〕 | 7/66〔1974–2001〕 | 19/54〔1974–2008〕 | 52/21〔1953–2009〕 | 47/26〔1954–2009〕 | 47/26〔1953–2009〕 |
| 677 三宅島(島) | 1/72〔1956–1956〕 | 1/72〔1956–1956〕 | 0/73 | 10/63〔1957–1999〕 | 35/38〔1965–2000〕 | 34/39〔1965–2000〕 | 46/27〔1954–2000〕 |
| 678 八丈島(島) | 37/36〔1953–2008〕 | 41/32〔1953–2008〕 | 23/50〔1955–2008〕 | 40/33〔1954–2008〕 | 57/16〔1953–2009〕 | 56/17〔1953–2009〕 | 56/17〔1953–2009〕 |

- 2021 年に観測の種目・地点が減ったあとも、かえで紅葉・いちょう黄葉の値が 2021〜2025 年にあるのは本州の 9 地点(長野・宇都宮・前橋・熊谷・水戸・甲府・銚子・東京・横浜)。松本・飯田・館山は 2005〜2007 年で終わっている。
- 本州 12 地点の 1991〜2025 年: かえで紅葉 328 件(rm 8: 288、9: 40)、いちょう黄葉 333 件(rm 8: 188、9: 145)。2016〜2025 年: かえで紅葉 76 件、いちょう黄葉 79 件。

## フェーズ 4: 段階14(紅葉の答え合わせ)の準備(通信しない)

- `docs/validation-plan.md`: 対象(関東甲信の本州 12 地点、2021 年以降も値がある 9 地点。伊豆諸島は外す案)、使う気温(Open-Meteo Historical API、8/26〜12/31、`timezone` 必須、モデルの固定は要目視)、予測日(v0 と同じ判定で初めて見頃になった日)、比べ方(予測 − 観測の分布、全体・地点・年・rm・標高の扱いごと)、標高(官署の標高を `elevation` に渡す案 + 渡さない場合と比べる。官署の座標・標高は別に要る)、通信量の見積もり、合格基準の候補 3 案(決めていない)、段階14 で要る承認。
- 通信量: 1 リクエスト = 1 地点 × 1 季節。最悪 約 9.2 call/リクエスト(推測)。推奨の案 A'(9 地点 × 10 年 × 標高 2 通り)= **180 リクエスト・約 1,660 call**・2 秒間隔で約 6 分。無料枠(10,000/日)にもハブの自主上限(3,000 リクエスト/日、推定 4,130 call/日)にも収まる。35 年に広げる案 B'(840 リクエスト・約 7,730 call)は 3 日以上に分ける。キャッシュは `IKIMONOBIYORI_DATA_DIR` の下の `cache/`。
- コード `ikimonobiyori/backtest.py`(通信しない): `predict`(v0 の `mean_tmin`・`stage_for` とプロファイルの閾値・季節で、初めて見頃になった日)、`pair`・`aggregate`(中央値・平均・標準偏差・MAD・四分位・±N 日以内の割合。N は引数)、`report_markdown`(判定は書かない)、`observed_dates`(正規化した観測から)、`archive_query`(問い合わせの組み立てだけ。`elevation` あり/なし)。
- テスト `tests/test_backtest.py`(12 件。合成データ): 閾値と窓がプロファイルから来ること、欠損を 0 で埋めないこと、季節の中で見頃にならなければ予測なし、差と集計の値、レポートの決定論、`archive-api.open-meteo.com` がまだ許可ホストにないこと。
- テスト: 170 → **182 件 OK**。ゴールデンは変わらず通る。

---

## まとめ(最終の報告)

### フェーズごとの結果
| フェーズ | commit | 主なファイル | テスト(前 → 後) | ゴールデン |
|---|---|---|---|---|
| 0 現状の確認 | `d19460b` | `docs/stage13-report.md`・`docs/stage13-decisions.md` | 138 OK(基準値) | 通る |
| 1 設計とデータ源 | `2bd8610` | `docs/design.md`・`docs/data-sources.md`・README | 138 → 138 OK | 通る |
| 2 カタログと時期の型 | `09432d2` | `ikimonobiyori/schemas/site-catalog.schema.json`・`ikimonobiyori/catalog.py`・`ikimonobiyori/data/catalog/`・プロファイル 7 つに `timing_type`・`tests/test_catalog.py` | 138 → 159 OK | 通る(変わらない) |
| 3 気象庁の生物季節観測 | `d5ebd8f` | `ikimonobiyori/jma_phenology.py`・`ikimonobiyori/data/jma_phenology.yaml`・`data/jma_phenology/README.md`・`raw/SOURCES.md`・`tests/test_jma_phenology.py` | 159 → 170 OK | 通る |
| 4 答え合わせの準備 | (この commit) | `docs/validation-plan.md`・`ikimonobiyori/backtest.py`・`tests/test_backtest.py` | 170 → 182 OK | 通る |

- v0 の挙動(閾値・式・band・出力)は変えていない。`engine.py`・`methods/`・`fetch/`・`main.py`・`compose.py` は変更なし。プロファイルは `timing_type` の追加だけ(v0 は読まない)。
- テストは biyori-hub の既存の仮想環境で実行した(D-01)。この PC の既定の `python` には jsonschema・PyYAML がない。

### 見直してほしい判断(順に)
1. **D-03** 気象庁のデータを public のリポジトリに置かない(規約は公開を認めると読めるが、要約経由でしか読めなかった)。目視で問題なければ `.gitignore` の 2 行を外す。
2. **D-12 / D-17** 正規化・答え合わせのコードをパッケージの中に置き、`--out` に明示したときだけ書く(規則 8 の読み方)。
3. **D-06 / D-07** カタログ・スキーマ・方針をパッケージの中に置いた(指示書は `data/catalog/`・`schemas/`)。
4. **D-08 / D-09** 公開会場の例外はホタルだけ、area_1km の座標は小数 2 桁(仮置き)。
5. **D-13** 年をまたぐ値の読み方(推測)。
6. **D-10 / D-11** スキーマの必須・任意、`example` の追加、ファイルの最上位の形。
7. **D-15** 伊豆諸島を答え合わせの主な対象から外す案。
8. **D-19 / D-20** 通信量の見積もりの前提、合格基準の候補。
9. **D-01 / D-02 / D-04 / D-05 / D-14 / D-16 / D-18 / D-21** その他。

### ユーザーが後で決めること(作業を止める理由にはしていない)
- 合格基準(`docs/validation-plan.md` §6 の 3 案から、または別の案)と、気象庁の紅葉日を v0 の「見頃」と「色づき始め」のどちらと比べるか。**結果を見る前に**。
- 要目視の規約・資料: 気象庁の公共データ利用規約の原文(public に置けるか)、付録 B の「自動巡回は控える」の記述の場所、累年値のフォーマットの PDF(rm の意味・値 0 の意味・年またぎ)、Open-Meteo の Historical API のモデルを固定する引数・ERA5 の引用文、**iNaturalist の利用規約と API の推奨手順(HTTP 403 で読めなかった)**、環境省の植生図の利用条件。
- 段階14 の承認: `archive-api.open-meteo.com` を許可ホストに足す、気象官署の緯度・経度・標高の取り方、案 A'(180 リクエスト)から始めるか。
- 足りなかったデータ: 気象官署の座標・標高(CSV に含まれない)。CSV は 7 ファイルともそろった。

### 推測で書いた部分
- 76 地点の座標・標高が山頂のものであること(ファイルに明記はない。名前と標高の値から)。
- CSV の地点番号が国際地点番号 47NNN の下 3 桁であること、地点名から都道府県・関東甲信への対応。
- 年をまたぐ値の読み方(春の 10〜12 月は前年、秋の 1〜3 月は翌年)。
- rm の意味(標本木の種の違いの可能性。未確認)。
- Open-Meteo の call の数え方(最悪 約 9.2 call/リクエスト)、予報 API の `elevation` が Historical API と同じ扱いであること、標本木が官署の構内か近くにあること。
- 合格基準の候補の数値(例であり根拠はない)。

### push すべきもの(push はユーザーが行う)
- ブランチ **`stage13`**(main の `add784e` から): `d19460b` → `2bd8610` → `09432d2` → `d5ebd8f` → フェーズ 4 の commit(`git log --oneline main..stage13` で確認できる)。
- フェーズ 5(biyori-hub への取り込み)は指示書どおり**実行していない**。push の後に、`vendor.lock` の更新(`hub/fetch_vendor.py` → `--apply` → `hub/check_vendor.py`)・ハブの unittest・manifest の `source.commit` の更新を行う。プロファイルの `phenology_labels`・`stage_order`・`config.yaml` の有効期間は変えていないので、ハブの manifest の写しを直す必要はない見込み。
