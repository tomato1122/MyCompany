"""デモソース。APIキー不要で静的なサンプルクーポンを返す。

キー未設定の環境でも収集〜保存のパイプライン全体を動作確認するためのもの。
期限切れサンプルを 1 件含み、コレクタの期限フィルタも確認できる。
"""

from __future__ import annotations

import logging
from datetime import timedelta

from ..models import JST, Coupon, make_coupon_id, now_utc
from .base import CouponSource

logger = logging.getLogger(__name__)


class DemoSource(CouponSource):
    """静的なサンプルクーポンを返すデモ用ソース。"""

    @property
    def name(self) -> str:
        return "demo"

    def fetch(self) -> list[Coupon]:
        now = now_utc().astimezone(JST)
        samples = [
            dict(
                key="ramen-10off",
                title="ラーメン一杯 100円引き",
                description="デモ用サンプルクーポン。全店舗で利用可能。",
                shop_name="デモラーメン 東京本店",
                discount="100円引き",
                url="https://example.com/coupons/ramen-10off",
                expires_at=now + timedelta(days=14),
            ),
            dict(
                key="cafe-drink-free",
                title="ドリンク1杯無料",
                description="デモ用サンプルクーポン。ケーキセット注文で適用。",
                shop_name="デモカフェ 渋谷店",
                discount="ドリンク無料",
                url="https://example.com/coupons/cafe-drink-free",
                expires_at=now + timedelta(days=7),
            ),
            dict(
                key="ec-5percent",
                title="全品5%OFFクーポン",
                description="デモ用サンプルクーポン。5,000円以上の購入で利用可。",
                shop_name="デモストア",
                discount="5%OFF",
                url="https://example.com/coupons/ec-5percent",
                expires_at=None,  # 期限なし
            ),
            dict(
                key="expired-sample",
                title="【期限切れ】餃子半額クーポン",
                description="デモ用サンプル。期限切れ除外の動作確認用で、保存されないのが正しい。",
                shop_name="デモ餃子 新宿店",
                discount="半額",
                url="https://example.com/coupons/expired-sample",
                expires_at=now - timedelta(days=1),
            ),
        ]
        coupons = [
            Coupon(
                id=make_coupon_id(self.name, s["key"]),
                source=self.name,
                title=s["title"],
                description=s["description"],
                shop_name=s["shop_name"],
                discount=s["discount"],
                url=s["url"],
                expires_at=s["expires_at"],
            )
            for s in samples
        ]
        logger.info("demo: サンプルクーポン %d 件を生成(うち1件は期限切れ)", len(coupons))
        return coupons
