# -*- coding: utf-8 -*-
"""开发期探查:打印各候选接口真实返回,据此校准 parser 字段索引。
用法: python .claude/skills/panqian/probes/probe_all.py [us|a50|fx|news|all]
"""
import sys, os, json as _json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Windows GBK 控制台无法编码 ⚠️ 等 emoji,统一切 UTF-8 输出(仅 probe 脚本)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from pk import base
from pk.config import (
    US_INDICES, US_VIX, A50_CODE, A50_BACKUP, CNR_DRAGON, CNR_STOCKS,
    FX, COMMODITY,
)

CLS_URL = ("https://www.cls.cn/nodeapi/updateTelegraphList?"
           "app=CailianpressWeb&category=&lastTime=&os=web&sv=7.7.5&rn=50")


def probe_us():
    codes = [c for c, _ in US_INDICES] + [US_VIX[0]]
    print("=== 美股+VIX probe ===")
    print("请求:", ",".join(codes))
    out = base.sina_quote(codes)
    for code, fields in out.items():
        print(f"\n[{code}] 字段数={len(fields)}")
        for i, f in enumerate(fields):
            print(f"  [{i}] {f!r}")
    if not out:
        print("⚠️ 新浪美股全失败 → 后续用 Yahoo ^IXIC/^GSPC/^DJI/^VIX(代理7897)替代")


def probe_a50():
    codes = [A50_CODE[0], A50_BACKUP[0], CNR_DRAGON[0]] + [c for c, _ in CNR_STOCKS]
    print("\n=== A50+中概 probe ===")
    print("请求:", ",".join(codes))
    out = base.sina_quote(codes)
    for code, fields in out.items():
        print(f"\n[{code}] 字段数={len(fields)}")
        for i, f in enumerate(fields[:15]):   # hf_ name 在 [13],打印到 15
            print(f"  [{i}] {f!r}")
    # A50 pct 自算验证(hf_ 无 pct 字段:[0]价 [3]昨收)
    af = out.get(A50_CODE[0], [])
    if len(af) > 3:
        try:
            price, prev = float(af[0]), float(af[3])
            if prev > 0:
                print(f"   A50 pct 自算: ({price}-{prev})/{prev}*100 = {(price-prev)/prev*100:+.4f}%")
        except ValueError:
            pass
    if A50_CODE[0] not in out or not out[A50_CODE[0]]:
        print(f"⚠️ A50 主代码({A50_CODE[0]}) 取数失败 — 尝试备份 {A50_BACKUP[0]}")
        bf = out.get(A50_BACKUP[0], [])
        if not bf:
            print(f"⚠️ A50 备份({A50_BACKUP[0]}) 亦失败 — A50 是关键维,失败需报告顶部明示盲区")


def probe_fx():
    codes = [c for c, _ in FX] + [c for c, _ in COMMODITY]
    print("\n=== 汇率+大宗 probe ===")
    print("请求:", ",".join(codes))
    out = base.sina_quote(codes)
    for code, fields in out.items():
        print(f"\n[{code}] 字段数={len(fields)}")
        for i, f in enumerate(fields[:15]):
            print(f"  [{i}] {f!r}")
    # 大宗 pct 自算验证(hf_ 无 pct:[0]价 [3]昨收)
    for code, name in COMMODITY:
        f = out.get(code, [])
        if len(f) > 3:
            try:
                price, prev = float(f[0]), float(f[3])
                if prev > 0:
                    print(f"   {name}({code}) pct 自算: ({price}-{prev})/{prev}*100 = {(price-prev)/prev*100:+.4f}%")
            except ValueError:
                pass
    if not out:
        print("⚠️ 新浪汇率+大宗全失败 — 非关键维,失败时该项空不阻断")


def probe_news():
    print("\n=== 新闻 probe(财联社/金十/新华) ===")
    # 财联社:task 给的 nodeapi/updateTelegraphList 已下线;测替代 endpoint
    cls_candidates = [
        CLS_URL,
        "https://www.cls.cn/v1/roll/get_roll_list?app=CailianpressWeb&category=&lastTime=&os=web&sv=7.7.5&rn=5",
        "https://www.cls.cn/v3/depth/home/assembled/1000",
        "https://www.cls.cn/v5/telegraph/lastest?app=CailianpressWeb&rn=5",
    ]
    cls_ok = False
    for url in cls_candidates:
        try:
            r = base.sess.get(url, timeout=15,
                              headers={"Referer": "https://www.cls.cn/telegraph",
                                       "User-Agent": "Mozilla/5.0"})
            ct = r.headers.get("Content-Type", "")
            print(f"[财联社试] {r.status_code} ct={ct} url={url[:80]}")
            if "json" in ct and r.status_code == 200:
                j = r.json()
                print(f"   顶层keys={list(j.keys())} 样例={_json.dumps(j, ensure_ascii=False)[:200]}")
                _data = j.get("data")
                if isinstance(_data, dict):
                    items = _data.get("roll_data", [])
                elif isinstance(_data, list):
                    items = _data
                else:
                    items = []
                if items:
                    print(f"   ✓ 拿到 {len(items)} 条,首条字段: {list(items[0].keys())}")
                    cls_ok = True
                    break
        except Exception as e:
            print(f"[财联社试] 异常: {e}")
    if not cls_ok:
        print("[财联社] ✗ 所有 endpoint 失败(404/签名错误 10012)→ fixture 存空 roll_data,parser 降级返回 []")

    # 金十:财经日历 API 需 sign,直连不可达
    print("\n[金十] 反爬强,直连 https://www.jin10.com/ 返回 HTML(数据由 JS 动态拉取 + sign),")
    print("       数据 API cdn.jin10.com/data_center/* 需 sign → fixture 存 {\"items\": []}")

    # 新华:RSS 通但无 pubDate → 时间窗无法过滤
    print("\n[新华] xinhuanet.com/*/news_*.xml RSS 可达(200,300 条),但 item 无 pubDate 字段,")
    print("       时间窗(昨夜 18:00~今晨)无法过滤 → 视同不可用,fixture 存 {\"items\": []}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("us", "all"):
        probe_us()
    if which in ("a50", "all"):
        probe_a50()
    if which in ("fx", "all"):
        probe_fx()
    if which in ("news", "all"):
        probe_news()
