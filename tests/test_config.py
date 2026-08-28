"""Configuration must make unsafe combinations impossible to express."""

from __future__ import annotations

import unittest

from options_alpha_lab.architecture.contracts import BotMode, SpreadStrategy
from options_alpha_lab.config import ConfigurationError, load_settings

BASE = {
    "BOT_MODE": "observe",
    "ALPACA_PAPER_TRADE": "true",
    "ALPACA_TRADING_ENABLED": "false",
    "DATABASE_URL": "sqlite+pysqlite:///:memory:",
}


def env(**overrides: str) -> dict[str, str]:
    merged = dict(BASE)
    for key, value in overrides.items():
        if value == "__unset__":
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


class ConfigurationTests(unittest.TestCase):
    def test_missing_bot_mode_fails_startup(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            load_settings(env(BOT_MODE="__unset__"))
        self.assertIn("BOT_MODE", str(ctx.exception))

    def test_unknown_bot_mode_fails_startup(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_settings(env(BOT_MODE="yolo"))

    def test_live_endpoint_is_not_configurable(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            load_settings(env(ALPACA_PAPER_TRADE="false"))
        self.assertIn("live", str(ctx.exception).lower())

    def test_trading_defaults_off(self) -> None:
        settings = load_settings(env(ALPACA_TRADING_ENABLED="__unset__"))
        self.assertFalse(settings.alpaca_trading_enabled)
        self.assertFalse(settings.may_write_orders)

    def test_write_authority_cannot_exist_outside_paper_execute(self) -> None:
        for mode in ("observe", "recommend"):
            with self.subTest(mode=mode):
                with self.assertRaises(ConfigurationError):
                    load_settings(env(BOT_MODE=mode, ALPACA_TRADING_ENABLED="true"))

    def test_paper_execute_with_trading_enabled_may_write(self) -> None:
        settings = load_settings(
            env(BOT_MODE="paper_execute", ALPACA_TRADING_ENABLED="true")
        )
        self.assertIs(settings.bot_mode, BotMode.PAPER_EXECUTE)
        self.assertTrue(settings.may_write_orders)

    def test_paper_execute_without_trading_enabled_may_not_write(self) -> None:
        settings = load_settings(env(BOT_MODE="paper_execute"))
        self.assertFalse(settings.may_write_orders)

    def test_database_url_required(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_settings(env(DATABASE_URL="__unset__"))

    def test_database_url_must_name_its_driver(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_settings(env(DATABASE_URL="postgresql://localhost:5432/db"))

    def test_non_boolean_flag_is_rejected_rather_than_coerced(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_settings(env(ALPACA_TRADING_ENABLED="maybe"))

    def test_operator_approval_defaults_on(self) -> None:
        # Fallback F-04: safe under a human-approval rule and an autonomy rule.
        self.assertTrue(load_settings(env()).require_operator_approval)

    def test_h0_allowlist_rejects_symbols_outside_spy(self) -> None:
        settings = load_settings(env())
        settings.require_allowed_underlying("spy")
        for symbol in ("QQQ", "NVDA", "IWM"):
            with self.subTest(symbol=symbol), self.assertRaises(ConfigurationError):
                settings.require_allowed_underlying(symbol)

    def test_h0_allowlist_accepts_only_debit_verticals(self) -> None:
        settings = load_settings(env())
        for strategy in SpreadStrategy:
            settings.require_allowed_strategy(strategy)




class EnvPrecedenceTests(unittest.TestCase):
    """The process environment must override .env, or an override silently no-ops."""

    def test_process_environment_wins_over_the_file(self) -> None:
        import os
        import tempfile
        from pathlib import Path

        from options_alpha_lab.config import load_env_file, resolved_env

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('OPENAI_MODEL="from-file"\nONLY_IN_FILE=yes\n', encoding="utf-8")
            self.assertEqual(load_env_file(path)["OPENAI_MODEL"], "from-file")

            os.environ["OPENAI_MODEL"] = "from-process"
            try:
                merged = resolved_env(path)
                self.assertEqual(merged["OPENAI_MODEL"], "from-process")
                # Values only present in the file still come through.
                self.assertEqual(merged["ONLY_IN_FILE"], "yes")
            finally:
                del os.environ["OPENAI_MODEL"]

    def test_quotes_are_stripped_from_file_values(self) -> None:
        import tempfile
        from pathlib import Path

        from options_alpha_lab.config import load_env_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("A=\"quoted\"\nB='single'\nC=bare\n", encoding="utf-8")
            values = load_env_file(path)
        self.assertEqual(values, {"A": "quoted", "B": "single", "C": "bare"})


if __name__ == "__main__":
    unittest.main()
