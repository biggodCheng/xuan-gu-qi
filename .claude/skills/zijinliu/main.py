"""行业资金流排行榜 — 编排入口。

流程: CHECKPOINT(防覆盖) → fetch_top_flows(两端) → 各端已 parse+dedup →
     存 zijin_<date>.json → 终端打印 markdown 摘要。

可注入 fetcher(测试用); 默认用 screener.fetcher。
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from screener import fetcher as _default_fetcher
from screener import storage


def _yi(val) -> str:
    """超大单等原始元值 → 亿元字符串(无值返回 '-')。"""
    if val is None:
        return "-"
    return f"{round(val / 1e8, 2)}"


def _dash(val):
    """None → '-', 其他(含 0)原样返回。"""
    return "-" if val is None else val


def _print_summary(data: dict, top: int, outflow_top: int) -> None:
    date_str = data["date"]
    print(f"\n# 行业资金流 · {date_str}（东方财富·今日）")
    print(f"流入 {data['inflow_count']} 个 / 流出 {data['outflow_count']} 个 | "
          "主力净流入额降序（占比 = 净流入/成交额，排除体量偏差）\n")

    print(f"## 主力净流入 Top {top}")
    print("| # | 行业 | 涨跌% | 主力净流入(亿) | 占比% | 超大单(亿) |")
    print("|---|---|---|---|---|---|")
    for i, it in enumerate(data["inflow"][:top], 1):
        print(f"| {i} | {it.get('name', '')} | {_dash(it.get('change_pct'))} | "
              f"{_dash(it.get('main_net_yi'))} | {_dash(it.get('main_pct'))} | "
              f"{_yi(it.get('super_large_net'))} |")

    print(f"\n## 主力净流出 Top {outflow_top}")
    print("| # | 行业 | 涨跌% | 主力净流出(亿) | 占比% | 超大单(亿) |")
    print("|---|---|---|---|---|---|")
    for i, it in enumerate(data["outflow"][:outflow_top], 1):
        print(f"| {i} | {it.get('name', '')} | {_dash(it.get('change_pct'))} | "
              f"{_dash(it.get('main_net_yi'))} | {_dash(it.get('main_pct'))} | "
              f"{_yi(it.get('super_large_net'))} |")


def run(today_str: str | None = None, output_dir: str | None = None,
        top: int = 20, outflow_top: int = 10, per_end: int = 100,
        force: bool = False, fetcher=None) -> bool:
    today_str = today_str or datetime.date.today().strftime("%Y-%m-%d")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = output_dir or os.path.join(base_dir, "data")
    fetcher = fetcher or _default_fetcher

    # 1. CHECKPOINT: 今日快照已存在且未 --force → STOP
    path = os.path.join(output_dir, f"zijin_{today_str}.json")
    if os.path.exists(path) and not force:
        print(f"⚠️ 今日资金流快照已存在：{path}，加 --force 覆盖。", flush=True)
        return False

    # 2. 两端取数(已 parse + dedup)
    print(f"[{today_str}] 抓取东财行业板块资金流（两端各 Top {per_end}）...", flush=True)
    flows = fetcher.fetch_top_flows(per_end=per_end)
    print(f"流入端 {len(flows['inflow'])} 条 / 流出端 {len(flows['outflow'])} 条（去重后）",
          flush=True)

    if not flows["inflow"] and not flows["outflow"]:
        print("⚠️ 抓取失败：两端均无数据（接口异常或被封）。未保存快照，可重试。", flush=True)
        return False

    # 3. 保存
    saved = storage.save_results(today_str, flows["inflow"], flows["outflow"], output_dir)
    print(f"已保存：{saved}", flush=True)

    # 4. 摘要
    _print_summary(storage.load_results(today_str, output_dir), top, outflow_top)
    return True


def main():
    p = argparse.ArgumentParser(description="行业资金流排行榜(复盘观察)")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--outflow-top", type=int, default=10)
    p.add_argument("--per-end", type=int, default=100)
    p.add_argument("--date", default=None)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    ok = run(today_str=args.date, top=args.top, outflow_top=args.outflow_top,
             per_end=args.per_end, force=args.force)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
