"""探测东财行业板块资金流接口 — 开发/维护用。

确认: ① 接口可用(push2delay + 系统代理) ② 字段语义 ③ 两端取数 ④ 去重策略有效。
接口改版/被封时重跑此脚本诊断。非测试覆盖部分,仅供人工核查。
"""
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests

_S = requests.Session()
_S.trust_env = True   # 跟随系统代理(同 renqibang), push2delay 直连会被关
_S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})

URL = "http://push2delay.eastmoney.com/api/qt/clist/get"
FS = "m:90+t:2+f:!50"
FIELDS = "f12,f14,f3,f62,f184,f66,f72"
_SUF = re.compile(r"[ⅡⅢⅣⅤⅥ]")


def fetch(po: int, pz: int = 100) -> list:
    params = {"pn": "1", "pz": str(pz), "po": str(po),
              "fid": "f62", "fs": FS, "fields": FIELDS, "fltt": "2"}
    r = _S.get(URL, params=params, timeout=15)
    data = (r.json() or {}).get("data") or {}
    diff = data.get("diff") or []
    items = list(diff.values()) if isinstance(diff, dict) else list(diff)
    print(f"  po={po} pz={pz} → status={r.status_code} total={data.get('total')} rows={len(items)}")
    return items


def dedup(items):
    """端内按 (f62,f184) 去重, 保留无罗马后缀名者。"""
    best = {}
    for it in items:
        if it.get("f62") is None:
            continue
        key = (it["f62"], it.get("f184"))
        cur = best.get(key)
        if cur is None or (_SUF.search(cur.get("f14", "")) and not _SUF.search(it.get("f14", ""))):
            best[key] = it
    return list(best.values())


if __name__ == "__main__":
    print("=== 流入端 (po=1 降序) ===")
    inflow = fetch(po=1)
    print("=== 流出端 (po=0 升序) ===")
    outflow = fetch(po=0)

    print("\n=== 流入端去重前/后 ===", len(inflow), "→", len(dedup(inflow)))
    print("Top 8 流入:")
    for it in dedup(inflow)[:8]:
        print(f"  {it.get('f14'):<12} f3={it.get('f3'):>6}%  f62={it.get('f62',0)/1e8:>7.2f}亿  f184={it.get('f184')}%  [{it.get('f12')}]")

    print("\n=== 流出端去重前/后 ===", len(outflow), "→", len(dedup(outflow)))
    print("Top 8 流出:")
    for it in dedup(outflow)[:8]:
        print(f"  {it.get('f14'):<12} f3={it.get('f3'):>6}%  f62={it.get('f62',0)/1e8:>7.2f}亿  f184={it.get('f184')}%  [{it.get('f12')}]")

    print("\n✅ 若两端都有合理数据(流入为正/流出为负, 行业名正常), 接口与去重策略可用。")
