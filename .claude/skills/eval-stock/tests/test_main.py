# -*- coding: utf-8 -*-
"""main.py 兜底逻辑测试：bridges 加载失败不崩溃、纯代码不经 resolve。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import main as m


def test_eval_q2_when_q2_not_loaded(monkeypatch):
    # 模拟 Q2 模块未加载 → 返回"数据不可用"，不崩溃
    monkeypatch.setattr(m, "_Q2", None)
    r = m._eval_q2("000021")
    assert r["verdict"] == "数据不可用"
    assert r["netprofit_yoy"] is None
    assert r["revenue_yoy"] is None
    assert r["confidence"] == "低"


def test_eval_track_when_sid_not_loaded(monkeypatch):
    # 模拟赛道模块未加载 → 返回空 track + 空 industry，不崩溃
    monkeypatch.setattr(m, "_SID", None)
    track, industry = m._eval_track("000021")
    assert track["tracks"] == []
    assert track["main"] == ""
    assert track["main_conf"] == ""
    assert industry == ""


def test_evaluate_one_pure_code_does_not_need_sid(monkeypatch):
    # 纯代码输入：即使 _SID 为 None，也能进入取数流程（不返回"名称解析不可用"错误）
    monkeypatch.setattr(m, "_SID", None)
    monkeypatch.setattr(m, "_LOADED", True)   # 避免 _lazy_load 覆盖我们的 None
    monkeypatch.setattr(m, "_Q2", None)       # Q2 也未加载，走兜底
    # 避免联网：短路取数函数
    monkeypatch.setattr(m, "fetch_kline", lambda code, days: [])
    monkeypatch.setattr(m, "fetch_marketcap", lambda code: (None, None))
    r = m.evaluate_one("000021")
    # 关键断言：纯代码被路由成功，未因 _SID=None 触发 resolve 报错
    assert r["code"] == "000021"
    assert r["error"] is None
    # Q2 兜底生效
    assert r["q2"]["verdict"] == "数据不可用"


def test_evaluate_one_name_query_without_sid_returns_resolve_error(monkeypatch):
    # 名称输入且 _SID=None → 返回"名称解析不可用"错误，而非崩溃
    monkeypatch.setattr(m, "_SID", None)
    monkeypatch.setattr(m, "_LOADED", True)
    r = m.evaluate_one("深科技")
    assert r["code"] == ""
    assert "名称解析不可用" in r["error"]
