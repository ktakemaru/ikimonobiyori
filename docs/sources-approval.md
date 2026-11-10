# 情報源の承認の一覧（台帳から作る。段階65 第3部）

この一覧は、台帳の実際の承認（`approval`）から `python -X utf8 -m ikimonobiyori.ask sources --approval` が作る（手で書き換えない。推奨と規約メモは `ikimonobiyori/data/approval_notes.yaml` に項目の id で置く）。
**承認は本人が行う**（Claude Code が記入するのは、本人がチャットの指示文で対象（id）と条件を明示したものだけ。`docs/operations.md` §2-0）。この表の推奨は参考で、承認とはみなさない。

## 集計

| 台帳 | 承認済み | 承認待ち | 取り消し・引退 |
|---|---|---|---|
| 施設（visitor_centers/centers.yaml） | 14 | 17 | 0 |
| 現況の情報源（sources/） | 44 | 34 | 3 |
| 行事・展示（facility_events/events.yaml） | 1 | 0 | 0 |
| 名所カタログ（catalog/） | 134 | 14 | 2 |

## 推奨の基準
- **承認してよい**: 公式・範囲内・転載禁止の明示がなく、最新の更新日が近く、状態や種名が読める。
- **要判断**: 使えるが、転載禁止の明示がある、または運営主体・利用期間に気になる点がある。
- **保留**: 今は使えない（更新が古い・シーズンが終わった・読めない・状態の語がない）。事情が変われば見直す。

承認した場合に使う内容は、施設台帳（A）では次のとおり。ほかの項目は使わない（記事や文章を転載しない）。
> 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。14日以内で、季節内の発信だけ。

## 1. 承認待ち

### 1-A. ビジターセンター・自然観察施設（承認待ち 17件）
承認の手順: 台帳の `approval.status` を `approved` にし、`approved_by` に承認した人を書く（docs/operations.md §2-2）。

| 施設 | 運営主体 | 最新情報のページ | 更新頻度 | 形式 | 規約メモ（転載禁止の明示の有無） | 範囲内 | 承認した場合に使う内容 | 推奨と理由 |
|---|---|---|---|---|---|---|---|---|
| 丹沢大山ナビ（神奈川県） | 神奈川県 自然環境保全センター（所管） | https://www.pref.kanagawa.jp/docs/f4y/tanzawaoyama_navi.html | 不明（更新日 2026-06-12） | html | 転載禁止の明示なし。サイトポリシー: 引用は自由・出典を記載・二次利用は所管へ事前問い合わせ。転載禁止の明示なし。自動取得の記載なし。robots.txt は /docs/f4y/ を拒否していない | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない | **保留**: ナビの『旬の植物』『開花情報』『紅葉情報』の各ページの URL を本文から確認できていない。最新は 2026-06-12。URL を確認してから |
| かながわパークレンジャー 開花記録（神奈川県） | 神奈川県 自然環境保全センター 自然保護公園部自然保護課 | https://www.pref.kanagawa.jp/docs/f4y/02yama/kanagawaparkranger/bloom/bloomtoppage.html | 不明（更新日 2026-06-20） | html | 転載禁止の明示なし。丹沢大山ナビと同じサイトポリシー。転載禁止の明示なし。robots.txt は拒否していない | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない | **保留**: 開花記録の最新が 2026-06-20 で、今は更新が止まっている。次の開花期に再確認（県の規約は引用自由・出典記載で問題なし） |
| 桐生自然観察の森 | 桐生市 都市整備部 公園緑地課 | https://www.city.kiryu.lg.jp/forest/shizen/ennai/1027794.html | 不明（更新日 2026-11-04） | html | **転載禁止の明示あり**。転載禁止の明示あり（このサイトについて: 文書・画像は許可なく使用・転載を禁止）。自動取得の記載なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 3〜10月 9:00〜16:30、11〜2月 9:30〜16:00。休園は火曜（祝日の場合は開園）と12/29〜1/3 | **要判断**: 転載禁止の明示あり。市の施設で最新 2026-11-04。許すかは本人の判断 |
| 市川市行徳野鳥観察舎（あいねすと） | 市川市 環境部 自然環境課 | https://www.city.ichikawa.lg.jp/page/1759.html | 年に4回（あいねすと通信） | pdf | **転載禁止の明示あり**。転載禁止の明示あり（サイトポリシー: 無断で複製・転用することはできない。引用等の例外あり）。自動取得の記載なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない | **保留**: 年4回のPDF（最新 2025-10-27）で現況に向かない。転載禁止の明示あり |
| 那須高原ビジターセンター | 那須平成の森フィールドセンター（プライバシーポリシーの原文） | https://nasu-vc.jp/nature/ | 随時（ページの記載） | html | 転載禁止の明示なし。プライバシーポリシーのみ（著作権ページは未確認）。転載禁止の明示なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 4〜11月 8:30〜17:30、休館は水曜（祝日の場合は翌日。紅葉期などは開館） | **保留**: 最新が 2026-05-09 で更新が古い。次の更新があれば見直し |
| 塩原温泉ビジターセンター | 確認できず（トップが文字化けして原文を読めなかった） | http://www.siobara.or.jp/vc/ | 不明（更新日 2026-11-06） | html | 転載禁止の明示なし。規約ページのリンクは見当たらず。フッターは Copyrights (C) 2023 のみ。ページが Shift_JIS 系で文字化けし、確認できていない項目が多い。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜16:30（休館の曜日は確認できず）、12/29〜1/3 休館 | **保留**: ページが文字化けして運営主体・規約を読めていない。確認できてから |
| 八島ビジターセンター（霧ヶ峰） | 町立（ページの記載。町名の文字はページ上で確認できず） | https://shimosuwaonsen.jp/yashima/category/weekly/ | 週1回（2026年は9/4〜10/30の毎週） | html | **転載禁止の明示あり**。転載禁止の明示あり（指示書の調査: PDF に『無断転載を禁ずる』。今回は PDF 本文が読めず確認できていない）。サイトのポリシーページは個人情報の取り扱いのみ。robots.txt は /wp-admin/ のみ拒否 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 開館 4月下旬〜11月上旬 9:30〜16:30、期間中無休。2026年の営業は 11/3 に終了 | **保留**: 今期は 10/30 で終了（冬季閉鎖）。転載禁止の明示あり（PDF）。来季（4月下旬）に再判断 |
| 裏磐梯ビジターセンター | 記載なし | https://urabandai-vc.jp/nature/ | 未確認 | html | 利用条件のページ確認できず(段階59 第1部) |  |  | **保留**: 範囲内か未確認 |
| 上高地ビジターセンター | 環境省 | https://www.kamikochi-vc.or.jp/whats-new/nature-updates | 未確認 | html | 出所明示で引用・転載可、商用は要連絡 |  |  | **要判断**: 範囲内か未確認 |
| ピッキオ（軽井沢野鳥の森） | ピッキオ | https://picchio.co.jp/archives/blog-cat/natureinfo | 未確認 | html | 転載の記載は確認できず |  |  | **保留**: 規約未確認 |
| 谷川岳インフォメーションセンター | 環境省 | 個別ページ未確認 | 未確認 | 未確認 | 出典明示で利用可(PDL1.0) |  |  | **保留**: 個別ページ未確認 |
| 小峰ビジターセンター | 東京都公園協会(サイトの表記) | https://www.tokyo-park.or.jp/park/komine/news/nature/ | 未確認(最新 2026-10-25) | html | サイトポリシー本文は未確認(段階60 第4部) |  |  | **保留**: 規約(サイトポリシー)未確認。自然情報の更新はある |
| 野呂川広河原インフォメーションセンター | 環境省 | 自然情報のページなし(施設の案内だけ) | 未確認 | 未確認 | 環境省の著作権・リンクについて |  |  | **保留**: 現況の発信が確認できない。11月中旬〜6月上旬は休館 |
| 赤沼自然情報センター | 栃木県立日光自然博物館(ページの表記) | https://blog.nikko-nsm.co.jp/cat_blog/低公害バス自然情報/ | 未確認 | html | 転載の記載なし(段階60 第4部) |  |  | **要判断**: 規約の確認と、ブログの更新日の確認。開館は 11/30 まで |
| 鹿沢インフォメーションセンター | 環境省 | 自然情報のページなし(施設の案内だけ) | 未確認 | 未確認 | 環境省の著作権・リンクについて |  |  | **保留**: 現況の発信が確認できない |
| 田貫湖ふれあい自然塾 | 環境省(サイトの表記) | https://tanuki-ko.gr.jp/nature-season/ | 未確認 | html | 転載の記載なし。All Rights Reserved |  |  | **保留**: 自然情報の日付が未確認 |
| 神奈川県立宮ヶ瀬ビジターセンター | 未確認(カードの出典の自然公園だより(2010年1月)は神奈川県公園協会のサイトに掲載) | なし(公式の施設ページを確認できなかった) | 未確認 | pdf | 規約のページなし(公式の施設ページが見つからない)。県の宮ケ瀬湖周辺施設の指定管理のページ(2026-03-27 更新)にも施設名がない | はい | カード2枚(シモバシラ)の事実と出典だけ | **保留**: 段階61 第8部で台帳に承認待ちで追加。公式サイトと現在の運営(2016年に閉館して改装されたとする報道がある。公式では未確認)を確かめられない |

### 1-B. 現況の情報源の台帳（承認待ち 34件）
承認の有無にかかわらず読んで記録してよい（段階34。区分は『公式ではない』などで出る）。承認は、台帳上の『公式の現況』扱いにするかどうかの判断。

| 台帳 | 情報源 | 発行元の種類 | 最新情報のページ | 形式 | 読めた状態（確認日） | 推奨と理由 |
|---|---|---|---|---|---|---|
| autumn_leaves.yaml | 東京都公園協会(紅葉を見に行こう!)（tokyo-park-kouyou-special） | park_manager | https://www.tokyo-park.or.jp/special/kouyou/index.html | status_page | ok（2026-11-05） | **要判断**: ユーザーの承認待ち(段階50)。条件(公式・読めた・利用条件に禁止なし・本文に指示文なし)は満たすが、今は前シーズンの最終版で今年の現況がない。通信先 www.tokyo-park.or.jp は段階47で承認済み。今シ… |
| autumn_leaves.yaml | 川根本町まちづくり観光協会（okuooi-koyo） | tourism_association | https://okuooi.gr.jp/pickup/page.php?id=3 | status_page | partial（2026-10-23） | **保留**: 状態が画像で、エージェントが読めない(読めたとは言えない) |
| autumn_leaves.yaml | 国営昭和記念公園(昭和記念公園管理センター)（showakinen-hanadayori） | park_manager | https://www.showakinen-koen.jp/hanadayori/ | status_page | ok（2026-11-10） | **保留**: 段階76 で足した(承認待ち)。同じ公園の showakinen-flower-information は承認済み。記事の一覧のページを別に台帳に持つかは本人の判断 |
| autumn_leaves.yaml | 塩原温泉観光協会（siobara-kankou） | tourism_association | https://www.siobara.or.jp/ | status_page | unconfirmed（2026-10-23） | **保留**: メンテナンス中で読めていない。現況のページがあるかも未確認 |
| autumn_leaves.yaml | 秩父観光協会（chichibu-kanko-kouyou） | tourism_association | https://www.chichibuji.gr.jp/event/kouyou/ | forecast_page | ok（2026-10-23） | **要判断**: robots.txt で AI エージェントによる取得を拒む意思が読み取れる(この道具は名指しされていないが安全側)。今年の状況もない |
| autumn_leaves.yaml | 伊勢原市（isehara-oyama-koyo） | municipality | https://www.city.isehara.kanagawa.jp/kankou_guide/docs/2024012600094/ | forecast_page | ok（2026-10-23） | **保留**: 2024 年公開の古いページで、今年の状態・日程がない(ライトアップ「11月下旬ごろ」だけ)。現況の情報源にせず、例年の時期の参考として人が開く URL にとどめる(ユーザーの見直し 2026-10-23) |
| autumn_leaves.yaml | 八方尾根索道事業者協議会(白馬八方尾根)（happo-one-news-green） | facility_operator | https://www.happo-one.jp/news-green/ | status_page | ok（2026-10-23） | **要判断**: 状態の決まった語がなく段階が付けられない。人が開く URL として扱う(段階16 の見直し 2026-10-23) |
| autumn_leaves.yaml | 一般社団法人いわき観光まちづくりビューロー(いわき市観光サイト)（iwaki-kanko-koyo） | tourism_association | https://kankou-iwaki.or.jp/feature/autumnleaves/top | status_page | ok（2026-11-10） | **保留**: 段階73 第3部で見つけた公式の紅葉情報(観光協会)。承認は本人 |
| autumn_leaves.yaml | 公益社団法人新潟県観光協会(にいがた観光ナビ)（niigata-kanko-koyo） | tourism_association | https://niigata-kankou.or.jp/season/autumn_leaves/ | status_page | ok（2026-11-10） | **保留**: 段階73 第3部で見つけた公式の紅葉情報(県の観光協会)。承認は本人 |
| autumn_leaves.yaml | 下郷町観光協会（shimogo-kanko-blog） | tourism_association | https://shimogo.jp/blog/ | status_page | ok（2026-11-10） | **保留**: 段階73 で見つけた公式の紅葉の発信(町の観光協会のブログ)。承認は本人 |
| birds.yaml | 谷津干潟自然観察センター(習志野市の施設)（yatsu-higata-center） | park_manager | https://www.seibu-la.co.jp/yatsuhigata/ | status_page | unconfirmed（2026-10-24） | **保留**: 読めなかった(HTTP 503)。利用条件も未確認。人が開く URL として扱う。次に読めたら条件を確かめる |
| birds.yaml | 我孫子市(鳥の博物館)（abiko-bird-museum-toridayori） | municipality | https://www.city.abiko.chiba.jp/bird-mus/info2/shupambutsu/toridayori.html | status_page | partial（2026-10-24） | **要判断**: 状態が PDF の中にあり、日付がない(readable: partial)。利用条件も未確認。人が開く URL として扱う |
| flowers.yaml | 京成バラ園芸株式会社(京成バラ園)（keisei-rose-garden） | facility_operator | https://www.keiseirose.co.jp/garden/ | status_page | ok（2026-10-24） | **要判断**: 利用条件を確かめられなかった(規約のページが見つからない)。robots.txt も未確認。人が開く URL として扱う |
| flowers.yaml | 横浜市(ガーデンネックレス横浜)（gardennecklace-yamate） | municipality | https://gardennecklace.city.yokohama.lg.jp/ | reference_link | unconfirmed（2026-10-31） | **保留**: 参考リンク(現況の情報源に数えない)。通信先が承認した4ホストにない。docs/pending-hosts.md に載せ、読まない |
| flowers.yaml | 横浜市西区役所（yokohama-nishi-hana） | municipality | https://www.city.yokohama.lg.jp/nishi/shokai/kanko/spot/hana.html | reference_link | unconfirmed（2026-10-31） | **保留**: 参考リンク(現況の情報源に数えない)。通信先が承認した4ホストにない。docs/pending-hosts.md に載せ、読まない |
| flowers.yaml | 横浜市(ガーデンネックレス横浜)（gardennecklace-kodomo） | municipality | https://gardennecklace.city.yokohama.lg.jp/ | reference_link | unconfirmed（2026-10-31） | **保留**: 参考リンク(現況の情報源に数えない)。通信先が承認した4ホストにない。docs/pending-hosts.md に載せ、読まない |
| flowers.yaml | 株式会社小田急箱根(箱根強羅公園)（hakonenavi-gorapark） | facility_operator | https://www.hakonenavi.jp/gorapark/info/ | status_page | unconfirmed（2026-10-31） | **保留**: 通信先がユーザーが承認した4ホスト(kanagawaparks.com・sankeien.or.jp・kanagawa-kankou.or.jp・www.welcome.city.yokohama.jp)にない。docs… |
| flowers.yaml | 綾瀬市(都市部 みどり公園課)（ayase-rose-garden） | municipality | https://www.city.ayase.kanagawa.jp/soshiki/midorikoenka/koen/4/15170.html | reference_link | unconfirmed（2026-10-31） | **保留**: 参考リンク(現況の情報源に数えない)。通信先が承認した4ホストにない。docs/pending-hosts.md に載せ、読まない |
| flowers.yaml | 小田原城総合管理事務所(小田原市観光協会)（odawaracastle-kikka） | facility_operator | https://odawaracastle.com/ | status_page | unconfirmed（2026-10-31） | **保留**: 通信先がユーザーが承認した4ホスト(kanagawaparks.com・sankeien.or.jp・kanagawa-kankou.or.jp・www.welcome.city.yokohama.jp)にない。docs… |
| flowers.yaml | 神奈川県(掲載ページ)（pref-kanagawa-zarugiku） | prefecture_tourism | https://www.pref.kanagawa.jp/docs/n8f/cnt/f300562/p327323.html | reference_link | unconfirmed（2026-10-31） | **保留**: 参考リンク(現況の情報源に数えない)。通信先が承認した4ホストにない。docs/pending-hosts.md に載せ、読まない |
| flowers.yaml | 川崎大師平間寺（kawasakidaishi-kikka） | temple_shrine | https://www.kawasakidaishi.com/ | status_page | unconfirmed（2026-10-31） | **保留**: 通信先がユーザーが承認した4ホスト(kanagawaparks.com・sankeien.or.jp・kanagawa-kankou.or.jp・www.welcome.city.yokohama.jp)にない。docs… |
| flowers.yaml | エリアマネジメント横須賀共同事業体(ソレイユの丘)（soleil-blooming-info） | park_manager | https://www.soleil-park.jp/blooming-info | status_page | unconfirmed（2026-10-31） | **保留**: 通信先がユーザーが承認した4ホスト(kanagawaparks.com・sankeien.or.jp・kanagawa-kankou.or.jp・www.welcome.city.yokohama.jp)にない。docs… |
| flowers.yaml | 横浜市(里山ガーデン実行委員会)（satoyama-garden-welcome） | municipality | https://www.satoyama-garden.jp/welcome/ | reference_link | unconfirmed（2026-10-31） | **保留**: 参考リンク(現況の情報源に数えない)。通信先が承認した4ホストにない。docs/pending-hosts.md に載せ、読まない |
| flowers.yaml | 神奈川県公園協会・サカタのタネグリーンサービスグループ（kanagawa-park-sakaigawa） | park_manager | https://kanagawa-park.or.jp/sakaigawa/ | reference_link | unconfirmed（2026-10-31） | **保留**: 参考リンク(現況の情報源に数えない)。通信先が承認した4ホストにない。docs/pending-hosts.md に載せ、読まない |
| flowers.yaml | 神奈川県公園協会・小田急電鉄共同事業体(秦野戸川公園)（kanagawa-park-hadanotokawa） | park_manager | https://www.kanagawa-park.or.jp/hadanotokawa/kaika.html | status_page | unconfirmed（2026-10-31） | **保留**: 通信先がユーザーが承認した4ホスト(kanagawaparks.com・sankeien.or.jp・kanagawa-kankou.or.jp・www.welcome.city.yokohama.jp)にない。docs… |
| secondary/autumn_leaves.yaml | tenki.jp(日本気象協会。紹介サイト)（tenki-kouyou-kanagawa） | weather_company | https://tenki.jp/kouyou/3/17/ | reference_link | refused（2026-11-04） | **保留**: 利用規約が、ブラウザ・RSSリーダー以外での取得を禁じているので、読まない(人が開くリンク)。段階34〜45で読んで観察の記録に残した過去の値は、日付つきの参考として残る。今後は新しく読まない |
| secondary/autumn_leaves.yaml | ウェザーニュース(人が開くリンク)（weathernews-koyo） | weather_company | https://weathernews.jp/koyo/ | reference_link | unconfirmed（2026-11-04） | **保留**: 複製・転載の禁止が取得に及ぶか判断に迷うため読まない(人が開くリンク)。読んでよいかはユーザーの確認が要る |
| secondary/autumn_leaves.yaml | ジョルダン(紹介サイト)（jorudan-koyo） | portal_media | https://www.jorudan.co.jp/koyo/ | reference_link | unconfirmed（2026-11-04） | **保留**: 転送ページしか返らず本文が読めない。回避の工夫(別経路・キャッシュ)はしない |
| secondary/autumn_leaves.yaml | GO TOKYO(東京都観光財団。紹介サイト)（gotokyo-autumn-leaves） | tourism_association | https://www.gotokyo.org/en/story/guide/autumn-leaves-forecast/index.html | reference_link | ok（2026-11-04） | **要判断**: 現況でも今年の予想でもなく、固定の時期だけ。通信先として承認されていない(gotokyo.org)ので、人が開くリンクにとどめる |
| secondary/autumn_leaves.yaml | 高尾ビジターセンター(発信元)・山と溪谷オンライン(掲載。紹介サイト)（yamakei-takao-visitor-center） | portal_media | 台帳に記載（山と溪谷オンラインの記事。ここには書かない） | reference_link | ok（2026-11-06） | **要判断**: 承認待ち(段階53 第3部)。利用規約を読んで利用者が承認するまで、答えの材料にしない |
| secondary/autumn_leaves.yaml | 御岳ビジターセンター(発信元)・山と溪谷オンライン(掲載。紹介サイト)（yamakei-mitake-visitor-center） | portal_media | 台帳に記載（山と溪谷オンラインの記事。ここには書かない） | reference_link | ok（2026-11-06） | **要判断**: 承認待ち(段階53 第3部)。利用規約を読んで利用者が承認するまで、答えの材料にしない |
| secondary/birds.yaml | バードリサーチ(特定非営利活動法人。参加者の投稿の集計。公式ではない)（bird-research-season-front） | portal_media | https://www.bird-research.jp/?page_id=2209 | reference_link | ok（2026-11-08） | **保留**: 承認待ち(段階61 第5部)。利用条件が確かめられず、投稿の集計なので、本人の判断まで答えの材料にしない |
| wintering_birds.yaml | 印西市立本埜第二小学校(本埜白鳥の郷のページ)（inzai-motono-hakucho） | municipality | https://motono-e.inzai.ed.jp/hakucho | status_page | unconfirmed（2026-11-07） | **保留**: 指示書 段階58 第10部。承認は本人が決める |
| wintering_birds.yaml | 三条市（sanjo-hakucho-hirai） | municipality | https://www.city.sanjo.niigata.jp/sanjonavi/see_do/nature/swan/2316.html | status_page | ok（2026-10-23） | **要判断**: 利用条件に、利用の前に市へ連絡するよう求める一文がある。個人利用の道具のため、事前連絡はしない。公開を検討するときに利用条件を見直す(ユーザーの判断 2026-10-23)。読まずに、人が開く URL として扱う |

### 1-D. 名所カタログの候補（status: candidate。14件）

| 台帳 | 名所（id） | 出典 |
|---|---|---|
| catalog/autumn_leaves.yaml | (例)〇〇渓谷の遊歩道（kouyou-example-0001） | https://example.org/kouyou-example-0001 |
| catalog/autumn_leaves.yaml | (例)△△山の中腹の広葉樹林（kouyou-example-0002） | https://example.org/kouyou-example-0002 |
| catalog/flowers.yaml | 港の見える丘公園（hana-0007） | https://www.city.yokohama.lg.jp/ |
| catalog/flowers.yaml | 横浜イングリッシュガーデン（hana-0008） | https://www.city.yokohama.lg.jp/ |
| catalog/flowers.yaml | 山下公園（hana-0009） | https://www.city.yokohama.lg.jp/ |
| catalog/flowers.yaml | 八景島 丘の広場バラ園（hana-0011） | https://www.city.yokohama.lg.jp/ |
| catalog/flowers.yaml | 日比谷花壇大船フラワーセンター（hana-0014） | https://www.city.kamakura.kanagawa.jp/ |
| catalog/flowers.yaml | 相模川ローズガーデン（hana-0018） | https://www.city.atsugi.kanagawa.jp/ |
| catalog/flowers.yaml | 平塚市総合公園バラ園（hana-0020） | https://www.city.hiratsuka.kanagawa.jp/ |
| catalog/flowers.yaml | 平塚八幡宮 菊花展（hana-0025） | https://www.city.hiratsuka.kanagawa.jp/ |
| catalog/flowers.yaml | 土屋ざる菊園（hana-0026） | https://www.city.hiratsuka.kanagawa.jp/ |
| catalog/flowers.yaml | イシックス馬入のお花畑（hana-0029） | https://www.city.hiratsuka.kanagawa.jp/ |
| catalog/flowers.yaml | 生田緑地ばら苑（hana-0034） | https://www.ikuta-rose.jp/open/open.html |
| catalog/flowers.yaml | 筑波実験植物園（hana-0041） | https://tbg.kahaku.go.jp/migoro-event/syokubutsu/index.html |

## 2. 承認済み

承認した人: user = 本人、claude_code_provisional = 段階の指示で Claude Code が仮に承認したもの（本人の見直しの対象）。

### 2-A. ビジターセンター・自然観察施設（承認済み 14件）

| 施設 | id | 承認した人・日 | 最新情報のページ | 規約メモ | 承認前の推奨 |
|---|---|---|---|---|---|
| 県立秦野ビジターセンター | hadano-vc | user（2026-11-07） | https://hadanovc.blogspot.com/ | 転載禁止の明示なし。専用の規約ページは確認できず。丹沢公式トップに『サイト内の写真は無断使用禁止』（写真のみ。要約由来）。robots.txt 未確認 | **承認してよい**: 県立・公式。最新 2026-11-06。転載禁止の明示なし。運営主体（指定管理者）の原文だけ未確認 |
| 県立西丹沢ビジターセンター | nishitanzawa-vc | user（2026-11-07） | https://nishitanzawashizenkyoushitsu.blogspot.com/ | 転載禁止の明示なし。専用の規約ページは確認できず。記載なし（取得した範囲）。robots.txt 未確認 | **承認してよい**: 県立・公式。最新 2026-11-01。転載禁止の明示なし。運営主体（指定管理者）の原文だけ未確認 |
| 箱根ビジターセンター | hakone-vc | user（2026-11-07） | https://hakonevc.sunnyday.jp/?page_id=160 | 転載禁止の明示なし。専用の規約ページは確認できず。フッターは All Rights Reserved のみ。転載禁止の明示なし。robots.txt 未確認 | **要判断**: 環境省の施設だがページ上に運営主体の明記がない。2026-12-01 から大規模改修で休館（11/30 まで）。使える期間が短い |
| 横浜自然観察の森 | yokohama-shizen-kansatsu | user（2026-11-07） | https://wbsj-yokohama.blog.jp/ | 転載禁止の明示なし。専用の規約ページは確認できず。フッターは著作権表示のみ。robots.txt 未確認 | **承認してよい**: 指定管理者は日本野鳥の会で近場。最新 2026-10-24。転載禁止の明示なし（規約ページは確認できず） |
| 高尾ビジターセンター | takao-vc | user（2026-11-07） | https://takaovc.ces-net.jp/ | **転載禁止の明示あり**。転載禁止の明示あり（ウェブサイトポリシー: 出典明記・無許可利用不可・改変禁止。『無断転載を禁ずる』の語そのものはない）。robots.txt 未確認 | **要判断**: 転載禁止の明示あり（出典明記・無許可利用不可・改変禁止）。短い語・日付・URL だけの利用を許すかは本人の判断。紅葉情報（11/6更新）と自然情報があり、内容は有用 |
| 御岳ビジターセンター | mitake-vc | user（2026-11-07） | https://mitakevc.ces-net.jp/nowmitake.html | **転載禁止の明示あり**。転載禁止の明示あり（ウェブサイトポリシー: 出典明記・無許可利用不可・改変禁止）。フッターに All Rights Reserved。robots.txt 未確認 | **要判断**: 転載禁止の明示あり（同上）。『御岳山の今』に紅葉・花・鳥・実が日付つき（11/6）で載り、内容はいちばん有用。許すかは本人の判断 |
| 埼玉県自然学習センター・北本自然観察公園 | kitamoto-shizen-gakushu | user（2026-11-07） | http://www.saitama-shizen.info/today/index.html | 転載禁止の明示なし。プライバシーポリシー・免責事項のみ（転載・自動取得の記載なし）。robots.txt は 404（拒否の記述なし）。ページ全体が Shift_JIS（CP932。文字コードの宣言なし）で、要約の道具では UTF-8 として読まれて日本語が全部文字化けする（2026-11-07 に今日の様子・事業ページ・トップで確認） | **承認してよい**: 県の施設・公式。最新 2026-11-06。転載禁止の明示なし。robots.txt は拒否なし。**ただしページが CP932（Shift_JIS）で、今の読み取りの道具では日本語が全部文字化けし、状態の語・種名を読めない**（行事のページも同じ）。承認しても、読む手段（CP932 で復号するコードによる取得。実通信は本人の認可が要る）ができるまで現況は出ない |
| 狭山丘陵いきものふれあいの里センター | sayama-ikimono-fureai | user（2026-11-07） | https://ikifure.info/category/nature/ | 転載禁止の明示なし。個人情報保護方針と免責事項のみ（転載・自動取得の記載なし）。robots.txt は /info2/wp-admin/ のみ拒否 | **承認してよい**: 県の施設・公式。ふれあいの里だよりが月ごと。転載禁止の明示なし。robots.txt は拒否なしを確認済み |
| 日光湯元ビジターセンター | nikko-yumoto-vc | user（2026-11-07） | http://www.nikkoyumoto-vc.com/new/nature_l.html | 転載禁止の明示なし。規約ページのリンクなし。フッターは All rights reserved のみ。転載禁止の明示なし。robots.txt 未確認 | **保留**: 開館は 9/1〜11/30。シーズン終了後は使えない（コードが季節外を除く）。来季に再判断 |
| 栃木県立日光自然博物館 | nikko-shizen-hakubutsukan | user（2026-11-07） | https://blog.nikko-nsm.co.jp/blog/ | 転載禁止の明示なし。個人情報保護方針のみ（著作権の記載なし）。フッターは All Rights Reserved のみ。robots.txt 未確認 | **承認してよい**: 県立。最新 2026-11-06。転載禁止の明示なし |
| 那須平成の森 | nasu-heisei-no-mori | user（2026-11-07） | https://nasuheisei-f.jp/nature/ | 転載禁止の明示なし。プライバシーポリシーのみ。フッターは Copyright の表示のみ。転載禁止の明示なし。robots.txt 未確認 | **承認してよい**: 最新 2026-10-23。転載禁止の明示なし |
| 奥多摩ビジターセンター | okutama-vc | user（2026-11-09） | https://okutamavc.ces-net.jp/info | **転載禁止の明示あり**。転載禁止の明示あり（著作権の項に『著作権法上認められた場合を除き、無断で複製・転用することはできません』。『転載』の語ではなく複製・転用の無断禁止）。リンクは原則自由（リンク先はトップ）。robots.txt は /wp-admin/ のみ拒否で /info は許可 | **保留**: お知らせはイベント・登山道・クマ情報が中心で、紅葉・花・鳥の状態の語が読めない。複製・転用の無断禁止の明示あり |
| 谷津干潟自然観察センター | yatsuhigata-nature-center | user（2026-11-07） | https://www.seibu-la.co.jp/yatsuhigata/blog/ | 転載禁止の明示なし。利用規約・サイトポリシー・著作権のリンクは確認できず（フッターは Copyright SEIBU Landscape のみ）。転載禁止の明示なし。robots.txt は /wp-admin/ のみ拒否で /yatsuhigata/ は許可 | **承認してよい**: 指定管理者の公式。『自然情報』に渡り鳥の観察記録。転載禁止の明示なし。最新は 10/13 で11月分はまだない |
| 尾瀬沼・山ノ鼻ビジターセンター（尾瀬保護財団） | oze-fnd | user（2026-11-09） | https://oze-fnd.or.jp/archives/category/if/ | **無断転載を禁じます** | **要判断**: 事実のみの扱いでよいか |

### 2-B. 現況の情報源の台帳（承認済み 44件）

| 台帳 | 情報源（id） | 承認した人・日 | 最新情報のページ |
|---|---|---|---|
| autumn_leaves.yaml | 日光市観光協会（nikko-kankou-autumn-leaves） | user（2026-10-23） | https://www.nikko-kankou.org/flowering/autumn-leaves |
| autumn_leaves.yaml | 箱根町観光協会（hakone-kankou-koyo） | user（2026-10-23） | https://www.hakone.or.jp/1804 |
| autumn_leaves.yaml | 大子町観光協会（daigo-kanko-koyo） | user（2026-10-23） | https://www.daigo-kanko.jp/themes/koyo.html |
| autumn_leaves.yaml | 茨城県(観光いばらき)（ibaraki-guide-autumn-leaves） | user（2026-10-23） | https://www.ibarakiguide.jp/special/autumn_leaves/page000493.html |
| autumn_leaves.yaml | やまなし観光推進機構(富士の国やまなし観光ネット。山梨県公式観光情報)（yamanashi-kankou-koyo） | user（2026-10-23） | https://www.yamanashi-kankou.jp/special/yamanashi-koyo.html |
| autumn_leaves.yaml | やまなし観光推進機構(富士の国やまなし観光ネット。山梨県公式観光情報)（yamanashi-kankou-koyo-csv） | user（2026-11-07） | https://www.yamanashi-kankou.jp/special/yamanashi-koyo.html |
| autumn_leaves.yaml | 東京都公園協会(六義園サービスセンター)（tokyo-park-rikugien-news） | user（2026-10-23） | https://www.tokyo-park.or.jp/park/rikugien/news/index.html |
| autumn_leaves.yaml | 国民公園協会 新宿御苑（fng-shinjuku-seasonal） | user（2026-10-23） | https://fng.or.jp/shinjuku/ |
| autumn_leaves.yaml | 長瀞町観光協会（nagatoro-kanko-koyo） | user（2026-11-07） | https://www.nagatoro.gr.jp/category/%E7%B4%85%E8%91%89%E6%83%85%E5%A0%B1/ |
| autumn_leaves.yaml | 国営昭和記念公園(昭和記念公園管理センター)（showakinen-flower-information） | user（2026-11-09） | https://www.showakinen-koen.jp/flower-information/ |
| autumn_leaves.yaml | 東京都公園協会(六義園サービスセンター)（tokyo-park-rikugien-lightup） | user（2026-10-23） | https://www.tokyo-park.or.jp/park/rikugien/news/2026/rikugiengardens.html |
| autumn_leaves.yaml | 長谷寺(鎌倉)（hasedera-lightup） | user（2026-10-23） | https://www.hasedera.jp/2026/10/23900/ |
| autumn_leaves.yaml | つくば観光コンベンション協会（ttca-autumn-tsukuba） | user（2026-10-23） | https://ttca.jp/autumnmttsukuba/ |
| autumn_leaves.yaml | 日光市観光協会（nikko-kankou-congestion） | user（2026-10-23） | https://www.nikko-kankou.org/features/congestion |
| autumn_leaves.yaml | 川根本町まちづくり観光協会（okuooi-traffic-sumata） | user（2026-10-23） | https://okuooi.gr.jp/important/page.php?id=427 |
| autumn_leaves.yaml | 沼田市観光協会（numata-kankou-news） | user（2026-10-23） | https://www.numata-kankou.jp/news/index.html |
| autumn_leaves.yaml | 谷川岳ヨッホ by 星野リゾート(谷川岳ロープウェイ)（tanigawadake-joch-information） | user（2026-10-23） | https://tanigawadake-joch.com/information/ |
| autumn_leaves.yaml | 富士河口湖町観光連盟（fujikawaguchiko-koyo-matsuri） | user（2026-10-23） | https://fujisan.ne.jp/news/6065/ |
| autumn_leaves.yaml | 東京都公園協会(小石川後楽園)（tokyo-park-koishikawa-event） | user（2026-10-23） | https://www.tokyo-park.or.jp/event_search/event_57.html |
| autumn_leaves.yaml | 神奈川県観光協会(観光かながわNOW。紹介サイト)（kanagawa-kankou-koyo-feature） | user（2026-11-04） | https://www.kanagawa-kankou.or.jp/features/koyo-kanagawa |
| autumn_leaves.yaml | 神奈川県自然環境保全センター(かながわパークレンジャー紅葉記録)（kanagawa-parkranger-koyo） | user（2026-11-05） | https://www.pref.kanagawa.jp/docs/f4y/02yama/kanagawaparkranger/leaves/l-top.html |
| autumn_leaves.yaml | 秩父市(秩父観光なび)（chichibu-navi-koyo） | user（2026-11-07） | https://navi.city.chichibu.lg.jp/p_flower/1553/ |
| autumn_leaves.yaml | (一社)長瀞町観光協会（nagatoro-koyo-matsuri-2026） | user（2026-11-07） | https://nagatoro.gr.jp/2026/10/%E9%95%B7%E7%80%9E%E7%B4%85%E8%91%89%E3%81%BE%E3%81%A4%E3%82%8A2026 |
| autumn_leaves.yaml | 日光市観光協会（nikko-kankou-lightup-2026） | user（2026-11-05） | https://www.nikko-kankou.org/event/1246 |
| birds.yaml | 公益財団法人日本野鳥の会(東京港野鳥公園の管理者)（tokyo-port-birdpark-today） | claude_code_provisional（2026-10-24） | https://wbsj-wildbirdpark.blog.jp/archives/cat_773662.html |
| birds.yaml | 東京都公園協会(葛西臨海公園サービスセンター)（tokyo-park-kasai-news） | claude_code_provisional（2026-10-24） | https://www.tokyo-park.or.jp/park/kasairinkai/news/index.html |
| birds.yaml | 公益財団法人日本野鳥の会(横浜自然観察の森の指定管理者)（wbsj-yokohama-blog） | claude_code_provisional（2026-10-24） | https://wbsj-yokohama.blog.jp |
| flowers.yaml | 国営ひたち海浜公園(ひたち公園管理センター)（hitachi-flower-info） | claude_code_provisional（2026-10-24） | https://www.hitachikaihin.jp/flower-plant/flower-info/ |
| flowers.yaml | 東京都公園協会(旧古河庭園サービスセンター)（tokyo-park-kyufurukawa-news） | claude_code_provisional（2026-10-24） | https://www.tokyo-park.or.jp/park/kyu-furukawa/news/index.html |
| flowers.yaml | 東京都公園協会(神代植物公園サービスセンター)（tokyo-park-jindai-news） | claude_code_provisional（2026-10-24） | https://www.tokyo-park.or.jp/park/jindai/news/index.html |
| flowers.yaml | 国営昭和記念公園(昭和管理センター)（showakinen-flower-information-flowers） | user（2026-11-09） | https://www.showakinen-koen.jp/flower-information/ |
| flowers.yaml | 神奈川県立花と緑のふれあいセンター 花菜ガーデン（kana-garden-news） | user（2026-11-08） | https://kana-garden.com/ |
| flowers.yaml | 公益社団法人神奈川県観光協会(観光かながわNOW)（kanagawa-kankou-kana-rose） | claude_code_provisional（2026-10-31） | https://www.kanagawa-kankou.or.jp/event/7882 |
| flowers.yaml | 小田原フラワーガーデンパートナーズ(代表企業 横浜緑地株式会社)（kanagawaparks-odawarafg） | claude_code_provisional（2026-10-31） | https://www.kanagawaparks.com/odawarafg/ |
| flowers.yaml | よこすかseasideパートナーズ(ヴェルニー公園)（kanagawaparks-verny） | claude_code_provisional（2026-10-31） | https://www.kanagawaparks.com/verny/blog/ |
| flowers.yaml | 公益財団法人三溪園保勝会（sankeien-kikka） | claude_code_provisional（2026-10-31） | https://www.sankeien.or.jp/ |
| flowers.yaml | くりはまフラワーパートナーズ(くりはま花の国)（kanagawaparks-kurihama） | claude_code_provisional（2026-10-31） | https://www.kanagawaparks.com/kurihama/ |
| secondary/autumn_leaves.yaml | ウォーカープラス(紹介サイト。公式ではない)（walkerplus-koyo-kanagawa） | user（2026-11-04） | https://koyo.walkerplus.com/list/ar0314/ |
| secondary/autumn_leaves.yaml | ウォーカープラス(紹介サイト。公式ではない)（walkerplus-koyo-tokyo） | user（2026-11-04） | https://koyo.walkerplus.com/list/ar0313/ |
| secondary/autumn_leaves.yaml | GO TOKYO(東京都観光財団。紹介サイト)（gotokyo-autumn-leaves-ja） | user（2026-11-05） | https://www.gotokyo.org/jp/story/guide/autumn-leaves-forecast/ |
| secondary/autumn_leaves.yaml | ちば観光ナビ(千葉県観光物産協会。紹介サイト)（maruchiba-koyo-feature） | user（2026-11-05） | https://maruchiba.jp/feature/detail_48.html |
| wintering_birds.yaml | 阿賀野市(公園管理事務所)（agano-hyoko-monthly） | user（2026-10-23） | https://www.city.agano.niigata.jp/soshiki/koenkanrijimusho/2/2/index.html |
| wintering_birds.yaml | 安曇野市(観光課)（azumino-hakucho-hirai） | user（2026-10-23） | https://www.city.azumino.nagano.jp/soshiki/32/10320.html |
| wintering_birds.yaml | 館林市（tatebayashi-hakucho） | user（2026-10-23） | https://www.city.tatebayashi.gunma.jp/s025/kanko/020/070/020/20200104065000.html |

### 2-C. 行事・展示の台帳（承認済み 1件）

| 施設（id） | 承認した人・日 | 行事のページ |
|---|---|---|
| 神奈川県立生命の星・地球博物館（kanagawa-museum） | user（2026-11-08） | https://nh.kanagawa-museum.jp/event/ |

### 2-D. 名所カタログ（承認済み 134件。うち本人の承認 14件を列挙）

| 台帳 | 名所（id） | 承認した日 |
|---|---|---|
| catalog/autumn_leaves.yaml | 奥日光 竜頭滝（kouyou-0026） | 2026-10-23 |
| catalog/autumn_leaves.yaml | 日塩もみじライン（kouyou-0027） | 2026-10-23 |
| catalog/autumn_leaves.yaml | 瀬戸合峡（kouyou-0028） | 2026-10-23 |
| catalog/autumn_leaves.yaml | 霧降高原 キスゲ平園地（kouyou-0029） | 2026-10-23 |
| catalog/autumn_leaves.yaml | 谷川岳 天神平(谷川岳ヨッホ)（kouyou-0030） | 2026-10-23 |
| catalog/autumn_leaves.yaml | 白馬 八方尾根(うさぎ平周辺)（kouyou-0031） | 2026-10-23 |
| catalog/autumn_leaves.yaml | 小石川後楽園（kouyou-0032） | 2026-10-23 |
| catalog/autumn_leaves.yaml | 金石水管橋(長瀞)（kouyou-0063） | 2026-11-08 |
| catalog/autumn_leaves.yaml | 白鳥橋(長瀞)（kouyou-0064） | 2026-11-08 |
| catalog/autumn_leaves.yaml | 埼玉県立自然の博物館（kouyou-0065） | 2026-11-08 |
| catalog/wintering_birds.yaml | 瓢湖(阿賀野市)（hakucho-0001） | 2026-10-23 |
| catalog/wintering_birds.yaml | 安曇野(犀川白鳥湖・御宝田遊水池)（hakucho-0002） | 2026-10-23 |
| catalog/wintering_birds.yaml | 多々良沼(館林市)（hakucho-0003） | 2026-10-23 |
| catalog/wintering_birds.yaml | 白鳥の郷公苑(三条市)（hakucho-0005） | 2026-10-23 |
- catalog/autumn_leaves.yaml: 承認した人 claude_code_provisional が 17件
- catalog/autumn_leaves.yaml: 承認した人 記入なし（段階19 以前の承認） が 20件
- catalog/birds.yaml: 承認した人 claude_code_provisional が 5件
- catalog/flowers.yaml: 承認した人 claude_code_provisional が 78件

## 3. 取り消し・引退（5件）

| 台帳 | 項目（id） | 状態 |
|---|---|---|
| secondary/autumn_leaves.yaml | ウォーカープラス(ウェザーニュースの予想の転載。紹介サイト)（walkerplus-koyo-forecast-east） | revoked |
| secondary/autumn_leaves.yaml | 日本気象(n-kishou。お天気ナビゲータ。紹介サイト)（nihon-kisho-koyo-forecast） | revoked |
| wintering_birds.yaml | 那珂市(商工観光課)（naka-kotokunuma） | revoked |
| catalog/flowers.yaml | 新磯ざる菊花見会（hana-0033） | retired |
| catalog/wintering_birds.yaml | 古徳沼(那珂市)（hakucho-0004） | retired |

## 4. 紹介サイトなど由来の値を持つ名所の出典（段階64 第6部・段階65 第2部で足したもの）

承認の記入はしていない。『区分』は、値の出典が施設・自治体自身の公式ページか、紹介サイトか。

| 名所（id） | 出典 | 区分 | 規約の要約 |
|---|---|---|---|
| 巾着田曼珠沙華公園（hana-0042） | https://www.pref.saitama.lg.jp/a1008/nigiwai-spot/spot5.html | 自治体の公式ページ(埼玉県。情報の出典は日高市と明記)。巾着田の管理者(日高市)自身のページではない | 埼玉県のサイトポリシーは未確認(/site/about/ は 404。2026-11-09)。転載の禁止は確認できていない |
| 亀戸天神社（hana-0043） | https://www.gotokyo.org/jp/spot/ev197/index.html | 紹介サイト(東京観光財団 GO TOKYO)。亀戸天神社自身のページではない | 許可なく複製・転載・配布などに使うことを禁じる。自動取得の規定はない(台帳 gotokyo-autumn-leaves-ja の確認 2026-11-05) |
| 芦川のすずらん群生地（hana-0044） | https://www.yamanashi-kankou.jp/fuefuki/event/ashigawa-suzuran.html | 県の観光公式(やまなし観光推進機構)。群生地の管理者自身のページではない | 「このサイトについて」に引用・転載・自動取得の規定はなく © 表示だけ(台帳 yamanashi-kankou-koyo の確認) |
| 府中市郷土の森博物館(梅園)（hana-0045） | https://www.gotokyo.org/jp/new-and-now/new-and-trending/260209/topics.html | 紹介サイト(東京観光財団 GO TOKYO)。施設自身のページではない | 許可なく複製・転載・配布などに使うことを禁じる。自動取得の規定はない(台帳 gotokyo-autumn-leaves-ja の確認) |
| あしかがフラワーパーク（hana-0046） | https://www.ashikaga.co.jp/ | 施設自身の公式ページ(あしかがフラワーパーク) | トップに著作権・無断転載・利用規約の記載やリンクはない(個人情報保護方針・運営会社・特商法の表示だけ。2026-11-09) |
| 吾妻山公園（hana-0047） | https://www.town.ninomiya.kanagawa.jp/0000001281.html | 自治体の公式ページ(二宮町。公園の管理者の町自身のページ) | 段階67 第5部(2026-11-09): 無断の複製・転用は不可(私的使用・引用を除く)。自動取得の記載なし |
| 寄ロウバイ園（hana-0048） | https://town.matsuda.kanagawa.jp/soshiki/9/roubaimatsuri.html | 自治体の公式ページ(松田町。園の運営の町自身のページ) | 段階67 第5部(2026-11-09): 無断の複製・転載・販売・貸与・改変は不可(私的使用・引用を除く)。自動取得の記載なし |
| 熱海梅園（hana-0049） | https://www.city.atami.lg.jp/hana/1003681/1003692/index.html | 自治体の公式ページ(熱海市。梅園の設置者の市自身のページ) | 段階67 第5部(2026-11-09): 市の許可なく複製・転用・販売などの二次利用を禁じる。自動取得の記載なし |
| 越生梅林（hana-0050） | https://ogose-kanko.jp/tourist_attractions/ogose-bairin | 町の観光協会の公式ページ(越生町観光協会) | 段階67 第5部(2026-11-09): フッターに「無断転載・複製を禁止」。規約のページはない |
| 偕楽園（hana-0051） | https://ibaraki-kairakuen.jp/zukan/ | 施設自身の公式ページ(偕楽園) | 段階67 第5部(2026-11-09): トップに規約のページへのリンクなし(© 茨城県)。転載の記載は確認できず |
| 曽我梅林（hana-0052） | https://www.city.odawara.kanagawa.jp/kanko/Flower/odawaraplum.html | 自治体の公式ページ(小田原市) | 段階67 第5部(2026-11-09): 権利者の許可なく複製・転用などの二次利用を禁じる。自動取得の記載なし |
| 権現堂桜堤（hana-0053） | https://www.city.satte.lg.jp/kanko_bunka_sport/kanko/11763.html | 自治体の公式ページ(幸手市) | 段階67 第5部(2026-11-09): 著作権のページ(4091.html)は未読。目次のページに転載の記載なし |

## 5. 国営昭和記念公園（showakinen-flower-information・showakinen-flower-information-flowers）の規約

- 読んだページ(2026-11-09): https://www.showakinen-koen.jp/about/ の「掲載データ・写真について」と https://www.showakinen-koen.jp/robots.txt。別の利用規約・サイトポリシーのページはない(フッターは個人情報保護方針・リンク集・サイトマップだけ)。
- 要約: 掲載データ・写真は「無断転載を禁じます」、著作権は公園に帰属。複製・自動取得の記載はなく、リンクはフリー(トップへ)。robots.txt は全ロボット向けに /wp-admin/ など管理用の 2 か所だけ拒否。
- 承認すると出る現況(2026-11-09 の記録): 記録 8 件(状態の読めるもの 7 件)。名所では 紅葉 3 か所(国営昭和記念公園(日本庭園)・カナール・イチョウ並木・かたらいのイチョウ並木)と 花 1 か所(国営昭和記念公園 hana-0004)。どれも状態の日付は 10/31〜11/05 で、新しさの区分は「やや古い」以下。
- 推奨: **要判断**。無断転載の禁止はあるが、状態の語・日付・URL の短い事実を出典つきで示す使い方(ほかの承認済みの施設と同じ)を許すかは本人の判断。

## 6. 知識カード・名所の出典の規約の要約（段階67 第5部。2026-11-09 に読んだ。承認の記入はしていない）

| 出典 | 読んだページ | 要約(2行以内) | 本人の判断 |
|---|---|---|---|
| 北杜市観光協会 | https://www.hokuto-kanko.jp/policy/ | プライバシーポリシーだけで、転載・複製・引用・自動取得の記載なし。トップに © 表示のみ。robots.txt は未確認 | — |
| 中央アルプス観光 | https://chuo-alps.com/privacy/ | 規約・著作権のページはなく、プライバシーポリシーにも転載・複製・自動取得の記載なし。© 表示のみ。robots.txt は未確認 | — |
| 駒ヶ根観光協会 | https://www.kankou-komagane.com/policy | プライバシーポリシーだけで、転載・複製・引用・自動取得の記載なし。© 表示のみ。robots.txt は未確認 | — |
| 新潟県観光協会 | https://niigata-kankou.or.jp/site-policy/ | 著作権は協会か情報提供者に帰属。私的使用・引用の範囲を超える使用は協会へ問い合わせ。自動取得の記載なし | — |
| 新穂高ロープウェイ(奥飛観光開発) | https://shinhotaka-ropeway.jp/privacy/ | 規約・著作権のページはなく、プライバシーポリシーにも転載・自動取得の記載なし。© 表示のみ | — |
| 大山観光電鉄 | https://www.ooyama-cable.co.jp/ | トップに規約・著作権のページへのリンクがない(© 表示のみ)。転載・自動取得の記載は確認できず | — |
| 立山黒部貫光 | https://www.alpen-route.co.jp/policy/ | サイトポリシーの入口はリンク集だけで、本文(s-policy-j)は上限のため未読。転載・自動取得の記載は未確認 | — |
| mtasama.com(浅間山ジオパーク推進協議会) | https://mtasama.com/ | 運営は浅間山ジオパーク推進協議会(公的な協議会)。規約のページはなく、転載・複製の記載なし。写真・ロゴの使用は申請制(要綱 PDF は未読) | — |
| 二宮町 | https://www.town.ninomiya.kanagawa.jp/site_policy/0000000003.html | 私的使用の複製・引用など著作権法で認められた場合を除き、無断の複製・転用は不可。自動取得の記載なし | 無断の複製・転用の禁止あり。本人の判断（2026-11-09）: 事実のみ・自分の言葉・出典明記で使用を継続 |
| 松田町 | https://town.matsuda.kanagawa.jp/site/userguide/08.html | 私的使用・引用などを除き、無断の複製・転載・販売・貸与・改変は不可。自動取得の記載なし | 無断の複製・転載の禁止あり。本人の判断（2026-11-09）: 事実のみ・自分の言葉・出典明記で使用を継続 |
| 熱海市 | https://www.city.atami.lg.jp/about/sitepolicy.html | 著作権は市に帰属。市の許可なく複製・転用・販売などの二次利用を固く禁じる。自動取得の記載なし | 許可のない二次利用の禁止あり。本人の判断（2026-11-09）: 事実のみ・自分の言葉・出典明記で使用を継続 |
| 越生町観光協会 | https://ogose-kanko.jp/ | フッターに「無断転載・複製を禁止」。規約のページはなく、自動取得の記載なし | 無断転載・複製の禁止あり。本人の判断（2026-11-09）: 事実のみ・自分の言葉・出典明記で使用を継続 |
| 偕楽園(茨城県) | https://ibaraki-kairakuen.jp/ | トップに規約・著作権のページへのリンクがない(© 茨城県の表示)。転載・自動取得の記載は確認できず | — |
| 小田原市 | https://www.city.odawara.kanagawa.jp/tyosaku/tyosakuetc.html | 権利者の許可なく複製・転用・販売などの二次利用を固く禁じる。リンクは原則自由。自動取得の記載なし | 許可のない二次利用の禁止あり。本人の判断（2026-11-09）: 事実のみ・自分の言葉・出典明記で使用を継続 |
| 幸手市 | https://www.city.satte.lg.jp/soshiki/hisyo/7228.html | 「市ホームページについて」は目次だけで、著作権のページ(4091.html)は上限のため未読。転載・自動取得の記載は未確認 | — |

### 高尾・御岳ビジターセンター: 施設の自前サイトと、山と溪谷オンライン経由の違い
| 項目 | 施設の自前サイト（takaovc.ces-net.jp・mitakevc.ces-net.jp） | 山と溪谷オンライン経由（掲載されていた情報） |
|---|---|---|
| 発信元 | 東京都の指定管理者（株式会社自然教育研究センター）の公式サイト | 同じ施設が発信した情報を、山と溪谷社が掲載したもの |
| 内容 | 高尾: 紅葉情報（11/6更新）・近ごろの自然情報（花・実・野鳥の種名）。御岳: 『御岳山の今』に紅葉・花・鳥・実が日付つきで載る | 山の状況の短い記事（状態の語） |
| 日付 | 日付つき（御岳 2026.11.6 など） | 掲載日による |
| 規約 | 施設のウェブサイトポリシー: 出典明記・無許可利用不可・改変禁止（転載禁止の明示あり） | 山と溪谷オンライン利用規約 第4条⑧（複製・転載の禁止）。利用者の決定 2026-11-06 で、記事の文章は使わず、状態の語・日付・URL だけに限る取り扱い（承認前 `approved: false`） |
| 現在の扱い | 承認待ち（台帳）。答えには出ない | 承認待ち。**データから山と溪谷オンラインの URL と、それだけが出どころの事実は削除済み**（段階55 第8部）。承認しても『○○発信』の短い形でしか使えない |
| 違い | 施設自身の発信なので、出どころが明確で内容も詳しい。ただし規約が無許可利用を禁じている | 第三者による掲載で、二重の規約がかかる。内容は自前サイトの要約にとどまる |
| 推奨 | **要判断**（短い語・日付・URL だけの利用を許すかを本人が決める）。許すなら自前サイトを使い、山と溪谷オンライン経由は使わない | 使わない（自前サイトで足りるため） |

## C. 山と溪谷オンライン（取り扱い規則）
`ikimonobiyori/data/observations/policy.yaml` の `record.restricted_sources`（`approved: false`）。承認しても、状態の語（30字以内）・日付・URL だけを『○○発信（山と溪谷オンライン掲載）』の形で出す。記事の文章・注意・種名・例年の時期などは出さない。現在は**データに山と溪谷オンラインの URL は1件もない**（段階55 第8部）。推奨: **保留**（高尾・御岳は自前サイトで足りる）。
