"""Exchange rates, and a couple of cryptocurrencies.

The rates are the European Central Bank's reference rates, set once each
working day around 4pm in Frankfurt and read through Frankfurter
(https://frankfurter.dev, free, no sign-up). The last couple of months
come along too, for each currency's trend line. Bitcoin and Ethereum come
from CoinGecko (https://www.coingecko.com, free), with their last week.

Everything that touches the network returns None on failure rather than
raising: the board carries on with the last rates it had.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from simple_info.core.http import SSL_CONTEXT

TIMEOUT_SECONDS = 10
FRANKFURTER_URL = "https://api.frankfurter.dev/v1"
COINGECKO_URL = "https://api.coingecko.com/api/v3"
HISTORY_DAYS = 45  # about a month of working days

# The currencies the ECB sets a rate for: code -> (name, symbol)
CURRENCIES = {
    "AUD": ("Australian Dollar", "A$"), "BRL": ("Brazilian Real", "R$"), "CAD": ("Canadian Dollar", "C$"),
    "CHF": ("Swiss Franc", "Fr"), "CNY": ("Chinese Yuan", "¥"), "CZK": ("Czech Koruna", "Kč"),
    "DKK": ("Danish Krone", "kr"), "EUR": ("Euro", "€"), "GBP": ("British Pound", "£"),
    "HKD": ("Hong Kong Dollar", "HK$"), "HUF": ("Hungarian Forint", "Ft"), "IDR": ("Indonesian Rupiah", "Rp"),
    "ILS": ("Israeli Shekel", "₪"), "INR": ("Indian Rupee", "₹"), "ISK": ("Icelandic Króna", "kr"),
    "JPY": ("Japanese Yen", "¥"), "KRW": ("South Korean Won", "₩"), "MXN": ("Mexican Peso", "Mex$"),
    "MYR": ("Malaysian Ringgit", "RM"), "NOK": ("Norwegian Krone", "kr"), "NZD": ("New Zealand Dollar", "NZ$"),
    "PHP": ("Philippine Peso", "₱"), "PLN": ("Polish Złoty", "zł"), "RON": ("Romanian Leu", "lei"),
    "SEK": ("Swedish Krona", "kr"), "SGD": ("Singapore Dollar", "S$"), "THB": ("Thai Baht", "฿"),
    "TRY": ("Turkish Lira", "₺"), "USD": ("US Dollar", "$"), "ZAR": ("South African Rand", "R"),
}
DEFAULT_CODES = ["EUR", "USD", "CAD", "AUD", "JPY", "CHF", "NZD", "SEK", "NOK"]

# CoinGecko id -> (name, symbol)
CRYPTO = {"bitcoin": ("Bitcoin", "₿"), "ethereum": ("Ethereum", "Ξ")}


@dataclass
class Rate:
    code: str
    rate: float  # how much of this currency one unit of the base buys
    previous: float  # the working day before's rate (0 if unknown)
    history: list[float] = field(default_factory=list)  # oldest first, ending with today's

    @property
    def name(self) -> str:
        return CURRENCIES.get(self.code, (self.code, ""))[0]

    @property
    def symbol(self) -> str:
        return CURRENCIES.get(self.code, ("", self.code))[1]

    @property
    def change(self) -> float:
        """Percentage change since the working day before."""
        return (self.rate / self.previous - 1) * 100 if self.previous else 0.0


@dataclass
class Coin:
    id: str
    price: float  # one coin, in the base currency
    change: float  # percentage over the last 24 hours
    history: list[float] = field(default_factory=list)  # the last week, oldest first

    @property
    def name(self) -> str:
        return CRYPTO.get(self.id, (self.id.title(), ""))[0]

    @property
    def symbol(self) -> str:
        return CRYPTO.get(self.id, ("", "?"))[1]


@dataclass
class Rates:
    base: str
    date: str  # the day the ECB set these rates, "2026-10-20"
    rates: list[Rate]
    coins: list[Coin]
    fetched_at: float


def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Simple-Info/1", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=SSL_CONTEXT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def parse_series(payload: dict, codes: list[str]) -> tuple[str, list[Rate]]:
    """(latest date, rates) from a Frankfurter time series."""
    days = payload.get("rates") or {}
    dates = sorted(d for d, v in days.items() if isinstance(v, dict))
    rates = []
    for code in codes:
        history = [float(days[d][code]) for d in dates if isinstance(days[d].get(code), (int, float))]
        if history:
            rates.append(Rate(code, history[-1], history[-2] if len(history) > 1 else 0.0, history))
    return (dates[-1] if dates else ""), rates


def fetch_rates(base: str, codes: list[str], today: Optional[float] = None) -> Optional[tuple[str, list[Rate]]]:
    codes = [c for c in codes if c in CURRENCIES and c != base]
    if base not in CURRENCIES or not codes:
        return None
    start = time.strftime("%Y-%m-%d", time.gmtime((today or time.time()) - HISTORY_DAYS * 86400))
    params = urllib.parse.urlencode({"base": base, "symbols": ",".join(codes)})
    data = _get_json(f"{FRANKFURTER_URL}/{start}..?{params}")
    if not isinstance(data, dict):
        return None
    try:
        date, rates = parse_series(data, codes)
    except (TypeError, ValueError, AttributeError):
        return None
    return (date, rates) if rates else None


def parse_coins(payload: list) -> list[Coin]:
    coins = []
    for c in payload if isinstance(payload, list) else []:
        try:
            spark = (c.get("sparkline_in_7d") or {}).get("price") or []
            coins.append(Coin(str(c["id"]), float(c["current_price"]), float(c.get("price_change_percentage_24h") or 0.0),
                              [float(v) for v in spark if isinstance(v, (int, float))]))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    order = list(CRYPTO)
    return sorted(coins, key=lambda c: order.index(c.id) if c.id in order else len(order))


def fetch_coins(base: str) -> Optional[list[Coin]]:
    params = urllib.parse.urlencode({"vs_currency": base.lower(), "ids": ",".join(CRYPTO), "sparkline": "true",
                                     "price_change_percentage": "24h"})
    data = _get_json(f"{COINGECKO_URL}/coins/markets?{params}")
    coins = parse_coins(data) if isinstance(data, list) else []
    return coins or None


def fetch(base: str, codes: list[str], crypto: bool) -> Optional[Rates]:
    """Everything the board shows, or None if the rates couldn't be had.
    (Coins that can't be had are just left out.)"""
    got = fetch_rates(base, codes)
    if got is None:
        return None
    date, rates = got
    coins = (fetch_coins(base) or []) if crypto else []
    return Rates(base, date, rates, coins, time.time())


# --- remembering the last rates, so a restart while offline still has some

MAX_CACHE_AGE_SECONDS = 4 * 86400


def save_rates(rates: Rates, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(rates)))
    except OSError:
        pass


def load_rates(path: Path, now: Optional[float] = None) -> Optional[Rates]:
    try:
        data = json.loads(path.read_text())
        data["rates"] = [Rate(**r) for r in data.get("rates", [])]
        data["coins"] = [Coin(**c) for c in data.get("coins", [])]
        rates = Rates(**data)
    except (OSError, ValueError, TypeError):
        return None
    if (now if now is not None else time.time()) - rates.fetched_at > MAX_CACHE_AGE_SECONDS:
        return None
    return rates


# --- display helpers

def format_rate(value: float) -> str:
    """Enough figures to be useful, never silly: 1.1901, 18.734, 201.39, 1,592."""
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 100:
        return f"{value:,.2f}"
    if value >= 10:
        return f"{value:.3f}"
    return f"{value:.4f}"


def format_money(value: float, symbol: str) -> str:
    """A price, like £62,267 or £1,836.98 or £0.3412."""
    if value >= 10000:
        return f"{symbol}{value:,.0f}"
    if value >= 1:
        return f"{symbol}{value:,.2f}"
    return f"{symbol}{value:.4f}"


def format_change(percent: float) -> str:
    arrow = "▲" if percent > 0.005 else "▼" if percent < -0.005 else "■"
    return f"{arrow} {abs(percent):.2f}%"
