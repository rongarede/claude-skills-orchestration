#!/bin/bash
# skill-snapshot migrate - 将旧格式快照迁移到分类目录

set -e
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

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

# 检查仓库是否已初始化
if [ ! -d "$LOCAL_REPO/.git" ]; then
    echo "错误: 仓库未初始化，请先执行 init"
    exit 1
fi

cd "$LOCAL_REPO"

# 拉取最新
git pull --quiet origin main 2>/dev/null || true
git fetch --tags --quiet

echo "=== 迁移旧格式快照到分类目录 ==="
echo ""

# 获取所有旧格式的 tags（skill/vN 格式，不含分类前缀）
OLD_TAGS=$(git tag -l "*" 2>/dev/null | grep -E "^[^/]+/v[0-9]+$" | sort -V)

if [ -z "$OLD_TAGS" ]; then
    echo "没有需要迁移的旧格式快照"
    exit 0
fi

# 按技能分组
OLD_SKILLS=$(echo "$OLD_TAGS" | sed 's|/v[0-9]*||' | sort -u)

echo "发现 $(echo "$OLD_SKILLS" | wc -l | tr -d ' ') 个技能需要迁移:"
for skill in $OLD_SKILLS; do
    category=$(get_category "$skill")
    count=$(echo "$OLD_TAGS" | grep "^$skill/v" | wc -l | tr -d ' ')
    echo "  $skill → $category/ ($count 个版本)"
done
echo ""

read -p "是否继续迁移? (y/N) " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "开始迁移..."

MIGRATED=0
FAILED=0

for skill in $OLD_SKILLS; do
    category=$(get_category "$skill")
    SKILL_TAGS=$(echo "$OLD_TAGS" | grep "^$skill/v" | sort -V)

    echo ""
    echo "迁移 $skill → $category/$skill"

    for old_tag in $SKILL_TAGS; do
        version=$(echo "$old_tag" | sed "s|$skill/||")
        new_tag="$category/$skill/$version"

        # 检查新 tag 是否已存在
        if git tag -l "$new_tag" | grep -q "$new_tag"; then
            echo "  跳过 $version (已存在)"
            continue
        fi

        # 获取旧 tag 的 commit
        commit=$(git rev-list -n 1 "$old_tag")
        msg=$(git tag -l "$old_tag" -n1 | sed "s|$old_tag[[:space:]]*||")

        # 创建新 tag
        git tag -a "$new_tag" "$commit" -m "$msg"
        echo "  ✓ $version → $new_tag"
        ((MIGRATED++))
    done
done

echo ""
echo "推送新 tags..."
git push --tags --quiet origin

echo ""
echo "=== 迁移完成 ==="
echo "迁移: $MIGRATED 个版本"
echo ""
echo "注意: 旧格式 tags 已保留，如需删除请手动执行:"
echo "  git tag -d <old-tag>"
echo "  git push origin :refs/tags/<old-tag>"
