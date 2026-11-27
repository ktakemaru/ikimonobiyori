# ビヨリコンシェルのための調べ: 資料(ask brief)の項目・山の一覧・花暦

作成 2026-11-27(段階4 の前の準備・第3部。指示書 `docs/stage4-prep-instructions.md`)。**調べて書いただけで、コードは変えていない。**
対象はイキモノビヨリ 0.2.0(main `8d9a15e` の上)。調べたのは、コード(`ikimonobiyori/guide_brief.py`・`auto_refresh.py`・`ask.py`・`wildflower.py`)・スキーマ(`ikimonobiyori/schemas/wildflower.schema.json`)と、通信を禁じた状態で作った実物の資料(3 章)。
ビヨリコンシェルの開発指示書 6.4 章(「どの項目を使えるかは、最初に実物の資料を見て `docs/ikimonobiyori-mapping.md` に書いてから実装する」)の下調べに使う。

## 1. 入口と出力

| 入口 | 標準出力 | 書き込み | 通信 |
|---|---|---|---|
| `python -X utf8 -m ikimonobiyori.ask brief "<質問>" [--now <ISO 8601>] [--prev <前の資料の id>]` | 3 行だけ: 資料の id・JSON のパス・Markdown のパス。資料の中身は JSON のファイルを読む | `IKIMONOBIYORI_DATA_DIR` の下の `briefs/<id>.json`・`<id>.md`・作業フォルダ `briefs/<id>.work/`(同じ id は上書き) | する: 候補の有効期間切れの現況のページを読み直す(1 問 5 ページ・25 秒・12 リクエストまで。`data/ask/guide_mode.yaml` の `auto_refresh`)。記録が変わったら資料をもう 1 回作る |
| `python -X utf8 -m ikimonobiyori.guide wildflower --site mNNN --month <月> --json` | JSON(スキーマ `ikimono-wildflower/1`) | しない(2026-11-27 に一時のデータ置き場で実行し、何も作られないことを確かめた) | しない(コードの説明と 2026-11-27 の実行で確かめた) |

- 資料の id は `b<YYYYMMDD>-<質問・now・prev の sha1 の先頭 8 文字>`(`guide_brief.brief_id`)。同じ質問・同じ `--now`・同じ `--prev` なら同じ id。
- 質問の文がないと終了コード 2。

## 2. 資料の項目(`schema: ikimonobiyori-guide-brief/1`)

資料の形を決める JSON Schema は、2026-11-27 に `ikimonobiyori/schemas/guide-brief.schema.json` を足した(足した項目と、いちばん上の必須の項目 `schema`・`id`・`question`・`now`・`candidates`・`facts`・`generator` だけを決める。ほかの項目は縛らない)。下の表は `guide_brief.build`・`build_refreshed`・`attach_refresh` のコードと、3 章の実物から作った。
印 ★ = コンシェルが使う見込みの項目(指示書の第3部 1 が挙げた、候補・順位・距離・今年の現況と日付・出典・知識カードに当たるもの)。候補の座標・ID・山の地点との結びつきと、資料を作った版は 2026-11-27 に足した(2.2・2.7。指示書 `docs/brief-concierge-fields-instructions.md`・報告書 `docs/brief-concierge-fields-report.md`)。確かさの段階は項目が無い(2.6)。

### 2.1 いちばん上

| 項目 | 意味 | 型 | 無いときの形 |
|---|---|---|---|
| `schema` | 資料の形の名前 `ikimonobiyori-guide-brief/1` | 文字列 | いつもある |
| ★ `generator` | 資料を作った版(2.7。2026-11-27 に足した) | オブジェクト | いつもある |
| `id` | 資料の id | 文字列 | いつもある |
| `question` | 質問の文(種の別名はカタカナの名前に直したもの) | 文字列 | いつもある |
| `asked`・`species_renamed` | 直す前の質問の文と、直した名前の組 | 文字列・配列 | 直していなければ項目ごと無い |
| `now` | 資料の基準の時刻(`--now`。省くと時計)。ISO 8601・オフセットつき | 文字列 | いつもある |
| `previous` | 続けて聞く質問のときの前の資料 `{id, question}` | オブジェクト | `null` |
| `dates` | `today`・`this_weekend`・`next_weekend`・`periods`(対象の期間)・`defaulted_date` | オブジェクト | いつもある |
| `intent`・`route` | 質問の意図と答えの経路の名前(例 `plan`) | 文字列 | `null` のことがある |
| `scope` | 範囲の決め方(`region`・`areas`・`no_origin`・`default` など) | 文字列 | いつもある |
| `region`・`areas` | 質問の地域・エリアの名前 | 文字列・配列 | `null`・空の配列 |
| `subjects` | 対象(例 `autumn_leaves`) | 配列 | 空の配列のことがある |
| ★ `origin`・`origin_source` | 出発地と、その決め方(`default` は既定の横浜) | 文字列 | — |
| `asked_mountain` | 聞かれた山の名所(2026-11-28)。`{site_ref, name, candidates: [{name, outlook, facts}]}`。`site_ref` は質問に挙げた山(`data/sites.yaml` の名前か括弧の前の部分)の `yamabiyori:mNNN`、`name` は `sites.yaml` の名前のまま。`candidates` は、その山の名所で資料の候補にあるもの(足した候補と、もとから候補にあったもの)の候補の `name`・`outlook` と、その候補の事実(`facts` の `place` が候補の名前のもの)の `id`。新しい値は作らず、候補と事実に今ある値を指すだけ。入るのは、山の名前から候補を足した(`added_by: mountain_name`)資料だけ。資料の Markdown では、候補の一覧より前に「聞かれた山の名所」の節になる(候補の行・事実の行をそのまま並べる) | オブジェクト | `null`(山の名前の入らない質問・足した候補が無い質問。高尾山のようにもとから候補にあって足さなかった山も `null`。`mountain_named_candidates` の `enabled: false` でも `null`) |
| ★ `candidates` | 候補(2.2) | 配列 | 空の配列 |
| `candidates_note` | 候補の選び方の 1 文(例「横浜からの距離で選びました。」) | 文字列 | `null` |
| `candidate_merges`・`candidate_merge_conflicts` | 同じ場所の候補をまとめた記録と、まとめられなかった食い違い | 配列 | 空の配列 |
| ★ `facts` | 確かめた事実(2.3) | 配列 | 空の配列(このとき `missing` に「確かめた事実がない(…)」) |
| `seasonal_obs` | 例年この時期の観察記録の集計(2.5) | 配列 | 空の配列 |
| ★ `cards` | 知識カード(2.4) | 配列 | 空の配列(このとき `missing` に「この質問に結びつく知識カードがない」) |
| `narrative` | 語りの材料 `{items: [{kind, card, title, place, text}], missing: [足りない種類]}` | オブジェクト | `items` が空の配列 |
| `missing` | 足りないものの文(「今年の現況がない候補: ○○」「調べる: …」など) | 文字列の配列 | 空の配列 |
| `research` | その場で調べる対象 `{targets: [{what, where, why, kind}]}` | オブジェクト | `targets` が空の配列 |
| `refresh_pages` | 読み直しの対象のページ `{name, subject, url, publisher, source_class, kind, reason, current_date, last_read, covers}` | 配列 | 空の配列 |
| `auto_refresh` | 読み直しの結果 `{pages: [{url, name, subject, result, detail, …}], elapsed_s, requests, refused}`。`result` は `code_read`・`unchanged`・`changed`・`failed`・`skipped` | オブジェクト | 読み直しの対象が無いとき・設定で切ったときは**項目ごと無い** |
| `photos` | 写真の候補 | 配列 | 項目ごと無いことがある |
| `rules` | 答えを書くときの決まりの文(`data/ask/guide_mode.yaml` の `rules`。今は 9 行) | 文字列の配列 | いつもある |
| `fallback` | 今までの形の答え `{text, stage, status}` | オブジェクト | `text` が空の文字列のことがある |

### 2.2 候補(`candidates` の 1 件)

| 項目 | 意味 | 型 | 無いときの形 |
|---|---|---|---|
| `subject` | 対象 | 文字列 | `null`(種の名所・町の候補など) |
| ★ `rank` | 対象ごとの順位(1 始まり) | 数 | `null`(例年の目安・町から足した候補など) |
| ★ `name` | 名所の名前 | 文字列 | いつもある |
| `chosen` | 今までの形の答えで選んだか | 真偽 | — |
| `aim` | 狙い(例 `near`) | 文字列 | `null` |
| ★ `distance_km`・`distance_estimated`・`distance_text` | 出発地からの直線の距離・推定かどうか・その文(「直線で約34km」) | 数・真偽・文字列 | `null`・`false`・項目ごと無い |
| `score`・`breakdown` | 順位の点数と内訳(イキモノビヨリの中の点数。ほかのビヨリと比べない) | 数・オブジェクト | `null` |
| `outlook`・`phrase` | 見込みの語(「見頃中の見込み」)と文 | 文字列 | `null` |
| ★ `current_state`・`current_date` | 今年の現況の語と日付 | 文字列 | `null`(今年の現況がない) |
| `prefecture`・`city` | 都県・市区町村 | 文字列 | `null` |
| `basis` | 候補の根拠(`current`・`typical`・`species`・`town` など) | 文字列 | 項目ごと無いことがある |
| `group` | 地域の組(例「東京・神奈川」) | 文字列 | `null` |
| `not_chosen_reason`・`reasons` | 選ばなかった理由・選んだ理由の語 | 文字列・配列 | `null`・空の配列 |
| `seasonal_obs_ids` | その地域の観察記録の id(公式の現況がない候補だけ) | 配列 | 項目ごと無い |
| `theme` | 種・テーマの語(種の名所・山の見どころの候補など) | 文字列 | 項目ごと無い |

2026-11-27 に足した項目(どの候補にも 6 つともある。`coord_precision` は同じ日の 2 回目の作業で足した。元のデータに無ければ `null`。資料の Markdown と `rules` には出さない):

| 項目 | 意味 | 型 | 入るとき |
|---|---|---|---|
| ★ `place_id` | 名所の ID。名所カタログの件は `ikimonobiyori:<カタログの id>`(例 `ikimonobiyori:kouyou-0024`)、観察の名所の件は `ikimonobiyori:<観察の名所の id>`(例 `ikimonobiyori:obs-kouyou-0088`) | 文字列 | 順位つきの候補(今までの形の答えの計画の行の `id` から)。例年の目安・町の名所・種の名所・季節の目玉は `null` |
| ★ `lat`・`lon` | 緯度・経度。元のデータの値のまま(カタログは各件の `location_precision` の桁で入っている)。野鳥の観察の名所だけは、野鳥のプロファイルの位置の粗さに丸めた値 | 数 | 名所カタログの `point`(承認待ちの件も、順位に使われていれば写す)、観察の名所の `catalog_ref` が指すカタログの `point`、観察の名所の `point`(`point.source` に出典が書かれたものだけ)の順。野鳥の観察の名所(`catalog_ref` が無いもの)は、出典の書かれた `point` か `bird_range` を、プロファイルの `care.location_precision`(野鳥は `area_10km` = 小数 1 桁)に丸めて出す(利用者の決定 2026-11-27。丸め方は提案の出力と同じ `proposals.coarse_precision`・`engine.round_coord`。丸める前の値は資料に入れない。絶対ルール 7) |
| `coord_source` | 座標を写した元: `catalog`・`catalog_via_spot`・`observation_spot`・`observation_spot_coarsened`(野鳥の観察の名所の座標を丸めたもの) | 文字列 | 座標があるとき |
| `coord_precision` | 座標の細かさ: 名所カタログ(`catalog`・`catalog_via_spot`)は、その件の `location_precision` の値のまま(`exact`・`area_1km`・`area_10km`)。`observation_spot_coarsened` は丸めた粗さ(野鳥は `area_10km`) | 文字列 | 座標があり、細かさが元のデータに書かれているとき。観察の名所の `point`(`observation_spot`)には細かさが書かれていないので、推測せず `null`。座標が `null` なら `null` |
| ★ `mountain_site_ref` | 山の地点との結びつき `yamabiyori:mNNN`(sites.yaml の `site_ref` の値。2026-11-27 に `site_ref` から名前を変えた) | 文字列 | カタログの件の `site_ref`(`yamabiyori:` で始まるもの)、観察の名所の `mountain_site_ref`(資料の候補を作るときだけ読む項目。2026-11-27 に足した)、種の名所の `mountain_site`(段階84 第1部 A)の順。観察の名所の `catalog_ref` が指すカタログの件の `site_ref` は借りない。観察の名所の値は sites.yaml にある山だけ使う。今データに結びつきがあるのは 7 件(下の表)。名前が山と同じでも、データに結びつきが無ければ `null` |

- 同じ名所でも対象ごとに別の ID がある(三溪園: 紅葉 `obs-kouyou-0002`・花 `obs-hana-0001`)。候補の ID は、候補を作った計画の行の ID。
- 提案の出力 `biyori-proposal/1` の `place.site_ref` は名所そのものの ID(`ikimonobiyori:<id>`)で、資料の `place_id` に当たる。資料の山の地点との結びつきは、それと区別するため `mountain_site_ref` という名前にした(資料の候補に `site_ref` という項目は無い)。提案の `place.lat`・`lon` は位置の粗さで丸めた値なので、資料の座標と違うことがある。
- 候補をまとめたとき(`candidate_merges`): まとめた記録の 1 件に、項目を写した元の候補の名前 `place_from` を入れる。元の候補の `place_id`(または `mountain_site_ref`)が食い違えば、候補の 6 つの項目を `null` にし、`place_conflict`(`members`・`reason`)を残す。
- 出発地からの距離(`distance_km`)は今までのまま(足した座標から計算し直さない)。8 つの資料では、足した座標から出した直線の距離との差はどれも 2km 未満だった(野鳥の丸めた座標は、丸めの分だけずれうる。15 の資料で最大 3km(舞岡公園))。

2026-11-27(2 回目。指示書 `docs/brief-concierge-fields-2-instructions.md`)に足したデータ(座標の値は足していない。リポジトリの中の件どうしを結んだだけ):

| 件 | 項目 | 値 | 確かめ |
|---|---|---|---|
| 観察の名所 三溪園(紅葉)`obs-kouyou-0002` | `catalog_ref` | `hana-0021`(花のカタログの三溪園) | 名前・都県・市区町村が同じ。対象が違うので、紅葉の候補の作り方(`observations.all_candidates` は同じ対象のカタログしか見ない)は変わらない |
| 観察の名所 高尾山 `obs-kouyou-0088` | `mountain_site_ref`(新しい項目) | `yamabiyori:m029` | 名前が同じ。名所の `point` は m029 の座標を写したもの |
| 観察の名所 御岳山 `obs-kouyou-0089` | `mountain_site_ref` | `yamabiyori:m031` | 同上(m031) |
| 観察の名所 陣馬山 `obs-kouyou-0093` | `mountain_site_ref` | `yamabiyori:m030` | 名前が同じ。名所に座標が無いので距離は確かめていない |
| 名所カタログ 筑波山 `kouyou-0015` | `site_ref`(今ある項目) | `yamabiyori:m057` | 名前(括弧の前)が同じ。座標の距離 約1.3km |
| 名所カタログ 大山(大山寺) `kouyou-0020` | `site_ref` | `yamabiyori:m027` | 名前(括弧の前)が同じ。座標の距離 約1.6km |
| 名所カタログ 霧ヶ峰 `hana-0037` | `site_ref` | `yamabiyori:m043` | 名前(括弧の前)が同じ。件に座標が無いので距離は確かめていない |
| 観察の名所 大山寺・大山阿夫利神社下社 `obs-kouyou-0019` | `mountain_site_ref` | `yamabiyori:m027` | 2026-11-28 に利用者の決定で足した(`docs/mountain-named-2-report.md` 第 1 部)。`catalog_ref` 先の `kouyou-0020` の `site_ref` と同じ山。名所に座標が無いので距離は確かめていない |

- 観察の名所の `mountain_site_ref` は、資料の候補を作るとき(`guide_brief._place_of`)だけ読む。名所カタログの `site_ref` は、提案の出力 `biyori-proposal/1` の `details.catalog_site_ref` にも写る(`proposals.py`。今までからある動き)。
- sites.yaml の山には都県の項目が無いので、都県は突き合わせていない。

2026-11-28(指示書 `docs/mountain-named-instructions.md`。報告は `docs/mountain-named-report.md`)に足した候補の印。山の名前を挙げた質問で、その山と結びついた名所を候補に入れる:

| 項目 | 意味 | 型 | 入るとき |
|---|---|---|---|
| `added_by` | 候補を入れた道。値は `mountain_name`(質問に挙げた山の名前から入れた) | 文字列 | 山の名前から入れた候補だけ。ほかの候補には項目ごと無い。`data/ask/guide_mode.yaml` の `mountain_named_candidates` で項目の名前・値を決め、`enabled: false` で切れる |

- 入る条件:
  - 質問の中の場所の語が、`data/sites.yaml` の山の名前(全体か括弧の前の部分。例「筑波山(女体山)」の「筑波山」)と同じ。「○○から」「○○発」の形は除く。
  - 対象を紅葉・花などに絞った質問。「○○の見どころ」のように対象が既定の 3 つのままの質問には入れない。
  - その山と結びついた名所(上の表の結びつき。観察の名所が `catalog_ref` で借りるカタログの件の `site_ref` も数える)が、質問の対象と合う。
  - まだ候補に無い(id か名前が同じ件があれば入れない。高尾山の紅葉は今までの道で入っているので、足さない)。
- 入る形:
  - 今までの形の答えの計画の順位にあれば、その行のまま末尾に足す(`rank` は 12 位より下の順位のまま、`basis` は `typical`/`current`、見込みも計画のまま)。
  - 計画の順位を作らない経路(見どころなど)では、市区町村の名所の行と同じ形で足す(`basis: town`・`rank: null`、例年の時期は名所カタログの窓)。
  - 今ある候補は外さず、順番も変えない。
- `mountain_site_ref` は今までの決まりのまま。大山寺・大山阿夫利神社下社(`obs-kouyou-0019`)は、大山の名前から入るが、観察の名所に `mountain_site_ref` が無く、`catalog_ref` 先の `site_ref` は借りないので `null`。

足す前の調べ(座標・`site_ref` が無いことの確かめ。2026-11-27・通信なし。3 章と同じ作り方): 「今週末、高尾山で紅葉を見たい」「今週末の紅葉の情報は?」「丹沢で今咲いている花は?」「八ヶ岳の見どころを教えて」「高尾山の見どころを教えて」の 5 つの資料で、すべての候補・事実・`fields` の項目の名前を合わせて数え、JSON 全体で `mNNN`・`yamabiyori`・`site_ref`・`"site"`・`"point"`・`"lat"`・`"lon"` を探した。どれも 0 件。`README.md`・`CHANGELOG.md`・`docs/guide-mode.md` にも、資料の候補に座標や山の地点が入るとは書かれていない(`docs/guide-mode.md` は「座標は記録しない(市町村まで)」)。データ置き場が空の状態で作ったので、実際のデータ置き場で作った資料では確かめていない。

#### コンシェル側で使うときのメモ(2026-11-27。書くだけ。決めるのはコンシェル側)

- 項目: 候補の `place_id`(名所の ID)・`lat`/`lon`(緯度・経度)・`coord_source`(座標を写した元)・`coord_precision`(座標の細かさ)・`mountain_site_ref`(山の地点 `yamabiyori:mNNN`)、資料の `generator`(`name`・`version`・`commit`・`dirty`・`generated_at`)。資料の形の名前は `ikimonobiyori-guide-brief/1` のまま。スキーマは `ikimonobiyori/schemas/guide-brief.schema.json`。資料の候補に `site_ref` という項目は無い(2026-11-27 に `mountain_site_ref` に変えた。提案の出力 `biyori-proposal/1` の `place.site_ref` は名所そのものの ID で、資料では `place_id` に当たる)。
- `lat`/`lon` が `null` の候補: 山・星の地点からの直線距離を計算できない。「日中」の枠に入れない、または名前・都県・市町村だけで扱う、などが考えられる。座標があるのは順位つきの候補の一部だけ(8 つの資料で 95 件中 65 件)。
- `coord_precision` で座標の細かさが分かる: `exact`(名所の位置)・`area_1km`(小数 2 桁。1km 程度ずれうる)・`area_10km`(小数 1 桁。5〜7km 程度ずれうる)。`null` は、座標はあるが細かさが元のデータに書かれていないもの(観察の名所の `point`。`coord_source: observation_spot`)。20km 以内などの判定では、`area_10km` の候補は端の扱いに注意が要る。
- `coord_source: observation_spot_coarsened` は野鳥の観察の名所の座標を、野鳥のプロファイルの位置の粗さ(`area_10km`)に丸めたもの。実際の場所から数 km ずれる。丸める前の値は資料に無い。地図にピンを立てる用途には向かない。
- `place_id` は 1 つの名所に 1 つではない: 同じ名所でも対象ごとに別の ID がある(三溪園の紅葉 `obs-kouyou-0002` と花 `obs-hana-0001`)。同じ名所かどうかを ID だけで決めると、別の名所に見えることがある。
- `mountain_site_ref` が入るのは、データに結びつきがある 6 か所(高尾山・御岳山・陣馬山・筑波山・大山・霧ヶ峰)と、種の名所の `mountain_site` だけ。大山のカタログの件 `kouyou-0020` は観察の名所 大山寺・大山阿夫利神社下社(`obs-kouyou-0019`)に借りられていて候補に出てこないので、今は大山の結びつきは資料に出ない。`null` でも山の近くの名所でないとは限らない。山との突き合わせは、`mountain_site_ref` があるときは ID で、無いときは座標と距離でする形が考えられる。
- `generator.commit` が `null` のとき(実行用のコピーなど)は、`version` だけで版を記録することになる。`dirty: true` のときは、その commit と手元の中身が違う。
- 資料の `id` は今までどおり質問・`now`・`prev` だけから決まり、`generator` を含まない。同じ id の資料でも `generated_at`・`commit` は作り直すたびに変わりうる。

### 2.3 確かめた事実(`facts` の 1 件)

| 項目 | 意味 | 型 | 無いときの形 |
|---|---|---|---|
| `id` | `F001` から | 文字列 | — |
| ★ `kind`・`kind_label` | `current`(今年の現況)・`typical`(例年の目安)・`event`(行事)・`facility`(施設)・`safety`(安全・規制)・`other`(その他の記録) | 文字列 | — |
| `place` | 場所の名前 | 文字列 | `null` |
| ★ `content` | 事実の文 | 文字列 | — |
| `values` | 文から取り出した日付・年・月・旬・時刻・料金・電話・URL・状態の語・人数(答えの照合に使う) | オブジェクト | 各項目が空の配列 |
| ★ `source`・`url` | 出典の名前と URL | 文字列 | `null` |
| ★ `source_class` | `official`(公式)・`secondary`(紹介サイトなど) | 文字列 | `null` のことがある |
| ★ `observed` | 現地の状態の日付(今年の現況のとき) | 文字列 | `null` |
| `read_at` | 読んだ時刻 | 文字列 | `null` |
| `fields` | 状態の語の原文・年など | オブジェクト | 項目ごと無い |

### 2.4 知識カード(`cards` の 1 件。`guide_brief._card_row`)

`id`・`title`・`category`・`place`・`link`・`narrative`・`where`・`facts`(文の配列)・`months`・`confidence`・★ `source`・★ `url`・`checked_on`・`source_class`・`values`。
小話・季節の暦のカードも同じ形で、`link` で区別する。3 章の例は知識カードが空のデータ置き場で作ったので、実物のカードは載せていない。

### 2.5 観察記録(`seasonal_obs` の 1 件)

`id`(`O001` から)・`kind`(`seasonal_obs`)・`kind_label`・`category`・`region`・`content`・`species`・`flowering`・`values`・`source`・`source_class`(`null`)・`url` ほか。iNaturalist の過去の記録を地域・週・分類ごとに数えたもの(位置は地域の名前だけ)。

### 2.6 確かさの段階

**「確かさの段階」の項目は無い。** README の「確かさの 3 段」(公式で確認・例年の目安・一般的な知識)は、資料の中では次の組み合わせで表れる: 事実の `kind`(`current` か `typical` か)と `source_class`(`official` か `secondary` か)、カードの `confidence`。段を決める対応の関数はイキモノビヨリ側に無い(答えの照合 `ask verify` は文の中身で確かめる)。

### 2.7 資料の版が分かる項目

- `schema`(`ikimonobiyori-guide-brief/1`)・`now`(基準の時刻。`--now` を渡せばその値で、作った時刻とは限らない)。
- `generator`(2026-11-27 に足した。資料の id の計算には入れない):

| 項目 | 中身 |
|---|---|
| `generator.name` | `ikimonobiyori` |
| `generator.version` | 版(`ikimonobiyori/__init__.py` の `__version__`。今は 0.2.0) |
| `generator.commit` | パッケージのあるリポジトリの commit(40 桁)。git が無い・読めない・パッケージがリポジトリの直下にない(実行用のコピーなど)ときは `null` |
| `generator.dirty` | 追跡中のファイルに未 commit の変更があるか(`git status --porcelain --untracked-files=no`)。分からなければ `null` |
| `generator.generated_at` | 実際に作った時刻(パソコンの時計。オフセットつき)。`now` とは別 |

- 同じ質問・同じ `now` なら、`generator.generated_at`(と `commit`・`dirty`)のほかは同じ資料。テスト(`BIYORI_UNDER_TEST=1`)では git を呼ばず `commit`・`dirty` は `null`、テスト専用の時計のときの `generated_at` は `now`。

## 3. 実物の例(通信なし)

**2026-11-27 の注**: 下の例は、項目を足す前の資料。今の資料には、いちばん上の `schema` の次に `generator` があり、候補の各件の末尾に 6 つの項目がある。同じ作り方で今の資料を作ると、下の 1 件目の候補の末尾は `"place_id": "ikimonobiyori:kouyou-0024", "lat": 35.711, "lon": 139.398, "coord_source": "catalog", "coord_precision": "exact", "mountain_site_ref": null`、`generator` は `{"name": "ikimonobiyori", "version": "0.2.0", "commit": null, "dirty": null, "generated_at": "2026-11-27T09:00:00+09:00"}`(テストの仕組みの下なので `commit`・`dirty` は `null`、`generated_at` は `now`)。

作り方(2026-11-27): `tests/helpers.py` を読み込んで(ソケット禁止・`BIYORI_UNDER_TEST=1`・一時のデータ置き場)、`guide_brief.build("今週末、高尾山で紅葉を見たい", now=2026-11-27T09:00+09:00)` を呼んだ。呼んだスクリプトは作業用の一時フォルダに置き、リポジトリには入れていない。
データ置き場が空なので、使ったのはリポジトリにあるデータ(名所カタログ・例年の目安など)だけで、今年の現況・知識カード・観察記録は入っていない。`build` を直接呼んだので `auto_refresh` の項目は無い(`ask brief` は `build_refreshed` を呼び、読み直しの対象があれば足す)。長い配列と文は「…」で縮め、空の配列が並ぶ `values` は 1 行にした。

```json
{
 "schema": "ikimonobiyori-guide-brief/1",
 "id": "b20261127-7d1fe484",
 "question": "今週末、高尾山で紅葉を見たい",
 "now": "2026-11-27T09:00:00+09:00",
 "previous": null,
 "dates": {"today": "2026-11-27", "this_weekend": ["2026-11-28", "2026-11-29"], "next_weekend": ["2026-12-05", "2026-12-06"],
           "periods": [["2026-11-28", "2026-11-29"]], "defaulted_date": false},
 "intent": "plan",
 "route": "plan",
 "scope": "no_origin",
 "region": null,
 "areas": [],
 "subjects": ["autumn_leaves"],
 "origin": "横浜",
 "origin_source": "default",
 "candidates": [
  {"subject": "autumn_leaves", "rank": 2, "name": "国営昭和記念公園(日本庭園)", "chosen": true, "aim": "near",
   "distance_km": 34, "distance_estimated": false, "score": 57.8,
   "breakdown": {"outlook": 40, "freshness": 0, "distance": 5.8, "festival": 6, "lightup": 6, "practical": 0, "source": 0},
   "outlook": "見頃中の見込み", "phrase": "例年の見頃の時期にあたります", "current_state": null, "current_date": null,
   "prefecture": "東京都", "not_chosen_reason": null, "reasons": [], "city": null, "basis": "typical", "group": "東京・神奈川",
   "distance_text": "直線で約34km"},
  "…(ほか 1 件)"
 ],
 "candidates_note": null,
 "candidate_merges": [],
 "candidate_merge_conflicts": [],
 "facts": [
  {"id": "F001", "kind": "typical", "kind_label": "例年の目安", "place": "国営昭和記念公園(日本庭園)",
   "content": "国営昭和記念公園(日本庭園): 例年 公式: モミジ類 10月下旬〜12月上旬(日本庭園など)",
   "values": {"dates": [], "years": [], "months": ["10", "12"], "jun": ["10月下旬", "12月上旬"], "times": [], "money": [], "phones": [], "urls": [], "states": [], "people": []},
   "source": "国営昭和記念公園", "source_class": "official", "url": "https://www.showakinen-koen.jp/flower-information/",
   "observed": null, "read_at": null, "fields": {"year": null}},
  "…(ほか 16 件)"
 ],
 "seasonal_obs": [],
 "cards": [],
 "narrative": {"items": [], "missing": ["なぜ今", "どこをどう見る", "見分け方", "次の季節"]},
 "missing": [
  "今年の現況がない候補: 国営昭和記念公園(日本庭園)",
  "今年の現況がない候補: 高尾山",
  "今年の情報が確認できていない候補: 久良岐公園、保土ケ谷公園",
  "今年の現況の記録がある候補がない",
  "この質問に結びつく知識カードがない"
 ],
 "research": {"targets": []},
 "refresh_pages": [
  {"name": "国営昭和記念公園(日本庭園)", "subject": "autumn_leaves", "url": "https://www.showakinen-koen.jp/flower-information/",
   "publisher": "国営昭和記念公園 花・植物", "source_class": "official", "kind": "status", "reason": "no_current",
   "current_date": null, "last_read": null, "covers": 1}
 ],
 "rules": ["…(9 行。答えの決まりの文)"],
 "fallback": {"text": "…(今までの形の答えの文)", "stage": 2, "status": "PASS"}
}
```

## 4. 山の座標の一覧(I2)

- `docs/sites-mountains-20261127.csv`: `ikimonobiyori/data/sites.yaml` の 76 座すべて(列: `id`・`name`・`lat`・`lon`・`elevation_m`・`kind`・`site_ref`。文字コード UTF-8)。値は sites.yaml のまま。
- sites.yaml の `copied_from`: ヤマビヨリ `mountain_weather_core.py`(MOUNTAINS)の commit `de66f1083b21cdf7c9054e6b27c6877c2e1723f4` から、2026-10-14 に 1 回だけ写したもの。以後は独立して管理している。
- **ヤマビヨリの側は読んでいないので、比べていない**(指示書のとおり)。コンシェル側で、棚の `yamabiyori/mountains.json` と ID で突き合わせて比べる。

## 5. 花暦(`guide wildflower`)

### 5.1 出力の形(スキーマ `ikimono-wildflower/1`)

項目: `schema`・`site {id, name, elevation_m}`・`area`・`month`・`status`・`flowers`・`upcoming`・`season_note`・`caveats`・`text`・`conclusion`(`conclusion` はスキーマの必須ではないが出る)。

| `status` | いつ | 形 |
|---|---|---|
| `ok` | 花暦がある山域(または、一部の地点だけ花暦がある山域のその地点)で、その月の花がある | `flowers` に花(名前・花期・見分けの語・保護の要否・確からしさ・出典など)、`upcoming` に翌月の花。`caveats` にマナー・ヤマビヨリの案内、保護種があれば山域までにしている旨、一部の地点だけならその旨 |
| `no_data` | 花暦はあるが、その月の花の記録が無い | `flowers` は空。`text` は「この月に例年見られる花の記録は、まだありません。…」 |
| `preparing` | 山がどの山域にも結ばれていない、または山域の花暦が準備中 | `flowers`・`upcoming` は空。`area` は山域の名前か「（山域の花ごよみは準備中）」。`text`・`conclusion` は「データ準備中です（この山域の花ごよみは、まだ集めていません）。」。`caveats` はヤマビヨリの案内だけ |

- sites.yaml に無い ID(例 `m999`)は、標準エラーに「地点 m999 は data/sites.yaml にありません」と出し、終了コード 2。
- 確かめた実行(2026-11-27・通信なし): `m029` 5 月 → `ok`(16 種)、`m029` 1 月 → `no_data`、`m003` 7 月 → `ok`(1 種・一部の地点だけの注意つき)、`m001`・`m002` 7 月 → `preparing`。

### 5.2 花暦がある山(22 座。2026-11-27 の `data/guide/wildflower_areas.yaml` から `wildflower.area_of_site` で引いた)

| 山域(状態) | 山 |
|---|---|
| 丹沢(ready) | m022 塔ノ岳・m023 丹沢山・m024 蛭ヶ岳・m025 檜洞丸・m026 鍋割山・m027 大山(伊勢原) |
| 奥多摩(ready) | m028 雲取山・m031 御岳山・m032 棒ノ折山(棒ノ嶺)・m058 大菩薩嶺 |
| 高尾(ready) | m029 高尾山・m030 陣馬山 |
| 霧ヶ峰(ready) | m043 霧ヶ峰(車山) |
| 尾瀬(ready) | m076 会津駒ヶ岳 |
| 八ヶ岳(準備中・一部の地点だけ) | m003 横岳・m004 硫黄岳 |
| 富士山周辺(準備中・一部の地点だけ) | m012 富士山(剣ヶ峰) |
| 北アルプス(準備中・一部の地点だけ) | m036 燕岳・m041 乗鞍岳(剣ヶ峰)・m065 立山(雄山)・m066 白馬岳 |
| 南アルプス(準備中・一部の地点だけ) | m046 北岳 |

- 山域が準備中で、その山には花暦が無い(`preparing`): 八ヶ岳 m002・m005〜m007、富士山周辺 m013〜m020、北アルプス m037〜m040、南アルプス m045・m047。
- どの山域にも結ばれていない(`preparing`): m001(谷川岳)・m008〜m011・m021・m033〜m035・m042・m044・m048〜m057・m059〜m064・m067〜m075(36 座)。
- 箱根の山域(ready)は、sites.yaml のどの山にも結ばれていない(`--area 箱根` で引く)。
- コンシェルの段階 4 の受け入れ条件の例との対応: 丹沢・高尾は花暦がある。谷川岳(m001)は `preparing`。尾瀬の山域は ready で、結ばれている山は m076 会津駒ヶ岳だけ。

## 6. コンシェルから呼ばれるときに困りそうな点(直していない)

1. ~~候補に座標と山の地点との結びつき(今の `mountain_site_ref`)が無い~~ → 2026-11-27 に足した(2.2)。ただし座標があるのは順位つきの候補の一部だけ(8 つの資料で 95 件中 65 件。2 回目の作業のあと)で、`mountain_site_ref` は結びつきのデータがある名所と種の名所の一部だけ。`null` の候補は、名前・都県・市区町村・出発地からの距離しか使えない。
2. ~~資料に commit・版・作った時刻が無い~~ → 2026-11-27 に `generator` を足した(2.7)。
3. **`ask brief` は通信する**(読み直し。1 問 25 秒まで。記録が変われば資料をもう 1 回作る)。読み直しを切る引数は無い。通信を禁じたとき(`BIYORI_UNDER_TEST=1` など)は読み直さず、`auto_refresh.refused` に理由を入れ、そのページを「読み直せませんでした」として `missing` に足す(`auto_refresh.run`・`attach_refresh` のコードから。実行では確かめていない)。時間は今の版では未計測(前の版の値は `docs/wait-notice-timings.md` に参考として置いた)。
4. **`ask brief` の標準出力は JSON ではない**(id とパスの 3 行)。コンシェルは 2 行目のパスの JSON を読むことになる。
5. **書き込み先**: 資料は `IKIMONOBIYORI_DATA_DIR`(未設定なら Windows は `%LOCALAPPDATA%\ikimonobiyori`)の `briefs/` に溜まる。古い資料を消す仕組みがあるかは確かめていない。コンシェルが別の `IKIMONOBIYORI_DATA_DIR` を渡すと、単体で使っている記録(現況・知識カード・観察記録)が見えなくなる。
6. **同じ質問・同じ `--now` は同じ id で上書き**される。読み直しで記録が変わると、同じ id でも中身が変わる(コンシェルの受け入れ条件の「イキモノビヨリの現況の読み直しで変わる部分は除く」に当たる)。
7. **出発地の既定は横浜**で、決まりの文(`rules`)にも「範囲は横浜から片道250km前後」とある。コンシェルの出発地が違うときの扱い(質問の文に出発地を入れたときなど)は確かめていない。
8. **`fallback.text` は今までの形の仕上げた文**。コンシェルの 6.4 章は仕上げた文をつながない形なので、使わない側に当たる。
9. ~~資料の JSON Schema が無い~~ → 2026-11-27 に足した(足した項目といちばん上の必須の項目だけ。ほかの項目の変化は見つけられない)。
10. 花暦は通信しない・書き込まない・約 1 秒。困る点は見つけていない。
