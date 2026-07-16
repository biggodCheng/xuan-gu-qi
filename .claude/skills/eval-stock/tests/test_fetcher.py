import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.fetcher import (
    tencent_symbol, get_board, zt_threshold,
    _parse_sina_kline, _parse_qt,
)


def test_tencent_symbol():
    assert tencent_symbol("600206") == "sh600206"
    assert tencent_symbol("000021") == "sz000021"
    assert tencent_symbol("920019") == "bj920019"


def test_get_board():
    assert get_board("600206") == "main"
    assert get_board("000021") == "main"
    assert get_board("300001") == "kc_cy"
    assert get_board("688001") == "kc_cy"
    assert get_board("830001") == "bj"
    assert get_board("920019") == "bj"


def test_zt_threshold():
    assert zt_threshold("000021") == 9.5
    assert zt_threshold("300001") == 19.5
    assert zt_threshold("830001") == 29.5


def test_parse_sina_kline_ok():
    payload = [
        {"day": "2026-07-01", "open": "10.0", "close": "10.5", "high": "10.6", "low": "9.9", "volume": "1000"},
        {"day": "2026-07-02", "open": "10.5", "close": "11.0", "high": "11.1", "low": "10.4", "volume": "1200"},
    ]
    rows = _parse_sina_kline(payload)
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-07-01"
    assert rows[0]["close"] == 10.5
    assert rows[0]["volume"] == 1000.0


def test_parse_sina_kline_missing_volume():
    # volume 缺失应容错为 0，不丢整根K线
    payload = [{"day": "2026-07-01", "open": "10.0", "close": "10.5", "high": "10.6", "low": "9.9"}]
    rows = _parse_sina_kline(payload)
    assert len(rows) == 1
    assert rows[0]["close"] == 10.5
    assert rows[0]["volume"] == 0.0


def test_parse_sina_kline_bad_payload():
    assert _parse_sina_kline(None) == []
    assert _parse_sina_kline("not a list") == []


def test_parse_qt_ok():
    parts = [""] * 50
    parts[44] = "800.5"
    parts[45] = "790.0"
    inner = "~".join(parts)
    raw = f'v_sz000021="{inner}";'
    total, circ = _parse_qt(raw)
    assert total == 800.5 and circ == 790.0


def test_parse_qt_bad():
    assert _parse_qt("garbage") == (None, None)
