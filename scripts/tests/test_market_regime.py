# -*- coding: utf-8 -*-
"""market_regime 宽度统计单元测试。

锁定两个历史 bug 的修复:
  1. 代码清洗: 新浪 hs_a 返回 'sh600000'/'bj920000' 带市场前缀, 旧 zfill(6) 不删字母 →
     startswith('300') 永不命中 → 全部误判 main 板块, 创业板/北交所涨停阈值用错。
  2. 涨停阈值: 旧 9.7/19.5/29.5 会把 9.7-9.9% 未封板股误判为涨停, 高估家数。
     新阈值 9.9/19.9/29.9 = 真实封板幅(A股涨停价 round(preclose*1.1,2) 落在 ~9.9-10.1%)。

另: 2026-07-21 发现的降级链 bug(东财被封→沪深300成分仅300只→全市场涨停122被报成16)
由集成测试 test_fetch_market_breadth_returns_full_market 守护。
"""
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import market_regime  # noqa: E402
import local_kline  # noqa: E402


# ---------- 单元: 代码清洗 (bug 1) ----------

def test_clean_code_strips_sina_prefix():
    """新浪 hs_a 返回带市场前缀, 必须剥离成纯6位。"""
    assert market_regime._clean_stock_code("sh600000") == "600000"
    assert market_regime._clean_stock_code("sz300001") == "300001"
    assert market_regime._clean_stock_code("bj920000") == "920000"


def test_clean_code_keeps_pure_digits():
    """东财 f12 已是纯6位(或 int), 清洗后不变。"""
    assert market_regime._clean_stock_code("600000") == "600000"
    assert market_regime._clean_stock_code(600519) == "600519"


# ---------- 单元: 涨停阈值 (bug 2) ----------

def test_stats_main_board_9_8_not_limit_up():
    """主板涨 9.8% 未封板, 不应计涨停 (旧阈值 9.7 会误判)。"""
    b = market_regime._breadth_stats([("600000", 9.8)], full=True)
    assert b["zt"] == 0


def test_stats_main_board_9_95_is_limit_up():
    """主板涨 9.95% 封板, 计涨停。"""
    b = market_regime._breadth_stats([("600000", 9.95)], full=True)
    assert b["zt"] == 1


def test_stats_cyb_with_sina_prefix_uses_20pct_threshold():
    """创业板股(新浪前缀 sz300001)涨 9.95% 不该算涨停(创业板阈值 19.9);
    旧 bug: 前缀未删 → 误判 main → 9.7 阈值 → 错误计涨停。"""
    b = market_regime._breadth_stats([("sz300001", 9.95)], full=True)
    assert b["zt"] == 0
    b2 = market_regime._breadth_stats([("sz300001", 19.95)], full=True)
    assert b2["zt"] == 1


def test_stats_bj_with_sina_prefix_uses_30pct_threshold():
    """北交所股(新浪前缀 bj920000)涨 9.95% 不该算涨停(北交阈值 29.9);
    旧 bug: 前缀未删 → 误判 main → 9.7 阈值 → 错误计涨停。"""
    b = market_regime._breadth_stats([("bj920000", 9.95)], full=True)
    assert b["zt"] == 0
    b2 = market_regime._breadth_stats([("bj920000", 29.95)], full=True)
    assert b2["zt"] == 1


def test_stats_limit_down_main_board():
    b = market_regime._breadth_stats([("600000", -9.95)], full=True)
    assert b["dt"] == 1


# ---------- 单元: 基础统计字段 ----------

def test_stats_basic_fields():
    pairs = [("600000", 1.5), ("000001", -0.5), ("300001", 0.0), ("600519", 9.95)]
    b = market_regime._breadth_stats(pairs, full=True)
    assert b["total"] == 4
    assert b["ups"] == 2       # 1.5, 9.95
    assert b["downs"] == 1     # -0.5
    assert b["flats"] == 1     # 0.0
    assert b["zt"] == 1        # 600519 封板
    assert b["full"] is True
    assert b["median"] == pytest.approx(0.75, abs=0.01)   # median([1.5,-0.5,0.0,9.95])=0.75


def test_stats_empty_returns_none():
    assert market_regime._breadth_stats([], full=True) is None
    assert market_regime._breadth_stats([("600000", None)], full=True) is None


def test_stats_full_flag_propagates():
    assert market_regime._breadth_stats([("600000", 1.0)], full=True)["full"] is True
    assert market_regime._breadth_stats([("600000", 1.0)], full=False)["full"] is False


# ---------- 集成: 真实全市场宽度 (依赖网络) ----------

@pytest.mark.skipif(os.environ.get("SKIP_NETWORK"), reason="SKIP_NETWORK=1 跳过网络测试")
def test_fetch_market_breadth_returns_full_market():
    """三源链(本地→东财→新浪)至少一源返回全市场量级(≥4000只)。
    本地源(当天数据齐)应首选命中; 本地过期/缺失时降级东财/新浪。绝不降级沪深300(非全市场)。"""
    b = market_regime.fetch_market_breadth()
    assert b is not None, "三源全失败, 宽度获取异常"
    assert b["total"] >= 4000, f"宽度非全市场量级: total={b['total']} source={b.get('source')}"
    assert "沪深300" not in b.get("source", ""), f"不该降级沪深300(非全市场): {b['source']}"


# ---------- 单元: 本地源当天校验 (核心新逻辑 — 宁拒勿用过期数据) ----------

def test_try_local_breadth_rejects_stale_data(monkeypatch):
    """本地源最近性: latest_date 距今天 > 4 天(长假中段/长期未下载)→ 拒绝。"""
    monkeypatch.setattr(market_regime, "HAS_LOCAL", True)
    monkeypatch.setattr(local_kline, "fetch_local_breadth",
                        lambda: ([("600000", 1.0)] * 5000, "2026-07-14", 5000))
    b, why = market_regime._try_local_breadth(today=datetime.date(2026, 7, 21))   # 距 7 天 > 4
    assert b is None
    assert "过时" in why


def test_try_local_breadth_accepts_recent_tradeday_over_weekend(monkeypatch):
    """周末/非交易日跑: 周五数据(距今≤4天)应视为最近交易日有效数据(本次改动核心)。"""
    monkeypatch.setattr(market_regime, "HAS_LOCAL", True)
    pairs = [("600000", 9.95)] * 5000
    monkeypatch.setattr(local_kline, "fetch_local_breadth",
                        lambda: (pairs, "2026-07-24", 5000))                       # 周五
    b, why = market_regime._try_local_breadth(today=datetime.date(2026, 7, 26))    # 周日, 距 2 天
    assert b is not None and why is None
    assert b["source"] == "本地vipdoc(2026-07-24)"


def test_try_local_breadth_rejects_low_coverage(monkeypatch):
    """本地源覆盖率<3000(客户端未下全) → 拒绝(防用残缺数据)。"""
    monkeypatch.setattr(market_regime, "HAS_LOCAL", True)
    monkeypatch.setattr(local_kline, "fetch_local_breadth",
                        lambda: ([("600000", 1.0)] * 100, "2026-07-21", 100))
    b, why = market_regime._try_local_breadth(today=datetime.date(2026, 7, 21))
    assert b is None
    assert "覆盖" in why


def test_try_local_breadth_accepts_valid_today(monkeypatch):
    """当天 + 覆盖达标 → 返回有效全市场宽度, source 标本地vipdoc。"""
    monkeypatch.setattr(market_regime, "HAS_LOCAL", True)
    pairs = [("600000", 9.95), ("300001", 19.95), ("000001", -0.5)] * 2000
    monkeypatch.setattr(local_kline, "fetch_local_breadth",
                        lambda: (pairs, "2026-07-21", 6000))
    b, why = market_regime._try_local_breadth(today=datetime.date(2026, 7, 21))
    assert b is not None and why is None
    assert b["source"].startswith("本地vipdoc")
    assert b["total"] == 6000 and b["full"] is True
