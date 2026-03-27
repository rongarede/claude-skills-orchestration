#!/usr/bin/env bash
set -euo pipefail

gate_file=""
phase=""
status=""
decision=""
critical=""
major=""
minor=""
must_fix=""
evidence=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --gate-file) gate_file="$2"; shift 2 ;;
    --phase) phase="$2"; shift 2 ;;
    --status) status="$2"; shift 2 ;;
    --decision) decision="$2"; shift 2 ;;
    --critical) critical="$2"; shift 2 ;;
    --major) major="$2"; shift 2 ;;
    --minor) minor="$2"; shift 2 ;;
    --must-fix) must_fix="$2"; shift 2 ;;
    --evidence) evidence="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$gate_file" && -n "$phase" && -n "$status" ]] || {
  echo "required: --gate-file --phase --status" >&2
  exit 1
}

mkdir -p "$(dirname "$gate_file")"

cat >> "$gate_file" <<REC

### Gate-${phase} Attempt $(date '+%Y%m%d-%H%M%S')

- 状态：\`${status}\`
- 审核结论：${decision}
- Critical: ${critical}
- Major: ${major}
- Minor: ${minor}
- Must-Fix：${must_fix}
- Evidence：${evidence}
REC
