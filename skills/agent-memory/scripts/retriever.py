"""Retriever: BM25-based three-dimensional scoring retrieval engine.

Scoring model (adapted from Stanford Generative Agents):
  score = recency + importance + relevance

Each dimension is normalized to [0, 1] before summing:
- Recency: exponential decay 0.995^hours_since_last_access
- Importance: memory.importance / 10
- Relevance: BM25 score (min-max normalized within candidate set)
"""

import math
import re
import sys
import os
from datetime import datetime
from typing import Optional

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    raise ImportError("Please install rank-bm25: pip install rank-bm25")

from memory_store import Memory, MemoryStore

# 低相关度警告阈值：当所有结果的最高分低于此值时，在 prompt 格式输出中插入警告
LOW_RELEVANCE_THRESHOLD = 2.4

# Phase 8: 层级加成——高层级记忆在检索评分中获得额外加分
LAYER_BONUS = {"L0": 0.0, "L1": 0.0, "L2": 0.3, "L3": 0.5}


# ==================== 分词器 ====================

def tokenize(text: str) -> list[str]:
    """Simple tokenizer that handles both Chinese and English.
    For Chinese: character-level + bigrams + trigrams.
    For English: whitespace + lowercase.
    """
    # Split on whitespace and punctuation, keep Chinese characters
    tokens = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z0-9_]+', text.lower())

    # Add bigrams and trigrams for Chinese characters to capture compound words
    chinese_chars = [t for t in tokens if '\u4e00' <= t <= '\u9fff']
    bigrams = [chinese_chars[i] + chinese_chars[i + 1] for i in range(len(chinese_chars) - 1)]
    trigrams = [chinese_chars[i] + chinese_chars[i + 1] + chinese_chars[i + 2] for i in range(len(chinese_chars) - 2)]

    return tokens + bigrams + trigrams


# ==================== 三维评分 ====================

def compute_recency(memory: Memory, now: Optional[datetime] = None, decay: float = 0.995) -> float:
    """Compute recency score with exponential decay.

    From Generative Agents: recency = decay_factor ^ hours_since_last_access
    decay_factor = 0.995

    If never accessed, use creation timestamp.
    """
    if now is None:
        now = datetime.now()

    last = memory.last_accessed or memory.timestamp
    try:
        last_dt = datetime.fromisoformat(last)
    except (ValueError, TypeError):
        return 1.0  # fallback: treat as just created

    hours = max(0, (now - last_dt).total_seconds() / 3600)
    return decay ** hours


def compute_importance(memory: Memory) -> float:
    """Normalize importance score to [0, 1].

    Importance is rated 1-10 at creation time (Generative Agents style).
    """
    return max(0.0, min(1.0, memory.importance / 10.0))


def compute_importance_score(memory: Memory) -> float:
    """Phase 1 改进版重要性评分，纳入 Active Recall、Retrieval Feedback 和 Usefulness。

    公式：
        base             = memory.importance / 10.0
        recall_bonus     = min(0.2, access_count * 0.02)          # Phase 1A
        feedback_adj     = (ratio - 0.5) * confidence * 0.4       # Phase 1B
            ratio        = positive_feedback / total_feedback
            confidence   = min(1.0, total_feedback / 10)
        usefulness_bonus = (usefulness_score - 0.5) * 0.4         # Phase 1C [-0.2, +0.2]
        score            = clamp(base + recall_bonus + feedback_adj + usefulness_bonus, 0.0, 1.0)
    """
    base = memory.importance / 10.0

    # Phase 1A: Active Recall bonus
    recall_bonus = min(0.2, memory.access_count * 0.02)

    # Phase 1B: Feedback adjustment
    total_fb = memory.positive_feedback + memory.negative_feedback
    if total_fb > 0:
        feedback_ratio = memory.positive_feedback / total_fb
        confidence = min(1.0, total_fb / 10)
        feedback_adj = (feedback_ratio - 0.5) * confidence * 0.4  # [-0.2, +0.2]
    else:
        feedback_adj = 0.0

    # Phase 1C: Usefulness score bonus
    usefulness = getattr(memory, 'usefulness_score', 0.5)
    usefulness_bonus = (usefulness - 0.5) * 0.4  # [-0.2, +0.2]

    return max(0.0, min(1.0, base + recall_bonus + feedback_adj + usefulness_bonus))


def compute_relevance_scores(query: str, memories: list[Memory]) -> list[float]:
    """Compute BM25 relevance scores for a query against memories.

    Builds a BM25 index over concatenated (keywords + content + context) per memory.
    Returns min-max normalized scores in [0, 1].
    """
    if not memories:
        return []

    # Build corpus: concatenate searchable fields per memory
    corpus = []
    for m in memories:
        text = ' '.join(m.keywords) + ' ' + m.content + ' ' + m.context + ' ' + ' '.join(m.tags)
        corpus.append(tokenize(text))

    query_tokens = tokenize(query)

    bm25 = BM25Okapi(corpus)
    raw_scores = bm25.get_scores(query_tokens)

    # Min-max normalization to [0, 1]
    min_s = float(min(raw_scores)) if len(raw_scores) > 0 else 0
    max_s = float(max(raw_scores)) if len(raw_scores) > 0 else 0

    if max_s - min_s < 1e-9:
        return [0.5] * len(memories)  # all equal → neutral score

    return [(float(s) - min_s) / (max_s - min_s) for s in raw_scores]


# ==================== 检索核心 ====================

def retrieve(
    query: str,
    store: MemoryStore,
    top_k: int = 3,
    spread: bool = True,
    spread_decay: float = 0.5,
    now: Optional[datetime] = None,
) -> list[tuple[Memory, float]]:
    """Retrieve top-k memories using three-dimensional scoring + spreading activation.

    Args:
        query: search query text
        store: memory store instance
        top_k: number of top memories to return
        spread: whether to activate linked memories (A-MEM style)
        spread_decay: weight multiplier for linked memories
        now: current time (for testing)

    Returns:
        List of (memory, score) tuples, sorted by score descending.
    """
    memories = store.load_all()
    if not memories:
        return []

    # Health 过滤：排除 blocked 记忆
    from feedback_loop import filter_by_health, check_memory_health
    memories = filter_by_health(memories, include_warning=True)
    if not memories:
        return []

    # Health 缓存：一次计算，多次使用
    health_cache = {mem.id: check_memory_health(mem) for mem in memories}

    # Step 1: Compute three-dimensional scores
    relevance_scores = compute_relevance_scores(query, memories)

    scored = []
    for i, mem in enumerate(memories):
        recency = compute_recency(mem, now=now)
        importance = compute_importance_score(mem)
        relevance = relevance_scores[i]

        # Phase 8: 层级加成
        layer_bonus = LAYER_BONUS.get(getattr(mem, 'layer', 'L1'), 0.0)

        total = recency + importance + relevance + layer_bonus
        scored.append((mem, total, {'recency': recency, 'importance': importance, 'relevance': relevance}))

    # Warning 记忆降权 ×0.5
    scored = [
        (mem, score * 0.5 if health_cache.get(mem.id, 'healthy') == 'warning' else score, detail)
        for mem, score, detail in scored
    ]

    # Step 2: Sort by total score
    scored.sort(key=lambda x: x[1], reverse=True)

    # Step 3: Take top-k
    top_results = scored[:top_k]

    # Step 4: Spreading activation (A-MEM style)
    if spread and top_results:
        seen_ids = {mem.id for mem, _, _ in top_results}
        spread_candidates = []

        for mem, score, _ in top_results:
            for related_id in mem.related_ids:
                if related_id not in seen_ids:
                    related_mem = store.get(related_id)
                    if related_mem:
                        # 按需计算关联记忆的 health 并加入缓存
                        if related_id not in health_cache:
                            health_cache[related_id] = check_memory_health(related_mem)
                        related_health = health_cache[related_id]
                        # 跳过 blocked 关联记忆
                        if related_health == 'blocked':
                            seen_ids.add(related_id)
                            continue
                        # Linked memories get decayed score
                        spread_score = score * spread_decay
                        # Warning 关联记忆同样降权
                        if related_health == 'warning':
                            spread_score *= 0.5
                        spread_candidates.append((related_mem, spread_score))
                        seen_ids.add(related_id)

        # Merge: top_results + spread candidates, re-sort
        all_results = [(mem, score) for mem, score, _ in top_results]
        all_results.extend(spread_candidates)
        all_results.sort(key=lambda x: x[1], reverse=True)

        # Update access metadata for retrieved memories
        now_iso = (now or datetime.now()).isoformat()
        for mem, _ in all_results:
            mem.access_count += 1
            mem.last_accessed = now_iso
            mem.retrieval_count = getattr(mem, 'retrieval_count', 0) + 1
            mem.last_retrieved = now_iso
            store.update(mem)

        return all_results

    results = [(mem, score) for mem, score, _ in top_results]

    # Update access metadata
    now_iso = (now or datetime.now()).isoformat()
    for mem, _ in results:
        mem.access_count += 1
        mem.last_accessed = now_iso
        mem.retrieval_count = getattr(mem, 'retrieval_count', 0) + 1
        mem.last_retrieved = now_iso
        store.update(mem)

    return results


# ==================== 跨 Store 联合检索 ====================

def retrieve_cross_agent(
    query: str,
    stores: list,
    top_k: int = 5,
    spread: bool = False,
    now: Optional[datetime] = None,
    annotate_source: bool = False,
) -> list:
    """跨多个 agent store 联合检索并去重排序。

    对每个 store 过采样（top_k*2），合并所有候选，按 score 降序排序，
    去重（相同 memory ID 取最高分），返回 top_k 条。

    Args:
        query: 搜索查询文本
        stores: MemoryStore 实例列表
        top_k: 返回结果数
        spread: 是否启用扩散激活（单 store 内）
        now: 当前时间（用于测试）
        annotate_source: 若为 True，返回 (Memory, score, source_name) 三元组；
                         否则返回 (Memory, score) 二元组

    Returns:
        若 annotate_source=False: list[tuple[Memory, float]]
        若 annotate_source=True:  list[tuple[Memory, float, str]]
    """
    if not stores:
        return []

    oversample_k = top_k * 2

    # 从每个 store 过采样，记录来源
    all_candidates: list[tuple[object, float, str]] = []  # (Memory, score, source_name)

    for store in stores:
        try:
            source_name = str(store.store_path) if hasattr(store, 'store_path') else ""
            results = retrieve(query, store, top_k=oversample_k, spread=spread, now=now)
            for mem, score in results:
                all_candidates.append((mem, score, source_name))
        except Exception:
            # 不存在的 store 或空 store 跳过
            continue

    if not all_candidates:
        return []

    # 去重：相同 memory ID 取最高分，保留对应的 source
    seen: dict[str, tuple[object, float, str]] = {}
    for mem, score, source in all_candidates:
        if mem.id not in seen or score > seen[mem.id][1]:
            seen[mem.id] = (mem, score, source)

    # 按 score 降序排序
    deduped = sorted(seen.values(), key=lambda x: x[1], reverse=True)

    # 取 top_k
    top = deduped[:top_k]

    if annotate_source:
        return [(mem, score, source) for mem, score, source in top]
    else:
        return [(mem, score) for mem, score, _ in top]


# ==================== 提示词格式化 ====================

def format_for_prompt(results: list[tuple[Memory, float]], max_items: int = 5) -> str:
    """Format retrieved memories for injection into subagent prompt.

    Returns a concise markdown block suitable for prompt injection.
    When all result scores are below LOW_RELEVANCE_THRESHOLD, a warning is prepended.
    """
    if not results:
        return ""

    max_score = max(score for _, score in results)
    lines = []
    if max_score < LOW_RELEVANCE_THRESHOLD:
        lines.append(f"> ⚠️ 以下记忆与当前查询相关性较低（最高分 {max_score:.2f} < {LOW_RELEVANCE_THRESHOLD:.2f}），仅供参考，请以任务指令为准。\n")

    lines.append("## 相关历史经验（联想记忆）\n")
    for i, (mem, score) in enumerate(results[:max_items], 1):
        lines.append(f"### 记忆 {i}（相关度: {score:.2f}）")
        lines.append(f"- **内容**: {mem.content}")
        lines.append(f"- **语境**: {mem.context}")
        lines.append(f"- **关键词**: {', '.join(mem.keywords)}")
        lines.append(f"- **重要性**: {mem.importance}/10")
        lines.append(f"- **时间**: {mem.timestamp}")
        if mem.related_ids:
            lines.append(f"- **关联**: {', '.join(mem.related_ids)}")
        lines.append("")

    return '\n'.join(lines)


# ==================== CLI Demo ====================

if __name__ == "__main__":
    import tempfile
    import shutil
    sys.path.insert(0, os.path.dirname(__file__))

    print("=" * 60)
    print("联想记忆系统 — CLI Demo")
    print("=" * 60)

    # 创建临时存储目录并填充示例数据
    tmp_path = tempfile.mkdtemp(prefix="agent_memory_")
    store = MemoryStore(store_path=tmp_path)

    samples = [
        Memory(
            id="mem_20260310_001",
            content="修复 LaTeX fontspec 编译错误，原因是 XeLaTeX 路径未正确配置",
            timestamp="2026-03-10T10:00:00",
            keywords=["LaTeX", "fontspec", "XeLaTeX", "编译错误", "路径配置"],
            tags=["bug-fix", "thesis", "latex"],
            context="论文编译流程中 XeLaTeX 引擎路径问题导致 fontspec 包加载失败",
            importance=7,
            related_ids=["mem_20260310_002"],
            access_count=2,
            last_accessed="2026-03-11T14:00:00"
        ),
        Memory(
            id="mem_20260310_002",
            content="配置 latexmk 自动编译流程，添加 -xelatex 参数和 synctex 支持",
            timestamp="2026-03-10T14:00:00",
            keywords=["latexmk", "自动编译", "xelatex", "synctex"],
            tags=["config", "thesis", "latex"],
            context="设置 latexmk 配置文件实现保存即编译的 LaTeX 工作流",
            importance=5,
            related_ids=["mem_20260310_001"],
            access_count=1,
            last_accessed="2026-03-10T16:00:00"
        ),
        Memory(
            id="mem_20260311_001",
            content="实现 Claude Code task-complete-hook，自动记录任务完成到 changelog",
            timestamp="2026-03-11T09:00:00",
            keywords=["hook", "task-complete", "changelog", "自动化"],
            tags=["feature", "claude-code", "automation"],
            context="PostToolUse hook 在 TaskUpdate completed 时自动追加记录到每日 changelog",
            importance=6,
            related_ids=[],
            access_count=0,
            last_accessed=None
        ),
        Memory(
            id="mem_20260311_002",
            content="精读 A-MEM 论文，提取 Zettelkasten 数据模型和联想链机制",
            timestamp="2026-03-11T15:00:00",
            keywords=["A-MEM", "Zettelkasten", "联想记忆", "数据模型", "论文"],
            tags=["research", "memory", "ai"],
            context="A-MEM 使用 Note 结构(content/keywords/tags/context/links)实现 agent 联想记忆",
            importance=8,
            related_ids=["mem_20260311_003"],
            access_count=1,
            last_accessed="2026-03-11T18:00:00"
        ),
        Memory(
            id="mem_20260311_003",
            content="精读 Generative Agents 论文，提取三维评分检索机制",
            timestamp="2026-03-11T18:00:00",
            keywords=["Generative Agents", "三维评分", "recency", "importance", "relevance"],
            tags=["research", "memory", "ai"],
            context="三维检索: recency(0.995^h) + importance(1-10) + relevance(cosine) 等权重min-max归一化",
            importance=8,
            related_ids=["mem_20260311_002"],
            access_count=0,
            last_accessed=None
        ),
    ]

    for m in samples:
        store.add(m)

    print(f"\n已加载 {store.count()} 条记忆\n")

    now = datetime(2026, 3, 12, 10, 0, 0)

    queries = [
        "LaTeX 编译错误怎么修",
        "联想记忆系统论文",
        "自动化 hook changelog",
    ]

    for query in queries:
        print(f"\n{'─' * 60}")
        print(f"查询: {query}")
        print('─' * 60)
        results = retrieve(query, store, top_k=3, spread=True, now=now)
        print(format_for_prompt(results))

    # 清理临时目录
    shutil.rmtree(tmp_path, ignore_errors=True)
