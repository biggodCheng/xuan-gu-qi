---
name: chuangxingao
description: A股创新高选股器 — 筛选当日收盘价创100个交易日新高的股票，结果保存为 JSON
---

# 创新高选股器

A股收盘后筛选创100个交易日新高的股票。

## 使用方式

输入 `/chuangxingao` 触发执行。

## 执行步骤

1. 确认依赖已安装：
   ```bash
   cd .claude/skills/chuangxingao && pip install -r requirements.txt
   ```

2. 运行选股脚本：
   ```bash
   cd .claude/skills/chuangxingao && python main.py
   ```

3. 脚本会：
   - 获取全 A 股当日行情
   - 逐个获取历史数据（约 10-20 分钟）
   - 计算哪些股票创100日新高
   - 结果保存到 `data/YYYY-MM-DD.json`

4. 向用户展示结果摘要：创新高股票数量、输出文件路径

## 非交易日

如果当天没有行情数据（周末、节假日），脚本会提示"未获取到行情数据，可能是非交易日"。

## 输出格式

```json
{
  "date": "2026-05-22",
  "description": "A股当日收盘价创100个交易日新高",
  "count": 42,
  "stocks": [
    {"code": "000001", "name": "平安银行", "close": 15.23, "high_100d": 15.10}
  ]
}
```
