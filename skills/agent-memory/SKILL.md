---
name: agent-memory
description: 联想记忆系统：为 Claude Code subagent 提供基于 BM25 + 三维评分的记忆检索、存储、反馈学习能力
version: 3.0
---

# Agent Memory System

为 Claude Code subagent 提供联想记忆能力。

## 核心能力

| 能力 | 模块 | 说明 |
|------|------|------|
| 存储 | memory_store.py | Markdown 文件存储，YAML frontmatter 元数据 |
| 检索 | retriever.py | BM25 + 扩散激活 + 三维评分（相关性/重要性/新近性） |
| 关联 | associator.py | 共现分析 + 语义相似度 |
| 提取 | extractor.py | 从任务描述自动提取结构化记忆 |
| 注入 | inject.py | 向 agent prompt 注入相关记忆上下文 |
| 演化 | evolver.py | LLM 驱动的记忆邻居演化 |
| 去重 | consolidator.py | Jaccard 相似度合并（阈值 0.85） |
| 衰减 | decay_engine.py | Ebbinghaus 遗忘曲线 R=e^(-t/S) |
| 学习 | feedback_loop.py | 自动推断 + 渐进式升级（降权→告警→阻断，health 过滤） |
| 触发 | trigger_tracker.py | 触发效率追踪：record/efficiency/adjust/stats/reset |
| 导出 | obsidian_export.py | Obsidian 笔记/MOC/Mermaid 图 |
| 注册 | registry.py | Agent 角色注册表 |

## 存储格式

每条记忆为一个 `.md` 文件，YAML frontmatter 包含元数据：

```yaml
---
id: task_example
name: 任务描述
description: 一句话摘要
type: task
owner: tetsu
scope: private
importance: 8
access_count: 3
positive_feedback: 5
negative_feedback: 1
keywords: [TDD, Python]
tags: [implementation]
timestamp: 2026-03-14T22:00:00
---

记忆正文内容...
```

## CLI 用法

```bash
# 基础路径
SCRIPT=~/.claude/skills/agent-memory/scripts/cli.py

# 快速添加记忆
python3 $SCRIPT --agent tetsu --store ~/mem/mem/agents/Worker/tetsu \
  quick-add --name "任务名" --description "描述" --type task --context "执行上下文" "正文内容"

# 检索记忆
python3 $SCRIPT --agent tetsu --store ~/mem/mem/agents/Worker/tetsu \
  retrieve --query "搜索关键词" --top-k 5

# 快速添加（明确字段）
python3 $SCRIPT --store ~/mem/mem/agents/Worker/tetsu \
  add --subject "任务主题" --description "详细描述" --keywords "kw1,kw2" --importance 7

# 反馈（手动正向）
python3 $SCRIPT --agent tetsu --store ~/mem/mem/agents/Worker/tetsu \
  feedback --memory-id "mem_id" --useful

# 反馈（手动负向）
python3 $SCRIPT --agent tetsu --store ~/mem/mem/agents/Worker/tetsu \
  feedback --memory-id "mem_id" --not-useful

# 反馈（自动推断）
python3 $SCRIPT --agent tetsu --store ~/mem/mem/agents/Worker/tetsu \
  feedback --memory-id "mem_id" --auto --event task_success

# 记忆去重合并
python3 $SCRIPT --store ~/mem/mem/agents/Worker/tetsu \
  consolidate --threshold 0.85 --dry-run

# 列出记忆
python3 $SCRIPT --store ~/mem/mem/agents/Worker/tetsu list --limit 10

# 统计
python3 $SCRIPT --store ~/mem/mem/agents/Worker/tetsu stats

# 生成索引（增量，默认）
python3 $SCRIPT --store ~/mem/mem/agents/Worker/tetsu generate-index

# 生成索引（强制全量重建）
python3 $SCRIPT --store ~/mem/mem/agents/Worker/tetsu generate-index --force

# 修复损坏记忆文件（--fix 自动修复, --delete 删除无法修复项, --yes 跳过确认）
python3 $SCRIPT --store ~/mem/mem/agents/Worker/tetsu repair --fix --delete --yes

# 一站式健康概览（blocked/warning/healthy 分布 + 衰减统计，--trigger-stats 附加触发效率）
python3 $SCRIPT --agent tetsu --store ~/mem/mem/agents/Worker/tetsu dashboard --trigger-stats
```

## 路径约束

| Agent | 正确路径 |
|-------|---------|
| tetsu | ~/mem/mem/agents/Worker/tetsu |
| shin | ~/mem/mem/agents/Auditor/shin |
| fumio | ~/mem/mem/agents/Weaver/fumio |
| root | ~/mem/mem/agents/root |

`--store` 参数优先于 `--agent` 推断的路径。

## 测试

```bash
cd ~/.claude/skills/agent-memory
python3 -m pytest  # 491 tests, ~5s
```

## 架构演进

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1 | Active Recall + Retrieval Feedback | 已完成 |
| Phase 2 | Memory Consolidation + Decay | 已完成 |
| Phase 3 | Feedback Learning Loop | 已完成 |
| Phase A | feedback_loop.py 审计修复（M1-M4） | 已完成 |
| Phase B | retriever + cli feedback 集成 | 已完成 |
| Phase C | trigger_tracker.py 智能触发追踪 | 已完成 |
| Phase D | 端到端测试（5 场景，12 tests） | 已完成 |
| Phase E | 全量审计 + 文档同步 | 已完成 |
| Round 2 | 深度集成（decay+feedback 联动、consolidator+health 联动、CLI dashboard） | 已完成 |
| Round 3 | 自动化集成（feedback hook、trigger-map 注释、CLI 专项测试 +60、evolver+feedback 联动） | 已完成 |
| Round 4 | 智能自动化（auto-consolidate hook、scheduled decay hook、cross-agent retriever、performance benchmarks） | 已完成 |
| Round 5 | 健壮性强化（conftest fixtures、incremental index、corrupted recovery、full workflow tests） | 已完成 |

也可在 CLI 中添加 health-check 和 trigger 子命令：

```bash
# 健康检查（--show-all 显示全部记忆，含 healthy 状态）
python3 $SCRIPT --agent tetsu --store ~/mem/mem/agents/Worker/tetsu health-check --show-all

# 触发追踪
python3 $SCRIPT --agent tetsu --store ~/mem/mem/agents/Worker/tetsu trigger stats

# 记忆演化
python3 $SCRIPT --store ~/mem/mem/agents/Worker/tetsu \
  evolve mem_xxxxx --context "新语境" --tags "tag1,tag2"

# 跨 agent 联合检索（Round 4 新增）
python3 $SCRIPT retrieve --cross-agent --query "搜索关键词" --top-k 5
python3 $SCRIPT retrieve --stores "~/mem/mem/agents/Worker/tetsu,~/mem/mem/agents/Auditor/shin" --query "搜索关键词"
```
