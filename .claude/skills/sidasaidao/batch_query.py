"""批量查询多只股票的赛道归属"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from screener.fetcher import resolve_stock_code, get_stock_detail
from screener.analyzer import match_tracks, format_result

STOCKS = sys.argv[1].split(",") if len(sys.argv) > 1 else []

results_track = {}  # {赛道名: [股票列表]}
results_none = []

for i, name in enumerate(STOCKS):
    name = name.strip()
    if not name:
        continue
    print(f"[{i+1}/{len(STOCKS)}] 查询: {name} ...", flush=True)

    try:
        code, stock_name = resolve_stock_code(name)
        if not code:
            print(f"  -> 未找到: {name}", flush=True)
            results_none.append({"name": name, "reason": "未找到"})
            continue

        detail = get_stock_detail(code)
        industry = detail.get("industry", "")
        concepts = detail.get("concepts", [])
        actual_name = detail.get("name", stock_name)

        matched = match_tracks(industry, concepts)
        result = format_result(code, actual_name, industry, concepts, matched)

        if matched:
            track_names = [t["track"] for t in matched]
            top_track = matched[0]
            print(f"  -> {actual_name}({code}): {', '.join(track_names)} | 主赛道={top_track['track']}({top_track['confidence']})", flush=True)

            for t in matched:
                tname = t["track"]
                if tname not in results_track:
                    results_track[tname] = []
                results_track[tname].append({
                    "code": code,
                    "name": actual_name,
                    "industry": industry,
                    "confidence": t["confidence"],
                    "matched_keywords": t["matched_keywords"][:8],
                    "sub_categories": t["sub_categories"],
                })
        else:
            print(f"  -> {actual_name}({code}): 不属于四大赛道 [{industry}]", flush=True)
            results_none.append({"code": code, "name": actual_name, "industry": industry})

        time.sleep(0.3)  # 避免请求过快
    except Exception as e:
        print(f"  -> 查询失败: {name} ({e})", flush=True)
        results_none.append({"name": name, "reason": str(e)})

# 输出汇总 JSON
output = {
    "summary": {
        "total": len(STOCKS),
        "matched": sum(len(v) for v in results_track.values()),
        "not_matched": len(results_none),
    },
    "tracks": {k: v for k, v in results_track.items()},
    "not_in_tracks": results_none,
}

output_path = os.path.join(os.path.dirname(__file__), "batch_result.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存: {output_path}", flush=True)
