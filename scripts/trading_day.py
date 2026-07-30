# -*- coding: utf-8 -*-
"""权威交易日解析 — 不信任本地系统时钟。

背景: 本机 Windows w32time 服务停摆, 系统时钟会跨日漂移(实测 07-29↔07-30 跳变),
导致依赖 datetime.now()/$(date) 定"今天"的 skill 文件名/数据日错位。本模块从新浪
日K取最新交易日作为数据日真相; 仅在网络全失败时降级本地时钟(此时应配合 drift 警告)。

为何用新浪而非本地 vipdoc: 新浪实时, 收盘后最新K线日=今日, 与东财资金流"数据日"
一致; 本地 vipdoc 未更新会滞后一天, 把今日数据误标成昨日。

API:
  latest_trading_day() -> "YYYY-MM-DD"  权威最近交易日(新浪日K末根); 失败降级本地时钟
  local_today_str()   -> "YYYY-MM-DD"  本地系统时钟日期(仅供 drift 对比, 不可信)
  drift_days(local, trading) -> int     trading - local 天数(0=一致, 正=时钟偏慢, 负=偏快)

导入约定(同 fupan→scripts/market_regime): 调用方先
    sys.path.insert(0, SCRIPTS_DIR)  # 项目根/scripts
    import trading_day
"""
import datetime
import json
import urllib.request

# 新浪日K: 一只流动性好的权重股即可定"最近交易日"; scale=240=日K, datalen=1=最新一根
_SINA_URL = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
             "CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen=1")
_SYMBOL = "sh600519"


def _sina_latest_day(symbol: str = _SYMBOL, timeout: float = 8.0):
    """从新浪日K取最新交易日(YYYY-MM-DD)。失败返回 None。"""
    url = _SINA_URL.format(sym=symbol)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn/",
    })
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
    data = json.loads(raw)
    if not data:
        return None
    return str(data[-1]["day"])[:10]


def latest_trading_day() -> str:
    """权威最近交易日。新浪失败 → 降级本地时钟(不可靠, 配合 drift 警告)。"""
    try:
        day = _sina_latest_day()
        if day:
            return day
    except Exception:
        pass
    return local_today_str()


def local_today_str() -> str:
    """本地系统时钟日期(仅供 drift 对比; 本机时钟会漂移, 勿单独使用)。"""
    return datetime.date.today().strftime("%Y-%m-%d")


def drift_days(local_str: str, trading_str: str) -> int:
    """trading - local 相差天数。0=一致; 正=本地时钟偏慢; 负=偏快(跨日)。"""
    fmt = "%Y-%m-%d"
    d_local = datetime.datetime.strptime(local_str, fmt).date()
    d_trade = datetime.datetime.strptime(trading_str, fmt).date()
    return (d_trade - d_local).days
