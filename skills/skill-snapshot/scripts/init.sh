#!/bin/bash
# skill-snapshot init - 初始化私有仓库

set -e

REPO_NAME="skill-snapshots"
LOCAL_PATH="$HOME/.claude/skill-snapshots"
GITHUB_USER=$(gh api user -q '.login')

echo "=== Skill Snapshot 初始化 ==="

# 检查 GitHub 仓库是否存在
if gh repo view "$GITHUB_USER/$REPO_NAME" &>/dev/null; then
    echo "✓ GitHub 仓库已存在: $GITHUB_USER/$REPO_NAME"
else
    echo "→ 创建私有仓库: $GITHUB_USER/$REPO_NAME"
    gh repo create "$REPO_NAME" --private --description "Claude Code Skills Snapshots (私有备份)" --clone=false
    echo "✓ 私有仓库已创建"
fi

# 检查本地目录
if [ -d "$LOCAL_PATH/.git" ]; then
    echo "✓ 本地仓库已存在: $LOCAL_PATH"
    cd "$LOCAL_PATH"
    git pull --quiet origin main 2>/dev/null || true
else
    echo "→ 克隆到本地: $LOCAL_PATH"
    if gh repo view "$GITHUB_USER/$REPO_NAME" --json isEmpty -q '.isEmpty' | grep -q true; then
        # 空仓库，需要先初始化
        mkdir -p "$LOCAL_PATH"
        cd "$LOCAL_PATH"
        git init --quiet
        git remote add origin "https://github.com/$GITHUB_USER/$REPO_NAME.git"

        # 创建 README
        cat > README.md << 'EOF'
# Skill Snapshots

Claude Code 技能快照私有备份仓库。

## 结构

每个技能对应一个目录，使用 Git tags 管理版本：

```
├── <skill-name>/
│   ├── SKILL.md
│   └── scripts/
```

Tags 格式: `<skill-name>/v<n>`

## 使用

此仓库由 `skill-snapshot` 技能自动管理，请勿手动修改。
EOF
        git add README.md
        git commit --quiet -m "Initial commit"
        git branch -M main
        git push --quiet -u origin main
        echo "✓ 仓库已初始化"
    else
        git clone --quiet "https://github.com/$GITHUB_USER/$REPO_NAME.git" "$LOCAL_PATH"
        echo "✓ 已克隆到本地"
    fi
fi

echo ""
echo "=== 初始化完成 ==="
echo "私有仓库: https://github.com/$GITHUB_USER/$REPO_NAME"
echo "本地路径: $LOCAL_PATH"
