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


from screener.indicators import std, hhv, llv, boll_upper


def test_std():
    # 经典示例 [2,4,4,4,5,5,7,9] 总体标准差 = 2.0
    vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
    result = std(vals, 8)
    assert abs(result[7] - 2.0) < 1e-9


def test_hhv_llv():
    vals = [5.0, 3.0, 8.0, 2.0, 6.0]
    h = hhv(vals, 3)
    l = llv(vals, 3)
    assert h[0] == 5.0 and l[0] == 5.0           # 不足时用所有可用值
    assert h[2] == 8.0                            # [5,3,8]
    assert h[3] == 8.0 and l[3] == 2.0            # [3,8,2]
    assert h[4] == 8.0 and l[4] == 2.0            # [8,2,6]


def test_boll_upper():
    closes = [10.0] * 20 + [11.0]
    result = boll_upper(closes, 20, 2)
    assert abs(result[19] - 10.0) < 1e-9          # 前20根常数：MA=10, STD=0
