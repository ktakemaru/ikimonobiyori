"""イキモノビヨリ v0(オフライン)。野鳥と紅葉だけを実装し、他の対象はプロファイルの骨組みだけ。

- 新規のビヨリなので、契約(biyori-proposal/1)をそのまま出力する。アダプター不要、manifest に source なし。
- vendor の2つのモジュール(yamabiyori / hoshibiyori)を import しない。
- 層: fetch/(応答の JSON を解釈するパーサーと、問い合わせの組み立て。通信はしない)→ methods/(純粋な手法)→ engine.py。
- 閾値・係数は ikimonobiyori/profiles/*.yaml の method.params からだけ読む(コードに直接書かない)。
- v0 は通信しない(6b で別途承認)。入力は inputs JSON(フィクスチャ)で渡す。
"""
__version__ = "0.1.0"
