# 報告書: 今年の現況を広く調べ、場所ごと・出どころごとに答える

指示書: `docs/current-status-instructions.md`(2026-11-28)。ブランチ `feature/current-status-breadth`(main `78e2604` から)。

## 第1部: 今の仕組み(実装の前に調べて書いた。コードは変えていない)

### 1. 「調べる(資料が薄い)」

- **出る条件**(`ikimonobiyori/research.py` の `needs`。`guide_brief.build` が呼ぶ):
  - 質問の種(`guide_materials.species_names`)の名所の行が `research.min_species_rows`(2)より少ない。
  - 質問に挙げた場所(`place_guard.candidates`・エリア・`research.question_places`)に、候補・知識カード・URL つきの事実が 1 つもない。
  - ほかに、仮の名所だけの市区町村(`_tentative_targets`)・聞かれた種の話のカードが 0 枚(`species_card`)。
  - 経路が `species_rows.routes_skip` のときは出さない。同じ質問で `research.once_hours`(24 時間)の中に一度調べていれば出さない(`already_researched`。代わりに `done_line`)。
  - 山の名前から足した候補は、今年の現況か例年の時期の事実を 1 つでも連れてくれば「名所がある」と数える(`_cands_for_needs`。前回の直し)。
- **出たあと AI がすること**(SKILL.md §0・`docs/guide-mode.md` §5・資料の `research.step_lines`):
  1. Web 検索で公式ページの URL を探す(要約を事実にしない)。
  2. `ask research fetch <URL> --brief <id>` で本文を読む。
  3. `ask research record --brief <id> --file <JSON>` で記録する。
  4. 資料を作り直す。
- **上限**: 1 問 3 ページ・最初の取得から 120 秒(`research.max_pages_per_question`・`max_seconds_per_question`)。同じホストへ 1 秒。robots.txt を先に読む。
- **読めるページ**: `allowed_page` が公式と判定したページだけ。紹介サイトはコードが止める。
- **記録してよい項目**(`research.fields`): 名所・都県・市町村・種・例年の時期・注意・出典。
  - `forbidden_fields` に `state`・`state_date`・`current` がある。**今年の現況は記録できない。**
  - 現況を出しているページは `current_status_page: true` を付けると、`research/pending_sources.jsonl` に承認待ちの候補として残るだけ。
- **資料への入り方**: 調べた記録は observations の記録(`research` の印つき)として、次の資料の名所・例年の目安の事実になる。

### 2. 読み直し(`auto_refresh`)

- **読むページ**(`guide_brief._refresh_targets` → `answer_plan.refresh_targets`):
  - 資料に入る候補(選ばなかった候補も)の、台帳(`data/sources/*.yaml`)で承認済みの `status_page` のうち、有効期間(`config.yaml`。現況 24 時間)が切れたもの。
  - 承認済みの施設の情報ページ(48 時間)。
  - 候補の順位の高い順に `auto_refresh.max_pages`(5)まで。合わせて `max_seconds`(25 秒)・通信 12 回まで。
- **結果ごとの決まり**(`auto_refresh.py`・資料の `auto_refresh.lines`):
  - `code_read`: 日光市観光協会・箱根町観光協会。コードが状態を読んで記録する。AI は何もしない。
  - `unchanged`: 前回の記録の原文がページに残っている。最後に確かめた時刻だけ更新する。AI は何もしない。
  - `changed`: 資料に節「読み直したページ」が出て、本文の控えの場所が示される。AI は本文で確かめた状態と日付を `ask record --batch`(施設は `ask vc-record`)で記録し、資料を作り直す。「Web を使わない」と書いてある。
  - `failed`: 「足りないもの」に「読み直せませんでした(○時点の記録のまま)」と出る。AI は古い記録のまま書く。
- **`changed` のあとに記録しなかったときに止める仕組みは無い**(照合にもフックにも無い)。

### 3. 記録(`ask record`)

- 入口: `python -X utf8 -m ikimonobiyori.ask record --out-dir <作業フォルダ> --batch <JSON>`(`observations.record`)。
- **必須**(`data/observations/policy.yaml` の `record.required`): `url`・`state`・`source_class`。`spot` か `name` のどちらか。
  - 名所の登録(`kind`+`typical`)・行事・公式の「行く前に」だけの記録は、`state` を省ける。
- `source_class` は `official`・`secondary` のどちらか(`record.source_classes`)。
- **状態と日付の持ち方**:
  - 状態は原文のまま 80 字まで(`state`)。正規化した語(`state_norm`)は読むたびにコードが付け直す。
  - 日付は `state_date`(YYYY-MM-DD)か、原文の「11/20時点」(`state_date_from_text`)。月のない「01日現在」は、読んだ日以前で補って印を付ける。
- **名所との結びつけ方**(`match_record`): 名所 id → 名前・別名の一致 → 別名辞書 → 名寄せ(当たりが 1 つのときだけ)。
- **同じ記録の判定**(`_dup_key`): 名所・状態の原文・状態の日付・例年・行事・`area`・都県・実用情報が同じなら、新しい記録にしない。
- **新しさ**(`observations.freshness`): 基準は状態の日付。状態の日付が無ければ読んだ日。
  - 紅葉・花は 2 日以内、野鳥は 7 日以内が「新しい」。14 日以内が「古い」、それより前が「かなり古い」(`freshness.fresh_days`・`stale_days`)。
  - 資料はこれと別に、対象の日より 7 日以上前の現況に「古い(○日前)」の印を付ける(`auto_refresh.stale_days`)。
  - CLAUDE.md の E(3 日・7 日)は `sources answer` の下書きの基準。資料は使っていない。
- **古い記録**: 捨てない。記録のファイルは追記だけ。使うのは下の 4 の 1 件だけ。

### 4. 資料への入り方

- 計画(`answer_run` → `observations.plan`/`facts`)が、名所ごとに記録を `assign_records` で割り当てる。`best_record` で 1 件を選び、候補の `current` にする。
  - `best_record` の選び方: 状態を持つ記録 → 状態の日付が新しい → 公式 → 読んだ時刻が新しい。
- 資料(`guide_brief._candidate_facts`)は、その 1 件を事実(`kind: current`。「名所: 状態(○/○時点、発行元)」)にする。
  - 候補の `current_state`・`basis: current`(「今年の現況あり」)・順位の点数も、計画のこの 1 件から作られる。
- **同じ名所に記録が複数あっても、資料に出るのは 1 件だけ**。ほかの発信元の記録・場所の違う記録は、資料に出ない。
- 施設の発信(`_vc_facts`)は、名所ではなく施設の事実として別に入る(例: 高尾ビジターセンターの「麓・中腹・山頂…見頃」)。

### 5. 照合(`ask verify`。`guide_verify.py`)

- **今の状態の語を止める決まり**:
  - 印のない文に、今の語(`now_words`)と状態の語(`state_words`)がある → `unmarked_now_state`。
  - 印のない文に、記録にある場所と状態の語がある → `unmarked_place_state`。
  - 印のある文の根拠が今年の現況でない → `now_state_not_current`。状態の語が事実と違う → `state_mismatch`。
  - 対象の日より前の現況を、対象の日の状態として言い切る → `stale_as_target`。
- **通る条件**: 今年の現況の事実の印と同じ文に、その事実にある状態の語で書く。または「確かめられていません」などの語(`honest_words`)を入れる。
- **手順を飛ばしたことを止める決まり**:
  - 照合(`guide_verify`)には無い。
  - Stop フックは「ask verify を通したか」「最後の文が一致するか」だけを見る。
  - 今までの形(`ask answer`)には `research_marks`(「調べる: 」など)があって検索の道具を使っていなければ止める決まりがある(`stop_hook.py`)。新しい形には無い。

### 6. 筑波山で広く調べなかった理由

資料 `b20261128-9eadc0c3`(2026-11-28 06:43、データ置き場に残っていたので読んだ)をもとにしています。

1. **「調べる」が出なかった。** 足した候補「筑波山(筑波山神社・宮脇駅周辺)」が、例年の目安の事実 F038(観光いばらき)を連れてきたため、`needs` は「名所がある」と数えた(1)。「今年の現況が無い」ことは、資料が薄いかどうかの条件に入っていない。
2. **台帳で読むのは 1 ページだけ。** 筑波山の承認済みの現況のページは観光いばらきだけで、読み直しは `changed` だった(2)。節「読み直したページ」に本文の控えが出たが、そのページには例年の時期しか無く、記録された現況は無い。記録しないまま答えても、止める決まりが無い(5)。
3. **調べる手順は今年の現況を記録できない。** `ask research record` は今年の現況を記録できない(1)。資料の手順も「Web を使わない」「今年の現況・行事の今年の日付は記録しない」と書いている。`ask record` には紹介サイトの現況を記録する入口があるが、新しい形の手順は、そこへ案内していない。
4. **記録があっても 1 件しか出ない。** 発信元ごとに記録しても、資料には名所ごとに `best_record` の 1 件しか出ない(4)。食い違いを並べる材料が資料に無い。
5. 照合は「今年の状況は確かめられていません」と書けば通る(5)。そのため、答えはその 1 文になった。

### 7. 名所の中の場所の違い

- **記録**: 「どのあたりか」の項目は無い。`area` はあるが、地域の名前(紅葉の地域の組)で、山頂・中腹の意味ではない。
- 原文の中に書かれた場所(高尾ビジターセンターの「麓・中腹・山頂・もみじ台見頃」)は、1 つの状態の原文として持つだけ。
- **カタログ**: 場所の違いは名所の名前の括弧の中にだけある(「筑波山(筑波山神社・宮脇駅周辺)」「国営昭和記念公園(日本庭園)」)。別の名所の件として持っている。同じ名所の中の区画ごとの状態を持つ項目は無い。
- 照合は、場所の違いを見ない。記録の場所の名前と状態の語が同じ文にあれば通る。
