# -*- coding: utf-8 -*-
"""fupan 第4步辅助: 扫描当日 炸板 / 断板 / 高位放量长上影 / 大跌, 输出名单 + 初步归类。
数据源: 本地招商证券 vipdoc (scripts/local_kline)。零网络, 永不被封。
用途: fupan 剧本第4步"失败案例·市场层面"的客观数据, 主观归类由人完成。

判定规则 (基于日K OHLC, lday 不复权, 短期形态不受影响):
  - 炸板: 盘中触及涨停(最高价涨幅≥limit*0.97) 但收盘未封板(收盘涨幅<limit*0.95)
  - 断板: 昨日涨停(昨涨幅≥limit*0.97) + 今日下跌(收盘涨幅<0)
  - 高位放量长上影: 上影占振幅>50% + 近20日高位(close≥hi20*0.93) + 量比>1.3 + 阴线
  - 大跌: 当日跌幅≤-7% (环境恶劣信号, 补充宽度)

用法:
  python scripts/fupan_failure_scan.py              # 自动取最新交易日
  python scripts/fupan_failure_scan.py --date 2026-07-22
  python scripts/fupan_failure_scan.py --top 15     # 每类名单最多列 N 只
"""
import os
import sys
import struct
import argparse
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import local_kline  # noqa: E402
try:
    import stock_names  # noqa: E402  名称映射(本地vipdoc无名称), 失败则名单退化为纯代码
    _label = stock_names.label
except Exception:
    _label = lambda code: code  # noqa: E731

# Windows + Git Bash utf-8 输出 (与 fupan.main 一致, 防 emoji/中文崩)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VIPDOC = local_kline.VIPDOC
_REC, _FMT = 32, "<IIIIIfII"


def read_tail(sym, n=25):
    """读本地 .day 尾部 n 根 (含 OHLC+量), 正序。文件不存在/空返回 []。"""
    path = local_kline._day_path(sym)
    if not os.path.exists(path):
        return []
    size = os.path.getsize(path)
    total = size // _REC
    if total == 0:
        return []
    start = max(0, total - n)
    with open(path, "rb") as f:
        f.seek(start * _REC)
        data = f.read((total - start) * _REC)
    rows = []
    for i in range(len(data) // _REC):
        b = data[i * _REC:(i + 1) * _REC]
        d, o, h, l, c, amt, vol, _res = struct.unpack(_FMT, b)
        ds = str(d)
        rows.append({
            "date": f"{ds[0:4]}-{ds[4:6]}-{ds[6:8]}",
            "open": o / 100.0, "high": h / 100.0, "low": l / 100.0, "close": c / 100.0,
            "volume": vol, "amount": amt,
        })
    return rows


def limit_of(bd):
    """板块涨停幅度: 北交所30% / 创业板·科创板20% / 主板10% (未细分ST 5%, ST较少影响有限)。"""
    return 0.30 if bd == "bj" else (0.20 if bd in ("cyb", "kcb") else 0.10)


def scan(target_date=None, top=15):
    zhaban, duanban, shangying, bigdown = [], [], [], []
    date_cnt = Counter()
    for market in ("sh", "sz", "bj"):
        d = os.path.join(VIPDOC, market, "lday")
        if not os.path.isdir(d):
            continue
        for fname in os.listdir(d):
            if not fname.endswith(".day"):
                continue
            sym = fname[:-4]
            bd = local_kline._classify_a_share(sym)
            if bd is None:
                continue
            rows = read_tail(sym, 25)
            if len(rows) < 3:
                continue
            today, prev, pprev = rows[-1], rows[-2], rows[-3]
            date_cnt[today["date"]] += 1
            if target_date and today["date"] != target_date:
                continue
            if prev["close"] <= 0 or pprev["close"] <= 0:
                continue
            code = "".join(ch for ch in sym if ch.isdigit())[-6:]
            limit = limit_of(bd)
            chg = (today["close"] - prev["close"]) / prev["close"]
            high_chg = (today["high"] - prev["close"]) / prev["close"]
            prev_chg = (prev["close"] - pprev["close"]) / pprev["close"]
            # 排除板块指数/除权异常 (单日涨跌超涨停极限, 与 fetch_local_breadth 一致)
            if abs(chg) > limit * 1.05 or abs(prev_chg) > limit * 1.05:
                continue

            # 炸板: 摸涨停未封
            if high_chg >= limit * 0.97 and chg < limit * 0.95:
                zhaban.append((code, bd, round(chg * 100, 2), round(high_chg * 100, 2)))
            # 断板: 昨涨停今跌
            if prev_chg >= limit * 0.97 and chg < 0:
                duanban.append((code, bd, round(chg * 100, 2), round(prev_chg * 100, 2)))
            # 高位放量长上影
            if len(rows) >= 6:
                hi20 = max(r["high"] for r in rows[-20:])
                rng = today["high"] - today["low"]
                upper = today["high"] - max(today["open"], today["close"])
                shadow_ratio = upper / rng if rng > 0 else 0
                avg5v = sum(r["volume"] for r in rows[-6:-1]) / 5
                vr = today["volume"] / avg5v if avg5v > 0 else 0
                if (shadow_ratio > 0.5 and today["close"] >= hi20 * 0.93
                        and vr > 1.3 and today["close"] < today["open"]):
                    shangying.append((code, bd, round(chg * 100, 2), round(vr, 2)))
            # 大跌 (≤-7%)
            if chg <= -0.07:
                bigdown.append((code, bd, round(chg * 100, 2)))

    latest = date_cnt.most_common(1)[0][0] if date_cnt else "?"
    # 跌停近似: ≤-limit*0.97
    dietting = [b for b in bigdown if abs(b[2]) >= (limit_of(b[1]) * 97)]
    return {
        "date": latest, "coverage": date_cnt.get(latest, 0),
        "zhaban": zhaban, "duanban": duanban,
        "shangying": shangying, "bigdown": bigdown,
        "dietting_n": len(dietting),
        "top": top,
    }


def fmt_board(bd):
    return {"main": "主板", "cyb": "创业", "kcb": "科创", "bj": "北交"}.get(bd, bd)


def main():
    ap = argparse.ArgumentParser(description="fupan 第4步失败模式扫描")
    ap.add_argument("--date", default="", help="指定交易日 YYYY-MM-DD, 缺省取最新")
    ap.add_argument("--top", type=int, default=15, help="每类名单最多列 N 只 (默认15)")
    args = ap.parse_args()

    r = scan(target_date=args.date or None, top=args.top)
    print(f"\n========== 失败模式扫描 · {r['date']} (覆盖 {r['coverage']} 只) ==========")
    print(f"炸板 {len(r['zhaban'])} | 断板 {len(r['duanban'])} | "
          f"高位放量长上影 {len(r['shangying'])} | 大跌(≤-7%) {len(r['bigdown'])} "
          f"(其中跌停 {r['dietting_n']})\n")

    # 断板 (最危险: 昨涨停今跌, 追高直接受害者) — 全列
    if r["duanban"]:
        print(f"【断板 {len(r['duanban'])} 只 · 昨涨停今跌 · 追高重灾区】")
        for code, bd, chg, prev_chg in sorted(r["duanban"], key=lambda x: x[2])[:r["top"]]:
            print(f"  {_label(code)} {fmt_board(bd):4} 今{chg:+6.2f}% (昨{prev_chg:+.1f}%涨停)")
        if len(r["duanban"]) > r["top"]:
            print(f"  ... 另有 {len(r['duanban']) - r['top']} 只")
        print()

    # 炸板 (盘中摸板被砸)
    if r["zhaban"]:
        print(f"【炸板 {len(r['zhaban'])} 只 · 盘中触及涨停未封 · 追高/分歧】")
        for code, bd, chg, high_chg in sorted(r["zhaban"], key=lambda x: x[2])[:r["top"]]:
            print(f"  {_label(code)} {fmt_board(bd):4} 收{chg:+6.2f}% (最高{high_chg:+.1f}%)")
        if len(r["zhaban"]) > r["top"]:
            print(f"  ... 另有 {len(r['zhaban']) - r['top']} 只")
        print()

    # 高位放量长上影 (见顶信号)
    if r["shangying"]:
        print(f"【高位放量长上影 {len(r['shangying'])} 只 · 见顶预警】")
        for code, bd, chg, vr in sorted(r["shangying"], key=lambda x: -x[3])[:r["top"]]:
            print(f"  {_label(code)} {fmt_board(bd):4} 收{chg:+6.2f}% 量比{vr:.1f}×")
        if len(r["shangying"]) > r["top"]:
            print(f"  ... 另有 {len(r['shangying']) - r['top']} 只")
        print()

    # 大跌 (环境恶劣信号)
    if r["bigdown"]:
        print(f"【大跌(≤-7%) {len(r['bigdown'])} 只 · 其中跌停≈{r['dietting_n']}】")
        for code, bd, chg, *_ in sorted(r["bigdown"], key=lambda x: x[2])[:r["top"]]:
            print(f"  {_label(code)} {fmt_board(bd):4} {chg:+6.2f}%")
        if len(r["bigdown"]) > r["top"]:
            print(f"  ... 另有 {len(r['bigdown']) - r['top']} 只")


if __name__ == "__main__":
    main()
