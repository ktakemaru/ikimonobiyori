# 指示書：イキモノビヨリを単体で完結させる（ikimonobiyori → biyori-hub。無人で PR まで）

これまでの方針（`C:\biyori-hub\docs\ikimonobiyori-rebirth-instructions.md` の2章・通信の作法、H9・H10 の決定）は**そのまま有効**。この指示書は、**役割の置き場所の誤り**を直す。

- 対象: `C:\ikimonobiyori`（主）と `C:\biyori-hub`。1つの Claude Code セッションで順に扱う。
- 利用者は操作できない。**最後まで無人で進める。** 質問・確認・承認を求めない。報告は日本語。
- 段階の番号とブランチ名は、既存の報告書と `git branch -a` を調べて**次の空き番号**を使う（以下、仮に「段階37」「段階H11」）。
- 進め方は前回と同じ（ブランチで作業、force push・`reset --hard`・`rm -rf` をしない、1回に1コマンド）。**マージはしない**。各部の最後は `git push` → `gh pr create` → `gh pr checks --watch` で CI が緑になるまで（赤なら直して push、最大3回）。
- 既存テストの期待値は変えない。ただし、この指示書で動かす・変える挙動を期待値として固めたテストだけは、新しい形に合わせて書き換えてよい（一覧を報告書に書く）。
- CLAUDE.md は、ハブのものは自分で書き換えない（必要なら `docs/stageH11-claude-md-proposal.md` に案）。ikimonobiyori の `CLAUDE.md`・`AGENTS.md` は、これまでどおり書き換えてよい（2つを同じ内容に保つ）。

---

## 1. 背景（利用者の確認、2026-11-01）

**設計（2026-10-21 の利用者の決定）**:
- yamabiyori・hoshibiyori・ikimonobiyori は、それぞれ**単体で動く専門家**。yamabiyori・hoshibiyori は単体のプラグインで、質問のたびに、キャッシュが古ければ自分で Open-Meteo を取りに行く（yamabiyori は3時間、hoshibiyori は MSM 3時間・ECMWF 6時間）。
- **biyori-hub は、情報を受け渡す基盤と、正しさ・安全の監査役。** 価値の判断（順位・絞り込み・推薦）は**コンシェルジュ**（今はハブのリポジトリの中のスキル `biyori-concierge` と `concierge_skill/`）。

**誤り**: 段階H8〜H10 で、生き物の「古ければ取りに行く → 読む → 記録 → 答えの材料 → 文章の検査」の手順を、ハブ側（`concierge_skill/ask.py`・`concierge_skill/verify_text.py`）に作った。そのため:
- ハブ経由で聞くと良い答えが出るが、`C:\ikimonobiyori` で単体で聞くと、取りに行かず、検査もされず、開発の言葉が混ざる。
- 記録が2か所に分かれている: ハブ経由は `C:\biyori-hub\runtime-data\ikimonobiyori`、単体は `C:\ikimonobiyori\runtime\ikimonobiyori`。ハブの `config.local.yaml` の `data_dir` が単体側を指している箇所もある（現況の取り込み `refresh_ikimono_status`）。

**単体の試用（2026-11-01、`C:\ikimonobiyori` で「11/3のおすすめをおしえて」。スキル `ikimono-weekend`）で見えたこと**:
- tenki.jp は読んだが、花・野鳥は「今回は取りに行っていません」「今年の現地の状態を読めたものはありません」。
- 「コードは変更していないので、テストは実行していません」「作業メモ」など、開発の言葉が答えに混ざった。
- 「01日現在」の月を読めず、状態の日付を空欄で記録した（11/1 に読んだので 11/1 と分かるはず）。
- ハブ経由では出ていた花菜ガーデン・くりはま花の国・ソレイユの丘、野鳥の iNaturalist の集計が出なかった（記録が別の場所にあるためと思われる。確かめること）。

**目的**: イキモノビヨリを、yamabiyori・hoshibiyori と同じく**単体で完結する専門家**にする。`C:\ikimonobiyori` で単体で聞いても、ハブ経由で聞いても、生き物の部分は**同じ質の答え**になること。

---

## 2. 第1部：ikimonobiyori（`C:\ikimonobiyori`、段階37）

main の最新から切る。

### 2-1. 手順をイキモノビヨリに移す

- ハブの `concierge_skill/ask.py`（手順の順番・呼び出しの記録・「読み直しました」の行の作り方・iNaturalist の取り直しの上限）と `concierge_skill/verify_text.py`（文章の検査器）が行っている**生き物の部分**を、ikimonobiyori の中に移す。例: `python -X utf8 -m ikimonobiyori.ask prepare|record|facts|verify`（名前は既存のコマンドの並びに合わせてよい）。
  - `prepare`: `observations refresh --plan`（＋野鳥の区域の集計が古ければ取り直しの対象）を出す。
  - `record`: 読んだ結果を記録する。この回に増えた記録の数をページごとに返す。
  - `facts`: 答えの材料。
  - `verify`: 文章の検査（文中の日付・状態の語・地名・数字・URL が材料にあるか、禁止の言い方・内部用語・開発の言葉がないか、候補が3件以上か、1,500字以内か、「読み直しました」とこの回の新しい記録の一致、野鳥に「例年の見頃」がないか、R4 の読み方（H10 の決定）など。ハブの検査器が今持っている規則をすべて引き継ぐ）。
  - 呼び出しの記録（`calls.json` に相当）も ikimonobiyori が書く。
- 評価表（R1〜R11、H10 の R4 の読み方を本文に書き込んだもの）を ikimonobiyori の `docs/` に移す（ハブの `docs/concierge-rubric.md` の生き物の部分）。
- ikimonobiyori の絶対ルール（ハブのモジュールを import しない、外部ライブラリは PyYAML・jsonschema・requests だけ、`ikimonobiyori/` の外を指さない）を守る。

### 2-2. 記録の置き場所を1か所にする

- 書き込み先の既定を、**リポジトリにも実行用コピーにも依存しない、利用者ごとの1か所**にする: `IKIMONOBIYORI_DATA_DIR` があればそれ、なければ Windows は `%LOCALAPPDATA%\ikimonobiyori`、それ以外は `~/.local/share/ikimonobiyori`。ikimonobiyori の CLAUDE.md・AGENTS.md の絶対ルール8を、この形に書き換える（利用者の承認済み）。
- **移行**: 既存の2か所（`C:\ikimonobiyori\runtime\ikimonobiyori` と `C:\biyori-hub\runtime-data\ikimonobiyori`）の記録（観察の記録・現況の記録 status_log・キャッシュ・区域の集計など）を、新しい置き場所へ**コピーして合わせる**。同じ事実の重複は 2-4 の規則でまとめる。**元の2か所は消さない・書き換えない**（戻せるように残す）。移行は1回だけ実行するコマンド（`python -X utf8 -m ikimonobiyori.migrate_data --dry-run` → 実行）にし、結果（件数・重複としてまとめた件数）を報告書に書く。
- テストは今までどおり一時フォルダを使い、利用者の置き場所に触れない。

### 2-3. 単体のスキル `ikimono-weekend` を作り直す

- 手順は 2-1 のコマンドだけを使う: `prepare` → 公開ページを読む → `record` → `facts` → 答えを書く → `verify`（通らなければ1回だけ書き直し、それでも通らなければ通らない文だけ除く）→ 出す。
- **公開ページの読み方**: その環境で WebFetch が直接使えればそれを、使えなければ読み取り用のサブエージェント（`web-fetch` など）を使う。サブエージェントには「状態の原文・状態の日付・例年の時期・行事の期間・URL」を書かれたとおりに返させる（H9 と同じ）。
- **対象と範囲**: 生き物（紅葉・花・野鳥・冬鳥など実装済みの対象）だけ。山・星には触れない。対象を指定しない質問（「11/3のおすすめをおしえて」）は、実装済みの対象を横断し、出発地（既定は横浜）から行ける範囲で答える。答えの冒頭で、対象の範囲（紅葉・花・野鳥）を一言で示す。
- **答えに開発の言葉を出さない**: 「テスト」「コード」「作業メモ」「記録済み」「スキル」「コマンド」などの開発・作業の言葉と、作業の経過の文（「検査が通ったので」「あとは答えを書くだけです」など）を、検査器の禁止の言い方に足す。
- スキルの説明文（description）は、「生き物（紅葉・花・野鳥など）の見頃・おすすめを、単体で答える」とする。山・星を合わせた提案は、ハブのコンシェルジュの役割と書き分ける。

### 2-4. 前回からの残り（小さな修正）

1. **月のない日付**: 「01日現在」のように月がない状態の日付は、**読んだ日以前でいちばん近いその日**として補う（11/1 に読んだ「01日現在」→ 11/1、11/1 に読んだ「31日現在」→ 10/31）。補ったことを記録に残す。テストを足す。
2. **重複の数え方**: 同じ名所・同じ状態の語・同じ状態の日付の記録は、URL や読んだ日が違っても**新しい記録に数えない**（「最後に確かめた日時」だけ更新する）。「読み直しました」「新しい記録が N件」は、本当に増えた件数で出す。
3. **状態の読み取りの歯止め**: 「例年の見頃」「見頃の時期」「見頃予想」のような、時期を表す語の中の「見頃」を、今の状態として読まない（H10 で、ウォーカープラスの「(例年の見頃のみ)」が「見頃」と読まれた）。テストを足す。
4. **紅葉の Open-Meteo の取得時刻**: iNaturalist と同じく、取得時刻を `--now` ではなく、実際に応答を受け取った時刻にする（H10 の確認事項2。利用者が承認）。期待値とゴールデンは変えず、時計を渡す形でテストを合わせる。

### 2-5. テスト（合成データ。通信しない）

1. 移した `prepare`・`record`・`facts`・`verify` が、ハブの H8〜H10 のテストと同じ挙動をする（ハブのテストの生き物の部分を写して足す）。
2. 書き込み先の既定（環境変数・Windows・それ以外）。
3. 移行: 2か所の記録が合わさり、重複がまとまり、元の2か所は変わらない。
4. 2-4 の4つ。
5. 開発の言葉・作業の経過の文が、検査器で落ちる。
6. 既存のテストがすべて通る。

全テスト OK を `docs/stage37-report.md`（空き番号）に書き、push → PR → CI が緑になるまで。PR のブランチの最後の commit の 40桁の SHA を控える。

---

## 3. 第2部：biyori-hub（`C:\biyori-hub`、段階H11）

main の最新から切る。

1. **固定の更新**: `vendor.lock`・`agents/ikimonobiyori/manifest.yaml`・`hub/core/place_names.json` の組を、第1部の PR のブランチの最後の commit（40桁）に更新する。自分で `hub/prepare_runtime.py ikimonobiyori --checkout` を実行する。
2. **ハブ側の手順を、イキモノビヨリを呼ぶだけにする**: `concierge_skill/ask.py`・`concierge_skill/verify_text.py` の生き物の部分を、ikimonobiyori の新しいコマンド（第1部）を `hub/core/ikimono_source.py` 経由で呼ぶ形に縮める。ハブ側に残すのは、呼び出しの記録・山・星の材料との組み合わせ・山・星の部分の検査だけ。コンシェルジュの答えの生き物の部分は、ikimonobiyori の `verify` に通す。
3. **書き込み先をそろえる**: `hub/core/ikimono_source.py` の書き込み先（`runtime-data/ikimonobiyori`）と、`config.local.yaml` の現況の `data_dir` を、第1部の新しい置き場所（`IKIMONOBIYORI_DATA_DIR`、既定は `%LOCALAPPDATA%\ikimonobiyori`）にそろえる。試し用の `BIYORI_IKIMONO_DATA_DIR` は残す。計測フック・宣言済みホストの仕組みは変えない。
4. スキル `biyori-concierge` の生き物の手順を、「ikimonobiyori の手順（vendor の `ikimono-weekend` スキル・`AGENTS.md`）に従う」と書き直す。山・星との組み合わせ・価値の判断はコンシェルジュに残す。
5. ハブの全テストと `hub/validate.py` が通ること。

---

## 4. 受け入れテスト（実際の通信で行う。PR を出す前に）

**単体**（`C:\ikimonobiyori` を作業フォルダとし、ikimonobiyori のスキル `ikimono-weekend` とコマンドだけを使う。ハブのモジュール・ハブのパスに触れないことを、呼び出しの記録で確かめる）:

1. 「11/3のおすすめをおしえて」（今回の試用の質問）
2. 「明日 紅葉を見に行きたい。神奈川でおすすめを教えて」
3. 「明日 野鳥を見に行くならどこ? 神奈川でおすすめを教えて」
4. 「どこか花を見に行きたい。おすすめを教えて」

**ハブ経由**（`C:\biyori-hub` のスキル `biyori-concierge`）: 上の 2 と、「11/3のおすすめをおしえて」。

合格の基準:
- 評価表 R1〜R11（H10 の R4 の読み方を本文に書き込んだもの）を、単体の4問・ハブ経由の2問のすべてが満たす。
- 単体の問1: 紅葉・花・野鳥を横断し、古い記録は読み直している（読めなければ、読みに行ったが取れなかったと書いている）。開発の言葉・作業の経過の文がない。「01日現在」のような日付が補われている。
- 単体とハブ経由の同じ質問（問2）で、生き物の候補と状態・日付が同じ（同じ置き場所の記録を使っている）。
- 「読み直しました」「新しい記録が N件」が、本当に増えた件数と一致する。

採点は、答えを書いていない別のサブエージェントに、評価表と答えだけを渡して行う。評価表の本文にない読み方を添えない。合わなければ直してやり直す（最大3回）。答えと採点を ikimonobiyori の `docs/stage37-acceptance.md` に保存し、ハブの PR からも参照する。

---

## 5. 最後の報告（日本語、短く）

ikimonobiyori の `docs/stage37-report.md` とハブの `docs/stageH11-report.md`、セッションの最後に:

1. 2つの PR の番号と CI の結果。
2. 記録が2か所に分かれていたかの確認結果と、移行の件数（合わせた件数・重複としてまとめた件数・新しい置き場所）。
3. 単体の問1（「11/3のおすすめをおしえて」）の答えの全文。
4. 書き換えたテストの一覧。
5. 利用者がやること（1ステップずつ。ウィンドウの名前と確かめ方つき）: ikimonobiyori の PR を「Create a merge commit」でマージ（ブランチは消さない）→ ハブの PR を同じくマージ → `C:\ikimonobiyori` のタブで `git checkout main` → `git pull` → `C:\biyori-hub` のタブで `git checkout main` → `git pull` → `.venv-hub\Scripts\python.exe -X utf8 hub\prepare_runtime.py ikimonobiyori --checkout` → ハブの CLAUDE.md の案があれば反映。
