# -*- coding: utf-8 -*-
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pattern_label  # noqa: E402
import local_kline  # noqa: E402


def _kl(closes):
    """从收盘价序列构造 K线 list（OHLC 围绕 close，date 占位）。"""
    return [{"date": f"D{i}", "open": c, "high": c * 1.005, "low": c * 0.995,
             "close": c, "volume": 10000} for i, c in enumerate(closes)]


# ---------- classify_shape: 合成数据确定性单测（零依赖）----------

def test_shape_breakout_from_box():
    """横盘突破型: 60日横盘10.0-10.27 + 首板10.5 破箱顶。"""
    closes = [10.0 + 0.03 * (i % 10) for i in range(61)] + [10.5]  # 62根, idx61=首板
    r = pattern_label.classify_shape(_kl(closes), height=1)
    assert r["label"] == "横盘突破"
    assert r["metrics"]["breakout"] >= 0.99
    assert r["metrics"]["retracement"] < 10


def test_shape_oversold_bounce():
    """超跌反抽型: 60日从12.0跌到9.64 + 首板10.0 未收复前高。"""
    closes = [12.0 - 0.04 * i for i in range(60)] + [9.8, 10.0]  # 62根
    r = pattern_label.classify_shape(_kl(closes), height=1)
    assert r["label"] == "超跌反抽"
    assert r["metrics"]["retracement"] > 15
    assert r["metrics"]["breakout"] < 1.0


def test_shape_new_stock_insufficient_data():
    """数据不足60日 → 次新。"""
    r = pattern_label.classify_shape(_kl([10.0, 10.1, 10.2]), height=1)
    assert r["label"] == "次新"


# ---------- 真实数据集成测试 (验证华天/兴欣) ----------

VIPDOC = r"D:\APP\招商证券\vipdoc"
HAS_VIPDOC = os.path.isdir(VIPDOC)


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_shape_real_huatian_bottom_breakout():
    """华天酒店 sz000428 (2026-07-29 三板) → 底部平台突破。

    60日前高3.89(2026-04-29)→慢跌3月到3.02(07-22)→末20日3.0-3.2筑底横盘→
    07-27放量破末20日高3.26。前期跌透(retracement22%)+近期筑底(vol20 5.8%)+破平台=底部反转。"""
    kl = local_kline.read_day("sz000428")
    r = pattern_label.classify_shape(kl, height=3)
    assert r["label"] == "底部平台突破", r


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_shape_real_xingxin_oversold():
    """兴欣新材 sz001358 (2026-07-29 三板) → 超跌反抽。"""
    kl = local_kline.read_day("sz001358")
    r = pattern_label.classify_shape(kl, height=3)
    assert r["label"] == "超跌反抽", r


# ---------- classify_volume ----------
def test_volume_yizi():
    assert pattern_label.classify_volume(vr=0.6, amp=0.5, seal=1.0, yizi=True) == "一字缩量"


def test_volume_shrink():
    assert pattern_label.classify_volume(vr=0.7, amp=5.0, seal=1.0) == "缩量"


def test_volume_mild():
    assert pattern_label.classify_volume(vr=2.2, amp=5.8, seal=1.0) == "温和放量"


def test_volume_blowoff_bad():
    assert pattern_label.classify_volume(vr=6.6, amp=6.8, seal=0.98) == "爆量烂板"


def test_volume_plain_up():
    assert pattern_label.classify_volume(vr=3.0, amp=4.0, seal=1.0) == "放量"


def test_volume_blowoff_bad_board_threshold():
    """爆量烂板振幅阈值按板块折算: 主板amp>5%, 创业/科创>10%。同 amp=8 主板烂板/创业不算。"""
    assert pattern_label.classify_volume(vr=6.6, amp=8.0, seal=0.98, bd="main") == "爆量烂板"
    assert pattern_label.classify_volume(vr=6.6, amp=8.0, seal=0.98, bd="cyb") == "放量"


# ---------- classify_sector (mock industry_map + _sector_stats) ----------
def test_sector_missing_map(monkeypatch):
    monkeypatch.setattr(pattern_label.industry_map, "load_map", lambda: {})
    r = pattern_label.classify_sector("sz000428")
    assert r["label"] == "映射缺失"


def test_sector_lone_wolf(monkeypatch):
    monkeypatch.setattr(pattern_label.industry_map, "load_map",
                        lambda: {"000428": "酒店", "000721": "酒店", "600754": "酒店"})
    monkeypatch.setattr(pattern_label, "_sector_stats", lambda ind: {"zt": 1, "median": 1.2})
    r = pattern_label.classify_sector("sz000428")
    assert r["label"] == "独狼"


def test_sector_surge_emotion(monkeypatch):
    monkeypatch.setattr(pattern_label.industry_map, "load_map", lambda: {"000428": "酒店"})
    monkeypatch.setattr(pattern_label, "_sector_stats", lambda ind: {"zt": 4, "median": 5.5})
    r = pattern_label.classify_sector("sz000428")
    assert r["label"] == "齐涨(情绪)"


# ---------- _suggest 建议归类规则 ----------
def test_suggest_blowoff_top_priority():
    assert pattern_label._suggest("超跌反抽", "爆量烂板", "独狼") == "出货烂板"
    assert pattern_label._suggest("超跌反抽", "爆量烂板", "齐涨(情绪)") == "出货烂板"


def test_suggest_message_board():
    assert pattern_label._suggest("横盘突破", "一字缩量", "独狼") == "消息板"


def test_suggest_emotion_board():
    assert pattern_label._suggest("箱体震荡", "放量", "齐涨(情绪)") == "情绪板"


def test_suggest_bottom_reversal():
    """底部平台突破+温和放量+独狼 → 底部反转苗头。"""
    assert pattern_label._suggest("底部平台突破", "温和放量", "独狼") == "底部反转苗头"


def test_suggest_capital_board():
    assert pattern_label._suggest("横盘突破", "温和放量", "独狼") == "资金板苗头"


def test_suggest_mixed():
    assert pattern_label._suggest("箱体震荡", "放量", "独狼") == "混合"


# ---------- label 综合判定 (真实数据, 仅断言 shape) ----------
@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_label_real_huatian():
    """华天酒店 综合 → 底部平台突破 (suggest 依赖运行时板块数据, 仅打印)。"""
    r = pattern_label.label("sz000428", height=3)
    assert r["shape"] == "底部平台突破", r
    print(f"  华天 suggest={r.get('suggest')} volume={r.get('volume')} sector={r.get('sector')}")


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_label_real_xingxin():
    """兴欣新材 综合 → 超跌反抽 (volume 实际是'放量'非'爆量烂板', 因3板封死 seal≈1.0)。"""
    r = pattern_label.label("sz001358", height=3)
    assert r["shape"] == "超跌反抽", r
    print(f"  兴欣 suggest={r.get('suggest')} volume={r.get('volume')} sector={r.get('sector')}")


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_strong_scan_includes_pattern_for_ladder():
    """fupan_strong_scan 连板股应带 pattern 字段。"""
    import fupan_strong_scan
    latest, stocks = fupan_strong_scan.scan()
    lian = [s for s in stocks if s["height"] >= 2]
    if lian:
        for s in lian[:8]:
            assert "pattern" in s, f"{s['code']} 缺 pattern 字段"
            assert "sym" in s, f"{s['code']} 缺 sym 字段"
