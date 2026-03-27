---
name: workflow-engine
description: 声明式工作流编排 — 读模板、管状态、调 Agent、断点恢复
---

# Workflow Engine

## 触发方式

- 用户说「执行 {template-name}」或「启动工作流 {template-name}」
- SessionStart 时自动检查未完成 run（断点恢复）

## 文件布局

| 路径 | 用途 |
|------|------|
| `~/mem/mem/workflows/templates/*.yaml` | YAML 模板定义 |
| `~/mem/mem/workflows/runs/*.json` | Run 状态文件 |
| `~/.claude/skills/workflow-engine/scripts/engine.py` | 状态管理工具 |

## root 执行协议

### Phase 1：初始化

```bash
# 解析模板，检查输入
python3 ~/.claude/skills/workflow-engine/scripts/engine.py parse {template_name}

# 创建 run 状态文件
python3 ~/.claude/skills/workflow-engine/scripts/engine.py create {template_name} key1=val1 key2=val2
```

记下返回的 `run_path`，后续所有操作都用它。

### Phase 2：执行循环

```
LOOP:
  1. 获取下一批可执行 step:
     python3 engine.py next {run_path}

  2. 如果无可执行 step → 检查 run 状态:
     python3 engine.py status {run_path}
     - status=completed → 工作流完成，退出
     - status=failed/paused → 通知用户，退出

  3. 对每个 ready step:
     a. 标记为 running:
        python3 engine.py update {run_path} {step_id} running

     b. 读取 agent 的 WhoAmI:
        ~/mem/mem/agents/{type}/{agent}/WhoAmI.md

     c. 调用 Agent tool:
        Agent(
          description="{agent} | {step_id}",
          model="sonnet",
          prompt="你是 {agent}...{WhoAmI内容}\n\n## 任务\n{step.prompt}"
        )

        NOTE: 同一组内的多个 step 用并行 Agent 调用

     d. Agent 完成后:
        - 成功 → python3 engine.py update {run_path} {step_id} completed "结果摘要"
        - 失败 → python3 engine.py update {run_path} {step_id} failed "错误信息"
                  python3 engine.py failure {run_path} {step_id}
                  根据返回的 action 执行:
                  - retry → 回到 3.c 重新调用
                  - goto → 回到 LOOP（engine 已重置目标 step）
                  - pause → 通知用户，退出循环
                  - skip → 继续下一个 step
                  - abort → 标记失败，退出

  4. 回到 LOOP
```

### Phase 3：断点恢复（SessionStart）

会话开始时执行：

```bash
python3 ~/.claude/skills/workflow-engine/scripts/engine.py check
```

如果返回非空列表：
- 向用户显示：「发现未完成工作流：{template} ({completed}/{total} 步完成)，停在 {current_step}」
- 用户确认 → 从 Phase 2 LOOP 继续
- 用户放弃 → `python3 engine.py update {run_path} {step_id} failed "用户放弃"`

## engine.py CLI 参考

| 命令 | 用法 | 返回 |
|------|------|------|
| `parse` | `engine.py parse <template>` | 模板结构 + 拓扑排序组 |
| `create` | `engine.py create <template> [k=v ...]` | `{"run_path": "..."}` |
| `next` | `engine.py next <run_path>` | 可执行 step 列表（含 agent/type/prompt） |
| `update` | `engine.py update <run_path> <step> <status> [result]` | `{"ok": true}` |
| `status` | `engine.py status <run_path>` | run 概览（template/status/steps） |
| `check` | `engine.py check` | 未完成 run 列表 |
| `failure` | `engine.py failure <run_path> <step>` | 行动指令（retry/goto/pause/skip/abort） |

## 模板 YAML Schema

```yaml
name: string          # 模板名
description: string   # 一句话描述
version: int          # 版本号

inputs:               # 输入参数
  - name: string      # 参数名
    required: bool    # 是否必需（默认 false）
    default: string   # 默认值

steps:                # 步骤列表
  - id: string        # 唯一标识
    agent: string     # agent 名（如 tetsu, shin）
    type: string      # agent 类型（如 蚁工, Auditor）
    depends_on: [id]  # 依赖的 step id 列表（可选）
    prompt_template: string  # 任务提示（支持 {{ var }} 变量）
    retry:            # 重试配置（可选）
      max_attempts: int
      on_failure: pause | skip | abort
    on_failure:       # 失败处理（可选）
      goto: step_id   # 回退到指定 step
      max_loops: int   # 最大回退次数
```

## 内置变量

| 变量 | 值 |
|------|------|
| `{{ today }}` | 当前日期 YYYY-MM-DD |
| `{{ 输入参数名 }}` | 用户传入或默认值 |

## 可用模板（11 个）

| 模板 | 描述 |
|------|------|
| fix-chain | 修复→审计→文档→提交 |
| define-chain | 角色定义→文档→提交 |
| feedback-chain | 反馈→吞食→文档→提交 |
| review-chain | 并行审查→修复→复审→提交 |
| audit-chain | CLAUDE.md 审计→修复→复审 |
| explore-chain | 并行探索→文档记录 |
| research-chain | 三路调研→归档 |
| daily-close-chain | 日记→changelog→提交 |
| project-init-chain | 创建项目→MOC→提交 |
| memory-chain | 记忆提取→关联→索引 |
| thesis-chain | 编辑→编译→审计→导出→提交 |
