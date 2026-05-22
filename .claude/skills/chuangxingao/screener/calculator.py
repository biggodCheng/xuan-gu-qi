def is_new_high(close: float, history: list[float]) -> bool:
    if not history:
        return False
    return close >= max(history)


def filter_new_highs(
    stocks: list[dict], histories: dict[str, list[float]]
) -> list[dict]:
    result = []
    for stock in stocks:
        code = stock["code"]
        history = histories.get(code, [])
        if not history:
            continue
        if is_new_high(stock["close"], history):
            result.append({
                "code": code,
                "name": stock["name"],
                "close": stock["close"],
                "high_100d": max(history),
            })
    return result
