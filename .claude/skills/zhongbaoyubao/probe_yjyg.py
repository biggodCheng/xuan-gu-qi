"""探测东方财富业绩预告接口字段名。

运行: python probe_yjyg.py
打印第一条预增样本的全部字段,人工确认 reportName 与字段名后,
把结果填入 screener/fetcher.py 顶部常量。

================ 实测结果(2026-07-02) ================
reportName = RPT_PUBLIC_OP_PREDICT   (RPT_LICO_FN_CPD_GD 已不可用,success=False)
filter 用 (REPORTDATE='2026-06-30') 有效,返回含所有预告类型,代码内按类型过滤
字段映射:
  代码 SECURITY_CODE / 名称 SECURITY_NAME_ABBR / 行业 PUBLISHNAME
  公告日 NOTICE_DATE("2026-07-03 00:00:00",取[:10]) / 报告期 REPORTDATE
  预告类型 FORECASTTYPE(值"预增"/"预减"/"扭亏"/"续盈"...)
  同比下限% INCREASEL / 同比上限% INCREASET   ← 不是 CHANGE_RATE_*
  预测净利下限 FORECASTL / 上限 FORECASTT(元) / 中值 INCREASEJZ% FORECASTJZ
样本: 广钢气体688548 预增 87.19%~138.24%(2026中报)
======================================================
"""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))

# 统一 stdout/stderr 用 utf-8(失败则忽略, 不阻断)。修中文/emoji 在 GBK 控制台崩溃。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

_SESSION = requests.Session()
_SESSION.trust_env = False
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
})

# 候选 reportName(优先试这个,失败换 RPT_PUBLIC_OP_PREDICT)
REPORT_NAMES = ["RPT_LICO_FN_CPD_GD", "RPT_PUBLIC_OP_PREDICT"]


def probe(report_date="2026-06-30"):
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    for rn in REPORT_NAMES:
        params = {
            "sortColumns": "NOTICE_DATE",
            "sortTypes": "-1",
            "pageSize": "5",
            "pageNumber": "1",
            "reportName": rn,
            "columns": "ALL",
            "filter": f"(REPORTDATE='{report_date}')",
        }
        r = _SESSION.get(url, params=params, timeout=15)
        data = r.json()
        ok = data.get("success")
        rows = (data.get("result") or {}).get("data") or []
        print(f"\n=== reportName={rn} report_date={report_date} success={ok} rows={len(rows)} ===")
        if rows:
            print(json.dumps(rows[0], ensure_ascii=False, indent=2))
            print("\n-- 含 RATE/CHANGE/LOWER/UPPER/TYPE/PREDICT/NOTICE/PROFIT 的字段 --")
            for k, v in rows[0].items():
                kw = ("RATE", "CHANGE", "LOWER", "UPPER", "TYPE", "PREDICT", "NOTICE", "PROFIT")
                if any(x in k.upper() for x in kw):
                    print(f"  {k} = {v}")
            return rn
    print(f"两个 reportName 对 {report_date} 均无数据。")
    return None


if __name__ == "__main__":
    # 先试今年中报,无数据则退到去年中报确认字段结构
    rn = probe("2026-06-30")
    if not rn:
        print("\n>>> 退回 2025-06-30 确认字段结构 <<<")
        probe("2025-06-30")
