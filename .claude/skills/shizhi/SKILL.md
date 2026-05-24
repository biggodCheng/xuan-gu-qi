---
name: shizhi
description: 市值筛选器 — 从涨停股中筛选市值小于指定阈值的股票
---

# 市值筛选器

从涨停股 JSON 文件中，筛选出市值小于指定阈值（默认200亿）的股票。

## 使用方式

输入 `/shizhi <zt_json文件路径>` 触发执行。

例如: `/shizhi .claude/skills/chuangxingao/data/zt_2026-05-24.json`

## 执行步骤

1. 确认依赖已安装：
   ```bash
   cd .claude/skills/shizhi && pip install -r requirements.txt
   ```

2. 运行筛选：
   ```bash
   cd .claude/skills/shizhi && python main.py <json文件路径>
   ```

3. 可选参数：
   - `--threshold 200`（市值上限，单位：亿，默认200）

4. 脚本会：
   - 读取涨停股 JSON 文件
   - 通过新浪财经 API 分页获取全市场市值数据
   - 过滤市值 < 阈值的股票，按市值升序排列
   - 结果保存到 `shizhi/data/sz_<date>.json`

5. 向用户展示结果摘要：命中股票数量、市值范围、输出文件路径

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
  "description": "涨停股中市值小于200亿的股票",
  "threshold_yi": 200,
  "total_input": 184,
  "count": 120,
  "stocks": [
    {
      "code": "600303",
      "name": "曙光股份",
      "close": 3.83,
      "market_cap_yi": 5.42
    }
  ]
}
```
