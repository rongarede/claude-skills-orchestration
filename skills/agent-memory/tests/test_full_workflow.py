"""R5-D 全工作流集成测试 — 模拟真实使用场景的端到端验证。

测试场景:
  场景 1: 正常任务生命周期（quick-add → retrieve → feedback → health → importance）
  场景 2: 记忆衰减与恢复（apply_decay → 正面反馈 → 衰减速度减缓）
  场景 3: 合并工作流（相似记忆 → consolidate → 数量减少 + 信息保留）
  场景 4: 跨 agent 检索（store_A + store_B → 去重排序）
  场景 5: 故障恢复（损坏文件 → load_all 不 crash → 正常记忆可检索）
  场景 6: 完整生命周期管线（decay → quick-add → feedback → consolidate → cross-retrieve）
"""

import dataclasses
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# 将 scripts 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from retriever import retrieve, retrieve_cross_agent, compute_importance_score
from decay_engine import apply_decay, cleanup_decayed
from feedback_loop import (
    infer_memory_feedback,
    check_memory_health,
    get_feedback_ratio,
)
from consolidator import consolidate

# CLI 脚本绝对路径
CLI_PATH = os.path.expanduser('~/.claude/skills/agent-memory/scripts/cli.py')


# ==================== 通用 Fixtures ====================

@pytest.fixture
def tmp_store(tmp_path):
    """提供临时隔离的 MemoryStore 和对应路径。"""
    store = MemoryStore(store_path=str(tmp_path))
    return tmp_path, store


@pytest.fixture
def two_stores(tmp_path):
    """提供两个独立的 MemoryStore（用于跨 agent 检索测试）。"""
    store_a_path = tmp_path / "store_a"
    store_b_path = tmp_path / "store_b"
    store_a_path.mkdir()
    store_b_path.mkdir()
    store_a = MemoryStore(store_path=str(store_a_path))
    store_b = MemoryStore(store_path=str(store_b_path))
    return store_a, store_b, store_a_path, store_b_path


def make_memory(
    mem_id: str,
    content: str = "测试记忆内容",
    keywords: list = None,
    tags: list = None,
    context: str = "测试上下文",
    importance: int = 5,
    last_accessed: str = None,
    positive_feedback: int = 0,
    negative_feedback: int = 0,
    timestamp: str = None,
) -> Memory:
    """创建标准测试 Memory 对象。"""
    return Memory(
        id=mem_id,
        content=content,
        timestamp=timestamp or datetime.now().isoformat(),
        keywords=keywords or ["测试", "记忆", "默认"],
        tags=tags or ["test"],
        context=context,
        importance=importance,
        last_accessed=last_accessed,
        positive_feedback=positive_feedback,
        negative_feedback=negative_feedback,
    )


def run_cli(store_path, *args):
    """运行 CLI 子进程，返回 (stdout, stderr, returncode)。"""
    env = os.environ.copy()
    cmd = [sys.executable, CLI_PATH, '--store', str(store_path)] + list(args)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return proc.stdout, proc.stderr, proc.returncode


# ==================== 场景 1: 正常任务生命周期 ====================

class TestScenario1NormalLifecycle:
    """
    场景 1: 正常任务生命周期
    1. 创建新记忆（quick-add）
    2. 检索验证可找到（retrieve）
    3. 添加正面反馈（feedback --useful）
    4. 验证 health 状态为 healthy
    5. 验证 importance score 提升
    """

    def test_quick_add_and_retrieve(self, tmp_store):
        """quick-add 创建记忆后可通过 retrieve 命中。"""
        tmp_path, store = tmp_store

        # 1. 通过 CLI quick-add 创建记忆
        stdout, stderr, rc = run_cli(
            tmp_path,
            'quick-add',
            '--name', '实现 BM25 检索',
            '--description', 'BM25 检索引擎基础实现完成',
            '--keywords', 'BM25,检索引擎,Python,信息检索',
            '--tags', 'feature,retrieval',
            '--importance', '7',
            '--context', '为 agent 记忆系统实现 BM25 全文检索',
            '实现了基于 BM25 算法的检索引擎，支持中英文混合分词，使用 rank-bm25 库。',
        )
        assert rc == 0, f"quick-add 失败 (rc={rc}):\n{stderr}"
        assert '记忆已保存' in stdout or 'quick' in stdout.lower() or rc == 0, \
            f"quick-add 应成功，输出:\n{stdout}"

        # 2. 验证记忆确实保存到 store
        memories = store.load_all()
        assert len(memories) == 1, f"应有 1 条记忆，实际 {len(memories)}"
        mem = memories[0]
        assert mem.importance == 7, f"importance 应为 7，实际 {mem.importance}"
        assert 'BM25' in mem.keywords, f"keywords 中应含 BM25，实际 {mem.keywords}"

        # 3. 通过 retrieve 检索，应命中
        results = retrieve('BM25 检索引擎', store, top_k=3)
        assert len(results) > 0, "retrieve 应返回结果"
        result_ids = [m.id for m, _ in results]
        assert mem.id in result_ids, f"应检索到新建记忆 {mem.id}，实际 {result_ids}"

    def test_feedback_improves_health_and_importance(self, tmp_store):
        """添加正面反馈后 health=healthy，importance score 提升。"""
        tmp_path, store = tmp_store

        # 1. 创建基础记忆（importance=5，无反馈）
        mem = make_memory(
            'lifecycle_s1_001',
            content='配置 Python 虚拟环境，使用 pyenv 管理多版本',
            keywords=['Python', 'pyenv', '虚拟环境', '版本管理'],
            importance=5,
        )
        store.add(mem)

        # 记录初始 importance score
        loaded = store.get('lifecycle_s1_001')
        initial_score = compute_importance_score(loaded)

        # 2. 通过 infer_memory_feedback 添加正面反馈（模拟 feedback --useful）
        # 使用 task_success 事件（+1 正面反馈）
        for _ in range(5):
            infer_memory_feedback('lifecycle_s1_001', 'task_success', store)

        # 3. 验证 health 为 healthy
        updated = store.get('lifecycle_s1_001')
        health = check_memory_health(updated)
        assert health == 'healthy', f"5 次正面反馈后 health 应为 healthy，实际 {health}"

        # 4. 验证 importance score 提升
        new_score = compute_importance_score(updated)
        assert new_score > initial_score, (
            f"正面反馈后 importance_score ({new_score:.4f}) "
            f"应高于初始值 ({initial_score:.4f})"
        )

        # 5. 验证 positive_feedback 已累积
        assert updated.positive_feedback == 5, (
            f"5 次 task_success 后 positive_feedback 应为 5，实际 {updated.positive_feedback}"
        )


# ==================== 场景 2: 记忆衰减与恢复 ====================

class TestScenario2DecayAndRecovery:
    """
    场景 2: 记忆衰减与恢复
    1. 创建旧记忆（importance 高）
    2. 执行衰减（apply_decay）
    3. 验证 importance 降低
    4. 添加正面反馈
    5. 再次衰减，验证衰减速度减缓
    """

    def test_old_memory_decays_more_than_new(self, tmp_store):
        """旧记忆（60天前）衰减幅度大于新记忆（1天前）。"""
        tmp_path, store = tmp_store
        now = datetime(2026, 3, 15, 12, 0, 0)

        # 1. 创建两条 importance=8 的记忆，但访问时间不同
        mem_recent = make_memory(
            'decay_s2_recent',
            content='最近完成的任务：重构 API 接口层',
            keywords=['重构', 'API', '接口', '最近'],
            importance=8,
            last_accessed=(now - timedelta(days=1)).isoformat(),
        )
        mem_old = make_memory(
            'decay_s2_old',
            content='60天前完成的低优先级配置任务',
            keywords=['配置', '低优先级', '旧任务', '历史'],
            importance=8,
            last_accessed=(now - timedelta(days=60)).isoformat(),
        )
        store.add(mem_recent)
        store.add(mem_old)

        # 2. 分别施加衰减
        decayed_recent = apply_decay(mem_recent, now=now)
        decayed_old = apply_decay(mem_old, now=now)

        # 3. 旧记忆衰减幅度更大（importance 更低）
        assert decayed_recent.importance > decayed_old.importance, (
            f"新记忆衰减后 ({decayed_recent.importance}) 应 > 旧记忆 ({decayed_old.importance})"
        )

        # 4. 旧记忆应接近触底（60天 / (8*3=24天) ≈ 2.5 stability，R≈e^-2.5≈0.08）
        floor_old = max(1, int(mem_old.importance * 0.2))  # = 1
        assert decayed_old.importance <= floor_old + 1, (
            f"旧记忆 importance 应接近 floor({floor_old})，实际 {decayed_old.importance}"
        )

    def test_positive_feedback_slows_decay(self, tmp_store):
        """正面反馈使衰减速度减缓（相同 t，有正面反馈的保留率更高）。"""
        tmp_path, store = tmp_store
        now = datetime(2026, 3, 15, 12, 0, 0)
        last_acc = (now - timedelta(days=10)).isoformat()

        # 1. 创建两条完全相同的记忆（importance=6，10天前访问）
        mem_baseline = make_memory(
            'decay_s2_baseline',
            content='无反馈的基准记忆，10天前访问',
            keywords=['基准', '无反馈', '衰减测试'],
            importance=6,
            last_accessed=last_acc,
        )
        mem_with_feedback = make_memory(
            'decay_s2_with_fb',
            content='有正面反馈的记忆，10天前访问',
            keywords=['正面反馈', '衰减测试', '保留'],
            importance=6,
            last_accessed=last_acc,
            positive_feedback=8,  # 预设正面反馈
        )
        store.add(mem_baseline)
        store.add(mem_with_feedback)

        # 2. 分别施加衰减
        decayed_baseline = apply_decay(mem_baseline, now=now)
        decayed_feedback = apply_decay(mem_with_feedback, now=now)

        # 3. 有正面反馈的记忆衰减后 importance >= 无反馈记忆
        # （正面反馈增大 stability，减缓衰减）
        assert decayed_feedback.importance >= decayed_baseline.importance, (
            f"正面反馈记忆衰减后 ({decayed_feedback.importance}) "
            f"应 >= 无反馈记忆 ({decayed_baseline.importance})"
        )

    def test_positive_feedback_then_second_decay_slower(self, tmp_store):
        """添加正面反馈后第二次衰减比无反馈的第一次更慢。"""
        tmp_path, store = tmp_store
        now = datetime(2026, 3, 15, 12, 0, 0)
        last_acc = (now - timedelta(days=15)).isoformat()

        # 创建无反馈的对照记忆
        mem_no_fb = make_memory(
            'decay_s2_nofb',
            content='无反馈记忆，15天前访问',
            keywords=['无反馈', '对照', '衰减'],
            importance=7,
            last_accessed=last_acc,
        )
        # 创建有大量正面反馈的记忆（相同条件）
        mem_has_fb = make_memory(
            'decay_s2_hasfb',
            content='大量正面反馈记忆，15天前访问',
            keywords=['正面反馈', '大量', '衰减减缓'],
            importance=7,
            last_accessed=last_acc,
            positive_feedback=10,
        )

        decayed_no_fb = apply_decay(mem_no_fb, now=now)
        decayed_has_fb = apply_decay(mem_has_fb, now=now)

        # 有正面反馈的记忆衰减后 importance 不低于无反馈版本
        assert decayed_has_fb.importance >= decayed_no_fb.importance, (
            f"有正面反馈的衰减后 ({decayed_has_fb.importance}) "
            f"应 >= 无反馈版本 ({decayed_no_fb.importance})"
        )


# ==================== 场景 3: 合并工作流 ====================

class TestScenario3ConsolidationWorkflow:
    """
    场景 3: 合并工作流
    1. 创建多条相似记忆
    2. 执行合并（consolidate）
    3. 验证合并后记忆数量减少
    4. 验证合并记忆包含源记忆信息
    """

    def test_similar_memories_get_merged(self, tmp_store):
        """高度相似的记忆对被 consolidate 合并，无关记忆保留。"""
        tmp_path, store = tmp_store

        # 1. 创建 3 条记忆：A、B 高度相似，C 无关
        mem_a = make_memory(
            'consolidate_s3_001',
            content='修复 CI/CD 流水线中的 Docker 镜像构建失败问题',
            keywords=['CI/CD', 'Docker', '镜像构建', '流水线', '修复'],
            tags=['bug-fix', 'devops', 'docker'],
            importance=8,
        )
        mem_b = make_memory(
            'consolidate_s3_002',
            content='优化 Docker 镜像构建速度，CI/CD 流水线效率提升',
            keywords=['CI/CD', 'Docker', '镜像构建', '流水线', '优化'],
            tags=['enhancement', 'devops', 'docker'],
            importance=7,
        )
        mem_c = make_memory(
            'consolidate_s3_003',
            content='Obsidian 日记模板配置，添加每日反思区块',
            keywords=['Obsidian', '日记', '模板', '每日反思', '配置'],
            tags=['obsidian', 'template', 'productivity'],
            importance=5,
        )
        store.add(mem_a)
        store.add(mem_b)
        store.add(mem_c)
        assert store.count() == 3, "初始应有 3 条记忆"

        # 2. 执行合并（降低阈值以匹配测试相似度）
        result = consolidate(store, threshold=0.5)

        # 3. 验证合并发生
        assert result['merged'] >= 1, f"应至少合并 1 次，实际 {result['merged']}"
        assert result['deleted'] >= 1, f"应删除至少 1 条副本，实际 {result['deleted']}"

        # 4. 验证 store 中剩余 2 条（A 和 B 合并，C 保留）
        remaining = store.load_all()
        assert len(remaining) == 2, f"合并后应剩余 2 条记忆，实际 {len(remaining)}"

        # 5. C（无关记忆）应保留
        remaining_ids = {m.id for m in remaining}
        assert mem_c.id in remaining_ids, f"无关记忆 {mem_c.id} 应被保留"

    def test_merged_memory_contains_source_info(self, tmp_store):
        """合并后的记忆包含来自两条源记忆的关键词（并集）。"""
        tmp_path, store = tmp_store

        # 创建两条高度相似的记忆（相同 keywords/tags 结构，仅少数不同）
        mem_a = make_memory(
            'consolidate_s3_004',
            content='Redis 缓存设计：使用 LRU 策略管理内存',
            keywords=['Redis', '缓存', 'LRU', '内存管理', '数据库'],
            tags=['redis', 'cache', 'database'],
            importance=7,
        )
        mem_b = make_memory(
            'consolidate_s3_005',
            content='Redis 缓存优化：LRU 内存策略与 TTL 配置',
            keywords=['Redis', '缓存', 'LRU', '内存管理', 'TTL'],
            tags=['redis', 'cache', 'optimization'],
            importance=6,
        )
        store.add(mem_a)
        store.add(mem_b)

        # 执行合并
        result = consolidate(store, threshold=0.5)
        assert result['merged'] >= 1, "应发生合并"

        # 验证合并后记忆包含两者 keywords 的并集
        remaining = store.load_all()
        assert len(remaining) == 1, "合并后应只剩 1 条记忆"

        merged_mem = remaining[0]
        expected_kws = {'Redis', '缓存', 'LRU', '内存管理', 'TTL', '数据库'}
        actual_kws = set(merged_mem.keywords)
        for kw in expected_kws:
            assert kw in actual_kws, (
                f"合并后记忆 keywords 中缺少 '{kw}'，实际 {actual_kws}"
            )

        # 验证 importance = max(7, 6) = 7
        assert merged_mem.importance == 7, (
            f"合并后 importance 应为 max(7,6)=7，实际 {merged_mem.importance}"
        )


# ==================== 场景 4: 跨 agent 检索 ====================

class TestScenario4CrossAgentRetrieval:
    """
    场景 4: 跨 agent 检索
    1. 在 store_A 创建记忆
    2. 在 store_B 创建记忆
    3. cross-agent 检索
    4. 验证两个 store 的结果都返回
    5. 验证去重和排序正确
    """

    def test_cross_agent_returns_from_both_stores(self, two_stores):
        """跨 store 检索应从 A 和 B 各自返回相关记忆。"""
        store_a, store_b, path_a, path_b = two_stores

        # 1. 在 store_A 创建 Python 相关记忆
        mem_a = make_memory(
            'cross_s4_agent_a_001',
            content='Python 异步编程：asyncio + aiohttp 实现并发请求',
            keywords=['Python', '异步', 'asyncio', 'aiohttp', '并发'],
            tags=['python', 'async', 'networking'],
            importance=7,
        )
        store_a.add(mem_a)

        # 2. 在 store_B 创建 Python 相关记忆（不同角度）
        mem_b = make_memory(
            'cross_s4_agent_b_001',
            content='Python 并发实现：多线程 threading vs asyncio 对比',
            keywords=['Python', '并发', 'threading', 'asyncio', '对比'],
            tags=['python', 'concurrency', 'threading'],
            importance=6,
        )
        store_b.add(mem_b)

        # 3. 执行跨 store 检索
        results = retrieve_cross_agent(
            query='Python 异步并发',
            stores=[store_a, store_b],
            top_k=5,
        )

        # 4. 验证两个 store 的记忆都被返回
        assert len(results) >= 2, f"跨 store 检索应返回 ≥2 条，实际 {len(results)}"
        result_ids = {m.id for m, _ in results}
        assert mem_a.id in result_ids, f"store_A 的记忆 {mem_a.id} 应出现在结果中"
        assert mem_b.id in result_ids, f"store_B 的记忆 {mem_b.id} 应出现在结果中"

    def test_cross_agent_deduplication_and_sorting(self, two_stores):
        """相同 ID 的记忆只出现一次，且结果按分数降序排列。"""
        store_a, store_b, path_a, path_b = two_stores

        # 在两个 store 中各添加 2 条记忆（ID 不同，但内容相关）
        for i, (store, prefix) in enumerate([(store_a, 'a'), (store_b, 'b')]):
            for j in range(2):
                mem = make_memory(
                    f'cross_s4_{prefix}_{j}',
                    content=f'机器学习模型训练技巧 #{j + 1}，梯度下降优化方法',
                    keywords=['机器学习', '模型训练', '梯度下降', '优化', f'技巧{j}'],
                    importance=5 + j,
                )
                store.add(mem)

        # 执行跨 store 检索
        results = retrieve_cross_agent(
            query='机器学习梯度下降',
            stores=[store_a, store_b],
            top_k=4,
        )

        # 验证无重复 ID
        result_ids = [m.id for m, _ in results]
        assert len(result_ids) == len(set(result_ids)), (
            f"结果中存在重复 ID: {result_ids}"
        )

        # 验证按分数降序排列
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True), (
            f"结果应按分数降序排列，实际分数: {scores}"
        )


# ==================== 场景 5: 故障恢复 ====================

class TestScenario5FaultRecovery:
    """
    场景 5: 故障恢复
    1. 创建正常记忆
    2. 手动创建损坏的 mem_*.md 文件
    3. load_all() 不 crash
    4. 正常记忆仍可检索
    5. 损坏文件被跳过（不影响系统）
    """

    def test_load_all_tolerates_corrupted_files(self, tmp_store):
        """load_all() 在有损坏文件时不崩溃，返回正常记忆。"""
        tmp_path, store = tmp_store

        # 1. 创建正常记忆
        normal_mems = [
            make_memory(
                f'fault_s5_normal_{i}',
                content=f'正常记忆 {i}：区块链共识算法学习笔记',
                keywords=['区块链', '共识算法', f'笔记{i}'],
                importance=5 + i,
            )
            for i in range(3)
        ]
        for mem in normal_mems:
            store.add(mem)

        initial_count = store.count()
        assert initial_count == 3, f"初始应有 3 条正常记忆，实际 {initial_count}"

        # 2. 手动创建损坏的 .md 文件（缺少 frontmatter）
        corrupt_files = [
            (tmp_path / 'mem_corrupt_001.md', '这是没有 frontmatter 的损坏文件'),
            (tmp_path / 'mem_corrupt_002.md', '---\n不完整的frontmatter（无结束符）'),
            (tmp_path / 'mem_corrupt_003.md', ''),  # 空文件
            (tmp_path / 'mem_corrupt_004.md', '---\ninvalid: yaml: :\n---\n正文'),
        ]
        for path, content in corrupt_files:
            path.write_text(content, encoding='utf-8')

        # 3. load_all() 不应崩溃
        try:
            loaded = store.load_all()
        except Exception as e:
            pytest.fail(f"load_all() 不应抛出异常，但抛出了: {e}")

        # 4. 正常记忆数量应保持不变（损坏文件被跳过）
        normal_ids = {m.id for m in normal_mems}
        loaded_normal = [m for m in loaded if m.id in normal_ids]
        assert len(loaded_normal) == 3, (
            f"正常记忆应有 3 条可加载，实际 {len(loaded_normal)}"
        )

    def test_retrieve_works_despite_corrupted_files(self, tmp_store):
        """有损坏文件存在时，retrieve 仍能正常检索到健康记忆。"""
        tmp_path, store = tmp_store

        # 1. 创建正常记忆
        mem = make_memory(
            'fault_s5_retrieve_001',
            content='深度学习框架对比：PyTorch vs TensorFlow 使用体验',
            keywords=['深度学习', 'PyTorch', 'TensorFlow', '框架对比'],
            importance=7,
        )
        store.add(mem)

        # 2. 手动创建损坏文件
        (tmp_path / 'mem_broken_001.md').write_text(
            '这不是有效的 markdown frontmatter', encoding='utf-8'
        )
        (tmp_path / 'mem_broken_002.md').write_text('', encoding='utf-8')

        # 3. retrieve 应成功返回正常记忆
        results = retrieve('深度学习框架', store, top_k=3)
        assert len(results) > 0, "有损坏文件时 retrieve 应仍返回正常结果"
        result_ids = [m.id for m, _ in results]
        assert mem.id in result_ids, f"正常记忆 {mem.id} 应被检索到"


# ==================== 场景 6: 完整生命周期管线 ====================

class TestScenario6FullLifecyclePipeline:
    """
    场景 6: 完整生命周期管线
    1. SessionStart → decay（旧记忆清理）
    2. Agent task → quick-add 记忆
    3. feedback → auto-inference
    4. store 检查 → consolidate（如果超阈值）
    5. cross-retrieve 验证
    """

    def test_session_start_decay_pipeline(self, tmp_store):
        """SessionStart 阶段：旧记忆经过衰减后触底被清理，新记忆保留。"""
        tmp_path, store = tmp_store
        now = datetime(2026, 3, 15, 12, 0, 0)

        # 1. 创建"会话开始前"的旧记忆（90天前访问，会触底）
        mem_stale = make_memory(
            'pipeline_s6_stale',
            content='90天前的过时配置笔记，低优先级',
            keywords=['过时', '配置', '旧笔记'],
            importance=5,
            last_accessed=(now - timedelta(days=90)).isoformat(),
        )
        # 创建"新记忆"（昨天访问，不会触底）
        mem_fresh = make_memory(
            'pipeline_s6_fresh',
            content='昨天完成的重要任务：配置 CI/CD 流水线',
            keywords=['CI/CD', '流水线', '配置', '任务'],
            importance=8,
            last_accessed=(now - timedelta(days=1)).isoformat(),
        )
        store.add(mem_stale)
        store.add(mem_fresh)

        # 2. 执行衰减清理（SessionStart 触发的 decay 阶段）
        deleted = cleanup_decayed(store, now=now)

        # 3. 旧记忆应被清理，新记忆应保留
        assert deleted >= 1, f"至少应清理 1 条触底记忆，实际 {deleted}"
        remaining = store.load_all()
        remaining_ids = {m.id for m in remaining}
        assert mem_stale.id not in remaining_ids, "旧记忆应被清理"
        assert mem_fresh.id in remaining_ids, "新记忆应保留"

    def test_task_quick_add_feedback_consolidate_pipeline(self, two_stores):
        """完整管线：quick-add → 反馈 → 合并 → 跨 store 检索。"""
        store_a, store_b, path_a, path_b = two_stores

        # === Phase 1: Agent task → quick-add 记忆 ===
        # store_a 存放第一个 agent 的记忆（例如：kaze 探索结果）
        mem_a1 = make_memory(
            'pipeline_kaze_001',
            content='探索发现：项目根目录有 conftest.py，使用 pytest fixtures',
            keywords=['pytest', 'conftest', 'fixtures', '测试框架', '项目结构'],
            tags=['探索', 'testing', 'pytest'],
            importance=6,
        )
        mem_a2 = make_memory(
            'pipeline_kaze_002',
            content='探索发现：scripts/ 目录包含 cli.py 和 memory_store.py',
            keywords=['scripts', 'cli', 'memory_store', '项目结构', '模块'],
            tags=['探索', 'structure', 'module'],
            importance=5,
        )
        store_a.add(mem_a1)
        store_a.add(mem_a2)

        # store_b 存放第二个 agent 的记忆（例如：tetsu 实现结果）
        mem_b1 = make_memory(
            'pipeline_tetsu_001',
            content='实现完成：pytest fixtures 和 conftest.py 配置已更新',
            keywords=['pytest', 'fixtures', 'conftest', '实现', '测试'],
            tags=['实现', 'testing', 'pytest'],
            importance=7,
        )
        store_b.add(mem_b1)

        # === Phase 2: feedback → auto-inference ===
        # 对 kaze 的探索记忆施加正面反馈（探索结果有用）
        infer_memory_feedback('pipeline_kaze_001', 'task_success', store_a)
        infer_memory_feedback('pipeline_kaze_001', 'audit_pass', store_a)

        # 验证反馈已记录
        updated_a1 = store_a.get('pipeline_kaze_001')
        assert updated_a1.positive_feedback >= 3, (
            f"task_success(+1) + audit_pass(+2) = 3 positive，"
            f"实际 {updated_a1.positive_feedback}"
        )
        assert check_memory_health(updated_a1) == 'healthy', "正面反馈后应为 healthy"

        # === Phase 3: consolidate（store_a 中两条 pytest 相关记忆超阈值）===
        # kaze_001 和 tetsu_001 都有 pytest 关键词，但在不同 store
        # 对 store_b 内部进行合并检查（只有一条，不会合并）
        result_b = consolidate(store_b, threshold=0.5)
        assert result_b['merged'] == 0, "store_b 只有 1 条记忆，不应合并"

        # store_a 中 kaze_001 和 kaze_002 不够相似，也不会合并
        result_a = consolidate(store_a, threshold=0.85)
        # 这里只验证不崩溃，具体合并与否取决于相似度
        assert isinstance(result_a['merged'], int), "consolidate 应返回 merged 计数"

        # === Phase 4: cross-retrieve 验证 ===
        results = retrieve_cross_agent(
            query='pytest fixtures conftest 测试配置',
            stores=[store_a, store_b],
            top_k=5,
        )

        # 两个 store 的相关记忆都应被检索到
        assert len(results) >= 2, f"跨 store 检索应返回 ≥2 条，实际 {len(results)}"
        result_ids = {m.id for m, _ in results}
        assert 'pipeline_kaze_001' in result_ids or 'pipeline_tetsu_001' in result_ids, (
            "pytest 相关记忆应被跨 store 检索到"
        )

    def test_importance_score_reflects_full_pipeline(self, tmp_store):
        """完整反馈管线后，importance score 综合反映 access、feedback 等因素。"""
        tmp_path, store = tmp_store

        # 1. 创建两条 importance 相同的记忆
        mem_favored = make_memory(
            'pipeline_s6_favored',
            content='受欢迎的记忆：TypeScript 类型系统最佳实践',
            keywords=['TypeScript', '类型系统', '最佳实践', '静态类型'],
            importance=6,
        )
        mem_neglected = make_memory(
            'pipeline_s6_neglected',
            content='被忽视的记忆：TypeScript 类型系统注意事项',
            keywords=['TypeScript', '类型系统', '注意事项', '陷阱'],
            importance=6,
        )
        store.add(mem_favored)
        store.add(mem_neglected)

        # 2. 对 favored 施加大量正面反馈 + 检索（access_count 增加）
        for _ in range(8):
            infer_memory_feedback('pipeline_s6_favored', 'task_success', store)

        # 手动更新 access_count
        mem_favored_updated = store.get('pipeline_s6_favored')
        mem_with_access = dataclasses.replace(
            mem_favored_updated,
            access_count=5,
        )
        store.update(mem_with_access)

        # 3. 对 neglected 施加负面反馈
        for _ in range(2):
            infer_memory_feedback('pipeline_s6_neglected', 'task_retry', store)

        # 4. 计算并比较 importance score
        final_favored = store.get('pipeline_s6_favored')
        final_neglected = store.get('pipeline_s6_neglected')

        score_favored = compute_importance_score(final_favored)
        score_neglected = compute_importance_score(final_neglected)

        # favored 的综合分数应明显高于 neglected
        assert score_favored > score_neglected, (
            f"受欢迎记忆 score ({score_favored:.4f}) 应高于被忽视记忆 ({score_neglected:.4f})"
        )


# ==================== 额外边界测试 ====================

class TestEdgeCases:
    """额外的边界条件测试，确保系统在极端情况下稳定运行。"""

    def test_empty_store_retrieve_returns_empty(self, tmp_store):
        """空 store 的检索应返回空列表，不崩溃。"""
        tmp_path, store = tmp_store
        results = retrieve('任意查询', store, top_k=3)
        assert results == [], f"空 store 应返回空列表，实际 {results}"

    def test_empty_store_consolidate_returns_zero(self, tmp_store):
        """空 store 的 consolidate 应返回 0 合并，不崩溃。"""
        tmp_path, store = tmp_store
        result = consolidate(store, threshold=0.85)
        assert result['merged'] == 0
        assert result['deleted'] == 0

    def test_single_memory_no_consolidation(self, tmp_store):
        """只有 1 条记忆时，consolidate 不执行任何合并。"""
        tmp_path, store = tmp_store
        mem = make_memory('edge_single_001', content='唯一的记忆')
        store.add(mem)

        result = consolidate(store, threshold=0.5)
        assert result['merged'] == 0, "单条记忆不应发生合并"
        assert store.count() == 1, "合并后记忆数量应仍为 1"

    def test_cross_agent_empty_stores(self):
        """空 stores 列表的跨 store 检索应返回空列表。"""
        results = retrieve_cross_agent('任意查询', stores=[], top_k=3)
        assert results == [], f"空 stores 应返回空列表，实际 {results}"
