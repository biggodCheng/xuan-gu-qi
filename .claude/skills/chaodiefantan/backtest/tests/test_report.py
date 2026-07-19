"""报告聚合与渲染测试。"""
from backtest.report import (
    compute_trade_returns, aggregate_overall, aggregate_by_year, render_markdown)


def _trade(exit_price, buy_price, exit_reason="trailing", hold_days=2,
           market_cap_T=120.0, mode="close"):
    return {"buy_price": buy_price, "exit_price": exit_price,
            "exit_reason": exit_reason, "hold_days": hold_days,
            "market_cap_T": market_cap_T, "mode": mode,
            "code": "000001", "signal_date": "2024-03-12"}


def _t(exit_price, buy_price, date):
    t = _trade(exit_price, buy_price)
    t["signal_date"] = date
    return compute_trade_returns(t, 0.0008)


def test_compute_trade_returns_gross_and_net():
    t = _trade(exit_price=10.6, buy_price=10.0)
    r = compute_trade_returns(t, fee=0.0008)
    assert abs(r["return_gross"] - 6.0) < 0.01
    assert r["return_net"] < r["return_gross"]
    assert r["return_net"] > 5.5


def test_aggregate_overall_metrics():
    trades = [
        compute_trade_returns(_trade(10.6, 10.0), 0.0008),
        compute_trade_returns(_trade(9.5, 10.0), 0.0008),
    ]
    agg = aggregate_overall(trades)
    assert agg["n"] == 2
    assert agg["wins"] == 1
    assert agg["win_rate"] == 50.0
    assert agg["avg_hold"] == 2.0
    assert agg["payoff"] > 0


def test_aggregate_by_year():
    trades = [
        _t(10.6, 10.0, "2018-06-01"),
        _t(9.5, 10.0, "2018-07-01"),
        _t(10.6, 10.0, "2021-03-01"),
    ]
    yg = aggregate_by_year(trades)
    assert "2018" in yg and "2021" in yg
    assert yg["2018"]["n"] == 2
    assert yg["2021"]["n"] == 1


def test_render_markdown_has_sections():
    trades = [compute_trade_returns(_trade(10.6, 10.0), 0.0008)]
    md = render_markdown(
        overall=aggregate_overall(trades),
        overall_open={"n": 1, "win_rate": 100.0, "avg_ret_net": 5.8,
                      "payoff": 0, "avg_hold": 2.0, "max_drawdown": 0,
                      "wins": 1, "avg_ret_gross": 6.0},
        elasticity={"hold_1": 1.0, "hold_3": 2.0, "hold_5": 1.5, "hold_10": 0.8,
                    "mfe": 3.0, "mae": -2.0, "n": 1},
        year_groups={"2018": {"n": 1, "win_rate": 100.0, "payoff": 0,
                              "avg_ret_net": 5.8}},
        cap_groups={},
        fit={"total_signals": 1, "per_day": 0.0, "avg_hold": 2.0,
             "stop_loss_share": 0.0, "stop_loss_saved": 0.0,
             "trading_days": 600},
        benchmark_ret=10.0,
        biases=[],
    )
    assert "一、策略整体有效性" in md
    assert "二、信号弹性" in md
    assert "三、按年分段" in md
    assert "四、市值阈值" in md
    assert "五、与实盘契合度" in md
    assert "2018" in md
