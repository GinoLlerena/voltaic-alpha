#!/bin/bash
# Full H0 validation. Runs every gate the release depends on, in order, and
# stops at the first failure. Intended to be the single command a reviewer runs.
set -euo pipefail
cd "$(dirname "$0")/.."

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
step() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# `cmd && pass` does NOT trip errexit when cmd fails: in an AND-OR list, only
# the final command is subject to `set -e`. Written that way, this script once
# printed "All gates passed" while the secret scan was failing. Every gate now
# goes through check(), which exits explicitly.
check() {
  local label="$1"; shift
  if "$@"; then pass "$label"; else
    printf '  \033[31mFAIL\033[0m  %s\n' "$label" >&2
    exit 1
  fi
}

quiet() { "$@" >/dev/null 2>&1; }

secret_scan() {
  git ls-files -z | grep -zvE '^(uv\.lock|\.secrets\.baseline)$' \
    | xargs -0 uv run detect-secrets-hook --baseline .secrets.baseline >/dev/null
}

deterministic_replay() {
  local a b
  a=$(uv run python -m options_alpha_lab.replay \
        --database-url "sqlite+pysqlite:///:memory:" | grep 'decision hash')
  b=$(uv run python -m options_alpha_lab.replay \
        --database-url "sqlite+pysqlite:///:memory:" | grep 'decision hash')
  [ -n "$a" ] && [ "$a" = "$b" ]
}

step "1. Lint"
check "ruff" quiet uv run ruff check .

step "2. Type check"
check "mypy strict" quiet uv run mypy

step "3. Offline suite"
check "all offline tests" quiet uv run pytest -q

step "4. Execution firewall boundary"
check "no broker write outside the gateway" \
  quiet uv run python scripts/check_no_write_path.py src

step "5. Frozen replay"
rm -f /tmp/oa_validation.db
check "both H0 fixtures replay into a durable trace" \
  quiet uv run python -m options_alpha_lab.replay \
  --database-url "sqlite+pysqlite:////tmp/oa_validation.db"

step "6. Replay determinism"
check "identical decision hashes across runs" deterministic_replay

step "7. Evidence database"
check "judge evidence database builds" quiet uv run python scripts/build_demo_db.py

step "8. Secret scan"
check "no secret in version control" secret_scan

step "9. Dependency audit"
check "no known vulnerabilities" quiet uv run pip-audit

printf '\n\033[32mAll H0 validation gates passed.\033[0m\n'
printf 'Not covered here, because they need credentials or a network:\n'
printf '  - live read path      uv run python -m options_alpha_lab.freeze\n'
printf '  - model ablation      uv run python -m options_alpha_lab.ablation <snapshot>\n'
printf '  - Paper lifecycle     uv run python -m options_alpha_lab.lifecycle <snapshot> --submit\n'
