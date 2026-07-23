# -*- coding: utf-8 -*-
"""维度2(A50期货 + 中概)parser 测试。基于 probe 真实 fixture。

probe 实测(2026-07-23):
- A50(hf_CN)新浪返回空 payload → parser 应输出 a50=None(fetch 据此降级)。
- 金龙(gb_hxc)/中概(gb_baba)字段同美股格式:[0]名称 [1]价 [2]涨跌幅%。
"""
import os
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


def test_parse_a50_cnr_a50_missing():
    # 无 hq_str_ 前缀的 mock,parser 须兼容;A50 空 → a50=None
    raw = 'var hf_CN="";var gb_baba="阿里,-2.5";'
    d = a50_cnr.parse_a50_cnr(raw)
    assert d["a50"] is None


def test_parse_a50_cnr_fixture_a50_empty_cnr_present():
    # fixture 中 A50 实测空,a50 应为 None;金龙+阿里应进 cnr
    with open(FIX, encoding="utf-8") as f:
        raw = f.read()
    d = a50_cnr.parse_a50_cnr(raw)
    assert d["a50"] is None  # A50(hf_CN)新浪实测空
    names = [c["name"] for c in d["cnr"]]
    assert "金龙中国" in names and "阿里" in names
    # 校准验证:gb_hxc [1]=6180.98 [2]=-1.80
    hxc = next(c for c in d["cnr"] if c["name"] == "金龙中国")
    assert hxc["pct"] == -1.80


def test_parse_a50_cnr_strips_hq_str_prefix():
    # 真实 wire 带 hq_str_ 前缀,parser 须剥掉再查 code
    raw = 'var hq_str_gb_hxc="金龙,6180.98,-1.80,ts,-1";'
    d = a50_cnr.parse_a50_cnr(raw)
    assert d["a50"] is None
    assert len(d["cnr"]) == 1
    assert d["cnr"][0]["pct"] == -1.80
