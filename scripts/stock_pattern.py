# -*- coding: utf-8 -*-
"""首板成色判定 单票 CLI。
用法:
  python scripts/stock_pattern.py 000428              # 单只(默认首板)
  python scripts/stock_pattern.py 000428,001358        # 多只
  python scripts/stock_pattern.py 000428 --height 3    # 指定连板高度
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(encoding="utf-8")  # 防 Windows GBK 崩溃
except Exception:
    pass

import pattern_label  # noqa: E402


def _prefix(code):
    """6位代码 → 推断市场前缀。60/68/9→sh, 00/30→sz, 8/4/920→bj。"""
    c = code.lstrip()
    if c.startswith(("60", "68", "9")):
        return "sh"
    if c.startswith(("00", "30")):
        return "sz"
    return "bj"


def run(codes, height=1):
    """codes: ['sz000428'] 或 ['000428'](自动补前缀)。打印每只三层判定。"""
    for raw in codes:
        sym = raw if raw[:2] in ("sh", "sz", "bj") else f"{_prefix(raw)}{raw}"
        r = pattern_label.label(sym, height=height)
        if "error" in r:
            print(f"{sym}: {r['error']}")
            continue
        m = r["metrics"]
        print(f"\n{sym}")
        print(f"  形态: {r['shape']:<8}(vol20 {m.get('volatility20','?')}% / "
              f"retracement {m.get('retracement','?')}% / breakout {m.get('breakout','?')})")
        print(f"  量能: {r['volume']:<8}(vr {m.get('vr','?')} / seal {m.get('seal','?')} / "
              f"amp {m.get('amp','?')}%)")
        print(f"  板块: {r['sector']}")
        print(f"  → 建议归类: {r['suggest']}（参考·需人工确认）")


def main():
    ap = argparse.ArgumentParser(description="首板成色判定 单票CLI")
    ap.add_argument("codes", help="股票代码,逗号分隔(000428,001358)")
    ap.add_argument("--height", type=int, default=1, help="连板高度(默认1=首板)")
    args = ap.parse_args()
    run([c.strip() for c in args.codes.split(",") if c.strip()], height=args.height)


if __name__ == "__main__":
    main()
