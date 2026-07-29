"""大盘环境开关 — 判断三大指数是否处于"加速阴跌段"。

仅当上证/沪深300/创业板指同步出现「空头排列(MA5<MA10<MA20) + 收盘跌破MA20 + 近5日缩量」
时才判为加速阴跌;此时超跌反弹信号可靠性低(熊市/下跌市历史必亏),应跳过扫描。
判据宽松:只排除最危险的"无承接阴跌"段,保留恐慌探底后的反抽机会。
"""
INDICES = [("sh000001", "上证指数"), ("sh000300", "沪深300"), ("sz399006", "创业板指")]
MA_SHORT, MA_MID, MA_LONG = 5, 10, 20


def _ma(vals: list[float], n: int) -> float | None:
    if len(vals) >= n:
        return sum(vals[-n:]) / n
    return None


def _index_crash(bars: list[dict]) -> bool:
    """单指数是否处于加速阴跌:空头排列 + 跌破MA20 + 近5日缩量。"""
    if len(bars) < MA_LONG + 1:
        return False
    closes = [b["close"] for b in bars]
    vols = [b.get("volume", b.get("vol", 0)) for b in bars]
    ma5, ma10, ma20 = _ma(closes, MA_SHORT), _ma(closes, MA_MID), _ma(closes, MA_LONG)
    cur = closes[-1]
    # 空头排列 + 收盘跌破MA20
    if not (ma5 and ma10 and ma20 and ma5 < ma10 < ma20 and cur < ma20):
        return False
    # 近5日缩量:近5日均量 <= 前5日均量(放量则有承接,不算缩量阴跌)
    if len(vols) >= 10:
        recent5 = sum(vols[-5:]) / 5
        prev5 = sum(vols[-10:-5]) / 5
        if prev5 > 0 and recent5 > prev5:
            return False
    return True


def is_market_crash(index_klines: dict[str, list[dict]]) -> bool:
    """三大指数是否同步处于加速阴跌段。

    Args:
        index_klines: {sym: 日K列表(正序,末根=当日)},每项含 close / volume。
                      缺失某指数则该指数视为非crash(不轻易判crash)。

    Returns:
        True = 三指数同步加速阴跌,应跳过超跌反弹扫描。
    """
    crashes = [_index_crash(index_klines.get(sym, [])) for sym, _ in INDICES]
    return len(crashes) == len(INDICES) and all(crashes)
