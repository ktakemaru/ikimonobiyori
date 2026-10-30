# 段階29b 報告(2026-10-31)

承認(ユーザー 2026-10-31): 承認A の範囲のまま(api.inaturalist.org の読み取りと、承認済みの 2 画像ホスト)。CC BY-NC 系は使わない。新しい通信先なし。ブランチ stage29、別 commit。push・マージなし。

## 結果の要約
- 対応表: 15 種 → **23 種**(「候補が 2 件」の 8 種を採用)。
- 写真が付いた種: **23 種のうち 15 種**。もとの 15 種に限ると **9 種**(前回は 1 種)。
- 通信: 計 **51** リクエスト(応答の形を見る試し 4・表づくり 10・写真 37。内訳は下)。すべて許可ホスト・全部 200。1 回の実行は 80 以下、間隔 1 秒以上。

## 変更(コード)
1. 写真: 既定の写真 → taxon_photos の順に見て、CC0 / CC BY / CC BY-SA の最初の 1 枚。学名・ホスト・形式・大きさの確認は従来どおり。
2. 「候補が 2 件以上」: 和名に完全一致する候補のうち、species が **ちょうど 1 件**で、ほかが応答の `ancestor_ids` でその種の下位と確かめられるときだけ採用。species が 2 件以上、または下位と確かめられないときは入れない。
3. 日本語名: 応答の日本語の名前(`all_names=true` の `names` の locale ja)のうち完全一致するものも使う。「カモ」「シギ」「チドリ」は `policy.yaml photos.skip_names` で対象外(問い合わせない)。
4. ページ: 「いま狙いたい鳥」は対応表にある種だけカード。ない語は「そのほか: …」の 1 行(文字だけ)。
5. 目での確認の除外: `guide_photos.exclude_photo`(キャッシュを消し、理由を `guide/export/photo_review.json` に残す。`photos-fetch` は取り直さない)。`photos-build-table --recheck` を追加(条件を変えたとき、前に入らなかった和名を調べ直す)。
- 値は `data/guide/policy.yaml` に追加(skip_names・review_file・multi_file・html.others)。コードに数値の閾値は足していない。

## 採用した「候補が 2 件」の種(8 種)
| 和名 | 採用(species) | taxon id | 一緒に一致した候補(下位) |
|---|---|---|---|
| オオタカ | Astur gentilis | 1579015 | Astur gentilis fujiyamae(subspecies, 1583221) |
| オオヒシクイ | Anser fabalis | 7009 | Anser fabalis middendorffii(subspecies, 710890) |
| オカヨシガモ | Mareca strepera | 558439 | Mareca strepera strepera(subspecies, 718535) |
| カイツブリ | Tachybaptus ruficollis | 4237 | Tachybaptus ruficollis poggei(subspecies, 560404) |
| カンムリカイツブリ | Podiceps cristatus | 4208 | Podiceps cristatus cristatus(subspecies, 512826) |
| コハクチョウ | Cygnus columbianus | 6917 | Cygnus columbianus bewickii(subspecies, 196538) |
| ジョウビタキ | Phoenicurus auroreus | 12993 | Phoenicurus auroreus auroreus(subspecies, 728266) |
| ヘラサギ | Platalea leucorodia | 3731 | Platalea leucorodia leucorodia(subspecies, 715379) |
和名はすべて優先名の完全一致(候補の共通名はどれも和名と同じ)。

## 表に入らなかった和名
- 種を特定しない語(問い合わせない): カモ・カモ類・シギ・シギ・チドリ類・チドリ・猛禽類・ハクチョウ類(関東)。
- **シロハラ・ヨシガモ**: 日本語名の照合を足しても入らなかった。検索(30 件)の結果に、日本語名がその和名と完全一致する候補が出てこなかった(別の鳥・植物の科などが並ぶ)。学名を自分の知識で補うことはしていない。

## 写真(23 種 → 15 種に付いた)
付いた 15 種(目で確認済み): オオタカ・オオハクチョウ・オカヨシガモ・オナガガモ・カイツブリ・カワセミ・カンムリカイツブリ・キンクロハジロ・コハクチョウ・ダイサギ・チュウヒ・ツグミ・ヘラサギ・ミコアイサ・ユリカモメ。
付かなかった 8 種:
| 種 | 理由 |
|---|---|
| オオバン | 取れた写真(CC BY-SA)が**卵 2 個**だったため、目で見て除外(photo_review に記録) |
| オオヒシクイ・キビタキ・ジョウビタキ・スズガモ・ハシビロガモ・ハマシギ・ホシハジロ | 既定の写真と taxon_photos(6〜12 枚)のどれも許可ライセンスでない(NC 系・ライセンスなし) |
目で見て注意が要ると思った 2 枚は残した(基準は満たす): ダイサギ=巣の中のヒナ 3 羽、ヘラサギ=2 羽が写り右の 1 羽は端で切れている。オオタカは元画像に撮影者の署名文字が入っている。差し替えるなら指示してください。

## 画面の確認
- **Playwright は入っていなかった**(インストールは新しいダウンロードになるので行っていない)。代わりに、手元の Chrome(ヘッドレス)で `file://` を直接開いた。ローカルサーバーは起動していない(前回の 127.0.0.1:8765 の件は未対応のまま)。
- スマホ幅 390px(幅 390 の iframe 内で表示。ヘッドレス Chrome は窓の最小幅が広いため): はみ出しなし、カード 1 列、写真なしの枠・「そのほか」行の表示を確認。
- スクリーンショット(gitignore 済み):
  - `C:\ikimonobiyori\runtime\ikimonobiyori\guide\pages\bird-guide-390.png`
  - `C:\ikimonobiyori\runtime\ikimonobiyori\guide\pages\bird-guide-desktop.png`
- ページ: `C:\ikimonobiyori\runtime\ikimonobiyori\guide\pages\bird-guide.html`(約 5 MB)。

## 通信の内訳(計測フックのログ runtime/ikimonobiyori/photos_req4〜7.log)
- 応答の形を見る試し 4(api.inaturalist.org。応答は保存していない)/ 表づくり 10 / 写真 37(api 22・inaturalist-open-data.s3.amazonaws.com 15)= 51。すべて 200。許可外ホストなし。

## 人の判断が要る点
- シロハラ・ヨシガモを入れるには、別の手がかり(学名を与える、など)が要る。
- 写真のない 8 種(ライセンス)。CC BY-NC を許すか、別の出どころ(Wikimedia Commons など。新しい通信先)にするか。
- ダイサギ(ヒナ)・ヘラサギ(切れ)を残すか。
- Playwright を入れてよいか(入れれば同じ確認を Playwright で再現できる)。
