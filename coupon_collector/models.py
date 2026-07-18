"""クーポンのドメインモデル。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

#: 日本標準時。国内クーポンの有効期限は JST 前提で扱う。
JST = timezone(timedelta(hours=9), name="JST")


def now_utc() -> datetime:
    """タイムゾーン付きの現在時刻(UTC)を返す。"""
    return datetime.now(timezone.utc)


def make_coupon_id(source: str, unique_key: str) -> str:
    """source + ソース内固有キーから安定したクーポンIDを生成する。"""
    digest = hashlib.sha256(f"{source}:{unique_key}".encode("utf-8")).hexdigest()
    return f"{source}-{digest[:16]}"


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """naive な datetime は JST とみなして aware に変換する。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=JST)
    return dt


def parse_datetime(value: Any) -> Optional[datetime]:
    """ISO 8601 文字列 / datetime / None を aware datetime に正規化する。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, str):
        try:
            return _ensure_aware(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None


@dataclass
class Coupon:
    """1件のクーポン情報。"""

    id: str
    source: str
    title: str
    description: str = ""
    shop_name: str = ""
    discount: str = ""
    url: str = ""
    expires_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=now_utc)

    def __post_init__(self) -> None:
        self.expires_at = parse_datetime(self.expires_at)
        self.fetched_at = parse_datetime(self.fetched_at) or now_utc()

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """有効期限切れなら True。期限未設定(None)は有効扱い。"""
        if self.expires_at is None:
            return False
        return self.expires_at < (now or now_utc())

    def to_dict(self) -> dict[str, Any]:
        """JSON/CSV 保存用の辞書表現(datetime は ISO 8601 文字列)。"""
        data = asdict(self)
        data["expires_at"] = self.expires_at.isoformat() if self.expires_at else None
        data["fetched_at"] = self.fetched_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Coupon":
        """to_dict の逆変換。未知のキーは無視する。"""
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        return cls(**{k: v for k, v in data.items() if k in known})


#: CSV 出力などで使う列順
COUPON_FIELDS = [
    "id",
    "source",
    "title",
    "description",
    "shop_name",
    "discount",
    "url",
    "expires_at",
    "fetched_at",
]
