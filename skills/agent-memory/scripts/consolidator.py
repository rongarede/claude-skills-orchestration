"""Phase 2.1 Memory Consolidation — 记忆去重合并模块。

设计：
- 相似度计算：基于 tokenize() 的 Jaccard 相似度（关键词 + content + context 合并字段）
- 合并策略：keywords/tags/related_ids 并集；importance 取最大；content 取最长；
            access_count/feedback 累加；保留 primary 的 id/name
- consolidate：调用 find_similar_pairs + merge_memories，可选 dry_run
"""

import sys
import os
from dataclasses import replace

sys.path.insert(0, os.path.dirname(__file__))

from memory_store import Memory, MemoryStore
from feedback_loop import check_memory_health


# ==================== 相似度计算 ====================

def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """计算两个集合的 Jaccard 相似度。"""
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return intersection / union


def _keyword_tag_set(memory: Memory) -> set:
    """提取记忆的关键词 + 标签集合（小写化）用于相似度比较。

    使用 keywords + tags 而非全文 token，原因：
    - keywords/tags 是人工整理的语义标签，信噪比高
    - 避免全文 bigram 展开导致的语义稀释
    - 相同主题的记忆通常共享大量 keywords/tags
    """
    kw = {k.lower() for k in (memory.keywords or [])}
    tags = {t.lower() for t in (memory.tags or [])}
    return kw | tags


def _compute_similarity(mem_a: Memory, mem_b: Memory) -> float:
    """计算两条记忆的相似度（Jaccard over keywords + tags）。

    返回值在 [0.0, 1.0] 区间。
    """
    set_a = _keyword_tag_set(mem_a)
    set_b = _keyword_tag_set(mem_b)
    return _jaccard_similarity(set_a, set_b)


# ==================== 核心函数 ====================

def find_similar_pairs(
    memories: list,
    threshold: float = 0.85,
) -> list:
    """两两计算相似度，返回相似度 >= threshold 的配对。

    Args:
        memories: Memory 对象列表
        threshold: 相似度阈值（默认 0.85）

    Returns:
        list of (Memory, Memory, float) 三元组，相似度由高到低排序
    """
    if len(memories) < 2:
        return []

    pairs = []
    n = len(memories)
    for i in range(n):
        for j in range(i + 1, n):
            score = _compute_similarity(memories[i], memories[j])
            if score >= threshold:
                pairs.append((memories[i], memories[j], float(score)))

    # 相似度由高到低排序
    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs


def merge_memories(primary: Memory, duplicate: Memory) -> Memory:
    """将 duplicate 合并入 primary，返回新的 Memory 对象。

    合并策略：
    - keywords/tags/related_ids：并集（去重）
    - importance：取较高值
    - content：保留较长者
    - access_count：累加
    - positive_feedback / negative_feedback：累加
    - id/name：保留 primary 的值

    Args:
        primary: 主记录（保留 id/name）
        duplicate: 被合并的副本

    Returns:
        新的 Memory 对象（不可变，原对象不变）
    """
    # keywords/tags/related_ids — 并集
    merged_keywords = list(dict.fromkeys(
        list(primary.keywords or []) + list(duplicate.keywords or [])
    ))
    merged_tags = list(dict.fromkeys(
        list(primary.tags or []) + list(duplicate.tags or [])
    ))
    # related_ids：并集并排除合并后自身 id（避免自环）
    merged_related = list(dict.fromkeys(
        list(primary.related_ids or []) + list(duplicate.related_ids or [])
    ))
    # 去除自身 id 的自环引用
    merged_related = [rid for rid in merged_related if rid != primary.id and rid != duplicate.id]

    # importance — 取较大值
    merged_importance = max(primary.importance, duplicate.importance)

    # content — 保留较长者
    merged_content = (
        primary.content
        if len(primary.content) >= len(duplicate.content)
        else duplicate.content
    )

    # access_count, positive_feedback, negative_feedback — 累加
    merged_access_count = primary.access_count + duplicate.access_count
    merged_positive = primary.positive_feedback + duplicate.positive_feedback
    merged_negative = primary.negative_feedback + duplicate.negative_feedback

    # 构建新 Memory（保留 primary 的其余字段，覆盖合并后字段）
    return replace(
        primary,
        keywords=merged_keywords,
        tags=merged_tags,
        related_ids=merged_related,
        importance=merged_importance,
        content=merged_content,
        access_count=merged_access_count,
        positive_feedback=merged_positive,
        negative_feedback=merged_negative,
    )


# ==================== 顶层入口 ====================

def consolidate(
    store: MemoryStore,
    threshold: float = 0.85,
    dry_run: bool = False,
) -> dict:
    """扫描 store，合并相似记忆对，返回操作摘要。

    流程：
    1. 加载所有记忆
    2. find_similar_pairs 找出相似对
    3. 贪心合并：对每对，将 importance 较低方并入较高方（或相等时保留第一个）
    4. 除非 dry_run，否则写入合并结果并删除副本

    Args:
        store: MemoryStore 实例
        threshold: 相似度阈值
        dry_run: 若为 True 则只预览，不修改 store

    Returns:
        dict with keys:
            "merged": 发生合并的次数（int）
            "deleted": 删除的记忆数（int）
            "pairs": 检出相似对的信息列表
    """
    memories = store.load_all()

    # ==================== 健康过滤 ====================
    # blocked 记忆完全排除合并流程
    active_memories = [m for m in memories if check_memory_health(m) != "blocked"]

    pairs = find_similar_pairs(active_memories, threshold=threshold)

    # ==================== 健康感知过滤相似对 ====================
    # 两条都是 warning → 不合并
    _HEALTH_ORDER = {"healthy": 0, "warning": 1}

    def _health_rank(mem: Memory) -> int:
        """数值越小表示健康状态越好（healthy=0 优于 warning=1）。"""
        return _HEALTH_ORDER.get(check_memory_health(mem), 0)

    filtered_pairs = []
    for mem_a, mem_b, score in pairs:
        rank_a = _health_rank(mem_a)
        rank_b = _health_rank(mem_b)
        # 两条都是 warning → 跳过
        if rank_a == 1 and rank_b == 1:
            continue
        filtered_pairs.append((mem_a, mem_b, score))

    # 构建返回的 pairs 信息（每项包含两个记忆的 id + 相似度分数）
    pairs_info = [(m1.id, m2.id, score) for m1, m2, score in filtered_pairs]

    if dry_run or not filtered_pairs:
        return {
            "merged": 0,
            "deleted": 0,
            "pairs": pairs_info,
        }

    # 贪心合并：用已处理 id 集合跟踪，避免重复合并
    merged_count = 0
    deleted_count = 0
    deleted_ids: set = set()

    for mem_a, mem_b, _score in filtered_pairs:
        # 跳过已被删除的记忆
        if mem_a.id in deleted_ids or mem_b.id in deleted_ids:
            continue

        # 决定 primary 和 duplicate：
        # 优先级：健康状态（healthy 优先 warning）> importance（大者优先）
        rank_a = _health_rank(mem_a)
        rank_b = _health_rank(mem_b)
        if rank_a < rank_b:
            # mem_a 更健康 → mem_a 做 primary
            primary, duplicate = mem_a, mem_b
        elif rank_b < rank_a:
            # mem_b 更健康 → mem_b 做 primary
            primary, duplicate = mem_b, mem_a
        elif mem_a.importance >= mem_b.importance:
            # 健康状态相同，importance 较高方做 primary
            primary, duplicate = mem_a, mem_b
        else:
            primary, duplicate = mem_b, mem_a

        # 合并
        merged = merge_memories(primary, duplicate)

        # 写入合并后记忆（覆盖 primary 文件）
        store.update(merged)

        # 删除副本
        store.delete(duplicate.id)
        deleted_ids.add(duplicate.id)

        merged_count += 1
        deleted_count += 1

    return {
        "merged": merged_count,
        "deleted": deleted_count,
        "pairs": pairs_info,
    }
