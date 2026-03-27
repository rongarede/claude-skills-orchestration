# Subagent Memory System

基于 BM25 + 三维评分的 Claude Code subagent 联想记忆系统。为每个 agent 提供独立的任务记忆存储、检索和关联管理。

## 角色体系

### 管理层

| 角色 | 身份 | 职责 |
|------|------|------|
| **root** | 主会话协调器（Opus 4.6） | 分析需求、制定计划、分配任务、验证结果。不直接操作文件 |
| **b1 / 惑者** | 用户（最终决策者） | 定义方向、创建角色、授权架构变更 |

### 通用角色（日式命名，model: sonnet）

| 角色 | 类型 | 职责 | 权限 |
|------|------|------|------|
| **kaze（风者）** | Explore | 代码探索、文件搜索、结构理解 | 只读 |
| **mirin（観者）** | Explore | 代码探索（第二探索者） | 只读 |
| **shin（審者）** | Auditor | 只读审计、质量评分、测试验证 | 只读 |
| **tetsu（鉄者）** | 蚁工 | 文件修改、bug 修复、配置更新 | 读写 |
| **sora（空者）** | Operator | 运维操作、环境设置 | 读写 |
| **yomi（読者）** | 斥候 | 外部信息勘探、学术检索、技术趋势分析、竞品调研 | 只读为主 + WebSearch/WebFetch |
| **haku（白者）** | 药师 | 代码审查（质量/安全/可维护性） | 只读 + lint/test |

### Singleton 角色（中文命名，b1 亲创）

| 角色 | 代号 | 职责 | 独占权限 |
|------|------|------|----------|
| **吞食者** | raiga | 吞食书籍/文档 → 产出 skill 和 CLAUDE.md 约束 | 内容消化与知识提炼 |
| **织者** | fumio | 管理所有书籍、项目文件、文档 | 知识库组织 |
| **母体** | norna | 创造与销毁 subagent | agent 生命周期管理 |
| **梦者** | yume | 管理所有 agent 的记忆（~/mem/mem/） | 记忆系统唯一管理者 |

## 生命周期管理

### 不朽 Agent
b1 直接创建的 11 个 agent 永不消亡。

### 可消亡 Agent
母体创建的新 subagent，反馈过差时触发消亡：

```
反馈过差 → root/b1 决定消亡
  → 母体执行销毁（registry 移除 + 目录清理）
  → 吞食者吞食全部信息 → 提炼为 skill/约束（知识不浪费）
  → 梦者清理记忆索引
```

## 核心机制

### 1. WhoAmI 注入
每次唤醒 subagent 时，将其 `WhoAmI.md` 注入 prompt 开头，确保 agent 知道自己是谁、边界在哪。

### 2. 越权拒绝
超出工作范围的任务 → 拒绝 + 说明原因 + 推荐正确角色。

### 3. Feedback 反馈
每个 agent 目录下有 `feedback_*.md` 文件，记录好/坏行为，用于持续改进。

### 4. 记忆保存（root 调度）
记忆保存由 **root（主会话）** 统一负责，非 subagent 自行义务。每个 Agent tool 返回后，root 立即派轻量 agent 调用 `quick-add` 保存该次任务记忆。不保存 = agent 工作未完成。

Memory Flush 自动触发事件（不依赖用户提醒）：

| 触发事件 | 保存内容 | 保存到 |
|----------|---------|--------|
| Agent 完成任务 | 任务摘要 + 关键发现 | 对应 agent 的 store |
| 重要架构决策 | 决策理由 + 备选方案 | `~/mem/mem/agents/root/` |
| 用户反馈/纠正 | 反馈内容 + 行为修正 | `~/mem/mem/agents/root/` |
| 话题切换 | 前一话题的工作摘要 | 对应 agent 的 store |
| 会话即将结束 | 全会话工作总结 | `~/mem/mem/agents/root/` |

### 5. 独立验证
shin 审计 → tetsu 修复 → shin 重验。不信任 subagent 自报结果。

### 6. 决策自主权
root 按影响程度分级决策：低影响直接做，中影响做后汇报，高影响请示 b1。

## 记忆存储

### 目录结构

```
~/mem/mem/
├── agents/                    # subagent 记忆
│   ├── Explore/
│   │   ├── kaze/              # 记忆文件 + WhoAmI.md + feedback
│   │   └── mirin/
│   ├── Auditor/shin/
│   ├── 蚁工/tetsu/
│   ├── Operator/sora/
│   ├── 斥候/yomi/
│   ├── 药师/haku/
│   ├── 吞食者/raiga/
│   ├── 织者/fumio/
│   ├── 母体/norna/
│   ├── 梦者/yume/
│   └── README.md
├── root/                      # root 协调器记忆
├── shared/                    # 跨 agent 共享记忆
└── auto-memory/               # Claude Code 原生 auto-memory
```

### 每个 Agent 目录包含

| 文件 | 说明 |
|------|------|
| `WhoAmI.md` | 身份定义：职责范围、工具权限、越权拒绝规则、强制收尾流程 |
| `role.md` | 技能分配与标准工作流（由母体定义） |
| `feedback_*.md` | 行为反馈记录（good/bad/prohibited），用于持续改进 |
| `{agent}_{date}_{seq}.md` | 任务记忆文件，每条独立存储（如 `tetsu_20260313_001.md`） |

### 记忆格式

每条记忆是一个独立 `.md` 文件，包含 YAML frontmatter + 正文：

```markdown
---
id: task_验证记忆保存机制修复
name: 验证记忆保存机制修复
description: 测试通过 + 5项验证全部通过
type: task
keywords: [记忆保存, 验证, agent-memory]
tags: [verification]
importance: 5
context: Task #65 修复验证
created_at: '2026-03-13T15:30:00'
owner: shin
scope: personal
---

验证内容：agent-memory 全量测试 93/93 通过...
```

### 记忆类型

| type | 用途 |
|------|------|
| `user` | 用户身份、偏好、知识背景 |
| `feedback` | 行为纠正、工作流改进 |
| `task` | 任务执行记录（最常用） |
| `knowledge` | 学到的技术知识 |
| `project` | 项目状态、决策、里程碑 |
| `reference` | 外部资源指针 |

## 技术架构

### 检索引擎
- **BM25** 关键词检索
- **三维评分**：relevance（相关性）+ recency（时效性）+ importance（重要性）
- **扩散激活**：通过 `related_ids` 拉入关联记忆

### 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 存储 | `scripts/memory_store.py` | Memory dataclass + MemoryStore 存储层 |
| 检索 | `scripts/retriever.py` | BM25 + 扩散激活 + 三维评分检索 |
| 关联 | `scripts/associator.py` | 记忆关联（共现分析 + 语义相似） |
| 提取 | `scripts/extractor.py` | 从任务描述提取结构化记忆 |
| 注入 | `scripts/inject.py` | 向 agent prompt 注入相关记忆 |
| 演化 | `scripts/evolver.py` | 记忆邻居演化（LLM 驱动） |
| 去重 | `scripts/consolidator.py` | 记忆去重合并（Jaccard 相似度 ≥ 0.85） |
| 衰减 | `scripts/decay_engine.py` | Ebbinghaus 遗忘曲线衰减（R=e^(-t/S)） |
| 学习 | `scripts/feedback_loop.py` | 反馈学习：自动推断 + 渐进式升级（health 过滤：blocked 排除，warning ×0.5） |
| 触发 | `scripts/trigger_tracker.py` | 触发效率追踪器：记录/分析/自动调整触发阈值 |
| 导出 | `scripts/obsidian_export.py` | 导出为 Obsidian 笔记/MOC/Mermaid 图 |
| 注册 | `scripts/registry.py` | Agent 角色注册表管理 |
| CLI | `scripts/cli.py` | 命令行入口（retrieve/add/feedback/consolidate/health-check/trigger 等） |

### CLI 使用

```bash
# 添加记忆（--agent 和 --store 必须在子命令 quick-add 之前，--keywords 必填）
python3 scripts/cli.py \
  --agent shin \
  --store ~/mem/mem/agents/Auditor/shin \
  quick-add \
  --name "审计结果" \
  --description "CLAUDE.md 审计通过" \
  --type task \
  --keywords "审计,CLAUDE.md,验证" \
  "审计内容详情..."

# 检索记忆
python3 scripts/cli.py \
  --agent shin \
  --store ~/mem/mem/agents/Auditor/shin \
  retrieve "审计" --top-k 5

# 列出记忆
python3 scripts/cli.py list --store ~/mem/mem/agents/Worker/tetsu

# 生成索引
python3 scripts/cli.py generate-index --store ~/mem/mem/agents/Auditor/shin

# 统计
python3 scripts/cli.py stats --store ~/mem/mem/agents/Worker/tetsu

# 记忆去重合并（--dry-run 只预览，不实际合并）
python3 scripts/cli.py consolidate --store ~/mem/mem/agents/Worker/tetsu --threshold 0.85 --dry-run

# 反馈（自动推断，event 可为 task_success/task_failure/audit_pass/audit_fail）
python3 scripts/cli.py \
  --agent tetsu \
  --store ~/mem/mem/agents/Worker/tetsu \
  feedback --memory-id "mem_id" --auto --event task_success

# 健康检查（显示 blocked/warning/healthy 分布）
python3 scripts/cli.py \
  --agent tetsu \
  --store ~/mem/mem/agents/Worker/tetsu \
  health-check

# 触发追踪（查看/重置触发效率统计）
python3 scripts/cli.py \
  --agent tetsu \
  --store ~/mem/mem/agents/Worker/tetsu \
  trigger stats

# 一站式健康概览（blocked/warning/healthy 分布 + 衰减统计）
python3 scripts/cli.py \
  --agent tetsu \
  --store ~/mem/mem/agents/Worker/tetsu \
  dashboard
```

### Phase 2: Memory Consolidation + Decay

- **记忆去重合并**：Jaccard 相似度检测，自动合并高度相似记忆（keywords/tags 并集、importance 取最大值）
- **遗忘曲线衰减**：Ebbinghaus 指数衰减 R=e^(-t/S)，读时计算不写磁盘，floor=base×0.2 防止完全消失

### Phase 3: Feedback Learning Loop

- **自动推断反馈**：任务成功/失败、审计通过/失败自动评分
- **手动覆盖**：用户反馈权重 ×3，可纠正自动推断
- **渐进式升级**：降权(1次) → 告警(3次) → 阻断(5次)，防止反复踩坑
- **健康检查**：记忆分 healthy/warning/blocked 三级，检索时自动过滤
- **decay + feedback 联动**：正面反馈减缓衰减速率，负面反馈加速衰减

### Round 2: 深度集成

- **decay + feedback 联动**：`feedback_loop.py` 产生的正面反馈降低衰减系数，使高质量记忆更持久
- **consolidator + health 联动**：`consolidator.py` 合并时跳过 `blocked` 状态记忆，保持记忆库健康
- **CLI dashboard**：一站式健康概览，汇总 blocked/warning/healthy 分布及衰减统计

### Round 3: 自动化集成

- **R3-A: feedback auto-inference hook**：`TaskUpdate` completed 事件自动推断反馈，无需手动触发；无需人工干预，任务成功/失败直接驱动 feedback_loop
- **R3-B: trigger-map weight/efficiency 注释**：12 个触发地图文件新增权重与效率字段注释，帮助 root 理解触发链路优先级
- **R3-C: CLI 专项测试**：新增 60 个测试覆盖 14+ 子命令（quick-add/retrieve/list/stats/generate-index/consolidate/feedback/health-check/trigger/dashboard/evolve），大幅提升 CLI 可靠性
- **R3-D: evolver + feedback 联动**：`evolver.py` 演化时过滤 `blocked` 记忆（不参与邻居演化）；`warning` 状态记忆权重降级；正面反馈记忆优先触发演化，提升演化质量

### Round 4: 智能自动化

- **R4-A: auto-consolidate hook**：store 记忆数超过 50 时自动触发合并，保持记忆库规模可控；合并前自动备份，防止误合并数据丢失
- **R4-B: scheduled decay hook**：`SessionStart` 事件触发 24h 自动衰减；跳过 24h 内已衰减的 store（避免重复计算），持久化衰减系数到 frontmatter
- **R4-C: cross-agent retriever**：跨 store 联合检索，支持 `--cross-agent` 和 `--stores` 参数；多 store 结果合并后统一三维评分排序；CLI 扩展 `retrieve` 子命令支持跨 agent 查询
- **R4-D: performance benchmarks**：100/500/1000 条记忆规模下全链路基准测试；29 个性能测试覆盖检索/合并/衰减/注入；确认线性扩展特性

### Round 5: 健壮性强化

- **R5-A: conftest fixtures**：`tests/conftest.py` 统一 pytest fixtures（`tmp_store`、`sample_memories`、`mock_llm_client`），消除各测试文件中的重复 setup 代码，提升测试一致性
- **R5-B: incremental index**：`generate-index --force` 标志支持强制全量重建索引；增量索引仅更新变更记忆，避免大规模 store 的全量扫描开销
- **R5-C: corrupted recovery**：损坏记忆文件自动检测与恢复；新增 `repair` CLI 子命令，扫描 store 中 YAML frontmatter 格式错误的文件并尝试修复或隔离
- **R5-D: full workflow tests**：端到端全流程健壮性测试，覆盖 store 初始化异常、并发写入、index 损坏恢复、跨 agent 检索边界条件等场景

### 路径约束（CRITICAL）

`--store` 必须使用**磁盘上的实际目录名**（英文类型名），不得使用旧的中文目录名（已不存在）：

| Agent | 正确路径 | 错误路径 |
|-------|---------|---------|
| tetsu | `~/mem/mem/agents/Worker/tetsu` | `~/mem/mem/agents/蚁工/tetsu` |
| yomi | `~/mem/mem/agents/Analyst/yomi` | `~/mem/mem/agents/斥候/yomi` |
| haku | `~/mem/mem/agents/Inspector/haku` | `~/mem/mem/agents/药师/haku` |
| fumio | `~/mem/mem/agents/Weaver/fumio` | `~/mem/mem/agents/织者/fumio` |
| kaze/mirin | `~/mem/mem/agents/Explore/{name}` | — |
| shin | `~/mem/mem/agents/Auditor/shin` | — |
| sora | `~/mem/mem/agents/Operator/sora` | — |
| raiga | `~/mem/mem/agents/Devourer/raiga` | `~/mem/mem/agents/吞食者/raiga` |
| norna | `~/mem/mem/agents/Matrix/norna` | `~/mem/mem/agents/母体/norna` |
| yume | `~/mem/mem/agents/Dreamer/yume` | `~/mem/mem/agents/梦者/yume` |
| root | `~/mem/mem/agents/root` | `~/mem/mem/root` |

### 测试

```bash
cd ~/.claude/skills/agent-memory
python -m pytest tests/ -v    # 491 tests, all passing
```

## 工作流示例

```
b1 提出需求
  → root 分析、创建 Task、分配角色
    → kaze 探索代码（注入 WhoAmI）
    → [root 立即保存 kaze 记忆]
    → tetsu 执行修改（注入 WhoAmI）
    → [root 立即保存 tetsu 记忆]
    → shin 审计验证（注入 WhoAmI）
    → [root 立即保存 shin 记忆]
  → root 验证结果（独立检查，不信任自报）
  → root 更新项目主页迭代日志
  → root 保存 root 决策记忆
```

## License

MIT
