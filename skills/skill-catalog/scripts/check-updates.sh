#!/bin/bash
# ============================================================
# skill-catalog check-updates
# 检查已安装的 Claude Code plugins 和外部 skill 仓库是否有更新
# ============================================================

# 注意：兼容 bash 3.x (macOS 默认版本)

# ==================== 配置 ====================
PLUGINS_DIR="$HOME/.claude/plugins"
SKILLS_DIR="$HOME/.claude/skills"
INSTALLED_FILE="$PLUGINS_DIR/installed_plugins.json"
MARKETPLACES_FILE="$PLUGINS_DIR/known_marketplaces.json"
MARKETPLACES_DIR="$PLUGINS_DIR/marketplaces"

# 代理配置（可选）
if [[ -n "$https_proxy" ]]; then
    CURL_PROXY="--proxy $https_proxy"
else
    CURL_PROXY=""
fi

# ==================== 颜色输出 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ==================== 工具函数 ====================
check_dependencies() {
    if ! command -v jq &> /dev/null; then
        echo "错误: 需要安装 jq"
        echo "  brew install jq"
        exit 1
    fi
}

get_github_latest_commit() {
    local repo="$1"
    local branch="${2:-main}"
    local result

    # 尝试使用 gh CLI（如果可用且已认证）
    if command -v gh &> /dev/null; then
        result=$(gh api "repos/$repo/commits/$branch" 2>/dev/null)
    else
        result=$(curl -s $CURL_PROXY "https://api.github.com/repos/$repo/commits/$branch" 2>/dev/null)
    fi

    if echo "$result" | jq -e '.sha' &>/dev/null; then
        local sha=$(echo "$result" | jq -r '.sha[:8]')
        local msg=$(echo "$result" | jq -r '.commit.message | split("\n")[0]')
        local date=$(echo "$result" | jq -r '.commit.author.date[:10]')
        echo "$sha|$msg|$date"
    else
        echo "error|无法获取|N/A"
    fi
}

get_local_git_commit() {
    local dir="$1"
    if [[ -d "$dir/.git" ]]; then
        (cd "$dir" && git rev-parse --short=8 HEAD 2>/dev/null) || echo "N/A"
    else
        echo "N/A"
    fi
}

# ==================== 主逻辑 ====================
check_dependencies

echo -e "${CYAN}=== 🔄 Skill/Plugin 更新检查 ===${NC}"
echo ""

# -------------------- 检查已安装 Plugins --------------------
echo -e "${BLUE}【已安装 Plugins】${NC}"
echo ""

if [[ -f "$INSTALLED_FILE" ]]; then
    plugins=$(jq -r '.plugins | keys[]' "$INSTALLED_FILE" 2>/dev/null)

    printf "%-35s %-12s %-12s %-8s\n" "Plugin" "本地版本" "安装日期" "Commit"
    printf "%-35s %-12s %-12s %-8s\n" "-----------------------------------" "------------" "------------" "--------"

    echo "$plugins" | while IFS= read -r plugin; do
        [[ -z "$plugin" ]] && continue

        version=$(jq -r ".plugins[\"$plugin\"][0].version // \"unknown\"" "$INSTALLED_FILE")
        installed_at=$(jq -r ".plugins[\"$plugin\"][0].installedAt[:10] // \"unknown\"" "$INSTALLED_FILE")
        commit_sha=$(jq -r ".plugins[\"$plugin\"][0].gitCommitSha[:8] // \"N/A\"" "$INSTALLED_FILE")

        printf "%-35s %-12s %-12s %-8s\n" "$plugin" "$version" "$installed_at" "$commit_sha"
    done
else
    echo "  未找到已安装 plugins 配置文件"
fi

echo ""

# -------------------- 检查 Marketplaces (外部 Skill 仓库) --------------------
echo -e "${BLUE}【Marketplaces / 外部 Skill 仓库】${NC}"
echo ""

if [[ -f "$MARKETPLACES_FILE" ]]; then
    printf "%-25s %-35s %-10s %-10s %-12s\n" "名称" "GitHub 仓库" "本地" "远端" "状态"
    printf "%-25s %-35s %-10s %-10s %-12s\n" "-------------------------" "-----------------------------------" "----------" "----------" "------------"

    marketplaces=$(jq -r 'keys[]' "$MARKETPLACES_FILE" 2>/dev/null)

    outdated_list=""

    echo "$marketplaces" | while IFS= read -r marketplace; do
        [[ -z "$marketplace" ]] && continue

        repo=$(jq -r ".[\"$marketplace\"].source.repo // \"unknown\"" "$MARKETPLACES_FILE")
        install_loc=$(jq -r ".[\"$marketplace\"].installLocation // \"\"" "$MARKETPLACES_FILE")

        if [[ "$repo" != "unknown" && "$repo" != "null" ]]; then
            # 获取本地 commit
            local_sha="N/A"
            if [[ -n "$install_loc" && -d "$install_loc" ]]; then
                local_sha=$(get_local_git_commit "$install_loc")
            fi

            # 获取远程最新 commit
            remote_info=$(get_github_latest_commit "$repo")
            IFS='|' read -r remote_sha msg date <<< "$remote_info"

            # 判断状态
            if [[ "$local_sha" == "N/A" ]]; then
                status="⚠️ 无Git"
            elif [[ "$remote_sha" == "error" ]]; then
                status="❓ API限制"
            elif [[ "$local_sha" == "$remote_sha" ]]; then
                status="✅ 最新"
            else
                status="🔄 有更新"
            fi

            printf "%-25s %-35s %-10s %-10s %-12s\n" "$marketplace" "$repo" "$local_sha" "$remote_sha" "$status"
        fi
    done
else
    echo "  未找到 marketplaces 配置文件"
fi

echo ""

# -------------------- 检查本地 Skills 与 Plugin 版本差异 --------------------
echo -e "${BLUE}【本地自定义 Skills 差异检查】${NC}"
echo ""

# 检查 obsidian 相关 skills
has_custom=false

# obsidian-markdown
local_path="$SKILLS_DIR/obsidian-markdown"
marketplace_path="$MARKETPLACES_DIR/obsidian-skills/skills/obsidian-markdown"
if [[ -d "$local_path" && -d "$marketplace_path" ]]; then
    local_file="$local_path/SKILL.md"
    remote_file="$marketplace_path/SKILL.md"
    if [[ -f "$local_file" && -f "$remote_file" ]]; then
        added=$(diff "$remote_file" "$local_file" 2>/dev/null | grep "^>" | wc -l | tr -d ' ')
        removed=$(diff "$remote_file" "$local_file" 2>/dev/null | grep "^<" | wc -l | tr -d ' ')
        if [[ "$added" != "0" || "$removed" != "0" ]]; then
            has_custom=true
            echo -e "  📝 ${CYAN}obsidian-markdown${NC}"
            echo "     本地新增: +$added 行, 远端独有: -$removed 行"
        fi
    fi
fi

# obsidian-bases
local_path="$SKILLS_DIR/obsidian-bases"
marketplace_path="$MARKETPLACES_DIR/obsidian-skills/skills/obsidian-bases"
if [[ -d "$local_path" && -d "$marketplace_path" ]]; then
    local_file="$local_path/SKILL.md"
    remote_file="$marketplace_path/SKILL.md"
    if [[ -f "$local_file" && -f "$remote_file" ]]; then
        added=$(diff "$remote_file" "$local_file" 2>/dev/null | grep "^>" | wc -l | tr -d ' ')
        removed=$(diff "$remote_file" "$local_file" 2>/dev/null | grep "^<" | wc -l | tr -d ' ')
        if [[ "$added" != "0" || "$removed" != "0" ]]; then
            has_custom=true
            echo -e "  📝 ${CYAN}obsidian-bases${NC}"
            echo "     本地新增: +$added 行, 远端独有: -$removed 行"
        fi
    fi
fi

# json-canvas
local_path="$SKILLS_DIR/json-canvas"
marketplace_path="$MARKETPLACES_DIR/obsidian-skills/skills/json-canvas"
if [[ -d "$local_path" && -d "$marketplace_path" ]]; then
    local_file="$local_path/SKILL.md"
    remote_file="$marketplace_path/SKILL.md"
    if [[ -f "$local_file" && -f "$remote_file" ]]; then
        added=$(diff "$remote_file" "$local_file" 2>/dev/null | grep "^>" | wc -l | tr -d ' ')
        removed=$(diff "$remote_file" "$local_file" 2>/dev/null | grep "^<" | wc -l | tr -d ' ')
        if [[ "$added" != "0" || "$removed" != "0" ]]; then
            has_custom=true
            echo -e "  📝 ${CYAN}json-canvas${NC}"
            echo "     本地新增: +$added 行, 远端独有: -$removed 行"
            echo "     (包含 Miro 风格可视化规范等自定义内容)"
        fi
    fi
fi

if [[ "$has_custom" == false ]]; then
    echo "  所有 skills 与 marketplace 版本一致，无自定义差异"
fi

echo ""

# -------------------- 本地独立 Skills 统计 --------------------
echo -e "${BLUE}【本地独立 Skills 统计】${NC}"
echo ""

local_only_count=0
local_only_list=""

for skill_dir in "$SKILLS_DIR"/*/; do
    [[ ! -d "$skill_dir" ]] && continue
    skill_name=$(basename "$skill_dir")

    # 跳过 obsidian 相关（已在上面检查）
    case "$skill_name" in
        obsidian-markdown|obsidian-bases|json-canvas) continue ;;
    esac

    # 检查是否有对应的 marketplace
    found_in_marketplace=false
    for mp_dir in "$MARKETPLACES_DIR"/*/; do
        [[ ! -d "$mp_dir" ]] && continue
        if [[ -d "$mp_dir/skills/$skill_name" ]] || [[ -d "$mp_dir/$skill_name" ]]; then
            found_in_marketplace=true
            break
        fi
    done

    if [[ "$found_in_marketplace" == false ]]; then
        local_only_count=$((local_only_count + 1))
        if [[ $local_only_count -le 15 ]]; then
            echo "  • $skill_name"
        fi
    fi
done

if [[ $local_only_count -gt 15 ]]; then
    echo "  ... 等共 $local_only_count 个本地独立 skills"
elif [[ $local_only_count -eq 0 ]]; then
    echo "  无本地独立 skills（所有 skills 均来自 marketplace）"
else
    echo ""
    echo "  共 $local_only_count 个本地独立 skills"
fi

echo ""
echo -e "${CYAN}=== 检查完成 ===${NC}"
