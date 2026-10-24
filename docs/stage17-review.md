# 段階17 見直し用の一覧(仮承認した情報源と名所)

段階17 で足した情報源と名所の一覧です。仮承認(`approved_by: claude_code_provisional`、2026-10-24)したものは、ユーザーが見直して取り消せます。
条件は段階16 と同じです: 公式の発信者・実際に読めた・利用条件に要約や出典つきの事実の利用を禁じる文がない・本文に埋め込まれた指示文がない。
ページは WebFetch(要約の道具)で 2026-10-24 に 1 回ずつ読みました。原文との照合は人の目でしていません。

取り消すとき: 台帳(`ikimonobiyori/data/sources/<対象>.yaml`)の `approval` を `{status: revoked, reason: ...}` か `pending` にします。名所カタログ(`data/catalog/<対象>.yaml`)は `status: retired` と `retired_at`・`retired_reason` にします。そのあと `python -X utf8 -m ikimonobiyori.sources check` を実行します。

## 情報源(10 件。仮承認 6・pending 4)

| 対象 | 情報源 id | 発信者 | URL | 状態の書き方 | 読めたか | 直近の更新日 | 仮承認 | 迷った点 |
|---|---|---|---|---|---|---|---|---|
| 野鳥 | tokyo-port-birdpark-today | 日本野鳥の会(東京港野鳥公園の管理者) | https://wbsj-wildbirdpark.blog.jp/archives/cat_773662.html | 語なし。記事「YYYY年M月D日の野鳥公園」に確認種数(「30種」) | 読めた(robots.txt なし) | 2026-10-22 | **仮承認** | 発信の場所がブログ(blog.jp)。記事は管理者のレンジャーのもの。利用条件は日本野鳥の会のリンクのページで確かめた(禁止なし。サイトポリシーのページは見つからない) |
| 野鳥 | tokyo-park-kasai-news | 東京都公園協会(葛西臨海公園) | https://www.tokyo-park.or.jp/park/kasairinkai/news/index.html | 語なし。鳥類園のニュースレター・ガイドツアーの記事が不定期 | 読めた | 2026-10-15 | **仮承認** | 日々の観察情報がなく、読んでも今の様子が分からないことが多い |
| 野鳥 | yatsu-higata-center | 谷津干潟自然観察センター | https://www.seibu-la.co.jp/yatsuhigata/ | 未確認 | **HTTP 503** | — | pending | 読めなかった。次に読めたら条件を確かめる |
| 野鳥 | wbsj-yokohama-blog | 日本野鳥の会(横浜自然観察の森の指定管理者) | https://wbsj-yokohama.blog.jp | 語なし。鳥以外の記事も多い | 読めた(robots.txt なし) | 2026-10-24 | **仮承認** | 鳥の記事が少ない(最新 3 件のうち 1 件) |
| 野鳥 | abiko-bird-museum-toridayori | 我孫子市(鳥の博物館) | https://www.city.abiko.chiba.jp/bird-mus/info2/shupambutsu/toridayori.html | PDF の中。日付なし | 一部(partial) | — | pending | 状態が PDF の中で日付がない。利用条件も未確認 |
| 花 | hitachi-flower-info | 国営ひたち海浜公園(ひたち公園管理センター) | https://www.hitachikaihin.jp/flower-plant/flower-info/ | 語: 紅葉見頃（後半）・見頃（後半）→ 見頃、咲き始め → 咲き始め。日付は「撮影日:M月D日」(年なし) | 読めた(robots.txt なし) | 2026-10-23 | **仮承認** | 年のない日付なので新しさはいつも「新しさ不明」。トップページの最初の要約で道具が「フッターに指示文」と報告したが、確かめ直すと指示文はなかった(道具の誤認と判断)。利用条件「リンク及び著作権」はリンク元の連絡を求める(このツールはリンクを公開しない) |
| 花 | tokyo-park-kyufurukawa-news | 東京都公園協会(旧古河庭園) | https://www.tokyo-park.or.jp/park/kyu-furukawa/news/index.html | 語なし(2026 年の見出し)。記事に「約100種中80種開花」(10月19日現在) | 読めた | 2026-10-19 | **仮承認** | 数から段階を決めないので、段階はいつも空 |
| 花 | tokyo-park-jindai-news | 東京都公園協会(神代植物公園) | https://www.tokyo-park.or.jp/park/jindai/news/index.html | 語なし。開花状況の記事はまだない | 読めた | 2026-10-08 | **仮承認** | 読んでも今の状態が分からないことが多い |
| 花 | showakinen-flower-information-flowers | 国営昭和記念公園 | https://www.showakinen-koen.jp/flower-information/ | 未確認 | **HTTP 504** | — | pending | 段階16 から応答がない |
| 花 | keisei-rose-garden | 京成バラ園芸株式会社 | https://www.keiseirose.co.jp/garden/ | 語: 秋バラが見頃です。→ 見頃(「開花中」は段階なし) | 読めた | 2026-10-23 | pending | 利用規約のページが見つからない。robots.txt も未確認 |

紅葉・冬鳥の台帳の変更(新しい情報源はなし):
- 冬鳥 `agano-hyoko-monthly`(阿賀野市 瓢湖): 一覧から今月の記事をたどる設定 `follow`(修正⑥)。承認は段階16 のまま(ユーザー)。
- 紅葉 `hakone-kankou-koyo`: 日付の種類 `date_basis: observed_date`(「M/D現在」。修正⑤)、covers の仙石原(長安寺)・恩賜箱根公園を名所カタログの id に(湖尻はカタログ外のまま。D-39)。

## 名所(12 件。すべて仮承認)

| 対象 | id | 名前 | 現況の情報源 | 迷った点 |
|---|---|---|---|---|
| 野鳥 | yacho-0001 | 東京港野鳥公園 | tokyo-port-birdpark-today | 干潟。潮位表(気象庁、地点「東京」)の人が開く URL を付けた |
| 野鳥 | yacho-0002 | 葛西臨海公園 鳥類園 | tokyo-park-kasai-news | 干潟は隣の葛西海浜公園。潮位表の URL を付けた |
| 野鳥 | yacho-0003 | 谷津干潟 | yatsu-higata-center(pending) | 情報源が読めていないが、公式の観察施設があるので名所として載せた |
| 野鳥 | yacho-0004 | 横浜自然観察の森 | wbsj-yokohama-blog | — |
| 野鳥 | yacho-0005 | 手賀沼(我孫子市鳥の博物館の周辺) | abiko-bird-museum-toridayori(pending) | 公式の調査結果は PDF の広報誌だけ(中身は確かめていない) |
| 花 | hana-0001 | 国営ひたち海浜公園 | hitachi-flower-info | 種類: コキア・キバナコスモス・バラ |
| 花 | hana-0002 | 旧古河庭園 | tokyo-park-kyufurukawa-news | 種類: 秋バラ |
| 花 | hana-0003 | 神代植物公園 | tokyo-park-jindai-news | 種類: 秋バラ・菊 |
| 花 | hana-0004 | 国営昭和記念公園 | showakinen-flower-information-flowers(pending) | 種類: コスモス。情報源が読めていない |
| 花 | hana-0005 | 京成バラ園 | keisei-rose-garden(pending) | 民間の施設。種類: 秋バラ |
| 紅葉 | kouyou-0034 | 箱根 仙石原(長安寺) | hakone-kankou-koyo | 段階14b では仙石原を除いていた(当時の指示書)。段階16 D-67 の課題として足した |
| 紅葉 | kouyou-0035 | 恩賜箱根公園 | hakone-kankou-koyo | 例年の時期の記載がない |

代表点の座標は、すべて Claude Code が公式ページの所在地・地名から推定した値です(野鳥は小数 1 桁 = area_10km、花・紅葉は小数 2 桁)。標高は不明(null)。

## 取り消しを検討してほしいもの
- **葛西臨海公園・横浜自然観察の森・神代植物公園の情報源**: 公式で読めるが、今の様子(状態)がほとんど書かれていない。答えでは「根拠」に出ないことが多い。
- **国営ひたち海浜公園**: 日付に年がないので、答えではいつも「新しさ不明(年の記載なし)」。
- **谷津干潟・国営昭和記念公園**: 読めない情報源しかない名所を載せている(人が開く URL として出る)。
