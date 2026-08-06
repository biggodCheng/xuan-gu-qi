"""D+N 专项：抗跌日 D 收盘买入、持有满 N 个交易日的收益/胜率。不满 N 日的批次自动排除。
自己拉本地 K 线算(不依赖 track_history 窗口字段)，创业板基准对照。纯文本输出。
用法: python perf_window.py [N]   (默认 3)
"""
import json, os, sys, statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screener.fetcher import get_stock_kline, get_index_kline
from screener.track_analyzer import align_after, window_return

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOW = int(sys.argv[1]) if len(sys.argv) > 1 else 3
# 全部批次; 不满 N 日的自动算出 None 被排除
BATCHES = ["2026-07-16", "2026-07-17", "2026-07-24", "2026-07-28", "2026-07-30"]

events = []
for b in BATCHES:
    p = os.path.join(HERE, "data", f"kd_{b}.json")
    if not os.path.exists(p):
        continue
    kd = json.load(open(p, encoding="utf-8"))
    for s in kd.get("stocks", []):
        events.append({"drop_date": b, "code": s["code"], "name": s.get("name", "")})

def calc(e):
    bars = get_stock_kline(e["code"], 40)
    al = align_after(bars, e["drop_date"]) if bars else None
    e["ret"] = window_return(al[0], al[1], WINDOW) if al else None
    return e
with ThreadPoolExecutor(max_workers=20) as ex:
    events = list(ex.map(calc, events))

valid = [e for e in events if e["ret"] is not None]
excluded = sorted({b for b in BATCHES if os.path.exists(os.path.join(HERE, "data", f"kd_{b}.json"))}
                  - {e["drop_date"] for e in valid})
by = defaultdict(list)
for e in valid:
    by[e["drop_date"]].append(e)

idx = get_index_kline("sz399006", 60)
def idx_dN(d):
    al = align_after(idx, d)
    return window_return(al[0], al[1], WINDOW) if al else None

def stat(evs):
    v = [e["ret"] for e in evs]
    n = len(v); pos = sum(1 for x in v if x > 0)
    return (n, round(sum(v)/n, 2), round(statistics.median(v), 2),
            f"{pos}/{n}({round(pos/n*100)}%)", round(max(v), 2), round(min(v), 2))

idx_header = f"创业板D+{WINDOW}"
print(f"===== D+{WINDOW} 收益（抗跌日 D 收盘买入，持有满 {WINDOW} 个交易日）=====")
print(f"已排除不满 {WINDOW} 交易日的批次: {excluded if excluded else '无'}")
print(f"{'批次':<12}{'N':>4}{'均值':>8}{'中位':>8}{'胜率(>0)':>12}{'最大':>8}{'最小':>8}{idx_header:>11}{'跑赢大盘':>10}")
tot = []
for b in sorted(by):
    n, av, md, wr, mx, mn = stat(by[b])
    ix = idx_dN(b)
    ix_s = f"{ix}%" if ix is not None else "—"
    beat_s = f"{round(av-ix,2)}%" if ix is not None else "—"
    print(f"{b:<12}{n:>4}{av:>8}{md:>8}{wr:>12}{mx:>8}{mn:>8}{ix_s:>11}{beat_s:>10}")
    tot += by[b]
n, av, md, wr, mx, mn = stat(tot)
ix_all = [x for x in (idx_dN(b) for b in sorted(by)) if x is not None]
ix_avg = round(sum(ix_all)/len(ix_all), 2) if ix_all else None
ix_avg_s = f"{ix_avg}%" if ix_avg is not None else "—"
beat_avg_s = f"{round(av-ix_avg,2)}%" if ix_avg is not None else "—"
print(f"{'合计':<12}{n:>4}{av:>8}{md:>8}{wr:>12}{mx:>8}{mn:>8}{ix_avg_s:>11}{beat_avg_s:>10}")

v = [e["ret"] for e in valid]
buckets = [("涨 >0%", lambda x: x > 0), ("小跌 0~-5%", lambda x: -5 <= x <= 0),
           ("中跌 -5~-10%", lambda x: -10 < x < -5), ("大跌 ≤-10%", lambda x: x <= -10)]
print("\n分布:")
for label, fn in buckets:
    c = sum(1 for x in v if fn(x))
    print(f"  {label:<14} {c} 只 ({round(c/len(v)*100)}%)")

rows = sorted(valid, key=lambda e: e["ret"])
ret_header = f"D+{WINDOW}%"
print(f"\nD+{WINDOW} 最佳 Top10:")
print(f"  {'code':<8}{'name':<10}{'批次':<12}{ret_header:>8}")
for e in rows[-10:][::-1]:
    print(f"  {e['code']:<8}{e.get('name',''):<10}{e['drop_date']:<12}{e['ret']:>8}")
print(f"\nD+{WINDOW} 最差 Bottom10:")
for e in rows[:10]:
    print(f"  {e['code']:<8}{e.get('name',''):<10}{e['drop_date']:<12}{e['ret']:>8}")
