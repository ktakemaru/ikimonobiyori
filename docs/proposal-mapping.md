# 現地の情報の答え → `biyori-proposal/1` の対応(段階18)

イキモノビヨリが公式な現況ページを読んで作る答え(状態・日付・出典)を、契約 `biyori-proposal/1` の提案として出すときの対応と規則。
対象はこのリポジトリの出力だけ。契約の正本は biyori-hub にあり、ここでは変えない(検査用の写しは `tests/contract/`)。

## 役割

- **読むのはエージェント**(Claude Code・Codex)。公式ページを読み、読んだ事実を記録する(`IKIMONOBIYORI_DATA_DIR` の下。項目は `data/sources/policy.yaml` の `record.fields`)。コードで読むのは日光市観光協会・箱根町観光協会だけ(`sources read`。計測フックの下)。
- **提案を作るのは決まったコマンド** `python -X utf8 -m ikimonobiyori.sources proposals`。
  - 入力は、同じ日に読んだ記録・名所カタログ(承認済み)・情報源の一覧(`data/sources/<対象>.yaml`)・方針(`policy.yaml`)・プロファイル。
  - 通信しない。LLM を使わない。同じ入力・同じ記録・同じ `--now` なら、必ず同じ出力になる。
- 規則の値(日数・対応の表・文言)は `policy.yaml` の `proposals` に置き、コードに書かない。

## 使う記録

- 読んだ日が `--now` の暦日と同じ記録だけを使う(記録の再利用は同じ日のうちだけ。段階16 A-2。`answer` と同じ)。
- 誤りの印(`erroneous`)と置き換えの印(`superseded`)の付いた記録は使わない。
- 同じ情報源・同じ地点・同じ地点の書き方ごとに、いちばん後に読んだ記録を使う(`latest_by_place`)。
- 情報源の種類が現況(`status_page`)の記録だけを提案にする。まつり・交通・見頃予測だけのページは提案にしない。
- 次の記録は提案にしない。理由を警告に1行ずつ書く(同じ名所は1回だけ)。
  - 表示が昨シーズンのままの疑いがある記録。
  - 読み方によって状態が食い違う記録。
  - 公式ページに今の状態の記載がない記録。
  - 名所カタログにない地点の記録。座標がなく、契約の `place` が作れないため。地点の名前を警告にまとめて書く。
  - 公式の日付が対象の日より 30 日以上前の記録。昨シーズンの残りの恐れがあるため。

## 対応表

| 要素 | 載せる先 | 書き方 |
|---|---|---|
| 名所名・代表点・標高・地域・位置の精度・名所 ID | `place` | `name`(名所カタログの名前)、`lat`・`lon`・`elevation_m`(代表点)、`region`(都道府県)、`location_precision`(カタログとプロファイルの粗い方。粗さに合わせて座標を丸める)、`site_ref: ikimonobiyori:<名所 ID>`、`sources`(カタログの出典) |
| 対象の日 | `time_window` | 日単位(`kind: calendar_day`、その日の 00:00 〜 翌日 00:00、オフセットつき)。複数日なら日ごとに 1 件 |
| 公式の状態 → 共通の段階 | `phenology_stage` | 共通の順番(0 前・1 始まり・2 見ごろ・3 最盛・4 終わり)→ 契約の値を固定の表で対応させる(`policy.yaml` の `proposals.phenology_stage_by_order`: 0 `before_bud`、1 `early_bloom`、2・3 `peak`、4 `late`)。段階が分からない書き方は付けない。対象ごとの細かい段階(例: 紅葉の「見ごろ」と「真っ盛り」)は `details` と `evidence` に残す |
| 公式の見頃予測が対象の日にかかるか | `suitability`・`evidence` | `evidence` に原文(`official_forecast`)と、かかるか(`forecast_hits_target_date`、真偽)。かかれば `band` を `maybe` にする(下の規則) |
| 適合の度合い | `suitability` | `band` は `no` か `maybe` だけ。`go` は出さない。`score` は共通の順番の値(0〜4)そのもの。尺度 `ikimonobiyori-official-stage-order-0-4-not-probability`。**段階の進み具合の目安で、確率でも「良さ」でもない**。段階が分からないときは `null`。`go_threshold` は `null` |
| 公式の状態の原文・日付の原文・新しさ・読み方 | `evidence` と `details` の両方 | `evidence` の項目は 4 つ。<br>・`official_state`: 原文の記号・語<br>・`official_updated` / `official_observed`: 公式の日付。年のある日付は `YYYY-MM-DD`、年のない日付は `M/D`<br>・`freshness`: 新しい/やや古い/古い。参考程度/更新日不明/新しさ不明<br>・`read_by`: 読み方の日本語のラベル(決まった形で読んだ/簡易な読み取り/人が原文を確かめた。方針の `proposals.read_by_labels`)<br>`details.observations[]` にも同じ値(読み方は元の値 `code` / `summary` / `user`)と、補った年の印(`updated_year_inferred`・`observed_year_inferred`)を残す |
| 発信元・URL・公式の日付・読んだ日時 | `evidence`・`data_as_of` | `evidence[].source` は発信元、`url`(読んだページ)、`last_updated`(年のある公式の日付だけ。年のない日付は `null`)、`source_type: official_notice`。`data_as_of` は情報源ごとに 1 件(`fetched_at` = 読んだ日時) |
| 検証されていないこと・古さ・年の補い・読み方の違い | `uncertainty` | `confidence` は `value: null`・`method: official-reports`・`validated: false`。`known_limits` は方針の決まった文(`proposals.known_limits`)。次のときにだけ、その文を足す。<br>・古い<br>・年の記載なし<br>・年を補った<br>・簡易な読み取り(読み方 `summary`)<br>・段階が分からない<br>・対象の日が先 |
| 渋滞・交通規制・マナー | `care` | `manners` に、プロファイルのマナー → 名所カタログのマナー → カタログの交通の注意(`tags.traffic_note`)の順で入れる(重複なし)。`do_not_disclose_exact_location` はプロファイルの値 |
| 読めなかった情報源・参考リンク・現況の情報源がない名所 | `diagnostics.warnings` と `details` | 例年の時期の候補の名所(`weekend` の `sites`)のうち提案にならなかったものは、警告に 1 行ずつ書く(「現況なし: 名所(理由)」。同じ名所は 1 回だけ)。参考リンクは、提案のある名所なら `details.reference_links` に、ない名所なら警告に書く |

その他の項目:

- 提案の `id` は `ikimonobiyori:status:<対象>:<対象の日>:<名所 ID>`。名所カタログの地点に対する気温の推定の提案(`main.py --site-set catalog`。`ikimonobiyori:<対象>:<対象の日>:<名所 ID>`)と区別するため、2 つ目に `status` を入れる(段階18 の確認、ユーザー 2026-10-24。`docs/stage18-decisions.md` D-29)。
- `title` は「<名所名> <対象の日> <対象名>」。
- `subject` はプロファイルの `category`・`name`・`profile_id`。
- 文書は既存の出力にそろえる。
  - `agent`: id `ikimonobiyori`、`version`、`commit: null`
  - `generated_at`: `--now`
  - `status`: 提案があり、現況なしの名所もなければ `ok`、それ以外は `partial`(`status_reason` つき)
  - `diagnostics.api_calls`: 0
- **同じ名所に地点の書き方が複数ある**とき(例: 1 つの名所に「木々」と「草紅葉」の 2 行): 提案は名所・日ごとに 1 件にまとめる。`evidence` と `details.observations` に行ごとの値を入れ、`evidence[].source` に地点の書き方を添える。`band`・`phenology_stage`・`score` は、行のうち下の順で最初のものから決める: band が `maybe` → 段階が進んでいる → 新しい。

## 同じ名所の複数の項目(段階22 A-1)

同じ名所(名所カタログの id)に公式の項目(地点の書き方)が複数あるとき、対象の日ごとに主項目を 1 つ選ぶ(`sources.primary_for`。答えと共有)。
▼は主にしない → ①見頃予測がその日にかかる → ②状態の日付(現地の日付、なければ更新日)が新しい → ③状態が進んでいる(◎ > ◯ > △ > ✕)→ ④台帳の主項目(`covers[].primary`)→ 地点の書き方の文字の順。

- band・案B は主項目に対して決める。`details.observations` は主項目が先。
- 主でない項目は `details.secondary_items`(`label`・`official_state`・`stage`・`official_observed`・`official_updated`・`official_forecast`・`forecast_status`)。補助の項目がない名所には付けない。
- 主項目と補助の項目で、見頃予測の扱い(予測の内 `current` か、過ぎた `keep`/`drop` か)が食い違うときは `details.item_notes` に決まった文(方針 `answer.item_disagreement`)。答えの根拠の欄の 1 行と同じ文。

## 注意の文の型(段階21・22。ハブも同じ型を使う)

答え(`answer`)とハブが使う決まった文。値は方針 `ikimonobiyori/data/sources/policy.yaml` の `answer`(正本はそちら。ここは写しで、`tests/test_stage22.py` が一致を確かめる)。**見頃予測の部分は必ず「」で囲む。** モデルが自分で文を書かない。

- 予測の時期を過ぎたが残した名所(案B。状態が ◎・◯ のとき。`past_forecast.sentences.peak`):
  `公式の見頃予測は「{forecast}」ですが、{when}公式は「{state}」です。予測の時期は過ぎており、終わりに近い可能性が高いです。`
- 同じ(状態が △ のとき。`past_forecast.sentences.starting`):
  `公式の見頃予測は「{forecast}」ですが、{when}公式はまだ色づき始めです。予測より遅れている可能性があります。`
- `{when}` は、現地の日付があれば `{md}時点で`、更新日だけなら `公式の更新日は{md}で、`(`{md}` は「10/25」の形)。`{state}` は公式の状態の原文(「◎」など)。
- 一部の対象の日だけに当てはまるときは、先頭に日を書く(`day_prefix`: `{days}は`。`{days}` は「11/1(日)」を「・」でつないだもの)。全部の日なら日を省く。「終盤の可能性があります」も同じ。
- 主項目と補助の項目で見頃予測の扱いが食い違うとき(`item_disagreement`。`{other}`・`{main}` は地点の書き方から先頭の【…】を除いたもの):
  - 補助の項目の予測を過ぎた: `「{other}」は公式の見頃予測「{forecast}」の時期を過ぎています(この名所は「{main}」の状態で判断しました)`
  - 補助の項目の予測が対象の日にかかる: `「{other}」は公式の見頃予測「{forecast}」が対象の日にかかります(この名所は「{main}」の状態で判断しました)`
- 予測の時期を過ぎたために外した名所(▼・✕は書かない): `予測の時期を過ぎる見込みのため外しました: {names}`

## band の決め方(暫定。`docs/stage18-decisions.md` D-10・D-14)

| 条件(上から順に) | band |
|---|---|
| 対象の日が読んだ日から 14 日より先で、公式の見頃予測がその日にかかる | `maybe` |
| 対象の日が読んだ日から 14 日より先で、見頃予測がかからない(今の状態では判断しない) | `no` |
| 公式の見頃予測が**その日より前に終わっている**(段階20・21。日ごとに判定)。公式の最新の状態が「始まり」「見ごろ」「最盛」(順番 1〜3)で、その状態の日付が読んだ日から 3 日以内なら下の行に進む(`known_limits` に予測の時期が過ぎたことを書く)。それ以外(▼・✕、状態が古い、日付が分からない) | `no` |
| 公式の状態が「見ごろ」「最盛」(共通の順番 2・3)。終わりも含める指定(`--late`)なら 4 も | `maybe` |
| 公式の状態が「始まり」(共通の順番 1) | `maybe` |
| 公式の見頃予測が対象の日にかかる | `maybe` |
| 段階が分からない書き方で、新しさが「新しい」「やや古い」 | `maybe`(`known_limits` に段階が分からないことを書く) |
| それ以外(「まだ」で予測もかからない、「終わり」、段階が分からず古い など) | `no` |

- `go` は出さない。上限は `maybe`(手法を答え合わせで確かめていない。CLAUDE.md 規則 2)。
- **新しさは band を変えない**。`uncertainty.known_limits` と `evidence` に書く。
  - 読んだ日から 7 日以上、または公式の日付が 14 日以上前の記録は、「古い。参考程度」を `known_limits` に書く。
  - 公式の日付が対象の日より 30 日以上前の記録は使わない。
- 「段階が分からない書き方で新しい」を `maybe` にするのは、`answer` が同じ記録を「公式の最新の記載」としておすすめに入れることがあるため。答えの文章と提案を食い違わせないため(D-14)。

## 並び

並びは表示の都合で、価値の判断(順位づけ)ではない。順位・絞り込み・推薦は窓口が行う。

1. 対象(指定した順)
2. band(`maybe` が先)
3. 段階の進み具合(共通の順番の大きい順。段階が分からないものは後)
4. 新しさ(新しい → やや古い → 新しさ不明 → 古い → 更新日不明)
5. 名所 ID
6. 対象の日

## 答え(`answer`)との関係

- `answer`(文章の下書き)と `proposals` は、同じ記録の絞り込みとまとめ(`summarize`)、同じ「使える行」の判定を共有する。
- `answer` のおすすめに出る名所は、`proposals` で `band: maybe` の提案になる。
- `answer` の根拠に出る現況の名所は、`proposals` の提案か警告のどちらかに出る(テスト `tests/test_proposals.py`)。
