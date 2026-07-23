from pk import mappings


def test_tone_cold_when_us_and_a50_down():
    assert mappings.tone(us_pct=-1.8, a50_pct=-0.6, vix=22) == "偏冷"


def test_tone_warm_when_us_up():
    assert mappings.tone(us_pct=1.5, a50_pct=0.4, vix=13) == "偏暖"


def test_tone_neutral_mixed():
    assert mappings.tone(us_pct=0.2, a50_pct=-0.1, vix=15) == "中性"


def test_tone_panic_when_vix_spike():
    assert mappings.tone(us_pct=-2.5, a50_pct=-1.0, vix=35) == "恐慌"


def test_signal_strength_strong_when_cold_and_vix_high():
    # 偏冷 + VIX>20 共振 → 强
    assert mappings.signal_strength(us_pct=-1.8, a50_pct=-0.6, vix=22) == "强"


def test_signal_strength_medium_when_cold_no_vix():
    # 偏冷但 VIX 不高 → 中
    assert mappings.signal_strength(us_pct=-1.8, a50_pct=-0.6, vix=15) == "中"


def test_signal_strength_weak_when_neutral():
    # 无明显方向 → 弱
    assert mappings.signal_strength(us_pct=0.2, a50_pct=-0.1, vix=15) == "弱"


def test_mapping_table_nonempty():
    assert len(mappings.EXPERIENCE_TABLE) >= 3
    for row in mappings.EXPERIENCE_TABLE:
        assert "signal" in row and "experience" in row
