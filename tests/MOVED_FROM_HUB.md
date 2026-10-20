# biyori-hub から移したテスト(段階12 フェーズ2)

biyori-hub の commit `c172548` の `tests/` から、イキモノビヨリの中身のテスト(窓口・ハブのモジュール・実際の iNaturalist の記録に触れないもの)を写した。
変換は、import の差し替え・パスの差し替え・ハブに依存する部分の除去だけで、**期待値は変えていない**。
ハブ側の削除はフェーズ 3 で行う(この表の「移した」だけを消す)。

| 新しい場所 | ハブの元 | 扱い |
|---|---|---|
| `test_ikimonobiyori.py` | `test_ikimonobiyori.py` の `Fixtures`・`Contract`・`Seasons`・`Birds`・`Methods`・`Parsers`・`ProfileSchema`(`test_manifest_matches_profiles` を除く)・`Cli` | 移した(ハブから消す) |
| (ハブに残す) | 同 `ProfileSchema.test_manifest_matches_profiles`・`WithHub`・`NarrativeExamples` | manifest・窓口・最終文の検査器に触れる |
| `test_fetch_open_meteo.py` | `test_ikimono_live.py` の `CacheTests`・`FetchTests`・`Recorded.test_marked_recorded_with_attribution`・`Recorded.test_parser_reads_real_responses`・`EndToEnd.test_main_live_requires_env_max_requests_and_hook` | 移した |
| 〃 (一部を除いた写し) | 同 `Recorded.test_engine_and_independent_check_on_recorded`、`EndToEnd.test_main_with_injected_http_produces_valid_proposal_and_independent_check_passes` | 独立検査器(`adapters/ikimono_check.py`)の行を除いた写し。**元はハブに残す** |
| (ハブに残す) | 同 `EndToEnd.test_independent_check_catches_inconsistencies` | 独立検査器はハブの仕事 |
| `test_fetch_inaturalist.py` | `test_ikimono_birds_live.py` の `Config.test_hosts_by_subject_only_birds_get_inaturalist`・`ShapeCheck`・`Fetch`・`Privacy`・`EndToEnd.test_live_refuses_both_subjects_and_shape_check_writes_file` | 移した |
| 〃 (一部を除いた写し) | 同 `EndToEnd.test_one_place_one_day_chain_and_independent_check` | 独立検査器の部分を除いた写し。**元はハブに残す** |
| 〃 (合成データで作り直し) | 同 `RecordedInaturalist` | 新しいリポジトリには実際の応答を置かない。`SyntheticInaturalistSparse` が合成データで同じ性質を確かめる。**元(実際の記録)はハブに残す** |
| (ハブに残す) | 同 `Config.test_runner_hosts_match_config`・`PositionEverywhere`・`RealBirdsThroughHub` | adapter・計測フック・窓口に触れる |
| `test_compose_and_survey.py` | `test_compose_and_survey.py` の `Compose`(`test_hub_reads_composed_snapshot_and_counts_age_from_each_component` を除く)・`SurveyAndLedger`(`test_host_daily_cap_counts_by_host_in_ledger` を除く)・`WindowSurvey` | 移した |
| 〃 (合成データで作り直し) | 同 `AbsenceWording.test_engine_warning_and_render_have_no_absence_claim` | エンジンの警告の部分だけを合成データで確かめる。**元(render・checktext を通す)はハブに残す** |
| (ハブに残す) | 同 上記の除いたテストと `AbsenceWording` | 窓口・台帳・最終文の検査器に触れる |
| `test_fetch_retry.py` | `test_stage7b.py` の `Retry`、`test_stage7c.py` の `KeepAlive`、`test_stage9b.py` の `Config.test_config_values_and_provisional_marker`・`RetryBehaviour` | 移した。偽の Session・`Flaky`・`R`・`fetch` も一緒に移した |
| (ハブに残す) | `test_stage7b.py` の `MinIntervalOverride`、`test_stage7c.py` の `HookCountsSessionRequests`・`TimeoutOverride`、`test_stage9b.py` の `Config.test_worst_case_fits_max_requests`・`Hook`・`Ledger`・`Wiring` | 計測フック・台帳・snapshotter・adapter・ワークフローに触れる |

このリポジトリだけのテスト: `test_golden.py`(ゴールデン G1・G2・G4)、`test_self_contained.py`(自己完結・書き込み先・実通信の許可の判定・テストの書き方の規則・文書)。
ゴールデンの G3(野鳥の記録を使う合成)は、実際の iNaturalist の記録から作るので、ハブにだけある。
