# 多角色双层记忆架构设计

## 概述

为 Associative Memory 系统引入多角色命名 + 双层记忆隔离机制。每个子代理拥有持久化角色身份和个人记忆，同时共享通用知识层。

## 角色命名系统

### 名字池（5-10 字母，按 subagent_type 分组）

| subagent_type | 名字池 |
|---------------|--------|
| Explore | Kaze, Mirin, Soren, Vento, Cirro |
| Worker | Tetsu, Aspen, Ember, Riven, Cobalt |
| Operator (general-purpose) | Sora, Nimba, Prism, Helix, Pulse |
| Auditor (code-reviewer) | Shin, Onyx, Argon, Quartz, Flint |
| Analyst (worker-researcher) | Yomi, Lyric, Astra, Cipher, Nexus |
| Inspector (worker-reviewer) | Haku, Rune, Velox, Ignis, Terra |

### 角色生命周期

- **分配**：主会话启动子代理时，从该类型名字池中分配一个 idle 角色
- **创建**：首次分配时自动创建 profile.json，角色从此持久存在
- **并发**：同类型可同时有多个 busy 角色（如 Kaze 和 Mirin 各领一个 Explore 任务）
- **释放**：任务完成后标记回 idle
- **持久**：角色跨会话保留，积累个人经验

## 存储结构

```
~/.claude/memory/
├── registry.json                ← 角色注册表
├── names.json                   ← 名字池状态
├── shared/
│   └── memories.jsonl           ← 所有角色共享的通用知识
└── agents/
    ├── kaze/
    │   ├── profile.json         ← 角色档案
    │   └── memories.jsonl       ← 个人记忆
    ├── tetsu/
    │   ├── profile.json
    │   └── memories.jsonl
    └── .../
```

### registry.json

```json
{
  "agents": {
    "kaze":  {"type": "Explore",  "status": "idle", "created": "2026-03-13"},
    "mirin": {"type": "Explore",  "status": "busy", "created": "2026-03-13"},
    "tetsu": {"type": "Worker",   "status": "idle", "created": "2026-03-13"}
  }
}
```

### profile.json

```json
{
  "name": "Kaze",
  "type": "Explore",
  "created": "2026-03-13T10:00:00",
  "task_count": 12,
  "last_active": "2026-03-13T14:30:00"
}
```

### 记忆 ID 格式

`{agent_name}_{YYYYMMDD}_{NNN}` — 例如 `kaze_20260313_001`

共享记忆 ID：`shared_{YYYYMMDD}_{NNN}`

## 双层记忆模型

### 层次

```
┌─────────────────────────────────┐
│         Shared Memory           │
│   所有角色都能读写的通用知识       │
└──────────┬──────────────────────┘
           │
     ┌─────┼─────┬─────┐
     │     │     │     │
   Kaze  Mirin Tetsu  ...
   个人   个人   个人
```

### 关联链接规则

- **同类型角色间**：可建立双向关联 ✅
- **跨类型角色间**：禁止关联 ✗
- **个人 ↔ Shared**：可读写，但不建立 related_ids 关联

```
Kaze(Explore) ↔ Mirin(Explore)    ✅ 同类型
Kaze(Explore) ↔ Tetsu(Worker)     ✗ 跨类型
Kaze(Explore) → Shared            ✅ 读写共享层
```

## 检索流程

```
角色 Kaze 检索 "字体编译错误"
     │
     ├─ 搜索 agents/kaze/memories.jsonl       ← 个人记忆
     ├─ 搜索 agents/mirin/memories.jsonl      ← 同类型其他角色
     ├─ 搜索 shared/memories.jsonl            ← 共享知识
     │
     ├─ 三维评分（recency + importance + relevance）合并排序
     ├─ 扩散激活（仅在同类型角色间扩散）
     └─ 返回 top-k
```

## 自动分类机制

### 创建时分类

| 条件 | 分类 |
|------|------|
| importance ≥ 8 且 tags 含通用类别（architecture, convention, config, standard, rule） | → shared |
| 默认 | → personal |

### 被动晋升

当一条 personal 记忆被 **≥ 3 个不同角色** 检索命中时，自动复制到 shared 层。

通过 `accessed_by` 字段追踪哪些角色检索过该记忆：

```python
# 检索命中时
if agent_name not in memory.accessed_by:
    memory.accessed_by.append(agent_name)
    if len(memory.accessed_by) >= 3:
        promote_to_shared(memory)
```

## 接口变更

### Memory dataclass 新增字段

```python
@dataclass
class Memory:
    # ... 原有字段 ...
    owner: str = ""                                    # "kaze"
    scope: str = "personal"                            # "personal" | "shared"
    accessed_by: list[str] = field(default_factory=list)  # 检索过的角色名
```

### MemoryStore 变更

```python
class MemoryStore:
    def __init__(
        self,
        agent_name: str = None,      # "kaze" → 定位个人存储
        agent_type: str = None,       # "Explore" → 定位同类型角色
        store_path: str = None,       # 向后兼容
    )

    def add(self, memory: Memory, scope: str = "personal") -> Memory
    def retrieve_merged(self, query, top_k=3, spread=True) -> list[tuple[Memory, float]]
    def check_promotion(self, memory_id: str) -> bool
```

### AgentRegistry

```python
class AgentRegistry:
    def assign(self, agent_type: str) -> str
        # 从名字池分配 idle 角色，返回角色名
    def release(self, agent_name: str)
        # 释放角色回 idle
    def get_agents_by_type(self, agent_type: str) -> list[str]
        # 返回该类型所有角色名
```

### associator.link_memory 变更

```python
def link_memory(new_memory, store, top_k=5, threshold=0.3):
    # 只在同 agent_type 的角色记忆间查找关联
    # 跨类型记忆不参与关联计算
```

## 完整数据流

```
主会话收到任务
     │
     ▼
  AgentRegistry.assign("Explore") → "kaze"
     │
     ▼
  启动子代理，注入角色身份
  "你是 Kaze，一个 Explore 型代理。"
     │
     ▼
  执行前：retrieve_merged("任务关键词")
  ├─ kaze/memories.jsonl      ← 自己的经验
  ├─ mirin/memories.jsonl     ← 同类型同事的经验
  ├─ shared/memories.jsonl    ← 通用知识
  └─ 合并注入 prompt
     │
     ▼
  子代理完成任务
     │
     ▼
  create_memory_from_task(task_info, agent_name="kaze")
  ├─ Haiku 提取 keywords/tags/context/importance
  ├─ 自动分类 → personal 或 shared
  ├─ link_memory() → 仅同类型角色间关联
  └─ 持久化到对应 JSONL
     │
     ▼
  check_promotion() → 被 ≥3 角色命中则晋升 shared
     │
     ▼
  AgentRegistry.release("kaze") → idle
```

## 向后兼容

- `store_path` 参数保留，直接指定路径时跳过角色逻辑
- 旧的 `memories.jsonl`（根目录）保留但不再新增，作为迁移源
- 现有测试通过 `store_path` 参数继续使用临时文件，不受影响

## 实施计划

| 阶段 | 内容 |
|------|------|
| Phase 6a | AgentRegistry + names.json + registry.json |
| Phase 6b | Memory dataclass + MemoryStore 双层改造 |
| Phase 6c | associator 同类型限制 + extractor 接入角色 |
| Phase 6d | CLI + inject + export 适配 |
| Phase 6e | 单元测试 + 集成测试更新 |

## Phase 7: 邻居演化机制

### 概述

借鉴 A-MEM 的 `update_neighbor` 模式，当新记忆创建时，LLM 主动决策是否更新已有邻居记忆的 context/tags/keywords。将知识网络从静态图变为自我修复的活图。

### 触发流程

```
create_memory_from_task()
     ├─ extract_memory_fields()        ← 已有
     ├─ link_memory()                  ← 已有
     ├─ store.add(memory)              ← 已有
     └─ evolve_neighbors()             ← 新增（auto_evolve=True 时）
         ├─ Step 1: should_evolve?（Haiku，~200 tokens）
         ├─ Step 2: generate_evolution_plan（Haiku，~300 tokens）
         └─ Step 3: execute_evolution（纯代码）
```

### Haiku 3 步分解

**Step 1 — 判断（1 次 Haiku 调用）**

输入：新记忆摘要 + top-3 邻居摘要
输出：`{"should_evolve": bool, "reason": "..."}`
False → 直接返回，省 2 次 API 调用

**Step 2 — 生成指令（1 次 Haiku 调用，仅 should_evolve=True）**

输入：新记忆完整内容 + 邻居完整内容
输出：
```json
{
  "updates": [
    {
      "neighbor_id": "kaze_20260313_001",
      "new_context": "LaTeX 字体问题排查，解决方案：fc-cache -fv",
      "add_tags": ["solved"],
      "add_keywords": ["fc-cache"]
    }
  ]
}
```
最多 3 条 updates。

**Step 3 — 执行（纯代码，0 次 LLM 调用）**

- 更新邻居的 context/tags/keywords
- 追加 evolution_history 记录
- store.update() 持久化

### 数据模型变更

Memory 新增 `evolution_history` 字段：

```python
evolution_history: list = field(default_factory=list)
# 每条记录：
# {
#   "timestamp": "2026-03-13T14:30:00",
#   "triggered_by": "mirin_20260313_002",
#   "changes": {
#       "context": {"old": "...", "new": "..."},
#       "tags": {"added": ["solved"]},
#       "keywords": {"added": ["fc-cache"]}
#   }
# }
```

控制膨胀：每条记忆最多保留最近 10 条演化历史。

### 新模块：scripts/evolver.py

```python
def should_evolve(new_memory, neighbors, client) -> tuple[bool, str]
def generate_evolution_plan(new_memory, neighbors, client) -> list[dict]
def execute_evolution(plan, store, triggered_by_id) -> list[str]
def evolve_neighbors(new_memory, store, agent_type=None, max_neighbors=3) -> list[str]
```

### 约束

- 演化只在同类型角色的记忆间发生
- 每次最多更新 3 个邻居
- Haiku API 失败时静默跳过（不影响主流程）
- auto_evolve 参数控制是否启用

### Token 消耗

| 场景 | Haiku 调用 | 估算 tokens |
|------|-----------|-------------|
| 不需要演化 | 1 次 | ~200 |
| 需要演化 | 2 次 | ~500 |
| A-MEM 对比 | 2 次（无条件） | ~800+ |
