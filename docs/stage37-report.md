# 段階37 の報告(指示書 `docs/stage37-H11-instructions.md` 第1部)

イキモノビヨリを、ヤマビヨリ・ホシビヨリと同じく**単体で完結する専門家**にした。生き物の手順(古ければ取りに行く → 読む → 記録 → 答えの材料 → 文章の検査)を biyori-hub から移し、記録の置き場所を利用者ごとの 1 か所にまとめた。

## できたこと
1. **手順をイキモノビヨリに移した**(2-1)
   - `ikimonobiyori/ask.py`: `python -X utf8 -m ikimonobiyori.ask prepare|inat-refresh|record|facts|verify`。ハブの `concierge_skill/ask.py` の生き物の部分(手順の順番・呼び出しの記録 `calls.json`・「読み直しました」の行 `this_round`/`fetch_line`・iNaturalist の取り直しの上限)を写した。`inat-refresh` は計測フック(`BIYORI_REQ_LOG`)と `BIYORI_ALLOW_LIVE=1` の下だけで動き、単体では `skipped: no_measure_hook` を残して古い集計を日付つきで使う(規則 6 を変えていない)。
   - `ikimonobiyori/ask_verify.py`: ハブの `concierge_skill/verify_text.py` の規則をすべて写した。語は `ikimonobiyori/data/ask/policy.yaml`。開発の言葉(`dev_terms`: テスト・コード・作業メモ・記録済み・スキル・コマンド・検査・実装 など。「フォトコンテスト」「ドレスコード」は数えない)と作業の経過の文(「あとは答えを書くだけ」「今回は取りに行っていません」など)を足した。
   - 評価表 `docs/ask-rubric.md`(ハブの `docs/concierge-rubric.md` の生き物の部分。H10 の R4 の読み方を本文に入れたまま。R10 に開発の言葉を足した)。
2. **記録の置き場所を 1 か所に**(2-2): `IKIMONOBIYORI_DATA_DIR` → なければ Windows は `%LOCALAPPDATA%\ikimonobiyori`、それ以外は `~/.local/share/ikimonobiyori`(`ikimonobiyori/paths.py`)。CLAUDE.md・AGENTS.md の絶対ルール 8 を書き換えた。テストは `tests/nonet.py` が一時フォルダを `IKIMONOBIYORI_DATA_DIR` に入れ、子プロセスにも渡す(利用者の置き場所に触れない)。
3. **移行**(`python -X utf8 -m ikimonobiyori.migrate_data --dry-run` → 実行。2026-11-01 12:2x に 1 回だけ実行)
   - 確認: 記録は 2 か所に分かれていた。単体(`C:\ikimonobiyori\runtime\ikimonobiyori`)の観察の記録は紅葉 7 件だけ、ハブ(`C:\biyori-hub\runtime-data\ikimonobiyori`)は紅葉 82・野鳥 11・花 16 件と iNaturalist のキャッシュ。単体で花菜ガーデン・くりはま花の国・ソレイユの丘・野鳥の集計が出なかったのは、記録とキャッシュがハブ側にしかなかったため(移行後は単体でも出る。受け入れテストで確認)。
   - 新しい置き場所: `C:\Users\takem\AppData\Local\ikimonobiyori`。
   - 件数: ファイル 552 件を見て 532 件をコピー(キャッシュなど)。観察の記録 116 行 → 115 行(重複としてまとめた 1 件。花)。ほかの JSON Lines(現況の記録 status_log・ガイドの記録など)1,517 行 → 1,517 行(重複 0)。元の 2 か所は消さず・書き換えていない。
4. **スキル `ikimono-weekend` を作り直した**(2-3): CLAUDE.md・AGENTS.md・SKILL.md の手順の先頭に「段階37: 単体で答える手順(最優先)」(prepare → 読む(WebFetch、なければ `web-fetch` サブエージェント)→ record → facts → 書く → verify(1 回だけ書き直し、だめなら通らない文を除く))。説明文は「生き物(紅葉・花・野鳥など)の見頃・おすすめを、単体で答える」。山・星を合わせた提案はハブのコンシェルジュの役割と書き分けた。
5. **前回からの残り**(2-4)
   1. 月のない日付「01日現在」→ 読んだ日以前でいちばん近いその日(11/1 に読んだ「31日現在」→ 10/31)。記録に `state_date_inferred: month_from_read_date`。`state_date_text`(日付の原文)も受け付ける。
   2. 重複: 同じ名所・同じ状態の語・同じ状態の日付(と同じ例年の時期・行事)は、URL や読んだ日が違っても新しい記録にしない。「最後に確かめた日時」は `observations/<対象>.confirmed.json` に持つ(記録の行は書き換えない)。日付のない記録の新しさは、最後に確かめた日で見る。
   3. 「例年の見頃」「見頃の時期」「見頃予想/予測」などの中の「見頃」を今の状態として読まない(`data/observations/policy.yaml` の `not_state_phrases`)。
   4. 紅葉の Open-Meteo の取得時刻を、応答を受け取った時刻にした(`fetch/live.py` の `received_at`。iNaturalist と同じ関数)。期待値・ゴールデンは変えず、テストに時計を渡した。
6. **受け入れテストで見つけて直したもの**: 段階36 より前に取った iNaturalist の集計(索引 `inat_index.json` がない)を、期間(前後 window_weeks 週)が対象の日を含めば使うようにした(`observations._inat_aggregation`。11/3 の質問で、11/2 を中心に取った集計を使えずに「記録は見つかっていません」になっていた)。通信はしない。

## テスト
`python -X utf8 -m unittest discover -s tests`(2026-11-01、commit b2f8d24 のコード)の最後の行: **`OK`**(`Ran 952 tests in 826.171s`)。

新しいテスト `tests/test_stage37.py`(49 件): 移した手順と検査器(ハブの H8〜H10 の生き物の部分を写した)・書き込み先の既定・移行・2-4 の 4 つ・開発の言葉・索引のない集計。

### 書き換えたテスト(この指示書で変えた挙動を固めていたものだけ)
- `tests/test_self_contained.py`: 未設定のときの既定の書き込み先(`runtime/ikimonobiyori` → 利用者ごとの 1 か所)と、パッケージの外を指してよい行の名前(`DEFAULT_DATA_DIR` → `LEGACY_DATA_DIR`)。
- `tests/test_fetch_open_meteo.py`: `test_default_cache_dir_is_runtime_not_snapshots` の既定の場所。取得の補助 `fetch` と `test_main_with_injected_http_produces_valid_proposal` に時計(`clock=lambda: NOW`)を渡す(期待値は同じ)。
- `tests/fakes.py`・`tests/test_fetch_retry.py`: 取得の補助に時計を渡す(期待値は同じ)。
- `tests/nonet.py`・`tests/helpers.py`: テストの書き込み先を一時フォルダに(期待値の変更ではない)。

## 受け入れテスト
`docs/stage37-acceptance.md`(答えの全文と採点)。

## 未確認事項・確認事項
1. **push・PR は行えていない**: この環境の権限設定で `git push` が拒否された(迂回していない)。ブランチ `stage37` はローカルにある。利用者が push と PR 作成をする必要がある(手順は最後の報告)。
2. 単体では iNaturalist の集計を取り直さない(規則 6: 計測フックの下だけ)。集計が古いときは、ハブ経由の質問で取り直すか、古い集計を日付つきで使う。単体の取り直しの仕組みを作るなら提案として相談したい。
3. 索引のない集計を期間内なら使う変更(上の 6)は、答えの材料の選び方の変更。閾値・式は変えていない。
