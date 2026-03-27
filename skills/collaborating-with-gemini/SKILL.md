---
name: collaborating-with-gemini
description: "[由 collaborating-hub 路由] Gemini CLI 后端实现。直接使用请通过 /collab 或 /gemini 触发 collaborating-hub。"
---

## Quick Start

```bash
~/.claude/skills/collaborating-with-gemini/scripts/gemini-agent.sh "你的任务" --cd "/path/to/project"
```

**输出:** JSON 格式，包含 `success`, `session_id`, `response`, 可选 `error`。

## Parameters

```
用法: gemini-agent.sh "任务描述" --cd /path/to/project [选项]

必需参数:
  --cd PATH          项目工作目录

可选参数:
  --agent, -a NAME   注入 agent 提示词 (如 security-reviewer, planner)
  --session, -s ID   续接会话 (使用之前返回的 session_id)
  --context, -c FILE 自定义上下文文件
  --model, -m MODEL  指定模型 (默认使用 gemini 配置)
  --timeout, -t SECS 超时时间 (默认 600 秒 / 10 分钟)
  --yolo             自动批准所有操作
  --auto-edit        仅自动批准编辑操作
  --output-format    输出格式 (json|text|stream-json)
  --save             保存会话到文件 (默认开启)
  --no-save          不保存会话
  --on-complete CMD  完成后执行的回调命令
  --no-notify        禁用完成通知
```

## Multi-turn Sessions

**始终捕获 `session_id`** 用于后续对话：

```bash
# 初始任务
~/.claude/skills/collaborating-with-gemini/scripts/gemini-agent.sh "分析 login.py 的认证逻辑" --cd "/project"

# 使用 session_id 继续
~/.claude/skills/collaborating-with-gemini/scripts/gemini-agent.sh "为刚才分析的代码写单元测试" --cd "/project" --session "gemini_20260128_123456_12345"
```

## Common Patterns

**代码审查 (只读模式):**
```bash
gemini-agent.sh "审查这段代码的安全性" --cd "/project" --agent security-reviewer
```

**规划任务:**
```bash
gemini-agent.sh "规划实现用户认证功能" --cd "/project" --agent planner
```

**自动执行 (YOLO 模式):**
```bash
gemini-agent.sh "重构这个函数" --cd "/project" --yolo
```

**带超时控制:**
```bash
gemini-agent.sh "复杂分析任务" --cd "/project" --timeout 900  # 15 分钟
```

**带完成回调:**
```bash
gemini-agent.sh "分析任务" --cd "/project" --on-complete "echo 'Done: \$GEMINI_SESSION_ID'"
```

**禁用通知:**
```bash
gemini-agent.sh "静默任务" --cd "/project" --no-notify
```

## Hook 回调机制

任务完成后自动执行 `--on-complete` 指定的命令，可用环境变量：

| 变量 | 说明 |
|------|------|
| `GEMINI_SESSION_ID` | 会话 ID |
| `GEMINI_SUCCESS` | 是否成功 (true/false) |
| `GEMINI_TASK` | 原始任务描述 |
| `GEMINI_AGENT` | 使用的 agent |
| `GEMINI_RESPONSE_FILE` | 响应文件路径 |
| `GEMINI_PROJECT_DIR` | 项目目录 |

**示例：完成后发送到 Slack**
```bash
gemini-agent.sh "分析代码" --cd "/project" \
  --on-complete 'curl -X POST -d "{\"text\":\"Gemini 完成: $GEMINI_TASK\"}" $SLACK_WEBHOOK'
```

## 完成通知

默认启用 macOS 系统通知（需要 `terminal-notifier` 或 `osascript`）：
- 成功：显示任务摘要
- 失败：显示错误信息

安装 terminal-notifier（推荐）：
```bash
brew install terminal-notifier
```

## Session Management

会话自动保存到 `~/.claude/skills/collaborating-with-gemini/sessions/`

**使用会话管理工具:**
```bash
# 列出所有会话
~/.claude/skills/collaborating-with-gemini/scripts/gemini-sessions.sh list

# 查看会话详情
~/.claude/skills/collaborating-with-gemini/scripts/gemini-sessions.sh show <session_id>

# 清理 7 天前的会话
~/.claude/skills/collaborating-with-gemini/scripts/gemini-sessions.sh clean 7
```

**会话文件内容:**
- `session_id`: 会话唯一标识
- `timestamp`: 执行时间
- `project_dir`: 项目目录
- `agent`: 使用的 agent
- `task`: 原始任务
- `full_prompt`: 完整提示词（含上下文和 agent）
- `response`: Gemini 响应
- `success`: 是否成功
- `error`: 错误信息（如有）

## Context Injection

自动加载上下文优先级:
1. `--context FILE` 指定的文件
2. `$PROJECT_DIR/CLAUDE.md`
3. `$PROJECT_DIR/AGENTS.md`
4. `$PROJECT_DIR/GEMINI.md`

## Agent Injection

可用的 agents（位于 `~/.claude/agents/`）:
- `planner` - 实现规划
- `architect` - 系统设计
- `security-reviewer` - 安全审查
- `code-reviewer` - 代码审查
- `tdd-guide` - 测试驱动开发
- 更多...

## Environment Variables

- `GEMINI_TIMEOUT`: 默认超时时间（秒），覆盖 `--timeout` 参数

## Output Format

成功响应:
```json
{
  "success": true,
  "session_id": "gemini_20260128_123456_12345",
  "agent": "security-reviewer",
  "context_source": "CLAUDE.md",
  "response": "Gemini 的响应内容..."
}
```

失败响应:
```json
{
  "success": false,
  "session_id": "gemini_20260128_123456_12345",
  "error": "错误信息",
  "exit_code": 1
}
```

## Troubleshooting

**Gemini 执行超时:**
- 增加 `--timeout` 值
- 检查网络连接
- 确认 Gemini CLI 认证有效: `gemini --version`

**无响应输出:**
- 确保 Gemini CLI 已正确安装和认证
- 尝试在终端直接运行 `gemini "test"` 测试

**TTY 相关问题:**
- 脚本使用 expect 处理 TTY 问题
- 确保 `/usr/bin/expect` 可用
