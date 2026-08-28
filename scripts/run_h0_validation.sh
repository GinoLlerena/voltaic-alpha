#!/bin/bash
# Full H0 validation. Runs every gate the release depends on, in order, and
# stops at the first failure. Intended to be the single command a reviewer runs.
set -euo pipefail
cd "$(dirname "$0")/.."

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

step "1. Lint"
uv run ruff check . >/dev/null && pass "ruff"

step "2. Type check"
uv run mypy >/dev/null && pass "mypy strict"

step "3. Offline suite"
uv run pytest -q >/dev/null && pass "all offline tests"

step "4. Execution firewall boundary"
uv run python scripts/check_no_write_path.py src >/dev/null \
  && pass "no broker write outside the gateway"

step "5. Frozen replay"
rm -f /tmp/oa_validation.db
uv run python -m options_alpha_lab.replay \
  --database-url "sqlite+pysqlite:////tmp/oa_validation.db" >/dev/null \
  && pass "both H0 fixtures replay into a durable trace"

step "6. Replay determinism"
A=$(uv run python -m options_alpha_lab.replay \
      --database-url "sqlite+pysqlite:///:memory:" | grep 'decision hash' | md5)
B=$(uv run python -m options_alpha_lab.replay \
      --database-url "sqlite+pysqlite:///:memory:" | grep 'decision hash' | md5)
[ "$A" = "$B" ] && pass "identical decision hashes across runs"

step "7. Evidence database"
uv run python scripts/build_demo_db.py >/dev/null && pass "judge evidence database builds"

step "8. Secret scan"
git ls-files -z | grep -zv '^uv\.lock$' \
  | xargs -0 uv run detect-secrets-hook --baseline .secrets.baseline >/dev/null \
  && pass "no secret in version control"

step "9. Dependency audit"
uv run pip-audit >/dev/null 2>&1 && pass "no known vulnerabilities"

printf '\n\033[32mAll H0 validation gates passed.\033[0m\n'
printf 'Not covered here, because they need credentials or a network:\n'
printf '  - live read path      uv run python -m options_alpha_lab.freeze\n'
printf '  - model ablation      uv run python -m options_alpha_lab.ablation <snapshot>\n'
printf '  - Paper lifecycle     uv run python -m options_alpha_lab.lifecycle <snapshot> --submit\n'
