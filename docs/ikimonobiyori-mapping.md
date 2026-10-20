# イキモノビヨリ v0 → biyori-proposal/1 対応表

実装: `ikimonobiyori/`（このリポジトリのパッケージ。biyori-hub が固定 commit で取り込む。biyori-hub の中にあったとき〔段階12より前〕の記述が残る文書がある。他のビヨリのコードを import しない）。閾値・係数は `ikimonobiyori/profiles/*.yaml` の `method.params` だけに書く（コードに直接書かない）。
調査と出典: `docs/ikimonobiyori-research.md`。**v0 は通信しない**（入力は `ikimono-inputs/1` の JSON。テストでは合成フィクスチャ `synthetic`）。

## 1. 点数の尺度（他のビヨリと比較しない。必ず `scale` つき）

| 対象 | scale 名 | 範囲 | 式の概要 |
|---|---|---|---|
| 野鳥 | `ikimonobiyori-birds-relative-frequency-0-1` | 0〜1 | 種の相対頻度 = 種の件数 ÷ 鳥類の観察記録の総数。条件は「場所×半径、対象日の前後 `window_weeks` 週、過去 `history_years` 年」。`go_threshold` は null（閾値方式でなく `maybe_min_relative_frequency` との比較は band の決め方） |
| 紅葉 | `ikimonobiyori-autumn-leaves-cold-progress-0-1` | 0〜1 | 進み = clamp((`start_min_temp_c` − M) ÷ (`start_min_temp_c` − `strong_min_temp_c`), 0, 1)。M = 対象日までの `mean_window_days` 日間の日最低気温の平均。**冷え込みの進みであって、紅葉そのものの進みではない** |

## 2. 提案の項目

| 契約の項目 | 野鳥（birds） | 紅葉（autumn_leaves） |
|---|---|---|
| `id` | `ikimonobiyori:birds:{日付}:{場所名}:{学名}` | `ikimonobiyori:autumn_leaves:{日付}:{地点ID}` |
| `subject` | `{category: observation_record, name: 和名(なければ学名), profile_id: birds}` | `{category: seasonal_progression, name: 紅葉, profile_id: autumn_leaves}` |
| `phenology_stage` | なし（野鳥には段階がない） | `before_bud`（色づき前）/ `early_bloom`（色づき始め）/ `peak`（見頃）。`late`（終盤・落葉）は v0 では判定しない（出典なし）。期間外は提案を出さない |
| `place` | `bird_areas` 相当の「場所×半径」の中心。**座標を `location_precision`（既定 `area_10km`）に合わせて丸める**: `area_1km`→小数2桁、`area_10km`→小数1桁、`municipality`→小数1桁、`exact`→そのまま（`engine.COORD_DECIMALS`） | `sites.yaml` の地点（名前・座標・標高・地域）。`location_precision: exact` |
| `time_window` | その日の 00:00〜翌 00:00 JST、**`kind: calendar_day`** | 同左 |
| `suitability.band` | 相対頻度 ≥ `maybe_min_relative_frequency` → `maybe`、未満 → `no`。**go は出さない**（`validated: false`） | `before_bud`（色づき前）→ `no`、**`early_bloom`（色づき始め）・`peak`（見頃）→ `maybe`**、`late`（終盤）→ `no`（`method.band_map`。段階6b-1 で色づき始めを `maybe` に変更: 気温の目安の幅が広く、一律に見送ると見頃の前後の情報が失われるため。上限が `maybe` なので go の山より下に並ぶ）。**go は出さない** |
| `suitability.score` | `{value: 相対頻度, scale, go_threshold: null}` | `{value: 進み, scale, go_threshold: null}` |
| `evidence[]` | `relative_frequency`・`species_observations`・`total_observations`・`years_used`・`window_weeks`。すべて `source_type: observation`、`url`（問い合わせの URL）、`last_updated`（最新の観察日。取れなければ null + 警告） | `min_temp_mean_window`・`min_temp_target_day`（`source_type: forecast`、`last_updated: null`: モデルの更新時刻が応答にない）、`mean_window_days`、閾値 `start_min_temp_c`・`advance_min_temp_c`（`source_type: static_reference`、出典 URL つき） |
| `uncertainty.confidence` | `{value: null, scale: null, method: observation-frequency, validated: false}` | `{value: null, scale: null, method: heuristic-unvalidated, validated: false}` |
| `uncertainty.reliable_up_to_days` | null（未確認） | null（未確認） |
| `uncertainty.known_limits` | プロファイルの `known_limits`（逐語） | 同左 |
| `care` | `{manners: プロファイルのマナー, do_not_disclose_exact_location: true}`（巣・ねぐらに近づかない、給餌しない、録音の再生で誘引しない） | `{manners: [...], do_not_disclose_exact_location: false}` |
| `details` | `provisional_params`（仮置きの値と出典または理由）、`taxon_name`、`taxon_id`、`area_radius_km`、`synthetic` | `provisional_params`、`site_id`、`synthetic` |
| `data_as_of[]` | `{source, source_type: observation, fetched_at, last_updated: 最新の観察日, url}` | `{source, source_type: forecast, fetched_at, last_updated: null, url}`（入力の `fetched_at`。取得時刻が分かるので窓口は「取得時刻」と書ける） |

### `time_window.kind` に `calendar_day` を選んだ理由
どちらの手法も**日単位の推定**で、時刻による変化を持たない（紅葉の段階は日最低気温の平均、野鳥の相対頻度は週単位の過去記録）。`activity_window`（日の出・日没に基づく）や `clear_window` を名乗ると、実際には時刻の根拠がないのに精密な窓とみなされ、窓口の衝突判定（精密な窓どうしの重なり）を誤らせる。粗い窓として出せば、yamabiyori の山の窓との組み合わせは「時間帯は要確認」（`needs_confirmation`）になる。

### 注意: 対象の月（`season.months`）が狭すぎないか
紅葉は `[9, 10, 11, 12]`（**provisional・出典なし**）。気象庁の生物季節観測指針（令和3年12月）の3.4 かえで・2.1.2 紅(黄)葉を確認したが、**紅葉の観察期間（月）の記述はなかった**ため、出典で更新できていない。
月の外では提案を出さず `not_applicable`（`out_of_season`）を返す仕様なので、**狭すぎる場合（標高の高い山の9月上旬より前、低地の12月下旬より後など）は、実際に色づいていても何も返らない**。範囲を広げるかは、今季の実測（`docs/ikimonobiyori-validation-plan.md`）で決める。

### 段階のラベル（`phenology_labels`、窓口の表示）
`before_bud`=色づき前 / `early_bloom`=色づき始め / `peak`=見頃 / `late`=終盤 / `out_of_season`=期間外（プロファイル `autumn_leaves.yaml`）。`render` が必ずこのラベルで表示し、narrative は言い換えない（検査器が `phenology_label_missing` / `phenology_label_conflict` で落とす）。

## 3. 状態（`status`）

| 状況 | 返し方 |
|---|---|
| 提案が1件以上 | `ok`。一部の対象が骨組み・期間外・入力欠落なら `partial`（`status_reason`）と警告 |
| 依頼の interests に対応するプロファイルがない | `not_applicable`、`no_matching_profile` |
| 対象が骨組み（`status: skeleton`）のみ | `not_applicable`、`profile_skeleton`（桜・彼岸花・ヒマワリ・ホタル・夜光虫） |
| 実装済みの対象で依頼の期間がすべて期間外 | `not_applicable`、`out_of_season`（紅葉は 9〜12 月以外。仮置き） |
| 期間内だが入力（気温の応答・観察記録）が足りない | `partial`、`no_input_data` + 警告（欠損を 0 で埋めない） |

## 4. 骨組みプロファイル（`status: skeleton`）
`cherry_blossom` / `higanbana` / `sunflower` / `fireflies` / `bioluminescence`。季節・予測の型・データ源の候補を調査（`docs/ikimonobiyori-research.md`）にもとづいて書き、**出典のない項目は「未確認」**（`season.months: null`）。エンジンは常に `not_applicable`（`profile_skeleton`）を返し、提案を出さない。

## 5. 仮置きの値の一覧（すべて provisional、プロファイルにだけある）
野鳥: `window_weeks=1`、`history_years=5`、`min_total_observations=30`、`maybe_min_relative_frequency=0.05`、`default_radius_km=10`（いずれも出典なし。バックテストで較正）。
紅葉: `start_min_temp_c=8`（言い伝えの目安。MLIT 大町ダム 2016、ウェザーニュース 2024）、`advance_min_temp_c=6`（同、5〜6℃の上端）、`strong_min_temp_c=5`（ウェザーニュース）、`mean_window_days=7`（出典なし）、`progress_shape=linear`（出典なし）。
**これらは検証されていない目安で、気象庁の基準ではない**。窓口の最終文では、`validated: false` として「確信度の数値は出力されていません」と書き、限界を `known_limits` の原文で添える。
