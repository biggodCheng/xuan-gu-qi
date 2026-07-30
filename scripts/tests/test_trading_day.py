# -*- coding: utf-8 -*-
"""trading_day 单测: 权威交易日解析(不信任本地系统时钟)。

背景: 本机 Windows w32time 服务停摆, 系统时钟会跨日漂移(实测 07-29↔07-30 跳变),
导致依赖 datetime.now()/$(date) 定"今天"的 skill 文件名/数据日错位。本模块从新浪
日K取最新交易日作为数据日真相; 仅在网络全失败时降级本地时钟(此时应配合 drift 警告)。
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import trading_day  # noqa: E402


class _FakeResp:
    """模拟 urllib urlopen 返回的响应对象(只需 .read())。"""
    def __init__(self, payload):
        self._payload = payload if isinstance(payload, bytes) else payload.encode("utf-8")

    def read(self):
        return self._payload


# ---------- latest_trading_day: 新浪解析 ----------

def test_latest_trading_day_parses_sina(monkeypatch):
    """新浪单根K线 → 取其 day 字段前10位(YYYY-MM-DD)。"""
    payload = json.dumps([{"day": "2026-07-30 15:00:00", "close": "1"}])
    monkeypatch.setattr(trading_day.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp(payload))
    assert trading_day.latest_trading_day() == "2026-07-30"


def test_latest_trading_day_takes_last_bar(monkeypatch):
    """多根K线时取最新(末尾)一根的日期。"""
    payload = json.dumps([{"day": "2026-07-28"}, {"day": "2026-07-29"}, {"day": "2026-07-30"}])
    monkeypatch.setattr(trading_day.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp(payload))
    assert trading_day.latest_trading_day() == "2026-07-30"


# ---------- latest_trading_day: 降级 ----------

def test_latest_trading_day_fallback_on_net_error(monkeypatch):
    """新浪网络异常 → 降级本地时钟日期(等于 local_today_str)。"""
    def boom(*a, **k):
        raise OSError("net")
    monkeypatch.setattr(trading_day.urllib.request, "urlopen", boom)
    assert trading_day.latest_trading_day() == trading_day.local_today_str()


def test_latest_trading_day_fallback_on_bad_json(monkeypatch):
    """新浪返回非 JSON / 空 → 降级, 不崩。"""
    monkeypatch.setattr(trading_day.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp("not json"))
    assert trading_day.latest_trading_day() == trading_day.local_today_str()


def test_latest_trading_day_fallback_on_empty_list(monkeypatch):
    """新浪返回空数组 → 降级。"""
    monkeypatch.setattr(trading_day.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResp("[]"))
    assert trading_day.latest_trading_day() == trading_day.local_today_str()


# ---------- drift_days ----------

def test_drift_days_zero_when_equal():
    assert trading_day.drift_days("2026-07-30", "2026-07-30") == 0


def test_drift_days_positive_when_clock_behind():
    """本地时钟=07-29(偏慢), 权威交易日=07-30 → +1。"""
    assert trading_day.drift_days("2026-07-29", "2026-07-30") == 1


def test_drift_days_negative_when_clock_ahead():
    """本地时钟=07-31(偏快跨日), 权威交易日=07-30 → -1。"""
    assert trading_day.drift_days("2026-07-31", "2026-07-30") == -1
