# -*- coding: utf-8 -*-
"""盘前外部温度计 (panqian) — 编排。
盘前采集 4 维隔夜信号 → 渲染「盘前外部温度计.md」。不预测涨跌。
对齐 fupan:屏蔽代理+trust_env=False、utf-8 stdout、argparse+步骤打印、写 output/{date}.md。

用法:
  python .claude/skills/panqian/main.py              # 默认盘前跑
  python .claude/skills/panqian/main.py --note "..."
"""
import argparse
import os
import sys

# Windows 中文控制台默认 GBK(cp936) 编不出 emoji(⚠️), print 会 UnicodeEncodeError;
# 统一 stdout/stderr 用 utf-8(失败则忽略, 不阻断)。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# 复用项目根 scripts/trading_day: 用新浪权威交易日, 免疫本机系统时钟漂移
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SKILL_DIR)))
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if os.path.isdir(_SCRIPTS_DIR) and _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
import trading_day

from datetime import datetime

from pk import config
from pk.base import FetchResult
from pk.us_stock import fetch_us
from pk.a50_cnr import fetch_a50_cnr
from pk.fx_commodity import fetch_fx_comm
from pk.news import fetch_news
from pk.mappings import tone, signal_strength
from pk.render import render

OUT_DIR = config.OUT_DIR

# Windows utf-8 输出(与 fupan 一致,防 emoji 崩)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CRITICAL = config.CRITICAL_DIMS   # ["us","a50"]:缺失需报告顶部明示


def fetch_all():
    """采集 4 维,返回 {dim: FetchResult}。各维独立,互不阻断。"""
    res = {}
    print("[1/4] 美股+VIX ...")
    res["us"] = fetch_us()
    print(f"      {res['us'].detail}")
    print("[2/4] A50+中概 ...")
    res["a50"] = fetch_a50_cnr()
    print(f"      {res['a50'].detail}")
    print("[3/4] 汇率+大宗 ...")
    res["fx"] = fetch_fx_comm()
    print(f"      {res['fx'].detail}")
    print("[4/4] 国际新闻 ...")
    res["news"] = fetch_news()
    print(f"      {res['news'].detail}")
    return res


def _us_pct(res):
    idx = (res["us"].data or {}).get("indices", []) if res["us"].ok else []
    nas = next((i for i in idx if i["name"] == "纳指"), None)
    return nas["pct"] if nas else 0.0


def _a50_pct(res):
    if not res["a50"].ok:
        return None
    a50 = (res["a50"].data or {}).get("a50")
    return a50["pct"] if a50 else None


def build_report_data(date_str, res, note=""):
    """4 维 FetchResult → render 所需 dict。"""
    us_pct = _us_pct(res)
    a50_pct = _a50_pct(res)
    vix = (res["us"].data or {}).get("vix") if res["us"].ok else None
    critical_missing = any(not res[d].ok for d in CRITICAL)

    q = {
        "us":   (res["us"].detail or "")[:1] if res["us"].ok else "⚠️",
        "a50":  "✓" if res["a50"].ok else "⚠️",
        "cnr":  "✓" if (res["a50"].data or {}).get("cnr") else "-",
        "fx":   "✓" if res["fx"].ok else "⚠️",
        "comm": "✓" if (res["fx"].data or {}).get("comm") else "-",
        "news": "✓" if res["news"].ok else "⚠️",
    }
    for k in q:
        if "✓" in q[k]:
            q[k] = "✓"
        elif q[k] in ("-", ""):
            q[k] = "-"
        else:
            q[k] = "⚠️"

    return {
        "date_str": date_str,
        "tone": tone(us_pct, a50_pct, vix or 0),
        "strength": signal_strength(us_pct, a50_pct, vix or 0),
        "us": res["us"].data if res["us"].ok else {"indices": [], "vix": None},
        "a50": res["a50"].data,
        "fx": res["fx"].data,
        "news": res["news"].data,
        "quality": q,
        "critical_missing": critical_missing,
        "note": note,
    }


def run(date_str=None, note=""):
    date_str = date_str or trading_day.latest_trading_day()
    trading_day.warn_if_drift(date_str)
    print(f"[{date_str}] 盘前外部温度计\n")
    res = fetch_all()
    data = build_report_data(date_str, res, note)
    md = render(data)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{date_str}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\n报告 -> {out_path}")
    if data["critical_missing"]:
        print("⚠️ 关键维(A50/美股)缺失,报告已明示盲区")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="盘前外部温度计")
    ap.add_argument("--note", default="", help="备注")
    args = ap.parse_args()
    run(note=args.note)


if __name__ == "__main__":
    main()
