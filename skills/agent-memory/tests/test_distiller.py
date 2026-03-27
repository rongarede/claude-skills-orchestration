"""测试套件：distiller.py 全覆盖测试。

覆盖以下模块：
- Knowledge / MemoryCluster 数据结构
- collect_candidates（候选记忆收集）
- cluster_memories（聚类算法）
- analyze_cluster（知识提炼）
- score_confidence（置信度评分）
- route_output（输出路由）
- execute_output（文件写入）
- distill（端到端流程）
"""

import dataclasses
import os
import sys

import pytest

# ==================== 路径修正 ====================
_SCRIPTS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'scripts')
)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from memory_store import Memory, MemoryStore
from distiller import (
    Knowledge,
    MemoryCluster,
    OutputAction,
    DistillResult,
    distill,
    collect_candidates,
    cluster_memories,
    analyze_cluster,
    score_confidence,
    route_output,
    execute_output,
)


# ==================== 辅助函数 ====================

def make_memory(
    id="mem_test_001",
    content="测试记忆内容",
    timestamp="2026-03-14T10:00:00",
    keywords=None,
    tags=None,
    context="测试上下文",
    importance=7,
    owner="tetsu",
    type="task",
    positive_feedback=0,
    negative_feedback=0,
    last_accessed=None,
    **kwargs,
) -> Memory:
    """快速创建 Memory 对象。"""
    return Memory(
        id=id,
        content=content,
        timestamp=timestamp,
        keywords=keywords if keywords is not None else ["测试", "记忆"],
        tags=tags if tags is not None else ["test"],
        context=context,
        importance=importance,
        owner=owner,
        type=type,
        positive_feedback=positive_feedback,
        negative_feedback=negative_feedback,
        last_accessed=last_accessed,
        **kwargs,
    )


def make_cluster(
    memories,
    shared_keywords=None,
    shared_tags=None,
    agents=None,
    avg_importance=7.0,
    avg_feedback_ratio=0.5,
) -> MemoryCluster:
    """快速创建 MemoryCluster 对象。"""
    return MemoryCluster(
        memories=tuple(memories),
        shared_keywords=tuple(shared_keywords or []),
        shared_tags=tuple(shared_tags or []),
        agents=tuple(agents or ["tetsu"]),
        avg_importance=avg_importance,
        avg_feedback_ratio=avg_feedback_ratio,
    )


def make_knowledge(
    id="know_20260314_001",
    title="Pattern: 测试",
    content="从 3 条记忆中提炼（来源角色：tetsu）：\n- 测试内容",
    knowledge_type="pattern",
    source_memories=("mem_001", "mem_002"),
    source_agents=("tetsu",),
    confidence=0.5,
    evidence_count=3,
    keywords=("测试", "记忆"),
    created="2026-03-14T10:00:00",
) -> Knowledge:
    """快速创建 Knowledge 对象。"""
    return Knowledge(
        id=id,
        title=title,
        content=content,
        knowledge_type=knowledge_type,
        source_memories=source_memories,
        source_agents=source_agents,
        confidence=confidence,
        evidence_count=evidence_count,
        keywords=keywords,
        created=created,
    )


# ==================== TestKnowledge ====================

class TestKnowledge:
    """Knowledge dataclass 结构测试。"""

    def test_knowledge_frozen(self):
        """frozen=True：不可直接修改字段。"""
        k = make_knowledge()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            k.title = "new title"  # type: ignore[misc]

    def test_knowledge_replace(self):
        """dataclasses.replace 可以创建副本并修改字段。"""
        k = make_knowledge(confidence=0.5)
        k2 = dataclasses.replace(k, confidence=0.9)
        assert k2.confidence == 0.9
        assert k.confidence == 0.5  # 原对象不受影响


# ==================== TestMemoryCluster ====================

class TestMemoryCluster:
    """MemoryCluster dataclass 结构测试。"""

    def test_cluster_frozen(self):
        """MemoryCluster 是 frozen dataclass，不可修改。"""
        cluster = make_cluster([make_memory()])
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            cluster.avg_importance = 9.9  # type: ignore[misc]

    def test_cluster_fields(self):
        """MemoryCluster 字段可正常访问。"""
        mem = make_memory(id="mem_x", keywords=["a", "b"], tags=["t1"])
        cluster = MemoryCluster(
            memories=(mem,),
            shared_keywords=("a", "b"),
            shared_tags=("t1",),
            agents=("tetsu",),
            avg_importance=7.0,
            avg_feedback_ratio=0.5,
        )
        assert cluster.avg_importance == 7.0
        assert cluster.shared_keywords == ("a", "b")
        assert cluster.agents == ("tetsu",)


# ==================== TestCollectCandidates ====================

class TestCollectCandidates:
    """collect_candidates 函数测试。"""

    def test_empty_stores(self):
        """空 stores 列表返回空记忆列表。"""
        result = collect_candidates([])
        assert result == []

    def test_filters_blocked_memories(self, tmp_path):
        """blocked 状态记忆被过滤（negative_feedback 多）。"""
        store = MemoryStore(store_path=str(tmp_path), agent_name="distiller")
        # 创建一条 blocked 记忆：ratio <= 0.2 且 negative >= 5
        blocked_mem = make_memory(
            id="mem_blocked_001",
            positive_feedback=1,
            negative_feedback=9,  # ratio = 0.1 <= 0.2, neg=9 >= 5 → blocked
        )
        store.add(blocked_mem)
        result = collect_candidates([str(tmp_path)])
        assert all(m.id != "mem_blocked_001" for m in result)

    def test_filters_low_retention(self, tmp_path):
        """retention < 0.3 的记忆被过滤（访问时间很久以前，importance 很低）。"""
        store = MemoryStore(store_path=str(tmp_path))
        # importance=1, last_accessed 很远的过去 → S = 1*3 = 3天，超过100天后 retention → 0
        old_mem = make_memory(
            id="mem_old_001",
            importance=1,
            last_accessed="2020-01-01T00:00:00",  # 6 年前
        )
        store.add(old_mem)
        result = collect_candidates([str(tmp_path)])
        assert all(m.id != "mem_old_001" for m in result)

    def test_multiple_stores(self, tmp_path):
        """多个 store 的记忆会被聚合返回。"""
        store1 = tmp_path / "store1"
        store2 = tmp_path / "store2"
        store1.mkdir()
        store2.mkdir()

        s1 = MemoryStore(store_path=str(store1))
        s2 = MemoryStore(store_path=str(store2))

        s1.add(make_memory(id="mem_s1_001", importance=8, content="store1 记忆：这是来自 store1 的独特内容"))
        s2.add(make_memory(id="mem_s2_001", importance=8, content="store2 记忆：这是来自 store2 的独特内容"))

        result = collect_candidates([str(store1), str(store2)])
        ids = [m.id for m in result]
        assert "mem_s1_001" in ids
        assert "mem_s2_001" in ids


# ==================== TestClusterMemories ====================

class TestClusterMemories:
    """cluster_memories 聚类算法测试。"""

    def test_empty_list(self):
        """空列表返回空 clusters。"""
        result = cluster_memories([])
        assert result == []

    def test_single_memory(self):
        """单条记忆返回一个包含该记忆的 cluster。"""
        mem = make_memory(keywords=["a", "b"], tags=["t1"])
        result = cluster_memories([mem])
        assert len(result) == 1
        assert result[0].memories == (mem,)

    def test_similar_memories_cluster_together(self):
        """共享足够多 keywords/tags 的记忆归入同一 cluster。"""
        # Jaccard >= 0.5：两条记忆共享 2/3 以上特征
        mem1 = make_memory(id="mem_001", keywords=["auth", "JWT", "token"], tags=["security"])
        mem2 = make_memory(id="mem_002", keywords=["auth", "JWT", "middleware"], tags=["security"])
        result = cluster_memories([mem1, mem2], threshold=0.5)
        # 两条记忆应在同一 cluster
        assert len(result) == 1
        assert len(result[0].memories) == 2

    def test_dissimilar_memories_separate(self):
        """无共同 keywords/tags 的记忆分为不同 cluster。"""
        mem1 = make_memory(id="mem_a", keywords=["LaTeX", "xelatex", "fontspec"], tags=["thesis"])
        mem2 = make_memory(id="mem_b", keywords=["JWT", "auth", "token"], tags=["security"])
        result = cluster_memories([mem1, mem2], threshold=0.5)
        # 两条记忆应在不同 cluster
        assert len(result) == 2

    def test_threshold_boundary(self):
        """Jaccard 恰好等于 threshold 时被归入同 cluster。"""
        # 构造：|intersection| / |union| == threshold
        # features_a = {"x", "y"}, features_b = {"x", "z"} → jaccard = 1/3 ≈ 0.33
        mem1 = make_memory(id="mem_c1", keywords=["x", "y"], tags=[])
        mem2 = make_memory(id="mem_c2", keywords=["x", "z"], tags=[])
        # 在 0.3 阈值下应合并（1/3 >= 0.3）
        result_low = cluster_memories([mem1, mem2], threshold=0.3)
        assert len(result_low) == 1
        # 在 0.5 阈值下应分开（1/3 < 0.5）
        result_high = cluster_memories([mem1, mem2], threshold=0.5)
        assert len(result_high) == 2

    def test_shared_keywords_computed(self):
        """shared_keywords 为出现 >= 50% 成员的高频词（并集中的高频词）。"""
        # 3 条记忆，threshold = max(1, 3//2) = 1，出现 >= 1 次的词纳入
        # auth, JWT 出现 3 次；token 出现 2 次；middleware 出现 1 次
        # 因此所有词都应进入 shared_keywords（threshold=1）
        mem1 = make_memory(id="mem_kw1", keywords=["auth", "JWT", "token"], tags=[])
        mem2 = make_memory(id="mem_kw2", keywords=["auth", "JWT", "middleware"], tags=[])
        mem3 = make_memory(id="mem_kw3", keywords=["auth", "JWT", "token"], tags=[])
        result = cluster_memories([mem1, mem2, mem3], threshold=0.4)
        assert len(result) == 1
        cluster = result[0]
        # auth, JWT 出现 3/3 次；token 出现 2/3 次；middleware 出现 1/3 次
        # threshold = max(1, 3//2) = 1 → 所有词纳入
        # 高置信度关键词（auth, JWT 出现 3 次）必须包含
        assert "auth" in cluster.shared_keywords
        assert "JWT" in cluster.shared_keywords


# ==================== TestAnalyzeCluster ====================

class TestAnalyzeCluster:
    """analyze_cluster 知识提炼测试。"""

    def test_feedback_memories_produce_rule(self):
        """cluster 中 feedback 类型记忆为主 → knowledge_type == 'rule'。"""
        mems = [
            make_memory(id=f"fb_{i}", type="feedback", keywords=["feedback", "rule"])
            for i in range(3)
        ]
        cluster = make_cluster(mems, shared_keywords=["feedback", "rule"])
        k = analyze_cluster(cluster)
        assert k.knowledge_type == "rule"

    def test_task_memories_produce_pattern(self):
        """cluster 中 task 类型记忆为主 → knowledge_type == 'pattern'。"""
        mems = [
            make_memory(id=f"task_{i}", type="task", keywords=["task", "pattern"])
            for i in range(3)
        ]
        cluster = make_cluster(mems, shared_keywords=["task", "pattern"])
        k = analyze_cluster(cluster)
        assert k.knowledge_type == "pattern"

    def test_knowledge_title_includes_keywords(self):
        """标题中包含 shared_keywords（最多 3 个）。"""
        mems = [make_memory(id=f"kw_{i}") for i in range(3)]
        cluster = make_cluster(mems, shared_keywords=["alpha", "beta", "gamma", "delta"])
        k = analyze_cluster(cluster)
        # 标题格式："{type.capitalize()}: {kw1}, {kw2}, {kw3}"
        assert "alpha" in k.title
        assert "beta" in k.title
        assert "gamma" in k.title

    def test_content_aggregation(self):
        """内容是各记忆第一行的去重聚合，不包含重复条目。"""
        mems = [
            make_memory(id="dup_0", content="共同内容\n其余行"),
            make_memory(id="dup_1", content="共同内容\n其余行"),  # 重复第一行
            make_memory(id="dup_2", content="不同内容"),
        ]
        cluster = make_cluster(mems)
        k = analyze_cluster(cluster)
        # "共同内容" 应只出现一次
        assert k.content.count("共同内容") == 1
        assert "不同内容" in k.content

    def test_all_keywords_collected(self):
        """keywords 是所有 cluster 成员 keywords 的并集（去重）。"""
        mems = [
            make_memory(id="kw_a", keywords=["a", "b"]),
            make_memory(id="kw_b", keywords=["b", "c"]),
            make_memory(id="kw_c", keywords=["c", "d"]),
        ]
        cluster = make_cluster(mems)
        k = analyze_cluster(cluster)
        assert set(k.keywords) == {"a", "b", "c", "d"}


# ==================== TestScoreConfidence ====================

class TestScoreConfidence:
    """score_confidence 置信度评分测试。"""

    def test_small_cluster_low_confidence(self):
        """小 cluster（2 条记忆）置信度较低。"""
        mems = [make_memory(id=f"s_{i}") for i in range(2)]
        cluster = make_cluster(
            mems,
            agents=["tetsu"],
            avg_importance=5.0,
            avg_feedback_ratio=0.5,
        )
        k = make_knowledge(evidence_count=2)
        score = score_confidence(k, cluster)
        # size_score = 2/10 = 0.2, feedback = 0.5, cross_agent = 1/5 = 0.2, imp = 5/10 = 0.5
        # = 0.3*0.2 + 0.3*0.5 + 0.25*0.2 + 0.15*0.5 = 0.06 + 0.15 + 0.05 + 0.075 = 0.335
        assert score < 0.5

    def test_large_cluster_higher(self):
        """大 cluster（10 条记忆）置信度高于小 cluster。"""
        mems_small = [make_memory(id=f"sm_{i}") for i in range(2)]
        mems_large = [make_memory(id=f"lg_{i}") for i in range(10)]
        cluster_small = make_cluster(mems_small, agents=["a"], avg_importance=5.0, avg_feedback_ratio=0.5)
        cluster_large = make_cluster(mems_large, agents=["a"], avg_importance=5.0, avg_feedback_ratio=0.5)
        k = make_knowledge()
        score_small = score_confidence(k, cluster_small)
        score_large = score_confidence(k, cluster_large)
        assert score_large > score_small

    def test_cross_agent_boost(self):
        """多角色 cluster 置信度高于单角色。"""
        mems = [make_memory(id=f"ca_{i}") for i in range(5)]
        cluster_single = make_cluster(mems, agents=["tetsu"], avg_importance=5.0, avg_feedback_ratio=0.5)
        cluster_multi = make_cluster(mems, agents=["tetsu", "kaze", "shin", "yomi", "haku"], avg_importance=5.0, avg_feedback_ratio=0.5)
        k = make_knowledge()
        score_single = score_confidence(k, cluster_single)
        score_multi = score_confidence(k, cluster_multi)
        assert score_multi > score_single

    def test_high_feedback_boost(self):
        """高正向反馈 cluster 置信度高于低反馈。"""
        mems = [make_memory(id=f"fb_{i}") for i in range(5)]
        cluster_low = make_cluster(mems, agents=["tetsu"], avg_importance=5.0, avg_feedback_ratio=0.1)
        cluster_high = make_cluster(mems, agents=["tetsu"], avg_importance=5.0, avg_feedback_ratio=0.9)
        k = make_knowledge()
        score_low = score_confidence(k, cluster_low)
        score_high = score_confidence(k, cluster_high)
        assert score_high > score_low

    def test_score_bounded_0_1(self):
        """置信度分数始终在 [0, 1] 范围内。"""
        # 极端最高
        mems = [make_memory(id=f"b_{i}") for i in range(20)]
        cluster_max = make_cluster(
            mems,
            agents=["a", "b", "c", "d", "e", "f"],
            avg_importance=10.0,
            avg_feedback_ratio=1.0,
        )
        k = make_knowledge()
        score = score_confidence(k, cluster_max)
        assert 0.0 <= score <= 1.0

        # 极端最低
        mems2 = [make_memory(id=f"b2_{i}") for i in range(1)]
        cluster_min = make_cluster(
            mems2,
            agents=["a"],
            avg_importance=0.0,
            avg_feedback_ratio=0.0,
        )
        score2 = score_confidence(k, cluster_min)
        assert 0.0 <= score2 <= 1.0


# ==================== TestRouteOutput ====================

class TestRouteOutput:
    """route_output 输出路由测试。"""

    def test_low_confidence_to_memory(self):
        """confidence < 0.4 → destination == 'memory'。"""
        k = make_knowledge(confidence=0.3)
        action = route_output(k, confidence=0.3, dry_run=False)
        assert action.destination == "memory"

    def test_medium_confidence_to_zettelkasten(self):
        """0.4 <= confidence < 0.7 → destination == 'zettelkasten'。"""
        k = make_knowledge(confidence=0.55)
        action = route_output(k, confidence=0.55, dry_run=False)
        assert action.destination == "zettelkasten"

    def test_high_confidence_to_candidate(self):
        """confidence >= 0.7 → destination == 'candidate'。"""
        k = make_knowledge(confidence=0.75)
        action = route_output(k, confidence=0.75, dry_run=False)
        assert action.destination == "candidate"

    def test_custom_dirs(self, tmp_path):
        """自定义输出目录应被正确使用。"""
        zk_dir = str(tmp_path / "zettelkasten")
        cand_dir = str(tmp_path / "candidates")

        k_zk = make_knowledge(confidence=0.55)
        action_zk = route_output(k_zk, 0.55, dry_run=False, zettelkasten_dir=zk_dir)
        assert action_zk.target_path == zk_dir

        k_cand = make_knowledge(confidence=0.8)
        action_cand = route_output(k_cand, 0.8, dry_run=False, candidate_dir=cand_dir)
        assert action_cand.target_path == cand_dir


# ==================== TestExecuteOutput ====================

class TestExecuteOutput:
    """execute_output 文件写入测试。"""

    def test_dry_run_no_write(self, tmp_path):
        """dry_run=True 时不写文件，返回空字符串。"""
        k = make_knowledge()
        action = OutputAction(
            knowledge=k,
            destination="memory",
            target_path=str(tmp_path / "output"),
            dry_run=True,
        )
        result = execute_output(action)
        assert result == ""
        # 目录不应创建
        assert not (tmp_path / "output").exists()

    def test_memory_output_creates_file(self, tmp_path):
        """destination='memory' 时创建 {id}.md 文件。"""
        k = make_knowledge(id="know_20260314_001")
        out_dir = str(tmp_path / "memory_out")
        action = OutputAction(
            knowledge=k,
            destination="memory",
            target_path=out_dir,
            dry_run=False,
        )
        path = execute_output(action)
        assert os.path.exists(path)
        assert path.endswith("know_20260314_001.md")
        content = open(path).read()
        assert "id: know_20260314_001" in content

    def test_zettelkasten_output_format(self, tmp_path):
        """destination='zettelkasten' 时文件含 YAML frontmatter 和 Obsidian 字段。"""
        k = make_knowledge(id="know_zk_001", title="Pattern: auth, JWT")
        out_dir = str(tmp_path / "zk_out")
        action = OutputAction(
            knowledge=k,
            destination="zettelkasten",
            target_path=out_dir,
            dry_run=False,
        )
        path = execute_output(action)
        assert os.path.exists(path)
        content = open(path).read()
        # 必须含 frontmatter 标识符
        assert content.startswith("---")
        assert 'title:' in content
        assert 'up:' in content
        assert 'maturity: seed' in content

    def test_candidate_output_format(self, tmp_path):
        """destination='candidate' 时文件含审阅清单。"""
        k = make_knowledge(id="know_cand_001")
        out_dir = str(tmp_path / "cand_out")
        action = OutputAction(
            knowledge=k,
            destination="candidate",
            target_path=out_dir,
            dry_run=False,
        )
        path = execute_output(action)
        assert os.path.exists(path)
        content = open(path).read()
        assert "审阅操作" in content
        assert "- [ ]" in content  # 审阅清单 checkbox


# ==================== TestDistillEndToEnd ====================

class TestDistillEndToEnd:
    """distill 端到端集成测试。"""

    def _make_similar_memories(self, store: MemoryStore, count: int, base_kw: list, base_tags: list):
        """向 store 写入 count 条相似记忆（共享 keywords/tags）。"""
        for i in range(count):
            mem = make_memory(
                id=f"e2e_{i:03d}",
                keywords=base_kw + [f"extra_{i}"],
                tags=base_tags,
                importance=8,
                type="task",
            )
            store.add(mem)

    def test_full_pipeline(self, tmp_path):
        """端到端：创建记忆 → distill → 验证返回的 DistillResult。"""
        store_dir = tmp_path / "store"
        store_dir.mkdir()
        zk_dir = str(tmp_path / "zk")
        cand_dir = str(tmp_path / "cand")

        store = MemoryStore(store_path=str(store_dir))
        # 写入 5 条相似记忆（共享 3 个 keywords），超过 min_cluster_size=3
        kw = ["auth", "JWT", "security"]
        for i in range(5):
            store.add(make_memory(
                id=f"full_{i:03d}",
                content=f"auth 认证记忆 {i}：使用 JWT 进行用户身份验证，token 有效期 {i+1} 小时，需要刷新策略",
                keywords=kw + [f"unique_{i}"],
                tags=["security"],
                importance=8,
                type="task",
            ))

        result = distill(
            stores=[str(store_dir)],
            min_cluster_size=3,
            dry_run=False,
            zettelkasten_dir=zk_dir,
            candidate_dir=cand_dir,
        )

        assert isinstance(result, DistillResult)
        assert result.clusters_found >= 1
        assert result.knowledge_extracted >= 1

    def test_dry_run_no_side_effects(self, tmp_path):
        """dry_run=True 时不写任何文件。"""
        store_dir = tmp_path / "store_dry"
        store_dir.mkdir()
        zk_dir = str(tmp_path / "zk_dry")
        cand_dir = str(tmp_path / "cand_dry")

        store = MemoryStore(store_path=str(store_dir))
        for i in range(5):
            store.add(make_memory(
                id=f"dry_{i:03d}",
                keywords=["auth", "JWT", "token", f"x_{i}"],
                tags=["security"],
                importance=8,
            ))

        result = distill(
            stores=[str(store_dir)],
            min_cluster_size=3,
            dry_run=True,
            zettelkasten_dir=zk_dir,
            candidate_dir=cand_dir,
        )

        # 输出目录不应被创建
        assert not os.path.exists(zk_dir)
        assert not os.path.exists(cand_dir)
        # actions 仍应被记录（dry_run 分析结果）
        assert isinstance(result, DistillResult)

    def test_all_blocked_memories(self, tmp_path):
        """全部记忆都是 blocked 状态时，返回空结果。"""
        store_dir = tmp_path / "store_blocked"
        store_dir.mkdir()
        store = MemoryStore(store_path=str(store_dir))

        for i in range(5):
            mem = make_memory(
                id=f"blk_{i:03d}",
                positive_feedback=0,
                negative_feedback=10,  # blocked
            )
            store.add(mem)

        result = distill(
            stores=[str(store_dir)],
            min_cluster_size=1,
            dry_run=True,
        )
        assert result.clusters_found == 0
        assert result.knowledge_extracted == 0

    def test_min_cluster_filter(self, tmp_path):
        """min_cluster_size 过滤过小的 cluster。"""
        store_dir = tmp_path / "store_min"
        store_dir.mkdir()
        store = MemoryStore(store_path=str(store_dir))

        # 写入 2 条相似记忆
        for i in range(2):
            store.add(make_memory(
                id=f"min_{i:03d}",
                keywords=["auth", "JWT", "security"],
                tags=["sec"],
                importance=8,
            ))

        # 要求至少 3 条才 distill
        result = distill(
            stores=[str(store_dir)],
            min_cluster_size=3,
            dry_run=True,
        )

        # 2 条组成的 cluster 应被跳过
        assert result.knowledge_extracted == 0
        assert result.skipped_small_clusters >= 1
