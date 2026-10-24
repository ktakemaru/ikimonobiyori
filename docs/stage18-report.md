# 段階18 報告(作業中)

## 途中経過

- フェーズ0: `stage18` を main(0350d72)から作成。決定の記録 `docs/stage18-decisions.md`(D-01〜D-13)、段階計画に段階18 を差し込んだ(春以降を 1 つずつ後ろへ)。ハブ側の設計と、このリポジトリの既存の契約の検査(`tests/helpers.py` の `schema_errors`、`tests/contract/` の写し)を読んで確かめた(ハブの内容は写していない)。
- フェーズ1: 対応表と規則 `docs/proposal-mapping.md`、方針の値 `policy.yaml` の `proposals`(段階の対応・日数・文言)。band の規則の補い D-14、同じ日の記録だけ D-15、カタログ外の地点は警告 D-16 など。
- フェーズ2: `ikimonobiyori/proposals.py` と `python -X utf8 -m ikimonobiyori.sources proposals`(`answer` と同じ入力 + `--weekend this|next`・`--request-id`・`--out`)。共通の入力の読み取りを `_answer_inputs` に、使える行の判定を `sources.usable_status_row` に分けた。合成データで契約の検査に通った。
