"""analyzer 纯逻辑单元测试。

运行:
    cd .claude/skills/q2zhanwang && python test_analyzer.py

覆盖:单季化、同比、势头方向、背离方向、verdict 矩阵、置信度、端到端(比亚迪真实数据)。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from screener.analyzer import (  # noqa: E402
    analyze,
    combine_verdict,
    confidence_level,
    divergence_direction,
    momentum_direction,
    single_quarterize,
    yoy,
)

YI = 1e8  # 亿


def _report(y, q, rev_yi, np_yi, gm, qdate=None):
    """构造累计口径 report(单位:亿)。"""
    return {
        "report_date": f"{y}-{q*3:02d}-30"[:10] if False else f"{y}-{(q*3):02d}-30",
        "qdate": qdate or f"{y}Q{q}",
        "year": y, "quarter": q,
        "revenue": rev_yi * YI if rev_yi is not None else None,
        "parent_netprofit": np_yi * YI if np_yi is not None else None,
        "gross_margin": gm,
    }


# 比亚迪真实累计数据(亿)
BYD_REPORTS = [
    _report(2026, 1, 1502.25, 40.85, 18.81, "2026Q1"),
    _report(2025, 4, 8039.65, 326.19, 17.74, "2025Q4"),
    _report(2025, 3, 5662.66, 233.33, 17.87, "2025Q3"),
    _report(2025, 2, 3712.81, 155.11, 18.01, "2025Q2"),
    _report(2025, 1, 1703.60, 91.55, 20.07, "2025Q1"),
    _report(2024, 4, 7771.02, 402.54, 19.44, "2024Q4"),
    _report(2024, 3, 5022.51, 252.38, 19.32, "2024Q3"),
    _report(2024, 2, 3011.27, 136.31, 18.78, "2024Q2"),
    _report(2024, 1, 1249.44, 45.69, 20.71, "2024Q1"),
]


class TestSingleQuarterize(unittest.TestCase):
    def test_q1_is_cumulative(self):
        single = single_quarterize([_report(2026, 1, 150.0, 40.0, 18.0)])
        self.assertAlmostEqual(single[(2026, 1)]["parent_netprofit"], 40.0 * YI)

    def test_q4_is_annual_minus_q3(self):
        # Q4单季 = 年报 - 三季报
        single = single_quarterize([
            _report(2025, 4, 800.0, 326.0, 17.0),  # 年报累计
            _report(2025, 3, 560.0, 233.0, 17.0),  # 三季报累计
        ])
        # 单季归母 = 326 - 233 = 93 亿
        self.assertAlmostEqual(single[(2025, 4)]["parent_netprofit"], 93.0 * YI)
        self.assertAlmostEqual(single[(2025, 4)]["revenue"], 240.0 * YI)

    def test_missing_prev_period_skipped(self):
        # 缺三季报,Q4无法单季化 → 不产出
        single = single_quarterize([_report(2025, 4, 800.0, 326.0, 17.0)])
        self.assertNotIn((2025, 4), single)

    def test_gross_margin_not_cumulative(self):
        # 毛利率是比率,直接取本期值,不单季化
        single = single_quarterize([
            _report(2025, 4, 800.0, 326.0, 17.5),
            _report(2025, 3, 560.0, 233.0, 17.0),
        ])
        self.assertAlmostEqual(single[(2025, 4)]["gross_margin"], 17.5)


class TestYoy(unittest.TestCase):
    def test_normal(self):
        # (40.85 - 91.55) / 91.55 ≈ -55.38
        self.assertAlmostEqual(yoy(40.85 * YI, 91.55 * YI), -55.38, places=1)

    def test_none_input(self):
        self.assertIsNone(yoy(40.0 * YI, None))
        self.assertIsNone(yoy(None, 90.0 * YI))

    def test_small_base(self):
        # 基数过小 → None(增速失真)
        self.assertIsNone(yoy(40.0 * YI, 50.0))  # 基数 50 元


class TestMomentum(unittest.TestCase):
    def test_decelerate(self):
        # Q1 -55 vs Q4 -38 → diff -17 < -5 → 减速
        self.assertEqual(momentum_direction(-55.38, -38.17), "减速")

    def test_accelerate(self):
        self.assertEqual(momentum_direction(80.0, 50.0), "加速")

    def test_flat(self):
        self.assertEqual(momentum_direction(30.0, 28.0), "持平")  # diff 2 < 5

    def test_insufficient(self):
        self.assertEqual(momentum_direction(None, -38.0), "数据不足")
        self.assertEqual(momentum_direction(-55.0, None), "数据不足")


class TestDivergence(unittest.TestCase):
    def test_compress(self):
        # 净利 -55 远弱于营收 -12,毛利率压缩 → 承压
        self.assertEqual(divergence_direction(-11.82, -55.38, -1.26), "利润承压")

    def test_improve(self):
        # 净利强于营收 + 毛利率扩张 → 改善
        self.assertEqual(divergence_direction(15.0, 40.0, 2.0), "利润改善")

    def test_sync(self):
        self.assertEqual(divergence_direction(20.0, 22.0, 0.5), "同步")

    def test_insufficient(self):
        self.assertEqual(divergence_direction(None, -55.0, -1.0), "数据不足")


class TestVerdict(unittest.TestCase):
    def test_full_matrix(self):
        cases = {
            ("加速", "改善"): "偏正", ("加速", "同步"): "偏正", ("加速", "承压"): "中性",
            ("持平", "改善"): "偏正", ("持平", "同步"): "中性", ("持平", "承压"): "偏负",
            ("减速", "改善"): "中性", ("减速", "同步"): "偏负", ("减速", "承压"): "偏负",
        }
        for (m, d), expected in cases.items():
            self.assertEqual(combine_verdict(m, d), expected, f"{m}+{d}")

    def test_insufficient_momentum(self):
        # 任一信号数据不足 → verdict 数据不足
        self.assertEqual(combine_verdict("数据不足", "承压"), "数据不足")
        self.assertEqual(combine_verdict("减速", "数据不足"), "数据不足")


class TestConfidence(unittest.TestCase):
    def test_same_direction_high(self):
        # 减速+承压 同向负 → 高
        self.assertEqual(confidence_level("减速", "承压", True), "高")
        self.assertEqual(confidence_level("加速", "改善", True), "高")

    def test_contradict_mid(self):
        # 加速+承压 矛盾 → 中
        self.assertEqual(confidence_level("加速", "承压", True), "中")

    def test_incomplete_low(self):
        self.assertEqual(confidence_level("减速", "承压", False), "低")

    def test_insufficient_low(self):
        self.assertEqual(confidence_level("数据不足", "承压", True), "低")


class TestAnalyzeByd(unittest.TestCase):
    def setUp(self):
        self.fin = {"code": "002594", "name": "比亚迪", "industry": "乘用车",
                    "reports": BYD_REPORTS}

    def test_q1_single_yoy(self):
        r = analyze(self.fin)
        self.assertAlmostEqual(r["q2_outlook"]["signals"]["momentum"]["q1_single_yoy"],
                               -55.38, places=1)

    def test_q4_single_yoy(self):
        r = analyze(self.fin)
        self.assertAlmostEqual(r["q2_outlook"]["signals"]["momentum"]["q4_single_yoy"],
                               -38.17, places=1)

    def test_momentum_decelerate(self):
        r = analyze(self.fin)
        self.assertEqual(r["q2_outlook"]["signals"]["momentum"]["direction"], "减速")

    def test_divergence_compress(self):
        r = analyze(self.fin)
        self.assertEqual(r["q2_outlook"]["signals"]["divergence"]["direction"], "利润承压")

    def test_verdict_negative(self):
        r = analyze(self.fin)
        self.assertEqual(r["q2_outlook"]["verdict"], "偏负")

    def test_confidence_high(self):
        # 两信号同向负 + 数据完整 → 高
        r = analyze(self.fin)
        self.assertEqual(r["q2_outlook"]["confidence"], "高")

    def test_q1_fields(self):
        r = analyze(self.fin)
        self.assertAlmostEqual(r["q1"]["parent_netprofit_yi"], 40.85, places=1)
        self.assertAlmostEqual(r["q1"]["parent_netprofit_prev_yi"], 91.55, places=1)


class TestAnalyzeEdge(unittest.TestCase):
    def test_new_stock_no_prev_q1(self):
        # 新股:只有 2026Q1,无 2025Q1 → 无法算同比 → 数据不足
        fin = {"code": "X", "name": "新股", "industry": "",
               "reports": [_report(2026, 1, 150.0, 40.0, 18.0)]}
        r = analyze(fin)
        self.assertEqual(r["q2_outlook"]["verdict"], "数据不足")

    def test_missing_2024_for_q4_base(self):
        # 缺 2024 数据 → Q4单季同比算不出 → 势头数据不足,confidence 低
        reports = [
            _report(2026, 1, 1502.25, 40.85, 18.81),
            _report(2025, 4, 8039.65, 326.19, 17.74),
            _report(2025, 3, 5662.66, 233.33, 17.87),
            _report(2025, 1, 1703.60, 91.55, 20.07),
        ]
        fin = {"code": "X", "name": "X", "industry": "", "reports": reports}
        r = analyze(fin)
        self.assertEqual(r["q2_outlook"]["signals"]["momentum"]["direction"], "数据不足")
        self.assertEqual(r["q2_outlook"]["confidence"], "低")

    def test_no_q1_at_all(self):
        fin = {"code": "X", "name": "X", "industry": "", "reports": []}
        r = analyze(fin)
        self.assertEqual(r["q2_outlook"]["verdict"], "数据不足")


if __name__ == "__main__":
    unittest.main(verbosity=2)
