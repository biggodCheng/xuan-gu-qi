# -*- coding: utf-8 -*-
"""维度3(汇率+大宗)parser 测试。基于 probe 真实 fixture。

probe 实测(2026-07-23):
- fx_susdcnh 可达,18 字段;[11]=pct(decimal,×100) → fixture 中 0.0021 → 0.21%。
- hf_gc/hf_cl/hf_cu 全空 payload → comm=[](非关键维,不阻断)。
"""
import os
import pytest
from pk import fx_commodity

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "sina_fx_comm.txt")


def _load_fix():
    with open(FIX, encoding="utf-8") as f:
        return f.read()


def test_parse_fx_comm():
    d = fx_commodity.parse_fx_comm(_load_fix())
    assert isinstance(d["fx"], list) and isinstance(d["comm"], list)
    for it in d["fx"] + d["comm"]:
        assert "name" in it and "pct" in it
        assert isinstance(it["pct"], float)


def test_parse_fx_comm_fx_extracted_with_calibrated_pct():
    # fixture 中 fx_susdcnh [11]=0.0021 → ×100 → 0.21%
    d = fx_commodity.parse_fx_comm(_load_fix())
    assert len(d["fx"]) == 1
    fx = d["fx"][0]
    assert fx["name"] == "离岸人民币"
    # IDX_PCT_FX=11, decimal-to-percent: 0.0021 * 100 = 0.21
    assert fx["pct"] == pytest.approx(0.21, abs=1e-9)


def test_parse_fx_comm_commodities_empty_when_hf_unavailable():
    # probe 实测 hf_gc/hf_cl/hf_cu 全空 → comm 应为空列表
    d = fx_commodity.parse_fx_comm(_load_fix())
    assert d["comm"] == []


def test_parse_fx_comm_strips_hq_str_prefix():
    # 真实 wire 带 hq_str_ 前缀,parser 须剥掉后再查 code
    raw = 'var hq_str_fx_susdcnh="t,6.78,6.78,6.78,1,6.78,6.78,6.78,6.78,n,0.01,0.0014,0.001,,7,6.7,,d";'
    d = fx_commodity.parse_fx_comm(raw)
    assert len(d["fx"]) == 1
    assert d["fx"][0]["pct"] == pytest.approx(0.14, abs=1e-9)  # 0.0014 * 100


def test_parse_fx_comm_ignores_empty_payload():
    d = fx_commodity.parse_fx_comm('var hq_str_fx_susdcnh="";')
    assert d["fx"] == []
    assert d["comm"] == []


def test_parse_fx_comm_skips_malformed_pct():
    # [11] 非数字 / NaN 均应跳过该条而不崩
    raw_nan = 'var hq_str_fx_susdcnh="t,6.78,bid,ask,1,open,high,low,prev,name,chg,NaN,amp,,y,d";'
    d_nan = fx_commodity.parse_fx_comm(raw_nan)
    assert d_nan["fx"] == []
    raw_str = 'var hq_str_fx_susdcnh="t,6.78,bid,ask,1,open,high,low,prev,name,chg,NOTANUM,amp,,y,d";'
    d_str = fx_commodity.parse_fx_comm(raw_str)
    assert d_str["fx"] == []
