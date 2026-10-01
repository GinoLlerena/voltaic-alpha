#!/bin/bash
# Retired 1 Oct 2026. Use scripts/ship_host.py.
#
# This script shipped a fixed list of paths over SSH:
#   worker:    app.py requirements.txt pyproject.toml README.md src
#   dashboard: the same, plus demo artifacts .streamlit
# It never shipped migrations/ or scripts/. The host consequently ran schema
# revision 0007 with 0008's migration file absent, and drifted from the release
# freeze in a dozen files (deploy-hygiene follow-ups, 21 Sep 2026).
#
# scripts/ship_host.py replaces it: one list of host paths (HOST_PATHS), a dry
# run that shows every difference against the host, Cloud Assistant instead of
# SSH, kept copies of whatever it replaces, and explicit flags - refused during
# the trading day - for a worker restart or a schema migration.
#
# It exits without doing anything, so an old habit cannot ship a partial
# payload again.
set -euo pipefail
cat >&2 <<'EOF'
deploy_worker.sh is retired. Use:

  python3 scripts/ship_host.py                            # dry run: every difference
  python3 scripts/ship_host.py --apply --restart-worker   # deploy the worker (outside the day)
  python3 scripts/ship_host.py --apply --restart options-alpha   # deploy the dashboard
  python3 scripts/ship_host.py --apply --migrate          # when the schema changes
EOF
exit 2
