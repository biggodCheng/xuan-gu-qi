def calc_daily_returns(kline_data: list[dict]) -> list[dict]:
    """计算每日涨幅。

    Args:
        kline_data: [{date, close}, ...] 按日期正序

    Returns:
        [{date, close, prev_close, pct_change}, ...] 跳过第一天
    """
    if len(kline_data) < 2:
        return []

    result = []
    for i in range(1, len(kline_data)):
        prev_close = kline_data[i - 1]["close"]
        close = kline_data[i]["close"]
        if prev_close <= 0:
            continue
        pct = (close - prev_close) / prev_close * 100
        result.append({
            "date": kline_data[i]["date"],
            "close": close,
            "prev_close": prev_close,
            "pct_change": round(pct, 2),
        })
    return result


def find_limit_ups(kline_data: list[dict], threshold: float = 9.5) -> list[dict]:
    """找出涨幅超过阈值的交易日。

    Returns:
        [{date, pct_change}, ...]
    """
    returns = calc_daily_returns(kline_data)
    return [
        {"date": r["date"], "pct_change": r["pct_change"]}
        for r in returns
        if r["pct_change"] >= threshold
    ]


def filter_limit_ups(
    stocks: list[dict],
    kline_map: dict[str, list[dict]],
    threshold: float = 9.5,
) -> list[dict]:
    """筛选有涨停的股票。

    Args:
        stocks: [{code, name, close, ...}, ...]
        kline_map: {code: [{date, close}, ...], ...}
        threshold: 涨停阈值（%）

    Returns:
        [{code, name, zt_dates, zt_pcts, close}, ...]
    """
    result = []
    for stock in stocks:
        code = stock["code"]
        kline = kline_map.get(code, [])
        if not kline:
            continue

        zt_days = find_limit_ups(kline, threshold)
        if not zt_days:
            continue

        result.append({
            "code": code,
            "name": stock["name"],
            "zt_dates": [d["date"] for d in zt_days],
            "zt_pcts": [d["pct_change"] for d in zt_days],
            "close": stock["close"],
        })

    return result
