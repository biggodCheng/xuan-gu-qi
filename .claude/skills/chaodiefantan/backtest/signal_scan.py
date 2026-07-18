"""信号扫描与去重 — 逐日切片复用 is_oversold_rebound 判定信号,同波去重。

去重: 同股 window 个交易日内重复信号只留最早一个(同一波反弹)。
"""
from screener.analyzer import is_oversold_rebound  # noqa: F401  (scan_signals 用,Task5)

DEDUP_WINDOW = 5  # 同股去重窗口(交易日)


def dedup_signals(signals: list[dict], trading_dates: list[str],
                  window: int = DEDUP_WINDOW) -> list[dict]:
    """同股 window 个交易日内的信号只保留最早一个。

    Args:
        signals: 信号列表(可乱序)。
        trading_dates: 全局交易日序列(升序),用于算交易日 index 差。
        window: 去重窗口(交易日数)。
    """
    date_idx = {d: i for i, d in enumerate(trading_dates)}
    ordered = sorted(signals, key=lambda s: (s["code"], s["signal_date"]))
    result: list[dict] = []
    last_date_by_code: dict[str, str] = {}
    for s in ordered:
        code, d = s["code"], s["signal_date"]
        if d not in date_idx:
            continue  # 信号日不在交易日序列(异常),丢弃
        last = last_date_by_code.get(code)
        if last is not None and date_idx[d] - date_idx[last] <= window:
            continue  # 同波,跳过
        result.append(s)
        last_date_by_code[code] = d
    return result
