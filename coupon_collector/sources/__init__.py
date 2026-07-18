"""クーポンソース(プラグイン)群。"""

from __future__ import annotations

from .base import CouponSource
from .demo import DemoSource
from .hotpepper import HotpepperSource
from .rakuten import RakutenSource

#: 登録済みソース(実行順)。新しいソースはここに追加する。
ALL_SOURCES: list[type[CouponSource]] = [
    DemoSource,
    HotpepperSource,
    RakutenSource,
]


def create_sources(names: list[str] | None = None) -> list[CouponSource]:
    """ソースをインスタンス化して返す。names 指定時はその名前のみ。

    未知の名前が含まれる場合は ValueError を送出する。
    """
    instances = [cls() for cls in ALL_SOURCES]
    if names is None:
        return instances
    by_name = {src.name: src for src in instances}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise ValueError(
            f"未知のソース名: {', '.join(unknown)} (利用可能: {', '.join(by_name)})"
        )
    return [by_name[n] for n in names]
