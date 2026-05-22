from screener.calculator import is_new_high, filter_new_highs


def test_is_new_high_true():
    close = 20.0
    history = [18.0, 19.0, 19.5, 20.0, 17.0]
    assert is_new_high(close, history) is True


def test_is_new_high_false():
    close = 18.0
    history = [18.0, 19.0, 19.5, 20.0, 17.0]
    assert is_new_high(close, history) is False


def test_is_new_high_empty_history():
    assert is_new_high(20.0, []) is False


def test_filter_new_highs():
    stocks = [
        {"code": "000001", "name": "平安银行", "close": 20.0},
        {"code": "000002", "name": "万科A", "close": 10.0},
    ]
    histories = {
        "000001": [18.0, 19.0, 19.5, 17.0],
        "000002": [11.0, 12.0, 10.5, 10.0],
    }
    result = filter_new_highs(stocks, histories)
    assert len(result) == 1
    assert result[0]["code"] == "000001"
    assert result[0]["close"] == 20.0
    assert result[0]["high_100d"] == 19.5


def test_filter_new_highs_no_history():
    stocks = [{"code": "000001", "name": "平安银行", "close": 20.0}]
    histories = {}
    result = filter_new_highs(stocks, histories)
    assert len(result) == 0


def test_filter_new_highs_short_history():
    stocks = [{"code": "000001", "name": "平安银行", "close": 20.0}]
    histories = {"000001": [15.0, 16.0]}
    result = filter_new_highs(stocks, histories)
    assert len(result) == 1
    assert result[0]["high_100d"] == 16.0
