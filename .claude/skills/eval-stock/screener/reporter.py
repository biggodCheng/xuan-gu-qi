# -*- coding: utf-8 -*-
"""终端 markdown 格式化。"""

_FUNNEL_STEPS = [
    ("① 趋势新高", "new_high", "趋势新高"),
    ("② 近15天涨停", "zt", "涨停"),
    ("③ 缩量回踩", "pullback", "缩量回踩"),
    ("④ 市值<200亿", "marketcap", "市值"),
]


def _lamp(dim) -> str:
    if "pass" in dim:
        return "✅" if dim["pass"] else "❌"
    if dim.get("verdict") == "偏正":
        return "✅"
    if dim.get("verdict") == "偏负":
        return "❌"
    return "➖"   # 中性 / 数据不足


def _funnel_verdict(stock: dict) -> tuple:
    """按 ①→②→③→④ 串联，任一不过即淘汰。返回 (达标/不达标, 淘汰步说明)。"""
    for label, key, name in _FUNNEL_STEPS:
        dim = stock.get(key, {})
        if not dim.get("pass", False):
            return "不达标", f"{label} 淘汰（{name}未过）"
    return "达标", ""


def _oneliner(stock: dict) -> str:
    verdict, where = _funnel_verdict(stock)
    parts = []
    if verdict == "不达标":
        parts.append(where)
    if not stock.get("new_high", {}).get("pass", False):
        parts.append("非新高/趋势走弱")
    if stock.get("marketcap", {}).get("total") and stock["marketcap"]["total"] >= 200:
        parts.append("大票")
    q2v = stock.get("q2", {}).get("verdict")
    if q2v == "偏负":
        parts.append("Q2偏负")
    tail = "；".join(parts) if parts else "各维度通过"
    prefix = "非体系标的，不建议追" if verdict == "不达标" else "符合体系，可重点跟踪"
    return f"{prefix}（{tail}）"


def format_report(stock: dict) -> str:
    if stock.get("error"):
        return f"{stock.get('name', stock.get('code', '?'))}: 取数失败 — {stock['error']}"

    lines = []
    header = (f"{stock['name']}({stock['code']}) · {stock.get('industry') or '—'}"
              f" · 数据截至 {stock.get('last_date', '?')}"
              f" · 最新 {stock.get('last_close', '?')}")
    if stock.get("intraday"):
        header += "（盘中未收盘）"
    lines.append(header)
    lines.append("─" * 45)

    for label, key, _ in _FUNNEL_STEPS:
        dim = stock.get(key, {})
        lines.append(f"{label}   {_lamp(dim)}  {dim.get('label', '')}")

    # Q2
    q2 = stock.get("q2", {})
    np = q2.get("netprofit_yoy")
    rev = q2.get("revenue_yoy")
    np_s = f"{np:+.0f}%" if np is not None else "N/A"
    rev_s = f"{rev:+.0f}%" if rev is not None else "N/A"
    lines.append(f"⑤ Q2展望      {_lamp(q2)}  {q2.get('verdict', '?')}"
                 f"（净利 {np_s} / 营收 {rev_s}）")

    # 赛道
    tr = stock.get("track", {})
    if tr.get("tracks"):
        main = f"主 {tr['main']}({tr.get('main_conf', '')})" if tr.get("main") else ""
        lines.append(f"⑥ 赛道        ✅  {'、'.join(tr['tracks'])} {main}")
    else:
        lines.append("⑥ 赛道        ❌  不属于四大赛道")

    lines.append("─" * 45)
    verdict, where = _funnel_verdict(stock)
    if verdict == "达标":
        lines.append("qsht 漏斗判定：①②③④ 全通过 → 达标")
    else:
        lines.append(f"qsht 漏斗判定：不达标 — {where}")
    lines.append(f"一句话：{_oneliner(stock)}")
    return "\n".join(lines)
