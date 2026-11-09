# 段階74 報告書: 「遠くても」の質問の答え(2026-11-10)

本人の指示(チャット、2026-11-10)に従い、「遠くても」の質問(`answer_plan.scope_of` が `wide`)の答えを直した。

## 変更
1. **地域ごとの節に、例年の時期に入っている名所を入れる**(`answer_plan.build`)
   - 今年の情報がなく外されていた名所(理由 `no_this_year`・`no_current`)のうち、対象の日が例年の時期に入っているもの(見込み `in_peak`・`late`)を、その地域の節に足す。上限は節ごとに `scope.wide.window.section_max`(2)。
   - 節の中の並びは、今年の現況がある候補が先、例年の時期だけの名所が後。後者には「今年の情報は未確認(冬桜の例年の時期に入っています)」の箇条を先頭に付ける(花の種類は名所カタログの `flower_windows` の `kind`)。
   - 「遠くても」では、地域ごとの節に入った候補をすべて(節の順のまま、上限 `scope.wide.max_items` = 10)答えに出す。見出しは「今回のおすすめ」ではなく「地域ごとの候補」にした(今年の情報が未確認の名所も入るので、答えの決まり B「今年の情報がない候補は今回のおすすめに入れない」に合わせた)。
   - 座標のない名所は、これまで出発地の県のものしか全範囲に入らなかった(桜山公園・城峯公園が落ちていた原因)。「遠くても」のときだけ、市区町村の代表点(`data/guide/places.yaml`)で距離を測り、範囲(250km)の中か確かめる(`observations._distance(wide=True)`)。
   - 字数の上限は、地域ごとの節の数を、既存の地域ごとの上乗せ(`length.per_region`)に数える(`answer_gates.length_limit`)。これがないと、遠い地域の名所から先に削られていた。
2. **「今年の情報が確認できていない候補」の欄を地域ごとに分ける**。地域の順(`scope.wide.groups`)、地域の中は距離の点を除いた点数の順。1 地域の行の上限は `scope.wide.no_this_year_per_group`(2)。
3. **冒頭の文**: 「遠くても」では「範囲全体から選びました。」(`data/ask/origins.yaml` の `lines.wide`)。
4. **Stop フックの表示**: Claude Code の公式の文書(https://code.claude.com/docs/en/hooks の Stop decision control。2026-11-10 に読んだ)によると、`{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "..."}}` を返すと、会話は `decision: "block"` と同じように続き(同じ繰り返しの保護)、画面では「Stop hook feedback」と出てフックのエラーの表示が出ない。
   - 出力の形を `data/ask/final_check.yaml` の `stop_hook.output`(`block` / `feedback`)で選べるようにした(`stop_hook.to_output`)。
   - **既定は `block` のまま**。`feedback` にすると既存のテスト `tests/test_stage72_hook.py` の `test_hook_script_blocks_via_child_process`(子プロセスの出力が `decision: block`)の期待値が変わるため、利用者の承認待ち。

## 値(すべて provisional。出典なし、指示の形に合わせた値)
`data/ask/plan.yaml` の `scope.wide`: `window.outlooks`・`window.codes`・`window.section_max`・`window.note`・`window.note_kind`・`max_items`・`heading`・`no_this_year_per_group`。

## テスト
- 追加: `tests/test_stage74_wide.py`(12 件。受け入れの確認「遠くても構いません。今見られる花と場所を教えて」で群馬の桜山公園・埼玉の城峯公園の冬桜が出ることを含む)。
- 既存のテストの期待値は変えていない。
- 全テストを4分割で実行: 470+519+481+424 = 1894件(数えた全体 1894件)すべて OK。CI は push していないので未実行。

## 残り
- 総合(複数の対象)の計画 `build_all` には、この節の作り方を入れていない(花だけ・紅葉だけの質問が対象)。
- 例年の時期の行の「(例年の見頃(神川町、公式)から…)」は、値の区分が `secondary`(通信先が公式の一覧にない)でも「公式」と書く既存の文。今回は変えていない。
