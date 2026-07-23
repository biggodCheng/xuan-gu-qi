# -*- coding: utf-8 -*-
"""panqian 配置:路径、代理、session、代码常量、关键词。"""
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .claude/skills/panqian
OUT_DIR = os.path.join(SKILL_DIR, "output")
TESTS_DIR = os.path.join(SKILL_DIR, "tests")
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")

# 本机 clash 代理(仅 Yahoo fallback 用;新浪/新闻直连)。
PROXY = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}

# 维度1 美股:新浪代码 → (展示名)
US_INDICES = [("gb_ixic", "纳指"), ("gb_inx", "标普500"), ("gb_dji", "道指")]
US_VIX = ("gb_vix", "VIX")

# 维度2:A50 期货 + 中概
A50_CODE = ("hf_CN", "富时A50")
CNR_DRAGON = ("gb_hxc", "金龙中国")
CNR_STOCKS = [
    ("gb_baba", "阿里"), ("gb_jd", "京东"), ("gb_pdd", "拼多多"),
    ("gb_bidu", "百度"), ("gb_ntes", "网易"),
]

# 维度3:汇率 + 大宗
FX = [("fx_susdcnh", "离岸人民币")]
COMMODITY = [
    ("hf_gc", "COMEX金"), ("hf_cl", "WTI原油"), ("hf_cu", "伦铜"),
]

# 维度4 新闻关键词
NEWS_KEYWORDS = [
    "美联储", "加息", "降息", "缩表", "CPI", "非农", "PPI", "PMI", "GDP",
    "地缘", "冲突", "战争", "制裁", "关税", "贸易", "财报", "央行",
    "欧央行", "黑天鹅", "突发",
]
POLICY_KEYWORDS = [
    "央行", "货币政策", "LPR", "降准", "MLF", "逆回购", "金融监管",
    "国务院", "证监会", "银保监", "发改委", "财政部", "产业政策",
]

CRITICAL_DIMS = ["us", "a50"]
