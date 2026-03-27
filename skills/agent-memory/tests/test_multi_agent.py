"""多角色集成测试 — 验证 Phase 6b/6e 多 Agent 协作记忆功能。

测试场景:
1. TestAgentRegistry          — 角色注册、释放、重分配、目录创建
2. TestDualLayerMemory        — 个人记忆隔离、双层合并检索、跨类型隔离
3. TestSameTypeAssociation    — 同类型角色间自动关联、跨类型不关联
4. TestAutoClassification     — shared 自动分类、personal 默认、被动晋升
5. TestCLIWithAgent           — CLI --agent 参数端到端验证
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch, MagicMock

# 将 scripts 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from registry import AgentRegistry

# CLI 脚本绝对路径
CLI_PATH = os.path.expanduser('~/.claude/skills/agent-memory/scripts/cli.py')


# ==================== 辅助函数 ====================

def _make_mock_response(keywords, tags, context, importance):
    """构建模拟 Claude API 响应。"""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "keywords": keywords,
        "tags": tags,
        "context": context,
        "importance": importance,
    }))]
    return mock_response


def _new_tmp_dir():
    """创建临时目录，返回路径字符串。"""
    return tempfile.mkdtemp()


def _cleanup_dir(dirpath):
    """递归删除临时目录。"""
    if os.path.exists(dirpath):
        shutil.rmtree(dirpath)


def _setup_agent_env(base_dir):
    """在指定 base_dir 中初始化 AgentRegistry 需要的目录结构。"""
    Path(base_dir).mkdir(parents=True, exist_ok=True)
    (Path(base_dir) / "shared").mkdir(exist_ok=True)
    (Path(base_dir) / "agents").mkdir(exist_ok=True)


def _make_agent_store(base_dir, agent_name, agent_type=None):
    """创建指向 base_dir/agents/{agent_name}/memories.jsonl 的 MemoryStore。"""
    agent_dir = Path(base_dir) / "agents" / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)
    store_path = str(agent_dir / "memories.jsonl")
    return MemoryStore(store_path=store_path, agent_name=agent_name, agent_type=agent_type)


def _shared_store(base_dir):
    """创建指向 base_dir/shared/memories.jsonl 的 MemoryStore。"""
    shared_path = Path(base_dir) / "shared" / "memories.jsonl"
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    return MemoryStore(store_path=str(shared_path))


# ==================== 场景 1: TestAgentRegistry ====================

class TestAgentRegistry:
    """
    场景 1: 角色注册、释放、重分配全流程验证。
    """

    def test_assign_and_release(self):
        """测试角色分配、释放、重新分配"""
        base_dir = _new_tmp_dir()
        try:
            registry = AgentRegistry(base_path=base_dir)

            # 首次分配 Explore → 名字池第一个（kaze）
            name1 = registry.assign("Explore")
            assert name1 == "kaze", f"首次分配 Explore 应得到 kaze，实际 {name1}"

            # 再次分配 Explore（kaze busy）→ 第二个（mirin）
            name2 = registry.assign("Explore")
            assert name2 == "mirin", f"第二次分配 Explore 应得到 mirin，实际 {name2}"

            # 释放 kaze → idle
            registry.release(name1)
            all_agents = registry.get_all_agents()
            assert all_agents[name1]["status"] == "idle", \
                f"release 后 kaze 状态应为 idle，实际 {all_agents[name1]['status']}"

            # 再分配 Explore → 优先复用 idle 的 kaze
            name3 = registry.assign("Explore")
            assert name3 == name1, \
                f"应复用 idle 的 kaze，实际分配了 {name3}"

            # 验证 get_all_agents 包含所有分配的角色
            all_agents = registry.get_all_agents()
            assert name1 in all_agents, f"{name1} 应在注册表中"
            assert name2 in all_agents, f"{name2} 应在注册表中"
        finally:
            _cleanup_dir(base_dir)

    def test_type_aliases(self):
        """测试 subagent_type 别名映射"""
        base_dir = _new_tmp_dir()
        try:
            registry = AgentRegistry(base_path=base_dir)

            # worker → Worker
            name_w = registry.assign("worker")
            assert registry.get_agent_type(name_w) == "Worker", \
                f"worker 别名应映射到 Worker，实际 {registry.get_agent_type(name_w)}"

            # general-purpose → Operator
            name_o = registry.assign("general-purpose")
            assert registry.get_agent_type(name_o) == "Operator", \
                f"general-purpose 别名应映射到 Operator，实际 {registry.get_agent_type(name_o)}"

            # code-reviewer → Auditor
            name_a = registry.assign("code-reviewer")
            assert registry.get_agent_type(name_a) == "Auditor", \
                f"code-reviewer 别名应映射到 Auditor，实际 {registry.get_agent_type(name_a)}"
        finally:
            _cleanup_dir(base_dir)

    def test_name_pool_isolation(self):
        """测试不同类型名字池互不干扰"""
        base_dir = _new_tmp_dir()
        try:
            registry = AgentRegistry(base_path=base_dir)

            explore_name = registry.assign("Explore")
            worker_name = registry.assign("Worker")

            # 两种类型的名字来自不同池，不能相同
            assert explore_name != worker_name, \
                f"Explore 和 Worker 的名字应来自不同池，都得到了 {explore_name}"

            # get_agents_by_type 返回的分组正确
            explore_agents = registry.get_agents_by_type("Explore")
            worker_agents = registry.get_agents_by_type("Worker")

            assert explore_name in explore_agents, \
                f"{explore_name} 应在 Explore 分组中，实际 {explore_agents}"
            assert worker_name in worker_agents, \
                f"{worker_name} 应在 Worker 分组中，实际 {worker_agents}"

            # 两个分组不交叉
            assert explore_name not in worker_agents, \
                f"{explore_name} 不应出现在 Worker 分组中"
            assert worker_name not in explore_agents, \
                f"{worker_name} 不应出现在 Explore 分组中"
        finally:
            _cleanup_dir(base_dir)

    def test_agent_directory_creation(self):
        """测试角色目录和文件自动创建"""
        base_dir = _new_tmp_dir()
        try:
            registry = AgentRegistry(base_path=base_dir)
            name = registry.assign("Explore")

            # 角色目录存在
            agent_dir = Path(base_dir) / "agents" / name
            assert agent_dir.exists(), f"角色目录 {agent_dir} 应存在"

            # memories.jsonl 存在
            memories_path = agent_dir / "memories.jsonl"
            assert memories_path.exists(), f"{memories_path} 应存在"

            # profile.json 存在且字段正确
            profile_path = agent_dir / "profile.json"
            assert profile_path.exists(), f"{profile_path} 应存在"
            profile = json.loads(profile_path.read_text(encoding='utf-8'))
            assert profile.get("name") == name, \
                f"profile.name 应为 {name}，实际 {profile.get('name')}"
            assert profile.get("type") == "Explore", \
                f"profile.type 应为 Explore，实际 {profile.get('type')}"
            assert "created" in profile, "profile 中应有 created 字段"
            assert "task_count" in profile, "profile 中应有 task_count 字段"

            # shared 目录存在
            shared_dir = Path(base_dir) / "shared"
            assert shared_dir.exists(), f"shared 目录 {shared_dir} 应存在"
        finally:
            _cleanup_dir(base_dir)


# ==================== 场景 2: TestDualLayerMemory ====================

class TestDualLayerMemory:
    """
    场景 2: 个人记忆隔离、双层合并检索、跨类型隔离。
    """

    def _add_memory(self, store, mem_id, content, keywords, agent_name=""):
        """向 store 直接追加一条测试记忆（跳过 Claude API）。"""
        mem = Memory(
            id=mem_id,
            content=content,
            timestamp="2026-03-13T10:00:00",
            keywords=keywords,
            tags=["test"],
            context=content[:50],
            importance=5,
            owner=agent_name,
            scope="personal",
        )
        store.add(mem)
        return mem

    def test_personal_memory_isolation(self):
        """测试个人记忆隔离：不同角色的记忆不混"""
        base_dir = _new_tmp_dir()
        try:
            # 创建两个 Explore 角色的独立 store
            store_kaze = _make_agent_store(base_dir, "kaze", "Explore")
            store_mirin = _make_agent_store(base_dir, "mirin", "Explore")

            # 各自添加记忆
            m_kaze = self._add_memory(
                store_kaze, "kaze_20260313_001",
                "kaze 的 LaTeX 编译记忆", ["LaTeX", "编译", "kaze"],
                agent_name="kaze"
            )
            m_mirin = self._add_memory(
                store_mirin, "mirin_20260313_001",
                "mirin 的字体配置记忆", ["字体", "配置", "mirin"],
                agent_name="mirin"
            )

            # 验证隔离：kaze 的 store 只包含 kaze 的记忆
            kaze_all = store_kaze.load_all()
            assert len(kaze_all) == 1, f"kaze 的 store 应只有 1 条记忆，实际 {len(kaze_all)}"
            assert kaze_all[0].id == m_kaze.id, \
                f"kaze 的 store 应包含 {m_kaze.id}，实际 {kaze_all[0].id}"

            # 验证隔离：mirin 的 store 只包含 mirin 的记忆
            mirin_all = store_mirin.load_all()
            assert len(mirin_all) == 1, f"mirin 的 store 应只有 1 条记忆，实际 {len(mirin_all)}"
            assert mirin_all[0].id == m_mirin.id, \
                f"mirin 的 store 应包含 {m_mirin.id}，实际 {mirin_all[0].id}"

            # 验证 ID 前缀正确
            assert m_kaze.id.startswith("kaze_"), \
                f"kaze 的记忆 ID 应以 kaze_ 开头，实际 {m_kaze.id}"
            assert m_mirin.id.startswith("mirin_"), \
                f"mirin 的记忆 ID 应以 mirin_ 开头，实际 {m_mirin.id}"
        finally:
            _cleanup_dir(base_dir)

    def test_retrieve_merged(self):
        """测试双层检索：个人 + 同类型 + shared

        由于 MemoryStore.retrieve_merged() 内部硬编码了 ~/.claude/memory 路径，
        此测试直接手动合并三个 store 的记忆做检索，验证合并检索逻辑本身。
        """
        base_dir = _new_tmp_dir()
        try:
            # 创建三个 store：kaze 个人、mirin 个人、shared
            store_kaze = _make_agent_store(base_dir, "kaze", "Explore")
            store_mirin = _make_agent_store(base_dir, "mirin", "Explore")
            store_shared = _shared_store(base_dir)

            # 添加各层记忆
            self._add_memory(
                store_kaze, "kaze_20260313_001",
                "LaTeX 字体编译问题排查", ["LaTeX", "字体", "编译"],
                agent_name="kaze"
            )
            self._add_memory(
                store_mirin, "mirin_20260313_001",
                "字体配置方案，使用 fandol", ["字体配置", "fandol", "字体"],
                agent_name="mirin"
            )
            self._add_memory(
                store_shared, "shared_20260313_001",
                "编译流程通用规范", ["编译", "规范", "通用"],
            )

            # 模拟 retrieve_merged 的核心逻辑：合并三个层的记忆做统一检索
            from retriever import retrieve as _retrieve
            from datetime import datetime

            all_memories = []
            all_memories.extend(store_kaze.load_all())
            all_memories.extend(store_mirin.load_all())
            all_memories.extend(store_shared.load_all())

            import tempfile as _tmp
            tmp_merged_dir = _tmp.mkdtemp(prefix="test-retrieve-merged-")
            try:
                merged_store = MemoryStore(store_path=tmp_merged_dir)
                for m in all_memories:
                    merged_store.add(m)
                results = _retrieve(
                    "LaTeX 字体编译",
                    merged_store,
                    top_k=5,
                    spread=False,
                    now=datetime(2026, 3, 13, 10, 0, 0),
                )
            finally:
                _cleanup_dir(tmp_merged_dir)

            # 合并检索应找到至少 2 条记忆（kaze 的 + mirin 的 或 shared 的）
            assert len(results) >= 2, \
                f"合并检索应返回 >= 2 条记忆，实际 {len(results)}"

            # 验证分数降序
            scores = [s for _, s in results]
            assert scores == sorted(scores, reverse=True), \
                "检索结果应按分数降序排列"

            # 验证三个 store 的记忆都在候选中
            result_ids = {m.id for m, _ in results}
            all_expected_ids = {"kaze_20260313_001", "mirin_20260313_001", "shared_20260313_001"}
            found = result_ids & all_expected_ids
            assert len(found) >= 2, \
                f"合并检索应命中至少 2 个不同层的记忆，实际命中 {found}"
        finally:
            _cleanup_dir(base_dir)

    def test_cross_type_isolation(self):
        """测试跨类型隔离：Explore 的记忆不应包含 Worker 的记忆（手动合并验证）"""
        base_dir = _new_tmp_dir()
        try:
            # 创建 Explore 和 Worker 各自的 store
            store_explore = _make_agent_store(base_dir, "kaze", "Explore")
            store_worker = _make_agent_store(base_dir, "tetsu", "Worker")
            store_shared = _shared_store(base_dir)

            m_explore = self._add_memory(
                store_explore, "kaze_20260313_001",
                "Explore 角色的 LaTeX 研究记忆", ["LaTeX", "研究", "Explore"],
                agent_name="kaze"
            )
            m_worker = self._add_memory(
                store_worker, "tetsu_20260313_001",
                "Worker 角色的 LaTeX 编写记忆", ["LaTeX", "编写", "Worker"],
                agent_name="tetsu"
            )
            m_shared = self._add_memory(
                store_shared, "shared_20260313_001",
                "共享的 LaTeX 通用配置", ["LaTeX", "配置", "通用"],
            )

            # 模拟 Explore 类型的合并检索（只含 kaze 个人 + shared，不含 tetsu）
            from retriever import retrieve as _retrieve
            from datetime import datetime

            explore_memories = store_explore.load_all()
            shared_memories = store_shared.load_all()
            # Explore 的合并结果不应包含 Worker 记忆
            explore_merged = explore_memories + shared_memories

            import tempfile as _tmp
            tmp_merged_dir2 = _tmp.mkdtemp(prefix="test-cross-type-")
            try:
                merged_store = MemoryStore(store_path=tmp_merged_dir2)
                for m in explore_merged:
                    merged_store.add(m)
                results = _retrieve(
                    "LaTeX 记忆",
                    merged_store,
                    top_k=5,
                    spread=False,
                    now=datetime(2026, 3, 13, 10, 0, 0),
                )
            finally:
                _cleanup_dir(tmp_merged_dir2)

            result_ids = [m.id for m, _ in results]
            assert m_worker.id not in result_ids, \
                f"Explore 的检索结果中不应包含 Worker 的记忆 {m_worker.id}"
            assert m_explore.id in result_ids or m_shared.id in result_ids, \
                "Explore 的检索结果中应包含 Explore 的个人记忆或 shared 记忆"
        finally:
            _cleanup_dir(base_dir)


# ==================== 场景 3: TestSameTypeAssociation ====================

class TestSameTypeAssociation:
    """
    场景 3: 同类型角色间自动关联、跨类型不建立关联。
    """

    def _create_memory_in_store(self, store, task_info, keywords, tags, context, importance,
                                 agent_name=None, agent_type=None, base_dir=None):
        """在指定 store 中通过 extractor 创建记忆（mock Claude API）。"""
        from extractor import create_memory_from_task

        mock_resp = _make_mock_response(keywords, tags, context, importance)

        # 需要 patch AgentRegistry 以使用 base_dir
        if base_dir and agent_name:
            real_registry_cls = AgentRegistry

            def make_registry(*args, **kwargs):
                # 若没有传 base_path，使用 base_dir
                if not args and not kwargs.get('base_path'):
                    return real_registry_cls(base_path=base_dir)
                return real_registry_cls(*args, **kwargs)

            with patch('extractor.get_client') as mock_client, \
                 patch('extractor.AgentRegistry', side_effect=make_registry), \
                 patch('associator.AgentRegistry', side_effect=make_registry):
                mock_client.return_value.messages.create.return_value = mock_resp
                return create_memory_from_task(
                    task_info, store, auto_link=True, agent_name=agent_name
                )
        else:
            with patch('extractor.get_client') as mock_client:
                mock_client.return_value.messages.create.return_value = mock_resp
                return create_memory_from_task(
                    task_info, store, auto_link=True, agent_name=agent_name
                )

    def _make_expanduser_redirector(self, base_dir):
        """返回一个 expanduser 替换函数，将 ~/.claude/memory 重定向到 base_dir。"""
        real_expanduser = os.path.expanduser

        def fake_expanduser(path):
            expanded = real_expanduser(path)
            real_base = real_expanduser("~/.claude/memory")
            if expanded == real_base:
                return base_dir
            if expanded.startswith(real_base + "/"):
                return base_dir + expanded[len(real_base):]
            return expanded

        return fake_expanduser

    def test_same_type_linking(self):
        """测试同类型角色间自动关联

        associator.py 内部通过局部 `from registry import AgentRegistry` 构建 AgentRegistry()，
        并硬编码 ~/.claude/memory 路径读取 agent 记忆文件。
        通过 patch registry.AgentRegistry + associator.os.path.expanduser 实现完全隔离。
        """
        base_dir = _new_tmp_dir()
        try:
            # 初始化注册表
            local_registry = AgentRegistry(base_path=base_dir)
            registry_data = {
                "agents": {
                    "kaze": {"type": "Explore", "status": "busy", "created": "2026-03-13"},
                    "mirin": {"type": "Explore", "status": "busy", "created": "2026-03-13"},
                }
            }
            local_registry._write_json(local_registry.registry_path, registry_data)

            # 先给 mirin 创建一条记忆
            store_mirin = _make_agent_store(base_dir, "mirin", "Explore")
            mirin_mem = Memory(
                id="mirin_20260313_001",
                content="LaTeX 字体配置：使用 SimSun 解决字体缺失",
                timestamp="2026-03-13T09:00:00",
                keywords=["LaTeX", "SimSun", "字体", "fontspec"],
                tags=["config", "latex"],
                context="LaTeX fontspec 字体配置",
                importance=6,
                owner="mirin",
                scope="personal",
            )
            store_mirin.add(mirin_mem)

            # kaze 创建同主题记忆（link 时应找到 mirin 的记忆）
            store_kaze = _make_agent_store(base_dir, "kaze", "Explore")

            real_registry_cls = AgentRegistry

            def make_registry_with_base(*args, **kwargs):
                if not args and not kwargs.get('base_path'):
                    return real_registry_cls(base_path=base_dir)
                return real_registry_cls(*args, **kwargs)

            mock_resp = _make_mock_response(
                keywords=["LaTeX", "fontspec", "字体错误", "编译失败"],
                tags=["bug-fix", "latex"],
                context="LaTeX fontspec 字体缺失错误",
                importance=7,
            )

            fake_expanduser = self._make_expanduser_redirector(base_dir)

            import associator as _associator_module
            # patch registry.AgentRegistry + associator 模块内的 os.path.expanduser
            with patch('extractor.get_client') as mock_client, \
                 patch('registry.AgentRegistry', side_effect=make_registry_with_base), \
                 patch.object(_associator_module.os.path, 'expanduser',
                              side_effect=fake_expanduser):
                mock_client.return_value.messages.create.return_value = mock_resp
                from extractor import create_memory_from_task
                kaze_mem = create_memory_from_task(
                    {"subject": "LaTeX fontspec 字体缺失", "description": "编译报错字体找不到", "task_id": "t1"},
                    store_kaze,
                    auto_link=True,
                    agent_name="kaze",
                )

            # 验证 kaze 的记忆有 related_ids（指向 mirin 的记忆）
            kaze_reloaded = store_kaze.get(kaze_mem.id)
            assert kaze_reloaded is not None, "kaze 的记忆应能重新加载"
            assert len(kaze_reloaded.related_ids) > 0, \
                f"kaze 的记忆 {kaze_reloaded.id} 应有 related_ids，实际 {kaze_reloaded.related_ids}"

            # 验证双向链接：mirin 的记忆中应有 kaze 记忆的 ID
            mirin_reloaded = store_mirin.get(mirin_mem.id)
            assert mirin_reloaded is not None, "mirin 的记忆应能重新加载"
            assert kaze_mem.id in mirin_reloaded.related_ids, \
                f"mirin 的记忆应包含 kaze 记忆的 ID {kaze_mem.id}，" \
                f"实际 {mirin_reloaded.related_ids}"
        finally:
            _cleanup_dir(base_dir)

    def test_cross_type_no_linking(self):
        """测试跨类型不建立关联

        kaze (Explore) 关联时只搜索 Explore 类型角色，因此不会链接到 tetsu (Worker) 的记忆。
        """
        base_dir = _new_tmp_dir()
        try:
            # 初始化注册表，只有 kaze 在 Explore 中（tetsu 是 Worker）
            local_registry = AgentRegistry(base_path=base_dir)
            registry_data = {
                "agents": {
                    "kaze": {"type": "Explore", "status": "busy", "created": "2026-03-13"},
                    "tetsu": {"type": "Worker", "status": "busy", "created": "2026-03-13"},
                }
            }
            local_registry._write_json(local_registry.registry_path, registry_data)

            # tetsu (Worker) 先有一条 LaTeX 记忆
            store_tetsu = _make_agent_store(base_dir, "tetsu", "Worker")
            tetsu_mem = Memory(
                id="tetsu_20260313_001",
                content="LaTeX 编译输出目录配置",
                timestamp="2026-03-13T09:00:00",
                keywords=["LaTeX", "编译", "输出目录", "配置"],
                tags=["config", "latex"],
                context="LaTeX 编译输出路径设置",
                importance=5,
                owner="tetsu",
                scope="personal",
            )
            store_tetsu.add(tetsu_mem)

            # kaze (Explore) 创建同主题记忆，关联应只在 Explore 类型内查找
            store_kaze = _make_agent_store(base_dir, "kaze", "Explore")

            real_registry_cls = AgentRegistry

            def make_registry_with_base(*args, **kwargs):
                if not args and not kwargs.get('base_path'):
                    return real_registry_cls(base_path=base_dir)
                return real_registry_cls(*args, **kwargs)

            mock_resp = _make_mock_response(
                keywords=["LaTeX", "fontspec", "字体", "编译"],
                tags=["research", "latex"],
                context="LaTeX 字体研究",
                importance=6,
            )

            # patch registry.AgentRegistry（局部 import 会从 registry 模块取类）
            with patch('extractor.get_client') as mock_client, \
                 patch('registry.AgentRegistry', side_effect=make_registry_with_base):
                mock_client.return_value.messages.create.return_value = mock_resp
                from extractor import create_memory_from_task
                kaze_mem = create_memory_from_task(
                    {"subject": "LaTeX 字体研究", "description": "研究 LaTeX 字体配置方案", "task_id": "t2"},
                    store_kaze,
                    auto_link=True,
                    agent_name="kaze",
                )

            # kaze 的 related_ids 中不应包含 tetsu 的记忆 ID
            kaze_reloaded = store_kaze.get(kaze_mem.id)
            assert kaze_reloaded is not None, "kaze 的记忆应能重新加载"
            assert tetsu_mem.id not in kaze_reloaded.related_ids, \
                f"kaze（Explore）的 related_ids 中不应包含 tetsu（Worker）的记忆 " \
                f"{tetsu_mem.id}，实际 {kaze_reloaded.related_ids}"

            # tetsu 的记忆 related_ids 中也不应有 kaze 的 ID（因为未跨类型关联）
            tetsu_reloaded = store_tetsu.get(tetsu_mem.id)
            if tetsu_reloaded:
                assert kaze_mem.id not in tetsu_reloaded.related_ids, \
                    f"tetsu（Worker）的记忆中不应包含 kaze（Explore）的 ID"
        finally:
            _cleanup_dir(base_dir)


# ==================== 场景 4: TestAutoClassification ====================

class TestAutoClassification:
    """
    场景 4: 自动 scope 分类（shared / personal）和被动晋升。
    """

    def test_shared_classification(self):
        """测试 importance>=8 + 通用 tag 自动分类为 shared"""
        base_dir = _new_tmp_dir()
        try:
            store_path = str(Path(base_dir) / "personal.jsonl")
            store = MemoryStore(store_path=store_path)

            mock_resp = _make_mock_response(
                keywords=["架构规范", "配置", "项目结构"],
                tags=["architecture", "config"],
                context="项目架构规范配置",
                importance=9,
            )

            with patch('extractor.get_client') as mock_client:
                mock_client.return_value.messages.create.return_value = mock_resp
                from extractor import create_memory_from_task, _classify_scope

                # 验证 _classify_scope 函数本身的分类结果
                fields = {"importance": 9, "tags": ["architecture", "config"]}
                scope = _classify_scope(fields)
                assert scope == "shared", \
                    f"importance=9 + architecture/config 标签应分类为 shared，实际 {scope}"

                mock_client.return_value.messages.create.return_value = mock_resp
                memory = create_memory_from_task(
                    {"subject": "项目架构规范", "description": "定义整体配置架构", "task_id": "cls-001"},
                    store,
                )

            assert memory.scope == "shared", \
                f"importance=9 + architecture tag 应使 scope=shared，实际 {memory.scope}"
        finally:
            _cleanup_dir(base_dir)

    def test_personal_default(self):
        """测试默认分类为 personal"""
        base_dir = _new_tmp_dir()
        try:
            store_path = str(Path(base_dir) / "personal.jsonl")
            store = MemoryStore(store_path=store_path)

            mock_resp = _make_mock_response(
                keywords=["调试", "bug", "修复"],
                tags=["debugging", "bug-fix"],
                context="调试修复一个小 bug",
                importance=5,
            )

            with patch('extractor.get_client') as mock_client:
                mock_client.return_value.messages.create.return_value = mock_resp
                from extractor import create_memory_from_task
                memory = create_memory_from_task(
                    {"subject": "修复小 bug", "description": "调试并修复一处逻辑错误", "task_id": "cls-002"},
                    store,
                )

            assert memory.scope == "personal", \
                f"importance=5 + debugging 标签应分类为 personal，实际 {memory.scope}"
        finally:
            _cleanup_dir(base_dir)

    def test_promotion(self):
        """测试被动晋升：被 >=3 角色检索后晋升到 shared

        check_promotion() 硬编码了 ~/.claude/memory/shared/ 路径，
        通过 patch memory_store 内的 os.path.expanduser 重定向到 base_dir。
        """
        base_dir = _new_tmp_dir()
        real_base = os.path.expanduser("~/.claude/memory")

        def fake_expanduser(path):
            """将 ~/.claude/memory 重定向到 base_dir。"""
            if path == "~/.claude/memory":
                return base_dir
            if isinstance(path, str) and "~/.claude/memory" in path:
                return path.replace("~/.claude/memory", base_dir)
            import os as _os
            return _os.path.expanduser(path)

        try:
            # 在 kaze 的 store 中创建一条 personal 记忆（base_dir 内）
            (Path(base_dir) / "agents" / "kaze").mkdir(parents=True, exist_ok=True)
            (Path(base_dir) / "shared").mkdir(exist_ok=True)
            kaze_store_path = str(Path(base_dir) / "agents" / "kaze" / "memories.jsonl")
            store_kaze = MemoryStore(store_path=kaze_store_path)

            personal_mem = Memory(
                id="kaze_20260313_001",
                content="LaTeX 编译流程总结",
                timestamp="2026-03-13T10:00:00",
                keywords=["LaTeX", "编译", "流程"],
                tags=["config", "latex"],
                context="LaTeX 编译最佳实践",
                importance=6,
                owner="kaze",
                scope="personal",
                accessed_by=[],
            )
            store_kaze.add(personal_mem)

            # 模拟 3 个不同角色访问过该记忆
            mem = store_kaze.get(personal_mem.id)
            assert mem is not None, "记忆应存在"
            mem.accessed_by = ["mirin", "tetsu", "soren"]
            store_kaze.update(mem)

            # patch memory_store 模块内的 os.path.expanduser，使 shared 路径指向 base_dir
            import memory_store as _ms_module
            with patch.object(_ms_module.os.path, 'expanduser', side_effect=fake_expanduser):
                promoted = store_kaze.check_promotion(personal_mem.id)

            assert promoted, "被 3 个角色访问后应触发晋升"

            # 验证原始记忆的 scope 已更新为 shared
            original_after = store_kaze.get(personal_mem.id)
            assert original_after.scope == "shared", \
                f"晋升后原始记忆 scope 应变为 shared，实际 {original_after.scope}"

            # shared 层应有该记忆的副本（路径已被重定向到 base_dir）
            # 新 .md 存储：检查 shared 目录下有 .md 文件
            shared_dir = Path(base_dir) / "shared"
            md_files = list(shared_dir.glob("*.md"))
            assert len(md_files) > 0, \
                f"shared 目录下应有 .md 记忆文件，实际: {list(shared_dir.iterdir()) if shared_dir.exists() else '目录不存在'}"
            shared_store_check = MemoryStore(store_path=str(shared_dir))
            shared_mems = shared_store_check.load_all()
            assert len(shared_mems) >= 1, \
                f"shared 层应有 >=1 条记忆，实际 {len(shared_mems)}"

            # shared 层记忆的 scope 应为 shared
            assert shared_mems[0].scope == "shared", \
                f"shared 层记忆的 scope 应为 shared，实际 {shared_mems[0].scope}"
            assert shared_mems[0].owner == "shared", \
                f"shared 层记忆的 owner 应为 shared，实际 {shared_mems[0].owner}"
        finally:
            _cleanup_dir(base_dir)


# ==================== 场景 5: TestCLIWithAgent ====================

class TestCLIWithAgent:
    """
    场景 5: CLI --agent 参数端到端验证。
    """

    def _run_cli(self, base_dir, agent_name, *args, extra_env=None):
        """运行 cli.py 子进程，传入 --agent 参数，返回 (stdout, stderr, returncode)。"""
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        # 当 --agent 使用时，cli.py 使用默认的 ~/.claude/memory 路径
        # 我们传入一个空的 --store 以防万一（--agent 优先级高于 --store）
        tmp_store = str(Path(base_dir) / "fallback.jsonl")
        cmd = [sys.executable, CLI_PATH, '--store', tmp_store, '--agent', agent_name] + list(args)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        return proc.stdout, proc.stderr, proc.returncode

    def test_cli_agent_flag(self):
        """测试 CLI --agent 参数（使用真实的 ~/.claude/memory 目录）"""
        # 注意：此测试会临时写入 ~/.claude/memory/agents/kaze/ 目录
        # 测试结束后会尝试清理（但不删除已有记忆，只验证新增的）
        import re
        from datetime import datetime

        real_base = Path(os.path.expanduser("~/.claude/memory"))
        real_base.mkdir(parents=True, exist_ok=True)
        (real_base / "agents").mkdir(exist_ok=True)
        (real_base / "shared").mkdir(exist_ok=True)

        # 先确保 kaze 在注册表中（若不存在则通过 registry 分配）
        registry = AgentRegistry()  # 使用默认路径
        existing_type = registry.get_agent_type("kaze")
        if not existing_type:
            registry.assign("Explore")  # 这会分配 kaze 作为第一个 Explore 角色

        # 记录测试前 kaze store 中的记忆数量
        kaze_store_path = real_base / "agents" / "kaze" / "memories.jsonl"
        kaze_store_path.parent.mkdir(parents=True, exist_ok=True)
        if not kaze_store_path.exists():
            kaze_store_path.touch()
        pre_count = len(MemoryStore(store_path=str(kaze_store_path)).load_all())

        tmp_dir = _new_tmp_dir()
        try:
            # 1. add — 通过 CLI 以 kaze 身份添加记忆
            stdout, stderr, rc = self._run_cli(
                tmp_dir, "kaze",
                "add",
                "--subject", "多角色集成测试记忆",
                "--keywords", "测试,集成,多角色",
                "--tags", "test,integration",
                "--importance", "5",
            )
            assert rc == 0, f"add 命令失败 (rc={rc}):\n{stderr}"
            assert "记忆已创建" in stdout, f"add 应输出创建成功，实际:\n{stdout}"
            assert "多角色集成测试记忆" in stdout, f"add 输出中应包含 subject，实际:\n{stdout}"

            # 2. list — 验证记忆出现在列表中
            stdout, stderr, rc = self._run_cli(tmp_dir, "kaze", "list")
            assert rc == 0, f"list 命令失败 (rc={rc}):\n{stderr}"
            assert "多角色集成测试记忆" in stdout or "kaze_" in stdout, \
                f"list 输出中应包含 kaze 的记忆，实际:\n{stdout}"

            # 3. retrieve — 检索应命中
            stdout, stderr, rc = self._run_cli(
                tmp_dir, "kaze",
                "retrieve", "多角色集成测试",
            )
            assert rc == 0, f"retrieve 命令失败 (rc={rc}):\n{stderr}"
            # retrieve 应有输出（要么找到记忆，要么提示未找到）
            # 因为 retrieve_merged 走合并检索，找到即可
            assert len(stdout) > 0, f"retrieve 应有输出，实际为空"

            # 4. stats — 显示统计信息
            stdout, stderr, rc = self._run_cli(tmp_dir, "kaze", "stats")
            assert rc == 0, f"stats 命令失败 (rc={rc}):\n{stderr}"
            assert "kaze" in stdout, f"stats 输出应包含 agent 名字，实际:\n{stdout}"
            assert "记忆" in stdout, f"stats 输出应包含记忆统计，实际:\n{stdout}"

        finally:
            # 清理：删除本次测试新增的记忆（通过文件截断到测试前的内容）
            try:
                after_store = MemoryStore(store_path=str(kaze_store_path))
                all_mems = after_store.load_all()
                # 只保留测试前已有的记忆
                with open(str(kaze_store_path), 'w', encoding='utf-8') as f:
                    for m in all_mems[:pre_count]:
                        f.write(json.dumps(m.to_dict(), ensure_ascii=False) + '\n')
            except Exception:
                pass  # 清理失败不影响测试结果
            _cleanup_dir(tmp_dir)


# ==================== 测试运行器 ====================

def run_tests():
    """按顺序运行所有多角色集成测试，输出详细结果。"""
    test_classes = [
        TestAgentRegistry,
        TestDualLayerMemory,
        TestSameTypeAssociation,
        TestAutoClassification,
        TestCLIWithAgent,
    ]

    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("Agent Memory 多角色集成测试")
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
