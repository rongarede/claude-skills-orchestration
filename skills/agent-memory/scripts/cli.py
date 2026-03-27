#!/usr/bin/env python3
"""CLI entry point for the agent-memory system.

Usage:
    python3 cli.py retrieve <query> [--top-k N] [--no-spread] [--format prompt|text]
    python3 cli.py add --subject <subject> [--description <desc>] [--keywords k1,k2] [--tags t1,t2] [--importance N]
    python3 cli.py stats
    python3 cli.py list [--limit N]
    python3 cli.py evolve <memory_id> [--context <ctx>] [--tags <tags>]
    python3 cli.py export [--output <dir>]
"""

import argparse
import dataclasses
import os
import sys
from datetime import datetime
from pathlib import Path

# Add scripts dir to path so sibling modules resolve correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory_store import Memory, MemoryStore
from retriever import retrieve, retrieve_cross_agent, format_for_prompt


DEFAULT_STORE = os.path.expanduser("~/.claude/memory/memories")
DEFAULT_EXPORT_DIR = str(Path(os.path.expanduser("~/Obsidian/300_Resources/Agent_Memory")))


# ==================== 工厂函数：根据参数创建 MemoryStore ====================

def get_store(args) -> MemoryStore:
    """根据参数创建合适的 MemoryStore。

    优先级：--store 参数 > --agent 参数 > 默认路径。
    """
    if getattr(args, 'store', None) and args.store != DEFAULT_STORE:
        return MemoryStore(store_path=args.store)
    if getattr(args, 'agent', None):
        from registry import AgentRegistry
        registry = AgentRegistry()
        agent_type = registry.get_agent_type(args.agent)
        return MemoryStore(agent_name=args.agent, agent_type=agent_type)
    return MemoryStore(store_path=args.store)


# ==================== 子命令实现 ====================

def cmd_retrieve(args):
    """检索与查询最相关的记忆，按三维评分排序。"""

    # --cross-agent 模式：自动扫描所有 agent store
    if getattr(args, 'cross_agent', False):
        agents_base = Path(os.path.expanduser("~/.claude/memory/agents"))
        stores = []
        if agents_base.exists():
            for store_path in sorted(agents_base.glob("*/*")):
                if store_path.is_dir():
                    stores.append(MemoryStore(store_path=str(store_path)))
        results = retrieve_cross_agent(
            query=args.query,
            stores=stores,
            top_k=args.top_k,
            spread=not args.no_spread,
        )
        if not results:
            print("未找到相关记忆。")
            return
        if args.format == "prompt":
            print(format_for_prompt(results))
        else:
            for mem, score in results:
                print(f"[{score:.2f}] {mem.id}: {mem.content}")
                print(f"         keywords: {', '.join(mem.keywords)}")
                print(f"         context:  {mem.context}")
                print(f"         importance: {mem.importance}/10 | accessed: {mem.access_count}x")
                if mem.related_ids:
                    print(f"         links: {', '.join(mem.related_ids)}")
                print()
        return

    # --stores 模式：指定多个 store 路径进行跨检索
    if getattr(args, 'stores', None):
        store_paths = [p.strip() for p in args.stores.split(",") if p.strip()]
        stores = [MemoryStore(store_path=p) for p in store_paths]
        results = retrieve_cross_agent(
            query=args.query,
            stores=stores,
            top_k=args.top_k,
            spread=not args.no_spread,
        )
        if not results:
            print("未找到相关记忆。")
            return
        if args.format == "prompt":
            print(format_for_prompt(results))
        else:
            for mem, score in results:
                print(f"[{score:.2f}] {mem.id}: {mem.content}")
                print(f"         keywords: {', '.join(mem.keywords)}")
                print(f"         context:  {mem.context}")
                print(f"         importance: {mem.importance}/10 | accessed: {mem.access_count}x")
                if mem.related_ids:
                    print(f"         links: {', '.join(mem.related_ids)}")
                print()
        return

    store = get_store(args)

    # 当指定 --agent 时使用合并检索（个人 + 同类型 + shared）
    if getattr(args, 'agent', None) and store.agent_name:
        results = store.retrieve_merged(
            query=args.query,
            top_k=args.top_k,
            spread=not args.no_spread,
        )
    else:
        results = retrieve(
            query=args.query,
            store=store,
            top_k=args.top_k,
            spread=not args.no_spread,
        )

    if not results:
        print("未找到相关记忆。")
        return

    if args.format == "prompt":
        print(format_for_prompt(results))
    else:
        for mem, score in results:
            print(f"[{score:.2f}] {mem.id}: {mem.content}")
            print(f"         keywords: {', '.join(mem.keywords)}")
            print(f"         context:  {mem.context}")
            print(f"         importance: {mem.importance}/10 | accessed: {mem.access_count}x")
            if mem.related_ids:
                print(f"         links: {', '.join(mem.related_ids)}")
            print()


def cmd_add(args):
    """手动添加一条记忆。"""
    store = get_store(args)

    # 解析 keywords 和 tags（逗号分隔字符串 → 列表）
    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else [args.subject]
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else ["manual"]

    content = f"{args.subject}: {args.description}" if args.description else args.subject

    memory = Memory(
        id=store.generate_id(),
        content=content,
        timestamp=datetime.now().isoformat(),
        keywords=keywords,
        tags=tags,
        context=args.subject,
        importance=args.importance,
    )

    # 当指定 --agent 时，标记记忆所有者
    if getattr(args, 'agent', None):
        memory = dataclasses.replace(memory, owner=args.agent)

    store.add(memory)

    print(f"记忆已创建: {memory.id}")
    print(f"  content:    {memory.content}")
    print(f"  keywords:   {', '.join(memory.keywords)}")
    print(f"  tags:       {', '.join(memory.tags)}")
    print(f"  importance: {memory.importance}/10")
    if memory.owner:
        print(f"  owner:      {memory.owner}")


def cmd_stats(args):
    """显示记忆库统计信息。"""
    store = get_store(args)
    memories = store.load_all()

    # 当指定 --agent 时，同时展示 shared 记忆统计
    if getattr(args, 'agent', None):
        shared_path = Path(os.path.expanduser("~/.claude/memory/shared"))
        if shared_path.exists():
            shared_store = MemoryStore(store_path=str(shared_path))
            shared_memories = shared_store.load_all()
        else:
            shared_memories = []

        print(f"=== Agent Memory 统计 [{args.agent}] ===")
        if not memories:
            print(f"个人记忆: 0 条")
        else:
            total = len(memories)
            avg_importance = sum(m.importance for m in memories) / total
            total_links = sum(len(m.related_ids) for m in memories)
            total_accesses = sum(m.access_count for m in memories)

            tag_counts: dict[str, int] = {}
            for m in memories:
                for t in m.tags:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            print(f"个人记忆总数:   {total}")
            print(f"平均重要性:     {avg_importance:.1f}/10")
            print(f"总关联链接:     {total_links}")
            print(f"总访问次数:     {total_accesses}")
            print(f"存储路径:       {store.store_path}")
            print("\nTop Tags (个人):")
            for tag, count in top_tags:
                print(f"  {tag}: {count}")

        print(f"\nShared 记忆总数: {len(shared_memories)}")
        if shared_memories:
            avg_shared = sum(m.importance for m in shared_memories) / len(shared_memories)
            print(f"Shared 平均重要性: {avg_shared:.1f}/10")
        return

    if not memories:
        print("记忆库为空。")
        return

    total = len(memories)
    avg_importance = sum(m.importance for m in memories) / total
    total_links = sum(len(m.related_ids) for m in memories)
    total_accesses = sum(m.access_count for m in memories)

    # Tag 分布统计
    tag_counts: dict[str, int] = {}
    for m in memories:
        for t in m.tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    print("=== Agent Memory 统计 ===")
    print(f"记忆总数:     {total}")
    print(f"平均重要性:   {avg_importance:.1f}/10")
    print(f"总关联链接:   {total_links}")
    print(f"总访问次数:   {total_accesses}")
    print(f"存储路径:     {args.store}")
    print("\nTop Tags:")
    for tag, count in top_tags:
        print(f"  {tag}: {count}")


def cmd_evolve(args):
    """更新已有记忆的 context 或 tags。"""
    store = get_store(args)
    memory = store.get(args.memory_id)

    if not memory:
        print(f"记忆 {args.memory_id} 不存在。")
        sys.exit(1)

    updated = False
    replace_kwargs: dict = {}
    if args.context:
        replace_kwargs["context"] = args.context
        updated = True
    if args.tags:
        replace_kwargs["tags"] = [t.strip() for t in args.tags.split(",")]
        updated = True

    if not updated:
        print("未提供任何更新字段（--context 或 --tags）。")
        return

    updated_memory = dataclasses.replace(memory, **replace_kwargs)
    store.update(updated_memory)
    print(f"记忆 {updated_memory.id} 已更新。")
    print(f"  context: {updated_memory.context}")
    print(f"  tags:    {', '.join(updated_memory.tags)}")


def cmd_list(args):
    """列出最近的记忆（按时间戳降序）。"""
    store = get_store(args)
    memories = store.load_all()

    if not memories:
        print("记忆库为空。")
        return

    # 按时间戳降序排列
    memories.sort(key=lambda m: m.timestamp, reverse=True)

    agent_header = f" [{args.agent}]" if getattr(args, 'agent', None) else ""
    print(f"最近 {min(args.limit, len(memories))} 条记忆{agent_header}（共 {len(memories)} 条）：\n")
    for m in memories[: args.limit]:
        links_info = f" [{len(m.related_ids)} links]" if m.related_ids else ""
        owner_info = f" owner:{m.owner}" if m.owner else ""
        preview = m.content[:60] + ("..." if len(m.content) > 60 else "")
        print(f"  {m.id} | imp:{m.importance}/10 | {preview}{links_info}{owner_info}")


def cmd_quick_add(args):
    """直接保存记忆，无需 API 调用"""
    store = get_store(args)

    from memory_store import Memory
    from datetime import datetime

    keywords = [k.strip() for k in args.keywords.split(',')]
    tags = [t.strip() for t in args.tags.split(',')]

    memory = Memory(
        id=store.generate_id(name=args.name, memory_type=args.type),
        content=args.content,
        timestamp=datetime.now().isoformat(),
        name=args.name or '',
        description=args.description or '',
        type=args.type,
        keywords=keywords,
        tags=tags,
        context=args.context or '',
        importance=args.importance,
        owner=getattr(args, 'agent', '') or '',
        scope='personal',
        layer=getattr(args, 'layer', 'L1') or 'L1',
    )

    store.add(memory)

    # 自动关联
    from associator import link_memory
    agent_type = None
    if hasattr(args, 'agent') and args.agent:
        from registry import AgentRegistry
        reg = AgentRegistry()
        agent_type = reg.get_agent_type(args.agent)

    updated = link_memory(memory, store, agent_type=agent_type)
    associations = updated.related_ids

    print(f'已保存: [{memory.id}] {memory.content[:50]}')
    print(f'关键词: {keywords}')
    print(f'标签: {tags}')
    print(f'重要度: {args.importance}')
    if associations:
        print(f'关联: {associations}')

    # 自动刷新索引
    _generate_index(store)


def _generate_index(store: MemoryStore) -> Path:
    """Generate MEMORY.md index grouped by memory type."""
    memories = store.load_all()

    type_order = ["user", "feedback", "task", "knowledge", "project", "reference"]
    grouped: dict[str, list[Memory]] = {t: [] for t in type_order}
    for mem in memories:
        mt = (mem.type or "task").strip().lower() or "task"
        if mt not in grouped:
            grouped[mt] = []
        grouped[mt].append(mem)

    lines: list[str] = ["# Memory Index", ""]
    for mt in type_order:
        items = grouped.get(mt, [])
        if not items:
            continue
        lines.append(f"## {mt.capitalize()}")
        for mem in sorted(items, key=lambda m: m.id):
            title = (mem.name or "").strip() or mem.id
            desc = (mem.description or "").strip() or (mem.context or "").strip() or mem.content.strip()
            desc = desc.replace("\n", " ")
            lines.append(f"- [{title}]({mem.id}.md) — {desc}")
        lines.append("")

    output = store.store_path / "MEMORY.md"
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    # 生成 .index-meta.json 用于后续增量检测
    import json as _json
    meta_path = store.store_path / ".index-meta.json"
    current_files: dict[str, float] = {}
    for f in store.store_path.glob("mem_*.md"):
        current_files[f.name] = f.stat().st_mtime
    for pattern in ["feedback_*.md", "task_*.md"]:
        for f in store.store_path.glob(pattern):
            current_files[f.name] = f.stat().st_mtime
    meta_path.write_text(_json.dumps(current_files, indent=2, ensure_ascii=False), encoding="utf-8")

    return output


def _generate_index_incremental(store_path: Path, force: bool = False) -> dict:
    """增量生成 MEMORY.md 索引。

    通过比较文件 mtime 与 .index-meta.json 中记录的值，
    只重新解析有变化的文件。返回统计 dict: {processed, skipped, removed}。

    参数：
        store_path: 记忆存储目录 Path
        force: 若为 True，强制全量重建（忽略 meta）
    """
    import json as _json

    meta_path = store_path / ".index-meta.json"
    type_order = ["user", "feedback", "task", "knowledge", "project", "reference"]

    # ---- 加载旧 meta（损坏时回退全量）----
    old_meta: dict[str, float] = {}
    if not force and meta_path.exists():
        try:
            raw = meta_path.read_text(encoding="utf-8").strip()
            if not raw:
                raise ValueError("empty meta file")
            old_meta = _json.loads(raw)
            if not isinstance(old_meta, dict):
                raise ValueError("meta is not a dict")
        except (ValueError, _json.JSONDecodeError):
            # 损坏：强制全量
            old_meta = {}
            force = True

    # ---- 扫描当前 mem_*.md 文件 ----
    current_files: dict[str, float] = {}
    for f in sorted(store_path.glob("mem_*.md")):
        current_files[f.name] = f.stat().st_mtime

    # ---- 判断哪些文件需要处理 ----
    to_process: list[str] = []
    skipped: list[str] = []
    removed_count = 0

    for filename in current_files:
        if force or filename not in old_meta or current_files[filename] != old_meta[filename]:
            to_process.append(filename)
        else:
            skipped.append(filename)

    # ---- 检测删除的文件 ----
    deleted_files = set(old_meta.keys()) - set(current_files.keys())
    removed_count = len(deleted_files)

    # ---- 若无变化且索引已存在，直接返回 ----
    if not to_process and not deleted_files and (store_path / "MEMORY.md").exists():
        return {"processed": 0, "skipped": len(skipped), "removed": 0}

    # ---- 加载所有记忆（增量：只重新解析需要处理的文件）----
    # 策略：始终读取全部记忆以生成完整索引，
    # 但统计数字反映增量处理情况
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from memory_store import MemoryStore, Memory

    store = MemoryStore(store_path=str(store_path))
    memories = store.load_all()

    # ---- 生成 MEMORY.md ----
    grouped: dict[str, list[Memory]] = {t: [] for t in type_order}
    for mem in memories:
        mt = (mem.type or "task").strip().lower() or "task"
        if mt not in grouped:
            grouped[mt] = []
        grouped[mt].append(mem)

    lines: list[str] = ["# Memory Index", ""]
    for mt in type_order:
        items = grouped.get(mt, [])
        if not items:
            continue
        lines.append(f"## {mt.capitalize()}")
        for mem in sorted(items, key=lambda m: m.id):
            title = (mem.name or "").strip() or mem.id
            desc = (mem.description or "").strip() or (mem.context or "").strip() or mem.content.strip()
            desc = desc.replace("\n", " ")
            lines.append(f"- [{title}]({mem.id}.md) — {desc}")
        lines.append("")

    output = store_path / "MEMORY.md"
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    # ---- 更新 meta：只保留当前存在的文件 ----
    new_meta = {filename: mtime for filename, mtime in current_files.items()}
    meta_path.write_text(_json.dumps(new_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "processed": len(to_process),
        "skipped": len(skipped),
        "removed": removed_count,
    }


def cmd_generate_index(args):
    """Generate MEMORY.md index in store directory (incremental by default)."""
    store = get_store(args)
    force = getattr(args, 'force', False)
    result = _generate_index_incremental(store.store_path, force=force)
    output = store.store_path / "MEMORY.md"
    print(f"索引已生成: {output}")
    print(f"  处理: {result['processed']} 个文件, 跳过: {result['skipped']} 个, 移除: {result['removed']} 个")


def cmd_feedback(args):
    """为指定记忆记录使用反馈（有用 / 无用 / 自动推断）。"""
    store = get_store(args)

    # --auto 与 --useful/--not-useful 互斥
    if getattr(args, 'auto', False) and (getattr(args, 'useful', False) or getattr(args, 'not_useful', False)):
        print("错误：--auto 与 --useful/--not-useful 互斥，请勿同时使用。")
        sys.exit(1)

    # --auto 模式：调用 infer_memory_feedback 自动推断
    if getattr(args, 'auto', False):
        if not getattr(args, 'event', None):
            print("错误：--auto 模式必须指定 --event 参数。")
            sys.exit(1)
        from feedback_loop import infer_memory_feedback
        result = infer_memory_feedback(args.memory_id, args.event, store)
        print(f"记忆 {result['memory_id']} 自动推断反馈已记录（event={result['event']}）。")
        print(f"  delta_positive: +{result['delta_positive']} | delta_negative: +{result['delta_negative']}")
        print(f"  positive: {result['new_positive']} | negative: {result['new_negative']}")
        return

    memory = store.get(args.memory_id)

    if not memory:
        print(f"记忆 {args.memory_id} 不存在。")
        sys.exit(1)

    if getattr(args, 'useful', False):
        new_usefulness = min(1.0, getattr(memory, 'usefulness_score', 0.5) + 0.1)
        updated_memory = dataclasses.replace(
            memory,
            positive_feedback=memory.positive_feedback + 1,
            usefulness_score=new_usefulness,
        )
        action = "positive"
    elif getattr(args, 'not_useful', False):
        new_usefulness = max(0.0, getattr(memory, 'usefulness_score', 0.5) - 0.1)
        updated_memory = dataclasses.replace(
            memory,
            negative_feedback=memory.negative_feedback + 1,
            usefulness_score=new_usefulness,
        )
        action = "negative"
    else:
        print("错误：必须指定 --useful、--not-useful 或 --auto --event <event>。")
        sys.exit(1)

    store.update(updated_memory)
    print(f"记忆 {updated_memory.id} 反馈已记录（{action}）。")
    print(f"  positive: {updated_memory.positive_feedback} | negative: {updated_memory.negative_feedback}")
    print(f"  usefulness_score: {updated_memory.usefulness_score:.2f}")


def cmd_trigger(args):
    """触发效率追踪：记录触发结果、查询统计、调整权重。"""
    from trigger_tracker import record_trigger, get_efficiency, adjust_weight, get_all_stats

    if args.trigger_cmd == "record":
        result = record_trigger(args.rule, args.result)
        print(f"已记录触发: 规则={args.rule!r} 结果={args.result}")
        print(f"  success={result['success']} failure={result['failure']} skip={result['skip']}")
        print(f"  last_triggered={result['last_triggered']}")

    elif args.trigger_cmd == "stats":
        if args.rule:
            eff = get_efficiency(args.rule)
            data = get_all_stats()
            rule_data = data.get("rules", {}).get(args.rule, {})
            print(f"=== 触发统计: {args.rule} ===")
            if rule_data:
                print(f"  success:  {rule_data.get('success', 0)}")
                print(f"  failure:  {rule_data.get('failure', 0)}")
                print(f"  skip:     {rule_data.get('skip', 0)}")
                print(f"  weight:   {rule_data.get('weight', 1.0)}")
                print(f"  效率:     {eff:.2%}")
                print(f"  last:     {rule_data.get('last_triggered', 'N/A')}")
            else:
                print("  （无记录）")
        else:
            data = get_all_stats()
            rules = data.get("rules", {})
            if not rules:
                print("暂无触发统计数据。")
                return
            print(f"=== 全部触发统计（{len(rules)} 条规则）===")
            for name, rule_data in sorted(rules.items()):
                s = rule_data.get("success", 0)
                f = rule_data.get("failure", 0)
                sk = rule_data.get("skip", 0)
                total = s + f
                eff = (s / total) if total > 0 else 0.5
                print(f"  {name}: success={s} failure={f} skip={sk} 效率={eff:.2%} weight={rule_data.get('weight', 1.0)}")

    elif args.trigger_cmd == "adjust":
        current_weight = getattr(args, "current_weight", 1.0) or 1.0
        new_weight, suggestion = adjust_weight(args.rule, current_weight=current_weight)
        eff = get_efficiency(args.rule)
        print(f"权重调整: 规则={args.rule!r}")
        print(f"  效率:       {eff:.2%}")
        print(f"  原权重:     {current_weight}")
        print(f"  新权重:     {new_weight}")
        if suggestion:
            print(f"  建议:       {suggestion}")

    elif args.trigger_cmd is None:
        if hasattr(args, '_trigger_parser'):
            args._trigger_parser.print_help()
        else:
            print("用法: cli.py trigger {record,stats,adjust}")
            print("子命令: record  记录一次触发结果")
            print("        stats   查询触发统计")
            print("        adjust  根据效率调整触发权重")
        return

    else:
        print(f"未知 trigger 子命令: {args.trigger_cmd!r}")
        sys.exit(1)


def cmd_health_check(args):
    """批量检查记忆库中所有记忆的健康状态。"""
    store = get_store(args)
    memories = store.load_all()

    from feedback_loop import check_memory_health
    stats = {"healthy": 0, "warning": 0, "blocked": 0}

    for mem in memories:
        try:
            health = check_memory_health(mem)
            stats[health] += 1
            if health != "healthy" or getattr(args, 'show_all', False):
                print(f"[{health.upper()}] {mem.id}: {mem.name or mem.content[:40]} "
                      f"(pos={mem.positive_feedback}, neg={mem.negative_feedback})")
        except Exception as e:
            print(f"[ERROR] {mem.id}: {e}")
            stats.setdefault("error", 0)
            stats["error"] += 1

    error_count = stats.get("error", 0)
    error_str = f", {error_count} error" if error_count else ""
    print(f"\n总计: {stats['healthy']} healthy, {stats['warning']} warning, {stats['blocked']} blocked{error_str}")


def cmd_stale(args):
    """列出长期未被检索的低价值记忆（过期候选）。"""
    store = get_store(args)

    from feedback_loop import identify_stale_memories

    stale = identify_stale_memories(
        store,
        min_days=args.min_days,
        min_retrievals=args.min_retrievals,
    )

    if not stale:
        print(f"未发现过期记忆（min_days={args.min_days}, min_retrievals={args.min_retrievals}）。")
        return

    print(f"发现 {len(stale)} 条过期记忆（>={args.min_days} 天未检索, importance < 5, retrievals <= {args.min_retrievals}）：\n")
    for mem in stale:
        retrieval_count = getattr(mem, 'retrieval_count', 0)
        preview = mem.content[:60] + ("..." if len(mem.content) > 60 else "")
        print(f"  {mem.id} | imp:{mem.importance}/10 | retrievals:{retrieval_count} | {preview}")


def cmd_export(args):
    """Export memories to Obsidian notes + graph."""
    from obsidian_export import export_all
    agent_name = getattr(args, 'agent', None)
    result = export_all(args.store, args.output, agent_name=agent_name)
    if result["status"] == "empty":
        print("No memories to export.")
    else:
        print(f"Exported {result['count']} memories to Obsidian")
        print(f"  MOC: {result['moc']}")
        print(f"  Graph: {result['graph']}")
        for p in result["notes"]:
            print(f"  Note: {p}")


def cmd_dashboard(args):
    """一站式系统健康概览。"""
    store = get_store(args)
    memories = store.load_all()

    from feedback_loop import check_memory_health
    from trigger_tracker import get_all_stats

    # === 区域 1：记忆健康分布 ===
    health_stats = {"healthy": 0, "warning": 0, "blocked": 0}
    blocked_list = []
    for mem in memories:
        try:
            h = check_memory_health(mem)
            health_stats[h] += 1
            if h == "blocked":
                blocked_list.append(f"  - {mem.id}: {mem.name or mem.content[:40]}")
        except Exception:
            pass

    print("=" * 50)
    print("📊 Agent Memory System Dashboard")
    print("=" * 50)
    print(f"\n## 记忆健康 ({len(memories)} 条)")
    print(f"  Healthy: {health_stats['healthy']}")
    print(f"  Warning: {health_stats['warning']}")
    print(f"  Blocked: {health_stats['blocked']}")
    if blocked_list:
        print("\n  Blocked 记忆:")
        for b in blocked_list[:5]:
            print(b)

    # === 区域 2：触发规则效率 ===
    trigger_stats_path = Path(os.path.expanduser("~/.claude/memory/workflows/trigger-stats.json"))
    if getattr(args, 'trigger_stats', None):
        trigger_stats_path = Path(args.trigger_stats)
    stats = get_all_stats(trigger_stats_path)
    rules = stats.get("rules", {})
    if rules:
        print(f"\n## 触发效率 ({len(rules)} 条规则)")
        for name, data in sorted(rules.items(), key=lambda x: x[1].get("weight", 1.0), reverse=True):
            total = data.get("success", 0) + data.get("failure", 0)
            eff = data["success"] / total * 100 if total > 0 else 0
            print(f"  {name}: 效率 {eff:.0f}% | 权重 {data.get('weight', 1.0):.1f} | 触发 {total} 次")
    else:
        print("\n## 触发效率: 暂无数据")

    # === 区域 3：反馈统计 ===
    total_pos = sum(m.positive_feedback for m in memories)
    total_neg = sum(m.negative_feedback for m in memories)
    print(f"\n## 反馈统计")
    print(f"  总正面: {total_pos}")
    print(f"  总负面: {total_neg}")
    if total_pos + total_neg > 0:
        print(f"  整体比率: {total_pos / (total_pos + total_neg):.1%}")

    # === 区域 4：系统概要 ===
    print(f"\n## 系统概要")
    print(f"  总记忆: {len(memories)}")
    if memories:
        avg_imp = sum(m.importance for m in memories) / len(memories)
        print(f"  平均 importance: {avg_imp:.1f}")
    else:
        print("  无记忆")
    print("=" * 50)


def _try_fix_frontmatter(text: str):
    """尝试修复常见的 frontmatter 损坏问题。

    支持的修复：
    1. 缺少结束 '---' 分隔符（frontmatter 未闭合）

    返回修复后的文本，若无法修复则返回 None。
    """
    import yaml as _yaml

    # 修复 1：有开头 ---\n 但没有结束 ---
    if text.startswith("---\n") and "\n---\n" not in text:
        lines = text.split("\n")
        for i, line in enumerate(lines[1:], 1):  # 跳过第一行 ---
            # 空行可能是 frontmatter 和 body 的分隔
            if line.strip() == "" and i > 1:
                fm_candidate = "\n".join(lines[1:i])
                try:
                    parsed = _yaml.safe_load(fm_candidate)
                    if isinstance(parsed, dict):
                        body = "\n".join(lines[i + 1:])
                        return f"---\n{fm_candidate}\n---\n\n{body}"
                except Exception:
                    pass
        return None

    return None


def cmd_repair(args):
    """扫描 store 中所有 .md 记忆文件，检查 YAML 可解析性，报告损坏文件。

    选项：
      --fix     尝试自动修复常见问题（如缺少结束 --- 分隔符）
      --delete  删除无法修复的损坏文件（需用户确认）
    """
    store = get_store(args)
    store_path = store.store_path

    if not store_path.exists():
        print(f"Store 目录不存在：{store_path}")
        return

    all_md = [p for p in sorted(store_path.glob("*.md")) if p.name != "MEMORY.md"]

    if not all_md:
        print(f"Store 为空（0 个记忆文件）：{store_path}")
        return

    fixable = []   # list of (path, fixed_content, error_msg)
    corrupted = [] # list of (path, error_msg) — 无法自动修复
    valid_count = 0

    for path in all_md:
        text = path.read_text(encoding="utf-8")
        try:
            store._frontmatter_to_memory(text)
            valid_count += 1
        except Exception as e:
            error_msg = str(e)
            fixed = _try_fix_frontmatter(text)
            if fixed is not None:
                # 验证修复后能解析
                try:
                    store._frontmatter_to_memory(fixed)
                    fixable.append((path, fixed, error_msg))
                except Exception:
                    corrupted.append((path, error_msg))
            else:
                corrupted.append((path, error_msg))

    total = len(all_md)
    corrupted_count = len(corrupted) + len(fixable)

    if corrupted_count == 0:
        print(f"检查完成：{total} 个文件，0 个损坏。Store 状态良好。")
        return

    # 报告损坏文件
    print(f"检查完成：{total} 个文件，{valid_count} 个有效，{corrupted_count} 个损坏。\n")

    if fixable:
        print(f"可自动修复（{len(fixable)} 个）：")
        for path, _, err in fixable:
            print(f"  [可修复] {path.name}")
            print(f"           原因：{err}")
        print()

    if corrupted:
        print(f"无法自动修复（{len(corrupted)} 个）：")
        for path, err in corrupted:
            print(f"  [损坏]   {path.name}")
            print(f"           原因：{err}")
        print()

    # --fix：自动修复可修复文件
    if getattr(args, 'fix', False):
        if fixable:
            fixed_count = 0
            for path, fixed_content, _ in fixable:
                try:
                    path.write_text(fixed_content, encoding="utf-8")
                    print(f"已修复：{path.name}")
                    fixed_count += 1
                except Exception as fix_err:
                    print(f"修复失败：{path.name} — {fix_err}")
            print(f"\n修复完成：{fixed_count}/{len(fixable)} 个文件已修复。")
        else:
            print("无可自动修复的文件。")

        if corrupted:
            print(f"\n{len(corrupted)} 个文件无法自动修复，请手动处理或使用 --delete 删除。")
        return

    # --delete：删除无法修复的文件
    if getattr(args, 'delete', False):
        if not corrupted:
            print("无需删除：无法修复的损坏文件为 0 个。")
            return
        print(f"将删除 {len(corrupted)} 个无法修复的损坏文件：")
        for path, _ in corrupted:
            print(f"  {path.name}")
        if getattr(args, 'yes', False):
            confirm = "y"
        elif sys.stdin.isatty():
            confirm = input("\n确认删除？[y/N] ").strip().lower()
        else:
            print("非 TTY 环境，跳过删除（请使用 --yes 强制确认）。")
            return
        if confirm == "y":
            deleted = 0
            for path, _ in corrupted:
                path.unlink()
                deleted += 1
                print(f"已删除：{path.name}")
            print(f"\n已删除 {deleted} 个损坏文件。")
        else:
            print("取消删除。")
        return

    # 纯报告模式（无选项）
    if fixable:
        print(f"提示：使用 --fix 可自动修复 {len(fixable)} 个文件。")
    if corrupted:
        print(f"提示：使用 --delete 可删除 {len(corrupted)} 个无法修复的文件。")


def cmd_distill(args):
    """从记忆中提炼知识"""
    from distiller import distill
    import glob as glob_mod

    if args.all_agents:
        # 自动发现所有 agent store
        base = os.path.expanduser("~/.claude/memory/agents")
        stores = []
        if os.path.isdir(base):
            for type_dir in os.listdir(base):
                type_path = os.path.join(base, type_dir)
                if os.path.isdir(type_path):
                    for agent_dir in os.listdir(type_path):
                        agent_path = os.path.join(type_path, agent_dir)
                        if os.path.isdir(agent_path):
                            stores.append(agent_path)
        if not stores:
            print("未找到任何 agent store")
            return
    elif args.stores:
        stores = [s.strip() for s in args.stores.split(",")]
    else:
        print("请指定 --stores 或 --all-agents")
        return

    result = distill(
        stores=stores,
        min_cluster_size=args.min_cluster,
        dry_run=args.dry_run,
        zettelkasten_dir=args.zettelkasten_dir or "",
        candidate_dir=args.candidate_dir or ""
    )

    print(f"\n=== Distill 结果 ===")
    print(f"发现 {result.clusters_found} 个 cluster")
    print(f"跳过 {result.skipped_small_clusters} 个小 cluster (< {args.min_cluster})")
    print(f"提炼 {result.knowledge_extracted} 条知识")

    if result.actions:
        print(f"\n--- 输出详情 ---")
        for action in result.actions:
            k = action.knowledge
            prefix = "[DRY-RUN] " if action.dry_run else ""
            print(f"{prefix}{k.title}")
            print(f"  类型: {k.knowledge_type} | 置信度: {k.confidence:.1%} | 证据: {k.evidence_count}")
            print(f"  目标: {action.destination} → {action.target_path or '(default)'}")
            print()


def cmd_consolidate(args):
    """扫描记忆库，合并相似记忆对。"""
    from consolidator import consolidate

    store = get_store(args)
    mode = "（dry-run 预览模式）" if args.dry_run else ""
    print(f"=== 记忆合并{mode} ===")
    print(f"阈值: {args.threshold} | 存储路径: {store.store_path}")
    print()

    result = consolidate(store, threshold=args.threshold, dry_run=args.dry_run)

    pairs = result["pairs"]
    if not pairs:
        print("未发现相似记忆对，无需合并。")
        return

    print(f"发现 {len(pairs)} 对相似记忆：")
    for id_a, id_b, score in pairs:
        print(f"  [{score:.3f}] {id_a}  ↔  {id_b}")
    print()

    if args.dry_run:
        print(f"预览完成（未修改）：发现 {len(pairs)} 对可合并记忆。")
        print("移除 --dry-run 参数以执行实际合并。")
    else:
        print(f"合并完成：merged={result['merged']}，deleted={result['deleted']}")


# ==================== 主入口 ====================

def main():
    parser = argparse.ArgumentParser(
        description="Agent Memory CLI — 联想记忆系统命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--store",
        default=DEFAULT_STORE,
        help=f"记忆库目录路径（默认: {DEFAULT_STORE}）",
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        help="角色名（如 kaze），使用该角色的个人记忆存储",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ---- retrieve ----
    p_retrieve = subparsers.add_parser("retrieve", help="检索记忆")
    p_retrieve.add_argument("query", help="搜索查询文本")
    p_retrieve.add_argument("--top-k", type=int, default=3, help="返回结果数（默认: 3）")
    p_retrieve.add_argument("--no-spread", action="store_true", help="禁用扩散激活")
    p_retrieve.add_argument(
        "--format",
        choices=["text", "prompt"],
        default="text",
        help="输出格式：text（默认）或 prompt（适合注入 subagent）",
    )
    p_retrieve.add_argument(
        "--cross-agent",
        action="store_true",
        dest="cross_agent",
        help="跨 Agent 模式：自动扫描 ~/.claude/memory/agents/*/ 下所有 store 进行联合检索",
    )
    p_retrieve.add_argument(
        "--stores",
        type=str,
        default=None,
        help="指定多个 store 路径（逗号分隔），进行跨 store 联合检索",
    )

    # ---- add ----
    p_add = subparsers.add_parser("add", help="添加新记忆")
    p_add.add_argument("--subject", required=True, help="记忆主题（必填）")
    p_add.add_argument("--description", default="", help="详细描述")
    p_add.add_argument("--keywords", help="关键词，逗号分隔（默认使用 subject）")
    p_add.add_argument("--tags", help="标签，逗号分隔（默认: manual）")
    p_add.add_argument("--importance", type=int, default=5, help="重要性 1-10（默认: 5）")

    # ---- stats ----
    subparsers.add_parser("stats", help="显示统计信息")

    # ---- evolve ----
    p_evolve = subparsers.add_parser("evolve", help="更新记忆字段")
    p_evolve.add_argument("memory_id", help="要更新的记忆 ID")
    p_evolve.add_argument("--context", help="新的语境描述")
    p_evolve.add_argument("--tags", help="新标签，逗号分隔")

    # ---- list ----
    p_list = subparsers.add_parser("list", help="列出最近记忆")
    p_list.add_argument("--limit", type=int, default=20, help="最多显示条数（默认: 20）")

    # ---- export ----
    p_export = subparsers.add_parser("export", help="导出记忆到 Obsidian 笔记和图谱")
    p_export.add_argument(
        "--output",
        default=DEFAULT_EXPORT_DIR,
        help=f"输出目录（默认: {DEFAULT_EXPORT_DIR}）",
    )

    # ---- quick-add ----
    parser_quick_add = subparsers.add_parser("quick-add", help="直接保存记忆（无需 API）")
    parser_quick_add.add_argument("content", help="记忆内容")
    parser_quick_add.add_argument("--keywords", required=True, help="关键词（逗号分隔）")
    parser_quick_add.add_argument("--tags", default="task", help="标签（逗号分隔，默认 task）")
    parser_quick_add.add_argument("--importance", type=int, default=5, help="重要度 1-10（默认 5）")
    parser_quick_add.add_argument("--context", default="", help="上下文说明")
    parser_quick_add.add_argument("--name", default="", help="人类可读短名")
    parser_quick_add.add_argument("--description", default="", help="一句话摘要")
    parser_quick_add.add_argument(
        "--type",
        dest="type",
        choices=["user", "feedback", "task", "knowledge", "project", "reference"],
        default="task",
        help="记忆类型（默认 task）",
    )
    parser_quick_add.add_argument(
        "--layer",
        dest="layer",
        choices=["L0", "L1", "L2", "L3"],
        default="L1",
        help="记忆层级（默认 L1）：L0=working, L1=episodic, L2=semantic, L3=core",
    )

    # ---- generate-index ----
    p_generate_index = subparsers.add_parser("generate-index", help="按类型生成 MEMORY.md 索引（增量）")
    p_generate_index.add_argument(
        "--force",
        action="store_true",
        help="强制全量重建（忽略 .index-meta.json 缓存）",
    )

    # ---- consolidate ----
    p_consolidate = subparsers.add_parser("consolidate", help="扫描记忆库，合并相似记忆对")
    p_consolidate.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="相似度阈值（默认: 0.85）",
    )
    p_consolidate.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="预览模式：只显示相似对，不执行合并",
    )

    # ---- feedback ----
    p_feedback = subparsers.add_parser("feedback", help="为指定记忆记录使用反馈")
    p_feedback.add_argument("--memory-id", required=True, dest="memory_id", help="要反馈的记忆 ID")
    p_feedback.add_argument("--auto", action="store_true", help="自动推断模式（调用 infer_memory_feedback）")
    p_feedback.add_argument("--event", help="事件类型（--auto 模式必填）：task_success|task_retry|audit_pass|audit_fail|user_positive|user_negative")
    feedback_group = p_feedback.add_mutually_exclusive_group(required=False)
    feedback_group.add_argument("--useful", action="store_true", help="标记为有用（positive_feedback +1）")
    feedback_group.add_argument("--not-useful", action="store_true", dest="not_useful",
                                help="标记为无用（negative_feedback +1）")

    # ---- stale ----
    p_stale = subparsers.add_parser("stale", help="列出长期未被检索的低价值记忆（过期候选）")
    p_stale.add_argument("--min-days", type=int, default=30, dest="min_days",
                          help="最少创建天数（默认: 30）")
    p_stale.add_argument("--min-retrievals", type=int, default=0, dest="min_retrievals",
                          help="最大允许检索次数（默认: 0，即从未被检索）")

    # ---- health-check ----
    p_health = subparsers.add_parser("health-check", help="批量检查记忆健康状态（healthy/warning/blocked）")
    p_health.add_argument("--show-all", action="store_true", dest="show_all",
                          help="显示所有记忆（不仅问题记忆）")

    # ---- dashboard ----
    p_dashboard = subparsers.add_parser("dashboard", help="一站式系统健康概览")
    p_dashboard.add_argument("--trigger-stats", dest="trigger_stats", default=None,
                             help="trigger-stats.json 路径（可选，默认 ~/.claude/memory/workflows/trigger-stats.json）")

    # ---- repair ----
    p_repair = subparsers.add_parser("repair", help="扫描并报告损坏的记忆文件（YAML 解析失败）")
    p_repair.add_argument(
        "--fix",
        action="store_true",
        help="尝试自动修复常见问题（如缺少结束 --- 分隔符）",
    )
    p_repair.add_argument(
        "--delete",
        action="store_true",
        help="删除无法修复的损坏文件（需用户确认）",
    )
    p_repair.add_argument(
        "--yes",
        action="store_true",
        help="跳过删除确认（适用于非 TTY 环境或自动化脚本）",
    )

    # ---- trigger ----
    p_trigger = subparsers.add_parser("trigger", help="触发效率追踪：record/stats/adjust")
    trigger_sub = p_trigger.add_subparsers(dest="trigger_cmd", metavar="TRIGGER_CMD")

    # trigger record
    p_tr = trigger_sub.add_parser("record", help="记录一次触发结果")
    p_tr.add_argument("--rule", required=True, help="规则名称")
    p_tr.add_argument("--result", required=True, choices=["success", "failure", "skip"],
                      help="触发结果：success | failure | skip")

    # trigger stats
    p_ts = trigger_sub.add_parser("stats", help="查询触发统计")
    p_ts.add_argument("--rule", default=None, help="指定规则（不填则显示全部）")

    # trigger adjust
    p_ta = trigger_sub.add_parser("adjust", help="根据效率调整触发权重")
    p_ta.add_argument("--rule", required=True, help="规则名称")
    p_ta.add_argument("--current-weight", type=float, default=1.0, dest="current_weight",
                      help="当前权重（默认 1.0）")

    # ---- distill ----
    p_distill = subparsers.add_parser("distill", help="从记忆中提炼可复用知识")
    p_distill.add_argument("--all-agents", action="store_true", dest="all_agents", help="扫描所有 agent store")
    p_distill.add_argument("--stores", help="逗号分隔的 store 路径列表")
    p_distill.add_argument("--min-cluster", type=int, default=3, dest="min_cluster", help="最小 cluster 大小 (默认: 3)")
    p_distill.add_argument("--dry-run", action="store_true", dest="dry_run", help="预览模式，不实际写入")
    p_distill.add_argument("--zettelkasten-dir", default="", dest="zettelkasten_dir", help="Zettelkasten 输出目录")
    p_distill.add_argument("--candidate-dir", default="", dest="candidate_dir", help="候选规则输出目录")
    p_distill.set_defaults(func=cmd_distill)

    args = parser.parse_args()

    # 将 p_trigger 注入 args，以便 cmd_trigger 调用 print_help()
    args._trigger_parser = p_trigger

    if not args.command:
        parser.print_help()
        return

    commands = {
        "retrieve": cmd_retrieve,
        "add": cmd_add,
        "quick-add": cmd_quick_add,
        "generate-index": cmd_generate_index,
        "stats": cmd_stats,
        "evolve": cmd_evolve,
        "list": cmd_list,
        "export": cmd_export,
        "feedback": cmd_feedback,
        "stale": cmd_stale,
        "consolidate": cmd_consolidate,
        "health-check": cmd_health_check,
        "trigger": cmd_trigger,
        "dashboard": cmd_dashboard,
        "repair": cmd_repair,
        "distill": cmd_distill,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
