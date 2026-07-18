"""クーポンソースの抽象基底クラス。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Coupon


class CouponSource(ABC):
    """クーポン取得元のプラグインインターフェース。

    新しいソースを追加する場合:
    1. このクラスを継承し `name` と `fetch()` を実装する
    2. APIキー等が必要なら `is_configured()` をオーバーライドする
    3. `sources/__init__.py` の ALL_SOURCES に登録する
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """ソースの識別名(CLI の --source で指定する名前)。"""

    def is_configured(self) -> bool:
        """実行に必要な設定(APIキー等)が揃っていれば True。

        False の場合、コレクタはエラーにせずこのソースをスキップする。
        """
        return True

    @abstractmethod
    def fetch(self) -> list[Coupon]:
        """クーポンを取得して返す。ネットワークエラー等は例外を送出してよい。"""
