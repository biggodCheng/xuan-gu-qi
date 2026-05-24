---
name: suolianghuicai
description: 缩量回踩筛选器 — 从涨停股中筛选涨停后缩量回踩的股票。当用户说"缩量回踩"、"缩量回调"、"量能萎缩"、"回调缩量"、"涨停后缩量"时触发。
---

# 缩量回踩筛选器

从涨停股 JSON 文件中，筛选出涨停后出现缩量回踩的股票。

## 使用方式

输入 `/suolianghuicai <zt_json文件路径>` 触发执行。

例如: `/suolianghuicai .claude/skills/chuangxingao/data/zt_2026-05-24.json`

**缺少文件路径时**，自动查找 `.claude/skills/chuangxingao/data/` 下最新的 `zt_*.json` 文件。若无可用文件，提示用户先运行 `/zhangting`。

## 策略选择

执行前，请先询问用户选择以下策略之一：

### 策略1：成交量递减+价格回落
涨停日后，连续N天成交量逐步缩小（每天 < 前一天的80%），且收盘价低于涨停日收盘价。
适合捕捉持续缩量调整的股票。

### 策略2：成交量低于均量+价格回落
涨停日后，某天成交量低于涨停前5日均量的60%，且收盘价低于涨停日收盘价。
适合捕捉突然缩量企稳的股票。

### 策略3：单日缩量回踩
涨停日后，某天成交量低于涨停日成交量的50%，且收盘价低于涨停日收盘价。
适合捕捉快速缩量回调的股票。

## 执行步骤

1. 确认依赖已安装：
   ```bash
   cd .claude/skills/suolianghuicai && pip install -r requirements.txt
   ```

2. 根据用户选择的策略运行：
   ```bash
   cd .claude/skills/suolianghuicai && python main.py <json文件路径> --strategy <1|2|3>
   ```

3. 可选参数：
   - `--shrink-ratio 0.8`（策略1：每天缩量比例，默认0.8）
   - `--min-days 2`（策略1：最少连续缩量天数，默认2）
   - `--ma-days 5`（策略2：均量天数，默认5）
   - `--volume-ratio 0.6`（策略2/3：成交量比例，策略2默认0.6，策略3默认0.5）

4. 脚本会：
   - 读取涨停股 JSON 文件
   - 并发获取每只股票K线数据（含成交量）
   - 按选定策略分析缩量回踩
   - 结果保存到源文件同目录下的 `slhc_<date>.json`

5. 读取输出文件，向用户展示结果摘要：
   - 命中股票数量 / 总输入数量
   - 使用的策略名称和参数
   - 输出文件路径
   - 列出前10只股票（代码、名称、涨停日、回踩天数、缩量比例、当前价）

## 边界条件

| 场景 | 处理方式 |
|------|---------|
| 文件路径不存在 | 提示"文件不存在"，建议先运行 `/zhangting` |
| JSON 格式错误 | 提示"文件格式异常"，展示期望格式 |
| 无命中股票 | 属正常情况，提示"当前策略下无缩量回踩股，可尝试其他策略" |
| API 请求超时 | 脚本有并发重试；若大面积失败，提示重试 |
| 策略参数无效（如 ratio > 1） | 提示"参数不合理"，使用默认值 |

## 流程链

本 skill 位于选股流程的**第三步**（与 `/shizhi` 并列）：
- 上游：`/chuangxingao` → `/zhangting` → 本 skill
- 本 skill 与 `/shizhi` 使用相同的上游（涨停股 JSON）

## 输入格式

接受 `zhangting` 技能输出的 JSON 文件：
```json
{
  "date": "2026-05-24",
  "stocks": [
    {"code": "600563", "name": "法拉电子", "zt_dates": ["2026-05-22"], "zt_pcts": [10.0], "close": 174.2}
  ]
}
```

## 输出格式

```json
{
  "date": "2026-05-24",
  "source": "zt_2026-05-24.json",
  "description": "缩量回踩（策略1：成交量递减+价格回落）",
  "strategy": "shrinking_volume",
  "count": 12,
  "stocks": [
    {
      "code": "600563",
      "name": "法拉电子",
      "last_zt_date": "2026-05-22",
      "last_zt_close": 174.2,
      "last_zt_pct": 10.0,
      "current_close": 165.0,
      "pullback_start_date": "2026-05-23",
      "pullback_days": 3,
      "volume_shrink_ratio": 0.45
    }
  ]
}
```
