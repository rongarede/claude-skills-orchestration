---
name: collaborating-with-codex
description: "[由 collaborating-hub 路由] Codex CLI 后端实现。直接使用请通过 /collab 或 /codex 触发 collaborating-hub。"
---

## Quick Start

```bash
python3 scripts/codex_bridge.py --cd "/path/to/project" --PROMPT "Your task"
```

**Output:** JSON with `success`, `SESSION_ID`, `agent_messages`, and optional `error`.

## Agent Role Injection (NEW)

Inject agent roles from `~/.claude/agents/` to customize Codex behavior:

```bash
# 使用 planner agent 角色
python3 scripts/codex_bridge.py --cd "/project" --agent planner --PROMPT "Plan the auth feature"

# 使用 security-reviewer agent 角色
python3 scripts/codex_bridge.py --cd "/project" --agent security-reviewer --PROMPT "Review auth.py for vulnerabilities"

# 列出可用 agents
python3 scripts/codex_bridge.py --cd "/project" --list-agents --PROMPT ""
```

### Agent 注入优先级

1. `--instructions` - 直接传入指令字符串（最高优先级）
2. `--instructions-file` - 指定指令文件路径
3. `--agent-file` - 指定自定义 agent 文件路径
4. `--agent` - 从 `~/.claude/agents/` 加载 agent

## Parameters

```
usage: codex_bridge.py [-h] --PROMPT PROMPT --cd CD
                       [--sandbox {read-only,workspace-write,danger-full-access}]
                       [--SESSION_ID SESSION_ID] [--skip-git-repo-check]
                       [--return-all-messages] [--image IMAGE] [--model MODEL]
                       [--yolo] [--profile PROFILE]
                       [--agent AGENT] [--agent-file AGENT_FILE]
                       [--agent-dir AGENT_DIR] [--list-agents]
                       [--instructions INSTRUCTIONS] [--instructions-file FILE]

Codex Bridge with Agent Role Injection

Core Options:
  --PROMPT PROMPT       Instruction for the task to send to codex.
  --cd CD               Set the workspace root for codex.
  --sandbox             Sandbox policy. Defaults to `read-only`.
  --SESSION_ID          Resume a previous session.
  --model MODEL         Model to use (e.g., gpt-5.2-codex).

Agent Role Injection:
  --agent AGENT         Agent name from ~/.claude/agents/ (e.g., 'planner').
  --agent-file FILE     Custom agent file path.
  --agent-dir DIR       Agent directory. Defaults to ~/.claude/agents/
  --list-agents         List available agents and exit.
  --instructions STR    Direct system instructions string.
  --instructions-file   Path to custom instructions file.

Other Options:
  --skip-git-repo-check Allow running outside a Git repository.
  --return-all-messages Return all messages including reasoning.
  --image IMAGE         Attach image files to the prompt.
  --yolo                Run without approvals or sandboxing.
  --profile PROFILE     Configuration profile from config.toml.
```

## Multi-turn Sessions

**Always capture `SESSION_ID`** from the first response for follow-up:

```bash
# Initial task with agent role
python3 scripts/codex_bridge.py --cd "/project" --agent architect --PROMPT "Design the API"

# Continue with SESSION_ID (agent role persists in session)
python3 scripts/codex_bridge.py --cd "/project" --SESSION_ID "uuid-from-response" --PROMPT "Add error handling"
```

## Common Patterns

**Planning with planner agent:**
```bash
python3 scripts/codex_bridge.py --cd "/project" --agent planner --PROMPT "Plan refactoring of auth module"
```

**Security review:**
```bash
python3 scripts/codex_bridge.py --cd "/project" --agent security-reviewer --PROMPT "Audit payment.py"
```

**Code review:**
```bash
python3 scripts/codex_bridge.py --cd "/project" --agent code-reviewer --PROMPT "Review recent changes"
```

**Custom instructions:**
```bash
python3 scripts/codex_bridge.py --cd "/project" --instructions "你是 Rust 专家，专注于性能优化" --PROMPT "Optimize this function"
```

**Debug with full trace:**
```bash
python3 scripts/codex_bridge.py --cd "/project" --agent build-error-resolver --PROMPT "Fix build errors" --return-all-messages
```

## Process Monitoring (NEW)

使用 `codex_monitor.py` 监控和管理 Codex 进程：

```bash
# 列出运行中的 Codex 进程
python3 scripts/codex_monitor.py --ps

# 查看最新会话的对话内容
python3 scripts/codex_monitor.py --session latest --messages 20

# 查看指定会话（使用 SESSION_ID）
python3 scripts/codex_monitor.py --session 019c08b7-8d56-7543 --messages 50

# 实时监控最新会话（Ctrl+C 停止）
python3 scripts/codex_monitor.py --watch

# 终止指定进程
python3 scripts/codex_monitor.py --kill 12345

# 终止所有 codex exec 进程
python3 scripts/codex_monitor.py --kill all

# JSON 格式输出（便于程序处理）
python3 scripts/codex_monitor.py --ps --json
python3 scripts/codex_monitor.py --session latest --json
```

### Monitor 参数

| 参数 | 说明 |
|------|------|
| `--ps` | 列出运行中的 Codex 进程 |
| `--kill <PID\|all>` | 终止进程 |
| `--session <ID\|latest>` | 查看会话内容 |
| `--watch` | 实时监控最新会话 |
| `--messages N` | 显示消息数量（默认 20） |
| `--json` | JSON 格式输出 |

## Workspace Integration (NEW)

Agent Workspace 提供任务交接与执行日志的持久化存储：

### 目录结构

```
~/agent-workspace/
├── config.json
├── projects/{project-slug}/
│   ├── plans/      # 任务计划文档
│   ├── logs/       # 执行日志 (JSONL)
│   └── artifacts/  # 中间产物
└── templates/
```

### 使用方式

```bash
# 带 workspace 日志的 Codex 调用
python3 scripts/codex_bridge.py --cd "/project" \
  --project swun-thesis --plan ch3-expansion --task-num 1 \
  --PROMPT "Your task"

# 禁用日志
python3 scripts/codex_bridge.py --cd "/project" --workspace none --PROMPT "Quick task"
```

### Workspace Manager

```bash
# 初始化项目
python3 scripts/workspace_manager.py init --project my-project --path /path/to/project

# 查看日志
python3 scripts/workspace_manager.py logs --project swun-thesis --last 10

# 查看 plan 执行状态
python3 scripts/workspace_manager.py status --plan ch3-expansion

# 清理 30 天前的文件
python3 scripts/workspace_manager.py clean --project swun-thesis --before 30d
```
