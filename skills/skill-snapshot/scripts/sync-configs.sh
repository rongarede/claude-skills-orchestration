#!/bin/bash
# ============================================================
# skill-snapshot sync-configs - 同步配置文件和子代理
# ============================================================

set -e

LOCAL_REPO="$HOME/.claude/skill-snapshots"
CONFIGS_DIR="$LOCAL_REPO/claude-configs"
AGENTS_DIR="$LOCAL_REPO/agents"
SOURCE_AGENTS_DIR="$HOME/.claude/agents"

# ==================== 配置映射 ====================
# 格式: "源路径|目标子目录"
declare -a CONFIG_MAPPINGS=(
    # 核心配置
    "$HOME/.claude/CLAUDE.md|global"
    "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/CLAUDE.md|obsidian"

    # Solidity 项目
    "$HOME/SolidityProject/面试文档/CLAUDE.md|solidity/interview"
    "$HOME/SolidityProject/denglian/modoule3/NFTMarket/CLAUDE.md|solidity/denglian-nft-market"
    "$HOME/SolidityProject/denglian/modoule6/launchpund/CLAUDE.md|solidity/denglian-launchpad"
    "$HOME/SolidityProject/denglian/modoule6/DAOBank/claude.md|solidity/denglian-daobank"
    "$HOME/SolidityProject/denglian/modoule7/claude.md|solidity/denglian-module7"

    # Solana 项目
    "$HOME/SolanaRust/IPFlow/programs/candy-machine/program/CLAUDE.md|solana/ipflow-candy-machine"
    "$HOME/SolanaRust/ipflow-v3/CLAUDE.md|solana/ipflow-v3"
    "$HOME/SolanaRust/metaplex-program-library/candy-machine/program/src/CLAUDE.md|solana/metaplex-candy-machine"

    # 其他项目
    "$HOME/v2x_ws/bisai/sumo_intersection_viz/CLAUDE.md|misc/sumo-viz"
)

# ==================== 工具函数 ====================
log_info() {
    echo "[INFO] $1"
}

log_success() {
    echo "[✓] $1"
}

log_skip() {
    echo "[SKIP] $1"
}

log_error() {
    echo "[ERROR] $1" >&2
}

# ==================== 同步子代理 ====================
sync_agents() {
    echo "=== 同步子代理配置 ==="
    echo ""

    # 创建目标目录
    mkdir -p "$AGENTS_DIR"

    local agents_synced=0
    local agents_skipped=0

    # 检查源目录是否存在
    if [ ! -d "$SOURCE_AGENTS_DIR" ]; then
        log_skip "agents 目录不存在: $SOURCE_AGENTS_DIR"
        return
    fi

    # 遍历所有 .md 文件
    for agent_file in "$SOURCE_AGENTS_DIR"/*.md; do
        # 检查文件是否存在（防止 glob 无匹配）
        [ -f "$agent_file" ] || continue

        local filename=$(basename "$agent_file")

        # 复制文件
        cp "$agent_file" "$AGENTS_DIR/$filename"
        log_success "agents/$filename"
        ((agents_synced++))
    done

    if [ $agents_synced -eq 0 ]; then
        log_info "无子代理文件"
    fi

    echo ""
    echo "子代理统计: 同步 $agents_synced"
}

# ==================== 主逻辑 ====================
main() {
    # 检查仓库是否已初始化
    if [ ! -d "$LOCAL_REPO/.git" ]; then
        log_error "仓库未初始化，请先执行 init"
        exit 1
    fi

    cd "$LOCAL_REPO"

    # 拉取最新
    git pull --quiet origin main 2>/dev/null || true

    echo "=== 同步 CLAUDE.md 配置文件 ==="
    echo ""

    # 创建配置目录
    mkdir -p "$CONFIGS_DIR"

    # 统计
    local synced=0
    local skipped=0
    local total=${#CONFIG_MAPPINGS[@]}

    # 遍历配置映射
    for mapping in "${CONFIG_MAPPINGS[@]}"; do
        local src="${mapping%%|*}"
        local dest_subdir="${mapping##*|}"
        local dest_dir="$CONFIGS_DIR/$dest_subdir"
        local dest_file="$dest_dir/CLAUDE.md"

        # 检查源文件是否存在
        if [ ! -f "$src" ]; then
            log_skip "$dest_subdir (源文件不存在)"
            ((skipped++))
            continue
        fi

        # 创建目标目录
        mkdir -p "$dest_dir"

        # 复制文件
        cp "$src" "$dest_file"
        log_success "$dest_subdir"
        ((synced++))
    done

    echo ""

    # 同步子代理
    sync_agents

    echo "=== 生成索引 ==="

    # 生成 README.md
    generate_readme

    echo ""
    echo "=== 提交变更 ==="

    # Git 操作
    git add claude-configs/ agents/

    # 检查是否有变化
    if git diff --cached --quiet; then
        log_info "无变化 - 所有配置与远程一致"
        echo ""
        echo "配置统计: 同步 $synced, 跳过 $skipped, 总计 $total"
        exit 0
    fi

    # 提交并推送
    local commit_msg="sync: update configs and agents ($(date '+%Y-%m-%d %H:%M'))"
    git commit --quiet -m "$commit_msg"
    git push --quiet origin main

    log_success "已推送到 GitHub"
    echo ""
    echo "配置统计: 同步 $synced, 跳过 $skipped, 总计 $total"
}

generate_readme() {
    local readme="$CONFIGS_DIR/README.md"
    local file_count=$(find "$CONFIGS_DIR" -name "CLAUDE.md" -type f | wc -l | tr -d ' ')
    local agent_count=$(find "$AGENTS_DIR" -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')

    cat > "$readme" << 'HEADER'
# Claude 配置文件备份

本目录备份了各项目的 `CLAUDE.md` 配置文件和自定义子代理。

## 目录结构

```
skill-snapshots/
├── claude-configs/      # CLAUDE.md 配置文件
│   ├── global/          # 全局配置 (~/.claude/CLAUDE.md)
│   ├── obsidian/        # Obsidian 知识库
│   ├── solidity/        # Solidity 项目
│   │   ├── interview/
│   │   ├── denglian-nft-market/
│   │   ├── denglian-launchpad/
│   │   ├── denglian-daobank/
│   │   └── denglian-module7/
│   ├── solana/          # Solana/Rust 项目
│   │   ├── ipflow-candy-machine/
│   │   ├── ipflow-v3/
│   │   └── metaplex-candy-machine/
│   └── misc/            # 其他项目
│       └── sumo-viz/
└── agents/              # 自定义子代理
    ├── code-reviewer.md
    ├── codex-executor.md
    ├── codex-reviewer.md
    └── research-analyst.md
```

## 子代理列表

HEADER

    # 动态生成子代理列表
    if [ -d "$AGENTS_DIR" ]; then
        echo "| 子代理 | 说明 |" >> "$readme"
        echo "|--------|------|" >> "$readme"
        for agent_file in "$AGENTS_DIR"/*.md; do
            [ -f "$agent_file" ] || continue
            local name=$(basename "$agent_file" .md)
            # 从文件中提取 description
            local desc=$(grep -A1 "^description:" "$agent_file" 2>/dev/null | tail -1 | sed 's/^[[:space:]]*//' | head -c 60)
            [ -z "$desc" ] && desc="自定义子代理"
            echo "| \`$name\` | $desc... |" >> "$readme"
        done
        echo "" >> "$readme"
    fi

    cat >> "$readme" << 'MAPPING'
## 配置文件来源映射

| 备份路径 | 原始路径 |
|----------|----------|
| `global/CLAUDE.md` | `~/.claude/CLAUDE.md` |
| `obsidian/CLAUDE.md` | `~/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/CLAUDE.md` |
| `solidity/interview/CLAUDE.md` | `~/SolidityProject/面试文档/CLAUDE.md` |
| `solidity/denglian-nft-market/CLAUDE.md` | `~/SolidityProject/denglian/modoule3/NFTMarket/CLAUDE.md` |
| `solidity/denglian-launchpad/CLAUDE.md` | `~/SolidityProject/denglian/modoule6/launchpund/CLAUDE.md` |
| `solidity/denglian-daobank/CLAUDE.md` | `~/SolidityProject/denglian/modoule6/DAOBank/claude.md` |
| `solidity/denglian-module7/CLAUDE.md` | `~/SolidityProject/denglian/modoule7/claude.md` |
| `solana/ipflow-candy-machine/CLAUDE.md` | `~/SolanaRust/IPFlow/programs/candy-machine/program/CLAUDE.md` |
| `solana/ipflow-v3/CLAUDE.md` | `~/SolanaRust/ipflow-v3/CLAUDE.md` |
| `solana/metaplex-candy-machine/CLAUDE.md` | `~/SolanaRust/metaplex-program-library/candy-machine/program/src/CLAUDE.md` |
| `misc/sumo-viz/CLAUDE.md` | `~/v2x_ws/bisai/sumo_intersection_viz/CLAUDE.md` |
| `agents/*.md` | `~/.claude/agents/*.md` |

## 同步命令

```bash
bash ~/.claude/skills/skill-snapshot/scripts/sync-configs.sh
```

或通过 Claude Code:

```
/skill-snapshot sync-configs
```

MAPPING

    echo "## 最后更新" >> "$readme"
    echo "" >> "$readme"
    echo "- **日期**: $(date '+%Y-%m-%d %H:%M')" >> "$readme"
    echo "- **配置文件数**: $file_count" >> "$readme"
    echo "- **子代理数**: $agent_count" >> "$readme"

    log_success "README.md 已更新"
}

main "$@"
