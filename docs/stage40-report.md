# 段階40 報告: 野草・高山植物（花が咲くもの）

## できたこと
- 新コマンド `python -X utf8 -m ikimonobiyori.guide wildflower --site <地点ID> | --area <山域> [--month N | --date YYYY-MM-DD] [--json]`（通信しない）。
  - 地点の鍵は `data/sites.yaml` の mNNN（ヤマビヨリと同じ）。山域への対応は `data/guide/wildflower_areas.yaml`。
  - 既定は、コンシェルジュが山の提案にそのまま添えられる文（例年の時期の目安・採らない／登山道から出ない・山の天気はヤマビヨリで）。`--json` は `schemas/wildflower.schema.json` に通る。
  - 保護が必要な種は `--site` の出力に出さず、`--area` だけに出す。準備中の山域・山域に結ばれていない地点は「データ準備中」（嘘を作らない）。
- 話題の登録: 野草・山野草・高山植物・お花畑（`guide theme`）。CLAUDE.md・AGENTS.md・スキルに短い節を足した（3 つとも同じ文）。
- 点検: `python -X utf8 -m ikimonobiyori.wildflower`（通信しない。問題 0 件）。
- 組み合わせの例: `docs/stage40-example.md`。受け入れの記録: `docs/stage40-acceptance.md`。

## 山域ごとの量（山域ごとにコミット）
| 山域 | 花暦の行（種数） | 月の網羅 | 定評 / 仮 | 発行元 |
|---|---|---|---|---|
| 丹沢 | 50 | 9 か月 | 7 / 43 | 4 |
| 箱根 | 36 | 10 か月 | 1 / 35 | 2 |
| 奥多摩 | 12 | 7 か月 | 6 / 6 | 7 |
| 高尾 | 32 | 8 か月 | 8 / 24 | 3 |
- 準備中（未着手）: 富士山周辺・八ヶ岳・南アルプス・北アルプス。したがって「夏の高山植物」は、今は答えられない（受け入れ質問 3 は、そう答えたうえで丹沢・箱根・奥多摩・高尾の夏の花を出した）。
- 浅い所: 奥多摩は 12 行だけ（東京都のレンジャー便りの PDF が文字として読めず、観光連盟・山岳メディア・青梅市観光協会が中心）。高尾は公的機関のページ（林野庁の PDF は 403）が読めず、すべて個人・メディアの発信（区分 secondary）。箱根は箱根湿生花園（園内の植栽・保全された花の花期）が中心で、標高・自生地は書かれていない。
- 学名・科は、出どころに書かれていたものだけ（学名はすべて空 = 不明）。iNaturalist の対応表（taxon id）は、写真の事前取得（承認B）で 95 種中 57 種が入った。

## 写真
`guide photos-prefetch --theme 野草 --all`（通信 174 件・3 回）で 29 種の写真を取得（キャッシュはコミットしない）。塔ノ岳 5 月の 17 件のうち taxon id が付いたもの 14、写真ありは 10。保護が必要な種は事前取得の一覧から除いた。

## テスト
- 新規: `tests/test_stage40.py`（14 件）。既存テストの期待値は変えていない。ゴールデンも作り直していない。
- 全テストの最後の行: `Ran 1035 tests in 1144.690s` / `OK`

## 受け入れテスト
- 通信しない範囲（`guide wildflower` の出力と `ask verify --generic`）で 3 問を確認し、3 件とも検査に合格。`--site m022 --month 5 --json` はスキーマに通り、花は 17 件。
- **行っていないこと**: 別のサブエージェントによる採点、実際の通信を使った質問 1〜9 の通しの受け入れ、iNaturalist の月別・標高帯の観察集計（D-5）、ページ（Artifact）での野草の写真つき表示。

## ハブの呼び方の確認（読むだけ）
`C:\biyori-hub\agents\ikimonobiyori\manifest.yaml` は、`interface.command`（`main.py` の提案）と `snapshot`（`adapters/ikimonobiyori_run.py`。対象は autumn_leaves・birds だけ）を宣言していて、`interests` には `wildflowers` があるが、野草の入口は宣言されていない。`guide wildflower` は通信しない純粋な CLI なので、ハブ側では新しい `interface`（例: `wildflower: {command: [{python}, -X, utf8, -m, ikimonobiyori.guide, wildflower, --site, {site}, --month, {month}, --json], output: stdout-json}`）を manifest に足し、`vendor.lock`・manifest の commit を更新するだけで繋がる見込み。ハブは変更していない（第 2 部は別の機会）。

## 決めたこと
- 地点が `sites.yaml` にない箱根は、山域でだけ引く（`sites: []`）。
- 開花時期が月だけの出どころは、月の精度（開始は上旬・終了は下旬として扱う）。出どころ間で食い違うときは、最も広い期間を採り、行の注記に両方を書いた。
- 保護種（ラン科・盗掘の記載のある種）は、行の注記に場所を書かない（点検が検出する）。
- 定評は、独立した発行元（名前が違うもの）2 件以上。個人の発信も数えるが、区分 `secondary` を出力に残す（「個人の登山記録を数えるのは別途の方針」の値は未定のため、提案: 定評の判定に公式を 1 件以上含める）。

## PR の状態
push の結果は、下の「PR」に追記する。

## 利用者がやること
push が拒否されている場合: 「`C:\ikimonobiyori` の Claude Code のタブ」で `! git push -u origin stage40` を実行する。成功すると `branch 'stage40' set up to track` と表示される。
