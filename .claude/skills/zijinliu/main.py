"""行业资金流排行榜 — 编排入口。

流程: CHECKPOINT(防覆盖) → fetch_top_flows(两端) → 各端已 parse+dedup →
     存 zijin_<date>.json → 终端打印 markdown 摘要。

可注入 fetcher(测试用); 默认用 screener.fetcher。
"""
import argparse
import datetime
import os
import sys

# Windows 中文控制台默认 GBK(cp936) 编不出 emoji(⚠️)：盘前/非交易日警告 print 会
# UnicodeEncodeError，且崩在 save_results 之前 → 数据白抓、JSON 不落盘。
# 强制 stdout/stderr 用 utf-8（stdlib，不引入依赖）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass  # stdout 非可重定向 TextIOWrapper（如重定向到文件）时忽略

sys.path.insert(0, os.path.dirname(__file__))

# 复用项目根 scripts/trading_day: 用新浪权威交易日, 免疫本机系统时钟漂移
# (本机 w32time 服务停摆, 系统时钟会跨日跳变, 详见 SKILL.md 边界条件)
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))              # .../zijinliu
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SKILL_DIR)))  # →skills→.claude→项目根
_SCRIPTS_DIR = os.path.join(_ROOT, "scripts")
if os.path.isdir(_SCRIPTS_DIR) and _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
import trading_day

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


def _market_session_warning(now=None) -> str:
    """盘前(<9:30)/周末 → 数据日警告; 盘中/盘后 → 空串。

    资金流接口在非交易时段返回上一交易日收盘数据(非今日)。交易日历简化为
    工作日(节假日未计)。盘中数据为今日实时、盘后为今日收盘, 均不警告。
    """
    now = now or datetime.datetime.now()
    if now.weekday() >= 5:
        return "⚠️ 当前为非交易日(周末)，数据为上一交易日收盘值，非今日。建议收盘后重跑。"
    if now.hour * 60 + now.minute < 9 * 60 + 30:
        return "⚠️ 当前为盘前(未开盘)，数据为上一交易日收盘值，非今日实时。建议收盘后重跑。"
    return ""


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
    today_str = today_str or trading_day.latest_trading_day()
    # 本机时钟漂移自检: 本地时钟日 vs 权威交易日, 跨日则警告(仍采用权威交易日)
    _drift = trading_day.drift_days(trading_day.local_today_str(), today_str)
    if _drift:
        print(f"⚠️ 本地时钟与权威交易日相差 {_drift} 天（本地 {trading_day.local_today_str()} → "
              f"权威 {today_str}），已采用权威交易日；建议修复系统时间(见 SKILL.md 边界条件)。", flush=True)
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

    # 2.5 盘前/非交易日 → 数据可能是上一交易日, 警告并持久化(防下游误读为今日)
    warning = _market_session_warning()
    if warning:
        print(warning, flush=True)

    # 3. 保存(盘前/非交易日时 note 持久化进 JSON, 下游读 is_stale 即知数据为上一交易日)
    saved = storage.save_results(today_str, flows["inflow"], flows["outflow"],
                                 output_dir, note=warning or None)
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
