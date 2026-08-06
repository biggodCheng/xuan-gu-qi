# -*- coding: utf-8 -*-
"""watchlist 跟踪票复盘脚本 (2026-07-29)。
读本地 vipdoc 日K(不复权), 计算每只票的均线/量能/偏离/承接, 输出复盘表。
记忆约束: 量能需双口径(今/昨 + 今/5日); GBK控制台要 reconfigure utf-8。
"""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # scripts/

from local_kline import read_day

# (sym, 名称, 上次记录日期, 上次记录价, 标签)
STOCKS = [
    ("sh600267", "海正药业", "07-20", 12.45,  "医药·企稳等待"),
    ("sh600900", "长江电力", "07-23", 28.94,  "电力·底仓首选"),
    ("sh601985", "中国核电", "07-23", 9.09,   "电力·防御中军"),
    ("sh600011", "华能国际", "07-23", 7.43,   "电力·弹性候选"),
    ("sz000938", "紫光股份", "07-27", 41.47,  "AI算力·等回踩"),
    ("sz002293", "罗莱生活", "07-21", 11.85,  "抗跌·防御消费"),
    ("sh688065", "凯赛生物", "07-21", 45.80,  "抗跌·生制"),
    ("sh600060", "海信视像", "07-21", 27.65,  "抗跌·黑电"),
    ("bj920438", "戈碧迦",   "07-21", 126.61, "抗跌·北交高危"),
    ("sh688019", "安集科技", "07-27", 264.90, "长鑫·次选最稳"),
    ("sz002409", "雅克科技", "07-27", 169.35, "长鑫·弹性高危"),
]
# 情绪/规避标的(非买入, 看结果)
SENTIMENT = [
    ("sz002879", "002879情绪", None, None, "5板分歧节点"),
    ("sz300117", "300117规避", None, None, "连跌停"),
    ("bj920680", "920680规避", None, None, "连跌停"),
    ("sh603221", "603221情绪", None, None, "一字板"),
]


def ma(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def fmt(x, p=2):
    return f"{x:+.{p}f}" if x is not None else "  -  "


def analyze(sym, name, last_date, last_price, tag, verbose=True):
    rows = read_day(sym)
    if not rows:
        print(f"  ⚠️ {sym} {name}: 本地无数据")
        return
    # 只取最近 30 根够算 MA20 + 5日均量
    rows = rows[-30:]
    closes = [r["close"] for r in rows]
    vols = [r["volume"] for r in rows]
    dates = [r["date"] for r in rows]

    today = rows[-1]
    yest = rows[-2]
    chg_today = (today["close"] - yest["close"]) / yest["close"] * 100

    m5, m10, m20 = ma(closes, 5), ma(closes, 10), ma(closes, 20)
    bull = m5 and m10 and m20 and m5 > m10 > m20

    # 量能双口径(用成交量手)
    vol_today = today["volume"]
    vol_yest = yest["volume"]
    vol5_mean = sum(vols[-6:-1]) / 5 if len(vols) >= 6 else None  # 前5日(不含今)
    vr_yl = vol_today / vol_yest if vol_yest else None
    vr_5d = vol_today / vol5_mean if vol5_mean else None

    # 距均线偏离
    d_m5 = (today["close"] - m5) / m5 * 100 if m5 else None
    d_m10 = (today["close"] - m10) / m10 * 100 if m10 else None
    d_m20 = (today["close"] - m20) / m20 * 100 if m20 else None

    # 近20日高低(承接/破前低判定用)
    win = closes[-20:] if len(closes) >= 20 else closes
    hi20 = max(win)
    lo20 = min(win)
    lo5 = min(closes[-5:])
    from_high20 = (today["close"] - hi20) / hi20 * 100
    from_low20 = (today["close"] - lo20) / lo20 * 100

    # vs 上次记录价
    vs_last = (today["close"] - last_price) / last_price * 100 if last_price else None

    print(f"### {name} · {sym[2:]} — {tag}")
    print(f"- 最新: {today['date']} 收 {today['close']:.2f} (今 {fmt(chg_today)}%)")
    print(f"- 均线: MA5={m5:.2f} MA10={m10:.2f} MA20={m20:.2f} | 多头排列: {'是↑' if bull else '否'}")
    print(f"- 偏离: 距MA5 {fmt(d_m5)}% | 距MA10 {fmt(d_m10)}% | 距MA20 {fmt(d_m20)}%")
    print(f"- 量能: 今/昨={vr_yl:.2f} 今/5日={vr_5d:.2f} | 成交量 {vol_today}")
    print(f"- 近端: 20日高 {hi20:.2f}(距 {fmt(from_high20)}%) 20日低 {lo20:.2f}(距 {fmt(from_low20)}%) 近5日低 {lo5:.2f}")
    if vs_last is not None:
        print(f"- vs 上次记录({last_date}={last_price}): {fmt(vs_last)}%")
    print()


print("=" * 70)
print("## 一、跟踪票复盘 (11 只活跃)")
print("=" * 70)
for s in STOCKS:
    analyze(*s)

print("=" * 70)
print("## 二、情绪/规避标的 (非买入, 看结果判市况)")
print("=" * 70)
for s in SENTIMENT:
    analyze(*s)
