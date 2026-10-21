import json
from unittest.mock import patch

from simple_info.core import currency as cx

SERIES = {
    "amount": 1.0, "base": "GBP", "start_date": "2026-10-16", "end_date": "2026-10-20",
    "rates": {
        "2026-10-20": {"EUR": 1.1901, "USD": 1.3347},
        "2026-10-16": {"EUR": 1.18, "USD": 1.34},
        "2026-10-19": {"EUR": 1.1876, "USD": 1.3331},
    },
}
COINS = [
    {"id": "ethereum", "current_price": 1836.98, "price_change_percentage_24h": 2.76, "sparkline_in_7d": {"price": [1800, 1810.5, 1836.98]}},
    {"id": "bitcoin", "current_price": 62267, "price_change_percentage_24h": -1.5, "sparkline_in_7d": {"price": [63000, None, 62267]}},
    {"id": "broken"},
]


class _Response:
    def __init__(self, data):
        self._data = json.dumps(data).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_parse_series_puts_the_days_in_order():
    date, rates = cx.parse_series(SERIES, ["USD", "EUR", "JPY"])
    assert date == "2026-10-20"
    usd, eur = rates  # JPY isn't in the data, so it's left out
    assert usd.code == "USD" and usd.history == [1.34, 1.3331, 1.3347] and usd.previous == 1.3331
    assert eur.rate == 1.1901 and round(eur.change, 2) == 0.21
    assert (eur.name, eur.symbol) == ("Euro", "€")


def test_parse_coins_keeps_our_order_and_skips_junk():
    bitcoin, ethereum = cx.parse_coins(COINS)
    assert (bitcoin.name, bitcoin.symbol, bitcoin.price, bitcoin.change) == ("Bitcoin", "₿", 62267.0, -1.5)
    assert bitcoin.history == [63000.0, 62267.0]
    assert ethereum.history == [1800.0, 1810.5, 1836.98]
    assert cx.parse_coins({"error": "rate limited"}) == []


def test_fetch_asks_for_the_right_things():
    urls = []

    def fake(request, **kwargs):
        urls.append(request.full_url)
        return _Response(SERIES if "frankfurter" in request.full_url else COINS)

    with patch("urllib.request.urlopen", side_effect=fake):
        rates = cx.fetch("GBP", ["EUR", "USD", "GBP", "XXX"], crypto=True)
    assert "base=GBP" in urls[0] and "symbols=EUR%2CUSD" in urls[0] and ".." in urls[0]
    assert "vs_currency=gbp" in urls[1] and "bitcoin" in urls[1]
    assert [r.code for r in rates.rates] == ["EUR", "USD"] and len(rates.coins) == 2 and rates.date == "2026-10-20"


def test_fetch_without_crypto_or_when_offline():
    with patch("urllib.request.urlopen", return_value=_Response(SERIES)) as opened:
        assert cx.fetch("GBP", ["EUR"], crypto=False).coins == []
        assert opened.call_count == 1
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert cx.fetch("GBP", ["EUR"], crypto=True) is None
    assert cx.fetch("XYZ", ["EUR"], crypto=False) is None
    # the rates arrive but CoinGecko doesn't: the coins are just left out
    responses = iter([_Response(SERIES), OSError("rate limited")])

    def flaky(*a, **k):
        r = next(responses)
        if isinstance(r, Exception):
            raise r
        return r

    with patch("urllib.request.urlopen", side_effect=flaky):
        rates = cx.fetch("GBP", ["EUR"], crypto=True)
    assert rates is not None and rates.coins == []


def test_cache_round_trips_and_expires(tmp_path):
    path = tmp_path / "rates.json"
    _, rates = cx.parse_series(SERIES, ["EUR"])
    saved = cx.Rates("GBP", "2026-10-20", rates, cx.parse_coins(COINS), fetched_at=1000.0)
    cx.save_rates(saved, path)
    assert cx.load_rates(path, now=2000.0) == saved
    assert cx.load_rates(path, now=1000.0 + 5 * 86400) is None
    path.write_text("not json")
    assert cx.load_rates(path) is None


def test_formatting():
    assert [cx.format_rate(v) for v in (1.19012, 18.7339, 211.054, 1592.4)] == ["1.1901", "18.734", "211.05", "1,592"]
    assert [cx.format_money(v, "£") for v in (62267.4, 1836.981, 0.34123)] == ["£62,267", "£1,836.98", "£0.3412"]
    assert cx.format_change(0.214) == "▲ 0.21%" and cx.format_change(-1.5) == "▼ 1.50%" and cx.format_change(0.001) == "■ 0.00%"
