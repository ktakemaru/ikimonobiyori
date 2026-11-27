# 報告書: 資料のコンシェル向けの項目の仕上げ

作成 2026-11-27 / 指示書 `docs/brief-concierge-fields-2-instructions.md` / ブランチ `feature/brief-concierge-fields-2`(main `87bf37b` から)

## まとめ

- 資料の候補の `site_ref` を `mountain_site_ref` に変え、座標の細かさ `coord_precision` を足しました。野鳥の観察の名所の座標は、野鳥のプロファイルの粗さ(`area_10km` = 小数 1 桁)に丸めて出すようにしました。丸め方は提案の出力と同じコードを使います。
- データは結びつきだけを 7 行足しました: 三溪園の紅葉 → 花のカタログの件、山との結びつき 6 件。緯度・経度の値は 1 つも足していません。
- 答えは変わっていません。15 の資料で、今回の項目を除いた JSON・Markdown・`fallback.text`・照合の結果が、直す前と同じでした。座標が入った候補は、8 つの資料で 52 件から 65 件に増えました。
- 通信していません。push・PR はまだです。既存のテストで変えたのは、前回足したテストファイルの、項目の名前・野鳥の座標・高尾山の結びつきを見ている行だけです。

| ブランチ | 最後の commit | 実行したテストと最後の行 |
|---|---|---|
| `feature/brief-concierge-fields-2` | この報告書の commit(作業は `17979d0`・`d32f65f`・`aba3e0c`・`5dc44d7`・`2d65ddf`・`5156beb`) | 関係する 57 本(下の「実行したテスト」)を `tests/` から 1 回で: `Ran 1130 tests in 187.534s` / `OK` |

## 第 0 部: 始める前の確かめ

- 始める前: ブランチ `main`、`git log -1` は `87bf37b Merge pull request #73 …`、追跡中のファイルに未 commit の変更なし(`docs/stage72〜85-instructions.md` の 6 つは追跡していないファイル)。main は `87bf37b` を含む。止まる条件には当たらなかった。
- 直す前の資料: 前回と同じ作り方で作った(`tests/helpers.py` を読み込んで通信を禁じる・空の一時のデータ置き場・`guide_brief.build(質問, now=2026-11-27T09:00+09:00)`・Markdown は `render_md`)。保存先は `C:/temp/ikimono-brief-fields-2-20261127/before/`。2 回作って同じになることを確かめた。キーの並びの変化も見えるように、JSON はキーを並べ替えずに書き出した。
- 15 の質問: 前回の 8 つ、追加の 4 つ(梅はどこで見られる?・2月の週末、梅を見たい・白鳥はどこで見られる?・冬桜について教えて)、山の名前が入る 3 つ(今週末、筑波山で紅葉を見たい・御岳山の紅葉はどう?・霧ヶ峰の花の見どころを教えて)。

## 第 1 部: `site_ref` → `mountain_site_ref`

- 変えた所: `guide_brief.py`(`PLACE_KEYS`・`_place_of`・`attach_place_fields`。`place_conflict.members` の項目名も変えた)、`data/ask/guide_mode.yaml`(`site_ref_prefix` → `mountain_site_ref_prefix`)、スキーマ `guide-brief.schema.json`、`tests/test_brief_concierge_fields.py`、`docs/concierge-brief-fields.md`、`README.md`、`CLAUDE.md`・`AGENTS.md`(同じ 1 行)、`CHANGELOG.md` の未公開の節。
- 資料の候補には `site_ref` という項目はもう無い。互換の仕組みは作っていない。
- 変えていないもの: 提案の出力の `place.site_ref`・`details.catalog_site_ref`、名所カタログ・`data/sites.yaml` の `site_ref` という項目名(コードもデータの `site_ref` を読む)。前回の報告書と指示書は、書いた時点の記録として残した。

## 第 2 部: 座標の細かさと野鳥の観察の名所の座標

- `coord_precision`: カタログの件(`catalog`)と `catalog_ref` 先の件(`catalog_via_spot`)は、その件の `location_precision` をそのまま入れる。丸めた野鳥の座標は、丸めた粗さを入れる。観察の名所の `point`(`observation_spot`)には細かさが書かれていないので、推測せず `null` にした。座標が `null` の候補は `null`。
  - 座標があって `coord_precision` が `null` の候補: 8 つの資料で 10 件、15 の資料で 16 件。どれも `observation_spot` で、旧古河庭園・町田薬師池公園・高尾山。
- 野鳥の観察の名所: `catalog_ref` が無い件は、出典つきの `point` か `bird_range` を、プロファイル `birds` の `care.location_precision`(`area_10km`)に丸めて出す。`coord_source` は `observation_spot_coarsened`。
  - 丸め方: 提案の出力 `proposals.place_of` の粗さの決め方を `proposals.coarse_precision` に切り出し(中身は同じ。ゴールデン・提案のテストは通った)、資料からはそれと `engine.round_coord` を呼ぶ。丸める桁が決まっていない粗さのときや、プロファイルが読めないときは、元の値を出さずに `null` にする。
  - 順番: `catalog_ref` 先のカタログの座標が先(横浜自然観察の森は今までどおり `catalog_via_spot` 35.3/139.6)。
  - 入った座標: 県立境川遊水地公園 35.4/139.5・舞岡公園 35.4/139.6・県立座間谷戸山公園 35.5/139.4・生田緑地 35.6/139.6・県立相模原公園 35.5/139.4(すべて `area_10km`)。鶴見川多目的遊水地・北本自然観察公園は元の座標が無いので `null` のまま。
  - 丸める前の値が出ないことは、テストで確かめた(資料の JSON と、データ置き場に書いた資料・ほかのファイルのすべての `lat`/`lon` の組に、丸める前の組が無いこと)。
  - ほかの対象の座標は今までどおり元の値のまま。設定は `spot_coords_skip_subjects` を `spot_coords_coarsen_subjects`(`[birds, wintering_birds]`)に変えた。`wintering_birds` の観察の名所は今は無い。
- 距離: 丸めた座標から出した出発地からの距離と今の `distance_km` の差は、15 の資料で最大 3km(舞岡公園 11km と 8km)。ほかの出どころは差 0km。

## 第 3 部: 観察の名所とカタログの件を結ぶ

先にコードで調べたこと: `catalog_ref` は、座標のほかに `observations._from_spot` が使っている。別名・例年の時期・行事・ページ・座標・標高を借り、借りたカタログの件を候補から外す(`used`)。`match_record` も使う(記録の割り当て)。ただし、ふだんの実行(`catalogs=None`)で読むのは**同じ対象のカタログだけ**。対象の違う件を指す `catalog_ref` は読まれないので、候補の作り方は変わらない。同じ対象の件に結ぶと答えが変わるので、同じ対象の件は結ばないことにした。結んだあと、`observations.all_candidates` の紅葉・花・野鳥の出力をまるごと書き出して比べ、結ぶ前と 1 バイトも違わないことを確かめた。

| 観察の名所 | 名前・都県・市区町村 | 結ぶ先 | 名前・都県・市区町村 | 結ぶ先の座標 | 結果 |
|---|---|---|---|---|---|
| `obs-kouyou-0002` | 三溪園・神奈川県・横浜市中区 | `hana-0021`(花) | 三溪園・神奈川県・横浜市中区 | あり(`exact`) | **結んだ** |

結ばなかった件:

| 観察の名所 | 相手 | 理由 |
|---|---|---|
| `obs-kouyou-0041` 明月院(神奈川県・鎌倉市) | `hana-0055` 明月院(神奈川県・鎌倉市) | 条件には合うが、相手に座標が無い(結んでも何も入らない) |
| `obs-kouyou-0070` 上野恩賜公園(東京都・台東区) | `hana-0091` 上野恩賜公園(東京都・台東区) | 同上 |
| `obs-kouyou-0083` 旧古河庭園(東京都・北区) | `hana-0002` 旧古河庭園(東京都・市区町村なし) | 相手の市区町村が書かれていない。また観察の名所に出典つきの座標があり、結ぶと今の座標の値が変わる |
| `obs-kouyou-0078` 神代植物公園(東京都・調布市) | `hana-0003` 神代植物公園(東京都・市区町村なし) | 相手の市区町村が書かれていない |
| `obs-kouyou-0003` 生田緑地 | `hana-0034` 生田緑地ばら苑 | 名前が違う(承認待ちで座標も無い) |
| `obs-kouyou-0010` 箱根強羅公園 | `hana-0016` 箱根強羅公園ローズガーデン | 名前が違う |
| `obs-kouyou-0032` 山下公園通り | `hana-0009` 山下公園 | 名前が違う |
| `obs-kouyou-0053` 養老渓谷 | `kouyou-0025` 養老渓谷(粟又の滝) | 名前が違う。同じ対象 |
| `obs-yacho-0001` 県立境川遊水地公園・`obs-yacho-0006` 生田緑地 | `hana-0031`・`hana-0034` | 野鳥の観察の名所は結ばない(指示書) |

- 前回の報告書が挙げた鎌倉 長谷寺(`kouyou-0021`・`hana-0054`)は、どちらもカタログの件で観察の名所ではないので、`catalog_ref` では結べない(どちらにも座標があるので、資料ではもう座標が入っている)。
- 結んだあと、三溪園の候補には `catalog_via_spot` で 35.417/139.66(`exact`)が入った(15 の資料のうち 5 つ)。

## 第 4 部: 山との結びつき

| 件 | 名前・都県・市区町村 | 山(sites.yaml) | 名前の一致(括弧の前) | 直線距離 | 置いた項目 | 結果 |
|---|---|---|---|---|---|---|
| 観察の名所 `obs-kouyou-0088` | 高尾山・東京都・八王子市 | m029 高尾山 | 同じ | 0km(名所の `point` が m029 の座標を写したもの) | `mountain_site_ref`(新しい項目) | 足した |
| 観察の名所 `obs-kouyou-0089` | 御岳山・東京都・青梅市 | m031 御岳山 | 同じ | 0km(同上、m031) | `mountain_site_ref` | 足した |
| 観察の名所 `obs-kouyou-0093` | 陣馬山・神奈川県・相模原市緑区 | m030 陣馬山 | 同じ | 名所に座標が無い | `mountain_site_ref` | 足した |
| 名所カタログ `kouyou-0015` | 筑波山(筑波山神社・宮脇駅周辺)・茨城県・(なし) | m057 筑波山(女体山) | 同じ | 1.28km | `site_ref`(今ある項目) | 足した |
| 名所カタログ `kouyou-0020` | 大山(大山寺)・神奈川県・(なし) | m027 大山(伊勢原) | 同じ | 1.61km | `site_ref` | 足した |
| 名所カタログ `hana-0037` | 霧ヶ峰(車山肩・富士見台・八島ヶ原湿原)・長野県・諏訪市・下諏訪町 | m043 霧ヶ峰(車山) | 同じ | 件に座標が無い | `site_ref` | 足した |

- 山の ID と名前の組は、6 件とも指示書の表と同じだった。10km より離れた件は無かった。
- sites.yaml の山には都県の項目が無い(`region: 関東甲信` だけ)。そのため都県は突き合わせていない。
- 名所そのものの ID(`id`)は書き換えていない。観察の名所の新しい項目 `mountain_site_ref` は、資料の候補を作るとき(`guide_brief._place_of`)だけ読む。値は sites.yaml にある山のときだけ使う。
- ほかに同じ条件(名前の括弧の前が sites.yaml の山と同じ)に合う件は、観察の名所・名所カタログに無かった。
- **大山の結びつきは資料に出ない**: 大山のカタログの件 `kouyou-0020` は、観察の名所 `obs-kouyou-0019`(大山寺・大山阿夫利神社下社。`catalog_ref: kouyou-0020`)に借りられていて、候補の作り方では候補から外れる。資料の候補は `obs-kouyou-0019` になるので、`kouyou-0020` の `site_ref` は資料には出ない。観察の名所が `catalog_ref` 先の `site_ref` を借りる読み方を一度足したが、指示書の 6 件の外の名所(`obs-kouyou-0019`)に結びつきが出るので外した(「6 件のほかは足さない」「迷ったらやらない側」。決めてほしいこと 1)。テスト `test_no_link_through_catalog_ref` で、借りないことを確かめている。
- **提案の出力に出る項目**: 名所カタログの `site_ref` は、提案の出力 `biyori-proposal/1` の `details.catalog_site_ref` にも写る(`proposals.py`。前からある動き)。筑波山・大山の現況が読めたときの提案に、`details.catalog_site_ref: yamabiyori:m057` などが新しく出る。ゴールデン・提案のテストは通った(テストのデータにこの 3 件は出てこない)。CLAUDE.md の「提案の項目を変えるときは事前に報告する」に当たりうるので、ここに書いた(決めてほしいこと 2)。
- 山の名前が入る 3 問の資料: 筑波山・御岳山・霧ヶ峰の名所は、どれも候補に出てこなかった。直す前から同じで、候補の選び方には触っていない。「今週末、筑波山で紅葉を見たい」「御岳山の紅葉はどう?」は紅葉の一覧(12 件。高尾山を含む)になり、高尾山に `m029` が入った。「霧ヶ峰の花の見どころを教えて」は ID の無い例年の目安 2 件(城峯公園・桜山公園)。6 件の結びつきは、実際のデータの `_place_of` を呼ぶテストで確かめた。

## `null` の件数

8 つの資料(直したあと。前回: 候補 95 件のうち ID 82・座標 52・山との結びつき 0):

| 候補の種類 | 件数 | `place_id` あり | null | 座標あり | null | `coord_precision` あり | null | `mountain_site_ref` あり | null |
|---|---|---|---|---|---|---|---|---|---|
| 順位つき | 82 | 82 | 0 | 65 | 17 | 55 | 27 | 4 | 78 |
| 例年の目安 | 11 | 0 | 11 | 0 | 11 | 0 | 11 | 0 | 11 |
| 町の名所 | 2 | 0 | 2 | 0 | 2 | 0 | 2 | 0 | 2 |
| 合計 | 95 | 82 | 13 | 65 | 30 | 55 | 40 | 4 | 91 |

- 座標の出どころ: `catalog` 37・`catalog_via_spot` 8(前回 5。三溪園の 3 件が増えた)・`observation_spot` 10・`observation_spot_coarsened` 10(新しく)。細かさ: `exact` 35・`area_10km` 20・`null` 10。
- `mountain_site_ref` の 4 件は、どれも高尾山(4 つの資料)。
- 順位つきで座標が `null` の 17 件の名所: 久良岐公園・保土ケ谷公園・円覚寺・北の丸公園・大佛次郎記念館・山手西洋館(山手ローズウィーク)・鶴見川多目的遊水地(観察の名所に座標が無い)、あやせローズガーデン・八景島 丘の広場バラ園・土屋ざる菊園(カタログの件に座標が無い)。

15 の資料:

| 候補の種類 | 件数 | `place_id` あり | null | 座標あり | null | `coord_precision` あり | null | `mountain_site_ref` あり | null |
|---|---|---|---|---|---|---|---|---|---|
| 順位つき | 106 | 106 | 0 | 87 | 19 | 71 | 35 | 6 | 100 |
| 例年の目安 | 14 | 0 | 14 | 0 | 14 | 0 | 14 | 0 | 14 |
| 町の名所 | 2 | 0 | 2 | 0 | 2 | 0 | 2 | 0 | 2 |
| 種の名所 | 34 | 0 | 34 | 0 | 34 | 0 | 34 | 0 | 34 |
| 合計 | 156 | 106 | 50 | 87 | 69 | 71 | 85 | 6 | 150 |

- 座標の出どころ: `catalog` 51・`catalog_via_spot` 10・`observation_spot` 16・`observation_spot_coarsened` 10。細かさ: `exact` 51・`area_10km` 20・`null` 16。

## 答えが変わらないことの確かめ

直す前(`before/`)と、最後のコードで作り直した資料(`after/`)を比べた(途中の第 2 部・第 3 部のあとでも比べ、同じだった)。

| 資料 | 質問 | JSON(今回の項目と `generator` を除く) | Markdown | `fallback.text` | 今回の項目で変わった候補 |
|---|---|---|---|---|---|
| q01 | 今週末、高尾山で紅葉を見たい | 同じ | 同じ | 同じ | 高尾山に `m029` |
| q02 | 今週末の紅葉の情報は? | 同じ | 同じ | 同じ | 三溪園に座標、高尾山に `m029` |
| q03 | 丹沢で今咲いている花は? | 同じ | 同じ | 同じ | なし |
| q04 | 八ヶ岳の見どころを教えて | 同じ | 同じ | 同じ | なし |
| q05 | 高尾山の見どころを教えて | 同じ | 同じ | 同じ | なし |
| q06 | 今週末、野鳥を見に行きたい | 同じ | 同じ | 同じ | 野鳥の観察の名所 5 件に丸めた座標 |
| q07 | 今週末のおすすめは? | 同じ | 同じ | 同じ | 三溪園に座標、高尾山に `m029`、野鳥の観察の名所 5 件に丸めた座標 |
| q08 | 神奈川と東京で紅葉の見ごろを教えて | 同じ | 同じ | 同じ | 三溪園に座標、高尾山に `m029` |
| q09〜q12 | 梅・2月の梅・白鳥・冬桜 | 同じ | 同じ | 同じ | なし |
| q13 | 今週末、筑波山で紅葉を見たい | 同じ | 同じ | 同じ | 三溪園に座標、高尾山に `m029` |
| q14 | 御岳山の紅葉はどう? | 同じ | 同じ | 同じ | 三溪園に座標、高尾山に `m029` |
| q15 | 霧ヶ峰の花の見どころを教えて | 同じ | 同じ | 同じ | なし |

- 比べ方: JSON は、直す前から `generator` と候補の `site_ref`・`lat`・`lon`・`coord_source` を、直したあとから `generator` と候補の `mountain_site_ref`・`coord_precision`・`lat`・`lon`・`coord_source` を除き、同じ形で書き出した文字列を比べた(キーの並びも含む)。Markdown はファイルのバイト列で比べた。
- 除いた項目の変化(15 の資料ぶん): 新しく座標が入った候補 15(三溪園 5・野鳥の観察の名所 10)、新しく `mountain_site_ref` が入った候補 6(高尾山)。**前回入っていた座標の値・出どころが変わった候補は 0**。座標が消えた候補も 0。`coord_precision` は全候補に新しく入った項目。
- 照合: 15 の資料それぞれで、同じ下書き 2 通り(`fallback.text` と、候補の名前と座標のある候補の数を書いた 1 文)を、直す前と直したあとの資料に `guide_verify.check` で照らした。30 通りとも結果がまったく同じだった。
- 候補の作り方: `observations.all_candidates` の紅葉・花・野鳥の出力が、直す前と 1 バイトも違わない(第 3 部・第 4 部のデータを足したあと)。

## 実行したテスト

- 関係する 57 本を `tests/` から 1 回で実行した: `Ran 1130 tests in 187.534s` / `OK`。一覧は `C:/temp/ikimono-brief-fields-2-20261127/tests-list.txt`。資料・照合(`test_stage75_guide`〜`test_stage85` の 23 本)、文書・設定(`test_sources`・`test_self_contained`・`test_stage63b`・`test_ikimonobiyori`)、カタログ・名所・`site_ref` を読むもの(`test_catalog`・`test_site_sets`・`test_birds_and_flowers`・`test_spot_coords`・`test_stage34`〜`36`・`38`・`47`・`50`・`54`・`56`・`57`・`test_stage62_tsukuba`・`test_stage62_regions`)、提案・契約・ゴールデン(`test_proposals`・`test_golden`・`test_compose_and_survey`・`test_stage19`〜`22`・`test_stage20_nikko_observed`・`test_stage20_records`・`test_stage23`・`27`・`48`・`51`)、`test_brief_concierge_fields`・`test_brief_concierge_fields_2`。
- 前回の「51 本」の正確な一覧は残っていなかった。そこで、前回の報告書に名前のあるものを全部含むように広めに選んだ。

## 変えたテスト

既存のテストで変えたのは `tests/test_brief_concierge_fields.py` の次の行だけ(期待値の変更・削除・スキップはこのほかに無い)。

| 行 | 変えたこと | 理由 |
|---|---|---|
| 2(説明の文) | `site_ref` → `mountain_site_ref` | 第 1 部(名前) |
| 85(`test_distance_is_unchanged_by_the_new_fields`) | `coord_source` が `observation_spot_coarsened` の候補を除く条件を足した | 野鳥の座標。丸めた座標は 2km の幅に入らない(生田緑地で 2km)。丸めの幅での確かめは新しいテストに移した(8km 未満) |
| 102(`test_spot_with_point`) | `"site_ref": None` → `"coord_precision": None, "mountain_site_ref": "yamabiyori:m029"` | 第 1 部(名前)・第 2 部(項目が増えた)・第 4 部(高尾山を m029 と結んだ)。この行は、指示書が認めた「`site_ref` の名前と野鳥の座標を見ている行」を超えて、項目の追加と値の変更も含む。この行は候補の項目をまるごと比べているので、項目を足すと必ず落ちる。高尾山の結びつきは指示書の第 4 部で足すと決まっていたので、避けられなかった |
| 114(`test_bird_spot_coordinates_are_not_copied`) | `assertIsNone(p["lat"])` → 丸めた座標 35.4/139.6・`observation_spot_coarsened` を確かめる | 野鳥の座標(利用者の決定)。関数名は変えていない |
| 134・150・167 | `site_ref` → `mountain_site_ref` | 第 1 部(名前)。134 の関数名 `test_mountain_site_gives_site_ref_only`・167 の関数名は変えていない |

足したテスト: `tests/test_brief_concierge_fields_2.py`(20 件)。座標の細かさの写し方、野鳥の丸め方とプロファイルの粗さ、丸める前の値がどこにも出ないこと、丸めた座標の距離、`catalog_ref` 先の座標が先になること、丸められないときは `null` になること、提案の出力の丸め方が今までと同じこと、三溪園の結びつき、対象の違う結びつきが同じ名所で野鳥でないこと、候補の作り方が変わらないこと、山の結びつき 6 件・名前と距離・ほかに結びつきが無いこと・`catalog_ref` 先の結びつきを借りないこと・sites.yaml に無い山を使わないこと、高尾山の資料。

## 確かめられていないこと

- **実通信つきの `ask brief`**。通信しない決まりなので実行していない。
- 大山の結びつきが資料に出る場面(上の第 4 部のとおり、今の作り方では出ない)。
- 提案の出力に `details.catalog_site_ref` が出ること。筑波山・大山の現況の記録が要るので、テストでも実行でも確かめていない。
- 陣馬山・霧ヶ峰(`hana-0037`)の位置(座標が無いので距離を出せない)。6 件すべての都県(sites.yaml に都県が無い)。
- 高尾山・御岳山の距離 0km は、名所の座標が山の座標を写したものなので、別に確かめたことにはならない。
- 山の名前が入る 3 問で、筑波山・御岳山・霧ヶ峰の名所が候補に出る資料(今の選び方では出てこない)。
- 実際のデータ置き場で作った資料、候補をまとめた資料(`candidate_merges`)、今年の現況つきの候補。
- 全テストと CI(push していないので未実行)。

## 利用者がやること

1. (`C:\ikimonobiyori` のウィンドウ、Git Bash)`git push -u origin feature/brief-concierge-fields-2` を実行する。
2. (GitHub)`feature/brief-concierge-fields-2` から main 向けの PR を作る。
3. (GitHub)その PR の CI が全部 pass であることを確かめる。
4. (GitHub)その PR をマージする。
5. (`C:\ikimonobiyori` のウィンドウ、Git Bash)`git switch main` を実行する。
6. (同じウィンドウ)`git pull` を実行する。
7. (同じウィンドウ。通信が要る)`time python -X utf8 -m ikimonobiyori.ask brief "今週末、高尾山で紅葉を見たい"` を実行し、1 行目に出た資料の id(`b2026…` の形)と、最後に出る `real` の時間を控える。
8. (同じウィンドウ)`python -X utf8 -c "import sys; from ikimonobiyori import guide_brief as GB; d=GB.load(sys.argv[1]); print(d['generator']); [print(r['name'], r['place_id'], r['lat'], r['lon'], r['coord_source'], r['coord_precision'], r['mountain_site_ref']) for r in d['candidates']]" <7 の 1 行目の id>` を実行する。`generator` に 40 桁の `commit` と `dirty: False` が入ること、高尾山の行に `yamabiyori:m029` が出ることを見る。

## コンシェル側で使うときのメモ(書くだけ。決めるのはコンシェル側。`docs/concierge-brief-fields.md` 2.2 にも同じ内容)

- 項目: 候補の `place_id`(名所の ID)・`lat`/`lon`(緯度・経度)・`coord_source`(座標を写した元)・`coord_precision`(座標の細かさ)・`mountain_site_ref`(山の地点 `yamabiyori:mNNN`)、資料の `generator`(`name`・`version`・`commit`・`dirty`・`generated_at`)。資料の形の名前は `ikimonobiyori-guide-brief/1` のまま。スキーマは `ikimonobiyori/schemas/guide-brief.schema.json`。資料の候補に `site_ref` という項目は無い(2026-11-27 に `mountain_site_ref` に変えた。提案の出力 `biyori-proposal/1` の `place.site_ref` は名所そのものの ID で、資料では `place_id` に当たる)。
- `lat`/`lon` が `null` の候補: 山・星の地点からの直線距離を計算できない。「日中」の枠に入れない、または名前・都県・市町村だけで扱う、などが考えられる。座標があるのは順位つきの候補の一部だけ(8 つの資料で 95 件中 65 件)。
- `coord_precision` で座標の細かさが分かる: `exact`(名所の位置)・`area_1km`(小数 2 桁。1km 程度ずれうる)・`area_10km`(小数 1 桁。5〜7km 程度ずれうる)。`null` は、座標はあるが細かさが元のデータに書かれていないもの(観察の名所の `point`。`coord_source: observation_spot`)。20km 以内などの判定では、`area_10km` の候補は端の扱いに注意が要る。
- `coord_source: observation_spot_coarsened` は野鳥の観察の名所の座標を、野鳥のプロファイルの位置の粗さ(`area_10km`)に丸めたもの。実際の場所から数 km ずれる。丸める前の値は資料に無い。地図にピンを立てる用途には向かない。
- `place_id` は 1 つの名所に 1 つではない: 同じ名所でも対象ごとに別の ID がある(三溪園の紅葉 `obs-kouyou-0002` と花 `obs-hana-0001`)。同じ名所かどうかを ID だけで決めると、別の名所に見えることがある。
- `mountain_site_ref` が入るのは、データに結びつきがある 6 か所(高尾山・御岳山・陣馬山・筑波山・大山・霧ヶ峰)と、種の名所の `mountain_site` だけ。大山のカタログの件 `kouyou-0020` は観察の名所 大山寺・大山阿夫利神社下社(`obs-kouyou-0019`)に借りられていて候補に出てこないので、今は大山の結びつきは資料に出ない。`null` でも山の近くの名所でないとは限らない。山との突き合わせは、`mountain_site_ref` があるときは ID で、無いときは座標と距離でする形が考えられる。
- `generator.commit` が `null` のとき(実行用のコピーなど)は、`version` だけで版を記録することになる。`dirty: true` のときは、その commit と手元の中身が違う。
- 資料の `id` は今までどおり質問・`now`・`prev` だけから決まり、`generator` を含まない。同じ id の資料でも `generated_at`・`commit` は作り直すたびに変わりうる。

## 決めてほしいこと

1. **大山の結びつきを資料に出すかどうか(提案)**: 大山のカタログの件 `kouyou-0020` に `site_ref: yamabiyori:m027` を足したが、この件は観察の名所 大山寺・大山阿夫利神社下社(`obs-kouyou-0019`)に借りられていて、資料には出ない。出す方法は 2 つある。(a) `guide_brief._place_of` で、観察の名所が `catalog_ref` 先の件の `site_ref` を借りる(コード 1 行。座標と同じ順番。今回いったん作って外した)。(b) `obs-kouyou-0019` に `mountain_site_ref: yamabiyori:m027` を書く(データ 1 行)。どちらも、指示書の 6 件の外の名所に結びつきが出る。
2. **提案の出力に出る `details.catalog_site_ref`**: 筑波山・大山・霧ヶ峰のカタログの件に `site_ref` を足したので、その現況の提案に `details.catalog_site_ref` が新しく出る(項目は前からあるが、値の入る件が増える)。このままでよいか。
3. **結ばなかった件**: 旧古河庭園・神代植物公園は、花のカタログの件に市区町村が書かれていないので結ばなかった。市区町村を書き足せば結べる。ただし旧古河庭園は、結ぶと今の座標(観察の名所の出典つきの `point`)がカタログの値に替わる。明月院・上野恩賜公園は相手に座標が無い。
4. **観察の名所の座標の細かさ**: 観察の名所の `point` には細かさの項目が無いので、`coord_precision` が `null` になる(15 の資料で 16 件)。`point` に `location_precision` を書き足すかどうか。
5. **山の名前が入る質問の候補**: 「今週末、筑波山で紅葉を見たい」「御岳山の紅葉はどう?」で筑波山・御岳山の名所が候補に出てこない(紅葉の一覧になる)。今回の範囲の外なので直していない。直すかどうか。
