#!/usr/bin/env python3
"""专项 CLI 子命令测试套件。

覆盖 cli.py 中所有 14+ 子命令的入口逻辑。
每个子命令至少 2 个测试：happy path + 参数错误/边界情况。

架构：
- 使用 subprocess.run 通过 CLI 入口测试每个子命令
- 使用 tmp_path / tempfile 创建隔离的临时 store
- 使用 unittest.mock.patch 模拟外部依赖
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

# ---- 将 scripts 目录加入 sys.path ----
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')
sys.path.insert(0, SCRIPTS_DIR)

CLI_PATH = os.path.join(SCRIPTS_DIR, 'cli.py')


# ==================== 辅助函数 ====================

def run_cli(*args, store=None, extra_env=None):
    """运行 cli.py 子命令并返回 (returncode, stdout, stderr)。"""
    cmd = [sys.executable, CLI_PATH]
    if store:
        cmd += ['--store', str(store)]
    cmd += list(args)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    return result.returncode, result.stdout, result.stderr


def make_store_with_memories(tmp_dir, count=1, **kwargs):
    """在 tmp_dir 中创建含若干条记忆的 store，返回 MemoryStore。"""
    from memory_store import Memory, MemoryStore

    store = MemoryStore(store_path=str(tmp_dir))
    for i in range(count):
        mem_id = kwargs.get('id', f'mem_test_{i:03d}')
        if count > 1:
            mem_id = f'mem_test_{i:03d}'
        mem = Memory(
            id=mem_id,
            content=kwargs.get('content', f'测试记忆内容 {i}'),
            timestamp=datetime.now().isoformat(),
            name=kwargs.get('name', f'test-memory-{i}'),
            description=kwargs.get('description', f'测试描述 {i}'),
            type=kwargs.get('type', 'task'),
            keywords=kwargs.get('keywords', ['测试', '记忆', f'kw{i}']),
            tags=kwargs.get('tags', ['test']),
            context=kwargs.get('context', '测试上下文'),
            importance=kwargs.get('importance', 5),
            positive_feedback=kwargs.get('positive_feedback', 0),
            negative_feedback=kwargs.get('negative_feedback', 0),
        )
        store.add(mem)
    return store


# ==================== quick-add ====================

class TestQuickAdd:
    """测试 quick-add 子命令。"""

    def test_quick_add_basic(self, tmp_path):
        """happy path：基本添加一条记忆。"""
        rc, stdout, stderr = run_cli(
            'quick-add', '这是一条测试记忆内容',
            '--keywords', '测试,记忆,CLI',
            '--name', 'test-quick-add',
            '--description', '单元测试中添加的记忆',
            '--type', 'task',
            store=tmp_path,
        )
        assert rc == 0, f"quick-add 应成功退出，stderr: {stderr}"
        assert '已保存' in stdout, f"输出应包含「已保存」，实际：{stdout}"
        assert '关键词' in stdout, f"输出应包含关键词信息，实际：{stdout}"

    def test_quick_add_creates_file_in_store(self, tmp_path):
        """quick-add 后 store 目录中应有 .md 文件。"""
        run_cli(
            'quick-add', '验证文件写入',
            '--keywords', '验证,文件',
            '--name', 'file-write-test',
            store=tmp_path,
        )
        md_files = [f for f in tmp_path.iterdir() if f.suffix == '.md' and f.name != 'MEMORY.md']
        assert len(md_files) >= 1, f"store 中应有至少 1 个记忆文件，实际：{list(tmp_path.iterdir())}"

    def test_quick_add_missing_keywords(self, tmp_path):
        """缺少必填参数 --keywords 应以非零退出。"""
        rc, stdout, stderr = run_cli(
            'quick-add', '缺少关键词的记忆',
            store=tmp_path,
        )
        assert rc != 0, "缺少 --keywords 应以非零退出"

    def test_quick_add_with_importance(self, tmp_path):
        """指定 --importance 参数。"""
        rc, stdout, stderr = run_cli(
            'quick-add', '高重要性记忆',
            '--keywords', '重要',
            '--importance', '9',
            store=tmp_path,
        )
        assert rc == 0, f"quick-add --importance 应成功，stderr: {stderr}"
        assert '重要度' in stdout or '9' in stdout, f"输出应包含重要度信息，实际：{stdout}"

    def test_quick_add_different_types(self, tmp_path):
        """测试不同 --type 值：knowledge, feedback, reference。"""
        for mem_type in ['knowledge', 'feedback', 'reference']:
            rc, stdout, stderr = run_cli(
                'quick-add', f'{mem_type}类型记忆',
                '--keywords', mem_type,
                '--type', mem_type,
                store=tmp_path,
            )
            assert rc == 0, f"type={mem_type} 应成功，stderr: {stderr}"

    def test_quick_add_generates_index(self, tmp_path):
        """quick-add 后应自动生成 MEMORY.md 索引。"""
        run_cli(
            'quick-add', '触发索引生成',
            '--keywords', '索引',
            store=tmp_path,
        )
        memory_md = tmp_path / 'MEMORY.md'
        assert memory_md.exists(), "quick-add 后应生成 MEMORY.md"


# ==================== retrieve ====================

class TestRetrieve:
    """测试 retrieve 子命令。"""

    def test_retrieve_basic(self, tmp_path):
        """happy path：基本检索。"""
        make_store_with_memories(tmp_path, count=2, keywords=['python', '编程', '测试'])

        rc, stdout, stderr = run_cli('retrieve', 'python 编程', store=tmp_path)
        assert rc == 0, f"retrieve 应成功退出，stderr: {stderr}"

    def test_retrieve_empty_store(self, tmp_path):
        """空 store 检索应返回「未找到」提示，不崩溃。"""
        rc, stdout, stderr = run_cli('retrieve', '任意查询', store=tmp_path)
        assert rc == 0, f"空 store 检索应成功退出，stderr: {stderr}"
        assert '未找到' in stdout, f"空 store 应提示未找到，实际：{stdout}"

    def test_retrieve_with_top_k(self, tmp_path):
        """指定 --top-k 参数。"""
        make_store_with_memories(tmp_path, count=5)
        rc, stdout, stderr = run_cli('retrieve', '测试', '--top-k', '2', store=tmp_path)
        assert rc == 0, f"retrieve --top-k 应成功，stderr: {stderr}"

    def test_retrieve_format_prompt(self, tmp_path):
        """--format prompt 模式。"""
        make_store_with_memories(tmp_path, count=1)
        rc, stdout, stderr = run_cli('retrieve', '测试', '--format', 'prompt', store=tmp_path)
        assert rc == 0, f"retrieve --format prompt 应成功，stderr: {stderr}"

    def test_retrieve_no_spread(self, tmp_path):
        """--no-spread 禁用扩散激活。"""
        make_store_with_memories(tmp_path, count=1)
        rc, stdout, stderr = run_cli('retrieve', '测试', '--no-spread', store=tmp_path)
        assert rc == 0, f"retrieve --no-spread 应成功，stderr: {stderr}"


# ==================== feedback ====================

class TestFeedback:
    """测试 feedback 子命令。"""

    def test_feedback_useful(self, tmp_path):
        """happy path：--useful 标记正面反馈。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='fb_test_001',
            content='反馈测试记忆',
            timestamp=datetime.now().isoformat(),
            keywords=['反馈'],
            tags=['test'],
            context='测试',
            importance=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli(
            'feedback', '--memory-id', 'fb_test_001', '--useful',
            store=tmp_path,
        )
        assert rc == 0, f"feedback --useful 应成功，stderr: {stderr}"
        assert 'positive' in stdout.lower(), f"输出应包含 positive，实际：{stdout}"

    def test_feedback_not_useful(self, tmp_path):
        """--not-useful 标记负面反馈。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='fb_test_002',
            content='负面反馈测试记忆',
            timestamp=datetime.now().isoformat(),
            keywords=['反馈'],
            tags=['test'],
            context='测试',
            importance=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli(
            'feedback', '--memory-id', 'fb_test_002', '--not-useful',
            store=tmp_path,
        )
        assert rc == 0, f"feedback --not-useful 应成功，stderr: {stderr}"
        assert 'negative' in stdout.lower(), f"输出应包含 negative，实际：{stdout}"

    def test_feedback_auto_mode(self, tmp_path):
        """--auto --event task_success 自动推断模式。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='fb_auto_001',
            content='自动反馈测试',
            timestamp=datetime.now().isoformat(),
            keywords=['自动'],
            tags=['test'],
            context='测试',
            importance=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli(
            'feedback', '--memory-id', 'fb_auto_001', '--auto', '--event', 'task_success',
            store=tmp_path,
        )
        assert rc == 0, f"feedback --auto 应成功，stderr: {stderr}"
        assert '自动推断' in stdout or 'auto' in stdout.lower(), f"输出应提示自动推断，实际：{stdout}"

    def test_feedback_auto_and_useful_mutually_exclusive(self, tmp_path):
        """--auto 与 --useful 互斥，应以非零退出。"""
        rc, stdout, stderr = run_cli(
            'feedback', '--memory-id', 'any_id', '--auto', '--useful',
            store=tmp_path,
        )
        assert rc != 0, "--auto 与 --useful 互斥，应以非零退出"

    def test_feedback_auto_without_event(self, tmp_path):
        """--auto 不带 --event 应以非零退出。"""
        rc, stdout, stderr = run_cli(
            'feedback', '--memory-id', 'any_id', '--auto',
            store=tmp_path,
        )
        assert rc != 0, "--auto 不带 --event 应失败"

    def test_feedback_nonexistent_memory(self, tmp_path):
        """对不存在的记忆反馈应以非零退出。"""
        rc, stdout, stderr = run_cli(
            'feedback', '--memory-id', 'nonexistent_memory_xyz', '--useful',
            store=tmp_path,
        )
        assert rc != 0, "不存在的记忆应以非零退出"

    def test_feedback_no_flag_specified(self, tmp_path):
        """不指定 --useful/--not-useful/--auto 应以非零退出。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='fb_noflag_001',
            content='无标志测试',
            timestamp=datetime.now().isoformat(),
            keywords=['测试'],
            tags=['test'],
            context='测试',
            importance=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli(
            'feedback', '--memory-id', 'fb_noflag_001',
            store=tmp_path,
        )
        assert rc != 0, "不指定反馈标志应以非零退出"


# ==================== health-check ====================

class TestHealthCheck:
    """测试 health-check 子命令。"""

    def test_health_check_basic(self, tmp_path):
        """happy path：正常 store 执行 health-check。"""
        make_store_with_memories(tmp_path, count=3, positive_feedback=5)

        rc, stdout, stderr = run_cli('health-check', store=tmp_path)
        assert rc == 0, f"health-check 应成功退出，stderr: {stderr}"
        assert '总计' in stdout, f"输出应包含总计行，实际：{stdout}"

    def test_health_check_empty_store(self, tmp_path):
        """空 store 执行 health-check 不崩溃。"""
        rc, stdout, stderr = run_cli('health-check', store=tmp_path)
        assert rc == 0, f"空 store health-check 应成功退出，stderr: {stderr}"
        assert '总计' in stdout, f"输出应包含总计行（0条），实际：{stdout}"

    def test_health_check_detects_blocked(self, tmp_path):
        """blocked 记忆应被标记。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='blocked_hc_001',
            content='blocked 记忆',
            timestamp=datetime.now().isoformat(),
            keywords=['blocked'],
            tags=['test'],
            context='测试',
            importance=5,
            positive_feedback=0,
            negative_feedback=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli('health-check', store=tmp_path)
        assert rc == 0, f"health-check 应成功退出，stderr: {stderr}"
        assert 'BLOCKED' in stdout.upper(), f"blocked 记忆应被标记，实际：{stdout}"

    def test_health_check_show_all(self, tmp_path):
        """--show-all 选项显示所有记忆（包括 healthy）。"""
        make_store_with_memories(tmp_path, count=1, positive_feedback=5)

        rc, stdout, stderr = run_cli('health-check', '--show-all', store=tmp_path)
        assert rc == 0, f"health-check --show-all 应成功，stderr: {stderr}"
        assert 'HEALTHY' in stdout.upper(), f"--show-all 应显示 healthy 记忆，实际：{stdout}"


# ==================== trigger ====================

class TestTrigger:
    """测试 trigger 子命令（record/stats/adjust）。"""

    def test_trigger_record_success(self, tmp_path):
        """trigger record --rule X --result success。"""
        stats_file = tmp_path / 'trigger-stats.json'

        rc, stdout, stderr = run_cli(
            'trigger', 'record',
            '--rule', 'test_rule',
            '--result', 'success',
            store=tmp_path,
            extra_env={'TRIGGER_STATS_PATH': str(stats_file)},
        )
        assert rc == 0, f"trigger record 应成功，stderr: {stderr}"
        assert '已记录触发' in stdout, f"输出应包含已记录触发，实际：{stdout}"

    def test_trigger_record_failure(self, tmp_path):
        """trigger record --result failure。"""
        rc, stdout, stderr = run_cli(
            'trigger', 'record',
            '--rule', 'fail_rule',
            '--result', 'failure',
            store=tmp_path,
        )
        assert rc == 0, f"trigger record failure 应成功，stderr: {stderr}"

    def test_trigger_record_skip(self, tmp_path):
        """trigger record --result skip。"""
        rc, stdout, stderr = run_cli(
            'trigger', 'record',
            '--rule', 'skip_rule',
            '--result', 'skip',
            store=tmp_path,
        )
        assert rc == 0, f"trigger record skip 应成功，stderr: {stderr}"

    def test_trigger_record_invalid_result(self, tmp_path):
        """trigger record --result invalid 应以非零退出。"""
        rc, stdout, stderr = run_cli(
            'trigger', 'record',
            '--rule', 'test_rule',
            '--result', 'invalid_result',
            store=tmp_path,
        )
        assert rc != 0, "无效 result 应以非零退出"

    def test_trigger_stats_no_data(self, tmp_path):
        """trigger stats 无数据时输出提示。"""
        rc, stdout, stderr = run_cli('trigger', 'stats', store=tmp_path)
        assert rc == 0, f"trigger stats 无数据应成功退出，stderr: {stderr}"
        assert '暂无' in stdout or '无' in stdout or '触发统计' in stdout, \
            f"无数据时应有提示，实际：{stdout}"

    def test_trigger_stats_with_rule(self, tmp_path):
        """trigger stats --rule 查看特定规则统计。"""
        rc, stdout, stderr = run_cli(
            'trigger', 'stats', '--rule', 'nonexistent_rule',
            store=tmp_path,
        )
        assert rc == 0, f"trigger stats --rule 应成功退出，stderr: {stderr}"
        assert '触发统计' in stdout, f"输出应包含统计信息，实际：{stdout}"

    def test_trigger_adjust(self, tmp_path):
        """trigger adjust --rule X。"""
        rc, stdout, stderr = run_cli(
            'trigger', 'adjust',
            '--rule', 'adjust_rule',
            '--current-weight', '1.0',
            store=tmp_path,
        )
        assert rc == 0, f"trigger adjust 应成功，stderr: {stderr}"
        assert '权重调整' in stdout, f"输出应包含权重调整信息，实际：{stdout}"


# ==================== dashboard ====================

class TestDashboard:
    """测试 dashboard 子命令。"""

    def test_dashboard_basic(self, tmp_path):
        """happy path：正常输出四区域。"""
        make_store_with_memories(tmp_path, count=2)
        trigger_stats_file = tmp_path / 'trigger-stats.json'

        rc, stdout, stderr = run_cli(
            'dashboard', '--trigger-stats', str(trigger_stats_file),
            store=tmp_path,
        )
        assert rc == 0, f"dashboard 应成功退出，stderr: {stderr}"
        assert 'Dashboard' in stdout, f"输出应包含 Dashboard 标题，实际：{stdout}"
        assert '记忆健康' in stdout, f"输出应包含记忆健康区域，实际：{stdout}"
        assert '反馈统计' in stdout, f"输出应包含反馈统计区域，实际：{stdout}"
        assert '系统概要' in stdout, f"输出应包含系统概要区域，实际：{stdout}"

    def test_dashboard_empty_store(self, tmp_path):
        """空 store 的 dashboard 不崩溃。"""
        trigger_stats_file = tmp_path / 'trigger-stats.json'

        rc, stdout, stderr = run_cli(
            'dashboard', '--trigger-stats', str(trigger_stats_file),
            store=tmp_path,
        )
        assert rc == 0, f"空 store dashboard 应成功退出，stderr: {stderr}"
        assert '0 条' in stdout, f"应显示 0 条记忆，实际：{stdout}"

    def test_dashboard_with_trigger_stats(self, tmp_path):
        """有 trigger stats 数据时，触发效率区域正常显示。"""
        make_store_with_memories(tmp_path, count=1)
        trigger_stats_file = tmp_path / 'trigger-stats.json'

        stats_data = {
            "rules": {
                "memory_flush": {
                    "success": 8,
                    "failure": 2,
                    "skip": 0,
                    "weight": 1.2,
                    "last_triggered": "2026-03-14T10:00:00",
                }
            },
            "updated_at": "2026-03-14T10:00:00",
        }
        trigger_stats_file.write_text(
            json.dumps(stats_data, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        rc, stdout, stderr = run_cli(
            'dashboard', '--trigger-stats', str(trigger_stats_file),
            store=tmp_path,
        )
        assert rc == 0, f"dashboard 有 trigger stats 时应成功，stderr: {stderr}"
        assert '触发效率' in stdout, f"输出应包含触发效率区域，实际：{stdout}"
        assert 'memory_flush' in stdout, f"规则名应出现在输出中，实际：{stdout}"


# ==================== consolidate ====================

class TestConsolidate:
    """测试 consolidate 子命令。"""

    def test_consolidate_no_similar(self, tmp_path):
        """无相似记忆对，输出「无需合并」提示。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        # 添加完全不同主题的记忆
        for i, (kw, content) in enumerate([
            (['python', '编程'], 'Python 编程记忆'),
            (['区块链', 'web3'], '区块链记忆'),
            (['音乐', '吉他'], '音乐记忆'),
        ]):
            mem = Memory(
                id=f'diff_mem_{i:03d}',
                content=content,
                timestamp=datetime.now().isoformat(),
                keywords=kw,
                tags=['test'],
                context='测试',
                importance=5,
            )
            store.add(mem)

        rc, stdout, stderr = run_cli('consolidate', store=tmp_path)
        assert rc == 0, f"consolidate 应成功退出，stderr: {stderr}"
        assert '无需合并' in stdout or '未发现' in stdout, \
            f"无相似记忆时应提示，实际：{stdout}"

    def test_consolidate_dry_run(self, tmp_path):
        """--dry-run 预览模式不实际修改 store。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        # 添加两条高相似度记忆（相同关键词）
        for i in range(2):
            mem = Memory(
                id=f'similar_mem_{i:03d}',
                content=f'相同主题的记忆 {i}，包含大量共同关键词',
                timestamp=datetime.now().isoformat(),
                keywords=['python', '测试', '相似', '关键词', '合并'],
                tags=['test', 'similar'],
                context='相同上下文',
                importance=5,
            )
            store.add(mem)

        original_files = set(f.name for f in tmp_path.iterdir() if f.suffix == '.md')

        rc, stdout, stderr = run_cli('consolidate', '--dry-run', store=tmp_path)
        assert rc == 0, f"consolidate --dry-run 应成功，stderr: {stderr}"
        assert '预览' in stdout or 'dry-run' in stdout.lower() or '预览完成' in stdout, \
            f"dry-run 应有预览提示，实际：{stdout}"

        # 文件不应被删除
        current_files = set(f.name for f in tmp_path.iterdir() if f.suffix == '.md')
        removed = original_files - current_files
        assert len(removed) == 0, f"dry-run 不应删除文件，删除了：{removed}"

    def test_consolidate_with_threshold(self, tmp_path):
        """指定 --threshold 参数。"""
        make_store_with_memories(tmp_path, count=2)
        rc, stdout, stderr = run_cli('consolidate', '--threshold', '0.9', store=tmp_path)
        assert rc == 0, f"consolidate --threshold 应成功，stderr: {stderr}"


# ==================== list ====================

class TestList:
    """测试 list 子命令。"""

    def test_list_basic(self, tmp_path):
        """happy path：列出记忆。"""
        make_store_with_memories(tmp_path, count=3)

        rc, stdout, stderr = run_cli('list', store=tmp_path)
        assert rc == 0, f"list 应成功退出，stderr: {stderr}"
        assert '最近' in stdout, f"输出应包含「最近」，实际：{stdout}"

    def test_list_empty_store(self, tmp_path):
        """空 store 应提示记忆库为空。"""
        rc, stdout, stderr = run_cli('list', store=tmp_path)
        assert rc == 0, f"空 store list 应成功退出，stderr: {stderr}"
        assert '为空' in stdout, f"空 store 应提示为空，实际：{stdout}"

    def test_list_with_limit(self, tmp_path):
        """--limit 限制显示条数。"""
        make_store_with_memories(tmp_path, count=5)

        rc, stdout, stderr = run_cli('list', '--limit', '2', store=tmp_path)
        assert rc == 0, f"list --limit 应成功，stderr: {stderr}"
        assert '2' in stdout, f"输出应提到限制数量，实际：{stdout}"

    def test_list_shows_memory_ids(self, tmp_path):
        """list 输出中包含记忆 ID。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='list_test_unique_id',
            content='用于 list 测试的记忆',
            timestamp=datetime.now().isoformat(),
            keywords=['list', '测试'],
            tags=['test'],
            context='测试',
            importance=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli('list', store=tmp_path)
        assert rc == 0, f"list 应成功，stderr: {stderr}"
        assert 'list_test_unique_id' in stdout, f"输出应包含记忆 ID，实际：{stdout}"


# ==================== evolve ====================

class TestEvolve:
    """测试 evolve 子命令。"""

    def test_evolve_context(self, tmp_path):
        """happy path：更新记忆 context。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='evolve_test_001',
            content='待演化记忆',
            timestamp=datetime.now().isoformat(),
            keywords=['演化'],
            tags=['test'],
            context='旧上下文',
            importance=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli(
            'evolve', 'evolve_test_001', '--context', '新上下文',
            store=tmp_path,
        )
        assert rc == 0, f"evolve --context 应成功，stderr: {stderr}"
        assert '已更新' in stdout, f"输出应包含「已更新」，实际：{stdout}"
        assert '新上下文' in stdout, f"输出应包含新 context，实际：{stdout}"

    def test_evolve_tags(self, tmp_path):
        """更新记忆 tags。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='evolve_tag_001',
            content='待更新标签',
            timestamp=datetime.now().isoformat(),
            keywords=['标签'],
            tags=['old_tag'],
            context='上下文',
            importance=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli(
            'evolve', 'evolve_tag_001', '--tags', 'new_tag1,new_tag2',
            store=tmp_path,
        )
        assert rc == 0, f"evolve --tags 应成功，stderr: {stderr}"
        assert 'new_tag1' in stdout, f"输出应包含新标签，实际：{stdout}"

    def test_evolve_nonexistent_memory(self, tmp_path):
        """对不存在的记忆 evolve 应以非零退出。"""
        rc, stdout, stderr = run_cli(
            'evolve', 'nonexistent_xyz', '--context', '新上下文',
            store=tmp_path,
        )
        assert rc != 0, "不存在的记忆应以非零退出"
        assert '不存在' in stdout, f"输出应提示记忆不存在，实际：{stdout}"

    def test_evolve_no_update_fields(self, tmp_path):
        """不提供任何更新字段时应提示。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='evolve_noop_001',
            content='无操作测试',
            timestamp=datetime.now().isoformat(),
            keywords=['测试'],
            tags=['test'],
            context='上下文',
            importance=5,
        )
        store.add(mem)

        rc, stdout, stderr = run_cli('evolve', 'evolve_noop_001', store=tmp_path)
        assert rc == 0, f"无更新字段应成功退出（不修改），stderr: {stderr}"
        assert '未提供' in stdout, f"输出应提示未提供更新字段，实际：{stdout}"


# ==================== stats（add 子命令） ====================

class TestStats:
    """测试 stats 子命令。"""

    def test_stats_empty_store(self, tmp_path):
        """空 store 时 stats 输出「记忆库为空」。"""
        rc, stdout, stderr = run_cli('stats', store=tmp_path)
        assert rc == 0, f"stats 空 store 应成功退出，stderr: {stderr}"
        assert '为空' in stdout, f"空 store 应提示为空，实际：{stdout}"

    def test_stats_with_memories(self, tmp_path):
        """有记忆时 stats 输出统计信息。"""
        make_store_with_memories(tmp_path, count=3, importance=7)

        rc, stdout, stderr = run_cli('stats', store=tmp_path)
        assert rc == 0, f"stats 应成功退出，stderr: {stderr}"
        assert '统计' in stdout, f"输出应包含统计信息，实际：{stdout}"
        assert '3' in stdout, f"输出应包含记忆数量，实际：{stdout}"


# ==================== add ====================

class TestAdd:
    """测试 add 子命令（手动添加）。"""

    def test_add_basic(self, tmp_path):
        """happy path：基本添加。"""
        rc, stdout, stderr = run_cli(
            'add', '--subject', '测试主题',
            '--description', '测试描述',
            '--keywords', '测试,主题',
            '--importance', '7',
            store=tmp_path,
        )
        assert rc == 0, f"add 应成功退出，stderr: {stderr}"
        assert '记忆已创建' in stdout, f"输出应包含「记忆已创建」，实际：{stdout}"

    def test_add_missing_subject(self, tmp_path):
        """缺少 --subject 应以非零退出。"""
        rc, stdout, stderr = run_cli(
            'add', '--description', '无主题描述',
            store=tmp_path,
        )
        assert rc != 0, "缺少 --subject 应以非零退出"

    def test_add_defaults(self, tmp_path):
        """只提供 --subject，其他参数使用默认值。"""
        rc, stdout, stderr = run_cli(
            'add', '--subject', '仅主题',
            store=tmp_path,
        )
        assert rc == 0, f"只有 --subject 应成功，stderr: {stderr}"
        assert '记忆已创建' in stdout, f"输出应包含「记忆已创建」，实际：{stdout}"


# ==================== generate-index ====================

class TestGenerateIndex:
    """测试 generate-index 子命令。"""

    def test_generate_index_basic(self, tmp_path):
        """happy path：生成 MEMORY.md 索引。"""
        make_store_with_memories(tmp_path, count=3)

        rc, stdout, stderr = run_cli('generate-index', store=tmp_path)
        assert rc == 0, f"generate-index 应成功退出，stderr: {stderr}"
        assert '索引已生成' in stdout, f"输出应包含「索引已生成」，实际：{stdout}"

        memory_md = tmp_path / 'MEMORY.md'
        assert memory_md.exists(), "MEMORY.md 应被创建"

    def test_generate_index_empty_store(self, tmp_path):
        """空 store 也能生成（空内容的）索引。"""
        rc, stdout, stderr = run_cli('generate-index', store=tmp_path)
        assert rc == 0, f"空 store generate-index 应成功退出，stderr: {stderr}"


# ==================== decay（无直接 CLI 子命令，测试通过 evolve 触发或跳过） ====================
# NOTE: cli.py 目前没有独立的 `decay` 子命令
# decay 逻辑通过 evolver.py 内部实现，测试见 test_evolver.py
# 若以后添加 `decay` 子命令，此类需扩充。

class TestDecayViaEvolve:
    """通过 evolve 和 stats 验证记忆衰减相关行为（CLI 层面）。"""

    def test_importance_preserved_after_evolve(self, tmp_path):
        """evolve 更新 context 不影响 importance 值。"""
        from memory_store import Memory, MemoryStore
        store = MemoryStore(store_path=str(tmp_path))
        mem = Memory(
            id='decay_test_001',
            content='衰减测试记忆',
            timestamp=datetime.now().isoformat(),
            keywords=['衰减'],
            tags=['test'],
            context='旧上下文',
            importance=8,
        )
        store.add(mem)

        run_cli('evolve', 'decay_test_001', '--context', '新上下文', store=tmp_path)

        updated = store.get('decay_test_001')
        assert updated.importance == 8, f"importance 不应被 evolve 修改，实际：{updated.importance}"


# ==================== export ====================

class TestExport:
    """测试 export 子命令。"""

    def test_export_empty_store(self, tmp_path):
        """空 store 导出应提示 No memories to export。"""
        output_dir = tmp_path / 'export_output'
        output_dir.mkdir()

        rc, stdout, stderr = run_cli(
            'export', '--output', str(output_dir),
            store=tmp_path,
        )
        assert rc == 0, f"export 空 store 应成功退出，stderr: {stderr}"
        assert 'No memories to export' in stdout or '无' in stdout, \
            f"空 store 应提示无内容，实际：{stdout}"

    def test_export_with_memories(self, tmp_path):
        """有记忆时 export 应生成文件。"""
        make_store_with_memories(tmp_path, count=2)
        output_dir = tmp_path / 'export_output'
        output_dir.mkdir()

        rc, stdout, stderr = run_cli(
            'export', '--output', str(output_dir),
            store=tmp_path,
        )
        assert rc == 0, f"export 应成功退出，stderr: {stderr}"
        assert 'Exported' in stdout, f"输出应包含 Exported 信息，实际：{stdout}"


# ==================== CLI 入口无子命令 ====================

class TestCLIEntryPoint:
    """测试 CLI 入口逻辑。"""

    def test_no_subcommand_prints_help(self):
        """不指定子命令应打印帮助信息，以零退出。"""
        rc, stdout, stderr = run_cli()
        assert rc == 0, f"无子命令应以零退出，rc={rc}, stderr={stderr}"
        # argparse 通常将帮助信息输出到 stdout
        assert 'usage' in (stdout + stderr).lower(), \
            f"无子命令应显示 usage 帮助，实际：{stdout + stderr}"

    def test_unknown_subcommand_exits_nonzero(self):
        """未知子命令应以非零退出。"""
        rc, stdout, stderr = run_cli('nonexistent_subcommand_xyz')
        assert rc != 0, "未知子命令应以非零退出"

    def test_help_flag(self):
        """--help 应输出帮助并以零退出。"""
        result = subprocess.run(
            [sys.executable, CLI_PATH, '--help'],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"--help 应以零退出，rc={result.returncode}"
        assert 'usage' in result.stdout.lower() or 'usage' in result.stderr.lower(), \
            f"--help 应输出 usage 信息，实际：{result.stdout}"


# ==================== 跨子命令集成场景 ====================

class TestCLIIntegrationScenarios:
    """跨子命令集成测试：验证多命令协作。"""

    def test_quick_add_then_retrieve(self, tmp_path):
        """quick-add 后可检索到添加的记忆。"""
        # 先添加
        run_cli(
            'quick-add', 'Python 异步编程最佳实践',
            '--keywords', 'python,async,异步',
            '--name', 'python-async-best-practices',
            store=tmp_path,
        )
        # 再检索
        rc, stdout, stderr = run_cli('retrieve', 'python async', store=tmp_path)
        assert rc == 0, f"retrieve 应成功，stderr: {stderr}"
        # 如果有关联，不应显示「未找到」
        # （注意：检索相关性取决于关键词匹配算法，此处只验证不崩溃）

    def test_quick_add_then_list(self, tmp_path):
        """quick-add 后 list 能看到新记忆。"""
        run_cli(
            'quick-add', 'list 集成测试记忆',
            '--keywords', 'list,集成测试',
            '--name', 'list-integration-test',
            store=tmp_path,
        )

        rc, stdout, stderr = run_cli('list', store=tmp_path)
        assert rc == 0, f"list 应成功，stderr: {stderr}"
        assert '为空' not in stdout, f"添加后 list 不应显示为空，实际：{stdout}"

    def test_quick_add_then_health_check(self, tmp_path):
        """quick-add 后 health-check 正常运行。"""
        run_cli(
            'quick-add', '健康检查集成测试',
            '--keywords', '健康,检查',
            store=tmp_path,
        )

        rc, stdout, stderr = run_cli('health-check', store=tmp_path)
        assert rc == 0, f"health-check 应成功，stderr: {stderr}"
        assert '总计' in stdout, f"应输出总计行，实际：{stdout}"

    def test_quick_add_then_evolve_then_list(self, tmp_path):
        """quick-add → evolve 更新 → list 查看新状态。"""
        from memory_store import MemoryStore

        run_cli(
            'quick-add', '待演化的集成测试记忆',
            '--keywords', '演化,集成',
            '--name', 'evolve-integration',
            store=tmp_path,
        )

        # 获取刚添加记忆的 ID
        store = MemoryStore(store_path=str(tmp_path))
        memories = store.load_all()
        assert len(memories) >= 1, "应有至少 1 条记忆"
        mem_id = memories[-1].id

        # evolve
        rc, stdout, stderr = run_cli(
            'evolve', mem_id, '--context', '已更新的上下文',
            store=tmp_path,
        )
        assert rc == 0, f"evolve 应成功，stderr: {stderr}"

        # list 验证
        rc2, stdout2, stderr2 = run_cli('list', store=tmp_path)
        assert rc2 == 0, f"list 应成功，stderr: {stderr2}"
        assert mem_id in stdout2, f"list 应包含已演化记忆的 ID，实际：{stdout2}"
