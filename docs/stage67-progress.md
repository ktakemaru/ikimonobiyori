# 段階67 進捗

ブランチ: stage67(main d1d12d9 から。段階65・66 は main にマージ済み)。開始 2026-11-09 05:59。
全テストは 4 分割(テストのモジュールを名前順に 4 つおきに分け、別のプロセスで並べて実行)。

| 部 | 状態 | commit | メモ |
|---|---|---|---|
| 第1部 判断の反映(B・C・E・F) | 済み | 65dd79b(事実の記録)・20ddd56(承認の記入)・(この行の commit) | B: 国営昭和記念公園の2つの情報源と通信先 showakinen-koen.jp を承認(条件: 状態の語30字以内・日付・URL)。花の台帳の readable・terms は承認の前に確認済みの事実を別 commit で記録。E: okutama-vc・oze-fnd を承認(allowed_fields は高尾・御岳と同じ)。C: 発行元の種類で「公式」を表示する仕組み(`ikimonobiyori/publisher.py`・`data/ask/publisher.yaml`。source_class は変えない)。4: 発行元はドメインでなく名前(二宮町・熱海市・大田区・静岡県)。F: 6つの出典のカード31枚の権利メモに本人の判断を記録(カードの置き場で commit)。docs/sources-approval.md を作り直し。全テスト 1,724 件 OK(4分割 419+455+448+402) |
