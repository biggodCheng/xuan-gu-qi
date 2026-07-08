import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from screener.bridges import get_q2_funcs, get_sid_funcs


def test_load_q2_funcs_callable():
    get_financial, analyze = get_q2_funcs()
    assert callable(get_financial) and callable(analyze)
    # analyze 是纯函数，喂空 reports 应回数据不足
    r = analyze({"code": "000000", "name": "", "industry": "", "reports": []})
    assert r["q2_outlook"]["verdict"] == "数据不足"


def test_load_sid_funcs_callable():
    resolve, get_detail, match = get_sid_funcs()
    assert callable(resolve) and callable(get_detail) and callable(match)
    # match_tracks 纯函数：空输入返回空列表
    assert match("", []) == []
