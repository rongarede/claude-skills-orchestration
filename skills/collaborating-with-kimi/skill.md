---
name: collaborating-with-kimi
description: "[由 collaborating-hub 路由] Kimi CLI 后端实现。直接使用请通过 /collab 或 /kimi 触发 collaborating-hub。"
---

## Quick Start

```bash
~/.claude/skills/collaborating-with-kimi/scripts/kimi-agent.sh "你的任务" --cd "/path/to/project"
```

**输出:** JSON 格式，包含 `success`, `session_id`, `response`, 可选 `error`。

## Parameters

```
用法: kimi-agent.sh "任务描述" --cd /path/to/project [选项]

必需参数:
  --cd PATH          项目工作目录

可选参数:
  --agent, -a NAME   注入 agent 提示词 (如 security-reviewer, planner)
  --session, -s ID   续接会话 (使用之前返回的 session_id)
  --context, -c FILE 自定义上下文文件
  --model, -m MODEL  指定模型 (默认使用 kimi 配置)
  --timeout, -t SECS 超时时间 (默认 120 秒)
  --yolo             自动批准所有操作
  --thinking         启用思考模式
  --no-thinking      禁用思考模式
  --output-format    输出格式 (json|text)
  --save             保存会话到文件 (默认开启)
  --no-save          不保存会话
```

## Multi-turn Sessions

**始终捕获 `session_id`** 用于后续对话：

```bash
# 初始任务
~/.claude/skills/collaborating-with-kimi/scripts/kimi-agent.sh "分析 login.py 的认证逻辑" --cd "/project"

# 使用 session_id 继续
~/.claude/skills/collaborating-with-kimi/scripts/kimi-agent.sh "为刚才分析的代码写单元测试" --cd "/project" --session "kimi_20260128_123456_12345"
```

## Common Patterns

**代码审查 (只读模式):**
```bash
kimi-agent.sh "审查这段代码的安全性" --cd "/project" --agent security-reviewer
```

**规划任务:**
```bash
kimi-agent.sh "规划实现用户认证功能" --cd "/project" --agent planner
```

**自动执行 (YOLO 模式):**
```bash
kimi-agent.sh "重构这个函数" --cd "/project" --yolo
```

**启用深度思考:**
```bash
kimi-agent.sh "复杂架构分析" --cd "/project" --thinking
```

## Session Management

会话自动保存到 `~/.claude/skills/collaborating-with-kimi/sessions/`

**使用会话管理工具:**
```bash
# 列出所有会话
~/.claude/skills/collaborating-with-kimi/scripts/kimi-sessions.sh list

# 查看会话详情
~/.claude/skills/collaborating-with-kimi/scripts/kimi-sessions.sh show <session_id>

# 清理 7 天前的会话
~/.claude/skills/collaborating-with-kimi/scripts/kimi-sessions.sh clean 7
```

## Context Injection

自动加载上下文优先级:
1. `--context FILE` 指定的文件
2. `$PROJECT_DIR/CLAUDE.md`
3. `$PROJECT_DIR/AGENTS.md`
4. `$PROJECT_DIR/KIMI.md`

## Agent Injection

可用的 agents（位于 `~/.claude/agents/`）:
- `planner` - 实现规划
- `architect` - 系统设计
- `security-reviewer` - 安全审查
- `code-reviewer` - 代码审查
- `tdd-guide` - 测试驱动开发
- 更多...

## Output Format

成功响应:
```json
{
  "success": true,
  "session_id": "kimi_20260128_123456_12345",
  "agent": "security-reviewer",
  "context_source": "CLAUDE.md",
  "response": "Kimi 的响应内容..."
}
```

失败响应:
```json
{
  "success": false,
  "session_id": "kimi_20260128_123456_12345",
  "error": "错误信息",
  "exit_code": 1
}
```

## Troubleshooting

**Kimi 执行超时:**
- 增加 `--timeout` 值
- 检查网络连接
- 确认 Kimi CLI 认证有效: `kimi info`

**无响应输出:**
- 确保 Kimi CLI 已正确安装和认证
- 尝试在终端直接运行 `kimi -p "test"` 测试

**登录问题:**
- 运行 `kimi login` 重新认证
