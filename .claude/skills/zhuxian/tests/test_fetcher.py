import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.fetcher import (  # noqa: E402
    get_concept_sectors,
    get_sector_kline,
    _get_board_members,
    _prefix,
    _aggregate,
)


def test_get_concept_sectors_parses_response():
    """东财 clist: f12=板块代码 f14=名称 f2=点数 f3=涨跌；翻页取全量。"""
    page1 = {"data": {"diff": [
        {"f12": "BK1106", "f14": "创新药", "f2": 1400.19, "f3": -0.93},
    ] + [{"f12": f"BK{i:04d}", "f14": f"填充{i}", "f2": 100, "f3": 0} for i in range(99)]}}
    page2 = {"data": {"diff": [{"f12": "BK9999", "f14": "尾页", "f2": 99, "f3": -1}]}}
    with patch("screener.fetcher._get_json", side_effect=[page1, page2]):
        result = get_concept_sectors()
    by = {s["code"]: s for s in result}
    assert by["BK1106"]["change_pct"] == -0.93
    assert "BK9999" in by  # 翻页取到


def test_get_concept_sectors_empty_response():
    with patch("screener.fetcher._get_json", return_value=None):
        assert get_concept_sectors() == []


def test_get_concept_sectors_filters_style_boards():
    """风格/元板块(百日新高/趋势股/昨日触板 等)按BK黑名单过滤; 参股XX是真题材保留。"""
    resp = {"data": {"diff": [
        {"f12": "BK1106", "f14": "创新药", "f2": 1400.19, "f3": -0.93},
        {"f12": "BK1676", "f14": "百日新高", "f2": 1317, "f3": -1.17},
        {"f12": "BK1715", "f14": "趋势股", "f2": 842, "f3": -0.4},
        {"f12": "BK0817", "f14": "昨日触板", "f2": 17, "f3": 0.4},
        {"f12": "BK0899", "f14": "CRO", "f2": 1869, "f3": -0.25},
        {"f12": "BK0514", "f14": "参股券商", "f2": 100, "f3": 0.5},  # 真题材,保留
    ]}}
    with patch("screener.fetcher._get_json", return_value=resp):
        result = get_concept_sectors()
    names = [s["name"] for s in result]
    assert "创新药" in names
    assert "CRO" in names
    assert "参股券商" in names  # 参股是真题材概念,保留
    assert "百日新高" not in names
    assert "趋势股" not in names
    assert "昨日触板" not in names


def test_prefix():
    assert _prefix("600276") == "sh"
    assert _prefix("688235") == "sh"
    assert _prefix("000001") == "sz"
    assert _prefix("300001") == "sz"
    assert _prefix("830001") == "bj"
    assert _prefix("920001") == "bj"


def test_get_board_members_parses_and_skips_st():
    resp = {"data": {"diff": [
        {"f12": "600276", "f14": "恒瑞医药"},
        {"f12": "000001", "f14": "平安银行"},
        {"f12": "000002", "f14": "*STxxx"},  # ST 应剔除
    ]}}
    with patch("screener.fetcher._get_json", return_value=resp):
        codes = _get_board_members("BK1106")
    assert "600276" in codes
    assert "000001" in codes
    assert "000002" not in codes  # ST 剔除


def test_aggregate_equal_weight():
    klines = {
        "600276": [
            {"date": "2026-07-20", "open": 10, "close": 10.5, "high": 11, "low": 9.5, "volume": 1000},
            {"date": "2026-07-21", "open": 10.5, "close": 11, "high": 11.5, "low": 10, "volume": 1100},
        ],
        "000001": [
            {"date": "2026-07-20", "open": 20, "close": 20.5, "high": 21, "low": 19.5, "volume": 2000},
            {"date": "2026-07-21", "open": 20.5, "close": 21, "high": 21.5, "low": 20, "volume": 2100},
        ],
    }
    result = _aggregate(klines, min_coverage=0.5)
    assert len(result) == 2
    assert result[0]["date"] == "2026-07-20"
    assert result[0]["close"] == round((10.5 + 20.5) / 2, 4)
    assert result[0]["volume"] == 3000  # volume 求和
    assert result[1]["date"] == "2026-07-21"


def test_aggregate_drops_low_coverage_days():
    klines = {
        "600276": [
            {"date": "2026-07-20", "open": 10, "close": 10.5, "high": 11, "low": 9.5, "volume": 1000},
            {"date": "2026-07-21", "open": 10.5, "close": 11, "high": 11.5, "low": 10, "volume": 1100},
        ],
        "000001": [  # 07-21 停牌无数据
            {"date": "2026-07-20", "open": 20, "close": 20.5, "high": 21, "low": 19.5, "volume": 2000},
        ],
    }
    result = _aggregate(klines, min_coverage=0.5)
    assert len(result) == 1  # 07-21 覆盖不足被丢
    assert result[0]["date"] == "2026-07-20"


def _stub_kl(sym, base, n=60):
    """构造一只个股 n 根 K 线(默认 60, 满足 _MIN_HISTORY 准入门槛), 首根 close=base+0.5。"""
    return [
        {"date": f"d{i:03d}", "open": base, "close": base + 0.5, "high": base + 1, "low": base - 0.5, "volume": base * 100}
        for i in range(n)
    ]


def test_get_sector_kline_aggregates_local():
    """get_sector_kline: 成分股(东财) + 本地个股K线 → 全成分等权聚合。"""
    members = ["600276", "000001", "300001", "600000", "000002", "600001"]  # 6 只 >= _MIN_COMPONENTS
    stock_kl = {
        "sh600276": _stub_kl("sh600276", 10),
        "sz000001": _stub_kl("sz000001", 20),
        "sz300001": _stub_kl("sz300001", 30),
        "sh600000": _stub_kl("sh600000", 40),
        "sz000002": _stub_kl("sz000002", 50),
        "sh600001": _stub_kl("sh600001", 60),
    }
    with patch("screener.fetcher._get_board_members", return_value=members), \
         patch("screener.fetcher.local_kline.read_day",
               side_effect=lambda sym: stock_kl.get(sym, [])):
        result = get_sector_kline("BK1106")
    assert len(result) == 60
    assert result[0]["date"] == "d000"
    expected = round((10.5 + 20.5 + 30.5 + 40.5 + 50.5 + 60.5) / 6, 4)
    assert result[0]["close"] == expected


def test_get_sector_kline_too_few_members():
    with patch("screener.fetcher._get_board_members", return_value=["600276"]):
        assert get_sector_kline("BK1106") == []


def test_get_sector_kline_member_fetch_fails():
    with patch("screener.fetcher._get_board_members", side_effect=Exception("net error")):
        assert get_sector_kline("BK1106") == []


def test_drop_short_history_excludes_new_ipo():
    """数据不足的新股/新进成分被剔除, 老股(>=60天)保留。"""
    from screener.fetcher import _drop_short_history, _MIN_HISTORY
    long_kl = [{"date": f"d{i:03d}", "open": 10, "close": 10, "high": 10, "low": 10, "volume": 100} for i in range(60)]
    new_ipo = [{"date": "d059", "open": 208, "close": 208, "high": 208, "low": 208, "volume": 100}]  # 仅 1 天
    klines = {"600276": long_kl, "001232": new_ipo}
    filtered = _drop_short_history(klines, _MIN_HISTORY)
    assert "600276" in filtered
    assert "001232" not in filtered  # 新股(1天 < 60)被剔除


def test_get_sector_kline_excludes_new_stock_pollution():
    """回归: 板块含仅 1 天数据的高价新股, 聚合均价不被其污染。

    001232 仅 08-04 一天 close=208, 曾把 EDA 11 只成分均价从 38 拉到 55(+44%)。
    修复后新股在聚合前被剔除, 均价 = 6 只老股均价, 不含 208。
    """
    members = ["600276", "000001", "300001", "600000", "000002", "600001", "001232"]  # 6 老 + 1 新
    bases = {"sh600276": 10, "sz000001": 20, "sz300001": 30, "sh600000": 40, "sz000002": 50, "sh600001": 60}

    def read(sym):
        if sym == "sz001232":
            return [{"date": "d059", "open": 208, "close": 208, "high": 208, "low": 208, "volume": 100}]
        return _stub_kl(sym, bases[sym])

    with patch("screener.fetcher._get_board_members", return_value=members), \
         patch("screener.fetcher.local_kline.read_day", side_effect=read):
        result = get_sector_kline("BK0946")
    assert len(result) == 60
    expected = round((10.5 + 20.5 + 30.5 + 40.5 + 50.5 + 60.5) / 6, 4)  # 6 只老股均价, 不含 208
    assert result[-1]["close"] == expected
