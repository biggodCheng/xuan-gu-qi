import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from screener.browser import parse_one


def test_parse_one_normal_row():
    # rank>=4 行: td 文本完整 (td9 = 新晋% / 铁杆%)
    cells = ['4', '-2', '', '000725', '', '排名详情 股吧', '--', '--', '--', '13.42% 86.58%']
    r = parse_one(cells, base_rank=4)
    assert r['rank'] == 4
    assert r['code'] == '000725'
    assert r['name'] == ''            # DOM 空(后续 fetcher 补)
    assert r['rank_change'] == '-2'
    assert r['popularity'] == 13.42   # 新晋粉丝%


def test_parse_one_top3_uses_base_rank():
    # rank 1 行: td[0] 文本空, rank 用 base_rank
    cells = ['', '52', '', '002384', '', '排名详情 股吧', '--', '--', '--', '29.08% 70.92%']
    r = parse_one(cells, base_rank=1)
    assert r['rank'] == 1
    assert r['code'] == '002384'
    assert r['rank_change'] == '52'
    assert r['popularity'] == 29.08


def test_parse_one_extracts_code_from_mixed():
    # 代码单元格可能含前缀如 SH600000
    cells = ['1', '5', '', 'SH600000', '', '排名详情 股吧', '--', '--', '--', '10.0% 90.0%']
    r = parse_one(cells, base_rank=1)
    assert r['code'] == '600000'


def test_parse_one_invalid_code_returns_none():
    cells = ['1', '5', '', '不是代码', '', '排名详情 股吧', '--', '--', '--', '10.0% 90.0%']
    assert parse_one(cells, base_rank=1) is None


def test_parse_one_no_fans_popularity_none():
    cells = ['5', '-1', '', '000001', '', '排名详情 股吧', '--', '--', '--', '']
    r = parse_one(cells, base_rank=5)
    assert r['popularity'] is None
    assert r['code'] == '000001'


def test_parse_one_too_few_cells():
    assert parse_one(['1', '2'], base_rank=1) is None
