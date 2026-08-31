"""Validated runtime configuration with fail-closed safety modes.

Implements implementation plan section 13 and Phase 0 section 4. Every rule here
exists to make an unsafe combination impossible to express, rather than merely
discouraged: a missing mode, a live endpoint, or write authority outside
``paper_execute`` raises at startup instead of surfacing at the first order.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .architecture.contracts import BotMode, SpreadStrategy

# Frozen by the Phase 0 record, section 3. Widening either set is a scope
# decision recorded in the decision log, never a configuration change.
H0_ALLOWED_UNDERLYINGS: frozenset[str] = frozenset({"SPY"})
H0_ALLOWED_STRATEGIES: frozenset[SpreadStrategy] = frozenset(
    {
        SpreadStrategy.BULL_CALL_DEBIT_SPREAD,
        SpreadStrategy.BEAR_PUT_DEBIT_SPREAD,
    }
)

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


class ConfigurationError(ValueError):
    """Raised when the environment cannot produce a safe configuration."""


def _require_bool(env: Mapping[str, str], key: str, *, default: str | None = None) -> bool:
    raw = env.get(key, default)
    if raw is None or not raw.strip():
        raise ConfigurationError(f"{key} must be set explicitly")
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigurationError(f"{key} must be a boolean, got {raw!r}")


@dataclass(frozen=True)
class Settings:
    """A configuration that has already been proven safe.

    Holding an instance of this class is evidence that every check below passed.
    Components therefore never re-derive safety from raw environment variables.
    """

    bot_mode: BotMode
    alpaca_paper_trade: bool
    alpaca_trading_enabled: bool
    require_operator_approval: bool
    database_url: str
    policy_version: str
    runtime_version: str
    allowed_underlyings: frozenset[str] = H0_ALLOWED_UNDERLYINGS
    allowed_strategies: frozenset[SpreadStrategy] = H0_ALLOWED_STRATEGIES

    @property
    def may_write_orders(self) -> bool:
        """The single place that answers whether a broker write is permitted."""
        return (
            self.bot_mode is BotMode.PAPER_EXECUTE
            and self.alpaca_trading_enabled
            and self.alpaca_paper_trade
        )

    def require_allowed_underlying(self, symbol: str) -> None:
        if symbol.strip().upper() not in self.allowed_underlyings:
            raise ConfigurationError(
                f"{symbol!r} is outside the H0 allowlist {sorted(self.allowed_underlyings)}"
            )

    def require_allowed_strategy(self, strategy: SpreadStrategy) -> None:
        if strategy not in self.allowed_strategies:
            raise ConfigurationError(f"{strategy.value} is outside the H0 structure allowlist")


def load_env_file(path: str | Path = ".env") -> dict[str, str]:
    """Parse a ``.env`` file into a mapping.

    Values may be quote-wrapped by ``scripts/configure_secrets.py``. The quotes
    are not part of the value: a quoted API key authenticates as a 401, and the
    failure looks like an expired credential rather than a parsing bug.
    """
    values: dict[str, str] = {}
    file_path = Path(path)
    if not file_path.exists():
        return values
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def resolved_env(path: str | Path = ".env") -> dict[str, str]:
    """`.env` values overlaid by the process environment.

    The process environment wins, which is the conventional dotenv precedence and
    the only way an operator can override a value for one run without editing a
    file. Reading the file alone silently ignored `OPENAI_MODEL=... command`,
    which looked like the override had been applied when it had not.
    """
    merged = load_env_file(path)
    merged.update({key: value for key, value in os.environ.items() if value})
    return merged


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings from the environment, refusing every unsafe combination."""
    source: Mapping[str, str] = os.environ if env is None else env

    raw_mode = source.get("BOT_MODE", "").strip()
    if not raw_mode:
        raise ConfigurationError(
            "BOT_MODE must be set explicitly to one of: "
            + ", ".join(mode.value for mode in BotMode)
        )
    try:
        bot_mode = BotMode(raw_mode)
    except ValueError as exc:
        raise ConfigurationError(
            f"BOT_MODE {raw_mode!r} is unknown; expected one of: "
            + ", ".join(mode.value for mode in BotMode)
        ) from exc

    paper = _require_bool(source, "ALPACA_PAPER_TRADE", default="true")
    if not paper:
        raise ConfigurationError(
            "ALPACA_PAPER_TRADE must be true. This project has no live authority, "
            "and a live endpoint is not a configurable option."
        )

    trading_enabled = _require_bool(source, "ALPACA_TRADING_ENABLED", default="false")
    if trading_enabled and bot_mode is not BotMode.PAPER_EXECUTE:
        raise ConfigurationError(
            f"ALPACA_TRADING_ENABLED cannot be true in {bot_mode.value} mode. "
            "Write authority exists only in paper_execute."
        )

    database_url = source.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigurationError("DATABASE_URL must be set")
    if database_url.startswith(("postgres://", "postgresql://")):
        raise ConfigurationError(
            "DATABASE_URL must name its driver explicitly, for example "
            "postgresql+psycopg://<user>:<password>@<host>:5432/<database>"
        )

    return Settings(
        bot_mode=bot_mode,
        alpaca_paper_trade=paper,
        alpaca_trading_enabled=trading_enabled,
        require_operator_approval=_require_bool(
            source, "REQUIRE_OPERATOR_APPROVAL", default="true"
        ),
        database_url=database_url,
        policy_version=source.get("POLICY_VERSION", "h0-provisional-1").strip(),
        runtime_version=source.get("RUNTIME_VERSION", "0.1.0").strip(),
    )
