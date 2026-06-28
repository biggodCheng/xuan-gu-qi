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


def std(values: list[float], n: int) -> list[float | None]:
    """总体标准差（除以 N，与通达信 STD 一致）。不足 n 日为 None。"""
    result: list[float | None] = [None] * len(values)
    for i in range(n - 1, len(values)):
        window = values[i - n + 1: i + 1]
        mean = sum(window) / n
        var = sum((x - mean) ** 2 for x in window) / n
        result[i] = var ** 0.5
    return result


def hhv(values: list[float], n: int) -> list[float]:
    """N 日最高（含当日，不足时用所有可用值）。"""
    result = [0.0] * len(values)
    for i in range(len(values)):
        start = max(0, i - n + 1)
        result[i] = max(values[start: i + 1])
    return result


def llv(values: list[float], n: int) -> list[float]:
    """N 日最低（含当日，不足时用所有可用值）。"""
    result = [0.0] * len(values)
    for i in range(len(values)):
        start = max(0, i - n + 1)
        result[i] = min(values[start: i + 1])
    return result


def boll_upper(closes: list[float], n: int = 20, w: float = 2) -> list[float | None]:
    """布林上轨 = MA(closes,n) + w*STD(closes,n)。"""
    ma_vals = ma(closes, n)
    std_vals = std(closes, n)
    return [
        None if (m is None or s is None) else m + w * s
        for m, s in zip(ma_vals, std_vals)
    ]
