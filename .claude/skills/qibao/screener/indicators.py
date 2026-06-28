from __future__ import annotations


def ma(values: list[float], n: int) -> list[float | None]:
    """简单移动平均。不足 n 日的位置为 None。"""
    result: list[float | None] = [None] * len(values)
    for i in range(n - 1, len(values)):
        result[i] = sum(values[i - n + 1: i + 1]) / n
    return result


def ema(values: list[float], n: int) -> list[float]:
    """指数移动平均，从首个值开始递推（与通达信 EMA 一致）。"""
    if not values:
        return []
    alpha = 2 / (n + 1)
    result = [0.0] * len(values)
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result
