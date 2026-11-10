# 段階75 進捗

開始: 2026-11-10 20:28(+09:00)。ブランチ stage75(main から)。

## 準備
- `ask warm` を1回実行(期限切れ 40 件)。現況のページ 13 件を取得のサブエージェント(web-fetch)で読み、22 件を `ask record`、事実のなかった 6 ページを `ask warm --mark`。
- A(今の ask answer)の 11 本(10問、5番は2つ)をデータ置き場の compare/stage75/A/ に保存(すべて PASS・段2)。

## 第1部 ask brief: 済
- ikimonobiyori/guide_brief.py・data/ask/guide_mode.yaml。answer_run.run に quiet(記録・直前の答え・読むページの固定を残さない。既定は今まで)。

## 第3部 ask verify --brief: 済(テストは未)
- ikimonobiyori/guide_verify.py。final_check.run・stop_hook.decide が合格した最終の文を受け入れる。
- 関係するテスト 195 件 OK(test_stage72_hook ほか)。

## 第2部: 済
- docs/guide-voice.md(4,775 バイト)・docs/guide-mode.md。CLAUDE.md・AGENTS.md の「構成」に参照 1 行(SKILL.md は 14,996 バイトで上限 15,000 に余地がないため足さない)。

## テスト
- tests/test_stage75_guide.py(36 件 OK)。回帰 33/33。

## 第4部: 進行中
- 資料 11 本(compare/stage75/C/ids.txt)。B(2 つのサブエージェント)・C(1 つ)を起動。C の照合は scratchpad の verify_c.sh。

## 残り
- 第4部の完了(C の書き直し・比較ファイル)、第5部 採点と報告書、全テスト4分割、commit

## 第4部・第5部: 済(2026-11-10 21:15 ごろ)
- A・B・C の 11 本をデータ置き場の compare/stage75/ に保存(comparison.md)。C は全問 ask verify に合格(書き直し 1 回が 5 本)。
- Q2・Q4 の資料の不具合(対象が複数の計画で花・野鳥の候補が入らない)を直し、作り直して C に書き直させた。
- 全テスト4分割 458+600+488+374=1,920 件 OK(全体 1,920 と一致)。回帰 33/33。
- 報告書 docs/stage75-report.md。commit(push なし)。
