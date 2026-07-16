"""大盘环境扫描 — qsht-agent 第 0 步。

拉取主要指数(上证/沪深300/创业板)近 150 日 K 线，计算回撤、均线位置、
量能、近期涨跌，输出环境判断(高位回调/超跌/震荡)，结果写 output/market_env.json
供 main.py 嵌入主报告开头。独立可运行: python market_env.py
"""
import json
import os

import requests

for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"

session = requests.Session()
session.trust_env = False

_HERE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(_HERE, "output")

INDEXES = {
    "上证指数": "sh000001",
    "沪深300": "sh000300",
    "创业板指": "sz399006",
}


def fetch(symbol: str, n: int = 150) -> list[dict]:
    """新浪 K 线(原生支持指数代码)。"""
    url = (
        "https://money.finance.sina.com.cn/quotes_service/api/"
        "json_v2.php/CN_MarketData.getKLineData"
    )
    params = {"symbol": symbol, "scale": 240, "ma": "no", "datalen": n}
    r = session.get(url, params=params, timeout=15)
    data = r.json()
    if not data:
        return []
    return [
        {
            "date": d["day"],
            "close": float(d["close"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "vol": float(d["volume"]),
        }
        for d in data
    ]


def analyze(name: str, sym: str) -> dict | None:
    kl = fetch(sym)
    if not kl:
        return None
    last = kl[-1]
    closes = [k["close"] for k in kl]
    vols = [k["vol"] for k in kl]
    high120 = max(k["high"] for k in kl)
    low120 = min(k["low"] for k in kl)
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    cur = last["close"]
    dd120 = (cur - high120) / high120 * 100
    pos120 = (cur - low120) / (high120 - low120) * 100 if high120 != low120 else 50
    chg = (cur - closes[-2]) / closes[-2] * 100
    ret5 = (cur - closes[-6]) / closes[-6] * 100 if len(closes) >= 6 else 0.0
    ret20 = (cur - closes[-21]) / closes[-21] * 100 if len(closes) >= 21 else 0.0
    vol5 = sum(vols[-5:]) / 5
    vol20 = sum(vols[-20:]) / 20
    vol_ratio = vol5 / vol20 if vol20 else 0
    return {
        "name": name,
        "symbol": sym,
        "date": last["date"],
        "close": round(cur, 2),
        "chg_pct": round(chg, 2),
        "dd120": round(dd120, 1),
        "pos120": round(pos120, 0),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "below_ma20": cur < ma20,
        "below_ma60": cur < ma60,
        "ret5": round(ret5, 1),
        "ret20": round(ret20, 1),
        "vol_ratio": round(vol_ratio, 2),
    }


def env_summary(idxs: list[dict]) -> tuple[str, str]:
    """根据指数指标给环境判断，返回 (summary 文字, regime 枚举)。

    regime 取值: missing / oversold / pullback / weak / neutral_strong / neutral。
    weak|oversold|pullback 为偏弱态，qsht-agent 据此触发空仓警示。
    """
    if not idxs:
        return "数据缺失", "missing"
    avg_dd = sum(i["dd120"] for i in idxs) / len(idxs)
    all_ret20_pos = all(i["ret20"] > 0 for i in idxs)
    all_ret5_neg = all(i["ret5"] < 0 for i in idxs)
    all_below = all(i["below_ma20"] and i["below_ma60"] for i in idxs)
    if avg_dd <= -15:
        return f"超跌态(均回撤{avg_dd:.0f}%)，留意阶段底部信号", "oversold"
    if all_ret20_pos and all_ret5_neg:
        return "高位回调态：20日仍正但5日急跌，非阶段见底", "pullback"
    if all_below and all_ret5_neg:
        return "弱势下行：三大指数跌破MA20/60且短期续跌", "weak"
    if all(i["ret20"] > 0 for i in idxs):
        return "震荡偏强：20日仍正，短期分化", "neutral_strong"
    return "震荡分化", "neutral"


def main():
    idxs = []
    for name, sym in INDEXES.items():
        m = analyze(name, sym)
        if m:
            idxs.append(m)
            ma_tag = ("↓MA20 " if m["below_ma20"] else "↑MA20 ") + (
                "↓MA60" if m["below_ma60"] else "↑MA60"
            )
            print(
                f"  {name} {m['date']} 收{m['close']} ({m['chg_pct']:+.2f}%) | "
                f"120日回撤{m['dd120']:.1f}% 位置{m['pos120']:.0f}% | {ma_tag} | "
                f"5日{m['ret5']:+.1f}% 20日{m['ret20']:+.1f}%"
            )
    summary, regime = env_summary(idxs)
    print(f"  → {summary} [regime={regime}]")

    out = {
        "as_of": (idxs[0]["date"] if idxs else None),
        "indexes": idxs,
        "summary": summary,
        "regime": regime,
    }
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "market_env.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"  大盘环境快照: {path}")
    return out


if __name__ == "__main__":
    main()
