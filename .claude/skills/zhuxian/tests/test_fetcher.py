import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.fetcher import (  # noqa: E402
    get_concept_sectors,
    get_sector_kline,
    _aggregate_klines,
)


def test_get_concept_sectors_parses_response():
    """getHQNodes 节点树片段：递归应提取 gn_ 概念板块，排除 new_ 行业板块。"""
    # 分步构造节点树，避免深层嵌套括号出错
    gn_leaf_1 = ["华为汽车", "", "gn_hwqc"]
    gn_leaf_2 = ["BC电池", "", "gn_BCdc"]
    hy_leaf = ["玻璃", "", "new_blhy"]
    concept_cat = ["概念板块", [gn_leaf_1, gn_leaf_2]]
    industry_cat = ["新浪行业", [hy_leaf]]
    a_stock_cat = ["A股", [concept_cat, industry_cat]]
    mock_resp = ["行情中心", [a_stock_cat]]

    with patch("screener.fetcher._get_json", return_value=mock_resp):
        result = get_concept_sectors()

    codes = [s["code"] for s in result]
    assert "gn_hwqc" in codes
    assert "gn_BCdc" in codes
    assert "new_blhy" not in codes  # 行业板块不应混入
    by_code = {s["code"]: s["name"] for s in result}
    assert by_code["gn_hwqc"] == "华为汽车"


def test_get_concept_sectors_empty_response():
    with patch("screener.fetcher._get_json", return_value=None):
        result = get_concept_sectors()
    assert result == []


def test_aggregate_klines_basic():
    """两只成分股日K等权聚合：close/open/high/low 取均值，volume 取和。"""
    klines_by_stock = {
        "sz001": [
            {"day": "2026-07-01", "open": 10, "close": 10.5, "high": 11, "low": 9.5, "volume": 1000},
            {"day": "2026-07-02", "open": 10.5, "close": 11, "high": 11.5, "low": 10, "volume": 1100},
        ],
        "sz002": [
            {"day": "2026-07-01", "open": 20, "close": 20.5, "high": 21, "low": 19.5, "volume": 2000},
            {"day": "2026-07-02", "open": 20.5, "close": 21, "high": 21.5, "low": 20, "volume": 2100},
        ],
    }
    result = _aggregate_klines(klines_by_stock, min_coverage=0.5)
    assert len(result) == 2
    assert result[0]["date"] == "2026-07-01"
    assert result[0]["close"] == round((10.5 + 20.5) / 2, 4)
    assert result[0]["high"] == round((11 + 21) / 2, 4)
    assert result[0]["low"] == round((9.5 + 19.5) / 2, 4)
    assert result[0]["volume"] == 3000  # 求和
    assert result[1]["date"] == "2026-07-02"


def test_aggregate_klines_drops_low_coverage_days():
    """某日仅有1只成分股有数据（低于 threshold），该日应被丢弃。"""
    klines_by_stock = {
        "sz001": [
            {"day": "2026-07-01", "open": 10, "close": 10.5, "high": 11, "low": 9.5, "volume": 1000},
            {"day": "2026-07-02", "open": 10.5, "close": 11, "high": 11.5, "low": 10, "volume": 1100},
        ],
        "sz002": [
            {"day": "2026-07-01", "open": 20, "close": 20.5, "high": 21, "low": 19.5, "volume": 2000},
            # 07-02 停牌无数据
        ],
    }
    result = _aggregate_klines(klines_by_stock, min_coverage=0.5)
    assert len(result) == 1
    assert result[0]["date"] == "2026-07-01"


def test_get_sector_kline_aggregates_components():
    """get_sector_kline 拉成分股 + 个股K线后聚合为板块K线。"""
    components = [{"symbol": f"sz00{i}"} for i in range(1, 7)]  # 6 只 >= _MIN_COMPONENTS
    stock_kl = {
        f"sz00{i}": [
            {"day": "2026-07-01", "open": 10 + i, "close": 10.5 + i, "high": 11 + i, "low": 9.5 + i, "volume": 1000 * i},
            {"day": "2026-07-02", "open": 10.5 + i, "close": 11 + i, "high": 11.5 + i, "low": 10 + i, "volume": 1100 * i},
        ]
        for i in range(1, 7)
    }
    with patch("screener.fetcher._get_components", return_value=components), \
         patch("screener.fetcher._get_stock_kline",
               side_effect=lambda sym, *a, **k: stock_kl.get(sym, [])):
        result = get_sector_kline("gn_test")
    assert len(result) == 2
    assert result[0]["date"] == "2026-07-01"
    expected_close = round(sum(10.5 + i for i in range(1, 7)) / 6, 4)
    assert result[0]["close"] == expected_close


def test_get_sector_kline_too_few_components_returns_empty():
    with patch("screener.fetcher._get_components", return_value=[{"symbol": "sz001"}]):
        result = get_sector_kline("gn_test")
    assert result == []


def test_get_sector_kline_error_returns_empty():
    with patch("screener.fetcher._get_components", side_effect=Exception("network error")):
        result = get_sector_kline("gn_test")
    assert result == []
