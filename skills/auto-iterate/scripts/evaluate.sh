#!/bin/bash
# ============================================================
# auto-iterate: 评估辅助脚本
# 支持 4 种目标类型：skill / skill-full / memory / code
# ============================================================

set -euo pipefail

readonly USAGE="Usage: evaluate.sh <skill|skill-full|memory|code> <target-path> [eval-command]"
TARGET_TYPE="${1:?$USAGE}"
TARGET_PATH="${2:?$USAGE}"
readonly TARGET_TYPE TARGET_PATH
EVAL_CMD="${3:-}"
readonly EVAL_CMD

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly SCRIPT_DIR

case "$TARGET_TYPE" in
  skill)
    # 检查 skill 结构完整性（基本检查）
    echo "=== Skill Structure Check ==="
    if [ ! -f "$TARGET_PATH" ]; then
      echo "ERROR: Target file not found: $TARGET_PATH"
      echo "score: 0"
      exit 1
    fi

    # 检查 frontmatter
    has_frontmatter=$(head -1 "$TARGET_PATH" | grep -c "^---" || true)
    has_name=$(grep -c "^name:" "$TARGET_PATH" || true)
    has_description=$(grep -c "^description:" "$TARGET_PATH" || true)

    echo "frontmatter: $has_frontmatter"
    echo "name_field: $has_name"
    echo "description_field: $has_description"
    echo "line_count: $(wc -l < "$TARGET_PATH")"
    echo "word_count: $(wc -w < "$TARGET_PATH")"
    ;;

  skill-full)
    # 委托给 evaluate_skill_full.py 进行复合评估
    echo "=== Skill-Full Composite Evaluation ==="
    if [ ! -d "$TARGET_PATH" ]; then
      echo "ERROR: Target directory not found: $TARGET_PATH"
      echo "score: 0"
      exit 1
    fi
    python3 "${SCRIPT_DIR}/evaluate_skill_full.py" "$TARGET_PATH"
    ;;

  memory)
    # 检查记忆目录完整性
    echo "=== Memory Directory Check ==="
    if [ ! -d "$TARGET_PATH" ]; then
      echo "ERROR: Target directory not found: $TARGET_PATH"
      echo "score: 0"
      exit 1
    fi

    total_files=$(find "$TARGET_PATH" -name "*.md" -not -name "WhoAmI.md" -not -name "MEMORY.md" -not -name "trigger-map.md" -not -name "role.md" -not -name "INDEX.md" | wc -l)
    has_memory_index=$([ -f "$TARGET_PATH/MEMORY.md" ] && echo 1 || echo 0)

    echo "total_memory_files: $total_files"
    echo "has_memory_index: $has_memory_index"

    if [ -f "$TARGET_PATH/MEMORY.md" ]; then
      index_entries=$(grep -c "\.md" "$TARGET_PATH/MEMORY.md" || true)
      echo "index_entries: $index_entries"
    fi
    ;;

  code)
    # 用户指定的评估命令
    echo "=== Code Evaluation ==="
    if [ -z "$EVAL_CMD" ]; then
      echo "ERROR: eval-command required for code target"
      exit 1
    fi
    eval "$EVAL_CMD"
    ;;

  *)
    echo "ERROR: Unknown target type: $TARGET_TYPE"
    echo "$USAGE"
    exit 1
    ;;
esac
