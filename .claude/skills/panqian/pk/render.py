# -*- coding: utf-8 -*-
"""报告渲染:盘前外部温度计.md。对齐 fupan render 的 L.append 模式。"""
from datetime import datetime
from pk.mappings import EXPERIENCE_TABLE


def render(d):
    """d: main 组装好的 dict(见 test_render._sample_data 结构)。返回 markdown 字符串。"""
    L = []
    a = L.append
    a(f"# 盘前外部温度计 · {d['date_str']}\n")

    if d.get("critical_missing"):
        a("---")
        a("## ⚠️ 外部信号缺失 · 盘前研判可靠性低")
        a("> 关键维(A50/美股)取数失败,以下数据不完整,研判仅供参考。\n---\n")

    # 第0步 隔夜定调
    a("## 0. 隔夜定调(一句话)")
    a(f"外部环境:**{d['tone']}** | 信号强度:{d['strength']}")
    a("> ⚠️ 这是\"外部环境\"描述,不是\"今天涨跌\"预测。开盘方向由盘口决定,不由此报告定。\n")

    # 第1步 美股
    a("## 1. 美股隔夜(定调)")
    a("| 指数 | 收盘 | 涨跌 |")
    a("|------|------|------|")
    us = d.get("us") or {}
    for it in (us.get("indices") or []):
        a(f"| {it['name']} | {it['price']} | {it['pct']:+.2f}% |")
    if us.get("vix") is not None:
        a(f"| VIX | - | {us['vix']:.1f} |")
    if us.get("indices"):
        nas = next((i for i in us["indices"] if i["name"] == "纳指"), None)
        dow = next((i for i in us["indices"] if i["name"] == "道指"), None)
        if nas and dow:
            struct = "纳指弱于道指(科技抛售)" if nas["pct"] < dow["pct"] else "纳指强于道指"
            a(f"\n结构:{struct}")
        if us.get("vix") and us["vix"] > 20:
            a("｜VIX>20 偏恐慌")

    # 第2步 A50+中概
    a("\n## 2. A50期货 + 中概(A股开盘风向标)")
    a50 = (d.get("a50") or {}).get("a50")
    if a50:
        a(f"A50期货:{a50['price']:.0f}({a50['pct']:+.2f}%) → 历史上对应A股开盘方向参考")
    else:
        a("A50期货:⚠️ 取数失败(关键维,开盘预判可靠性下降)")
    cnr = (d.get("a50") or {}).get("cnr") or []
    if cnr:
        a("热门中概:" + " / ".join(f"{c['name']} {c['pct']:+.1f}%" for c in cnr))

    # 第3步 汇率+大宗
    a("\n## 3. 汇率 + 大宗(板块映射)")
    fx = (d.get("fx") or {}).get("fx") or []
    comm = (d.get("fx") or {}).get("comm") or []
    if fx:
        a("汇率:" + " / ".join(f"{x['name']} {x['pct']:+.2f}%" for x in fx))
    if comm:
        a("大宗:" + " / ".join(f"{x['name']} {x['pct']:+.2f}%" for x in comm))

    # 第4步 新闻
    a("\n## 4. 国际重大事件(昨夜18:00~今晨)")
    news_items = (d.get("news") or {}).get("items") or []
    if news_items:
        for it in news_items:
            star = "★" * it.get("star", 1)
            a(f"- [{star}] {it['title']}({it['source']})")
    else:
        a("- *(自动抓取无结果,见取数质量栏,必要时手动补充)*")
    a("\n> ⚠️ 若有重大突发未抓到(接口被封/漏抓),手动补充在此。")

    # 第5步 历史经验映射
    a("\n## 5. 历史经验映射(经验·非预测)")
    a("| 隔夜信号组合 | 历史经验(静态整理,非回测) |")
    a("|---|---|")
    for row in EXPERIENCE_TABLE:
        a(f"| {row['signal']} | {row['experience']} |")
    a("\n> 经验法则,非今日必然;辅助研判,不据此下单。")

    # 第6步 人工研判 checkpoint
    a("\n## 6. 你的盘前研判 [⛔ CHECKPOINT · 人工填写]")
    a("- 今日最值得警惕的隔夜信号:____")
    a("- 受益/受损板块初判:____")
    a("- 盘前纪律自检:[ ]不赌开盘 [ ]不追高开 [ ]等盘口信号")

    # 取数质量
    q = d.get("quality") or {}
    a("\n## 取数质量")
    a(f"美股{q.get('us','-')}｜A50{q.get('a50','-')}｜中概{q.get('cnr','-')}｜"
      f"汇率{q.get('fx','-')}｜大宗{q.get('comm','-')}｜新闻{q.get('news','-')}")

    if d.get("note"):
        a(f"\n> 备注:{d['note']}")
    a(f"\n---\n*生成于 {datetime.now():%Y-%m-%d %H:%M} | 客观陈列,不预测涨跌,不构成投资建议*")
    return "\n".join(L)
