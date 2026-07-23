# -*- coding: utf-8 -*-
"""维度3(汇率+大宗)parser 测试。基于 probe 真实 fixture。

probe 实测(2026-07-23 22:20):
- fx_susdcnh 可达,18 字段;[11]=pct(decimal,×100) → fixture 中 0.0023 → 0.23%。
- hf_GC/hf_CL/hf_HG 可达,15 字段:[0]价 [3]昨收 → parser 自算 pct = (price-prev)/prev*100。
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
    # fixture 中 fx_susdcnh [11]=0.0023 → ×100 → 0.23%
    d = fx_commodity.parse_fx_comm(_load_fix())
    assert len(d["fx"]) == 1
    fx = d["fx"][0]
    assert fx["name"] == "离岸人民币"
    # IDX_PCT_FX=11, decimal-to-percent: 0.0023 * 100 = 0.23
    assert fx["pct"] == pytest.approx(0.23, abs=1e-9)


def test_parse_fx_comm_commodities_self_calc_pct():
    # hf_GC/CL/HG 实测可达 → comm 3 条,pct 从 price[0]+prev[3] 自算
    d = fx_commodity.parse_fx_comm(_load_fix())
    assert len(d["comm"]) == 3
    names = [c["name"] for c in d["comm"]]
    assert "COMEX金" in names and "WTI原油" in names and "伦铜" in names
    # GC: [0]=4046.550 [3]=4047.000 → pct 自算(数学验证 IDX_PREV_HF=3)
    gc = next(c for c in d["comm"] if c["name"] == "COMEX金")
    gc_pct = (4046.550 - 4047.000) / 4047.000 * 100
    assert gc["pct"] == pytest.approx(gc_pct, abs=1e-9)
    # CL: [0]=91.385 [3]=91.340
    cl = next(c for c in d["comm"] if c["name"] == "WTI原油")
    cl_pct = (91.385 - 91.340) / 91.340 * 100
    assert cl["pct"] == pytest.approx(cl_pct, abs=1e-9)
    # HG: [0]=637.310 [3]=637.450
    hg = next(c for c in d["comm"] if c["name"] == "伦铜")
    hg_pct = (637.310 - 637.450) / 637.450 * 100
    assert hg["pct"] == pytest.approx(hg_pct, abs=1e-9)


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


def test_parse_fx_comm_comm_prev_zero_skipped():
    # hf_ prev<=0 应跳过(防除零)
    raw = 'var hq_str_hf_GC="100,,100,0,110,90,t,0,0,0,0,0,2026-07-23,金,0";'
    d = fx_commodity.parse_fx_comm(raw)
    assert d["comm"] == []
