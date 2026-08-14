from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol


@dataclass
class UnderlyingInfo:
    symbol: str
    name: str | None = None
    sector: str | None = None
    next_earnings: date | None = None
    spot: float | None = None
    spot_change_pct: float | None = None
    asof: datetime | None = None


@dataclass
class ContractSnapshot:
    occ_symbol: str
    underlying: str
    expiry: date
    strike: float
    call_put: str
    volume: int | None = None
    open_interest: int | None = None
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    iv: float | None = None
    spot: float | None = None
    asof: datetime | None = None
    source: str = "yahoo"

    @property
    def mid(self) -> float | None:
        if self.bid is not None and self.ask is not None and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.last_price

    @property
    def est_premium(self) -> float | None:
        px = self.mid
        if px is None or not self.volume:
            return None
        return float(self.volume) * px * 100.0

    @property
    def spread_pct(self) -> float | None:
        if self.bid is None or self.ask is None or self.ask <= 0:
            return None
        mid = (self.bid + self.ask) / 2.0
        if mid <= 0:
            return None
        return (self.ask - self.bid) / mid


@dataclass
class OccDailyRow:
    session_date: date
    occ_symbol: str
    underlying: str
    expiry: date
    strike: float
    call_put: str
    volume: int | None = None
    open_interest: int | None = None


@dataclass
class MarketBundle:
    asof: datetime
    underlyings: list[UnderlyingInfo] = field(default_factory=list)
    snapshots: list[ContractSnapshot] = field(default_factory=list)
    occ_rows: list[OccDailyRow] = field(default_factory=list)
    source: str = "replay"


class MarketDataProvider(Protocol):
    name: str

    def discover(self) -> list[str]:
        ...

    def fetch_underlying(self, symbol: str) -> UnderlyingInfo | None:
        ...

    def fetch_chain(self, symbol: str) -> list[ContractSnapshot]:
        ...

    def fetch_occ_oi(self, symbol: str) -> list[OccDailyRow]:
        ...
