# -*- coding: utf-8 -*-
"""首板成色判定核心库: 形态/量能/板块联动 三层客观标签 + 建议归类。

数据源: 本地 vipdoc (scripts/local_kline.read_day, 零网络) + 东财行业映射 (industry_map)。
纯函数, 可独立测试。供 fupan_strong_scan(连板前N) 和 stock_pattern(单票CLI) 复用。

设计见 docs/superpowers/specs/2026-07-29-stock-pattern-design.md。
注意: 标签是描述性的, 非选股门槛, 禁止做胜率回测调参 (见 spec 非目标)。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import local_kline  # noqa: E402
import industry_map  # noqa: E402


def classify_shape(kl, height=1):
    """形态判定: 本轮上涨启动(首板)的形态。

    kl: [{date,open,high,low,close,volume}, ...] 正序, 末根=最新交易日。
    height: 连板高度(首板=1)。基准日 = 首板前一日 = kl[len-1-height]。
    返回 {"label": str, "metrics": {...}}。
    label ∈ {次新, 底部平台突破, 超跌反抽, 横盘突破, 箱体震荡, 混合}。

    度量(实现优化 spec 4.1): 横盘度用收盘价区间波动率(max-min)/mean,
    而非日内振幅——低价股日内振幅天然偏大失真。阈值15%经华天8.3%/兴欣36%实测标定。
    """
    n = len(kl)
    base = n - 1 - height  # 首板前一日索引
    if n < 62 or base < 60:
        return {"label": "次新", "metrics": {"reason": "数据不足60日"}}

    win = kl[base - 60:base]          # 基准日前60日(不含基准日)
    closes = [r["close"] for r in win]
    peak60 = max(closes)
    peak_idx = closes.index(peak60)
    trough = min(r["close"] for r in win[peak_idx:])  # peak之后到基准日的最低收
    retracement = (peak60 - trough) / peak60 if peak60 > 0 else 0

    v20 = [r["close"] for r in kl[base - 20:base]]    # 基准日前20日收盘
    volatility20 = (max(v20) - min(v20)) / (sum(v20) / len(v20)) if v20 else 0
    peak20 = max(v20) if v20 else 0                    # 末20日最高收(近期平台顶)

    first_board_close = kl[base + 1]["close"]         # 首板日收盘
    breakout = first_board_close / peak60 if peak60 > 0 else 0       # vs 60日前高
    breakout20 = first_board_close / peak20 if peak20 > 0 else 0     # vs 末20日高(近期平台)

    metrics = {
        "volatility20": round(volatility20 * 100, 2),
        "peak60": round(peak60, 2),
        "trough": round(trough, 2),
        "retracement": round(retracement * 100, 2),
        "breakout": round(breakout, 3),
        "breakout20": round(breakout20, 3),
    }

    # 前期跌透(retracement>15%) + 近期筑底(volatility20<15%) + 突破近期平台: 底部反转(华天型)
    if retracement > 0.15 and volatility20 < 0.15 and breakout20 >= 0.99:
        return {"label": "底部平台突破", "metrics": metrics}
    # 前期跌 + 未收复前高: 下跌途中反抽(兴欣型)
    if retracement > 0.15 and breakout < 1.0:
        return {"label": "超跌反抽", "metrics": metrics}
    # 前期无大跌(retracement<10%) + 横盘 + 突破前高: 中高位箱体突破
    if volatility20 < 0.15 and breakout >= 0.99 and retracement < 0.10:
        return {"label": "横盘突破", "metrics": metrics}
    if volatility20 >= 0.15 and retracement < 0.15 and breakout < 0.99:
        return {"label": "箱体震荡", "metrics": metrics}
    return {"label": "混合", "metrics": metrics}
