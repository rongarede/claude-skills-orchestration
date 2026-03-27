#!/bin/bash
# Codex Bridge with Context + Agent Injection
# 用法:
#   codex-agent.sh "任务描述" --cd /path/to/project
#   codex-agent.sh "任务描述" --cd /path/to/project --agent security-reviewer
#   codex-agent.sh "任务描述" --cd /path/to/project --agent planner --session SESSION_ID

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRIDGE_SCRIPT="$SCRIPT_DIR/codex_bridge.py"
AGENTS_DIR="/Users/bit/.claude/agents"

# 解析参数
TASK=""
AGENT=""
SESSION_ID=""
PROJECT_DIR=""
CONTEXT_FILE=""
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --agent|-a)
            AGENT="$2"
            shift 2
            ;;
        --session|-s)
            SESSION_ID="$2"
            shift 2
            ;;
        --cd)
            PROJECT_DIR="$2"
            shift 2
            ;;
        --context|-c)
            CONTEXT_FILE="$2"
            shift 2
            ;;
        --sandbox)
            EXTRA_ARGS="$EXTRA_ARGS --sandbox $2"
            shift 2
            ;;
        --yolo)
            EXTRA_ARGS="$EXTRA_ARGS --yolo"
            shift
            ;;
        --return-all-messages)
            EXTRA_ARGS="$EXTRA_ARGS --return-all-messages"
            shift
            ;;
        *)
            if [ -z "$TASK" ]; then
                TASK="$1"
            fi
            shift
            ;;
    esac
done

# 显示帮助
if [ -z "$TASK" ] || [ -z "$PROJECT_DIR" ]; then
    echo "用法: $0 \"任务描述\" --cd /path/to/project [选项]"
    echo ""
    echo "必需参数:"
    echo "  --cd PATH          项目工作目录"
    echo ""
    echo "可选参数:"
    echo "  --agent NAME       注入 agent 提示词"
    echo "  --session ID       续接会话"
    echo "  --context FILE     自定义上下文文件"
    echo "  --sandbox MODE     沙箱模式 (read-only|workspace-write|danger-full-access)"
    echo "  --yolo             跳过所有确认"
    echo "  --return-all-messages  返回完整消息"
    echo ""
    echo "可用 agents:"
    ls "$AGENTS_DIR"/*.md 2>/dev/null | xargs -I {} basename {} .md | sed 's/^/  - /'
    echo ""
    echo "示例:"
    echo "  $0 \"审查安全\" --cd /project --agent security-reviewer"
    echo "  $0 \"规划功能\" --cd /project --agent planner"
    exit 1
fi

# 加载项目上下文
PROJECT_CONTEXT=""
if [ -n "$CONTEXT_FILE" ] && [ -f "$CONTEXT_FILE" ]; then
    PROJECT_CONTEXT="$(cat "$CONTEXT_FILE")

---
"
    echo "✓ 已加载上下文: $CONTEXT_FILE"
elif [ -f "$PROJECT_DIR/CLAUDE.md" ]; then
    # 自动从 CLAUDE.md 提取关键信息
    PROJECT_CONTEXT="## 项目上下文

$(head -100 "$PROJECT_DIR/CLAUDE.md")

---
"
    echo "✓ 已加载上下文: CLAUDE.md"
elif [ -f "$PROJECT_DIR/AGENTS.md" ]; then
    PROJECT_CONTEXT="## 项目上下文

$(head -100 "$PROJECT_DIR/AGENTS.md")

---
"
    echo "✓ 已加载上下文: AGENTS.md"
fi

# 注入 Agent 提示词
AGENT_PROMPT=""
if [ -n "$AGENT" ]; then
    AGENT_FILE="$AGENTS_DIR/$AGENT.md"
    if [ -f "$AGENT_FILE" ]; then
        # 提取 frontmatter 之后的内容
        AGENT_PROMPT=$(awk '/^---$/{if(++c==2)p=1;next}p' "$AGENT_FILE")
        AGENT_PROMPT="## Agent 角色: $AGENT

$AGENT_PROMPT

---
"
        echo "✓ 已注入 agent: $AGENT"
    else
        echo "⚠ Agent 不存在: $AGENT"
        echo "可用: $(ls "$AGENTS_DIR"/*.md | xargs -I {} basename {} .md | tr '\n' ' ')"
        exit 1
    fi
fi

# 组装完整 PROMPT
FULL_PROMPT="${AGENT_PROMPT}${PROJECT_CONTEXT}## 任务:
${TASK}"

# 执行
if [ -n "$SESSION_ID" ]; then
    python3 "$BRIDGE_SCRIPT" --cd "$PROJECT_DIR" --SESSION_ID "$SESSION_ID" --PROMPT "$FULL_PROMPT" $EXTRA_ARGS
else
    python3 "$BRIDGE_SCRIPT" --cd "$PROJECT_DIR" --PROMPT "$FULL_PROMPT" $EXTRA_ARGS
fi
