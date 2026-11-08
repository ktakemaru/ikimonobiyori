# 答えの検査(自動で作る文書。手で直さない)

> この文書は `ikimonobiyori/data/ask/answer_contract.json`(答えの仕様)から `python -X utf8 -m ikimonobiyori.answer_gates doc --write` で作る。
> 仕様を直したら作り直す(`tests/test_stage63a.py` が一致を確かめる)。段階63a(2026-11-08)。

## 答えの形と流れ

質問 → `ask answer`(`ikimonobiyori/answer_run.py`)→ 記録から材料・計画・骨組み → 自動修正 → 必須の4つの検査 → 答え。
フォールバックの順: 1 polished → 2 skeleton → 3 partial → 4 minimal。どの段でも空の答えにしない。

| 状態 | 意味 |
|---|---|
| PASS | 必須の4つの検査に合格 |
| DEGRADED | 一部の候補・主張を外した、または未確認を明記した最低限の答え |
| BLOCKED | 危険な案内(安全の検査の不合格)を外して、残りを答えた |

## 必須の4つの検査(合否に使う)

### 事実の照合(`fact`)

本文の日付・数値・場所名・出典が、骨組みの事実(facts)と一致する。観察の日と情報を取った日を混同しない。使わない情報源を使わない

| 検査のID | 見ること |
|---|---|
| `unknown_url` | 文中の URL が集めた事実にある |
| `unknown_date` | 文中の日付(M/D・M月D日)が事実にある |
| `unknown_period` | 旬(N月上旬など)が事実にある |
| `unknown_number` | 数字が事実にある(小さな数と助数詞は除く) |
| `unknown_place` | 地名の辞書の語が事実にある |
| `unknown_state` | 状態の語が、その名所の記録にある |
| `state_symbol_raw` | 状態の記号のまま書かない(語にする) |
| `blocked_source` | ウェザーニュース・tenki.jp・日本気象協会などを使わない |
| `sns_source` | SNS を出典にしない |
| `phone_not_from_official` | 電話番号は取得した公式ページにあるものだけ |
| `date_range` | 状態の日付は 1 つ(範囲にしない) |
| `old_year_basis` | 古い年の記事だけをおすすめの根拠にしない |
| `restricted_source` | 山と溪谷オンライン由来の事実の決まり |
| `visitor_center_not_approved` | 承認済みで季節内の施設の発信だけ |
| `visitor_center_field_not_allowed` | 施設ごとに使わない項目(種名・開館時間)を書かない |
| `vc_legacy_line` | 施設の発信を古い1行の形(○○発信、M/D時点: 状態)で書いた(段階64 第1部) |
| `event_as_typical` | 行事・まつり・展示の期間を、例年の見頃として書いた(段階64 第2部 3) |
| `guide_eye_not_from_card` | ガイドの目は知識カードの事実のまま |
| `ended_phenology_this_year` | 観測を終えた種目に「今年の」と書かない |
| `jma_normal_source_missing` | 平年の目安に気象庁の出典と加工の行 |
| `source_missing` | 本文に出た候補の今の状態のページが出典にある |
| `knowledge_fact_not_in_card` | 知識の答えの事実はカードにある |
| `knowledge_source_missing` | 使ったカードの出典がある |
| `polish_added_fact` | 整えた文章に骨組みにない事実を足さない |
| `polish_dropped_fact` | 骨組みの現況の日付・見込み・確かさの語・出典を落とさない |
| `polish_unmapped_sentence` | 骨組みに対応しない文を足さない |
| `polish_fixed_line_changed` | 骨組みの事実の行を変えない(第4部) |
| `event_date_mismatch` | 行事の日付が台帳と一致 |
| `event_weekday_mismatch` | 行事の曜日が暦と一致 |
| `event_weekday_missing` | 行事の日付に曜日 |
| `event_date_no_year` | 行事の日付に年 |
| `event_date_missing` | 台帳の行事の日付がある |
| `event_time_mismatch` | 行事の時刻が台帳と一致 |
| `event_capacity_mismatch` | 定員が台帳と一致 |
| `event_target_mismatch` | 対象が台帳と一致 |
| `event_not_approved` | 承認済みの施設の行事だけ |
| `event_invalid_in_ledger` | 台帳の項目が正しい行事だけ |
| `event_not_in_ledger` | 台帳にない行事を書かない |
| `event_fact_not_in_ledger` | 台帳にない事実を書かない |
| `event_source_unknown` | 行事の出典が台帳の URL |
| `event_source_missing` | 行事の出典がある |

### 安全(`safety`)

危険な案内がない。立入禁止・利用制限・閉館・休園を無視していない。不確かなことを断定していない

| 検査のID | 見ること |
|---|---|
| `unsupported_peak_claim` | 「見頃です」は見頃の記録がある名所だけ |
| `old_record_as_now` | 古い記録で「いま見頃」と書かない |
| `assertive_forecast` | 見込みを言い切らない |
| `lead_too_assertive` | 冒頭の確かさを、おすすめのいちばん弱いものに合わせる |
| `stale_state_asserted` | 古い表示の残る発行元の状態は参考と書く |
| `closed_not_stated` | 休みの名所は休みを言い切る |
| `practical_other_day` | 対象の日でない日の開園時間を書かない |
| `polish_caution_word` | 比較・最上級・断定の語を足さない |
| `now_visible_unsupported` | 観察の記録があることと、今見られることを分ける(新しい現況の記録がない名所で「今見られる」と書かない) |

### 整合(`consistency`)

同じ答えの中で、日付・場所・おすすめが食い違わない(冒頭の文と「今回のおすすめ」の一致など)

| 検査のID | 見ること |
|---|---|
| `lead_mismatch` | 冒頭の文の場所・語が今回のおすすめと一致 |
| `plan_unplanned_spot` | 計画にない名所を①②③に書かない |
| `outlook_conflict` | 見込みと食い違う言い回しを書かない |
| `season_contradiction` | 記録があるのに「見つかっていません」と書かない |
| `festival_mixed_with_state` | まつりの期間と現況を同じ行に混ぜない |
| `event_past` | 終わった行事を書かない |

### 出力可能(`output`)

空でない。形が壊れていない。未確認のことを未確認と書けている。利用者に質問していない

| 検査のID | 見ること |
|---|---|
| `empty_answer` | 空の答えにしない |
| `question_in_answer` | 利用者に質問しない |
| `pick_note_missing` | 現況のない候補に「今年の状況は確認できていません」 |
| `festival_no_state_missing` | まつりだけの候補に、現況を確認できていないことを書く |
| `area_missing` | 質問のエリア・地域を全部書く |
| `inat_unlabeled` | iNaturalist に「公式ではありません」 |
| `inat_scope_missing` | iNaturalist の傾向の範囲を書く |
| `knowledge_refused` | 「答えられません」型にしない |
| `ask_back_only` | 聞き返しだけで終えない |
| `event_none` | 行事の答えに台帳の行事がある |

## 自動修正(コードが直してから、もう一度4つの検査を通す)

コードが直してから、もう一度4つの検査を通す。直せなかったものは、対応する検査の不合格になる(質問の文は出力可能、それ以外は警告)

### その文を消す(`delete_sentence`)

| 検査のID | 見ること |
|---|---|
| `internal_word` | 内部用語・作業の事情の語(台帳・承認済み・骨組みなど) |
| `internal_term` | 内部用語(英語の識別子など) |
| `dev_term` | 開発の言葉(テスト・コード・スキルなど) |
| `forbidden_phrase` | 作業の経過の文 |
| `process_phrase` | 検査・記録の事情の文 |
| `process_excuse` | 作業の事情・「ご希望なら調べます」型 |
| `work_report` | 作業の報告(読みに行った・増えた) |
| `reply_dev_term` | 返事の本文の外の作業の説明 |
| `offer_not_allowed` | 一覧にない提案の文(できないことを提案しない) |
| `official_not_tried` | 読む前に「読めていません」と書かない |
| `question_in_answer` | 利用者に質問しない |
| `reread_without_new_records` | 新しい記録がないのに「読み直しました」と書かない |
| `reread_not_from_record` | 読み直しの文は決まった文だけ |
| `knowledge_refused` | 「答えられません」型にしない |

### 出典の一覧を本文の事実から作り直す(`rebuild_sources`)

| 検査のID | 見ること |
|---|---|
| `source_unused` | 出典は本文で使った事実の出どころだけ |
| `source_missing` | 本文に出た候補の今の状態のページが出典にある |
| `sources_heading` | 出典の見出しは「出典」 |
| `knowledge_source_unused` | 知識の答えの出典は使ったカードだけ |

### 点数の低い候補から減らす(`reduce_candidates`)

| 検査のID | 見ること |
|---|---|
| `too_long` | 字数の上限(length) |

## 警告(合否に使わない。記録だけ)

合否に使わない。記録(logs/answers.jsonl)に残すだけ

| 検査のID | 見ること |
|---|---|
| `too_few_candidates` | 候補の数(計画の件数まで) |
| `no_typical_in_candidate` | 各候補に例年の見頃 |
| `no_season_birds_in_candidate` | 野鳥の候補に「この時期に見られる鳥」 |
| `birds_typical_phrase` | 野鳥に「例年の見頃」と書かない |
| `fetch_skipped` | 記録が古いのに読みに行っていない(手順の記録) |
| `practical_missing` | 実用情報があれば 1 つは書く |
| `practical_fallback_missing` | 実用情報がなければ決まった一文 |
| `typical_unknown_without_alternative` | 例年の時期が分からないときは今年の行事か前年の記録を添える |
| `plan_pick_missing` | 計画のおすすめを①②③に書く |
| `origin_km_missing` | 新しい出発地の各おすすめに距離 |
| `origin_missing` | 使った出発地を書く |
| `subject_wrong_word` | 対象別の定型文(鳥に「咲き具合」など) |
| `repeated_phrase` | 「公式ではない」の繰り返し |
| `vc_state_species_joined` | 施設の発信の状態の語の直後に括弧の種名 |
| `vc_species_without_kind` | 施設の発信の種名に区分 |
| `typo` | 項目名の誤字 |
| `knowledge_starts_with_list` | 知識の答えを一覧で始めない |
| `clarify_not_one_sentence` | 聞き返しは 1 文だけ |
| `long_quote` | 「」の中の長い原文 |
| `quote_repeated` | 長い引用は 1 か所まで |
| `too_long` | 字数の上限(length) |
| `source_unused` | 出典は本文で使った事実の出どころだけ |
| `knowledge_source_unused` | 知識の答えの出典は使ったカードだけ |
| `sources_heading` | 出典の見出しは「出典」 |

## 字数の上限

字数の上限(目安)。1 地域・1 期間・1 対象は base。対象・期間の節が増えるごとに per_segment、地域が増えるごとに per_region を足す。超えたら、点数の低い候補から減らして作り直す(合否には使わない)

- 基本: 1500 字
- 対象・期間の節が 1 つ増えるごと: +1500 字
- 地域が 1 つ増えるごと: +700 字

## 新しい検査を足すとき

4つの検査で扱えない理由と、それを捉えるテストを書いてから、先にこの仕様で分類する。分類のない ID は事実の検査として扱われる(合否に使う)。
