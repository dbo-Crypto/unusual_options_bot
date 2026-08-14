from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from app.config import get_settings
from app.providers.base import ContractSnapshot, MarketBundle, OccDailyRow, UnderlyingInfo


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class ReplayProvider:
    name = "replay"

    def __init__(self, fixtures_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.dir = Path(fixtures_dir or settings.fixtures_dir)

    def load_bundle(self) -> MarketBundle:
        path = self.dir / "market_bundle.json"
        raw = json.loads(path.read_text())
        asof = _parse_dt(raw.get("asof")) or datetime.now()
        underlyings = [
            UnderlyingInfo(
                symbol=u["symbol"],
                name=u.get("name"),
                sector=u.get("sector"),
                next_earnings=_parse_date(u.get("next_earnings")),
                spot=u.get("spot"),
                spot_change_pct=u.get("spot_change_pct"),
                asof=asof,
            )
            for u in raw.get("underlyings", [])
        ]
        snapshots = [
            ContractSnapshot(
                occ_symbol=s["occ_symbol"],
                underlying=s["underlying"],
                expiry=_parse_date(s["expiry"]),  # type: ignore[arg-type]
                strike=float(s["strike"]),
                call_put=s["call_put"],
                volume=s.get("volume"),
                open_interest=s.get("open_interest"),
                last_price=s.get("last_price"),
                bid=s.get("bid"),
                ask=s.get("ask"),
                iv=s.get("iv"),
                spot=s.get("spot"),
                asof=asof,
                source="replay",
            )
            for s in raw.get("snapshots", [])
        ]
        occ_rows = [
            OccDailyRow(
                session_date=_parse_date(r["session_date"]),  # type: ignore[arg-type]
                occ_symbol=r["occ_symbol"],
                underlying=r["underlying"],
                expiry=_parse_date(r["expiry"]),  # type: ignore[arg-type]
                strike=float(r["strike"]),
                call_put=r["call_put"],
                volume=r.get("volume"),
                open_interest=r.get("open_interest"),
            )
            for r in raw.get("occ_history", [])
        ]
        return MarketBundle(asof=asof, underlyings=underlyings, snapshots=snapshots, occ_rows=occ_rows, source="replay")

    def load_later_marks(self) -> list[dict]:
        path = self.dir / "market_bundle.json"
        raw = json.loads(path.read_text())
        return list(raw.get("later_marks") or [])

    def load_news(self) -> list[dict]:
        path = self.dir / "market_bundle.json"
        raw = json.loads(path.read_text())
        return list(raw.get("news") or [])

    def discover(self) -> list[str]:
        return [u.symbol for u in self.load_bundle().underlyings]

    def fetch_underlying(self, symbol: str) -> UnderlyingInfo | None:
        for u in self.load_bundle().underlyings:
            if u.symbol == symbol.upper():
                return u
        return None

    def fetch_chain(self, symbol: str) -> list[ContractSnapshot]:
        return [s for s in self.load_bundle().snapshots if s.underlying == symbol.upper()]

    def fetch_occ_oi(self, symbol: str) -> list[OccDailyRow]:
        return [r for r in self.load_bundle().occ_rows if r.underlying == symbol.upper()]
