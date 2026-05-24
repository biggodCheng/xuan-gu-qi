---
name: zhangting
description: 涨停筛选器 — 从创新高股票中筛选最近1个月有涨停（涨幅>=9.5%）的股票
---

# 涨停筛选器

从创新高股票 JSON 文件中，筛选出最近1个月内有涨停（日涨幅 >= 9.5%）的股票。

## 使用方式

输入 `/zhangting <json文件路径>` 触发执行。

例如: `/zhangting .claude/skills/chuangxingao/data/2026-05-24.json`

## 执行步骤

1. 确认依赖已安装：
   ```bash
   cd .claude/skills/zhangting && pip install -r requirements.txt
   ```

2. 运行筛选脚本：
   ```bash
   cd .claude/skills/zhangting && python main.py <json文件路径>
   ```

3. 脚本会：
   - 读取指定的 JSON 文件，提取股票列表
   - 并发获取每只股票最近30个交易日的K线数据（约1-3分钟）
   - 计算每日涨幅，筛选涨幅 >= 9.5% 的股票
   - 结果保存到源文件同目录下的 `zt_<date>.json`

4. 向用户展示结果摘要：涨停股数量、输出文件路径

## 输入格式

接受 `chuangxingao` 技能输出的 JSON 文件：
```json
{
  "date": "2026-05-24",
  "stocks": [
    {"code": "600563", "name": "法拉电子", "close": 174.2, "high_100d": 162.36}
  ]
}
```

## 输出格式

```json
{
  "date": "2026-05-24",
  "source": "2026-05-24.json",
  "description": "最近1个月内有涨停（涨幅>=9.5%）",
  "count": 35,
  "stocks": [
    {
      "code": "600563",
      "name": "法拉电子",
      "zt_dates": ["2026-05-20"],
      "zt_pcts": [9.82],
      "close": 174.2
    }
  ]
}
```
