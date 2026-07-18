"""骨架 import 冒烟测试。"""


def test_import_analyzer():
    from screener.analyzer import is_oversold_rebound
    assert callable(is_oversold_rebound)


def test_backtest_pkg():
    import backtest  # noqa: F401
    assert True
