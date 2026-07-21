# -*- coding: utf-8 -*-
"""local_kline 单元/集成测试。

锁定招商证券 vipdoc 通达信 .day 二进制解析格式:
  每记录 32 字节, struct '<IIIIIfII'
  date(int YYYYMMDD) / open / high / low / close(int, 实际价÷100)
  / amount(float,成交额元) / vol(int,成交量手) / reserve(int)
"""
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import local_kline  # noqa: E402

VIPDOC = r"D:\APP\招商证券\vipdoc"
HAS_VIPDOC = os.path.isdir(VIPDOC)


# ---------- 单元: 纯字节解析 (确定性, 锁格式) ----------

def test_parse_day_bytes_decodes_one_record():
    """一条茅台真实日K: 2026-07-21 开1308.98/高1344.70/低1296.87/收1308.00 额10174304256 量7714770"""
    raw = struct.pack('<IIIIIfII', 20260721, 130898, 134470, 129687, 130800,
                      10174304256, 7714770, 0)
    rows = local_kline._parse_day_bytes(raw)
    assert len(rows) == 1
    r = rows[0]
    assert r["date"] == "2026-07-21"
    assert r["open"] == 1308.98
    assert r["high"] == 1344.70
    assert r["low"] == 1296.87
    assert r["close"] == 1308.00
    assert r["amount"] == pytest.approx(10174304256.0, abs=2048)  # float32 存储, 容忍量化误差
    assert r["volume"] == 7714770


def test_parse_day_bytes_empty_returns_empty():
    assert local_kline._parse_day_bytes(b"") == []


def test_parse_day_bytes_ignores_trailing_partial_record():
    """尾部不足32字节的残缺记录应被忽略, 不报错。"""
    full = struct.pack('<IIIIIfII', 20260101, 10000, 10100, 9900, 10000, 1e8, 1000, 0)
    rows = local_kline._parse_day_bytes(full + b"\x00\x01")  # 多2字节残缺
    assert len(rows) == 1


def test_parse_day_bytes_keeps_storage_order():
    """.day 文件本身正序存储(早→晚), 解析后顺序保持。"""
    raw = (struct.pack('<IIIIIfII', 20260101, 10000, 10100, 9900, 10000, 1e8, 1000, 0)
           + struct.pack('<IIIIIfII', 20260102, 10100, 10200, 10000, 10100, 1e8, 1100, 0))
    rows = local_kline._parse_day_bytes(raw)
    assert [r["date"] for r in rows] == ["2026-01-01", "2026-01-02"]


# ---------- 单元: 路径构建 ----------

def test_day_path_sh_index():
    p = local_kline._day_path("sh000001")
    assert p.endswith(os.path.join("sh", "lday", "sh000001.day"))


def test_day_path_sz_index_lowercase_tolerant():
    """大写/小写 sym 都应能定位文件 (vipdoc 文件名全小写)。"""
    p = local_kline._day_path("SZ399006")
    assert p.endswith(os.path.join("sz", "lday", "sz399006.day"))


# ---------- 集成: 真实本地文件 ----------

@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_read_day_real_maotai():
    rows = local_kline.read_day("sh600519")
    assert len(rows) > 100
    assert set(rows[0]) >= {"date", "open", "high", "low", "close", "volume", "amount"}
    assert rows[0]["close"] > 0
    assert rows[0]["date"] < rows[-1]["date"]  # 正序


def test_read_day_missing_returns_empty(monkeypatch, tmp_path):
    """VIPDOC 指向空目录时, 任何 sym 都返回 [] (不报错)。"""
    monkeypatch.setattr(local_kline, "VIPDOC", str(tmp_path))
    assert local_kline.read_day("sh600519") == []


@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_fetch_index_kline_format_matches_fupan():
    """fupan.fetch_index_kline 约定: [{date,close,volume},...] 正序, 末尾 days 条。
    volume 取成交额(元), 与新浪 getKLineData 语义一致, 供 fupan 量能比判定。"""
    rows = local_kline.fetch_index_kline("sh000001", days=20)
    assert 0 < len(rows) <= 20
    assert set(rows[0]) == {"date", "close", "volume"}
    assert isinstance(rows[0]["close"], float)
    assert "/" not in rows[0]["date"]  # YYYY-MM-DD


# ---------- 单元: A股板块分类 (供 fetch_local_breadth 过滤非A股) ----------

def test_classify_a_share_a_stock_boards():
    assert local_kline._classify_a_share("sh600519") == "main"   # 沪主板
    assert local_kline._classify_a_share("sz000001") == "main"   # 深主板
    assert local_kline._classify_a_share("sz300750") == "cyb"    # 创业板
    assert local_kline._classify_a_share("sz301088") == "cyb"
    assert local_kline._classify_a_share("sh688981") == "kcb"    # 科创板
    assert local_kline._classify_a_share("bj430047") == "bj"     # 北交所
    assert local_kline._classify_a_share("bj920019") == "bj"


def test_classify_a_share_excludes_non_a_stock():
    """指数 / B股 / 基金ETF / 转债 不计入全市场宽度。"""
    assert local_kline._classify_a_share("sh000001") is None      # 上证指数
    assert local_kline._classify_a_share("sz399001") is None      # 深证成指
    assert local_kline._classify_a_share("sh900901") is None      # 沪B
    assert local_kline._classify_a_share("sz200002") is None      # 深B
    assert local_kline._classify_a_share("sh510300") is None      # 沪市ETF
    assert local_kline._classify_a_share("sz159915") is None      # 深市ETF
    assert local_kline._classify_a_share("sh113001") is None      # 沪转债


# ---------- 集成: 全市场宽度 (本地 vipdoc, 零网络) ----------

@pytest.mark.skipif(not HAS_VIPDOC, reason="无招商证券 vipdoc 目录")
def test_fetch_local_breadth_returns_full_market():
    """本地全市场宽度: 全市场量级(≥4000只)、合法日期、当日覆盖率达标(≥3000)。"""
    pairs, latest_date, cov = local_kline.fetch_local_breadth()
    assert len(pairs) >= 4000, f"本地宽度非全市场量级: {len(pairs)}"
    assert len(latest_date) == 10 and latest_date[4] == "-", f"日期格式异常: {latest_date}"
    assert cov >= 3000, f"当日覆盖率不足: {cov} (需≥3000)"


def test_fetch_local_breadth_missing_vipdoc(monkeypatch, tmp_path):
    """VIPDOC 指向空目录时返回空三元组, 不报错。"""
    monkeypatch.setattr(local_kline, "VIPDOC", str(tmp_path))
    pairs, latest_date, cov = local_kline.fetch_local_breadth()
    assert pairs == [] and latest_date == "" and cov == 0
