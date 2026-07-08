# -*- coding: utf-8 -*-
"""
每日准入清单 (Daily Picks) — 准入工具 B
============================================================
把市况信号 + 准入清单 + qsht-agent 选股流水线打通。
读 qsht-agent 最新选股报告, 叠加实时市况信号和准入清单, 输出"今日可关注清单"。
回答: 今天市况如何? qsht 选出的票里, 哪几只符合准入清单可以买?

用法:
  python scripts/daily_picks.py                    # 用最新 qsht 输出 + 实时市况
  python scripts/daily_picks.py --qsht-date 2026-07-03  # 指定 qsht 输出日期
  python scripts/daily_picks.py --run-qsht         # 先自动跑 qsht-agent 再过滤(慢 10-25 分钟)

前置: 默认读 .claude/skills/qsht-agent/output/{日期}.md, 需先跑过 qsht-agent
输出: docs/trade-review/output/picks_{日期}.md
"""
import argparse
import glob
import os
import re
import subprocess
import sys
from datetime import datetime

from market_regime import (fetch_index_kline, trend_score, fetch_market_breadth,
                           breadth_score, grade, INDICES, LIGHT, ADVICE)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QSHT_OUT = os.path.join(ROOT, ".claude", "skills", "qsht-agent", "output")
OUT_DIR = os.path.join(ROOT, "docs", "trade-review", "output")


# ---------- 1. 找/读 qsht 输出 ----------
def latest_qsht_path(qsht_date=None):
    if qsht_date:
        p = os.path.join(QSHT_OUT, f"{qsht_date}.md")
        if os.path.exists(p):
            return p
        print(f"[WARN] 指定 qsht 输出不存在: {p}")
    files = [f for f in glob.glob(os.path.join(QSHT_OUT, "*.md"))
             if not os.path.basename(f).startswith("pullback")]
    if not files:
        return None
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def parse_table_rows(md, section_start):
    """提取某 ## 段落里的表格数据行(返回 list of cell-list)。"""
    i = md.find(section_start)
    if i < 0:
        return []
    j = md.find("\n## ", i + len(section_start))
    if j < 0:
        j = len(md)
    block = md[i:j]
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or not cells[0] or cells[0] in ("股票名称", "股票代码"):
            continue
        rows.append(cells)
    return rows


def parse_zt(md):
    """第2步近期涨停 → [{name,code,price,zt}]"""
    out = []
    for c in parse_table_rows(md, "## 第2步"):
        if len(c) >= 3:
            try:
                out.append(dict(name=c[0], code=c[1], price=float(c[2]),
                                zt=c[3] if len(c) > 3 else ""))
            except ValueError:
                pass
    return out


def parse_qibao(md):
    """起爆点信号 → {code: cells}"""
    return {c[1]: c for c in parse_table_rows(md, "## 起爆点信号") if len(c) >= 2}


def parse_final(md):
    """最终结果/第4步漏斗 → set(code)"""
    rows = parse_table_rows(md, "## 最终结果") or parse_table_rows(md, "## 第4步")
    return {c[1] for c in rows if len(c) >= 2}


def parse_q2_positive(md):
    """偏正/中性公司名称集合"""
    i = md.find("### 偏正/中性公司")
    if i < 0:
        return set()
    j = md.find("\n## ", i + 10)
    if j < 0:
        j = len(md)
    block = md[i:j]
    names = set()
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("*") or line.startswith(">") or "：" in line or not line:
            continue
        # 名称行: 中文逗号分隔
        for part in re.split(r"[，,、]", line):
            p = re.sub(r"[^一-龥A-Za-z0-9]", "", part)
            if 2 <= len(p) <= 6 and not re.search(r"[只信号数据]", p):
                names.add(p)
    return names


# ---------- 2. 市况(复用 market_regime) ----------
def get_regime():
    t_score = 0
    idx_infos = []
    for sym, label in INDICES:
        sc, info, _ = trend_score(fetch_index_kline(sym))
        t_score += sc
        idx_infos.append((label, sc, info))
    breadth = fetch_market_breadth()
    b_score = breadth_score(breadth)
    total = t_score + b_score
    color, name = grade(total)
    return dict(t=t_score, b=b_score, total=total, color=color, name=name,
                idx=idx_infos, breadth=breadth)


def price_tier(p):
    if p < 25:
        return "buy", "可买入(<25)"
    if p < 35:
        return "watch", "观察(25-35)"
    return "avoid", "回避(>35)"


def main():
    ap = argparse.ArgumentParser(description="每日准入清单(准入工具B)")
    ap.add_argument("--qsht-date", default="", help="qsht 输出日期 YYYY-MM-DD")
    ap.add_argument("--run-qsht", action="store_true", help="先自动跑 qsht-agent(慢)")
    args = ap.parse_args()

    if args.run_qsht:
        print("[0] 自动运行 qsht-agent (10-25 分钟) ...")
        subprocess.run([sys.executable, os.path.join(ROOT, ".claude", "skills", "qsht-agent", "main.py")], cwd=ROOT)

    qsht_path = latest_qsht_path(args.qsht_date)
    if not qsht_path:
        print("[ERR] 找不到 qsht 输出。先跑: python .claude/skills/qsht-agent/main.py")
        sys.exit(1)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(qsht_path))
    qsht_date = m.group(1) if m else "unknown"

    print(f"[1/3] 读 qsht 输出: {os.path.basename(qsht_path)}")
    md = open(qsht_path, encoding="utf-8").read()
    zt = parse_zt(md)
    qibao = parse_qibao(md)
    final = parse_final(md)
    q2pos = parse_q2_positive(md)
    print(f"      近期涨停 {len(zt)} | 起爆 {len(qibao)} | 最终漏斗 {len(final)} | Q2偏正/中 {len(q2pos)}")

    print("[2/3] 取实时市况信号 ...")
    reg = get_regime()
    print(f"      {reg['name']} (得分 {reg['total']:+d})")

    print("[3/3] 准入过滤 + 渲染 ...")
    cards = []
    for s in zt:
        tier, tier_name = price_tier(s["price"])
        cards.append(dict(
            name=s["name"], code=s["code"], price=s["price"], zt=s["zt"],
            tier=tier, tier_name=tier_name,
            is_qibao=s["code"] in qibao,
            is_final=s["code"] in final,
            q2="偏正" if (s["name"] in q2pos) else "",
        ))
    buyable = [c for c in cards if c["tier"] == "buy"]
    watch = [c for c in cards if c["tier"] == "watch"]
    avoid_n = sum(1 for c in cards if c["tier"] == "avoid")

    def rank(c):
        return (not c["is_final"], not c["is_qibao"], not c["q2"], c["price"])
    buyable.sort(key=rank)
    watch.sort(key=rank)

    # 渲染
    L = []
    a = L.append
    today = datetime.now().strftime("%Y-%m-%d")
    a(f"# 每日准入清单 · {today}\n")
    a(f"> 基于 qsht 选股({qsht_date}) + 实时市况 + 准入清单 8 条\n")
    a(f"## 市况: {LIGHT[reg['color']]} {reg['name']} · 得分 {reg['total']:+d} (趋势{reg['t']:+d}+宽度{reg['b']:+d})\n")
    for line in ADVICE[reg["color"]]:
        a(line)
    a("")
    if reg["color"] == "red":
        a("> ⛔ **退守市, 今日不开任何新仓。** 下面清单仅供观察选股池, 不要下单——这是你过去亏大钱的市况。\n")

    a(f"\n## ✅ 可买入池(价位<25, 满足准入[1][2]): {len(buyable)} 只\n")
    a("> 仍需逐项核对: [3]单笔<5万 [4]14:45后下单 [5]不补仓 [6]未连亏2笔 [7]3-5天/止损-5%/止盈+8%\n")
    if buyable:
        a("| 股票 | 代码 | 价 | 涨停日 | 起爆 | Q2 | 漏斗 |")
        a("|---|---|---|---|---|---|---|")
        for c in buyable:
            ztshort = (c["zt"][:16] + "…") if len(c["zt"]) > 16 else c["zt"]
            a(f"| {c['name']} | {c['code']} | {c['price']} | {ztshort} | {'是' if c['is_qibao'] else ''} | {c['q2']} | {'★' if c['is_final'] else ''} |")
    else:
        a("*(无——今日近期涨停股全部价位>25, 不符合准入。那就别买。)*")

    if watch:
        a(f"\n## 👀 观察池(价位25-35): {len(watch)} 只 (价位偏高, 暂不进场, 跟踪等回调)\n")
        a("| 股票 | 代码 | 价 | 涨停日 | 起爆 | Q2 |")
        a("|---|---|---|---|---|---|")
        for c in watch:
            ztshort = (c["zt"][:16] + "…") if len(c["zt"]) > 16 else c["zt"]
            a(f"| {c['name']} | {c['code']} | {c['price']} | {ztshort} | {'是' if c['is_qibao'] else ''} | {c['q2']} |")

    a(f"\n## ⛔ 高价过滤: {avoid_n} 只 (>35元, 不符合准入[1], 略)\n")

    a("\n## 📋 准入清单(每笔买入前逐项打勾, 缺一不买)\n")
    a("```")
    a("□[1] 买入价 < 25 元")
    a("□[2] 近5日涨停 或 量比≥1.5 (强势基因 — qsht涨停/起爆已满足)")
    a("□[3] 单笔仓位 < 5 万 (建议 1-3 万)")
    a("□[4] 14:45 后尾盘下单")
    a("□[5] 亏损持仓绝不加仓")
    a("□[6] 今日未连亏 2 笔")
    a("□[7] 持仓3-5天, -5%止损 / +8%止盈")
    a(f"□[8] 市况非🔴退守  (当前: {LIGHT[reg['color']]} {reg['name']}" + ("  ✗ 不满足!" if reg["color"] == "red" else "  ✓") + ")")
    a("```")

    a("\n## 📈 市况细节")
    a("| 指数 | 得分 | 收盘 | MA20 | 站上/跌破 | 20日位置 |")
    a("|---|---|---|---|---|---|")
    for label, sc, info in reg["idx"]:
        if info:
            a(f"| {label} | {sc:+d} | {info['close']:.1f} | {info['ma20']:.1f} | {info['above_ma']} | {info['state']} |")
    if reg["breadth"]:
        b = reg["breadth"]
        a(f"\n宽度[{b.get('source', '?')}]: 涨{b['ups']}/跌{b['downs']} 涨停{b['zt']} 中位{b['median']:+.2f}%")

    a("\n---")
    a(f"*qsht 选股于 {qsht_date} | 市况取实时 | 本清单为筛选辅助, 最终决策结合仓位与心态*")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"picks_{today}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"\n报告 -> {out_path}")
    print("=" * 50)
    print(f"  市况: {reg['name']} ({reg['total']:+d})")
    print(f"  可买入(<25): {len(buyable)} | 观察(25-35): {len(watch)} | 回避(>35): {avoid_n}")
    print("=" * 50)


if __name__ == "__main__":
    main()
