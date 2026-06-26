"""分析层 — 单季化、信号计算、Q2 展望判定、格式化。

纯逻辑(无网络),可单测。核心思想:
- 接口给的是累计口径,自带同比随报告期变口径(一季报=单季、年报=全年),不可跨期比较。
- 故统一自算单季值与单季同比,口径一致。
- 用两个信号推断 Q2:A 同比势头(加速度) + B 营收-净利背离。
"""

# ---- 可调阈值 ----
THRESHOLD_MOMENTUM = 5.0      # 势头:|Q1单季同比 - Q4单季同比| > 5pct 才算加速/减速
DIVERGENCE_GAP = 10.0         # 背向:|净利同比 - 营收同比| > 10pct 才算明显背离
GROSS_MARGIN_CHG = 1.0        # 毛利率变化 > 1pct 视为有方向
BASE_EPS = 1e6                # 去年同期单季绝对值 < 100万元 → 基数过小,增速失真

YI = 1e8  # 亿元

# verdict 判定矩阵 (势头方向, 背离方向) → 展望
_VERDICT_MATRIX = {
    ("加速", "改善"): "偏正", ("加速", "同步"): "偏正", ("加速", "承压"): "中性",
    ("持平", "改善"): "偏正", ("持平", "同步"): "中性", ("持平", "承压"): "偏负",
    ("减速", "改善"): "中性", ("减速", "同步"): "偏负", ("减速", "承压"): "偏负",
}


# ============ 单季化 ============

def single_quarterize(reports: list[dict]) -> dict:
    """累计口径 → 单季值。

    Returns:
        {(year, quarter): {revenue, parent_netprofit, gross_margin, anomaly}}
        Q1单季=累计;Qq(q>1)单季=本期累计-同年 q-1 期累计。
        毛利率是比率,直接取本期值。缺前一季度则该期不产出。
    """
    cum: dict[tuple, dict] = {}
    for r in reports:
        key = (r["year"], r["quarter"])
        if key not in cum:  # 同期取首次(理论上不重复)
            cum[key] = r

    single: dict[tuple, dict] = {}
    for (y, q), r in cum.items():
        if q == 1:
            single[(y, 1)] = {
                "revenue": r["revenue"],
                "parent_netprofit": r["parent_netprofit"],
                "gross_margin": r["gross_margin"],
                "anomaly": False,
            }
        else:
            prev = cum.get((y, q - 1))
            if prev is None:
                continue  # 缺前一季度,无法单季化
            np_single = _sub(r["parent_netprofit"], prev["parent_netprofit"])
            anomaly = _is_anomaly(r["parent_netprofit"], np_single)
            single[(y, q)] = {
                "revenue": _sub(r["revenue"], prev["revenue"]),
                "parent_netprofit": np_single,
                "gross_margin": r["gross_margin"],  # 比率不单季化
                "anomaly": anomaly,
            }
    return single


def _sub(a, b):
    if a is None or b is None:
        return None
    return a - b


def _is_anomaly(cum_np, single_np) -> bool:
    """合理性校验:单季为负但累计为正、或单季>累计(疑似数据重述)。"""
    if single_np is None or cum_np is None:
        return False
    if single_np < 0 < cum_np:
        return True
    if cum_np > 0 and single_np > cum_np:
        return True
    return False


# ============ 同比 ============

def yoy(curr, prev) -> float | None:
    """同比增速%。任一为 None 或基数过小 → None。"""
    if curr is None or prev is None:
        return None
    if abs(prev) < BASE_EPS:
        return None
    return (curr - prev) / abs(prev) * 100


# ============ 信号方向 ============

def momentum_direction(q1_yoy, q4_yoy) -> str:
    """信号A:同比势头。Q1单季同比 vs 去年Q4单季同比。"""
    if q1_yoy is None or q4_yoy is None:
        return "数据不足"
    diff = q1_yoy - q4_yoy
    if diff > THRESHOLD_MOMENTUM:
        return "加速"
    if diff < -THRESHOLD_MOMENTUM:
        return "减速"
    return "持平"


def divergence_direction(rev_yoy, np_yoy, gm_chg) -> str:
    """信号B:营收-净利背离。"""
    if rev_yoy is None or np_yoy is None:
        return "数据不足"
    gap = np_yoy - rev_yoy  # 净利同比 - 营收同比
    margin_compress = gm_chg is not None and gm_chg < -GROSS_MARGIN_CHG
    margin_expand = gm_chg is not None and gm_chg > GROSS_MARGIN_CHG
    if gap < -DIVERGENCE_GAP or (margin_compress and np_yoy < rev_yoy):
        return "利润承压"
    if gap > DIVERGENCE_GAP or (margin_expand and np_yoy > rev_yoy):
        return "利润改善"
    return "同步"


# ============ 判定 ============

def _norm_div(d_dir: str) -> str:
    """归一化背离方向为矩阵键:利润承压→承压、利润改善→改善、同步→同步。"""
    if "承压" in d_dir:
        return "承压"
    if "改善" in d_dir:
        return "改善"
    if "同步" in d_dir:
        return "同步"
    return d_dir  # 数据不足等


def combine_verdict(m_dir: str, d_dir: str) -> str:
    """势头 × 背离 → Q2展望。任一数据不足 → 数据不足。"""
    if "数据不足" in (m_dir, d_dir):
        return "数据不足"
    return _VERDICT_MATRIX.get((m_dir, _norm_div(d_dir)), "中性")


def confidence_level(m_dir: str, d_dir: str, data_complete: bool) -> str:
    """置信度:两信号同向→高;矛盾或含持平→中;数据缺期/异常→低。"""
    if not data_complete or "数据不足" in (m_dir, d_dir):
        return "低"
    d = _norm_div(d_dir)
    if (m_dir == "加速" and d == "改善") or (m_dir == "减速" and d == "承压"):
        return "高"
    return "中"


# ============ 主分析 ============

def analyze(fin: dict) -> dict:
    """主入口:财报数据 → Q2展望结果。

    Args:
        fin: fetcher.get_financial 的返回 {code, name, industry, reports}

    Returns:
        完整结果 dict(含 q1 基础数据 + q2_outlook)。
    """
    reports = fin.get("reports", [])
    single = single_quarterize(reports)

    # 定位本期 Q1(数据中 year 最大的 Q1)
    q1_years = sorted({y for (y, q) in single.keys() if q == 1})
    cur_year = q1_years[-1] if q1_years else None

    base = {
        "code": fin.get("code", ""),
        "name": fin.get("name", ""),
        "industry": fin.get("industry", ""),
        "report_period": f"{cur_year}Q1" if cur_year else "",
        "q1": {},
        "q2_outlook": {},
        "data_date": "",
        "source": "东方财富 datacenter RPT_LICO_FN_CPD",
    }

    if cur_year is None:
        base["q2_outlook"] = _empty_outlook("无任何一季报数据")
        return base

    cur_q1 = single.get((cur_year, 1))
    prev_q1 = single.get((cur_year - 1, 1))
    q4_prev = single.get((cur_year - 1, 4))     # 去年 Q4 单季
    q4_prev2 = single.get((cur_year - 2, 4))    # 前年 Q4 单季(算去年Q4同比基数)

    # Q1 同比
    q1_np = cur_q1["parent_netprofit"] if cur_q1 else None
    q1_rev = cur_q1["revenue"] if cur_q1 else None
    q1_gm = cur_q1["gross_margin"] if cur_q1 else None

    np_q1_yoy = yoy(q1_np, prev_q1["parent_netprofit"] if prev_q1 else None)
    rev_q1_yoy = yoy(q1_rev, prev_q1["revenue"] if prev_q1 else None)
    np_q4_yoy = yoy(
        q4_prev["parent_netprofit"] if q4_prev else None,
        q4_prev2["parent_netprofit"] if q4_prev2 else None,
    )

    # 毛利率变化
    gm_prev = prev_q1["gross_margin"] if prev_q1 else None
    gm_chg = (q1_gm - gm_prev) if (q1_gm is not None and gm_prev is not None) else None

    # 信号方向
    m_dir = momentum_direction(np_q1_yoy, np_q4_yoy)
    d_dir = divergence_direction(rev_q1_yoy, np_q1_yoy, gm_chg)

    # 数据完整度
    data_complete = all([
        cur_q1 is not None, prev_q1 is not None,
        q4_prev is not None, q4_prev2 is not None,
        not (cur_q1 or {}).get("anomaly"),
        not (q4_prev or {}).get("anomaly"),
    ])

    verdict = combine_verdict(m_dir, d_dir)
    confidence = confidence_level(m_dir, d_dir, data_complete)

    # 是否已有更新报告期(提示)
    latest = reports[0] if reports else None  # 倒序,最新在前
    newer_note = None
    if latest and (latest["year"], latest["quarter"]) != (cur_year, 1):
        newer_note = f"已有更新的报告期 {latest['qdate']},本展望仍基于 {cur_year}Q1"

    # Q1 报告日
    q1_report = next((r for r in reports
                      if r["year"] == cur_year and r["quarter"] == 1), None)
    base["data_date"] = q1_report["report_date"] if q1_report else ""

    # 组装
    base["q1"] = {
        "netprofit_yoy": _r2(np_q1_yoy),
        "revenue_yoy": _r2(rev_q1_yoy),
        "gross_margin": _r2(q1_gm),
        "gross_margin_prev": _r2(gm_prev),
        "parent_netprofit_yi": _to_yi(q1_np),
        "parent_netprofit_prev_yi": _to_yi(prev_q1["parent_netprofit"]) if prev_q1 else None,
    }
    base["q2_outlook"] = {
        "verdict": verdict,
        "confidence": confidence,
        "signals": {
            "momentum": {
                "q1_single_yoy": _r2(np_q1_yoy),
                "q4_single_yoy": _r2(np_q4_yoy),
                "direction": m_dir,
                "note": _momentum_note(np_q1_yoy, np_q4_yoy, m_dir),
            },
            "divergence": {
                "revenue_yoy": _r2(rev_q1_yoy),
                "netprofit_yoy": _r2(np_q1_yoy),
                "gross_margin_chg": _r2(gm_chg),
                "direction": d_dir,
                "note": _divergence_note(rev_q1_yoy, np_q1_yoy, gm_chg, d_dir),
            },
        },
        "summary": _summary(verdict, m_dir, d_dir, confidence, newer_note),
    }
    return base


def _empty_outlook(reason: str) -> dict:
    return {
        "verdict": "数据不足",
        "confidence": "低",
        "signals": {"momentum": {}, "divergence": {}},
        "summary": f"关键数据缺失,无法给出Q2展望:{reason}",
    }


def _momentum_note(q1_yoy, q4_yoy, direction) -> str:
    if direction == "数据不足":
        return "Q4单季同比数据缺失,无法判断势头"
    q1 = f"{q1_yoy:+.1f}%" if q1_yoy is not None else "N/A"
    q4 = f"{q4_yoy:+.1f}%" if q4_yoy is not None else "N/A"
    if direction == "加速":
        return f"Q1单季同比 {q1} 较 Q4单季同比 {q4} 增长加速,Q2有望延续"
    if direction == "减速":
        return f"Q1单季同比 {q1} 较 Q4单季同比 {q4} 进一步走弱,Q2承压"
    return f"Q1单季同比 {q1} 与 Q4单季同比 {q4} 基本持平,势头平稳"


def _divergence_note(rev_yoy, np_yoy, gm_chg, direction) -> str:
    if direction == "数据不足":
        return "营收或净利同比缺失,无法判断背离"
    rev = f"{rev_yoy:+.1f}%" if rev_yoy is not None else "N/A"
    np_ = f"{np_yoy:+.1f}%" if np_yoy is not None else "N/A"
    gm = ""
    if gm_chg is not None:
        gm = f",毛利率{'升' if gm_chg > 0 else '降'}{abs(gm_chg):.1f}pct"
    if direction == "利润承压":
        return f"营收同比 {rev} 但净利同比 {np_}{gm},成本/价格压力,Q2净利承压"
    if direction == "利润改善":
        return f"营收同比 {rev},净利同比 {np_}{gm},盈利能力改善,Q2有望向好"
    return f"营收同比 {rev} 与净利同比 {np_} 基本同步{gm}"


def _summary(verdict, m_dir, d_dir, confidence, newer_note) -> str:
    if verdict == "数据不足":
        return "关键数据缺失,无法给出Q2展望" + (f"。{newer_note}" if newer_note else "")
    parts = []
    if m_dir == "加速":
        parts.append("增长加速")
    elif m_dir == "减速":
        parts.append("增长减速")
    if d_dir == "利润承压":
        parts.append("利润承压")
    elif d_dir == "利润改善":
        parts.append("利润改善")
    body = "、".join(parts) if parts else "信号中性"
    text = f"Q2展望{verdict}(置信度{confidence}):{body}。"
    if newer_note:
        text += newer_note
    return text


def _r2(v):
    """保留 2 位小数,None 透传。"""
    return round(v, 2) if v is not None else None


def _to_yi(v):
    """元 → 亿元,保留 2 位。"""
    return round(v / YI, 2) if v is not None else None
