# -*- coding: utf-8 -*-
"""build_candidates 单测 — 波段超跌反弹候选筛选纯函数。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # boduan/
from main import build_candidates


def _bar(date, o, h, l, c, v):
    return {"date": date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def test_build_candidates_finds_qualified_skips_unqualified():
    # 合格股: 20日 100→65(跌35%>30%) + T日阳包阴+放量2.5倍
    bars_good = []
    for i in range(20):
        c = 100 - (100 - 65) / 19 * i
        bars_good.append(_bar(f"2024-01-{i+1:02d}", c + 0.5, c + 1, c - 1, c, 1000))
    bars_good.append(_bar("2024-01-21", 65.3, 66.5, 64, 67, 2500))  # close67>open65.3阳, >open[T-1]65.5, high66.5>66, vol2500=2.5×
    # 不合格股: 未超跌(平盘)
    bars_bad = [_bar(f"2024-01-{i+1:02d}", 10, 11, 9, 10, 100) for i in range(21)]

    stocks = [{"code": "001", "name": "合格股", "close": 67, "market_cap": 50.0},
              {"code": "002", "name": "不合格", "close": 10, "market_cap": 50.0}]
    klines = {"001": bars_good, "002": bars_bad}

    cands = build_candidates(stocks, klines, drop_pct=30.0, vol_ratio=2.5)
    assert len(cands) == 1
    assert cands[0]["code"] == "001"
    assert cands[0]["name"] == "合格股"
    assert cands[0]["drop20"] <= -30
    assert cands[0]["stop_loss"] == 64.0       # T-1(bars_good[-2])最低
    assert cands[0]["vol_ratio"] == 2.5
    assert cands[0]["market_cap"] == 50.0


def test_build_candidates_empty_klines_skipped():
    stocks = [{"code": "X", "name": "X", "close": 10, "market_cap": 30.0}]
    assert build_candidates(stocks, {}, drop_pct=30.0, vol_ratio=2.5) == []
