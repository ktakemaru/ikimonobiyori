# 段階28b 変更後の一覧(提案の実装を試した結果。実装は戻したので、いまのコードの出力ではない。docs/stage28b-proposed.patch を当てたとき)

`guide.build(include_runtime=False)` の野鳥・冬鳥の全件(名所と種類の説明)。参照数 = `independent_sources`。種名・時期は「表示してよい」と判定されたものだけ。

件数: 49

| テーマ | 種別 | 名前 | 段階 | 承認 | 参照数 | 答えに出る種名 | 答えに出る時期 |
|---|---|---|---|---|---|---|---|
| 冬鳥 | kind | カモ類 | curated | provisional | 2 | オナガガモ・キンクロハジロ・コガモ・ハシビロガモ・ヒドリガモ・ホシハジロ・マガモ | 秋から冬に飛来し、春に戻る |
| 冬鳥 | kind | キンクロハジロ | reference | candidate | 1 | — | — |
| 冬鳥 | kind | シギ・チドリ類 | curated | provisional | 2 | シギ・チドリ | 春と秋の渡り(秋は9月ごろ) |
| 冬鳥 | kind | シロハラ | curated | provisional | 4 | シロハラ | 10〜11月に関東平野へ渡ってくる冬鳥 |
| 冬鳥 | kind | ジョウビタキ | curated | provisional | 3 | ジョウビタキ | 10月下旬ごろから渡来 |
| 冬鳥 | kind | スズガモ・カンムリカイツブリ | reference | candidate | 1 | — | — |
| 冬鳥 | kind | タシギ・コガモ | reference | candidate | 1 | — | — |
| 冬鳥 | kind | ツグミ | curated | provisional | 3 | ツグミ | 10月に飛来。関東の低地では11月中旬〜12月に普通 |
| 冬鳥 | kind | ハクチョウ類(関東) | curated | provisional | 2 | オオハクチョウ・コハクチョウ | おおむね10月〜3月ごろ |
| 冬鳥 | kind | ハマシギ | curated | provisional | 2 | ハマシギ | 冬(越冬) |
| 冬鳥 | kind | ヒドリガモ | reference | candidate | 1 | — | — |
| 冬鳥 | kind | ホシハジロ | reference | candidate | 1 | — | — |
| 冬鳥 | kind | ユリカモメ | curated | provisional | 2 | ユリカモメ | 冬 |
| 冬鳥 | kind | 漂鳥(ルリビタキ・アオジなど) | reference | candidate | 1 | — | — |
| 冬鳥 | place | 五行川白鳥飛来地 | curated | provisional | 2 | オオハクチョウ | 10月下旬〜3月下旬 |
| 冬鳥 | place | 古徳沼 | curated | approved | 2 | オオハクチョウ | — |
| 冬鳥 | place | 城沼 | reference | candidate | 1 | — | — |
| 冬鳥 | place | 大塚池公園 | curated | provisional | 3 | オオハクチョウ | 10月中旬〜3月下旬ごろ |
| 冬鳥 | place | 本埜白鳥の郷 | curated | provisional | 3 | コハクチョウ | 10月下旬〜3月上旬 |
| 冬鳥 | place | 白鳥の里(北浦) | curated | provisional | 2 | オオハクチョウ | — |
| 冬鳥 | place | 稲波干拓 | curated | provisional | 2 | オオヒシクイ | — |
| 冬鳥 | place | 菅生沼 | curated | provisional | 6 | コハクチョウ | 例年11月〜2月頃 |
| 冬鳥 | place | 越辺川(川島町) | curated | provisional | 2 | — | — |
| 野鳥 | place | ふなばし三番瀬海浜公園 | reference | candidate | 1 | — | — |
| 野鳥 | place | 不忍池 | curated | provisional | 5 | キンクロハジロ | 冬は水鳥 |
| 野鳥 | place | 井の頭恩賜公園 | curated | provisional | 3 | カモ | 冬 |
| 野鳥 | place | 光が丘公園 | curated | provisional | 5 | オオタカ | — |
| 野鳥 | place | 多摩川河口 | curated | provisional | 3 | — | — |
| 野鳥 | place | 奥日光(戦場ヶ原・中禅寺湖) | curated | provisional | 2 | — | — |
| 野鳥 | place | 妙岐ノ鼻・和田公園(霞ヶ浦) | curated | provisional | 2 | — | — |
| 野鳥 | place | 彩湖 | curated | provisional | 2 | — | — |
| 野鳥 | place | 手賀沼 | curated | provisional | 3 | — | 冬鳥は11月〜3月ごろ |
| 野鳥 | place | 新宿御苑 | reference | candidate | 1 | — | — |
| 野鳥 | place | 明治神宮 | reference | candidate | 1 | — | — |
| 野鳥 | place | 東京港野鳥公園 | curated | provisional | 6 | カモ・シギ・チドリ・猛禽類 | 通年(秋〜春にカモ・シギ) |
| 野鳥 | place | 東京湾の干潟(お台場海浜公園・森ヶ崎の鼻) | reference | candidate | 1 | — | — |
| 野鳥 | place | 横浜自然観察の森 | curated | provisional | 3 | キビタキ | — |
| 野鳥 | place | 水元公園(水元かわせみの里) | curated | provisional | 5 | カワセミ | 年間を通じてほぼ毎日 |
| 野鳥 | place | 泉の森 | curated | provisional | 2 | — | 通年 |
| 野鳥 | place | 渡良瀬遊水地 | curated | provisional | 4 | チュウヒ | — |
| 野鳥 | place | 皇居周辺(北の丸公園・お濠) | curated | provisional | 4 | オオバン・オカヨシガモ・カイツブリ・キンクロハジロ・ジョウビタキ・ハシビロガモ・ミコアイサ・ユリカモメ・ヨシガモ | 秋〜冬 |
| 野鳥 | place | 県立座間谷戸山公園 | curated | provisional | 3 | — | — |
| 野鳥 | place | 石神井公園 | curated | provisional | 3 | オナガガモ・カモ・カワセミ・キンクロハジロ・シロハラ・ジョウビタキ・ダイサギ・ホシハジロ | 秋〜春 |
| 野鳥 | place | 秋ヶ瀬公園 | curated | provisional | 3 | — | — |
| 野鳥 | place | 自然教育園 | curated | provisional | 2 | カワセミ | — |
| 野鳥 | place | 葛西海浜公園 | curated | provisional | 3 | スズガモ・カンムリカイツブリ・ヘラサギ | 冬 |
| 野鳥 | place | 葛西臨海公園 鳥類園 | curated | provisional | 7 | — | 通年 |
| 野鳥 | place | 行徳鳥獣保護区 | reference | candidate | 1 | — | — |
| 野鳥 | place | 谷津干潟 | curated | provisional | 3 | シギ・チドリ | — |
