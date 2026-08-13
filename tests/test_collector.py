"""collector.py のユニットテスト(スキップ・重複除去・期限切れ除外)。"""

from __future__ import annotations

from datetime import timedelta

import pytest

from coupon_collector import collector
from coupon_collector.collector import collect, filter_active
from coupon_collector.models import Coupon
from coupon_collector.sources.base import CouponSource
from tests.conftest import FIXED_NOW, make_coupon


class FakeSource(CouponSource):
    """テスト用ソース。設定状態・返却内容・例外を制御できる。"""

    def __init__(self, name="fake", coupons=None, configured=True, error=None):
        self._name = name
        self._coupons = coupons or []
        self._configured = configured
        self._error = error
        self.fetch_called = 0

    @property
    def name(self) -> str:
        return self._name

    def is_configured(self) -> bool:
        return self._configured

    def fetch(self) -> list[Coupon]:
        self.fetch_called += 1
        if self._error is not None:
            raise self._error
        return list(self._coupons)


@pytest.fixture(autouse=True)
def freeze_time_and_sleep(monkeypatch):
    """now_utc を固定し、ソース間ウェイトの実 sleep を記録のみに置換する。"""
    monkeypatch.setattr(collector, "now_utc", lambda: FIXED_NOW)
    sleeps: list[float] = []
    monkeypatch.setattr(collector.time, "sleep", sleeps.append)
    yield sleeps


def _valid(id_: str) -> Coupon:
    return make_coupon(id=id_, expires_at=FIXED_NOW + timedelta(days=7))


class TestCollect:
    def test_empty_sources(self):
        assert collect([]) == []

    def test_collects_from_all_sources(self):
        s1 = FakeSource("s1", [_valid("a")])
        s2 = FakeSource("s2", [_valid("b")])
        result = collect([s1, s2])
        assert {c.id for c in result} == {"a", "b"}

    def test_unconfigured_source_is_skipped_without_fetch(self):
        skipped = FakeSource("nokey", [_valid("x")], configured=False)
        active = FakeSource("ok", [_valid("y")])
        result = collect([skipped, active])
        assert [c.id for c in result] == ["y"]
        assert skipped.fetch_called == 0

    def test_fetch_error_skips_only_that_source(self):
        s1 = FakeSource("ok1", [_valid("a")])
        broken = FakeSource("broken", error=RuntimeError("API down"))
        s2 = FakeSource("ok2", [_valid("b")])
        result = collect([s1, broken, s2])
        assert {c.id for c in result} == {"a", "b"}
        assert s2.fetch_called == 1

    def test_all_sources_fail_returns_empty(self):
        result = collect([FakeSource("x", error=ValueError("boom"))])
        assert result == []

    def test_duplicate_ids_first_source_wins(self):
        c1 = make_coupon(id="dup", title="先勝ち", expires_at=FIXED_NOW + timedelta(days=1))
        c2 = make_coupon(id="dup", title="後発", expires_at=FIXED_NOW + timedelta(days=1))
        result = collect([FakeSource("s1", [c1]), FakeSource("s2", [c2, _valid("other")])])
        by_id = {c.id: c for c in result}
        assert len(result) == 2
        assert by_id["dup"].title == "先勝ち"

    def test_duplicates_within_single_source_deduped(self):
        c = _valid("same")
        result = collect([FakeSource("s", [c, c, c])])
        assert len(result) == 1

    def test_expired_coupons_excluded(self):
        expired = make_coupon(id="old", expires_at=FIXED_NOW - timedelta(seconds=1))
        valid = _valid("new")
        no_expiry = make_coupon(id="forever", expires_at=None)
        result = collect([FakeSource("s", [expired, valid, no_expiry])])
        assert {c.id for c in result} == {"new", "forever"}

    def test_boundary_expiry_exactly_now_is_kept(self):
        # 収集開始時刻ちょうどが期限のクーポンは有効扱い(is_expired の < 比較)
        c = make_coupon(id="edge", expires_at=FIXED_NOW)
        assert [x.id for x in collect([FakeSource("s", [c])])] == ["edge"]

    def test_source_returning_empty_list(self):
        assert collect([FakeSource("s", [])]) == []


class TestWaitBetweenSources:
    def test_no_sleep_for_single_source(self, freeze_time_and_sleep):
        collect([FakeSource("s1", [_valid("a")])])
        assert freeze_time_and_sleep == []

    def test_sleep_inserted_between_fetches(self, freeze_time_and_sleep):
        collect([FakeSource("s1", [_valid("a")]), FakeSource("s2", [_valid("b")])])
        assert freeze_time_and_sleep == [collector.WAIT_BETWEEN_SOURCES]

    def test_no_sleep_when_prior_sources_skipped(self, freeze_time_and_sleep):
        # 未設定スキップのみが先行する場合、最初の実 fetch 前に待たない
        collect([
            FakeSource("nokey", configured=False),
            FakeSource("real", [_valid("a")]),
        ])
        assert freeze_time_and_sleep == []


class TestFilterActive:
    def test_filters_with_explicit_now(self):
        coupons = [
            make_coupon(id="past", expires_at=FIXED_NOW - timedelta(days=1)),
            make_coupon(id="future", expires_at=FIXED_NOW + timedelta(days=1)),
            make_coupon(id="none", expires_at=None),
        ]
        active = filter_active(coupons, now=FIXED_NOW)
        assert [c.id for c in active] == ["future", "none"]

    def test_empty_list(self):
        assert filter_active([], now=FIXED_NOW) == []
