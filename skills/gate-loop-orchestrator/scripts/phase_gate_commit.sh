#!/usr/bin/env bash
set -euo pipefail

repo=""
msg=""
files=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) repo="$2"; shift 2 ;;
    --message) msg="$2"; shift 2 ;;
    --files) shift; while [[ $# -gt 0 ]]; do files+=("$1"); shift; done ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$repo" ]] || { echo "--repo required" >&2; exit 1; }
[[ -n "$msg" ]] || { echo "--message required" >&2; exit 1; }
[[ "${#files[@]}" -gt 0 ]] || { echo "--files required" >&2; exit 1; }

git -C "$repo" add "${files[@]}"

if git -C "$repo" diff --cached --quiet; then
  echo "No staged changes for commit."
  exit 0
fi

git -C "$repo" commit -m "$msg"
