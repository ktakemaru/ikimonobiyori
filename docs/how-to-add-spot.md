# 花の名所を足す手順(段階33)

花の名所は `ikimonobiyori/data/catalog/flowers.yaml` に足す。値の出どころがないものは推測で埋めない(不明は書かない)。

1. **名称・所在**: `name`、`tags.prefecture`、`tags.city`(市区町村。座標からの推測はしない)、`tags.flower_kinds`。
2. **状態**: 最初は `status: candidate`。運営者の公式ページで開花状況が読め、承認した通信先のときだけ `approved`(`approved_by`・`approved_at`)。
3. **例年の時期**: 種類ごとに `flower_windows`(`kind`・`start`・`end`・`source_url`・`source_year`)。承認した通信先の外のホストで読んだ値は `source_host` と `unapproved_host: true` の印を付ける(`python -X utf8 -m ikimonobiyori.catalog_audit` が漏れを調べる)。
4. **今年のイベント期間**: `events`(年つき。`verified: true` は承認した通信先の公式ページで年つきで確かめたものだけ)。
5. **座標**: 取得元は承認した通信先の公式の地図(`official_map`)か Wikidata(`wikidata`)だけ。`python -X utf8 -m ikimonobiyori.catalog_coords fetch --live --max-requests N`(`BIYORI_ALLOW_LIVE=1`・計測フックの下だけ)→ `apply`。名称と市区町村が一致し、県の範囲に入るときだけ入る。ほかは座標なし(地域を指定しない質問には出ない)。`point` を入れたら `coordinate_source`(`kind`・`checked_on`)も入れる。
6. **現況の情報源**: 台帳 `data/sources/flowers.yaml` に足し、名所の `status_sources` に id を書く。
7. 足したら `python -X utf8 -m unittest discover -s tests` を実行する。
