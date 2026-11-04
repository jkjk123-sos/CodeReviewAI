# -*- coding: utf-8 -*-
"""进程内 LRU + TTL。缓存键 = 报告内容哈希，命中率靠 fingerprint 稳定。"""
from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    def __init__(self, capacity: int = 256, ttl_s: int = 300) -> None:
        self.capacity = capacity
        self.ttl_s = ttl_s
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    @staticmethod
    def key_of(payload: str) -> str:
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            self.misses += 1
            return None
        ts, value = item
        if time.time() - ts > self.ttl_s:
            self._data.pop(key, None)
            self.misses += 1
            return None
        self._data.move_to_end(key)
        self.hits += 1
        return value

    def put(self, key: str, value: Any) -> None:
        if key in self._data:
            self._data.pop(key)
        self._data[key] = (time.time(), value)
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)
            self.evictions += 1

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"size": len(self._data), "hits": self.hits, "misses": self.misses,
                "evictions": self.evictions,
                "hit_rate": round(self.hits / total, 4) if total else 0.0}
