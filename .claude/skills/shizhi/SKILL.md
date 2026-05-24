---
name: shizhi
description: 市值筛选器 — 从涨停股中筛选市值小于指定阈值的股票。当用户说"筛小盘股"、"市值小于X亿"、"低市值"、"流通盘小"、"找小票"时触发。
---

# 市值筛选器

从涨停股 JSON 文件中，筛选出市值小于指定阈值（默认200亿）的股票。

## 使用方式

输入 `/shizhi <zt_json文件路径>` 触发执行。

例如: `/shizhi .claude/skills/chuangxingao/data/zt_2026-05-24.json`

**缺少文件路径时**，自动查找 `.claude/skills/chuangxingao/data/` 下最新的 `zt_*.json` 文件。若无可用文件，提示用户先运行 `/zhangting`。

## 执行步骤

1. 确认依赖已安装：
   ```bash
   cd .claude/skills/shizhi && pip install -r requirements.txt
   ```

2. 如果用户指定了阈值（如"50亿以下"），使用该值；否则使用默认值200亿。

3. 运行筛选：
   ```bash
   cd .claude/skills/shizhi && python main.py <json文件路径> --threshold <阈值>
   ```

4. 脚本会：
   - 读取涨停股 JSON 文件
   - 通过新浪财经 API 分页获取全市场市值数据
   - 过滤市值 < 阈值的股票，按市值升序排列
   - 结果保存到 `shizhi/data/sz_<date>.json`

5. 读取输出文件，向用户展示结果摘要：
   - 命中股票数量 / 总输入数量
   - 市值范围（最小 ~ 最大）
   - 输出文件路径
   - 列出前10只股票（代码、名称、市值）

## 边界条件

| 场景 | 处理方式 |
|------|---------|
| 文件路径不存在 | 提示"文件不存在"，建议先运行 `/zhangting` |
| JSON 格式错误 | 提示"文件格式异常"，展示期望格式 |
| API 请求失败 | 提示"市值数据获取失败，请稍后重试" |
| 结果为空 | 提示"当前阈值下无命中，可尝试调高阈值" |
| 阈值为0或负数 | 提示"阈值必须为正数"，使用默认值200 |

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
