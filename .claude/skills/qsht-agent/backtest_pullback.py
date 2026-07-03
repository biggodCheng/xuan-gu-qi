"""缩量回踩策略有效性复盘脚本。

扫描 chuangxingao/data/slhc_*.json 中所有历史回踩识别事件，
拉取每只标的从"识别日"到最新数据日的真实日K，
统计持有N日收益、最大有利/不利偏移、识别后是否涨停及涨停次日表现，
用于验证"回踩后涨停=兑现窗口而非启动点"的假设。

复用 suolianghuicai.screener.fetcher.get_stock_kline。
"""
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

# 复用 suolianghuicai 的 K 线抓取器
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "suolianghuicai")))
from screener.fetcher import get_stock_kline  # noqa: E402

DATA_DIR = os.path.normpath(os.path.join(_HERE, "..", "chuangxingao", "data"))
OUTPUT_DIR = os.path.join(_HERE, "output")


def zt_threshold(code: str) -> float:
    """按板块返回涨停涨幅阈值(收盘)。"""
    if code.startswith(("30", "68")):
        return 19.5
    if code.startswith(("4", "8", "92")):
        return 29.5
    return 9.5


def collect_events() -> list[dict]:
    """扫描所有 slhc_*.json，汇总回踩识别事件。

    去重：同一只股票(base_close + last_zt_date 相同)视为同一回踩形态，
    只保留最早的识别日(应对 6/28=6/26 副本等非交易日重复文件)。
    """
    seen: set[tuple] = set()
    events = []
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "slhc_*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        identify_date = data["date"]
        for s in data["stocks"]:
            key = (s["code"], s["last_zt_date"], round(s["current_close"], 2))
            if key in seen:
                continue  # 同一回踩形态已记录，跳过副本
            seen.add(key)
            events.append(
                {
                    "identify_date": identify_date,
                    "code": s["code"],
                    "name": s["name"],
                    "last_zt_date": s["last_zt_date"],
                    "last_zt_close": s["last_zt_close"],
                    "base_close": s["current_close"],
                    "shrink_ratio": s["volume_shrink_ratio"],
                    "pullback_days": s["pullback_days"],
                    "source": os.path.basename(path),
                }
            )
    return events


def fetch_klines(codes: list[str], days: int = 40) -> dict[str, list[dict]]:
    """并发拉取多只股票日K，缓存避免重复。"""
    kline_map: dict[str, list[dict]] = {}

    def _task(c):
        return c, get_stock_kline(c, days=days)

    with ThreadPoolExecutor(max_workers=10) as ex:
        for code, kl in ex.map(_task, codes):
            kline_map[code] = kl or []
    return kline_map


def analyze_event(ev: dict, kline: list[dict]) -> dict:
    """对单个事件计算识别后的走势指标。"""
    res = {**ev, "note": ""}
    idx = {k["date"]: i for i, k in enumerate(kline)}
    idate = ev["identify_date"]

    if idate not in idx:
        # 用 base_close 反查最接近的一日
        cand = [i for i, k in enumerate(kline) if abs(k["close"] - ev["base_close"]) < 0.01]
        if not cand:
            res["note"] = "识别日不在K线范围"
            res["future"] = []
            return res
        start_i = cand[0]
        res["note"] = "识别日按收盘价匹配"
    else:
        start_i = idx[idate]

    future = kline[start_i:]  # 含识别日
    after = future[1:]  # 识别日之后
    res["future"] = future
    res["after"] = after
    res["last_date"] = future[-1]["date"] if future else idate
    return res


def metrics(evx: dict) -> dict:
    """计算收益/涨停等指标。"""
    base = evx["base_close"]
    after = evx.get("after", [])
    code = evx["code"]
    thr = zt_threshold(code)

    closes_after = [k["close"] for k in after]
    seq_closes = [evx["future"][0]["close"]] + closes_after  # 识别日 + 后续

    def ret_n(n):
        if n - 1 < len(closes_after):
            return (closes_after[n - 1] - base) / base * 100
        return None

    # 最大有利/不利偏移(基于识别日后收盘)
    mfe = (max(closes_after) - base) / base * 100 if closes_after else None
    mae = (min(closes_after) - base) / base * 100 if closes_after else None

    # 涨停探测:识别日后每日涨幅(收盘vs前日收盘)
    zt_days = []
    for i in range(1, len(seq_closes)):
        prev, cur = seq_closes[i - 1], seq_closes[i]
        pct = (cur - prev) / prev * 100
        if pct >= thr - 0.3:  # 容差
            zt_days.append({"date": after[i - 1]["date"], "close": cur, "pct": pct, "i": i})

    # 涨停次日表现(第一个涨停的次日)
    zt_next = None
    if zt_days:
        z = zt_days[0]
        ni = z["i"] + 1  # seq_closes 索引
        if ni < len(seq_closes):
            zt_next = {
                "date": after[ni - 1]["date"] if ni - 1 < len(after) else None,
                "close": seq_closes[ni],
                "chg": (seq_closes[ni] - z["close"]) / z["close"] * 100,
            }

    end_close = closes_after[-1] if closes_after else base
    return {
        "base": base,
        "end_close": end_close,
        "end_ret": (end_close - base) / base * 100,
        "ret_1": ret_n(1),
        "ret_2": ret_n(2),
        "ret_3": ret_n(3),
        "ret_5": ret_n(5),
        "mfe": mfe,
        "mae": mae,
        "zt_days": zt_days,
        "zt_next": zt_next,
        "hold_days": len(closes_after),
    }


def fmt(v, suffix="%", na="—"):
    if v is None:
        return na
    return f"{v:+.2f}{suffix}"


def compute_summary(events_x: list[tuple[dict, dict]]) -> dict:
    """计算复盘统计汇总(供报告渲染与 stats JSON 共用)。"""
    valid = [(e, m) for e, m in events_x if m["hold_days"] > 0]
    n = len(valid)
    if n == 0:
        return {"n": 0}
    avg_end = sum(m["end_ret"] for _, m in valid) / n
    avg_mfe = sum(m["mfe"] for _, m in valid) / n
    avg_mae = sum(m["mae"] for _, m in valid) / n
    win = sum(1 for _, m in valid if m["end_ret"] > 0)
    zt_cnt = sum(1 for _, m in valid if m["zt_days"])
    zt_with_next = [m for _, m in valid if m["zt_days"] and m["zt_next"]]
    zt_down = sum(1 for m in zt_with_next if m["zt_next"]["chg"] < 0)
    return {
        "n": n,
        "avg_end_ret": round(avg_end, 2),
        "avg_mfe": round(avg_mfe, 2),
        "avg_mae": round(avg_mae, 2),
        "win": win,
        "zt_cnt": zt_cnt,
        "zt_with_next": len(zt_with_next),
        "zt_down": zt_down,
    }


def build_report(events_x: list[tuple[dict, dict]], latest_date: str) -> str:
    dates = sorted({e["identify_date"] for e, _ in events_x})
    codes = sorted({e["code"] for e, _ in events_x})
    span = f"{dates[0]}–{dates[-1]}" if dates[0] != dates[-1] else dates[0]
    lines = []
    lines.append(f"# 缩量回踩策略有效性复盘（截至 {latest_date}）\n")
    lines.append(f"> 基于 {span} qsht-agent 输出的全部缩量回踩识别事件（去重后），")
    lines.append("> 回拉每只标的识别日后的真实日K，统计持有收益与涨停兑现情况。")
    lines.append(
        f"> **小样本({len(events_x)}事件/{len(codes)}股)，结论仅供参考，非统计显著。**\n"
    )

    # 事件级明细表
    lines.append("## 一、识别事件明细（基准=识别日收盘）\n")
    lines.append("| 识别日 | 代码 | 名称 | 缩量比 | 基准收盘 | 持有日数 | 末值涨跌 | +1日 | +2日 | +3日 | 最大涨幅 | 最大回撤 | 识别后涨停 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for ev, m in events_x:
        zt_str = "—"
        if m["zt_days"]:
            zt_str = f"{m['zt_days'][0]['date'].split('-')[1:]}"  # 简写
            zt_str = "/".join(m["zt_days"][0]["date"].split("-")[1:])
        lines.append(
            "| {idate} | {code} | {name} | {sr} | {base:.2f} | {hd} | {end} | {r1} | {r2} | {r3} | {mfe} | {mae} | {zt} |".format(
                idate=ev["identify_date"],
                code=ev["code"],
                name=ev["name"],
                sr=f"{ev['shrink_ratio']:.2f}",
                base=m["base"],
                hd=m["hold_days"],
                end=fmt(m["end_ret"]),
                r1=fmt(m["ret_1"]),
                r2=fmt(m["ret_2"]),
                r3=fmt(m["ret_3"]),
                mfe=fmt(m["mfe"]),
                mae=fmt(m["mae"]),
                zt=zt_str,
            )
        )

    # 涨停兑现分析
    lines.append("\n## 二、回踩后涨停 → 次日表现（兑现窗口验证）\n")
    lines.append("| 识别日 | 代码 | 名称 | 涨停日 | 涨停涨幅% | 涨停次日涨跌% | 解读 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    any_zt = False
    for ev, m in events_x:
        for z in m["zt_days"]:
            any_zt = True
            nxt = m["zt_next"]
            if z is m["zt_days"][0] and nxt:
                chg = nxt["chg"]
                read = "兑现(次日下跌)" if chg < 0 else ("延续上涨" if chg > 1 else "高位震荡")
                lines.append(
                    f"| {ev['identify_date']} | {ev['code']} | {ev['name']} | "
                    f"{z['date']} | {z['pct']:.2f} | {chg:+.2f} | {read} |"
                )
            elif not nxt:
                lines.append(
                    f"| {ev['identify_date']} | {ev['code']} | {ev['name']} | "
                    f"{z['date']} | {z['pct']:.2f} | — | 涨停为最新日,无次日数据 |"
                )
    if not any_zt:
        lines.append("| — | — | — | — | — | — | 全样本识别后无涨停 |")

    # 统计汇总
    s = compute_summary(events_x)
    n = s["n"]
    lines.append(f"\n## 三、统计汇总（{n} 个有后续数据的事件）\n")
    if n:
        lines.append(f"- 平均末值收益(识别日→最新): **{s['avg_end_ret']:+.2f}%**")
        lines.append(f"- 平均最大涨幅 MFE: **{s['avg_mfe']:+.2f}%**  /  平均最大回撤 MAE: **{s['avg_mae']:+.2f}%**")
        lines.append(f"- 末值正收益事件: {s['win']}/{n}")
        lines.append(f"- 识别后出现涨停的事件: {s['zt_cnt']}/{n}")
        if s["zt_with_next"]:
            lines.append(
                f"- 涨停次日下跌占比: {s['zt_down']}/{s['zt_with_next']} "
                f"({s['zt_down']/s['zt_with_next']*100:.0f}%)"
            )

    lines.append("\n## 四、结论\n")
    lines.append("> 见正文分析。该复盘为小样本探索性分析，不可作为策略定型依据。")
    lines.append("\n---\n*本报告由 backtest_pullback.py 自动生成。*")
    return "\n".join(lines)


def main():
    events = collect_events()
    print(f"共 {len(events)} 个回踩识别事件，涉及 {len({e['code'] for e in events})} 只股票")

    codes = sorted({e["code"] for e in events})
    kline_map = fetch_klines(codes)

    events_x = []
    for ev in events:
        kl = kline_map.get(ev["code"], [])
        if not kl:
            print(f"  [跳过] {ev['code']} {ev.get('name') or ev['code']} K线为空")
            continue
        evx = analyze_event(ev, kl)
        m = metrics(evx)
        events_x.append((ev, m))
        zt = f"涨停{m['zt_days'][0]['date']}" if m["zt_days"] else "无涨停"
        nxt = f"次日{m['zt_next']['chg']:+.1f}%" if m["zt_next"] else ""
        print(
            f"  {ev['identify_date']} {ev['code']} {(ev.get('name') or ev['code']):<6} "
            f"base={m['base']:.2f} 末值{fmt(m['end_ret'])} "
            f"MFE{fmt(m['mfe'])}/MAE{fmt(m['mae'])} | {zt} {nxt}"
        )

    latest_date = max(e["identify_date"] for e in events)
    report = build_report(events_x, latest_date)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"pullback_review_{latest_date}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已生成: {out_path}")

    # 写统计快照(固定路径)，供 qsht-agent/main.py 嵌入主报告
    dates = sorted({e["identify_date"] for e in events})
    codes = sorted({e["code"] for e in events})
    stats = {
        "as_of": latest_date,
        "span": f"{dates[0]}–{dates[-1]}" if dates[0] != dates[-1] else dates[0],
        "events_total": len(events),
        "stocks_total": len(codes),
        **compute_summary(events_x),
        "report_file": f"pullback_review_{latest_date}.md",
    }
    stats_path = os.path.join(OUTPUT_DIR, "pullback_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"统计快照: {stats_path}")


if __name__ == "__main__":
    main()
