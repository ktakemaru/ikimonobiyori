# 承認待ちの情報源の一覧（段階56 第6部。2026-11-07）

本人が承認を判断しやすいように、承認待ちの情報源を表にした。**承認は本人が行う**（Claude Code は承認も `approved_by` の記入もしない）。

## 推奨の基準
- **承認してよい**: 公式・範囲内・転載禁止の明示がなく、最新の更新日が近く、状態や種名が読める。
- **要判断**: 使えるが、転載禁止の明示がある、または運営主体・利用期間に気になる点がある。
- **保留**: 今は使えない（更新が古い・シーズンが終わった・読めない・状態の語がない）。事情が変われば見直す。

承認した場合に使う内容は、施設台帳（A）では次のとおり。ほかの項目は使わない（記事や文章を転載しない）。
> 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。14日以内で、季節内の発信だけ。

## A. ビジターセンター・自然観察施設（台帳 `ikimonobiyori/data/visitor_centers/centers.yaml`。20施設）
承認の手順: 台帳の `approval.status` を `approved` にし、`approved_by` に承認した人を書く（docs/operations.md §2-2 をこの台帳向けに読み替える）。承認しても、シーズンが終わった施設・14日より古い発信は答えに出ない（コードが除く）。

集計: 承認してよい 8件／要判断 4件／保留 8件。

| 施設 | 運営主体 | 最新情報のページ | 更新頻度 | 形式 | 規約メモ（転載禁止の明示の有無） | 範囲内 | 承認した場合に使う内容 | 推奨と理由 |
|---|---|---|---|---|---|---|---|---|
| 埼玉県自然学習センター・北本自然観察公園 | 指定管理者 公益財団法人埼玉県生態系保護協会（県の案内の原文） | http://www.saitama-shizen.info/today/index.html | 不明（更新日 2026-11-06） | html | 転載禁止の明示なし。プライバシーポリシー・免責事項のみ（転載・自動取得の記載なし）。robots.txt は 404（拒否の記述なし）。ページ全体が Shift_JIS（CP932。文字コードの宣言なし）で、要約の道具では UTF-8 として読まれて日本語が全部文字化けする（2026-11-07 に今日の様子・事業ページ・トップで確認） | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜17:00、休館は月曜（祝日の場合は開館）・祝日の翌日・年末年始 | **承認してよい**: 県の施設・公式。最新 2026-11-06。転載禁止の明示なし。robots.txt は拒否なし。**ただしページが CP932（Shift_JIS）で、今の読み取りの道具では日本語が全部文字化けし、状態の語・種名を読めない**（行事のページも同じ）。承認しても、読む手段（CP932 で復号するコードによる取得。実通信は本人の認可が要る）ができるまで現況は出ない |
| 栃木県立日光自然博物館 | 株式会社日光自然博物館（個人情報保護方針の原文） | https://blog.nikko-nsm.co.jp/blog/ | 不明（更新日 2026-11-06） | html | 転載禁止の明示なし。個人情報保護方針のみ（著作権の記載なし）。フッターは All Rights Reserved のみ。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 4/1〜11/10 9:00〜17:00、11/11〜3/31 10:00〜16:00。休館は5〜11月無休、12〜4月は月曜、12/29〜1/3 | **承認してよい**: 県立。最新 2026-11-06。転載禁止の明示なし |
| 横浜自然観察の森 | 指定管理者 公益財団法人日本野鳥の会（所管 横浜市みどり環境局） | https://wbsj-yokohama.blog.jp/ | 不明（更新日 2026-10-24） | html | 転載禁止の明示なし。専用の規約ページは確認できず。フッターは著作権表示のみ。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない | **承認してよい**: 指定管理者は日本野鳥の会で近場。最新 2026-10-24。転載禁止の明示なし（規約ページは確認できず） |
| 狭山丘陵いきものふれあいの里センター | 指定管理者 公益財団法人トトロのふるさと基金（県の案内の原文） | https://ikifure.info/category/nature/ | ふれあいの里だより（令和8年N月号の形式で投稿） | html | 転載禁止の明示なし。個人情報保護方針と免責事項のみ（転載・自動取得の記載なし）。robots.txt は /info2/wp-admin/ のみ拒否 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜17:00、月曜定休（祝日・県民の日を除く）、祝日の翌日、年末年始（12/29〜1/3） | **承認してよい**: 県の施設・公式。ふれあいの里だよりが月ごと。転載禁止の明示なし。robots.txt は拒否なしを確認済み |
| 県立秦野ビジターセンター | 神奈川県立（指定管理者の原文は未確認） | https://hadanovc.blogspot.com/ | 不明（更新日 2026-11-06） | html | 転載禁止の明示なし。専用の規約ページは確認できず。丹沢公式トップに『サイト内の写真は無断使用禁止』（写真のみ。要約由来）。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜16:30、休館は年末年始（12/29〜1/3）のみ | **承認してよい**: 県立・公式。最新 2026-11-06。転載禁止の明示なし。運営主体（指定管理者）の原文だけ未確認 |
| 県立西丹沢ビジターセンター | 神奈川県立（指定管理者の原文は未確認） | https://nishitanzawashizenkyoushitsu.blogspot.com/ | 不明（更新日 2026-11-01） | html | 転載禁止の明示なし。専用の規約ページは確認できず。記載なし（取得した範囲）。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 8:30〜16:30（12月〜3月は16:00まで）、休館は月曜（祝日の場合は翌平日）と年末年始 | **承認してよい**: 県立・公式。最新 2026-11-01。転載禁止の明示なし。運営主体（指定管理者）の原文だけ未確認 |
| 谷津干潟自然観察センター | 谷津干潟ワイズユース・パートナーズ（代表企業 西武造園株式会社）（指定管理者） | https://www.seibu-la.co.jp/yatsuhigata/blog/ | 月1〜7件（2026年のアーカイブ。最新は10/13） | html | 転載禁止の明示なし。利用規約・サイトポリシー・著作権のリンクは確認できず（フッターは Copyright SEIBU Landscape のみ）。転載禁止の明示なし。robots.txt は /wp-admin/ のみ拒否で /yatsuhigata/ は許可 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜17:00（入館は16:30まで）、休館日は月曜（祝休日の場合は次の平日）・12/28〜1/1 | **承認してよい**: 指定管理者の公式。『自然情報』に渡り鳥の観察記録。転載禁止の明示なし。最新は 10/13 で11月分はまだない |
| 那須平成の森 | 那須平成の森フィールドセンター（プライバシーポリシーの原文） | https://nasuheisei-f.jp/nature/ | 不明（更新日 2026-10-23） | html | 転載禁止の明示なし。プライバシーポリシーのみ。フッターは Copyright の表示のみ。転載禁止の明示なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜16:30（5・7・8月は〜17:00）、休園は水曜（祝日の翌日、GW・お盆・年末年始は無休） | **承認してよい**: 最新 2026-10-23。転載禁止の明示なし |
| 御岳ビジターセンター | 指定管理者 株式会社自然教育研究センター（東京都の施設） | https://mitakevc.ces-net.jp/nowmitake.html | 不明（更新日 2026-11-06） | html | **転載禁止の明示あり**。転載禁止の明示あり（ウェブサイトポリシー: 出典明記・無許可利用不可・改変禁止）。フッターに All Rights Reserved。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・URL・開館時間のみ（台帳の allowed_fields。種名（10種まで）は使わない）。記事や文章は使わない。開館時間: 9:00〜16:30、休館は月曜（祝日の場合は翌日）・年末年始 | **要判断**: 転載禁止の明示あり（同上）。『御岳山の今』に紅葉・花・鳥・実が日付つき（11/6）で載り、内容はいちばん有用。許すかは本人の判断 |
| 桐生自然観察の森 | 桐生市 都市整備部 公園緑地課 | https://www.city.kiryu.lg.jp/forest/shizen/ennai/1027794.html | 不明（更新日 2026-11-04） | html | **転載禁止の明示あり**。転載禁止の明示あり（このサイトについて: 文書・画像は許可なく使用・転載を禁止）。自動取得の記載なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 3〜10月 9:00〜16:30、11〜2月 9:30〜16:00。休園は火曜（祝日の場合は開園）と12/29〜1/3 | **要判断**: 転載禁止の明示あり。市の施設で最新 2026-11-04。許すかは本人の判断 |
| 箱根ビジターセンター | 環境省の施設（ページ上の運営主体の明記なし。イベント告知に自然公園財団箱根支部の表記） | https://hakonevc.sunnyday.jp/?page_id=160 | 不明（更新日 2026-11-06） | html | 転載禁止の明示なし。専用の規約ページは確認できず。フッターは All Rights Reserved のみ。転載禁止の明示なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜17:00（最終入館16:30）、休館は毎週月曜と12/29〜1/3。2026-12-01〜2027年1月中旬は大規模改修のため休館 | **要判断**: 環境省の施設だがページ上に運営主体の明記がない。2026-12-01 から大規模改修で休館（11/30 まで）。使える期間が短い |
| 高尾ビジターセンター | 指定管理者 株式会社自然教育研究センター（東京都の施設） | https://takaovc.ces-net.jp/ | 不明（更新日 2026-11-04） | html | **転載禁止の明示あり**。転載禁止の明示あり（ウェブサイトポリシー: 出典明記・無許可利用不可・改変禁止。『無断転載を禁ずる』の語そのものはない）。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・URL・開館時間のみ（台帳の allowed_fields。種名（10種まで）は使わない）。記事や文章は使わない。開館時間: 10:00〜16:00、休館は月曜（祝日の場合は連休明けの平日）・年末年始 | **要判断**: 転載禁止の明示あり（出典明記・無許可利用不可・改変禁止）。短い語・日付・URL だけの利用を許すかは本人の判断。紅葉情報（11/6更新）と自然情報があり、内容は有用 |
| かながわパークレンジャー 開花記録（神奈川県） | 神奈川県 自然環境保全センター 自然保護公園部自然保護課 | https://www.pref.kanagawa.jp/docs/f4y/02yama/kanagawaparkranger/bloom/bloomtoppage.html | 不明（更新日 2026-06-20） | html | 転載禁止の明示なし。丹沢大山ナビと同じサイトポリシー。転載禁止の明示なし。robots.txt は拒否していない | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない | **保留**: 開花記録の最新が 2026-06-20 で、今は更新が止まっている。次の開花期に再確認（県の規約は引用自由・出典記載で問題なし） |
| 丹沢大山ナビ（神奈川県） | 神奈川県 自然環境保全センター（所管） | https://www.pref.kanagawa.jp/docs/f4y/tanzawaoyama_navi.html | 不明（更新日 2026-06-12） | html | 転載禁止の明示なし。サイトポリシー: 引用は自由・出典を記載・二次利用は所管へ事前問い合わせ。転載禁止の明示なし。自動取得の記載なし。robots.txt は /docs/f4y/ を拒否していない | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない | **保留**: ナビの『旬の植物』『開花情報』『紅葉情報』の各ページの URL を本文から確認できていない。最新は 2026-06-12。URL を確認してから |
| 八島ビジターセンター（霧ヶ峰） | 町立（ページの記載。町名の文字はページ上で確認できず） | https://shimosuwaonsen.jp/yashima/category/weekly/ | 週1回（2026年は9/4〜10/30の毎週） | html | **転載禁止の明示あり**。転載禁止の明示あり（指示書の調査: PDF に『無断転載を禁ずる』。今回は PDF 本文が読めず確認できていない）。サイトのポリシーページは個人情報の取り扱いのみ。robots.txt は /wp-admin/ のみ拒否 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 開館 4月下旬〜11月上旬 9:30〜16:30、期間中無休。2026年の営業は 11/3 に終了 | **保留**: 今期は 10/30 で終了（冬季閉鎖）。転載禁止の明示あり（PDF）。来季（4月下旬）に再判断 |
| 塩原温泉ビジターセンター | 確認できず（トップが文字化けして原文を読めなかった） | http://www.siobara.or.jp/vc/ | 不明（更新日 2026-11-06） | html | 転載禁止の明示なし。規約ページのリンクは見当たらず。フッターは Copyrights (C) 2023 のみ。ページが Shift_JIS 系で文字化けし、確認できていない項目が多い。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜16:30（休館の曜日は確認できず）、12/29〜1/3 休館 | **保留**: ページが文字化けして運営主体・規約を読めていない。確認できてから |
| 奥多摩ビジターセンター | 株式会社自然教育研究センター（CES）（指定管理者） | https://okutamavc.ces-net.jp/info | 約週1回（2026-09-09〜11-06 の8件） | html | **転載禁止の明示あり**。転載禁止の明示あり（著作権の項に『著作権法上認められた場合を除き、無断で複製・転用することはできません』。『転載』の語ではなく複製・転用の無断禁止）。リンクは原則自由（リンク先はトップ）。robots.txt は /wp-admin/ のみ拒否で /info は許可 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 9:00〜16:30、休館日は月曜（祝日の場合は連休明けの平日）・年末年始。入館無料 | **保留**: お知らせはイベント・登山道・クマ情報が中心で、紅葉・花・鳥の状態の語が読めない。複製・転用の無断禁止の明示あり |
| 市川市行徳野鳥観察舎（あいねすと） | 市川市 環境部 自然環境課 | https://www.city.ichikawa.lg.jp/page/1759.html | 年に4回（あいねすと通信） | pdf | **転載禁止の明示あり**。転載禁止の明示あり（サイトポリシー: 無断で複製・転用することはできない。引用等の例外あり）。自動取得の記載なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない | **保留**: 年4回のPDF（最新 2025-10-27）で現況に向かない。転載禁止の明示あり |
| 日光湯元ビジターセンター | 自然公園財団 日光支部（フッターの原文） | http://www.nikkoyumoto-vc.com/new/nature_l.html | 不明（更新日 2026-11-05） | html | 転載禁止の明示なし。規約ページのリンクなし。フッターは All rights reserved のみ。転載禁止の明示なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 2026-09-01〜11-30 毎日 9:00〜16:00 | **保留**: 開館は 9/1〜11/30。シーズン終了後は使えない（コードが季節外を除く）。来季に再判断 |
| 那須高原ビジターセンター | 那須平成の森フィールドセンター（プライバシーポリシーの原文） | https://nasu-vc.jp/nature/ | 随時（ページの記載） | html | 転載禁止の明示なし。プライバシーポリシーのみ（著作権ページは未確認）。転載禁止の明示なし。robots.txt 未確認 | はい | 状態の語（30字以内）・日付・種名（10種まで）・URL・開館時間。記事や文章は使わない。開館時間: 4〜11月 8:30〜17:30、休館は水曜（祝日の場合は翌日。紅葉期などは開館） | **保留**: 最新が 2026-05-09 で更新が古い。次の更新があれば見直し |

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

## B. 現況の情報源の台帳（`ikimonobiyori/data/sources/`）の承認待ち（32件）

これらは段階15〜50で台帳に入った情報源で、承認待ちの理由は台帳の `approval.reason` にある。施設台帳（A）と違い、承認の有無にかかわらず**読んで記録してよい**（段階34。区分は『公式ではない』などで出る）。承認は、台帳上の『公式の現況』扱いにするかどうかの判断。

推奨は理由から決めた。『保留』は読めない・今年の現況がない・規約で読めないもの、『要判断』は条件は満たすが今は材料が出ていないもの。

| 台帳 | 情報源 | 発行元の種類 | 最新情報のページ | 形式 | 読めた状態（確認日） | 推奨と理由 |
|---|---|---|---|---|---|---|
| autumn_leaves.yaml | 東京都公園協会(紅葉を見に行こう!)（tokyo-park-kouyou-special） | park_manager | https://www.tokyo-park.or.jp/special/kouyou/index.html | status_page | ok（2026-11-05） | **要判断**: ユーザーの承認待ち(段階50)。条件(公式・読めた・利用条件に禁止なし・本文に指示文なし)は満たすが、今は前シーズンの最終版で今年の現況がない。通信先 www.tokyo-park.or.jp は段階47で承認済み。今シ… |
| autumn_leaves.yaml | 川根本町まちづくり観光協会（okuooi-koyo） | tourism_association | https://okuooi.gr.jp/pickup/page.php?id=3 | status_page | partial（2026-10-23） | **保留**: 状態が画像で、エージェントが読めない(読めたとは言えない) |
| autumn_leaves.yaml | 長瀞町観光協会（nagatoro-kanko-koyo） | tourism_association | https://www.nagatoro.gr.jp/category/%E7%B4%85%E8%91%89%E6%83%85%E5%A0%B1/ | status_page | unconfirmed（2026-10-23） | **保留**: 読めていない(HTTP 503)。状態の書き方も未確認 |
| autumn_leaves.yaml | 国営昭和記念公園(昭和記念公園管理センター)（showakinen-flower-information） | park_manager | https://www.showakinen-koen.jp/flower-information/ | status_page | ok（2026-11-05） | **要判断**: 通信先 www.showakinen-koen.jp は段階47の承認ホストの一覧にない。記録は出所の区分 official で残るが、台帳の承認はユーザーの見直しを待つ |
| autumn_leaves.yaml | 塩原温泉観光協会（siobara-kankou） | tourism_association | https://www.siobara.or.jp/ | status_page | unconfirmed（2026-10-23） | **保留**: メンテナンス中で読めていない。現況のページがあるかも未確認 |
| autumn_leaves.yaml | 秩父観光協会（chichibu-kanko-kouyou） | tourism_association | https://www.chichibuji.gr.jp/event/kouyou/ | forecast_page | ok（2026-10-23） | **要判断**: robots.txt で AI エージェントによる取得を拒む意思が読み取れる(この道具は名指しされていないが安全側)。今年の状況もない |
| autumn_leaves.yaml | 伊勢原市（isehara-oyama-koyo） | municipality | https://www.city.isehara.kanagawa.jp/kankou_guide/docs/2024012600094/ | forecast_page | ok（2026-10-23） | **保留**: 2024 年公開の古いページで、今年の状態・日程がない(ライトアップ「11月下旬ごろ」だけ)。現況の情報源にせず、例年の時期の参考として人が開く URL にとどめる(ユーザーの見直し 2026-10-23) |
| autumn_leaves.yaml | 八方尾根索道事業者協議会(白馬八方尾根)（happo-one-news-green） | facility_operator | https://www.happo-one.jp/news-green/ | status_page | ok（2026-10-23） | **要判断**: 状態の決まった語がなく段階が付けられない。人が開く URL として扱う(段階16 の見直し 2026-10-23) |
| birds.yaml | 谷津干潟自然観察センター(習志野市の施設)（yatsu-higata-center） | park_manager | https://www.seibu-la.co.jp/yatsuhigata/ | status_page | unconfirmed（2026-10-24） | **保留**: 読めなかった(HTTP 503)。利用条件も未確認。人が開く URL として扱う。次に読めたら条件を確かめる |
| birds.yaml | 我孫子市(鳥の博物館)（abiko-bird-museum-toridayori） | municipality | https://www.city.abiko.chiba.jp/bird-mus/info2/shupambutsu/toridayori.html | status_page | partial（2026-10-24） | **要判断**: 状態が PDF の中にあり、日付がない(readable: partial)。利用条件も未確認。人が開く URL として扱う |
| flowers.yaml | 国営昭和記念公園(昭和管理センター)（showakinen-flower-information-flowers） | park_manager | https://www.showakinen-koen.jp/flower-information/ | status_page | unconfirmed（2026-10-24） | **保留**: 読めなかった(HTTP 504)。利用条件も未確認。人が開く URL として扱う |
| flowers.yaml | 京成バラ園芸株式会社(京成バラ園)（keisei-rose-garden） | facility_operator | https://www.keiseirose.co.jp/garden/ | status_page | ok（2026-10-24） | **要判断**: 利用条件を確かめられなかった(規約のページが見つからない)。robots.txt も未確認。人が開く URL として扱う |
| flowers.yaml | 神奈川県立花と緑のふれあいセンター 花菜ガーデン（kana-garden-news） | park_manager | https://kana-garden.com/ | status_page | unconfirmed（2026-10-31） | **保留**: 通信先がユーザーが承認した4ホスト(kanagawaparks.com・sankeien.or.jp・kanagawa-kankou.or.jp・www.welcome.city.yokohama.jp)にない。docs… |
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
| wintering_birds.yaml | 三条市（sanjo-hakucho-hirai） | municipality | https://www.city.sanjo.niigata.jp/sanjonavi/see_do/nature/swan/2316.html | status_page | ok（2026-10-23） | **要判断**: 利用条件に、利用の前に市へ連絡するよう求める一文がある。個人利用の道具のため、事前連絡はしない。公開を検討するときに利用条件を見直す(ユーザーの判断 2026-10-23)。読まずに、人が開く URL として扱う |

## C. 山と溪谷オンライン（取り扱い規則）
`ikimonobiyori/data/observations/policy.yaml` の `record.restricted_sources`（`approved: false`）。承認しても、状態の語（30字以内）・日付・URL だけを『○○発信（山と溪谷オンライン掲載）』の形で出す。記事の文章・注意・種名・例年の時期などは出さない。現在は**データに山と溪谷オンラインの URL は1件もない**（段階55 第8部）。推奨: **保留**（高尾・御岳は自前サイトで足りる）。
