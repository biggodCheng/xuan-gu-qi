import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.reporter import format_report, _lamp, _funnel_verdict


def test_lamp():
    assert _lamp({"pass": True}) == "✅"
    assert _lamp({"pass": False}) == "❌"
    assert _lamp({"verdict": "中性"}) == "➖"
    assert _lamp({}) == "➖"


def test_funnel_pass_all():
    r = {"new_high": {"pass": True}, "zt": {"pass": True},
         "pullback": {"pass": True}, "marketcap": {"pass": True}}
    verdict, where = _funnel_verdict(r)
    assert verdict == "达标" and where == ""


def test_funnel_fail_at_marketcap():
    r = {"new_high": {"pass": True}, "zt": {"pass": True},
         "pullback": {"pass": True}, "marketcap": {"pass": False}}
    verdict, where = _funnel_verdict(r)
    assert verdict == "不达标" and "市值" in where


def test_funnel_fail_at_new_high():
    r = {"new_high": {"pass": False}, "zt": {"pass": True},
         "pullback": {"pass": False}, "marketcap": {"pass": True}}
    verdict, where = _funnel_verdict(r)
    assert verdict == "不达标" and "趋势新高" in where


def test_format_report_contains_core_lines():
    stock = {
        "code": "000021", "name": "深科技", "industry": "消费电子",
        "last_date": "2026-07-07", "last_close": 54.07, "intraday": False,
        "new_high": {"pass": True, "label": "今日新高"},
        "zt": {"pass": True, "label": "2 次"},
        "pullback": {"pass": True, "label": "d6 起 2 天"},
        "marketcap": {"pass": False, "label": "851 亿"},
        "q2": {"verdict": "中性", "confidence": "中", "netprofit_yoy": 35.35,
               "revenue_yoy": 10.67, "summary": "..."},
        "track": {"tracks": ["AI硬件和基础设施", "大工业"], "main": "AI硬件和基础设施",
                  "main_conf": "中"},
        "error": None,
    }
    out = format_report(stock)
    assert "深科技(000021)" in out
    assert "851 亿" in out
    assert "不达标" in out
    assert "市值" in out  # 漏斗在市值淘汰


def _base_stock():
    """基本达标 stock（①②③④全过），用于⑦维度测试。"""
    return {
        "code": "000021", "name": "深科技", "industry": "消费电子",
        "last_date": "2026-07-07", "last_close": 54.07, "intraday": False,
        "new_high": {"pass": True, "label": "今日新高"},
        "zt": {"pass": True, "label": "2 次"},
        "pullback": {"pass": True, "label": "d6 起 2 天"},
        "marketcap": {"pass": True, "label": "150 亿", "total": 150, "circ": 150},
        "q2": {"verdict": "中性", "confidence": "中", "netprofit_yoy": 35.35,
               "revenue_yoy": 10.67, "summary": "..."},
        "track": {"tracks": ["AI硬件和基础设施"], "main": "AI硬件和基础设施",
                  "main_conf": "中"},
        "support": {"hit_count": 2, "pass": True, "label": "有力（2/3：缩量、不破支撑）"},
        "error": None,
    }


def test_format_report_support_strong():
    stock = _base_stock()
    out = format_report(stock)
    assert "⑦ 承接" in out
    assert "有力" in out


def test_format_report_support_weak_warns():
    stock = _base_stock()
    stock["support"] = {"hit_count": 0, "pass": False, "label": "弱（0/3）"}
    out = format_report(stock)
    assert "⑦ 承接" in out
    assert "承接偏弱，等买点" in out  # 软警示出现在"一句话"
