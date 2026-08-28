"""Freeze a live read-only observation into a replayable fixture.

The Phase 2 exit gate asks for a *reproducible* evidence pack. Live data is not
reproducible, so the read path writes its observation to disk with the provider
metadata and payload hashes that made it, and every later phase replays that
frozen file. Nothing here submits an order or writes to the broker.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import load_env_file
from .evidence import EvidenceError, build_snapshot
from .hashing import payload_hash
from .providers.alpaca_readonly import ProviderError, ProviderRead, ReadOnlyAlpacaClient
from .snapshot_io import snapshot_to_dict

DEFAULT_OUTPUT_DIR = Path("fixtures/h0/frozen")
# Request a slightly wider window than the policy uses so boundary behaviour is
# observable, then trim to the eligible window before writing.
REQUEST_DTE_LOW = 10
REQUEST_DTE_HIGH = 60
FROZEN_DTE_LOW = 14
FROZEN_DTE_HIGH = 45
FROZEN_STRIKE_WINDOW = Decimal("0.06")


def _read_manifest(reads: dict[str, ProviderRead]) -> dict[str, Any]:
    """Provenance for the frozen observation. No credentials, no headers."""
    return {
        "manifest_version": "h0.1",
        "frozen_at": datetime.now(UTC).isoformat(),
        "reads": {
            name: {
                "provider": read.provider,
                "endpoint": read.endpoint,
                "feed": read.feed,
                "source_time": read.source_time.isoformat() if read.source_time else None,
                "received_time": read.received_time.isoformat(),
                "pages": read.pages,
                "payload_hash": read.payload_hash,
            }
            for name, read in sorted(reads.items())
        },
    }


def freeze(
    symbol: str,
    output_dir: Path,
    *,
    label: str | None = None,
    env_path: str = ".env",
) -> tuple[Path, Path]:
    env = load_env_file(env_path)
    api_key = env.get("ALPACA_API_KEY", "")
    secret_key = env.get("ALPACA_SECRET_KEY", "")

    with ReadOnlyAlpacaClient(api_key, secret_key) as client:
        # Entitlement is discovered, not assumed (`F-06`, `DEC-006`).
        client.option_feed = client.detect_option_feed(symbol)
        client.stock_feed = client.detect_stock_feed(symbol)
        today = date.today()
        reads = {
            "account": client.account(),
            "clock": client.clock(),
            "bars": client.daily_bars(symbol),
            "chain": client.option_chain(
                symbol,
                expiration_gte=(today + timedelta(days=REQUEST_DTE_LOW)).isoformat(),
                expiration_lte=(today + timedelta(days=REQUEST_DTE_HIGH)).isoformat(),
            ),
        }

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    snapshot_id = f"{symbol.lower()}-{label or 'live'}-{stamp}"
    snapshot = build_snapshot(
        snapshot_id=snapshot_id,
        symbol=symbol,
        account_read=reads["account"],
        clock_read=reads["clock"],
        bars_read=reads["bars"],
        chain_read=reads["chain"],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    document = snapshot_to_dict(snapshot)

    # Trim to the eligible window. The filter is declared in the manifest and the
    # untrimmed read hash is retained, so the reduction is auditable rather than
    # a quiet convenience.
    spot = snapshot.underlying_price
    full_chain = document["option_chain"]
    document["option_chain"] = [
        quote
        for quote in full_chain
        if FROZEN_DTE_LOW <= quote["dte"] <= FROZEN_DTE_HIGH
        and abs(quote["strike"] - spot) / spot <= FROZEN_STRIKE_WINDOW
    ]

    manifest = _read_manifest(reads)
    manifest["frozen_chain_filter"] = {
        "dte_low": FROZEN_DTE_LOW,
        "dte_high": FROZEN_DTE_HIGH,
        "strike_window_fraction": str(FROZEN_STRIKE_WINDOW),
        "contracts_read": len(full_chain),
        "contracts_frozen": len(document["option_chain"]),
    }
    manifest["snapshot_input_hash"] = payload_hash(document)

    snapshot_path = output_dir / f"{snapshot_id}.snapshot.json"
    manifest_path = output_dir / f"{snapshot_id}.manifest.json"
    snapshot_path.write_text(
        json.dumps(_jsonify(document), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return snapshot_path, manifest_path


def _jsonify(value: Any) -> Any:
    from decimal import Decimal
    from enum import Enum

    if isinstance(value, Enum):
        return _jsonify(value.value)
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m options_alpha_lab.freeze",
        description="Freeze a live read-only Alpaca observation into a replayable fixture.",
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--label", default=None, help="Label embedded in the snapshot id")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), type=Path)
    args = parser.parse_args(argv)

    try:
        snapshot_path, manifest_path = freeze(args.symbol, Path(args.output_dir), label=args.label)
    except (ProviderError, EvidenceError) as exc:
        print(f"freeze failed: {exc}", file=sys.stderr)
        return 1

    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    print(f"snapshot  {snapshot_path}")
    print(f"manifest  {manifest_path}")
    print(f"  symbol        {document['symbol']} @ {document['underlying_price']}")
    print(f"  signals       {len(document['signals'])}")
    print(f"  option quotes {len(document['option_chain'])}")
    print(f"  data quality  {document['data_quality']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
