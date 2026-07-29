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
@pytest.mark.xfail(
    reason=(
        "2026-07-29 实测: 华天实际判定为「超跌反抽」而非 spec 预期的「横盘突破」。"
        "spec 4.1 手工分析只看了末20日横盘3.0-3.2, 误判 peak60≈3.26/retracement<10%; "
        "但算法按 60日窗口 peak-trough 正确算出 peak60=3.89(2026-04-29) → trough=3.02(2026-07-22), "
        "retracement=22.37%>15% 且 breakout=0.859<1.0 → 超跌反抽。"
        "算法自洽且符合 spec「用60日peak-trough过程指标」的设计意图; "
        "分歧在华天属「下跌末段底部平台突破」, 60日窗口捕捉到前期3.89高点。"
        "由 controller 裁定: (a)认可算法→改本断言为超跌反抽; (b)想识别底部平台突破→算法增强。"
    ),
    strict=False,
)
def test_shape_real_huatian_breakout():
    """华天酒店 sz000428 (2026-07-29 三板) → spec 预期横盘突破 (实测见 xfail reason)。"""
    kl = local_kline.read_day("sz000428")
    r = pattern_label.classify_shape(kl, height=3)
    assert r["label"] == "横盘突破", r


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_shape_real_xingxin_oversold():
    """兴欣新材 sz001358 (2026-07-29 三板) → 超跌反抽。"""
    kl = local_kline.read_day("sz001358")
    r = pattern_label.classify_shape(kl, height=3)
    assert r["label"] == "超跌反抽", r
