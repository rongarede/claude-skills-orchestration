#!/usr/bin/env python3
"""Export memories to Obsidian notes and generate visualizations.

Exports:
1. Individual memory notes to 300_Resources/Agent_Memory/
2. A MOC (Map of Content) index note
3. A Mermaid graph showing memory associations
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory_store import Memory, MemoryStore

OBSIDIAN_VAULT = Path(os.path.expanduser("~/Obsidian"))
MEMORY_DIR = OBSIDIAN_VAULT / "300_Resources" / "Agent_Memory"
DEFAULT_STORE = os.path.expanduser("~/.claude/memory/memories")


def export_memory_note(memory: Memory, output_dir: Path) -> Path:
    """Export a single memory as an Obsidian note.

    Returns the path to the created note.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build note content
    filename = f"{memory.id}.md"
    filepath = output_dir / filename

    # Related links as wikilinks
    related_links = ", ".join([f"[[{rid}]]" for rid in memory.related_ids]) if memory.related_ids else "无"

    content = f"""---
title: "{memory.id}"
date: {memory.timestamp[:10] if len(memory.timestamp) >= 10 else datetime.now().strftime('%Y-%m-%d')}
tags:
{chr(10).join(f'  - {t}' for t in memory.tags)}
  - agent-memory
up: "[[_agent_memory_moc]]"
importance: {memory.importance}
access_count: {memory.access_count}
---

# {memory.id}

## 内容

{memory.content}

## 语境

{memory.context}

## 关键词

{', '.join(memory.keywords)}

## 关联记忆

{related_links}

## 元数据

| 字段 | 值 |
|------|-----|
| 重要性 | {memory.importance}/10 |
| 访问次数 | {memory.access_count} |
| 最后访问 | {memory.last_accessed or '从未'} |
| 创建时间 | {memory.timestamp} |
"""

    filepath.write_text(content, encoding='utf-8')
    return filepath


def export_moc(memories: list[Memory], output_dir: Path) -> Path:
    """Export a Map of Content (MOC) index for all memories."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "_agent_memory_moc.md"

    # Sort by importance (desc), then timestamp (desc)
    sorted_mems = sorted(memories, key=lambda m: (-m.importance, m.timestamp), reverse=False)

    # Group by tags
    tag_groups: dict[str, list[Memory]] = {}
    for m in sorted_mems:
        for t in m.tags:
            if t != "agent-memory":
                tag_groups.setdefault(t, []).append(m)

    # Build MOC
    lines = [
        "---",
        'title: "Agent Memory MOC"',
        "tags:",
        "  - moc",
        "  - agent-memory",
        'up: "[[300_Resources/_resources_moc]]"',
        "---",
        "",
        "# Agent Memory MOC",
        "",
        f"总记忆数: {len(memories)} | 总关联: {sum(len(m.related_ids) for m in memories)}",
        "",
        "## 按重要性排序",
        "",
    ]

    for m in sorted_mems:
        imp_bar = "█" * m.importance + "░" * (10 - m.importance)
        links_count = len(m.related_ids)
        lines.append(f"- [[{m.id}]] | {imp_bar} | {m.content[:50]}... | {links_count} links")

    lines.extend(["", "## 按标签分组", ""])
    for tag, mems in sorted(tag_groups.items()):
        lines.append(f"### {tag}")
        for m in mems:
            lines.append(f"- [[{m.id}]] — {m.content[:40]}...")
        lines.append("")

    # Dataview query
    lines.extend([
        "## 动态索引",
        "",
        "```dataview",
        'TABLE importance AS "重要性", access_count AS "访问次数", file.ctime AS "创建时间"',
        'FROM "300_Resources/Agent_Memory"',
        'WHERE contains(up, this.file.link)',
        'SORT importance DESC',
        "```",
    ])

    filepath.write_text('\n'.join(lines), encoding='utf-8')
    return filepath


def export_mermaid_graph(memories: list[Memory], output_dir: Path) -> Path:
    """Generate a Mermaid graph showing memory associations."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "memory_graph.md"

    lines = [
        "---",
        'title: "记忆关联图谱"',
        "tags:",
        "  - graph",
        "  - agent-memory",
        'up: "[[_agent_memory_moc]]"',
        "---",
        "",
        "# 记忆关联图谱",
        "",
        "```mermaid",
        "graph LR",
    ]

    # Add nodes
    for m in memories:
        # Truncate content for node label
        label = m.content[:30].replace('"', "'")
        # Color by importance
        if m.importance >= 8:
            lines.append(f'    {m.id}["{label}"]:::high')
        elif m.importance >= 5:
            lines.append(f'    {m.id}["{label}"]:::medium')
        else:
            lines.append(f'    {m.id}["{label}"]:::low')

    # Add edges
    seen_edges: set[tuple[str, str]] = set()
    for m in memories:
        for rid in m.related_ids:
            edge = tuple(sorted([m.id, rid]))
            if edge not in seen_edges:
                seen_edges.add(edge)
                lines.append(f"    {m.id} --- {rid}")

    # Styles
    lines.extend([
        "",
        "    classDef high fill:#ff6b6b,stroke:#333,color:#fff",
        "    classDef medium fill:#ffd93d,stroke:#333,color:#333",
        "    classDef low fill:#6bcb77,stroke:#333,color:#fff",
        "```",
        "",
        "**图例：** 🔴 高重要性(8-10) | 🟡 中重要性(5-7) | 🟢 低重要性(1-4)",
    ])

    filepath.write_text('\n'.join(lines), encoding='utf-8')
    return filepath


def export_all(store_path: str = None, output_dir: str = None, agent_name: str = None) -> dict:
    """Export memories to Obsidian.

    当 agent_name 指定时，只导出该角色的个人记忆。
    未指定时导出全部记忆（向后兼容）。

    Returns dict with counts and paths.
    """
    if agent_name:
        from registry import AgentRegistry
        registry = AgentRegistry()
        agent_type = registry.get_agent_type(agent_name)
        store = MemoryStore(agent_name=agent_name, agent_type=agent_type)
    else:
        store = MemoryStore(store_path=store_path or DEFAULT_STORE)

    memories = store.load_all()
    out = Path(output_dir) if output_dir else MEMORY_DIR

    # 当指定角色时，将导出目录设为角色专属子目录
    if agent_name and not output_dir:
        out = MEMORY_DIR / agent_name

    if not memories:
        return {"status": "empty", "count": 0}

    # Export individual notes
    note_paths = []
    for m in memories:
        p = export_memory_note(m, out)
        note_paths.append(str(p))

    # Export MOC
    moc_path = export_moc(memories, out)

    # Export graph
    graph_path = export_mermaid_graph(memories, out)

    return {
        "status": "success",
        "count": len(memories),
        "notes": note_paths,
        "moc": str(moc_path),
        "graph": str(graph_path),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Export memories to Obsidian")
    parser.add_argument("--store", default=DEFAULT_STORE, help="Path to memory store directory")
    parser.add_argument("--output", default=str(MEMORY_DIR), help="Output directory")
    parser.add_argument("--agent", default=None, help="角色名，只导出该角色的记忆")
    args = parser.parse_args()

    result = export_all(args.store, args.output, agent_name=args.agent)

    if result["status"] == "empty":
        print("No memories to export.")
    else:
        print(f"Exported {result['count']} memories")
        print(f"  MOC: {result['moc']}")
        print(f"  Graph: {result['graph']}")
        for p in result["notes"]:
            print(f"  Note: {p}")
