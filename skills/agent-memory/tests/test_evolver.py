"""邻居演化引擎单元测试。

测试场景:
1. TestShouldEvolve       — should_evolve() 函数各分支
2. TestGenerateEvolutionPlan — generate_evolution_plan() 函数各分支
3. TestExecuteEvolution   — execute_evolution() 函数各分支
4. TestEvolveNeighborsIntegration — evolve_neighbors() 完整流程
"""

import os
import sys
import json
import tempfile
import traceback
from datetime import datetime
from unittest.mock import patch, MagicMock, call

# 将 scripts 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
import evolver
from evolver import (
    should_evolve,
    generate_evolution_plan,
    execute_evolution,
    evolve_neighbors,
)


# ==================== 辅助函数 ====================

def _new_tmp_store():
    """创建隔离的临时 JSONL 文件，返回 (path, store)。"""
    tmp = tempfile.NamedTemporaryFile(suffix='.jsonl', delete=False)
    tmp.close()
    return tmp.name, MemoryStore(tmp.name)


def _make_memory(mem_id, content, keywords, tags=None, context="", importance=5):
    """快速构造 Memory 对象。"""
    return Memory(
        id=mem_id,
        content=content,
        timestamp=datetime.now().isoformat(),
        keywords=keywords,
        tags=tags or [],
        context=context,
        importance=importance,
    )


def _make_mock_client(response_text):
    """构造返回指定 JSON 文本的 mock client。"""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=response_text)]
    mock_client.messages.create.return_value = mock_response
    return mock_client


# ==================== 场景 1: TestShouldEvolve ====================

class TestShouldEvolve:
    """should_evolve() 函数各分支测试。"""

    def test_should_evolve_true(self):
        """新记忆包含邻居没有的解决方案 → should_evolve=True"""
        new_memory = _make_memory(
            "mem_new_001",
            "LaTeX 字体问题已解决：运行 fc-cache -fv 刷新字体缓存",
            keywords=["LaTeX", "字体", "fc-cache", "解决方案"],
            context="fc-cache -fv 解决 LaTeX 字体缺失问题",
        )
        neighbor = _make_memory(
            "mem_neighbor_001",
            "LaTeX fontspec 找不到字体",
            keywords=["LaTeX", "fontspec", "字体", "编译失败"],
            context="LaTeX fontspec 找不到系统字体",
        )

        mock_client = _make_mock_client(
            json.dumps({"should_evolve": True, "reason": "新记忆包含解决方案"})
        )

        with patch.object(evolver, 'get_client', return_value=mock_client):
            result, reason = should_evolve(new_memory, [neighbor])

        assert result is True, f"应返回 True，实际 {result}"
        assert "解决方案" in reason, f"reason 中应包含'解决方案'，实际 '{reason}'"

    def test_should_evolve_false(self):
        """新记忆没有新信息 → should_evolve=False"""
        new_memory = _make_memory(
            "mem_new_002",
            "LaTeX fontspec 配置记录",
            keywords=["LaTeX", "fontspec", "配置"],
            context="fontspec 配置说明",
        )
        neighbor = _make_memory(
            "mem_neighbor_002",
            "LaTeX fontspec 详细配置指南",
            keywords=["LaTeX", "fontspec", "配置", "字体安装"],
            context="fontspec 完整配置已记录",
        )

        mock_client = _make_mock_client(
            json.dumps({"should_evolve": False, "reason": "信息已包含"})
        )

        with patch.object(evolver, 'get_client', return_value=mock_client):
            result, reason = should_evolve(new_memory, [neighbor])

        assert result is False, f"应返回 False，实际 {result}"
        assert "信息已包含" in reason, f"reason 应为'信息已包含'，实际 '{reason}'"

    def test_should_evolve_no_neighbors(self):
        """没有邻居 → 直接返回 False，不调用 API"""
        new_memory = _make_memory(
            "mem_new_003",
            "某项任务内容",
            keywords=["任务", "内容"],
        )

        mock_client = MagicMock()

        with patch.object(evolver, 'get_client', return_value=mock_client):
            result, reason = should_evolve(new_memory, [])

        assert result is False, f"无邻居时应返回 False，实际 {result}"
        assert reason == "no neighbors", f"reason 应为 'no neighbors'，实际 '{reason}'"
        mock_client.messages.create.assert_not_called()

    def test_should_evolve_api_error(self):
        """API 调用失败 → 静默返回 False，reason 以 'error:' 开头"""
        new_memory = _make_memory(
            "mem_new_004",
            "某项任务内容",
            keywords=["任务", "内容"],
        )
        neighbor = _make_memory(
            "mem_neighbor_004",
            "相关邻居记忆",
            keywords=["邻居", "记忆"],
        )

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API 超时")

        with patch.object(evolver, 'get_client', return_value=mock_client):
            result, reason = should_evolve(new_memory, [neighbor])

        assert result is False, f"API 失败时应返回 False，实际 {result}"
        assert reason.startswith("error:"), f"reason 应以 'error:' 开头，实际 '{reason}'"


# ==================== 场景 2: TestGenerateEvolutionPlan ====================

class TestGenerateEvolutionPlan:
    """generate_evolution_plan() 函数各分支测试。"""

    def test_generate_plan(self):
        """正常生成演化指令"""
        new_memory = _make_memory(
            "mem_new_010",
            "LaTeX 字体问题已解决：fc-cache -fv",
            keywords=["LaTeX", "字体", "fc-cache", "解决方案"],
            context="fc-cache -fv 解决 LaTeX 字体缺失问题",
        )
        neighbor = _make_memory(
            "mem_001",
            "LaTeX fontspec 找不到字体",
            keywords=["LaTeX", "fontspec", "字体"],
            context="LaTeX fontspec 找不到系统字体",
        )

        plan_response = {
            "updates": [
                {
                    "neighbor_id": "mem_001",
                    "new_context": "LaTeX fontspec 找不到系统字体；解决方案：fc-cache -fv",
                    "add_tags": ["solved"],
                    "add_keywords": ["fc-cache"],
                }
            ]
        }
        mock_client = _make_mock_client(json.dumps(plan_response))

        with patch.object(evolver, 'get_client', return_value=mock_client):
            updates = generate_evolution_plan(new_memory, [neighbor])

        assert len(updates) == 1, f"应返回 1 条指令，实际 {len(updates)}"
        u = updates[0]
        assert u["neighbor_id"] == "mem_001", f"neighbor_id 不符，实际 {u['neighbor_id']}"
        assert "new_context" in u, "update 中应有 new_context 字段"
        assert "add_tags" in u, "update 中应有 add_tags 字段"
        assert "add_keywords" in u, "update 中应有 add_keywords 字段"

    def test_generate_plan_max_3(self):
        """限制最多 3 条指令"""
        new_memory = _make_memory(
            "mem_new_011",
            "某项大型任务",
            keywords=["任务"],
        )
        neighbors = [
            _make_memory(f"mem_{i:03d}", f"邻居记忆 {i}", keywords=["邻居"])
            for i in range(5)
        ]

        # 模拟 API 返回 5 条 updates
        five_updates = [
            {"neighbor_id": f"mem_{i:03d}", "new_context": f"更新上下文 {i}", "add_tags": [], "add_keywords": []}
            for i in range(5)
        ]
        mock_client = _make_mock_client(json.dumps({"updates": five_updates}))

        with patch.object(evolver, 'get_client', return_value=mock_client):
            updates = generate_evolution_plan(new_memory, neighbors)

        assert len(updates) == 3, f"最多返回 3 条指令，实际 {len(updates)}"
        # 验证是前 3 条（按顺序截断）
        for i in range(3):
            assert updates[i]["neighbor_id"] == f"mem_{i:03d}", \
                f"第 {i} 条 neighbor_id 应为 mem_{i:03d}，实际 {updates[i]['neighbor_id']}"

    def test_generate_plan_api_error(self):
        """API 失败 → 返回空列表"""
        new_memory = _make_memory(
            "mem_new_012",
            "某项任务",
            keywords=["任务"],
        )
        neighbor = _make_memory(
            "mem_neighbor_012",
            "邻居记忆",
            keywords=["邻居"],
        )

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("网络错误")

        with patch.object(evolver, 'get_client', return_value=mock_client):
            updates = generate_evolution_plan(new_memory, [neighbor])

        assert updates == [], f"API 失败时应返回空列表，实际 {updates}"


# ==================== 场景 3: TestExecuteEvolution ====================

class TestExecuteEvolution:
    """execute_evolution() 函数各分支测试。"""

    def test_execute_updates_fields(self):
        """执行更新：context, tags, keywords 全部正确更新"""
        store_path, store = _new_tmp_store()

        try:
            neighbor = _make_memory(
                "mem_exec_001",
                "LaTeX fontspec 找不到字体",
                keywords=["LaTeX", "fontspec", "字体"],
                tags=["bug"],
                context="LaTeX fontspec 找不到系统字体",
            )
            store.add(neighbor)

            plan = [
                {
                    "neighbor_id": "mem_exec_001",
                    "new_context": "LaTeX fontspec 找不到字体；解决方案：fc-cache -fv",
                    "add_tags": ["solved"],
                    "add_keywords": ["fc-cache", "解决方案"],
                }
            ]

            updated_ids = execute_evolution(plan, store, triggered_by_id="mem_trigger_001")

            assert "mem_exec_001" in updated_ids, \
                f"mem_exec_001 应在更新列表中，实际 {updated_ids}"

            # 从 store 重新加载，验证字段
            reloaded = store.get("mem_exec_001")
            assert reloaded is not None, "更新后记忆应仍存在"
            assert reloaded.context == "LaTeX fontspec 找不到字体；解决方案：fc-cache -fv", \
                f"context 未正确更新，实际 '{reloaded.context}'"
            assert "solved" in reloaded.tags, f"tags 中应包含 'solved'，实际 {reloaded.tags}"
            assert "fc-cache" in reloaded.keywords, \
                f"keywords 中应包含 'fc-cache'，实际 {reloaded.keywords}"
            assert "解决方案" in reloaded.keywords, \
                f"keywords 中应包含 '解决方案'，实际 {reloaded.keywords}"

        finally:
            os.unlink(store_path)

    def test_execute_records_history(self):
        """记录 evolution_history：timestamp, triggered_by, changes 齐全"""
        store_path, store = _new_tmp_store()

        try:
            neighbor = _make_memory(
                "mem_exec_002",
                "某项初始记忆",
                keywords=["初始"],
                context="初始上下文",
            )
            store.add(neighbor)

            plan = [
                {
                    "neighbor_id": "mem_exec_002",
                    "new_context": "演化后的上下文",
                    "add_tags": [],
                    "add_keywords": [],
                }
            ]

            execute_evolution(plan, store, triggered_by_id="mem_trigger_002")

            reloaded = store.get("mem_exec_002")
            assert len(reloaded.evolution_history) == 1, \
                f"应有 1 条演化历史，实际 {len(reloaded.evolution_history)}"

            entry = reloaded.evolution_history[0]
            assert "timestamp" in entry, "历史记录中应有 timestamp 字段"
            assert entry["triggered_by"] == "mem_trigger_002", \
                f"triggered_by 应为 'mem_trigger_002'，实际 {entry['triggered_by']}"
            assert "changes" in entry, "历史记录中应有 changes 字段"
            assert "context" in entry["changes"], "changes 中应有 context 字段"
            assert entry["changes"]["context"]["old"] == "初始上下文", \
                f"changes.context.old 应为 '初始上下文'，实际 {entry['changes']['context']['old']}"
            assert entry["changes"]["context"]["new"] == "演化后的上下文", \
                f"changes.context.new 应为 '演化后的上下文'，实际 {entry['changes']['context']['new']}"

        finally:
            os.unlink(store_path)

    def test_execute_history_truncation(self):
        """evolution_history 超过 10 条时截断，保留最新 10 条"""
        store_path, store = _new_tmp_store()

        try:
            # 构造已有 10 条历史的记忆
            existing_history = [
                {
                    "timestamp": f"2026-03-0{i}T10:00:00",
                    "triggered_by": f"mem_old_{i:03d}",
                    "changes": {"context": {"old": f"旧上下文 {i}", "new": f"新上下文 {i}"}},
                }
                for i in range(1, 11)
            ]
            neighbor = Memory(
                id="mem_exec_003",
                content="某项记忆",
                timestamp=datetime.now().isoformat(),
                keywords=["记忆"],
                tags=[],
                context="当前上下文",
                importance=5,
                evolution_history=existing_history,
            )
            store.add(neighbor)

            # 再执行一次演化（第 11 条）
            plan = [
                {
                    "neighbor_id": "mem_exec_003",
                    "new_context": "第 11 次演化后的上下文",
                    "add_tags": [],
                    "add_keywords": [],
                }
            ]

            execute_evolution(plan, store, triggered_by_id="mem_trigger_003")

            reloaded = store.get("mem_exec_003")
            # 截断后应保留最新 10 条
            assert len(reloaded.evolution_history) == 10, \
                f"演化历史应截断至 10 条，实际 {len(reloaded.evolution_history)}"
            # 最后一条应是刚刚执行的
            last_entry = reloaded.evolution_history[-1]
            assert last_entry["triggered_by"] == "mem_trigger_003", \
                f"最后一条历史的 triggered_by 应为 'mem_trigger_003'，实际 {last_entry['triggered_by']}"
            # 最老的一条（index 0）应是第 2 条旧记录（第 1 条被丢弃）
            first_entry = reloaded.evolution_history[0]
            assert first_entry["triggered_by"] == "mem_old_002", \
                f"第一条历史应为 mem_old_002（最旧的被丢弃），实际 {first_entry['triggered_by']}"

        finally:
            os.unlink(store_path)

    def test_execute_no_changes(self):
        """没有实际变更时不更新记忆，不添加历史记录"""
        store_path, store = _new_tmp_store()

        try:
            neighbor = _make_memory(
                "mem_exec_004",
                "某项记忆",
                keywords=["记忆"],
                tags=["existing-tag"],
                context="现有上下文",
            )
            store.add(neighbor)

            # 计划中 new_context 与已有 context 相同，add_tags 已存在，add_keywords 已存在
            plan = [
                {
                    "neighbor_id": "mem_exec_004",
                    "new_context": "现有上下文",  # 与现有 context 相同
                    "add_tags": ["existing-tag"],  # 已存在的 tag
                    "add_keywords": ["记忆"],  # 已存在的 keyword
                }
            ]

            updated_ids = execute_evolution(plan, store, triggered_by_id="mem_trigger_004")

            assert "mem_exec_004" not in updated_ids, \
                f"无实际变更时不应出现在更新列表中，实际 {updated_ids}"

            reloaded = store.get("mem_exec_004")
            assert len(reloaded.evolution_history) == 0, \
                f"无变更时不应添加历史记录，实际 {len(reloaded.evolution_history)}"

        finally:
            os.unlink(store_path)


# ==================== 场景 4: TestEvolveNeighborsIntegration ====================

class TestEvolveNeighborsIntegration:
    """evolve_neighbors() 完整流程集成测试。"""

    def test_full_evolution_flow(self):
        """完整流程：找邻居 → 判断 → 生成指令 → 执行"""
        store_path, store = _new_tmp_store()

        try:
            # 在 store 中创建 2 条相关记忆
            neighbor1 = _make_memory(
                "mem_integ_001",
                "LaTeX fontspec 找不到字体",
                keywords=["LaTeX", "fontspec", "字体", "编译失败"],
                context="LaTeX fontspec 找不到系统字体",
            )
            neighbor2 = _make_memory(
                "mem_integ_002",
                "xelatex 编译时字体配置问题",
                keywords=["xelatex", "字体", "配置", "编译"],
                context="xelatex 字体配置失败",
            )
            store.add(neighbor1)
            store.add(neighbor2)

            # 创建触发演化的新记忆
            new_memory = _make_memory(
                "mem_integ_new",
                "LaTeX 字体问题解决：fc-cache -fv 刷新字体缓存后恢复正常",
                keywords=["LaTeX", "字体", "fc-cache", "解决方案", "fontspec"],
                context="fc-cache -fv 解决 LaTeX 字体缺失",
            )

            # Mock should_evolve 返回 True
            should_evolve_response = json.dumps(
                {"should_evolve": True, "reason": "新记忆包含解决方案"}
            )
            # Mock generate_plan 返回更新 neighbor1 的指令
            plan_response = json.dumps({
                "updates": [
                    {
                        "neighbor_id": "mem_integ_001",
                        "new_context": "LaTeX fontspec 找不到系统字体；解决方案：fc-cache -fv",
                        "add_tags": ["solved"],
                        "add_keywords": ["fc-cache"],
                    }
                ]
            })

            call_count = [0]

            def mock_create(**kwargs):
                call_count[0] += 1
                mock_response = MagicMock()
                if call_count[0] == 1:
                    # 第一次调用：should_evolve
                    mock_response.content = [MagicMock(text=should_evolve_response)]
                else:
                    # 第二次调用：generate_plan
                    mock_response.content = [MagicMock(text=plan_response)]
                return mock_response

            mock_client = MagicMock()
            mock_client.messages.create.side_effect = mock_create

            # Mock find_associations 返回邻居 IDs
            with patch.object(evolver, 'get_client', return_value=mock_client), \
                 patch('associator.find_associations', return_value=["mem_integ_001", "mem_integ_002"]):
                updated = evolve_neighbors(new_memory, store)

            assert "mem_integ_001" in updated, \
                f"mem_integ_001 应在更新列表中，实际 {updated}"

            # 验证 neighbor1 已被更新
            reloaded_n1 = store.get("mem_integ_001")
            assert "fc-cache" in reloaded_n1.keywords, \
                f"keywords 中应包含 'fc-cache'，实际 {reloaded_n1.keywords}"
            assert "solved" in reloaded_n1.tags, \
                f"tags 中应包含 'solved'，实际 {reloaded_n1.tags}"

            # 验证 evolution_history 已记录
            assert len(reloaded_n1.evolution_history) == 1, \
                f"应有 1 条演化历史，实际 {len(reloaded_n1.evolution_history)}"
            assert reloaded_n1.evolution_history[0]["triggered_by"] == "mem_integ_new", \
                f"triggered_by 应为 'mem_integ_new'，实际 {reloaded_n1.evolution_history[0]['triggered_by']}"

        finally:
            os.unlink(store_path)

    def test_evolve_skipped_when_not_needed(self):
        """should_evolve=False 时不调用 generate_evolution_plan"""
        store_path, store = _new_tmp_store()

        try:
            neighbor = _make_memory(
                "mem_skip_001",
                "邻居记忆",
                keywords=["邻居"],
                context="已完整的上下文",
            )
            store.add(neighbor)

            new_memory = _make_memory(
                "mem_skip_new",
                "新记忆，没有新增价值",
                keywords=["邻居", "内容"],
            )

            # should_evolve 返回 False
            should_evolve_response = json.dumps(
                {"should_evolve": False, "reason": "信息已完整"}
            )

            mock_client = _make_mock_client(should_evolve_response)

            with patch.object(evolver, 'get_client', return_value=mock_client), \
                 patch('associator.find_associations', return_value=["mem_skip_001"]):
                updated = evolve_neighbors(new_memory, store)

            assert updated == [], f"should_evolve=False 时应返回 []，实际 {updated}"
            # 只调用了一次 API（should_evolve），generate_plan 未调用
            assert mock_client.messages.create.call_count == 1, \
                f"只应调用 1 次 API（should_evolve），实际 {mock_client.messages.create.call_count} 次"

        finally:
            os.unlink(store_path)

    def test_evolve_silent_fallback(self):
        """全流程异常时静默返回空列表，不崩溃"""
        store_path, store = _new_tmp_store()

        try:
            new_memory = _make_memory(
                "mem_fallback_new",
                "某项新记忆",
                keywords=["新记忆"],
            )

            # get_client 抛出异常（模拟所有 API 调用失败）
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = Exception("服务不可用")

            with patch.object(evolver, 'get_client', return_value=mock_client), \
                 patch('associator.find_associations', side_effect=Exception("查找邻居失败")):
                updated = evolve_neighbors(new_memory, store)

            assert updated == [], f"全流程异常时应返回 []，实际 {updated}"

        finally:
            os.unlink(store_path)


# ==================== 测试运行器 ====================

def run_tests():
    """按顺序运行所有测试，输出详细结果。"""
    test_classes = [
        TestShouldEvolve,
        TestGenerateEvolutionPlan,
        TestExecuteEvolution,
        TestEvolveNeighborsIntegration,
    ]

    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("Evolver 模块单元测试")
    print("=" * 60)

    for cls in test_classes:
        instance = cls()
        for method_name in sorted(dir(instance)):
            if not method_name.startswith('test_'):
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
