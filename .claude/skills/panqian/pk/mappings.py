# -*- coding: utf-8 -*-
"""历史经验映射(经验·非预测)。
静态人工整理的经验法则,非程序化回测。仅辅助研判,不据此下单。
tone() 给第0步"隔夜定调",signal_strength() 给信号强度。
阈值是经验值,可随沉淀调整。"""


def tone(us_pct, a50_pct, vix):
    """外部环境定调:偏暖/中性/偏冷/恐慌。基于美股+A50+VIX 综合。
    注意:这是'外部环境',不是'A股今天涨跌'。"""
    # 恐慌:VIX 飙升(>30) + 美股大跌(<-2)
    if vix and vix > 30 and us_pct < -2:
        return "恐慌"
    # 偏冷:美股跌>1.5 或 A50跌>0.5
    if us_pct < -1.5 or (a50_pct is not None and a50_pct < -0.5):
        return "偏冷"
    # 偏暖:美股涨>1
    if us_pct > 1:
        return "偏暖"
    return "中性"


def signal_strength(us_pct, a50_pct, vix):
    """信号强度:强/中/弱。多源同向=强。"""
    cold = us_pct < -1.5 or (a50_pct is not None and a50_pct < -0.5)
    warm = us_pct > 1
    if (cold or warm) and vix and vix > 20:
        return "强"
    if cold or warm:
        return "中"
    return "弱"


# 第5步历史经验映射表(静态,经验非回测)
EXPERIENCE_TABLE = [
    {"signal": "纳指跌>1.5% & A50跌>0.5%", "experience": "A股低开概率较高,但低开高走 vs 低开低走看量能"},
    {"signal": "避险急升(VIX>20 & 金涨)", "experience": "防御板块(电力/医药/高股息)相对抗跌"},
    {"signal": "人民币急贬(离岸>0.3%)", "experience": "北向流出压力,核心资产承压;出口链相对受益"},
    {"signal": "油价大涨>3%", "experience": "石化/油服利好;航空/物流成本承压"},
    {"signal": "VIX单日飙升>30", "experience": "避险情绪极致,通常对应外围黑天鹅,A股跟跌但节奏看自身位置"},
]
