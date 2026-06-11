from __future__ import annotations

STRATEGIES = {
    "shrinking_volume": "策略1：成交量递减+价格回落",
    "below_average": "策略2：成交量低于均量+价格回落",
    "single_day": "策略3：单日缩量回踩",
}


def strategy_shrinking_volume(
    after_zt: list[dict],
    zt_close: float,
    shrink_ratio: float = 0.8,
    min_days: int = 2,
) -> dict | None:
    """策略1：涨停后连续N天成交量递减且价格低于涨停日收盘价。

    Args:
        after_zt: 涨停日之后的K线数据 [{date, close, volume}, ...]
        zt_close: 涨停日收盘价
        shrink_ratio: 每天成交量相对前一天的比例阈值（默认0.8）
        min_days: 至少连续几天缩量才算命中（默认2）
    """
    if len(after_zt) < min_days:
        return None

    best_start = -1
    best_len = 0
    cur_start = -1
    cur_len = 0

    for i in range(len(after_zt)):
        if after_zt[i]["close"] >= zt_close:
            cur_start = -1
            cur_len = 0
            continue

        if cur_start == -1:
            cur_start = i
            cur_len = 1
        elif after_zt[i]["volume"] < after_zt[i - 1]["volume"] * shrink_ratio:
            cur_len += 1
        else:
            if cur_len > best_len:
                best_start = cur_start
                best_len = cur_len
            cur_start = i
            cur_len = 1

    if cur_len > best_len:
        best_start = cur_start
        best_len = cur_len

    if best_len < min_days or best_start < 0:
        return None

    segment = after_zt[best_start: best_start + best_len]
    last_vol = segment[-1]["volume"]
    first_vol = segment[0]["volume"]
    vol_ratio = last_vol / first_vol if first_vol > 0 else 0

    return {
        "pullback_start_date": segment[0]["date"],
        "pullback_days": best_len,
        "volume_shrink_ratio": round(vol_ratio, 4),
    }


def strategy_below_average(
    after_zt: list[dict],
    before_zt: list[dict],
    zt_close: float,
    ma_days: int = 5,
    volume_ratio: float = 0.6,
) -> dict | None:
    """策略2：涨停后成交量低于涨停前均量的一定比例，且价格回落。

    Args:
        after_zt: 涨停日之后的K线数据
        before_zt: 涨停日之前的K线数据（用于计算均量）
        zt_close: 涨停日收盘价
        ma_days: 均量计算天数（默认5）
        volume_ratio: 低于均量的比例（默认0.6）
    """
    if not before_zt or not after_zt:
        return None

    recent = before_zt[-ma_days:]
    if not recent:
        return None

    avg_vol = sum(d["volume"] for d in recent) / len(recent)
    threshold = avg_vol * volume_ratio

    for d in after_zt:
        if d["close"] < zt_close and d["volume"] < threshold:
            return {
                "pullback_start_date": d["date"],
                "pullback_days": 1,
                "volume_shrink_ratio": round(d["volume"] / avg_vol, 4),
            }

    return None


def strategy_single_day(
    after_zt: list[dict],
    zt_volume: float,
    zt_close: float,
    volume_ratio: float = 0.5,
) -> dict | None:
    """策略3：涨停后某天成交量低于涨停日的volume_ratio倍，且价格回落。

    Args:
        after_zt: 涨停日之后的K线数据
        zt_volume: 涨停日成交量
        zt_close: 涨停日收盘价
        volume_ratio: 相对涨停日成交量的比例（默认0.7）
    """
    if not after_zt or zt_volume <= 0:
        return None

    threshold = zt_volume * volume_ratio

    for d in after_zt:
        if d["close"] < zt_close and d["volume"] < threshold:
            return {
                "pullback_start_date": d["date"],
                "pullback_days": 1,
                "volume_shrink_ratio": round(d["volume"] / zt_volume, 4),
            }

    return None


def analyze_pullback(
    kline_data: list[dict],
    zt_date: str,
    zt_close: float,
    strategy: str,
    **params,
) -> dict | None:
    """分析单只股票是否有缩量回踩。

    Args:
        kline_data: [{date, close, volume}, ...] 按日期正序
        zt_date: 最后一次涨停日
        zt_close: 涨停日收盘价
        strategy: 策略名称
        **params: 策略参数
    """
    zt_idx = None
    for i, d in enumerate(kline_data):
        if d["date"] == zt_date:
            zt_idx = i
            break

    if zt_idx is None:
        return None

    after_zt = kline_data[zt_idx + 1:]
    before_zt = kline_data[:zt_idx]
    zt_volume = kline_data[zt_idx]["volume"]

    if not after_zt:
        return None

    if strategy == "shrinking_volume":
        return strategy_shrinking_volume(
            after_zt, zt_close, **params
        )
    elif strategy == "below_average":
        return strategy_below_average(
            after_zt, before_zt, zt_close, **params
        )
    elif strategy == "single_day":
        return strategy_single_day(
            after_zt, zt_volume, zt_close, **params
        )

    return None


def filter_pullbacks(
    stocks: list[dict],
    kline_map: dict[str, list[dict]],
    strategy: str,
    **params,
) -> list[dict]:
    """筛选缩量回踩的股票。

    Args:
        stocks: [{code, name, zt_dates, zt_pcts, close, last_zt_close}, ...]
        kline_map: {code: [{date, close, volume}, ...], ...}
        strategy: 策略名称
        **params: 策略参数

    Returns:
        [{code, name, last_zt_date, last_zt_close, current_close, ...}, ...]
    """
    result = []
    for stock in stocks:
        code = stock["code"]
        kline = kline_map.get(code, [])
        if not kline:
            continue

        zt_dates = stock.get("zt_dates", [])
        if not zt_dates:
            continue

        last_zt_date = zt_dates[-1]
        zt_pcts = stock.get("zt_pcts", [])
        zt_pct = zt_pcts[-1] if zt_pcts else 10.0

        # 涨停日收盘价：从stock的close反推，或从K线中获取
        zt_close = stock.get("close")
        # 从K线中找到涨停日当天收盘价
        for d in kline:
            if d["date"] == last_zt_date:
                zt_close = d["close"]
                break

        pullback = analyze_pullback(kline, last_zt_date, zt_close, strategy, **params)
        if pullback is None:
            continue

        current_close = kline[-1]["close"] if kline else stock["close"]

        result.append({
            "code": code,
            "name": stock["name"],
            "last_zt_date": last_zt_date,
            "last_zt_close": zt_close,
            "last_zt_pct": zt_pct,
            "current_close": current_close,
            **pullback,
        })

    return result
