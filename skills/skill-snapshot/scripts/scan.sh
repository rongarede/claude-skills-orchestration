#!/bin/bash
# skill-snapshot scan - 扫描技能，判断哪些需要备份（支持分类）

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

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

check_skill() {
    local skill_path="${1%/}"
    local skill_name="$(basename "$skill_path")"

    # 规则 1: archive 目录
    if [ "$skill_name" = "archive" ]; then
        echo "SKIP|$skill_name|归档目录|"
        return
    fi

    # 规则 2: 符号链接（外部安装）
    if [ -L "$skill_path" ]; then
        echo "SKIP|$skill_name|符号链接（外部安装）|"
        return
    fi

    # 规则 3: 快照工具本身
    if [ "$skill_name" = "skill-snapshot" ]; then
        echo "SKIP|$skill_name|快照工具本身|"
        return
    fi

    # 规则 4: 包含 .git（自带版本控制）
    if [ -d "$skill_path/.git" ]; then
        echo "SKIP|$skill_name|自带 Git 版本控制|"
        return
    fi

    # 规则 5: 包含 .venv 或 node_modules（大量依赖）
    if [ -d "$skill_path/.venv" ] || [ -d "$skill_path/node_modules" ]; then
        echo "SKIP|$skill_name|包含依赖目录 (.venv/node_modules)|"
        return
    fi

    # 规则 6: 体积超过 10MB
    local size_kb=$(du -sk "$skill_path" 2>/dev/null | cut -f1)
    if [ "$size_kb" -gt 10240 ]; then
        local size_mb=$((size_kb / 1024))
        echo "SKIP|$skill_name|体积过大 (${size_mb}MB > 10MB)|"
        return
    fi

    # 规则 7: 没有 SKILL.md（可能不是有效技能）
    if [ ! -f "$skill_path/SKILL.md" ]; then
        echo "SKIP|$skill_name|缺少 SKILL.md|"
        return
    fi

    # 通过所有检查，需要备份
    local files=$(find "$skill_path" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')
    local size=$(du -sh "$skill_path" 2>/dev/null | cut -f1)
    local category=$(get_category "$skill_name")

    # 检查是否已有快照（兼容新旧格式）
    local has_snapshot=""
    if [ -d "$LOCAL_REPO/.git" ]; then
        cd "$LOCAL_REPO"
        local new_latest=$(git tag -l "$category/$skill_name/v*" 2>/dev/null | sort -V | tail -1)
        local old_latest=$(git tag -l "$skill_name/v*" 2>/dev/null | sort -V | tail -1)
        if [ -n "$new_latest" ]; then
            has_snapshot="$new_latest"
        elif [ -n "$old_latest" ]; then
            has_snapshot="$old_latest (旧格式)"
        fi
    fi

    echo "BACKUP|$skill_name|$files files, $size|$has_snapshot|$category"
}

echo "=== 技能快照扫描 ==="
echo ""

# 收集结果到临时文件（兼容 bash 3.x）
BACKUP_FILE=$(mktemp)
SKIP_FILE=$(mktemp)
trap "rm -f $BACKUP_FILE $SKIP_FILE" EXIT

for skill_dir in "$SKILLS_DIR"/*/; do
    [ -d "$skill_dir" ] || continue
    result=$(check_skill "$skill_dir")

    type=$(echo "$result" | cut -d'|' -f1)
    if [ "$type" = "BACKUP" ]; then
        echo "$result" >> "$BACKUP_FILE"
    else
        echo "$result" >> "$SKIP_FILE"
    fi
done

# 按分类输出需要备份的
echo "【需要备份】"

# 获取所有分类并排序
CATEGORIES=$(cut -d'|' -f5 "$BACKUP_FILE" 2>/dev/null | sort -u)

TOTAL_BACKUP=0
NEED_BACKUP_FILE=$(mktemp)
trap "rm -f $BACKUP_FILE $SKIP_FILE $NEED_BACKUP_FILE" EXIT

for category in $CATEGORIES; do
    echo ""
    echo "  [$category]"
    grep "|$category$" "$BACKUP_FILE" | while IFS='|' read -r type name info snapshot cat; do
        if [ -n "$snapshot" ]; then
            echo "    ✓ $name ($info) [已有: $snapshot]"
        else
            echo "    ○ $name ($info) [未备份]"
            echo "$name" >> "$NEED_BACKUP_FILE"
        fi
    done
    TOTAL_BACKUP=$((TOTAL_BACKUP + $(grep -c "|$category$" "$BACKUP_FILE" 2>/dev/null || echo 0)))
done

TOTAL_BACKUP=$(wc -l < "$BACKUP_FILE" | tr -d ' ')
TOTAL_SKIP=$(wc -l < "$SKIP_FILE" | tr -d ' ')

echo ""
echo "【跳过】"
if [ "$TOTAL_SKIP" -eq 0 ]; then
    echo "  (无)"
else
    while IFS='|' read -r type name reason rest; do
        echo "  ✗ $name - $reason"
    done < "$SKIP_FILE"
fi

# 统计
echo ""
echo "----------------------------------------"
echo "需要备份: $TOTAL_BACKUP 个"
echo "跳过: $TOTAL_SKIP 个"

# 检查未备份的
NEED_BACKUP_COUNT=$(wc -l < "$NEED_BACKUP_FILE" 2>/dev/null | tr -d ' ')
if [ "$NEED_BACKUP_COUNT" -gt 0 ]; then
    echo ""
    echo "【待备份】$NEED_BACKUP_COUNT 个技能尚未创建快照:"
    while read -r name; do
        echo "  - $name"
    done < "$NEED_BACKUP_FILE"
fi
