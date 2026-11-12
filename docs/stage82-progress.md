# 段階82 進捗

- 開始: 2026-11-12 22:31(+09:00)。上限 03:31。第1〜3部は 00:31 まで。第4部は 02:51 で区切る。
- ブランチ: stage81 は main にマージ済み(origin/main 55f9cde)。main を最新にして stage82 を切った。
- 通信の回数: 0

## 第1部
- 23:00 第1部(種の名前の読み替え species_alias.py・species_alias.yaml)・第2部(trait_errors・資料の「公的な解説」・guide-voice の悪い例)・第3部(通年・行けない時期・苔のテーマ・調べるのは 1 回・白駒の池と箱根美術館の記録・カードのテーマ付け 66 枚/苔 2 枚)のコードとテスト(test_stage82_names/traits/yearround)。関係するテストは OK。
- コキア: 公式で例年の時期を確かめられず(2025年の発表は今年の予想だけ)。記録していない。
- 次: 全テスト 4 分割 → commit → 第4部(写真の点検)
- 23:05 第4部のコード(Commons の選ばない語 deny_re・東アジア east_asia_re・地域で分かれる鳥 regional_species・点検の記録 photo_checks.json・ask photo-review list|set・ask photo-reply・Stop フックの photo_fix・docs/guide-mode.md の手順)とテスト test_stage82_photos。
- 写真は 315 枚・27 束。束の一覧は scratchpad の sheets/bNN.txt(mkbatches.py。点検済みは飛ばすので、再開時は作り直せばよい)。一覧画像は sheet.ps1(System.Drawing)。
- 全テスト(1 回目)は policy.yaml の制御文字(\b)の誤りで巻き込まれて失敗 → 直してやり直し中。
- 23:15 苔の質問を Sonnet(サブエージェント)で試した: ask verify 1 回で合格・調べる節なし(一度調べたので)・白駒の池と箱根美術館が出た。compare/stage82/koke/。
- 追加の直し: コケモモ・コケリンドウを苔にしない / 苔の記録を季節の花の候補に入れない(read_records の include_themes) / 題で表のひらがなをカタカナに / カードを引く文にカタカナの名前を添える(_card_question)。
- コキア: 公式の古い発表は 404、2025 の発表は今年の予想だけ → 記録しない。
- 全テスト 2 回目を実行中(split4.sh の出力を Ran/OK/FAIL だけに)。終わったら patch_after.py(非花の種・SKILL/CLAUDE/AGENTS の 1 行)→ 関係するテスト → commit → 写真の点検。
