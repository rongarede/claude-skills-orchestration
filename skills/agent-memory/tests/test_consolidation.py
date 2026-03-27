"""Phase 2.1 记忆去重合并测试：Memory Consolidation。

TDD 流程：
1. RED:  先运行确认全部失败（consolidator.py 尚不存在）
2. GREEN: 实现 consolidator.py 让测试通过
3. REFACTOR: 清理

测试函数覆盖：
- find_similar_pairs: 相似对检出、阈值过滤、空列表
- merge_memories:     keywords/tags 并集、importance 取最大、content 取最长、
                      access_count/feedback 累加
- consolidate:        执行合并、dry_run 不修改、自定义阈值
"""

import os
import sys
import shutil
import tempfile

# ==================== 路径设置 ====================

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore

# consolidator 尚未实现 — 以下 import 在 RED 阶段必然 ImportError
from consolidator import find_similar_pairs, merge_memories, consolidate


# ==================== 辅助函数 ====================

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


def new_tmp_store():
    """创建隔离的临时 MemoryStore，返回 (tmp_dir_path, store)。"""
    tmp_dir = tempfile.mkdtemp()
    return tmp_dir, MemoryStore(store_path=tmp_dir)


# ==================== find_similar_pairs ====================

class TestFindSimilarPairs:
    """测试 find_similar_pairs 的相似对检出逻辑。"""

    def test_find_similar_pairs_above_threshold(self):
        """两条高度相似的记忆应被检出为相似对。

        内容相近、关键词重叠，BM25 相似度应超过默认阈值 0.85。
        """
        mem_a = make_memory(
            id="sim_a",
            content="Python 调试技巧：使用 pdb 设置断点调试代码",
            keywords=["Python", "调试", "pdb", "断点"],
            tags=["python", "debug"],
            context="Python 调试工具使用",
        )
        mem_b = make_memory(
            id="sim_b",
            content="Python 调试方法：利用 pdb 断点工具调试代码",
            keywords=["Python", "调试", "pdb", "断点"],
            tags=["python", "debug"],
            context="Python 调试方法 pdb",
        )

        pairs = find_similar_pairs([mem_a, mem_b], threshold=0.85)

        assert len(pairs) >= 1, "两条高度相似的记忆应被检出为至少 1 对"
        # 每个元素应为 (Memory, Memory, float) 三元组
        pair = pairs[0]
        assert len(pair) == 3, f"相似对应为三元组 (mem, mem, score)，实际长度 {len(pair)}"
        m1, m2, score = pair
        assert isinstance(m1, Memory), "第一个元素应为 Memory 实例"
        assert isinstance(m2, Memory), "第二个元素应为 Memory 实例"
        assert isinstance(score, float), f"相似度分数应为 float，实际 {type(score)}"
        assert 0.0 <= score <= 1.0, f"相似度分数应在 [0, 1]，实际 {score}"
        # 两条记忆的 id 应在对中
        ids_in_pair = {m1.id, m2.id}
        assert ids_in_pair == {"sim_a", "sim_b"}, f"对中应包含 sim_a 和 sim_b，实际 {ids_in_pair}"

    def test_find_similar_pairs_below_threshold(self):
        """内容差异明显的两条记忆不应被检出为相似对。"""
        mem_a = make_memory(
            id="diff_a",
            content="Python 调试技巧：使用 pdb 设置断点调试代码",
            keywords=["Python", "调试", "pdb"],
            tags=["python"],
            context="Python 调试",
        )
        mem_b = make_memory(
            id="diff_b",
            content="区块链共识算法：工作量证明与权益证明的优缺点对比",
            keywords=["区块链", "共识算法", "工作量证明"],
            tags=["blockchain"],
            context="区块链技术",
        )

        pairs = find_similar_pairs([mem_a, mem_b], threshold=0.85)

        assert len(pairs) == 0, (
            f"内容差异明显的记忆不应被检出为相似对，实际检出 {len(pairs)} 对"
        )

    def test_find_similar_pairs_empty_list(self):
        """空列表输入应返回空列表，不抛异常。"""
        pairs = find_similar_pairs([], threshold=0.85)

        assert pairs == [], f"空列表应返回 []，实际 {pairs}"

    def test_find_similar_pairs_single_memory(self):
        """单条记忆无法配对，应返回空列表。"""
        mem = make_memory(id="solo", content="单条记忆内容")
        pairs = find_similar_pairs([mem], threshold=0.85)

        assert pairs == [], f"单条记忆应返回空列表，实际 {pairs}"


# ==================== merge_memories ====================

class TestMergeMemories:
    """测试 merge_memories 的合并字段策略。"""

    def test_merge_keywords_union(self):
        """合并后 keywords 应为两条记忆 keywords 的并集。"""
        primary = make_memory(
            id="primary_kw",
            keywords=["Python", "调试", "pdb"],
            importance=7,
        )
        duplicate = make_memory(
            id="dup_kw",
            keywords=["Python", "调试", "断点", "trace"],
            importance=5,
        )

        merged = merge_memories(primary, duplicate)

        merged_kw_set = set(merged.keywords)
        expected_union = {"Python", "调试", "pdb", "断点", "trace"}
        assert expected_union == merged_kw_set, (
            f"合并后 keywords 应为并集 {expected_union}，实际 {merged_kw_set}"
        )

    def test_merge_tags_union(self):
        """合并后 tags 应为两条记忆 tags 的并集。"""
        primary = make_memory(
            id="primary_tags",
            tags=["python", "debug"],
            importance=7,
        )
        duplicate = make_memory(
            id="dup_tags",
            tags=["python", "trace", "tools"],
            importance=5,
        )

        merged = merge_memories(primary, duplicate)

        merged_tags_set = set(merged.tags)
        expected_union = {"python", "debug", "trace", "tools"}
        assert expected_union == merged_tags_set, (
            f"合并后 tags 应为并集 {expected_union}，实际 {merged_tags_set}"
        )

    def test_merge_importance_max(self):
        """合并后 importance 应取两者中的较高值。"""
        primary = make_memory(id="primary_imp", importance=6)
        duplicate = make_memory(id="dup_imp", importance=9)

        merged = merge_memories(primary, duplicate)

        assert merged.importance == 9, (
            f"合并后 importance 应取较高值 9，实际 {merged.importance}"
        )

    def test_merge_importance_max_primary_higher(self):
        """primary importance 更高时，合并后仍取较高值。"""
        primary = make_memory(id="primary_imp2", importance=8)
        duplicate = make_memory(id="dup_imp2", importance=4)

        merged = merge_memories(primary, duplicate)

        assert merged.importance == 8, (
            f"合并后 importance 应取较高值 8，实际 {merged.importance}"
        )

    def test_merge_content_longest(self):
        """合并后 content 应保留两者中较长的内容。"""
        short_content = "Python 调试"
        long_content = "Python 调试技巧：使用 pdb 设置断点，可以逐行追踪代码执行流程，是排查复杂逻辑 bug 的利器"
        primary = make_memory(id="primary_content", content=short_content, importance=7)
        duplicate = make_memory(id="dup_content", content=long_content, importance=5)

        merged = merge_memories(primary, duplicate)

        assert merged.content == long_content, (
            f"合并后 content 应保留较长者，实际 '{merged.content[:30]}...'"
        )

    def test_merge_content_longest_primary_longer(self):
        """primary content 更长时，合并后保留 primary content。"""
        long_content = "Python 调试技巧：使用 pdb 设置断点，可以逐行追踪代码执行流程，是排查复杂逻辑 bug 的利器"
        short_content = "pdb 断点调试"
        primary = make_memory(id="primary_content2", content=long_content, importance=7)
        duplicate = make_memory(id="dup_content2", content=short_content, importance=5)

        merged = merge_memories(primary, duplicate)

        assert merged.content == long_content, (
            f"primary content 更长时，合并后应保留 primary content"
        )

    def test_merge_access_count_sum(self):
        """合并后 access_count 应为两者的累加值。"""
        primary = make_memory(id="primary_ac", access_count=3, importance=7)
        duplicate = make_memory(id="dup_ac", access_count=5, importance=5)

        merged = merge_memories(primary, duplicate)

        assert merged.access_count == 8, (
            f"合并后 access_count 应为 3+5=8，实际 {merged.access_count}"
        )

    def test_merge_feedback_sum(self):
        """合并后 positive_feedback 和 negative_feedback 均应累加。"""
        primary = make_memory(
            id="primary_fb",
            positive_feedback=4,
            negative_feedback=1,
            importance=7,
        )
        duplicate = make_memory(
            id="dup_fb",
            positive_feedback=3,
            negative_feedback=2,
            importance=5,
        )

        merged = merge_memories(primary, duplicate)

        assert merged.positive_feedback == 7, (
            f"合并后 positive_feedback 应为 4+3=7，实际 {merged.positive_feedback}"
        )
        assert merged.negative_feedback == 3, (
            f"合并后 negative_feedback 应为 1+2=3，实际 {merged.negative_feedback}"
        )

    def test_merge_primary_is_higher_importance(self):
        """合并后的主记录 id 应来自 importance 较高的一方（primary 参数）。

        merge_memories 的调用约定：primary 是重要性较高方。
        返回的 Memory id 应与 primary 一致。
        """
        primary = make_memory(id="primary_id", importance=8)
        duplicate = make_memory(id="dup_id", importance=3)

        merged = merge_memories(primary, duplicate)

        assert merged.id == "primary_id", (
            f"合并后 id 应为 primary 的 id，实际 {merged.id}"
        )

    def test_merge_related_ids_union(self):
        """合并后 related_ids 应为两者的并集（去重）。"""
        primary = make_memory(id="primary_rid", importance=7)
        primary.related_ids = ["mem_a", "mem_b"]
        duplicate = make_memory(id="dup_rid", importance=5)
        duplicate.related_ids = ["mem_b", "mem_c"]

        merged = merge_memories(primary, duplicate)

        merged_rids = set(merged.related_ids)
        expected = {"mem_a", "mem_b", "mem_c"}
        # 合并后的记忆自身 id 不应出现在 related_ids 中
        assert expected == merged_rids or expected.issubset(merged_rids), (
            f"合并后 related_ids 应包含并集 {expected}，实际 {merged_rids}"
        )


# ==================== consolidate ====================

class TestConsolidate:
    """测试 consolidate 函数的完整合并流程。"""

    def test_consolidate_merges_similar(self):
        """consolidate 执行后相似记忆应合并为一条，store 中数量减少。

        两条高度相似记忆 → consolidate → store 中只剩 1 条，返回 merged=1, deleted=1。
        """
        tmp_dir, store = new_tmp_store()
        try:
            mem_a = make_memory(
                id="cons_a",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=7,
            )
            mem_b = make_memory(
                id="cons_b",
                content="Python 调试方法：利用 pdb 断点工具调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=5,
            )
            store.add(mem_a)
            store.add(mem_b)

            result = consolidate(store, threshold=0.85, dry_run=False)

            assert isinstance(result, dict), f"consolidate 应返回 dict，实际 {type(result)}"
            assert "merged" in result, "返回 dict 中应包含 'merged' 键"
            assert "deleted" in result, "返回 dict 中应包含 'deleted' 键"
            assert "pairs" in result, "返回 dict 中应包含 'pairs' 键"

            assert result["merged"] >= 1, (
                f"相似记忆应被合并，merged 应 ≥ 1，实际 {result['merged']}"
            )
            assert result["deleted"] >= 1, (
                f"重复记忆应被删除，deleted 应 ≥ 1，实际 {result['deleted']}"
            )

            # store 中的记忆数量应减少
            remaining = store.count()
            assert remaining == 1, (
                f"合并后 store 中应只剩 1 条记忆，实际 {remaining}"
            )

        finally:
            shutil.rmtree(tmp_dir)

    def test_consolidate_dry_run(self):
        """dry_run=True 时不修改 store，仅返回将要合并的预览信息。"""
        tmp_dir, store = new_tmp_store()
        try:
            mem_a = make_memory(
                id="dry_a",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=7,
            )
            mem_b = make_memory(
                id="dry_b",
                content="Python 调试方法：利用 pdb 断点工具调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=5,
            )
            store.add(mem_a)
            store.add(mem_b)

            count_before = store.count()
            result = consolidate(store, threshold=0.85, dry_run=True)

            # dry_run 不修改 store
            count_after = store.count()
            assert count_after == count_before, (
                f"dry_run=True 时 store 不应被修改，操作前 {count_before} 条，操作后 {count_after} 条"
            )

            # 但仍应返回预览信息
            assert isinstance(result, dict), "dry_run 也应返回结果 dict"
            assert "pairs" in result, "dry_run 结果中应包含 'pairs' 预览"

        finally:
            shutil.rmtree(tmp_dir)

    def test_consolidate_custom_threshold(self):
        """自定义低阈值（0.3）应检出更多对，自定义高阈值（0.99）应检出更少对。"""
        tmp_dir_low, store_low = new_tmp_store()
        tmp_dir_high, store_high = new_tmp_store()
        try:
            # 中等相似度的两条记忆
            mem_a = make_memory(
                id="thr_a",
                content="Python 调试工具 pdb 的使用方法",
                keywords=["Python", "pdb", "调试"],
                tags=["python"],
                importance=5,
            )
            mem_b = make_memory(
                id="thr_b",
                content="Python 代码调试和 pdb 断点技巧",
                keywords=["Python", "pdb", "断点"],
                tags=["python"],
                importance=5,
            )

            store_low.add(make_memory(id="thr_a", content=mem_a.content,
                                      keywords=mem_a.keywords, tags=mem_a.tags))
            store_low.add(make_memory(id="thr_b", content=mem_b.content,
                                      keywords=mem_b.keywords, tags=mem_b.tags))

            store_high.add(make_memory(id="thr_a", content=mem_a.content,
                                       keywords=mem_a.keywords, tags=mem_a.tags))
            store_high.add(make_memory(id="thr_b", content=mem_b.content,
                                       keywords=mem_b.keywords, tags=mem_b.tags))

            result_low = consolidate(store_low, threshold=0.3, dry_run=True)
            result_high = consolidate(store_high, threshold=0.99, dry_run=True)

            # 低阈值检出的对数 ≥ 高阈值检出的对数
            pairs_low = len(result_low.get("pairs", []))
            pairs_high = len(result_high.get("pairs", []))
            assert pairs_low >= pairs_high, (
                f"低阈值(0.3)应检出更多或相等的对数 ({pairs_low}) vs 高阈值(0.99) ({pairs_high})"
            )

        finally:
            shutil.rmtree(tmp_dir_low)
            shutil.rmtree(tmp_dir_high)

    def test_consolidate_no_similar_memories(self):
        """完全不相似的记忆不应触发合并。"""
        tmp_dir, store = new_tmp_store()
        try:
            mem_a = make_memory(
                id="nosim_a",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                keywords=["Python", "pdb", "调试"],
                tags=["python"],
            )
            mem_b = make_memory(
                id="nosim_b",
                content="区块链共识算法：工作量证明与权益证明的机制对比",
                keywords=["区块链", "共识算法", "工作量证明"],
                tags=["blockchain"],
            )
            store.add(mem_a)
            store.add(mem_b)

            result = consolidate(store, threshold=0.85, dry_run=False)

            assert result["merged"] == 0, (
                f"完全不相似的记忆不应被合并，merged={result['merged']}"
            )
            assert result["deleted"] == 0, (
                f"不相似时不应有删除，deleted={result['deleted']}"
            )
            assert store.count() == 2, (
                f"无合并时 store 应仍有 2 条记忆，实际 {store.count()}"
            )

        finally:
            shutil.rmtree(tmp_dir)

    def test_consolidate_empty_store(self):
        """空 store 调用 consolidate 应返回 merged=0, deleted=0，不抛异常。"""
        tmp_dir, store = new_tmp_store()
        try:
            result = consolidate(store, threshold=0.85, dry_run=False)

            assert result["merged"] == 0, f"空 store 应 merged=0，实际 {result['merged']}"
            assert result["deleted"] == 0, f"空 store 应 deleted=0，实际 {result['deleted']}"
            assert result["pairs"] == [], f"空 store 应 pairs=[]，实际 {result['pairs']}"

        finally:
            shutil.rmtree(tmp_dir)

    def test_consolidate_result_pairs_structure(self):
        """consolidate 返回的 pairs 列表中，每个元素应包含被合并记忆的信息。"""
        tmp_dir, store = new_tmp_store()
        try:
            mem_a = make_memory(
                id="pair_a",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                importance=7,
            )
            mem_b = make_memory(
                id="pair_b",
                content="Python 调试方法：利用 pdb 断点工具调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                importance=5,
            )
            store.add(mem_a)
            store.add(mem_b)

            result = consolidate(store, threshold=0.85, dry_run=True)

            if len(result.get("pairs", [])) > 0:
                pair_item = result["pairs"][0]
                # pair_item 应包含两个记忆 id 和相似度分数
                assert len(pair_item) >= 2, (
                    f"pairs 中每项应包含至少 2 个元素（两个记忆的 id 或 Memory 对象），实际 {len(pair_item)}"
                )

        finally:
            shutil.rmtree(tmp_dir)


# ==================== TestConsolidationHealthIntegration ====================

class TestConsolidationHealthIntegration:
    """测试合并与健康状态的联动"""

    def test_blocked_memories_excluded_from_consolidation(self):
        """blocked 记忆不参与合并。

        blocked 条件：negative_feedback >= 5 且 ratio <= 0.2（positive=0）
        即使两条记忆高度相似，只要有一条是 blocked 就不应出现在合并对中。
        """
        tmp_dir, store = new_tmp_store()
        try:
            # mem_a: blocked (negative=5, positive=0 → ratio=0.0, neg>=5)
            mem_blocked = make_memory(
                id="blocked_mem",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=7,
                positive_feedback=0,
                negative_feedback=5,
            )
            # mem_b: healthy，与 mem_a 高度相似
            mem_healthy = make_memory(
                id="healthy_mem",
                content="Python 调试方法：利用 pdb 断点工具调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=5,
                positive_feedback=0,
                negative_feedback=0,
            )
            store.add(mem_blocked)
            store.add(mem_healthy)

            result = consolidate(store, threshold=0.85, dry_run=True)

            # blocked 记忆不参与合并，pairs 中不应包含 blocked_mem
            pairs = result.get("pairs", [])
            blocked_in_pairs = any(
                "blocked_mem" in (p[0], p[1]) for p in pairs
            )
            assert not blocked_in_pairs, (
                f"blocked 记忆不应出现在合并对中，实际 pairs={pairs}"
            )

        finally:
            shutil.rmtree(tmp_dir)

    def test_warning_memory_not_primary(self):
        """warning 记忆不能作为主记忆（合并目标）。

        当两条记忆都是 warning 时，不应发生合并。
        当 warning + healthy 合并时，healthy 应做主（见 test_mixed_health_consolidation）。
        """
        tmp_dir, store = new_tmp_store()
        try:
            # mem_a: warning (negative=3, positive=0 → ratio=0.0, neg>=3)
            mem_warning_a = make_memory(
                id="warning_a",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=7,
                positive_feedback=0,
                negative_feedback=3,
            )
            # mem_b: warning
            mem_warning_b = make_memory(
                id="warning_b",
                content="Python 调试方法：利用 pdb 断点工具调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=5,
                positive_feedback=0,
                negative_feedback=3,
            )
            store.add(mem_warning_a)
            store.add(mem_warning_b)

            # 两条都是 warning，不应合并
            result = consolidate(store, threshold=0.85, dry_run=False)

            assert result["merged"] == 0, (
                f"两条 warning 记忆不应被合并，merged={result['merged']}"
            )
            assert store.count() == 2, (
                f"两条 warning 记忆不应被删除，store 应仍有 2 条，实际 {store.count()}"
            )

        finally:
            shutil.rmtree(tmp_dir)

    def test_healthy_memories_consolidate_normally(self):
        """healthy 记忆正常合并（向后兼容）。

        两条 healthy 记忆高度相似 → 应正常触发合并，merged=1。
        """
        tmp_dir, store = new_tmp_store()
        try:
            mem_a = make_memory(
                id="healthy_a",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=7,
                positive_feedback=0,
                negative_feedback=0,
            )
            mem_b = make_memory(
                id="healthy_b",
                content="Python 调试方法：利用 pdb 断点工具调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=5,
                positive_feedback=0,
                negative_feedback=0,
            )
            store.add(mem_a)
            store.add(mem_b)

            result = consolidate(store, threshold=0.85, dry_run=False)

            assert result["merged"] >= 1, (
                f"两条 healthy 记忆应正常合并，merged={result['merged']}"
            )
            assert store.count() == 1, (
                f"合并后 store 应只剩 1 条记忆，实际 {store.count()}"
            )

        finally:
            shutil.rmtree(tmp_dir)

    def test_mixed_health_consolidation(self):
        """混合健康状态：healthy + warning 可以合并，healthy 为主。

        mem_a (healthy, importance=5) + mem_b (warning, importance=7)
        → 合并时 mem_a 应做主（healthy 优先），即使 importance 更低。
        """
        tmp_dir, store = new_tmp_store()
        try:
            # mem_a: healthy（importance 较低）
            mem_healthy = make_memory(
                id="mixed_healthy",
                content="Python 调试技巧：使用 pdb 设置断点调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=5,
                positive_feedback=0,
                negative_feedback=0,
            )
            # mem_b: warning（importance 较高，但健康状态差）
            mem_warning = make_memory(
                id="mixed_warning",
                content="Python 调试方法：利用 pdb 断点工具调试代码",
                keywords=["Python", "调试", "pdb", "断点"],
                tags=["python", "debug"],
                importance=7,
                positive_feedback=0,
                negative_feedback=3,
            )
            store.add(mem_healthy)
            store.add(mem_warning)

            result = consolidate(store, threshold=0.85, dry_run=False)

            # 合并应发生
            assert result["merged"] >= 1, (
                f"healthy + warning 应触发合并，merged={result['merged']}"
            )
            assert store.count() == 1, (
                f"合并后 store 应只剩 1 条记忆，实际 {store.count()}"
            )

            # 保留下来的记忆 id 应该是 healthy 的（mixed_healthy）
            remaining = store.load_all()
            assert len(remaining) == 1
            assert remaining[0].id == "mixed_healthy", (
                f"合并后应保留 healthy 记忆（mixed_healthy）为主，"
                f"实际保留 id={remaining[0].id}"
            )

        finally:
            shutil.rmtree(tmp_dir)
