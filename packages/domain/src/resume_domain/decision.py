"""打招呼决策。"""

from __future__ import annotations


def should_greet(score: int, threshold: int) -> bool:
    """分数达到阈值则打招呼。"""

    return score >= threshold
