"""Phase 1 记忆反馈改进测试：Active Recall + Retrieval Feedback。

TDD 流程：
1. RED: 先运行确认全部失败
2. GREEN: 修改代码让测试通过
3. REFACTOR: 清理
"""

import os
import sys
import shutil
import tempfile
import subprocess
from datetime import datetime

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore


def make_memory(**kwargs) -> Memory:
    """辅助函数：创建测试用 Memory，设置必填字段默认值。"""
    defaults = dict(
        id="test_mem_001",
        content="测试记忆内容",
        timestamp="2026-03-14T10:00:00",
        keywords=["测试", "记忆"],
        tags=["test"],
        context="测试上下文",
        importance=5,
    )
    defaults.update(kwargs)
    return Memory(**defaults)


# ==================== Phase 1A: Active Recall ====================

class TestActiveRecall:
    """测试 compute_importance_score 中的 Active Recall bonus。"""

    def test_active_recall_bonus(self):
        """access_count > 0 的记忆，compute_importance_score 应高于 access_count=0 的记忆。

        recall_bonus = min(0.2, access_count * 0.02)
        access_count=5 → bonus=0.10
        """
        from retriever import compute_importance_score

        mem_with_access = make_memory(importance=5, access_count=5)
        mem_no_access = make_memory(importance=5, access_count=0)

        score_with = compute_importance_score(mem_with_access)
        score_without = compute_importance_score(mem_no_access)

        # access_count=5 → recall_bonus=0.10，得分应更高
        assert score_with > score_without, (
            f"access_count=5 的记忆得分 ({score_with:.3f}) 应高于 access_count=0 ({score_without:.3f})"
        )
        # 差值应约为 0.10
        diff = score_with - score_without
        assert abs(diff - 0.10) < 0.001, f"差值应为 0.10，实际为 {diff:.3f}"

    def test_active_recall_cap(self):
        """access_count=100 时 bonus 不超过 0.2（上限保护）。"""
        from retriever import compute_importance_score

        mem_high_access = make_memory(importance=5, access_count=100)
        mem_no_access = make_memory(importance=5, access_count=0)

        score_high = compute_importance_score(mem_high_access)
        score_zero = compute_importance_score(mem_no_access)

        diff = score_high - score_zero
        assert diff <= 0.2 + 1e-9, f"recall_bonus 不应超过 0.2，实际差值为 {diff:.3f}"
        # 且应等于上限 0.2
        assert abs(diff - 0.2) < 0.001, f"access_count=100 时 bonus 应恰好为上限 0.2，实际为 {diff:.3f}"

    def test_active_recall_zero(self):
        """access_count=0 时无 bonus（向后兼容）。"""
        from retriever import compute_importance_score, compute_importance

        mem = make_memory(importance=7, access_count=0)
        # compute_importance_score 应与旧 compute_importance 一致（无额外 bonus）
        old_score = compute_importance(mem)
        new_score = compute_importance_score(mem)

        # 没有 feedback 时，access_count=0，两者应相等
        assert abs(new_score - old_score) < 1e-9, (
            f"access_count=0 时新旧评分应相等：old={old_score}, new={new_score}"
        )

    def test_active_recall_10_gives_0_2(self):
        """access_count=10 时 bonus=0.2（恰好达到上限）。"""
        from retriever import compute_importance_score

        mem_access10 = make_memory(importance=5, access_count=10)
        mem_no_access = make_memory(importance=5, access_count=0)

        diff = compute_importance_score(mem_access10) - compute_importance_score(mem_no_access)
        assert abs(diff - 0.2) < 0.001, f"access_count=10 时 bonus 应为 0.2，实际为 {diff:.3f}"


# ==================== Phase 1B: Retrieval Feedback 字段 ====================

class TestFeedbackFields:
    """测试 Memory dataclass 的 feedback 字段。"""

    def test_feedback_fields_default(self):
        """新建 Memory 默认 positive_feedback=0, negative_feedback=0。"""
        mem = make_memory()
        assert mem.positive_feedback == 0, f"positive_feedback 默认值应为 0，实际：{mem.positive_feedback}"
        assert mem.negative_feedback == 0, f"negative_feedback 默认值应为 0，实际：{mem.negative_feedback}"

    def test_feedback_persistence(self):
        """创建记忆 → 更新 positive_feedback → 重新加载 → 字段正确。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="fb_test_001")
            store.add(mem)

            # 更新 positive_feedback
            loaded = store.get("fb_test_001")
            loaded.positive_feedback = 3
            store.update(loaded)

            # 重新加载验证
            reloaded = store.get("fb_test_001")
            assert reloaded.positive_feedback == 3, (
                f"positive_feedback 应为 3，实际：{reloaded.positive_feedback}"
            )
            assert reloaded.negative_feedback == 0
        finally:
            shutil.rmtree(tmp_dir)

    def test_backward_compatible(self):
        """旧格式记忆（无 feedback 字段）应正常加载，默认值为 0。"""
        # 直接用 from_dict 传入无 feedback 字段的旧格式数据
        old_data = {
            "id": "old_mem_001",
            "content": "旧格式记忆",
            "timestamp": "2026-01-01T00:00:00",
            "keywords": ["旧", "格式"],
            "tags": ["legacy"],
            "context": "旧格式测试",
            "importance": 5,
        }
        mem = Memory.from_dict(old_data)
        assert mem.positive_feedback == 0, f"旧格式记忆 positive_feedback 应默认为 0，实际：{mem.positive_feedback}"
        assert mem.negative_feedback == 0, f"旧格式记忆 negative_feedback 应默认为 0，实际：{mem.negative_feedback}"

    def test_backward_compatible_file(self):
        """从缺少 feedback 字段的旧 markdown 文件加载记忆。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            # 手动写入不含 feedback 字段的旧格式文件
            old_md = """---
id: old_file_mem_001
name: 旧格式文件
description: 测试旧格式文件向后兼容
type: task
owner: ''
scope: personal
importance: 6
access_count: 2
last_accessed: null
keywords:
- 旧格式
- 文件
tags:
- legacy
context: 旧格式文件测试
timestamp: '2026-01-01T00:00:00'
related: []
accessed_by: []
evolution_history: []
---

旧格式记忆内容，无 feedback 字段
"""
            import pathlib
            (pathlib.Path(tmp_dir) / "old_file_mem_001.md").write_text(old_md, encoding='utf-8')

            store = MemoryStore(store_path=tmp_dir)
            memories = store.load_all()
            assert len(memories) == 1
            mem = memories[0]
            assert mem.positive_feedback == 0
            assert mem.negative_feedback == 0
        finally:
            shutil.rmtree(tmp_dir)


# ==================== Phase 1B: Feedback 影响评分 ====================

class TestFeedbackAdjustment:
    """测试 feedback 对 compute_importance_score 评分的影响。"""

    def test_feedback_adjusts_importance_positive(self):
        """positive_feedback=8, negative_feedback=2 → importance 评分上调。"""
        from retriever import compute_importance_score

        mem_positive = make_memory(importance=5, access_count=0,
                                    positive_feedback=8, negative_feedback=2)
        mem_neutral = make_memory(importance=5, access_count=0,
                                   positive_feedback=0, negative_feedback=0)

        score_positive = compute_importance_score(mem_positive)
        score_neutral = compute_importance_score(mem_neutral)

        assert score_positive > score_neutral, (
            f"positive_feedback=8 时评分 ({score_positive:.3f}) 应高于 neutral ({score_neutral:.3f})"
        )

    def test_feedback_adjusts_importance_negative(self):
        """positive_feedback=2, negative_feedback=8 → importance 评分下调。"""
        from retriever import compute_importance_score

        mem_negative = make_memory(importance=5, access_count=0,
                                    positive_feedback=2, negative_feedback=8)
        mem_neutral = make_memory(importance=5, access_count=0,
                                   positive_feedback=0, negative_feedback=0)

        score_negative = compute_importance_score(mem_negative)
        score_neutral = compute_importance_score(mem_neutral)

        assert score_negative < score_neutral, (
            f"negative_feedback=8 时评分 ({score_negative:.3f}) 应低于 neutral ({score_neutral:.3f})"
        )

    def test_feedback_cold_start(self):
        """total_feedback < 10 → confidence 低，调整幅度小。"""
        from retriever import compute_importance_score

        # total_feedback=3（confidence = 3/10 = 0.3），全部为 positive
        mem_low_fb = make_memory(importance=5, access_count=0,
                                  positive_feedback=3, negative_feedback=0)
        # total_feedback=10（confidence = 1.0），全部为 positive（满信心）
        mem_high_fb = make_memory(importance=5, access_count=0,
                                   positive_feedback=10, negative_feedback=0)
        mem_neutral = make_memory(importance=5, access_count=0,
                                   positive_feedback=0, negative_feedback=0)

        adj_low = compute_importance_score(mem_low_fb) - compute_importance_score(mem_neutral)
        adj_high = compute_importance_score(mem_high_fb) - compute_importance_score(mem_neutral)

        # 低总反馈量的调整幅度应小于高总反馈量
        assert adj_low < adj_high, (
            f"cold start 时调整幅度 ({adj_low:.3f}) 应小于高信心时 ({adj_high:.3f})"
        )

    def test_feedback_formula_values(self):
        """验证具体的公式计算结果。

        importance=5, access_count=0, positive_feedback=8, negative_feedback=2
        base = 5/10 = 0.50
        recall_bonus = 0
        total_fb = 10, feedback_ratio = 0.8, confidence = min(1.0, 10/10) = 1.0
        feedback_adj = (0.8 - 0.5) * 1.0 * 0.4 = 0.12
        expected = 0.50 + 0 + 0.12 = 0.62
        """
        from retriever import compute_importance_score

        mem = make_memory(importance=5, access_count=0,
                          positive_feedback=8, negative_feedback=2)
        score = compute_importance_score(mem)
        assert abs(score - 0.62) < 0.001, f"预期 0.62，实际 {score:.4f}"

    def test_feedback_score_clamped_to_0_1(self):
        """评分应始终在 [0, 1] 范围内。"""
        from retriever import compute_importance_score

        # 极端情况：高 importance + 满 recall + 满 positive feedback
        mem_max = make_memory(importance=10, access_count=100,
                               positive_feedback=100, negative_feedback=0)
        # 极端情况：低 importance + 全 negative feedback
        mem_min = make_memory(importance=1, access_count=0,
                               positive_feedback=0, negative_feedback=100)

        score_max = compute_importance_score(mem_max)
        score_min = compute_importance_score(mem_min)

        assert 0.0 <= score_max <= 1.0, f"最大评分超出 [0,1]：{score_max}"
        assert 0.0 <= score_min <= 1.0, f"最小评分低于 [0,1]：{score_min}"


# ==================== Phase 1B: CLI feedback 命令 ====================

class TestCliFeedback:
    """测试 CLI feedback 子命令。"""

    def test_cli_feedback_positive(self):
        """cli feedback --memory-id xxx --useful → positive_feedback += 1。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="cli_fb_001", positive_feedback=0, negative_feedback=0)
            store.add(mem)

            # 调用 CLI
            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                ["python3", cli_path, "--store", tmp_dir,
                 "feedback", "--memory-id", "cli_fb_001", "--useful"],
                capture_output=True, text=True
            )
            assert result.returncode == 0, f"CLI 返回非零：{result.stderr}"

            # 验证字段更新
            updated = store.get("cli_fb_001")
            assert updated.positive_feedback == 1, (
                f"positive_feedback 应为 1，实际：{updated.positive_feedback}"
            )
            assert updated.negative_feedback == 0

        finally:
            shutil.rmtree(tmp_dir)

    def test_cli_feedback_negative(self):
        """cli feedback --memory-id xxx --not-useful → negative_feedback += 1。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="cli_fb_002", positive_feedback=0, negative_feedback=0)
            store.add(mem)

            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                ["python3", cli_path, "--store", tmp_dir,
                 "feedback", "--memory-id", "cli_fb_002", "--not-useful"],
                capture_output=True, text=True
            )
            assert result.returncode == 0, f"CLI 返回非零：{result.stderr}"

            updated = store.get("cli_fb_002")
            assert updated.negative_feedback == 1, (
                f"negative_feedback 应为 1，实际：{updated.negative_feedback}"
            )
            assert updated.positive_feedback == 0

        finally:
            shutil.rmtree(tmp_dir)

    def test_cli_feedback_accumulates(self):
        """多次调用 feedback，计数累积（不是覆盖）。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)
            mem = make_memory(id="cli_fb_003", positive_feedback=2, negative_feedback=1)
            store.add(mem)

            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            # 再加一个 positive
            subprocess.run(
                ["python3", cli_path, "--store", tmp_dir,
                 "feedback", "--memory-id", "cli_fb_003", "--useful"],
                capture_output=True, text=True
            )

            updated = store.get("cli_fb_003")
            assert updated.positive_feedback == 3, (
                f"累积后 positive_feedback 应为 3，实际：{updated.positive_feedback}"
            )
            assert updated.negative_feedback == 1  # 不变

        finally:
            shutil.rmtree(tmp_dir)

    def test_cli_feedback_nonexistent_memory(self):
        """对不存在的 memory_id 执行 feedback 应返回错误。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            cli_path = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'cli.py')
            result = subprocess.run(
                ["python3", cli_path, "--store", tmp_dir,
                 "feedback", "--memory-id", "nonexistent_id", "--useful"],
                capture_output=True, text=True
            )
            assert result.returncode != 0, "对不存在的记忆执行 feedback 应失败"
        finally:
            shutil.rmtree(tmp_dir)


# ==================== HIGH-1 集成测试：retrieve() 接入 compute_importance_score ====================

class TestRetrieveUsesImportanceScore:
    """集成测试：验证 retrieve() 主流程中 importance 维度受 feedback 影响。

    这是 HIGH-1 修复的验证测试：确保 retrieve() 调用 compute_importance_score
    而非旧版 compute_importance，使 feedback 字段真正影响检索排序。
    """

    def test_retrieve_favors_high_feedback_memory(self):
        """高 positive_feedback 的记忆在 retrieve() 结果中得分应高于无 feedback 同等记忆。

        设计：
        - mem_A: importance=5, positive_feedback=10, negative_feedback=0 → feedback_adj=+0.2
        - mem_B: importance=5, positive_feedback=0, negative_feedback=0  → feedback_adj=0
        - 两者 recency 和 relevance 相同
        - 若 retrieve() 接入了 compute_importance_score，mem_A 的 score 应高于 mem_B
        """
        from retriever import retrieve

        tmp_dir = tempfile.mkdtemp()
        try:
            store = MemoryStore(store_path=tmp_dir)

            now = datetime(2026, 3, 14, 12, 0, 0)
            ts = "2026-03-14T12:00:00"  # 与 now 相同，recency=1.0

            mem_a = Memory(
                id="feedback_high_001",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                timestamp=ts,
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                context="Python 调试工具使用",
                importance=5,
                positive_feedback=10,
                negative_feedback=0,
                access_count=0,
                last_accessed=ts,
            )
            mem_b = Memory(
                id="feedback_zero_002",
                content="Python 调试技巧：使用 print 语句输出调试信息",
                timestamp=ts,
                keywords=["Python", "调试", "print", "输出"],
                tags=["python", "debug"],
                context="Python 调试方法",
                importance=5,
                positive_feedback=0,
                negative_feedback=0,
                access_count=0,
                last_accessed=ts,
            )

            store.add(mem_a)
            store.add(mem_b)

            results = retrieve("Python 调试", store, top_k=2, spread=False, now=now)

            assert len(results) == 2, f"应返回 2 条结果，实际：{len(results)}"

            # 找到两条记忆的得分
            scores = {mem.id: score for mem, score in results}
            assert "feedback_high_001" in scores, "mem_A 应在结果中"
            assert "feedback_zero_002" in scores, "mem_B 应在结果中"

            score_a = scores["feedback_high_001"]
            score_b = scores["feedback_zero_002"]

            assert score_a > score_b, (
                f"高 feedback 记忆 ({score_a:.4f}) 得分应高于无 feedback 记忆 ({score_b:.4f})。"
                f"若相等，说明 retrieve() 仍在使用旧版 compute_importance（HIGH-1 未修复）。"
            )

        finally:
            shutil.rmtree(tmp_dir)

    def test_retrieve_penalizes_high_negative_feedback(self):
        """高 negative_feedback 的记忆在 retrieve() 结果中得分应低于无 feedback 同等记忆。

        设计：
        - 两条记忆内容和关键词完全相同（BM25 得分一致），仅 feedback 不同
        - mem_C: importance=5, positive_feedback=0, negative_feedback=10 → feedback_adj=-0.2
        - mem_D: importance=5, positive_feedback=0, negative_feedback=0  → feedback_adj=0
        - recency 相同（同一时间戳），relevance 理论上相同
        - importance 维度：mem_C = 0.3, mem_D = 0.5 → mem_C 总分应低
        """
        from retriever import compute_importance_score

        now = datetime(2026, 3, 14, 12, 0, 0)
        ts = "2026-03-14T12:00:00"

        # 直接比较 importance 维度得分，不依赖 BM25 relevance（避免关键词差异干扰）
        mem_c = Memory(
            id="negative_fb_003",
            content="测试记忆内容",
            timestamp=ts,
            keywords=["测试", "记忆"],
            tags=["test"],
            context="测试上下文",
            importance=5,
            positive_feedback=0,
            negative_feedback=10,
            access_count=0,
            last_accessed=ts,
        )
        mem_d = Memory(
            id="neutral_fb_004",
            content="测试记忆内容",
            timestamp=ts,
            keywords=["测试", "记忆"],
            tags=["test"],
            context="测试上下文",
            importance=5,
            positive_feedback=0,
            negative_feedback=0,
            access_count=0,
            last_accessed=ts,
        )

        # importance 维度：高负反馈 < 中性
        score_c = compute_importance_score(mem_c)
        score_d = compute_importance_score(mem_d)

        assert score_c < score_d, (
            f"高负反馈记忆 importance_score ({score_c:.4f}) 应低于中性记忆 ({score_d:.4f})。"
            f"若相等，说明 compute_importance_score 未正确处理 negative_feedback（HIGH-1 相关）。"
        )

        # 验证公式：importance=5, negative_feedback=10, confidence=1.0
        # feedback_adj = (0.0 - 0.5) * 1.0 * 0.4 = -0.2
        # score = 0.5 + 0 + (-0.2) = 0.3
        assert abs(score_c - 0.3) < 0.001, f"预期 0.30，实际 {score_c:.4f}"
        assert abs(score_d - 0.5) < 0.001, f"预期 0.50，实际 {score_d:.4f}"
