# 構成(段階77 で CLAUDE.md・AGENTS.md の「構成」から移した箇条)

CLAUDE.md の大きさを増やさないために移した。内容は変えていない。

- `ikimonobiyori/fetch/spot_coords.py` 公式のスポットのページ(日光市観光協会・箱根町観光協会だけ)の、地図の埋め込み(iframe の src)の座標の数字の組だけを読む小さなコード(`sources spot-coords`。段階19 の続き。HTML・本文は保存しない。数字がなければ「座標なし」で推測しない。計測フックの下・robots.txt を先に・2 秒以上空ける・429 で止める)。名所カタログの座標は、これで確認できたものだけを承認する(推定の座標は使わない)。
- `ikimonobiyori/proposals.py` 同じ日に読んだ記録・名所カタログ・情報源の一覧から `biyori-proposal/1` の提案を組み立てる(`sources proposals`。段階18。通信しない・LLM なし・`go` を出さない。対応と規則は `docs/proposal-mapping.md`、値は `policy.yaml` の `proposals`)。`answer` と同じ記録・同じ使える行の判定(`sources.usable_status_row`)を使う。
- `ikimonobiyori/regional.py` 地域(都道府県)を必須の絞り込みにした花の答え(`sources regional`。段階32。通信しない・書き込まない)。確度の 3 段階(公式の現況・今年のイベント期間つき・例年の時期のみ)・見頃を過ぎたものと状態を読み取れなかったものの除外・近隣(県外)の分離・内部用語の自己検査。値と文は `ikimonobiyori/data/regional/policy.yaml`。既存の `answer`(`answer.py`)は変えない。花の名所は `flower_windows`(種類ごとの例年の時期。取得元の年つき)・`events`(今年のイベント期間。`verified` は公式の通信先の年つきの記載。紹介サイトの値は `source_class: secondary`)・`tags.city` を持てる。
- `ikimonobiyori/catalog_audit.py` 花の名所の、紹介サイトなど(公式ではない)由来の値(出所の区分 `source_class: secondary`。旧い印 `unapproved_host` も同じ)を一覧にする監査(`python -X utf8 -m ikimonobiyori.catalog_audit`。通信しない・書き込まない)。区分の漏れ(公式の通信先の外なのに区分がない値)は終了コード 1(出所の記録のため。値は使う)。
