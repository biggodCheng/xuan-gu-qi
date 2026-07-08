# -*- coding: utf-8 -*-
"""分析层 — 趋势新高/涨停/缩量回踩/市值门槛 纯函数。"""

RECENT_HIGH_DAYS = 20   # 近一月窗口（交易日）
LOOKBACK = 100          # 新高回看交易日
RECENT_ZT_DAYS = 15
SHRINK_RATIO = 0.8
MIN_PULLBACK_DAYS = 2
MKTCAP_THRESHOLD = 200  # 亿元


def check_new_high(kline: list[dict],
                   recent_days: int = RECENT_HIGH_DAYS,
                   lookback: int = LOOKBACK) -> dict:
    """近 recent_days 内任一天创该日前 lookback 日新高 → 通过。

    优先标"今日新高"，否则标"近N日前 创新高"，否则标"距高点 -X%"。
    """
    if len(kline) < lookback + 1:
        return {"pass": False, "label": "数据不足", "detail": f"K线仅 {len(kline)} 根"}

    today_close = kline[-1]["close"]
    # 今日是否新高（与前 lookback 根比，严格高于才算新高）
    if today_close > max(d["close"] for d in kline[-(lookback + 1):-1]):
        return {"pass": True, "label": "今日新高",
                "detail": f"今日 {today_close:.2f} 创 {lookback} 日新高"}

    # 近 recent_days 内是否曾新高（从最近往远找，取最近一次）
    for i in range(len(kline) - 1, len(kline) - recent_days - 1, -1):
        before = kline[max(0, i - lookback):i]
        if kline[i]["close"] > max(d["close"] for d in before):
            days_ago = len(kline) - 1 - i
            return {"pass": True,
                    "label": f"近 {days_ago} 日前 {kline[i]['date']} 创 {lookback} 日新高",
                    "detail": f"当日 {kline[i]['close']:.2f}"}

    high_recent = max(d["close"] for d in kline[-lookback:])
    pct = (today_close / high_recent - 1) * 100 if high_recent else 0
    return {"pass": False, "label": f"距高点 {pct:.1f}%",
            "detail": f"近 {recent_days} 日均未创新高"}
