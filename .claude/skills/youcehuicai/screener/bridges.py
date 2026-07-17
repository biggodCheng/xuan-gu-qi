"""桥接 kangdie 数据层（新浪全A+个股OHLCV+市值+指数K线），复用数据源。

youcehuicai 数据需求与 kangdie 相同（含指数K线用于企稳门控），不重复实现 fetcher。
"""
import importlib.util
import sys
import types
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_KANGDIE_SCREENER = _PROJECT_ROOT / ".claude" / "skills" / "kangdie" / "screener"
_PKG = "yc_kangdie"


def _load_kangdie_fetcher():
    if _PKG not in sys.modules:
        m = types.ModuleType(_PKG)
        m.__path__ = [str(_KANGDIE_SCREENER)]
        sys.modules[_PKG] = m
    full = f"{_PKG}.fetcher"
    if full not in sys.modules:
        spec = importlib.util.spec_from_file_location(full, _KANGDIE_SCREENER / "fetcher.py")
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = _PKG
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
    return sys.modules[full]


_kf = _load_kangdie_fetcher()
get_all_stocks_today = _kf.get_all_stocks_today
get_stock_kline = _kf.get_stock_kline
get_market_cap_map = _kf.get_market_cap_map
get_index_kline = _kf.get_index_kline
