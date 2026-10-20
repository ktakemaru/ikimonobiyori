# 取得の記録(気象庁 生物季節観測の累年値ファイル)

段階13 フェーズ 3 で、作業指示書の「通信の許可」に従い**一度だけ**取得した(再取得のループ・定期実行は作っていない。ファイルごとに 6 秒あけた)。
入口のページ: https://www.data.jma.go.jp/sakura/data/download_ruinenchi.html(https://www.data.jma.go.jp/sakura/data/index.html からリンク)
取得の道具: Python urllib(User-Agent `ikimonobiyori stage13 one-time manual download (personal, non-commercial)`)。スクリプトはリポジトリに置いていない(一度だけの取得のため)。

出典: 気象庁ホームページ「生物季節観測累年値」(https://www.data.jma.go.jp/sakura/data/download_ruinenchi.html)

このフォルダの CSV はリポジトリに置かない(`.gitignore`。`docs/data-sources.md` §1.4、判断 D-03)。この記録だけを置く。

| ファイル | 現象 | URL | 取得日時 | HTTP | バイト数 | SHA-256 |
|---|---|---|---|---|---|---|
| 015.csv | かえで紅葉 | https://www.data.jma.go.jp/sakura/data/ruinenchi/015.csv | 2026-10-21T07:46:19+09:00 | 200 | 50963 | `278c175a8661f3c1c82cf4119d4609aab05dad159f6388bec5fe90eaebbd7008` |
| 016.csv | かえで落葉 | https://www.data.jma.go.jp/sakura/data/ruinenchi/016.csv | 2026-10-21T07:46:25+09:00 | 200 | 50487 | `9a6dca67a54e52b3922fbaac0b4df5f433328d62494ccc20fa7514d3ebd6f618` |
| 013.csv | いちょう黄葉 | https://www.data.jma.go.jp/sakura/data/ruinenchi/013.csv | 2026-10-21T07:46:31+09:00 | 200 | 50015 | `62ddc1a01ae2e6859f8cfefba66139528c0f78940b36e0c84466d89fefa90b0a` |
| 014.csv | いちょう落葉 | https://www.data.jma.go.jp/sakura/data/ruinenchi/014.csv | 2026-10-21T07:46:37+09:00 | 200 | 50241 | `7c90dbd3e037ce1eb1e078f1f6be803e3aa6328ce5271f47786ef632d4c0579e` |
| 004.csv | さくら開花 | https://www.data.jma.go.jp/sakura/data/ruinenchi/004.csv | 2026-10-21T07:46:43+09:00 | 200 | 50241 | `53b51c305f867fe2a0a8a398c449cec73439cfdcae0ec64cbe845b7c2f9a76ad` |
| 005.csv | さくら満開 | https://www.data.jma.go.jp/sakura/data/ruinenchi/005.csv | 2026-10-21T07:46:50+09:00 | 200 | 50034 | `6be6f4ae2e149f473563d510efed0fa0ad7ad740f642598f3df62267437e07ff` |
| 001.csv | うめ開花 | https://www.data.jma.go.jp/sakura/data/ruinenchi/001.csv | 2026-10-21T07:46:56+09:00 | 200 | 47922 | `7ebf1033dc9978bc2d24c586c18b5cb976c82e720bbe50ee9d6ed8e791aac609` |
