"""
邻居演化引擎

当新记忆创建时，LLM 主动决策是否更新已有邻居记忆的 context/tags/keywords。
采用 3 步分解调用：判断 → 生成指令 → 执行更新。

Feedback 联动（Phase 3-D）：
- blocked 记忆跳过演化（不浪费资源）
- warning 记忆降低演化优先级（排在 healthy 之后）
- 正面反馈记忆优先演化，演化时额外 +0.1 importance boost（最高 10）
- 合并时继承两条源记忆中更好的 feedback 元数据
"""

import dataclasses
import json
import os
import sys
from datetime import datetime
from typing import Optional

from memory_store import Memory, MemoryStore

MAX_EVOLUTION_HISTORY = 10

# feedback ratio 阈值：超过此值视为正面反馈，演化时给予 importance boost
_POSITIVE_RATIO_THRESHOLD = 0.7
# importance boost 幅度（正面反馈记忆演化时）
_IMPORTANCE_BOOST = 1
# importance 上限
_MAX_IMPORTANCE = 10


# ==================== Feedback 优先级工具 ====================

def _get_health_and_ratio(memory: Memory) -> tuple:
    """返回 (health: str, ratio: float) 用于排序。

    health 优先级权重：healthy=2, warning=1, blocked=0（不会进入演化）
    """
    from feedback_loop import check_memory_health, get_feedback_ratio
    health = check_memory_health(memory)
    ratio = get_feedback_ratio(memory)
    return health, ratio


def _filter_and_prioritize(memories: list) -> list:
    """过滤 blocked 记忆，按 health + feedback_ratio 排序，返回优先级排序列表。

    规则：
    1. blocked 记忆被完全过滤（ratio <= 0.2 且 negative >= 5）
    2. healthy 记忆排在 warning 记忆之前
    3. 相同 health 状态内，按 feedback_ratio 降序排列

    Args:
        memories: Memory 列表

    Returns:
        过滤并排序后的 Memory 列表（blocked 已移除）
    """
    from feedback_loop import check_memory_health, get_feedback_ratio

    result = []
    for mem in memories:
        health = check_memory_health(mem)
        if health == "blocked":
            continue
        result.append(mem)

    # 按 health 等级（healthy > warning）和 ratio 降序排列
    health_order = {"healthy": 1, "warning": 0}

    def sort_key(mem):
        health = check_memory_health(mem)
        ratio = get_feedback_ratio(mem)
        return (health_order.get(health, 0), ratio)

    result.sort(key=sort_key, reverse=True)
    return result


def merge_feedback(mem_a: Memory, mem_b: Memory) -> Memory:
    """合并两条记忆的 feedback 元数据，继承较好的那条的数据。

    "较好"定义：positive_feedback 绝对值更高。
    若相等，则取 negative_feedback 更低的。

    Args:
        mem_a: 第一条记忆
        mem_b: 第二条记忆

    Returns:
        一个新的 Memory 对象（以 mem_b 为基础），继承最佳 feedback 数据。
        使用 dataclasses.replace() 确保不可变性。
    """
    # 选出 feedback 更好的那条
    if mem_a.positive_feedback > mem_b.positive_feedback:
        best = mem_a
    elif mem_b.positive_feedback > mem_a.positive_feedback:
        best = mem_b
    else:
        # positive 相等，选 negative 更低的
        best = mem_a if mem_a.negative_feedback <= mem_b.negative_feedback else mem_b

    return dataclasses.replace(
        mem_b,
        positive_feedback=best.positive_feedback,
        negative_feedback=best.negative_feedback,
    )


def get_client():
    """获取 Anthropic 客户端（与 extractor 共享，便于统一 mock）"""
    import anthropic
    return anthropic.Anthropic()


def _build_should_evolve_prompt(new_memory: Memory, neighbors: list) -> str:
    """构建 Step 1 prompt：判断是否需要演化"""
    neighbor_summaries = []
    for n in neighbors:
        neighbor_summaries.append(
            f"- [{n.id}] {n.context} (keywords: {', '.join(n.keywords[:5])})"
        )

    return f"""你是一个记忆管理系统。判断新记忆是否包含能更新已有邻居记忆的新信息。

新记忆：
- 内容：{new_memory.content}
- 关键词：{', '.join(new_memory.keywords)}
- 上下文：{new_memory.context}

已有邻居记忆：
{chr(10).join(neighbor_summaries)}

判断：新记忆是否包含邻居尚未知道的信息（如解决方案、新发现、修正）？
如果邻居的 context 已经完整，不需要更新。

返回 JSON（不要包含其他文本）：
{{"should_evolve": true/false, "reason": "一句话说明原因"}}"""


def _build_evolution_plan_prompt(new_memory: Memory, neighbors: list) -> str:
    """构建 Step 2 prompt：生成演化指令"""
    neighbor_details = []
    for n in neighbors:
        neighbor_details.append(
            f"ID: {n.id}\n内容: {n.content}\n上下文: {n.context}\n关键词: {', '.join(n.keywords)}\n标签: {', '.join(n.tags)}"
        )

    return f"""你是一个记忆管理系统。根据新记忆的信息，为需要更新的邻居记忆生成更新指令。

新记忆：
内容：{new_memory.content}
关键词：{', '.join(new_memory.keywords)}
上下文：{new_memory.context}

邻居记忆：
{(chr(10) + '---' + chr(10)).join(neighbor_details)}

规则：
1. 只更新真正需要补充信息的邻居
2. new_context 应该在原有 context 基础上补充新信息，不要完全重写
3. add_tags 和 add_keywords 只添加新的，不重复已有的
4. 最多更新 3 个邻居

返回 JSON（不要包含其他文本）：
{{"updates": [{{"neighbor_id": "xxx", "new_context": "更新后的上下文", "add_tags": ["tag1"], "add_keywords": ["kw1"]}}]}}"""


def should_evolve(
    new_memory: Memory,
    neighbors: list,
    client=None,
) -> tuple:
    """
    Step 1: 判断是否需要演化邻居（1 次 Haiku 调用）
    Returns: (should_evolve: bool, reason: str)
    """
    if not neighbors:
        return (False, "no neighbors")

    if client is None:
        client = get_client()

    prompt = _build_should_evolve_prompt(new_memory, neighbors)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # 从响应中提取 JSON
        if '{' in text:
            text = text[text.index('{'):text.rindex('}') + 1]
        result = json.loads(text)
        return (result.get("should_evolve", False), result.get("reason", ""))
    except Exception as e:
        return (False, f"error: {str(e)}")


def generate_evolution_plan(
    new_memory: Memory,
    neighbors: list,
    client=None,
) -> list:
    """
    Step 2: 生成演化指令（1 次 Haiku 调用）
    Returns: list of update dicts
    """
    if client is None:
        client = get_client()

    prompt = _build_evolution_plan_prompt(new_memory, neighbors)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if '{' in text:
            text = text[text.index('{'):text.rindex('}') + 1]
        result = json.loads(text)
        updates = result.get("updates", [])
        # 最多更新 3 个邻居
        return updates[:3]
    except Exception as e:
        print(f"[evolver] generate_evolution_plan error: {e}", file=sys.stderr)
        return []


def execute_evolution(
    plan: list,
    store: MemoryStore,
    triggered_by_id: str,
) -> list:
    """
    Step 3: 执行演化更新 + 记录 evolution_history（纯代码）

    Feedback 联动：
    - 正面反馈记忆（ratio > _POSITIVE_RATIO_THRESHOLD）演化时额外获得 importance boost
    - 使用 dataclasses.replace() 确保不可变性

    Returns: list of updated memory IDs
    """
    from feedback_loop import get_feedback_ratio

    updated_ids = []
    now = datetime.now().isoformat()

    for update in plan:
        neighbor_id = update.get("neighbor_id")
        if not neighbor_id:
            continue

        neighbor = store.get(neighbor_id)
        if not neighbor:
            continue

        changes = {}
        new_context = neighbor.context
        new_tags = list(neighbor.tags)
        new_keywords = list(neighbor.keywords)
        new_importance = neighbor.importance
        new_history = list(neighbor.evolution_history)

        # 更新 context
        ctx = update.get("new_context")
        if ctx and ctx != neighbor.context:
            changes["context"] = {"old": neighbor.context, "new": ctx}
            new_context = ctx

        # 新增 tags
        add_tags = update.get("add_tags", [])
        if add_tags:
            extra_tags = [t for t in add_tags if t not in neighbor.tags]
            if extra_tags:
                changes["tags"] = {"added": extra_tags}
                new_tags = list(set(new_tags + extra_tags))

        # 新增 keywords
        add_keywords = update.get("add_keywords", [])
        if add_keywords:
            extra_kw = [k for k in add_keywords if k not in neighbor.keywords]
            if extra_kw:
                changes["keywords"] = {"added": extra_kw}
                new_keywords = list(set(new_keywords + extra_kw))

        if not changes:
            continue

        # 正面反馈 importance boost（不可变方式计算新值）
        ratio = get_feedback_ratio(neighbor)
        if ratio > _POSITIVE_RATIO_THRESHOLD:
            new_importance = min(_MAX_IMPORTANCE, neighbor.importance + _IMPORTANCE_BOOST)
            if new_importance != neighbor.importance:
                changes["importance"] = {"old": neighbor.importance, "new": new_importance}

        # 追加演化历史
        history_entry = {
            "timestamp": now,
            "triggered_by": triggered_by_id,
            "changes": changes,
        }
        new_history.append(history_entry)

        # 截断历史到 MAX_EVOLUTION_HISTORY
        if len(new_history) > MAX_EVOLUTION_HISTORY:
            new_history = new_history[-MAX_EVOLUTION_HISTORY:]

        # 使用 dataclasses.replace() 确保不可变性
        updated_neighbor = dataclasses.replace(
            neighbor,
            context=new_context,
            tags=new_tags,
            keywords=new_keywords,
            importance=new_importance,
            evolution_history=new_history,
        )
        store.update(updated_neighbor)
        updated_ids.append(neighbor_id)

    return updated_ids


def evolve_neighbors(
    new_memory: Memory,
    store: MemoryStore,
    agent_type: str = None,
    max_neighbors: int = 3,
) -> list:
    """
    入口函数：完整的邻居演化流程

    1. 找 top-N 同类型邻居
    2. should_evolve() → 不需要则 return []
    3. generate_evolution_plan()
    4. execute_evolution()
    5. return 被更新的 ID 列表
    """
    from associator import find_associations

    # 找邻居（复用 associator 的逻辑）
    try:
        neighbor_ids = find_associations(
            new_memory, store, top_k=max_neighbors,
            threshold=0.2, agent_type=agent_type,
        )
    except Exception:
        neighbor_ids = []

    if not neighbor_ids:
        return []

    # 加载邻居 Memory 对象
    neighbors = []
    for nid in neighbor_ids:
        mem = store.get(nid)
        if mem:
            neighbors.append(mem)

    # 若同类型跨角色场景，在其他存储中查找未找到的邻居
    if not neighbors and agent_type:
        from registry import AgentRegistry
        from pathlib import Path
        registry = AgentRegistry()
        same_type_agents = registry.get_agents_by_type(agent_type)
        base = Path(os.path.expanduser("~/.claude/memory"))
        for agent in same_type_agents:
            agent_path = base / "agents" / agent
            if agent_path.exists():
                agent_store = MemoryStore(store_path=str(agent_path))
                for nid in neighbor_ids:
                    mem = agent_store.get(nid)
                    if mem:
                        neighbors.append(mem)

    if not neighbors:
        return []

    # Feedback 过滤 + 优先级排序：blocked 跳过，warning 降级，正面优先
    neighbors = _filter_and_prioritize(neighbors)

    if not neighbors:
        return []

    # Step 1: 是否需要演化？
    try:
        do_evolve, reason = should_evolve(new_memory, neighbors)
    except Exception:
        return []

    if not do_evolve:
        return []

    # Step 2: 生成演化指令
    try:
        plan = generate_evolution_plan(new_memory, neighbors)
    except Exception:
        return []

    if not plan:
        return []

    # Step 3: 执行演化
    updated = execute_evolution(plan, store, new_memory.id)

    # 检查跨角色存储中尚未更新的条目
    if agent_type:
        updated_set = set(updated)
        remaining = [u for u in plan if u.get("neighbor_id") not in updated_set]
        if remaining:
            from registry import AgentRegistry
            from pathlib import Path
            registry = AgentRegistry()
            same_type_agents = registry.get_agents_by_type(agent_type)
            base = Path(os.path.expanduser("~/.claude/memory"))
            for agent in same_type_agents:
                agent_path = base / "agents" / agent
                if agent_path.exists():
                    agent_store = MemoryStore(store_path=str(agent_path))
                    cross_updated = execute_evolution(remaining, agent_store, new_memory.id)
                    updated.extend(cross_updated)

    return updated
