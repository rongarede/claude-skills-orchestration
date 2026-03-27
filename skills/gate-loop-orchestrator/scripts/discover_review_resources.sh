#!/usr/bin/env bash
set -euo pipefail

ROOTS=(
  "$HOME/.claude/skills"
  "$HOME/.agents/skills"
  "$HOME/.codex/skills"
)

echo "== Local Review Subagents =="
if [[ -d "$HOME/.claude/agents" ]]; then
  find "$HOME/.claude/agents" -maxdepth 1 -type f -name "*.md" \
    | awk 'BEGIN{IGNORECASE=1} /review|audit/ {print "- " $0}'
else
  echo "- (none)"
fi

echo
echo "== Local Review Skills =="
found=0
for root in "${ROOTS[@]}"; do
  [[ -d "$root" ]] || continue
  while IFS= read -r skill_md; do
    if grep -Eiq 'review|audit|gate|code-review' "$skill_md"; then
      echo "- $skill_md"
      found=1
    fi
  done < <(find "$root" -maxdepth 2 -type f \( -name 'SKILL.md' -o -name 'skill.md' \))
done

if [[ "$found" -eq 0 ]]; then
  echo "- (none)"
fi

echo
echo "== Recommended Reviewer =="
if [[ -f "$HOME/.claude/agents/reviewer.md" ]]; then
  echo "reviewer-subagent:$HOME/.claude/agents/reviewer.md"
elif [[ -d "$HOME/.claude/skills/requesting-code-review" ]]; then
  echo "review-skill:$HOME/.claude/skills/requesting-code-review"
else
  echo "fallback:explorer-subagent"
fi
