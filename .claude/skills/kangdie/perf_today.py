"""一次性：07-16/17/24/28 四批抗跌种子 截至 2026-07-30 的表现 + 今日单日涨跌。
读 track_history.json(累计/窗口) + 拉本地K线算今日单日。纯文本输出(避GBK emoji坑)。
"""
import json, os, sys, statistics
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from screener.fetcher import get_stock_kline

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = json.load(open(os.path.join(HERE, "data", "track_history.json"), encoding="utf-8"))
BATCHES = ["2026-07-16", "2026-07-17", "2026-07-24", "2026-07-28"]
AS_OF = HIST.get("as_of", "?")

events = [e for e in HIST["events"] if e["drop_date"] in BATCHES and e.get("end_ret") is not None]

# ---- 今日单日涨跌(去重股票) ----
codes = sorted({e["code"] for e in events})
today_map = {}
def fetch_today(code):
    bars = get_stock_kline(code, 4)
    if len(bars) < 2:
        return code, None, None, None
    c1, c0 = bars[-1]["close"], bars[-2]["close"]
    if c0 <= 0:
        return code, None, bars[-1]["day"], bars[-2]["day"]
    return code, round((c1 / c0 - 1) * 100, 2), bars[-1]["day"], bars[-2]["day"]
with ThreadPoolExecutor(max_workers=20) as ex:
    for code, chg, d1, d0 in ex.map(fetch_today, codes):
        today_map[code] = (chg, d1, d0)

# 确认最新交易日 (today_map[code] = (chg, 最新日, 前日))
latest_day = max((v[1] for v in today_map.values() if v[1]), default="?")
prev_day = max((v[2] for v in today_map.values() if v[2] and v[1] == latest_day), default="?")

def avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None
def median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None
def winrate(xs):
    pos = sum(1 for x in xs if x is not None and x > 0)
    n = sum(1 for x in xs if x is not None)
    return f"{pos}/{n}({round(pos/n*100) if n else 0}%)" if n else "—"

# ---- 分批统计 ----
print(f"===== 四批抗跌种子表现（截至 {AS_OF}，最新交易日 {latest_day} vs {prev_day}）=====")
print(f"{'批次':<10}{'N':>4}{'去重':>5}{'今日均':>8}{'今日胜':>10}{'累计均':>8}{'累计胜':>10}{'D+5':>7}{'D+10':>7}{'D+20':>7}{'MFE':>7}{'MAE':>7}{'首反':>9}")
overall_today, overall_end = [], []
for b in BATCHES:
    evs = [e for e in events if e["drop_date"] == b]
    codes_b = {e["code"] for e in evs}
    today_b = [today_map[c][0] for c in codes_b if today_map.get(c, (None,))[0] is not None]
    end_b = [e["end_ret"] for e in evs]
    d5 = [e.get("d5") for e in evs]; d10 = [e.get("d10") for e in evs]; d20 = [e.get("d20") for e in evs]
    mfe = [e.get("mfe") for e in evs]; mae = [e.get("mae") for e in evs]
    fr = [e.get("first_rebound") for e in evs]
    fr_hit = sum(1 for x in fr if x is True); fr_n = sum(1 for x in fr if x is not None)
    overall_today += today_b
    overall_end += end_b
    print(f"{b:<10}{len(evs):>4}{len(codes_b):>5}{avg(today_b)!s:>8}{winrate(today_b):>10}{avg(end_b)!s:>8}{winrate(end_b):>10}"
          f"{avg(d5)!s:>7}{avg(d10)!s:>7}{avg(d20)!s:>7}{avg(mfe)!s:>7}{avg(mae)!s:>7}{f'{fr_hit}/{fr_n}':>9}")
codes_all = {e["code"] for e in events}
print(f"{'ALL':<10}{len(events):>4}{len(codes_all):>5}{avg(overall_today)!s:>8}{winrate(overall_today):>10}{avg(overall_end)!s:>8}{winrate(overall_end):>10}")

# ---- 今日单日明细(去重) ----
rows = []
seen = set()
for e in events:
    c = e["code"]
    if c in seen:
        continue
    seen.add(c)
    t = today_map.get(c, (None,))[0]
    rows.append((c, e.get("name", ""), e["drop_date"], t, e.get("end_ret"), e.get("d5"), e.get("d10")))
rows_today = sorted([r for r in rows if r[3] is not None], key=lambda r: r[3])

print("\n===== 今日单日最抗跌 Top15（去重股）=====")
print(f"{'code':<8}{'name':<10}{'最早批':<12}{'今日%':>8}{'累计%':>8}{'D+5':>7}{'D+10':>7}")
for r in rows_today[-15:][::-1]:
    print(f"{r[0]:<8}{r[1]:<10}{r[2]:<12}{r[3]!s:>8}{r[4]!s:>8}{r[5]!s:>7}{r[6]!s:>7}")
print("\n===== 今日单日最补跌 Bottom15（去重股）=====")
for r in rows_today[:15]:
    print(f"{r[0]:<8}{r[1]:<10}{r[2]:<12}{r[3]!s:>8}{r[4]!s:>8}{r[5]!s:>7}{r[6]!s:>7}")

# ---- 累计末值明细(去重) ----
rows_end = sorted([r for r in rows if r[4] is not None], key=lambda r: r[4])
print("\n===== 累计末值最佳 Top10（相对各批D收盘，去重取最早批次）=====")
for r in rows_end[-10:][::-1]:
    print(f"{r[0]:<8}{r[1]:<10}{r[2]:<12}{'今日':>6}{r[3]!s:>8}{'累计':>6}{r[4]!s:>8}")
print("\n===== 累计末值最差 Bottom10 =====")
for r in rows_end[:10]:
    print(f"{r[0]:<8}{r[1]:<10}{r[2]:<12}{'今日':>6}{r[3]!s:>8}{'累计':>6}{r[4]!s:>8}")
