---
name: renqibang
description: 人气榜 — 抓取东方财富股吧个股人气榜前100(热度榜)，保存人气排名、所属行业、题材(上榜原因)、新晋粉丝%、排名变动到本地JSON。当用户说"人气榜"、"股吧人气"、"热门股人气"、"东方财富人气榜"、"人气排名"、"renqibang"时触发。
---

# 人气榜（东方财富股吧人气榜 Top100）

抓取东方财富股吧个股人气榜 Top100 快照，作为**市场情绪观察参考**。

> ⚠️ 高人气 ≠ 买点。人气榜反映市场关注度，利好出尽时高人气股常兑现下跌。须结合 qsht 选股体系的趋势/回踩/市值/业绩纪律使用，避免追涨。

## 使用方式

输入 `/renqibang` 触发。

## 执行步骤

1. 🔴 CHECKPOINT（运行前检查今日快照是否已存在）:
   ```bash
   ls .claude/skills/renqibang/data/popularity_$(date +%Y-%m-%d).json 2>/dev/null
   ```
   - 已存在 → 🛑 STOP，提示"今日人气榜快照已抓取，重跑会覆盖"，询问确认。
   - 不存在 → 继续。

2. 确认依赖（首次需装 chromium）:
   ```bash
   cd .claude/skills/renqibang && pip install -r requirements.txt && python -m playwright install chromium
   ```

3. 运行:
   ```bash
   cd .claude/skills/renqibang && python main.py
   ```
   > Playwright 会启动 headless chromium 渲染页面（约 10-30 秒）。

4. 脚本会:渲染 `guba.eastmoney.com/rank`（浏览器自动解密人气榜密文）→ 翻页取 Top100 → 并发请求 push2 补行业/题材/名称 → 存 `data/popularity_<date>.json` → 终端打印 Top10 + 行业分布 + 热门题材。

5. 读取 `data/popularity_<date>.json` 或终端摘要向用户展示。

## 实测 DOM 结构（经 probe_rank.py 确认，2026-07-14）

> 榜单页前端改版会导致 selector 失效。失效时重跑 `python probe_rank.py`，按输出更新 `screener/browser.py` 顶部常量。

- RANK_ROW_SELECTOR = `table tbody tr`（每页 20 行，5 页 = 100）
- RANK_CELL_SELECTOR = `td`
- NEXT_PAGE_SELECTOR = `a:has-text('下一页')`（ajax 翻页，URL 不变）
- HOT_TAB_SELECTOR = `""`（默认 tab 即热度榜 .ranktit.hotrank.active）
- 列顺序：td[0]=rank（前3名 DOM 空，用累计序号）、td[1]=rank_change、td[3]=code、td[4]=name（DOM 空，由 push2 补）、td[9]=新晋%/铁杆%

## 字段来源

| 字段 | 来源 |
|---|---|
| 人气排名 rank | 榜单排序（累计序号） |
| 代码 code | 榜单 DOM td[3] |
| 名称 name | **榜单 DOM 为空，由 push2 f58 补** |
| 排名变动 rank_change | 榜单 DOM td[1] |
| 新晋粉丝% popularity | 榜单 DOM td[9]（榜单无独立热度值，热度以排名体现） |
| 所属行业 industry | push2 stock/get `f127` |
| 题材（上榜原因）reason | push2 stock/get `f129`（概念板块） |

## 边界条件

| 触发 | 处理 |
|---|---|
| Playwright/chromium 未装 | 提示 `pip install playwright && python -m playwright install chromium` |
| 非交易日 | 人气榜基于股吧行为仍有数据，正常抓取 |
| 榜单不足 100 | 取实际条数，count 如实显示 |
| 榜单 selector 失效（前端改版） | 报错/数据为空，重跑 probe_rank.py 更新 selector |
| push2 字段为空（部分北交所/新股） | 行业/题材/名称留空，不阻断 |
| 今日快照已存在 | CHECKPOINT 询问是否覆盖 |

## ❌ 不要做

- 不要把高人气当买入信号（高人气≠会涨，常是兑现下跌窗口）
- 不要为"上榜原因"抓股吧帖子+LLM（题材用 push2 f129 轻量获取）
- 不要纯 Python 逆向榜单接口（加密动态派生+改版即失效；用 Playwright 渲染）
- 不要忽略 CHECKPOINT 直接覆盖今日快照

## 局限

- 人气榜是股吧用户行为衍生的热度，不代表基本面
- "上榜原因"=题材概念（f129），是所沾概念，未必是当日催化事件
- popularity 为新晋粉丝%（榜单无独立热度数值，热度以排名体现）
- name 由 push2 f58 补全（榜单 DOM 不渲染名称）
- 仅抓热度榜 Top100 快照，不反映盘中动态
- 依赖 chromium；前端改版可能导致 selector/加密逻辑变化，需维护
