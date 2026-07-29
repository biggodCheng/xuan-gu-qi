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


def _clist(fs, fields, pz=500):
    """请求东财 clist, 返回 diff 列表(list[dict])。失败/重试耗尽返回 []。可被测试 mock。"""
    params = {"pn": "1", "pz": str(pz), "po": "1", "fid": "f3",
              "fs": fs, "fields": fields, "fltt": "2"}
    for attempt in range(RETRIES):
        try:
            payload = _session.get(CLIST_URL, params=params, timeout=15).json() or {}
            diff = (payload.get("data") or {}).get("diff") or []
            return list(diff.values()) if isinstance(diff, dict) else list(diff)
        except Exception as e:
            if attempt < RETRIES - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            print(f"push2delay 请求失败(fs={fs}): {e}", flush=True)
            return []


def refresh():
    """两层拉取构建 {code6: 行业名} 映射并落盘。
    1) 行业板块列表(fs=m:90+t:2+f:!50) → f12=BK代码, f14=行业名
    2) 每板块成分股(fs=b:BKxxxx) → f12=股票代码, 取后6位
    """
    industries = _clist(INDUSTRY_FS, "f12,f14")
    mapping = {}
    for ind in industries:
        bk = ind.get("f12")
        name = ind.get("f14")
        if not bk or not name:
            continue
        for s in _clist(f"b:{bk}", "f12", pz=500):
            code = (s.get("f12") or "")[-6:]
            if code.isdigit():
                mapping[code] = name
        time.sleep(0.1)  # 礼貌限频
    os.makedirs(os.path.dirname(MAP_PATH), exist_ok=True)
    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    return mapping


def main():
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="东财一级行业映射")
    ap.add_argument("--refresh", action="store_true", help="重新从东财拉取并缓存")
    args = ap.parse_args()
    if args.refresh:
        m = refresh()
        print(f"已刷新行业映射: {len(m)} 只股票 → {MAP_PATH}")
    else:
        print(f"当前映射: {len(load_map())} 只 (用 --refresh 刷新)")


if __name__ == "__main__":
    import sys
    main()
