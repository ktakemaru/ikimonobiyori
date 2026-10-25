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
