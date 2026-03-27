#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto-iterate: 8 维 WhoAmI.md 评估脚本

对单个 agent 角色定义文件（WhoAmI.md）进行 8 维加权评估。

维度与权重：
  角色边界(15%) + 方法论深度(15%) + 工具链覆盖(10%) + 防幻觉机制(15%)
  + 输出标准化(15%) + 简洁性(10%) + 可执行性(10%) + 自洽性(10%)

用法: python3 evaluate_whoami.py <whoami.md-path>
"""

import re
import sys
from pathlib import Path
from typing import NamedTuple


# ==================== 数据模型 ====================

class DimResult(NamedTuple):
    """单维度评估结果。"""

    score: float
    bonuses: list[str]
    deductions: list[str]


# ==================== 维度配置 ====================

WEIGHTS: dict[str, float] = {
    "role_boundary": 0.15,
    "methodology": 0.15,
    "toolchain": 0.10,
    "anti_hallucination": 0.15,
    "output_standard": 0.15,
    "conciseness": 0.10,
    "actionability": 0.10,
    "consistency": 0.10,
}

# 简洁性阶梯：(上限行数, 分数)
CONCISENESS_TIERS: list[tuple[int, float]] = [
    (100, 10.0),
    (150, 8.5),
    (200, 7.0),
    (250, 5.5),
    (300, 4.0),
    (350, 2.5),
    (400, 1.5),
]
CONCISENESS_FLOOR = 0.5

# 角色边界模糊词
BOUNDARY_FUZZY: list[str] = [
    "视情况", "可能负责", "有时", "看情况",
    "sometimes responsible", "might handle",
]


# ==================== 工具函数 ====================

def _clamp(val: float, lo: float = 0.0, hi: float = 10.0) -> float:
    """Clamp 值到 [lo, hi]。"""
    return max(lo, min(hi, val))


def _count_re(pattern: str, text: str) -> int:
    """统计正则匹配次数。"""
    return len(re.findall(pattern, text, re.MULTILINE))


def _has_section(text: str, keywords: list[str]) -> bool:
    """检查是否存在包含 keywords 中任一项的章节标题。"""
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


def _extract_section(text: str, heading: str) -> str:
    """提取 heading 到下一个同级 heading 之间的内容。

    :param text: 全文
    :param heading: heading 关键词（大小写不敏感）
    """
    pat = re.compile(
        r"^(#{1,3}\s*[^\n]*" + re.escape(heading) + r"[^\n]*)"
        r"(.*?)(?=\n#{1,3}\s|\Z)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    m = pat.search(text)
    return m.group(0) if m else ""


# ==================== 维度评估配置表 ====================
# 数据驱动：每维度用配置表 + 循环，避免硬编码 if/else

# 维度 1: 角色边界 (15%, 基准 3.0, 上限 10.0)
_BOUNDARY_CHECKS: list[tuple[str, list[str], float, str]] = [
    ("section", ["工作范围", "我的工作范围", "Work Scope"],
     1.0, "has work scope section"),
    ("section", ["越权拒绝", "越权", "Out of Scope"],
     1.0, "has out-of-scope rules"),
    ("list_min3", ["我不负责", "不负责", "Not responsible"],
     1.0, "has 'not responsible' list >= 3 items"),
    ("keyword_any", ["与.*的区别", "与.*区别", "区分"],
     1.0, "has role differentiation"),
    ("section", ["工具权限", "Tool Permission"],
     1.0, "has tool permission list"),
    ("keyword_any", ["subagent_type"],
     0.5, "has subagent_type description"),
    ("no_fuzzy", BOUNDARY_FUZZY,
     1.0, "no boundary fuzzy words"),
    ("keyword_any", ["名称", "类型", "**名称**", "**类型**"],
     0.5, "has explicit role name + type"),
]

# 维度 2: 方法论深度 (15%, 基准 2.0, 上限 10.0)
_METHODOLOGY_CHECKS: list[tuple[str, list[str], float, str]] = [
    ("keyword_any", ["L0", "L1", "L2", "Level 0", "级别"],
     1.5, "has grading system"),
    ("keyword_any", ["触发条件", "trigger condition",
                     "适用", "when to use"],
     1.0, "grade trigger conditions"),
    ("keyword_any", ["时间", "< 1min", "< 5min", "< 15min"],
     0.5, "grade time expectations"),
    ("keyword_any", ["决策树", "流程图", "decision tree", "→"],
     1.0, "has decision tree / flow"),
    ("keyword_any", ["Phase A", "Phase B", "Phase C",
                     "Phase D", "Phase E", "阶段"],
     1.0, "has multi-phase protocol"),
    ("keyword_any", ["迭代", "递归", "Chain-of",
                     "Round 1", "Round 2"],
     1.0, "has iterative search strategy"),
    ("keyword_any", ["终止条件", "终止", "termination",
                     "快速退出"],
     0.5, "has termination conditions"),
    ("keyword_any", ["STORM", "多视角", "persona",
                     "multi-perspective"],
     1.0, "has multi-perspective method"),
    ("keyword_any", ["Brief", "Research Brief", "输入.*Brief"],
     0.5, "has brief input format"),
]

# 维度 3: 工具链覆盖 (10%, 基准 4.0, 上限 10.0)
_TOOLCHAIN_CHECKS: list[tuple[str, list[str], float, str]] = [
    ("section", ["工具", "Tool", "允许", "Permission"],
     1.0, "has tool list"),
    ("keyword_any", ["降级", "graceful", "fallback",
                     "不可用", "unavailable"],
     2.0, "has degradation strategy"),
    ("keyword_any", ["探针", "probe", "健康", "health check",
                     "PROBE_OK"],
     1.5, "has health probe"),
    ("code_block_has", ["WebSearch", "WebFetch", "Read",
                        "Bash", "Glob", "Grep"],
     1.0, "has tool call examples"),
    ("keyword_any", ["完整模式", "搜索模式", "本地模式", "终止"],
     0.5, "has degradation levels"),
]

# 维度 4: 防幻觉机制 (15%, 基准 2.0, 上限 10.0)
_ANTI_HALLUCINATION_CHECKS: list[tuple[str, list[str], float, str]] = [
    ("section", ["幻觉", "hallucination", "Hallucination"],
     1.5, "has hallucination detection section"),
    ("keyword_any", ["禁止行为", "禁止", "Prohibited", "禁止编造"],
     1.0, "has prohibited behavior list"),
    ("keyword_any", ["工具调用失败", "tool failure",
                     "调用失败", "失败后"],
     1.0, "has tool failure handling"),
    ("keyword_any", ["连续.*失败.*终止", "连续 2 次",
                     "consecutive", "立即终止"],
     1.0, "has consecutive-failure-then-stop rule"),
    ("keyword_any", ["完整性声明", "integrity statement",
                     "完整性"],
     1.0, "has output integrity statement template"),
    ("keyword_any", ["自检", "self-check", "实际调用"],
     1.0, "has self-check step"),
    ("keyword_any", ["2026-03-18", "事件", "incident",
                     "教训", "lesson"],
     0.5, "references historical incident"),
    ("keyword_any", ["[V]", "[S]", "[I]", "[U]",
                     "Verified", "Single-source",
                     "Inferred", "Unverified"],
     1.0, "has evidence grading system"),
]

# 维度 5: 输出标准化 (15%, 基准 2.0, 上限 10.0)
_OUTPUT_CHECKS: list[tuple[str, list[str], float, str]] = [
    ("keyword_any", ["报告模板", "report template", "输出格式",
                     "output format", "调研报告"],
     1.5, "has report template"),
    ("keyword_any", ["Facts", "Analysis", "Recommendations",
                     "事实层", "分析层", "建议层"],
     1.5, "has layered output structure"),
    ("keyword_any", ["[V]", "[S]", "[I]", "[U]",
                     "证据分级"],
     1.5, "has evidence grade labels"),
    ("keyword_any", ["引用格式", "citation format",
                     "DOI", "来源"],
     1.0, "has citation format spec"),
    ("keyword_any", ["质量门禁", "V 最低", "U 最高",
                     "门禁"],
     1.0, "has quality gate (V/S min ratio)"),
    ("keyword_any", ["完整性声明", "调研完整性"],
     0.5, "has integrity statement"),
    ("keyword_any", ["记忆保存", "quick-add",
                     "agent-memory"],
     0.5, "has memory save command"),
    ("keyword_any", ["自动触发", "auto trigger",
                     "→ shin", "→ kaze", "→ haku"],
     0.5, "has auto-trigger rules"),
]

# 维度 7: 可执行性 (10%, 基准 3.0, 上限 10.0)
_ACTIONABILITY_CHECKS: list[tuple[str, list[str], float, str]] = [
    ("code_block_count", [], 1.0, "has code blocks"),
    ("code_block_min3", [], 0.5, "code blocks >= 3"),
    ("numbered_steps", [], 1.0, "has numbered steps >= 3"),
    ("keyword_any", ["输入", "输出", "input", "output"],
     1.0, "steps have I/O spec"),
    ("keyword_any", ["条件", "如果", "若", "if", "→"],
     0.5, "has conditional branching"),
    ("file_path_count", [], 0.5, "has concrete file paths"),
    ("keyword_any", ["quick-add", "agent-memory",
                     "cli.py"],
     1.0, "has memory save command template"),
    ("table_rows", [], 0.5, "has tables >= 3 rows"),
    ("multi_tables", [], 0.5, "has multiple tables >= 3"),
    ("no_vague", ["视情况而定", "看情况", "酌情",
                  "depends on context"],
     0.5, "no vague guidance"),
]


# ==================== 维度评估函数 ====================

def _run_checks(
    content: str,
    checks: list[tuple[str, list[str], float, str]],
    base: float,
) -> DimResult:
    """通用配置驱动评估。

    :param content: 文件全文
    :param checks: 检查配置列表
    :param base: 基准分数
    """
    score = base
    bonuses: list[str] = []
    deductions: list[str] = []
    lower = content.lower()

    for check_type, params, pts, label in checks:
        hit = _dispatch_check(check_type, params, content, lower)
        if hit:
            score += pts
            bonuses.append(f"{label} (+{pts})")

    return DimResult(_clamp(score), bonuses, deductions)


def _dispatch_check(
    check_type: str,
    params: list[str],
    content: str,
    lower: str,
) -> bool:
    """Dispatch a single check by type.

    :param check_type: check type identifier
    :param params: check-specific parameters
    :param content: original text
    :param lower: lowercased text
    """
    dispatch = {
        "section": lambda: _check_section(content, params),
        "keyword_any": lambda: _check_keyword_any(lower, params),
        "no_fuzzy": lambda: _check_no_fuzzy(lower, params),
        "list_min3": lambda: _check_list_min3(content, params),
        "code_block_has": lambda: _check_code_block_has(
            content, params),
        "code_block_count": lambda: _check_code_block_count(
            content),
        "code_block_min3": lambda: _check_code_block_min3(
            content),
        "numbered_steps": lambda: _check_numbered_steps(content),
        "file_path_count": lambda: _check_file_paths(content),
        "table_rows": lambda: _check_table_rows(content),
        "multi_tables": lambda: _check_multi_tables(content),
        "no_vague": lambda: _check_no_vague(lower, params),
    }
    fn = dispatch.get(check_type)
    return fn() if fn else False


def _check_section(content: str, kws: list[str]) -> bool:
    """Check if any keyword appears in a heading."""
    return _has_section(content, kws)


def _check_keyword_any(lower: str, kws: list[str]) -> bool:
    """Check if any keyword is present (case-insensitive)."""
    return any(k.lower() in lower for k in kws)


def _check_no_fuzzy(lower: str, fuzzy_list: list[str]) -> bool:
    """Check that no fuzzy words are present."""
    return not any(w.lower() in lower for w in fuzzy_list)


def _check_list_min3(
    content: str, heading_kws: list[str],
) -> bool:
    """Check that a section has >= 3 list items.

    :param content: full text
    :param heading_kws: heading keywords to find the section
    """
    for kw in heading_kws:
        sec = _extract_section(content, kw)
        if sec:
            items = _count_re(r"^\s*[-*]\s+", sec)
            if items >= 3:
                return True
    return False


def _check_code_block_has(
    content: str, tool_names: list[str],
) -> bool:
    """Check that code blocks mention any of the tool names."""
    blocks = re.findall(
        r"```.*?```", content, re.DOTALL)
    for block in blocks:
        if any(t in block for t in tool_names):
            return True
    return False


def _check_code_block_count(content: str) -> bool:
    """Check that there is at least 1 code block."""
    return _count_re(r"^```", content) >= 2


def _check_code_block_min3(content: str) -> bool:
    """Check that there are >= 3 code blocks (6 fence markers)."""
    return _count_re(r"^```", content) >= 6


def _check_numbered_steps(content: str) -> bool:
    """Check for >= 3 numbered steps."""
    return _count_re(r"^\s*\d+\.\s", content) >= 3


def _check_file_paths(content: str) -> bool:
    """Check for concrete file paths."""
    paths = re.findall(r"(?:~/|/|\./)[\w./-]+\.\w+", content)
    return len(paths) >= 1


def _check_table_rows(content: str) -> bool:
    """Check for tables with >= 3 rows."""
    return _count_re(r"^\s*\|.*\|", content) >= 3


def _check_multi_tables(content: str) -> bool:
    """Check for >= 3 separate tables (header+separator pairs)."""
    seps = _count_re(r"^\s*\|[\s:|-]+\|", content)
    return seps >= 3


def _check_no_vague(lower: str, vague: list[str]) -> bool:
    """Check that no vague guidance phrases are present."""
    return not any(v.lower() in lower for v in vague)


# ==================== 维度 1: 角色边界 ====================

def eval_role_boundary(content: str) -> DimResult:
    """评估角色边界清晰度。基准 3.0，上限 10.0。

    :param content: WhoAmI.md 全文
    """
    return _run_checks(content, _BOUNDARY_CHECKS, base=3.0)


# ==================== 维度 2: 方法论深度 ====================

def eval_methodology(content: str) -> DimResult:
    """评估方法论深度。基准 2.0，上限 10.0。

    :param content: WhoAmI.md 全文
    """
    return _run_checks(content, _METHODOLOGY_CHECKS, base=2.0)


# ==================== 维度 3: 工具链覆盖 ====================

def eval_toolchain(content: str) -> DimResult:
    """评估工具链覆盖。基准 4.0，上限 10.0。

    :param content: WhoAmI.md 全文
    """
    return _run_checks(content, _TOOLCHAIN_CHECKS, base=4.0)


# ==================== 维度 4: 防幻觉机制 ====================

def eval_anti_hallucination(content: str) -> DimResult:
    """评估防幻觉机制。基准 2.0，上限 10.0。

    :param content: WhoAmI.md 全文
    """
    return _run_checks(
        content, _ANTI_HALLUCINATION_CHECKS, base=2.0)


# ==================== 维度 5: 输出标准化 ====================

def eval_output_standard(content: str) -> DimResult:
    """评估输出标准化。基准 2.0，上限 10.0。

    :param content: WhoAmI.md 全文
    """
    return _run_checks(content, _OUTPUT_CHECKS, base=2.0)


# ==================== 维度 6: 简洁性 ====================

def _tier_score(line_count: int) -> float:
    """Return tier-based score for line count."""
    for limit, tier in CONCISENESS_TIERS:
        if line_count <= limit:
            return tier
    return CONCISENESS_FLOOR


def _max_consecutive_blanks(lines: list[str]) -> int:
    """Return max run of consecutive blank lines."""
    consec = mx = 0
    for ln in lines:
        consec = consec + 1 if not ln.strip() else 0
        mx = max(mx, consec)
    return mx


def _duplicate_lines(lines: list[str]) -> list[str]:
    """Return lines that appear more than 3 times."""
    counts: dict[str, int] = {}
    for ln in lines:
        stripped = ln.strip()
        if stripped:
            counts[stripped] = counts.get(stripped, 0) + 1
    return [ln for ln, cnt in counts.items() if cnt > 3]


def eval_conciseness(content: str) -> DimResult:
    """评估简洁性。阶梯制，上限 10.0。

    :param content: WhoAmI.md 全文
    """
    bonuses: list[str] = []
    deductions: list[str] = []
    lines = content.splitlines()
    n = len(lines)

    score = _tier_score(n)
    bonuses.append(f"{n} lines -> base {score}")

    blanks = sum(1 for ln in lines if not ln.strip())
    if n > 0 and blanks / n > 0.25:
        score -= 1.0
        deductions.append(
            f"blank ratio {blanks / n:.0%} > 25% (-1.0)")

    mx = _max_consecutive_blanks(lines)
    if mx >= 3:
        score -= 0.5
        deductions.append(
            f"consecutive blanks {mx} >= 3 (-0.5)")

    duplicates = _duplicate_lines(lines)
    if duplicates:
        score -= 1.5
        deductions.append(
            f"repeated lines (>3x): {len(duplicates)} (-1.5)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 维度 7: 可执行性 ====================

def eval_actionability(content: str) -> DimResult:
    """评估可执行性。基准 3.0，上限 10.0。

    :param content: WhoAmI.md 全文
    """
    return _run_checks(content, _ACTIONABILITY_CHECKS, base=3.0)


# ==================== 维度 8: 自洽性（子检查函数） ====================

_TOOL_RE = (
    r"\b(Read|Write|Edit|Bash|Glob|Grep|"
    r"WebSearch|WebFetch)\b"
)


def _check_tool_perm(
    content: str,
) -> tuple[float, list[str], set[str]]:
    """Check tool permissions vs actual usage.

    :param content: full text
    :returns: (deduction, issues, perm_tools)
    """
    perm_sec = (_extract_section(content, "工具权限")
                or _extract_section(content, "Tool Permission"))
    body_tools = set(re.findall(_TOOL_RE, content))
    perm_tools = set(re.findall(_TOOL_RE, perm_sec))
    extra = body_tools - perm_tools
    if perm_tools and extra:
        return 1.0, [
            f"tools used but not in permissions: "
            f"{extra} (-1.0)"], perm_tools
    return 0.0, [], perm_tools


def _check_identity(content: str) -> tuple[float, list[str]]:
    """Check role name and type consistency.

    :param content: full text
    """
    ded = 0.0
    issues: list[str] = []
    for label, pat in [
        ("names", r"\*\*名称\*\*[：:]\s*(\S+)"),
        ("types", r"\*\*类型\*\*[：:]\s*(\S+)"),
    ]:
        vals = set(re.findall(pat, content))
        if len(vals) > 1:
            ded += 0.5
            issues.append(
                f"inconsistent role {label}: {vals} (-0.5)")
    return ded, issues


def _check_level_defs(content: str) -> tuple[float, list[str]]:
    """Check methodology level definitions consistency.

    :param content: full text
    """
    defs = re.findall(r"\*\*L(\d)\*\*\s*\|?\s*(\S+)", content)
    level_map: dict[str, set[str]] = {}
    for lvl, desc in defs:
        level_map.setdefault(lvl, set()).add(desc)
    for lvl, descs in level_map.items():
        if len(descs) > 1:
            return 1.0, [
                f"L{lvl} described differently: "
                f"{descs} (-1.0)"]
    return 0.0, []


def _check_scope_conflict(
    content: str,
) -> tuple[float, list[str]]:
    """Check not-responsible vs work-scope contradiction.

    :param content: full text
    """
    not_resp = (_extract_section(content, "我不负责")
                or _extract_section(content, "不负责"))
    scope_sec = _extract_section(content, "工作范围")
    if not (not_resp and scope_sec):
        return 0.0, []
    items = re.findall(r"[-*]\s+(.+?)→", not_resp)
    scope_lower = scope_sec.lower()
    for item in items:
        if item.strip().lower() in scope_lower:
            return 1.0, [
                f"'{item.strip()}' in both scope "
                f"and not-responsible (-1.0)"]
    return 0.0, []


def _check_degrade_tools(
    content: str, perm_tools: set[str],
) -> tuple[float, list[str]]:
    """Check degradation tools match permissions.

    :param content: full text
    :param perm_tools: tools listed in permissions section
    """
    sec = _extract_section(content, "降级")
    if not (sec and perm_tools):
        return 0.0, []
    used = set(re.findall(
        r"\b(WebSearch|WebFetch|Bash|Read|Grep|Glob)\b", sec))
    extra = used - perm_tools
    if extra:
        return 0.5, [
            f"degradation mentions tools not "
            f"in permissions: {extra} (-0.5)"]
    return 0.0, []


def _check_storm_dupes(content: str) -> tuple[float, list[str]]:
    """Check STORM persona table duplicates.

    :param content: full text
    """
    rows = re.findall(
        r"\|\s*(\S+视角|\S+ Persona)\s*\|", content)
    if len(rows) == len(set(rows)):
        return 0.0, []
    dupes = [s for s in set(rows) if rows.count(s) > 1]
    if dupes:
        return 1.0, [
            f"STORM persona duplicated: {dupes} (-1.0)"]
    return 0.0, []


def _check_dead_refs(content: str) -> tuple[float, list[str]]:
    """Check for dead internal references.

    :param content: full text
    """
    refs = re.findall(r"(?:见|详见|参见)\s*(\S+)", content)
    headers = {
        h.lower().strip()
        for h in re.findall(
            r"^#{1,4}\s+(.+)$", content, re.MULTILINE)}
    ded = 0.0
    issues: list[str] = []
    for ref in refs:
        clean = ref.strip("（）()「」")
        if (len(clean) > 1
                and clean.lower() not in headers
                and not clean.startswith(("~", "/"))):
            ded += 0.5
            issues.append(
                f"possible dead ref: '{clean}' (-0.5)")
    return ded, issues


# ==================== 维度 8: 自洽性（组合） ====================

def eval_consistency(content: str) -> DimResult:
    """评估内部一致性。基准 7.0，扣分制，上限 10.0。

    :param content: WhoAmI.md 全文
    """
    score = 7.0
    bonuses: list[str] = []
    deductions: list[str] = []

    # 子检查 1-7
    tool_ded, tool_iss, perm_tools = _check_tool_perm(content)
    sub_checks = [
        (tool_ded, tool_iss),
        _check_identity(content),
        _check_level_defs(content),
        _check_scope_conflict(content),
        _check_degrade_tools(content, perm_tools),
        _check_storm_dupes(content),
        _check_dead_refs(content),
    ]
    for ded, issues in sub_checks:
        score -= ded
        deductions.extend(issues)

    # Bonus: all checks passed with no deductions
    if not deductions:
        score += 3.0
        bonuses.append("no inconsistencies found (+3.0)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 评估引擎 ====================

EvalFn = type(eval_role_boundary)

EVALUATORS: dict[str, EvalFn] = {
    "role_boundary": eval_role_boundary,
    "methodology": eval_methodology,
    "toolchain": eval_toolchain,
    "anti_hallucination": eval_anti_hallucination,
    "output_standard": eval_output_standard,
    "conciseness": eval_conciseness,
    "actionability": eval_actionability,
    "consistency": eval_consistency,
}


def evaluate(content: str) -> dict[str, DimResult]:
    """运行全部 8 维评估，返回 {维度名: DimResult}。

    :param content: WhoAmI.md 全文
    """
    return {
        name: fn(content)
        for name, fn in EVALUATORS.items()
    }


def compute_total(results: dict[str, DimResult]) -> float:
    """加权总分。

    :param results: 8 维评估结果
    """
    return sum(
        r.score * w
        for (dim, w), r in zip(
            WEIGHTS.items(),
            (results[d] for d in WEIGHTS),
        )
    )


# ==================== 报告输出 ====================

def _print_dim(dim: str, weight: float, result: DimResult) -> None:
    """Print a single dimension's report line."""
    pct = int(weight * 100)
    print(f"{dim}: {result.score:.2f}  (weight: {pct}%)")
    for b in result.bonuses:
        print(f"  + {b}")
    for d in result.deductions:
        print(f"  - {d}")


def _print_weakest(results: dict[str, DimResult], n: int) -> None:
    """Print the N weakest dimensions."""
    ranked = sorted(results.items(), key=lambda kv: kv[1].score)
    print(f"weakest {n} dimensions:")
    for dim, r in ranked[:n]:
        print(f"  {dim}: {r.score:.2f}")
        for d in r.deductions:
            print(f"    - {d}")


def print_report(
    path: str,
    results: dict[str, DimResult],
    total: float,
    line_count: int,
) -> None:
    """打印 8 维评估报告。

    :param path: 文件路径
    :param results: 8 维评估结果
    :param total: 加权总分
    :param line_count: 文件行数
    """
    print(f"file: {path}")
    print(f"lines: {line_count}")
    print("---")

    for dim, weight in WEIGHTS.items():
        _print_dim(dim, weight, results[dim])

    print("---")
    print(f"total_score: {total:.2f}")
    print("---")
    _print_weakest(results, 3)


# ==================== 入口 ====================

def main() -> None:
    """Entry point: evaluate a single WhoAmI.md file."""
    if len(sys.argv) < 2:
        print("Usage: evaluate_whoami.py <whoami.md-path>")
        sys.exit(1)

    path = Path(sys.argv[1]).resolve()
    if not path.is_file():
        print(f"ERROR: not a file: {path}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8", errors="replace")
    line_count = len(content.splitlines())
    results = evaluate(content)
    total = compute_total(results)
    print_report(str(path), results, total, line_count)


if __name__ == "__main__":
    main()
