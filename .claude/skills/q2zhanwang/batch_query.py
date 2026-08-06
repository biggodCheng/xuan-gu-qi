"""Q2展望 — 批量查询入口。

用法:
    python batch_query.py <stocks.json>
    python batch_query.py .claude/skills/zhangting/data/zt_2026-06-25.json

读取股票列表(zhangting/chuangxingao 输出的 {date, stocks:[{code,...}]} 或纯列表),
逐只推断 Q2 展望,按 verdict(偏正→中性→偏负)再按净利同比降序,
结果存 data/batch_<date>.json。
"""

import datetime
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from screener.fetcher import get_financial  # noqa: E402
from screener.analyzer import analyze  # noqa: E402

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# verdict 排序权重:偏正最前,数据不足最后
_VERDICT_ORDER = {"偏正": 0, "中性": 1, "偏负": 2, "数据不足": 3}


def run(input_path: str, output_dir: str = _DATA_DIR) -> dict:
    """批量查询,返回汇总结果 dict(同时写盘)。"""
    stocks = _load_stocks(input_path)
    if not stocks:
        print(f"未从 {input_path} 读取到股票,请检查文件格式", flush=True)
        return {"error": "无有效股票", "source": input_path}

    print(f"共 {len(stocks)} 只股票,开始批量推断 Q2 展望...", flush=True)

    results = []
    failed = []
    report_period = ""

    for i, s in enumerate(stocks, 1):
        code = str(s.get("code") or "").strip()
        if not code:
            continue
        fin = get_financial(code)
        if not fin["reports"]:
            failed.append(code)
            _nm = s.get("name")
            print(f"  [{i}/{len(stocks)}] {f'{_nm}({code})' if _nm else code}  ✗ 无财报数据", flush=True)
            continue

        r = analyze(fin)
        if not report_period:
            report_period = r.get("report_period", "")
        results.append({
            "code": r.get("code"),
            "name": r.get("name"),
            "industry": r.get("industry"),
            "verdict": r.get("q2_outlook", {}).get("verdict"),
            "confidence": r.get("q2_outlook", {}).get("confidence"),
            "netprofit_yoy": r.get("q1", {}).get("netprofit_yoy"),
            "revenue_yoy": r.get("q1", {}).get("revenue_yoy"),
            "q2_note": r.get("q2_outlook", {}).get("summary"),
        })
        v = r.get("q2_outlook", {}).get("verdict")
        _nm = r.get("name")
        print(f"  [{i}/{len(stocks)}] {f'{_nm}({code})' if _nm else code}  → {v}", flush=True)

    # 排序:verdict 升序(偏正在前),再按净利同比降序
    results.sort(key=lambda x: (
        _VERDICT_ORDER.get(x.get("verdict"), 9),
        -((x.get("netprofit_yoy") if x.get("netprofit_yoy") is not None else -1e18)),
    ))

    summary = {
        "report_period": report_period,
        "source": os.path.basename(input_path),
        "total": len(stocks),
        "count": len(results),
        "failed": len(failed),
        "failed_codes": failed,
        "stocks": results,
    }

    os.makedirs(output_dir, exist_ok=True)
    date_tag = datetime.date.today().strftime("%Y-%m-%d")
    out_path = os.path.join(output_dir, f"batch_{date_tag}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 分布统计
    from collections import Counter
    dist = Counter(r["verdict"] for r in results)
    print("\n" + "=" * 56, flush=True)
    print(f"完成: 成功 {len(results)} / 失败 {len(failed)} / 共 {len(stocks)}", flush=True)
    dist_str = "  ".join(f"{k} {dist[k]}" for k in
                         ["偏正", "中性", "偏负", "数据不足"] if dist.get(k))
    print(f"分布: {dist_str}", flush=True)
    print(f"输出: {out_path}", flush=True)
    print("=" * 56, flush=True)

    return summary


def _load_stocks(input_path: str) -> list[dict]:
    """读取股票列表,兼容 {stocks:[...]} 和 纯列表 [...]。"""
    try:
        with open(input_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"文件不存在: {input_path}", flush=True)
        return []
    except json.JSONDecodeError as e:
        print(f"JSON 格式错误: {e}", flush=True)
        return []

    if isinstance(data, dict):
        return data.get("stocks", [])
    if isinstance(data, list):
        return data
    return []


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python batch_query.py <stocks.json>", flush=True)
        print("示例:", flush=True)
        print("  python batch_query.py .claude/skills/zhangting/data/zt_2026-06-25.json", flush=True)
        sys.exit(1)

    run(sys.argv[1])
