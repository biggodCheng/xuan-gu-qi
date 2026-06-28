from screener.analyzer import analyze_qibao


def _flat_then_breakout() -> list[dict]:
    """前 39 根横盘交替 9.5/10.5（high=10.6,low=9.4,vol=1000），末根放量起爆。"""
    kline = []
    for i in range(39):
        close = 9.5 if i % 2 == 0 else 10.5
        kline.append({
            "date": f"d{i}", "open": 10.0, "high": 10.6, "low": 9.4,
            "close": close, "volume": 1000.0,
        })
    kline.append({  # 第40根(末根)：放量突破
        "date": "d39", "open": 10.5, "high": 13.1, "low": 10.4,
        "close": 13.0, "volume": 20000.0,
    })
    return kline


def test_qibao_hit_and_xushi():
    result = analyze_qibao(_flat_then_breakout())
    assert result is not None                  # 起爆命中
    assert result["boll_breakout"] is True
    assert result["macd_above_zero"] is True
    assert result["xushi"] is True             # 起爆前横盘 → 兼蓄势
    assert result["signals"] == ["起爆", "兼蓄势"]
    assert result["pct_chg"] > 0
    assert result["vol_ratio"] > 2


def test_no_breakout():
    kline = _flat_then_breakout()
    kline[-1]["close"] = 10.0                  # 末根未突破
    assert analyze_qibao(kline) is None


def test_no_volume():
    kline = _flat_then_breakout()
    kline[-1]["volume"] = 1000.0               # 末根未倍量
    assert analyze_qibao(kline) is None


def test_min_history_skip():
    kline = _flat_then_breakout()[:39]         # 仅 39 根，不足 MIN_HISTORY(40)
    assert analyze_qibao(kline) is None
