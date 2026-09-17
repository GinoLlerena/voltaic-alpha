# Units and the environment contract

`CIIP-I-016`. Two units here previously existed only on the deployed host. A
rebuild could not restore what was never captured, and on 10 September a rebuild
did exactly that.

## What lives where

Every unit lives here, and only here. `scripts/restore_hosted_demo.sh` calls
`deploy/install_units.sh` rather than writing any unit of its own.

| Unit | Purpose |
|---|---|
| `options-alpha-worker.service` | the base unit `arm_worker.sh` overrides |
| `options-alpha.service` | the Streamlit dashboard |
| `options-alpha-api.service` | the read-only presentation API, loopback only |
| `options-alpha-port80.service` | redirects 80 to 8501 |
| `options-alpha-backup.{service,timer}` | hourly verified dump |
| `options-alpha-watchdog.{service,timer}` | five-minute liveness check |

### What the consolidation found

Five units had lived as heredocs in the restore script while the host ran
different text, and **all five differed**. Two differences were functional:

- the deployed watchdog had lost `--record`, so it detected and printed while the
  durable incident record — the one every other integrity failure lands in —
  never heard about it;
- the restore script's port 80 unit interpolated nothing. Its heredoc is quoted,
  so it wrote a literal `$PUBLIC_PORT` into the unit, and systemd does not expand
  shell variables in `ExecStart`. A host rebuilt from that script would have got
  a redirect unit that could not work. The host's working copy had literal ports,
  so it was written by something else — which is the drift itself.

The remaining three differed in description text, `AccuracySec`, `After=`, and
the `BACKUP_KEEP=12` retention that existed only on the host. The committed units
take the host's working text plus the watchdog's `--record`.

Timers are enabled **and started** by the installer: enabling alone leaves a
rebuilt host with no backups and no watchdog until something reboots it.

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

**The dashboard's "read-only" is enforced twice.** In code, by
`scripts/check_no_write_path.py`, which parses the tree to prove no broker write
can be expressed outside the single named gateway file. And in the database, by
the grant: `DASHBOARD_DATABASE_URL` resolves to `options_alpha_ro`, which holds
`SELECT` and nothing else.

That second half is new as of `CIIP-I-017`. Until then both URLs resolved to the
same `options_alpha` role, which holds `INSERT/UPDATE/DELETE/TRUNCATE` on every
table — the separate environment file had the shape of least authority without
the substance.

`deploy/create_readonly_role.sh` creates or re-keys the role and repoints the
env file; `deploy/verify_readonly_role.sh` proves the property and **exits
non-zero if any write succeeds**, so it is a gate after a rebuild rather than
something a human skims. The writes it attempts are real: a check that cannot
fail proves nothing.

`ALTER DEFAULT PRIVILEGES` is set for role `options_alpha`, so a table created
by a future migration is readable by the dashboard without re-running anything.
