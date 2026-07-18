"""全ソースを実行して収集結果をマージするコレクタ。"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Iterable, Optional

from .models import Coupon, now_utc
from .sources.base import CouponSource

logger = logging.getLogger(__name__)

#: ソース間のウェイト(秒)。API 提供元への負荷配慮。
WAIT_BETWEEN_SOURCES = 1.0


def collect(sources: Iterable[CouponSource]) -> list[Coupon]:
    """各ソースを順に実行し、重複と期限切れを除いたクーポン一覧を返す。

    - is_configured() が False のソースはエラーにせずスキップ(ログに残す)
    - fetch() が例外を投げたソースもスキップし、他のソースは続行
    - ソース間には 1 秒のウェイトを入れる
    """
    merged: dict[str, Coupon] = {}
    now = now_utc()
    fetched_any = False

    for source in sources:
        if not source.is_configured():
            logger.info(
                "ソース '%s' はAPIキー等が未設定のためスキップします", source.name
            )
            continue

        if fetched_any:
            time.sleep(WAIT_BETWEEN_SOURCES)

        logger.info("ソース '%s' から取得を開始", source.name)
        try:
            coupons = source.fetch()
        except Exception:
            logger.exception("ソース '%s' の取得に失敗したためスキップします", source.name)
            continue
        fetched_any = True

        added = dupes = expired = 0
        for coupon in coupons:
            if coupon.is_expired(now):
                expired += 1
                continue
            if coupon.id in merged:
                dupes += 1
                continue
            merged[coupon.id] = coupon
            added += 1
        logger.info(
            "ソース '%s': %d 件追加 (重複 %d 件・期限切れ %d 件を除外)",
            source.name, added, dupes, expired,
        )

    logger.info("収集完了: 合計 %d 件", len(merged))
    return list(merged.values())


def filter_active(coupons: Iterable[Coupon], now: Optional[datetime] = None) -> list[Coupon]:
    """期限切れを除いた一覧を返す(保存前の既存データのクリーニングにも使用)。"""
    reference = now or now_utc()
    return [c for c in coupons if not c.is_expired(reference)]
