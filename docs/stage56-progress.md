# 段階56 進捗
開始: 2026-11-07。main(f7e0202、段階55マージ済み)から stage56 を切った。

## 第1部 済み(ask plan)
answer_plan.py・data/ask/plan.yaml・ask.py(plan)・ask_verify.py(plan照合)・regress(plan:true、24件)・スキル/CLAUDE/AGENTS(5-2と(l))。tests/test_stage56.py(28件)。全テスト 1265件 OK(422秒)。
注: 検査器の節見出し対応(lead_mismatch)も同じコードにあるため第1部の commit に入る。第2部は文面の整合と追加テスト。

## 第2部 済み(狙い別の節と検査の整合)
lead_mismatch は見出しを挟んでも数える(第1部の commit に実装)。文面を CLAUDE.md/AGENTS.md/スキルで plan と整合(該当ある狙いだけ・節2つ以上のときだけ見出し)。テスト追加。全テスト OK。

## 第3部 済み(例年の見頃の補完)
町田薬師池(ウォーカープラス 11月中旬～下旬)・高尾山(Enjoy Tokyo 11月中旬～12月上旬)・御岳山(ウォーカープラス 10月下旬～11月中旬)を spots.yaml の typical に追加(紹介=secondary、2026-11-07 取得)。長瀞(阪急トラベル)は検索で該当ページに到達できず確認できなかったため入れない(tenki.jp は使わない)。全テスト OK。

## 第4部 済み(答えの文面の不具合)
1 過ぎた名所に終盤と書かない(plan の conflicts + outlook_conflict 検査)、2 1日だけの行事(festivals.py single_day_text。ラベルは期間のみ)、3 iNaturalist の出典を条件つき検索URL(observations.human_inat_url、facts の inat.source_url。site_url は残す=既存テスト維持)、4 「例年」の重複(typical_labels.known_strip)。テスト追加。全テスト1274件 OK、回帰 24/24。

## 第5部 作業済み・未commit(全テストが未完了)
再調査の結果は docs/stage56-recheck.md、データは centers.yaml(20施設)・festivals.yaml(28件)・spots.yaml(obs-kouyou-0092)・tests/test_stage56.py(Recheck)。関係するテスト(test_stage55/54/53/56/regress、124件)は OK。
全テストの実行がシステムのメモリ不足で停止された(自動停止。テストの失敗ではない)。指示書のとおり全テスト OK を確かめてから commit するため、第5部は commit していない。第6部・第7部は未着手。再開は本人の指示(メモリに余裕があるとき)。

## 第5部 済み(commit)
全テストを4部分に分けて別プロセスで実行: 311+293+432+240=1276件(数えた全体 1276件。直前の1274件+第5部で足した2件)すべて OK。

## 第6部 済み(commit)
docs/sources-approval.md(施設20件+台帳の承認待ち32件+山と溪谷オンライン。推奨 承認してよい8/要判断4/保留8)。tests に ApprovalList。全テストを4分割: 1278件(数えた全体 1278)すべて OK。
