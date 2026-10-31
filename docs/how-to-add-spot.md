# 花の名所を足す手順(段階33)

花の名所は `ikimonobiyori/data/catalog/flowers.yaml` に足す。値の出どころがないものは推測で埋めない(不明は書かない)。

1. **名称・所在**: `name`、`tags.prefecture`、`tags.city`(市区町村。座標からの推測はしない)、`tags.flower_kinds`。
2. **状態**: 最初は `status: candidate`。運営者の公式ページで開花状況が読め、公式の通信先のときに `approved`(`approved_by`・`approved_at`)。
3. **例年の時期**: 種類ごとに `flower_windows`(`kind`・`start`・`end`・`source_url`・`source_year`)。公式の通信先の外のホストで読んだ値は `source_host` と出所の区分 `source_class: secondary` を付ける(段階34。値は候補の根拠に使う。`python -X utf8 -m ikimonobiyori.catalog_audit` が漏れを調べる)。
4. **今年のイベント期間**: `events`(年つき。`verified: true` は公式の通信先のページで年つきで確かめたもの。紹介サイトで読んだ年つきの期間は `source_class: secondary` を付けて入れる)。
5. **座標**: 取得元は公式の通信先の地図(`official_map`)か Wikidata(`wikidata`)だけ。`python -X utf8 -m ikimonobiyori.catalog_coords fetch --live --max-requests N`(`BIYORI_ALLOW_LIVE=1`・計測フックの下だけ)→ `apply`。名称と市区町村が一致し、県の範囲に入るときだけ入る。ほかは座標なし(地域・市区町村のタグで地域の質問には出る)。`point` を入れたら `coordinate_source`(`kind`・`checked_on`)も入れる。
6. **現況の情報源**: 台帳 `data/sources/flowers.yaml` に足し、名所の `status_sources` に id を書く。
7. 足したら `python -X utf8 -m unittest discover -s tests` を実行する。
