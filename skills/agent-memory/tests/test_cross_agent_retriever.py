"""R4-C 跨 Store 联合检索测试。

测试 retrieve_cross_agent() 函数和 CLI --cross-agent / --stores 选项。

测试清单：
1. test_single_store_same_as_regular    — 单 store 与普通 retrieve 结果一致
2. test_multi_store_merged              — 多 store 结果合并
3. test_dedup_same_id                   — 相同 ID 去重（取最高分）
4. test_score_ordering                  — 跨 store 按 score 降序排序
5. test_top_k_limit                     — 结果数量限制
6. test_empty_stores                    — 空 store 列表不报错
7. test_nonexistent_store_skipped       — 不存在的 store 路径跳过
8. test_source_annotation               — 结果标注来源 store
9. test_oversampling                    — 过采样保证充足候选
10. test_partial_empty_stores           — 部分 store 为空时正常返回其余结果
11. test_cli_cross_agent_flag           — CLI --cross-agent 选项
12. test_cli_stores_option              — CLI --stores 选项
"""

import os
import sys
import shutil
import subprocess
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from retriever import retrieve, retrieve_cross_agent

CLI_PATH = os.path.expanduser('~/.claude/skills/agent-memory/scripts/cli.py')


# ==================== 辅助函数 ====================

def _make_memory(mem_id: str, content: str, keywords: list[str],
                 importance: int = 5, timestamp: str = "2026-03-10T10:00:00") -> Memory:
    """构建测试记忆。"""
    return Memory(
        id=mem_id,
        content=content,
        timestamp=timestamp,
        keywords=keywords,
        tags=["test"],
        context=content[:50],
        importance=importance,
        related_ids=[],
        access_count=0,
        last_accessed=None,
    )


def _create_store(tmp_path: str, memories: list[Memory]) -> MemoryStore:
    """在 tmp_path 创建填充了记忆的 MemoryStore。"""
    store = MemoryStore(store_path=tmp_path)
    for m in memories:
        store.add(m)
    return store


def _run_cli(*args):
    """运行 cli.py，返回 (stdout, stderr, returncode)。"""
    cmd = [sys.executable, CLI_PATH] + list(args)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return proc.stdout, proc.stderr, proc.returncode


# ==================== 测试类 ====================

class TestCrossAgentRetriever:

    def test_single_store_same_as_regular(self):
        """单 store 与普通 retrieve 结果一致（score 可能有微小差异，但排序和 ID 应相同）。"""
        tmp_dir = tempfile.mkdtemp()
        try:
            memories = [
                _make_memory("mem_001", "LaTeX 编译错误修复", ["LaTeX", "编译", "错误"], importance=7),
                _make_memory("mem_002", "Python 调试技巧", ["Python", "调试", "技巧"], importance=5),
                _make_memory("mem_003", "Git 工作流规范", ["Git", "工作流", "规范"], importance=6),
            ]
            store = _create_store(tmp_dir, memories)
            now = datetime(2026, 3, 12, 10, 0, 0)

            # 普通检索
            regular_results = retrieve("LaTeX 编译", store, top_k=3, spread=False, now=now)
            # 跨 store 检索（单 store）
            cross_results = retrieve_cross_agent(
                "LaTeX 编译", [store], top_k=3, spread=False, now=now
            )

            regular_ids = [m.id for m, _ in regular_results]
            cross_ids = [m.id for m, _ in cross_results]

            assert regular_ids == cross_ids, \
                f"单 store 跨检索结果 ID 应与普通检索一致\n普通: {regular_ids}\n跨检索: {cross_ids}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_multi_store_merged(self):
        """多 store 结果合并：来自不同 store 的记忆都应出现在结果中。"""
        tmp_a = tempfile.mkdtemp()
        tmp_b = tempfile.mkdtemp()
        try:
            store_a = _create_store(tmp_a, [
                _make_memory("mem_a1", "LaTeX 字体配置", ["LaTeX", "字体", "fontspec"], importance=7),
            ])
            store_b = _create_store(tmp_b, [
                _make_memory("mem_b1", "LaTeX 编译脚本自动化", ["LaTeX", "编译", "脚本", "自动化"], importance=6),
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)

            results = retrieve_cross_agent("LaTeX", [store_a, store_b], top_k=5, spread=False, now=now)
            result_ids = {m.id for m, _ in results}

            assert "mem_a1" in result_ids, f"store_a 的记忆应出现在结果中，实际: {result_ids}"
            assert "mem_b1" in result_ids, f"store_b 的记忆应出现在结果中，实际: {result_ids}"
        finally:
            shutil.rmtree(tmp_a, ignore_errors=True)
            shutil.rmtree(tmp_b, ignore_errors=True)

    def test_dedup_same_id(self):
        """相同 ID 去重：若同一记忆出现在多个 store，只保留最高分（ID 只出现一次）。"""
        tmp_a = tempfile.mkdtemp()
        tmp_b = tempfile.mkdtemp()
        try:
            shared_mem = _make_memory("shared_001", "共享 LaTeX 规范", ["LaTeX", "规范", "共享"], importance=8)

            store_a = _create_store(tmp_a, [shared_mem])
            store_b = _create_store(tmp_b, [shared_mem])  # 同一条记忆也在 store_b
            now = datetime(2026, 3, 12, 10, 0, 0)

            results = retrieve_cross_agent("LaTeX 规范", [store_a, store_b], top_k=5, spread=False, now=now)
            result_ids = [m.id for m, _ in results]

            assert result_ids.count("shared_001") == 1, \
                f"相同 ID 应去重，只出现一次，实际: {result_ids}"
        finally:
            shutil.rmtree(tmp_a, ignore_errors=True)
            shutil.rmtree(tmp_b, ignore_errors=True)

    def test_score_ordering(self):
        """跨 store 结果按 score 降序排序。"""
        tmp_a = tempfile.mkdtemp()
        tmp_b = tempfile.mkdtemp()
        try:
            # store_a: 高重要性 LaTeX 记忆
            store_a = _create_store(tmp_a, [
                _make_memory("high_a", "LaTeX XeLaTeX 编译关键配置", ["LaTeX", "XeLaTeX", "编译", "配置"], importance=9),
            ])
            # store_b: 中等重要性记忆
            store_b = _create_store(tmp_b, [
                _make_memory("mid_b", "LaTeX 基础语法", ["LaTeX", "语法", "基础"], importance=4),
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)

            results = retrieve_cross_agent("LaTeX 编译", [store_a, store_b], top_k=5, spread=False, now=now)
            scores = [s for _, s in results]

            assert scores == sorted(scores, reverse=True), \
                f"结果应按 score 降序排列，实际分数: {scores}"
        finally:
            shutil.rmtree(tmp_a, ignore_errors=True)
            shutil.rmtree(tmp_b, ignore_errors=True)

    def test_top_k_limit(self):
        """结果数量不超过 top_k。"""
        tmp_a = tempfile.mkdtemp()
        tmp_b = tempfile.mkdtemp()
        try:
            store_a = _create_store(tmp_a, [
                _make_memory(f"a_{i}", f"LaTeX 记忆 {i}", ["LaTeX", f"主题{i}"], importance=5)
                for i in range(5)
            ])
            store_b = _create_store(tmp_b, [
                _make_memory(f"b_{i}", f"LaTeX 编译记忆 {i}", ["LaTeX", "编译", f"方法{i}"], importance=6)
                for i in range(5)
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)

            results = retrieve_cross_agent("LaTeX", [store_a, store_b], top_k=3, spread=False, now=now)

            assert len(results) <= 3, \
                f"结果数量应不超过 top_k=3，实际: {len(results)}"
        finally:
            shutil.rmtree(tmp_a, ignore_errors=True)
            shutil.rmtree(tmp_b, ignore_errors=True)

    def test_empty_stores(self):
        """空 store 列表不报错，返回空列表。"""
        results = retrieve_cross_agent("任意查询", [], top_k=5)
        assert results == [], f"空 stores 应返回空列表，实际: {results}"

    def test_nonexistent_store_skipped(self):
        """不存在的 store 路径（目录被删除后）应跳过，不报错。"""
        tmp_dir = tempfile.mkdtemp()
        tmp_gone = tempfile.mkdtemp()  # 先创建后删除，模拟"消失的"store
        try:
            real_store = _create_store(tmp_dir, [
                _make_memory("real_001", "LaTeX 真实记忆", ["LaTeX", "真实"], importance=7),
            ])
            # 先正常创建 store，然后删除其目录，使其"消失"
            gone_store = MemoryStore(store_path=tmp_gone)
            shutil.rmtree(tmp_gone, ignore_errors=True)  # 删除目录，模拟不存在

            now = datetime(2026, 3, 12, 10, 0, 0)

            # 不应抛出异常
            results = retrieve_cross_agent(
                "LaTeX", [real_store, gone_store], top_k=5, spread=False, now=now
            )

            # 真实 store 的记忆应正常返回
            result_ids = {m.id for m, _ in results}
            assert "real_001" in result_ids, \
                f"真实 store 的记忆应正常返回，实际: {result_ids}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            shutil.rmtree(tmp_gone, ignore_errors=True)

    def test_source_annotation(self):
        """结果应标注来源 store 名称（store_path 的最后一个目录名）。"""
        tmp_a = tempfile.mkdtemp(suffix="_store_a")
        tmp_b = tempfile.mkdtemp(suffix="_store_b")
        try:
            store_a = _create_store(tmp_a, [
                _make_memory("ann_a1", "LaTeX 来自 store_a", ["LaTeX", "store_a"], importance=7),
            ])
            store_b = _create_store(tmp_b, [
                _make_memory("ann_b1", "LaTeX 来自 store_b", ["LaTeX", "store_b"], importance=6),
            ])
            now = datetime(2026, 3, 12, 10, 0, 0)

            # retrieve_cross_agent 返回 (Memory, score, source_store_name) 三元组
            results = retrieve_cross_agent(
                "LaTeX", [store_a, store_b], top_k=5, spread=False, now=now,
                annotate_source=True
            )

            assert len(results) > 0, "应有检索结果"
            # 每条结果都是 (Memory, score, source) 三元组
            assert len(results[0]) == 3, \
                f"annotate_source=True 时，每条结果应为 (Memory, score, source) 三元组，实际: {results[0]}"

            sources = {item[2] for item in results}
            # 来源应包含 store 路径信息（非空字符串）
            for src in sources:
                assert isinstance(src, str) and len(src) > 0, \
                    f"来源标注应为非空字符串，实际: {src!r}"
        finally:
            shutil.rmtree(tmp_a, ignore_errors=True)
            shutil.rmtree(tmp_b, ignore_errors=True)

    def test_oversampling(self):
        """验证过采样机制：每个 store 采样 top_k*2 条，保证候选充足。"""
        tmp_a = tempfile.mkdtemp()
        tmp_b = tempfile.mkdtemp()
        try:
            # store_a: 10 条 LaTeX 记忆
            store_a = _create_store(tmp_a, [
                _make_memory(f"a_{i}", f"LaTeX 编译方法 {i}", ["LaTeX", "编译", f"方法{i}"],
                             importance=i % 10 + 1,
                             timestamp=f"2026-03-{10+i:02d}T10:00:00")
                for i in range(10)
            ])
            # store_b: 10 条 LaTeX 记忆
            store_b = _create_store(tmp_b, [
                _make_memory(f"b_{i}", f"LaTeX 配置技巧 {i}", ["LaTeX", "配置", f"技巧{i}"],
                             importance=i % 10 + 1,
                             timestamp=f"2026-03-{10+i:02d}T12:00:00")
                for i in range(10)
            ])
            now = datetime(2026, 3, 20, 10, 0, 0)

            # 要求 top_k=4，应能从 20 条候选中选出最优的 4 条
            results = retrieve_cross_agent("LaTeX 编译配置", [store_a, store_b], top_k=4, spread=False, now=now)

            assert len(results) == 4, \
                f"应恰好返回 top_k=4 条结果（两个 store 共 20 条），实际: {len(results)}"
        finally:
            shutil.rmtree(tmp_a, ignore_errors=True)
            shutil.rmtree(tmp_b, ignore_errors=True)

    def test_partial_empty_stores(self):
        """部分 store 为空时，正常返回其余 store 的结果。"""
        tmp_a = tempfile.mkdtemp()
        tmp_b = tempfile.mkdtemp()  # 空 store
        try:
            store_a = _create_store(tmp_a, [
                _make_memory("active_001", "Python 异步编程", ["Python", "异步", "asyncio"], importance=7),
            ])
            store_b_empty = MemoryStore(store_path=tmp_b)  # 无任何记忆
            now = datetime(2026, 3, 12, 10, 0, 0)

            results = retrieve_cross_agent(
                "Python 异步", [store_a, store_b_empty], top_k=5, spread=False, now=now
            )

            result_ids = {m.id for m, _ in results}
            assert "active_001" in result_ids, \
                f"store_a 的记忆应正常返回，实际: {result_ids}"
        finally:
            shutil.rmtree(tmp_a, ignore_errors=True)
            shutil.rmtree(tmp_b, ignore_errors=True)


# ==================== CLI 测试 ====================

class TestCrossAgentCLI:

    def test_cli_stores_option(self):
        """CLI --stores 选项：指定逗号分隔的 store 列表进行跨检索。"""
        tmp_a = tempfile.mkdtemp()
        tmp_b = tempfile.mkdtemp()
        try:
            # 在两个 store 中各添加一条记忆（通过 MemoryStore API）
            store_a = _create_store(tmp_a, [
                _make_memory("cli_a1", "LaTeX 编译 CLI 测试 store_a", ["LaTeX", "编译", "CLI"], importance=7),
            ])
            store_b = _create_store(tmp_b, [
                _make_memory("cli_b1", "LaTeX 字体 CLI 测试 store_b", ["LaTeX", "字体", "CLI"], importance=6),
            ])

            # 运行 CLI：--stores store_a_path,store_b_path
            stdout, stderr, rc = _run_cli(
                "--store", tmp_a,  # 主 store（--stores 会覆盖）
                "retrieve",
                "LaTeX",
                "--stores", f"{tmp_a},{tmp_b}",
                "--top-k", "5",
            )

            assert rc == 0, f"CLI --stores 应成功执行 (rc={rc}):\n{stderr}"
            assert len(stdout.strip()) > 0, f"CLI --stores 应有输出，实际为空"
        finally:
            shutil.rmtree(tmp_a, ignore_errors=True)
            shutil.rmtree(tmp_b, ignore_errors=True)

    def test_cli_cross_agent_flag(self):
        """CLI --cross-agent 选项：自动扫描 ~/mem/mem/agents/*/*/ 下所有 store。

        此测试只验证 CLI 不报错并返回结果（或"未找到"提示），不验证具体内容。
        """
        agents_base = Path(os.path.expanduser("~/mem/mem/agents"))

        stdout, stderr, rc = _run_cli(
            "retrieve",
            "LaTeX 编译",
            "--cross-agent",
            "--top-k", "3",
        )

        assert rc == 0, f"CLI --cross-agent 应成功执行 (rc={rc}):\n{stderr}"
        # 输出应为检索结果或"未找到"提示，不应有 traceback
        assert "Traceback" not in stderr, \
            f"CLI --cross-agent 不应有 Python 异常:\n{stderr}"


# ==================== 测试运行器 ====================

def run_tests():
    """顺序运行所有跨 Store 检索测试。"""
    test_classes = [TestCrossAgentRetriever, TestCrossAgentCLI]

    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("R4-C 跨 Store 联合检索测试")
    print("=" * 60)

    for cls in test_classes:
        instance = cls()
        for method_name in sorted(dir(instance)):
            if not method_name.startswith("test_"):
                continue
            label = f"{cls.__name__}.{method_name}"
            try:
                getattr(instance, method_name)()
                passed += 1
                print(f"  PASS  {label}")
            except Exception as exc:
                failed += 1
                errors.append((label, traceback.format_exc()))
                print(f"  FAIL  {label}: {exc}")

    print()
    print("=" * 60)
    print(f"结果: {passed} 通过 / {failed} 失败")
    print("=" * 60)

    if errors:
        print("\n详细错误信息:")
        for label, trace in errors:
            print(f"\n--- {label} ---")
            print(trace)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
