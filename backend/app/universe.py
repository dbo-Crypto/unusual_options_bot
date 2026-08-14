"""Default liquid universe scanned every live cycle."""

LIQUID_UNIVERSE: list[str] = [
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLC", "XLRE",
    "SMH", "XBI", "KRE", "GDX", "ARKK",
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD", "AVGO", "NFLX",
    "INTC", "AMAT", "MU", "QCOM", "CRM", "ORCL", "ADBE", "NOW", "AVGO",
    "JPM", "BAC", "GS", "WFC", "C",
    "XOM", "CVX",
    "UNH", "JNJ", "LLY", "ABBV",
    "HD", "COST", "WMT",
    "BA", "CAT", "GE",
    "COIN", "HOOD", "PLTR", "SNOW", "UBER", "SHOP", "CRWD", "PANW",
    "AMD", "TSM", "ASML",
]

# Deduplicate while preserving order
LIQUID_UNIVERSE = list(dict.fromkeys(LIQUID_UNIVERSE))

SECTOR_ETFS = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Utilities": "XLU",
    "Basic Materials": "XLB",
    "Communication Services": "XLC",
    "Real Estate": "XLRE",
    "Semiconductors": "SMH",
}

ZERO_DTE_UNDERLYINGS = {"SPY", "QQQ", "IWM", "DIA", "SPX", "^SPX"}
