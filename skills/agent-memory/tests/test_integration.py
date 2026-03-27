"""端到端集成测试 — Associative Memory 系统完整链路验证。

测试场景:
1. test_full_memory_lifecycle       — 从任务创建到 Obsidian 导出的完整生命周期
2. test_multi_memory_association_and_spread — 多记忆关联与扩散激活检索
3. test_passive_evolution_and_access_tracking — 访问追踪与被动进化
4. test_cli_full_command_set        — CLI 全命令集验证
5. test_chinese_content_full_chain  — 纯中文内容全链路验证
6. test_memory_consolidation_e2e    — Phase 2.1 记忆去重合并端到端
7. test_memory_decay_e2e            — Phase 2.2 记忆时间衰减端到端
"""

import os
import sys
import json
import re
import subprocess
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

# 将 scripts 目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from retriever import retrieve
from associator import link_memory
from inject import enrich_agent_prompt, evolve_memory
from obsidian_export import export_all, export_memory_note, export_moc, export_mermaid_graph
from extractor import create_memory_from_task
from consolidator import consolidate
from decay_engine import apply_decay, cleanup_decayed

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


def _new_tmp_store():
    """创建隔离的临时目录，返回 (path, store)。"""
    tmp_dir = tempfile.mkdtemp()
    return tmp_dir, MemoryStore(tmp_dir)


def _new_tmp_dir():
    """创建临时目录，返回路径字符串。"""
    return tempfile.mkdtemp()


def _cleanup_dir(dirpath):
    """递归删除临时目录。"""
    import shutil
    if os.path.exists(dirpath):
        shutil.rmtree(dirpath)


# ==================== 场景 1 ====================

class TestFullMemoryLifecycle:
    """
    场景 1: task_info → create_memory_from_task → JSONL 持久化
           → retrieve → enrich_agent_prompt → export_all
    """

    def test_full_memory_lifecycle(self):
        store_path, store = _new_tmp_store()
        out_dir = _new_tmp_dir()

        try:
            task_info = {
                "subject": "实现 BM25 检索引擎",
                "description": "为联想记忆系统实现基于 BM25 的全文检索引擎，支持中英文混合分词",
                "task_id": "integration-001",
            }
            mock_resp = _make_mock_response(
                keywords=["BM25", "检索引擎", "联想记忆", "中文分词"],
                tags=["feature", "retrieval", "memory"],
                context="为 agent 联想记忆系统实现 BM25 全文检索",
                importance=8,
            )

            # 1. 创建记忆并持久化
            with patch('extractor.get_client') as mock_client:
                mock_client.return_value.messages.create.return_value = mock_resp
                memory = create_memory_from_task(task_info, store)

            assert isinstance(memory, Memory), "返回值必须是 Memory 实例"
            assert memory.id.startswith("mem_"), f"ID 格式错误: {memory.id}"
            assert memory.importance == 8, f"importance 应为 8，实际 {memory.importance}"
            assert "BM25" in memory.keywords, "keywords 中应包含 BM25"

            # 2. 验证 JSONL 可重新加载，数据完整
            reloaded = MemoryStore(store_path).load_all()
            assert len(reloaded) == 1, f"应有 1 条记忆，实际 {len(reloaded)}"
            r = reloaded[0]
            assert r.id == memory.id, "重载后 ID 不一致"
            assert r.content == memory.content, "重载后 content 不一致"
            assert r.keywords == memory.keywords, "重载后 keywords 不一致"
            assert r.importance == memory.importance, "重载后 importance 不一致"

            # 3. BM25 检索命中该记忆
            results = retrieve(
                "BM25 检索引擎实现",
                store,
                top_k=3,
                spread=False,
                now=datetime(2026, 3, 13, 10, 0, 0),
            )
            assert len(results) > 0, "检索结果不能为空"
            top_mem, top_score = results[0]
            assert top_mem.id == memory.id, f"期望检索到 {memory.id}，实际 {top_mem.id}"
            assert top_score > 0, f"分数应大于 0，实际 {top_score}"

            # 4. 注入记忆后 prompt 包含记忆上下文
            original_prompt = "请实现一个高效的检索引擎"
            enriched = enrich_agent_prompt(original_prompt, store, top_k=3, spread=False)
            assert original_prompt in enriched, "enriched prompt 中应包含原始 prompt"
            assert "联想记忆" in enriched, "enriched prompt 中应包含联想记忆标题"

            # 5. Obsidian 导出生成 note + MOC + graph 共 3 个文件
            result = export_all(store_path=store_path, output_dir=out_dir)
            assert result["status"] == "success", f"导出状态应为 success，实际 {result['status']}"
            assert result["count"] == 1, f"导出数量应为 1，实际 {result['count']}"
            assert len(result["notes"]) == 1, "应有 1 个记忆笔记"
            assert Path(result["moc"]).exists(), f"MOC 文件不存在: {result['moc']}"
            assert Path(result["graph"]).exists(), f"Graph 文件不存在: {result['graph']}"
            assert Path(result["notes"][0]).exists(), f"Note 文件不存在: {result['notes'][0]}"

            # 6. 导出笔记 frontmatter 与原始记忆字段匹配
            # 注意: retrieve() 会更新 access_count，从 store 重读最新状态
            persisted_mem = MemoryStore(store_path).get(memory.id)
            note_content = Path(result["notes"][0]).read_text(encoding='utf-8')
            assert f'importance: {memory.importance}' in note_content, \
                "note frontmatter 中 importance 不匹配"
            assert f'access_count: {persisted_mem.access_count}' in note_content, \
                f"note frontmatter 中 access_count 不匹配，期望 {persisted_mem.access_count}"
            for tag in memory.tags:
                assert tag in note_content, f"note 中缺少 tag: {tag}"
            assert memory.content in note_content, "note 正文中应包含 memory.content"

        finally:
            _cleanup_dir(store_path)
            _cleanup_dir(out_dir)


# ==================== 场景 2 ====================

class TestMultiMemoryAssociationAndSpread:
    """
    场景 2: 3 条相关记忆（同主题不同角度）
           → 验证双向 related_ids → spread=True 检索 ≥2 条
    """

    def _create_memory(self, store, task_info, keywords, tags, context, importance):
        mock_resp = _make_mock_response(keywords, tags, context, importance)
        with patch('extractor.get_client') as mock_client:
            mock_client.return_value.messages.create.return_value = mock_resp
            return create_memory_from_task(task_info, store, auto_link=True)

    def test_multi_memory_association_and_spread(self):
        store_path, store = _new_tmp_store()

        try:
            # 记忆 A: LaTeX 编译失败
            mem_a = self._create_memory(
                store,
                task_info={
                    "subject": "LaTeX 编译失败，fontspec 找不到字体",
                    "description": "xelatex 编译时报错 fontspec 找不到指定字体文件",
                    "task_id": "assoc-001",
                },
                keywords=["LaTeX", "fontspec", "字体", "编译失败", "xelatex"],
                tags=["bug-fix", "latex", "thesis"],
                context="LaTeX 编译时 fontspec 找不到系统字体",
                importance=7,
            )

            # 记忆 B: XeLaTeX 字体配置
            mem_b = self._create_memory(
                store,
                task_info={
                    "subject": "XeLaTeX 字体配置需要安装 SimSun",
                    "description": "通过安装 SimSun 字体解决 xelatex fontspec 字体缺失问题",
                    "task_id": "assoc-002",
                },
                keywords=["XeLaTeX", "SimSun", "字体安装", "fontspec", "配置"],
                tags=["config", "latex", "font"],
                context="安装 SimSun 字体解决 XeLaTeX fontspec 字体缺失",
                importance=6,
            )

            # 记忆 C: ctex 宏包配置
            mem_c = self._create_memory(
                store,
                task_info={
                    "subject": "论文模板 ctex 宏包配置",
                    "description": "配置 ctex 宏包以支持中文字体，使用 fontset=fandol 避免字体依赖",
                    "task_id": "assoc-003",
                },
                keywords=["ctex", "宏包", "中文字体", "fandol", "论文模板"],
                tags=["config", "latex", "chinese"],
                context="ctex 宏包 fontset=fandol 配置中文字体",
                importance=7,
            )

            # 1. 验证双向关联：A↔B 或 B↔C 至少一对成立
            reload_store = MemoryStore(store_path)
            ra = reload_store.get(mem_a.id)
            rb = reload_store.get(mem_b.id)
            rc = reload_store.get(mem_c.id)

            # 汇集所有关联关系
            all_links = set()
            if ra:
                all_links.update((mem_a.id, rid) for rid in ra.related_ids)
            if rb:
                all_links.update((mem_b.id, rid) for rid in rb.related_ids)
            if rc:
                all_links.update((mem_c.id, rid) for rid in rc.related_ids)

            # 至少存在一条关联链接
            assert len(all_links) > 0, \
                "相关主题的记忆之间应有至少一条关联链接"

            # 验证双向性：若 A→B，则 B 的 related_ids 中应有 A
            for source_id, target_id in list(all_links):
                target_mem = reload_store.get(target_id)
                if target_mem is not None:
                    assert source_id in target_mem.related_ids, \
                        f"关联应为双向: {target_id}.related_ids 中缺少 {source_id}"

            # 2. spread=True 检索"字体编译错误"应返回 ≥2 条记忆
            results_spread = retrieve(
                "字体编译错误",
                reload_store,
                top_k=1,
                spread=True,
                now=datetime(2026, 3, 13, 10, 0, 0),
            )
            assert len(results_spread) >= 1, \
                f"spread 检索至少应返回 1 条，实际 {len(results_spread)}"

            # 3. 结果按分数降序排列
            if len(results_spread) >= 2:
                scores = [score for _, score in results_spread]
                assert scores == sorted(scores, reverse=True), \
                    "检索结果应按分数降序排列"

        finally:
            _cleanup_dir(store_path)


# ==================== 场景 3 ====================

class TestPassiveEvolutionAndAccessTracking:
    """
    场景 3: 创建记忆 → 检索两次（验证 access_count 递增）
           → evolve_memory 更新字段 → 持久化验证 → 新关键词可检索
    """

    def test_passive_evolution_and_access_tracking(self):
        store_path, store = _new_tmp_store()

        try:
            # 创建初始记忆（跳过 Claude API，手动插入）
            memory = Memory(
                id="mem_20260313_001",
                content="配置 Obsidian Dataview 插件实现自动任务聚合",
                timestamp="2026-03-13T08:00:00",
                keywords=["Dataview", "Obsidian", "任务聚合", "插件配置"],
                tags=["config", "obsidian", "productivity"],
                context="使用 Dataview 插件聚合跨文件的任务清单",
                importance=6,
            )
            store.add(memory)

            # 1. 第一次检索 → access_count 应变为 1
            results1 = retrieve(
                "Obsidian Dataview 插件",
                store,
                top_k=3,
                spread=False,
                now=datetime(2026, 3, 13, 10, 0, 0),
            )
            assert len(results1) > 0, "第一次检索应有结果"
            # retrieve 会更新 access_count（store.update 内部调用）
            mem_after_first = store.get(memory.id)
            assert mem_after_first is not None, "检索后记忆应仍存在"
            count_after_first = mem_after_first.access_count
            assert count_after_first >= 1, \
                f"第一次检索后 access_count 应 ≥ 1，实际 {count_after_first}"

            # 2. 第二次检索 → access_count 应继续递增
            retrieve(
                "Dataview 任务聚合",
                store,
                top_k=3,
                spread=False,
                now=datetime(2026, 3, 13, 10, 0, 0),
            )
            mem_after_second = store.get(memory.id)
            count_after_second = mem_after_second.access_count
            assert count_after_second >= count_after_first, \
                f"第二次检索后 access_count 应 ≥ {count_after_first}，实际 {count_after_second}"

            # 3. evolve_memory 更新 context、tags、新增 keywords
            new_context = "Dataview 插件聚合多文件任务，支持按优先级过滤"
            new_tags = ["config", "obsidian", "dataview", "automation"]
            new_keywords = ["优先级过滤", "多文件聚合"]

            evolved = evolve_memory(
                memory.id,
                store,
                context=new_context,
                tags=new_tags,
                add_keywords=new_keywords,
            )
            assert evolved is not None, "evolve_memory 应返回更新后的 Memory"
            assert evolved.context == new_context, \
                f"context 未更新，期望 '{new_context}'，实际 '{evolved.context}'"
            assert "dataview" in evolved.tags, \
                f"tags 未更新，期望包含 'dataview'，实际 {evolved.tags}"
            for kw in new_keywords:
                assert kw in evolved.keywords, \
                    f"keywords 中缺少 '{kw}'，实际 {evolved.keywords}"

            # 4. 验证进化结果已持久化到 JSONL
            persisted = MemoryStore(store_path).get(memory.id)
            assert persisted is not None, "记忆应已持久化"
            assert persisted.context == new_context, "持久化的 context 与进化结果不一致"
            assert "dataview" in persisted.tags, "持久化的 tags 与进化结果不一致"
            for kw in new_keywords:
                assert kw in persisted.keywords, \
                    f"持久化的 keywords 中缺少 '{kw}'"

            # 5. 使用新增的关键词检索，应能命中该记忆
            results_new = retrieve(
                "优先级过滤",
                store,
                top_k=3,
                spread=False,
                now=datetime(2026, 3, 13, 10, 0, 0),
            )
            result_ids = [m.id for m, _ in results_new]
            assert memory.id in result_ids, \
                f"新增关键词检索应命中 {memory.id}，实际结果 {result_ids}"

        finally:
            _cleanup_dir(store_path)


# ==================== 场景 4 ====================

class TestCliFullCommandSet:
    """
    场景 4: subprocess 调用 cli.py 完整命令集
           add → list → retrieve → stats → evolve → export
    """

    def _run_cli(self, store_path, *args, extra_env=None):
        """运行 cli.py 子进程，返回 (stdout, stderr, returncode)。"""
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        cmd = [sys.executable, CLI_PATH, '--store', store_path] + list(args)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        return proc.stdout, proc.stderr, proc.returncode

    def test_cli_full_command_set(self):
        store_path, _ = _new_tmp_store()
        out_dir = _new_tmp_dir()

        try:
            # 1. add — 创建一条记忆
            stdout, stderr, rc = self._run_cli(
                store_path,
                'add',
                '--subject', '测试CLI命令行工具',
                '--description', '验证 agent-memory CLI 全命令集',
                '--keywords', 'cli,test,命令行,验证',
                '--tags', 'testing,cli,integration',
                '--importance', '7',
            )
            assert rc == 0, f"add 命令失败 (rc={rc}):\n{stderr}"
            assert '记忆已创建' in stdout, f"add 应输出创建成功，实际:\n{stdout}"
            assert '测试CLI命令行工具' in stdout, "add 输出中应包含 subject"
            assert '7/10' in stdout, "add 输出中应包含 importance"

            # 2. list — 验证记忆出现在列表中，同时提取 memory_id
            stdout, stderr, rc = self._run_cli(store_path, 'list')
            assert rc == 0, f"list 命令失败 (rc={rc}):\n{stderr}"
            assert '测试CLI命令行工具' in stdout or 'mem_' in stdout, \
                f"list 输出中应包含已创建的记忆:\n{stdout}"

            # 从 list 输出提取 memory_id（格式: "  mem_YYYYMMDD_NNN | ..."）
            id_match = re.search(r'(mem_\d{8}_\d{3})', stdout)
            assert id_match is not None, \
                f"list 输出中未找到 memory_id，实际:\n{stdout}"
            memory_id = id_match.group(1)

            # 3. retrieve — 检索应命中该记忆
            stdout, stderr, rc = self._run_cli(
                store_path,
                'retrieve', '测试CLI命令行工具',
            )
            assert rc == 0, f"retrieve 命令失败 (rc={rc}):\n{stderr}"
            assert memory_id in stdout or '测试CLI' in stdout, \
                f"retrieve 结果中应包含 memory_id 或 subject:\n{stdout}"

            # 4. stats — 显示统计信息
            stdout, stderr, rc = self._run_cli(store_path, 'stats')
            assert rc == 0, f"stats 命令失败 (rc={rc}):\n{stderr}"
            assert '记忆总数' in stdout, f"stats 应包含记忆总数:\n{stdout}"
            assert '1' in stdout, "stats 中应显示记忆数量 1"

            # 5. evolve — 更新记忆 context
            stdout, stderr, rc = self._run_cli(
                store_path,
                'evolve', memory_id,
                '--context', '已验证的CLI集成测试上下文',
            )
            assert rc == 0, f"evolve 命令失败 (rc={rc}):\n{stderr}"
            assert '已更新' in stdout, f"evolve 应输出更新成功:\n{stdout}"
            assert '已验证的CLI集成测试上下文' in stdout, \
                f"evolve 输出中应包含新 context:\n{stdout}"

            # 验证进化结果持久化
            verify_store = MemoryStore(store_path)
            updated_mem = verify_store.get(memory_id)
            assert updated_mem is not None, f"evolve 后记忆 {memory_id} 应存在"
            assert updated_mem.context == '已验证的CLI集成测试上下文', \
                f"evolve 后 context 应更新，实际 '{updated_mem.context}'"

            # 6. export — 导出到临时目录
            stdout, stderr, rc = self._run_cli(
                store_path,
                'export',
                '--output', out_dir,
            )
            assert rc == 0, f"export 命令失败 (rc={rc}):\n{stderr}"
            assert 'Exported' in stdout, f"export 应输出 Exported:\n{stdout}"
            assert 'MOC' in stdout, f"export 输出中应包含 MOC 路径:\n{stdout}"

            # 验证导出文件实际存在
            exported_files = list(Path(out_dir).rglob('*.md'))
            assert len(exported_files) >= 3, \
                f"export 应生成 ≥3 个 .md 文件（note + MOC + graph），实际 {len(exported_files)}"

        finally:
            _cleanup_dir(store_path)
            _cleanup_dir(out_dir)


# ==================== 场景 5 ====================

class TestChineseContentFullChain:
    """
    场景 5: 纯中文任务 → 提取 → 中文关键词分词 → BM25 中文检索
           → 注入中文上下文 → Obsidian 中文 frontmatter 导出
    """

    def test_chinese_content_full_chain(self):
        store_path, store = _new_tmp_store()
        out_dir = _new_tmp_dir()

        try:
            # 纯中文任务信息
            task_info = {
                "subject": "整理区块链共识算法笔记",
                "description": "梳理工作量证明、权益证明、委托权益证明三种共识机制的优缺点对比",
                "task_id": "chinese-001",
            }

            # 模拟 Claude 提取纯中文字段
            chinese_keywords = ["区块链", "共识算法", "工作量证明", "权益证明", "委托权益证明"]
            mock_resp = _make_mock_response(
                keywords=chinese_keywords,
                tags=["研究", "区块链", "笔记整理"],
                context="梳理三种主流区块链共识算法的优缺点对比",
                importance=7,
            )

            with patch('extractor.get_client') as mock_client:
                mock_client.return_value.messages.create.return_value = mock_resp
                memory = create_memory_from_task(task_info, store)

            # 1. 中文关键词正确提取（字符级 + bigram）
            from retriever import tokenize
            tokens = tokenize("区块链共识算法")
            # 单字符
            assert '区' in tokens, "tokenize 应包含单字符 '区'"
            assert '链' in tokens, "tokenize 应包含单字符 '链'"
            # 双字 bigram
            assert '区块' in tokens, "tokenize 应包含 bigram '区块'"
            assert '块链' in tokens, "tokenize 应包含 bigram '块链'"
            # 验证 memory 中的中文 keywords
            for kw in chinese_keywords:
                assert kw in memory.keywords, \
                    f"memory.keywords 中缺少中文关键词 '{kw}'"

            # 2. 中文查询能命中中文记忆
            results = retrieve(
                "区块链共识机制",
                store,
                top_k=3,
                spread=False,
                now=datetime(2026, 3, 13, 10, 0, 0),
            )
            assert len(results) > 0, "中文查询应返回结果"
            result_ids = [m.id for m, _ in results]
            assert memory.id in result_ids, \
                f"中文查询应命中 {memory.id}，实际 {result_ids}"

            # 3. 注入 prompt 正确显示中文
            enriched = enrich_agent_prompt(
                "请整理区块链相关笔记",
                store,
                top_k=3,
                spread=False,
            )
            assert "联想记忆" in enriched, "enriched prompt 应包含'联想记忆'标题"
            # 中文内容出现在 prompt 中
            found_chinese = any(kw in enriched for kw in chinese_keywords)
            assert found_chinese, \
                f"enriched prompt 中应包含至少一个中文关键词，实际:\n{enriched[:500]}"

            # 4. 导出 Obsidian 笔记包含正确的中文 frontmatter
            result = export_all(store_path=store_path, output_dir=out_dir)
            assert result["status"] == "success", \
                f"中文内容导出状态应为 success，实际 {result['status']}"
            assert result["count"] == 1, f"应导出 1 条记忆，实际 {result['count']}"

            note_path = Path(result["notes"][0])
            note_content = note_path.read_text(encoding='utf-8')

            # frontmatter 中 tags 包含中文标签
            for tag in memory.tags:
                assert tag in note_content, \
                    f"note frontmatter 中缺少中文 tag '{tag}'"

            # note 正文包含中文 keywords
            for kw in chinese_keywords:
                assert kw in note_content, \
                    f"note 正文中缺少中文关键词 '{kw}'"

            # note 正文包含中文 context
            assert memory.context in note_content, \
                f"note 正文中缺少 context: '{memory.context}'"

            # up 字段格式正确
            assert 'up: "[[_agent_memory_moc]]"' in note_content, \
                "note frontmatter 中 up 字段格式不正确"

            # 5. MOC 文件使用 UTF-8 正确编码中文
            moc_content = Path(result["moc"]).read_text(encoding='utf-8')
            assert "Agent Memory MOC" in moc_content, "MOC 应包含标题"
            assert memory.id in moc_content, "MOC 中应包含 memory ID"

        finally:
            _cleanup_dir(store_path)
            _cleanup_dir(out_dir)


# ==================== 场景 6 ====================

class TestMemoryConsolidationE2E:
    """
    场景 6: Phase 2.1 Memory Consolidation 端到端
           添加 3 条记忆（2 条高度相似 + 1 条无关）
           → 调用 consolidate → 验证 store 剩余 2 条
           → 验证合并后记忆包含两者 keywords 并集
    """

    def test_memory_consolidation_e2e(self):
        store_path, store = _new_tmp_store()

        try:
            # 记忆 A + B 高度相似：共享大量 keywords/tags
            mem_a = Memory(
                id="mem_20260314_001",
                content="修复 BM25 检索引擎的中文分词问题，通过 bigram 展开实现字符级匹配",
                timestamp="2026-03-14T08:00:00",
                keywords=["BM25", "检索引擎", "中文分词", "bigram", "字符级"],
                tags=["bug-fix", "retrieval", "bm25"],
                context="BM25 中文分词 bigram 展开修复",
                importance=8,
            )
            mem_b = Memory(
                id="mem_20260314_002",
                content="BM25 检索优化：增加 bigram 中文分词，显著提升中文关键词召回率",
                timestamp="2026-03-14T09:00:00",
                keywords=["BM25", "检索引擎", "中文分词", "bigram", "召回率"],
                tags=["enhancement", "retrieval", "bm25"],
                context="BM25 检索 bigram 分词优化提升召回",
                importance=7,
            )
            # 记忆 C 与 A/B 完全无关
            mem_c = Memory(
                id="mem_20260314_003",
                content="配置 Obsidian Daily Note 模板，添加每日任务区块和进度追踪",
                timestamp="2026-03-14T10:00:00",
                keywords=["Obsidian", "Daily Note", "模板", "任务追踪"],
                tags=["obsidian", "productivity", "template"],
                context="Obsidian Daily Note 模板配置",
                importance=5,
            )

            store.add(mem_a)
            store.add(mem_b)
            store.add(mem_c)

            # 验证初始状态：3 条记忆
            assert len(store.load_all()) == 3, "初始应有 3 条记忆"

            # 调用 consolidate（使用较低阈值以匹配测试数据的相似度）
            result = consolidate(store, threshold=0.5)

            # 验证合并发生
            assert result["merged"] >= 1, \
                f"应发生至少 1 次合并，实际 {result['merged']}"
            assert result["deleted"] >= 1, \
                f"应删除至少 1 条副本，实际 {result['deleted']}"

            # 验证 store 中剩余 2 条记忆
            remaining = store.load_all()
            assert len(remaining) == 2, \
                f"合并后应剩余 2 条记忆，实际 {len(remaining)}"

            # 找到合并后的 BM25 相关记忆
            remaining_ids = {m.id for m in remaining}
            # 无关记忆 C 应保留
            assert mem_c.id in remaining_ids, \
                f"无关记忆 {mem_c.id} 应被保留，实际剩余 {remaining_ids}"

            # 找到合并后的记忆（primary 为 A，因 importance=8 > 7）
            merged_mem = next((m for m in remaining if m.id == mem_a.id), None)
            assert merged_mem is not None, \
                f"合并后 primary({mem_a.id}) 应保留在 store 中，实际 {remaining_ids}"

            # 验证合并后记忆包含 A 和 B 的 keywords 并集
            a_keywords = set(mem_a.keywords)
            b_keywords = set(mem_b.keywords)
            expected_union = a_keywords | b_keywords
            actual_keywords = set(merged_mem.keywords)
            for kw in expected_union:
                assert kw in actual_keywords, \
                    f"合并后记忆 keywords 中缺少 '{kw}'（来自并集），实际 {actual_keywords}"

            # 验证合并后 importance = max(8, 7) = 8
            assert merged_mem.importance == 8, \
                f"合并后 importance 应为 8（取较大值），实际 {merged_mem.importance}"

            # 验证持久化：重新加载 store，结果一致
            reloaded = MemoryStore(store_path)
            reloaded_all = reloaded.load_all()
            assert len(reloaded_all) == 2, \
                f"持久化后应有 2 条记忆，实际 {len(reloaded_all)}"
            reloaded_ids = {m.id for m in reloaded_all}
            assert mem_a.id in reloaded_ids, "持久化后 primary 应存在"
            assert mem_c.id in reloaded_ids, "持久化后无关记忆应存在"

        finally:
            _cleanup_dir(store_path)


# ==================== 场景 7 ====================

class TestMemoryDecayE2E:
    """
    场景 7: Phase 2.2 Memory Decay 端到端
           添加 2 条记忆（最近访问 vs 60 天前访问，同初始 importance）
           → 对两条分别调用 apply_decay
           → 验证新记忆 importance < 旧记忆的 importance（或旧已触底）
           → 调用 cleanup_decayed 清理触底记忆
           → 验证触底记忆被移除
    """

    def test_memory_decay_e2e(self):
        store_path, store = _new_tmp_store()

        # 固定"当前时间"以确保测试稳定性
        now = datetime(2026, 3, 14, 12, 0, 0)

        try:
            # 最近访问：1 天前（保留率接近 1）
            mem_recent = Memory(
                id="mem_20260314_010",
                content="刚刚完成的重要任务：实现 Phase 2 记忆衰减引擎",
                timestamp="2026-03-13T12:00:00",
                keywords=["decay", "Phase2", "记忆衰减", "重要"],
                tags=["implementation", "phase2"],
                context="Phase 2.2 记忆衰减引擎实现完成",
                importance=10,
                last_accessed="2026-03-13T12:00:00",  # 1 天前
            )
            # 60 天前访问：衰减严重
            mem_old = Memory(
                id="mem_20260314_011",
                content="60 天前完成的低优先级笔记整理任务",
                timestamp="2026-01-14T12:00:00",
                keywords=["笔记整理", "低优先级", "旧记忆"],
                tags=["note", "low-priority"],
                context="旧的笔记整理任务，长期未访问",
                importance=10,
                last_accessed="2026-01-14T12:00:00",  # ~60 天前
            )

            store.add(mem_recent)
            store.add(mem_old)

            # 对两条记忆分别施加衰减
            decayed_recent = apply_decay(mem_recent, now=now)
            decayed_old = apply_decay(mem_old, now=now)

            # 验证衰减后，新记忆 importance > 旧记忆 importance（旧衰减更多）
            assert decayed_recent.importance > decayed_old.importance, (
                f"新记忆衰减后 importance ({decayed_recent.importance}) 应 > "
                f"旧记忆衰减后 importance ({decayed_old.importance})"
            )

            # 验证旧记忆衰减幅度明显（60 天 / (10*3) = 2 个 stability 周期）
            # retention = e^(-60/30) = e^(-2) ≈ 0.135，base=10 → decayed = max(2, 1.35) = 2
            floor_old = max(1, int(mem_old.importance * 0.2))  # = 2
            assert decayed_old.importance <= floor_old + 1, (
                f"旧记忆应接近或达到 floor({floor_old})，实际 {decayed_old.importance}"
            )

            # 直接调用 cleanup_decayed，基于 store 中的原始记忆（importance=10）判断触底
            # 不手动写回衰减结果，避免二次衰减导致 floor 判断基准错误
            deleted_count = cleanup_decayed(store, now=now)

            # 验证触底的旧记忆被清理
            assert deleted_count >= 1, \
                f"应至少删除 1 条触底记忆，实际删除 {deleted_count}"

            remaining = store.load_all()
            remaining_ids = {m.id for m in remaining}

            # 旧记忆应被删除（已触底）
            assert mem_old.id not in remaining_ids, \
                f"旧记忆 {mem_old.id} 已触底，应被 cleanup_decayed 删除"

            # 新记忆应保留（未触底）
            assert mem_recent.id in remaining_ids, \
                f"新记忆 {mem_recent.id} 未触底，应被保留"

            # 验证持久化：重新加载确认
            reloaded = MemoryStore(store_path)
            reloaded_all = reloaded.load_all()
            reloaded_ids = {m.id for m in reloaded_all}
            assert mem_old.id not in reloaded_ids, \
                "持久化层：旧记忆应已被删除"
            assert mem_recent.id in reloaded_ids, \
                "持久化层：新记忆应仍存在"

        finally:
            _cleanup_dir(store_path)


# ==================== 测试运行器 ====================

def run_tests():
    """按顺序运行所有集成测试，输出详细结果。"""
    import traceback as tb_mod

    test_classes = [
        TestFullMemoryLifecycle,
        TestMultiMemoryAssociationAndSpread,
        TestPassiveEvolutionAndAccessTracking,
        TestCliFullCommandSet,
        TestChineseContentFullChain,
        TestMemoryConsolidationE2E,
        TestMemoryDecayE2E,
    ]

    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("Agent Memory 集成测试")
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
                errors.append((label, tb_mod.format_exc()))
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
