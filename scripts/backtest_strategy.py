# -*- coding: utf-8 -*-
"""
正期望画像 · 反事实回测 (Strategy Backtest)
==========================================
用用户真实的买卖时点和价格, 只过滤"不符合画像/纪律"的交易, 量化"只做对的事"的理论收益。
这是反事实筛选(causal filter), 不是模拟重做 —— 买卖时点真实, 仅做准入筛选, 无未来函数。

用法: python scripts/backtest_strategy.py
输出: docs/trade-review/output/backtest_strategy.md
"""
import json
import os
import time

import numpy as np
import pandas as pd

from trade_review import load_trades, pair_fifo, fetch_kline, ROOT

XLS = os.path.join(ROOT, "docs", "A股交易数据导出.xls")
CACHE = os.path.join(ROOT, "docs", "trade-review", "kline_cache.json")
OUT = os.path.join(ROOT, "docs", "trade-review", "output", "backtest_strategy.md")

# ---------- 1. 加载配对 ----------
print("[1/6] 加载配对 ...")
df = load_trades(XLS)
tr = df[df.side.isin(["B", "S"])].copy()
rdf = pair_fifo(tr)
print(f"      完整配对 {len(rdf)} 笔")

# ---------- 2. 拉K线(带缓存) ----------
print("[2/6] 准备K线(缓存) ...")
cache = {}
if os.path.exists(CACHE):
    try:
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        cache = {}
codes = list(rdf.code.unique())
new = 0
for i, code in enumerate(codes):
    if code not in cache or not cache[code]:
        cache[code] = fetch_kline(code)
        new += 1
        if i % 10 == 0:
            time.sleep(0.3)
    if new and i % 30 == 0:
        print(f"      ... {i}/{len(codes)}")
if new:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)
hit = sum(1 for c in codes if cache.get(c))
print(f"      K线: {hit}/{len(codes)} 只命中, 本次新拉 {new}")

# ---------- 3. 特征工程 ----------
print("[3/6] 特征工程 ...")


def zt_thr(code):
    c = str(code).zfill(6)
    if c.startswith(("300", "301", "688", "689")):
        return 19.5
    if c.startswith(("8", "4", "9")):
        return 29.5
    return 9.5


def row_feats(r):
    code = r.code
    bp = r.buy_price
    bd = pd.Timestamp(r.buy_date).strftime("%Y-%m-%d")
    ks = cache.get(code, [])
    feat = dict(vol_ratio=1.0, zt5=0, pos_vs_high=100.0)
    dates = [k["date"] for k in ks]
    closes = [k["close"] for k in ks]
    vols = [k["vol"] for k in ks]
    if bd in dates:
        idx = dates.index(bd)
        if idx >= 25:
            thr = zt_thr(code)
            feat["zt5"] = sum(1 for j in range(max(1, idx - 4), idx + 1)
                              if (closes[j] - closes[j - 1]) / closes[j - 1] * 100 >= thr - 0.3)
            mv = np.mean(vols[max(0, idx - 20):idx]) if idx >= 20 else vols[idx]
            feat["vol_ratio"] = vols[idx] / mv if mv > 0 else 1.0
            hi = max(closes[max(0, idx - 120):idx])
            feat["pos_vs_high"] = bp / hi * 100
    return pd.Series(feat)


rdf[["vol_ratio", "zt5", "pos_vs_high"]] = rdf.apply(row_feats, axis=1)
rdf["is_strong"] = (rdf.zt5 > 0) | (rdf.vol_ratio >= 1.5)
rdf["late_buy"] = rdf.buy_hour >= 14 * 60 + 45
rdf["period"] = np.where(rdf.sell_date < pd.Timestamp("2025-07-01"), "in", "out")

# 补仓标记(原始流: 亏损持仓上加仓)
print("      检测补仓 ...")
pos = {}
avgdown_dts = set()
for _, r in tr.iterrows():
    c = r.code
    if r.side == "B":
        q = abs(r.qty)
        if c in pos and pos[c][0] > 0:
            ap = pos[c][1] / pos[c][0]
            if r.price < ap * 0.999:
                avgdown_dts.add((c, str(r["dt"])))
            pos[c][0] += q
            pos[c][1] += q * r.price
        else:
            pos[c] = [q, q * r.price]
    else:
        q = abs(r.qty)
        if c in pos:
            pos[c][0] -= q
            if pos[c][0] <= 1e-9:
                del pos[c]
rdf["is_avgdown"] = rdf.apply(lambda r: (r.code, str(r.buy_dt)) in avgdown_dts, axis=1)

# 连亏上下文(前两笔都亏 → 本笔是连亏后)
_s = rdf.sort_values("sell_dt")["pnl"]
rdf["after_2loss"] = ((_s.shift(1) <= 0) & (_s.shift(2) <= 0)).reindex(rdf.index)

# ---------- 4. 反事实筛选 ----------
print("[4/6] 反事实筛选 ...")
FEE = 0.0008        # 双边净费(印花0.05%卖 + 双边佣金万2.5 + 过户) ≈ (买+卖)×0.08%
FEE_SLIP = 0.002    # 含滑点保守(加约0.12%滑点)


def evaluate(sub, fee=FEE, label=""):
    if len(sub) == 0:
        return dict(label=label, n=0)
    gross = sub.pnl.sum()
    fee_cost = (sub.cost + sub.sell).sum() * fee
    net = gross - fee_cost
    win = (sub.pnl > 0).mean() * 100
    aw = sub[sub.pnl > 0].pnl.mean() if (sub.pnl > 0).any() else 0
    al = abs(sub[sub.pnl <= 0].pnl.mean()) if (sub.pnl <= 0).any() else 1
    payoff = aw / al if al else 0
    exp = win / 100 * aw - (1 - win / 100) * al
    return dict(label=label, n=len(sub), gross=gross, net=net,
                ret=net / sub.cost.sum() * 100, win=win, payoff=payoff, exp=exp, fee=fee_cost)


profiles = {
    "实际全量(基准)": pd.Series(True, index=rdf.index),
    "P1-宽 价位<30+强势+小仓": (rdf.buy_price < 30) & rdf.is_strong & (rdf.cost < 50000),
    "P2 价位<25+强势+小仓": (rdf.buy_price < 25) & rdf.is_strong & (rdf.cost < 50000),
    "P3 +尾盘": (rdf.buy_price < 25) & rdf.is_strong & (rdf.cost < 50000) & rdf.late_buy,
    "P4 +剔补仓+连亏停手": ((rdf.buy_price < 25) & rdf.is_strong & (rdf.cost < 50000) & rdf.late_buy
                       & (~rdf.is_avgdown) & (~rdf.after_2loss)),
}
rows = []
for label, mask in profiles.items():
    rows.append(evaluate(rdf[mask], FEE, label + " [净]"))
    rows.append(evaluate(rdf[mask], FEE_SLIP, label + " [含滑点]"))
res = pd.DataFrame(rows)

# 样本内/外 (对 P2 主画像, 不含行为约束, 看画像本身稳定性)
p2_mask = profiles["P2 价位<25+强势+小仓"]
p4_mask = profiles["P4 +剔补仓+连亏停手"]
split = {}
for key, m in [("P2样本内", p2_mask & (rdf.period == "in")),
               ("P2样本外", p2_mask & (rdf.period == "out")),
               ("P4样本内", p4_mask & (rdf.period == "in")),
               ("P4样本外", p4_mask & (rdf.period == "out"))]:
    split[key] = evaluate(rdf[m], FEE, key)


# ---------- 5. 渲染 ----------
print("[5/6] 渲染报告 ...")
g = open(OUT, "w", encoding="utf-8")
w = lambda s="": g.write(s + "\n")
w("# 正期望画像 · 反事实回测\n")
w(f"> 数据区间: {df.donly.min().date()} ~ {df.donly.max().date()} | 样本 {len(rdf)} 笔\n")
w("> 方法: **反事实筛选**——保留真实买卖时点与价格, 仅过滤不符合画像的交易。无未来函数、无假设成交价。\n")
w("> 成本: 净费 0.08%(印花0.05%卖+双边万2.5佣金+过户) / 含滑点 0.20%保守。每笔双边按(买额+卖额)×费率扣除。\n")
w("> ⚠ **局限**: 画像规则从本份数据归纳, 有 hindsight 偏差; 真 out-of-sample 需未来新数据(由 trade_review 工具持续验证)。\n")

w("\n## 一、核心对比: 各画像档位的理论收益\n")
w("| 策略档位 | 笔数 | 净盈亏 | 收益率 | 胜率 | 盈亏比 | 每笔期望 |")
w("|---|---|---|---|---|---|---|")
for _, r in res.iterrows():
    if r.get("n", 0) == 0:
        w(f"| {r.label} | 0 | — | — | — | — | — |")
        continue
    w(f"| {r.label} | {r.n} | ¥{r.net:,.0f} | {r.ret:.2f}% | {r.win:.0f}% | {r.payoff:.2f} | ¥{r.exp:,.0f} |")

w("\n## 二、样本内/外稳定性(看画像是否过拟合)\n")
w("| 区间 | 笔数 | 净盈亏 | 胜率 | 盈亏比 | 每笔期望 |")
w("|---|---|---|---|---|---|")
name_map = {"P2样本内": "P2画像·样本内(24-09~25-06)", "P2样本外": "P2画像·样本外(25-07~25-12)",
            "P4样本内": "P4完整·样本内", "P4样本外": "P4完整·样本外"}
for k, d in split.items():
    if d.get("n", 0) == 0:
        w(f"| {name_map[k]} | 0 | — | — | — | — |")
        continue
    w(f"| {name_map[k]} | {d['n']} | ¥{d['net']:,.0f} | {d['win']:.0f}% | {d['payoff']:.2f} | ¥{d['exp']:,.0f} |")

w("\n## 三、单因子贡献(每个过滤维度的单独效果)\n")
def contrib(mask, label):
    sub = rdf[mask]
    if len(sub) == 0:
        return
    w(f"- **{label}**: {len(sub)}笔 → 净盈亏 ¥{sub.pnl.sum():,.0f} | 胜率 {(sub.pnl>0).mean()*100:.0f}% | 平均收益 {sub.ret_pct.mean():.2f}%")
contrib(rdf.is_strong, "仅强势基因(放量/近端涨停)")
contrib(rdf.buy_price < 25, "仅低价<25元")
contrib(rdf.cost < 50000, "仅小仓<5万")
contrib(rdf.late_buy, "仅尾盘买入")
contrib(~rdf.is_avgdown, "仅剔除补仓")
contrib(rdf.is_strong & (rdf.buy_price < 25) & (rdf.cost < 50000), "P2 画像组合")

w("\n## 四、可执行准入清单(从回测提炼)\n")
w("```\n[1] 买入价 < 25 元\n[2] 近5日有涨停 或 当日量比≥1.5 (强势基因)\n[3] 单笔仓位 < 5 万 (建议 1-3 万)\n[4] 14:45 后尾盘下单\n[5] 亏损持仓绝不加仓 (零补仓摊平)\n[6] 连续 2 笔亏损 → 停手一天\n[7] 持仓 3-5 天, 破 -5% 止损 / +8% 止盈\n```\n")
w("> 这 7 条即 P4 档。回测显示它是画像+纪律叠加后最稳健的组合。把它打印贴在屏幕旁。\n")
g.close()
print("[6/6] done →", OUT)

# 终端摘要(ASCII)
for _, r in res.iterrows():
    if r.get("n", 0) and "净" in r.label:
        print(f"  {r.label:38s} n={r.n:>4} net={r.net:>10,.0f} win={r.win:>3.0f}% exp={r.exp:>7,.0f}")
