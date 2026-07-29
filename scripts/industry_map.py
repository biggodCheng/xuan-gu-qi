# -*- coding: utf-8 -*-
"""东财一级行业映射: code6 → 行业名。供 pattern_label.classify_sector 板块联动判定。

映射一次性从东财 push2delay 拉取缓存到 data/industry_map.json, 纯本地读取。
请求基础设施同 zijinliu/screener/fetcher.py (trust_env=True 跟随系统代理 + UA + Referer)。
刷新: python scripts/industry_map.py --refresh  (建议每月一次, 新股上市后跑)
"""
import json
import os
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.path.join(HERE, "..", "data", "industry_map.json")

_session = requests.Session()
_session.trust_env = True  # 跟随系统代理, push2delay 直连会被关
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})

CLIST_URL = "http://push2delay.eastmoney.com/api/qt/clist/get"
INDUSTRY_FS = "m:90+t:2+f:!50"   # 东财一级行业板块
RETRIES = 3


def load_map():
    """读 data/industry_map.json → {code6: 行业名}。文件不存在返回 {}。"""
    if not os.path.exists(MAP_PATH):
        return {}
    with open(MAP_PATH, encoding="utf-8") as f:
        return json.load(f)
