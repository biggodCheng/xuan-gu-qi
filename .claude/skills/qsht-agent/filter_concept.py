"""从涨停股票中筛选属于指定概念板块的股票。

用法:
    python filter_concept.py <zt_json> [--out out.json]       # 联网查询概念
    python filter_concept.py --reuse <cached_concept_json>    # 复用已缓存概念数据重算

概念方向（区分核心/代理，子串匹配大小写不敏感）:
  - 柔性屏:   核心=柔性屏/柔性显示   代理=柔性电子/OLED
  - 玻璃基板: 核心=玻璃基板          （光伏玻璃/药用玻璃不算）
  - 复合集流体: 核心=复合集流体/复合铜箔/复合铝箔  代理=铜箔
  - 折叠屏:   核心=折叠屏/折叠/UTG
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.dirname(SKILL_DIR)  # .../.claude/skills
SIDA = os.path.join(SKILLS_DIR, "sidasaidao")
sys.path.insert(0, SIDA)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 目标方向 → {core: 核心关键词, proxy: 代理关联关键词}
TARGETS = {
    "柔性屏": {"core": ["柔性屏", "柔性显示", "柔性oled"],
               "proxy": ["柔性电子", "oled"]},
    "玻璃基板": {"core": ["玻璃基板"], "proxy": []},
    "复合集流体": {"core": ["复合集流体", "复合铜箔", "复合铝箔"],
                  "proxy": ["铜箔"]},
    "折叠屏": {"core": ["折叠屏", "折叠", "utg"], "proxy": []},
}


def _hit(concepts, keywords):
    matched = []
    for kw in keywords:
        for c in concepts:
            if kw in c.lower():
                if c not in matched:
                    matched.append(c)
    return matched


def match_targets(concepts):
    """返回 {方向: {"core":[...], "proxy":[...]}} 仅含命中项。"""
    hit = {}
    for d, groups in TARGETS.items():
        core = _hit(concepts, groups["core"])
        proxy = _hit(concepts, groups["proxy"])
        if core or proxy:
            hit[d] = {"core": core, "proxy": proxy}
    return hit


def query_one(stock):
    code = stock["code"]
    try:
        from screener.fetcher import get_stock_detail
        detail = get_stock_detail(code)
        concepts = detail.get("concepts", []) or []
        return {
            "code": code,
            "name": stock.get("name") or detail.get("name", ""),
            "industry": detail.get("industry", ""),
            "concepts": concepts,
            "hit": match_targets(concepts),
        }
    except Exception as e:
        return {"code": code, "name": stock.get("name", ""), "error": str(e),
                "concepts": [], "hit": {}}


def analyze(results):
    """results: list of detail dicts（含 concepts/hit/或需现场计算 hit）。"""
    # 始终基于 concepts 重算 hit（兼容旧缓存的不同 hit 格式）
    for r in results:
        r["hit"] = match_targets(r.get("concepts", []))

    by_direction = {k: [] for k in TARGETS}
    multi = {}
    for r in results:
        for d, levels in r["hit"].items():
            by_direction[d].append({
                "code": r["code"], "name": r.get("name", ""),
                "industry": r.get("industry", ""),
                "core": levels.get("core", []),
                "proxy": levels.get("proxy", []),
            })
        if len(r["hit"]) >= 2:
            multi[r["code"]] = {
                "name": r.get("name", ""),
                "industry": r.get("industry", ""),
                "directions": {d: (r["hit"][d]) for d in r["hit"]},
            }
    return by_direction, multi


def report(by_direction, multi, total):
    print("\n" + "=" * 56, flush=True)
    for d, v in by_direction.items():
        core_only = [x for x in v if x["core"]]
        proxy_only = [x for x in v if not x["core"] and x["proxy"]]
        print(f"\n【{d}】命中 {len(v)} 只（核心 {len(core_only)} / 代理 {len(proxy_only)}）",
              flush=True)
        for x in sorted(core_only, key=lambda i: i["code"]):
            tag = "核心:" + ",".join(x["core"])
            if x["proxy"]:
                tag += " | 关联:" + ",".join(x["proxy"])
            print(f"  ★ {x['name']}({x['code']}) 行业={x['industry']} → {tag}",
                  flush=True)
        for x in sorted(proxy_only, key=lambda i: i["code"]):
            print(f"    {x['name']}({x['code']}) 行业={x['industry']} → 关联:"
                  + ",".join(x["proxy"]), flush=True)

    print(f"\n【同时命中≥2个方向的核心标的】{len(multi)} 只:", flush=True)
    for code, info in multi.items():
        dirs = []
        for d, lv in info["directions"].items():
            parts = []
            if lv.get("core"):
                parts.append("核心:" + ",".join(lv["core"]))
            if lv.get("proxy"):
                parts.append("关联:" + ",".join(lv["proxy"]))
            dirs.append(f"{d}({' / '.join(parts)})")
        print(f"  ★★ {info['name']}({code}) 行业={info['industry']}", flush=True)
        print(f"       → {' ; '.join(dirs)}", flush=True)
    print(f"\n（共扫描 {total} 只涨停股）", flush=True)


def main():
    args = sys.argv[1:]
    reuse = "--reuse" in args
    args = [a for a in args if a != "--reuse"]

    out_path = os.path.join(SKILLS_DIR, "chuangxingao", "data",
                            "zt_concept_filter.json")

    if reuse:
        src = args[0] if args else out_path
        with open(src, "r", encoding="utf-8") as f:
            cached = json.load(f)
        results = cached["all_details"]
        print(f"复用缓存概念数据: {src}（{len(results)} 只）", flush=True)
    else:
        zt_path = args[0] if args else os.path.join(
            SKILLS_DIR, "chuangxingao", "data", "zt_2026-06-15.json")
        with open(zt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        stocks = data["stocks"]
        print(f"共 {len(stocks)} 只涨停股，并发查询概念（20线程）...", flush=True)
        results = []
        with ThreadPoolExecutor(max_workers=20) as ex:
            futs = {ex.submit(query_one, s): s["code"] for s in stocks}
            done = 0
            for fut in as_completed(futs):
                results.append(fut.result())
                done += 1
                if done % 10 == 0:
                    print(f"  已查询 {done}/{len(stocks)}...", flush=True)

    by_direction, multi = analyze(results)
    total = len(results)

    output = {
        "summary": {"total": total,
                    "hit_any": sum(1 for r in results if r.get("hit"))},
        "by_direction": {d: sorted(v, key=lambda x: x["code"])
                         for d, v in by_direction.items()},
        "multi_direction_stocks": multi,
        "all_details": results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    report(by_direction, multi, total)
    print(f"\n结果已保存: {out_path}", flush=True)


if __name__ == "__main__":
    main()
