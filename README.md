# イキモノビヨリ (ikimonobiyori)

紅葉・花・野鳥・高山植物の「今週末どこへ行くとよいか」「いつごろ・どこで見られるか」を、公開されている情報から下調べして答える、ネイチャーガイド役のツールです。
公式ページから読んだ今の様子、主催者の行事・観察会、気象庁の観測値から計算した平年の目安、出典つきの知識カードを組み合わせ、Claude Code の会話(スキル `ikimono-weekend`)で答えます。
出発地は既定で横浜(東京・大宮など、質問で変えられます)で、地域の指定がなければ出発地から片道 250 km 前後の、登録済みの名所の全範囲から探します。
個人・非商用の下調べのためのツールです。〇〇ビヨリ(ヤマビヨリ・ホシビヨリなど)の仲間で、共通の契約 `biyori-proposal/1`(提案)も出力します。

## 何ができるか

| 質問の例 | 答えの内容 |
|---|---|
| 「今週末の紅葉のおすすめは?」「明日 野鳥を見に行くならどこ?」「11/3のおすすめをおしえて」 | 今回のおすすめ(①②③)と、狙い別の節(近場・歩いて・遠出・ライトアップなど)。対象を指定しなければ紅葉・花・野鳥を横断 |
| 「西沢渓谷や大菩薩嶺の紅葉はどう?」「秩父・長瀞のエリアは?」 | 名所ごとの今の様子(公式ページの状態の語と「○/○時点」)・例年の時期・実用情報・出発地からの直線距離 |
| 「今週末の観察会やまつりは?」 | 主催者が決めた行事・まつりの期間(色づき・咲き具合とは別の行に書く) |
| 「東京の紅葉は、平年はいつ頃?」 | 気象庁の生物季節観測から計算した平年の目安(平均・最早・最遅、使った期間とデータ点数) |
| 「チングルマはいつ見られる?」「丹沢で見られる野草は?」 | 高山植物・野草の例年の花期(山域・地点・種の名前で) |
| 「ガンカモ類の調査とは?」「〜と〜の違いは?」 | 知識カード(出典つき)から、どんなもの → 違い → 出会い方の順の答え |
| 「写真つきのページにして」 | 直前の答えと同じ内容の、種の代表写真つきの HTML ページ |

- 今年の様子は、現地の公式な発信(自治体・観光協会・公園や施設の管理者・ビジターセンター)を主にします。公式でない情報や古い情報も、答えを止める理由にはせず、出所と日付を添えて確かさとして示します。
- 古い年の記事・SNS の投稿は根拠にしません。気象会社の見頃予想(ウェザーニュース・tenki.jp・日本気象協会など)は、転載を含めて使いません。
- 野鳥の位置は粗く丸め(既定は小数 1 桁)、正確な座標・観察者は保存も出力もしません。答えには観察のマナーを添えます。

## 仕組みの概要

事実はコードが作り、文章は書き手(エージェント)が整え、数値と日付は検査で照合します。

1. **準備と読み取り**: `ask prepare` が、記録がない・古い名所と読むページを出す。エージェントが公開ページを読み、状態の原文・日付・URL だけを `ask record` で記録する(本文は保存しない)。野鳥は `ask inat-refresh` で iNaturalist の集計を取り直す。
2. **材料**: `ask facts` が、名所ごとの今の状態・例年の時期・行事・距離・休園日などをまとめる。
3. **計画**: `ask plan` が、候補の順位・今回のおすすめ・節をコードの式で決める(値は `ikimonobiyori/data/ask/plan.yaml`)。
4. **骨組み**: `ask skeleton` が、冒頭の文・おすすめ・確かさの決まり文・出典まで、事実の入った骨組みを作る。
5. **整えと検査**: 書き手は言い回しだけを整え、`ask polish-check` が骨組みとの事実の一致(日付・距離・名前・URL など)と、文面の決まりを検査する。通らなければ骨組みのままの答えを出す。

答えの手順の全体は [`CLAUDE.md`](CLAUDE.md)(Codex 向けは同じ内容の [`AGENTS.md`](AGENTS.md))と、スキル [`.claude/skills/ikimono-weekend/SKILL.md`](.claude/skills/ikimono-weekend/SKILL.md) にあります。

### 計算による判定(v0)と契約

- `ikimonobiyori/main.py` は、依頼 `biyori-request/1` から契約 `biyori-proposal/1` の提案を作ります。v0 の計算の手法があるのは紅葉と野鳥です(桜・彼岸花・ひまわり・ホタル・夜光虫・花・冬鳥のプロファイルは骨組みで、`not_applicable: profile_skeleton` を返します)。
  - 紅葉: Open-Meteo の日最低気温から段階を決める(`temperature_progression`)。気象庁の生物季節観測との答え合わせは不合格だったため([`docs/stage14-result.md`](docs/stage14-result.md))、現況がない名所の補助の推定にとどめます。
  - 野鳥: iNaturalist の観察記録の集計から、種ごとの相対頻度(0〜1)を出す(`observation_frequency`)。
- 判定はすべて未検証(`validated: false`)で、`band` の上限は `maybe`(`go` は出しません)。確信度の数値は出力しません(`null`)。点数は他のビヨリの点数と比べません。
- 閾値・係数・窓・年数はプロファイル(`ikimonobiyori/profiles/*.yaml` の `method.params`)と方針の YAML にだけ書き、コードに直接書きません(テストが検査します)。時刻は ISO 8601(オフセットつき)、欠損は `null`、同じ入力・同じ `--now` なら同じ出力です。

## データの出どころと利用条件

記録の詳細は [`docs/data-sources.md`](docs/data-sources.md) にあります。

- **Open-Meteo**(紅葉の気温): 無料 API は非商用のみ(1 日 10,000 call)。データは CC BY 4.0。帰属表示:
  *Weather data by [Open-Meteo.com](https://open-meteo.com/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)*
  (`tests/fixtures/recorded_open_meteo_2026-10-14.json` は 2026-10-14 に取得した実際の応答の記録で、同じ帰属を付けています)。
- **iNaturalist**(野鳥の観察記録の集計・種の代表写真): 利用規約・API の推奨手順は**ユーザー確認済み(2026-10-21、data-sources.md の記録)**(`docs/data-sources.md` §3)。保存・出力するのは集計値(種ごとの件数と分類名)だけで、学習には使いません。実際の応答はリポジトリに置かず、テストは合成データで行います。写真は許可されたライセンスのものを、その場所で撮られたものではない「種の代表写真」として使い、リポジトリには入れません(写真が取れない種は Wikimedia Commons の、CC0・CC BY・CC BY-SA・パブリックドメインで作者の表記があるものを使います)。
- **気象庁 生物季節観測**(平年の目安・紅葉の答え合わせ): 出典:気象庁ホームページ「生物季節観測累年値」(https://www.data.jma.go.jp/sakura/data/download_ruinenchi.html)。公共データ利用規約(第1.0版)(https://www.digital.go.jp/resources/open_data/public_data_license_v1.0)に従い、出典と加工したことを明記しています。平年の目安(`ikimonobiyori/data/jma_normals/normals.yaml`)は、気象庁の観測値をもとにイキモノビヨリが平均等を計算したもので、気象庁が作成した値(平年値)ではありません。
- **環境省・生物多様性センター**(外来種リスト・ガンカモ類の生息調査・モニタリングサイト1000・鳥類標識調査など): 公開ページの事実を、出典つき・自分の言葉で知識カードにしています。
- **各公式サイト**(自治体・観光協会・公園や施設の管理者・ビジターセンター・博物館など): 答えるときに読み、状態の短い原文・日付・URL だけを記録します。定期的な巡回・本文の保存はせず、robots.txt や応答で自動アクセスを拒むページは読みません(人が開く URL として示します)。利用条件はページごとに確かめ、台帳に残しています。
- **地点カタログ**(`ikimonobiyori/data/sites.yaml`): [yamabiyori](https://github.com/ktakemaru/yamabiyori)(MIT)の山リスト(`MOUNTAINS`、commit `de66f10`)を一度だけ複製したもの。複製元は `copied_from` に記録しています。

### 公開しないもの

知識カード(`knowledge/cards.jsonl`)と発行物台帳(`knowledge/publications.jsonl`。メタデータとハッシュだけ)は、リポジトリの外のデータ置き場(`IKIMONOBIYORI_DATA_DIR` の下)に置き、このリポジトリには含めません。出典ごとに転載・複製の条件が違い、公開してよいか確かめきれないものがあるためです。実行で作る記録・キャッシュ・写真・ページも同じ置き場に書きます。

## 情報源の承認

- 公式の情報源(現況の台帳 `ikimonobiyori/data/sources/`、ビジターセンターの台帳 `ikimonobiyori/data/visitor_centers/`、行事の台帳 `ikimonobiyori/data/facility_events/`)は、**利用者が承認したもの**を公式の現況・行事として答えに使います。承認待ちの施設の発信・行事は答えに出ません。
- 承認の判断は利用者が行います。手順は [`docs/operations.md`](docs/operations.md) §2、判断の材料は [`docs/sources-approval.md`](docs/sources-approval.md)・[`docs/sources-approval-61.md`](docs/sources-approval-61.md) にあります。
- 紹介サイト(ウォーカープラスなど)は別の台帳(`ikimonobiyori/data/sources/secondary/`)に置き、答えでは「公式ではありません」と添える参考にとどめます。

## 使い方

Python 3.13 で確認しています。依存は `requirements.txt`(PyYAML・jsonschema・requests・pdfminer.six と、それらの依存。版は固定)です。

```
python -m pip install -r requirements.txt
```

### 会話で使う

このリポジトリを開いた Claude Code で、「今週末の紅葉のおすすめは?」「明日 野鳥を見に行くならどこ?」のように聞くと、スキル `ikimono-weekend` の手順で答えます。コマンドを直接使うときの入口は次のとおりです。

```
python -X utf8 -m ikimonobiyori.ask -h      # 質問に答える手順(prepare・facts・plan・skeleton・polish-check・verify・page など)
python -X utf8 -m ikimonobiyori.guide -h    # 名所のガイド・野草と高山植物(wildflower)・写真つきページ(page)
```

### 提案(`biyori-proposal/1`)を作る

```
# オフライン(入力 JSON = ikimono-inputs/1。tests/fixtures/synthetic_inputs.json は合成)
python -X utf8 ikimonobiyori/main.py --request REQ.json --inputs tests/fixtures/synthetic_inputs.json --now 2026-10-14T22:00:00+09:00

# 問い合わせの一覧(通信なし)
python -X utf8 ikimonobiyori/main.py --request REQ.json --plan-queries --now 2026-10-14T22:00:00+09:00

# キャッシュだけから(通信しない)
python -X utf8 ikimonobiyori/main.py --request REQ.json --cache-only --now 2026-10-14T22:00:00+09:00
```

`REQ.json` は依頼 `biyori-request/1`(`interests` に `autumn_leaves` か `birds`)。`--now` は必須(オフセットつき)です。

### 書き込み先

記録・キャッシュ・作業フォルダは、環境変数 **`IKIMONOBIYORI_DATA_DIR`** の下に書きます。未設定のときは、Windows は `%LOCALAPPDATA%\ikimonobiyori`、それ以外は `~/.local/share/ikimonobiyori` です。リポジトリの中(`ikimonobiyori/` を含む)には書きません。

### 実通信の制限

- **Open-Meteo などの実通信(`--live`)は、このリポジトリ単独では実行できません。** 環境変数 `BIYORI_ALLOW_LIVE=1`、明示的な `--max-requests`、そして通信の記録・上限・許可ホストを強制する**計測フック**(環境変数 `BIYORI_REQ_LOG`。biyori-hub の `hub/measure/`)が要ります。許可ホストは `ikimonobiyori/config.yaml` の `live.allowed_hosts_by_subject` だけです。
- **iNaturalist の集計と写真**は、単体でもイキモノビヨリ自身の小さな上限(`ikimonobiyori/netbudget.py`)の下で取りに行きます: 1 回の実行の上限(集計は 10、写真は 80 リクエスト)、同じホストへの間隔 1 秒以上、宣言済みのホストだけ、実行ごとの記録を `IKIMONOBIYORI_DATA_DIR` の下の `netlog/requests.jsonl` に残します。
- `BIYORI_UNDER_TEST=1`(テスト中)なら、`--live` は常に拒否します。

## biyori-hub との関係

[biyori-hub](https://github.com/ktakemaru/biyori-hub) は、ヤマビヨリ・ホシビヨリと同じように、このリポジトリを**固定 commit で取り込み(`vendor.lock`)**、manifest 1 枚で窓口(コンシェルジュ)に登録します。

- このリポジトリは**ハブのコードもデータも参照しません**(`tests/test_self_contained.py` が検査します)。ハブ側の `adapters/ikimonobiyori_run.py` が、取り込んだコードを子プロセスで起動し、提案を契約で検査し、部品を合成します。
- 契約 `biyori-proposal/1` の正本はハブの `schemas/` にあります。`tests/contract/biyori-proposal.schema.json` はその**写し**(検査用。`tests/contract/README.md`)で、このリポジトリでは変えません。
- 山・星を合わせた提案、窓口の最終文・独立検査器・定期実行・計測フックはハブの仕事です。窓口との統合のテストはハブ側にあります。
- ハブから呼ばれても単体で聞かれても、同じコマンド・同じ書き込み先(`IKIMONOBIYORI_DATA_DIR`。ハブは必ず渡します)を使います。

## テストと CI

```
python -X utf8 -m unittest discover -s tests
```

- テストは通信しません(ソケットは `tests/nonet.py` で禁止、子プロセスも `tests/nonet_child/` で禁止)。テストごとの所要時間は `python -X utf8 tools/slow_tests.py` で測れます。
- GitHub Actions([`.github/workflows/ci.yml`](.github/workflows/ci.yml))が、push と pull request のときに Ubuntu 24.04 と Windows で Python 3.13 の同じテストを実行します(`BIYORI_UNDER_TEST=1`。実通信はしません)。
- ゴールデン(`tests/fixtures/golden/`)は、出力が変わっていないことを確かめます。

## ファイル構成

- `ikimonobiyori/` パッケージ
  - 答えの手順: `ask.py`(質問に答える手順の CLI)、`answer_plan.py`(計画)、`skeleton.py`(骨組み)、`polish.py`・`ask_verify.py`(整えの一致検査・答えの検査)、`observations.py`(読んだ事実の記録と答えの材料)、`guide.py`(ガイド型の答え・写真)、`wildflower.py`(野草・高山植物)、`knowledge.py`(知識カード)、`jma_normals.py`(平年の目安)、`visitor_centers.py`・`facility_events.py`・`festivals.py`(施設の発信・行事・まつり)
  - 計算による提案: `engine.py`(依頼 + 入力 + プロファイル → 提案)、`methods/`(手法)、`fetch/`(パーサー・キャッシュ・取得層)、`compose.py`(紅葉と野鳥の部品の合成)、`main.py`(CLI)
  - `profiles/` 対象ごとのプロファイル、`data/` 名所カタログ・台帳・方針の YAML、`config.yaml` 取得層の運用値、`schemas/` スキーマ、`paths.py` ファイルの場所、`livegate.py` 実通信の許可の判定、`netbudget.py` 単体での通信の上限
- `data/jma_phenology/` 気象庁 生物季節観測の累年値の CSV(取得したままのもの)と、並べ替えた `normalized.csv`。紅葉の答え合わせに使う([`data/jma_phenology/README.md`](data/jma_phenology/README.md))
- `docs/` 設計と調査の記録(段階ごとの指示書・報告書を含む。biyori-hub の中にあったときの記述が残ります)
  - [`docs/design.md`](docs/design.md) 設計(役割の分担・時期の型・対象別の仕様・名所カタログ・検証方針)
  - [`docs/data-sources.md`](docs/data-sources.md) データ源ごとの使いみち・取り方・利用条件・出典表示
  - [`docs/operations.md`](docs/operations.md) 運用手順(指示書の渡し方・台帳の承認・知識カードのバックアップ)
  - [`docs/ask-rubric.md`](docs/ask-rubric.md) 答えの評価表
  - [`docs/proposal-mapping.md`](docs/proposal-mapping.md) 記録から提案 `biyori-proposal/1` への対応
  - [`docs/validation-plan.md`](docs/validation-plan.md)・[`docs/stage14-result.md`](docs/stage14-result.md) 紅葉の答え合わせの計画と結果
  - [`docs/how-to-add-spot.md`](docs/how-to-add-spot.md) 名所の足し方
- `tests/` テスト。`tests/fixtures/` は合成データ・Open-Meteo の記録・ゴールデン(`golden/`)、`tests/contract/` は契約の写し
- `tools/slow_tests.py` テストの所要時間の計測

## ライセンス

[MIT](LICENSE)。データの出典は上記のとおり(Open-Meteo は CC BY 4.0、iNaturalist の利用条件はユーザー確認済み〔2026-10-21〕、気象庁のデータは公共データ利用規約(第1.0版)で加工を明記)。
