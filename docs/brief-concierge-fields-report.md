# 報告書: 資料(ask brief)にコンシェル向けの項目を足す

作成 2026-11-27 / 指示書 `docs/brief-concierge-fields-instructions.md` / ブランチ `feature/brief-concierge-fields`(main `72a11ad` から)

## まとめ

- 資料の候補に `place_id`・`lat`・`lon`・`coord_source`・`site_ref`、いちばん上に `generator`(版・commit・未 commit の変更・作った時刻)を足しました。値はリポジトリのデータから写すだけで、無いものは `null` です。スキーマ `ikimonobiyori/schemas/guide-brief.schema.json` を足しました。
- 答えは変わっていません。8 つの資料(と追加の 4 つ)で、足した項目を除いた JSON・Markdown・`fallback.text` が、直す前と一字一句同じでした。
- 埋まったのは順位つきの候補だけで、8 つの資料の候補 95 件のうち ID が 82 件、座標が 52 件です。`site_ref` は 0 件でした(結びつきのデータがあるのは種の名所の `mountain_site` だけで、8 つの資料には出てこなかった)。
- 通信していません。push・PR はまだです。既存のテストの期待値は変えていません。

| ブランチ | 最後の commit | 実行したテストと最後の行 |
|---|---|---|
| `feature/brief-concierge-fields` | この報告書の commit(実装は `c3ae2db` と、その直しの commit) | 関係する 51 本(資料・照合の `test_stage75_guide`〜`test_stage85` の 20 本、文書・設定を読む `test_sources`・`test_self_contained`・`test_stage63b` ほか 13 本、提案・契約・ゴールデンの `test_proposals`・`test_golden`・`test_compose_and_survey`・`test_ikimonobiyori`・`test_stage19`〜`test_stage22` ほか 17 本、新しい `test_brief_concierge_fields` を最後に)を `tests/` から 1 回で: `Ran 1125 tests in 157.516s` / `OK` |

## 候補の出どころ(第 0 部 3。実装の前に書いた)

調べ方: `guide_brief.build` のコード(`_candidates`・`typical_candidates`・`_town_candidates`・`_species_facts`・`_dated_species_candidates`・`bird_highlights`・`_area_plan`・`merge_same_candidates`)と、通信を禁じて作った直す前の資料(8 問 + 追加の 4 問)の候補 130 件を、データのファイルと突き合わせた。

| 候補の種類(資料での見分け方) | 作られる元 | 元の行に ID | 元のデータに座標 | 山の地点との結びつき |
|---|---|---|---|---|
| 順位つきの候補(`rank` が数。`basis` は `current` か `typical`) | 今までの形の答えの計画(`answer_plan.json`)の順位の行。行は名所カタログ(`data/catalog/*.yaml`)か観察の名所(`data/observations/spots.yaml`)の 1 件 | **ある**: 順位の行の `id`(カタログの `kouyou-0024`・`hana-0021`・`yacho-0001` など、観察の名所の `obs-kouyou-0002` など)。今までは資料に写していなかった | カタログ: `point`(例を除く 149 件中 74 件にある。花は 92 件中 17 件。値は各件の `location_precision` の桁で入っている)。観察の名所: `point` 28 件・`bird_range` 6 件(野鳥)、`catalog_ref` でカタログの件を指すものが 7 件 | カタログの `site_ref` は例の 1 件(`kouyou-example-0002`)だけ。観察の名所には項目なし(高尾山 `obs-kouyou-0088` の `point.source` に「sites.yaml m029 の座標」と文で書かれているだけ) |
| 例年の目安(`rank` が `null`・`basis: typical`・`subject: null`) | ガイドのカタログ(`guide.build()`。`data/guide/catalog.yaml`) | ある: `g-` + テーマ・都道府県・名前の sha1 の先頭 10 文字(`guide.entry_id`)。名前・テーマが変わると変わる。今の候補の行には写していない | **無い**(ガイドのカタログに座標の項目がない) | 無い |
| 町の名所(`basis: town`) | 名所カタログ(承認済み)とガイドのカタログ(`guide_materials.town_spots`) | 元の行にはある(カタログの `id`・ガイドの `g-`)が、`town_spots` の行に ID を運んでいない | カタログの件は `point` がある。ガイドの件は無い | 無い |
| 種の名所(`basis: species`) | 名所カタログ・記録・ガイドのカタログ(`season_place.gather`) | 行に ID を運んでいない | カタログの件は `point` がある(行には運んでいない) | **ある**: 候補の `mountain_site`(段階84 第1部 A。括弧の前の名前が sites.yaml の山と同じ名所。山の名前が入る。sites.yaml の `site_ref` は `yamabiyori:mNNN`) |
| 季節の目玉の観察地(`basis: highlight`) | `data/ask/guide_mode.yaml` の `bird_highlights.sites`(名前・都県・市町村・テーマ) | 無い | 無い | 無い |
| エリアの名所(山域の質問) | 順位つきの候補と同じ(`_area_plan` が別の計画を作る) | 順位つきと同じ | 順位つきと同じ | 順位つきと同じ |
| 日付つきの種の名所(`basis: species`。`_dated_species_candidates`) | 今までの形の答えが選んだ名所の名前だけ | 無い | 無い | 無い |
| 記録の種の名所(`basis: species`。`_place_records`。質問の場所の、読んだ事実の記録) | データ置き場の、Web から読んだ事実の記録(`observations.read_records`) | 無い | 無い(記録は市町村まで。座標は記録しない) | 無い |

- 同じ名前でも対象ごとに別の ID がある(三溪園: 紅葉 `obs-kouyou-0002`・花 `obs-hana-0001`。鎌倉 長谷寺: `kouyou-0021`・`hana-0054`。旧古河庭園・生田緑地・県立境川遊水地公園も)。候補は名前で 1 件にまとめているので、先に来た対象の行の ID になる。
- 8 問の資料の候補 95 件の内訳: 順位つき 82 件(`basis: typical`)・例年の目安 11 件・町の名所 2 件。種の名所・季節の目玉・今年の現況つき・まとめた候補(`candidate_merges`)は 0 件(データ置き場が空なので)。追加の 4 問(種の質問)の候補 35 件は、種の名所 34 件・例年の目安 1 件。

## 足した項目

| 項目 | 場所 | 中身 | 無いとき |
|---|---|---|---|
| `place_id` | 候補 | 名所カタログの件は `ikimonobiyori:<カタログの id>`、観察の名所の件は `ikimonobiyori:<観察の名所の id>`。計画の順位の行の `id` から | `null` |
| `lat`・`lon` | 候補 | 元のデータの値のまま(丸めない)。名所カタログの `point`(`status: candidate` の件も、順位に使われていれば写す。例: 山下公園 `hana-0009`)→ 観察の名所の `catalog_ref` が指すカタログの `point` → 観察の名所の `point`(`point.source` に出典が書かれたものだけ。決めてほしいこと 5)の順。野鳥の観察の名所の座標は写さない(決めてほしいこと 2) | `null` |
| `coord_source` | 候補 | `catalog`・`catalog_via_spot`・`observation_spot` | `null` |
| `site_ref` | 候補 | `yamabiyori:mNNN`。種の名所の `mountain_site` が指す sites.yaml の山の `site_ref`、またはカタログの件の `site_ref`(`yamabiyori:` で始まるものだけ) | `null` |
| `place_from`・`place_conflict` | `candidate_merges` の 1 件 | まとめた候補に項目を写した元の候補の名前。元の候補の `place_id`・`site_ref` が食い違ったときは、候補の 5 つの項目を `null` にし、`place_conflict: {members, reason}` を残す | `place_from: null` |
| `generator` | いちばん上(`schema` の次) | `name`(`ikimonobiyori`)・`version`(`ikimonobiyori/__init__.py` の `__version__` から読む)・`commit`(40 桁)・`dirty`(追跡中のファイルの未 commit の変更)・`generated_at`(パソコンの時計) | `commit`・`dirty` は `null` |

- 名前の合わせ方: 提案の出力 `biyori-proposal/1` の `place.lat`・`place.lon` と同じ名前にした。**`site_ref` は合わせられなかった**: 提案の `place.site_ref` は名所そのものの ID(`ikimonobiyori:<id>`)で、資料ではそれを `place_id` にした。資料の `site_ref` は、指示書のとおり山の地点との結びつき(提案では `details.catalog_site_ref` に近い)なので、同じ名前で意味が違う。また提案の座標は位置の粗さで丸めた値なので、資料の座標と違うことがある(今のカタログは各件の粗さの桁で入っているので、カタログの件では同じ値になる)。
- 足した場所: `guide_brief.py` の `place_fields_before_merge`・`attach_place_fields`(候補をまとめる直前と直後)と `generator_info`。設定は `data/ask/guide_mode.yaml` の `concierge_fields`。資料の Markdown(`render_md`)と `rules` は触っていない。
- commit の読み方: `git -C <パッケージのフォルダ> rev-parse --show-toplevel` でリポジトリの直下にパッケージがあることを確かめてから、`rev-parse HEAD` と `status --porcelain --untracked-files=no`。引数の配列で呼び、`--no-optional-locks` を付ける(git が `.git/index` を書き直さない。書き込み先の決まり 8)。待ち時間の上限 5 秒(仮の値)。失敗したら `null` で、資料は作る。今あるコードに同じ用途の部品は無かった(`knowledge_backup.py` の git は別のリポジトリ用)。`parent.parent` を使うと `tests/test_self_contained.py`(パッケージの外を指さない)に当たったので、パッケージのフォルダから呼ぶ形にした。
- テストでの差し替え: `BIYORI_UNDER_TEST=1` では git を呼ばない(`commit`・`dirty` は `null`。`_git_state(run=...)` に差し替えを渡したときだけ呼ぶ)。テスト専用の時計(`IKIMONOBIYORI_TEST_CLOCK`。`tests/nonet.py` が有効にする)のときは `generated_at` に `now` を使う。今ある `test_stage75_guide` の「同じ質問・同じ now なら資料全体が同じ」のテストを、期待値を変えずに通すため。

### 実物の例(通信なし。テストの仕組みの下で作った「今週末、野鳥を見に行きたい」の資料から 3 件)

```json
{"name": "東京港野鳥公園", "rank": 1, "basis": "typical", "distance_km": 22, "place_id": "ikimonobiyori:yacho-0001", "lat": 35.6, "lon": 139.8, "coord_source": "catalog", "site_ref": null}
{"name": "舞岡公園", "rank": 7, "basis": "typical", "distance_km": 11, "place_id": "ikimonobiyori:obs-yacho-0002", "lat": null, "lon": null, "coord_source": null, "site_ref": null}
{"name": "横浜自然観察の森", "rank": 10, "basis": "typical", "distance_km": 19, "place_id": "ikimonobiyori:obs-yacho-0003", "lat": 35.3, "lon": 139.6, "coord_source": "catalog_via_spot", "site_ref": null}
```

(候補のほかの項目は省いた。東京港野鳥公園の座標は、カタログの `location_precision: area_10km` の桁(小数 1 桁)のまま。)

`generator`: テストの仕組みの下では `{"name": "ikimonobiyori", "version": "0.2.0", "commit": null, "dirty": null, "generated_at": "2026-11-27T09:00:00+09:00"}`。テストの外で `generator_info()` だけを呼んだとき(通信なし。2026-11-27): `{"name": "ikimonobiyori", "version": "0.2.0", "commit": "f28bd57c8539538c0381a8acd4b92b19ded26070", "dirty": true, "generated_at": "2026-11-27T21:23:50+09:00"}`(実装を commit する前なので `dirty: true`)。

## `null` の件数と、埋めるための提案

8 つの資料(直したあと。候補 95 件):

| 候補の種類 | 件数 | `place_id` あり | `place_id` null | 座標あり | 座標 null | `site_ref` あり | `site_ref` null |
|---|---|---|---|---|---|---|---|
| 順位つき(`basis: typical`) | 82 | 82 | 0 | 52 | 30 | 0 | 82 |
| 例年の目安 | 11 | 0 | 11 | 0 | 11 | 0 | 11 |
| 町の名所 | 2 | 0 | 2 | 0 | 2 | 0 | 2 |
| 合計 | 95 | 82 | 13 | 52 | 43 | 0 | 95 |

- 座標の出どころ: `catalog` 37 件・`catalog_via_spot` 5 件・`observation_spot` 10 件(旧古河庭園・町田薬師池公園・高尾山。どれも `point.source` に出典が書かれている)。
- 順位つきで座標が `null` の 30 件の内訳: 観察の名所に `point` が無い 14 件(三溪園・久良岐公園・保土ケ谷公園・円覚寺・北の丸公園・大佛次郎記念館・山手西洋館(山手ローズウィーク)・鶴見川多目的遊水地)、野鳥の観察の名所なので写さなかった 10 件(生田緑地・県立境川遊水地公園・県立座間谷戸山公園・県立相模原公園・舞岡公園)、カタログの件に `point` が無い 6 件(あやせローズガーデン・八景島 丘の広場バラ園・土屋ざる菊園)。
- 追加の 4 問(種の質問。候補 35 件): 種の名所 34 件・例年の目安 1 件。5 つの項目はすべて `null`(`mountain_site` のある候補は出てこなかった)。
- 足した座標から出した出発地(横浜)からの直線の距離と、今までの `distance_km` の差は、座標のある候補すべてで 2km 未満だった(食い違いは見つからなかった)。

埋めるための提案(**データもコードも足していない**):

1. **観察の名所に `catalog_ref` を足す**: 三溪園(紅葉 `obs-kouyou-0002`)は、同じ名所の花のカタログの件 `hana-0021` に座標があるが、結びつきが無いので写していない。生田緑地・旧古河庭園なども同じ形。結びつきを足せば `catalog_via_spot` で埋まる。
2. **観察の名所に出典つきの `point` を足す**: 久良岐公園・保土ケ谷公園・円覚寺・北の丸公園・大佛次郎記念館・鶴見川多目的遊水地など。
3. **花のカタログの `point`**: 承認済みを含む 92 件中 17 件にしかない(あやせローズガーデンなど)。
4. **例年の目安・町の名所**: ガイドのカタログ(`data/guide/catalog.yaml`)には ID(`g-…`)はあるが座標が無い。ID はテーマ・都道府県・名前から計算した値で、名前が変わると変わるので、今回は「変わらない ID」として写さなかった(決めてほしいこと 3)。座標を入れるには、ガイドのカタログの件から名所カタログ・観察の名所の件への結びつきの項目が要る。
5. **種の名所・町の名所**: 元の行が名所カタログの件のことがあるが、`season_place` の行・`town_spots` の行に ID を運んでいない。行にカタログの id を運ぶ(コードの変更)と、座標が入る候補が増える。
6. **山の地点との結びつき**: 名前が sites.yaml の山と同じなのに結びつきのデータが無いもの(`season_place.mountain_site` の名前の合わせ方で数えた。結んでいない): 観察の名所 3 件(高尾山 `obs-kouyou-0088` → m029・御岳山 `obs-kouyou-0089` → m031・陣馬山 `obs-kouyou-0093` → m030)、名所カタログ 3 件(筑波山 `kouyou-0015` → m057・大山(大山寺) `kouyou-0020` → m027・霧ヶ峰 `hana-0037` → m043)。8 つの資料では高尾山の 1 件だけが当たった。観察の名所・カタログに `site_ref` の項目を足して本人が承認すれば、結べる。

## 答えが変わらないことの確かめ

直す前(`C:/temp/ikimono-brief-fields-20261127/before/`)と直したあと(`.../after/`)の資料を、同じ作り方(`tests/helpers.py` を読み込んで通信を禁じ、空の一時のデータ置き場で `guide_brief.build(質問, now=2026-11-27T09:00+09:00)`。Markdown は `render_md`)で作って比べた。直す前の資料は 2 回作って同じになることを先に確かめた。

| 資料 | 質問 | JSON(足した項目を除く) | Markdown | `fallback.text` |
|---|---|---|---|---|
| q1 | 今週末、高尾山で紅葉を見たい | 同じ | 同じ | 同じ |
| q2 | 今週末の紅葉の情報は? | 同じ | 同じ | 同じ |
| q3 | 丹沢で今咲いている花は? | 同じ | 同じ | 同じ |
| q4 | 八ヶ岳の見どころを教えて | 同じ | 同じ | 同じ |
| q5 | 高尾山の見どころを教えて | 同じ | 同じ | 同じ |
| q6 | 今週末、野鳥を見に行きたい | 同じ | 同じ | 同じ |
| q7 | 今週末のおすすめは? | 同じ | 同じ | 同じ |
| q8 | 神奈川と東京で紅葉の見ごろを教えて(地域を指定した質問) | 同じ | 同じ | 同じ |

- 比べ方: JSON は、直したあとの資料から `generator` と候補の 5 つの項目(と `candidate_merges` の `place_from`・`place_conflict`。8 つの資料では 0 件)を除いて、直す前と同じ形で書き出した文字列が、直す前のファイルと一字一句同じか。Markdown はファイルのバイト列で比べた。
- 追加の 4 問(「梅はどこで見られる?」「2月の週末、梅を見たい」「白鳥はどこで見られる?」「冬桜について教えて」。種の名所の候補を見るため。`before-extra/`・`after-extra/`)も、4 つとも同じだった。
- 最後のコードで作り直して比べたのが上の結果(途中の版でも同じだった)。

## 確かめられていないこと

- **実通信つきの `ask brief`** で `generator` と座標が入るか(通信しない決まりなので実行していない)。`ask brief` は `build_refreshed` → `build` を通るので同じ項目が入るはずだが、実行では確かめていない。テストの外では git を呼ぶので、`commit`・`dirty` が入るかもそのときに見る(上の `generator_info()` だけの呼び出しでは入った)。
- 種の名所に `mountain_site` がある候補の `site_ref`(テストは `_place_of` に直接渡して確かめた。空のデータ置き場の資料には出てこなかった)。
- 候補をまとめた資料(`candidate_merges` がある資料)。テストは合成の候補で確かめた。
- 今年の現況つきの候補(`basis: current`)・季節の目玉・記録の種の名所が入った資料(データ置き場が空なので出てこない)。
- 実際のデータ置き場で作った資料。
- 全テスト(CI に任せる決まり。push していないので CI は未実行)。
- 照合(`ask verify`)の合否: 12 の資料それぞれで、直す前と直したあとの資料に同じ下書きを `guide_verify.check` で照らし、結果がまったく同じことを確かめた(下書きは `fallback.text` と、候補の名前と緯度の数を書いた 1 文の 2 通り。24 通りとも同じ)。照合のテスト(`test_stage75_guide`〜`test_stage85`)も通った。実際に AI が書いた下書きでは確かめていない。

## 変えたテスト

- 既存のテストは変えていない(期待値・削除・スキップなし)。
- 足したテスト: `tests/test_brief_concierge_fields.py`(21 件。出典のない観察の名所の座標を写さないこと・承認待ちのカタログの件の座標を写すことを含む。8 つの資料のスキーマ・項目がそろうこと・作業用の項目が残らないこと・Markdown と `rules` に出ないこと・カタログの座標の写し・距離との食い違いがないこと・観察の名所の座標の順番・野鳥の観察の名所の座標を写さないこと・山の地点の `site_ref`・まとめた候補の 3 通り・`generator` の id と中身・git の読み方と失敗・テストでは git を呼ばないこと・時計)。
- 途中で落ちたテストと直し方: `test_stage75_guide.Brief.test_same_question_same_now_same_brief`(資料全体の一致)が `generated_at` の秒の違いで落ちた。期待値は変えず、テスト専用の時計のときは `generated_at` に `now` を使う形にした。`test_self_contained.test_no_path_outside_the_package` が `parent.parent` で落ちた。パッケージのフォルダから git を呼ぶ形にした。

## 利用者がやること

1. (`C:\ikimonobiyori` のウィンドウ、Git Bash)`git push -u origin feature/brief-concierge-fields` を実行し、main 向けの PR を作る。
2. (GitHub)その PR の CI が全部 pass であることを確かめてマージする。
3. (`C:\ikimonobiyori` のウィンドウ、Git Bash)`git switch main` と `git pull` を実行する。
4. (`C:\ikimonobiyori` のウィンドウ。通信が要る)`python -X utf8 -m ikimonobiyori.ask brief "今週末、高尾山で紅葉を見たい"` を実行し、1 行目に出た資料の id(`b2026…` の形)を控える。
5. (同じウィンドウ)`python -X utf8 -c "import sys; from ikimonobiyori import guide_brief as GB; d=GB.load(sys.argv[1]); print(d['generator']); [print(r['name'], r['place_id'], r['lat'], r['lon'], r['coord_source'], r['site_ref']) for r in d['candidates']]" <4 の 1 行目の id>` を実行し、`generator` に 40 桁の `commit` と `dirty: False` が入っていること、候補の行に 5 つの項目が出ることを見る。

## コンシェル側で使うときのメモ(書くだけ。決めるのはコンシェル側)

- 項目: 候補の `place_id`(名所の ID)・`lat`/`lon`(緯度・経度)・`coord_source`(座標を写した元)・`site_ref`(山の地点 `yamabiyori:mNNN`)、資料の `generator`(`name`・`version`・`commit`・`dirty`・`generated_at`)。資料の形の名前は `ikimonobiyori-guide-brief/1` のまま。スキーマは `ikimonobiyori/schemas/guide-brief.schema.json`。
- `lat`/`lon` が `null` の候補: 山・星の地点からの直線距離を計算できない。「日中」の枠に入れない、または名前・都県・市町村だけで扱う、などが考えられる。今の資料では座標があるのは順位つきの候補の一部(8 つの資料で 95 件中 52 件)だけ。
- 座標の細かさは件ごとに違う(カタログの `location_precision`: `exact`・`area_1km` = 小数 2 桁・`area_10km` = 小数 1 桁。野鳥の名所は小数 1 桁が多く、10km 程度ずれうる)。20km 以内の判定では、端の候補の扱いに注意が要る。資料には細かさの項目は無い(決めてほしいこと 4)。
- `place_id` は 1 つの名所に 1 つではない: 同じ名所でも対象ごとに別の ID がある(三溪園の紅葉 `obs-kouyou-0002` と花 `obs-hana-0001`)。同じ名所かどうかを ID だけで決めると、別の名所に見えることがある。
- `site_ref` が `null` でも、山の近くの名所でないとは限らない(高尾山の観察の名所は山 m029 と結びつきのデータが無い)。山との突き合わせは、`site_ref` があるときは ID で、無いときは座標と距離でする形が考えられる。
- `generator.commit` が `null` のとき(実行用のコピーなど)は、`version` だけで版を記録することになる。`dirty: true` のときは、その commit と手元の中身が違う。
- 資料の `id` は今までどおり質問・`now`・`prev` だけから決まり、`generator` を含まない。同じ id の資料でも `generated_at`・`commit` は作り直すたびに変わりうる。

## 決めてほしいこと

1. **`site_ref` の名前**: 提案の出力 `biyori-proposal/1` では `place.site_ref` が名所そのものの ID(`ikimonobiyori:<id>`)の意味なので、資料の `site_ref`(山の地点との結びつき)と名前が同じで意味が違う。指示書のとおりの名前にしたが、たとえば `mountain_site_ref` に変えるかどうか。
2. **野鳥の観察の名所の座標**: `data/observations/spots.yaml` の野鳥の 6 件の `bird_range` は小数 2 桁で、野鳥のプロファイルの位置の粗さ(`area_10km` = 小数 1 桁)より細かい。絶対ルール 7 に当たりうるので写さなかった(`null`)。小数 1 桁に丸めて出すかどうか(丸めるのは指示書の「丸めない」と食い違う)。
3. **ガイドのカタログの ID(`g-…`)**: 例年の目安・町の名所の候補の元の件には `g-…` の ID があり、`data/guide/catalog.yaml` にも書かれているが、テーマ・都道府県・名前から計算した値なので名前が変わると変わる。「変わらない ID」に当たらないと考えて写さなかった(`null`)。写すかどうか。
4. **座標の細かさの項目**: 座標の細かさ(カタログの `location_precision`)を候補に足すかどうか(指示書の項目に無いので足していない)。
5. **出典の書かれていない観察の名所の座標**: `spots.yaml` の 20 件(`obs-kouyou-0094`〜`0115` の一部。秩父・山中湖・富士吉田などの名所)の `point` には `source` が無く、別の名所どうしで同じ値のものがある(市町村の代表点の可能性)。名所の座標とは言えないので**写さなかった**(`null`)。8 つの資料には出てこない。出典を確かめて `source` を書けば写るようになる。写すかどうか。
6. **埋めるための提案**(上の 1〜6。データ・コードを足すかどうか)。
