# 段階83 進捗

- 開始 2026-11-13 07:53(+09:00)。データ集めの区切り 15:08、終了 15:53。
- ブランチ: stage82 は main 未マージ → stage82 の最後の commit(9ab6588)の上に stage83 を切った。

## 第1部(段階82 の続き 2 の本人の判断 6 件)
- 1 中央アルプス観光を公式に: guide_mode.yaml の research.declared_publishers_approved(中央アルプス観光株式会社・フッターの英語名 "Chuo Alps Kanko Co., Ltd.")。https://chuo-alps.com/season/ を読み、千畳敷カール(長野県駒ヶ根市)のチングルマ「7月〜8月」を記録(research record)。
- 2 河津桜・冬桜の型: 資料を作って確かめた(season_place・河津桜 5 か所・例年2月〜3月)。変更なし。
- 3 紹介サイトの行: そのまま。
- 4 畳平の所在地: 記録を岐阜県高山市に直した(データ置き場の observations/flowers.jsonl。元は flowers.before-stage83.jsonl)。岐阜県は都県の一覧の外なので資料から外れる。
- 5 カタログの月だけの記載: season_place.catalog_window_text(窓が月まるごとで note に「旬」がない → 「1月〜3月」)。
- 6 「○年○月現在」: observations.strip_as_of(parse_typical の前に除く)。渡良瀬遊水地の公式の記録は時期なしになった。
- 関係するテスト 660 件 OK、新しいテスト test_stage83_part1(6 件)OK。全テストは第2部と一緒に。
- 通信: Web 検索 1・取得 4(research fetch 3 回(2 回は名前の確かめで止まり読まず)・web-fetch 1)。

## 第2部(観察記録の集計) 08:23
- 第1部 commit d0df656(全テスト 2,220 件・回帰 34/34)。
- 問い合わせの確かめ(通信 約 30 回): week= は ISO 週・開花の注釈(12/13)で件数が変わる・place_id の複数指定は足し算・histogram の week_of_year は /observations の week= と同じ。
- seasonal_obs.py(集計・保存・status・fetch)・data/observations/seasonal.yaml・資料の節「例年この時期の観察記録」[O…]・verify(seasonal_obs_errors)・ask warm に取り直しの数。
- 取得は裏で: scratchpad の fetchloop.sh(1 回 60 回まで・束ごとに保存)。順: 44〜49 週 → 2・5・8月の週 → 残り。進み具合は scratchpad の fetch_progress.log。再開は同じ 3 つの呼び出し(取れた分は飛ばす)。

## 第3部・第4部(仕組み)
- カードの calendar: {environment, months, target, where} と tale: {topic}。ふつうの選び方(load_shown)からは除き、資料が calendar_cards(2 枚・場所や種を決めない質問は 4 枚)・tale_cards(1 枚)で足す。

## 第3部・第4部(カード) 08:55
- 集計の取得は終わった: 522 回(6 地域 × 52 週 × 3 回 + 合計 6 × 5 回)。status の missing 0。
- カードの束: c01 横浜自然観察の森(環境省)・c02/c03 我孫子市鳥の博物館の鳥だより・c04 三番瀬(千葉県)・c05 ライチョウ(静岡市・環境省)・c06 磯(海の博物館)・c07 東京都建設局の花の暦12か月+小話7・c08 奥日光の冬(日光自然博物館・環境省)・c09 谷津干潟だより・c10 てがたん15号(小話4)。束のファイルは scratchpad の cards/。
- 既存のカードへの札 55 件(データ置き場の knowledge/calendar_tags.jsonl。バックアップの許可の一覧に足した)。
- 権利メモを各サイトのサイトポリシーで確かめて直した(34 枚)。海の博物館は未確認 → 施設の解説。
- カード 787 枚(暦 60・小話 11)。バックアップ済み。
- 次: 全テストの結果を見て第2部〜第4部の仕組みを commit → 暦の空き(表)を埋める → 小話の一覧(第4部 3)。
