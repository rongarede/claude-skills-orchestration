"""pytest 配置：注册自定义标记，定义全局公共 fixtures。

公共 Fixtures
-------------
clean_store       空的 MemoryStore（目录模式）
sample_memory     单条标准化 Memory 对象（无 feedback 字段）
sample_memory_fb  单条含 feedback 字段的 Memory 对象
populated_store   预填充 5 条记忆的 MemoryStore（含多样化关键词）
memory_factory    工厂函数，灵活创建 Memory（kwargs 覆盖默认值）
"""

import os
import sys
import tempfile
import shutil

import pytest

# 确保 scripts 目录始终在 sys.path 中（子测试文件也会 insert，这里兜底保证）
_SCRIPTS = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', 'scripts')
)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from memory_store import Memory, MemoryStore  # noqa: E402  (路径已在上面设置)


# ==================== pytest 标记注册 ====================

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )


# ==================== 核心 fixtures ====================

@pytest.fixture
def clean_store(tmp_path):
    """空的 MemoryStore（目录模式），每个测试函数独立隔离。"""
    return MemoryStore(store_path=str(tmp_path))


@pytest.fixture
def sample_memory():
    """单条标准化 Memory 对象，适合不需要 feedback 字段的测试。"""
    return Memory(
        id="mem_20260314_001",
        content="修复 LaTeX fontspec 编译错误，XeLaTeX 路径配置问题",
        timestamp="2026-03-14T10:00:00",
        keywords=["LaTeX", "fontspec", "编译错误", "路径配置"],
        tags=["bug-fix", "thesis"],
        context="XeLaTeX 引擎路径未正确配置导致 fontspec 包加载失败",
        importance=7,
    )


@pytest.fixture
def sample_memory_fb():
    """单条含 feedback 字段的 Memory 对象，适合 feedback/health 相关测试。"""
    return Memory(
        id="mem_20260314_002",
        content="实现 Claude Code task-complete-hook，自动记录任务完成到 changelog",
        timestamp="2026-03-14T12:00:00",
        keywords=["hook", "task-complete", "changelog", "自动化"],
        tags=["feature", "automation"],
        context="PostToolUse hook 在 TaskUpdate completed 时自动追加记录",
        importance=6,
        positive_feedback=0,
        negative_feedback=0,
        access_count=0,
        last_accessed=None,
        related_ids=[],
    )


@pytest.fixture
def populated_store(tmp_path):
    """预填充 5 条多样化记忆的 MemoryStore。

    5 条记忆覆盖不同主题域（LaTeX/CI/研究/数据库/安全），
    importance 分布为 7/5/8/6/9，方便测试排序和过滤逻辑。
    """
    store = MemoryStore(store_path=str(tmp_path))
    samples = [
        Memory(
            id="mem_20260310_001",
            content="修复 LaTeX fontspec 编译错误，XeLaTeX 路径未正确配置",
            timestamp="2026-03-10T10:00:00",
            keywords=["LaTeX", "fontspec", "XeLaTeX", "编译错误"],
            tags=["bug-fix", "thesis"],
            context="XeLaTeX 引擎路径问题导致 fontspec 包加载失败",
            importance=7,
            related_ids=["mem_20260310_002"],
            access_count=2,
            last_accessed="2026-03-11T14:00:00",
        ),
        Memory(
            id="mem_20260310_002",
            content="配置 latexmk 自动编译，添加 -xelatex 参数和 synctex 支持",
            timestamp="2026-03-10T14:00:00",
            keywords=["latexmk", "自动编译", "xelatex", "synctex"],
            tags=["config", "thesis"],
            context="latexmk 配置文件实现保存即编译的 LaTeX 工作流",
            importance=5,
            related_ids=["mem_20260310_001"],
            access_count=1,
            last_accessed="2026-03-10T16:00:00",
        ),
        Memory(
            id="mem_20260311_001",
            content="精读 A-MEM 论文，提取 Zettelkasten 数据模型和联想链机制",
            timestamp="2026-03-11T09:00:00",
            keywords=["A-MEM", "Zettelkasten", "联想记忆", "数据模型"],
            tags=["research", "memory", "ai"],
            context="A-MEM 使用 Note 结构实现 agent 联想记忆系统",
            importance=8,
            related_ids=["mem_20260311_002"],
            access_count=1,
            last_accessed="2026-03-11T18:00:00",
        ),
        Memory(
            id="mem_20260311_002",
            content="优化 PostgreSQL 查询索引，减少全表扫描提升响应速度",
            timestamp="2026-03-11T15:00:00",
            keywords=["PostgreSQL", "索引", "查询优化", "全表扫描"],
            tags=["database", "performance"],
            context="为高频查询字段添加复合索引，响应时间从 2s 降至 50ms",
            importance=6,
            related_ids=[],
            access_count=0,
            last_accessed=None,
        ),
        Memory(
            id="mem_20260312_001",
            content="实现 JWT 认证中间件，添加 token 过期检测和刷新机制",
            timestamp="2026-03-12T10:00:00",
            keywords=["JWT", "认证", "中间件", "token", "安全"],
            tags=["security", "auth", "feature"],
            context="Bearer token 过期时自动刷新，避免用户被强制登出",
            importance=9,
            related_ids=[],
            access_count=3,
            last_accessed="2026-03-14T08:00:00",
        ),
    ]
    for m in samples:
        store.add(m)
    return store


@pytest.fixture
def memory_factory():
    """工厂函数：灵活创建 Memory 对象，kwargs 覆盖默认值。

    用法：
        def test_something(memory_factory):
            mem = memory_factory(importance=9, tags=["security"])
            mem2 = memory_factory(id="custom_001", content="自定义内容")
    """
    _counter = [0]

    def _create(
        id=None,
        content="测试记忆内容",
        timestamp="2026-03-14T10:00:00",
        keywords=None,
        tags=None,
        context="测试上下文",
        importance=5,
        **kwargs
    ):
        _counter[0] += 1
        return Memory(
            id=id or f"mem_factory_{_counter[0]:04d}",
            content=content,
            timestamp=timestamp,
            keywords=keywords if keywords is not None else ["测试", "记忆", "内容"],
            tags=tags if tags is not None else ["test"],
            context=context,
            importance=importance,
            **kwargs
        )

    return _create
