"""Phase 1C 检索使用反馈闭环测试。

覆盖：
- retrieval_count 自动递增
- last_retrieved 自动更新
- usefulness_score 反馈更新（useful / not-useful）
- usefulness_score 纳入 importance 评分
- identify_stale_memories 过期记忆检测
- 新字段的 frontmatter 序列化/反序列化向后兼容
"""

import os
import sys
import dataclasses

import pytest

_SCRIPTS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'scripts')
)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from datetime import datetime
from memory_store import Memory, MemoryStore
from retriever import retrieve, compute_importance_score
from feedback_loop import identify_stale_memories


# ==================== Fixtures ====================

@pytest.fixture
def store_with_memories(tmp_path):
    """创建包含 3 条记忆的 store，用于检索测试。"""
    store = MemoryStore(store_path=str(tmp_path))
    memories = [
        Memory(
            id="mem_001",
            content="修复 LaTeX fontspec 编译错误",
            timestamp="2026-03-10T10:00:00",
            keywords=["LaTeX", "fontspec", "编译错误"],
            tags=["bug-fix"],
            context="XeLaTeX 路径未配置导致 fontspec 加载失败",
            importance=7,
            retrieval_count=0,
            last_retrieved="",
            usefulness_score=0.5,
        ),
        Memory(
            id="mem_002",
            content="配置 latexmk 自动编译流程",
            timestamp="2026-03-10T14:00:00",
            keywords=["latexmk", "编译", "自动化"],
            tags=["config"],
            context="latexmk 保存即编译工作流",
            importance=5,
            retrieval_count=0,
            last_retrieved="",
            usefulness_score=0.5,
        ),
        Memory(
            id="mem_003",
            content="实现联想记忆系统检索引擎",
            timestamp="2026-03-11T09:00:00",
            keywords=["联想记忆", "检索", "BM25"],
            tags=["feature"],
            context="BM25 + 三维评分检索引擎",
            importance=8,
            retrieval_count=0,
            last_retrieved="",
            usefulness_score=0.5,
        ),
    ]
    for m in memories:
        store.add(m)
    return store


# ==================== Test: retrieval_count increments ====================

class TestRetrievalCountIncrements:
    """检索后 retrieval_count 应自动 +1。"""

    def test_single_retrieval_increments_count(self, store_with_memories):
        """单次检索后，被返回的记忆 retrieval_count 应为 1。"""
        store = store_with_memories
        now = datetime(2026, 3, 12, 10, 0, 0)

        results = retrieve("LaTeX 编译错误", store, top_k=1, spread=False, now=now)
        assert len(results) >= 1

        # 重新从 store 读取，验证持久化
        mem = store.get(results[0][0].id)
        assert mem.retrieval_count == 1
        assert mem.last_retrieved != ""

    def test_multiple_retrievals_accumulate(self, store_with_memories):
        """多次检索后，retrieval_count 应累加。"""
        store = store_with_memories
        now = datetime(2026, 3, 12, 10, 0, 0)

        # 第一次检索
        retrieve("LaTeX 编译错误", store, top_k=1, spread=False, now=now)
        # 第二次检索
        now2 = datetime(2026, 3, 12, 11, 0, 0)
        retrieve("LaTeX fontspec", store, top_k=1, spread=False, now=now2)

        mem = store.get("mem_001")
        assert mem.retrieval_count >= 2

    def test_last_retrieved_is_iso_format(self, store_with_memories):
        """last_retrieved 应为 ISO 格式时间字符串。"""
        store = store_with_memories
        now = datetime(2026, 3, 12, 10, 0, 0)

        retrieve("LaTeX", store, top_k=1, spread=False, now=now)
        mem = store.get("mem_001")
        # 验证可以被 fromisoformat 解析
        parsed = datetime.fromisoformat(mem.last_retrieved)
        assert parsed == now

    def test_retrieval_with_spread_also_tracks(self, store_with_memories):
        """启用 spread 时，被返回的记忆也应更新 retrieval_count。"""
        store = store_with_memories
        now = datetime(2026, 3, 12, 10, 0, 0)

        results = retrieve("LaTeX", store, top_k=3, spread=True, now=now)
        for mem, _ in results:
            reloaded = store.get(mem.id)
            assert reloaded.retrieval_count >= 1


# ==================== Test: usefulness_score update ====================

class TestUsefulnessScoreUpdate:
    """--useful / --not-useful 反馈应更新 usefulness_score。"""

    def test_useful_feedback_increases_score(self, tmp_path):
        """标记 useful 后 usefulness_score 应 +0.1。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id="mem_fb_001",
            content="测试记忆",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="测试上下文",
            importance=5,
            usefulness_score=0.5,
        )
        store.add(mem)

        # 模拟 --useful 反馈逻辑
        memory = store.get("mem_fb_001")
        new_usefulness = min(1.0, memory.usefulness_score + 0.1)
        updated = dataclasses.replace(
            memory,
            positive_feedback=memory.positive_feedback + 1,
            usefulness_score=new_usefulness,
        )
        store.update(updated)

        reloaded = store.get("mem_fb_001")
        assert abs(reloaded.usefulness_score - 0.6) < 1e-9
        assert reloaded.positive_feedback == 1

    def test_not_useful_feedback_decreases_score(self, tmp_path):
        """标记 not-useful 后 usefulness_score 应 -0.1。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id="mem_fb_002",
            content="测试记忆",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="测试上下文",
            importance=5,
            usefulness_score=0.5,
        )
        store.add(mem)

        memory = store.get("mem_fb_002")
        new_usefulness = max(0.0, memory.usefulness_score - 0.1)
        updated = dataclasses.replace(
            memory,
            negative_feedback=memory.negative_feedback + 1,
            usefulness_score=new_usefulness,
        )
        store.update(updated)

        reloaded = store.get("mem_fb_002")
        assert abs(reloaded.usefulness_score - 0.4) < 1e-9
        assert reloaded.negative_feedback == 1

    def test_usefulness_score_clamped_at_bounds(self, tmp_path):
        """usefulness_score 不应超出 [0.0, 1.0] 范围。"""
        store = MemoryStore(store_path=str(tmp_path))

        # 测试上界
        mem_high = Memory(
            id="mem_fb_high",
            content="高分记忆",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="测试",
            importance=5,
            usefulness_score=0.95,
        )
        store.add(mem_high)
        m = store.get("mem_fb_high")
        new_score = min(1.0, m.usefulness_score + 0.1)
        updated = dataclasses.replace(m, usefulness_score=new_score)
        store.update(updated)
        assert store.get("mem_fb_high").usefulness_score == 1.0

        # 测试下界
        mem_low = Memory(
            id="mem_fb_low",
            content="低分记忆",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="测试",
            importance=5,
            usefulness_score=0.05,
        )
        store.add(mem_low)
        m = store.get("mem_fb_low")
        new_score = max(0.0, m.usefulness_score - 0.1)
        updated = dataclasses.replace(m, usefulness_score=new_score)
        store.update(updated)
        assert store.get("mem_fb_low").usefulness_score == 0.0


# ==================== Test: usefulness in importance scoring ====================

class TestUsefulnessInImportanceScoring:
    """usefulness_score 应影响 compute_importance_score 的输出。"""

    def test_high_usefulness_boosts_score(self):
        """usefulness_score=1.0 应提升 importance score。"""
        base_mem = Memory(
            id="test_001",
            content="测试",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="测试",
            importance=5,
            usefulness_score=0.5,
        )
        high_mem = dataclasses.replace(base_mem, usefulness_score=1.0)

        base_score = compute_importance_score(base_mem)
        high_score = compute_importance_score(high_mem)

        assert high_score > base_score

    def test_low_usefulness_reduces_score(self):
        """usefulness_score=0.0 应降低 importance score。"""
        base_mem = Memory(
            id="test_002",
            content="测试",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="测试",
            importance=5,
            usefulness_score=0.5,
        )
        low_mem = dataclasses.replace(base_mem, usefulness_score=0.0)

        base_score = compute_importance_score(base_mem)
        low_score = compute_importance_score(low_mem)

        assert low_score < base_score

    def test_neutral_usefulness_no_effect(self):
        """usefulness_score=0.5（默认）应不影响评分。"""
        mem = Memory(
            id="test_003",
            content="测试",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="测试",
            importance=5,
            usefulness_score=0.5,
        )
        # usefulness_bonus = (0.5 - 0.5) * 0.4 = 0.0
        score = compute_importance_score(mem)
        # base = 5/10 = 0.5, recall_bonus = 0, feedback_adj = 0, usefulness_bonus = 0
        assert abs(score - 0.5) < 1e-9

    def test_importance_score_clamped(self):
        """importance score 应 clamp 到 [0.0, 1.0]。"""
        mem_extreme = Memory(
            id="test_004",
            content="测试",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="测试",
            importance=10,
            access_count=20,
            positive_feedback=10,
            negative_feedback=0,
            usefulness_score=1.0,
        )
        score = compute_importance_score(mem_extreme)
        assert score <= 1.0
        assert score >= 0.0


# ==================== Test: stale memory identification ====================

class TestStaleMemoryIdentification:
    """identify_stale_memories 应正确标记过期记忆。"""

    def test_old_low_importance_no_retrieval_is_stale(self, tmp_path):
        """30+ 天前创建、importance < 5、从未被检索 = 过期。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id="stale_001",
            content="旧的低价值记忆",
            timestamp="2026-01-01T10:00:00",
            keywords=["旧", "低"],
            tags=["test"],
            context="旧记忆",
            importance=3,
            retrieval_count=0,
        )
        store.add(mem)

        now = datetime(2026, 3, 15, 10, 0, 0)
        stale = identify_stale_memories(store, min_days=30, now=now)
        assert len(stale) == 1
        assert stale[0].id == "stale_001"

    def test_high_importance_not_stale(self, tmp_path):
        """importance >= 5 的记忆不应被标记为过期。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id="not_stale_001",
            content="高价值记忆",
            timestamp="2026-01-01T10:00:00",
            keywords=["高", "价值"],
            tags=["test"],
            context="高价值",
            importance=5,
            retrieval_count=0,
        )
        store.add(mem)

        now = datetime(2026, 3, 15, 10, 0, 0)
        stale = identify_stale_memories(store, min_days=30, now=now)
        assert len(stale) == 0

    def test_recently_created_not_stale(self, tmp_path):
        """创建不到 30 天的低价值记忆不应被标记。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id="recent_001",
            content="新的低价值记忆",
            timestamp="2026-03-10T10:00:00",
            keywords=["新"],
            tags=["test"],
            context="新记忆",
            importance=2,
            retrieval_count=0,
        )
        store.add(mem)

        now = datetime(2026, 3, 15, 10, 0, 0)
        stale = identify_stale_memories(store, min_days=30, now=now)
        assert len(stale) == 0

    def test_retrieved_memory_not_stale(self, tmp_path):
        """被检索过的低价值旧记忆不应被标记（min_retrievals=0）。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id="retrieved_001",
            content="被检索过的旧记忆",
            timestamp="2026-01-01T10:00:00",
            keywords=["旧"],
            tags=["test"],
            context="旧但被用过",
            importance=3,
            retrieval_count=1,
        )
        store.add(mem)

        now = datetime(2026, 3, 15, 10, 0, 0)
        stale = identify_stale_memories(store, min_days=30, min_retrievals=0, now=now)
        assert len(stale) == 0

    def test_custom_min_retrievals(self, tmp_path):
        """自定义 min_retrievals 阈值。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id="low_retrieval_001",
            content="低检索量旧记忆",
            timestamp="2026-01-01T10:00:00",
            keywords=["旧"],
            tags=["test"],
            context="旧记忆",
            importance=3,
            retrieval_count=2,
        )
        store.add(mem)

        now = datetime(2026, 3, 15, 10, 0, 0)
        # min_retrievals=2 意味着 retrieval_count <= 2 的记忆算过期
        stale = identify_stale_memories(store, min_days=30, min_retrievals=2, now=now)
        assert len(stale) == 1

    def test_empty_store_returns_empty(self, tmp_path):
        """空 store 应返回空列表。"""
        store = MemoryStore(store_path=str(tmp_path))
        stale = identify_stale_memories(store)
        assert stale == []


# ==================== Test: Backward compatibility ====================

class TestBackwardCompatibility:
    """旧记忆（缺失新字段）应使用默认值正常加载。"""

    def test_old_memory_loads_with_defaults(self, tmp_path):
        """不含 retrieval_count/last_retrieved/usefulness_score 的记忆文件应正常加载。"""
        store = MemoryStore(store_path=str(tmp_path))
        # 手动写入不含新字段的 frontmatter
        md_content = """---
id: old_mem_001
name: ''
description: ''
type: task
owner: ''
scope: personal
importance: 5
access_count: 0
last_accessed: null
keywords:
- 旧
- 记忆
tags:
- test
context: 旧的记忆文件
timestamp: '2026-03-10T10:00:00'
related: []
accessed_by: []
evolution_history: []
positive_feedback: 0
negative_feedback: 0
layer: L1
---

旧的记忆内容
"""
        (tmp_path / "old_mem_001.md").write_text(md_content, encoding='utf-8')
        mem = store.get("old_mem_001")
        assert mem is not None
        assert mem.retrieval_count == 0
        assert mem.last_retrieved == ""
        assert abs(mem.usefulness_score - 0.5) < 1e-9

    def test_roundtrip_with_new_fields(self, tmp_path):
        """新字段的序列化和反序列化应一致。"""
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id="roundtrip_001",
            content="往返测试",
            timestamp="2026-03-14T10:00:00",
            keywords=["测试"],
            tags=["test"],
            context="往返",
            importance=6,
            retrieval_count=5,
            last_retrieved="2026-03-14T15:00:00",
            usefulness_score=0.8,
        )
        store.add(mem)
        loaded = store.get("roundtrip_001")
        assert loaded.retrieval_count == 5
        assert loaded.last_retrieved == "2026-03-14T15:00:00"
        assert abs(loaded.usefulness_score - 0.8) < 1e-9
