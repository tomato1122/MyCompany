"""sources/ 配下(demo / hotpepper / rakuten)のユニットテスト。

hotpepper / rakuten は http.get_json をモックし、実 API は一切叩かない。
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from coupon_collector import collector
from coupon_collector import http
from coupon_collector.collector import collect
from coupon_collector.models import make_coupon_id, now_utc
from coupon_collector.sources import ALL_SOURCES, create_sources
from coupon_collector.sources.demo import DemoSource
from coupon_collector.sources.hotpepper import (
    API_KEY_ENV as HP_KEY_ENV,
    API_URL as HP_API_URL,
    DEFAULT_LARGE_AREA,
    HotpepperSource,
    LARGE_AREA_ENV,
)
from coupon_collector.sources.rakuten import (
    API_URL as RK_API_URL,
    APP_ID_ENV,
    DEFAULT_KEYWORD,
    KEYWORD_ENV,
    RakutenSource,
)


@pytest.fixture
def fake_get_json(monkeypatch):
    """http.get_json をモックし、呼び出し記録と応答を制御する。"""

    class Fake:
        def __init__(self):
            self.calls = []
            self.response = {}

        def __call__(self, url, params=None):
            self.calls.append((url, params))
            return self.response

    fake = Fake()
    monkeypatch.setattr(http, "get_json", fake)
    return fake


# ---------------------------------------------------------------- demo


class TestDemoSource:
    def test_always_configured(self):
        assert DemoSource().is_configured() is True

    def test_fetch_returns_four_samples_including_one_expired(self):
        coupons = DemoSource().fetch()
        assert len(coupons) == 4
        expired = [c for c in coupons if c.is_expired()]
        assert len(expired) == 1
        assert "期限切れ" in expired[0].title

    def test_expired_sample_is_filtered_by_collector(self, monkeypatch):
        monkeypatch.setattr(collector.time, "sleep", lambda s: None)
        result = collect([DemoSource()])
        assert len(result) == 3  # 期限切れ1件は保存対象にならないのが正
        assert all(not c.is_expired() for c in result)
        assert make_coupon_id("demo", "expired-sample") not in {c.id for c in result}

    def test_ids_are_stable_across_fetches(self):
        ids1 = [c.id for c in DemoSource().fetch()]
        ids2 = [c.id for c in DemoSource().fetch()]
        assert ids1 == ids2

    def test_no_expiry_sample_exists(self):
        coupons = DemoSource().fetch()
        assert any(c.expires_at is None for c in coupons)


# ---------------------------------------------------------------- hotpepper


def _hp_shop(**over):
    shop = {
        "id": "J001",
        "name": "テスト居酒屋",
        "genre": {"name": "居酒屋", "catch": "ジャンルキャッチ"},
        "catch": "店舗キャッチ",
        "coupon_urls": {"sp": "https://example.com/sp/J001", "pc": "https://example.com/pc/J001"},
    }
    shop.update(over)
    return shop


class TestHotpepperSource:
    def test_not_configured_without_api_key(self, monkeypatch):
        monkeypatch.delenv(HP_KEY_ENV, raising=False)
        assert HotpepperSource().is_configured() is False

    def test_configured_with_api_key(self, monkeypatch):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        assert HotpepperSource().is_configured() is True

    def test_fetch_builds_expected_params(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        monkeypatch.delenv(LARGE_AREA_ENV, raising=False)
        fake_get_json.response = {"results": {"shop": []}}
        HotpepperSource().fetch()
        url, params = fake_get_json.calls[0]
        assert url == HP_API_URL
        assert params["key"] == "dummy-key"
        assert params["format"] == "json"
        assert params["large_area"] == DEFAULT_LARGE_AREA

    def test_large_area_env_override(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        monkeypatch.setenv(LARGE_AREA_ENV, "Z012")
        fake_get_json.response = {"results": {"shop": []}}
        HotpepperSource().fetch()
        assert fake_get_json.calls[0][1]["large_area"] == "Z012"

    def test_response_mapped_to_coupon(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        fake_get_json.response = {"results": {"shop": [_hp_shop()]}}
        coupons = HotpepperSource().fetch()
        assert len(coupons) == 1
        c = coupons[0]
        assert c.id == make_coupon_id("hotpepper", "J001")
        assert c.source == "hotpepper"
        assert c.title == "テスト居酒屋 のクーポン"
        assert c.shop_name == "テスト居酒屋"
        assert c.description == "居酒屋 / 店舗キャッチ"
        assert c.discount == "店舗キャッチ"
        assert c.url == "https://example.com/sp/J001"  # sp 優先
        assert c.expires_at is None

    def test_pc_url_fallback_when_no_sp(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        shop = _hp_shop(coupon_urls={"pc": "https://example.com/pc/J001"})
        fake_get_json.response = {"results": {"shop": [shop]}}
        assert HotpepperSource().fetch()[0].url == "https://example.com/pc/J001"

    def test_shop_without_coupon_url_skipped(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        fake_get_json.response = {
            "results": {"shop": [_hp_shop(coupon_urls={}), _hp_shop(coupon_urls=None)]}
        }
        assert HotpepperSource().fetch() == []

    def test_genre_catch_fallback(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        fake_get_json.response = {"results": {"shop": [_hp_shop(catch="")]}}
        c = HotpepperSource().fetch()[0]
        assert c.discount == "ジャンルキャッチ"

    def test_missing_shop_id_falls_back_to_url_for_id(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        shop = _hp_shop(id="")
        fake_get_json.response = {"results": {"shop": [shop]}}
        c = HotpepperSource().fetch()[0]
        assert c.id == make_coupon_id("hotpepper", "https://example.com/sp/J001")

    def test_api_error_raises_runtime_error(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        fake_get_json.response = {"results": {"error": [{"code": 3000, "message": "APIキー不正"}]}}
        with pytest.raises(RuntimeError, match="ホットペッパーAPIエラー"):
            HotpepperSource().fetch()

    def test_empty_results(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(HP_KEY_ENV, "dummy-key")
        fake_get_json.response = {"results": {}}
        assert HotpepperSource().fetch() == []


# ---------------------------------------------------------------- rakuten


def _rk_item(**over):
    item = {
        "itemCode": "shop:item001",
        "itemName": "テスト商品",
        "itemUrl": "https://example.com/item001",
        "itemCaption": "商品説明です。",
        "shopName": "テストショップ",
        "pointRate": 5,
    }
    item.update(over)
    return item


class TestRakutenSource:
    def test_not_configured_without_app_id(self, monkeypatch):
        monkeypatch.delenv(APP_ID_ENV, raising=False)
        assert RakutenSource().is_configured() is False

    def test_configured_with_app_id(self, monkeypatch):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        assert RakutenSource().is_configured() is True

    def test_fetch_builds_expected_params(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        monkeypatch.delenv(KEYWORD_ENV, raising=False)
        fake_get_json.response = {"Items": []}
        RakutenSource().fetch()
        url, params = fake_get_json.calls[0]
        assert url == RK_API_URL
        assert params["applicationId"] == "dummy-app-id"
        assert params["keyword"] == DEFAULT_KEYWORD

    def test_keyword_env_override(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        monkeypatch.setenv(KEYWORD_ENV, "半額")
        fake_get_json.response = {"Items": []}
        RakutenSource().fetch()
        assert fake_get_json.calls[0][1]["keyword"] == "半額"

    def test_response_mapped_to_coupon(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        fake_get_json.response = {"Items": [{"Item": _rk_item()}]}
        coupons = RakutenSource().fetch()
        assert len(coupons) == 1
        c = coupons[0]
        assert c.id == make_coupon_id("rakuten", "shop:item001")
        assert c.source == "rakuten"
        assert c.title == "テスト商品"
        assert c.shop_name == "テストショップ"
        assert c.discount == "ポイント5倍"
        assert c.url == "https://example.com/item001"
        assert c.expires_at is None

    def test_flat_entry_without_item_wrapper(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        fake_get_json.response = {"Items": [_rk_item()]}
        assert len(RakutenSource().fetch()) == 1

    def test_point_rate_one_means_no_discount_label(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        fake_get_json.response = {"Items": [{"Item": _rk_item(pointRate=1)}]}
        assert RakutenSource().fetch()[0].discount == ""

    def test_caption_truncated_to_200_chars(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        fake_get_json.response = {"Items": [{"Item": _rk_item(itemCaption="あ" * 500)}]}
        assert len(RakutenSource().fetch()[0].description) == 200

    def test_item_without_code_and_url_skipped(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        fake_get_json.response = {"Items": [{"Item": _rk_item(itemCode="", itemUrl="")}]}
        assert RakutenSource().fetch() == []

    def test_missing_item_code_uses_url_for_id(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        fake_get_json.response = {"Items": [{"Item": _rk_item(itemCode="")}]}
        c = RakutenSource().fetch()[0]
        assert c.id == make_coupon_id("rakuten", "https://example.com/item001")

    def test_api_error_raises_runtime_error(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        fake_get_json.response = {
            "error": "wrong_parameter",
            "error_description": "specify valid applicationId",
        }
        with pytest.raises(RuntimeError, match="楽天APIエラー"):
            RakutenSource().fetch()

    def test_empty_items(self, monkeypatch, fake_get_json):
        monkeypatch.setenv(APP_ID_ENV, "dummy-app-id")
        fake_get_json.response = {"Items": []}
        assert RakutenSource().fetch() == []


# ---------------------------------------------------------------- registry


class TestCreateSources:
    def test_default_returns_all_sources(self):
        names = [s.name for s in create_sources()]
        assert names == [cls().name for cls in ALL_SOURCES]

    def test_select_by_name(self):
        sources = create_sources(["demo"])
        assert [s.name for s in sources] == ["demo"]

    def test_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError, match="未知のソース名"):
            create_sources(["nonexistent"])
