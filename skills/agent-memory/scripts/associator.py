"""Associator: manages memory links (A-MEM style association chains).

When a new memory is created, find top-5 similar existing memories via BM25.
If similarity exceeds threshold, establish bidirectional links.
"""

import os
from pathlib import Path

from memory_store import Memory, MemoryStore
from retriever import compute_relevance_scores, tokenize


def find_associations(
    new_memory: Memory,
    store: MemoryStore,
    top_k: int = 5,
    threshold: float = 0.3,
    agent_type: str = None,
) -> list[str]:
    """Find existing memories that should be linked to a new memory.

    Args:
        new_memory: the newly created memory
        store: memory store (used as fallback when agent_type is None)
        top_k: number of candidates to consider
        threshold: minimum BM25 relevance score to establish link
        agent_type: 指定时，只在同类型角色的记忆中搜索

    Returns:
        List of memory IDs that should be linked.
    """
    if agent_type:
        # 收集同类型所有角色的记忆
        from registry import AgentRegistry
        registry = AgentRegistry()
        same_type_agents = registry.get_agents_by_type(agent_type)
        base = Path(os.path.expanduser("~/.claude/memory"))
        all_memories = []
        for agent in same_type_agents:
            agent_path = base / "agents" / agent
            if agent_path.exists():
                agent_store = MemoryStore(store_path=str(agent_path))
                all_memories.extend(agent_store.load_all())
        existing = [m for m in all_memories if m.id != new_memory.id]
    else:
        existing = [m for m in store.load_all() if m.id != new_memory.id]

    if not existing:
        return []

    # Use content + keywords + context as query
    query = ' '.join(new_memory.keywords) + ' ' + new_memory.content + ' ' + new_memory.context
    scores = compute_relevance_scores(query, existing)

    # Filter by threshold and take top-k
    candidates = [(existing[i], scores[i]) for i in range(len(existing)) if scores[i] >= threshold]
    candidates.sort(key=lambda x: x[1], reverse=True)

    return [mem.id for mem, _ in candidates[:top_k]]


def link_memory(
    new_memory: Memory,
    store: MemoryStore,
    top_k: int = 5,
    threshold: float = 0.3,
    agent_type: str = None,
) -> Memory:
    """Find associations and establish bidirectional links.

    Modifies both the new memory and the linked existing memories.

    Args:
        new_memory: the newly created memory
        store: memory store for the new memory (also used for reverse links when agent_type is None)
        top_k: number of candidates to consider
        threshold: minimum BM25 relevance score to establish link
        agent_type: 指定时，只在同类型角色间建立关联
    """
    associated_ids = find_associations(new_memory, store, top_k, threshold, agent_type)

    if not associated_ids:
        return new_memory

    # Update new memory's links
    new_memory.related_ids = list(set(new_memory.related_ids + associated_ids))

    if agent_type:
        # 跨角色反向链接：找到各记忆所在的角色存储并更新
        from registry import AgentRegistry
        registry = AgentRegistry()
        same_type_agents = registry.get_agents_by_type(agent_type)
        base = Path(os.path.expanduser("~/.claude/memory"))

        for assoc_id in associated_ids:
            # 在同类型各角色的存储中查找该记忆
            for agent in same_type_agents:
                agent_path = base / "agents" / agent
                if agent_path.exists():
                    agent_store = MemoryStore(store_path=str(agent_path))
                    existing = agent_store.get(assoc_id)
                    if existing:
                        existing.related_ids = list(set(existing.related_ids + [new_memory.id]))
                        agent_store.update(existing)
                        break  # 找到即停，避免重复处理
    else:
        # 原始行为：所有记忆在同一个 store 中
        for aid in associated_ids:
            existing = store.get(aid)
            if existing and new_memory.id not in existing.related_ids:
                existing.related_ids = list(set(existing.related_ids + [new_memory.id]))
                store.update(existing)

    return new_memory
