"""性能测试：记忆系统在不同规模下的响应时间基准。

测试规模：100 / 500 / 1000 条记忆
测试维度：
  - retrieve()          检索时间
  - find_similar_pairs() 合并对查找时间
  - apply_decay()        衰减时间
  - load_all()           加载时间
  - check_memory_health  健康检查时间
  - 完整流水线          端到端时间

性能阈值：
  - retrieve(1000)               < 2 秒
  - find_similar_pairs(500)      < 5 秒
  - load_all(1000)               < 3 秒
  - apply_decay(1000)            < 2 秒
  - health_check(1000)           < 1 秒
"""

import os
import sys
import time
import random
import string
import pytest
from datetime import datetime, timedelta

# 将 scripts 目录加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from memory_store import Memory, MemoryStore
from retriever import retrieve
from consolidator import find_similar_pairs
from decay_engine import apply_decay
from feedback_loop import check_memory_health, filter_by_health


# ==================== 标记 ====================

pytestmark = pytest.mark.slow


# ==================== 工具函数 ====================

# 各维度主题词池：保证不同记忆使用不同关键词，避免相似度过高导致合并测试异常慢
_TOPIC_DOMAINS = [
    ("machine-learning", ["gradient", "backprop", "neural", "loss", "optimizer"], ["ml", "ai", "research"]),
    ("database", ["index", "query", "schema", "transaction", "deadlock"], ["db", "backend", "data"]),
    ("networking", ["tcp", "socket", "packet", "latency", "bandwidth"], ["network", "infra", "ops"]),
    ("frontend", ["component", "render", "state", "props", "dom"], ["react", "ui", "web"]),
    ("devops", ["pipeline", "container", "deploy", "rollback", "helm"], ["ci", "cd", "ops"]),
    ("security", ["encryption", "token", "auth", "cve", "pentest"], ["security", "infosec"]),
    ("compiler", ["lexer", "parser", "ast", "codegen", "ssa"], ["compilers", "systems", "cs"]),
    ("blockchain", ["consensus", "hash", "block", "merkle", "tx"], ["crypto", "web3", "blockchain"]),
    ("testing", ["mock", "stub", "fixture", "coverage", "mutation"], ["qa", "testing", "tdd"]),
    ("observability", ["trace", "metric", "span", "alert", "slo"], ["monitoring", "ops", "infra"]),
    ("distributed", ["raft", "paxos", "shard", "replica", "quorum"], ["distributed", "systems"]),
    ("graphics", ["shader", "vertex", "fragment", "texture", "rasterize"], ["gpu", "graphics", "games"]),
    ("nlp", ["token", "embedding", "attention", "bert", "corpus"], ["nlp", "ai", "research"]),
    ("robotics", ["servo", "kinematics", "sensor", "slam", "trajectory"], ["robotics", "iot"]),
    ("cloud", ["lambda", "s3", "vpc", "autoscale", "loadbalancer"], ["cloud", "aws", "infra"]),
    ("os", ["kernel", "syscall", "thread", "semaphore", "interrupt"], ["os", "systems", "c"]),
    ("gamedev", ["physics", "collision", "sprite", "tilemap", "pathfind"], ["unity", "games"]),
    ("embedded", ["firmware", "gpio", "uart", "interrupt", "flash"], ["embedded", "iot", "c"]),
    ("bioinformatics", ["genome", "alignment", "fastq", "phylogeny", "codon"], ["bio", "research"]),
    ("quantum", ["qubit", "entangle", "superposition", "decoherence", "gate"], ["quantum", "physics"]),
]

_RANDOM_WORDS = list(string.ascii_lowercase) + [
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi", "rho",
    "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega",
    "red", "blue", "green", "yellow", "purple", "orange", "cyan", "magenta",
    "swift", "rust", "python", "java", "golang", "kotlin", "scala", "elixir",
]


def _random_word() -> str:
    return random.choice(_RANDOM_WORDS)


def _random_sentence(n_words: int = 10) -> str:
    return " ".join(_random_word() for _ in range(n_words))


def generate_memories(tmp_path, count: int) -> MemoryStore:
    """生成 count 个随机 Memory 并写入 tmp_path，返回 MemoryStore。

    为避免相似度过高（使 consolidate 测试异常慢），每条记忆使用不同的主题域。
    确保关键词 + 标签各不相同，Jaccard 相似度天然较低。
    """
    store = MemoryStore(store_path=str(tmp_path))
    base_time = datetime(2025, 1, 1, 0, 0, 0)
    n_domains = len(_TOPIC_DOMAINS)

    for i in range(count):
        domain_idx = i % n_domains
        domain_name, domain_kw, domain_tags = _TOPIC_DOMAINS[domain_idx]

        # 每条记忆独立添加随机后缀，保证全局唯一
        unique_suffix = f"_{i}_{_random_word()}"
        kw = [f"{k}{unique_suffix}" for k in domain_kw[:3]] + [_random_word(), _random_word()]
        tags = [f"{t}{unique_suffix}" for t in domain_tags[:2]]

        importance = random.randint(1, 10)
        ts = (base_time + timedelta(hours=i * 2)).isoformat()
        # 随机设置最近访问时间：约 30% 的记忆有 last_accessed
        last_accessed = (
            (base_time + timedelta(hours=i * 2 + random.randint(1, 48))).isoformat()
            if random.random() < 0.3
            else None
        )

        mem = Memory(
            id=f"perf_{i:04d}",
            content=f"[{domain_name}] {_random_sentence(12)} index={i}",
            timestamp=ts,
            keywords=kw,
            tags=tags,
            context=f"性能测试记忆 #{i}，主题={domain_name}，{_random_sentence(6)}",
            importance=importance,
            related_ids=[],
            access_count=random.randint(0, 5),
            last_accessed=last_accessed,
            name=f"perf-mem-{i:04d}",
            description=f"性能测试条目 {i}",
            type="task",
            positive_feedback=random.randint(0, 3),
            negative_feedback=random.randint(0, 1),
        )
        store.add(mem)

    return store


# ==================== Fixtures ====================

@pytest.fixture(scope="module")
def store_100(tmp_path_factory):
    """100 条记忆的预生成 store（module 级别，只生成一次）。"""
    tmp = tmp_path_factory.mktemp("perf100")
    return generate_memories(tmp, 100)


@pytest.fixture(scope="module")
def store_500(tmp_path_factory):
    """500 条记忆的预生成 store。"""
    tmp = tmp_path_factory.mktemp("perf500")
    return generate_memories(tmp, 500)


@pytest.fixture(scope="module")
def store_1000(tmp_path_factory):
    """1000 条记忆的预生成 store。"""
    tmp = tmp_path_factory.mktemp("perf1000")
    return generate_memories(tmp, 1000)


# ==================== 辅助：计时上下文管理器 ====================

class Timer:
    """简单计时器，用 with Timer() as t 包裹被测代码，t.elapsed 取耗时（秒）。"""

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, *_):
        self.elapsed = time.time() - self._start


# ==================== load_all 性能测试 ====================

class TestLoadAll:
    """MemoryStore.load_all() 在不同规模下的加载时间。"""

    def test_load_all_100(self, store_100):
        """100 条记忆 load_all 应 < 0.5 秒。"""
        with Timer() as t:
            mems = store_100.load_all()
        assert len(mems) == 100, f"期望 100 条，实际 {len(mems)} 条"
        assert t.elapsed < 0.5, f"load_all(100) 耗时 {t.elapsed:.3f}s，超过阈值 0.5s"

    def test_load_all_500(self, store_500):
        """500 条记忆 load_all 应 < 1.5 秒。"""
        with Timer() as t:
            mems = store_500.load_all()
        assert len(mems) == 500, f"期望 500 条，实际 {len(mems)} 条"
        assert t.elapsed < 1.5, f"load_all(500) 耗时 {t.elapsed:.3f}s，超过阈值 1.5s"

    def test_load_all_1000(self, store_1000):
        """1000 条记忆 load_all 应 < 3 秒。"""
        with Timer() as t:
            mems = store_1000.load_all()
        assert len(mems) == 1000, f"期望 1000 条，实际 {len(mems)} 条"
        assert t.elapsed < 3.0, f"load_all(1000) 耗时 {t.elapsed:.3f}s，超过阈值 3.0s"


# ==================== retrieve 性能测试 ====================

class TestRetrieve:
    """retrieve() 三维评分检索在不同规模下的响应时间。"""

    def test_retrieve_100(self, store_100):
        """100 条记忆的检索应 < 0.3 秒。"""
        with Timer() as t:
            results = retrieve("machine learning neural network", store_100, top_k=5)
        assert isinstance(results, list)
        assert t.elapsed < 0.3, f"retrieve(100) 耗时 {t.elapsed:.3f}s，超过阈值 0.3s"

    def test_retrieve_500(self, store_500):
        """500 条记忆的检索应 < 1 秒。"""
        with Timer() as t:
            results = retrieve("database query optimization index", store_500, top_k=5)
        assert isinstance(results, list)
        assert t.elapsed < 1.0, f"retrieve(500) 耗时 {t.elapsed:.3f}s，超过阈值 1.0s"

    def test_retrieve_1000(self, store_1000):
        """1000 条记忆的检索应 < 2 秒。"""
        with Timer() as t:
            results = retrieve("networking latency tcp socket", store_1000, top_k=5)
        assert isinstance(results, list)
        assert t.elapsed < 2.0, f"retrieve(1000) 耗时 {t.elapsed:.3f}s，超过阈值 2.0s"

    def test_retrieve_returns_results(self, store_1000):
        """验证 retrieve 返回有效结果（功能性保障）。"""
        results = retrieve("security encryption auth token", store_1000, top_k=3)
        assert len(results) <= 3
        for mem, score in results:
            assert isinstance(score, float)
            assert score >= 0.0

    def test_retrieve_spread_disabled_1000(self, store_1000):
        """关闭扩散激活时，1000 条记忆的检索应 < 1.5 秒。"""
        with Timer() as t:
            results = retrieve(
                "compiler ast parser lexer",
                store_1000,
                top_k=5,
                spread=False,
            )
        assert isinstance(results, list)
        assert t.elapsed < 1.5, f"retrieve(1000, spread=False) 耗时 {t.elapsed:.3f}s，超过阈值 1.5s"


# ==================== consolidate find_similar_pairs 性能测试 ====================

class TestConsolidate:
    """find_similar_pairs() 两两相似度计算的性能。

    注意：generate_memories 保证了不同主题域使用不同关键词，
    Jaccard 相似度极低，pairs 结果通常为空，但 O(n²) 遍历仍然发生，
    测试的是遍历和相似度计算的性能。
    """

    def test_consolidate_find_pairs_100(self, store_100):
        """100 条记忆的两两相似度计算应 < 0.5 秒。"""
        mems = store_100.load_all()
        with Timer() as t:
            pairs = find_similar_pairs(mems, threshold=0.85)
        assert isinstance(pairs, list)
        assert t.elapsed < 0.5, f"find_similar_pairs(100) 耗时 {t.elapsed:.3f}s，超过阈值 0.5s"

    def test_consolidate_find_pairs_500(self, store_500):
        """500 条记忆的两两相似度计算应 < 5 秒。"""
        mems = store_500.load_all()
        with Timer() as t:
            pairs = find_similar_pairs(mems, threshold=0.85)
        assert isinstance(pairs, list)
        assert t.elapsed < 5.0, f"find_similar_pairs(500) 耗时 {t.elapsed:.3f}s，超过阈值 5.0s"

    def test_consolidate_find_pairs_low_threshold(self, store_100):
        """低阈值（0.3）下 100 条记忆的相似度计算应 < 0.5 秒。"""
        mems = store_100.load_all()
        with Timer() as t:
            pairs = find_similar_pairs(mems, threshold=0.3)
        assert isinstance(pairs, list)
        assert t.elapsed < 0.5, f"find_similar_pairs(100, threshold=0.3) 耗时 {t.elapsed:.3f}s"


# ==================== decay apply_decay 性能测试 ====================

class TestDecay:
    """apply_decay() 对批量记忆施加时间衰减的性能。"""

    def _batch_decay(self, store, now=None):
        """加载所有记忆并逐条应用衰减，返回耗时和结果数。"""
        mems = store.load_all()
        now = now or datetime(2026, 3, 15, 0, 0, 0)
        results = []
        with Timer() as t:
            for m in mems:
                results.append(apply_decay(m, now=now))
        return t.elapsed, results

    def test_decay_100(self, store_100):
        """100 条记忆批量衰减应 < 0.1 秒。"""
        elapsed, results = self._batch_decay(store_100)
        assert len(results) == 100
        assert elapsed < 0.1, f"apply_decay×100 耗时 {elapsed:.3f}s，超过阈值 0.1s"

    def test_decay_500(self, store_500):
        """500 条记忆批量衰减应 < 0.5 秒。"""
        elapsed, results = self._batch_decay(store_500)
        assert len(results) == 500
        assert elapsed < 0.5, f"apply_decay×500 耗时 {elapsed:.3f}s，超过阈值 0.5s"

    def test_decay_1000(self, store_1000):
        """1000 条记忆批量衰减应 < 2 秒。"""
        elapsed, results = self._batch_decay(store_1000)
        assert len(results) == 1000
        assert elapsed < 2.0, f"apply_decay×1000 耗时 {elapsed:.3f}s，超过阈值 2.0s"

    def test_decay_result_correctness(self, store_100):
        """验证衰减结果的正确性：importance 不超过原始值，不低于 floor。"""
        mems = store_100.load_all()
        now = datetime(2030, 1, 1, 0, 0, 0)  # 远未来，应触发明显衰减
        for m in mems:
            decayed = apply_decay(m, now=now)
            floor_val = max(1, int(m.importance * 0.2))
            assert decayed.importance >= floor_val, (
                f"记忆 {m.id} 衰减后 importance={decayed.importance} 低于 floor={floor_val}"
            )
            assert decayed.importance <= m.importance, (
                f"记忆 {m.id} 衰减后 importance={decayed.importance} 高于原始值 {m.importance}"
            )


# ==================== health_check 批量检查性能 ====================

class TestHealthCheck:
    """check_memory_health() 批量健康检查的性能。"""

    def _batch_health_check(self, store):
        """加载所有记忆并批量检查健康状态，返回耗时和统计。"""
        mems = store.load_all()
        results = {}
        with Timer() as t:
            for m in mems:
                results[m.id] = check_memory_health(m)
        return t.elapsed, results

    def test_health_check_batch_100(self, store_100):
        """100 条记忆批量健康检查应 < 0.05 秒。"""
        elapsed, results = self._batch_health_check(store_100)
        assert len(results) == 100
        assert elapsed < 0.05, f"health_check×100 耗时 {elapsed:.3f}s，超过阈值 0.05s"

    def test_health_check_batch_500(self, store_500):
        """500 条记忆批量健康检查应 < 0.2 秒。"""
        elapsed, results = self._batch_health_check(store_500)
        assert len(results) == 500
        assert elapsed < 0.2, f"health_check×500 耗时 {elapsed:.3f}s，超过阈值 0.2s"

    def test_health_check_batch_1000(self, store_1000):
        """1000 条记忆批量健康检查应 < 1 秒。"""
        elapsed, results = self._batch_health_check(store_1000)
        assert len(results) == 1000
        assert elapsed < 1.0, f"health_check×1000 耗时 {elapsed:.3f}s，超过阈值 1.0s"

    def test_health_check_distribution(self, store_1000):
        """验证健康状态分布合理：大多数为 healthy（功能性验证）。"""
        mems = store_1000.load_all()
        statuses = [check_memory_health(m) for m in mems]
        healthy_count = statuses.count("healthy")
        # generate_memories 生成的记忆 positive_feedback<=3, negative_feedback<=1
        # 因此大多数记忆总反馈 < 3，应为 healthy
        assert healthy_count > len(mems) * 0.5, (
            f"healthy 记忆数 {healthy_count}/{len(mems)} 低于预期 50%"
        )

    def test_filter_by_health_1000(self, store_1000):
        """filter_by_health 在 1000 条记忆下应 < 1 秒。"""
        mems = store_1000.load_all()
        with Timer() as t:
            filtered = filter_by_health(mems, include_warning=True)
        assert isinstance(filtered, list)
        assert t.elapsed < 1.0, f"filter_by_health(1000) 耗时 {t.elapsed:.3f}s，超过阈值 1.0s"


# ==================== 端到端流水线测试 ====================

class TestEndToEndPipeline:
    """完整流程：load → health filter → retrieve → find_similar_pairs → apply_decay。"""

    def test_end_to_end_pipeline_100(self, store_100):
        """100 条记忆的完整流水线应 < 1 秒。

        流程：
        1. load_all
        2. filter_by_health
        3. retrieve（检索 top-5）
        4. find_similar_pairs（threshold=0.85）
        5. apply_decay（批量衰减）
        """
        now = datetime(2026, 3, 15, 0, 0, 0)

        with Timer() as t:
            # Step 1: 加载
            mems = store_100.load_all()

            # Step 2: 健康过滤
            healthy_mems = filter_by_health(mems, include_warning=True)

            # Step 3: 检索
            results = retrieve("testing mock fixture coverage", store_100, top_k=5, now=now)

            # Step 4: 查找相似对
            pairs = find_similar_pairs(healthy_mems, threshold=0.85)

            # Step 5: 批量衰减
            decayed = [apply_decay(m, now=now) for m in healthy_mems]

        assert len(mems) == 100
        assert isinstance(results, list)
        assert isinstance(pairs, list)
        assert len(decayed) == len(healthy_mems)
        assert t.elapsed < 1.0, f"端到端流水线(100) 耗时 {t.elapsed:.3f}s，超过阈值 1.0s"

    def test_end_to_end_pipeline_500(self, store_500):
        """500 条记忆的完整流水线应 < 8 秒（含 O(n²) 合并步骤）。"""
        now = datetime(2026, 3, 15, 0, 0, 0)

        with Timer() as t:
            mems = store_500.load_all()
            healthy_mems = filter_by_health(mems, include_warning=True)
            results = retrieve("distributed raft consensus shard", store_500, top_k=5, now=now)
            pairs = find_similar_pairs(healthy_mems, threshold=0.85)
            decayed = [apply_decay(m, now=now) for m in healthy_mems]

        assert len(mems) == 500
        assert isinstance(results, list)
        assert t.elapsed < 8.0, f"端到端流水线(500) 耗时 {t.elapsed:.3f}s，超过阈值 8.0s"

    def test_retrieve_multiple_queries_100(self, store_100):
        """连续执行 10 次检索（100 条），总时间应 < 2 秒。"""
        queries = [
            "machine learning gradient descent",
            "database index query plan",
            "networking tcp packet loss",
            "frontend react component state",
            "devops kubernetes helm deploy",
            "security token authentication",
            "compiler ast code generation",
            "blockchain consensus merkle",
            "testing coverage mock stub",
            "observability trace metric alert",
        ]
        now = datetime(2026, 3, 15, 0, 0, 0)
        with Timer() as t:
            for q in queries:
                retrieve(q, store_100, top_k=3, now=now)
        assert t.elapsed < 2.0, f"10 次连续检索(100) 总耗时 {t.elapsed:.3f}s，超过阈值 2.0s"

    def test_store_count_perf(self, store_1000):
        """store.count() 在 1000 条记忆下应 < 0.1 秒（基于 glob，O(n)）。"""
        with Timer() as t:
            count = store_1000.count()
        assert count == 1000
        assert t.elapsed < 0.1, f"store.count(1000) 耗时 {t.elapsed:.3f}s，超过阈值 0.1s"


# ==================== 数据生成测试（自验证） ====================

class TestDataGeneration:
    """验证 generate_memories helper 本身的正确性。"""

    def test_generate_100_creates_correct_count(self, store_100):
        mems = store_100.load_all()
        assert len(mems) == 100

    def test_generate_500_creates_correct_count(self, store_500):
        mems = store_500.load_all()
        assert len(mems) == 500

    def test_generated_memories_have_unique_ids(self, store_100):
        mems = store_100.load_all()
        ids = [m.id for m in mems]
        assert len(ids) == len(set(ids)), "记忆 ID 存在重复"

    def test_generated_memories_have_valid_importance(self, store_100):
        mems = store_100.load_all()
        for m in mems:
            assert 1 <= m.importance <= 10, f"记忆 {m.id} 的 importance={m.importance} 超出范围 [1, 10]"

    def test_generated_memories_low_similarity(self, store_100):
        """验证生成的记忆相似度低（大多数对不应超过阈值 0.5）。"""
        mems = store_100.load_all()
        # 取前 20 条做快速验证（避免 O(n²) 过慢）
        sample = mems[:20]
        pairs_50 = find_similar_pairs(sample, threshold=0.5)
        # 大多数对不应相似（允许少量偶然相似）
        total_pairs = len(sample) * (len(sample) - 1) // 2
        similar_ratio = len(pairs_50) / max(1, total_pairs)
        assert similar_ratio < 0.2, (
            f"生成数据相似度过高：{len(pairs_50)}/{total_pairs} 对超过阈值 0.5，比率 {similar_ratio:.2%}"
        )
