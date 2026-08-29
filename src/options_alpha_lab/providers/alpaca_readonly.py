"""A least-privilege, read-only Alpaca client.

This adapter issues HTTP GET requests and nothing else. It is deliberately not
built on ``alpaca_py.TradingClient``: that class carries ``submit_order``,
``cancel_order``, and ``close_position`` as latent capability, and "we chose not
to call them" is a weaker claim than "the object cannot express them". The
execution SDK is introduced in Phase 4, behind the deterministic gateway, and
only there.

Every read is returned wrapped in a :class:`ProviderRead` carrying provider,
feed, endpoint, source time, receipt time, page count, and a payload hash, so a
recorded decision can be traced back to the exact bytes it was made from.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ..hashing import payload_hash

PAPER_TRADING_HOST = "https://paper-api.alpaca.markets"
MARKET_DATA_HOST = "https://data.alpaca.markets"

#: Alpaca returns 403 with this message when the account has no OPRA agreement.
OPRA_UNSIGNED_MESSAGE = "OPRA agreement is not signed"


class ProviderError(RuntimeError):
    """A read failed. Callers fail closed rather than substituting a default."""


class EntitlementError(ProviderError):
    """The account lacks the entitlement a requested feed needs."""


@dataclass(frozen=True)
class ProviderRead:
    """One read, with everything needed to reproduce and date it."""

    provider: str
    endpoint: str
    feed: str
    source_time: datetime | None
    received_time: datetime
    pages: int
    payload: Any
    payload_hash: str = field(default="", compare=False)

    def with_hash(self) -> ProviderRead:
        return ProviderRead(
            provider=self.provider,
            endpoint=self.endpoint,
            feed=self.feed,
            source_time=self.source_time,
            received_time=self.received_time,
            pages=self.pages,
            payload=self.payload,
            payload_hash=payload_hash(_jsonable(self.payload)),
        )


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, float):
        # Provider JSON uses floats; hashing requires exactness, so pin the
        # textual form rather than refusing the read.
        return repr(value)
    return value


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class ReadOnlyAlpacaClient:
    """GET-only Alpaca access. Has no method that can change broker state."""

    provider = "alpaca"

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        option_feed: str = "indicative",
        stock_feed: str = "iex",
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key or not secret_key:
            raise ProviderError("Alpaca credentials are required for read-only access")
        self.option_feed = option_feed
        self.stock_feed = stock_feed
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
                "accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ReadOnlyAlpacaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transport ---------------------------------------------------------
    def _get(self, url: str, params: Mapping[str, Any] | None = None) -> Any:
        try:
            response = self._client.get(url, params=dict(params or {}))
        except httpx.HTTPError as exc:
            raise ProviderError(f"GET {url} failed: {exc}") from exc
        if response.status_code == 403 and OPRA_UNSIGNED_MESSAGE in response.text:
            raise EntitlementError(OPRA_UNSIGNED_MESSAGE)
        if response.status_code >= 400:
            raise ProviderError(f"GET {url} returned {response.status_code}: {response.text[:200]}")
        return response.json()

    def _paged(
        self, url: str, params: Mapping[str, Any], collection: str
    ) -> tuple[list[Any] | dict[str, Any], int]:
        """Follow ``next_page_token`` to completion.

        Partial chains are a silent correctness failure for option selection, so
        pagination is exhausted rather than truncated at the first page.
        """
        merged: dict[str, Any] = dict(params)
        items_list: list[Any] = []
        items_map: dict[str, Any] = {}
        is_mapping = False
        pages = 0
        token: str | None = None
        while True:
            if token:
                merged["page_token"] = token
            body = self._get(url, merged)
            pages += 1
            chunk = body.get(collection) if isinstance(body, dict) else None
            if isinstance(chunk, dict):
                is_mapping = True
                items_map.update(chunk)
            elif isinstance(chunk, list):
                items_list.extend(chunk)
            token = body.get("next_page_token") if isinstance(body, dict) else None
            if not token:
                break
            if pages > 50:
                raise ProviderError(f"GET {url} exceeded 50 pages; refusing to loop")
        return (items_map if is_mapping else items_list), pages

    # -- reads -------------------------------------------------------------
    def account(self) -> ProviderRead:
        received = datetime.now(UTC)
        body = self._get(f"{PAPER_TRADING_HOST}/v2/account")
        return ProviderRead(
            provider=self.provider,
            endpoint="/v2/account",
            feed="paper-trading",
            source_time=received,
            received_time=received,
            pages=1,
            payload=body,
        ).with_hash()

    def clock(self) -> ProviderRead:
        received = datetime.now(UTC)
        body = self._get(f"{PAPER_TRADING_HOST}/v2/clock")
        return ProviderRead(
            provider=self.provider,
            endpoint="/v2/clock",
            feed="paper-trading",
            source_time=_parse_time(body.get("timestamp")),
            received_time=received,
            pages=1,
            payload=body,
        ).with_hash()

    def calendar(self, start: str, end: str) -> ProviderRead:
        """Trading sessions with their open and close times, in Eastern wall clock.

        Only trading days are returned, so a date's absence is itself the answer
        for weekends and holidays.
        """
        received = datetime.now(UTC)
        body = self._get(
            f"{PAPER_TRADING_HOST}/v2/calendar", {"start": start, "end": end}
        )
        return ProviderRead(
            provider=self.provider,
            endpoint="/v2/calendar",
            feed="paper-trading",
            source_time=received,
            received_time=received,
            pages=1,
            payload={"sessions": body},
        ).with_hash()

    def daily_bars(self, symbol: str, limit: int = 1000, lookback_days: int = 400) -> ProviderRead:
        received = datetime.now(UTC)
        # `start` is mandatory in practice: without it Alpaca returns only the
        # current session, which silently starves every moving average.
        start = (received - timedelta(days=lookback_days)).date().isoformat()
        bars, pages = self._paged(
            f"{MARKET_DATA_HOST}/v2/stocks/{symbol}/bars",
            {
                "timeframe": "1Day",
                "limit": limit,
                "feed": self.stock_feed,
                "adjustment": "split",
                "start": start,
            },
            "bars",
        )
        newest = None
        if isinstance(bars, list) and bars:
            newest = _parse_time(bars[-1].get("t"))
        return ProviderRead(
            provider=self.provider,
            endpoint=f"/v2/stocks/{symbol}/bars",
            feed=self.stock_feed,
            source_time=newest,
            received_time=received,
            pages=pages,
            payload={"symbol": symbol, "bars": bars},
        ).with_hash()

    def option_contracts(
        self, underlying: str, *, expiration_gte: str, expiration_lte: str, limit: int = 10000
    ) -> ProviderRead:
        received = datetime.now(UTC)
        contracts, pages = self._paged(
            f"{PAPER_TRADING_HOST}/v2/options/contracts",
            {
                "underlying_symbols": underlying,
                "expiration_date_gte": expiration_gte,
                "expiration_date_lte": expiration_lte,
                "status": "active",
                "limit": limit,
            },
            "option_contracts",
        )
        return ProviderRead(
            provider=self.provider,
            endpoint="/v2/options/contracts",
            feed="paper-trading",
            source_time=received,
            received_time=received,
            pages=pages,
            payload={"underlying": underlying, "option_contracts": contracts},
        ).with_hash()

    def option_chain(
        self, underlying: str, *, expiration_gte: str, expiration_lte: str
    ) -> ProviderRead:
        received = datetime.now(UTC)
        snapshots, pages = self._paged(
            f"{MARKET_DATA_HOST}/v1beta1/options/snapshots/{underlying}",
            {
                "feed": self.option_feed,
                "limit": 1000,
                "expiration_date_gte": expiration_gte,
                "expiration_date_lte": expiration_lte,
            },
            "snapshots",
        )
        newest: datetime | None = None
        if isinstance(snapshots, dict):
            for snap in snapshots.values():
                quote_time = _parse_time((snap.get("latestQuote") or {}).get("t"))
                if quote_time and (newest is None or quote_time > newest):
                    newest = quote_time
        return ProviderRead(
            provider=self.provider,
            endpoint=f"/v1beta1/options/snapshots/{underlying}",
            feed=self.option_feed,
            source_time=newest,
            received_time=received,
            pages=pages,
            payload={"underlying": underlying, "snapshots": snapshots},
        ).with_hash()

    def detect_stock_feed(self, symbol: str = "SPY") -> str:
        """Prefer the consolidated SIP tape when the account is entitled to it."""
        try:
            body = self._get(
                f"{MARKET_DATA_HOST}/v2/stocks/{symbol}/bars",
                {"timeframe": "1Day", "limit": 1, "feed": "sip",
                 "start": (datetime.now(UTC) - timedelta(days=7)).date().isoformat()},
            )
        except ProviderError:
            return "iex"
        return "sip" if isinstance(body, dict) and body.get("bars") else "iex"

    def detect_option_feed(self, underlying: str = "SPY") -> str:
        """Return the best option feed this account is actually entitled to.

        Entitlement is discovered, never assumed: an account that gains OPRA
        later should tighten its freshness policy without a code change.
        """
        try:
            self._get(
                f"{MARKET_DATA_HOST}/v1beta1/options/snapshots/{underlying}",
                {"feed": "opra", "limit": 1},
            )
        except EntitlementError:
            return "indicative"
        except ProviderError:
            return "indicative"
        return "opra"


def iter_snapshot_items(read: ProviderRead) -> Iterator[tuple[str, dict[str, Any]]]:
    snapshots = read.payload.get("snapshots") if isinstance(read.payload, dict) else None
    if isinstance(snapshots, dict):
        for symbol, snap in sorted(snapshots.items()):
            if isinstance(snap, dict):
                yield symbol, snap
