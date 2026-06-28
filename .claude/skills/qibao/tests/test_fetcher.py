from screener.fetcher import _parse_tencent_item, _parse_sina_item


def test_parse_tencent_item():
    # 腾讯日K格式: [日期, 开盘, 收盘, 最高, 最低, 成交量]
    item = ["2026-06-29", "10.00", "10.50", "10.60", "9.90", "100000"]
    assert _parse_tencent_item(item) == {
        "date": "2026-06-29", "open": 10.0, "close": 10.5,
        "high": 10.6, "low": 9.9, "volume": 100000.0,
    }


def test_parse_sina_item():
    item = {
        "day": "2026-06-29", "open": "10.00", "high": "10.60",
        "low": "9.90", "close": "10.50", "volume": "100000",
    }
    assert _parse_sina_item(item) == {
        "date": "2026-06-29", "open": 10.0, "close": 10.5,
        "high": 10.6, "low": 9.9, "volume": 100000.0,
    }
