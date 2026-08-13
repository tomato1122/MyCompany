"""共通フィクスチャ・ヘルパ。

方針:
- 実ネットワークアクセスは行わない(http.get_json / requests.get をモック)
- 時刻依存は固定日時 FIXED_NOW を基準にし、flaky にしない
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from coupon_collector.models import Coupon

#: テスト全体で使う固定基準時刻(UTC)
FIXED_NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=timezone.utc)


def make_coupon(
    id: str = "test-0001",
    source: str = "test",
    title: str = "テストクーポン",
    expires_at=None,
    **kwargs,
) -> Coupon:
    """テスト用 Coupon を簡潔に生成する。"""
    return Coupon(id=id, source=source, title=title, expires_at=expires_at, **kwargs)


@pytest.fixture
def fixed_now() -> datetime:
    return FIXED_NOW


@pytest.fixture
def future() -> datetime:
    """FIXED_NOW から見て未来(有効)の期限。"""
    return FIXED_NOW + timedelta(days=30)


@pytest.fixture
def past() -> datetime:
    """FIXED_NOW から見て過去(期限切れ)の期限。"""
    return FIXED_NOW - timedelta(days=1)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """テスト中の実 HTTP アクセスを全面的に禁止する安全網。"""

    def _blocked(*args, **kwargs):  # pragma: no cover - 呼ばれたらテストの誤り
        raise AssertionError("テスト中の実ネットワークアクセスは禁止です")

    monkeypatch.setattr("requests.sessions.Session.request", _blocked)
