#!/bin/bash
# skill-snapshot save - 保存技能快照（支持分类目录）

set -e
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

SKILL_NAME="$1"
MESSAGE="$2"
SKILLS_DIR="$HOME/.claude/skills"
LOCAL_REPO="$HOME/.claude/skill-snapshots"
CATEGORIES_FILE="$HOME/.claude/skills/skill-snapshot/categories.conf"

# 获取技能分类
get_category() {
    local skill="$1"
    if [ -f "$CATEGORIES_FILE" ]; then
        local cat=$(grep "^$skill=" "$CATEGORIES_FILE" 2>/dev/null | cut -d'=' -f2)
        if [ -n "$cat" ]; then
            echo "$cat"
            return
        fi
    fi
    echo "uncategorized"
}

# 参数检查
if [ -z "$SKILL_NAME" ]; then
    echo "错误: 请指定技能名称"
    echo "用法: save.sh <skill-name> [message]"
    exit 1
fi

SKILL_PATH="$SKILLS_DIR/$SKILL_NAME"

# 检查技能是否存在
if [ ! -d "$SKILL_PATH" ]; then
    echo "错误: 技能不存在: $SKILL_PATH"
    exit 1
fi

# 检查是否为符号链接
if [ -L "$SKILL_PATH" ]; then
    echo "错误: $SKILL_NAME 是符号链接（外部安装），不支持快照"
    exit 1
fi

# 检查仓库是否已初始化
if [ ! -d "$LOCAL_REPO/.git" ]; then
    echo "错误: 仓库未初始化，请先执行 init"
    exit 1
fi

cd "$LOCAL_REPO"

# 拉取最新
git pull --quiet origin main 2>/dev/null || true
git fetch --tags --quiet

# 获取分类
CATEGORY=$(get_category "$SKILL_NAME")
DEST_DIR="$CATEGORY/$SKILL_NAME"

# 确定版本号（兼容旧格式和新格式）
OLD_TAGS=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V | tail -1)
NEW_TAGS=$(git tag -l "$CATEGORY/$SKILL_NAME/v*" 2>/dev/null | sort -V | tail -1)

if [ -n "$NEW_TAGS" ]; then
    LAST_NUM=$(echo "$NEW_TAGS" | sed "s|$CATEGORY/$SKILL_NAME/v||")
    NEXT_VERSION="v$((LAST_NUM + 1))"
elif [ -n "$OLD_TAGS" ]; then
    LAST_NUM=$(echo "$OLD_TAGS" | sed "s|$SKILL_NAME/v||")
    NEXT_VERSION="v$((LAST_NUM + 1))"
else
    NEXT_VERSION="v1"
fi

TAG_NAME="$CATEGORY/$SKILL_NAME/$NEXT_VERSION"

# 默认消息
if [ -z "$MESSAGE" ]; then
    MESSAGE="Snapshot at $(date '+%Y-%m-%d %H:%M')"
fi

echo "=== 保存快照 ==="
echo "技能: $SKILL_NAME"
echo "分类: $CATEGORY"
echo "版本: $NEXT_VERSION"
echo "说明: $MESSAGE"
echo ""

# 复制技能目录到分类目录（排除 .git 和 __pycache__）
mkdir -p "$LOCAL_REPO/$CATEGORY"
rm -rf "$LOCAL_REPO/$DEST_DIR"
mkdir -p "$LOCAL_REPO/$DEST_DIR"
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='.DS_Store' \
    "$SKILL_PATH/" "$LOCAL_REPO/$DEST_DIR/"

# Git 操作
git add "$DEST_DIR/"

# 检查是否有变化
if git diff --cached --quiet; then
    echo "✓ 无变化 - 内容与最新快照相同，无需保存"
    LATEST_TAG=$(git tag -l "$CATEGORY/$SKILL_NAME/v*" 2>/dev/null | sort -V | tail -1)
    if [ -z "$LATEST_TAG" ]; then
        LATEST_TAG=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V | tail -1)
    fi
    if [ -n "$LATEST_TAG" ]; then
        echo "→ 最新快照: $LATEST_TAG"
    fi
    exit 0
fi

git commit --quiet -m "[$CATEGORY/$SKILL_NAME] $NEXT_VERSION: $MESSAGE"
git tag -a "$TAG_NAME" -m "$MESSAGE"
git push --quiet origin main
git push --quiet origin "$TAG_NAME"

echo "✓ 快照已保存: $TAG_NAME"
echo "→ 可用 'restore $SKILL_NAME $NEXT_VERSION' 恢复"
