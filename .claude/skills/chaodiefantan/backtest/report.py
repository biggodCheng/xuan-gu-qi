"""报告聚合 + markdown 渲染 — 4 目标对应章节。详见 spec §7。"""

FEE_NET = 0.0008       # 净费(印花0.05%卖+双边万2.5佣金+过户)
FEE_SLIP = 0.002       # 含滑点保守
CAP_BANDS = [(0, 50), (50, 100), (100, 300), (300, 500), (500, float("inf"))]


def compute_trade_returns(trade: dict, fee: float = FEE_NET) -> dict:
    """计算单笔毛/净收益率(%)。fee 按双边(买额+卖额)×fee 扣。"""
    buy, exit_ = trade["buy_price"], trade["exit_price"]
    ret_gross = (exit_ - buy) / buy * 100
    cost_pct = (buy + exit_) / buy * fee * 100     # 双边费占买入价比
    out = dict(trade)
    out["return_gross"] = ret_gross
    out["return_net"] = ret_gross - cost_pct
    return out


def aggregate_overall(trades: list[dict]) -> dict:
    """整体有效性聚合: 胜率/盈亏比/平均持有/最大单笔回撤。"""
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0, "payoff": 0, "avg_hold": 0,
                "avg_ret_net": 0, "avg_ret_gross": 0, "max_drawdown": 0, "wins": 0}
    rets = [t["return_net"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    payoff = avg_win / avg_loss if avg_loss > 0 else float("inf") if wins else 0
    return {
        "n": n,
        "wins": len(wins),
        "win_rate": len(wins) / n * 100,
        "payoff": round(payoff, 2),
        "avg_hold": round(sum(t["hold_days"] for t in trades) / n, 2),
        "avg_ret_net": round(sum(rets) / n, 2),
        "avg_ret_gross": round(sum(t["return_gross"] for t in trades) / n, 2),
        "max_drawdown": round(min(rets), 2) if rets else 0,
    }


def aggregate_by_cap(trades: list[dict]) -> dict:
    """按市值分带聚合(各带 n/胜率/盈亏比/平均净收益)。"""
    out = {}
    for lo, hi in CAP_BANDS:
        sub = [t for t in trades if lo <= t.get("market_cap_T", 0) < hi]
        if not sub:
            out[f"{lo}-{hi}"] = {"n": 0}
            continue
        agg = aggregate_overall(sub)
        out[f"{lo}-{hi}"] = agg
    return out


def render_markdown(overall: dict, overall_open: dict, elasticity: dict,
                    cap_groups: dict, fit: dict, benchmark_ret: float,
                    biases: list[dict]) -> str:
    """渲染 4 目标 markdown 报告。"""
    L = []
    L.append("# 超跌反弹策略回测报告（2024-01 ~ 2026-07）\n")
    L.append("> 探索性小样本分析，结论非统计显著。详见偏差声明。\n")

    # 一、整体有效性
    L.append("## 一、策略整体有效性（主口径：T日收盘买入）\n")
    o = overall
    if o["n"] == 0:
        L.append("无信号。\n")
    else:
        L.append(f"- 信号数: **{o['n']}**  | 胜率: **{o['win_rate']:.0f}%**  | "
                 f"盈亏比: **{o['payoff']}**  | 平均持有: **{o['avg_hold']}日**")
        L.append(f"- 平均每笔净收益: **{o['avg_ret_net']:+.2f}%**  "
                 f"(毛 {o['avg_ret_gross']:+.2f}%)  | 最大单笔回撤: **{o['max_drawdown']:.2f}%**")
        L.append(f"- vs 创业板指同期: **{benchmark_ret:+.2f}%**")
        oo = overall_open
        L.append(f"\n**对照口径（T+1开盘买入）**: n={oo.get('n',0)} "
                 f"胜率 {oo.get('win_rate',0):.0f}% 平均净收益 {oo.get('avg_ret_net',0):+.2f}% "
                 f"(差异大=信号次日普遍高开吞噬收益)")

    # 二、信号弹性
    L.append("\n## 二、信号弹性与最佳持有期\n")
    e = elasticity
    if e.get("n", 0):
        L.append(f"- 固定持有 1/3/5/10 日平均收益: "
                 f"{e['hold_1']:+.2f}% / {e['hold_3']:+.2f}% / "
                 f"{e['hold_5']:+.2f}% / {e['hold_10']:+.2f}%")
        L.append(f"- MFE(平均最大涨幅) **{e['mfe']:+.2f}%** / "
                 f"MAE(平均最大回撤) **{e['mae']:+.2f}%**")
        L.append(f"- 平均实际持有: **{overall['avg_hold']:.1f}日** "
                 f"(短=印证反弹多一日游)")

    # 三、市值阈值
    L.append("\n## 三、市值阈值合理性（分市值带）\n")
    L.append("| 市值带(亿) | 笔数 | 胜率 | 盈亏比 | 平均净收益 |")
    L.append("|---|---|---|---|---|")
    for band, agg in cap_groups.items():
        if agg.get("n", 0) == 0:
            L.append(f"| {band} | 0 | — | — | — |")
        else:
            L.append(f"| {band} | {agg['n']} | {agg['win_rate']:.0f}% | "
                     f"{agg['payoff']} | {agg['avg_ret_net']:+.2f}% |")

    # 四、契合度
    L.append("\n## 四、与实盘契合度\n")
    f = fit
    L.append(f"- 2.5年信号总数 **{f['total_signals']}** ≈ 日均 **{f['per_day']:.2f}个** "
             f"(交易日{f['trading_days']})")
    L.append(f"- 平均持有 **{f['avg_hold']:.1f}日** → 年化换手强度评估")
    L.append(f"- 硬止损①触发占比 **{f['stop_loss_share']:.0%}**，"
             f"避免损失约 **{f['stop_loss_saved']:+.2f}%**/笔")
    L.append("\n> 结合用户'过度交易/不止损/补仓'画像: 信号频率与换手是否助长过度交易，"
             "见正文评估。")

    # 偏差声明
    if biases:
        L.append("\n## 已知偏差声明\n")
        L.append("| 偏差 | 方向 | 说明 |")
        L.append("|---|---|---|")
        for b in biases:
            L.append(f"| {b['name']} | {b['direction']} | {b['note']} |")

    return "\n".join(L)
