---
name: qibao
description: 起爆点筛选器 — 从创新高股中筛选放量起爆的股票（突破布林上轨+倍量+MACD水上金叉），并标注是否兼蓄势。当用户说"起爆"、"起爆点"、"放量突破"、"主力起爆"、"突破布林"时触发。
---

# 起爆点筛选器

从创新高股 JSON 中，筛选出最近一个交易日"放量起爆"的股票。忠实翻译通达信"主力监测系统"公式，因数据源无 L2 大单资金流，蓄势改用"横盘+放量阳线"近似。

## 使用方式

输入 `/qibao <chuangxingao_json路径>` 触发执行。

例如：`/qibao .claude/skills/chuangxingao/data/2026-06-29.json`

**缺少文件路径时**，自动查找 `.claude/skills/chuangxingao/data/` 下最新的 `{date}.json`。若无可用文件，提示用户先运行 `/chuangxingao`。

## 信号定义

**起爆（核心信号，输出条件）**
- B1 收盘上穿布林上轨（MA20+2σ）
- B2 倍量：当日量 > 前5日最高量 × 2
- B3 MACD 水上多头状态：DIF > DEA 且 DIF > 0

**蓄势（兼蓄势标注）**
- A1 起爆前 20 日振幅 < 15%（横盘）
- A2 当日放量阳线：量 > MA(量,5)×1.5 且收阳

起爆命中即输出；同时满足蓄势则 `signals` 追加"兼蓄势"（蓄势充分的真突破）。

## 执行步骤

1. 确认依赖：
   ```bash
   cd .claude/skills/qibao && pip install -r requirements.txt
   ```

2. 🔴 CHECKPOINT：确认输入文件存在且为 chuangxingao 输出格式（含 `date` 与 `stocks[].code/name`）。缺失则提示先运行 `/chuangxingao`。

3. 运行：
   ```bash
   cd .claude/skills/qibao && python main.py <json文件路径>
   ```
   可选：`--days 120`（K线天数）。

4. 脚本会：读取创新高股 → 并发获取 OHLCV K线（20线程）→ 计算指标 → 筛选起爆 → 保存 `qibao/data/qb_{date}.json`。

5. 读取输出，展示摘要：起爆数量、其中兼蓄势数量、逐只（代码/名称/涨幅/量比/信号）。

## 边界条件

| 场景 | 处理方式 |
|------|---------|
| 输入文件不存在 | 提示"文件不存在"，建议先运行 `/chuangxingao` |
| 历史不足 40 日 | 跳过该股票，汇总打印跳过数量 |
| 腾讯 API 残缺/失败 | 自动回退新浪 API（腾讯/新浪均直连禁代理 `NO_PROXY=*`，走代理会被关连接） |
| 无起爆股 | 属正常，提示"今日无起爆信号" |

## ❌ 反例

| 不要 | 原因 | 正确做法 |
|---|---|---|
| 把"仅蓄势未起爆"当作信号输出 | 蓄势是状态不是买点 | 只输出起爆股，蓄势仅作兼蓄势标注 |
| 期望 L2 大单资金流 | 数据源只有日 OHLCV | 蓄势用横盘+放量阳线近似 |

## 流程链

- 上游：`/chuangxingao`（创新高股）
- 下游：`/qsht-agent` 选股流水线（作为创新高之后的派生步骤）

## 输入格式

```json
{
  "date": "2026-06-29",
  "stocks": [{"code": "600563", "name": "法拉电子", "close": 174.2}]
}
```

## 输出格式

```json
{
  "date": "2026-06-29",
  "source": "2026-06-29.json",
  "description": "起爆=突破布林上轨+倍量+MACD水上金叉；蓄势=横盘+放量阳线(无L2资金流)",
  "count": 1,
  "stocks": [
    {"code": "600563", "name": "法拉电子", "close": 174.2, "pct_chg": 8.5,
     "vol_ratio": 2.3, "boll_breakout": true, "macd_above_zero": true,
     "xushi": true, "signals": ["起爆", "兼蓄势"]}
  ]
}
```
