# -*- coding: utf-8 -*-
"""
大盘市况判断 (Market Regime)
==================================
每天判断大盘市况, 给出 🟢进攻 / 🟡防守 / 🔴退守 三档信号, 直接回答"今天该不该交易"。
专治"调整市继续硬干"的盲区 —— 把交易冲动用一个客观数字信号拦在前面。

信号逻辑:
  趋势分(上证+沪深300+创业板): 价格vsMA20 + MA20斜率 + 近20日新高/新低, 每个-3~+3, 三指数合计-9~+9
  宽度分: 涨停家数 + 涨跌比 + 涨幅中位数, 合计约-4~+4
  综合 = 趋势 + 宽度;  >=+4 进攻 / -3~+3 防守 / <=-4 退守

用法: python scripts/market_regime.py [--note "..."]
输出: docs/trade-review/output/regime_YYYY-MM-DD.md
      docs/trade-review/regime_history.json (历史, 看市况转变)
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import requests

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
sess = requests.Session()
sess.trust_env = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "trade-review", "output")
HISTORY = os.path.join(ROOT, "docs", "trade-review", "regime_history.json")

INDICES = [("sh000001", "上证指数"), ("sh000300", "沪深300"), ("sz399006", "创业板指")]


# ---------- 1. 指数K线 ----------
def fetch_index_kline(sym, days=70):
    """新浪主, 腾讯备。返回 [{date,close},...] 正序。"""
    # 新浪
    try:
        r = sess.get("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
                     params={"symbol": sym, "scale": 240, "ma": "no", "datalen": days}, timeout=15)
        data = r.json()
        if data:
            return [{"date": d["day"], "close": float(d["close"])} for d in data]
    except Exception:
        pass
    # 腾讯备选
    try:
        start = "2025-01-01"
        r = sess.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                     params={"param": f"{sym},day,{start},,{days+5},qfq"}, timeout=15)
        d = r.json()
        if d.get("code") == 0:
            sd = d.get("data", {}).get(sym, {})
            rows = sd.get("qfqday", []) or sd.get("day", [])
            return [{"date": it[0], "close": float(it[2])} for it in rows]
    except Exception:
        pass
    return []


def trend_score(kline):
    """单指数趋势分: -3~+3。价格vsMA20 + MA20斜率 + 近20日新高/新低。"""
    if len(kline) < 25:
        return 0, {}, None
    closes = [k["close"] for k in kline]
    ma20 = np.mean(closes[-20:])
    cur = closes[-1]
    prev_ma = np.mean(closes[-25:-5])  # 10天前的MA20近似
    score = 0
    # 价格 vs MA20
    above = cur > ma20
    score += 1 if above else -1
    # MA20 斜率(5日变化近似)
    rising = ma20 > prev_ma
    score += 1 if rising else -1
    # 近20日新高/新低
    hi20 = max(closes[-20:])
    lo20 = min(closes[-20:])
    if cur >= hi20 - 1e-9:
        score += 1
    elif cur <= lo20 + 1e-9:
        score -= 1
    info = dict(close=cur, ma20=ma20, above_ma="站上" if above else "跌破",
                slope="上行" if rising else "下行",
                state="近20日新高" if cur >= hi20 - 1e-9 else ("近20日新低" if cur <= lo20 + 1e-9 else "中段"))
    return score, info, cur


# ---------- 2. 市场宽度(东财全A股) ----------
def fetch_market_breadth(retries=3):
    """东财全市场优先, 失败降级新浪沪深300成分。返回统计dict(含source)或None。"""
    def _stats(pairs, full):
        chgs = [c for _, c in pairs if c is not None]
        if not chgs:
            return None
        ups = sum(1 for c in chgs if c > 0)
        downs = sum(1 for c in chgs if c < 0)
        zt = dt = 0
        for code, chg in pairs:
            if chg is None:
                continue
            c = str(code).zfill(6)
            if c.startswith(("300", "301", "688", "689")):
                zl, dl = 19.5, -19.5
            elif c.startswith(("8", "4", "92")):
                zl, dl = 29.5, -29.5
            else:
                zl, dl = 9.7, -9.7
            if chg >= zl:
                zt += 1
            elif chg <= dl:
                dt += 1
        return dict(ups=ups, downs=downs, flats=len(chgs) - ups - downs, zt=zt, dt=dt,
                    median=float(np.median(chgs)), total=len(chgs),
                    up_down_ratio=ups / downs if downs else 99, full=full)

    # 源1: 东财全市场
    for attempt in range(retries):
        try:
            r = sess.get("http://push2.eastmoney.com/api/qt/clist/get",
                         params={"pn": 1, "pz": 6000, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                                 "fid": "f3", "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                                 "fields": "f12,f3"}, timeout=20,
                         headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
            data = r.json().get("data", {}).get("diff") or []
            if data:
                pairs = []
                for it in data:
                    try:
                        pairs.append((str(it.get("f12", "")), float(it.get("f3"))))
                    except Exception:
                        pass
                b = _stats(pairs, True)
                if b:
                    b["source"] = "东财全市场"
                    return b
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5)
    # 源2: 新浪沪深300成分(权重宽度)
    H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
         "Referer": "http://vip.stock.finance.sina.com.cn/"}
    rows = []
    for page in range(1, 4):
        try:
            r = sess.get("http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData",
                         params={"page": page, "num": 100, "node": "hs300", "sort": "changepercent", "asc": 0},
                         headers=H, timeout=15)
            d = r.json()
            if d:
                rows.extend(d)
            time.sleep(0.3)
        except Exception:
            pass
    if len(rows) >= 100:
        pairs = []
        for x in rows:
            try:
                pairs.append((x.get("symbol", ""), float(x.get("changepercent", 0) or 0)))
            except Exception:
                pass
        b = _stats(pairs, False)
        if b:
            b["source"] = "新浪沪深300成分(权重宽度)"
            return b
    print("  [WARN] 宽度获取失败(东财+新浪均失败), 仅用趋势分判断")
    return None


def breadth_score(b):
    if b is None:
        return 0
    s = 0
    # 涨跌比(全市场/成分都适用)
    if b["up_down_ratio"] >= 2.0:
        s += 1
    elif b["up_down_ratio"] < 0.5:
        s -= 1
    # 涨幅中位数
    if b["median"] >= 1.0:
        s += 1
    elif b["median"] <= -1.0:
        s -= 1
    # 涨停潮(仅全市场有意义)
    if b.get("full"):
        if b["zt"] >= 60:
            s += 2
        elif b["zt"] >= 30:
            s += 1
        if b["dt"] >= 60:
            s -= 2
        elif b["dt"] >= 30:
            s -= 1
    return s


# ---------- 3. 等级 ----------
def grade(total):
    if total >= 4:
        return "green", "进攻市"
    if total <= -4:
        return "red", "退守市"
    return "yellow", "防守市"


ADVICE = {
    "green": [
        "🟢 进攻市 — 可正常按准入清单交易",
        "• 仓位可用到 5 万上限, 强势股可持有到 +8% 止盈",
        "• 开盘强势 + 放量 + 低价 的票可积极介入",
        "• 这是赚钱最容易的市况, 但仍遵守单笔≤5万、零补仓",
    ],
    "yellow": [
        "🟡 防守市 — 只做最强信号, 降频减仓",
        "• 仓位减半 (单笔 ≤ 2.5 万), 每周交易 ≤ 5 笔",
        "• 只做近端涨停+放量的最强票, 避开早盘, 14:45 后再定夺",
        "• 连亏 1 笔就停手半天 (进攻市允许 2 笔, 防守市只允许 1 笔)",
    ],
    "red": [
        "🔴 退守市 — 不开新仓! 只处理存量",
        "• 历史上你 80% 的大亏损发生在这种市况 (25年1月/10月)",
        "• 不开任何新仓, 只对存量执行止损/止盈",
        "• 把精力放在复盘和选股池更新, 等市况转黄/绿再动手",
    ],
}


# ---------- 4. 历史 ----------
def load_hist():
    if os.path.exists(HISTORY):
        try:
            with open(HISTORY, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def append_hist(rec):
    hist = load_hist()
    # 同一天覆盖
    hist = [h for h in hist if h["date"] != rec["date"]]
    hist.append(rec)
    hist = hist[-120:]
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    return hist


# ---------- 5. 渲染 ----------
LIGHT = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def render(date_tag, idx_scores, idx_infos, breadth, t_score, b_score, total, color, name, hist, note):
    L = []
    a = L.append
    a(f"# 大盘市况 · {date_tag}\n")
    if note:
        a(f"> **备注**: {note}\n")
    a(f"> 综合得分 **{total:+d}** = 趋势 {t_score:+d} + 宽度 {b_score:+d}\n")
    a(f"## 信号: {LIGHT[color]} {color.upper()} · {name}\n")
    for line in ADVICE[color]:
        a(line)
    a("")

    a("\n## 📈 指数趋势")
    a("| 指数 | 收盘 | MA20 | 站上/跌破 | MA20斜率 | 20日位置 | 得分 |")
    a("|---|---|---|---|---|---|---|")
    for (sym, label), sc, info in idx_scores:
        if info:
            a(f"| {label} | {info['close']:.1f} | {info['ma20']:.1f} | {info['above_ma']} | {info['slope']} | {info['state']} | {sc:+d} |")

    a("\n## 🌡️ 市场宽度")
    if breadth:
        a(f"- 数据源: {breadth.get('source', '未知')}")
        a(f"- 涨/跌/平: **{breadth['ups']}** / {breadth['downs']} / {breadth['flats']}  (共 {breadth['total']} 只)")
        a(f"- 涨跌比: **{breadth['up_down_ratio']:.2f}** : 1  | 涨幅中位数: **{breadth['median']:+.2f}%**")
        a(f"- 涨停 **{breadth['zt']}** 只 / 跌停 **{breadth['dt']}** 只")
        if breadth.get("full"):
            if breadth["zt"] >= 60:
                a("- 涨停潮, 赚钱效应强")
            elif breadth["zt"] < 20:
                a("- 涨停稀少, 赚钱效应弱")
        else:
            a("- (沪深300成分, 涨停数参考意义小, 主要看涨跌比和中位数)")
    else:
        a("- *(宽度数据获取失败, 仅用趋势分判断)*")

    if hist and len(hist) >= 2:
        a("\n## 📅 近期市况")
        a("| 日期 | 得分 | 信号 |")
        a("|---|---|---|")
        for h in hist[-10:]:
            a(f"| {h['date']} | {h['score']:+d} | {LIGHT.get(h['color'])} {h['name']} |")
        # 市况转变提醒
        if len(hist) >= 2 and hist[-2]["color"] != hist[-1]["color"]:
            a(f"\n> ⚡ 市况转变: {hist[-2]['name']} → {hist[-1]['name']}")
            if hist[-1]["color"] == "red":
                a("> **从进攻/防守转入退守, 立即停止开新仓!**")
            elif hist[-1]["color"] == "green":
                a("> 市况转暖, 可逐步恢复正常交易节奏")

    a("\n---")
    a(f"*生成于 {datetime.now():%Y-%m-%d %H:%M} | 信号为客观数字, 不保证未来有效, 最终判断结合自身仓位与心态*\n")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="大盘市况判断")
    ap.add_argument("--note", default="", help="备注")
    ap.add_argument("--no-history", action="store_true", help="不入历史")
    args = ap.parse_args()
    date_tag = datetime.now().strftime("%Y-%m-%d")

    print("[1/4] 拉指数K线 ...")
    idx_scores = []
    t_score = 0
    for sym, label in INDICES:
        kl = fetch_index_kline(sym)
        sc, info, _ = trend_score(kl)
        idx_scores.append(((sym, label), sc, info))
        t_score += sc
        print(f"      {label}: {len(kl)}根 得分{sc:+d}")
    print(f"      趋势分合计 {t_score:+d}")

    print("[2/4] 拉市场宽度 ...")
    breadth = fetch_market_breadth()
    b_score = breadth_score(breadth)
    if breadth:
        print(f"      [{breadth.get('source','?')}] 涨{breadth['ups']}/跌{breadth['downs']} 涨停{breadth['zt']} 中位{breadth['median']:+.2f}% 宽度分{b_score:+d}")
    print(f"      宽度分 {b_score:+d}")

    total = t_score + b_score
    color, name = grade(total)
    print(f"[3/4] 综合 {total:+d} -> {name}")

    hist = []
    if not args.no_history:
        hist = append_hist(dict(date=date_tag, score=total, color=color, name=name, note=args.note))
    else:
        hist = load_hist()

    md = render(date_tag, idx_scores, idx_scores, breadth, t_score, b_score, total, color, name, hist, args.note)
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"regime_{date_tag}.md")
    if os.path.exists(out_path):
        out_path = os.path.join(OUT_DIR, f"regime_{date_tag}-{datetime.now().strftime('%H%M')}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"[4/4] 报告 -> {out_path}")
    print("\n" + "=" * 48)
    print(f"  信号: {name}  (得分 {total:+d})")
    print(f"  详情见报告文件")
    print("=" * 48)


if __name__ == "__main__":
    main()
