# 台帳で公式の扱いにしていない通信先の一覧(段階32。段階34 で扱いを変更)

**段階34(利用者の決定 2026-11-01)**: 下のホストも読む。読んだ値は出所の区分 `secondary`(公式ではない)として候補の根拠に使い、答えに出所と日付を添える。台帳の `approval.status` は「公式」の区分の判定にだけ使う。以下は段階32 の記録。

段階32(花の神奈川対応。指示書 2026-10-31)で、ユーザーが今回の実行で通信を認めたホストは次の 4 つだった(段階34 で限定をやめた)。

- `www.kanagawaparks.com`(横浜緑地が運営する県立公園など)
- `www.sankeien.or.jp`(三溪園)
- `www.kanagawa-kankou.or.jp`(神奈川県観光協会 観光かながわNOW)
- `www.welcome.city.yokohama.jp`(横浜市観光情報。今回の台帳には入れていない。リダイレクトで読めなかった)

下のホストは、各地点の公式の運営者のページと思われるが、**台帳では公式の扱いにしていない**(段階32 では読まなかった。段階34 からは読み、区分 secondary で使う)(台帳は `approval.status: pending`、答えでは「公式の現況は未確認(公式ページ: URL)」)。承認するかどうかはユーザーが決める。承認するときは、robots.txt と利用条件を読み、台帳の `readable`・`terms`・`approval` を直す。

| ホスト | 運営者(分かる範囲) | 台帳の情報源 id | 名所 |
|---|---|---|---|
| kana-garden.com | 神奈川県立花と緑のふれあいセンター 花菜ガーデン | kana-garden-news | 花菜ガーデン |
| www.hakonenavi.jp | 株式会社小田急箱根 | hakonenavi-gorapark | 箱根強羅公園ローズガーデン |
| www.soleil-park.jp | エリアマネジメント横須賀共同事業体 | soleil-blooming-info | 長井海の手公園 ソレイユの丘 |
| www.kawasakidaishi.com | 川崎大師平間寺 | kawasakidaishi-kikka | 川崎大師 菊花展 |
| odawaracastle.com | 小田原城総合管理事務所(小田原市観光協会) | odawaracastle-kikka | 小田原城 菊花展 |
| gardennecklace.city.yokohama.lg.jp | 横浜市(ガーデンネックレス横浜) | gardennecklace-yamate, gardennecklace-kodomo | 山手イタリア山庭園、横浜市こども植物園 |
| www.city.yokohama.lg.jp | 横浜市西区役所 | yokohama-nishi-hana | 野毛山公園 |
| www.city.ayase.kanagawa.jp | 綾瀬市 みどり公園課 | ayase-rose-garden | あやせローズガーデン |
| www.pref.kanagawa.jp | 神奈川県(掲載ページ。主催は大雄町花咲く里山協議会) | pref-kanagawa-zarugiku | 大雄町 花咲く里山(ざる菊まつり) |
| www.satoyama-garden.jp | 横浜市(里山ガーデン実行委員会) | satoyama-garden-welcome | 里山ガーデン |
| kanagawa-park.or.jp / www.kanagawa-park.or.jp | 神奈川県公園協会 | kanagawa-park-sakaigawa, kanagawa-park-hadanotokawa | 県立境川遊水地公園、秦野戸川公園 |

## 運営者の公式ページを確認できなかった名所(candidate。おすすめに使わない)

港の見える丘公園・横浜イングリッシュガーデン・山下公園・八景島 丘の広場バラ園・日比谷花壇大船フラワーセンター・相模川ローズガーデン・平塚市総合公園バラ園・平塚八幡宮 菊花展・土屋ざる菊園・イシックス馬入のお花畑・生田緑地ばら苑(閉苑の案内あり)。

## 経緯

名所の公式ページを探す調査(2026-10-31)で、調査役のエージェントが上のホスト(と、認めた 4 ホストのほか数ホスト)のページを読んだ。指示書は『承認する通信先(これ以外は読まない)』としていたので、これは指示書の範囲を超えた読み取りだった(調査の依頼の文に『主に認めた 4 ホストを優先して読んでよい』と書いたため)。そこで得た事実のうち、**4 ホストの外から得た値は、段階32 では段階 B(今年のイベント期間つき)・段階 A(公式の現況)に使わなかった**(段階34 からは区分 secondary として使う)(`events` の `verified: false` か、例年の時期の根拠の `flower_windows` に、取得元の年つきで書いた)。
