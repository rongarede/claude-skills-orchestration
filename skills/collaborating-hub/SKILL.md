---
name: collaborating-hub
description: 统一的外部 AI CLI 协作入口。支持 Codex、Gemini、Kimi 三个后端，按触发词或 --backend 参数自动路由。触发词：/collab、协作调用、调用 codex、调用 gemini、调用 kimi、/gemini、/kimi、/codex
---

# AI CLI 协作中心

统一入口，将任务路由到 Codex / Gemini / Kimi CLI。

## 路由规则

| 触发词 | 后端 | 脚本路径 |
|--------|------|----------|
| `/codex`、`调用 codex`、`codex 协作` | Codex | `~/.claude/skills/collaborating-with-codex/scripts/codex_bridge.py` |
| `/gemini`、`调用 gemini`、`gemini 协作` | Gemini | `~/.claude/skills/collaborating-with-gemini/scripts/gemini-agent.sh` |
| `/kimi`、`调用 kimi`、`kimi 协作` | Kimi | `~/.claude/skills/collaborating-with-kimi/scripts/kimi-agent.sh` |

## 统一接口

所有后端共享的参数：

```
必需:
  --cd PATH            项目工作目录

通用可选:
  --agent, -a NAME     注入 agent 角色 (planner, security-reviewer, code-reviewer...)
  --session, -s ID     续接会话
  --context, -c FILE   自定义上下文文件
  --model, -m MODEL    指定模型
  --yolo               自动批准所有操作
```

## Quick Start

```bash
# Codex
python3 ~/.claude/skills/collaborating-with-codex/scripts/codex_bridge.py \
  --cd "/project" --PROMPT "Your task"

# Gemini
~/.claude/skills/collaborating-with-gemini/scripts/gemini-agent.sh \
  "你的任务" --cd "/project"

# Kimi
~/.claude/skills/collaborating-with-kimi/scripts/kimi-agent.sh \
  "你的任务" --cd "/project"
```

## 各后端专属参数

### Codex 专属

```
--sandbox {read-only,workspace-write,danger-full-access}
--PROMPT PROMPT          任务描述（必需，注意大写）
--return-all-messages    返回含推理的完整消息
--image IMAGE            附加图片
--profile PROFILE        配置文件 profile
--skip-git-repo-check    允许在非 Git 仓库运行
```

**进程监控** (`codex_monitor.py`):
```bash
python3 ~/.claude/skills/collaborating-with-codex/scripts/codex_monitor.py --ps        # 列出进程
python3 ~/.claude/skills/collaborating-with-codex/scripts/codex_monitor.py --watch     # 实时监控
python3 ~/.claude/skills/collaborating-with-codex/scripts/codex_monitor.py --kill all  # 终止所有
```

### Gemini 专属

```
--auto-edit              仅自动批准编辑操作
--output-format FORMAT   json|text|stream-json
--timeout SECS           超时（默认 600 秒）
--on-complete CMD        完成后回调命令
--no-notify              禁用系统通知
```

**会话管理** (`gemini-sessions.sh`):
```bash
~/.claude/skills/collaborating-with-gemini/scripts/gemini-sessions.sh list
~/.claude/skills/collaborating-with-gemini/scripts/gemini-sessions.sh show <id>
~/.claude/skills/collaborating-with-gemini/scripts/gemini-sessions.sh clean 7
```

### Kimi 专属

```
--thinking               启用深度思考模式
--no-thinking            禁用思考模式
--timeout SECS           超时（默认 120 秒）
```

**会话管理** (`kimi-sessions.sh`):
```bash
~/.claude/skills/collaborating-with-kimi/scripts/kimi-sessions.sh list
~/.claude/skills/collaborating-with-kimi/scripts/kimi-sessions.sh show <id>
~/.claude/skills/collaborating-with-kimi/scripts/kimi-sessions.sh clean 7
```

## 输出格式（统一）

```json
{
  "success": true,
  "session_id": "<backend>_<timestamp>_<pid>",
  "agent": "security-reviewer",
  "response": "响应内容..."
}
```

## 选择后端的建议

| 场景 | 推荐后端 | 原因 |
|------|----------|------|
| 代码生成/重构 | Codex | 沙箱隔离，进程监控 |
| 长时间分析任务 | Gemini | 10 分钟超时，完成通知 |
| 快速问答/思考链 | Kimi | 思考模式，轻量快速 |
| 安全审查 | 任意 | 均支持 agent 注入 |
