# Associative Memory — Execution Plan

## Status Legend
- [ ] Pending
- [x] Completed
- [!] Blocked (see blockers.md)

## Phase 1: 核心存储与检索 (MVP) ✅
- [x] 设计并实现记忆 JSONL schema (`memory_store.py`)
- [x] 实现 BM25 检索器 (`retriever.py`)
- [x] 实现三维评分函数 (recency + importance + relevance)
- [x] 实现联想链管理 (`associator.py`)
- [x] 编写单元测试 (17/17 passed)
- [x] Demo 验证: 3 组查询全部命中正确记忆

## Phase 2: Hook 集成与自动化
- [x] 实现 daily journal 自动总结 hook (`journal-summarizer.py`)
- [x] 实现 `extractor.py` (Claude API 提取 K/G/X/importance)
  - Gate: 单元测试全通过 + mock API 测试
- [x] 实现 `memory-extract-hook.py` (TaskUpdate → 后台提取记忆)
  - Gate: 端到端测试 — 完成 Task → 自动生成记忆条目
- [x] 集成自动关联 (BM25 Top-5 → 阈值过滤 → 写入 related_ids)
  - Gate: 新记忆自动与已有记忆建立链接 (create_memory_from_task calls link_memory with auto_link=True)

## Phase 3: Skill 封装与联想扩散
- [x] 创建 `agent-memory` SKILL.md (触发词、工作流、接口)
- [x] 实现 CLI 入口 (`cli.py`: retrieve / add / evolve / stats)
- [x] 实现记忆注入到 subagent prompt 的标准流程
- [x] 实现被动演化 (使用后可更新 context/tags)
  - Gate: 演化后记忆的 context 确实被更新

## Phase 4: Obsidian 可视化与优化 (Future)
- [x] 记忆导出为 Obsidian 笔记
- [x] 记忆图谱可视化 (.canvas 或 Mermaid)
- [x] 与 PARA 体系对齐
- [ ] 性能优化与参数调优

## Blockers
(none currently)
