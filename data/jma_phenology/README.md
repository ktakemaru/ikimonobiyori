# 気象庁 生物季節観測(答え合わせの正解側のデータ)

段階13 で作成。気温型(紅葉・いちょう・桜・梅)の答え合わせ(`docs/validation-plan.md`)に使う。v0 の判定はこのデータを使わない。

## 出典
- 元のデータ: 出典:気象庁ホームページ「生物季節観測累年値」(https://www.data.jma.go.jp/sakura/data/download_ruinenchi.html)
- `normalized.csv`: 気象庁「生物季節観測累年値」(https://www.data.jma.go.jp/sakura/data/download_ruinenchi.html)を加工して作成(イキモノビヨリ `ikimonobiyori.jma_phenology`)。公共データ利用規約(第1.0版)(https://www.digital.go.jp/resources/open_data/public_data_license_v1.0)
- 加工の内容: 列の年 × 地点の表を「地点・年・現象」ごとの行に並べ替え、月日(MMDD)を日付(YYYY-MM-DD)にした。値 0 を「値なし」(`status: no_value`)にした。年をまたぐ値を隣の年の日付にした(下の「推測」)。値のある最後の年より後の列(未来の年)を落とした。地点名の全角空白を除いた。値は変えていない。

## 置いているもの・利用条件
- `raw/*.csv`: 取得した元のファイル(気象庁の累年値ファイルそのもの。cp932・CRLF。**変更していない**。`.gitattributes` で改行も変換しない)。取得の記録は `raw/SOURCES.md`(URL・日時・SHA-256)。
- `normalized.csv`: 加工したもの。**ファイルの冒頭の `#` で始まる 3 行に、出典と加工したことを書いている**(`ikimonobiyori.jma_phenology.read_csv` は読み飛ばす)。
- 利用条件: 気象庁ホームページのコンテンツは公共データ利用規約(第1.0版)に準拠(複製・公衆送信・翻案を認める。数値データは著作権の対象外)。出典と、加工したものには加工したことを記載する。2026-10-21 のユーザーの判断で、このリポジトリ(public)に置くことにした(`docs/data-sources.md` §1.4、判断 D-03 の見直し・D-22)。
- 加工したものを、気象庁が作成した未加工の情報であるかのように使わないこと(規約 1.1.2)。

## 作り方(通信しない)
```
python -X utf8 -m ikimonobiyori.jma_phenology normalize --raw-dir data/jma_phenology/raw --out data/jma_phenology/normalized.csv
python -X utf8 -m ikimonobiyori.jma_phenology summary --normalized data/jma_phenology/normalized.csv --region 関東甲信
```
読み方の定義は `ikimonobiyori/data/jma_phenology.yaml`。

## normalized.csv の列
| 列 | 内容 |
|---|---|
| `station_no` | CSV の地点番号(3 桁。国際地点番号 47NNN の下 3 桁と読める = 推測) |
| `station_name` | 地点名 |
| `phenomenon_code` / `phenomenon` | 現象(`015` kaede_koyo かえでの紅葉、`016` kaede_rakuyo、`013` icho_koyo いちょうの黄葉、`014` icho_rakuyo、`004` sakura_kaika、`005` sakura_mankai、`001` ume_kaika) |
| `year` | 列の年(季節の年) |
| `date` | 観測日(YYYY-MM-DD)。値なしは空 |
| `status` | `observed` / `no_value`(欠測・観測なし・観測終了の区別は CSV からは分からない) |
| `rm` | CSV の rm の値をそのまま(意味は**未確認**。フォーマットの PDF を読めなかった。値は 4・6・7・8・9) |
| `cross_year` | 1 = 年をまたいだ値(隣の年の日付にした) |
| `lat` / `lon` / `elevation_m` | CSV に含まれない。9 地点(長野・宇都宮・前橋・熊谷・水戸・甲府・銚子・東京・横浜)だけ、気象庁「地域気象観測所一覧」(https://www.jma.go.jp/jma/kishou/know/amedas/ame_master.pdf、2026-10-22 取得)から `ikimonobiyori/data/jma_phenology.yaml` に書いた値(出典: 気象庁ホームページ。度分を度に直し小数 4 桁)。ほかの地点は空 |

## 推測で決めた部分
- 年をまたぐ値: 春の現象(うめ・さくら)の 10〜12 月の値は前年、秋の現象(紅葉・落葉)の 1〜3 月の値は翌年の日付と読んだ。フォーマットの PDF の断片(「2015」「2014 12 15」「2015」「1215」)と、実際の値の月の分布からの推測。**要目視(フォーマットの PDF)**。
- 地点の都道府県・地方の対応は、地点名からの対応(外部の資料で確認していない)。
