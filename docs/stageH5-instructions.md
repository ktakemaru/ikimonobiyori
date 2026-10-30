# 段階H5 作業指示書(ハブ側で行う作業。C:\biyori-hub、ブランチ stageH5)

作成: 2026-10-30(ikimonobiyori 段階26 のフェーズE)。**この指示書は ikimonobiyori の段階26 が書いたもの。ハブのリポジトリは段階26 では一切変更していない**(読んだだけ)。

## 前提
- ikimonobiyori の `stage24`・`stage25`・`stage26` を、ユーザーが push して `main` にマージしたあとに行う(マージ前の commit を vendor.lock に入れない)。
- 無人実行でよい。迷ったら安全側(vendor.lock を更新しない・変更しない)に倒し、報告に書く。

## (a) vendor.lock の更新(段階10・H3・H4a の既存のやり方)
1. ikimonobiyori の `main` の先頭のフル SHA(40 桁)を確かめる(`git ls-remote https://github.com/ktakemaru/ikimonobiyori main` か GitHub の画面)。
2. `vendor.lock` の `ikimonobiyori` の行を、`https://github.com/ktakemaru/ikimonobiyori` と**そのフル SHA** に直す(タブ区切り 3 列。現在は `fa47992b9f9ad7e35e40ef6af3be1e7281fd47fe`)。他の行は触らない。
3. `hub/fetch_vendor.py` で取り込み、`hub/check_vendor.py` で検証する(`vendor/` は読み取り専用扱い。手で直さない)。
4. 取り込み後、`vendor/ikimonobiyori` が ikimonobiyori の `main` と同じ内容であること(`tests/contract/` の契約の写し `biyori-proposal.schema.json` が、ハブの `schemas/biyori-proposal.schema.json` と同じであること。段階26 の確認では**同じ**だった)。

## (b) `details.reference_count` の確認結果(段階26 で読んで判断したこと)
- **落ちない見込み**。根拠:
  - 契約 `schemas/biyori-proposal.schema.json` の `details` は `{"type": "object", "description": "ビヨリ固有の自由欄。窓口は根拠として使わない。"}` で、項目の数・名前を制限していない。ルートも `additionalProperties: true`。
  - ハブのコードが `details` を読む場所は `hub/core/ikimono_status.py`(`details.kind` と `details.observations` の `read_at` だけ)、`hub/core/collect.py`(`details.component.generated_at`・`details.display_lines`)、`hub/core/checktext.py`(`details.score_explain`)。**項目数・項目名を数えたり、未知の項目を拒否したりする箇所はなかった**。
  - `tests/test_stage5b3.py:251` は `details["component"]` の項目が 3 つであることを確かめるが、これは部品(`component`)の中で、`reference_count` は `details` 直下なので関係しない。
- **ただし要確認(落ちる可能性があるもの)**: ハブのテストの期待値(golden)に、`details` の中身まで比べているものがある。`tests/fixtures/stage12/golden_proposals/g3_composed.json`・`g4_child_birds.json`・`g4_composed.json`、`tests/fixtures/stageH4a/golden_status_snapshot.json` に、参照数が付く名所(東京港野鳥公園・葛西臨海公園・六義園・新宿御苑など)の名前がある。これらが「取り込んだコードを実行した結果」と比べるテストなら、`details.reference_count` が増えて**比較で落ちる**。静的な固定の写しなら落ちない。H5 で、vendor 更新の前後に全テストを実行して確かめる。落ちた場合は、ハブの golden を作り直すのではなく、**ユーザーに報告して承認を待つ**(ハブの CLAUDE.md の規則に従う)。

## (c) ハブ側のテスト・CI で確かめること
1. vendor 更新の前に、ハブの全テストが通ること(基準)。
2. 更新後、全テスト・`hub/validate.py`・`hub/check_vendor.py` が通ること。
3. ikimonobiyori の manifest の写し(`agents/ikimonobiyori/manifest.yaml` の `phenology_labels`・`stage_order`・`ttl_s`)が、ikimonobiyori の側の値と同じであること(段階24〜26 は変えていない)。
4. 独立検査器・最終文の検査器が、`details.reference_count` のある提案で落ちないこと(上の (b) の確認を実際に実行して確かめる)。
5. 野鳥の「定評」の地点が増えたこと(野鳥 20・冬鳥 8 前後)で、窓口の回答の件数や並びが変わるテストがないか。

## (d) 窓口の最終文で参照数を使うかの取り決めの案(契約は変えない)
- 案1(推奨): 最終文では参照数を**使わない**(今のまま)。参照数は ikimonobiyori 側のガイド型の答えと、提案の `details.reference_count`(窓口は根拠として使わない自由欄)に残す。
- 案2: 窓口の最終文に、場所の行の文末で `（参照数 N）` と凡例を 1 回付ける。条件: (1) `details.reference_count` がある提案だけ(ない場所には付けない・1 の仮置きをしない)、(2) 凡例は答えに 1 回、(3) 文言は ikimonobiyori の `data/guide/policy.yaml` の `reference_count` と同じ(`（参照数 {n}）`、「参照数は、その場所を紹介している独立した発行元の数です。」)、(4) 最終文の検査器に、参照数が `details.reference_count` と一致することを確かめる規則を足す。**契約は変えない**(自由欄 `details` の項目の名前を取り決めるだけ)。
- どちらにするかは、ユーザーの判断。決まるまでは案1。

## 報告に書くこと
- vendor.lock の更新前後の SHA、(b) の確認結果(実際に落ちたか)、全テストの件数、案1・案2 のどちらにしたか。
