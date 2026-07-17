# -*- coding: utf-8 -*-
"""用 importlib 复用 q2zhanwang 的核心函数，绕开多个 screener 包名冲突。

照抄 eval-stock/screener/bridges.py，改包名前缀 kd_ 避免命名空间冲突。
不写文件、无副作用。
"""
import importlib.util
import sys
import types
from pathlib import Path

# bridges.py 位于 <root>/.claude/skills/kangdie/screener/bridges.py
# parents[0]=screener [1]=kangdie [2]=skills [3]=.claude [4]=xuan-gu-qi
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_SKILLS_DIR = _PROJECT_ROOT / ".claude" / "skills"


def _ensure_pkg(pkg_name: str, screener_dir: Path) -> str:
    """注册临时命名空间包 pkg_name，__path__ 指向 screener_dir。返回包名。"""
    if pkg_name not in sys.modules:
        m = types.ModuleType(pkg_name)
        m.__path__ = [str(screener_dir)]
        sys.modules[pkg_name] = m
    return pkg_name


def _load_sub(pkg_name: str, sub: str, path: Path):
    full = f"{pkg_name}.{sub}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, path)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = pkg_name  # 支持模块内相对导入(from .xxx)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_skill(skill: str):
    screener_dir = _SKILLS_DIR / skill / "screener"
    pkg = _ensure_pkg(f"kd_{skill}", screener_dir)
    fetcher = _load_sub(pkg, "fetcher", screener_dir / "fetcher.py")
    analyzer = _load_sub(pkg, "analyzer", screener_dir / "analyzer.py")
    return fetcher, analyzer


# ---- Q2 ----

def get_q2_funcs():
    """返回 (get_financial, analyze)。失败抛异常，由调用方兜底。"""
    f, a = _load_skill("q2zhanwang")
    return f.get_financial, a.analyze


# ---- 四大赛道 ----

def get_sid_funcs():
    """返回 (get_stock_detail, match_tracks)。失败抛异常，由调用方兜底。

    get_stock_detail(code) -> {code,name,industry,concepts}
    match_tracks(industry, concepts) -> [{"track":"大工业","confidence":"高",...},...]
    注意：sidasaidao/analyzer 依赖同级 tracks.py，必须先加载 tracks 再加载 analyzer。
    """
    screener_dir = _SKILLS_DIR / "sidasaidao" / "screener"
    pkg = _ensure_pkg("kd_sidasaidao", screener_dir)
    _load_sub(pkg, "tracks", screener_dir / "tracks.py")  # analyzer 的 from .tracks 依赖
    fetcher = _load_sub(pkg, "fetcher", screener_dir / "fetcher.py")
    analyzer = _load_sub(pkg, "analyzer", screener_dir / "analyzer.py")
    return fetcher.get_stock_detail, analyzer.match_tracks
