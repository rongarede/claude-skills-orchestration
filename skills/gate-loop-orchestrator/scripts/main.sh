#!/usr/bin/env bash
set -euo pipefail

cmd="${1:-}"
shift || true

case "$cmd" in
  init)
    echo "[gate-loop] init"
    echo "- tips: run discover_review_resources.sh to auto-select reviewer"
    ;;
  discover)
    bash "$(dirname "$0")/discover_review_resources.sh"
    ;;
  *)
    echo "usage:"
    echo "  main.sh init --repo <repo> --todo <todo.md> --gate <gates.md> --phase-start N --phase-end M"
    echo "  main.sh discover"
    exit 1
    ;;
esac
