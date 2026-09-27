"""Defer optional integrations until an operation actually needs them."""
from threading import RLock


class LazyService:
    def __init__(self, name, factory):
        self.name = name
        self.factory = factory
        self.instance = None
        self._lock = RLock()

    def _get(self):
        with self._lock:
            if self.instance is None:
                self.instance = self.factory()
            return self.instance

    def __getattr__(self, attr):
        return getattr(self._get(), attr)
