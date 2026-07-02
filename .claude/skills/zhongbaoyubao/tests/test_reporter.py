import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.storage import empty_pool, add_active, refresh_active
from screener.reporter import render_report


def _pool_with_active():
    p = empty_pool()
    add_active(p, {"code": "600160", "name": "巨化股份", "yoy_lower": 80.0,
                   "yoy_upper": 120.0, "notice_date": "2026-07-10"})
    refresh_active(p, "600160", {
        "base_date": "2026-07-11", "base_price": 10.0, "daily": [{"date": "2026-07-11"}],
        "last_close": 11.0, "chg_total": 10.0, "chg_today": 1.0,
        "held_days": 1, "remain_days": 29,
    })
    return p


def test_report_contains_sections():
    md = render_report(_pool_with_active(), "2026-07-11", new_codes={"600160"}, expired_codes=[])
    assert "# 中报预报跟踪 · 2026-07-11" in md
    assert "## 今日新增" in md
    assert "巨化股份" in md
    assert "## 活跃跟踪" in md
    assert "## 涨跌分布" in md


def test_report_distribution_counts():
    md = render_report(_pool_with_active(), "2026-07-11", new_codes=set(), expired_codes=[])
    assert "为正 1" in md  # chg_total=10>0 → 1 只正
