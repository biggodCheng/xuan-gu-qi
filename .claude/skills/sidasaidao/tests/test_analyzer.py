# -*- coding: utf-8 -*-
"""sidasaidao 匹配逻辑单测。

重点验证 2026-07-20 的过匹配修复：
主业无关（industry 不命中赛道）且仅靠 1 个附带概念命中的赛道，视为边缘命中（低），不计入结果。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.analyzer import match_tracks, _calc_confidence


# ============ match_tracks：边缘命中过滤 ============

def test_haizheng_no_industry_single_concept_filtered():
    """海正药业式误判：主业化学原料药(非四大赛道)，仅靠'AI应用（医药医疗）'1个概念命中AI硬件
    → 视为边缘命中(低)，不返回AI硬件赛道，整体不属于四大赛道。"""
    tracks = match_tracks("化学原料药", ["AI应用（医药医疗）"])
    names = [t["track"] for t in tracks]
    assert "AI硬件和基础设施" not in names
    assert tracks == []


def test_no_industry_two_concepts_kept_as_mid():
    """主业无关但≥2个独立概念命中 → 保留为'中'（多概念支撑，非边缘）。"""
    tracks = match_tracks("农业", ["芯片", "半导体"])
    ai = next(t for t in tracks if t["track"] == "AI硬件和基础设施")
    assert ai["confidence"] == "中"


def test_industry_hit_can_be_high():
    """主业命中赛道 → 可达'高'。"""
    tracks = match_tracks("汽车整车", ["新能源车", "电池"])
    dagongye = next(t for t in tracks if t["track"] == "大工业")
    assert dagongye["confidence"] == "高"


def test_haizheng_full_concepts_no_track():
    """海正药业完整概念集（31个，含'AI应用（医药医疗）'）→ 不属于四大赛道。"""
    concepts = [
        "化学原料药", "基金重仓", "出口退税", "超级细菌", "保险重仓", "社保重仓",
        "融资融券", "生物疫苗", "抗癌", "免疫治疗", "仿制药", "创新药", "中盘",
        "抗癌药物", "昨日涨停", "国资改革", "动物疫苗", "养老产业", "医药电商",
        "医疗美容", "抗流感", "原料药", "宠物经济", "合成生物", "AI应用（医药医疗）",
        "DeepSeek概念", "生物医药", "禽流感药物", "浙江国资", "阿尔茨海默", "预盈预增",
    ]
    tracks = match_tracks("化学原料药", concepts)
    assert tracks == []


# ============ _calc_confidence：无行业命中分支 ============

def test_conf_no_industry_zero_concept_low():
    """无行业命中 + 0 独立概念 → 低。"""
    conf = _calc_confidence(
        matched_keywords={"AI应用"},
        matched_from={"industry": [], "concepts": []},  # 无概念命中（kw 命中但记录到 sub_cat）
        matched_sub_cats={"AI应用"},
    )
    assert conf == "低"


def test_conf_no_industry_one_concept_low():
    """无行业命中 + 1 独立概念 → 低（单概念不论 kw/subcat 计数）。"""
    conf = _calc_confidence(
        matched_keywords={"AI应用"},
        matched_from={"industry": [], "concepts": ["AI应用（医药医疗）"]},
        matched_sub_cats={"AI应用"},
    )
    assert conf == "低"


def test_conf_no_industry_two_concepts_mid():
    """无行业命中 + 2 独立概念 → 中。"""
    conf = _calc_confidence(
        matched_keywords={"芯片", "半导体"},
        matched_from={"industry": [], "concepts": ["芯片", "半导体"]},
        matched_sub_cats={"芯片设计"},
    )
    assert conf == "中"


def test_conf_industry_hit_concepts_high():
    """行业命中 + 有概念 → 高。"""
    conf = _calc_confidence(
        matched_keywords={"汽车", "新能源车"},
        matched_from={"industry": ["汽车整车"], "concepts": ["新能源车"]},
        matched_sub_cats={"汽车整车"},
    )
    assert conf == "高"
