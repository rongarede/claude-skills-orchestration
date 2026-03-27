#!/bin/bash
# skill-snapshot restore - 恢复技能到指定版本（支持分类目录）

set -e
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

SKILL_NAME="$1"
VERSION="$2"
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
    echo "用法: restore.sh <skill-name> [version]"
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

# 获取可用版本（兼容新旧格式）
NEW_TAGS=$(git tag -l "$CATEGORY/$SKILL_NAME/v*" 2>/dev/null | sort -V)
OLD_TAGS=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V)

# 合并并去重
AVAILABLE_TAGS=$(echo -e "$NEW_TAGS\n$OLD_TAGS" | grep -v "^$" | sort -V | uniq)

if [ -z "$AVAILABLE_TAGS" ]; then
    echo "错误: 没有找到 $SKILL_NAME 的快照"
    exit 1
fi

# 如果未指定版本，列出可用版本
if [ -z "$VERSION" ]; then
    echo "=== $SKILL_NAME 可用版本 ==="
    echo "分类: $CATEGORY"
    echo ""
    for tag in $AVAILABLE_TAGS; do
        # 提取版本号（兼容新旧格式）
        if [[ "$tag" == *"/$SKILL_NAME/"* ]]; then
            ver=$(echo "$tag" | sed "s|.*/||")
        else
            ver=$(echo "$tag" | sed "s|$SKILL_NAME/||")
        fi
        msg=$(git tag -l "$tag" -n1 | sed "s|$tag ||")
        date=$(git log -1 --format="%ci" "$tag" 2>/dev/null | cut -d' ' -f1)
        echo "  $ver - $date - $msg"
    done
    echo ""
    echo "请指定要恢复的版本，如: restore $SKILL_NAME v2"
    exit 0
fi

# 查找匹配的 tag（优先新格式）
TAG_NAME=""
if git tag -l "$CATEGORY/$SKILL_NAME/$VERSION" | grep -q "$VERSION"; then
    TAG_NAME="$CATEGORY/$SKILL_NAME/$VERSION"
elif git tag -l "$SKILL_NAME/$VERSION" | grep -q "$VERSION"; then
    TAG_NAME="$SKILL_NAME/$VERSION"
fi

# 检查版本是否存在
if [ -z "$TAG_NAME" ]; then
    echo "错误: 版本不存在: $VERSION"
    echo "可用版本:"
    for tag in $AVAILABLE_TAGS; do
        if [[ "$tag" == *"/$SKILL_NAME/"* ]]; then
            ver=$(echo "$tag" | sed "s|.*/||")
        else
            ver=$(echo "$tag" | sed "s|$SKILL_NAME/||")
        fi
        echo "  $ver"
    done
    exit 1
fi

SKILL_PATH="$SKILLS_DIR/$SKILL_NAME"

# 检查目标是否为符号链接
if [ -L "$SKILL_PATH" ]; then
    echo "错误: $SKILL_NAME 是符号链接（外部安装），不支持恢复"
    exit 1
fi

echo "=== 恢复快照 ==="
echo "技能: $SKILL_NAME"
echo "分类: $CATEGORY"
echo "版本: $VERSION"
echo ""

# 备份当前版本（如果存在且有变化）
if [ -d "$SKILL_PATH" ]; then
    BACKUP_DIR="$SKILLS_DIR/.snapshot-backup"
    mkdir -p "$BACKUP_DIR"
    BACKUP_NAME="$SKILL_NAME-$(date '+%Y%m%d%H%M%S')"
    cp -r "$SKILL_PATH" "$BACKUP_DIR/$BACKUP_NAME"
    echo "→ 当前版本已备份到: .snapshot-backup/$BACKUP_NAME"
fi

# Checkout 到指定 tag
git checkout --quiet "$TAG_NAME"

# 确定源目录（兼容新旧格式）
if [[ "$TAG_NAME" == *"/$SKILL_NAME/"* ]]; then
    SRC_DIR="$CATEGORY/$SKILL_NAME"
else
    SRC_DIR="$SKILL_NAME"
fi

# 复制到 skills 目录
rm -rf "$SKILL_PATH"
mkdir -p "$SKILL_PATH"
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='.DS_Store' \
    "$LOCAL_REPO/$SRC_DIR/" "$SKILL_PATH/"

# 切回 main
git checkout --quiet main

echo "✓ 已恢复到 $TAG_NAME"
echo "→ 技能位置: $SKILL_PATH"
