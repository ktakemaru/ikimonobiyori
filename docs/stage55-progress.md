# 段階55 進捗

開始 2026-11-07。main(段階54マージ済み 8e924cd)から stage55 を切った。実行順: 7 → 8 → 2 → 3 → 4 → 5 → 6。

| 部 | 状態 | commit | メモ |
|---|---|---|---|
| 7 | 済み | (下記) | 曜日チェックを日付ごとの年で照合(season._tokens)。年またぎ・年省略の終わり・月省略の終わりに対応。Moonlight Rose Garden を公式(flowerpark.or.jp)で確認して追加。test_stage55 11件 OK、回帰 20/20 |
| 8 | 済み | (下記) | 山と溪谷オンラインの URL を花暦・種の事実・山ごとの記載・保存データ・生成ページから削除(docs/stage55-yamakei-removal.md)。test_stage51 の併記テスト1件の期待値を変更(理由を記載)。test_stage55 14件 OK |
| 2 | 済み | (下記) | 台帳の新しい種別(ビジターセンター・自然観察施設): ikimonobiyori/visitor_centers.py、data/visitor_centers/{policy,centers}.yaml(centers は空。第3部で pending を追加)。30字・10種の上限、承認待ちは使わない、転載禁止の明示、シーズン終了の判定。test_stage55 26件 OK |
