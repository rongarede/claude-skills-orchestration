#!/usr/bin/env bash
# Auto-pilot: autonomous execution driver for agent-memory project
# Usage: bash auto-pilot.sh [max_iterations]
#
# Reads plan.md, finds next unchecked step, asks Claude to execute it.
# Stops when all steps are done or max_iterations reached.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLAN_FILE="$SCRIPT_DIR/plan.md"
BLOCKERS_FILE="$SCRIPT_DIR/blockers.md"
LOG_FILE="$SCRIPT_DIR/auto-pilot.log"
MAX_ITERATIONS="${1:-20}"
COOLDOWN=30  # seconds between iterations
FAIL_COUNT=0
MAX_FAILS=3

# Proxy settings
export https_proxy=http://127.0.0.1:7897
export http_proxy=http://127.0.0.1:7897
export all_proxy=socks5://127.0.0.1:7897

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

check_remaining() {
    grep -c '^\- \[ \]' "$PLAN_FILE" 2>/dev/null || echo 0
}

get_next_step() {
    grep -m1 '^\- \[ \]' "$PLAN_FILE" | sed 's/^- \[ \] //'
}

log "=== Auto-pilot started (max $MAX_ITERATIONS iterations) ==="
log "Plan: $PLAN_FILE"

for i in $(seq 1 "$MAX_ITERATIONS"); do
    REMAINING=$(check_remaining)

    if [ "$REMAINING" -eq 0 ]; then
        log "✅ All steps completed! Exiting."
        break
    fi

    NEXT_STEP=$(get_next_step)
    log "--- Iteration $i/$MAX_ITERATIONS | Remaining: $REMAINING | Next: $NEXT_STEP ---"

    # Invoke Claude in headless mode
    PROMPT="You are working on the agent-memory project at ~/.claude/skills/agent-memory/.

Read the plan at $PLAN_FILE. The next step is: \"$NEXT_STEP\"

Execute this step using TDD approach:
1. Write tests first (RED)
2. Implement to pass tests (GREEN)
3. Verify all tests pass
4. If the step has a Gate check, verify it passes
5. Update plan.md: change '- [ ]' to '- [x]' for this step
6. If blocked, write details to $BLOCKERS_FILE and mark the step with [!]

Working directory: $SCRIPT_DIR
Use existing code in scripts/ and tests/ as reference.
Do NOT modify already-completed steps.
After completion, append a progress entry to the project log at /Users/bit/Obsidian/100_Projects/Active/Project_Associative_Memory/Associative_Memory_项目主页.md under '## 进度记录'."

    if claude -p "$PROMPT" \
        --dangerously-skip-permissions \
        --model sonnet \
        --max-budget-usd 0.50 \
        >> "$LOG_FILE" 2>&1; then
        log "✓ Step completed successfully"
        FAIL_COUNT=0
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log "✗ Step failed (fail $FAIL_COUNT/$MAX_FAILS)"

        if [ "$FAIL_COUNT" -ge "$MAX_FAILS" ]; then
            log "⚠️ Max failures reached. Writing blocker and stopping."
            echo "## $(date '+%Y-%m-%d %H:%M')" >> "$BLOCKERS_FILE"
            echo "Step: $NEXT_STEP" >> "$BLOCKERS_FILE"
            echo "Failed $MAX_FAILS times consecutively. Manual intervention needed." >> "$BLOCKERS_FILE"
            echo "" >> "$BLOCKERS_FILE"
            break
        fi
    fi

    log "Cooling down for ${COOLDOWN}s..."
    sleep "$COOLDOWN"
done

FINAL_REMAINING=$(check_remaining)
log "=== Auto-pilot finished. Remaining steps: $FINAL_REMAINING ==="
