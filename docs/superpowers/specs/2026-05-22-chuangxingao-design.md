# 创新高选股器 (chuangxingao) 设计文档

## Context

需要一个 Claude Code Skill，每天股市收盘后，筛选出 A 股中当日收盘价创 100 个交易日新高的股票，将股票代码和名称以 JSON 格式保存。这是技术分析中的经典策略——创阶段新高意味着强势突破。

## 方案选择

**选定方案：纯 akshare 单脚本**

- 用 akshare 获取全 A 股行情数据
- 无需 API key，免费开源
- 运行时间约 10-20 分钟，每日一次可接受
- 后续可演进为加缓存方案提速

## 项目结构

```
xuan-gu-qi/
├── .claude/
│   └── skills/
│       └── chuangxingao/
│           ├── SKILL.md            # Skill 定义文件（/chuangxingao 命令）
│           ├── screener/
│           │   ├── __init__.py
│           │   ├── fetcher.py      # 数据获取：akshare 行情数据
│           │   ├── calculator.py   # 计算逻辑：判断100日新高
│           │   └── storage.py      # JSON 文件读写
│           ├── main.py             # 入口脚本
│           ├── requirements.txt    # 依赖：akshare, pandas
│           └── data/               # 输出目录，按日期存放结果
│               ├── 2026-05-22.json
│               └── ...
└── CLAUDE.md
```

所有文件自包含在 `.claude/skills/chuangxingao/` 目录下。

## 模块职责

### fetcher.py — 数据获取

- 使用 `akshare.stock_zh_a_spot_em()` 获取全 A 股当日行情（代码、名称、收盘价等）
- 对每只股票使用 `akshare.stock_zh_a_hist()` 获取近 120 个自然日的日 K 线数据（约 100 个交易日）
- 封装为两个主要函数：
  - `get_all_stocks_today()` → 返回 DataFrame（code, name, close）
  - `get_stock_history(code, days=120)` → 返回 DataFrame（date, close）

### calculator.py — 计算逻辑

- 输入：当日收盘价 + 过去 100 个交易日收盘价序列
- 判断逻辑：`今日收盘价 >= 过去100个交易日最高收盘价`
- 输出：创新高的股票列表
- 主要函数：
  - `find_new_highs(today_data, history_fetch_func, period=100)` → 返回 list[dict]

### storage.py — 存储模块

- 创建 `data/` 目录（如不存在）
- 按日期保存 JSON 文件：`data/YYYY-MM-DD.json`
- 如果当日文件已存在，覆盖更新
- 主要函数：
  - `save_results(date_str, stocks_data, output_dir)` → 写入 JSON
  - `load_results(date_str, output_dir)` → 读取 JSON（可选）

### main.py — 入口脚本

串联完整流程：
1. 检查依赖是否安装
2. 调用 fetcher 获取全 A 股当日行情
3. 逐个获取历史数据，调用 calculator 判断创新高
4. 调用 storage 保存结果
5. 打印摘要（总数、耗时）

## JSON 输出格式

```json
{
  "date": "2026-05-22",
  "description": "A股当日收盘价创100个交易日新高",
  "count": 42,
  "stocks": [
    {
      "code": "000001",
      "name": "平安银行",
      "close": 15.23,
      "high_100d": 15.10
    }
  ]
}
```

字段说明：
- `date`：交易日期
- `description`：筛选条件描述
- `count`：创新高股票数量
- `stocks`：股票列表
  - `code`：股票代码
  - `name`：股票名称
  - `close`：当日收盘价
  - `high_100d`：过去100个交易日最高收盘价

## Skill 定义 (SKILL.md)

- 命令名：`/chuangxingao`
- 触发条件：用户输入 `/chuangxingao`
- 行为：执行 `python main.py`，运行完整筛选流程
- 运行前检查依赖，未安装则提示 `pip install -r requirements.txt`
- 完成后展示摘要信息

## 异常处理

- **非交易日**：检测到无当日行情数据，输出提示"今日非交易日"
- **akshare 接口报错**：单个股票重试 3 次后跳过，记录到日志
- **网络超时**：单次请求 30 秒超时
- **data 目录不存在**：自动创建

## 定时任务（后续扩展）

第一版不实现，但预留扩展点：
- 可使用 Claude Code 的 CronCreate 工具，设置每个交易日 15:30 自动触发
- 也可使用 Windows Task Scheduler 定时执行 `python main.py`

## 依赖

```
akshare>=1.12.0
pandas>=2.0.0
```

## 验证方式

1. 运行 `pip install -r requirements.txt` 安装依赖
2. 执行 `python main.py`
3. 检查 `data/` 目录下是否生成了当日 JSON 文件
4. 验证 JSON 内容格式正确，stocks 列表中的股票确实满足创新高条件
5. 在 Claude Code 中输入 `/chuangxingao` 验证 Skill 触发正常
