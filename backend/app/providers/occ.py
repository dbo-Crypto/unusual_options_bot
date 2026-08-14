from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from app.providers.base import OccDailyRow

log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
SERIES_URL = "https://marketdata.theocc.com/series-search"
VOLUME_URL = "https://marketdata.theocc.com/volume-query"
HEADERS = {"User-Agent": "unusual-options-bot/0.1 (personal research)"}


def parse_occ_series_text(text: str, symbol: str, session_date: date | None = None) -> list[OccDailyRow]:
    """Parse the tab-separated OCC series-search dump."""
    session_date = session_date or datetime.now(ET).date()
    rows: list[OccDailyRow] = []
    for raw in text.splitlines():
        if "\t" not in raw:
            continue
        parts = [p.strip() for p in raw.split("\t")]
        # Expected: SYMBOL, '', YYYY, MM, DD, strike_int, strike_dec, "C P"|C|P, call_oi, put_oi, limit
        # Mini options like 2AAPL appear as the first field.
        if len(parts) < 10:
            continue
        try:
            product = parts[0].strip()
            # Skip mini/adjusted roots for v1 (2AAPL, 3AAPL, ...)
            if product and product[0].isdigit():
                continue
            if product.upper() != symbol.upper() and not product.upper().startswith(symbol.upper()):
                # first column can be padded "AAPL  "
                if symbol.upper() not in product.upper():
                    continue
            year, month, day = int(parts[2]), int(parts[3]), int(parts[4])
            strike = float(parts[5]) + float(parts[6]) / 1000.0
            cp_field = parts[7].replace(" ", "")
            expiry = date(year, month, day)
            occ_root = f"{symbol.upper()}{expiry.strftime('%y%m%d')}"
        except (ValueError, IndexError):
            continue

        def _oi(idx: int) -> int | None:
            try:
                return int(float(parts[idx].replace(",", "")))
            except (ValueError, IndexError):
                return None

        if "C" in cp_field and "P" in cp_field:
            call_oi, put_oi = _oi(8), _oi(9)
            strike_key = f"{strike:.3f}".rstrip("0").rstrip(".")
            if call_oi is not None:
                rows.append(
                    OccDailyRow(
                        session_date=session_date,
                        occ_symbol=f"{occ_root}C{strike_key}",
                        underlying=symbol.upper(),
                        expiry=expiry,
                        strike=strike,
                        call_put="C",
                        open_interest=call_oi,
                    )
                )
            if put_oi is not None:
                rows.append(
                    OccDailyRow(
                        session_date=session_date,
                        occ_symbol=f"{occ_root}P{strike_key}",
                        underlying=symbol.upper(),
                        expiry=expiry,
                        strike=strike,
                        call_put="P",
                        open_interest=put_oi,
                    )
                )
        elif cp_field == "C":
            rows.append(
                OccDailyRow(
                    session_date=session_date,
                    occ_symbol=f"{occ_root}C{strike:.3f}".rstrip("0").rstrip("."),
                    underlying=symbol.upper(),
                    expiry=expiry,
                    strike=strike,
                    call_put="C",
                    open_interest=_oi(8),
                )
            )
        elif cp_field == "P":
            rows.append(
                OccDailyRow(
                    session_date=session_date,
                    occ_symbol=f"{occ_root}P{strike:.3f}".rstrip("0").rstrip("."),
                    underlying=symbol.upper(),
                    expiry=expiry,
                    strike=strike,
                    call_put="P",
                    open_interest=_oi(8),
                )
            )
    return rows


def parse_occ_volume_csv(text: str, symbol: str) -> dict[str, int]:
    """Sum customer+firm+market-maker volume into call/put totals for an underlying."""
    totals = {"C": 0, "P": 0}
    lines = text.strip().splitlines()
    if not lines:
        return totals
    header = [h.strip().lower() for h in lines[0].split(",")]
    try:
        qty_i = header.index("quantity")
        und_i = header.index("underlying")
        cp_i = header.index("porc")
    except ValueError:
        return totals
    for line in lines[1:]:
        cols = [c.strip() for c in line.split(",")]
        if len(cols) <= max(qty_i, und_i, cp_i):
            continue
        if cols[und_i].upper() != symbol.upper():
            continue
        cp = cols[cp_i].upper()[:1]
        if cp not in totals:
            continue
        try:
            totals[cp] += int(float(cols[qty_i]))
        except ValueError:
            continue
    return totals


class OccProvider:
    name = "occ"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch_occ_oi(self, symbol: str, session_date: date | None = None) -> list[OccDailyRow]:
        try:
            with httpx.Client(timeout=self.timeout, headers=HEADERS, follow_redirects=True) as client:
                resp = client.get(SERIES_URL, params={"symbolType": "U", "symbol": symbol.upper()})
                resp.raise_for_status()
            return parse_occ_series_text(resp.text, symbol, session_date)
        except Exception as exc:
            log.warning("OCC series search failed for %s: %s", symbol, exc)
            return []

    def fetch_underlying_volume(self, symbol: str, session_date: date | None = None) -> dict[str, int]:
        session_date = session_date or datetime.now(ET).date()
        try:
            with httpx.Client(timeout=self.timeout, headers=HEADERS, follow_redirects=True) as client:
                resp = client.get(
                    VOLUME_URL,
                    params={
                        "reportDate": session_date.strftime("%Y%m%d"),
                        "format": "csv",
                        "volumeQueryType": "O",
                        "symbolType": "U",
                        "symbol": symbol.upper(),
                        "reportType": "D",
                    },
                )
                resp.raise_for_status()
            return parse_occ_volume_csv(resp.text, symbol)
        except Exception as exc:
            log.warning("OCC volume query failed for %s: %s", symbol, exc)
            return {"C": 0, "P": 0}

    def ping(self) -> dict:
        try:
            rows = self.fetch_occ_oi("AAPL")
            return {
                "ok": bool(rows),
                "asof": datetime.now(timezone.utc).isoformat(),
                "sample_rows": len(rows),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
