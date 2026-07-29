# -*- coding: utf-8 -*-
"""
每日复盘 → 次日剧本 (fupan)
==================================
收盘后串联市况(market_regime) + 主线(zhuxian) + 自拉指数K线(结构/量能),
按高手复盘 5 步产出「次日剧本.md」(三套应对预案)。

核心理念: 不预测涨跌, 只做"信号触发才动手"的应对。

流程:
  第0步 市况总开关 (market_regime 🔴/🟡/🟢) — 决定要不要操作
  第1步 大盘状态 (结构MA排列 + 量能 + 权重vs题材)
  第2步 主线与阶段 (zhuxian Top + 阶段判定: 启动/加速/分歧/退潮)
  第3步 强势股拆解 (首板属性/连板健康/分歧节点 — 人工研判)
  第4步 失败案例 (市场宽度风险信号 — 炸板/断板归类人工)
  第5步 次日剧本 (三套情景: 继续走强/分歧震荡/全面走弱)

用法:
  python .claude/skills/fupan/main.py                 # 默认, 自包含运行
  python .claude/skills/fupan/main.py --note "..."    # 加备注
  python .claude/skills/fupan/main.py --top 3         # 主线只看 Top 3

输出: .claude/skills/fupan/output/{日期}.md
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime

import numpy as np
import requests

# ---------- 路径 ----------
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))          # .../fupan
SKILLS_DIR = os.path.dirname(SKILL_DIR)                         # .../skills
CLAUDE_DIR = os.path.dirname(SKILLS_DIR)                        # .../.claude
ROOT = os.path.dirname(CLAUDE_DIR)                              # 项目根
OUT_DIR = os.path.join(SKILL_DIR, "output")
ZHUXIAN_DATA = os.path.join(ROOT, ".claude", "skills", "zhuxian", "data")
PANQIAN_DIR = os.path.join(ROOT, ".claude", "skills", "panqian", "output")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")

# 屏蔽代理 (与 market_regime/kangdie 一致, 避免拉数据被本地代理干扰)
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
sess = requests.Session()
sess.trust_env = False

# Windows + Git Bash: Python stdout 默认 cp936, emoji(🔴)无法编码会崩, 中文也会乱码;
# 统一重定向为 utf-8 输出 (失败则降级, 不阻断)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 复用 market_regime 的核心函数 (市况判定逻辑), 失败则降级
sys.path.insert(0, SCRIPTS_DIR)
try:
    import local_kline                     # 招商证券 vipdoc 本地日K (快/不被封), 指数K线优先走它
    HAS_LOCAL = True
except Exception:
    HAS_LOCAL = False
try:
    import market_regime
    HAS_REGIME = True
except Exception as _e:
    HAS_REGIME = False
    print(f"  [WARN] 无法 import market_regime({_e}), 市况将降级(仅用指数结构)")
try:
    import fupan_strong_scan               # 第3步: 涨停+连板梯队扫描 (本地vipdoc)
    import fupan_failure_scan              # 第4步: 炸板/断板/大跌扫描 (本地vipdoc)
    HAS_SCAN = True
except Exception as _e:
    HAS_SCAN = False
    print(f"  [WARN] 无法 import 扫描模块({_e}), 第3/4步降级为纯checklist")

INDICES = [("sh000001", "上证指数"), ("sh000300", "沪深300"), ("sz399006", "创业板指")]
LIGHT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


# ---------- 1. 指数K线(含volume) ----------
def fetch_index_kline(sym, days=70):
    """指数日K, 返回 [{date,close,volume},...] 正序。volume(成交额元)用于量能判定。
    优先本地 vipdoc(招商证券通达信 day 文件, 快/不被封); 本地无数据才 fallback 新浪。
    指数无除权问题, 本地不复权价直接可用。"""
    if HAS_LOCAL:
        kl = local_kline.fetch_index_kline(sym, days=days)
        if kl:
            return kl
        print(f"  [INFO] 本地无 {sym} 日K, fallback 新浪")
    try:
        r = sess.get(
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
            params={"symbol": sym, "scale": 240, "ma": "no", "datalen": days}, timeout=15)
        data = r.json()
        if data:
            return [{"date": d["day"], "close": float(d["close"]),
                     "volume": float(d.get("volume", 0) or 0)} for d in data]
    except Exception:
        pass
    return []


# ---------- 2. 大盘结构 (MA排列) ----------
def structure_state(kl):
    """返回 (状态, 详情dict)。状态: 上升/震荡/反弹末尾/下跌/数据不足。"""
    if len(kl) < 21:
        return "数据不足", {}
    closes = [k["close"] for k in kl]
    ma5 = float(np.mean(closes[-5:]))
    ma10 = float(np.mean(closes[-10:]))
    ma20 = float(np.mean(closes[-20:]))
    cur = closes[-1]
    hi20 = max(closes[-20:])
    arrange = "多头" if (ma5 > ma10 > ma20) else ("空头" if (ma5 < ma10 < ma20) else "交织")
    info = dict(cur=cur, ma5=ma5, ma10=ma10, ma20=ma20, arrange=arrange)
    # 下跌: 收盘<MA20 且 空头排列
    if cur < ma20 and ma5 < ma10 < ma20:
        return "下跌", info
    # 上升: 收盘>MA20 且 多头排列
    if cur > ma20 and ma5 > ma10 > ma20:
        if cur >= hi20 * 0.98:                       # 触近前高 → 警惕见顶
            info["warn"] = "触近20日高点, 警惕见顶"
            return "反弹末尾", info
        return "上升", info
    # 反弹末尾: 反弹中(近5日涨)且接近前高
    if len(closes) >= 6 and closes[-1] > closes[-6] and cur >= hi20 * 0.97:
        info["warn"] = "反弹接近前高, 警惕"
        return "反弹末尾", info
    return "震荡", info


# ---------- 3. 量能 ----------
def volume_state(kl):
    """返回 (状态, ratio5, ratio1)。
    ratio5=今/前5日均(看趋势), ratio1=今/昨(看短期, 贴合行情软件"较昨"口径)。
    双口径防误判: 地量反弹日 ratio5 仍<1(前5日含高位拉高均值), 但 ratio1>1 已示放量。"""
    vols = [k["volume"] for k in kl if k.get("volume", 0) > 0]
    if len(vols) < 6:
        return "数据不足", 0.0, 0.0
    today = vols[-1]
    avg5 = float(np.mean(vols[-6:-1]))
    if avg5 <= 0:
        return "数据不足", 0.0, 0.0
    ratio5 = today / avg5
    ratio1 = today / vols[-2] if vols[-2] > 0 else 0.0
    # 放量: 5日均或昨量任一显著放大; 缩量: 两者都缩; 否则平量
    if ratio5 > 1.2 or ratio1 > 1.2:
        return "放量(资金进攻)", ratio5, ratio1
    if ratio5 < 0.8 and ratio1 < 0.9:
        return "缩量(观望浓)", ratio5, ratio1
    return "平量(观望)", ratio5, ratio1


# ---------- 4. 权重 vs 题材 ----------
def weight_vs_theme(sh_chg, cyb_chg):
    diff = sh_chg - cyb_chg
    if diff > 0.5:
        return "权重护盘(上证强/创业板弱, 虚涨, 赚钱效应差)"
    if diff < -0.5:
        return "题材主导(创业板强, 赚钱效应在中小票)"
    return "同涨同跌(无分化)"


# ---------- 5. 市况总开关 (复用 market_regime) ----------
def regime_switch():
    """返回 (color, name, total, breadth)。自包含: 复用 market_regime 核心函数重算。"""
    if not HAS_REGIME:
        return None, None, None, None
    t_score = 0
    for sym, _label in INDICES:
        kl = market_regime.fetch_index_kline(sym)         # market_regime 版本只要 close
        sc, _info, _ = market_regime.trend_score(kl)
        t_score += sc
    breadth = market_regime.fetch_market_breadth()
    b_score = market_regime.breadth_score(breadth)
    total = t_score + b_score
    color, name = market_regime.grade(total)
    return color, name, total, breadth


# ---------- 6. 主线与阶段 (读 zhuxian json) ----------
def load_zx(date_str):
    p = os.path.join(ZHUXIAN_DATA, f"zx_{date_str}.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def mainline_stage(today_zx, top_n=5):
    """读近7日 zx_*.json, 判主线阶段。返回 (阶段, 详情dict)。"""
    if today_zx is None:
        return "未跑zhuxian", {"hint": "建议先运行 /zhuxian 获取主线板块, 第2步将更完整"}
    sectors = today_zx.get("sectors", [])[:top_n]
    files = sorted(glob.glob(os.path.join(ZHUXIAN_DATA, "zx_*.json")))
    hist_scores = []
    for fp in files[-7:]:
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("sectors"):
                hist_scores.append((d.get("date", ""), d["sectors"][0].get("trend_score", 0)))
        except Exception:
            pass
    info = {
        "top": [(s.get("name"), s.get("trend_score"), s.get("period_return_20d")) for s in sectors],
        "hist": hist_scores,
    }
    # 阶段初判: 基于 Top1 趋势得分变化 (粗判, 非精确)
    if len(hist_scores) >= 3:
        recent = [s for _, s in hist_scores[-3:]]
        if recent[-1] > recent[0] + 2:
            return "加速期(Top1得分连续上升)", info
        if recent[-1] < recent[0] - 2:
            return "分歧/退潮期(Top1得分见顶回落)", info
        return "震荡期(Top1得分平稳)", info
    return "数据不足(需积累多日zx)", info


# ---------- 6.5 隔夜信号对照 (读 panqian 盘前温度计) ----------
def _panqian_tone(pq_path):
    """从 panqian 报告抓'隔夜定调'一行,返回 (tone_str, a50_pct) 或 (None, None)。"""
    try:
        with open(pq_path, encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return None, None
    import re
    m = re.search(r"外部环境:\*\*(.+?)\*\*", txt)
    tone = m.group(1) if m else None
    a50m = re.search(r"A50期货:[\d.]+\(([+-]?[\d.]+)%\)", txt)
    a50_pct = float(a50m.group(1)) if a50m else None
    return tone, a50_pct


def realize_degree(predicted_low, chg):
    """兑现度:预示低开 vs 当日实际涨跌(close-based)。返回 兑现/背离/部分兑现。
    注: fupan K线无 open 字段, 用当日涨跌(close vs prev close)对照。"""
    if predicted_low:
        if chg < -0.15:
            return "兑现"
        if chg > 0.15:
            return "背离"
        return "部分兑现"
    return "兑现" if chg > -0.15 else "背离"


def render_panqian_link(date_str, sh_chg):
    """渲染第-1步对照小节。读 panqian 当日报告,对照今日实际涨跌。
    无 panqian 报告 → 降级提示。"""
    pq_path = os.path.join(PANQIAN_DIR, f"{date_str}.md")
    tone, a50_pct = _panqian_tone(pq_path)
    L = ["## -1. 隔夜信号 vs 今日实际(读自 panqian 盘前温度计)"]
    if tone is None:
        L.append("> ⚠️ 未找到今日 panqian 盘前温度计,建议盘前先跑 `/panqian`,以形成隔夜信号对照闭环。")
        return "\n".join(L) + "\n"
    predicted_low = (a50_pct is not None and a50_pct < -0.3) or tone in ("偏冷", "恐慌")
    deg = realize_degree(predicted_low, sh_chg)
    L.append(f"- 隔夜预示:外部**{tone}**" +
             (f"(A50 {a50_pct:+.2f}% → 预示{'低开' if predicted_low else '平/高开'})" if a50_pct is not None else ""))
    L.append(f"- 今日实际:上证当日 {sh_chg:+.2f}%(close-based; fupan K线无 open, 开盘级对照待补)")
    L.append(f"- 兑现度:【{deg}】")
    L.append("- 教训沉淀:____(人工填, 本次隔夜信号灵不灵)")
    return "\n".join(L) + "\n"


# ---------- 7. 渲染次日剧本 ----------
def render(date_str, color, name, total, breadth, idx_data, stage, stage_info, note,
           strong=None, failure=None, panqian_block=""):
    L = []
    a = L.append
    # 预算指数当日涨跌 + 最新交易日日期 (供第1步表格 + 第4步背离校验共用)
    sh_chg = cyb_chg = 0.0
    latest_date = ""
    for _lbl, _kl in idx_data:
        if not _kl:
            continue
        if "上证" in _lbl:
            latest_date = str(_kl[-1].get("date", ""))[:10]
        if len(_kl) >= 2:
            _chg = (_kl[-1]["close"] - _kl[-2]["close"]) / _kl[-2]["close"] * 100
        else:
            _chg = 0.0
        if "上证" in _lbl:
            sh_chg = _chg
        if "创业板" in _lbl:
            cyb_chg = _chg
    a(f"# 次日剧本 · {date_str}\n")
    if panqian_block:
        a(panqian_block)
    if latest_date and latest_date != date_str:
        a(f"> **数据截至最新交易日 {latest_date}**（{date_str} 盘中或尚未收盘, 采用最近完整交易日数据）\n")
    if note:
        a(f"> **备注**: {note}\n")

    # 退守/市况不明 顶部 banner (⛔CHECKPOINT 代码层兑现: 报告顶部明示纪律)
    if color == "red":
        a("\n---")
        a("## ⛔ 退守市 · 今日不开新仓")
        a("> 市况总开关 🔴, 第5步仓位栏**强制锁🔴空仓**, 只处理存量止损/止盈。**不因想买票而放宽。**")
        a("---\n")
    elif color is None:
        a("\n---")
        a("## ⛔ 市况不明 · 默认偏保守空仓")
        a("> market_regime 不可用, 无法判定市况总开关。**默认按退守处理: 不开新仓**, 第5步仓位栏锁🔴空仓, 建议修复 market_regime 后重跑。")
        a("---\n")

    # 第0步 市况总开关
    a("## 0. 市况总开关")
    if color:
        a(f"**{LIGHT[color]} {color.upper()} · {name}** (综合得分 {total:+d})\n")
        if color == "red":
            a("> 🔴 退守市 → 剧本直接落「空仓观望」, 不开新仓, 只处理存量止损/止盈。\n")
        elif color == "yellow":
            a("> 🟡 防守市 → 半仓做个股, 只做最强信号, 降频减仓。\n")
        else:
            a("> 🟢 进攻市 → 可正常仓位按 qsht 体系选股。\n")
    else:
        a("*(market_regime 不可用, 跳过市况总开关, 仅参考下方大盘结构)*\n")

    # 第1步 大盘状态
    a("## 1. 大盘状态（不看涨跌看状态）")
    a("| 指数 | 收盘 | 当日% | 结构(MA5/10/20) | 量能 |")
    a("|---|---|---|---|---|")
    for label, kl in idx_data:
        if kl:
            if len(kl) >= 2:
                chg = (kl[-1]["close"] - kl[-2]["close"]) / kl[-2]["close"] * 100
            else:
                chg = 0.0
            st, sinfo = structure_state(kl)
            vs, ratio5, ratio1 = volume_state(kl)
            arrange = sinfo.get("arrange", "-")
            ratio_s = (f"今/昨{ratio1:.2f} 今/5日{ratio5:.2f}") if ratio5 > 0 else "-"
            a(f"| {label} | {kl[-1]['close']:.1f} | {chg:+.2f}% | {st}({arrange}) | {vs} {ratio_s} |")
        else:
            a(f"| {label} | 取数失败 | - | - | - |")
    a(f"\n**权重 vs 题材**: {weight_vs_theme(sh_chg, cyb_chg)}")

    # 第2步 主线与阶段
    a("\n## 2. 主线与阶段（资金在哪抱团）")
    a(f"**主线阶段初判**: {stage}")
    if stage_info.get("top"):
        a("\n| 主线板块 | 趋势得分 | 20日涨幅 |")
        a("|---|---|---|")
        for nm, score, ret in stage_info["top"]:
            ret_s = f"{ret:+.1f}%" if isinstance(ret, (int, float)) else "-"
            a(f"| {nm} | {score} | {ret_s} |")
    if stage_info.get("hint"):
        a(f"\n> ⚠️ {stage_info['hint']}")
    if stage_info.get("hist"):
        a(f"\n*近7日 Top1 趋势得分序列: {' → '.join(str(s) for _, s in stage_info['hist'])}*")

    # 第3步 强势股拆解 (客观扫描 + 人工研判)
    a("\n## 3. 强势股拆解（⛔ 人工研判必填）")
    if strong and strong[1]:
        _, stocks = strong
        ladder = {}
        for s in stocks:
            ladder[s["height"]] = ladder.get(s["height"], 0) + 1
        first_board = ladder.get(1, 0)
        lian = sorted([s for s in stocks if s["height"] >= 2],
                      key=lambda x: (-x["height"], -x["chg"]))
        ladder_s = " / ".join(f"{h}板×{ladder[h]}" for h in sorted(ladder, reverse=True))
        a(f"**[客观扫描 · 本地vipdoc · fupan_strong_scan]** 今日涨停 **{len(stocks)}** 只: "
          f"首板 **{first_board}** + 连板 **{len(stocks)-first_board}**。梯队: {ladder_s}")
        if lian:
            a("\n| 代码 | 高度 | 收盘 | 封板 | 量比 | 振幅 | 客观标签 | 成色(pattern) |")
            a("|---|---|---|---|---|---|---|---|")
            for s in lian[:8]:
                sig = []
                if s["yizi"]:
                    sig.append("一字")
                if s["seal"] < 0.99:
                    sig.append("烂板")
                if s["vr"] >= 3:
                    sig.append("爆量")
                elif 0 < s["vr"] < 0.8:
                    sig.append("缩量")
                p = s.get("pattern")
                if p and "error" not in p:
                    pat = f"{p['shape']}/{p['volume']}/{p['sector']}→{p['suggest']}"
                else:
                    pat = "—"
                a(f"| {s['code']} | {s['height']}板 | {s['chg']:+.1f}% | {s['seal']:.2f} | "
                  f"{s['vr']:.1f} | {s['amp']:.1f}% | {' '.join(sig) or '温和'} | {pat} |")
            if len(lian) > 8:
                a(f"\n*…另有 {len(lian)-8} 只连板 (2板为主, 拆解优先看高度前8)*")
    a("\n> **三维度拆解** (从连板高度前N挑, 人工研判):")
    a("> - **首板属性**: 情绪板(板块齐涨/换手>20%) / 资金板(独立突破/龙虎榜) / 消息板(利好驱动/秒板)")
    a("> - **连板健康度**: 换手10–25% + 量温和放大 = 健康 ✅ / 连续一字 / 爆量烂板 = 不健康 ❌")
    a("> - **分歧节点**: 被砸崩(放量长阴)→不接力 / 承接走强(缩量企稳再涨停)→可接力")
    a(">\n> 填写: _______________________________________________")

    # 第4步 失败案例
    a("\n## 4. 失败案例·市场层面（⛔ 人工研判必填）")
    if breadth:
        a(f"- 涨停 **{breadth['zt']}** 只 / 跌停 **{breadth['dt']}** 只 / "
          f"涨跌比 {breadth['up_down_ratio']:.2f}:1 / 涨幅中位数 {breadth['median']:+.2f}%")
        # 宽度与指数背离校验 (防数据源脏数据误导: 东财宽度接口偶发异常)
        med = breadth.get("median", 0)
        # 宽度与指数背离校验: 相对背离(指数与中位数反向) + 绝对异常(中位±8%正常市场不可能, 东财宽度脏数据兜底)
        diverge = (cyb_chg < -2 and med > 3) or (cyb_chg > 2 and med < -3) or abs(med) > 8
        if diverge:
            a(f"- ⚠️ **宽度数据与指数严重背离**(创业板 {cyb_chg:+.1f}% 但中位 {med:+.2f}%), "
              f"疑数据源异常, **以指数为准, 忽略本行宽度**")
        elif breadth.get("full"):
            if breadth.get("zt", 0) < 20:
                a("- ⚠️ 涨停稀少, 赚钱效应弱, 警惕环境恶劣")
            if breadth.get("dt", 0) >= 30:
                a("- ⚠️ 跌停潮, 市场风险高")
    else:
        a("- *(宽度数据不可用)*")
    if failure and (failure["zhaban"] or failure["duanban"] or failure["bigdown"]):
        a(f"\n**[客观扫描 · 本地vipdoc · fupan_failure_scan]** "
          f"炸板 **{len(failure['zhaban'])}** / 断板 **{len(failure['duanban'])}** / "
          f"高位长上影 **{len(failure['shangying'])}** / 大跌≤-7% **{len(failure['bigdown'])}**"
          f"(其中跌停≈{failure['dietting_n']})")
        if failure["duanban"]:
            du = sorted(failure["duanban"], key=lambda x: x[2])[:8]
            a(f"- **断板{len(failure['duanban'])}只(昨涨停今跌·追高重灾区)**: " +
              " / ".join(f"{d[0]} {d[2]:+.1f}%" for d in du))
        if failure["bigdown"]:
            bds = sorted(failure["bigdown"], key=lambda x: x[2])[:8]
            a(f"- **大跌{len(failure['bigdown'])}只**: " +
              " / ".join(f"{b[0]} {b[2]:+.1f}%" for b in bds))
    a("\n**归类根源** (人工研判):")
    a("> - **追高**(距5日高点>15% 或 ≥3板后追) / **模式外冲动**(非主线/qsht外) / **环境恶劣**(🔴退守市强操作)")
    a("> - 填写: _______________________________________________")
    a("> - 自己账户的失败交易由 `trade_review.py` 周复盘覆盖, 本步只看市场层面")

    # 第5步 次日剧本
    a("\n## 5. 🎬 次日三套剧本")
    a("> 不是预测涨跌, 是分情景给「触发信号 + 操作 + 仓位」。**信号触发前手放口袋。**\n")
    # 仓位联动: green=正常 / yellow=半仓 / red或None(市况不明)=空仓(偏保守, 对齐"少交易+严纪律")
    if color == "green":
        pos_a = "🟢正常"
    elif color == "yellow":
        pos_a = "🟡半仓"
    else:  # red 或 None(市况不明)
        pos_a = "🔴空仓(退守)"
    # B情景联动: 退守市或市况不明 → 整体锁空仓 (修bug: 原color=None时pos_b误给"🟡半仓以下"与pos_a矛盾)
    pos_b = "🔴空仓(退守)" if color in ("red", None) else "🟡半仓以下"
    a("| 情景 | 触发信号 | 操作 | 仓位 |")
    a("|---|---|---|---|")
    a(f"| **A 主线继续走强** | 龙头高开秒板/继续连板, 涨停家数不减 | 锁定主线强势股, 按 qsht 选接力标的 | {pos_a} |")
    a(f"| **B 分歧震荡** | 龙头高开低走/烂板增多, 涨跌互现 | 持股设止损(破MA10或前日低), **不追加** | {pos_b} |")
    a("| **C 全面走弱** | 龙头断板/低开, 创业板跌>1%, 涨停骤减 | **空仓观望**, 止损离场 | 🔴空仓 |")
    a("\n> **铁律**: 不到确认信号不动手。" +
      ("退守/市况不明→直接空仓。" if color in ("red", None) else "市况转弱信号出现即收手。"))

    a("\n> ⛔ **交付前 CHECKPOINT**: 第3步(强势股拆解)与第4步(失败归类)的 checklist 必须各至少填1条研判, 否则剧本视为未完成——空着交差属反例。")
    a("\n---")
    a(f"*生成于 {datetime.now():%Y-%m-%d %H:%M} | 客观数据 + 规则模板, 不构成投资建议, 主观部分需人工研判*")
    return "\n".join(L)


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="每日复盘 → 次日剧本")
    ap.add_argument("--note", default="", help="备注")
    ap.add_argument("--top", type=int, default=5, help="主线板块看 Top N (默认5)")
    ap.add_argument("--strict", action="store_true", help="门禁: 第3/4步占位符未填时报告顶部加红色banner且exit=1")
    args = ap.parse_args()
    date_str = datetime.now().strftime("%Y-%m-%d")
    print(f"[{date_str}] 每日复盘 → 次日剧本\n")

    print("[0/5] 市况总开关 (market_regime) ...")
    color, name, total, breadth = regime_switch()
    # 宽度是市况判定的关键输入: 三源(本地→东财→新浪)都取不到当日全市场数据 → 停止执行
    # (用户 2026-07-21 要求: 不用过期/错误宽度糊弄, 宁停勿错)
    if breadth is None:
        print("\n" + "=" * 52)
        print("⛔ 停止执行: 未取到最近交易日全市场宽度数据")
        if not HAS_REGIME:
            print("  原因: market_regime 不可用, 请检查 scripts/market_regime.py")
        else:
            print("  三源(本地vipdoc → 东财 → 新浪)均失败, 各源原因见上方 [宽度·...] 行。")
            print("  宽度是市况总开关关键输入, 缺失则无法可靠判市况 → 不生成剧本。")
            print("  排查: ① 招商证券客户端盘后下载最近交易日日线(本地源); ② 网络可达性(东财/新浪)。")
        print("=" * 52)
        sys.exit(1)
    if color:
        print(f"      {LIGHT[color]} {name} (得分 {total:+d})")
    else:
        print("      [降级] 仅用指数结构判断")

    print("[1/5] 拉指数K线 (结构/量能) ...")
    idx_data = []
    for sym, label in INDICES:
        kl = fetch_index_kline(sym)
        idx_data.append((label, kl))
        st, _ = structure_state(kl)
        vs, ratio5, ratio1 = volume_state(kl)
        ratio_s = (f"今/昨{ratio1:.2f} 今/5日{ratio5:.2f}") if ratio5 > 0 else "-"
        print(f"      {label}: {len(kl)}根 结构={st} 量能={vs}({ratio_s})")

    print("[2/5] 主线与阶段 (zhuxian) ...")
    today_zx = load_zx(date_str)
    stage, stage_info = mainline_stage(today_zx, top_n=args.top)
    print(f"      {stage}")

    print("[3/5] 强势股拆解 + 失败模式扫描 (本地vipdoc) ...")
    strong = failure = None
    if HAS_SCAN:
        try:
            strong = fupan_strong_scan.scan(top=8)
            failure = fupan_failure_scan.scan(top=8)
            if strong and strong[1]:
                _ladder = {}
                for s in strong[1]:
                    _ladder[s["height"]] = _ladder.get(s["height"], 0) + 1
                print("      涨停" + str(len(strong[1])) + "只 梯队: " +
                      " ".join(f"{h}板×{_ladder[h]}" for h in sorted(_ladder, reverse=True)))
            if failure:
                print(f"      炸板{len(failure['zhaban'])}/断板{len(failure['duanban'])}/"
                      f"大跌{len(failure['bigdown'])}(跌停≈{failure['dietting_n']})")
        except Exception as _e:
            print(f"      [WARN] 扫描失败({_e}), 第3/4步降级为纯checklist")
            strong = failure = None
    else:
        print("      [降级] 扫描模块不可用, 第3/4步为纯checklist")

    print("[4/5] 市场宽度信号 ...")
    if breadth:
        print(f"      涨停{breadth['zt']}/跌停{breadth['dt']} 中位{breadth['median']:+.2f}%")

    print("[5/5] 渲染次日剧本 ...")
    # 第-1步: 隔夜信号对照(读 panqian). 算上证当日涨跌(close-based, fupan K线无 open).
    sh_kl = next((kl for lbl, kl in idx_data if "上证" in lbl), [])
    sh_chg_pq = 0.0
    if len(sh_kl) >= 2:
        _prev = sh_kl[-2]["close"]
        sh_chg_pq = (sh_kl[-1]["close"] - _prev) / _prev * 100
    panqian_block = render_panqian_link(date_str, sh_chg_pq)
    md = render(date_str, color, name, total, breadth, idx_data, stage, stage_info, args.note,
                strong=strong, failure=failure, panqian_block=panqian_block)
    # --strict 门禁: 第3/4步 checklist 占位符未填时, 报告顶部加红色banner (防"空着交差")
    incomplete = args.strict and "_______" in md
    if incomplete:
        md = ("> ⛠️ **剧本未完成**: 第3步(强势股拆解)/第4步(失败归类)的 checklist 占位符仍为空, "
              "仓位建议**在填写前不生效**。请人工研判填入后再作为操作依据。\n\n---\n\n") + md
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{date_str}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n报告 -> {out_path}")
    print("\n" + "=" * 48)
    print(f"  次日剧本已生成: {out_path}")
    if color:
        tilt = "空仓观望" if color == "red" else ("半仓" if color == "yellow" else "正常")
        print(f"  市况: {LIGHT[color]} {name}  剧本倾向: {tilt}")
    print("=" * 48)
    if incomplete:
        print("  ⚠️ [STRICT] 第3/4步占位符未填, 已加红色banner, exit=1")
        sys.exit(1)


if __name__ == "__main__":
    main()
