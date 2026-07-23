# -*- coding: utf-8 -*-
"""开发期探查:打印各候选接口真实返回,据此校准 parser 字段索引。
用法: python .claude/skills/panqian/probes/probe_all.py [us|a50|fx|news|all]
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pk import base
from pk.config import US_INDICES, US_VIX


def probe_us():
    codes = [c for c, _ in US_INDICES] + [US_VIX[0]]
    print("=== 美股+VIX probe ===")
    print("请求:", ",".join(codes))
    out = base.sina_quote(codes)
    for code, fields in out.items():
        print(f"\n[{code}] 字段数={len(fields)}")
        for i, f in enumerate(fields):
            print(f"  [{i}] {f!r}")
    if not out:
        print("⚠️ 新浪美股全失败 → 后续用 Yahoo ^IXIC/^GSPC/^DJI/^VIX(代理7897)替代")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("us", "all"):
        probe_us()
