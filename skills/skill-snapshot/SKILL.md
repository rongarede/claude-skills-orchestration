---
name: skill-snapshot
description: Use when creating, listing, diffing, saving, or restoring reversible snapshots of local Claude Code skills with a Git-backed workflow.
---

# Skill Snapshot

为 Claude Code 技能创建快照，支持版本回退。存储在 GitHub 私有仓库，按分类目录组织。

## 触发词

- "快照"、"snapshot"、"保存技能"、"备份技能"
- "回退技能"、"恢复技能"、"restore skill"
- "/skill-snapshot"

## 命令格式

```
/skill-snapshot <command> [args]
```

### 可用命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `init` | 初始化私有仓库 | `/skill-snapshot init` |
| `scan` | 扫描技能，按分类显示备份状态 | `/skill-snapshot scan` |
| `save <skill> [message]` | 保存快照到分类目录 | `/skill-snapshot save my-skill "添加断点续写"` |
| `restore <skill> [version]` | 恢复版本 | `/skill-snapshot restore my-skill v2` |
| `list [skill]` | 列出快照（按分类分组） | `/skill-snapshot list my-skill` |
| `diff <skill> [version]` | 对比差异 | `/skill-snapshot diff my-skill v1` |
| `migrate` | 迁移旧格式快照到分类目录 | `/skill-snapshot migrate` |
| `sync-configs` | 同步所有 CLAUDE.md 配置 | `/skill-snapshot sync-configs` |

## 分类配置

技能分类定义在 `categories.conf` 文件中：

```conf
# 格式: skill-name=category
collaborating-with-codex=ai-collaboration
paper-mapping=writing
obsidian-bases=obsidian
coding-standards=development
planning-with-files=workflow
skill-authoring=meta
agent-browser=utilities
```

### 预定义分类

| 分类 | 说明 | 示例技能 |
|------|------|----------|
| `ai-collaboration` | AI 协作工具 | collaborating-with-codex, task-dispatcher |
| `writing` | 写作与文档 | paper-mapping, pdf2md-academic |
| `obsidian` | Obsidian 相关 | obsidian-bases, nb-query, notebooklm |
| `development` | 开发模式 | coding-standards, tdd-workflow |
| `workflow` | 工作流程 | planning-with-files, changelog |
| `meta` | 元技能管理 | skill-authoring, skill-catalog |
| `utilities` | 工具类 | agent-browser, web-fetch-fallback |
| `uncategorized` | 未分类（默认） | 未在配置中定义的技能 |

## 版本标签格式

- **新格式**: `<category>/<skill-name>/v<n>`（如 `writing/paper-mapping/v1`）
- **旧格式**: `<skill-name>/v<n>`（如 `paper-mapping/v1`，兼容但建议迁移）

## 忽略规则

scan 命令根据以下规则自动判断哪些技能需要备份：

| 规则 | 跳过原因 |
|------|----------|
| `archive/` 目录 | 归档目录 |
| 符号链接 | 外部安装的技能 |
| `skill-snapshot` | 快照工具本身 |
| 包含 `.git/` | 自带版本控制 |
| 包含 `.venv/` 或 `node_modules/` | 包含大量依赖 |
| 体积 > 10MB | 体积过大 |
| 缺少 `SKILL.md` | 可能不是有效技能 |

## 执行流程

### scan - 扫描技能

扫描所有技能，按分类显示备份状态。

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/scan.sh
```

输出示例：
```
【需要备份】

  [ai-collaboration]
    ✓ collaborating-with-codex (7 files, 68K) [已有: ai-collaboration/collaborating-with-codex/v1]
    ✓ task-dispatcher (7 files, 48K) [已有: ai-collaboration/task-dispatcher/v1]

  [writing]
    ✓ paper-mapping (1 files, 8K) [已有: writing/paper-mapping/v1]
    ○ new-skill (3 files, 12K) [未备份]

【跳过】
  ✗ skill-snapshot - 快照工具本身
  ✗ external-plugin - 符号链接（外部安装）
```

### save - 保存快照

参数：
- `<skill>`: 技能名称（必填）
- `[message]`: 快照说明（可选，默认为时间戳）

流程：
1. 验证技能存在于 `~/.claude/skills/<skill>/`
2. 从 `categories.conf` 获取分类
3. 确定下一个版本号
4. 复制技能目录到 `~/.claude/skill-snapshots/<category>/<skill>/`
5. Git add, commit, tag, push

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/save.sh "<skill>" "[message]"
```

### restore - 恢复版本

参数：
- `<skill>`: 技能名称（必填）
- `[version]`: 版本号（可选，默认列出可用版本）

流程：
1. 拉取最新仓库
2. 查找匹配的 tag（兼容新旧格式）
3. Checkout 到指定 tag
4. 复制到 `~/.claude/skills/<skill>/`
5. 切回 main 分支

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/restore.sh "<skill>" "[version]"
```

### migrate - 迁移旧格式

将旧格式快照（`skill/vN`）迁移到新的分类目录格式（`category/skill/vN`）。

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/migrate.sh
```

流程：
1. 扫描所有旧格式 tags
2. 根据 `categories.conf` 确定分类
3. 为每个旧 tag 创建对应的新格式 tag
4. 推送新 tags（保留旧 tags）

### list - 列出快照

参数：
- `[skill]`: 技能名称（可选，不填则按分类列出所有）

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/list.sh "[skill]"
```

## 存储结构

```
~/.claude/skill-snapshots/          # 本地仓库
├── ai-collaboration/               # 分类目录
│   ├── collaborating-with-codex/
│   │   ├── SKILL.md
│   │   └── scripts/
│   └── task-dispatcher/
├── writing/
│   ├── paper-mapping/
│   └── pdf2md-academic/
├── obsidian/
│   ├── obsidian-bases/
│   └── nb-query/
├── development/
├── workflow/
├── meta/
├── utilities/
├── claude-configs/                 # CLAUDE.md 配置备份
│   ├── global/
│   ├── obsidian/
│   ├── solidity/
│   ├── solana/
│   └── README.md
└── README.md

GitHub Tags (新格式):
├── ai-collaboration/collaborating-with-codex/v1
├── writing/paper-mapping/v1
├── obsidian/nb-query/v1
└── ...
```

## 使用示例

### 场景 1：首次使用

```
用户: 帮我初始化技能快照
Claude: [执行 init]
```

### 场景 2：修改前保存

```
用户: 我要改 paper-mapping，先保存一下
Claude: [执行 save paper-mapping "修改前备份"]
输出:
  技能: paper-mapping
  分类: writing
  版本: v2
  ✓ 快照已保存: writing/paper-mapping/v2
```

### 场景 3：改坏了回退

```
用户: paper-mapping 改坏了，退回上一版
Claude: [执行 restore paper-mapping v1]
输出: 已恢复到 writing/paper-mapping/v1
```

### 场景 4：查看历史

```
用户: paper-mapping 有哪些版本？
Claude: [执行 list paper-mapping]
输出:
  === paper-mapping 快照历史 ===
  分类: writing

  v1 - 2025-01-05 - 初始版本 [新]
  v2 - 2025-01-08 - 添加断点续写 [新]
```

### 场景 5：迁移旧格式

```
用户: 帮我把旧的快照迁移到分类目录
Claude: [执行 migrate]
输出:
  发现 43 个技能需要迁移:
    collaborating-with-codex → ai-collaboration/ (3 个版本)
    paper-mapping → writing/ (1 个版本)
    ...
  是否继续迁移? (y/N)
```

## 注意事项

1. **分类配置**: 新技能需要在 `categories.conf` 中添加分类，否则归入 `uncategorized`
2. **向后兼容**: restore/list 命令兼容新旧两种格式的 tags
3. **迁移建议**: 建议执行 `migrate` 将旧格式迁移到新格式
4. **符号链接跳过**: 外部安装的技能（符号链接）不支持快照
5. **网络依赖**: save/restore/migrate 需要网络连接推送到 GitHub
