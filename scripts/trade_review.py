# -*- coding: utf-8 -*-
"""
实盘账户周末复盘工具 (Trade Review)
====================================
读取券商导出的成交流水 xls, 做 FIFO 配对, 输出纪律 dashboard + 历史趋势。

用法:
  python scripts/trade_review.py                       # 用默认数据跑, 快速模式
  python scripts/trade_review.py docs/xxx.xls          # 指定数据文件
  python scripts/trade_review.py --pattern             # 额外拉热门票K线做形态分析(慢)
  python scripts/trade_review.py --note "本周开始执行准入清单"  # 加备注

输出:
  docs/trade-review/output/review_YYYY-MM-DD.md   # 本次复盘报告
  docs/trade-review/history.json                  # 历史指标快照(用于趋势)

设计原则: 盯纪律, 不盯选股。核心是 4 个指标(胜率/盈亏比/每笔期望/大单占比)翻正。
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta

import pandas as pd

# 屏蔽代理, 避免拉K线时被本地代理干扰
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_XLS = os.path.join(ROOT, "docs", "A股交易数据导出.xls")
OUT_DIR = os.path.join(ROOT, "docs", "trade-review", "output")
HISTORY = os.path.join(ROOT, "docs", "trade-review", "history.json")


# ============================================================
# 1. 数据加载与清洗
# ============================================================
def load_trades(xls_path: str) -> pd.DataFrame:
    """读取券商导出 xls(实为 GBK TSV), 清洗成标准 DataFrame。"""
    df = pd.read_csv(xls_path, sep="\t", encoding="gbk", dtype=str)
    df.columns = ["code", "name", "flag", "date", "time", "price", "qty", "amount", "tid", "oid", "acct"]

    def strip_formula(s):
        if pd.isna(s):
            return s
        s = str(s).strip()
        return s[2:-1] if s.startswith('="') else s

    for c in ["code", "name", "tid", "acct"]:
        df[c] = df[c].map(strip_formula)
    for c in ["price", "qty", "amount"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["dt"] = pd.to_datetime(df["date"] + " " + df["time"], format="%Y%m%d %H:%M:%S", errors="coerce")
    df["donly"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.sort_values("dt").reset_index(drop=True)

    def side(x):
        x = str(x)
        if "买入" in x:
            return "B"
        if "卖出" in x or "限价卖" in x:
            return "S"
        return "X"

    df["side"] = df["flag"].map(side)
    return df


# ============================================================
# 2. FIFO 配对
# ============================================================
def pair_fifo(tr: pd.DataFrame) -> pd.DataFrame:
    """对买卖流水做 FIFO 配对, 得到每笔完整交易(round-trip)。"""
    lots = defaultdict(deque)
    rounds = []
    for _, r in tr.iterrows():
        c = r.code
        q = abs(r.qty)
        p = r.price
        d = r.donly
        t = r["dt"]
        if r.side == "B":
            lots[c].append([q, p, d, t, r["name"]])
        else:
            rem = q
            while rem > 0:
                if not lots[c]:
                    break
                lot = lots[c][0]
                m = min(rem, lot[0])
                rounds.append(dict(
                    code=c, name=lot[4], buy_date=lot[2], buy_dt=lot[3], sell_date=d, sell_dt=t,
                    qty=m, buy_price=lot[1], sell_price=p, cost=m * lot[1], sell=m * p,
                    pnl=m * (p - lot[1]), ret_pct=(p / lot[1] - 1) * 100,
                    hold_days=(d - lot[2]).days if pd.notna(d) and pd.notna(lot[2]) else None,
                ))
                lot[0] -= m
                rem -= m
                if lot[0] <= 1e-9:
                    lots[c].popleft()
    rdf = pd.DataFrame(rounds)
    rdf["buy_hour"] = rdf["buy_dt"].dt.hour * 60 + rdf["buy_dt"].dt.minute
    return rdf


# ============================================================
# 3. 指标计算
# ============================================================
def core_metrics(rdf: pd.DataFrame) -> dict:
    n = len(rdf)
    if n == 0:
        return {}
    win = rdf[rdf.pnl > 0]
    loss = rdf[rdf.pnl <= 0]
    pnl_sum = rdf.pnl.sum()
    cost_sum = rdf.cost.sum()
    win_rate = len(win) / n * 100
    avg_win = win.pnl.mean() if len(win) else 0
    avg_loss = abs(loss.pnl.mean()) if len(loss) else 1
    payoff = avg_win / avg_loss if avg_loss else 0
    expectancy = win_rate / 100 * avg_win - (1 - win_rate / 100) * avg_loss
    return dict(
        trades=n, pnl=pnl_sum, cost=cost_sum, ret_total=pnl_sum / cost_sum * 100,
        win_rate=win_rate, payoff=payoff, expectancy=expectancy,
        avg_win=avg_win, avg_loss=-avg_loss, max_win=rdf.pnl.max(), max_loss=rdf.pnl.min(),
    )


def discipline_metrics(rdf: pd.DataFrame, tr: pd.DataFrame) -> dict:
    """交易纪律: 大单占比 / 连亏加码 / 补仓摊平 / 尾盘占比。"""
    # 大单占比 (>=5万)
    big = (rdf.cost >= 50000).sum()
    big_pct = big / len(rdf) * 100 if len(rdf) else 0
    huge = rdf[rdf.cost >= 100000]
    huge_pnl = huge.pnl.sum() if len(huge) else 0

    # 连续亏损后加码: 按 sell_dt 排序, 找连续>=2笔亏损后, 下一笔仓位是否>中位
    s = rdf.sort_values("sell_dt").reset_index(drop=True)
    med_cost = s.cost.median()
    streak_loss_trades = 0
    streak_loss_addup = 0
    for i in range(2, len(s)):
        if s.loc[i - 1, "pnl"] <= 0 and s.loc[i - 2, "pnl"] <= 0:
            streak_loss_trades += 1
            if s.loc[i, "cost"] > med_cost:
                streak_loss_addup += 1

    # 补仓摊平: 原始流水中, 在持仓亏损(买入价<持仓均价)时加仓的次数
    pos = {}  # code -> [qty, cost]
    avg_downs = 0
    avg_down_codes = set()
    for _, r in tr.iterrows():
        c = r.code
        if r.side == "B":
            q = abs(r.qty)
            if c in pos and pos[c][0] > 0:
                avg_price = pos[c][1] / pos[c][0]
                if r.price < avg_price * 0.999:  # 加仓价低于持仓成本 = 亏损摊薄
                    avg_downs += 1
                    avg_down_codes.add(c)
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

    # 尾盘买入占比 (14:45 后)
    late = (rdf.buy_hour >= 14 * 60 + 45).sum()
    late_pct = late / len(rdf) * 100 if len(rdf) else 0
    # 开盘35分钟追涨占比
    early = ((rdf.buy_hour >= 9 * 60 + 25) & (rdf.buy_hour < 10 * 60)).sum()
    early_pct = early / len(rdf) * 100 if len(rdf) else 0

    return dict(
        big_order_pct=big_pct, big_orders=int(big), huge_pnl=huge_pnl,
        streak_loss_trades=streak_loss_trades, streak_loss_addup=streak_loss_addup,
        avg_downs=avg_downs, avg_down_codes=len(avg_down_codes),
        late_buy_pct=late_pct, early_buy_pct=early_pct,
    )


def friction_metrics(rdf: pd.DataFrame, tr: pd.DataFrame, df: pd.DataFrame) -> dict:
    """交易摩擦: 频率 / 换手 / 估算成本 / 交易股票数。"""
    span_days = (df.donly.max() - df.donly.min()).days
    months = span_days / 30.4
    buy_amt = tr[tr.side == "B"].amount.sum()
    sell_amt = tr[tr.side == "S"].amount.sum()
    turnover = buy_amt + sell_amt
    stamp = sell_amt * 0.0005
    comm = turnover * 0.00025
    transfer = turnover * 0.00001
    cost = stamp + comm + transfer
    trade_days = tr.donly.nunique()
    return dict(
        months=months, trades_per_month=len(rdf) / months if months else 0,
        orders_per_day=len(tr) / trade_days if trade_days else 0,
        n_stocks=tr.code.nunique(), turnover=turnover, est_cost=cost,
        orders=len(tr),
    )


def monthly_curve(rdf: pd.DataFrame) -> pd.DataFrame:
    s = rdf.copy()
    s["ym"] = s.sell_date.dt.to_period("M")
    return s.groupby("ym").agg(pnl=("pnl", "sum"), trades=("pnl", "size"))


# ============================================================
# 4. 纪律红绿灯
# ============================================================
def signal_light(core, disc) -> tuple:
    """返回 (整体灯色, 各条目状态列表)。盯的是纪律不是收益。"""
    items = []
    # 1. 每笔期望
    e = core["expectancy"]
    items.append(("每笔期望值", e, f"¥{e:,.0f}", "green" if e > 0 else ("yellow" if e > -50 else "red")))
    # 2. 胜率
    wr = core["win_rate"]
    items.append(("胜率", wr, f"{wr:.1f}%", "green" if wr >= 52 else ("yellow" if wr >= 48 else "red")))
    # 3. 盈亏比
    po = core["payoff"]
    items.append(("盈亏比", po, f"{po:.2f}", "green" if po >= 1.2 else ("yellow" if po >= 1.0 else "red")))
    # 4. 大单占比
    bp = disc["big_order_pct"]
    items.append(("大单(≥5万)占比", bp, f"{bp:.1f}%", "green" if bp < 10 else ("yellow" if bp < 20 else "red")))
    # 5. 连亏后加码
    sla = disc["streak_loss_addup"]
    items.append(("连亏后加码笔数", sla, f"{sla}笔", "green" if sla == 0 else ("yellow" if sla <= 5 else "red")))
    # 6. 补仓摊平
    ad = disc["avg_downs"]
    items.append(("亏损加仓(补仓摊平)", ad, f"{ad}次/{disc['avg_down_codes']}只", "green" if ad == 0 else ("yellow" if ad <= 10 else "red")))
    # 7. 月交易笔数
    # (用全局均值做参考, 后续按 trend 判断)

    levels = [it[3] for it in items]
    if "red" in levels:
        overall = "red"
    elif "yellow" in levels:
        overall = "yellow"
    else:
        overall = "green"
    return overall, items


# ============================================================
# 5. 形态分析(可选, 需联网)
# ============================================================
def fetch_kline(code, start="2024-03-01", count=800):
    import requests
    sess = requests.Session()
    sess.trust_env = False
    c = str(code).zfill(6)
    sym = f"sh{c}" if c.startswith("6") else (f"bj{c}" if c.startswith(("4", "8", "9")) else f"sz{c}")
    try:
        r = sess.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                     params={"param": f"{sym},day,{start},,{count},qfq"}, timeout=15)
        d = r.json()
        if d.get("code") != 0:
            return []
        sd = d.get("data", {}).get(sym, {})
        rows = sd.get("qfqday", []) or sd.get("day", [])
        return [dict(date=it[0], close=float(it[2]), vol=float(it[5]) if len(it) > 5 else 0) for it in rows]
    except Exception:
        return []


def pattern_metrics(rdf: pd.DataFrame, hot_codes: list) -> dict:
    """对热门票拉K线, 算 放量比例 / 追涨停比例 / 形态下胜率。"""
    KL = {}
    for i, code in enumerate(hot_codes):
        KL[code] = fetch_kline(code)
        if i % 5 == 0:
            time.sleep(0.3)

    def zt_thr(code):
        c = str(code).zfill(6)
        if c.startswith(("300", "301", "688", "689")):
            return 19.5
        if c.startswith(("8", "4", "9")):
            return 29.5
        return 9.5

    rows = []
    for _, r in rdf.iterrows():
        if r.code not in KL or not KL[r.code]:
            continue
        ks = KL[r.code]
        dates = [k["date"] for k in ks]
        bd = pd.Timestamp(r.buy_date).strftime("%Y-%m-%d")
        if bd not in dates:
            idx = min(range(len(dates)), key=lambda i: abs(pd.Timestamp(dates[i]) - pd.Timestamp(bd)))
            if abs(pd.Timestamp(dates[idx]) - pd.Timestamp(bd)).days > 3:
                continue
        else:
            idx = dates.index(bd)
        if idx < 25:
            continue
        closes = [k["close"] for k in ks]
        vols = [k["vol"] for k in ks]
        day_pct = (closes[idx] - closes[idx - 1]) / closes[idx - 1] * 100
        thr = zt_thr(r.code)
        import numpy as np
        zt5 = sum(1 for j in range(max(1, idx - 4), idx + 1)
                  if (closes[j] - closes[j - 1]) / closes[j - 1] * 100 >= thr - 0.3)
        mv = np.mean(vols[max(0, idx - 20):idx]) if idx >= 20 else vols[idx]
        vr = vols[idx] / mv if mv > 0 else 1
        rows.append(dict(pnl=r.pnl, ret=r.ret_pct, is_zt=int(day_pct >= thr - 0.3),
                         zt5=zt5, vol_ratio=vr))
    F = pd.DataFrame(rows)
    if F.empty:
        return {}
    chase = F[F.zt5 > 0]
    nochase = F[F.zt5 == 0]
    vol_hi = F[F.vol_ratio >= 1.5]
    vol_lo = F[F.vol_ratio < 1.0]
    return dict(
        sample=len(F),
        chase_n=len(chase), chase_win=(chase.pnl > 0).mean() * 100 if len(chase) else 0,
        chase_ret=chase.ret.mean() if len(chase) else 0,
        nochase_win=(nochase.pnl > 0).mean() * 100 if len(nochase) else 0,
        vol_hi_win=(vol_hi.pnl > 0).mean() * 100 if len(vol_hi) else 0,
        vol_lo_win=(vol_lo.pnl > 0).mean() * 100 if len(vol_lo) else 0,
        chase_pct=len(chase) / len(F) * 100, vol_hi_pct=len(vol_hi) / len(F) * 100,
    )


# ============================================================
# 6. 历史快照
# ============================================================
def load_history() -> list:
    if os.path.exists(HISTORY):
        try:
            with open(HISTORY, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def append_history(snapshot: dict) -> list:
    hist = load_history()
    hist.append(snapshot)
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    return hist


# ============================================================
# 7. 渲染报告
# ============================================================
LIGHT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def render(args, df, tr, rdf, core, disc, fric, overall, items, monthly, pat, prev):
    L = []
    a = L.append
    span = f"{df.donly.min().date()} ~ {df.donly.max().date()}"
    a(f"# 实盘复盘 · {args.date_tag}\n")
    if args.note:
        a(f"> **备注**: {args.note}\n")
    a(f"> 数据区间: {span} | 完整配对 {len(rdf)} 笔 | 买卖流水 {len(tr)} 条\n")

    # ---- Dashboard ----
    a("## 🎯 纪律 Dashboard")
    a(f"\n**整体: {LIGHT[overall]} {overall.upper()}**\n")
    a("| 纪律指标 | 当前 | 状态 | 目标 |")
    a("|---|---|---|---|")
    targets = {
        "每笔期望值": ">0 (翻正)",
        "胜率": "≥52%",
        "盈亏比": "≥1.2",
        "大单(≥5万)占比": "<10%",
        "连亏后加码笔数": "0",
        "亏损加仓(补仓摊平)": "0",
    }
    for name, val, disp, lvl in items:
        a(f"| {name} | {disp} | {LIGHT[lvl]} | {targets[name]} |")

    # ---- vs 上次 ----
    if prev:
        a("\n### 📈 vs 上次复盘\n")
        a("| 指标 | 上次 | 本次 | 变化 |")
        a("|---|---|---|---|")
        for k, name in [("pnl", "累计盈亏"), ("win_rate", "胜率%"), ("payoff", "盈亏比"),
                        ("expectancy", "每笔期望"), ("big_order_pct", "大单占比%"), ("avg_downs", "补仓摊平")]:
            old = prev.get(k, 0) or 0
            new = snapshot_get(core, disc, k)
            if new is None:
                continue
            arrow = "📈" if (k in ("pnl", "win_rate", "payoff", "expectancy") and new > old) or \
                    (k in ("big_order_pct", "avg_downs") and new < old) else "📉"
            a(f"| {name} | {old:,.1f} | {new:,.1f} | {arrow} |")

    # ---- 盈利能力 ----
    a("\n## 💰 盈利能力")
    a(f"- 已实现盈亏: **¥{core['pnl']:,.0f}** (收益率 {core['ret_total']:.2f}%)")
    a(f"- 胜率 {core['win_rate']:.1f}% | 盈亏比 {core['payoff']:.2f} | 每笔期望 **¥{core['expectancy']:,.0f}**")
    a(f"- 平均盈利 ¥{core['avg_win']:,.0f} / 平均亏损 ¥{core['avg_loss']:,.0f}")
    a(f"- 最大盈利 ¥{core['max_win']:,.0f} / 最大亏损 ¥{core['max_loss']:,.0f}")

    # ---- 交易纪律(细节) ----
    a("\n## ⚖️ 交易纪律(核心)")
    a(f"- **大单(≥5万)** {disc['big_orders']}笔 占 {disc['big_order_pct']:.1f}% → 其中≥10万的单子合计 ¥{disc['huge_pnl']:,.0f}")
    a(f"- **连亏后加码**: 连续≥2笔亏损后, 又下了 {disc['streak_loss_trades']} 笔, 其中 {disc['streak_loss_addup']} 笔仓位加码(>中位数)")
    a(f"- **补仓摊平**: 在亏损持仓上加仓 {disc['avg_downs']} 次, 涉及 {disc['avg_down_codes']} 只票 ← 账户头号杀手")
    a(f"- **尾盘买入占比** {disc['late_buy_pct']:.1f}% (正期望时段) | **开盘35分钟追涨占比** {disc['early_buy_pct']:.1f}% (负期望)")

    # ---- 摩擦 ----
    a("\n## 🩸 交易摩擦")
    a(f"- 月均 {fric['trades_per_month']:.0f} 笔完整交易 / 每个交易日 {fric['orders_per_day']:.1f} 单 / 涉及 {fric['n_stocks']} 只股票")
    a(f"- 双边周转 ¥{fric['turnover']:,.0f} | 估算交易成本 ¥{fric['est_cost']:,.0f}")

    # ---- 形态 ----
    if pat:
        a("\n## 📊 形态质量(热门票 K 线还原)")
        a(f"- 样本 {pat['sample']} 笔")
        a(f"- 追涨停/近端含涨停 {pat['chase_pct']:.0f}% → 胜率 {pat['chase_win']:.0f}% (强势=对的)")
        a(f"- 缩量冷门 → 胜率 {pat['nochase_win']:.0f}% (弱势=错的)")
        a(f"- 放量(量比≥1.5)占 {pat['vol_hi_pct']:.0f}% → 胜率 {pat['vol_hi_win']:.0f}% | 缩量胜率 {pat['vol_lo_win']:.0f}%")

    # ---- 月度曲线 ----
    a("\n## 📅 月度盈亏")
    cum = 0
    maxabs = max(abs(monthly.pnl).max(), 1)
    for ym, row in monthly.iterrows():
        cum += row.pnl
        bar = "█" * max(1, int(abs(row.pnl) / maxabs * 25))
        sign = "+" if row.pnl >= 0 else "-"
        a(f"- {ym} {sign}¥{abs(row.pnl):>9,.0f} {bar} (累计 ¥{cum:,.0f})")

    # ---- 行动清单 ----
    a("\n## ✅ 下周行动清单")
    actions = []
    if disc["avg_downs"] > 0:
        actions.append(f"🔴 **零补仓**: 本周又出现 {disc['avg_downs']} 次亏损加仓 → 下周任何浮亏单禁止加仓, 加仓唯一前提=浮盈+趋势延续")
    if disc["big_order_pct"] >= 15:
        actions.append(f"🔴 **单笔≤5万**: 大单占 {disc['big_order_pct']:.0f}% → 下周单笔仓位硬上限 5 万, 建议主力仓位 1-3 万")
    if disc["streak_loss_addup"] > 0:
        actions.append(f"🟡 **连亏2笔停手**: 本周连亏后加码 {disc['streak_loss_addup']} 笔 → 设规则: 连续 2 笔亏损强制停手一天")
    if disc["early_buy_pct"] > 30:
        actions.append(f"🟡 **避开开盘**: 开盘 35 分钟追涨占 {disc['early_buy_pct']:.0f}% → 下周买入集中在 10:00 后 / 14:00 后")
    if fric["trades_per_month"] > 30:
        actions.append(f"🟡 **降频**: 月均 {fric['trades_per_month']:.0f} 笔 → 下周目标 ≤ 15 笔, 只做符合准入清单的票")
    if core["payoff"] < 1.0:
        actions.append("🟡 **让利润奔跑**: 盈亏比 < 1 → 盈利单延后止盈到 +8%, 亏损单铁律 -5% 止损")
    if not actions:
        actions.append("🟢 本周纪律全部达标, 保持! 重点转向优化选股胜率。")
    for x in actions:
        a(f"- {x}")

    a("\n---")
    a(f"*生成于 {datetime.now():%Y-%m-%d %H:%M} | 数据: {args.xls}*")
    return "\n".join(L)


def snapshot_get(core, disc, k):
    if k in core:
        return core[k]
    if k in disc:
        return disc[k]
    return None


def make_snapshot(core, disc, args) -> dict:
    return dict(
        date=args.date_tag, pnl=round(core["pnl"], 2), win_rate=round(core["win_rate"], 1),
        payoff=round(core["payoff"], 3), expectancy=round(core["expectancy"], 2),
        big_order_pct=round(disc["big_order_pct"], 1), avg_downs=disc["avg_downs"],
        note=args.note,
    )


# ============================================================
# 8. main
# ============================================================
def main():
    ap = argparse.ArgumentParser(description="实盘账户周末复盘工具")
    ap.add_argument("xls", nargs="?", default=DEFAULT_XLS, help="券商导出的 xls 路径")
    ap.add_argument("--pattern", action="store_true", help="额外拉热门票K线做形态分析(慢, 需联网)")
    ap.add_argument("--note", default="", help="本次复盘备注")
    ap.add_argument("--no-history", action="store_true", help="不追加历史快照")
    args = ap.parse_args()
    args.xls = os.path.abspath(args.xls)
    if not os.path.exists(args.xls):
        print(f"[ERR] 找不到数据文件: {args.xls}")
        sys.exit(1)
    args.date_tag = datetime.now().strftime("%Y-%m-%d")

    print(f"[1/5] 读取 {os.path.basename(args.xls)} ...")
    df = load_trades(args.xls)
    tr = df[df.side.isin(["B", "S"])].copy()
    print(f"      流水 {len(df)} 条, 买卖 {len(tr)} 条")

    print("[2/5] FIFO 配对 ...")
    rdf = pair_fifo(tr)
    print(f"      完整配对 {len(rdf)} 笔")

    print("[3/5] 计算指标 ...")
    core = core_metrics(rdf)
    disc = discipline_metrics(rdf, tr)
    fric = friction_metrics(rdf, tr, df)
    monthly = monthly_curve(rdf)
    overall, items = signal_light(core, disc)

    pat = {}
    if args.pattern:
        print("[4/5] 拉热门票 K 线做形态(可能需 1-2 分钟) ...")
        hot = rdf.code.value_counts()
        hot_codes = hot[hot >= 5].index.tolist()
        pat = pattern_metrics(rdf, hot_codes)
        print(f"      形态样本 {pat.get('sample', 0)} 笔")
    else:
        print("[4/5] 跳过形态分析(加 --pattern 启用)")

    print("[5/5] 渲染报告 + 更新历史 ...")
    prev = None
    if not args.no_history:
        hist = load_history()
        prev = hist[-1] if hist else None
        snap = make_snapshot(core, disc, args)
        append_history(snap)

    report = render(args, df, tr, rdf, core, disc, fric, overall, items, monthly, pat, prev)
    os.makedirs(OUT_DIR, exist_ok=True)
    # 同一天多次跑, 加时间后缀
    tag = args.date_tag if (not args.no_history) else args.date_tag + "-" + datetime.now().strftime("%H%M")
    out_path = os.path.join(OUT_DIR, f"review_{tag}.md")
    if os.path.exists(out_path):
        out_path = os.path.join(OUT_DIR, f"review_{args.date_tag}-{datetime.now().strftime('%H%M')}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    # 终端摘要(ASCII 安全)
    print("\n" + "=" * 50)
    print(f"  整体: {overall.upper()} | 胜率 {core['win_rate']:.1f}% | 盈亏比 {core['payoff']:.2f}")
    print(f"  每笔期望: {core['expectancy']:,.0f} RMB | 大单占比: {disc['big_order_pct']:.1f}%")
    print(f"  补仓摊平: {disc['avg_downs']}次 | 连亏加码: {disc['streak_loss_addup']}笔")
    print("=" * 50)
    print(f"报告: {out_path}")
    if not args.no_history:
        print(f"历史: {HISTORY}")


if __name__ == "__main__":
    main()
