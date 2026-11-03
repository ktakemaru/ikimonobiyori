"""ページに載せる写真を、同じ写真は 1 回だけ埋め込む小さな入れ物(段階39 A-6)。

同じ種のカードが 1 ページに何度も出ても、画像のデータ(base64)は CSS に 1 回だけ書き、カードはクラスで参照する。
CSP は `default-src 'none'; img-src data:; style-src 'unsafe-inline'` のまま(JavaScript なし。CSS の background-image の data: は img-src に含まれる)。
縮小・再圧縮はしない(外部ライブラリを足さない)。画像のバイト列が同じものを同じ番号にする。"""
import base64
import hashlib
import html

MIME = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
BASE_CSS = ".ph { display: block; width: 100%; aspect-ratio: 4 / 3; background-size: cover; background-position: center; background-repeat: no-repeat; background-color: #e7ebe8; border-radius: 0.3rem; }"


class PhotoPool:
    def __init__(self, max_bytes=None):
        self.max_bytes = max_bytes          # 埋め込む画像（base64 後）の合計の上限。超える新しい画像は載せない（None なら無制限）
        self.skipped = 0                    # 上限で載せなかった画像の数
        self.encoded = 0
        self._ids = {}          # sha256 → 番号
        self._css = []          # 番号順の CSS 規則
        self.refs = 0           # 参照した回数
        self.bytes = 0          # 埋め込んだ画像のバイト数(重複を除く)

    def tag(self, meta, data, alt):
        """→ <div class="ph phN" role="img" aria-label="alt"></div>。同じ画像は同じ番号。上限を超える新しい画像は None（呼び出し側は名前だけの行に回す）。"""
        key = hashlib.sha256(data).hexdigest()
        n = self._ids.get(key)
        if n is None:
            size = (len(data) + 2) // 3 * 4
            if self.max_bytes is not None and self.encoded + size > self.max_bytes:
                self.skipped += 1
                return None
            self.encoded += size
            n = len(self._ids) + 1
            self._ids[key] = n
            uri = f"data:{MIME[meta['image_type']]};base64," + base64.b64encode(data).decode("ascii")
            self._css.append(f'.ph{n} {{ background-image: url("{uri}"); }}')
            self.bytes += len(data)
        self.refs += 1
        return f'<div class="ph ph{n}" role="img" aria-label="{html.escape(str(alt), quote=True)}"></div>'

    def fits(self, data):
        """この画像を（まだ載せていなければ）載せられるか。載せ済みの画像・上限なしは真。"""
        if self.max_bytes is None or hashlib.sha256(data).hexdigest() in self._ids:
            return True
        return self.encoded + (len(data) + 2) // 3 * 4 <= self.max_bytes

    def css(self):
        return BASE_CSS + "\n" + "\n".join(self._css)

    @property
    def unique(self):
        return len(self._ids)
