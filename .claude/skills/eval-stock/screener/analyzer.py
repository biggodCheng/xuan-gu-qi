# -*- coding: utf-8 -*-
"""分析层 — 趋势新高/涨停/缩量回踩/市值门槛 纯函数。"""

RECENT_HIGH_DAYS = 20   # 近一月窗口（交易日）
LOOKBACK = 100          # 新高回看交易日
RECENT_ZT_DAYS = 15
SHRINK_RATIO = 0.8
MIN_PULLBACK_DAYS = 2
MKTCAP_THRESHOLD = 500  # 亿元
SUPPORT_WINDOW = 10        # 承接观察窗口（近 N 交易日）
SUPPORT_LOOKBACK = 20      # 支撑基准回看（回调前平台）
SUPPORT_TOLERANCE = 0.98   # 不破支撑容忍度（防假跌破）
LOWER_SHADOW_RATIO = 0.5   # 长下影阈值（下影占振幅比）；0.5 较宽松，对称十字星(open==close 居中)恰=0.5 也会命中
SUPPORT_HIT_THRESHOLD = 2  # "承接有力"命中信号门槛


def check_new_high(kline: list[dict],
                   recent_days: int = RECENT_HIGH_DAYS,
                   lookback: int = LOOKBACK) -> dict:
    """近 recent_days 内任一天创该日前 lookback 日新高 → 通过。

    优先标"今日新高"，否则标"近N日前 创新高"，否则标"距高点 -X%"。
    """
    if len(kline) < lookback + 1:
        return {"pass": False, "label": "数据不足", "detail": f"K线仅 {len(kline)} 根"}

    today_close = kline[-1]["close"]
    # 今日是否新高（与前 lookback 根比）
    if today_close >= max(d["close"] for d in kline[-(lookback + 1):-1]):
        return {"pass": True, "label": "今日新高",
                "detail": f"今日 {today_close:.2f} 创 {lookback} 日新高"}

    # 近 recent_days 内是否曾新高（从最近往远找，取最近一次）
    for i in range(len(kline) - 1, len(kline) - recent_days - 1, -1):
        before = kline[max(0, i - lookback):i]
        if kline[i]["close"] >= max(d["close"] for d in before):
            days_ago = len(kline) - 1 - i
            return {"pass": True,
                    "label": f"近 {days_ago} 日前 {kline[i]['date']} 创 {lookback} 日新高",
                    "detail": f"当日 {kline[i]['close']:.2f}"}

    high_recent = max(d["close"] for d in kline[-lookback:])
    pct = (today_close / high_recent - 1) * 100 if high_recent else 0
    return {"pass": False, "label": f"距高点 {pct:.1f}%",
            "detail": f"近 {recent_days} 日均未创新高"}


def check_recent_zt(kline: list[dict], threshold: float,
                    recent_days: int = RECENT_ZT_DAYS) -> dict:
    """近 recent_days 天内单日涨幅(close vs prev_close) >= threshold。"""
    if len(kline) < 2:
        return {"pass": False, "count": 0, "label": "无", "dates": [], "_raw": []}
    window = kline[-(recent_days + 1):]
    raw = []
    for i in range(1, len(window)):
        prev = window[i - 1]["close"]
        if prev <= 0:
            continue
        chg = (window[i]["close"] - prev) / prev * 100
        if chg >= threshold:
            raw.append({"date": window[i]["date"], "chg": round(chg, 2),
                        "close": window[i]["close"], "volume": window[i]["volume"]})
    if raw:
        date_str = "、".join(z["date"][5:] for z in raw[:5])
        label = f"{len(raw)} 次（{date_str}）"
    else:
        label = "无"
    return {
        "pass": len(raw) > 0,
        "count": len(raw),
        "label": label,
        "dates": [{"date": z["date"], "chg": z["chg"]} for z in raw],
        "_raw": raw,
    }


def check_pullback(kline: list[dict], zt_raw: list[dict],
                   shrink_ratio: float = SHRINK_RATIO,
                   min_days: int = MIN_PULLBACK_DAYS) -> dict:
    """策略1：最后一次涨停后连续 close<zt_close 且 volume<prev*shrink_ratio。"""
    if not zt_raw:
        return {"pass": False, "label": "无近期涨停"}
    lz = zt_raw[-1]
    zt_date, zt_close = lz["date"], lz["close"]
    idx = next((i for i, d in enumerate(kline) if d["date"] == zt_date), None)
    if idx is None:
        return {"pass": False, "label": "涨停日不在K线"}
    after = kline[idx + 1:]
    if len(after) < min_days:
        return {"pass": False, "label": "涨停后交易日不足"}

    best_len = cur_len = 0
    best_start = cur_start = -1
    for i in range(len(after)):
        if after[i]["close"] >= zt_close:
            cur_start, cur_len = -1, 0
            continue
        if cur_start == -1:
            cur_start, cur_len = i, 1
        elif after[i]["volume"] < after[i - 1]["volume"] * shrink_ratio:
            cur_len += 1
        else:
            if cur_len > best_len:
                best_len, best_start = cur_len, cur_start
            cur_start, cur_len = i, 1
    if cur_len > best_len:
        best_len, best_start = cur_len, cur_start

    if best_len >= min_days and best_start >= 0:
        seg = after[best_start:best_start + best_len]
        fv = seg[0]["volume"]
        ratio = seg[-1]["volume"] / fv if fv > 0 else 0
        return {"pass": True,
                "label": f"{seg[0]['date']} 起 {best_len} 天，量比 {ratio:.2f}"}
    return {"pass": False, "label": "未形成缩量回踩"}


def check_marketcap(total: float | None, circ: float | None = None,
                    threshold: float = MKTCAP_THRESHOLD) -> dict:
    if total is None:
        return {"pass": False, "label": "市值数据不可用", "total": None, "circ": circ}
    return {"pass": total < threshold,
            "label": f"{total:.0f} 亿" + (f" / 流通 {circ:.0f} 亿" if circ else ""),
            "total": total, "circ": circ}


def check_support(kline: list[dict]) -> dict:
    """承接 3 信号：下跌缩量 / 不破支撑 / 砸盘收回(长下影代理)。

    返回 {hit_count, signals, label, detail}。pass 键按 hit_count 三态：
    >= SUPPORT_HIT_THRESHOLD → True（✅）；==0 → False（❌）；
    ==1 或数据不足(None) → 省略该键（下游靠"有 pass 键"判通过/失败，无 pass 键视为中性 ➖）。

    signals 字段([s1,s2,s3] 布尔)供调试/未来扩展，reporter 当前不消费。
    """
    need = SUPPORT_WINDOW + SUPPORT_LOOKBACK
    if len(kline) < need:
        return {"hit_count": None, "label": "数据不足",
                "detail": f"K线仅 {len(kline)} 根，需 ≥{need}"}

    start = len(kline) - SUPPORT_WINDOW
    recent = kline[start:]
    base = kline[start - SUPPORT_LOOKBACK:start]

    # 信号1：下跌缩量 — 近窗口内存在 close<prev_close 且 volume<prev*SHRINK_RATIO
    s1 = False
    s1_ratio = None
    for i in range(start, len(kline)):
        prev = kline[i - 1]
        if kline[i]["close"] < prev["close"] and prev["volume"] > 0 and kline[i]["volume"] > 0:
            ratio = kline[i]["volume"] / prev["volume"]
            if ratio < SHRINK_RATIO:
                s1, s1_ratio = True, ratio
                break

    # 信号2：不破支撑 — 近窗口最低价 ≥ 前段(近10日之前20日)最低价 × 容忍度
    #         注：固定窗口近似，非真实平台支撑；持续下跌股此基准为下跌中途低点
    base_low = min(d["low"] for d in base)
    recent_low = min(d["low"] for d in recent)
    s2 = recent_low >= base_low * SUPPORT_TOLERANCE

    # 信号3：砸盘收回 — 近窗口内存在长下影K（下影占振幅 ≥ LOWER_SHADOW_RATIO）
    s3 = False
    s3_ratio = None
    for d in recent:
        hi, lo = d["high"], d["low"]
        if hi <= lo:
            continue
        ratio = (min(d["open"], d["close"]) - lo) / (hi - lo)
        if ratio >= LOWER_SHADOW_RATIO:
            s3, s3_ratio = True, ratio
            break

    signals = [s1, s2, s3]
    hit = sum(signals)
    names = []
    if s1: names.append("缩量")
    if s2: names.append("不破支撑")
    if s3: names.append("砸盘收回")

    detail_parts = []
    if s1_ratio is not None:
        detail_parts.append(f"量比{s1_ratio:.2f}")
    detail_parts.append(f"低{recent_low:.2f}/撑{base_low:.2f}")
    if s3_ratio is not None:
        detail_parts.append(f"下影{s3_ratio:.2f}")
    detail = "；".join(detail_parts)

    if hit >= SUPPORT_HIT_THRESHOLD:
        return {"hit_count": hit, "signals": signals, "pass": True,
                "label": f"有力（{hit}/3：{'、'.join(names)}）", "detail": detail}
    if hit == 0:
        return {"hit_count": 0, "signals": signals, "pass": False,
                "label": "弱（0/3）", "detail": detail}
    return {"hit_count": 1, "signals": signals,
            "label": f"一般（1/3：{names[0]}）", "detail": detail}
