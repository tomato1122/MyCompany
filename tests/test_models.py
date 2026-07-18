"""models.py のユニットテスト(純粋ロジック)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from coupon_collector.models import (
    COUPON_FIELDS,
    JST,
    Coupon,
    make_coupon_id,
    now_utc,
    parse_datetime,
)
from tests.conftest import FIXED_NOW, make_coupon


class TestMakeCouponId:
    def test_deterministic(self):
        assert make_coupon_id("demo", "key1") == make_coupon_id("demo", "key1")

    def test_format_is_source_prefix_plus_16_hex(self):
        cid = make_coupon_id("hotpepper", "J001234567")
        prefix, digest = cid.rsplit("-", 1)
        assert prefix == "hotpepper"
        assert len(digest) == 16
        int(digest, 16)  # 16進として妥当

    def test_different_keys_differ(self):
        assert make_coupon_id("demo", "a") != make_coupon_id("demo", "b")

    def test_different_sources_differ(self):
        assert make_coupon_id("demo", "a") != make_coupon_id("rakuten", "a")

    def test_source_key_boundary_not_ambiguous(self):
        # "a"+"bc" と "ab"+"c" が同じ連結にならない(区切り文字が効いている)
        assert make_coupon_id("a", "bc") != make_coupon_id("ab", "c")

    def test_unicode_key(self):
        cid = make_coupon_id("rakuten", "クーポン:五割引")
        assert cid.startswith("rakuten-")


class TestParseDatetime:
    def test_none_and_empty_string(self):
        assert parse_datetime(None) is None
        assert parse_datetime("") is None

    def test_invalid_string_returns_none(self):
        assert parse_datetime("not-a-date") is None
        assert parse_datetime("2026-13-99") is None

    def test_non_datetime_type_returns_none(self):
        assert parse_datetime(12345) is None
        assert parse_datetime(["2026-01-01"]) is None

    def test_naive_iso_string_assumed_jst(self):
        dt = parse_datetime("2026-01-15 12:00:00")
        assert dt == datetime(2026, 1, 15, 12, 0, tzinfo=JST)
        assert dt.utcoffset() == timedelta(hours=9)

    def test_aware_iso_string_offset_preserved(self):
        dt = parse_datetime("2026-01-15T12:00:00+00:00")
        assert dt == datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)

    def test_naive_datetime_assumed_jst(self):
        dt = parse_datetime(datetime(2026, 1, 15, 12, 0))
        assert dt.tzinfo is JST

    def test_aware_datetime_passthrough(self):
        src = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        assert parse_datetime(src) is src


class TestNowUtc:
    def test_is_aware_utc(self):
        dt = now_utc()
        assert dt.tzinfo is timezone.utc


class TestCouponPostInit:
    def test_expires_at_string_is_parsed(self):
        c = make_coupon(expires_at="2026-06-01T00:00:00+09:00")
        assert isinstance(c.expires_at, datetime)
        assert c.expires_at.utcoffset() == timedelta(hours=9)

    def test_naive_expires_at_normalized_to_jst(self):
        c = make_coupon(expires_at=datetime(2026, 6, 1, 0, 0))
        assert c.expires_at.tzinfo is JST

    def test_invalid_expires_at_string_becomes_none(self):
        # 仕様: 不正な日時文字列は None(=期限なし・有効扱い)になる
        c = make_coupon(expires_at="garbage")
        assert c.expires_at is None
        assert c.is_expired(FIXED_NOW) is False

    def test_fetched_at_defaults_to_aware_now(self):
        c = make_coupon()
        assert c.fetched_at.tzinfo is not None

    def test_invalid_fetched_at_falls_back_to_now(self):
        c = Coupon(id="x", source="s", title="t", fetched_at="broken")
        assert isinstance(c.fetched_at, datetime)
        assert c.fetched_at.tzinfo is not None


class TestIsExpired:
    def test_no_expiry_is_never_expired(self):
        assert make_coupon(expires_at=None).is_expired(FIXED_NOW) is False

    def test_future_expiry_not_expired(self):
        c = make_coupon(expires_at=FIXED_NOW + timedelta(days=1))
        assert c.is_expired(FIXED_NOW) is False

    def test_past_expiry_expired(self):
        c = make_coupon(expires_at=FIXED_NOW - timedelta(seconds=1))
        assert c.is_expired(FIXED_NOW) is True

    def test_boundary_exactly_at_expiry_is_still_valid(self):
        # 境界値: expires_at == now は「期限切れではない」(厳密な < 比較)
        c = make_coupon(expires_at=FIXED_NOW)
        assert c.is_expired(FIXED_NOW) is False

    def test_boundary_one_microsecond_after(self):
        c = make_coupon(expires_at=FIXED_NOW)
        assert c.is_expired(FIXED_NOW + timedelta(microseconds=1)) is True

    def test_timezone_aware_comparison(self):
        # JST 正午の期限は UTC 3:00 ちょうど。UTC 3:00:01 では期限切れ
        c = make_coupon(expires_at=datetime(2026, 1, 15, 12, 0))  # naive -> JST
        assert c.is_expired(datetime(2026, 1, 15, 2, 59, 59, tzinfo=timezone.utc)) is False
        assert c.is_expired(datetime(2026, 1, 15, 3, 0, 1, tzinfo=timezone.utc)) is True


class TestDictRoundtrip:
    def test_to_dict_serializes_datetimes_to_iso(self):
        c = make_coupon(expires_at=FIXED_NOW, fetched_at=FIXED_NOW)
        d = c.to_dict()
        assert d["expires_at"] == FIXED_NOW.isoformat()
        assert d["fetched_at"] == FIXED_NOW.isoformat()

    def test_to_dict_none_expiry(self):
        assert make_coupon(expires_at=None).to_dict()["expires_at"] is None

    def test_to_dict_keys_match_coupon_fields(self):
        assert set(make_coupon().to_dict().keys()) == set(COUPON_FIELDS)

    def test_roundtrip_preserves_all_fields(self):
        c = Coupon(
            id="demo-abc",
            source="demo",
            title="タイトル",
            description="説明",
            shop_name="店",
            discount="5%OFF",
            url="https://example.com/c",
            expires_at=FIXED_NOW + timedelta(days=3),
            fetched_at=FIXED_NOW,
        )
        restored = Coupon.from_dict(c.to_dict())
        assert restored == c

    def test_roundtrip_none_expiry(self):
        c = make_coupon(expires_at=None, fetched_at=FIXED_NOW)
        assert Coupon.from_dict(c.to_dict()) == c

    def test_from_dict_ignores_unknown_keys(self):
        d = make_coupon(fetched_at=FIXED_NOW).to_dict()
        d["unknown_field"] = "value"
        d["_extra"] = 1
        restored = Coupon.from_dict(d)
        assert restored.id == "test-0001"

    def test_from_dict_missing_required_key_raises(self):
        with pytest.raises(TypeError):
            Coupon.from_dict({"source": "demo", "title": "t"})  # id 欠落
