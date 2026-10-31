# 段階30 報告(2026-10-31)

承認(ユーザー 2026-10-31): iNaturalist に許可ライセンス(CC0 / CC BY / CC BY-SA)の写真がない種に限り、Wikimedia Commons から取ってよい。新しい通信先は commons.wikimedia.org(API。読み取りだけ)と upload.wikimedia.org(画像の実体)の 2 つだけ。Wikidata は承認済みの www.wikidata.org を、種の画像の名前を調べる目的に限って使う。CC BY-NC は使わない。ブランチ stage29、別 commit。push・マージなし。

## 結果の要約
- 対応表: 23 種 → **25 種**(シロハラ・ヨシガモを、ユーザー指定の学名で追加)。
- 写真が付いた種: **25 種のうち 25 種**(iNaturalist 14・Wikimedia Commons 11)。付かなかった種はありません。
- 写真は 1 枚ずつ自分で見て確認した(下の表)。除外したのは、前回のオオバン(卵)に加え、今回の差し替えの過程で ヨシガモのピンぼけ 1 枚(下記)。

## 変更(コード)
1. **写真の差し替え**: 目で見て使わないと決めた iNaturalist の写真だけを外し、種は残して別の許可ライセンスの候補を選び直す(`guide_photos.exclude_inat_photo`。外した写真の id は手元の `photo_skip.json` に残す)。候補が尽きた種は Commons へ。
2. **Commons**(`fetch/commons_photos.py`、`guide photos-commons --live --max-requests N [--only 和名…]`): 写真のない種だけ、1 種ずつ順番に。(a) Wikidata で学名の語と学名(P225)の記述がある項目を探し、**応答の P225 が表の学名と完全一致する分類群がちょうど 1 件**のときだけ → (b) P18 のファイル名(preferred が先)→ (c) Commons の imageinfo(ライセンス・作者・ファイルのページ・サムネイル幅 500)→ (d) サムネイルを upload.wikimedia.org から取る。条件を満たさなければ写真なし。
   - ライセンスは `LicenseShortName` が CC0 / Public domain / CC BY / CC BY-SA(版つき)に完全に合うものだけ。NC・ND・GFDL・不明は使わない。`Restrictions` の注記があるもの、写真の形式でないもの(SVG など)、ファイルのページが commons.wikimedia.org でないもの、サムネイルが承認ホストでないもの、2 MB 超は使わない。作者の表記は HTML のタグを除いた文字だけ(CC BY・CC BY-SA は作者が必須。CC0・パブリックドメインは「作者の記載なし」で可)。
   - User-Agent は既存の `biyori-hub/ikimonobiyori (personal, non-commercial)`(アプリ名と用途だけ。メールアドレスなし)。
   - 取れた写真はその場で保存する(あとの通信で中止されても失わない)。
3. **ユーザー指定の学名**(`photos-build-table --named`): policy の `photos.named_scientific`(シロハラ=Turdus pallidus、ヨシガモ=Mareca falcata)を iNaturalist の taxa で学名検索し、学名が完全一致・ランク species・鳥類の候補がちょうど 1 件のときだけ表に入れる。表(`data/guide/bird_taxa.yaml`)に出どころを「ユーザー指定の学名」と書く。**行の項目ではなく、同じファイルの別の欄 `sources:`(和名 → 出どころ)に書いた**: 既存テスト `test_stage29.test_committed_table_has_facts_only` が「表の各行の項目はちょうど 4 つ(和名・学名・taxon id・確認日)」と決めており、行に `source` を足すと落ちる。既存テストの期待値は書き換えない決まりなので、この形にした。行の項目として持たせたいなら、そのテストの期待値の変更の承認が要る(下の判断事項)。**結果: 2 種とも一致して入った**(taxon id 12779・558440)。
4. **ページ**: Commons の写真は、出どころ表示に作者・ライセンス・「出どころ: Wikimedia Commons」・「ファイルのページ(Wikimedia Commons)」へのリンク(http/https のみ・`rel="noopener noreferrer"`・エスケープ)。末尾の写真提供は「iNaturalist / Wikimedia Commons」。iNaturalist の写真の表示は変えていない。CSP・data URI・JavaScript なしのまま。
5. 値は `data/guide/policy.yaml` の `photos.commons` と `photos.named_*`(コードに数値の閾値なし)。許可ホストは `config.yaml` に新しい対象 `guide_photos_commons` として足した。既存の `guide_photos`(3 ホスト)と `guide_places`(www.wikidata.org だけ)は変えていない(既存テストの期待値も変えていない)。

## 注意してほしい点
- **サムネイルのホストの置き換え**: Commons の API が返すサムネイルの URL は、今は承認外の `thumb.wikimedia.org` だった。ホストを広げず、`/wikipedia/commons/thumb/` で始まるパスだけを、**同じパスのまま upload.wikimedia.org に置き換えて**取っている(クエリは捨てる。`policy photos.commons.thumb_host_rewrite`)。置き換え後の取得はすべて 200 で、保存した形式も確認済み。この扱いに異論があれば指示してください。
- **Wikidata から HTTP 429 を 2 回**受けた(計測フックが実行を中止した)。1 回目は、候補の項目を 1 件ずつ読んでいたため。2 回目は間隔 3 秒でも 21 件目で。いずれも再試行はせず、(1) 項目の読み取りを 1 回にまとめる (2) Wikimedia 向けの間隔を 6 秒に広げる(`commons.min_interval_s`。ユーザー指示は 1 秒以上)に直し、数分置いてから再実行して完了した。再実行は新しい実行で、同じ要求を続けて送り直してはいない。
- Wikidata の検索式は `P225=値` の形が 0 件になったため、「学名の語 + `haswbstatement:P225`」の形にし、完全一致は応答の P225 で確かめている。

## 写真が付いた 25 種(目で確認済み)
| 種 | 出どころ | ライセンス | 作者(表示される表記) | 確認 |
|---|---|---|---|---|
| ヘラサギ | iNaturalist(差し替え) | CC BY | Kim, Hyun-tae | 成鳥が飛翔、全身。前回の「端で切れた 1 羽」から変更 |
| ダイサギ | **Commons(差し替え)** | CC BY-SA 2.0 | Bernard DUPONT from FRANCE | 成鳥が水辺に立つ全身。前回のヒナ 3 羽(iNaturalist の許可ライセンスの候補がそれだけ)から変更 |
| ヨシガモ | **Commons** | CC BY-SA 3.0 | Alpsdake | ヨシガモ♂の全身 |
| シロハラ | **Commons** | CC BY-SA 3.0 | Alpsdake | 全身 |
| オオバン | **Commons** | CC BY 4.0 | Alexis Lours | 全身(前回は iNaturalist の卵の写真を除外していた) |
| オオヒシクイ | **Commons** | CC0 | Hobbyfotowiki | 全身 |
| キビタキ | **Commons** | CC0 | muangpaisuetrong | ♂の全身 |
| ジョウビタキ | **Commons** | CC BY-SA 4.0 | Laitche | ♂の全身 |
| スズガモ | **Commons** | CC BY-SA 4.0 | MPF | ♂の全身 |
| ハシビロガモ | **Commons** | Public domain | U.S. Fish and Wildlife Service Headquarters(Commons の作者欄の表記) | ♂が翼を広げた全身 |
| ハマシギ | **Commons** | CC BY 2.0 | Jevgenijs Slihto from Riga, Latvia | 全身 |
| ホシハジロ | **Commons** | CC BY 2.0 | Tony Hisgett from Birmingham, UK | ♂の全身 |
| オオタカ・オオハクチョウ・オカヨシガモ・オナガガモ・カイツブリ・カワセミ・カンムリカイツブリ・キンクロハジロ・コハクチョウ・チュウヒ・ツグミ・ミコアイサ・ユリカモメ | iNaturalist | CC0 / CC BY / CC BY-SA(前回確認済み) | ページの「写真の出どころ」に表示 | 前回確認済みのまま |

目で見て外したもの: **ヨシガモの iNaturalist の写真**(CC BY。ピンぼけの飛翔で、頭が栗色に緑の帯とコガモ類に見え、ヨシガモと確かめられなかった。外したあとの iNaturalist の候補はすべて NC 系で、Commons の写真に決まった)。ダイサギ(ヒナ)とヘラサギ(端で切れた 1 羽)は前回の写真を差し替えた(上の表)。
気づいた点(残した): オオタカ(iNaturalist)は元画像に撮影者の署名文字が入っている。ヘラサギ(iNaturalist)は元画像に撮影者名・URL の文字が入っている。

## 付かなかった種
なし(25 種すべてに付いた)。

## 通信
- 合計 **75** リクエスト(うち HTTP 429 が 2 回、ほかはすべて 200)。計測フックのログ `runtime/ikimonobiyori/photos_req8〜18.log`。
- ホスト別: www.wikidata.org 40(200 が 38・429 が 2)/ commons.wikimedia.org 14 / upload.wikimedia.org 12 / api.inaturalist.org 7 / inaturalist-open-data.s3.amazonaws.com 2。許可外のホストなし。
- 内訳: ユーザー指定の学名の確認 2、iNaturalist の選び直し 7(情報 5 + 画像 2。ヨシガモは候補が尽きて画像なし)、Wikidata の検索式の試し 3・応答の形の確認 2、Commons 本番(シロハラ 4、1 回目の中止まで 12+21、完了 20)。
- 1 回の実行はどれも 60(Commons)・80(iNaturalist)以下。間隔は Commons で 3〜6 秒、iNaturalist で 1 秒以上。通信エラーの再試行はしていない。

## 画面の確認
- Playwright は入っていないため(ダウンロードになるのでこちらでは入れていない)、手元の Chrome(ヘッドレス)で `file://` を直接開いた。ローカルサーバーは起動していない。
- ページ: `C:\ikimonobiyori\runtime\ikimonobiyori\guide\pages\bird-guide.html`(約 5.6 MB。`<img>` はすべて data URI の 51 個・外部の画像 URL なし・`<script>` なし)。
- スマホ幅 390px(幅 390 の iframe で表示): はみ出しなし・カード 1 列・写真が付いた全カードの表示を確認。`C:\ikimonobiyori\runtime\ikimonobiyori\guide\pages\bird-guide-390.png`
- デスクトップ幅: `C:\ikimonobiyori\runtime\ikimonobiyori\guide\pages\bird-guide-desktop.png`
- どちらも gitignore 済みの場所。

## コミットしないもの
画像・写真の URL・撮影者名は commit しない(キャッシュは `runtime/`)。commit する表は事実だけ(和名・学名・taxon id・確認日・出どころの欄)。

## 人の判断が要る点
- サムネイルのホスト置き換え(thumb.wikimedia.org → upload.wikimedia.org。同じパス)でよいか。
- Wikimedia への間隔を 6 秒にしたままでよいか(Wikidata が 429 を返したため)。
- 出どころを表の行の項目にしたいか(そのテスト `test_committed_table_has_facts_only` の期待値を 4 項目から 5 項目に変える承認が要る)。今は別の欄 `sources:`。
- Playwright を入れてよいか。
- 写真に撮影者の署名・URL の文字が入った元画像(オオタカ・ヘラサギ)を残すか。
- 前回から残っている 127.0.0.1:8765 のローカルサーバーがあれば止めてください(今回は起動していない)。

## テスト
`python -X utf8 -m unittest discover -s tests` の最後の行: `Ran 741 tests in 206.181s` / `OK`(新しいテスト 43 件は `tests/test_stage30.py`。既存テストの期待値は変えていない)。
