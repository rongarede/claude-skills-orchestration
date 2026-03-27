#!/bin/bash
# Kimi CLI Bridge with Context + Agent Injection
# 用法:
#   kimi-agent.sh "任务描述" --cd /path/to/project
#   kimi-agent.sh "任务描述" --cd /path/to/project --agent security-reviewer
#   kimi-agent.sh "任务描述" --cd /path/to/project --session SESSION_ID

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SESSIONS_DIR="$SKILL_DIR/sessions"
AGENTS_DIR="/Users/bit/.claude/agents"

# 确保 sessions 目录存在
mkdir -p "$SESSIONS_DIR"

# 默认值
TASK=""
AGENT=""
SESSION_ID=""
PROJECT_DIR=""
CONTEXT_FILE=""
MODEL=""
THINKING_MODE=""
YOLO_MODE=false
OUTPUT_FORMAT="text"
SAVE_SESSION=true
TIMEOUT_SECS=120

# ==================== 显示帮助函数 ====================
show_help() {
    cat << 'EOF'
Kimi CLI Bridge - 非交互式调用 Kimi CLI

用法: kimi-agent.sh "任务描述" --cd /path/to/project [选项]

必需参数:
  --cd PATH          项目工作目录

可选参数:
  --agent, -a NAME   注入 agent 提示词
  --session, -s ID   续接会话
  --context, -c FILE 自定义上下文文件
  --model, -m MODEL  指定模型
  --timeout, -t SECS 超时时间 (默认 120 秒)
  --yolo             自动批准所有操作
  --thinking         启用思考模式
  --no-thinking      禁用思考模式
  --output-format    输出格式 (json|text)
  --save             保存会话 (默认)
  --no-save          不保存会话
  --help, -h         显示帮助

可用 agents:
EOF
    ls "$AGENTS_DIR"/*.md 2>/dev/null | xargs -I {} basename {} .md | sed 's/^/  - /' || echo "  (无可用 agents)"

    cat << 'EOF'

示例:
  kimi-agent.sh "审查安全" --cd /project --agent security-reviewer
  kimi-agent.sh "规划功能" --cd /project --agent planner
  kimi-agent.sh "继续对话" --cd /project --session abc123
EOF
}

# ==================== 解析参数 ====================
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
        --model|-m)
            MODEL="$2"
            shift 2
            ;;
        --yolo)
            YOLO_MODE=true
            shift
            ;;
        --thinking)
            THINKING_MODE="--thinking"
            shift
            ;;
        --no-thinking)
            THINKING_MODE="--no-thinking"
            shift
            ;;
        --output-format|-o)
            OUTPUT_FORMAT="$2"
            shift 2
            ;;
        --save)
            SAVE_SESSION=true
            shift
            ;;
        --no-save)
            SAVE_SESSION=false
            shift
            ;;
        --timeout|-t)
            TIMEOUT_SECS="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            if [ -z "$TASK" ]; then
                TASK="$1"
            fi
            shift
            ;;
    esac
done

# 验证必需参数
if [ -z "$TASK" ] || [ -z "$PROJECT_DIR" ]; then
    show_help
    exit 1
fi

# 验证项目目录存在
if [ ! -d "$PROJECT_DIR" ]; then
    echo '{"success": false, "error": "项目目录不存在: '"$PROJECT_DIR"'"}' | jq .
    exit 1
fi

# ==================== 加载项目上下文 ====================
PROJECT_CONTEXT=""
CONTEXT_SOURCE=""

if [ -n "$CONTEXT_FILE" ] && [ -f "$CONTEXT_FILE" ]; then
    PROJECT_CONTEXT="$(cat "$CONTEXT_FILE")"
    CONTEXT_SOURCE="$CONTEXT_FILE"
elif [ -f "$PROJECT_DIR/CLAUDE.md" ]; then
    PROJECT_CONTEXT="$(head -100 "$PROJECT_DIR/CLAUDE.md")"
    CONTEXT_SOURCE="CLAUDE.md"
elif [ -f "$PROJECT_DIR/AGENTS.md" ]; then
    PROJECT_CONTEXT="$(head -100 "$PROJECT_DIR/AGENTS.md")"
    CONTEXT_SOURCE="AGENTS.md"
elif [ -f "$PROJECT_DIR/KIMI.md" ]; then
    PROJECT_CONTEXT="$(head -100 "$PROJECT_DIR/KIMI.md")"
    CONTEXT_SOURCE="KIMI.md"
fi

# ==================== 注入 Agent 提示词 ====================
AGENT_PROMPT=""
if [ -n "$AGENT" ]; then
    AGENT_FILE="$AGENTS_DIR/$AGENT.md"
    if [ -f "$AGENT_FILE" ]; then
        # 提取 frontmatter 之后的内容
        AGENT_PROMPT=$(awk '/^---$/{if(++c==2)p=1;next}p' "$AGENT_FILE")
    else
        echo '{"success": false, "error": "Agent 不存在: '"$AGENT"'"}' | jq .
        exit 1
    fi
fi

# ==================== 组装完整 PROMPT ====================
FULL_PROMPT=""

if [ -n "$AGENT_PROMPT" ]; then
    FULL_PROMPT="## Agent 角色: $AGENT

$AGENT_PROMPT

---

"
fi

if [ -n "$PROJECT_CONTEXT" ]; then
    FULL_PROMPT="${FULL_PROMPT}## 项目上下文 (来源: $CONTEXT_SOURCE)

$PROJECT_CONTEXT

---

"
fi

FULL_PROMPT="${FULL_PROMPT}## 任务:
$TASK"

# ==================== 生成 Session ID ====================
if [ -z "$SESSION_ID" ]; then
    NEW_SESSION_ID="kimi_$(date +%Y%m%d_%H%M%S)_$$"
else
    NEW_SESSION_ID="$SESSION_ID"
fi

# ==================== 构建 Kimi 命令参数 ====================
build_kimi_args() {
    local args=""

    # 工作目录
    args="$args -w \"$PROJECT_DIR\""

    # 模型
    if [ -n "$MODEL" ]; then
        args="$args -m $MODEL"
    fi

    # 思考模式
    if [ -n "$THINKING_MODE" ]; then
        args="$args $THINKING_MODE"
    fi

    # YOLO 模式
    if [ "$YOLO_MODE" = true ]; then
        args="$args --yolo"
    fi

    # 恢复会话
    if [ -n "$SESSION_ID" ]; then
        args="$args -S $SESSION_ID"
    fi

    echo "$args"
}

# ==================== 执行 Kimi ====================
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEMP_OUTPUT=$(mktemp)
TEMP_ERROR=$(mktemp)

# 超时设置（秒）
TIMEOUT=${KIMI_TIMEOUT:-$TIMEOUT_SECS}

# 切换到项目目录执行
cd "$PROJECT_DIR"

# 构建参数
KIMI_ARGS=$(build_kimi_args)

# 执行并捕获输出（带超时）
run_with_timeout() {
    local timeout=$1
    shift

    # 启动后台进程
    "$@" &
    local pid=$!

    # 等待进程完成或超时
    local count=0
    while [ $count -lt $timeout ]; do
        if ! kill -0 $pid 2>/dev/null; then
            # 进程已结束
            wait $pid
            return $?
        fi
        sleep 1
        count=$((count + 1))
    done

    # 超时，杀死进程
    kill $pid 2>/dev/null
    wait $pid 2>/dev/null
    return 124  # 超时退出码
}

set +e
# 使用 kimi -p 参数传递 prompt
run_with_timeout $TIMEOUT kimi -w "$PROJECT_DIR" $THINKING_MODE $([ "$YOLO_MODE" = true ] && echo "--yolo") $([ -n "$MODEL" ] && echo "-m $MODEL") $([ -n "$SESSION_ID" ] && echo "-S $SESSION_ID") -p "$FULL_PROMPT" > "$TEMP_OUTPUT" 2> "$TEMP_ERROR"
EXIT_CODE=$?
set -e

# 检查超时
if [ $EXIT_CODE -eq 124 ]; then
    echo '{"success": false, "error": "Kimi 执行超时 ('"$TIMEOUT"'s)", "exit_code": 124}' | jq .
    rm -f "$TEMP_OUTPUT" "$TEMP_ERROR"
    exit 1
fi

# ==================== 处理输出 ====================
RESPONSE=""
ERROR_MSG=""
SUCCESS=true

if [ $EXIT_CODE -ne 0 ]; then
    SUCCESS=false
    ERROR_MSG=$(cat "$TEMP_ERROR")
fi

# 读取输出
if [ -f "$TEMP_OUTPUT" ] && [ -s "$TEMP_OUTPUT" ]; then
    RESPONSE=$(cat "$TEMP_OUTPUT")
fi

# 如果没有响应内容，标记失败
if [ -z "$RESPONSE" ] && [ "$SUCCESS" = true ]; then
    SUCCESS=false
    ERROR_MSG="Kimi 未返回任何响应"
fi

# ==================== 保存会话 ====================
if [ "$SAVE_SESSION" = true ]; then
    SESSION_FILE="$SESSIONS_DIR/${TIMESTAMP}_${NEW_SESSION_ID}.json"

    # 构建会话记录 JSON
    cat > "$SESSION_FILE" << EOJSON
{
  "session_id": "$NEW_SESSION_ID",
  "timestamp": "$TIMESTAMP",
  "project_dir": "$PROJECT_DIR",
  "agent": "$AGENT",
  "context_source": "$CONTEXT_SOURCE",
  "thinking_mode": "$THINKING_MODE",
  "yolo_mode": $YOLO_MODE,
  "model": "$MODEL",
  "task": $(echo "$TASK" | jq -Rs .),
  "full_prompt": $(echo "$FULL_PROMPT" | jq -Rs .),
  "response": $(echo "$RESPONSE" | jq -Rs .),
  "success": $SUCCESS,
  "error": $(echo "$ERROR_MSG" | jq -Rs .),
  "exit_code": $EXIT_CODE
}
EOJSON
fi

# ==================== 输出结果 ====================
# 清理临时文件
cleanup() {
    rm -f "$TEMP_OUTPUT" "$TEMP_ERROR"
}
trap cleanup EXIT

# 构建输出 JSON
if [ "$SUCCESS" = true ]; then
    # 尝试解析 JSON 响应，如果失败则作为文本处理
    if echo "$RESPONSE" | jq . > /dev/null 2>&1; then
        # 响应是有效 JSON
        cat << EOJSON
{
  "success": true,
  "session_id": "$NEW_SESSION_ID",
  "agent": "$AGENT",
  "context_source": "$CONTEXT_SOURCE",
  "response": $RESPONSE
}
EOJSON
    else
        # 响应是纯文本
        cat << EOJSON
{
  "success": true,
  "session_id": "$NEW_SESSION_ID",
  "agent": "$AGENT",
  "context_source": "$CONTEXT_SOURCE",
  "response": $(echo "$RESPONSE" | jq -Rs .)
}
EOJSON
    fi
else
    cat << EOJSON
{
  "success": false,
  "session_id": "$NEW_SESSION_ID",
  "error": $(echo "$ERROR_MSG" | jq -Rs .),
  "exit_code": $EXIT_CODE
}
EOJSON
fi
