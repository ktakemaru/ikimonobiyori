# イキモノビヨリ 調査メモ（段階6a）

調査日: 2026-10-14。**公式ドキュメントのページの読み取りだけ**で、iNaturalist・GBIF・eBird・Open-Meteo の API は一切呼んでいない（6b で別途承認）。
凡例: ✅ 確認できた（出典あり）／ ⚠ 一部のみ確認（二次情報、または検索結果の要約）／ ❌ 未確認。**出典のない閾値・数値は書かない。**

ページの取得方法の制約: iNaturalist・GBIF・eBird の公式 API リファレンスは JavaScript で描画されるページ（Swagger / Postman）で、本文を取得できなかった。
そのため、パラメータの詳細は **公式クライアントではない `pyinaturalist` / `pygbif` / `rebird` のドキュメント**（二次情報）で確認し、その旨を付けた。6b の前に、公式ページをブラウザで目視確認する。

## 1. iNaturalist API（野鳥の観察記録）

| 項目 | 内容 | 状態・出典 |
|---|---|---|
| ベース URL | `https://api.inaturalist.org/v1/`（公式ドキュメント: `https://api.inaturalist.org/v1/docs/`） | ⚠ ドキュメントの URL は確認。本文は JS 描画で取得できず |
| 観察記録 | `GET /observations` | ⚠ `pyinaturalist` の関数一覧に `get_observations`。ページ本文は途中までしか読めていない |
| 種ごとの件数 | `GET /observations/species_counts`（`species_counts` 相当） | ⚠ `pyinaturalist` の関数一覧に `get_observation_species_counts`。レスポンスの項目名（`results[].count`・`results[].taxon.name` など）は ❌ 未確認 |
| 場所の指定 | `lat` / `lng` / `radius`（km の円）、`place_id` | ✅（`pyinaturalist` 文書: "Must be within a `radius` kilometer circle around this lat/lng"、"Must be observed within the place with this ID"）。`radius` の上限は ❌ 未確認 |
| 期間の指定 | `d1`（以降）/ `d2`（以前）、`month`、`year` | ✅（同上: "Must be observed on or after this date" など） |
| 分類 | `taxon_id`（子孫を含む）、`iconic_taxa`（鳥類は `Aves`） | ✅ `taxon_id`/`iconic_taxa` の説明は同上。`Aves` という値は ⚠（iNaturalist の iconic taxon 名として知られているが、今回のページでは値の確認なし） |
| 品質 | `quality_grade`（`needs_id` / `research` / `casual`）、`verifiable`（"Equivalent to quality_grade=needs_id,research"）、`captive`、`geoprivacy` | ✅（`pyinaturalist` 文書）。`casual` の値は ⚠ |
| 位置の秘匿 | `geoprivacy`（観察者が設定。秘匿された記録は座標が粗くなる） | ⚠ パラメータは確認。秘匿記録の座標の扱いは ❌ 未確認 |
| ページング | `page` / `per_page` | `per_page` の上限は ❌ 未確認 |
| レート制限 | 「API の利用は最大 100 リクエスト/分で絞られる。60 リクエスト/分以下を求める。1 日 10,000 リクエスト以下」。「性能に深刻な影響を与える利用は予告なくブロックされうる」 | ⚠ 検索結果の要約（"iNaturalist API Recommended Practices"/利用規約の記述として）。**一次ページ（`https://www.inaturalist.org/pages/api+recommended+practices`）は HTTP 403 で直接確認できなかった**。また開発者フォーラムに「60/分でも 429 が出た」という報告がある（`https://forum.inaturalist.org/t/429-error-from-observations-histogram-api-when-calling-at-60-calls-minute/64709`）。→ 60/分を上限ではなく天井とみなし、余裕（例: 30/分以下）を取る方針（数値は 6b で決める） |
| User-Agent | アプリを識別できる User-Agent を付けることを推奨 | ⚠ `pyinaturalist` 文書が「アプリ情報を user-agent に入れる」ことを推奨。iNaturalist 公式の記述は ❌ 未確認 |
| キャッシュ | クライアント側のキャッシュ | ⚠ `pyinaturalist` は既定で全リクエストをキャッシュ（ほとんどのエンドポイントで 30 分、taxa/places で 1 日）。公式の指示ではなく、同ライブラリの既定 |
| 帰属・写真のライセンス | 写真は個別のライセンス（`photo_license` で絞れる）。ハブは写真を使わない方針（出力に含めない） | ⚠ `photo_license` パラメータは確認。各ライセンスの条件・帰属の書き方は ❌ 未確認 |
| 記録のライセンス（観察データ） | ❌ 未確認 | |

## 2. GBIF API（日本国内の鳥類記録）

| 項目 | 内容 | 状態・出典 |
|---|---|---|
| 検索 | `GET https://api.gbif.org/v1/occurrence/search` | ⚠ `pygbif` の `occurrences.search` から（公式ページ `https://techdocs.gbif.org/en/openapi/v1/occurrence` は JS 描画で本文を取得できず） |
| 絞り込み | `country`（`JP`）、`geometry`、`eventDate`、`taxonKey`、`hasCoordinate`、`facet`/`facetMincount` | ⚠ `pygbif` の関数シグネチャ（`https://pygbif.readthedocs.io/en/latest/modules/occurrence.html`）。値の書式（geometry は WKT など）は ❌ 未確認 |
| 鳥類 | `taxonKey` に鳥綱（Aves）の taxonKey を指定 | ❌ キー番号は未確認（6b で公式の Species API の仕様確認が要る） |
| 取得件数 | `limit`（既定 300）、`offset` | ⚠ 既定値 300 は `pygbif`。2015 年の GBIF メーリングリストに「`offset` の上限は 200,000（ドキュメントは更新されていない）」とあるが**古く、現在の上限は ❌ 未確認** |
| 件数だけ | `GET /occurrence/count` | ❌ 未確認（今回のページでは確認できず） |
| レート制限・利用条件 | ❌ 未確認 | |
| データのライセンス | 記録ごと（CC0 / CC BY / CC BY-NC）。引用の要件あり | ❌ 未確認（6b 前に公式ページで確認） |

## 3. eBird API 2.0（任意の補助源）

| 項目 | 内容 | 状態・出典 |
|---|---|---|
| キー | **必要**。eBird アカウントに紐づく。ヘッダー `X-eBirdApiToken`。取得先 `https://ebird.org/api/keygen` | ✅ 利用規約（`https://www.birds.cornell.edu/home/ebird-api-terms-of-use/`）に「ほとんどの API にキーが必要で、eBird アカウントに紐づく」。ヘッダー名と keygen は ⚠（`rebird` / 他の実装から） |
| 近傍の最近の観察 | `GET /data/obs/geo/recent`（`lat`,`lng`,`dist`,`back`,`max`） | ⚠ `rebird` 文書: `dist` は 0〜50 km（既定 25）、`back` は 1〜30 日（既定 14）、`max` は 1〜10000 |
| 利用条件 | 規約で **商用目的の利用は別許可**（商用の定義は広い）。データは「eBird データ利用規約」に従う。濫用は停止されうる | ✅ 規約（上記 URL）。数値のレート制限は ❌ 未確認（第三者サイトの「約 1,000/日」は裏付けなし） |
| できないこと | 任意地点の「季節別の出現頻度」を直接返す API は、今回のページでは確認できず | ❌ 未確認（bar chart データ等の有無） |

結論: eBird は**キーが要り商用不可の補助源**。v0 では使わず、6b で任意の補助として検討する。

## 4. 紅葉の進行の目安（気温と色づき）

| 項目 | 内容 | 状態・出典 |
|---|---|---|
| 目安 | 「最低気温が 8℃以下になると紅葉が始まり、最低気温が 5〜6℃になると紅葉が進んで見頃になると言われています」 | ✅ ただし**言い伝え**として書かれている。国土交通省 北陸地方整備局 大町ダム管理所 記者発表資料（平成 28 年 10 月 24 日）。`https://www.hrr.mlit.go.jp/omachi/news/back/kisyahappyou/161024/161024omachikouyou.pdf`（大町ダム周辺・日射量と気温の低下が必要、とも書かれている） |
| 別の記述 | 「落葉樹が紅葉や黄葉に色づき始めるには、その日の最低気温が 8℃以下となることが必要で、5℃以下になると色づきは一気に進むとされています」。ただし**「イロハモミジを対象にした指標」「全体的にみるとこれぐらいになるという一つの目安で、明確に 8℃以下、5℃以下というデータが存在するわけではありません」** | ✅ ウェザーニュース 2024-11-14、京都府立植物園の樹木医（中井貞氏）のコメント。`https://weathernews.jp/news/202410/310205/` |
| 気象庁の基準か | **気象庁がこの 8℃/5℃ を基準として定めた記述は確認できなかった** | ❌ 気象庁の公式ページには見つからず（検索のみ） |
| 気象庁の観測の定義 | 紅（黄）葉日 = 「目視によって、対象とする植物を全体として眺めたときに、その葉の色の大部分が紅（黄）色系統の色に変り、緑色系統の色がほとんど認められなくなった最初の日」。観測は気象官署の標本木で目視 | ✅ 気象庁「生物季節観測指針」令和 3 年 12 月、2.1.2（`https://www.data.jma.go.jp/sakura/data/shishin.pdf`）。かえでの種・標本木の詳細は 3.4 節（今回は未読） |
| 積算温度（「低温遭遇の積算」）などの手法 | ❌ 未確認（広く使われる基準を出典つきで確認できなかった） | |
| 標高による遅れ | 標高が高いほど早く色づく、が一般に言われるが、数値の出典なし | ❌ 未確認（数値は書かない） |

**ハブでの扱い**: 8℃/5〜6℃ は「**出典はあるが、非公式の言い伝えで、種・地域差があり、気象庁の基準ではない目安**」。プロファイルでは `provisional: true`、出典（上の 2 件）と「言い伝えの目安」である理由を必ず付け、確信度の数値は出さない（`heuristic-unvalidated`）。

## 5. Open-Meteo（日別気温）

| 項目 | 内容 | 状態・出典 |
|---|---|---|
| 予報 | `https://api.open-meteo.com/v1/forecast`。`past_days` は 0〜92（既定 0）、`forecast_days` は 0〜16（既定 7） | ✅ `https://open-meteo.com/en/docs` |
| 日別の気温 | `daily=temperature_2m_min,temperature_2m_max`（"a simple 24 hour aggregation from hourly values"）。日別変数を指定するときは `timezone` が必須（`Asia/Tokyo`） | ✅ 同上 |
| 過去 | `https://archive-api.open-meteo.com/v1/archive`。`start_date`/`end_date`（yyyy-mm-dd）、`daily=temperature_2m_min` あり。ERA5 は「1940年〜現在、5日遅れで日次更新」、ECMWF IFS（9km）は「2017年〜現在、6時間ごと・遅れなし」 | ✅ `https://open-meteo.com/en/docs/historical-weather-api` |
| 平均気温 | `temperature_2m_mean` の識別子は archive ページの daily 定義に**記載なし** | ❌ 未確認（v0 は最低気温を使う） |
| 複数地点 | 緯度・経度をカンマ区切りで複数指定できる（応答は構造体のリスト）。**最大数は書かれていない** | ✅ 記述あり／上限は ❌ 未確認 |
| 1リクエストあたりの変数・日数の制限 | ページには明記なし。課金上の重み付け（変数 10 超または 2 週間超で複数 call、1 日 10,000 call）は価格ページ（段階 2B で確認済み、式は推測） | ⚠ 他のビヨリと**無料枠を共有** |
| 標高補正 | archive ページに `elevation` パラメータが列挙されているが、意味は本調査では読んでいない | ❌ 未確認（山の標高で気温を補正できるか。6b で確認） |
| 利用条件 | 無料枠は非商用。帰属（CC BY 4.0）。Copernicus 表記（"Generated using Copernicus Climate Change Service information 2022."） | ✅ 上記ページ |

紅葉の見積り（v0 の設計）: 地点ごとに 1 リクエスト（`past_days` + `forecast_days` と日別の最低気温 1 変数）。変数 1・日数 ≤ 16 + 過去 ≤ 92 なので、重みは最小（1 リクエスト = 1 call 程度と推定、**未確認**）。

## 6. 地点カタログの持ち方（標高・座標）

- 紅葉: **山・山域の地点**（名前・緯度・経度・標高 m・地域・種別）。初期は yamabiyori の山リスト（`vendor/yamabiyori/mountain_weather_core.py` の `MOUNTAINS`、固定 commit `de66f10`）を**一度だけ複製**し、以後は独立（`ikimonobiyori/data/sites.yaml`、複製元の記録つき）。標高は気温の補正や「標高が高いほど早い」の補助に使えるが、補正式の出典は ❌ 未確認（v0 では使わない）。
- 野鳥: 地点ではなく**場所 × 半径**（iNaturalist は `lat`/`lng`/`radius`）。カタログに `bird_areas` の欄を設けるが、中身は 6b で決める。
- 座標の丸め（希少種・営巣地への配慮）: 契約の `location_precision`（`exact`/`area_1km`/`area_10km`/`municipality`）。野鳥の既定は `area_10km`。

## 7. 6a でやっていないこと（6b で別途承認）
iNaturalist・GBIF・eBird・Open-Meteo の API 呼び出し、取得結果のキャッシュ、バックテスト。応答のパーサーは、**公式ドキュメントの応答例の形に合わせた合成フィクスチャ**（`synthetic`）で検査する。ただし、応答の項目名は上の ❌ の部分を含むため、**パーサーは 6b の最初の実応答で必ず再確認する**。

## 8. 6b（API の実通信）の推奨手順（案。実行は承認後）

**目的**: パーサー（合成フィクスチャで検査済み）が、実際の応答の形で動くことの確認と、リクエスト数・実行時間・キャッシュの実測。まず**1地点・1場所・少量**から。

| 対象 | 呼び出す API | 1回あたりのリクエスト数（見積り） | 上限（案） | 止める条件 |
|---|---|---|---|---|
| 紅葉（Open-Meteo） | `GET https://api.open-meteo.com/v1/forecast`（`daily=temperature_2m_min`、`past_days`=平均日数、`forecast_days`=必要日数、`timezone=Asia/Tokyo`） | 地点ごとに 1 リクエスト。最初は **3 地点 = 3 リクエスト**。全 76 地点は 76 リクエスト（複数座標を 1 リクエストにまとめられるが、重み付けは未確認なので最初はまとめない）。call 換算は変数 1・日数 約 8〜10 日（過去 7 + 予報）で 1 リクエスト ≒ 1 call と**推定**（価格ページの規則、未確認） | 最初の実行は **10 リクエスト以下**。1 日の合計は既存の枠（`snapshot.daily_request_cap` 3000）の中で、他のビヨリと共有 | 429・4xx・5xx で即中止（再試行しない）。許可ホストは `api.open-meteo.com` のみ（既存の計測フックを使う） |
| 野鳥（iNaturalist） | `GET https://api.inaturalist.org/v1/observations/species_counts`（`lat`,`lng`,`radius`,`d1`,`d2`,`iconic_taxa=Aves`,`quality_grade=research`）、最新の観察日用に `GET /observations`（`per_page` 小、`order_by=observed_on desc` 相当は**未確認**） | 場所 × 対象日 × 過去年（`history_years`=5）+ 最新日用 1 = 1 場所・1 日あたり **6 リクエスト**。週末 2 日なら **12 リクエスト/場所**。最初は **1 場所・1 日 = 6 リクエスト** | **60 リクエスト/分以下を天井**として、**30/分以下**に自主制限（フォーラムに 60/分でも 429 の報告）。1 日 10,000 以下（利用規約の記述、一次ページ未確認）。最初の実行は **10 リクエスト以下** | 429・4xx・5xx で即中止。許可ホストに `api.inaturalist.org` を**追加する承認が要る**（自分では広げない）。User-Agent に識別できる名前を付ける |
| GBIF / eBird | v0 の対象外（任意の補助）。**6b でも使わない**案 | — | — | eBird はキーが要り商用不可 |

**6b の前にやること**: (1) iNaturalist・GBIF・eBird の公式 API リファレンス（Swagger / Postman）を**ブラウザで目視確認**し、本書の ❌ 未確認（レスポンスの項目名、`per_page` 上限、`iconic_taxa=Aves`、レート制限の一次ページ、ライセンスの帰属）を埋める。(2) 野鳥の場所（`bird_areas`）を 1 つ決める。位置の丸め（`area_10km`）のとおり、出力と出典 URL には丸めた中心を使う。(3) 実行は `BIYORI_ALLOW_LIVE=1` と `--max-requests` つきで 1 回、続けてキャッシュ確認（取得層にキャッシュ層を足す必要がある。v0 にはない）。
**止まる点**: 実応答の形が合成フィクスチャと違えば、パーサーは `ParseError` で止まる（推測で補わない）。そのときは実応答を保存して報告し、パーサーを直してから再実行する。

## 9. 6b-2（野鳥）の推奨手順の更新案（6b-1 のあと。実行は、場所を決めて承認した後）

6b-1 で、キャッシュ層（`ikimonobiyori/fetch/cache.py`、保存先 `runtime/ikimonobiyori/cache/`、TTL は設定）、`--cache-only`、読めない応答の保存（`runtime/ikimonobiyori/_unparsed/`）、計測フックつきの実行役（許可ホストは `api.open-meteo.com` のみ）ができた。野鳥はこれを再利用する。

**前提として私（ユーザー）が決めること**: (1) `bird_areas` の最初の場所（名前・中心・半径）、(2) 許可リストへの `api.inaturalist.org` の追加（自分では広げない）、(3) iNaturalist の一次ドキュメントの確認方法（下記）。

**iNaturalist の一次ドキュメントの確認方法（案）**
- 公式の API リファレンス（`https://api.inaturalist.org/v1/docs/`）は JS 描画で、今回の読み取りでは本文を取れなかった。
- (a) ブラウザ操作（Claude in Chrome）を使えば本文を読める可能性がある。ただし**ページの読み込みは iNaturalist のサーバーへの通信**になるため、「iNaturalist への通信は行わない」の範囲に入る。承認があれば使う（読むだけ。API のデータ取得はしない）。
- (b) ユーザーが公式ページをブラウザで開き、パラメータ表（`per_page` の上限、`iconic_taxa` の値、レスポンスの項目名）と利用規約（レート制限）を貼り付ける。
- (c) 最初の実応答で形を確認する。**1リクエストだけ**（`species_counts`、1場所・1年分、`per_page` 小）を実行し、応答をそのまま `_unparsed/` 相当に保存して、パーサー（合成フィクスチャで検査済み）が読めるかを確認する。読めなければ止めて報告し、パーサーを直してから次へ進む。
- 推奨は (c) を最初に、(a)/(b) で裏付け。

**段階**
1. 1リクエストの形の確認（上の (c)）。上限 3 リクエスト。
2. 1場所・1日（過去5年 + 最新の観察日 = **6 リクエスト**）。上限 10。続けてキャッシュ確認の 1 回（0 リクエストのはず）。
3. 週末 2 日（12 リクエスト）→ 通しで窓口（`check-text` まで）。

**レート・停止条件**: 30 リクエスト/分以下に自主制限（60/分でも 429 の報告がある）。429・4xx・5xx で即中止（再試行しない）、許可外ホストは送信前に中止、`ParseError` は実応答を保存して止める。User-Agent に識別できる名前を付ける（設定済み）。キャッシュ TTL は iNaturalist の更新頻度の実測がないので、野鳥の過去記録（昨年以前）は長め（日単位）の**仮置き**を設定に追加する（現在の 3 時間は予報用）。
**位置**: 問い合わせの中心座標は、出力に載せる値と同じ丸め（`area_10km` は小数1桁）を使い、正確な座標をキャッシュ・出力・URL に残さない（6a で出典 URL から座標を除いた方針を実通信でも守る）。

## 10. 6b-2 の決定事項（ユーザーの回答、2026-10-14。実行はまだしない）
- **野鳥の最初の場所（候補）**: 軽井沢周辺。丸めた中心 北緯36.3度・東経138.6度（`area_10km`）、半径 5〜10km 想定（最初は 10km を候補に）。`ikimonobiyori/data/sites.yaml` の `bird_areas` に `status: candidate`（未承認）で記録した。他の場所がよければ差し替える。`approved` になるまで問い合わせの対象にしない。
- **iNaturalist の確認方法**: (c) 最初の実応答で形を確認する（上限 3 リクエスト）。一次ドキュメントの本文は静的取得ではほぼ読めないので期待しない。利用条件とレート制限だけは、**ブラウザでの目視確認**を勧める。許可は『公式ドキュメントのページを読むだけ』に限り、API 呼び出しとは分ける。

## 11. 6b-2 の結果（2026-10-14）

### A. 公式ドキュメントのブラウザでの目視確認 → **読めなかった**
承認（iNaturalist の公式ページ 5 ページ以内、読むだけ）にもとづき、Claude in Chrome で `api.inaturalist.org/v1/docs/`、API の推奨手順（`inaturalist.org/pages/api+recommended+practices`）、API リファレンス、利用規約を読むつもりだった。
`tabs_context_mcp` が 2 回とも「Browser extension is not connected」（Chrome 拡張が接続されていない）で失敗したため、**1 ページも読んでいない**（回避はしていない。WebFetch で同じ iNaturalist のページを取りに行くことも、承認の範囲（ブラウザで読むだけ）を超えるのでしていない）。
→ 規約・レート制限・帰属・ライセンス・`per_page` の上限は §1 のとおり**未確認のまま**。今回の用途（個人・非営利・集計値のみ）が規約上問題ないかの判断も**未確認**（根拠となる一次ページを読めていない）。確認するには、拡張を接続して再度指示をもらうか、ユーザーが該当ページを貼る。

### 実際の応答で確認できたこと（一次ページの代わりの事実。公式の仕様の確認ではない）
- `GET https://api.inaturalist.org/v1/observations/species_counts?lat=36.3&lng=138.6&radius=10&d1=2025-10-10&d2=2025-10-24&iconic_taxa=Aves&quality_grade=research&per_page=10` は **HTTP 200**。認証なし、GET のみ。`per_page=10` と `per_page=200` のどちらも 200（`per_page` の上限は未確認のまま。200 までは通った）。
- 応答の形（合成フィクスチャと一致）: 最上位 `page` / `per_page` / `results` / `total_results`、`results[]` は `count` と `taxon`。`taxon` には `id`・`name`（学名）・`preferred_common_name`・`rank`・`iconic_taxon_name` のほか、`ancestor_ids`・`ancestry`・`atlas_id`・`complete_rank`・`default_photo`・`extinct`・`flag_counts`・`observations_count`・`parent_id`・`provisional`・`rank_level`・`wikipedia_url` などがある（`tests/fixtures/ikimonobiyori/recorded_inaturalist_2026-10-14.json` の `fields_seen`）。**保護状況（conservation status）や位置の秘匿（geoprivacy）の項目は応答になかった。**
- `preferred_common_name` は**英語**（例: Long-tailed Tit）。ロケールの指定（日本語名）は未確認。
- レート制限のヘッダ（`X-RateLimit-*`、`Retry-After`）は**応答になかった**（返ってきたヘッダ: Accept-Ranges, Access-Control-*, Age, Cache-Control, Connection, Content-Type, Date, ETag, Server, Transfer-Encoding, Vary, X-Cache, X-Content-Type-Options）。429 も出ていない。
- **観察の少なさ**: 軽井沢周辺（半径 10km）、対象日 10/17 の前後 1 週間、research grade の鳥類は、過去 5 年（2021〜2025）で **11 件**（2021〜2023 年は 0 件、2024 年は 6 種 6 件、2025 年は 3 種 5 件）。プロファイルの `min_total_observations=30` 未満のため、提案は出ない（「欠損を 0 で埋めない」・閾値は変更しない）。

### 規約上の注意（暫定。一次ページ未読）
- 今回の実装は、**集計値（種ごとの件数と分類名）のみ**を保存し、写真・観察者の情報は保存しない（`minimize_species_counts`）。応答に含まれていた `default_photo` などの項目は、受信後すぐに捨てている。
- 記録・集計のライセンスと帰属の要件、キャッシュの保存・再配布の可否は**未確認**。公開（再配布）はしない前提（個人利用、`runtime/` は gitignore）。

### 参考照合（軽井沢周辺の野鳥。検証ではなく参考）
- 軽井沢野鳥の森（約100ha・約3km の遊歩道）は「80種とも100種ともいわれるほど多くの野鳥が生息」、別の記述では年間約80種が観察できる国設の森。バードウォッチングのベストシーズンは冬〜春で、秋が最適とは書かれていない。出典: rurubu（https://rurubu.jp/andmore/spot/80019714）、ピッキオ/NTA のツアー案内（https://www.nta.co.jp/activity/mountain/eco_tour/koshinetsu/nagano/152/）、BE-PAL（https://www.bepal.net/archives/676226）。いずれも検索結果の要約で、本文は直接読んでいない。
- **10 月の具体的な観察種・冬鳥の到着時期の情報は見つからず**。iNaturalist の 5 年で 8 種 11 件は、この森の年間約 80 種と比べて**少なすぎる**（観察者が少ない／research grade のみ／半径 10km・前後 1 週間の窓が狭い）。モデルの結果（提案なし）は「データ不足」で、観察できる鳥がいないという意味ではない。
- 8 種（マガモ・コガモ・キンクロハジロ・カワガラス・ハクセキレイ・カルガモ・エナガ・シジュウカラ類）は一般的な水鳥・山地の鳥で、特に希少として知られる種は含まれていない（私の知識による判断。保護区分の出典確認はしていない）。応答に保護状況・位置秘匿の項目がなく、**機械的には判別できない**。位置は丸めた中心だけを使い、種ごとの位置は一切出していない。

## 12. iNaturalist 公式ページの二次的な要約（助言役が WebFetch で取得。2026-10-14）【要目視】
**これは原文ではなく要約**で、助言役（ユーザーの側）が WebFetch で読んだ内容。ハブ（私）は一次ページを読めていない。ユーザーは気が向いたときに自分のブラウザで目視する（急がない）。出典 URL: https://www.inaturalist.org/pages/api+recommended+practices と https://www.inaturalist.org/pages/terms 。

| 項目 | 要約（二次的） |
|---|---|
| レート | 約 1 リクエスト/秒、1 日あたり約 1 万リクエスト。分あたりの上限の記載はない。超えると 429、継続すると IP をブロックされうる。メディアのダウンロードは 5GB/時・24GB/日を超えると恒久ブロックの可能性 |
| User-Agent | 設定を推奨（アプリ名または iNaturalist のユーザー名） |
| 一括取得 | API は大量ダウンロード向けではない（観察データは書き出し機能を使う）。`per_page` は観察で最大 200。ページングは 1 万件まで |
| 利用許諾 | 推奨ページにデータのライセンスの記載はない。引用は GBIF の DOI（10.15468/ab3s5x）を案内 |
| 規約（terms） | 投稿コンテンツの既定ライセンスは CC BY-NC（投稿者が別に指定しない場合）。AI/機械学習の学習への利用を制限する記述がある（範囲は要目視）。自動アクセスやスクレイピングの個別規定は見当たらない |

**今回の用途の判断**: 個人・非営利・種ごとの集計値のみ・写真や観察者の情報は保存しない・学習には使わない、という使い方は、読んだ範囲（要約）では問題は見当たらないが、**断定しない（要目視）**。
**ハブの運用への反映**: 自主制限は 30 リクエスト/分（2 秒間隔。要約の「約 1 リクエスト/秒」より厳しい）、さらに `hub/config.yaml` の `snapshot.host_daily_caps` で iNaturalist は 1 日（JST）1,000 リクエスト（仮置き。推奨の約 1 万/日の 1/10）。台帳 `snapshots/_ledger.jsonl` に host つきで数える。`per_page` 最大 200 は、ハブの実行（§11）で 200 が通った事実と矛盾しない。
**§1 の表との関係**: §1 の「レート制限 60/分以下」は検索結果の要約に基づく別の情報で、こちら（約 1 リクエスト/秒）の方が一次ページに近い（どちらも二次情報）。両方とも守る設定（2 秒間隔）にしてある。

## 13. 6c の結果（2026-10-14）
- **野鳥のデータ密度の調査**: `docs/ikimonobiyori-bird-density-survey.md`。10〜11月・全年・半径10km・research grade の鳥類の観察総数は、軽井沢周辺 76、葛西臨海公園周辺 1,559、谷津干潟周辺 368、渡良瀬遊水地周辺 78、河口湖周辺 183、印旛沼周辺 67。`/v1/observations` の `total_results` は観察の件数、`species_counts` の `total_results` は種の数。`locale=ja` で日本語名が返った。
- **スナップショットの合成**: `ikimonobiyori/compose.py`（`docs/scheduling.md` に更新間隔の考え方）。

## 14. 非公式・未確認のパラメータ（段階5a）
次の書き方は、**実応答では通ったが、公式ドキュメントで確認していない**（一次ページ未読）。変わる・使えなくなる可能性がある。
- `locale=ja`（`species_counts` で `preferred_common_name` を日本語にする）。野鳥の問い合わせにはこれを付ける（5a から）。**日本語名が返らない種は、返ってきた名前（英語名など）をそのまま使い、学名は必ず `details.taxon_name` に持つ**。
- `month=10,11`、`year=2021,…,2025`、`day=10,…,24` のようなカンマ区切りの複数指定。軽井沢の1点で、年ごとの問い合わせと同じ結果（種ごとの件数まで一致）になった。
- `per_page=1`（件数だけ欲しいとき）。

## 15. 5a の結果（2026-10-14）
- 現行の窓（±7日）・5年・10km・research の鳥類の観察数: 軽井沢 11（6b-2 と一致）、葛西臨海公園 394、谷津干潟 44、河口湖 20、渡良瀬遊水地 4、印旛沼 4。30 以上の葛西・谷津干潟を `bird_areas` に追加（`docs/ikimonobiyori-bird-density-survey.md`）。
- 6c の概算（15/61倍）は外挿として当たらなかった（谷津・河口湖は約半分、渡良瀬・印旛は約1/4）。一点の較正で他の場所を外挿しない。
- `year`・`day` の複数指定は、`species_counts` でも年ごとの問い合わせと同じ結果（種数 8、合計 11、種ごとの件数も一致）。将来、1場所・1日あたりのリクエストを 5 → 1 にできる可能性がある（採用は未決・未実装）。

## 16. 紅葉の気温の標高（プロファイルから移した事例。5c-2）
Open-Meteo の気温は**格子の標高**のもの（応答の `elevation`）で、山頂の標高とは異なる。2026-10-14 の記録: 八ヶ岳(赤岳) 山頂 2,899m・格子 2,599m、谷川岳 山頂 1,977m・格子 1,920m、高尾山 山頂 599m・格子 598m（`docs/measurements.md`）。標高による補正はしていない（山頂より暖かい側にずれうる）。プロファイルの `known_limits` は事実だけを短く持ち、事例はここに置く。
## 17. 日本語名の実測（5c-2）
`species_counts` に `locale=ja` を付けると、`preferred_common_name` が返った種の割合（2026-10-15、年の複数指定・research grade の鳥類）: 葛西臨海公園周辺 58/58、谷津干潟周辺 23/23、軽井沢周辺 8/8。他の場所・種は未確認。野鳥の `known_limits` は『日本語名が取れない種がありうる』に更新した。
