def is_new_high(close: float, history: list[float]) -> bool:
    if not history:
        return False
    return close >= max(history)


def filter_new_highs(
    stocks: list[dict],
    histories: dict[str, list[float]],
    min_history: int = 60,
) -> list[dict]:
    """筛选当日收盘价创近期新高的股票。

    Args:
        stocks: 当日行情列表，每项含 code/name/close。
        histories: 每只股票的历史收盘价（不含当日）。
        min_history: 参与判定的最少历史天数。历史数据不足（如数据源对
            个别股票只返回极少几条）时不纳入，避免把无足够历史可比的
            股票误判为新高。默认 60（约 100 个交易日的 60%）。
    """
    result = []
    for stock in stocks:
        code = stock["code"]
        history = histories.get(code, [])
        if len(history) < min_history:
            continue
        if is_new_high(stock["close"], history):
            result.append({
                "code": code,
                "name": stock["name"],
                "close": stock["close"],
                "high_100d": max(history),
            })
    return result
