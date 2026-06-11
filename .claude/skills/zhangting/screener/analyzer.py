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


def get_board_threshold(code: str) -> float:
    """根据股票代码判断板块，返回对应的涨停阈值。

    - 主板（600/601/603/000/001/002/003）：涨跌幅限制 10%，阈值 9.5%
    - 科创板（688）：涨跌幅限制 20%，阈值 19.5%
    - 创业板（300/301）：涨跌幅限制 20%，阈值 19.5%
    - 北交所（920/8/4）：涨跌幅限制 30%，阈值 29.5%
    """
    # 科创板
    if code.startswith("688"):
        return 19.5
    # 创业板
    if code.startswith(("300", "301")):
        return 19.5
    # 北交所
    if code.startswith(("920", "8", "4")):
        return 29.5
    # 主板（及其他）
    return 9.5


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


def _parse_date(date_str: str):
    """解析日期字符串，支持 YYYY-MM-DD 和 YYYYMMDD 格式。"""
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def filter_limit_ups(
    stocks: list[dict],
    kline_map: dict[str, list[dict]],
    threshold: float = 9.5,
    days_back: int = 15,
) -> list[dict]:
    """筛选有涨停的股票。

    Args:
        stocks: [{code, name, close, ...}, ...]
        kline_map: {code: [{date, close}, ...], ...}
        threshold: 涨停阈值（%），当使用 get_board_threshold 按板块区分时忽略此参数
        days_back: 向前查找的自然日天数，默认15天

    Returns:
        [{code, name, zt_dates, zt_pcts, close}, ...]
    """
    from datetime import timedelta

    result = []
    failed_codes = []
    for stock in stocks:
        code = stock["code"]
        kline = kline_map.get(code, [])
        if not kline:
            failed_codes.append(code)
            continue

        # 以K线最新日期为基准，向前推 days_back 天
        latest_date = _parse_date(kline[-1]["date"])
        if latest_date is None:
            failed_codes.append(code)
            continue
        cutoff_date = latest_date - timedelta(days=days_back)

        board_threshold = get_board_threshold(code)
        zt_days = find_limit_ups(kline, board_threshold)

        # 只保留 cutoff_date 之后的涨停
        zt_days_filtered = []
        for d in zt_days:
            zt_date = _parse_date(d["date"])
            if zt_date and zt_date >= cutoff_date:
                zt_days_filtered.append(d)

        if not zt_days_filtered:
            continue

        result.append({
            "code": code,
            "name": stock["name"],
            "zt_dates": [d["date"] for d in zt_days_filtered],
            "zt_pcts": [d["pct_change"] for d in zt_days_filtered],
            "close": stock["close"],
        })

    if failed_codes:
        print(f"  [警告] {len(failed_codes)} 只股票K线数据获取失败: {', '.join(failed_codes)}", flush=True)

    return result
