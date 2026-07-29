# -*- coding: utf-8 -*-
"""维度2(A50期货 + 中概)parser 测试。基于 probe 真实 fixture。

probe 实测(2026-07-23 22:20):
- A50(hf_CHA50CFD)可达,15 字段:[0]价 [7]昨收 → parser 自算 pct = (price-prev)/prev*100。
- 金龙(gb_hxc)/中概(gb_baba)字段同美股格式:[0]名称 [1]价 [2]涨跌幅%。
"""
import os
import pytest
from pk import a50_cnr

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sina_a50_cnr.txt")


def test_parse_a50_cnr():
    with open(FIX, encoding="utf-8") as f:
        raw = f.read()
    d = a50_cnr.parse_a50_cnr(raw)
    assert "a50" in d
    assert isinstance(d["cnr"], list)
    if d["a50"]:
        assert "pct" in d["a50"]


def test_parse_a50_cnr_fixture_a50_present_cnr_present():
    # fixture 中 A50(hf_CHA50CFD)实测可达 → a50 非 None,pct 为自算值
    with open(FIX, encoding="utf-8") as f:
        raw = f.read()
    d = a50_cnr.parse_a50_cnr(raw)
    assert d["a50"] is not None
    # price=[0]=15165.200, prev=[7]=15232.000(真昨收,fixture)
    assert d["a50"]["price"] == pytest.approx(15165.200, abs=1e-9)
    # pct 自算:(price-prev)/prev*100 — 数学验证 IDX_PRICE_HF=0 / IDX_PREV_HF=7
    expected_pct = (15165.200 - 15232.000) / 15232.000 * 100
    assert d["a50"]["pct"] == pytest.approx(expected_pct, abs=1e-9)
    # 金龙 + 阿里 应进 cnr(pct 直接取 gb_ [2]字段)
    names = [c["name"] for c in d["cnr"]]
    assert "金龙中国" in names and "阿里" in names
    hxc = next(c for c in d["cnr"] if c["name"] == "金龙中国")
    assert hxc["pct"] == pytest.approx(0.03, abs=1e-9)   # gb_hxc [2]=0.03


def test_parse_a50_cnr_a50_missing_when_empty():
    # A50 代码在 wire 里但 payload 空 → a50=None
    raw = 'var hf_CHA50CFD="";var gb_baba="阿里,116.56,-1.20,ts,-1";'
    d = a50_cnr.parse_a50_cnr(raw)
    assert d["a50"] is None
    assert len(d["cnr"]) == 1
    assert d["cnr"][0]["pct"] == pytest.approx(-1.20, abs=1e-9)


def test_parse_a50_cnr_strips_hq_str_prefix():
    # 真实 wire 带 hq_str_ 前缀,parser 须剥掉再查 code;无 A50 行 → a50=None
    raw = 'var hq_str_gb_hxc="金龙,6180.98,-1.80,ts,-1";'
    d = a50_cnr.parse_a50_cnr(raw)
    assert d["a50"] is None
    assert len(d["cnr"]) == 1
    assert d["cnr"][0]["pct"] == pytest.approx(-1.80, abs=1e-9)


def test_pick_hf_prev_zero_returns_none():
    # prev[7]<=0 应返回 None(防除零);[7]="0" 触发 prev<=0 分支
    fields = ["100", "", "100", "100", "110", "90", "22:00:00", "0", "100", "", "", "", "2026-07-23", "名", "0"]
    assert a50_cnr._pick_hf(fields) is None


def test_pick_hf_malformed_returns_none():
    # 非数字 price([0])/prev([7]) 应返回 None(不抛);此处 [0] 非数字
    bad = ["NOTANUM", "", "100", "100", "110", "90", "22:00:00", "100", "100", "", "", "", "2026-07-23", "名", "0"]
    assert a50_cnr._pick_hf(bad) is None
    short = ["100"]   # 字段不足(缺 [7] 昨收)
    assert a50_cnr._pick_hf(short) is None
