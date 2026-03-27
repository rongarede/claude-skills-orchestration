"""知识提取引擎：从多个 memory store 中聚类提炼可复用知识。

设计原则：
- 纯算法实现，无 LLM 依赖
- 所有 dataclass 使用 frozen=True（不可变）
- 复用现有模块：memory_store, feedback_loop, decay_engine
- 输出按置信度分层：memory（低）→ zettelkasten（中）→ candidate（高）
"""

# ==================== 标准库 ====================
import hashlib
import os
import sys
import dataclasses
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

# ==================== 路径修正（确保本地模块可 import）====================
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ==================== 本地模块 ====================
from memory_store import Memory, MemoryStore
from feedback_loop import filter_by_health, get_feedback_ratio, check_memory_health
from decay_engine import compute_retention


# ==================== 数据结构 ====================

@dataclass(frozen=True)
class Knowledge:
    """从记忆 cluster 中提炼出的单条知识。"""
    id: str                           # know_YYYYMMDD_NNN
    title: str                        # 一句话标题
    content: str                      # 提炼的知识内容
    knowledge_type: str               # "rule" | "pattern" | "insight"
    source_memories: tuple            # 来源记忆 ID（frozen 需要 tuple）
    source_agents: tuple              # 来源角色
    confidence: float                 # 0-1
    evidence_count: int               # 支撑记忆数量
    keywords: tuple                   # 聚合后的关键词
    created: str = ""                 # ISO datetime


@dataclass(frozen=True)
class MemoryCluster:
    """由相似记忆组成的聚类。"""
    memories: tuple                   # tuple of Memory objects
    shared_keywords: tuple            # 交集关键词
    shared_tags: tuple                # 交集标签
    agents: tuple                     # 涉及的角色
    avg_importance: float = 0.0
    avg_feedback_ratio: float = 0.5


@dataclass(frozen=True)
class OutputAction:
    """单条知识的输出动作。"""
    knowledge: Knowledge
    destination: str                  # "memory" | "zettelkasten" | "candidate"
    target_path: str                  # 输出文件路径
    dry_run: bool = False


@dataclass(frozen=True)
class DistillResult:
    """distill() 的最终返回值。"""
    clusters_found: int
    knowledge_extracted: int
    actions: tuple                    # tuple of OutputAction
    skipped_small_clusters: int


# ==================== 主入口 ====================

def distill(
    stores: list,
    min_cluster_size: int = 3,
    dry_run: bool = False,
    zettelkasten_dir: str = "",
    candidate_dir: str = "",
) -> DistillResult:
    """主入口：从多个 store 中提炼知识。

    Args:
        stores: store 路径列表（字符串）
        min_cluster_size: 最小 cluster 大小（少于此数跳过）
        dry_run: 若为 True 只分析，不写文件
        zettelkasten_dir: Zettelkasten 输出目录（中置信度）
        candidate_dir: 候选规则输出目录（高置信度）

    Returns:
        DistillResult
    """
    candidates = collect_candidates(stores)
    clusters = cluster_memories(candidates, threshold=0.5)

    # 过滤小 cluster
    valid = [c for c in clusters if len(c.memories) >= min_cluster_size]
    skipped = len(clusters) - len(valid)

    actions = []
    for cluster in valid:
        knowledge = analyze_cluster(cluster)
        # 最小内容质量门槛：content 至少 50 字符
        if len(knowledge.content) < 50:
            skipped += 1
            continue
        confidence = score_confidence(knowledge, cluster)
        knowledge = dataclasses.replace(knowledge, confidence=confidence)
        action = route_output(knowledge, confidence, dry_run, zettelkasten_dir, candidate_dir)
        if not dry_run:
            execute_output(action)
        actions.append(action)

    return DistillResult(
        clusters_found=len(clusters),
        knowledge_extracted=len(actions),
        actions=tuple(actions),
        skipped_small_clusters=skipped,
    )


# ==================== 候选记忆收集 ====================

def collect_candidates(stores: list) -> list:
    """从多个 store 加载 healthy 记忆，过滤低 retention。

    Args:
        stores: store 路径列表

    Returns:
        过滤后的 Memory 列表
    """
    all_memories = []
    now = datetime.now()

    for store_path in stores:
        store = MemoryStore(store_path, agent_name="distiller")
        memories = store.load_all()
        # 排除 blocked / warning 记忆
        healthy = filter_by_health(memories, include_warning=False)
        # 过滤低 retention 记忆（threshold = 0.3）
        for m in healthy:
            ref = m.last_accessed if m.last_accessed else (m.timestamp if m.timestamp else None)
            retention = compute_retention(ref, m.importance, now)
            if retention > 0.3:
                all_memories.append(m)

    return _deduplicate(all_memories)


# ==================== 去重辅助 ====================

def _deduplicate(memories: list, threshold: float = 0.9) -> list:
    """去除近似重复记忆，保留 importance 更高的。

    Args:
        memories: Memory 列表
        threshold: Jaccard 相似度阈值，>= threshold 则视为重复

    Returns:
        去重后的 Memory 列表
    """
    if len(memories) < 2:
        return memories

    to_remove: set = set()
    for i, a in enumerate(memories):
        if i in to_remove:
            continue
        for j, b in enumerate(memories[i + 1:], i + 1):
            if j in to_remove:
                continue
            words_a = set(a.content.lower().split()) if a.content else set()
            words_b = set(b.content.lower().split()) if b.content else set()
            if not words_a or not words_b:
                continue
            sim = len(words_a & words_b) / len(words_a | words_b)
            if sim >= threshold:
                # 保留 importance 更高的，相同 importance 时保留较早出现的（i）
                loser = j if a.importance >= b.importance else i
                to_remove.add(loser)

    return [m for i, m in enumerate(memories) if i not in to_remove]


# ==================== 聚类 ====================

def cluster_memories(memories: list, threshold: float = 0.5) -> list:
    """按 keyword+tag Jaccard 相似度贪心聚类。

    Args:
        memories: Memory 列表
        threshold: Jaccard 阈值（>= threshold 视为相似）

    Returns:
        MemoryCluster 列表
    """
    if not memories:
        return []

    if len(memories) == 1:
        m = memories[0]
        return [MemoryCluster(
            memories=tuple(memories),
            shared_keywords=tuple(m.keywords) if m.keywords else (),
            shared_tags=tuple(m.tags) if m.tags else (),
            agents=tuple({m.owner} if m.owner else {"unknown"}),
            avg_importance=float(m.importance),
            avg_feedback_ratio=get_feedback_ratio(m),
        )]

    def features(m: Memory) -> set:
        return set(m.keywords or []) | set(m.tags or [])

    def jaccard(a: Memory, b: Memory) -> float:
        sa, sb = features(a), features(b)
        if not sa and not sb:
            return 0.0
        union = sa | sb
        if not union:
            return 0.0
        return len(sa & sb) / len(union)

    # 按 importance 降序处理，重要记忆优先成为 cluster 中心
    sorted_mems = sorted(memories, key=lambda m: m.importance, reverse=True)

    assigned = set()
    clusters = []

    for mem in sorted_mems:
        if id(mem) in assigned:
            continue

        cluster_mems = [mem]
        assigned.add(id(mem))

        for other in sorted_mems:
            if id(other) in assigned:
                continue
            # 与 cluster 中任意一条记忆的相似度 >= threshold 则加入
            if any(jaccard(other, cm) >= threshold for cm in cluster_mems):
                cluster_mems.append(other)
                assigned.add(id(other))

        # 构建 MemoryCluster（高频词：出现 >= 50% 成员数量的词）
        from collections import Counter
        threshold_count = max(1, len(cluster_mems) // 2)

        kw_counter: Counter = Counter()
        for m in cluster_mems:
            kw_counter.update(set(m.keywords or []))
        shared_kw = {kw for kw, count in kw_counter.items() if count >= threshold_count}

        tag_counter: Counter = Counter()
        for m in cluster_mems:
            tag_counter.update(set(m.tags or []))
        shared_tags_set = {tag for tag, count in tag_counter.items() if count >= threshold_count}
        agents = {(m.owner or "unknown") for m in cluster_mems}
        avg_imp = sum(m.importance for m in cluster_mems) / len(cluster_mems)
        avg_fb = sum(get_feedback_ratio(m) for m in cluster_mems) / len(cluster_mems)

        clusters.append(MemoryCluster(
            memories=tuple(cluster_mems),
            shared_keywords=tuple(sorted(shared_kw)),
            shared_tags=tuple(sorted(shared_tags_set)),
            agents=tuple(sorted(agents)),
            avg_importance=round(avg_imp, 2),
            avg_feedback_ratio=round(avg_fb, 2),
        ))

    return clusters


# ==================== 知识分析 ====================

def analyze_cluster(cluster: MemoryCluster) -> Knowledge:
    """从 cluster 中提取知识（纯算法，无 LLM）。

    知识类型判断：
    - feedback 类记忆为主 → rule
    - task 类记忆为主 → pattern
    - 其他 → insight

    Args:
        cluster: MemoryCluster 对象

    Returns:
        Knowledge 对象（confidence 留 0.0，由 score_confidence 填充）
    """
    # 统计各 type 数量
    type_counts: dict = {}
    for m in cluster.memories:
        t = getattr(m, "type", "task") or "task"
        type_counts[t] = type_counts.get(t, 0) + 1

    dominant_type = max(type_counts, key=type_counts.get)
    if dominant_type == "feedback":
        knowledge_type = "rule"
    elif dominant_type == "task":
        knowledge_type = "pattern"
    else:
        knowledge_type = "insight"

    # 生成标题：共同关键词 + 知识类型
    kw_str = ", ".join(cluster.shared_keywords[:3]) if cluster.shared_keywords else "general"
    title = f"{knowledge_type.capitalize()}: {kw_str}"

    # 生成内容：聚合每条记忆前 3 行作为要点（去重）
    bullet_points = []
    for m in cluster.memories:
        if not m.content:
            continue
        lines = m.content.strip().split("\n")[:3]
        summary = " ".join(line.strip()[:200] for line in lines if line.strip())
        if summary and summary not in bullet_points:
            bullet_points.append(summary)

    content = (
        f"从 {len(cluster.memories)} 条记忆中提炼"
        f"（来源角色：{', '.join(cluster.agents)}）：\n"
    )
    content += "\n".join(f"- {bp}" for bp in bullet_points[:15])

    # 聚合所有关键词
    all_keywords: set = set()
    for m in cluster.memories:
        all_keywords.update(m.keywords or [])

    h = hashlib.sha256("_".join(m.id for m in cluster.memories).encode()).hexdigest()[:6]
    knowledge_id = f"know_{datetime.now().strftime('%Y%m%d')}_{h}"

    return Knowledge(
        id=knowledge_id,
        title=title,
        content=content,
        knowledge_type=knowledge_type,
        source_memories=tuple(m.id for m in cluster.memories),
        source_agents=cluster.agents,
        confidence=0.0,
        evidence_count=len(cluster.memories),
        keywords=tuple(sorted(all_keywords)),
        created=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    )


# ==================== 置信度评分 ====================

def score_confidence(knowledge: Knowledge, cluster: MemoryCluster) -> float:
    """计算知识置信度（0-1）。

    加权公式：
    - 0.30 × cluster 大小得分（记忆数 / 10，上限 1.0）
    - 0.30 × 平均反馈质量
    - 0.25 × 跨 agent 覆盖度（角色数 / 5，上限 1.0）
    - 0.15 × 平均重要性（importance / 10，上限 1.0）

    Args:
        knowledge: Knowledge 对象
        cluster: 对应的 MemoryCluster

    Returns:
        置信度，范围 [0.0, 1.0]
    """
    size_score = min(1.0, len(cluster.memories) / 10)
    feedback_score = cluster.avg_feedback_ratio
    cross_agent = min(1.0, len(cluster.agents) / 5)
    importance_score = min(1.0, cluster.avg_importance / 10)

    return round(
        0.30 * size_score
        + 0.30 * feedback_score
        + 0.25 * cross_agent
        + 0.15 * importance_score,
        3,
    )


# ==================== 输出路由 ====================

def route_output(
    knowledge: Knowledge,
    confidence: float,
    dry_run: bool,
    zettelkasten_dir: str = "",
    candidate_dir: str = "",
) -> OutputAction:
    """根据置信度决定输出目标。

    置信度分层：
    - < 0.4  → memory（保存到 ~/mem/mem/shared/）
    - 0.4-0.7 → zettelkasten（Obsidian 笔记）
    - >= 0.7 → candidate（CLAUDE.md 候选规则）

    Args:
        knowledge: Knowledge 对象
        confidence: 置信度
        dry_run: 是否只分析不写文件
        zettelkasten_dir: Zettelkasten 输出目录
        candidate_dir: 候选规则输出目录

    Returns:
        OutputAction
    """
    if confidence < 0.4:
        dest = "memory"
        target = os.path.expanduser("~/mem/mem/shared")
    elif confidence < 0.7:
        dest = "zettelkasten"
        target = zettelkasten_dir or os.path.expanduser(
            "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
            "/300_Resources/Zettelkasten"
        )
    else:
        dest = "candidate"
        target = candidate_dir or os.path.expanduser("~/mem/mem/distilled")

    return OutputAction(
        knowledge=knowledge,
        destination=dest,
        target_path=target,
        dry_run=dry_run,
    )


# ==================== 输出执行 ====================

def execute_output(action: OutputAction) -> str:
    """执行输出动作，返回写入的文件路径。

    Args:
        action: OutputAction 对象

    Returns:
        写入的文件路径字符串，dry_run 时返回空字符串
    """
    if action.dry_run:
        return ""

    # 路径安全验证：确保输出路径在用户目录下（防止路径穿越攻击）
    if action.target_path:
        import tempfile
        # 路径安全检查时，也对 target_path 做 realpath 解析
        real_path = os.path.realpath(action.target_path)
        home = os.path.realpath(os.path.expanduser("~"))
        tmp_dir = os.path.realpath(tempfile.gettempdir())
        in_home = real_path.startswith(home + os.sep) or real_path == home
        # macOS 上 /tmp 是 /private/tmp 的符号链接，额外允许两种前缀
        in_tmp = (real_path.startswith(tmp_dir + os.sep) or real_path == tmp_dir
                  or real_path.startswith("/private/tmp" + os.sep)
                  or real_path.startswith("/tmp" + os.sep))
        if not (in_home or in_tmp):
            raise ValueError(f"路径不安全，必须在用户目录或临时目录下: {real_path}")

    k = action.knowledge

    if action.destination == "memory":
        out_dir = action.target_path or os.path.expanduser("~/mem/mem/shared")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{k.id}.md")
        content = _render_memory(k)

    elif action.destination == "zettelkasten":
        out_dir = action.target_path or os.path.expanduser(
            "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
            "/300_Resources/Zettelkasten"
        )
        os.makedirs(out_dir, exist_ok=True)
        # Obsidian 友好文件名（替换非法字符，截断长度）
        safe_title = k.title.replace("/", "-").replace(":", " -")[:80]
        path = os.path.join(out_dir, f"{safe_title}.md")
        content = _render_zettelkasten(k)

    elif action.destination == "candidate":
        out_dir = action.target_path or os.path.expanduser("~/mem/mem/distilled")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{k.id}.md")
        content = _render_candidate(k)

    else:
        return ""

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ==================== 渲染函数 ====================

def _render_memory(k: Knowledge) -> str:
    """渲染为 memory store 格式的 Markdown。"""
    keywords_str = "\n".join(f"  - {kw}" for kw in k.keywords[:10])
    sources_list = "\n".join(f"  - {sid}" for sid in k.source_memories[:10])
    return (
        f"---\n"
        f"id: {k.id}\n"
        f'name: "{k.title}"\n'
        f'description: "从 {k.evidence_count} 条记忆中提炼的{k.knowledge_type}"\n'
        f"type: knowledge\n"
        f"owner: distiller\n"
        f"scope: shared\n"
        f"importance: {min(10, max(1, int(k.confidence * 10)))}\n"
        f"keywords:\n{keywords_str}\n"
        f"tags:\n  - distilled\n  - {k.knowledge_type}\n"
        f"related_ids:\n{sources_list}\n"
        f"confidence: {k.confidence}\n"
        f"---\n\n"
        f"{k.content}\n"
    )


def _render_zettelkasten(k: Knowledge) -> str:
    """渲染为 Obsidian Zettelkasten 笔记格式。"""
    extra_tags = list(k.keywords[:5])
    all_tags = [k.knowledge_type, "distilled"] + extra_tags
    tags_str = "\n".join(f"  - {t}" for t in all_tags)
    return (
        f"---\n"
        f'title: "{k.title}"\n'
        f'up: "[[_zettelkasten_moc]]"\n'
        f"tags:\n{tags_str}\n"
        f"confidence: {k.confidence}\n"
        f"evidence_count: {k.evidence_count}\n"
        f"source_agents: {list(k.source_agents)}\n"
        f"created: {k.created}\n"
        f"maturity: seed\n"
        f"---\n\n"
        f"# {k.title}\n\n"
        f"{k.content}\n\n"
        f"## 来源\n\n"
        f"- 提炼自 {k.evidence_count} 条 agent 记忆\n"
        f"- 涉及角色：{', '.join(k.source_agents)}\n"
        f"- 置信度：{k.confidence:.1%}\n"
        f"- 知识类型：{k.knowledge_type}\n"
    )


def _render_candidate(k: Knowledge) -> str:
    """渲染为 CLAUDE.md 候选规则格式。"""
    return (
        f"---\n"
        f"id: {k.id}\n"
        f'title: "{k.title}"\n'
        f"knowledge_type: {k.knowledge_type}\n"
        f"confidence: {k.confidence}\n"
        f"evidence_count: {k.evidence_count}\n"
        f"source_agents: {list(k.source_agents)}\n"
        f"status: pending_review\n"
        f"created: {k.created}\n"
        f"---\n\n"
        f"# 候选规则：{k.title}\n\n"
        f"## 提炼内容\n\n"
        f"{k.content}\n\n"
        f"## 建议注入位置\n\n"
        f"- 知识类型：{k.knowledge_type}\n"
        f"- 置信度：{k.confidence:.1%}（高置信度，建议审阅后写入 CLAUDE.md 或 WhoAmI）\n"
        f"- 来源角色：{', '.join(k.source_agents)}\n"
        f"- 证据数量：{k.evidence_count} 条记忆\n\n"
        f"## 审阅操作\n\n"
        f"- [ ] 确认知识正确性\n"
        f"- [ ] 决定注入位置（CLAUDE.md / WhoAmI / 放弃）\n"
        f"- [ ] 执行注入\n"
    )
