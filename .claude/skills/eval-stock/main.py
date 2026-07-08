# -*- coding: utf-8 -*-
"""eval-stock CLI：python main.py <代码或名称>[,...]
对每只股票跑 qsht 6 维度，终端打印 markdown 汇总。
"""
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import fetch_kline, fetch_marketcap, zt_threshold
from screener.analyzer import (
    check_new_high, check_recent_zt, check_pullback, check_marketcap,
)
from screener.bridges import get_q2_funcs, get_sid_funcs
from screener.reporter import format_report

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KLINE_DAYS = 130
_Q2 = None   # lazy
_SID = None
_LOADED = False


def _lazy_load():
    global _Q2, _SID, _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        _Q2 = get_q2_funcs()       # (get_financial, analyze)
    except Exception as e:
        print(f"[eval-stock] Q2 模块加载失败: {e}", file=sys.stderr)
        _Q2 = None
    try:
        _SID = get_sid_funcs()     # (resolve, get_detail, match_tracks)
    except Exception as e:
        print(f"[eval-stock] 赛道模块加载失败: {e}", file=sys.stderr)
        _SID = None


def _is_intraday(last_date: str) -> bool:
    if not last_date:
        return False
    now = datetime.now()
    if last_date != now.strftime("%Y-%m-%d"):
        return False
    # 交易时段：09:30–15:00
    return (now.hour > 9 or (now.hour == 9 and now.minute >= 30)) and now.hour < 15


def _eval_q2(code: str) -> dict:
    if not _Q2:
        return {"verdict": "数据不可用", "confidence": "低",
                "netprofit_yoy": None, "revenue_yoy": None,
                "summary": "Q2 模块未加载", "industry": ""}
    try:
        get_financial, analyze = _Q2
        fin = get_financial(code)
        industry = fin.get("industry", "")
        if not fin.get("reports"):
            return {"verdict": "数据不足", "confidence": "低",
                    "netprofit_yoy": None, "revenue_yoy": None,
                    "summary": "无财报", "industry": industry}
        r = analyze(fin)
        q1 = r.get("q1", {})
        out = r.get("q2_outlook", {})
        return {
            "verdict": out.get("verdict", "数据不足"),
            "confidence": out.get("confidence", "低"),
            "netprofit_yoy": q1.get("netprofit_yoy"),
            "revenue_yoy": q1.get("revenue_yoy"),
            "summary": out.get("summary", ""),
            "industry": r.get("industry", "") or industry,
        }
    except Exception as e:
        return {"verdict": "数据不可用", "confidence": "低",
                "netprofit_yoy": None, "revenue_yoy": None,
                "summary": f"加载失败: {e}", "industry": ""}


def _eval_track(code: str) -> tuple:
    """返回 (track_dict, industry)。"""
    if not _SID:
        return {"tracks": [], "main": "", "main_conf": ""}, ""
    try:
        _, get_detail, match = _SID
        detail = get_detail(code)
        industry = detail.get("industry", "")
        matched = match(industry, detail.get("concepts", []))
        tracks = [m["track"] for m in matched]
        main = matched[0]["track"] if matched else ""
        main_conf = matched[0]["confidence"] if matched else ""
        return {"tracks": tracks, "main": main, "main_conf": main_conf}, industry
    except Exception:
        return {"tracks": [], "main": "", "main_conf": ""}, ""


def evaluate_one(query: str) -> dict:
    _lazy_load()
    query = query.strip()
    code, name = None, None
    if re.match(r"^[03468]\d{5}$", query):
        code = query                       # 纯代码直接用，不依赖 sidasaidao
    elif _SID:
        resolve, _, _ = _SID
        try:
            code, name = resolve(query)
        except Exception:
            code, name = None, None
    if not code:
        return {"code": "", "name": query, "error": f"未找到股票或名称解析不可用: {query}"}

    kline = fetch_kline(code, KLINE_DAYS)
    total, circ = fetch_marketcap(code)

    threshold = zt_threshold(code)
    nh = check_new_high(kline)
    zt = check_recent_zt(kline, threshold)
    pb = check_pullback(kline, zt.get("_raw", []))
    mc = check_marketcap(total, circ)
    q2 = _eval_q2(code)
    track, industry = _eval_track(code)
    if not industry:
        industry = q2.get("industry", "")

    last_date = kline[-1]["date"] if kline else ""
    last_close = kline[-1]["close"] if kline else None

    return {
        "code": code, "name": name, "industry": industry,
        "last_date": last_date, "last_close": last_close,
        "intraday": _is_intraday(last_date),
        "new_high": nh, "zt": zt, "pullback": pb, "marketcap": mc,
        "q2": q2, "track": track, "error": None,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python main.py <代码或名称>[,...]")
        print("示例: python main.py 深科技,有研新材")
        sys.exit(1)
    queries = [q.strip() for q in sys.argv[1].split(",") if q.strip()]
    for i, q in enumerate(queries):
        stock = evaluate_one(q)
        if i:
            print("\n")
        print(format_report(stock))


if __name__ == "__main__":
    main()
