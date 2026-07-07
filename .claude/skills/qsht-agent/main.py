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
Q2ZHANWANG = os.path.join(SKILLS_DIR, "q2zhanwang", "batch_query.py")  # 第5步 Q2 业绩展望批量入口
QIBAO = os.path.join(SKILLS_DIR, "qibao", "main.py")  # 起爆点筛选（创新高派生）

# 回踩策略复盘(每日自动累积样本，独立于主漏斗，失败不阻断)
_HERE = os.path.dirname(os.path.abspath(__file__))
BACKTEST = os.path.join(_HERE, "backtest_pullback.py")
BACKTEST_STATS = os.path.join(_HERE, "output", "pullback_stats.json")

# 第0步大盘环境扫描(选股前打印温度，失败不阻断)
MARKET_ENV = os.path.join(_HERE, "market_env.py")
MARKET_ENV_JSON = os.path.join(_HERE, "output", "market_env.json")


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


def run_q2_step(zt_json_path: str) -> dict:
    """对近期涨停股批量推断 Q2 业绩展望（调用 q2zhanwang/batch_query.py）。

    成功返回 batch 结果 dict（含 stocks/total/count/failed，stocks 按 verdict 排序、
    偏正在前）；subprocess 失败或输出文件缺失时返回 {"stocks": [], "failed": True}，
    不抛异常、不阻断主报告。
    """
    if not run_step("Q2业绩展望", [sys.executable, Q2ZHANWANG, zt_json_path]):
        return {"stocks": [], "failed": True}

    # batch_query 内部用 date.today() 写 data/batch_<today>.json
    today = datetime.now().strftime("%Y-%m-%d")
    batch_out = os.path.join(SKILLS_DIR, "q2zhanwang", "data", f"batch_{today}.json")
    data = check_file(batch_out, "Q2展望")
    if not data:
        return {"stocks": [], "failed": True}
    return data


def run_backtest_step() -> dict | None:
    """运行缩量回踩策略复盘(每日自动累积样本)，返回统计摘要或 None。

    扫描全部历史 slhc 识别事件回拉真实日K，统计持有收益与涨停兑现情况。
    独立于主漏斗：失败/无数据均不阻断主报告，仅跳过该 section。
    """
    if not run_step("回踩策略复盘", [sys.executable, BACKTEST]):
        return None
    data = check_file(BACKTEST_STATS, "回踩复盘")
    if not data or data.get("n", 0) == 0:
        return None
    return data


def run_market_env_step() -> dict | None:
    """第0步：大盘环境扫描(上证/沪深300/创业板)，返回快照 dict 或 None。

    在选股前运行，控制台打印大盘温度；失败不阻断主流程。
    """
    if not run_step("大盘环境扫描", [sys.executable, MARKET_ENV]):
        return None
    data = check_file(MARKET_ENV_JSON, "大盘环境")
    if not data or not data.get("indexes"):
        return None
    return data


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
            v = s.get(key)
            if v is None:
                v = "-"  # 字段缺失或值为 None（如数据不足的同比）统一显示 "-"
            elif isinstance(v, float):
                v = round(v, 2)
            elif isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def _q2_section(q2_data: dict) -> list[str]:
    """生成第5步 Q2 业绩展望 section（表格 + 偏正/中性公司列表，置于文档最后）。"""
    lines = []
    stocks = q2_data.get("stocks", [])

    if not stocks:
        lines.append("## 第5步：Q2业绩展望·近期涨停")
        lines.append("")
        lines.append("Q2展望分析未取得有效数据（财报接口异常或全部数据不足）。")
        return lines

    # verdict 分布（偏正/中性/偏负/数据不足）
    dist = {}
    for s in stocks:
        v = s.get("verdict", "")
        dist[v] = dist.get(v, 0) + 1
    dist_str = "  ".join(f"{k} {dist[k]}" for k in ["偏正", "中性", "偏负", "数据不足"] if dist.get(k))

    lines.append(f"## 第5步：Q2业绩展望·近期涨停（{len(stocks)}只 · {dist_str}）")
    lines.append("")
    lines.append("> 基于 2026Q1 已披露业绩推断；verdict 为方向判断非精确预测；confidence=低者仅供参考。")
    lines.append("")
    lines.extend(_stocks_table(stocks, [
        ("name", "股票名称"),
        ("code", "股票代码"),
        ("industry", "行业"),
        ("verdict", "Q2展望"),
        ("confidence", "置信度"),
        ("netprofit_yoy", "净利同比%"),
        ("revenue_yoy", "营收同比%"),
        ("q2_note", "展望说明"),
    ]))
    lines.append("")

    # 偏正/中性公司列表（按置信度高/中/低分段，中文逗号分隔）
    picks = [s for s in stocks if s.get("verdict") in ("偏正", "中性")]
    pos = sum(1 for s in picks if s.get("verdict") == "偏正")
    neu = sum(1 for s in picks if s.get("verdict") == "中性")
    lines.append(f"### 偏正/中性公司（偏正 {pos} + 中性 {neu} = {len(picks)} 只 · 按置信度分段）")
    lines.append("")

    if not picks:
        lines.append("无")
        return lines

    # 按置信度分三档：高=两信号同向最可靠；中=信号矛盾或含持平；低=数据缺期/基数过小仅供参考
    by_conf = {"高": [], "中": [], "低": []}
    for s in picks:
        c = s.get("confidence", "")
        if c in by_conf:
            by_conf[c].append(s.get("name", ""))
    hints = {
        "高": "两信号同向，最可靠",
        "中": "信号矛盾或含持平",
        "低": "数据缺期或基数过小，仅供参考",
    }
    for level in ("高", "中", "低"):
        names = by_conf[level]
        lines.append(f"**置信度{level} · {len(names)} 只**（{hints[level]}）：")
        lines.append("，".join(names) if names else "无")
        lines.append("")
    return lines


def _backtest_section(s: dict) -> list[str]:
    """生成回踩策略复盘摘要 section(累积样本，指向完整复盘报告)。"""
    lines = []
    as_of = s.get("as_of", "?")
    span = s.get("span", "?")
    n = s.get("n", 0)
    stocks = s.get("stocks_total", "?")
    avg_end = s.get("avg_end_ret", 0)
    avg_mfe = s.get("avg_mfe", 0)
    avg_mae = s.get("avg_mae", 0)
    win = s.get("win", 0)
    zt_cnt = s.get("zt_cnt", 0)
    zt_down = s.get("zt_down", 0)
    zt_with_next = s.get("zt_with_next", 0)
    lines.append(f"## 第6步：回踩策略复盘（截至 {as_of} · 样本 {span} · {n}事件/{stocks}股）")
    lines.append("")
    lines.append("> 每日自动累积：扫描全部历史 slhc 识别事件，回拉识别日后真实日K统计有效性。小样本探索性结论，非统计显著。")
    lines.append("")
    lines.append(f"- 平均末值收益(识别日→最新): **{avg_end:+.2f}%** ｜ 平均 MFE {avg_mfe:+.2f}% / MAE {avg_mae:+.2f}%")
    zt_part = f" ｜ 识别后涨停 {zt_cnt}/{n}"
    if zt_with_next:
        zt_part += f" ｜ 涨停次日下跌 {zt_down}/{zt_with_next}"
    lines.append(f"- 末值正收益: {win}/{n}{zt_part}")
    lines.append("")
    report_file = s.get("report_file", "pullback_review.md")
    lines.append(f"完整复盘见 [{report_file}](output/{report_file})")
    return lines


def _market_env_section(env: dict) -> list[str]:
    """生成大盘环境 section(置于主报告开头作为背景)。"""
    lines = []
    as_of = env.get("as_of", "?")
    idxs = env.get("indexes", [])
    lines.append(f"## 大盘环境（{as_of}）")
    lines.append("")
    lines.append("| 指数 | 收盘 | 当日% | 120日回撤% | 区间位置% | vs MA20/60 | 5日% | 20日% |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for i in idxs:
        ma_tag = ("↓" if i.get("below_ma20") else "↑") + "/" + (
            "↓" if i.get("below_ma60") else "↑"
        )
        lines.append(
            f"| {i['name']} | {i['close']} | {i['chg_pct']:+.2f} | {i['dd120']:.1f} | "
            f"{i['pos120']:.0f} | {ma_tag} | {i['ret5']:+.1f} | {i['ret20']:+.1f} |"
        )
    lines.append("")
    lines.append(f"> **环境判断**：{env.get('summary', '—')}")
    return lines


def generate_markdown(
    date_str: str,
    stats: list[dict],
    step_stocks: dict[str, list[dict]],
    final_stocks: list[dict],
    q2_data: dict | None = None,
    backtest_summary: dict | None = None,
    market_env: dict | None = None,
) -> str:
    lines = [f"# 选股报告 - {date_str}", ""]

    # 第0步：大盘环境(置于报告最开头作为背景)
    if market_env is not None:
        lines.extend(_market_env_section(market_env))
        lines.append("")

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

    # 起爆点信号（创新高派生）
    qb_stocks = step_stocks.get("起爆点", [])
    if qb_stocks:
        lines.append(f"## 起爆点信号·创新高股（{len(qb_stocks)}只）")
        lines.append("")
        lines.append("> 起爆=突破布林上轨+倍量+MACD水上金叉；兼蓄势=起爆前横盘+放量阳线(无L2资金流)")
        lines.append("")
        lines.extend(_stocks_table(qb_stocks, [
            ("name", "股票名称"),
            ("code", "股票代码"),
            ("close", "现价"),
            ("pct_chg", "涨幅%"),
            ("vol_ratio", "量比"),
            ("signals", "信号"),
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

    # 第5步：Q2业绩展望（近期涨停）
    if q2_data is not None:
        lines.extend(_q2_section(q2_data))
        lines.append("")

    # 第6步：回踩策略复盘(累积样本，置于文档最末)
    if backtest_summary is not None:
        lines.extend(_backtest_section(backtest_summary))
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

    # 第0步：大盘环境扫描(选股前打印温度，失败不阻断)
    market_env = run_market_env_step()

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
        _finish(date_str, stats, step_stocks, [], q2_input=None, market_env=market_env)
        return

    # Step 1.5: 起爆点（创新高派生，失败不阻断主流程）
    qibao_out = os.path.join(SKILLS_DIR, "qibao", "data", f"qb_{date_str}.json")
    if run_step("起爆点筛选", [sys.executable, QIBAO, cxg_out]):
        qb_data = check_file(qibao_out, "起爆点")
        if qb_data:
            stats.append({"name": "起爆点", "count": qb_data.get("count", 0)})
            step_stocks["起爆点"] = qb_data.get("stocks", [])

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
        _finish(date_str, stats, step_stocks, [], q2_input=None, market_env=market_env)
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
        _finish(date_str, stats, step_stocks, [], q2_input=zt_out, market_env=market_env)
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

    _finish(date_str, stats, step_stocks, final_stocks, q2_input=zt_out, market_env=market_env)


def _finish(
    date_str: str,
    stats: list[dict],
    step_stocks: dict[str, list[dict]],
    final_stocks: list[dict],
    q2_input: str | None = None,
    market_env: dict | None = None,
):
    """统一收尾：近期涨停非空时跑 Q2 展望，跑回踩复盘，再生成报告。"""
    q2_data = run_q2_step(q2_input) if q2_input else None
    backtest_summary = run_backtest_step()
    _output_report(date_str, stats, step_stocks, final_stocks, q2_data, backtest_summary, market_env)


def _output_report(
    date_str: str,
    stats: list[dict],
    step_stocks: dict[str, list[dict]],
    stocks: list[dict],
    q2_data: dict | None = None,
    backtest_summary: dict | None = None,
    market_env: dict | None = None,
):
    md = generate_markdown(date_str, stats, step_stocks, stocks, q2_data, backtest_summary, market_env)
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
