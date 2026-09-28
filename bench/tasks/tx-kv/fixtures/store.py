"""Naive KV store — starting point. The production contract is in task.md."""
from typing import Any


class StoreError(Exception):
    pass


class MissingKey(StoreError):
    def __init__(self, key):
        super().__init__(f"missing key: {key}")
        self.key = key


class Store:
    def __init__(self):
        self._d: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._check(value)
        self._d[key] = value

    def get(self, key: str) -> Any:
        if key not in self._d:
            raise MissingKey(key)
        return self._d[key]

    def delete(self, key: str) -> None:
        if key not in self._d:
            raise MissingKey(key)
        del self._d[key]

    def keys(self) -> list[str]:
        return sorted(self._d)

    def snapshot(self) -> dict:
        return dict(self._d)

    def _check(self, value) -> None:
        ok = isinstance(value, (str, int)) or (
            isinstance(value, list) and all(isinstance(x, (str, int)) for x in value))
        if not ok:
            raise TypeError("unsupported value type")
