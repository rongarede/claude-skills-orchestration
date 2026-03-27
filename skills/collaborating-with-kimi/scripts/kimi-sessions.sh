#!/bin/bash
# Kimi Session Manager
# 用法:
#   kimi-sessions.sh list              列出所有会话
#   kimi-sessions.sh show <session_id> 查看会话详情
#   kimi-sessions.sh clean [days]      清理旧会话 (默认 7 天)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SESSIONS_DIR="$SKILL_DIR/sessions"

# 确保 sessions 目录存在
mkdir -p "$SESSIONS_DIR"

show_help() {
    cat << 'EOF'
Kimi Session Manager - 管理 Kimi 会话记录

用法:
  kimi-sessions.sh list              列出所有会话
  kimi-sessions.sh show <session_id> 查看会话详情
  kimi-sessions.sh clean [days]      清理旧会话 (默认 7 天)
  kimi-sessions.sh help              显示帮助

示例:
  kimi-sessions.sh list
  kimi-sessions.sh show kimi_20260128_123456_12345
  kimi-sessions.sh clean 7
EOF
}

list_sessions() {
    echo "=== Kimi 会话列表 ==="
    echo ""

    if [ -z "$(ls -A "$SESSIONS_DIR" 2>/dev/null)" ]; then
        echo "暂无会话记录"
        return
    fi

    printf "%-35s %-20s %-15s %s\n" "SESSION_ID" "TIMESTAMP" "AGENT" "SUCCESS"
    printf "%-35s %-20s %-15s %s\n" "----------" "---------" "-----" "-------"

    for file in "$SESSIONS_DIR"/*.json; do
        if [ -f "$file" ]; then
            session_id=$(jq -r '.session_id // "N/A"' "$file")
            timestamp=$(jq -r '.timestamp // "N/A"' "$file")
            agent=$(jq -r '.agent // "-"' "$file")
            success=$(jq -r '.success // "N/A"' "$file")
            printf "%-35s %-20s %-15s %s\n" "$session_id" "$timestamp" "$agent" "$success"
        fi
    done
}

show_session() {
    local session_id="$1"

    if [ -z "$session_id" ]; then
        echo "错误: 请提供 session_id"
        exit 1
    fi

    # 查找匹配的会话文件
    local found=false
    for file in "$SESSIONS_DIR"/*"$session_id"*.json; do
        if [ -f "$file" ]; then
            echo "=== 会话详情: $session_id ==="
            jq . "$file"
            found=true
            break
        fi
    done

    if [ "$found" = false ]; then
        echo "错误: 未找到会话 $session_id"
        exit 1
    fi
}

clean_sessions() {
    local days="${1:-7}"

    echo "清理 $days 天前的会话..."

    local count=0
    local now=$(date +%s)
    local threshold=$((days * 86400))

    for file in "$SESSIONS_DIR"/*.json; do
        if [ -f "$file" ]; then
            local file_time=$(stat -f %m "$file" 2>/dev/null || stat -c %Y "$file" 2>/dev/null)
            local age=$((now - file_time))

            if [ $age -gt $threshold ]; then
                rm -f "$file"
                count=$((count + 1))
            fi
        fi
    done

    echo "已清理 $count 个会话"
}

# 主逻辑
case "${1:-help}" in
    list)
        list_sessions
        ;;
    show)
        show_session "$2"
        ;;
    clean)
        clean_sessions "$2"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "未知命令: $1"
        show_help
        exit 1
        ;;
esac
