# -*- coding: utf-8 -*-
"""fupan 第3步辅助: 扫描当日涨停 + 连板梯队 (连板高度前N), 输出名单 + 客观健康度指标。
数据源: 本地招商证券 vipdoc (scripts/local_kline)。零网络, 永不被封。
用途: fupan 剧本第3步"强势股拆解"的客观数据, 三维度(首板属性/连板健康/分歧节点)由人研判。

判定规则 (基于日K OHLC, lday 不复权, 短期连板不受影响):
  - 涨停: 当日收盘涨幅 ≥ limit*0.97 (主板10%/创业·科创20%/北交30%)
  - 连板高度: 从今日(须涨停)往回数连续涨停天数; 首板=1
  - 一字板: 日内振幅<1% 且 开盘即涨停 (open≥昨收*(1+limit*0.95))
  - 封板强度 seal: 收盘涨幅/limit, 越接近1封板越牢; <0.99=烂板(未封死)
  - 量比 vr: 今日量/前5日均量, 温和放大(1-2)=健康, 爆量(>3)+烂板=不健康

用法:
  python scripts/fupan_strong_scan.py              # 自动取最新交易日
  python scripts/fupan_strong_scan.py --date 2026-07-23
  python scripts/fupan_strong_scan.py --top 12     # 连板股详情最多列 N 只
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

try:
    import pattern_label  # 可选: 连板股追加首板成色 pattern 标签
    _HAS_PATTERN = True
except Exception:
    _HAS_PATTERN = False

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

VIPDOC = local_kline.VIPDOC
_REC, _FMT = 32, "<IIIIIfII"


def read_tail(sym, n=15):
    """读本地 .day 尾部 n 根 (含 OHLC+量), 正序。"""
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
            "volume": vol,
        })
    return rows


def limit_of(bd):
    return 0.30 if bd == "bj" else (0.20 if bd in ("cyb", "kcb") else 0.10)


def fmt_bd(bd):
    return {"main": "主板", "cyb": "创业", "kcb": "科创", "bj": "北交"}.get(bd, bd)


def scan(target_date=None, top=12):
    stocks = []
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
            rows = read_tail(sym, 15)
            if len(rows) < 2:
                continue
            today, prev = rows[-1], rows[-2]
            date_cnt[today["date"]] += 1
            if target_date and today["date"] != target_date:
                continue
            if prev["close"] <= 0:
                continue
            limit = limit_of(bd)
            chg = (today["close"] - prev["close"]) / prev["close"]
            if abs(chg) > limit * 1.05:        # 排除板块指数/除权异常
                continue
            if chg < limit * 0.97:             # 今日未涨停, 跳过
                continue
            # 连板高度: 从倒数第二根往回数连续涨停
            height = 1
            for i in range(len(rows) - 2, 0, -1):
                pc = rows[i - 1]["close"]
                if pc <= 0:
                    break
                if (rows[i]["close"] - pc) / pc >= limit * 0.97:
                    height += 1
                else:
                    break
            # 客观健康度指标
            amp = (today["high"] - today["low"]) / today["low"] if today["low"] > 0 else 0
            yizi = amp < 0.011 and today["open"] >= prev["close"] * (1 + limit * 0.95)
            seal = chg / limit
            avg5v = sum(r["volume"] for r in rows[-6:-1]) / 5 if len(rows) >= 6 else 0
            vr = today["volume"] / avg5v if avg5v > 0 else 0
            code = "".join(ch for ch in sym if ch.isdigit())[-6:]
            stocks.append({
                "code": code, "bd": bd, "sym": sym, "height": height,
                "chg": round(chg * 100, 2), "seal": round(seal, 2),
                "vr": round(vr, 2), "yizi": yizi, "amp": round(amp * 100, 2),
            })
    # 连板股追加首板成色 pattern 标签 (仅前 top 只, 控制 classify_sector 成本)
    if _HAS_PATTERN:
        lian_sorted = sorted([s for s in stocks if s["height"] >= 2],
                             key=lambda x: (-x["height"], -x["chg"]))
        for s in lian_sorted[:top]:
            try:
                s["pattern"] = pattern_label.label(s["sym"], height=s["height"])
            except Exception:
                s["pattern"] = None
    latest = date_cnt.most_common(1)[0][0] if date_cnt else "?"
    return latest, stocks


def main():
    ap = argparse.ArgumentParser(description="fupan 第3步强势股/连板扫描")
    ap.add_argument("--date", default="", help="指定交易日 YYYY-MM-DD, 缺省取最新")
    ap.add_argument("--top", type=int, default=12, help="连板股详情最多列 N 只 (默认12)")
    args = ap.parse_args()

    latest, stocks = scan(args.date or None, args.top)
    ladder = Counter(s["height"] for s in stocks)
    first_board = ladder.get(1, 0)
    lian_total = len(stocks) - first_board
    print(f"\n========== 强势股扫描 · {latest} ==========")
    print(f"今日涨停 {len(stocks)} 只: 首板 {first_board} + 连板 {lian_total}")
    print("\n【连板梯队】(高度 → 只数)")
    for h in sorted(ladder, reverse=True):
        tag = "首板" if h == 1 else f"{h}板"
        print(f"  {tag:6} {ladder[h]} 只")

    lian = [s for s in stocks if s["height"] >= 2]
    lian.sort(key=lambda x: (-x["height"], -x["chg"]))
    if lian:
        print(f"\n【连板股 {len(lian)} 只 · 按高度降序 (拆解候选)】")
        print(f"  {'股票(代码)':<24}{'板':4}{'收盘':7}{'封板':6}{'量比':6}{'振幅':6}备注")
        for s in lian[:args.top]:
            note = []
            if s["yizi"]:
                note.append("一字")
            if s["seal"] < 0.99:
                note.append("烂板")
            if s["vr"] >= 3:
                note.append("爆量")
            elif 0 < s["vr"] < 0.8:
                note.append("缩量")
            print(f"  {_label(s['code']):<24}{s['height']:<4d}{s['chg']:+6.1f}% {s['seal']:.2f}  "
                  f"{s['vr']:5.1f} {s['amp']:5.1f}% {'/'.join(note)}")
        if len(lian) > args.top:
            print(f"  ... 另有 {len(lian) - args.top} 只连板")


if __name__ == "__main__":
    main()
