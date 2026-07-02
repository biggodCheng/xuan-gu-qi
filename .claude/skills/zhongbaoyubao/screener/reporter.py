"""markdown 报告生成(纯格式化,无网络/无 IO)。"""


def _f(v, suffix="%"):
    """数字格式化,None→N/A。"""
    if v is None:
        return "N/A"
    return f"{v:+.2f}{suffix}" if suffix else f"{v:.2f}"


def _row_active(s: dict) -> str:
    return ("| {code} | {name} | {yl} | {nd} | {bp} | {lc} | {ct} | {cd} | {hd} | {rd} |").format(
        code=s.get("code"), name=s.get("name"),
        yl=_f(s.get("yoy_lower"), ""), nd=s.get("notice_date", ""),
        bp=_f(s.get("base_price"), ""), lc=_f(s.get("last_close"), ""),
        ct=_f(s.get("chg_total")), cd=_f(s.get("chg_today")),
        hd=s.get("held_days", 0), rd=s.get("remain_days", 0),
    )


def render_report(pool: dict, today_str: str, new_codes: set, expired_codes: list) -> str:
    """生成每日 markdown 报告。

    new_codes: 今日入池的 code 集合;expired_codes: 今日迁出的 code 列表。
    """
    active = sorted(pool.get("active", []),
                    key=lambda s: (s.get("chg_total") if s.get("chg_total") is not None else -1e9),
                    reverse=True)
    new = [s for s in pool.get("active", []) + pool.get("expired", [])
           if s.get("code") in new_codes]
    expired = [s for s in pool.get("expired", []) if s.get("code") in set(expired_codes)]

    chg = [s.get("chg_total") for s in active if s.get("chg_total") is not None]
    pos = sum(1 for c in chg if c > 0)
    neg = sum(1 for c in chg if c < 0)
    avg = (sum(chg) / len(chg)) if chg else 0.0

    lines = [f"# 中报预报跟踪 · {today_str}", ""]
    th = pool.get("threshold", {})
    lines += [
        "## 概览",
        f"- 报告期:{pool.get('report_period','')}（预告对应 {pool.get('report_date','')}）",
        f"- 阈值:{th.get('predict_type','预增')} 且同比下限≥{th.get('yoy_lower_min',50)}%｜"
        f"跟踪{th.get('hold_days',30)}交易日｜基准={th.get('base','次日开盘')}｜口径=前复权累计涨跌",
        f"- 跟踪池:活跃 {len(active)} 只 / 已到期 {len(pool.get('expired',[]))} 只 / "
        f"待重试 {len(pool.get('skipped',[]))} 只",
        f"- 今日新增:{len(new)} 只 ｜ 今日到期:{len(expired)} 只",
        "",
    ]

    lines += ["## 今日新增（{} 只）".format(len(new)),
              "| 代码 | 名称 | 预增下限 | 预增上限 | 公告日 | 基准日 | 基准价 |",
              "|---|---|---|---|---|---|---|"]
    for s in new:
        lines.append("| {code} | {name} | {yl} | {yu} | {nd} | {bd} | {bp} |".format(
            code=s.get("code"), name=s.get("name"),
            yl=_f(s.get("yoy_lower"), ""), yu=_f(s.get("yoy_upper"), ""),
            nd=s.get("notice_date", ""), bd=s.get("base_date", ""),
            bp=_f(s.get("base_price"), "")))
    lines.append("")

    lines += ["## 活跃跟踪（按累计涨跌降序）",
              "| 代码 | 名称 | 预增下限 | 公告日 | 基准价 | 今收 | 累计涨跌% | 当日涨跌% | 持有天数 | 剩余天数 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for s in active:
        lines.append(_row_active(s))
    lines.append("")

    lines += ["## 今日到期（移出活跃）",
              "| 代码 | 名称 | 基准价 | 期末收 | 累计涨跌% | 持有天数 |",
              "|---|---|---|---|---|---|"]
    for s in expired:
        lines.append("| {c} | {n} | {bp} | {lc} | {ct} | {hd} |".format(
            c=s.get("code"), n=s.get("name"), bp=_f(s.get("base_price"), ""),
            lc=_f(s.get("last_close"), ""), ct=_f(s.get("chg_total")), hd=s.get("held_days", 0)))
    lines.append("")

    lines += ["## 涨跌分布（活跃股）",
              f"- 累计为正 {pos} 只 / 为负 {neg} 只 / 平均累计涨跌 {avg:+.2f}%",
              ""]
    return "\n".join(lines)
