# 段階18 報告(作業中)

## 途中経過

- フェーズ0: `stage18` を main(0350d72)から作成。決定の記録 `docs/stage18-decisions.md`(D-01〜D-13)、段階計画に段階18 を差し込んだ(春以降を 1 つずつ後ろへ)。ハブ側の設計と、このリポジトリの既存の契約の検査(`tests/helpers.py` の `schema_errors`、`tests/contract/` の写し)を読んで確かめた(ハブの内容は写していない)。
- フェーズ1: 対応表と規則 `docs/proposal-mapping.md`、方針の値 `policy.yaml` の `proposals`(段階の対応・日数・文言)。band の規則の補い D-14、同じ日の記録だけ D-15、カタログ外の地点は警告 D-16 など。
- フェーズ2: `ikimonobiyori/proposals.py` と `python -X utf8 -m ikimonobiyori.sources proposals`(`answer` と同じ入力 + `--weekend this|next`・`--request-id`・`--out`)。共通の入力の読み取りを `_answer_inputs` に、使える行の判定を `sources.usable_status_row` に分けた。合成データで契約の検査に通った。
- フェーズ3: `answer` のおすすめの選び方が `sources.usable_status_row` を使うようにした(提案と同じ判定。答えの出力は変わらない。既存テストはそのまま通る)。スキル・AGENTS.md・CLAUDE.md の手順に「10. 提案を出す」を足した。整合のテスト `tests/test_proposals.py`(5 件。答えのおすすめ・根拠の名所と提案の名所が一致、おすすめは maybe)。
- フェーズ4: `tests/test_proposals.py`(27 件: 整合・契約・ゴールデン 4 対象・決定的・go なし・evidence の照合値・年のない日付・年の補いの印・band の規則・古さ・30 日・14 日より先・警告の重複なし・同じ名所の複数行・位置の丸め・交通の注意・禁止語・印の付いた記録・子プロセスの CLI(ソケット禁止)・--out・--weekend next)。ハブの `validate.py` でゴールデン 4 つが OK(D-26)。不具合 3 つを直した(D-24)。
