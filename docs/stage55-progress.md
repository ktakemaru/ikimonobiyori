# 段階55 進捗

開始 2026-11-07。main(段階54マージ済み 8e924cd)から stage55 を切った。実行順: 7 → 8 → 2 → 3 → 4 → 5 → 6。

| 部 | 状態 | commit | メモ |
|---|---|---|---|
| 7 | 済み | (下記) | 曜日チェックを日付ごとの年で照合(season._tokens)。年またぎ・年省略の終わり・月省略の終わりに対応。Moonlight Rose Garden を公式(flowerpark.or.jp)で確認して追加。test_stage55 11件 OK、回帰 20/20 |
| 8 | 済み | (下記) | 山と溪谷オンラインの URL を花暦・種の事実・山ごとの記載・保存データ・生成ページから削除(docs/stage55-yamakei-removal.md)。test_stage51 の併記テスト1件の期待値を変更(理由を記載)。test_stage55 14件 OK |
| 2 | 済み | (下記) | 台帳の新しい種別(ビジターセンター・自然観察施設): ikimonobiyori/visitor_centers.py、data/visitor_centers/{policy,centers}.yaml(centers は空。第3部で pending を追加)。30字・10種の上限、承認待ちは使わない、転載禁止の明示、シーズン終了の判定。test_stage55 26件 OK |
| 3 | 済み(一部) | (下記) | 施設18件を承認待ちで台帳に追加(約90回の取得+検索4回)。奥多摩VC・キスゲ平・牛久・谷津干潟は確認できず。八島は2026-10-30が最終号(ended)。docs/stage55-facilities.md |
| 4 | 済み(一部) | (下記) | 行事4件を追加(横浜自然観察の森2・北本2。公式で確認)。年が読めない・市名未確認・翌シーズンのものは足さず(docs/stage55-events.md)。候補の名所 obs-yacho-0008 を追加 |
| 5 | 済み | (下記) | 答えでの使い方: visitor_centers.record_reports/read_reports/fact_rows(承認済み・季節内・14日以内だけ)、ask facts に visitor_centers(なければキーなし)、検査器 visitor_center_errors(承認済みでない施設の「○○発信」を落とす)、回帰テスト2件追加(22/22)。スキル3か所に(k)を追記。test_stage52 の併記の期待値を第8部の影響で更新 |
