# 報告書: コンシェルの段階 4 の前の準備(2026-11-27)

指示書: `docs/stage4-prep-instructions.md`(写し。元は `C:/temp/ikimonobiyori-stage4-prep-instructions.md`)。

## まとめ

- 第1部: README・AGENTS.md・CLAUDE.md・スキルの「biyori-hub との関係」を「ビヨリコンシェルとの関係」に書き換えました。契約の正本はコンシェルの `schemas/` です。決まりの中身は緩めていません。
- 第2部: 長い作業の前の予告の節と、実測だけの時間の表を AGENTS.md・CLAUDE.md に入れました。スキルには「予告の 1 行は例外」を足しました。出どころと手本は `docs/wait-notice-timings.md` です。
- 第3部: 資料の項目の一覧(`docs/concierge-brief-fields.md`)と、山 76 座の座標の一覧(`docs/sites-mountains-20261127.csv`)を書きました。資料の候補には、座標・`site_ref`・commit がありません。
- 通信はしていません。`ask brief` は実行していません(資料の例は、通信を禁じたテストの仕組みの下で作りました)。コードと既存テストの期待値は変えていません。
- push・PR・CI はまだです。手元で関係するテストだけを実行し、すべて OK でした。

| 部 | ブランチ | 最後の commit | 実行したテストと最後の行 |
|---|---|---|---|
| 第0部 | `docs/concierge-relation` | `0e666c9`(指示書の写し) | なし |
| 第1部 | `docs/concierge-relation` | `cf24e49` | 文書を見ている 20 本(`test_sources`・`test_self_contained`・`test_stage22`・`test_stage63b`・`test_proposals` ほか)を `tests/` から: `Ran 603 tests in 65.345s` / `OK` |
| 第2部 | `docs/wait-notice` | `221cc1f` | 文書を見ている 18 本: `Ran 560 tests in 68.095s` / `OK` |
| 第3部 | `docs/wait-notice` | `e8aaac4` | なし(文書と CSV だけ。docs/ を読むテストは無いことを確かめた) |
| 報告書 | `docs/wait-notice` | この報告書の commit | なし |

CI は、push していないので未実行です。

## 第0部(始める前の確かめ)

- 止まる条件には当たりませんでした。追跡中のファイルに変更は無く、main は `8d9a15e` で、`C:/biyori-concierge/docs/wait-notice.md` も読めました。
- 始めたときのイキモノビヨリ: ブランチ `main`、`8d9a15e Merge pull request #70 from ktakemaru/docs-readme-0.2.0`。追跡していないファイルは `docs/stage72・73・78・83・84・85-instructions.md` で、触っていません。
- ビヨリコンシェル(読むだけ): ブランチ `feature/stage3-day-flow`、`c6e277d 段階 3 第 2 部の報告書と通しの試しの記録`。読んだのは `docs/wait-notice.md`、`docs/biyori-concierge-instructions.md` の 6.4 章・7 章(I1・I2)と段階 4、`schemas/` の一覧と `biyori-vocabulary.yaml` です。
- 「biyori-hub」「ハブ」「vendor.lock」が出る行は、README・AGENTS.md・CLAUDE.md・スキル・`docs/` で **293 行**ありました(指示書の写しを `docs/` に入れる前に数えた値)。

## 第1部(「biyori-hub との関係」の書き換え)

293 行の扱い: 直した 33 行、今も正しいのでそのまま 10 行、判断がつかず直さなかった 7 行、昔の記録なのでそのまま 243 行。

### 直した行(33)

| ファイル | 行(書き換える前の番号) | 直したこと |
|---|---|---|
| README.md | 166・168・170・171・172・173 | 節を「ビヨリコンシェルとの関係」に書き換えました。取り込まずに手元の版を呼ぶこと、入口は `ask brief` と `guide wildflower`、読むのは資料であること、契約と語彙の正本はコンシェルの `schemas/`、単体で動くこと、hub の開発中止(2026-11-15)。hub のために作って残しているものは表にし、「残している理由」か「使っていない」を 1 行ずつ書きました。`biyori-hub` の語は残しています(`test_self_contained` が README にこの語があることを確かめるため) |
| AGENTS.md・CLAUDE.md(同じ内容) | 5 | 冒頭の 1 行を「ビヨリコンシェルが、取り込まずに手元の版を呼ぶ」にしました |
| 同上 | 17(絶対ルール 4) | 正本の場所を「ビヨリコンシェルの `schemas/`」に直しました |
| 同上 | 21(絶対ルール 6) | 計測フックが要る決まりはそのままにし、「開発を中止した biyori-hub の」とだけ足しました |
| 同上 | 26(絶対ルール 8) | 「biyori-hub から呼ばれても」を「ビヨリコンシェルから呼ばれても」に直しました。`ikimonobiyori/` の中に書き込まない決まりは残し、理由を「biyori-hub が `vendor/` から動かしていたときからの決まり」に直しました |
| 同上 | 33(構成) | livegate を「同じ判定として作った。比べるテストはハブ側にあった」に直しました |
| 同上 | 84(手順 C) | 「デバッグ・ハブ用」を「デバッグ用」に直しました(手順の部分は 3 つのファイルで同じにしてあります) |
| 同上 | 95(手順 E の見出し) | 「biyori-hub の窓口が使う」を「使っていた」に直しました |
| 同上 | 114〜117 | 節を「ビヨリコンシェルとの関係」に書き換えました。事前にユーザーへ報告する決まりは、段階のラベル・並び・有効期間と、提案の `id`・`phenology_stage` の値・`details.component`・`diagnostics` について残しました。manifest への写しとハブ側の統合のテストは「使っていない」と書きました |
| スキル `SKILL.md` | 3(description)・48・59 | 「山・星を合わせた提案はビヨリコンシェルの役割」にしました。48・59 は AGENTS.md と同じ直し方です |
| docs/proposal-mapping.md | 4 | 契約の正本は「ビヨリコンシェルの `schemas/`(以前は biyori-hub)」にしました |
| docs/ikimonobiyori-mapping.md | 3 | 「ビヨリコンシェルが手元の版を取り込まずに呼ぶ〔以前は biyori-hub が固定 commit で取り込んでいた〕」にしました |

一覧の範囲の外で直したもの: `tests/contract/README.md` に、正本がコンシェルの `schemas/` に移ったことと、2026-11-27 に写しと正本がバイト単位で同じだったこと(`cmp` で確かめた)を足しました。ハッシュの行とスキーマのファイルは変えていません。

### 今も正しいのでそのままにした行(10)

- README.md 151(`--live` に計測フックが要る): 決まりを緩めないので残しました。
- README.md 196(`docs/` に biyori-hub の中にあったときの記述が残る): 今もそのとおりです。
- AGENTS.md・CLAUDE.md 22(`BIYORI_REQ_LOG` があればハブの計測フックを使う): コードの動きとして今もあるので残しました。
- AGENTS.md・CLAUDE.md 27(絶対ルール 9。biyori-hub のモジュールを import しない): 指示書に「緩めることになる行は直さない」とあります。指す先をコンシェルに置き換えると、テストが見ている hub の禁止が文から消えてしまうので、残しました。
- AGENTS.md・CLAUDE.md 38・41(hub から移した経緯・hub の中にあったときの記述が残る): 経緯の記録です。

### 判断がつかず直さなかった行(7)

| ファイル:行 | 今の文(要点) | 直さなかった理由 |
|---|---|---|
| docs/data-sources.md:96 | 「実通信はこれまでどおり biyori-hub の計測フックの下で、その場の承認があるときだけ」 | 段階38(iNaturalist を自前の上限の下で単体で取りに行く)と合わない可能性があります。決まりの中身に関わるので、直しませんでした |
| docs/data-sources.md:110 | 1 日の上限は「ハブの `host_daily_caps`」 | hub が止まった今の上限の扱いを書くと、決まりを変えることになります |
| docs/data-sources.md:111 | User-Agent の値 `biyori-hub/ikimonobiyori (personal, non-commercial)` | 値は `config.yaml` にあり、通信の動きです |
| docs/proposal-mapping.md:63・65 | 注意の文の型を「ハブも同じ型を使う」 | `test_stage22` がこの文書の写しを読みます。コンシェルが同じ型を使うかは確かめていません |
| docs/ask-rubric.md:31 | 「ハブから呼ばれたときは計測フックの下で取り直す」 | 評価表の項目です。コードの動きとしては今もあります |
| docs/design.md:61 | 「窓口(biyori-hub)の変更は、この設計の範囲ではしない」 | 設計の記録で、今の形に合わせると意味が変わります |

### 昔の記録なのでそのままにした行(243)

段階ごとの指示書・報告書・決定の記録(`docs/stage*`)、`docs/rules-history.md`(24 行)、`docs/ikimonobiyori-research.md`(4 行)、`docs/validation-plan.md`(6 行。当時の hub の上限で立てた計画)、`docs/ask-rubric.md:3`(経緯)、`docs/design.md:43`(当時の許可の設定の例)。

### コードとテスト

- コードとテストは変えていません。`ikimonobiyori/livegate.py` の docstring(「ハブ側のテストが確かめる」)と、テストの docstring にある hub の記述も、そのままです。
- 期待値を変えたテストはありません。

## 第2部(長い作業の前の予告)

- AGENTS.md・CLAUDE.md の「## 報告のしかた」の前に「## 長い作業の前に伝える」を足しました。正本の場所・要点 3 つ・4 行の表です。
- 手順の部分(3 つのファイルで同じ)の「道具を呼ぶあいだにも書かない」の後ろに「(時間つきの予告 1 行は例外。AGENTS.md「長い作業の前に伝える」)」を足しました。
- **指示書と違うところ**: 指示書は CLAUDE.md を「例外とだけ書く薄い層」としていますが、このリポジトリでは CLAUDE.md は AGENTS.md の全文の写しです(`test_self_contained` が、見出し以外が同じであることを確かめています)。そのため、節と表は CLAUDE.md にも入っています。
- 字数の上限(`test_stage63b`): スキルは 15000 バイトまでのところ、足す前が 14961 バイトでした。スキル 8 行目の「(`tests/test_sources.py` が一致を検査する)」を外して場所を作り、今は **14997 バイト**です。AGENTS.md・CLAUDE.md は 30000 バイトまでのところ **29637 バイト**です。表を短くするため、出どころの詳細と手本は `docs/wait-notice-timings.md` に分けました。

### 時間の表

| 作業 | コマンド | 目安 | 出どころ |
|---|---|---|---|
| 資料を作る(読み直すページがあるとき) | `ask brief` | 読み直しに 5.6〜17.1 秒、作り直しまでの全体で 37〜40 秒 | `docs/stage85-report.md`「確かめ」の表。手元の PC・3 問(全体は 2 問)。段階85 第1部の版で、施設のページを足す前 |
| 資料を作る(読み直すページがないとき) | `ask brief` | 未計測 | 段階77 の 1.7〜4.2 秒は、読み直しを入れる前の版なので使っていません |
| 山の花暦 | `guide wildflower --json` | 0.88〜1.20 秒 | この作業(2026-11-27)。手元の PC・6 回(`m001`・`m002` を 7 月で 3 回ずつ。指示書の「3 回」を 2 地点で行いました) |
| 全テスト | `unittest discover -s tests` | 4 組に分けて 1 組 60〜209 秒 | `docs/stage85-report.md`「通信と時間」。手元の PC |

未計測の作業: `ask brief` の読み直しなしと、施設のページを読み直すとき、`ask answer`(段階63b の値は古い版のもの)、`ask research fetch`、写真の取得(`guide photos-*`・`ask photos`)、写真つきのページ(`guide page`・`ask page`)、`seasonal_obs fetch`・`taxa`、`ask inat-refresh`、`ask warm`。
通信しない資料づくり(空のデータ置き場で `build` を直接呼んだもの。5.3 秒・3.4 秒)は、本当の使い方と条件が違うので、表には入れていません。

## 第3部(コンシェルのための調べ)

詳細は `docs/concierge-brief-fields.md` にあります。

- **コンシェルが使える項目**: 候補の `name`・`rank`・`distance_km`(出発地からの直線)・`distance_text`・`prefecture`・`city`・`current_state`・`current_date`、事実の `kind`(今年の現況・例年の目安・行事・施設・安全)・`content`・`source`・`url`・`source_class`・`observed`、知識カードの `facts`・`source`・`url`、`missing`、`origin`。
- **足りない項目**:
  - 候補の座標と、山の地点との結びつき(`site_ref: yamabiyori:mNNN`)が無い。
  - 確かさの段階の項目が無い(事実の `kind` と `source_class` の組み合わせで表れる)。
  - 資料の commit・版・作った時刻が無い(`schema` と `now` はある)。
  - 資料の JSON Schema が無い。
- 山 76 座の座標を `docs/sites-mountains-20261127.csv` に出しました。ヤマビヨリとは比べていません。元は 2026-10-14 にヤマビヨリの commit `de66f10` から写したものです。
- 花暦がある山は 22 座です。うち 14 座は山域全体に花暦があり、8 座は一部の地点だけです。`status` は `ok`・`no_data`・`preparing` の 3 つで、例として谷川岳(m001)は `preparing` です。
- 困りそうな点は 10 個並べました。大きいのは、`ask brief` が通信し、読み直しを切る引数が無いこと、標準出力が JSON ではなくパスであること、出発地の既定が横浜であることです。

## 確かめられていないこと

- CI(push していないため)。
- 全テスト(決まりのとおり CI に任せています)。
- 今の版の `ask brief` の時間(通信が要るので実行していません)。
- 通信を禁じたときに `ask brief` の読み直しが断られる形は、コードを読んで書いただけで、入口からは実行していません。
- コンシェル側の計測フック・出発地の扱い・資料を消す仕組みがあるか。
- ヤマビヨリの座標との違い(I2。読んでいません)。

## 利用者がやること

1. (`C:\ikimonobiyori` のウィンドウ、Git Bash)`git push -u origin docs/concierge-relation` を実行し、main 向けの PR を作る。
2. (GitHub)その PR の CI が全部 pass であることを確かめてマージする。
3. (`C:\ikimonobiyori` のウィンドウ、Git Bash)`git push -u origin docs/wait-notice` を実行し、main 向けの PR を作る(1 本目のマージのあとなら、差分は第2部・第3部・報告書だけになります)。
4. (GitHub)その PR の CI が全部 pass であることを確かめてマージする。
5. (`C:\ikimonobiyori` のウィンドウ。通信が要る)同じ質問で `time python -X utf8 -m ikimonobiyori.ask brief "今週末の紅葉の情報は?"` を 3 回続けて測り、2 回目からを「読み直すページがないとき」として `docs/wait-notice-timings.md` と AGENTS.md・CLAUDE.md の表に書く(1 回目は「読み直すページがあるとき」の測り直し)。
6. (同じウィンドウ。通信が要る)写真つきのページ・`ask research fetch` など、未計測の作業を測る場合は、実際に使うときに時間を記録して表に足す。

## 決めてほしいこと

1. 時間の表の「読み直しあり 37〜40 秒」は、施設のページを足す前の版で測った値です。このまま使いますか。測り直すまで「未計測」に戻しますか(正本 5 章は「中身が変わったら直すまでは未計測」としています)。
2. スキルが 14997/15000 バイト、AGENTS.md・CLAUDE.md が 29637/30000 バイトで、ほぼ上限です。次に足すときは、削るか、上限(テストの期待値)を変えることになります。
3. スキル 8 行目から「(`tests/test_sources.py` が一致を検査する)」を外しました(場所を作るため)。戻すなら、ほかを削る必要があります。
4. CLAUDE.md は全文の写しのままにしました(テストが写しであることを求めています)。指示書の「薄い層」に変えるなら、テストの変更が要ります。
5. 絶対ルール 9 の「biyori-hub のモジュールを import しない」を、ビヨリコンシェルのモジュールにも広げますか(広げるなら、テストを足すのがよいと思います)。
6. 判断がつかなかった 7 行(第1部の表)。特に `docs/data-sources.md:96` は、段階38 の決まりと合わない可能性があります。
7. `config.yaml` の `live.user_agent`(`biyori-hub/ikimonobiyori …`)を変えますか(通信の動きの変更です)。
8. コンシェルへの提案(7 章の形)の候補として、資料の候補に `site_ref`・座標を足すこと、資料に commit・版を足すこと、読み直しを切る引数、資料の JSON Schema があります。どれを出すかは、コンシェルの段階 4 で実物を見てからです。
