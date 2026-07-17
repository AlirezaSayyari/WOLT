import threading
import time
from collections.abc import Callable


class RateLimiter:
    def __init__(self, interval_seconds: float, clock: Callable[[], float] = time.monotonic):
        if interval_seconds < 0:
            raise ValueError("interval_seconds cannot be negative")
        self._interval = interval_seconds
        self._clock = clock
        self._last_allowed: dict[tuple[int, str], float] = {}
        self._lock = threading.Lock()

    def allow(self, listen_port: int, mac_address: str) -> bool:
        key = (listen_port, mac_address)
        now = self._clock()
        with self._lock:
            previous = self._last_allowed.get(key)
            if previous is not None and now - previous < self._interval:
                return False
            self._last_allowed[key] = now
            return True
