import json
import os
import subprocess
import sys
from datetime import datetime

SKILLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHUANGXINGAO = os.path.join(SKILLS_DIR, "chuangxingao", "main.py")
SHIZHI = os.path.join(SKILLS_DIR, "shizhi", "main.py")
SZ_THRESHOLD = 200  # 第4步市值筛选阈值（亿），与 shizhi 输出文件名 sz_<date>_<threshold>.json 对应
ZHANGTING = os.path.join(SKILLS_DIR, "zhangting", "main.py")
SUOLIANGHUICAI = os.path.join(SKILLS_DIR, "suolianghuicai", "main.py")


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"\n{'=' * 50}", flush=True)
    print(f"[步骤] {name}", flush=True)
    print(f"[命令] {' '.join(cmd)}", flush=True)

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print(f"[错误] {name} 失败（退出码 {result.returncode}）", flush=True)
        return False

    return True


def check_file(path: str, label: str) -> dict | None:
    if not os.path.exists(path):
        print(f"[错误] {label} 输出文件不存在: {path}", flush=True)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _stocks_table(stocks: list[dict], columns: list[tuple[str, str]]) -> list[str]:
    """生成 markdown 表格行。columns: [(key, header), ...]"""
    lines = []
    header = "| " + " | ".join(h for _, h in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines.append(header)
    lines.append(sep)
    for s in stocks:
        vals = []
        for key, _ in columns:
            v = s.get(key, "")
            if isinstance(v, float):
                v = round(v, 2)
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def generate_markdown(
    date_str: str,
    stats: list[dict],
    step_stocks: dict[str, list[dict]],
    final_stocks: list[dict],
) -> str:
    lines = [f"# 选股报告 - {date_str}", ""]

    # 筛选流水线统计
    lines.append("## 筛选流水线")
    for i, s in enumerate(stats, 1):
        lines.append(f"{i}. {s['name']}：{s['count']} 只")
    lines.append("")

    # 第1步：创新高
    cxg_stocks = step_stocks.get("创新高", [])
    if cxg_stocks:
        lines.append(f"## 第1步：创新高（{len(cxg_stocks)}只）")
        lines.append("")
        lines.extend(_stocks_table(cxg_stocks, [
            ("name", "股票名称"),
            ("code", "股票代码"),
            ("close", "当前价格"),
            ("high_100d", "100日最高"),
        ]))
        lines.append("")

    # 第2步：近期涨停
    zt_stocks = step_stocks.get("近期涨停", [])
    if zt_stocks:
        lines.append(f"## 第2步：近期涨停（{len(zt_stocks)}只）")
        lines.append("")
        lines.extend(_stocks_table(zt_stocks, [
            ("name", "股票名称"),
            ("code", "股票代码"),
            ("close", "当前价格"),
            ("zt_dates", "涨停日期"),
            ("zt_pcts", "涨停涨幅%"),
        ]))
        lines.append("")

    # 第3步：缩量回踩
    slhc_stocks = step_stocks.get("缩量回踩", [])
    if slhc_stocks:
        lines.append(f"## 第3步：缩量回踩（{len(slhc_stocks)}只）")
        lines.append("")
        lines.extend(_stocks_table(slhc_stocks, [
            ("name", "股票名称"),
            ("code", "股票代码"),
            ("current_close", "当前价格"),
            ("last_zt_date", "最近涨停日"),
            ("last_zt_close", "涨停日收盘"),
            ("pullback_days", "回踩天数"),
            ("volume_shrink_ratio", "缩量比"),
        ]))
        lines.append("")

    # 第4步：市值<200亿
    sz_stocks = step_stocks.get("市值<200亿", [])
    if sz_stocks:
        lines.append(f"## 第4步：市值<200亿（{len(sz_stocks)}只）")
        lines.append("")
        lines.extend(_stocks_table(sz_stocks, [
            ("name", "股票名称"),
            ("code", "股票代码"),
            ("close", "当前价格"),
            ("market_cap_yi", "市值(亿)"),
        ]))
        lines.append("")

    # 最终结果
    lines.append("## 最终结果")
    if not final_stocks:
        lines.append("今日无符合条件的股票。")
    else:
        lines.extend(_stocks_table(final_stocks, [
            ("name", "股票名称"),
            ("code", "股票代码"),
            ("close", "当前价格"),
            ("market_cap_yi", "市值(亿)"),
        ]))
    lines.append("")

    return "\n".join(lines)


def _normalize_close(data: dict, src_path: str):
    """将 current_close 字段归一化为 close，确保下游市值筛选器兼容。"""
    changed = False
    for s in data.get("stocks", []):
        if "close" not in s and "current_close" in s:
            s["close"] = s["current_close"]
            changed = True
    if changed:
        with open(src_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"qsht-agent 选股流水线 - {date_str}", flush=True)

    # 预测各步骤输出路径
    # Step 1: 创新高 → chuangxingao/data/{date}.json
    cxg_out = os.path.join(SKILLS_DIR, "chuangxingao", "data", f"{date_str}.json")
    # Step 2: 涨停 (input=cxg_out) → 保存到输入同目录 → chuangxingao/data/zt_{date}.json
    zt_out = os.path.join(SKILLS_DIR, "chuangxingao", "data", f"zt_{date_str}.json")
    # Step 3: 缩量回踩 (input=zt_out) → 保存到输入同目录 → chuangxingao/data/slhc_{date}.json
    slhc_out = os.path.join(SKILLS_DIR, "chuangxingao", "data", f"slhc_{date_str}.json")
    # Step 4: 市值 (input=slhc_out) → 保存到 shizhi/data/sz_{date}.json
    sz_out = os.path.join(SKILLS_DIR, "shizhi", "data", f"sz_{date_str}_{SZ_THRESHOLD}.json")

    stats = []
    step_stocks = {}
    final_stocks = []

    # Step 1: 创新高
    if not run_step("创新高筛选", [sys.executable, CHUANGXINGAO]):
        sys.exit(1)
    cxg_data = check_file(cxg_out, "创新高")
    if not cxg_data:
        sys.exit(1)
    stats.append({"name": "创新高", "count": cxg_data.get("count", 0)})
    step_stocks["创新高"] = cxg_data.get("stocks", [])
    if cxg_data.get("count", 0) == 0:
        print("[提示] 创新高筛选无结果，流水线结束。", flush=True)
        _output_report(date_str, stats, step_stocks, [])
        return

    # Step 2: 涨停筛选
    if not run_step("涨停筛选", [sys.executable, ZHANGTING, cxg_out]):
        sys.exit(1)
    zt_data = check_file(zt_out, "涨停筛选")
    if not zt_data:
        sys.exit(1)
    stats.append({"name": "近期涨停", "count": zt_data.get("count", 0)})
    step_stocks["近期涨停"] = zt_data.get("stocks", [])
    if zt_data.get("count", 0) == 0:
        print("[提示] 涨停筛选无结果，流水线结束。", flush=True)
        _output_report(date_str, stats, step_stocks, [])
        return

    # Step 3: 缩量回踩（策略1）
    if not run_step(
        "缩量回踩筛选",
        [sys.executable, SUOLIANGHUICAI, zt_out, "--strategy", "1"],
    ):
        sys.exit(1)
    slhc_data = check_file(slhc_out, "缩量回踩")
    if not slhc_data:
        sys.exit(1)
    stats.append({"name": "缩量回踩", "count": slhc_data.get("count", 0)})
    step_stocks["缩量回踩"] = slhc_data.get("stocks", [])
    if slhc_data.get("count", 0) == 0:
        print("[提示] 缩量回踩筛选无结果，流水线结束。", flush=True)
        _output_report(date_str, stats, step_stocks, [])
        return

    # 归一化 current_close → close，确保市值筛选器兼容
    _normalize_close(slhc_data, slhc_out)

    # Step 4: 市值筛选
    if not run_step("市值筛选", [sys.executable, SHIZHI, slhc_out, "--threshold", str(SZ_THRESHOLD)]):
        sys.exit(1)
    sz_data = check_file(sz_out, "市值筛选")
    if not sz_data:
        sys.exit(1)
    stats.append({"name": "市值<200亿", "count": sz_data.get("count", 0)})
    step_stocks["市值<200亿"] = sz_data.get("stocks", [])
    final_stocks = sz_data.get("stocks", [])

    _output_report(date_str, stats, step_stocks, final_stocks)


def _output_report(
    date_str: str,
    stats: list[dict],
    step_stocks: dict[str, list[dict]],
    stocks: list[dict],
):
    md = generate_markdown(date_str, stats, step_stocks, stocks)
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    md_path = os.path.join(output_dir, f"{date_str}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\n{'=' * 50}", flush=True)
    print(f"选股报告已生成: {md_path}", flush=True)
    for s in stats:
        print(f"  {s['name']}：{s['count']} 只", flush=True)


if __name__ == "__main__":
    main()
