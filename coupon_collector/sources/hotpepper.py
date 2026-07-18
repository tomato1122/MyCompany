"""ホットペッパーグルメ API(リクルートWebサービス)ソース。

公式 API ドキュメント: https://webservice.recruit.co.jp/doc/hotpepper/reference.html
クーポン付き(coupon_urls を持つ)飲食店をクーポン情報として整形する。
APIキーは環境変数 HOTPEPPER_API_KEY で指定する。
"""

from __future__ import annotations

import logging
import os

from .. import http
from ..models import Coupon, make_coupon_id
from .base import CouponSource

logger = logging.getLogger(__name__)

API_URL = "https://webservice.recruit.co.jp/hotpepper/gourmet/v1/"
API_KEY_ENV = "HOTPEPPER_API_KEY"
#: 検索対象の大エリアコード(デフォルト: Z011 = 東京)。環境変数で変更可能。
LARGE_AREA_ENV = "HOTPEPPER_LARGE_AREA"
DEFAULT_LARGE_AREA = "Z011"
FETCH_COUNT = 50


class HotpepperSource(CouponSource):
    """ホットペッパーグルメのクーポン付き店舗を取得するソース。"""

    @property
    def name(self) -> str:
        return "hotpepper"

    def is_configured(self) -> bool:
        return bool(os.environ.get(API_KEY_ENV))

    def fetch(self) -> list[Coupon]:
        params = {
            "key": os.environ[API_KEY_ENV],
            "format": "json",
            "large_area": os.environ.get(LARGE_AREA_ENV, DEFAULT_LARGE_AREA),
            "count": FETCH_COUNT,
        }
        data = http.get_json(API_URL, params=params)
        results = data.get("results", {})
        if "error" in results:
            raise RuntimeError(f"ホットペッパーAPIエラー: {results['error']}")

        coupons: list[Coupon] = []
        for shop in results.get("shop", []):
            coupon_urls = shop.get("coupon_urls") or {}
            coupon_url = coupon_urls.get("sp") or coupon_urls.get("pc") or ""
            if not coupon_url:
                continue  # クーポンを持たない店舗はスキップ
            shop_id = shop.get("id", "")
            shop_name = shop.get("name", "")
            genre = (shop.get("genre") or {}).get("name", "")
            catch = shop.get("catch") or (shop.get("genre") or {}).get("catch", "")
            coupons.append(
                Coupon(
                    id=make_coupon_id(self.name, shop_id or coupon_url),
                    source=self.name,
                    title=f"{shop_name} のクーポン",
                    description=" / ".join(x for x in (genre, catch) if x),
                    shop_name=shop_name,
                    discount=catch,
                    url=coupon_url,
                    expires_at=None,  # API は個別クーポンの期限を返さない
                )
            )
        logger.info("hotpepper: クーポン付き店舗 %d 件を取得", len(coupons))
        return coupons
