"""桥接 kangdie 的数据层（新浪全A列表 + 个股OHLCV + 市值），复用数据源。

chaojie 的数据需求与 kangdie 完全相同，故不重复实现 fetcher，
通过 importlib 加载 kangdie/screener/fetcher.py（绕开 screener 包名冲突）。
"""
import importlib.util
import sys
import types
from pathlib import Path

# bridges.py 位于 <root>/.claude/skills/chaojie/screener/bridges.py
# parents[0]=screener [1]=chaojie [2]=skills [3]=.claude [4]=xuan-gu-qi
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_KANGDIE_SCREENER = _PROJECT_ROOT / ".claude" / "skills" / "kangdie" / "screener"

_PKG = "cj_kangdie"


def _load_kangdie_fetcher():
    """加载 kangdie/screener/fetcher.py 到临时命名空间包 cj_kangdie.fetcher。"""
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
