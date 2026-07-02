# ============================================================
# hearthstone/cache.py — 简单 TTL 缓存，避免频繁请求官网
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(slots=True)
class CacheItem(Generic[T]):
    value: T
    expires_at: datetime


class TtlCache(Generic[T]):
    """进程内 TTL 缓存；高层服务只关心 get/set，不耦合存储细节。"""

    def __init__(self, ttl_seconds: int):
        self.ttl = timedelta(seconds=ttl_seconds)
        self._items: dict[str, CacheItem[T]] = {}

    def get(self, key: str) -> T | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item.expires_at <= datetime.now(timezone.utc):
            self._items.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: T) -> None:
        self._items[key] = CacheItem(
            value=value,
            expires_at=datetime.now(timezone.utc) + self.ttl,
        )

    def clear(self) -> None:
        self._items.clear()
