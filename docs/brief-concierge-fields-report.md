# 報告書: 資料(ask brief)にコンシェル向けの項目を足す

作成 2026-11-27 / 指示書 `docs/brief-concierge-fields-instructions.md` / ブランチ `feature/brief-concierge-fields`(main `72a11ad` から)

## 候補の出どころ(第 0 部 3。実装の前に書いた)

調べ方: `guide_brief.build` のコード(`_candidates`・`typical_candidates`・`_town_candidates`・`_species_facts`・`_dated_species_candidates`・`bird_highlights`・`_area_plan`・`merge_same_candidates`)と、通信を禁じて作った直す前の資料(8 問 + 追加の 4 問)の候補 130 件を、データのファイルと突き合わせた。

| 候補の種類(資料での見分け方) | 作られる元 | 元の行に ID | 元のデータに座標 | 山の地点との結びつき |
|---|---|---|---|---|
| 順位つきの候補(`rank` が数。`basis` は `current` か `typical`) | 今までの形の答えの計画(`answer_plan.json`)の順位の行。行は名所カタログ(`data/catalog/*.yaml`)か観察の名所(`data/observations/spots.yaml`)の 1 件 | **ある**: 順位の行の `id`(カタログの `kouyou-0024`・`hana-0021`・`yacho-0001` など、観察の名所の `obs-kouyou-0002` など)。今までは資料に写していなかった | カタログ: `point`(例を除く 149 件中 74 件にある。花は 92 件中 17 件。値は各件の `location_precision` の桁で入っている)。観察の名所: `point` 28 件・`bird_range` 6 件(野鳥)、`catalog_ref` でカタログの件を指すものが 7 件 | カタログの `site_ref` は例の 1 件(`kouyou-example-0002`)だけ。観察の名所には項目なし(高尾山 `obs-kouyou-0088` の `point.source` に「sites.yaml m029 の座標」と文で書かれているだけ) |
| 例年の目安(`rank` が `null`・`basis: typical`・`subject: null`) | ガイドのカタログ(`guide.build()`。`data/guide/catalog.yaml`) | ある: `g-` + テーマ・都道府県・名前の sha1 の先頭 10 文字(`guide.entry_id`)。名前・テーマが変わると変わる。今の候補の行には写していない | **無い**(ガイドのカタログに座標の項目がない) | 無い |
| 町の名所(`basis: town`) | 名所カタログ(承認済み)とガイドのカタログ(`guide_materials.town_spots`) | 元の行にはある(カタログの `id`・ガイドの `g-`)が、`town_spots` の行に ID を運んでいない | カタログの件は `point` がある。ガイドの件は無い | 無い |
| 種の名所(`basis: species`) | 名所カタログ・記録・ガイドのカタログ(`season_place.gather`) | 行に ID を運んでいない | カタログの件は `point` がある(行には運んでいない) | **ある**: 候補の `mountain_site`(段階84 第1部 A。括弧の前の名前が sites.yaml の山と同じ名所。山の名前が入る。sites.yaml の `site_ref` は `yamabiyori:mNNN`) |
| 季節の目玉の観察地(`basis: highlight`) | `data/ask/guide_mode.yaml` の `bird_highlights.sites`(名前・都県・市町村・テーマ) | 無い | 無い | 無い |
| エリアの名所(山域の質問) | 順位つきの候補と同じ(`_area_plan` が別の計画を作る) | 順位つきと同じ | 順位つきと同じ | 順位つきと同じ |
| 日付つきの種の名所(`basis: species`。`_dated_species_candidates`) | 今までの形の答えが選んだ名所の名前だけ | 無い | 無い | 無い |

- 同じ名前でも対象ごとに別の ID がある(三溪園: 紅葉 `obs-kouyou-0002`・花 `obs-hana-0001`。鎌倉 長谷寺: `kouyou-0021`・`hana-0054`。旧古河庭園・生田緑地・県立境川遊水地公園も)。候補は名前で 1 件にまとめているので、先に来た対象の行の ID になる。
- 8 問の資料の候補 95 件の内訳: 順位つき 82 件(`basis: typical`)・例年の目安 11 件・町の名所 2 件。種の名所・季節の目玉・今年の現況つき・まとめた候補(`candidate_merges`)は 0 件(データ置き場が空なので)。追加の 4 問(種の質問)の候補 35 件は、種の名所 34 件・例年の目安 1 件。

(このあとの章は実装のあとに書く)
