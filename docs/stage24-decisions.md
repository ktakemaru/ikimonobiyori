# 段階24 決めたこと・解釈した点(2026-10-30)

指示書: `stage24-instructions.md`(ユーザー、2026-10-30)。ブランチ `stage24`。

## 決めたこと
1. **定評のしきい値をテーマ別に**(フェーズ1)。`data/guide/policy.yaml` の `tiers.curated.min_independent_by_theme` に野鳥・冬鳥 = 2(出典「ユーザー指示 2026-10-30」、`provisional: false`)。ほかのテーマは既定の `min_independent` = 3(暫定のまま)。コードは `guide.curated_min` が表を読むだけで、数字を持たない。
2. **変えなかったもの**: `needs_class_any`(A・B・C を 1 件以上)、`existence_classes`、`show_fact_min_independent`(2)、範囲(250 km)、位置の丸め(野鳥 area_10km、冬鳥 area_1km。野鳥に public_venue の例外は付けていない)。
3. **発行元の数え方**: iko-yo.net と report.iko-yo.net、rurubu.jp と kids.rurubu.jp は既存の表で同じ発行元になる。tabi-mag.jp も表にある(「旅行総合研究所タビリス」)。表への追加は不要だった(テストで確かめた)。
4. **却下・退役の保証**(フェーズ2 の 6)。`policy.yaml` の `retired_guard` に、見る場所(名所カタログの `status: retired`、見直しの `rejected`)を書き、`guide.load_retired` がデータから名前と出どころの URL を集める。
   - 退役・却下された名前の名所は、件数が足りても定評にならず、候補のまま(理由「却下・退役済み(…)」)。
   - 退役した出どころの URL は、定評の件数に数えない。
   - 古徳沼は、段階23 の記録に出どころが 3 件あり、しきい値 2 だと自動で昇格するところだった。この保証で**参考のまま**(`tests/test_stage24.py`)。
5. **参照数の表示**(フェーズ3)。
   - ガイド型: `guide find ... --text` が、コードの文だけで答えを組み立てる(各場所の行の文末に `（参照数 N）`、最後に凡例を 1 回)。文言は `data/guide/policy.yaml` の `reference_count` と `answer`。内部用語の検査つき。
   - 現況型: `answer` の下書きで、おすすめの行に同じ参照数を付ける。照らし方は、現況の対象 → ガイドのテーマ(`subject_theme`)と、名前の末尾のかっこを除いた名前の一致。ガイドの仮承認以上のカタログにない場所には付けない。凡例は 1 つでも付いたときだけ、最後に 1 回。付けられなかった件数は**作業メモ**に出す(答えには出さない)。
   - 提案(`biyori-proposal/1`): 契約の自由欄 `details` に `reference_count` を足した(同じ照らし方。ない場所は項目なし)。**契約のスキーマは変えていない**(`details` は「ビヨリ固有の自由欄」)。
6. **スキル・規則の追記**: `.claude/skills/ikimono-weekend/SKILL.md`・`CLAUDE.md`・`AGENTS.md` の同じ節に、参照数と定評の下限(野鳥・冬鳥 2 件、ほか 3 件)を追記した(3 つは一致のテストで検査される)。

## 解釈した点(人の確認が要る)
- **「冬鳥」を野鳥と同じ扱い(2 件)にしたのは、私の解釈**(冬鳥は野鳥の一部と考えた)。指示書の「野鳥と冬鳥は 2 件」の文面とも合う。変えるときは `min_independent_by_theme` の `冬鳥` の行を消す(3 件に戻る)。
- 検索の上限: 指示書は 1 地点 3 回まで検索だが、`guide log-request` の上限(collect 80 回。段階23 までに 66 回使用)により 8 回しか使えなかった。**上限は広げていない**(規則 6)。1 地点 1 回にした。残りの地点は「未着手」。
- 新しい市区町村の代表点は通信(Wikidata)が要るため取っていない。候補のまま「範囲は未確認」の地点が多い。
- 参照数のない地点が検索の要約だけで数えられている場合がある(出どころの記録の `origin: search`)。種名・時期は、2 件以上が言うものだけを答えに出す(既存の規則どおり)。

## 触ったファイル(フェーズごと)
- フェーズ1: `data/guide/policy.yaml`、`guide.py`、`data/guide/catalog.yaml`・`candidates.yaml`(build の結果を写した)、`tests/test_stage24.py`。
- フェーズ3: `data/guide/policy.yaml`、`data/sources/policy.yaml`(`answer.reference_*`)、`guide.py`、`answer.py`、`sources.py`(`_answer_cli`)、`proposals.py`、`SKILL.md`・`CLAUDE.md`・`AGENTS.md`、`tests/test_stage24.py`。指示書の列挙にない `answer.py`・`sources.py`・`proposals.py`・`data/sources/policy.yaml` を変えたのは、現況型の答えと提案にも参照数を付ける指示(フェーズ3 の 3・5)のため。
- フェーズ2: `data/guide/records.jsonl`・`catalog.yaml`・`candidates.yaml`、`docs/stage23-review.md`(座間谷戸山公園の 1 行。既存のテストが「仮承認は全部この一覧にある」ことを確かめるため。テストは変えていない)、`docs/seeds/stage24-seeds.md`。`seed_map.yaml` は使っていない(`import-seed` ではなく `record-candidate` で記録したため)。
