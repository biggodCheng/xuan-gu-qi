# -*- coding: utf-8 -*-
"""开发期探查:打印各候选接口真实返回,据此校准 parser 字段索引。
用法: python .claude/skills/panqian/probes/probe_all.py [us|a50|fx|news|all]
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Windows GBK 控制台无法编码 ⚠️ 等 emoji,统一切 UTF-8 输出(仅 probe 脚本)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from pk import base
from pk.config import US_INDICES, US_VIX, A50_CODE, CNR_DRAGON, CNR_STOCKS


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


def probe_a50():
    codes = [A50_CODE[0], CNR_DRAGON[0]] + [c for c, _ in CNR_STOCKS]
    print("\n=== A50+中概 probe ===")
    print("请求:", ",".join(codes))
    out = base.sina_quote(codes)
    for code, fields in out.items():
        print(f"\n[{code}] 字段数={len(fields)}")
        for i, f in enumerate(fields[:12]):
            print(f"  [{i}] {f!r}")
    if A50_CODE[0] not in out or not out[A50_CODE[0]]:
        print(f"⚠️ A50({A50_CODE[0]}) 取数失败 — A50 是关键维,失败需报告顶部明示盲区")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("us", "all"):
        probe_us()
    if which in ("a50", "all"):
        probe_a50()
