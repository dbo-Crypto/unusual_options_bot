from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.providers.base import ContractSnapshot, UnderlyingInfo
from app.universe import LIQUID_UNIVERSE

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        if value != value:  # NaN
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None


def _occ_symbol(underlying: str, expiry: date, call_put: str, strike: float) -> str:
    return f"{underlying.upper()}{expiry.strftime('%y%m%d')}{call_put}{strike:g}"


class YahooProvider:
    name = "yahoo"

    def __init__(self) -> None:
        self._tickers: dict = {}

    def _ticker(self, symbol: str):
        import yfinance as yf

        key = symbol.upper()
        if key not in self._tickers:
            self._tickers[key] = yf.Ticker(key)
        return self._tickers[key]

    def discover(self) -> list[str]:
        return list(LIQUID_UNIVERSE)

    def fetch_underlying(self, symbol: str) -> UnderlyingInfo | None:
        try:
            t = self._ticker(symbol)
            info = {}
            try:
                info = t.info or {}
            except Exception:
                info = {}
            spot = None
            change = None
            try:
                fi = t.fast_info
                if isinstance(fi, dict):
                    spot = _safe_float(fi.get("lastPrice") or fi.get("last_price"))
                else:
                    spot = _safe_float(getattr(fi, "last_price", None) or getattr(fi, "lastPrice", None))
            except Exception:
                spot = _safe_float(info.get("regularMarketPrice"))
            prev = _safe_float(info.get("regularMarketPreviousClose"))
            if spot is not None and prev:
                change = (spot - prev) / prev * 100.0
            earnings = None
            raw = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
            if raw:
                try:
                    earnings = datetime.fromtimestamp(int(raw), tz=ET).date()
                except (TypeError, ValueError, OSError):
                    earnings = None
            return UnderlyingInfo(
                symbol=symbol.upper(),
                name=info.get("shortName") or info.get("longName"),
                sector=info.get("sector"),
                next_earnings=earnings,
                spot=spot,
                spot_change_pct=change,
                asof=datetime.now(timezone.utc),
            )
        except Exception as exc:
            log.warning("Yahoo underlying failed for %s: %s", symbol, exc)
            return None

    def fetch_chain(self, symbol: str) -> list[ContractSnapshot]:
        try:
            t = self._ticker(symbol)
            expiries = list(t.options or [])
        except Exception as exc:
            log.warning("Yahoo expiries failed for %s: %s", symbol, exc)
            return []

        # Cap expiries: nearest 8 to keep Yahoo polite
        expiries = expiries[:8]
        und = self.fetch_underlying(symbol)
        spot = und.spot if und else None
        asof = datetime.now(timezone.utc)
        out: list[ContractSnapshot] = []
        for exp_str in expiries:
            try:
                expiry = date.fromisoformat(exp_str)
                chain = t.option_chain(exp_str)
            except Exception as exc:
                log.debug("Yahoo chain %s %s failed: %s", symbol, exp_str, exc)
                continue
            for cp, frame in (("C", chain.calls), ("P", chain.puts)):
                if frame is None or frame.empty:
                    continue
                for _, row in frame.iterrows():
                    strike = _safe_float(row.get("strike"))
                    if strike is None:
                        continue
                    occ = str(row.get("contractSymbol") or _occ_symbol(symbol, expiry, cp, strike))
                    out.append(
                        ContractSnapshot(
                            occ_symbol=occ,
                            underlying=symbol.upper(),
                            expiry=expiry,
                            strike=strike,
                            call_put=cp,
                            volume=_safe_int(row.get("volume")),
                            open_interest=_safe_int(row.get("openInterest")),
                            last_price=_safe_float(row.get("lastPrice")),
                            bid=_safe_float(row.get("bid")),
                            ask=_safe_float(row.get("ask")),
                            iv=_safe_float(row.get("impliedVolatility")),
                            spot=spot,
                            asof=asof,
                            source="yahoo",
                        )
                    )
        return out

    def fetch_news(self, symbol: str, limit: int = 5) -> list[dict]:
        out: list[dict] = []
        try:
            items = list(self._ticker(symbol).news or [])[:limit]
        except Exception as exc:
            log.debug("Yahoo news failed for %s: %s", symbol, exc)
            return out
        for item in items:
            title = item.get("title") or (item.get("content") or {}).get("title")
            if not title:
                continue
            ts = item.get("providerPublishTime")
            published = None
            if ts:
                try:
                    published = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    published = None
            link = item.get("link") or (item.get("content") or {}).get("canonicalUrl", {})
            if isinstance(link, dict):
                link = link.get("url")
            out.append({"symbol": symbol.upper(), "title": title, "published_at": published, "url": link, "source": "yahoo"})
        return out

    def ping(self) -> dict:
        try:
            info = self.fetch_underlying("SPY")
            return {
                "ok": bool(info and info.spot),
                "asof": datetime.now(timezone.utc).isoformat(),
                "sample_spot": info.spot if info else None,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
