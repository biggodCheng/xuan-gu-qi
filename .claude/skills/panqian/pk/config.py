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
# A50 新浪代码 hf_CHA50CFD(probe 2026-07-23 实测 15 字段可达);原 hf_CN 是错代码(新浪无此标的)。
A50_CODE = ("hf_CHA50CFD", "富时中国A50期货")
# 备份:主代码失效时降级用(恒指期货,同 hf_ 字段布局);可选,fetch 内尝试。
A50_BACKUP = ("hf_HSI", "恒生指数期货")
CNR_DRAGON = ("gb_hxc", "金龙中国")
CNR_STOCKS = [
    ("gb_baba", "阿里"), ("gb_jd", "京东"), ("gb_pdd", "拼多多"),
    ("gb_bidu", "百度"), ("gb_ntes", "网易"),
]

# 维度3:汇率 + 大宗
FX = [("fx_susdcnh", "离岸人民币")]
# 大宗新浪代码必须大写 hf_GC/CL/HG(probe 实测可达);原小写 hf_gc/cl/cu 是错代码,且铜 cu 错(应为 HG)。
COMMODITY = [
    ("hf_GC", "COMEX金"), ("hf_CL", "WTI原油"), ("hf_HG", "伦铜"),
]

# 维度4 新闻关键词
NEWS_KEYWORDS = [
    "美联储", "加息", "降息", "缩表", "CPI", "非农", "PPI", "PMI", "GDP",
    "地缘", "冲突", "战争", "制裁", "关税", "贸易", "财报", "央行",
    "欧央行", "黑天鹅", "突发",
    # 隔夜市场信号(美股/大宗)是 A 股盘前核心映射,东财7x24 主源接入后补齐
    "美股", "纳指", "道指", "标普", "黄金", "白银", "原油", "布油",
    # 盘前宏观信号(reviewer 数据驱动补齐:titleColor=3 红字中被关键词误杀的有效信号)
    "特斯拉", "失业", "国债", "收益率", "美元", "美债",
]
POLICY_KEYWORDS = [
    "央行", "货币政策", "LPR", "降准", "MLF", "逆回购", "金融监管",
    "国务院", "证监会", "银保监", "发改委", "财政部", "产业政策",
]

CRITICAL_DIMS = ["us", "a50"]
