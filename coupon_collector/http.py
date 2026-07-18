"""HTTP アクセスの共通処理(タイムアウト・User-Agent・リトライ)。

マナー:
- タイムアウト 10 秒
- User-Agent を明示
- リトライは最大 2 回(計 3 試行)、間隔を空ける
- 対象は公式 API のみ(robots.txt を回避するようなアクセスは行わない)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

from . import __version__

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 2  # 初回 + 最大2回のリトライ
RETRY_WAIT_SECONDS = 1.0
USER_AGENT = f"coupon-collector/{__version__} (+https://github.com/mycompany; contact: dev@mycompany.example)"


def get_json(url: str, params: Optional[dict[str, Any]] = None) -> Any:
    """GET リクエストを送り JSON を返す。失敗時は最大2回リトライし、それでも失敗なら例外。"""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                wait = RETRY_WAIT_SECONDS * (attempt + 1)
                logger.warning(
                    "HTTP取得に失敗 (%s, 試行 %d/%d)。%.1f秒後にリトライします: %s",
                    url, attempt + 1, MAX_RETRIES + 1, wait, exc,
                )
                time.sleep(wait)
    assert last_error is not None
    raise last_error
