"""Q2展望 — 单只查询主入口。

用法:
    python main.py "比亚迪"
    python main.py "002594"
    python main.py "600519"

基于 2026Q1 已披露业绩,推断 Q2 业绩走向,输出定性展望 + 信号面板。
"""

import json
import os
import sys

# Windows 终端 UTF-8 输出,避免 GBK 编码错误
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import resolve_stock_code, get_financial  # noqa: E402
from screener.analyzer import analyze  # noqa: E402


def run(query: str) -> str:
    """执行 Q2 展望查询,返回 JSON 字符串。"""
    print(f"正在查询: {query} ...", flush=True)

    code, name = resolve_stock_code(query)
    if not code:
        result = {
            "error": f"未找到股票: {query}",
            "suggestion": "请检查股票代码或名称是否正确",
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    print(f"找到股票: {name}（{code}）", flush=True)

    print("正在获取财报数据(近9期)...", flush=True)
    fin = get_financial(code)
    if not fin["reports"]:
        result = {
            "code": code, "name": name,
            "error": "未获取到财报数据",
            "suggestion": "该股可能尚未披露 2026Q1,或数据接口异常,请稍后重试",
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    if not fin["name"]:
        fin["name"] = name  # 兜底用 resolve 的名称

    print("正在分析 Q2 展望...", flush=True)
    result = analyze(fin)

    _print_summary(result)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _print_summary(r: dict) -> None:
    """终端打印人类可读摘要。"""
    outlook = r.get("q2_outlook", {})
    q1 = r.get("q1", {})
    sig = outlook.get("signals", {})
    mom = sig.get("momentum", {})
    div = sig.get("divergence", {})

    print("\n" + "=" * 56, flush=True)
    print(f"【{r.get('name')}（{r.get('code')}】Q2展望: {outlook.get('verdict')}"
          f" (置信度: {outlook.get('confidence')})", flush=True)

    print(f"\nQ1 基础({r.get('report_period')}):", flush=True)
    print(f"  归母净利同比: {_pct(q1.get('netprofit_yoy'))}   "
          f"营收同比: {_pct(q1.get('revenue_yoy'))}", flush=True)
    print(f"  归母净利: {_yi(q1.get('parent_netprofit_yi'))}"
          f" (去年同期 {_yi(q1.get('parent_netprofit_prev_yi'))})", flush=True)
    print(f"  毛利率: {_plain(q1.get('gross_margin'))}"
          f" (去年同期 {_plain(q1.get('gross_margin_prev'))})", flush=True)

    print(f"\n信号A 同比势头: {mom.get('direction')}", flush=True)
    print(f"  Q1单季同比 {_pct(mom.get('q1_single_yoy'))} "
          f"vs Q4单季同比 {_pct(mom.get('q4_single_yoy'))}", flush=True)
    print(f"  → {mom.get('note')}", flush=True)

    print(f"\n信号B 营收-净利背离: {div.get('direction')}", flush=True)
    print(f"  营收 {_pct(div.get('revenue_yoy'))} / 净利 {_pct(div.get('netprofit_yoy'))}"
          f" / 毛利率变化 {_pctchg(div.get('gross_margin_chg'))}", flush=True)
    print(f"  → {div.get('note')}", flush=True)

    print(f"\n总结: {outlook.get('summary')}", flush=True)
    print("=" * 56, flush=True)


def _pct(v) -> str:
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "N/A"


def _plain(v) -> str:
    """水平值(毛利率等)不带符号。"""
    return f"{v:.2f}%" if isinstance(v, (int, float)) else "N/A"


def _pctchg(v) -> str:
    return f"{v:+.2f}pct" if isinstance(v, (int, float)) else "N/A"


def _yi(v) -> str:
    return f"{v:.2f}亿" if isinstance(v, (int, float)) else "N/A"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python main.py <股票代码或名称>", flush=True)
        print("示例:", flush=True)
        print("  python main.py 比亚迪", flush=True)
        print("  python main.py 002594", flush=True)
        print("  python main.py 600519", flush=True)
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    output = run(query)
    print(f"\n{output}", flush=True)
