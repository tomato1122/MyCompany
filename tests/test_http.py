"""http.py のユニットテスト(リトライ・タイムアウト設定・ヘッダ)。

requests.get をモックし、実ネットワークアクセスは行わない。
リトライ間隔の sleep も記録のみに置換して flaky/低速化を防ぐ。
"""

from __future__ import annotations

import pytest
import requests

from coupon_collector import http


class FakeResponse:
    def __init__(self, json_data=None, status_error=None, json_error=None):
        self._json_data = json_data
        self._status_error = status_error
        self._json_error = json_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._json_data


@pytest.fixture
def sleeps(monkeypatch):
    recorded: list[float] = []
    monkeypatch.setattr(http.time, "sleep", recorded.append)
    return recorded


@pytest.fixture
def fake_get(monkeypatch):
    """http.requests.get を差し替え、応答列(または例外)を順に返す。"""

    class Fake:
        def __init__(self):
            self.responses = []
            self.calls = []

        def __call__(self, url, params=None, headers=None, timeout=None):
            self.calls.append({
                "url": url, "params": params, "headers": headers, "timeout": timeout,
            })
            result = self.responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

    fake = Fake()
    monkeypatch.setattr(http.requests, "get", fake)
    return fake


class TestGetJson:
    def test_success_first_attempt(self, fake_get, sleeps):
        fake_get.responses = [FakeResponse({"ok": True})]
        assert http.get_json("https://api.example.com") == {"ok": True}
        assert len(fake_get.calls) == 1
        assert sleeps == []

    def test_sends_user_agent_and_timeout(self, fake_get, sleeps):
        fake_get.responses = [FakeResponse({})]
        http.get_json("https://api.example.com", params={"key": "v"})
        call = fake_get.calls[0]
        assert call["headers"]["User-Agent"] == http.USER_AGENT
        assert call["headers"]["Accept"] == "application/json"
        assert call["timeout"] == http.TIMEOUT_SECONDS
        assert call["params"] == {"key": "v"}

    def test_retries_then_succeeds(self, fake_get, sleeps):
        fake_get.responses = [
            requests.ConnectionError("refused"),
            FakeResponse({"ok": 2}),
        ]
        assert http.get_json("https://api.example.com") == {"ok": 2}
        assert len(fake_get.calls) == 2
        assert sleeps == [http.RETRY_WAIT_SECONDS]

    def test_all_attempts_fail_raises_last_error(self, fake_get, sleeps):
        fake_get.responses = [
            requests.ConnectionError("e1"),
            requests.Timeout("e2"),
            requests.Timeout("e3-last"),
        ]
        with pytest.raises(requests.Timeout, match="e3-last"):
            http.get_json("https://api.example.com")
        assert len(fake_get.calls) == http.MAX_RETRIES + 1  # 計3試行
        # バックオフ: 1.0, 2.0 秒(最後の失敗後は sleep しない)
        assert sleeps == [http.RETRY_WAIT_SECONDS * 1, http.RETRY_WAIT_SECONDS * 2]

    def test_http_error_status_triggers_retry(self, fake_get, sleeps):
        fake_get.responses = [
            FakeResponse(status_error=requests.HTTPError("500 Server Error")),
            FakeResponse({"recovered": True}),
        ]
        assert http.get_json("https://api.example.com") == {"recovered": True}
        assert len(fake_get.calls) == 2

    def test_invalid_json_body_triggers_retry(self, fake_get, sleeps):
        fake_get.responses = [
            FakeResponse(json_error=ValueError("invalid json")),
            FakeResponse({"recovered": True}),
        ]
        assert http.get_json("https://api.example.com") == {"recovered": True}

    def test_invalid_json_exhausts_retries(self, fake_get, sleeps):
        fake_get.responses = [
            FakeResponse(json_error=ValueError("bad body")) for _ in range(3)
        ]
        with pytest.raises(ValueError, match="bad body"):
            http.get_json("https://api.example.com")
