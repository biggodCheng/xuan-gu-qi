from screener.indicators import ma, ema


def test_ma():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = ma(vals, 3)
    assert result[:2] == [None, None]          # 不足3日无值
    assert result[2] == 2.0                      # (1+2+3)/3
    assert result[3] == 3.0                      # (2+3+4)/3
    assert result[4] == 4.0                      # (3+4+5)/3


def test_ema():
    vals = [10.0, 11.0, 12.0, 11.0, 10.0, 13.0]
    n = 5
    result = ema(vals, n)
    assert result[0] == vals[0]                  # 首值=原值
    alpha = 2 / (n + 1)
    for i in range(1, len(vals)):                 # 验证递推关系
        expected = alpha * vals[i] + (1 - alpha) * result[i - 1]
        assert abs(result[i] - expected) < 1e-9
