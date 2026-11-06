# 運用手順書（イキモノビヨリ）

対象: 毎回の運用を自分で行う管理者。1ステップずつ、確認の方法つきで書く。作業の場所は `C:\ikimonobiyori`（リポジトリ）、GitHub は `ktakemaru/ikimonobiyori`。

## 1. 指示書の渡し方と、終わったあとの手順

### 1-1. 指示書を渡す
1. 指示書を `C:\ikimonobiyori\docs\` に保存する。ファイル名の例: `stage55-xxxx-instructions.md`（文字コードは UTF-8）。
2. **確認**: エクスプローラーで `C:\ikimonobiyori\docs\` を開き、ファイルがあることを見る。ターミナルなら `ls docs` で名前が出る。
3. 作業用の Claude Code のウィンドウを開く。**作業フォルダが `C:\ikimonobiyori` のウィンドウ**を選ぶ（ウィンドウの上か下に出るフォルダ名で確認する。別のフォルダのウィンドウに頼むと、指示書が見つからない）。
4. **確認**: そのウィンドウで `git status` を頼むか、自分で `git status` を実行し、`On branch main`・`nothing to commit` と出ること（他の変更が混ざっていたら、先に片づける）。`git pull` で最新にしておく。
5. 依頼の文面（そのまま貼る。番号は指示書に合わせる）:
   `docs\stageNN-xxxx-instructions.md を読んで、特に「0-2. 無人実行の方針」を守り、第1部から第N部まで、最初から最後まで、質問せずに自分で判断して実行してください。docs\stageNN-progress.md がすでにあれば、それを読んで、未完了の部から続けてください。`
6. 途中で止まったとき（利用上限・時間切れ）は、**同じ依頼文をもう一度**貼る。進捗ファイル（`docs\stageNN-progress.md`）を読んで、済みの部を飛ばして続ける。

### 1-2. 終わったあとの手順（push、PR、CI、マージ）
Claude Code は commit までを行う。push・PR・マージは自分で行う（権限で拒否される。回避しない）。

1. 報告書 `docs\stageNN-report.md` を開き、先頭の「push は未実施」の行を確認する。「完了」「未完了」「判断したこと」を読む。
2. ターミナル（PowerShell か Git Bash）で `cd C:\ikimonobiyori`、`git branch --show-current` を実行し、`stageNN` と出ることを確認する。
3. `git push -u origin stageNN` を実行する。**確認**: 最後に `branch 'stageNN' set up to track ...` と出る。
4. ブラウザで GitHub の `ktakemaru/ikimonobiyori` を開き、黄色いバナー「Compare & pull request」を押す（なければ「Pull requests」→「New pull request」で base `main`、compare `stageNN`）。タイトルは「段階NN: …」、説明に報告書の要点を貼る。「Create pull request」を押す。
5. PR のページの下にある **Checks（CI）**を見る。全部が緑のチェックになるまで待つ（数分〜10分）。赤い×があれば、§4-2 に従う。**CI の全項目が pass であることがマージの条件**。
6. 緑になったら「Merge pull request」→「Confirm merge」。**確認**: PR の表示が紫の「Merged」になる。
7. 手元を最新にする: `git checkout main`、`git pull`。**確認**: `git log --oneline -3` に「Merge pull request #NN」が出る。

## 2. 台帳の承認の手順

承認待ち（pending）の情報源は、承認するまで答えの材料にならない。承認は自分が行う（Claude Code は承認しない）。

### 2-1. 承認の前に確認すること
1. 利用規約・ポリシーのページを**自分で読む**（台帳の項目 `terms.url`）。自動取得・転載・二次利用の禁止の有無を見る。
2. `robots.txt` で拒否されていないか（台帳の `readable.robots`）。
3. 出どころの区分（公式／紹介サイト）が合っているか（主催者・運営者自身の発信だけが「公式」）。
4. ウェザーニュース・tenki.jp 由来でないこと（§3）。
5. 山と溪谷オンライン（yamakei-online.com）のページは、承認しても「状態の短い語句（30字以内）・日付・URL」だけが使われる（§3）。

### 2-2. 承認する
1. 該当のファイルを開く。紅葉の紹介サイト・ビジターセンターは `ikimonobiyori\data\sources\secondary\autumn_leaves.yaml`、公式は `ikimonobiyori\data\sources\autumn_leaves.yaml`（花は `flowers.yaml`、野鳥は `birds.yaml`、冬鳥は `wintering_birds.yaml`）。
2. 対象の項目（`id:` で探す。例 `yamakei-takao-visitor-center`）の `approval:` の行を、`{status: approved, reason: "承認(YYYY-MM-DD)。利用規約を読んだ"}` に書き換える。
3. **山と溪谷オンライン由来の記録を使うときだけ**、もう1か所: `ikimonobiyori\data\observations\policy.yaml` の `restricted_sources:` の `approved: false` を `approved: true` にする。
4. **確認**: `python -X utf8 -m unittest discover -s tests -p "test_sources.py"` の最後の行が `OK`。
5. commit（Claude Code に頼むか、自分で `git add`・`git commit`）、push、PR、CI、マージ（§1-2）。

## 3. 規則の一覧（決定の日付つき）
| 規則 | 決定 |
|---|---|
| ウェザーニュース（ウェザーニューズ）由来の予想は、転載を含めて使わない・読まない（weathernews.jp、n-kishou.com、ウォーカープラス等に載った転載の予想） | 2026-11-06 |
| tenki.jp は読まない（利用規約が自動取得を禁じる） | 2026-11-05 |
| 山と溪谷オンライン由来は、状態の短い語句（30字以内）・日付・URL だけ。文章は保存・転載・要約・言い換えしない。安全情報（日没・通行止め・一方通行など）は書かず、URL への案内だけ。承認まで答えの材料にしない。記録はリポジトリの外（`%LOCALAPPDATA%\ikimonobiyori`）にだけ置く | 2026-11-06（段階54） |
| 日付と曜日が今年の暦と合わないものは、前年以前のものとして使わない（曜日チェック） | 2026-11-06（段階53） |
| まつり・イベントの期間は「主催者が設定した期間」として、現況（色づき状況）とは別の行に書く。期間は色づきを保証しない | 2026-11-06（段階53） |
| 公式かどうかは確度ラベルで示す。答えを止める理由にしない。主催者・運営者自身の発信だけを「公式」とする | 2026-11-01（段階34） |
| 古いデータでも答える。日付つきで、断定せずに | 2026-11-01（段階34） |
| 写真の取得は確認なしで行ってよい（上限・間隔は方針のまま）。花・野草の写真は開花を優先し、学名と状態を表示する | 2026-11-03 / 2026-11-06 |
| 答えに作業の事情・内部用語を出さない。検査（`ask verify`）を通ってから出す | 2026-11-03（段階39） |
| 手元で全テストを走らせない（CI に任せる）。関係するテストだけ実行する | 2026-11-04（段階46） |
| push・PR・マージは自分が行う | 段階34 以降 |

## 4. 失敗したときの対処

### 4-1. 取得が失敗したとき
1. 失敗の種類を見る: HTTP 403・自動アクセス拒否 → そのページは読まない（回避しない）。「人が開く URL」として答えに添える。HTTP 503・タイムアウト → 時間をおいて**1回だけ**やり直す。
2. 同じ相手先で10回続けて失敗したら、その作業を中断する（相手先への負荷を避ける）。
3. 内容のないごく短い応答（148バイトなど）は、読めた扱いにしない。別の読み方（同じ公式サイトの別ページ）で1回だけ再取得する。
4. 直らなければ、台帳の `readable.note` に「【要確認(日付): 理由】」を書いておく（削除・承認の変更はしない）。

### 4-2. CI が赤のとき
1. PR の Checks で赤い項目をクリックし、ログの最後の `FAILED` の行と、その上の `Traceback` を見る。
2. 自分の変更が原因か判断する。**既存テストの期待値を書き換えない・ゴールデンを作り直して合わせない**（落ちたのは挙動が変わった合図）。
3. Claude Code のウィンドウ（`C:\ikimonobiyori`）に、ログの該当部分を貼って「この失敗を直してください（テストの期待値は変えない）」と頼む。
4. 手元で関係するテストだけ: `python -X utf8 -m unittest discover -s tests -p "test_stageNN.py"`。最後の行が `OK`。
5. commit → push（同じブランチ。PR が自動で更新される）→ CI がもう一度回る。

### 4-3. 答えが崩れたとき（作業の事情が出る、冒頭とおすすめが食い違う、出典がない、など）
1. まず回帰テストを実行: `python -X utf8 -m ikimonobiyori.regress`。最後の行 `N/N 件が期待どおり` を見る（約5秒）。外れた質問の ID が出る。
2. 外れなければ、崩れた答えを `regress` の cases.yaml（`ikimonobiyori\data\regress\cases.yaml`）に「既知の崩れ」として足す依頼を Claude Code にする。
3. 答えの検査: `python -X utf8 -m ikimonobiyori.ask verify --out-dir <作業フォルダ> --text <答えのファイル>`。指摘のコードを見る。
4. 最近の変更を `git log --oneline -10` で確認し、原因の部を特定する。
5. 条件を緩めて合わせない。コード側を直す。

## 5. 季節ごとの確認（チェックリスト）
- **11月上旬（毎年）**: 東京都公園協会の紅葉情報（https://www.tokyo-park.or.jp/special/kouyou/index.html）が新しい年の版に変わったか。「最終情報更新日」が今年の日付になっていれば、台帳の「要確認」の印を外す依頼をする。（2026年は11/10ごろ開始の見込み。2026-11-06 時点では令和7年版の最終版のまま。）
- **10月〜12月**: 各地のまつりの期間（紅葉まつり・菊花展・ライトアップ）。年つき・曜日つきで確認できたものだけを `data\observations\festivals.yaml` に足す。前年のページが残っていないか（曜日チェックが見つける）。
- **11月〜3月**: 冬鳥（白鳥・ガンカモ）の飛来。新潟（阿賀野市）・長野（安曇野）・群馬（館林）の飛来数のページが今季の更新になっているか（2026-11-06 時点で館林は3月のまま。要確認）。
- **12月〜2月**: 冬の花（水仙・ロウバイ・梅・河津桜）のイベントの日付（多くは年が明けてから公開）。台帳に冬の花の情報源を足す準備。
- **2月〜4月**: 桜・梅・春の花に向けて、名所の一覧・台帳・写真の事前取得（`guide photos-prefetch --theme 花 --all`）の準備。
- **毎月**: 台帳の健全性点検（段階54 第10部の方法。URL が読めるか、前シーズンのままでないか）。結果は `docs\source-health-YYYY-MM.md`。
