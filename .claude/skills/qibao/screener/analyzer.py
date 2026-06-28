from __future__ import annotations

from screener.indicators import boll_upper, cross, hhv, llv, ma, macd

MIN_HISTORY = 40          # 布林(20)+MACD(26+9) warmup 留余量
BOLL_N = 20
BOLL_W = 2
VOL_MA_N = 5
XUSHI_AMP = 0.15          # 蓄势横盘：前期20日振幅阈值
VOL_MA_RATIO = 1.5        # 蓄势放量：vol > MA(vol,5)*1.5
BOOM_VOL_MULT = 2         # 起爆倍量：vol > 前期5日最高量*2


def analyze_qibao(kline_data: list[dict]) -> dict | None:
    """检查最近一个交易日是否为起爆点。

    Args:
        kline_data: [{date,open,high,low,close,volume}, ...] 按日期正序

    Returns:
        起爆命中返回结果 dict，否则 None。
    """
    n = len(kline_data)
    if n < MIN_HISTORY:
        return None

    highs = [d["high"] for d in kline_data]
    lows = [d["low"] for d in kline_data]
    closes = [d["close"] for d in kline_data]
    volumes = [d["volume"] for d in kline_data]
    opens = [d["open"] for d in kline_data]

    last = n - 1
    prev = n - 2

    boll_up = boll_upper(closes, BOLL_N, BOLL_W)
    ma_vol = ma(volumes, VOL_MA_N)
    dif, dea = macd(closes)
    hhv_vol = hhv(volumes, VOL_MA_N)

    # 起爆条件（均看末根）
    b1 = cross(closes, boll_up)[last]                       # B1 收盘上穿布林上轨
    b2 = volumes[last] > hhv_vol[prev] * BOOM_VOL_MULT      # B2 倍量
    b3 = dif[last] > dea[last] and dif[last] > 0            # B3 MACD 水上金叉状态

    if not (b1 and b2 and b3):
        return None

    # 蓄势条件
    # A1 横盘：起爆日之前 20 日的 high/low 振幅 < 阈值（不含起爆日大涨）
    prev_highs = highs[last - BOLL_N:last]
    prev_lows = lows[last - BOLL_N:last]
    a1 = (max(prev_highs) / min(prev_lows) - 1) < XUSHI_AMP
    # A2 放量阳线：末根 vol > MA(vol,5)*1.5 且收阳
    a2 = volumes[last] > ma_vol[last] * VOL_MA_RATIO and closes[last] > opens[last]
    xushi = bool(a1 and a2)

    pct_chg = (closes[last] - closes[prev]) / closes[prev]
    vol_ratio = volumes[last] / ma_vol[last] if ma_vol[last] else 0.0

    signals = ["起爆"]
    if xushi:
        signals.append("兼蓄势")

    return {
        "close": round(closes[last], 4),
        "pct_chg": round(pct_chg * 100, 2),
        "vol_ratio": round(vol_ratio, 2),
        "boll_breakout": True,
        "macd_above_zero": dif[last] > 0,
        "xushi": xushi,
        "signals": signals,
    }


def filter_qibao(stocks: list[dict], kline_map: dict[str, list[dict]]) -> list[dict]:
    """批量筛选起爆股。

    Args:
        stocks: [{code, name, ...}, ...]（来自上游创新高 JSON）
        kline_map: {code: [{date,open,high,low,close,volume}, ...]}

    Returns:
        [{code, name, close, pct_chg, vol_ratio, boll_breakout,
          macd_above_zero, xushi, signals}, ...]
    """
    result = []
    for stock in stocks:
        code = stock["code"]
        kline = kline_map.get(code, [])
        if not kline:
            continue
        hit = analyze_qibao(kline)
        if hit is None:
            continue
        result.append({"code": code, "name": stock["name"], **hit})
    return result
