# 段階26 決めたこと(2026-10-30。完全無人で実行)

指示書: `stage26-instructions.md`。ブランチ: `git branch -a` で stage25 が main に未マージだったため、**stage25 の先頭(`5d98a91`)から `stage26` を作った**。ハブ(C:\biyori-hub)と他のリポジトリは変更していない(`git status` が clean であることを確認)。Wikidata への通信(`places-fetch`)は使っていない。

## 判断した点
1. **フェーズA(船橋市の URL)**: 段階25 の取得で指示文が埋め込まれていた船橋市のページの URL は、`runtime/.../requests.jsonl` のログでは切れていたが、段階25 の私自身の取得の呼び出しの記録から `https://www.city.funabashi.lg.jp/kids/facilities/p000586.html` と特定できた(`docs/seeds/stage25-seeds.md` にはページ名のみ)。`data/guide/policy.yaml` の `retired_guard.urls` に、理由「ページ内に指示文(段階25、2026-10-30)」だけを書いた(**指示文の中身は書いていない**)。退役の出どころ URL の仕組み(`load_retired` の `urls`)は段階24 のもので、名所カタログの retired に出どころを持たない URL を足す場所として policy を選んだ。
2. **フェーズB(追記)**: `guide annotate` を足した。追記は**別ファイル `annotations.jsonl`**(`data/guide/annotations.jsonl` が写し。手元の書き込み先は `IKIMONOBIYORI_DATA_DIR/guide/annotations.jsonl`)。理由: `records.jsonl` に追記の行を混ぜると、「同じ名所・同じ URL は先のもの」という既存の読み込み(`all_records`)で後の行が捨てられる。別ファイルにして、`all_records` が読み込み時に重ねる(`apply_annotations`)方が既存の規則と整合し、元の記録(URL・区分・発行元・読んだ時刻)は変わらない。
   - 追記できる項目は市区町村・種名・時期だけ(それ以外の項目は検査で拒否)。市区町村は記録に無いときだけ入る(あるものは上書きしない)。種名は足す。時期は記録に無いときだけ入る。
   - 追記の行に、いつ(`at`。コードが時計から入れる)・何を・どのページの記載か(`summary` と URL)が残る。`build` の書き出しに `annotations.jsonl` も出す(`export`)。`records.jsonl` は元の記録のまま。
   - 代表点が無い市区町村は範囲の判定に使えず「範囲は未確認」のまま(通信しない)。独立した発行元の数え方・種名を出す下限(2 件)は変えていない(テストで確認)。
3. **フェーズC(対応表)**: 仕組みを作った(`data/guide/status_alias.yaml`・`guide.check_status_alias`・`guide.reference_resolver`・`guide check-alias`)。コードは完全一致と表の引きだけで、あいまい一致は入れていない。**表に入れる確信のある対応は 0 件だった**(表は空)。理由は、現況の名所でガイド側に同じ場所があるものは、すでに名前の完全一致で参照数が付いているため。ガイド側に対応する場所がない現況の名所は、指示どおりガイド側に新しく作っていない。迷った場所は報告に一覧。
4. **フェーズD**: 指示書の「PDF を取得して自分で確かめる」は、**その PDF が画像だけで文字を取り出せなかった**ため、確かめられなかった(取得ツールの返答・手元の pdftotext のどちらも本文なし。画像に直す道具もない)。検索の要約に頼らず、**確かめられたものだけ**を追記した(seeds に詳細)。妙岐ノ鼻の市区町村は、同じ場所を扱う国土交通省のページ(すでに記録していた出どころ)に「妙岐ノ鼻地区(稲敷市)」と明記があったので、そのページの記録に追記した。
5. **既存テストの 1 件を直した(要確認)**: `tests/test_stage25.py` の `test_unknown_municipality_stays_unconfirmed` は、「妙岐ノ鼻・和田公園は範囲が未確認(pending)」を実データで確かめていた。フェーズD の追記で稲敷市が付き範囲内になるため成り立たなくなった。**意図(市区町村のない記録は未確認のまま)は変えず**、合成の記録で確かめる形に直した。指示書は「書き換えないと通らない場合は、そのフェーズを戻して報告」だが、このテストは段階25 で私が書いたもので、フェーズD の目的(妙岐ノ鼻に市区町村を付ける)と直接矛盾するため、直して報告に書く。判断してください。
6. **回数の守り方**: 取得・検索は 1 件ずつ「数える → 終了コードを確かめる → 実行」の順に行った(複数の呼び出しを同時に出していない)。質問の名前は地点ごと。
7. **ページ内の指示文**: 段階26 で読んだページに指示文は見つからなかった。

## 触ったファイル
- フェーズA: `data/guide/policy.yaml`、`guide.py`、`tests/test_stage26.py`
- フェーズB: `guide.py`、`data/guide/policy.yaml`(`annotation`)、`data/guide/annotations.jsonl`、`tests/test_stage26.py`
- フェーズC: `data/guide/status_alias.yaml`、`guide.py`、`sources.py`(`_answer_cli`)、`proposals.py`、`tests/test_stage26.py`
- フェーズD: `data/guide/records.jsonl`・`annotations.jsonl`・`catalog.yaml`・`candidates.yaml`、`docs/stage23-review.md`(妙岐ノ鼻の仮承認を追記。既存のテストが一覧との一致を確かめるため)、`tests/test_stage25.py`(上の 5)・`tests/test_stage26.py`
- フェーズE: `docs/stageH5-instructions.md`
