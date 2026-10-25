# 段階23 の決定(2026-10-25)

指示書 `stage23-instructions.md`(ユーザー承認済み 2026-10-25)への対応。無人で進める前提で、迷ったときは安全側(載せない・参考にとどめる・文書に書くだけ)を選び、ここに理由を書く。契約 `biyori-proposal/1` は変えない。main・biyori-hub には触れない。push しない。

## D-01 準備
- `main`(`fa47992`。段階22 のマージ後。`git pull` で最新を確認)から `stage23` を作った。

## D-02 決定事項(指示書の表。ユーザー承認 2026-10-25)
- 2種類の質問: **現況型**(「今どうなっている?」)は、これまでどおり公式の記載・日付つきだけで答える。**ガイド型**(「どこで・いつごろ・どんな種類?」)は、ウェブ検索で広く集め、出どころを区分して答える。
- 信頼の物差し: 「公式かどうか」ではなく、**独立した出どころの数(定評)と日付(新しさ)**。出どころの種類(A〜D)は記録するが、信頼の段階は数と新しさで決める。
- 信頼の段階: `curated`(定評)/ `verified`(確認済み)/ `reference`(参考)。ホシビヨリの `curated_external`・`viewpoint_reference` と言葉の意味をそろえる。
- 数字は大まか(「約30種」「たくさん」)。原文と違う数字を作らない。
- 「今いる・今咲いている」と言うときだけ、日付つきの現況が要る。名所と例年の時期は `curated` でよい。
- 開園時間・休園日・立入禁止・安全の規制は、日付と出どころをつけて書く。確認できなければ書かず「公式ページで確認してください」。
- 条件を満たすものは**仮承認**(無人)。ユーザーが朝に一覧で見直し、外せる。
- 範囲は東京・横浜から直線 250 km。範囲の外はおすすめ枠に入れない。

## D-03 通信の承認(指示書。ユーザー承認 2026-10-25)
- 検索(WebSearch): 集める 80 回・試験 60 回。取得(WebFetch): 集める 60 回・試験 40 回(検索結果に出た公開ページだけ。ログイン・SNS・自動アクセスを拒むサイトは読まない。429 でそのホストを止める)。
- 市区町村の代表点(`www.wikidata.org`、コードで読む): 100 回。座標だけ(CC0)。1 件 2 秒以上あける。429 で止める。
- 質問への答えの途中で「読みますか?」と聞き返さない(1 質問あたり検索 8 回・取得 8 回まで)。
- CLAUDE.md 規則 6 の「許可ホストは自分で広げない」との関係: `www.wikidata.org` は、この指示書でユーザーが承認したホストとして `config.yaml` の `live.allowed_hosts_by_subject.guide_places` に足す(ほかの対象の許可には足さない)。

## D-04 現状(フェーズ1。変更していない。事実だけ)
### 1. 名所カタログと台帳の構造
- 名所カタログ: `ikimonobiyori/data/catalog/<対象>.yaml`(スキーマ `schemas/site-catalog.schema.json`、`ikimono-site-catalog/1`)。件数は紅葉 46・野鳥 5・花 5・冬鳥 5(2026-10-25)。件の項目は id・name・subjects・timing_type・species・kind・point(lat・lon・elevation_m)・location_precision・sensitive・public_venue・typical_window(MM-DD の start・end)・tags(prefecture・area・terrain・access・flower_kinds など)・status_sources・status(approved など)・approved_by・approved_at・sources(url・title・checked_on)・note など。必須は id・name・subjects・timing_type・kind・location_precision・status・sources。
- 位置の粗さ: `data/catalog/policy.yaml` の `min_location_precision`(既定 exact、野鳥・ホタル area_10km=小数 1 桁、冬鳥 area_1km=小数 2 桁)。検査は `catalog.check_entry`。
- 座標の出どころ: カタログの多くは「Claude Code の推定(小数 2 桁)」とコメントに書いてある。段階19 で、日光・箱根の公式ページの地図の埋め込みの座標(`fetch/spot_coords.py`)で確かめたものだけを承認する規則になった。`data/regions.yaml` の代表点も Claude Code の知識による推定。
- 250 km の判定: `data/catalog/policy.yaml` の `range_limit`(起点 東京・横浜、球の近似)。`catalog.nearest_origin_km` が距離を計算し、`catalog.check_entry`(範囲外はエラー)と `sources.region_report`(地域の代表点の内外)が使う。
- 情報源の台帳: `ikimonobiyori/data/sources/<対象>.yaml`(スキーマ `schemas/status-sources.schema.json`)。情報源ごとに url・approval(status)・readable・reader(code / agent)・notation(状態の書き方の対応)・`covers`(その情報源が伝える地点。site=カタログの id か name=カタログ外の名前、label=公式ページの地点の書き方、primary など)。件数は紅葉 23・野鳥 5・花 5・冬鳥 5。

### 2. ガイド型の質問が「お答えできません」になる箇所
- 対象の判定: `sources subjects` が、台帳・名所カタログ・プロファイルの `stages` のそろった対象だけを `implemented: true` にする(紅葉・野鳥・花・冬鳥)。桜・ホタル・夜光虫・彼岸花・ひまわりは `implemented: false`。
- 未実装の答えの文: `data/sources/policy.yaml` の `unimplemented.text`「{name}は、まだお答えできません(公式の情報源と名所の一覧をまだ作っていないため)。…」。CLAUDE.md・AGENTS.md・SKILL.md の「未実装の対象を聞かれたら(段階17 修正⑩)」がこの文で答えるよう指示している。
- 実装済みの対象でも、手順は「台帳で approved の情報源だけを読む」「名所カタログの名所から候補を出す」なので、カタログにない場所(石神井公園・不忍池など)や、カタログに時期のない種類(サザンカ・ロウバイなど)は答えに出せない。
- 話題の対応表: 方針 `topics.items` は 野鳥・鳥・探鳥・白鳥・冬鳥・紅葉・花・お花 の 8 語だけ。「渡り鳥」「カモ」「ホタル」「桜」「カワセミ」「梅」などは結びつかない(`topic` が空 → 終了コード 1)。

### 3. 記録の書き方と、読んだ時刻
- 記録: `IKIMONOBIYORI_DATA_DIR`(既定 `runtime/ikimonobiyori/`)の下の `status_log/<対象>.jsonl`(JSON Lines。`sources.append_records`。同じ日の同じ事実は二重に書かない)。
- **読んだ時刻をモデルが書いている箇所**: `sources record --read-at <時刻>`(手順 5。モデルが時刻を渡し、そのまま `read_at` になる)と、`sources read --now <時刻> --record`(コードで読むときも、`read_at` はモデルが渡した `--now`)。`spot-coords --now` も同じ。
- 同じ日の記録の再利用: 方針 `reuse.same_day_only: true`。`sources.records_on(subject, day)` が読んだ時刻の暦日で絞る。未来の時刻の記録を除く処理はない。手元の記録(`runtime/ikimonobiyori/status_log/`、2026-10-25 16:12 の時点)には未来の時刻の記録はなかった(紅葉 199・野鳥 2・花 8・冬鳥 12 件)。
- 「聞き返す」動き: 手順 3 の「コードで読む前に 1 回だけ聞く(段階17 修正①)」。`read_plan` に `reader: code` の情報源があると「公式ページをコードで読みます(通信が発生します)。よいですか」と聞く。

### 4. 既存のコマンドとデータの置き場
- `python -m ikimonobiyori.sources`: check・weekend・region・subjects・topic・normalize・record・log・supersede・mark-erroneous・unmark-erroneous・amend・summary・read(--live)・v0・follow・answer・spot-coords(--live)・proposals。`python -m ikimonobiyori.catalog check`。`python -m ikimonobiyori.main`(v0 の提案)。
- 公開(追跡)のデータ: `ikimonobiyori/data/`(カタログ・台帳・方針・地域)・`ikimonobiyori/profiles/`・`docs/`。公開しない(追跡外)データ: `runtime/ikimonobiyori/`(status_log・cache・status_read・weekend・backtest)。

### 5. 計測フックと通信の承認
- 実通信は `livegate.live_allowed()`(`BIYORI_ALLOW_LIVE=1`、テスト中は常に拒否)+ 明示の `--max-requests` + 計測フック(`BIYORI_REQ_LOG`。biyori-hub の `hub/measure/sitecustomize.py` を PYTHONPATH に足した子プロセスで、許可ホスト `BIYORI_ALLOW_HOSTS`・件数の上限 `BIYORI_REQ_MAX`・4xx/5xx で即中止・最小間隔を強制)。許可ホストは `config.yaml` の `live.allowed_hosts_by_subject`。
- エージェントの道具(WebSearch・WebFetch)は計測フックの外。これまでは回数を手で数えていた。

## D-05 ガイド用のデータの形(フェーズ2)
- **既存の名所カタログ(`data/catalog/`)とは別に、ガイド用のデータを `ikimonobiyori/data/guide/` に置く**(指示書の「カタログと並ぶガイド用のデータ」)。理由: 既存のカタログは現況の提案(`proposals`)・台帳の検査・ゴールデンが読む。ガイドの名所を混ぜると、契約の出力や既存の検査が変わる。ガイドの名所は `proposals` に出さない(指示書)。
- コード: `ikimonobiyori/guide.py`(CLI `python -X utf8 -m ikimonobiyori.guide`)。値は `data/guide/policy.yaml`(区分の表・段階の規則・上限)。コードに値を持たない。
- ファイル:
  - `data/guide/records.jsonl`: 候補の記録(1 行 = 1 つの出どころが 1 つの名所について言った事実)。手元(`IKIMONOBIYORI_DATA_DIR/guide/candidates.jsonl`)に書いた記録を、見直して `guide build` の書き出し(`guide/export/`)から写す。**実行でリポジトリの追跡ファイルを変えない**(CLAUDE.md 規則 8)ため、写すのはエージェントの作業(これまでのカタログの仮承認と同じ)。
  - `data/guide/places.yaml`: 市区町村の代表点(Wikidata。項目の id・座標 小数 2 桁・読んだ時刻)。
  - `data/guide/reviews.yaml`: ユーザーの見直し(外した・承認した・行って確認した)。手元の `guide reject` などは `IKIMONOBIYORI_DATA_DIR/guide/reviews.jsonl` に書き、build はどちらも読む(あと勝ち)。
  - `data/guide/catalog.yaml`(仮承認・承認した名所)・`data/guide/candidates.yaml`(候補のまま・外したもの、理由つき): records・places・reviews から `guide build` が作る。テストが、写した結果と作り直した結果の一致を確かめる。
- 名所の項目(build の結果): `id`(テーマ・都道府県・名前から決まる `g-` + 16 進 10 桁)・`theme`・`name`・`prefecture`・`municipality`・`kinds`(種類ごとの独立した出どころの数と、答えに出してよいか `shown`)・`season`(例年の時期の原文 `text`、月日の窓 `window`、一致する独立した出どころの数、`shown`)・`tier`・`independent_sources`・`classes`・`exists_confirmed`・`range`(status・km・起点・項目の id)・`approval`(`state`: provisional / approved / rejected / candidate、`at`、`by`: auto-rule / user、候補の理由 `reasons`)・`sources`(URL・ホスト・発行元・区分・読んだ時刻・読み方)・`latest_status`(運営者の日付つきの状態があれば)・`access`。
  - 指示書の `approval.state` は provisional / approved / rejected の 3 つ。規則を満たさないものを表すために `candidate` を足した(カタログには入れず、`candidates.yaml` に置く)。
- テーマ: 野鳥・冬鳥・桜・花・ホタル・紅葉(方針 `themes`)。同じ場所でもテーマが違えば別の名所として数える(桜山公園の桜と紅葉など)。理由: 例年の時期と出どころがテーマごとに違うため。
- 例年の時期: 出どころごとに `{text, from, to}`(「10月下旬」「2月末」「1月」の形。旬は既存の `month_thirds`)か `{text, year_round: true}`。年は持たない(例年)。表示する時期は、区分の強い出どころ(A→B→C→D)の原文。重なる時期を言う独立した出どころの数を数える。

## D-06 出どころの区分と、独立した出どころの数え方(フェーズ2 の 2・3)
- 区分はホストの表(`hosts`。後ろが一致する最長のもの)で決める。表にないホストは C(指示書)。`lg.jp`・`tokyo.jp` の自治体のページは A、`go.jp` は B。**公的なドメイン(lg.jp・go.jp)の PDF は B**(調査・資料)にした(`pdf_class_by_suffix`)。理由: 指示書の B「都・環境省などの調査・資料の PDF」。東京都の環境局・建設局のホスト(`kankyo.metro.tokyo.lg.jp`・`kensetsu.metro.tokyo.lg.jp`)は B。
- GO TOKYO(東京観光財団)は指示書の例に従い A。
- 発行元: 表の `publisher`(東京都の 3 つのホストは「東京都」で 1 件)。表にないものは公開接尾辞(`co.jp`・`lg.jp`・`blog.jp` など)の 1 つ下まで(`rurubu.jp` と `kids.rurubu.jp` は同じ)。`ameblo.jp`・`note.com` はパスの最初の部分まで(別の人は別の発行元)。
- **独立した出どころ**: 同じ発行元・同じ URL・書き写し(記録の `copies_of` に元の URL。元の発行元とも 1 つ)を 1 つにまとめた数(union-find)。同じ個人のブログの複数ページは、同じホストなので 1 件。
- 安全側の判断: YAMAP(`yamap.com`)は、別の利用者の記録でも 1 件と数える(個人を区別する手がかりをコードで確かめられないため。少なめに数える)。
- SNS(x.com・instagram.com など。方針 `unreadable_hosts`)の URL は記録しない(指示書: SNS は読まない)。

## D-07 信頼の段階・実在・範囲(フェーズ2 の 4〜6)
- `verified`: 運営者の発信(A)で日付つきの状態(`status: {state, date}`)が読めたもの、またはユーザーが `guide visited <id>` で「行って確認した」と記録したもの。メディア(C)の「見ごろ」では確認済みにしない。
- `curated`: 独立した出どころ 3 件以上で、A・B・C が 1 件以上。`reference`: それ以外(1〜2 件、または D だけ)。強い順に verified → curated → reference。
- 実在の確認: A・B・C の出どころが 1 件以上(D だけの名所は候補のまま)。
- 範囲: 名所の市区町村の代表点(Wikidata)から、起点(東京・横浜。`data/catalog/policy.yaml` の `range_limit`)までの直線距離。表示は 10 km 単位。代表点のない名所は `pending`(「範囲は未確認」。仮承認しない)。座標を推定で作らない。
- 仮承認の条件: 段階が verified か curated・実在の確認あり・範囲内・外されていない。満たすものは `approval: {state: provisional, by: auto-rule, at: 最後に読んだ日}`。
- 種類・時期を答えに出すのは、独立した出どころ 2 件以上が同じことを言うときだけ(`shown`。フェーズ3 の 2)。1 件だけの種類は見直しの一覧にも出さない(記録には残る)。

## D-08 市区町村の代表点の読み方(フェーズ2 の 6)
- `www.wikidata.org` の `wbgetentities`(日本語版ウィキペディアの記事名 → 項目)で、座標(P625)と日本語の説明だけを読む(`fetch/wikidata.py`)。1 回に 10 件の記事名(`config.yaml` の `live.wikidata.titles_per_request`)。
- 記事名は「市区町村名」→「市区町村名 (都道府県)」→「市区町村名 (都道府県の略)」の順に試す。**項目の日本語の説明に都道府県の名前がないものは使わない**(同じ名前の別の市町村を取らないため)。
- 実通信は sources の read と同じゲート(`BIYORI_ALLOW_LIVE=1`・`--max-requests`・計測フック `BIYORI_REQ_LOG`)。テスト中は常に拒否。回数は手元の `guide/places_requests.jsonl` に数え、方針の上限 100 回を超えない。
- 政令市の区(横浜市鶴見区など)は市(横浜市)の代表点を使う(10 km 単位の判定には足りる)。

## D-09 検索・取得の回数の数え方
- エージェントの道具(WebSearch・WebFetch)は計測フックの外なので、`guide log-request --kind search|fetch --phase collect|trial --text <言葉・URL> [--question Qn]` で、使う前に 1 回ずつ数える。上限(方針 `budget`)に達していたら終了コード 3 で、その回は使わない。合計は `guide usage`。記録は手元(コミットしない)。

## D-10 付録A の取り込み(フェーズ3 の 3)
- `docs/seeds/stage23-seeds.md` に付録A をそのまま写した(事実と URL だけ)。表の行 → 候補の項目の対応は `data/guide/seed_map.yaml`(Claude Code が表の言葉を項目の形に直した。数字は表のまま)。
- **付録A の行の種類・時期は、その行のすべての URL が言ったものとして記録した**(付録A は URL ごとの内訳を持たないため)。区分・発行元・独立した出どころの数・段階は、取り込み時にコードが計算し直した(付録A の「出どころの種類」「段階」は使っていない)。
- 1 つの行に 2 つのテーマが入っている S02(桜山公園の冬桜と紅葉)は、URL を分けて 2 つの名所にした(`urls`)。
- 季節の言葉だけの時期(「冬」「秋〜春」「秋〜冬」)は、気象庁の季節の区分(春 3〜5月・夏 6〜8月・秋 9〜11月・冬 12〜2月)で月に直した。原文の言葉は `season.text` に残る。
- 箇条書きの節(桜の種類の説明・ホタルの種類)は、場所を持たない「種類の説明」(`scope: kind`)にした。出典の URL は、その箇条書きが挙げたもの(冬桜と寒桜は、寒桜の行の 2 つの出典を両方に付けた。寒桜の行に「冬桜とは別の種」とあるため)。ホタルは、資料の題名(宮城県の資料はゲンジボタル、岩手県の資料はヒメボタル)で種類に分けた。
- 時期の分からない H05(城山公園 つばきの径)と B09(明治神宮。春・秋の 2 つの時期)は、時期を持たない名所にした。

## D-11 種類の説明(scope: kind)
- 冬の渡り鳥の種類と時期(付録A の A-2)、桜・ホタルの種類は、場所を持たないので、名所とは別の「種類の説明」として持つ(`scope: kind`。範囲は `not_applicable`)。
- 仮承認の条件は、名所とは別: **独立した出どころ 2 件以上**(フェーズ3 の 2「同じ種名・時期が、独立した出どころ2件以上にあるとき、ガイドの答えに出してよい」)と実在の確認(A・B・C の出どころ)。名所の 3 件の規則は場所の定評のためのもので、種類の説明には当てない。

## D-12 集めた候補(フェーズ3 の 4・5)
- 検索 66 回・取得 1 回(上限 80・60)。市区町村の代表点 9 回(Wikidata。上限 100)。合計 66 の市区町村の代表点を読み、すべて都道府県の名前が説明にある項目だった(読めなかったものはない)。
- 検索の結果は、検索の道具が出す抜粋の要約(`origin: search`)。**要約がどの URL の内容かをはっきり示していないときは、その URL に事実を結びつけなかった**(例: 明治神宮のカワセミ、代々木公園以外の早咲きの桜の一部、関東の河津桜の個別の名所)。取得は BE-PAL の東京の梅の名所 11 選の 1 回(`origin: fetch`)。
- 同じプレスリリースを載せた 2 つのサイト(zaikei.co.jp と newscast.jp の宝登山の臘梅園)は、書き写し(`copies_of`)として 1 件に数えた。
- 区分の表に、集めている途中で出てきたホスト(群馬県・山梨県・千葉県の観光協会、よみうりランド(HANA・BIYORI の運営)、東京都の交通局、マップル、フォートラベル(個人の旅行記 = D)、プロバイダーの個人のページ ne.jp = D)を足した。都道府県の地域ドメイン(`*.chiba.jp` など)は自治体なので A、その PDF は B。
- **区分・発行元は、記録したときの値ではなく、build のときの方針の表で決め直す**(表に足したホストを、前に読んだ記録にも効かせるため)。
- ページの中の指示(「〜しろ」)は、読んだ範囲では見つからなかった。
- 見つからなかったもの: **関東のヒメボタルの名所**(「ヒメボタル 関東 名所」で検索。岩手・岡山・大阪の例と生態の資料だけ)。**東京都内の寒椿・椿の名所**(「寒椿 名所 東京」「椿 名所 東京 公園 見頃」。都外の国営武蔵丘陵森林公園だけ)。**十月桜の都内の名所**(「十月桜 名所 東京」)。光が丘公園のカワセミは、BE-PAL の 1 件だけ(公式の紹介ではアオサギ・オオタカ)。
- 推定で足さなかったもの: 検索の要約にあった一般的な目安(「ロウバイは1月〜2月上旬」などは伊勢崎市の資料という出どころつきのものだけ記録)。

## D-13 答えに使う絞り方(find)
- おすすめ(`recommend`): 仮承認・承認・範囲内で、対象の日が例年の時期に入るもの。時期の分からない名所・時期を言う出どころが 1 件だけの名所は、対象の日に合うと言わない(`no_season`)。種類で絞るときは、その種類を言う独立した出どころが 2 件以上の名所だけをおすすめにし、1 件だけなら参考(`reference`)。
- これから(`upcoming`): 例年の時期の始まりが対象の日から 60 日以内(方針 `upcoming_days`。仮置き)。
- 範囲の外(`out_of_range`)は別の欄。名指しの質問のときだけ答えに使う。

## D-14 仮承認と見直しの一覧(フェーズ4)
- 規則(D-07・D-11)を満たすものを `guide build` が仮承認(`approval: {state: provisional, by: auto-rule}`)にし、`data/guide/catalog.yaml` に置いた。満たさないものは `candidates.yaml`(理由つき)。
- 見直しの一覧 `docs/stage23-review.md` は `guide review` の出力に、読み方と外し方を足したもの。テーマごとに、仮承認の表を先に出し、候補は `<details>` で折りたたんだ(朝 5 分で仮承認だけを見られるように)。
- 外す: `guide reject <id> --reason ...`(手元の `guide/reviews.jsonl` に、時刻はコードの時計)。build は `data/guide/reviews.yaml` と手元の見直しの両方を読み、外した名所は理由があっても仮承認しない(`rejected`)。リポジトリに残すときは reviews.yaml に写す(実行で追跡ファイルを変えないため)。
- 承認(`guide approve`)・行って確認した(`guide visited`。段階が verified になる)も同じ形で記録する。

## D-15 スキルの手順(フェーズ5)
- `.claude/skills/ikimono-weekend/SKILL.md`・`AGENTS.md`・`CLAUDE.md` の同じ節(`ikimono-weekend:begin`〜`end`)に、「現況型とガイド型」「ガイド型の答え方」を足した。3 つは同じ内容(既存のテストが一致を確かめる)。
- 言い換えの表: ガイドのテーマへは `data/guide/policy.yaml` の `words`(渡り鳥・ホタル・桜の品種・冬の花など)。現況の対象へは `data/sources/policy.yaml` の `topics` に、**現況の対象が実装済みのものだけ**を足した(渡り鳥・ハクチョウ・カモ・ツル・カワセミ → 野鳥・冬鳥、梅・水仙・サザンカ・ロウバイ・ツバキ・バラ → 花)。桜・ホタルは現況の対象が未実装なので `topics` には足さず、ガイド型だけで答える(既存のテストが `topics` の対象は実装済みであることを確かめるため)。
- 未実装の対象の質問: 今の状態は答えられないことは変えず、名所・時期・種類はガイド型で答えるように手順を変えた(方針の `unimplemented.text` の文は変えていない)。
- **聞き返さない**: 「コードで読む前に 1 回だけ聞く」(段階17 修正①)を、指示書(ユーザーの決定 2026-10-25)に従い「聞き返さない」に変えた。コードで読むのは、事前の許可(`docs/design.md` §0.1)と計測フックがあるときだけ。ないときは要約の道具で読み「簡易な読み取り」の 1 行を書く(CLAUDE.md 規則 6 は変えない)。

## D-16 既存テストの期待値の変更(フェーズ5)
- `tests/test_reading_steps.py::Steps`: 手順の文に「1 回だけ「公式ページをコードで読みます(通信が発生します)。よいですか」」があることを確かめていた。指示書のフェーズ5 の 3「聞き返さない」に従い手順を変えたため、確かめる文を「**聞き返さない**(段階23」に変え、テストの名前を `test_the_steps_do_not_ask_back_and_record_before_answering` にした。ほかの確かめる文(「今回は簡易な読み取りです。表記のぶれがありえます」など)は変えていない。
