# 段階29 決めたこと(2026-10-31。ブランチ stage29)

## 1. ユーザーの承認(指示書 stage29-instructions.md §1 の原文どおり、2026-10-30)
- 承認A: 写真の取得のため、次の通信先を**この目的に限って**許す。
  - `api.inaturalist.org`(種の検索と写真情報。読み取りだけ)
  - 写真の実体の配信元は、API の応答に出てくるホストのうち **`static.inaturalist.org` と `inaturalist-open-data.s3.amazonaws.com` の2つだけ**。ほかのホストの写真は使わない(取得しない)。
- 承認B: 手元のPCのブラウザで開く単独のHTMLファイルを作る。写真はそのファイルに埋め込む。
- 承認C: 野鳥(ガイド型)が対象。冬鳥は同じ仕組みで出せるなら対象に含めてよいが、野鳥を先に完成させる。

## 2. ブランチ
- stage27・stage28 は main にマージ済み。**stage28b は未マージ**だったため、main からではなく、最新の先頭(stage28b の `4f41e79`)から `stage29` を作った(参照数の数え方の変更が、ページに出る参照数に効くため)。

## 3. フェーズA(表と写真の取得)
- 値はすべて `data/guide/policy.yaml` の `photos` に置いた(上限 80・間隔 1 秒・2MB・ライセンス・ホスト・形式)。許可ホストは `config.yaml` の `live.allowed_hosts_by_subject.guide_photos`(承認Aの 3 つ)。
- 実装: `fetch/inat_photos.py`(表づくり・写真の取得。通信は呼び出し側から渡された関数だけ)、`guide_photos.py`(表・キャッシュ・コマンド)。`SessionGetter.get_bytes` を足した(バイト列のまま取る・リダイレクトを追わない)。
- 種の対応表は `data/guide/bird_taxa.yaml`(和名・学名・taxon id・確認日だけ)。`photos-build-table` の書き込み先は、既存の build と同じ流れで IKIMONOBIYORI_DATA_DIR の下の `guide/export/`(規則 8。リポジトリの追跡ファイルを実行で変えない)。見直して `data/guide/` に写す。
- 「カモ類」「ハクチョウ類」「シギ・チドリ」など種を特定しない語は、問い合わせずに対象外(`skip_name_suffixes`・`skip_name_chars`)。ほかの語は、すべての条件(ランク species・日本語の一般名が完全一致・一致がちょうど 1 件・鳥類)を満たしたときだけ表に入る。
- 写真は taxon の既定の写真だけ。ライセンスが CC0・CC BY・CC BY-SA のときだけ。応答が 1 件でない・学名が表と違う・id が違う・撮影者の表記がない・ホストが許可外・http は使わない。
- 画像は先頭のバイト列で形式(JPEG・PNG・WebP)を確かめ、2MB を超えるもの・形式違いは捨てる。リダイレクトは追わない(行き先が許可外になりうるため)。
- 同じ種は取り直さない(キャッシュにあれば飛ばす)。1 回の実行の上限は policy の `max_requests_per_run`(80)と `--max-requests` の小さいほう。
- 表づくりでは、すでに表にある和名と、前に入らなかった和名(`bird_taxa_rejected.json`)は取り直さない。
- `answer_parts`(欄ごとの行)を `render_answer` から取り出した(HTML が同じ部品を使うため)。`guide find --text` の出力は変わらない(変更前後で一致を確かめた)。
