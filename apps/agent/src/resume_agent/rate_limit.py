"""限速。"""

from __future__ import annotations

import random
import time


def sleep_action_delay(min_ms: int, max_ms: int) -> None:
    low = max(0, min_ms)
    high = max(low, max_ms)
    time.sleep(random.randint(low, high) / 1000.0)
