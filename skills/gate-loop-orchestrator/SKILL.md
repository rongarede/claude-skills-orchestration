---
name: gate-loop-orchestrator
description: "通用 Gate 循环门禁机制。触发词：/gate-loop、gate循环、门禁循环、phase gate。自动检索本地 review skill/subagent，失败自动修复并复检，Gate 通过后自动提交。"
---

# Gate Loop Orchestrator

用于把“Phase -> Gate -> Fail 修复 -> Re-Gate -> Pass Commit -> Next Phase”固化为可复用流程。

## 触发方式

- `/gate-loop`
- 「gate 循环」
- 「门禁机制自动推进」
- 「phase gate 自动执行」

## 强制规则

1. 每个 phase 完成后必须触发一次 gate 审计。
2. gate=FAIL 时禁止进入下一 phase，必须自动修复并复检。
3. gate=PASS 后必须立即执行一次 commit。
4. 审计器必须来自“本地可用 subagent 或 review skill 自动检索结果”。

## 自动检索（本地）

先执行：

```bash
bash ~/.claude/skills/gate-loop-orchestrator/scripts/discover_review_resources.sh
```

检索优先级：

1. 本地子代理（名称含 `review` / `audit`）
2. 本地 review 类 skill（如 `requesting-code-review`）
3. 兜底：内置 `explorer` subagent

## 执行流程

### 1) 初始化

```bash
bash ~/.claude/skills/gate-loop-orchestrator/scripts/main.sh init \
  --repo /abs/repo \
  --todo /abs/path/todo.md \
  --gate /abs/path/gates.md \
  --phase-start 1 \
  --phase-end 8
```

### 2) 每个 phase 的循环

- 执行 phase 实际任务（代码/文档/测试）
- 调用审计 subagent 或 review skill
- 将结果写入 gate 记录
- FAIL：执行修复并重新审计
- PASS：执行 commit（`phase_gate_commit.sh`）并推进下一个 phase

### 3) 通过后提交

```bash
bash ~/.claude/skills/gate-loop-orchestrator/scripts/phase_gate_commit.sh \
  --repo /abs/repo \
  --message "round-N: pass gate-N" \
  --files file1 file2 ...
```

## Gate 记录模板

模板文件：

- `~/.claude/skills/gate-loop-orchestrator/templates/gate-record.md`

可用脚本追加记录：

```bash
bash ~/.claude/skills/gate-loop-orchestrator/scripts/write_gate_record.sh \
  --gate-file /abs/path/gates.md \
  --phase 3 \
  --status PASS \
  --decision "Gate Decision: PASS" \
  --critical 0 --major 0 --minor 1 \
  --must-fix "无" \
  --evidence "path:line"
```

## 失败修复策略

- 优先修复 Critical
- 再修复 Major
- Minor 仅记录不阻断（除非用户指定）
- 每轮修复后必须重跑同一 gate

## 最终完成条件

- `phase-start..phase-end` 对应 gate 全部 PASS
- 每个 gate PASS 后均有 commit 记录
- todo 与 gate 文档状态一致
