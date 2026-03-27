"""Extractor: Claude API-based memory field extraction.

Calls Claude Haiku to extract structured memory fields (keywords, tags, context, importance)
from task completion information.
"""

import json
import os
from datetime import datetime
from typing import Optional

from memory_store import Memory, MemoryStore
from associator import link_memory


def get_client():
    """Get Anthropic client. Separated for easy mocking in tests."""
    import anthropic
    return anthropic.Anthropic()


def build_extraction_prompt(task_info: dict) -> str:
    """Build the LLM prompt for memory field extraction."""
    subject = task_info.get("subject", "N/A")
    description = task_info.get("description", "N/A")

    return f"""从以下任务完成信息中提取记忆字段。返回严格的 JSON 格式（不要 markdown 代码块）。

任务标题: {subject}
任务描述: {description}

请提取:
1. keywords: 至少3个关键词，按重要性排序（数组）
2. tags: 至少3个分类标签，如 bug-fix, feature, research, thesis, config 等（数组）
3. context: 一句话语境摘要，不超过50字（字符串）
4. importance: 重要性评分 1-10，1=日常琐事 10=重大决策（整数）

JSON 格式:
{{"keywords": [...], "tags": [...], "context": "...", "importance": N}}"""


def extract_memory_fields(task_info: dict) -> dict:
    """Extract memory fields from task info using Claude API.

    Args:
        task_info: dict with 'subject', 'description', 'task_id'

    Returns:
        dict with 'keywords', 'tags', 'context', 'importance'
    """
    fallback = {
        "keywords": _fallback_keywords(task_info),
        "tags": ["task"],
        "context": task_info.get("subject", "任务完成"),
        "importance": 5
    }

    try:
        client = get_client()
        prompt = build_extraction_prompt(task_info)

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_text = response.content[0].text.strip()

        # Try to parse JSON (handle possible markdown code blocks)
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        result = json.loads(raw_text)

        # Validate fields
        if not isinstance(result.get("keywords"), list) or len(result["keywords"]) < 1:
            result["keywords"] = fallback["keywords"]
        if not isinstance(result.get("tags"), list) or len(result["tags"]) < 1:
            result["tags"] = fallback["tags"]
        if not isinstance(result.get("context"), str) or len(result["context"]) == 0:
            result["context"] = fallback["context"]
        if not isinstance(result.get("importance"), int) or not (1 <= result["importance"] <= 10):
            result["importance"] = fallback["importance"]

        return result

    except (json.JSONDecodeError, KeyError, IndexError):
        return fallback
    except Exception:
        return fallback


def _fallback_keywords(task_info: dict) -> list:
    """Generate fallback keywords from task subject."""
    import re
    subject = task_info.get("subject", "") + " " + task_info.get("description", "")
    # Extract Chinese and English words
    tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z0-9_]+', subject)
    # Take first 5 unique tokens
    seen = set()
    keywords = []
    for t in tokens:
        if t.lower() not in seen and len(t) > 1:
            seen.add(t.lower())
            keywords.append(t)
            if len(keywords) >= 5:
                break
    return keywords or ["task"]


def create_memory_from_task(
    task_info: dict,
    store: MemoryStore,
    auto_link: bool = True,
    agent_name: str = None,
    auto_evolve: bool = True,
) -> Memory:
    """Create a complete Memory from task info: extract fields, store, and optionally link.

    Args:
        task_info: dict with 'subject', 'description', 'task_id'
        store: MemoryStore instance
        auto_link: whether to auto-link with existing memories
        agent_name: 指定时，用作 Memory 的 owner 字段，并限制关联只在同类型角色间发生
        auto_evolve: 是否在记忆创建后触发邻居演化（需要 related_ids 非空）

    Returns:
        The created Memory object
    """
    # Extract fields via LLM
    fields = extract_memory_fields(task_info)

    # Build content from subject + description
    subject = task_info.get("subject", "")
    description = task_info.get("description", "")
    content = f"{subject}: {description}" if description else subject

    # Auto-classify scope
    scope = _classify_scope(fields)

    # Create memory
    memory = Memory(
        id=store.generate_id(),
        content=content,
        timestamp=datetime.now().isoformat(),
        keywords=fields["keywords"],
        tags=fields["tags"],
        context=fields["context"],
        importance=fields["importance"],
        owner=agent_name or "",
        scope=scope,
    )

    # Auto-link with existing memories
    if auto_link:
        # 获取 agent_type 以限制关联只在同类型角色间发生
        agent_type = None
        if agent_name:
            from registry import AgentRegistry
            registry = AgentRegistry()
            agent_type = registry.get_agent_type(agent_name)
        memory = link_memory(memory, store, threshold=0.2, agent_type=agent_type)

    # 若分类为 shared，同时写入共享层
    if scope == "shared":
        from pathlib import Path
        import os as _os
        shared_path = Path(_os.path.expanduser("~/.claude/memory/shared"))
        shared_path.parent.mkdir(parents=True, exist_ok=True)
        shared_store = MemoryStore(store_path=str(shared_path))
        # 生成 shared ID：使用 shared_ 前缀 + 今日日期，序号自动递增
        today = datetime.now().strftime("%Y%m%d")
        shared_id = shared_store.generate_id(id_prefix=f"shared_{today}")
        shared_memory = Memory(
            id=shared_id,
            content=memory.content,
            timestamp=memory.timestamp,
            keywords=memory.keywords[:],
            tags=memory.tags[:],
            context=memory.context,
            importance=memory.importance,
            owner="shared",
            scope="shared",
        )
        shared_store.add(shared_memory)

    # Persist
    store.add(memory)

    # 触发邻居演化（Phase 7）：记忆已入库后，主动更新相关邻居的 context/tags/keywords
    if auto_evolve and memory.related_ids:
        try:
            from evolver import evolve_neighbors
            agent_type = None
            if agent_name:
                from registry import AgentRegistry
                registry = AgentRegistry()
                agent_type = registry.get_agent_type(agent_name)
            evolve_neighbors(memory, store, agent_type=agent_type)
        except Exception:
            pass  # 静默回退 — 演化失败不影响记忆创建

    return memory


def _classify_scope(fields: dict) -> str:
    """自动分类记忆的 scope：shared 或 personal。

    判断规则：importance >= 8 且包含通用架构/配置类 tag → shared；否则 personal。
    """
    shared_tags = {
        "architecture", "convention", "config", "standard", "rule",
        "configuration", "infrastructure", "protocol",
    }
    if fields.get("importance", 0) >= 8:
        if any(tag in shared_tags for tag in fields.get("tags", [])):
            return "shared"
    return "personal"
