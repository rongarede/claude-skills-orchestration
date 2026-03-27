#!/bin/bash
# ============================================================
# reflex-fuzz: 收集反射系统现状
# ============================================================

set -e

# ==================== 配置 ====================
STATS_FILE="$HOME/mem/mem/workflows/trigger-stats.json"
TRIGGER_MAP="$HOME/mem/mem/workflows/trigger-map.md"
RULES_COPY="$HOME/.claude/rules/trigger-map.md"
POST_HOOK="$HOME/.claude/hooks/post-agent-trigger-stats.py"
PRE_HOOK="$HOME/.claude/hooks/pre-agent-cb-check.py"
CONFIG="$HOME/.claude/hooks/reflex-config.json"

# ==================== 检查依赖 ====================
check_dependencies() {
    command -v jq >/dev/null || { echo "需要 jq: brew install jq"; exit 1; }
    command -v python3 >/dev/null || { echo "需要 python3"; exit 1; }
}

# ==================== 主逻辑 ====================
main() {
    check_dependencies

    echo "## 反射系统现状快照"
    echo ""

    # 统计快照
    echo "### 反射统计"
    echo "| 反射 | 成功 | 失败 | 跳过 | CB | Recovery |"
    echo "|------|------|------|------|-----|----------|"

    python3 -c "
import json
with open('$STATS_FILE') as f:
    data = json.load(f)
rules = data.get('rules', data.get('reflexes', {}))
for name, entry in rules.items():
    s = entry.get('success', 0)
    f = entry.get('failure', 0)
    sk = entry.get('skip', 0)
    cb = entry.get('cb_state', 'CLOSED')
    rh = len(entry.get('recovery_history', []))
    rec = f'{rh} records' if rh > 0 else '—'
    print(f'| {name} | {s} | {f} | {sk} | {cb} | {rec} |')
"

    echo ""

    # 一致性检查
    echo "### 一致性"
    if diff -q "$TRIGGER_MAP" "$RULES_COPY" > /dev/null 2>&1; then
        echo "SSOT vs 副本：一致"
    else
        echo "SSOT vs 副本：有差异"
    fi

    # 语法检查
    echo ""
    echo "### Hook 语法"
    if python3 -c "import py_compile; py_compile.compile('$POST_HOOK', doraise=True)" 2>/dev/null; then
        echo "post-agent-trigger-stats.py: OK"
    else
        echo "post-agent-trigger-stats.py: 语法错误"
    fi
    if python3 -c "import py_compile; py_compile.compile('$PRE_HOOK', doraise=True)" 2>/dev/null; then
        echo "pre-agent-cb-check.py: OK"
    else
        echo "pre-agent-cb-check.py: 语法错误"
    fi
}

main "$@"
