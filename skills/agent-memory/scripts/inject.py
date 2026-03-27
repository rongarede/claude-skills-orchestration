"""Memory injection: enrich subagent prompts with relevant historical memories.

Provides functions to:
1. Build injection context from memory store
2. Enrich an agent prompt with relevant memories
3. Mark memories as used (update access metadata)
4. Evolve memories (passive update of context/tags/keywords)
"""

from datetime import datetime
from typing import Optional

from memory_store import Memory, MemoryStore
from retriever import retrieve, format_for_prompt


def build_injection_context(
    query: str,
    store: MemoryStore,
    top_k: int = 3,
    spread: bool = True,
    max_chars: int = 2000,
    agent_name: str = None,
    agent_type: str = None,
) -> str:
    """Build a memory context block for injection into a subagent prompt.

    Args:
        query: the task description or search query
        store: memory store instance
        top_k: number of top memories
        spread: enable spreading activation
        max_chars: maximum character limit for the context block
        agent_name: 角色名，指定后使用合并检索（个人 + 同类型 + shared）
        agent_type: 角色类型，用于合并检索时筛选同类型角色

    Returns:
        Formatted markdown string, or empty string if no relevant memories.
    """
    # 当 agent_name 指定且 store 支持合并检索时，使用双层检索
    if agent_name and hasattr(store, 'retrieve_merged') and store.agent_name:
        results = store.retrieve_merged(query, top_k=top_k, spread=spread)
    else:
        results = retrieve(query, store, top_k=top_k, spread=spread)

    if not results:
        return ""

    context = format_for_prompt(results)

    # 截断超出 max_chars 的部分
    if len(context) > max_chars:
        context = context[:max_chars] + "\n\n...(记忆已截断)\n"

    return context


def enrich_agent_prompt(
    original_prompt: str,
    store: MemoryStore,
    top_k: int = 3,
    spread: bool = True,
    max_chars: int = 2000,
    agent_name: str = None,
    agent_type: str = None,
) -> str:
    """Enrich a subagent prompt with relevant memories.

    Prepends relevant memory context before the original prompt.
    If no relevant memories found, returns original prompt unchanged.

    Args:
        original_prompt: the original task prompt for the subagent
        store: memory store instance
        top_k: number of memories to inject
        spread: enable spreading activation
        max_chars: max chars for memory section
        agent_name: 角色名，指定后使用合并检索
        agent_type: 角色类型，用于合并检索时筛选同类型角色

    Returns:
        Enriched prompt string.
    """
    context = build_injection_context(
        query=original_prompt,
        store=store,
        top_k=top_k,
        spread=spread,
        max_chars=max_chars,
        agent_name=agent_name,
        agent_type=agent_type,
    )

    if not context:
        return original_prompt

    return f"{context}\n---\n\n{original_prompt}"


def mark_memories_used(memory_ids: list[str], store: MemoryStore) -> None:
    """Mark memories as accessed (update access_count and last_accessed).

    Called after memories are successfully injected into a subagent prompt.
    """
    now = datetime.now().isoformat()
    for mid in memory_ids:
        mem = store.get(mid)
        if mem:
            mem.access_count += 1
            mem.last_accessed = now
            store.update(mem)


def evolve_memory(
    memory_id: str,
    store: MemoryStore,
    context: Optional[str] = None,
    tags: Optional[list[str]] = None,
    add_keywords: Optional[list[str]] = None,
) -> Optional[Memory]:
    """Passively evolve a memory by updating its context, tags, or keywords.

    This is the simplified version of A-MEM's Memory Evolution —
    instead of automatic LLM-driven evolution on every write,
    we allow manual/triggered updates after a memory has been used.

    Args:
        memory_id: ID of the memory to evolve
        store: memory store instance
        context: new context string (replaces existing)
        tags: new tags list (replaces existing)
        add_keywords: additional keywords to append

    Returns:
        Updated Memory object, or None if not found.
    """
    mem = store.get(memory_id)
    if not mem:
        return None

    if context is not None:
        mem.context = context
    if tags is not None:
        mem.tags = tags
    if add_keywords is not None:
        existing = set(mem.keywords)
        for kw in add_keywords:
            if kw not in existing:
                mem.keywords.append(kw)

    store.update(mem)
    return mem
