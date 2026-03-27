#!/bin/bash
# gemini-sessions.sh - 管理 Gemini 会话历史
# 用法:
#   gemini-sessions.sh list          列出所有会话
#   gemini-sessions.sh show ID       显示指定会话详情
#   gemini-sessions.sh clean [days]  清理指定天数前的会话

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SESSIONS_DIR="$SKILL_DIR/sessions"

case "$1" in
    list|ls)
        echo "=== Gemini 会话历史 ==="
        echo ""
        if [ -d "$SESSIONS_DIR" ] && [ "$(ls -A "$SESSIONS_DIR" 2>/dev/null)" ]; then
            for f in "$SESSIONS_DIR"/*.json; do
                [ -f "$f" ] || continue
                session_id=$(jq -r '.session_id' "$f" 2>/dev/null)
                timestamp=$(jq -r '.timestamp' "$f" 2>/dev/null)
                task=$(jq -r '.task' "$f" 2>/dev/null | head -c 50)
                success=$(jq -r '.success' "$f" 2>/dev/null)
                agent=$(jq -r '.agent // "none"' "$f" 2>/dev/null)

                status="✓"
                [ "$success" = "false" ] && status="✗"

                echo "[$status] $timestamp | $session_id"
                echo "    Agent: $agent"
                echo "    Task: ${task}..."
                echo ""
            done
        else
            echo "暂无会话记录"
        fi
        ;;

    show|get)
        if [ -z "$2" ]; then
            echo "用法: $0 show <session_id>"
            exit 1
        fi

        # 查找匹配的会话文件
        found=false
        for f in "$SESSIONS_DIR"/*"$2"*.json; do
            [ -f "$f" ] || continue
            found=true
            echo "=== 会话详情 ==="
            jq '.' "$f"
            break
        done

        if [ "$found" = false ]; then
            echo "未找到会话: $2"
            exit 1
        fi
        ;;

    clean)
        days=${2:-7}
        echo "清理 $days 天前的会话..."

        if [ -d "$SESSIONS_DIR" ]; then
            count=$(find "$SESSIONS_DIR" -name "*.json" -mtime +$days | wc -l)
            find "$SESSIONS_DIR" -name "*.json" -mtime +$days -delete
            echo "已删除 $count 个会话文件"
        else
            echo "会话目录不存在"
        fi
        ;;

    *)
        echo "Gemini 会话管理工具"
        echo ""
        echo "用法:"
        echo "  $0 list              列出所有会话"
        echo "  $0 show <id>         显示会话详情"
        echo "  $0 clean [days]      清理旧会话 (默认 7 天)"
        ;;
esac
