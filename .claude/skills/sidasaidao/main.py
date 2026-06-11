"""四大赛道查询器 — 主入口。

用法:
    python main.py "比亚迪"
    python main.py "002594"
    python main.py "600519"

输出 JSON 格式的赛道匹配结果到 stdout。
"""

import json
import os
import sys

# Windows 终端使用 UTF-8 输出，避免 GBK 编码错误
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import resolve_stock_code, get_stock_detail
from screener.analyzer import match_tracks, format_result


def run(query: str) -> str:
    """执行四大赛道查询，返回格式化的 JSON 字符串。"""
    print(f"正在查询: {query} ...", flush=True)

    # 第一步：解析股票代码
    code, name = resolve_stock_code(query)

    if not code:
        result = {
            "error": f"未找到股票: {query}",
            "suggestion": "请检查股票代码或名称是否正确",
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    print(f"找到股票: {name}（{code}）", flush=True)

    # 第二步：获取行业和概念数据
    print("正在获取行业和概念板块数据...", flush=True)
    detail = get_stock_detail(code)

    industry = detail.get("industry", "")
    concepts = detail.get("concepts", [])
    actual_name = detail.get("name", name)

    print(f"行业: {industry or '未知'}", flush=True)
    print(f"概念板块: {len(concepts)} 个", flush=True)

    if concepts:
        # 只显示前 10 个概念
        preview = ", ".join(concepts[:10])
        if len(concepts) > 10:
            preview += f" ... 等 {len(concepts)} 个"
        print(f"  {preview}", flush=True)

    # 第三步：匹配四大赛道
    print("正在匹配四大赛道...", flush=True)
    matched = match_tracks(industry, concepts)

    # 第四步：格式化结果
    result = format_result(code, actual_name, industry, concepts, matched)

    # 输出到 stdout
    output = json.dumps(result, ensure_ascii=False, indent=2)

    # 打印摘要
    print("\n" + "=" * 50, flush=True)
    if matched:
        print(f"【{actual_name}（{code}】所属赛道:", flush=True)
        for t in matched:
            print(
                f"  ✓ {t['track']}（置信度: {t['confidence']}）"
                f" — 匹配: {', '.join(t['matched_keywords'][:5])}"
                f"{'...' if len(t['matched_keywords']) > 5 else ''}",
                flush=True,
            )
        if result.get("cross_track_note"):
            print(f"\n  跨赛道关联: {result['cross_track_note']}", flush=True)
    else:
        print(f"【{actual_name}（{code}】不属于四大赛道", flush=True)
        if industry:
            print(f"  行业: {industry}", flush=True)
        if concepts:
            print(f"  概念: {', '.join(concepts[:5])}...", flush=True)
    print("=" * 50, flush=True)

    return output


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
