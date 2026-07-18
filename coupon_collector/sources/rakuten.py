"""楽天商品検索 API(Rakuten Ichiba Item Search API)ソース。

公式 API ドキュメント: https://webservice.rakuten.co.jp/documentation/ichiba-item-search
「クーポン」キーワードでセール・クーポン対象商品を検索して整形する。
アプリIDは環境変数 RAKUTEN_APP_ID で指定する。
"""

from __future__ import annotations

import logging
import os

from .. import http
from ..models import Coupon, make_coupon_id
from .base import CouponSource

logger = logging.getLogger(__name__)

API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
APP_ID_ENV = "RAKUTEN_APP_ID"
#: 検索キーワード(デフォルト: クーポン)。環境変数で変更可能。
KEYWORD_ENV = "RAKUTEN_KEYWORD"
DEFAULT_KEYWORD = "クーポン"
FETCH_COUNT = 30  # 1ページの最大取得件数


class RakutenSource(CouponSource):
    """楽天市場のクーポン/セール対象商品を取得するソース。"""

    @property
    def name(self) -> str:
        return "rakuten"

    def is_configured(self) -> bool:
        return bool(os.environ.get(APP_ID_ENV))

    def fetch(self) -> list[Coupon]:
        params = {
            "applicationId": os.environ[APP_ID_ENV],
            "format": "json",
            "keyword": os.environ.get(KEYWORD_ENV, DEFAULT_KEYWORD),
            "hits": FETCH_COUNT,
            "sort": "-updateTimestamp",
        }
        data = http.get_json(API_URL, params=params)
        if "error" in data:
            raise RuntimeError(
                f"楽天APIエラー: {data.get('error')} - {data.get('error_description')}"
            )

        coupons: list[Coupon] = []
        for entry in data.get("Items", []):
            item = entry.get("Item", entry)
            item_code = item.get("itemCode", "")
            item_url = item.get("itemUrl", "")
            if not item_code and not item_url:
                continue
            point_rate = item.get("pointRate", 1)
            discount = f"ポイント{point_rate}倍" if point_rate and point_rate > 1 else ""
            caption = (item.get("itemCaption") or "").strip()
            coupons.append(
                Coupon(
                    id=make_coupon_id(self.name, item_code or item_url),
                    source=self.name,
                    title=item.get("itemName", ""),
                    description=caption[:200],
                    shop_name=item.get("shopName", ""),
                    discount=discount,
                    url=item_url,
                    expires_at=None,  # API は個別のクーポン期限を返さない
                )
            )
        logger.info("rakuten: クーポン/セール対象商品 %d 件を取得", len(coupons))
        return coupons
