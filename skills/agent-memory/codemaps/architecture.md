---
title: Agent-Memory System Codemap
updated: 2026-03-15
scope: ~/.claude/skills/agent-memory/
---

# Agent-Memory 系统架构图

## 系统概述

基于 BM25 + 三维评分的联想记忆系统，为 Claude Code subagent 提供跨会话持久化记忆。

- 语言：Python
- 测试：644 个（31 个测试文件）
- 模块：15 个脚本
- CLI 命令：14 个
- 外部依赖：rank_bm25, PyYAML, anthropic SDK

## 分层架构

```
Layer 5 (入口)    cli.py ──────────────────────────────── 14 个子命令
                     │
Layer 4 (整合)    extractor.py ────────────────────────── LLM 提取 → 建链 → 演化
                     │
Layer 3 (功能)    associator.py │ inject.py │ distiller.py │ evolver.py │ obsidian_export.py
                     │              │             │               │              │
Layer 2 (算法)    retriever.py ─── decay_engine.py ─── consolidator.py
                     │              │                    │
Layer 1 (基础)    memory_store.py ─── feedback_loop.py
                     │
Layer 0 (独立)    registry.py ─── trigger_tracker.py
```

## 核心数据流

### 写入流（快速路径）
```
用户/hook → cli.py quick-add → MemoryStore.add() → {id}.md
```

### 写入流（LLM 路径）
```
hook → extractor → Claude Haiku → keywords/tags → associator.link
     → MemoryStore.add → [shared] → evolver
```

### 检索流
```
cli.py retrieve → store.load_all → filter_by_health → BM25
               → 三维评分 → top-k → [spread] → 扩散激活 → format_for_prompt
```

### 注入流
```
inject.enrich_agent_prompt → retrieve → format → 拼接到 prompt 头部
```

### 维护流
```
consolidate : Jaccard ≥ 0.85 → merge
decay       : R = e^(-t/S), S = importance × 3d
distill     : cluster → analyze → route(memory/zettelkasten/candidate)
```

## 数据模型

Memory（17 字段）：

| 分组 | 字段 |
|------|------|
| 标识 | id, name, description, type, owner, scope |
| 内容 | content, context, keywords, tags |
| 时间 | timestamp, last_accessed |
| 评分 | importance(1-10), access_count, positive_feedback, negative_feedback |
| 关联 | related_ids, accessed_by, evolution_history |

存储格式：YAML frontmatter + Markdown body（`.md` 文件）

## 关键常量

| 常量 | 值 | 作用 |
|------|----|------|
| LOW_RELEVANCE_THRESHOLD | 2.4 | 低相关度警告 |
| decay_factor | 0.995/h | 时间衰减 |
| consolidate threshold | 0.85 | Jaccard 合并阈值 |
| cluster threshold | 0.5 | 聚类阈值 |
| blocked 条件 | ratio ≤ 0.2 且 neg ≥ 5 | 封锁记忆 |
| warning 条件 | ratio ≤ 0.4 且 neg ≥ 3 | 警告记忆 |
| WEIGHT range | [0.3, 1.5] | 触发权重范围 |

## 模块接口速查

### memory_store.py — 存储
```
MemoryStore: add(mem) | load_all() | get(id) | update(mem) | delete(id) | retrieve_merged()
```

### retriever.py — 检索
```
retrieve(query, store, top_k=3)
retrieve_cross_agent(query, stores, top_k=5)
format_for_prompt(results)
三维评分: total = recency + importance_score + relevance  (各 [0,1])
```

### inject.py — 注入
```
build_injection_context(query, store)
enrich_agent_prompt(prompt, store)
mark_memories_used(ids, store)
```

### feedback_loop.py — 反馈
```
infer_memory_feedback(id, event, store)
check_memory_health(mem)  →  healthy | warning | blocked
filter_by_health(mems)
```

### consolidator.py — 合并
```
consolidate(store, threshold=0.85, dry_run)  →  {merged, deleted, skipped}
```

### decay_engine.py — 衰减
```
compute_retention(last_accessed, importance)  →  R
apply_decay(mem)  →  new_mem
cleanup_decayed(store)
```

### distiller.py — 提炼
```
distill(stores, min_cluster_size=3)  →  DistillResult(clusters_found, knowledge_extracted, actions)
```

### associator.py — 关联
```
link_memory(new_mem, store, threshold=0.3)  →  Memory（双向链接）
```

### evolver.py — 演化
```
evolve_neighbors(new_mem, store)  →  [updated_mems]（LLM 驱动）
```

### extractor.py — 提取
```
create_memory_from_task(task_info, store)  →  Memory（Claude Haiku 提取字段）
```

### registry.py — 注册表
```
AgentRegistry: assign(type) | release(name) | get_agent_type(name)
```

### trigger_tracker.py — 触发追踪
```
record_trigger(rule, result)
get_efficiency(rule)
adjust_weight(rule, weight)
```

## 外部集成

### Hook 调用

| Hook | 触发事件 | 功能 |
|------|----------|------|
| memory-extract-hook.py | TaskUpdate 完成 | 自动提取记忆 |
| post-memory-consolidate-hook.py | Agent 完成 | 自动合并 |
| post-task-feedback-hook.py | TaskUpdate | 自动反馈 |
| session-start-decay-hook.py | SessionStart | 批量衰减 |

### 数据目录

| 路径 | 内容 |
|------|------|
| `~/mem/mem/agents/{Type}/{name}/` | 各 agent 记忆 |
| `~/mem/mem/agents/root/` | root 主会话记忆 |
| `~/mem/mem/shared/` | 跨 agent 共享记忆 |
| `~/mem/mem/workflows/` | 工作流状态与模板 |
| `~/.claude/memory/registry.json` | Agent 注册表 |
| `~/mem/mem/workflows/trigger-stats.json` | 触发统计 |
