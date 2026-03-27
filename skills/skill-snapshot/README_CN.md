# Skill Snapshot

[English](README.md)

一个用于为 Claude Code 技能创建快照的技能，支持版本控制。将备份存储在私有 GitHub 仓库中，随时可以恢复到任意版本。

## 功能特性

- **快照管理**：保存、恢复、列表、对比技能版本
- **私有 GitHub 存储**：自动创建并同步到私有仓库
- **智能扫描**：自动识别哪些技能需要备份
- **版本标签**：每个快照都有标签（如 `my-skill/v1`、`my-skill/v2`）

## 安装

将 `skill-snapshot` 文件夹复制到 Claude Code 技能目录：

```bash
cp -r skill-snapshot ~/.claude/skills/
```

## 命令

| 命令 | 说明 |
|------|------|
| `init` | 初始化私有 GitHub 仓库 |
| `scan` | 扫描技能，识别需要备份的技能 |
| `save <skill> [message]` | 保存快照 |
| `restore <skill> [version]` | 恢复到指定版本 |
| `list [skill]` | 列出所有快照 |
| `diff <skill> [version]` | 对比当前版本与快照的差异 |

## 使用示例

### 首次设置

```
用户: 初始化技能快照
Claude: [执行 init - 创建私有仓库]
```

### 修改前保存

```
用户: 保存 my-skill 快照
Claude: [执行 save my-skill "修改前备份"]
输出: 已保存快照 my-skill/v1
```

### 改坏了恢复

```
用户: my-skill 改坏了，恢复到 v1
Claude: [执行 restore my-skill v1]
输出: 已恢复到 my-skill/v1
```

### 扫描需要备份的技能

```
用户: 哪些技能需要备份？
Claude: [执行 scan]
输出:
  【需要备份】
    ✓ my-skill (5 files, 68K) [已有: my-skill/v1]
    ○ new-skill (3 files, 12K) [未备份]

  【跳过】
    ✗ external-plugin - 符号链接（外部安装）
    ✗ git-managed-skill - 自带 Git 版本控制
```

## 跳过规则

`scan` 命令会自动跳过以下情况：

| 规则 | 原因 |
|------|------|
| `archive/` 目录 | 归档目录 |
| 符号链接 | 外部安装的技能 |
| `skill-snapshot` 本身 | 快照工具本身 |
| 包含 `.git/` | 自带版本控制 |
| 包含 `.venv/` 或 `node_modules/` | 包含大量依赖 |
| 体积 > 10MB | 体积过大 |
| 缺少 `SKILL.md` | 不是有效技能 |

## 系统要求

- 已安装并认证 [GitHub CLI](https://cli.github.com/)（`gh`）
- 已安装 Git
- macOS 或 Linux（使用 bash 脚本）

## 存储结构

```
~/.claude/skill-snapshots/          # 本地仓库
├── my-skill/
│   ├── SKILL.md
│   └── scripts/
├── another-skill/
│   └── SKILL.md
└── README.md

GitHub Tags:
├── my-skill/v1
├── my-skill/v2
└── another-skill/v1
```

## 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE)
