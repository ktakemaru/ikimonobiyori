# 段階18 報告: 現地の情報の答えを biyori-proposal/1 で出すコマンド

**最初に読むこと**
1. 結論: できた。止める条件には当たっていない。
   - 同じ日に読んだ記録・名所カタログ・情報源の一覧から、契約 `biyori-proposal/1` の提案を組み立てるコマンドを作った。通信も LLM も使わない。決定的で、`go` は出さない。
   - 契約は変えていない。新しいホストも足していない。
2. 使い方: `python -X utf8 -m ikimonobiyori.sources proposals --now <時刻> [--subjects <対象>|all] [--date …|--weekend next] [--early] [--late] [--region …] [--out <ファイル>]`。既定は標準出力。提案の id は `ikimonobiyori:status:<対象>:<日>:<名所 ID>`(気温の推定の id と区別。D-29)。
3. band: `maybe` か `no` だけ。
   - `maybe` になるのは、見ごろ・最盛、始まり、公式の見頃予測が対象の日にかかる、段階の分からない書き方で新しい(D-14)、のどれか。それ以外は `no`。
   - 新しさは band を変えず、`evidence` と `known_limits` に書く。公式の日付が対象の日より 30 日以上前の記録は使わない。
4. 照合が要る値は `evidence` と `details` の両方に入れた: 公式の状態の原文・公式の日付の原文(年のない日付は `M/D`)・新しさ・読み方。
5. ハブ側の検査: biyori-hub の `python hub/validate.py <ファイル>`(読むだけ)で、ゴールデン 4 つとも `OK (biyori-proposal/1)`(D-26)。
6. テスト: `python -X utf8 -m unittest discover -s tests` → `Ran 386 tests` / `OK`(段階18 の前は 355 件。確認後の id の変更で 3 件を足した)。
7. 確認後(2026-10-24): id を区別した(D-29)、D-14 の 3 つ目と段階の対応はユーザー確認済み(D-30・D-31)、カタログにない 23 地点は次の段階で足す(末尾に一覧。D-32)。

## 各フェーズでしたこと

| フェーズ | commit | 内容 |
|---|---|---|
| 0 | `3823eee` | 決定の記録 D-01〜D-13、段階計画に段階18 を差し込み(春以降を 1 つずつ後ろへ) |
| 1 | `4c2d4fa` | 対応表と規則 `docs/proposal-mapping.md`、方針 `policy.yaml` の `proposals`(段階の対応・日数・文言)。コードより先 |
| 2 | `c4cb6e3` | `ikimonobiyori/proposals.py` と `sources proposals`。共通の入力 `_answer_inputs`、使える行の判定 `usable_status_row` |
| 3 | `3486f40` | `answer` も `usable_status_row` を使う(出力は変わらない)。手順(スキル・AGENTS.md・CLAUDE.md)に「10. 提案を出す」。整合のテスト |
| 4 | `039e1c6` | 次のテストを足した。<br>・契約の検査<br>・ゴールデン(紅葉・冬鳥・花・野鳥)<br>・性質のテスト<br>・子プロセスの CLI(ソケット禁止)<br>ハブの `validate.py` で確認した。不具合 3 つを直した(D-24) |
| 5 | `6778337` | 今日の記録で 5 通りを出した(`docs/stage18-trial.md`)。重複した警告を直した(D-27) |
| 6 | (この commit) | この報告 |

## 決定事項からはみ出した判断(`docs/stage18-decisions.md`)

- **D-14** band の規則の補い:
  - 終わり(4)は `no`。`--late` のときだけ `maybe`。
  - 対象の日が 14 日より先なら、見頃予測だけで判断する。
  - 段階の分からない書き方で、新しさが「新しい」「やや古い」なら `maybe`。`answer` が同じ記録をおすすめに入れることがあるため。
  - 情報なしの書き方は提案にしない。
- **D-15** 使う記録は同じ日に読んだものだけ(再利用の規則のまま)。そのため「読んだ日から 7 日以上」の印は今は付かない。
- **D-16・D-28** 名所カタログにない地点は提案にしない。座標がないため。警告に名前をまとめる。
- **D-17** 同じ名所の複数の行(地点の書き方)は、名所・日ごとに 1 件にまとめる。id の形 `ikimonobiyori:<対象>:<日>:<名所 ID>` を守るため。
- **D-18** `known_limits` は方針の決まった文だけ。プロファイルの `known_limits` は使わない。紅葉のものは気温の推定の限界で、冬鳥・花のものには内部用語が入っている。
- **D-19** 交通の注意は指示書どおり `care.manners` に入れた。
- **D-20** `site_ref` は `ikimonobiyori:<名所 ID>`。`area_id` は付けない。
- **D-21** 位置の粗さは、カタログとプロファイルの粗い方。座標もその粗さに丸める。
- **D-22** 年のない日付は `M/D` で書き、`last_updated` は `null`。
- **D-23** `evidence` の読み方は日本語のラベル。禁止語 `code` を避けるため。元の値は `details` にある。
- **D-24** 不具合 3 つを直した。
  - 補った年の印が `summarize` の行になかった(項目を足した。`answer` の出力は変わらない)。
  - 作業用の集合が `data_as_of` に残り、JSON にできなかった。
  - 更新日がない行に、更新日の年を補った印が付いた。
- **D-27** 提案のある名所は「現況なし」の警告に出さない。

## ユーザーの確認が要ること

確認事項 1〜4 は、ユーザーの確認(2026-10-24)で決まった。

1. **カタログ外の地点**: 次の段階で足す。今は足さず、末尾に一覧を残した(D-32)。
2. **band の補い**(D-14)の 3 つ目: ユーザー確認済み(D-30)。
3. **`phenology_stage` の対応**: ユーザー確認済み(D-31)。
4. **id の重なり**: 現況の提案の id を `ikimonobiyori:status:…` に変えた。気温の推定の id は変わらない(D-29。テストで確認、ハブの `validate.py` でも 4 つとも OK)。

push と PR はしていない。

## 次の段階への提案

- **ハブ側**:
  - 取り込みの commit を上げる(`vendor.lock`)。
  - manifest に、`interface.snapshot` とは別に `proposals` のコマンドを宣言する。通信しない、子プロセスの許可先は `none`。読み取りは、エージェントがその場の承認の後に行う。
  - 既存のスナップショット(気温の推定)を置き換えるかは、ハブで決める。置き換えない方が安全。現況のない名所の補助として残せる。
  - ハブの契約の検査、独立検査器の対応(`details.kind: official_status` の提案。`go` なし・確信度なし)、ゴールデン。
  - manifest の `phenology_labels` が、冬鳥・花にはない。窓口が表示に使う段階のラベルを、`details.official_status.stage_label` から取る形にするかを決める。
- **ビヨリコンシェルの最小版**: 次の順で呼ぶ。
  1. エージェントが読んで記録する(手順 1〜5)。
  2. `proposals --subjects all --now … --date …` を呼び、出力を山・星の提案と一緒に collect に渡す。
  3. 最終文で、`evidence` の `official_state`・`freshness`・`read_by` を照合する。読み方が「簡易な読み取り」なら、その 1 行を出す。
- **v0 の推定を混ぜるか**: このコマンドでは混ぜていない。混ぜるなら、現況の提案のない名所だけに別の提案として足す。`known_limits` に「気温からの推定(未検証。答え合わせで不合格)」を付け、id を分ける(例: 対象名に `_estimate`)。混ぜると窓口の絞り込みで現況と推定が並ぶので、窓口の規則(同じ名所なら現況を先に)を先に決めるのがよい。

## 途中経過

- フェーズ0: `stage18` を main(0350d72)から作成。決定の記録 `docs/stage18-decisions.md`(D-01〜D-13)、段階計画に段階18 を差し込んだ(春以降を 1 つずつ後ろへ)。ハブ側の設計と、このリポジトリの既存の契約の検査(`tests/helpers.py` の `schema_errors`、`tests/contract/` の写し)を読んで確かめた(ハブの内容は写していない)。
- フェーズ1: 対応表と規則 `docs/proposal-mapping.md`、方針の値 `policy.yaml` の `proposals`(段階の対応・日数・文言)。band の規則の補い D-14、同じ日の記録だけ D-15、カタログ外の地点は警告 D-16 など。
- フェーズ2: `ikimonobiyori/proposals.py` と `python -X utf8 -m ikimonobiyori.sources proposals`(`answer` と同じ入力 + `--weekend this|next`・`--request-id`・`--out`)。共通の入力の読み取りを `_answer_inputs` に、使える行の判定を `sources.usable_status_row` に分けた。合成データで契約の検査に通った。
- フェーズ3: `answer` のおすすめの選び方が `sources.usable_status_row` を使うようにした(提案と同じ判定。答えの出力は変わらない。既存テストはそのまま通る)。スキル・AGENTS.md・CLAUDE.md の手順に「10. 提案を出す」を足した。整合のテスト `tests/test_proposals.py`(5 件。答えのおすすめ・根拠の名所と提案の名所が一致、おすすめは maybe)。
- フェーズ4: `tests/test_proposals.py`(27 件: 整合・契約・ゴールデン 4 対象・決定的・go なし・evidence の照合値・年のない日付・年の補いの印・band の規則・古さ・30 日・14 日より先・警告の重複なし・同じ名所の複数行・位置の丸め・交通の注意・禁止語・印の付いた記録・子プロセスの CLI(ソケット禁止)・--out・--weekend next)。ハブの `validate.py` でゴールデン 4 つが OK(D-26)。不具合 3 つを直した(D-24)。
- フェーズ5: 今日の記録で 5 通り(紅葉 次の土日・来週末、冬鳥、花、野鳥)を出した(`docs/stage18-trial.md`)。すべて契約の検査に通った。答えとの違いはカタログ外の地点だけ(D-28)。重複した警告の不具合を直した(D-27)。

## 名所カタログにない紅葉の地点(2026-10-24 の記録。次の段階でカタログに足す。D-32)

2026-10-24 に読んだ記録のうち、名所カタログにない地点(情報源の covers の `name` で記録したもの)。座標がないので提案にならず、警告の「名所の一覧にない地点」に出た。名前は情報源の covers の `name`。

| # | 地点 | 情報源 ID |
|---|---|---|
| 1 | 八溝山 | `daigo-kanko-koyo` |
| 2 | 月待の滝 | `daigo-kanko-koyo` |
| 3 | 永源寺(大子町) | `daigo-kanko-koyo` |
| 4 | 男体山(大子町) | `daigo-kanko-koyo` |
| 5 | 元箱根 | `hakone-kankou-koyo` |
| 6 | 宮ノ下 | `hakone-kankou-koyo` |
| 7 | 旧街道 甘酒茶屋付近 | `hakone-kankou-koyo` |
| 8 | 箱根湯本 | `hakone-kankou-koyo` |
| 9 | 六方沢 | `nikko-kankou-autumn-leaves` |
| 10 | 小網ダム | `nikko-kankou-autumn-leaves` |
| 11 | 川治温泉 | `nikko-kankou-autumn-leaves` |
| 12 | 平家の里 | `nikko-kankou-autumn-leaves` |
| 13 | 日光だいや川公園 | `nikko-kankou-autumn-leaves` |
| 14 | 日光の社寺 | `nikko-kankou-autumn-leaves` |
| 15 | 杉並木公園 | `nikko-kankou-autumn-leaves` |
| 16 | 湯西川水の郷 | `nikko-kankou-autumn-leaves` |
| 17 | 蛇王の滝 | `nikko-kankou-autumn-leaves` |
| 18 | 足尾 銀山平 | `nikko-kankou-autumn-leaves` |
| 19 | 霧降滝 | `nikko-kankou-autumn-leaves` |
| 20 | 鬼怒川温泉 丸山 | `nikko-kankou-autumn-leaves` |
| 21 | 鬼怒楯岩大吊橋 | `nikko-kankou-autumn-leaves` |
| 22 | 鬼怒沼 | `nikko-kankou-autumn-leaves` |
| 23 | 龍王峡 | `nikko-kankou-autumn-leaves` |

参考: 現況の情報源の covers には、ほかに名前で書かれた地点が 3 つある。2026-10-24 の記録にはなかった。
- 接岨峡・長島ダム・奥大井湖上駅(`okuooi-koyo`)
- 智満寺(`okuooi-koyo`)
- 西沢渓谷(`yamanashi-kankou-koyo`)
