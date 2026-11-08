# 段階63a 第0部 検査の棚卸し(2026-11-08。コードは変えていない)

対象: main 16fc43d から切った `stage63` の時点のコード。行番号はこの時点のもの。
`docs/answer-checks.md` は**まだない**(段階63 第3部で作る予定だったもの。63a 第6部で、定義ファイルから自動で作る)。

## 答えを作る流れ(読んだ範囲)

| 工程 | コード | 出力 |
|---|---|---|
| 取得の対象 | `ask.py` `Flow.prepare`(→ `observations.plan`) | plan.json |
| 記録 | `Flow.record`(→ `observations.record`) | observations/*.jsonl |
| 材料 | `Flow.facts`(→ `observations.facts`・`visitor_centers.fact_rows`) | facts.json |
| 計画 | `Flow.plan`(→ `answer_plan.build` / `build_all` / `build_periods` / `build_areas`) | answer_plan.json |
| 骨組み | `skeleton.compose` | skeleton.txt |
| 整え | エージェント(書き手) | answer.txt |
| 検査 | `ask_verify.check`(facts あり)/ `generic_check`(facts なし)/ `intent.check`・`check_event`(知識・行事)/ `polish.check`(骨組みとの一致) | check.json・check_polish.json |
| 落ちたとき | `ask.minimal_answer`(骨組みを `check` に通し、落ちたら「今は答えを用意できません」)・`polish.decide`(整えなおし 1 回) | final.txt |

答え全体が止まる仕組み: `ask_verify.check` の `ok` は、**すべての**文の誤りと答え全体の誤りが 0 のときだけ真(`ask_verify.py:462`)。どの検査の 1 件でも、答え全体が不合格になる。落ちたときの逃げ道は骨組みだけで、**骨組みも同じ `check` に通す**(`ask.py:237`)。骨組みが落ちると 1 行の「今は答えを用意できません」になる(`ask.py:241`、文は `data/ask/plan.yaml:171`)。

## 分類と処置の語

- 分類: 事実 / 安全 / 整合 / 出力可能 / 品質 / 表現(63a 第0部)
- 処置: 維持 / 統合 / 警告にする / コードの自動修正にする / 生成側へ移す / 削除候補
- 「維持」「統合」は、必須の4つの検査(事実の照合・安全・整合・出力可能)のどれかに入れるもの。それ以外は合否に使わない(63a 第2部)。

## 表(facts のある答え: `ask_verify.check`)

| 検査のID | ファイル:行 | 何を見るか | 分類 | 処置 | 衝突・重複する検査 |
|---|---|---|---|---|---|
| unknown_url | ask_verify.py:197 | 文中の URL が facts にある | 事実 | 維持(事実の照合) | source_missing・source_unused と同じ URL を別の観点で見る |
| unknown_date | ask_verify.py:203,206 | 文中の日付(M/D・M月D日)が facts にある | 事実 | 維持(事実の照合) | polish_added_fact(date) と重複(骨組みは facts から作るので、骨組みにない日付 ⊂ facts にない日付ではない。未確認) |
| unknown_period | ask_verify.py:210 | 旬(N月上旬など)が facts にある | 事実 | 維持(事実の照合) | polish_added_fact(month) |
| unknown_number | ask_verify.py:222 | 数字が facts にある(小さな数+助数詞は除く) | 事実 | 維持(事実の照合) | polish_added_fact(number・km) |
| unknown_place | ask_verify.py:226 | 地名の辞書の語が facts にある | 事実 | 維持(事実の照合) | polish_added_fact(name) |
| unknown_state | ask_verify.py:233 | 状態の語が、その名所の記録にある | 事実 | 維持(事実の照合) | — |
| unsupported_peak_claim | ask_verify.py:238 | 「見頃です」などは、見頃の記録がある名所だけ | 安全(不確かな断定) | 維持(安全) | assertive_forecast・lead_too_assertive と同じ「断定」を別の語で見る |
| old_record_as_now | ask_verify.py:240 | 古い記録で「いま見頃」と書かない | 安全(不確かな断定) | 維持(安全) | stale_state_asserted |
| forbidden_phrase | ask_verify.py:186 | 作業の経過の文(R10) | 表現 | コードの自動修正(その文を削除) | internal_word・process_excuse・work_report と同じ目的 |
| internal_term | ask_verify.py:190 | 内部用語(英語の識別子など) | 表現 | コードの自動修正(統合: 内部用語の削除) | internal_word(ask_verify.py:266)・term_errors(ask_verify.py:923)と重複 |
| dev_term | ask_verify.py:193 | 開発の言葉(テスト・コード・スキル…) | 表現 | コードの自動修正(統合: 内部用語の削除) | 同上 |
| internal_word | ask_verify.py:266 | 段階62 の内部用語(台帳・承認済み・骨組み…)。出典より前の行 | 表現 | コードの自動修正(統合: 内部用語の削除) | internal_term・dev_term |
| process_excuse | ask_verify.py:338 | 作業の事情・「ご希望なら調べます」型 | 表現 | コードの自動修正(その文を削除) | forbidden_phrase・work_report |
| work_report | ask_verify.py:617 | 作業の報告(読みに行った・増えた) | 表現 | コードの自動修正(その文を削除) | 同上 |
| question_in_answer | ask_verify.py:328 | 答えの中の質問の文 | 出力可能(本人の決まり) | コードの自動修正(その文を削除)。削除のあと出力可能の検査で 0 件を確かめる | ask_back_only(generic) |
| offer_not_allowed | ask_verify.py:374 | 一覧にない提案の文 | 表現(本人の決まり: できないことを提案しない) | コードの自動修正(その文を削除) | — |
| blocked_source | ask_verify.py:278 | ウェザーニュース・tenki.jp・日本気象協会などの語・ホスト | 事実(使わない情報源) | 維持(事実の照合: 出典の適合) | regress.py:91 にも同じ |
| sns_source | ask_verify.py:285 | SNS の URL | 事実(使わない情報源) | 維持(事実の照合) | — |
| phone_not_from_official | ask_verify.py:281 | 電話番号が取得した事実にある | 事実 | 維持(事実の照合) | unknown_number と一部重複 |
| sources_heading | ask_verify.py:288 | 英語の出典の見出し | 表現 | 生成側へ移す(出典は骨組みが「出典」で作る)+ 自動修正 | — |
| too_few_candidates | ask_verify.py:413 | 地域の候補が 3 件(計画の件数まで)以上 | 品質 | 警告にする | 計画の件数で上限を切る(段階58)。計画が少なければ骨組みも少ない |
| no_typical_in_candidate / no_season_birds_in_candidate | ask_verify.py:421 | 各候補の段に例年の見頃(野鳥はこの時期の鳥) | 品質 | 生成側へ移す(骨組みが必ず書く)+ 警告 | — |
| birds_typical_phrase | ask_verify.py:423,427 | 野鳥に「例年の見頃」と書かない | 表現 | 警告にする | subject_wrong_word と同じ目的 |
| reread_without_new_records / reread_not_from_record | ask_verify.py:475,477 | 「読み直しました」は新しい記録があるときだけ・決まった文 | 表現 | 削除候補(段階51 から答えに読み直しの文を書かない。work_report が同じ文を落とす) | work_report |
| fetch_skipped | ask_verify.py:479 | 古い記録があるのに、この回は読みに行っていない | 品質(手順の検査。答えの中身ではない) | 警告にする(段階63b: 読み直しは有効期間と上限 3 ページで決める) | 段階62 の動作確認で答えを止めた(stage62-report.md:144) |
| closed_not_stated | ask_verify.py:733 | 休みの名所を書いたら、休みを言い切る文 | 安全 | 維持(安全)。骨組みは休みの行を必ず書く(skeleton.py:84-86) | — |
| typical_unknown_without_alternative | ask_verify.py:781 | 例年の時期が分からないときは今年の行事か前年の記録を添える | 品質 | 生成側へ移す(骨組みの typical_line)+ 警告 | — |
| work_report・lead 系・… は stage51_errors(ask_verify.py:605-698)の中 | | | | | |
| lead_mismatch | ask_verify.py:594,601 | 冒頭の語・名所が「今回のおすすめ」にある | 整合 | 維持(整合)。冒頭はコードがおすすめから作る(自動修正) | 段階63 の試用で 3 回続けて落ちた(冒頭の名所は書き手が足した) |
| lead_too_assertive | ask_verify.py:597 | おすすめに「可能性」があれば冒頭も断定しない | 安全(不確かな断定) | 統合(安全の断定の検査)。冒頭はコードが作る | unsupported_peak_claim |
| inat_unlabeled / inat_scope_missing | ask_verify.py:637,639 | iNaturalist に「公式ではありません」・範囲 | 安全(不確かさの表示) | 生成側へ移す(骨組み skeleton.py:62-63)+ 統合(出力可能: 未確認を未確認と書く) | — |
| source_missing | ask_verify.py:645,649 | 本文に出た候補の現況の URL が出典にある | 事実(出典) | 統合(事実の照合: 本文の事実 → 出典の対応表)。出典はコードが本文から作る | source_unused・polish_dropped_fact(source)と**衝突**(下の衝突1) |
| source_unused | ask_verify.py:673 | 出典の URL が本文の事実の出どころ | 事実(出典) | コードの自動修正(出典を本文の事実から作り直す)。合否は事実の照合で 1 回だけ | **衝突1**・**衝突3** |
| assertive_forecast | ask_verify.py:652 | 見込みを言い切らない(「見ごろに入る時期です」) | 安全(不確かな断定) | 維持(安全) | unsupported_peak_claim・lead_too_assertive・outlook_conflict |
| date_range | ask_verify.py:656 | 状態の日付を範囲にしない | 事実(観察の日の扱い) | 維持(事実の照合) | regress.py:87 |
| stale_state_asserted | ask_verify.py:661 | 古い表示の残る発行元の状態は参考と書く | 安全(不確かな断定) | 維持(安全) | old_record_as_now |
| festival_mixed_with_state | ask_verify.py:680 | まつりの期間の行に現況の語(「時点」)を混ぜない | 整合 | 統合(整合)。ただし判定の範囲を候補の段に限る | **衝突2**(お知らせの行) |
| festival_no_state_missing | ask_verify.py:683 | まつりだけの候補に「色づき状況は確認できていません」 | 出力可能(未確認を未確認と書く) | 統合(出力可能)。骨組みが必ず書く(skeleton.py:44) | — |
| practical_missing | ask_verify.py:691 | 実用情報があれば 1 つは書く | 品質 | 警告にする(骨組みは書く: skeleton.py:90-91) | — |
| practical_fallback_missing | ask_verify.py:693 | 実用情報がなければ決まった一文 | 品質 | 生成側へ移す(skeleton.py:296-297)+ 警告 | — |
| long_quote | ask_verify.py:697 | 「」の中の長い原文 | 表現(転載の決まり) | コードの自動修正(骨組みの `_no_long_quote` と同じ処理) | quote_repeated と重複 |
| quote_repeated | ask_verify.py:312 | 長い引用は 1 か所まで | 表現 | 統合(long_quote へ)・自動修正 | long_quote |
| state_symbol_raw | ask_verify.py:352 | 状態の記号のまま書かない | 事実(状態の読み方) | 生成側へ移す(骨組みは display の語を使う)+ 維持(事実の照合) | unknown_state |
| practical_other_day | ask_verify.py:358 | 対象の日でない日の開園時間 | 安全(利用の制限) | 維持(安全) | — |
| season_contradiction | ask_verify.py:362 | 記録があるのに「記録は見つかっていません」 | 整合 | 維持(整合) | — |
| restricted_source | ask_verify.py:556 | 山と溪谷オンライン由来の事実の決まり | 事実(情報源の決まり) | 維持(事実の照合)。材料の段階でも除く(二重) | observations.read_records |
| visitor_center_not_approved | ask_verify.py:491,507,541 | 承認済み・季節内でない施設の発信 | 事実(承認待ちの情報源を使わない) | 維持(事実の照合) | 3 か所で同じ判定 → 統合 |
| visitor_center_field_not_allowed | ask_verify.py:502,504 | 施設ごとに使わない項目(種名・開館時間) | 事実(情報源の決まり) | 維持(事実の照合) | — |
| vc_state_species_joined / vc_species_without_kind | ask_verify.py:531,536 | 施設の発信の文の形 | 表現 | 生成側へ移す(骨組みの決まった文)+ 警告 | 段階55 の古い形(legacy)を除外している(ask_verify.py:523) |
| plan_unplanned_spot | answer_plan.py:828 | 計画にない名所を①②③に書かない | 整合 | 維持(整合) | — |
| plan_pick_missing | answer_plan.py:831 | 計画のおすすめが①②③にある | 整合 | 警告にする(外した候補は局所化で DEGRADED。骨組みは全部書く) | — |
| outlook_conflict | answer_plan.py:806 | 見込みと食い違う言い回し | 整合 | 維持(整合) | assertive_forecast |
| origin_km_missing | answer_plan.py:838 | 新しい出発地の各おすすめに距離 | 品質 | 生成側へ移す(骨組みは distance_text を書く)+ 警告 | — |
| old_year_basis | answer_plan.py:843 | 古い年の記事だけをおすすめの根拠にしない | 事実(観察の日の扱い) | 維持(事実の照合) | — |
| pick_note_missing | answer_plan.py:850 | 現況のない候補に「今年の状況は確認できていません」 | 出力可能(未確認を未確認と書く) | 維持(出力可能) | — |
| area_missing | answer_plan.py:724 | 質問のエリアを全部書く | 出力可能 | 生成側へ移す(骨組みは候補のないエリアも 1 行書く: skeleton.py:240-241)+ 維持(出力可能) | — |
| origin_missing | ask_verify.py:452 | 使った出発地を書く | 品質 | 生成側へ移す(骨組みは origin_line を書く)+ 警告 | — |
| official_not_tried | ask_verify.py:320 | 取得を試みる前に「読めていません」 | 表現 | コードの自動修正(その文を削除) | process_excuse |
| subject_wrong_word | ask_verify.py:305 | 鳥の答えに「咲き具合」など | 表現 | 警告にする | birds_typical_phrase |
| repeated_phrase | ask_verify.py:459 | 「公式ではない」の繰り返し | 表現 | 警告にする | — |
| too_long | ask_verify.py:461 | 1,500 字 × 節の数 | 品質 | コードの自動修正(地域・期間の数で上限を広げ、超えたら点数の低い候補から減らす)。合否に使わない | **衝突4** |
| guide_eye_not_from_card | knowledge.py:185 | ガイドの目がカードの事実のまま | 事実 | 維持(事実の照合) | polish_added_fact |
| ended_phenology_this_year / jma_normal_source_missing | jma_normals.py:214,217 | 観測を終えた種目に「今年の」・出典の行 | 事実 | 維持(事実の照合)/ 出典は生成側 | — |
| reply_dev_term | ask_verify.py:850 | 返事の本文の外の作業の説明 | 表現 | コードの自動修正(統合: 内部用語の削除) | dev_term |

## 表(整えた文章と骨組みの一致: `polish.check`)

| 検査のID | ファイル:行 | 何を見るか | 分類 | 処置 | 衝突・重複する検査 |
|---|---|---|---|---|---|
| polish_added_fact | polish.py:86 | 骨組みにない日付・曜日・時刻・距離・月・年・数値・URL・名前 | 事実 | 維持(事実の照合。第4部: 構造化した骨組みの事実と照合) | unknown_* |
| polish_dropped_fact(current_date・phrase・certainty) | polish.py:91,96,100 | 現況の日付・見込みの言い回し・確かさの語が落ちた | 事実 / 安全 | 維持(事実の照合・安全) | — |
| polish_dropped_fact(source・見出し) | polish.py:104,107 | 骨組みの出典 URL が落ちた | 事実(出典) | 統合(出典はコードが本文から作り直すので、落ちたら作り直す) | **衝突3** |
| polish_unmapped_sentence | polish.py:146 | 骨組みに対応しない文 | 事実(足した事実の疑い) | 維持(事実の照合)。落ちたら骨組みを答えにする | — |
| polish_caution_word | polish.py:155 | 比較・最上級・断定の語を足した | 安全(不確かな断定) | 維持(安全) | assertive_forecast |

## 表(facts のない答え: `generic_check`・知識・行事)

| 検査のID | ファイル:行 | 何を見るか | 分類 | 処置 | 衝突・重複する検査 |
|---|---|---|---|---|---|
| forbidden_phrase / process_phrase / dev_term / internal_term | ask_verify.py:916,920,923 | term_errors(行ごと) | 表現 | コードの自動修正(統合: 内部用語の削除) | check_sentence の同名の検査と重複(実装が 2 つ。内部用語の語の比べ方も違う: 190 行は英字の境界、923 行は ASCII のときだけ境界) |
| typo | ask_verify.py:891 | 項目名の誤字 | 表現 | 警告にする | — |
| ask_back_only / too_few_candidates | ask_verify.py:899 | 聞き返しだけ・候補が少ない | 出力可能 / 品質 | ask_back_only は出力可能に統合(質問の文は削除)、件数は警告 | question_in_answer |
| clarify_not_one_sentence | ask_verify.py:886 | 聞き返しは 1 文だけ | 表現 | 削除候補(`ask answer` は聞き返さない。63a 守ること 3) | — |
| knowledge_starts_with_list | intent.py:140 | 知識の答えが一覧で始まらない | 表現 | 警告にする | — |
| knowledge_refused | intent.py:143 | 「答えられません」型 | 出力可能 | 統合(出力可能)・その文を削除 | process_excuse |
| knowledge_fact_not_in_card | intent.py:147 | カードにない事実 | 事実 | 維持(事実の照合) | — |
| knowledge_source_unused / knowledge_source_missing | intent.py:151,154 | カードの出典の対応 | 事実(出典) | 統合(出典の対応表) | source_unused・source_missing と同じ形 |
| event_*(16 種) | facility_events.py:192-269 | 行事の日付・曜日・時刻・定員・対象・台帳・承認・出典 | 事実 | 維持(事実の照合)。event_not_approved は事実(承認待ちを使わない)、event_past は整合 | — |

## 回帰の検査(regress.py。答えの合否ではなく、回帰の確認)

aim_mismatch・blocked_source・date_range・no_lead・pending_source・plan_missing・plan_out_of_region・weekday_mismatch・work_or_internal_word(regress.py:81-163)。`check` の同名の検査の写しを含む(blocked_source・date_range)。処置: 維持(回帰の確認として。答えの合否には使わない)。

## 件数の要約

答えの合否に関わる検査の ID(regress を除く)は、grep で数えて 96 種(ask_verify 61・answer_plan 7・polish 4・intent 5・knowledge 1・jma_normals 2・facility_events 16)。表では、近いもの(event_* の 16 種、reread_* の 2 種など)を 1 行にまとめ、77 行にした。

| 処置 | 件数(表の行の数) | 主な例 |
|---|---|---|
| 維持(4つの検査に入れる) | 33 | unknown_*・blocked_source・closed_not_stated・plan_unplanned_spot・polish_added_fact・event_* |
| 統合(重複をまとめて 4 つの検査に入れる) | 9 | source_missing・polish の出典・lead_too_assertive・festival_*・knowledge_source_*・ask_back_only |
| 警告にする | 9 | too_few_candidates・practical_missing・fetch_skipped・repeated_phrase・plan_pick_missing |
| コードの自動修正にする | 14 | 内部用語(5 つの実装)・作業の事情(3)・質問の文・提案の文・source_unused・too_long・long_quote |
| 生成側へ移す | 10 | 例年の見頃・iNaturalist の表示・出発地・距離・施設の発信の文・出典の見出し |
| 削除候補 | 2 | reread_*・clarify_not_one_sentence |

(1 つの行に「生成側へ移す + 警告」のように 2 つの処置があるものは、先に書いたほうで数えた。)

## 見つかった衝突(根拠つき)

**衝突1(確認済み)出典の 2 つの数え方**: 骨組みは、本文の**どこか**に名前が出た候補の現況の URL を出典に入れる(`skeleton.py:303-308`、`Material` に `seg_text` を設定しない)。検査の `source_unused` は、本文に出た候補の URL だけを「使った」と数え、対象別の節があると**その対象の節の中**に出た候補だけを数える(`ask_verify.py:663-673` が `mentioned_cands` を使い、`mentioned_cands` は `mat.seg_text` を見る: `ask_verify.py:701-704`。`seg_text` は `ask_verify.py:405` で設定)。
再現: `%LOCALAPPDATA%\ikimonobiyori\ask\20261108-105735`(「今日お出かけするならどこ?」)の skeleton.txt を `check` に通すと、`source_unused` が 2 件(`koyo.walkerplus.com/detail/ar0314e393173`、`yamanashi-kankou.jp/special/documents/koyo_1106.csv`)。前者は根岸森林公園、後者は紅葉台の現況の URL で、どちらも骨組みの「今年の情報が確認できていない候補」の行(skeleton.txt 42〜43 行)に名前だけが出ている(この欄は最後の節「野鳥」の中に入るので、紅葉の節の候補として数えられない)。行には例年の見頃しか書いておらず、現況の URL は本文の事実の出どころではない。→ 出典は「本文に出した事実 → その出どころ」の 1 つの対応表から作り、検査も同じ表を使う(63a 第2部・段階63 第1部 1)。

**衝突2(確認済み)お知らせの行とまつりの検査**: 骨組みの「行く前に確認すること」のお知らせの行は「…(11/6時点の公式のお知らせ)」の形(`official_pages.notice_lines`)。まつりの検査は、まつりのある候補が本文にあると、**どの行でも**「まつり期間中」と現況の語「時点」(`data/ask/policy.yaml:106` の festival_state_words)が同じ行にあれば落とす(`ask_verify.py:674-681`)。同じ作業フォルダで、くりはま花の国のお知らせ「コスモスまつり期間中の無料バスを11月7日から運行(11/6時点の公式のお知らせ)」が `festival_mixed_with_state` で落ちた(候補ごとに 1 回で 4 件)。骨組みが作った行を、骨組みが通る前提の検査が落とす。

**衝突3(確認済み)出典を削ると別の検査が落ちる**: 整えた文章から出典を削ると、骨組みとの一致検査が「骨組みの出典が落ちています」で落とす(`polish.py:102-105`)。削らなければ衝突1の `source_unused` が落とす。`20261108-105735` の check_polish.json は、整えなおし 6 回のあと骨組み(`use: skeleton`)になり、その骨組みも衝突1・2で落ちて「今は答えを用意できません」になった(`ask.py:241`)。`20261108-111103` では、知識カードの出典(PDF・xlsx)を整えた文章が落として `polish_dropped_fact` になった。

**衝突4(確認済み)字数の上限と、書き手の追加**: `too_long` は 1,500 字 × 節の数(`ask_verify.py:456-461`)。複数地域(`region_parts`)は節の数に入らない(節は `split_segments` の見出しだけ)。`20261108-111103`(「神奈川と東京で紅葉の見ごろ」)の整えた文章は 1,626 字で落ちた。骨組みには字数で候補を減らす処理がない(`skeleton.compose`)。骨組み自体が上限を超えるかは、この回の骨組みでは**未確認**。

**衝突5(確認済み)冒頭の文**: 冒頭の文は書き手が整えるので、名所の名前を足すと `lead_mismatch`(`ask_verify.py:598-601`)。`20261108-111103` で 4 件(箱根(芦ノ湖)・高尾山・箱根 仙石原(長安寺)・箱根(湯本))。骨組みの冒頭(`skeleton.lead_for`)は名所の名前を含まないので、骨組みでは起きない。→ 冒頭はコードがおすすめから作り、整えの対象から外す(63a 第2部・第4部)。

**衝突6(確認済み)手順の検査が答えを止める**: `fetch_skipped`(`ask_verify.py:478-479`)は、記録が古いのにこの回は読みに行っていないとき、**答えの中身に関係なく**不合格にする。段階62 の動作確認の質問で、骨組みの最小の答えも通らず「今は答えを用意できません」になった(`docs/stage62-report.md:144`「この回は読み直していない `fetch_skipped`」)。

**重複(確認済み)内部用語の 5 つの実装**: `check_sentence` の internal_term(英字の境界で比べる。ask_verify.py:188-190)・dev_term(193)・`internal_word_errors`(出典の見出しより前だけ。266)・`term_errors` の internal_term(ASCII のときだけ境界。923)・`reply_check` の reply_dev_term(850)。語の一覧も 3 つ(policy.yaml の internal_terms・dev_terms・internal_words)。同じ文が経路によって通ったり落ちたりする可能性がある(具体的な文での再現は**未確認**)。

**重複(確認済み)断定の検査**: unsupported_peak_claim・old_record_as_now・assertive_forecast・lead_too_assertive・stale_state_asserted・outlook_conflict・polish_caution_word の 7 つが、どれも「不確かなことを断定しない」を別の語の一覧で見ている。→ 安全の検査に統合。

**未確認(欠陥と断定しない)**:
- 複数地域の答え(`region_parts`)で、骨組みそのものが 1,500 字を超えるか(衝突4)。
- `plan_pick_missing` と、骨組みの `use_headings` の節の組み合わせで、おすすめが重複・欠落するか。
- 期間別の節で、`lead_vs_picks` の全体の冒頭と節の冒頭の照合(`ask_verify.py:629-631`)が、骨組みの冒頭(全体の `lead_for`)と食い違うか。
