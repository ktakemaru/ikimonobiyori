# 段階17 報告: 試用で見つかった修正と、野鳥・花の追加

(フェーズ8 で仕上げる)

## 途中経過
- フェーズ0: `stage17` を main(a78263c)から作成。決定の記録 `docs/stage17-decisions.md`(D-01〜D-18)、段階計画に段階17 を差し込んだ。
- フェーズ1: 答えの形を直した(結論が先・内部用語なし・重複なし・日付は地点ごとに 1 つ)。答えの下書き `sources answer`(`answer.py`)、合成の答えの例、禁止語のテスト `tests/test_answer.py`。
- フェーズ2: 手順の抜けを直した。コードで読む前に 1 回だけ聞く・聞けなければ「簡易な読み取り」(`docs/design.md` §0.1 に事前の許可の方法)、答えの前に必ず記録(`read_by`)、新しさの基準(`official_observed`・`freshness_basis`)、瓢湖は一覧から今月の記事(`follow`)。テスト `tests/test_reading_steps.py`。
- フェーズ3: 野鳥 `birds` を同じ型に(段階 少ない/増えている/多い/減っている、探鳥地 5〔仮承認 3・pending 2〕、干潟に潮位表の案内)。食い違いの原因は `implemented`(手順)と プロファイルの status(計算)の取り違え。話題 → 対象、未実装の答え方、iNaturalist はユーザー確認済みと明記。
