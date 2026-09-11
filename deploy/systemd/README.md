# Units and the environment contract

`CIIP-I-016`. Two units here previously existed only on the deployed host. A
rebuild could not restore what was never captured, and on 10 September a rebuild
did exactly that.

## What lives where

| Unit | Defined in | Why |
|---|---|---|
| `options-alpha-worker.service` | **this directory** | the base unit `arm_worker.sh` overrides |
| `options-alpha.service` | **this directory** | the dashboard, previously in no file at all |
| `options-alpha-port80.service` | `scripts/restore_hosted_demo.sh` | written inline during host restore |
| `options-alpha-backup.{service,timer}` | `scripts/restore_hosted_demo.sh` | ditto |
| `options-alpha-watchdog.{service,timer}` | `scripts/restore_hosted_demo.sh` | ditto |

The five inline units are deliberately **not** copied here. Two definitions of
one unit drift, and the drifted copy is discovered at the worst moment. Merging
them into this directory is worth doing, but it is a change to a restore path
that currently works, so it belongs in its own commit with its own verification.

Install what is here with `deploy/install_units.sh`, on the host.

## The environment contract

Neither unit starts without its `EnvironmentFile`. `install_units.sh` refuses to
enable a unit whose file is absent rather than letting systemd fail it at start,
because that failure reads like a code fault and is not one.

**`/etc/options-alpha.env`** — worker. Mode `0600`, root-owned, never in git.

| Key | Notes |
|---|---|
| `DATABASE_URL` | single-writer connection |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Paper credentials |
| `ALPACA_PAPER_TRADE` | `true` |
| `ALPACA_TRADING_ENABLED` | `false` while disarmed; `arm_worker.sh` flips it |
| `OPENAI_API_KEY` | memo generation |
| `BOT_MODE` | `observe` |
| `REQUIRE_OPERATOR_APPROVAL` | `true` |

**`/etc/options-alpha-dashboard.env`** — dashboard. Mode `0600`, root-owned.

| Key | Notes |
|---|---|
| `DASHBOARD_DATABASE_URL` | the dashboard's only variable |

## Two properties that are load-bearing

**The base worker unit is disarmed.** It hard-codes `--mode observe`, which
decides and records but prepares no order and reaches no broker. Arming is a
separate recorded action: `arm_worker.sh` writes a
`10-paper-execute.conf` drop-in that overrides `ExecStart` and supplies an
operator approval token. That is why the base unit belongs in version control —
a drop-in overrides something it assumes is present, and a base unit rebuilt by
hand slightly differently would be inherited silently by the next arming.

`tests/test_deploy_units.py` asserts both halves of this.

**The dashboard's "read-only" is enforced by code, not by the database.** The
unit describes a read-only dashboard, and `scripts/check_no_write_path.py`
parses the tree to prove no broker write can be expressed outside the single
named gateway file. But `DASHBOARD_DATABASE_URL` and `DATABASE_URL` currently
resolve to the **same** Postgres role, `options_alpha`, which holds
`INSERT/UPDATE/DELETE/TRUNCATE` on all 21 tables. The separate env file gives
the shape of least authority without the substance.

This is recorded, not fixed. Granting a genuinely read-only role is a change to
a running service's credentials and wants its own commit — see `CIIP-I-017`.
