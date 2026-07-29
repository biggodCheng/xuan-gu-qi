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


def classify_volume(vr, amp, seal, yizi=False, bd=None):
    """量能标签。vr=量比, amp=振幅(百分比, 如5.8表示5.8%), seal=封板强度, yizi=是否一字。
    bd=板块(main/cyb/kcb/bj): 爆量烂板的振幅阈值按板块折算(主板>5%/创业·科创>10%/北交>15%),
    因创业科创20%涨停振幅天然大。返回 ∈ {一字缩量, 缩量, 温和放量, 爆量烂板, 放量}。"""
    amp_bad = 10.0 if bd in ("cyb", "kcb") else (15.0 if bd == "bj" else 5.0)
    if yizi and vr < 0.8 and amp < 1:
        return "一字缩量"
    if vr < 0.8:
        return "缩量"
    if vr > 3 and amp > amp_bad and seal < 0.99:
        return "爆量烂板"
    if 1.0 <= vr <= 2.5 and seal >= 0.99:
        return "温和放量"
    if vr > 2.5:
        return "放量"
    return "温和放量"  # vr 0.8-1.0 兜底归温和


def _sector_stats(industry):
    """统计某行业当日成分股表现(本地 vipdoc)。返回 {zt:涨停数, median:中位涨幅%}。可被测试 mock。"""
    imap = industry_map.load_map()
    codes = [c for c, ind in imap.items() if ind == industry]
    chgs = []
    zt = 0
    for code in codes:
        for pre in ("sh", "sz", "bj"):
            rows = local_kline.read_day(f"{pre}{code}")
            if len(rows) >= 2 and rows[-1]["close"] > 0 and rows[-2]["close"] > 0:
                chg = (rows[-1]["close"] - rows[-2]["close"]) / rows[-2]["close"]
                chgs.append(chg)
                bd = local_kline._classify_a_share(f"{pre}{code}")
                limit = 0.30 if bd == "bj" else (0.20 if bd in ("cyb", "kcb") else 0.10)
                if chg >= limit * 0.97:
                    zt += 1
                break
    if not chgs:
        return {"zt": 0, "median": 0}
    chgs.sort()
    median = chgs[len(chgs) // 2] * 100
    return {"zt": zt, "median": round(median, 2)}


def classify_sector(sym):
    """板块联动判定。sym(如 sz000428) → 行业 → 该行业当日成分股统计。
    返回 {"label": str, "stats": {...}}。label ∈ {独狼, 齐涨(情绪), 板块漂移, 映射缺失}。"""
    code = sym[-6:]  # 取后6位代码 (sh/sz/bj 前缀或纯代码都兼容)
    imap = industry_map.load_map()
    industry = imap.get(code)
    if not industry:
        return {"label": "映射缺失", "stats": {}}
    stats = _sector_stats(industry)
    if stats["zt"] >= 3 or stats["median"] > 4:
        return {"label": "齐涨(情绪)", "stats": stats}
    if stats["zt"] <= 1 and stats["median"] < 2:
        return {"label": "独狼", "stats": stats}
    return {"label": "板块漂移", "stats": stats}


def _suggest(shape, volume, sector):
    """三层客观标签 → 建议归类(参考·需人工确认)。顺序优先, 先命中先返回。"""
    if shape == "超跌反抽" and volume == "爆量烂板":
        return "出货烂板"
    if volume == "一字缩量":
        return "消息板"
    if sector == "齐涨(情绪)":
        return "情绪板"
    if shape == "底部平台突破" and volume == "温和放量" and sector == "独狼":
        return "底部反转苗头"
    if shape == "横盘突破" and volume == "温和放量" and sector == "独狼":
        return "资金板苗头"
    return "混合"


def _limit_of_bd(bd):
    return 0.30 if bd == "bj" else (0.20 if bd in ("cyb", "kcb") else 0.10)


def label(sym, height=1):
    """综合判定: 读本地K + 算量能 + 三层标签 + 建议归类。
    sym: sh/sz/bj + 6位代码。height: 连板高度(默认1=首板)。
    返回 dict {sym, shape, volume, sector, suggest, metrics} 或 {sym, error}。"""
    kl = local_kline.read_day(sym)
    if len(kl) < 2:
        return {"sym": sym, "error": "无本地数据"}

    sh = classify_shape(kl, height)

    today, prev = kl[-1], kl[-2]
    if prev["close"] <= 0:
        return {"sym": sym, "error": "前收异常"}
    bd = local_kline._classify_a_share(sym) or "main"
    limit = _limit_of_bd(bd)
    chg = (today["close"] - prev["close"]) / prev["close"]
    seal = chg / limit if limit > 0 else 0
    avg5v = sum(r["volume"] for r in kl[-6:-1]) / 5 if len(kl) >= 6 else today["volume"]
    vr = today["volume"] / avg5v if avg5v > 0 else 0
    amp = (today["high"] - today["low"]) / today["low"] * 100 if today["low"] > 0 else 0
    yizi = amp < 1.1 and today["open"] >= prev["close"] * (1 + limit * 0.95)

    vol = classify_volume(vr=round(vr, 2), amp=round(amp, 2),
                          seal=round(seal, 2), yizi=yizi, bd=bd)
    sec = classify_sector(sym)
    suggest = _suggest(sh["label"], vol, sec["label"])

    return {
        "sym": sym, "shape": sh["label"], "volume": vol,
        "sector": sec["label"], "suggest": suggest,
        "metrics": {**sh["metrics"], "vr": round(vr, 2),
                    "seal": round(seal, 2), "amp": round(amp, 2)},
    }
