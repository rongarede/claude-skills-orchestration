#!/bin/bash
# skill-snapshot list - 列出快照版本（支持分类目录）

set -e
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

SKILL_NAME="$1"
LOCAL_REPO="$HOME/.claude/skill-snapshots"
CATEGORIES_FILE="$HOME/.claude/skills/skill-snapshot/categories.conf"

# 检查仓库是否已初始化
if [ ! -d "$LOCAL_REPO/.git" ]; then
    echo "错误: 仓库未初始化，请先执行 init"
    exit 1
fi

cd "$LOCAL_REPO"

# 拉取最新 tags
git fetch --tags --quiet 2>/dev/null || true

if [ -z "$SKILL_NAME" ]; then
    # 列出所有技能的快照（按分类分组）
    echo "=== 所有技能快照（按分类）==="
    echo ""

    ALL_TAGS=$(git tag -l 2>/dev/null | sort)

    if [ -z "$ALL_TAGS" ]; then
        echo "暂无快照"
        exit 0
    fi

    # 分离新格式和旧格式
    # 新格式: category/skill/vN (3 段)
    # 旧格式: skill/vN (2 段)

    NEW_FORMAT_TAGS=$(echo "$ALL_TAGS" | grep -E "^[^/]+/[^/]+/v[0-9]+$" || true)
    OLD_FORMAT_TAGS=$(echo "$ALL_TAGS" | grep -E "^[^/]+/v[0-9]+$" || true)

    # 处理新格式 tags
    if [ -n "$NEW_FORMAT_TAGS" ]; then
        CATEGORIES=$(echo "$NEW_FORMAT_TAGS" | cut -d'/' -f1 | sort -u)

        for category in $CATEGORIES; do
            printf "【%s】\n" "$category"

            # 获取该分类下的所有技能
            SKILLS=$(echo "$NEW_FORMAT_TAGS" | grep "^$category/" | cut -d'/' -f2 | sort -u)

            for skill in $SKILLS; do
                SKILL_TAGS=$(git tag -l "$category/$skill/v*" | sort -V)
                COUNT=$(echo "$SKILL_TAGS" | wc -l | tr -d ' ')
                LATEST=$(echo "$SKILL_TAGS" | tail -1 | rev | cut -d'/' -f1 | rev)
                echo "  $skill ($COUNT 个版本, 最新: $LATEST)"
            done
            echo ""
        done
    fi

    # 处理旧格式 tags
    if [ -n "$OLD_FORMAT_TAGS" ]; then
        echo "【uncategorized】(旧格式，建议迁移)"

        OLD_SKILLS=$(echo "$OLD_FORMAT_TAGS" | cut -d'/' -f1 | sort -u)

        for skill in $OLD_SKILLS; do
            SKILL_TAGS=$(git tag -l "$skill/v*" | sort -V)
            COUNT=$(echo "$SKILL_TAGS" | wc -l | tr -d ' ')
            LATEST=$(echo "$SKILL_TAGS" | tail -1 | rev | cut -d'/' -f1 | rev)
            echo "  $skill ($COUNT 个版本, 最新: $LATEST)"
        done
        echo ""
    fi

    echo "查看特定技能: list <skill-name>"
else
    # 列出指定技能的快照
    # 尝试新格式和旧格式
    NEW_TAGS=$(git tag -l "*/$SKILL_NAME/v*" 2>/dev/null | sort -V)
    OLD_TAGS=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V)

    if [ -z "$NEW_TAGS" ] && [ -z "$OLD_TAGS" ]; then
        echo "没有找到 $SKILL_NAME 的快照"
        exit 0
    fi

    # 获取分类
    CATEGORY=""
    if [ -n "$NEW_TAGS" ]; then
        CATEGORY=$(echo "$NEW_TAGS" | head -1 | cut -d'/' -f1)
    fi

    echo "=== $SKILL_NAME 快照历史 ==="
    if [ -n "$CATEGORY" ]; then
        echo "分类: $CATEGORY"
    fi
    echo ""

    # 显示新格式
    if [ -n "$NEW_TAGS" ]; then
        for tag in $NEW_TAGS; do
            ver=$(echo "$tag" | rev | cut -d'/' -f1 | rev)
            msg=$(git tag -l "$tag" -n1 | sed "s|$tag[[:space:]]*||")
            date=$(git log -1 --format="%ci" "$tag" 2>/dev/null | cut -d' ' -f1)
            echo "  $ver - $date - $msg [新格式]"
        done
    fi

    # 显示旧格式
    if [ -n "$OLD_TAGS" ]; then
        for tag in $OLD_TAGS; do
            ver=$(echo "$tag" | rev | cut -d'/' -f1 | rev)
            msg=$(git tag -l "$tag" -n1 | sed "s|$tag[[:space:]]*||")
            date=$(git log -1 --format="%ci" "$tag" 2>/dev/null | cut -d' ' -f1)
            echo "  $ver - $date - $msg [旧格式]"
        done
    fi

    echo ""
    # 确定最新版本
    if [ -n "$NEW_TAGS" ]; then
        LATEST=$(echo "$NEW_TAGS" | tail -1 | rev | cut -d'/' -f1 | rev)
    else
        LATEST=$(echo "$OLD_TAGS" | tail -1 | rev | cut -d'/' -f1 | rev)
    fi
    echo "最新版本: $LATEST"
fi
