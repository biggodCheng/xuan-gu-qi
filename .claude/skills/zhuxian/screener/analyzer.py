def calc_moving_averages(closes: list[float], periods: list[int]) -> dict[int, list[float | None]]:
    """计算简单移动平均线。

    Returns:
        {period: [None, ..., val, ...]}，前 period-1 个为 None。
    """
    result = {}
    for p in periods:
        ma = [None] * len(closes)
        for i in range(p - 1, len(closes)):
            ma[i] = sum(closes[i - p + 1 : i + 1]) / p
        result[p] = ma
    return result


def find_swing_points(kline_data: list[dict], window: int = 5) -> dict:
    """用滚动窗口法识别波段高点和低点。

    一个波段高点是其前后各 window 根 K 线中的最大值。
    一个波段低点是其前后各 window 根 K 线中的最小值。

    Returns:
        {"highs": [{"index", "date", "price"}, ...], "lows": [...]}
    """
    n = len(kline_data)
    highs = []
    lows = []

    for i in range(window, n - window):
        high_vals = [kline_data[j]["high"] for j in range(i - window, i + window + 1) if j != i]
        low_vals = [kline_data[j]["low"] for j in range(i - window, i + window + 1) if j != i]

        is_high = kline_data[i]["high"] > max(high_vals)
        is_low = kline_data[i]["low"] < min(low_vals)

        if is_high:
            highs.append({
                "index": i,
                "date": kline_data[i]["date"],
                "price": kline_data[i]["high"],
            })
        if is_low:
            lows.append({
                "index": i,
                "date": kline_data[i]["date"],
                "price": kline_data[i]["low"],
            })

    return {"highs": highs, "lows": lows}


def check_higher_highs(highs: list[dict]) -> bool:
    """检查最近的波段高点是否递增。"""
    if len(highs) < 2:
        return False
    recent = highs[-3:] if len(highs) >= 3 else highs[-2:]
    return all(recent[i]["price"] < recent[i + 1]["price"] for i in range(len(recent) - 1))


def check_higher_lows(lows: list[dict]) -> bool:
    """检查最近的波段低点是否递增。"""
    if len(lows) < 2:
        return False
    recent = lows[-3:] if len(lows) >= 3 else lows[-2:]
    return all(recent[i]["price"] < recent[i + 1]["price"] for i in range(len(recent) - 1))


def check_ma_bullish(ma_values: dict[int, list[float | None]], idx: int) -> bool:
    """检查 idx 位置均线是否多头排列：MA5 > MA10 > MA20 > MA60。"""
    for p in (5, 10, 20, 60):
        if p not in ma_values or ma_values[p][idx] is None:
            return False
    return ma_values[5][idx] > ma_values[10][idx] > ma_values[20][idx] > ma_values[60][idx]


def calc_trend_score(kline_data: list[dict], swing: dict, ma_values: dict) -> int:
    """综合趋势评分（0-100）。

    Higher Highs:  25 分
    Higher Lows:   25 分
    均线排列:      20 分
    区间涨幅:      15 分
    接近前高:      15 分
    """
    score = 0
    highs = swing["highs"]
    lows = swing["lows"]
    last_idx = len(kline_data) - 1
    closes = [k["close"] for k in kline_data]

    # Higher Highs (25 分)
    if len(highs) >= 2:
        recent_highs = highs[-3:] if len(highs) >= 3 else highs[-2:]
        hh_count = sum(1 for i in range(len(recent_highs) - 1) if recent_highs[i]["price"] < recent_highs[i + 1]["price"])
        if hh_count >= 2:
            score += 25
        elif hh_count == 1:
            score += 15
    # else: 0 分

    # Higher Lows (25 分)
    if len(lows) >= 2:
        recent_lows = lows[-3:] if len(lows) >= 3 else lows[-2:]
        hl_count = sum(1 for i in range(len(recent_lows) - 1) if recent_lows[i]["price"] < recent_lows[i + 1]["price"])
        if hl_count >= 2:
            score += 25
        elif hl_count == 1:
            score += 15

    # 均线排列 (20 分)
    if check_ma_bullish(ma_values, last_idx):
        score += 20
    else:
        # 部分排列：MA5 > MA10 且 MA20 > MA60
        ok = 0
        if ma_values.get(5, [None])[-1] and ma_values.get(10, [None])[-1]:
            if ma_values[5][last_idx] is not None and ma_values[10][last_idx] is not None:
                if ma_values[5][last_idx] > ma_values[10][last_idx]:
                    ok += 1
        if ma_values.get(20, [None])[-1] and ma_values.get(60, [None])[-1]:
            if ma_values[20][last_idx] is not None and ma_values[60][last_idx] is not None:
                if ma_values[20][last_idx] > ma_values[60][last_idx]:
                    ok += 1
        if ok == 2:
            score += 10

    # 区间涨幅 (15 分)
    ret_20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) > 20 and closes[-21] > 0 else 0
    ret_60 = (closes[-1] / closes[-61] - 1) * 100 if len(closes) > 60 and closes[-61] > 0 else 0
    if ret_20 > 0 and ret_60 > 0:
        score += 15
    elif ret_20 > 0 or ret_60 > 0:
        score += 8

    # 接近前高 (15 分)
    if highs:
        recent_high_price = highs[-1]["price"]
        current_close = closes[-1]
        if recent_high_price > 0:
            distance = (recent_high_price - current_close) / recent_high_price * 100
            if distance <= 3:
                score += 15
            elif distance <= 5:
                score += 10
            elif distance <= 10:
                score += 5

    return score


def generate_reason(hh: bool, hl: bool, ma_bullish: bool, ret_20: float, ret_60: float) -> str:
    """生成人类可读的选入原因。"""
    parts = []
    if ma_bullish:
        parts.append("均线多头排列")
    if hh:
        parts.append("近期连续突破前高")
    if hl:
        parts.append("低点逐步抬高")
    if ret_20 > 0:
        parts.append(f"20日涨幅{ret_20:.1f}%")
    if ret_60 > 0:
        parts.append(f"60日涨幅{ret_60:.1f}%")
    return "，".join(parts) if parts else "趋势偏强"


def analyze_sector(kline_data: list[dict], min_score: int = 50) -> dict | None:
    """对单个板块做完整趋势分析。

    Returns:
        分析结果字典，或 None（数据不足或得分不达标）。
    """
    if len(kline_data) < 60:
        return None

    closes = [k["close"] for k in kline_data]
    last_idx = len(kline_data) - 1

    # 均线
    ma_values = calc_moving_averages(closes, [5, 10, 20, 60])

    # 波段点
    swing = find_swing_points(kline_data, window=5)

    # 趋势判断
    hh = check_higher_highs(swing["highs"])
    hl = check_higher_lows(swing["lows"])
    ma_bullish = check_ma_bullish(ma_values, last_idx)

    # 评分
    trend_score = calc_trend_score(kline_data, swing, ma_values)
    if trend_score < min_score:
        return None

    # 区间涨幅
    ret_20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) > 20 and closes[-21] > 0 else 0
    ret_60 = (closes[-1] / closes[-61] - 1) * 100 if len(closes) > 60 and closes[-61] > 0 else 0

    # 最近波段高低点
    recent_high = swing["highs"][-1]["price"] if swing["highs"] else closes[-1]
    prev_high = swing["highs"][-2]["price"] if len(swing["highs"]) >= 2 else recent_high
    recent_low = swing["lows"][-1]["price"] if swing["lows"] else closes[-1]
    prev_low = swing["lows"][-2]["price"] if len(swing["lows"]) >= 2 else recent_low

    return {
        "ma5": round(ma_values[5][last_idx], 2) if ma_values[5][last_idx] else None,
        "ma10": round(ma_values[10][last_idx], 2) if ma_values[10][last_idx] else None,
        "ma20": round(ma_values[20][last_idx], 2) if ma_values[20][last_idx] else None,
        "ma60": round(ma_values[60][last_idx], 2) if ma_values[60][last_idx] else None,
        "recent_high": round(recent_high, 2),
        "prev_high": round(prev_high, 2),
        "recent_low": round(recent_low, 2),
        "prev_low": round(prev_low, 2),
        "trend_score": trend_score,
        "period_return_20d": round(ret_20, 2),
        "period_return_60d": round(ret_60, 2),
        "reason": generate_reason(hh, hl, ma_bullish, ret_20, ret_60),
    }


def rank_sectors(sectors: list[dict], top_n: int = 10) -> list[dict]:
    """按趋势得分排名，取前 N 个。"""
    ranked = sorted(sectors, key=lambda s: (s["trend_score"], s.get("period_return_20d", 0)), reverse=True)
    return ranked[:top_n]
