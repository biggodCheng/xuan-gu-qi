# suolianghuicai (缩量回踩筛选器) 设计文档

## Context

项目已有 chuangxingao（创新高选股）和 zhangting（涨停筛选）两个 skill，形成了 "创新高 → 涨停" 的选股流水线。用户需要在涨停股中进一步筛选出"缩量回踩"的股票——即涨停后成交量萎缩、价格回调的股票，这类股票通常被认为后续可能有再次上涨的机会。

## 数据流

```
zt_2026-05-24.json (输入，来自 zhangting skill)
  → 提取股票列表 + 最后涨停日
  → 并发获取K线数据（含 volume 字段）
  → 按用户选择的策略分析缩量回踩
  → slhc_2026-05-24.json (输出，保存在输入文件同目录)
```

## 文件结构

```
.claude/skills/suolianghuicai/
├── SKILL.md              # 技能描述、使用方式、策略选择交互
├── main.py               # 入口：参数解析、编排流程
├── screener/
│   ├── __init__.py
│   ├── fetcher.py        # 新浪API获取K线，返回 {date, close, volume}
│   ├── analyzer.py       # 三种缩量回踩策略 + 筛选入口
│   └── storage.py        # 读取输入JSON + 保存结果JSON
└── requirements.txt      # requests
```

## K线数据获取 (fetcher.py)

- 复用 zhangting 的新浪财经 API（`CN_MarketData.getKLineData`）
- API 返回的 JSON 中本身包含 `volume` 字段，直接解析
- 返回格式：`[{date: str, close: float, volume: float}, ...]` 按日期正序
- 获取天数：需要覆盖从最后一次涨停日到当前日期，默认获取 30 天 K 线

## 三种缩量回踩策略 (analyzer.py)

### 策略1 - 成交量递减 + 价格回落 (`shrinking_volume`)

在最后一次涨停日之后，检查连续交易日是否出现成交量逐步缩小且价格低于涨停日收盘价。

- 条件：存在连续 N 天（默认 >= 2 天），每天成交量 < 前一天的 `shrink_ratio`（默认 0.8）
- 同时这些天的收盘价均低于涨停日收盘价
- 参数：`shrink_ratio`（默认 0.8，即每天缩量 20% 以上）

### 策略2 - 成交量低于均量 + 价格回落 (`below_average`)

以涨停日前 N 天的平均成交量为基准，检查涨停后是否有交易日成交量显著低于该基准。

- 计算涨停日前 `ma_days` 天（默认 5 天）的平均成交量
- 条件：涨停后某天成交量 < 均量 × `volume_ratio`（默认 0.6）
- 且当天收盘价 < 涨停日收盘价
- 参数：`ma_days`（默认 5）、`volume_ratio`（默认 0.6）

### 策略3 - 单日缩量回踩 (`single_day`)

涨停日后任意一天成交量显著低于涨停日成交量，且价格回落。

- 条件：某天成交量 < 涨停日成交量 × `volume_ratio`（默认 0.5）
- 且当天收盘价 < 涨停日收盘价
- 参数：`volume_ratio`（默认 0.5）

## 筛选入口函数

```python
def analyze_pullback(
    kline_data: list[dict],
    zt_date: str,
    zt_close: float,
    strategy: str,  # "shrinking_volume" | "below_average" | "single_day"
    **params,
) -> dict | None
```

返回命中结果或 None。预留 `zt_date` 参数为列表的扩展接口（当前只取最后一个涨停日）。

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
      "current_close": 165.0,
      "pullback_start_date": "2026-05-23",
      "pullback_days": 3,
      "volume_shrink_ratio": 0.45
    }
  ]
}
```

## SKILL.md 交互设计

1. 用户输入 `/suolianghuicai <zt_json路径>`
2. SKILL.md 展示三种策略说明，Claude 让用户选择
3. 根据选择执行：`python main.py <json路径> --strategy <1|2|3>`
4. 可选参数通过 `--shrink-ratio`、`--ma-days`、`--volume-ratio` 传递
5. 输出结果摘要

## 依赖

- requests（HTTP 请求）
- 复用新浪财经 API，无需新增外部依赖

## 扩展性

- analyzer 的 `analyze_pullback` 函数接受 `zt_date` 参数，当前传单个日期（最后一次涨停），未来可传列表实现"每次涨停后都检查"
- 三种策略均为独立函数，新增策略只需添加函数 + 注册

## 验证

1. 准备测试数据：使用已有的 `zt_2026-05-24.json`
2. 分别运行三种策略，检查输出 JSON 格式正确
3. 人工抽查 2-3 只股票的 K 线数据，验证缩量回踩判断是否合理
4. 检查无涨停后数据的股票是否被正确跳过
