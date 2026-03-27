#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto-iterate: skill-full 复合评估脚本 v2

对一个完整 skill 目录进行 6 维加权评估，输出复合分数。
维度：定义质量(20%) + Pylint(20%) + Flake8(10%) + 一致性(15%)
      + 复杂度(15%) + Docstring覆盖率(20%)
用法: python3 evaluate_skill_full.py <skill-dir>

v2 修复：
- 自评悖论：排除评估脚本自身（evaluate_skill*.py）
- definition 天花板：添加 version 字段加分 (+0.5)，正确上限 10.0
- pylint 压缩映射移除：直接使用原始 pylint 平均分
- flake8 归一化更严格：total_warnings * 0.75（约 13 个警告归零）
- consistency 自我引用：评估脚本不计入引用检查
"""

import ast
import sys
import subprocess
import re
from pathlib import Path
from typing import Optional

# 评估脚本自身排除集合（自评悖论修复）
EVAL_SCRIPTS: frozenset[str] = frozenset({
    "evaluate_skill.py",
    "evaluate_skill_full.py",
    "evaluate_skill_full_v2.py",
})


# ===== 维度 1: 定义质量 (check_skill_md) =====

def _check_base_deductions(content: str) -> tuple[float, list[str]]:
    """检查 skill.md 基准结构，返回 (base_score, issues)

    从基准 5.0 中扣分：frontmatter / 触发词 / 工作流 / 约束 / 行数。

    :param content: skill.md 文件的完整文本内容
    """
    base_score = 5.0
    issues: list[str] = []

    # frontmatter 检查
    if not content.startswith("---"):
        base_score -= 2.0
        issues.append("missing frontmatter")
    else:
        if "name:" not in content:
            base_score -= 1.0
            issues.append("missing name in frontmatter")
        if "description:" not in content:
            base_score -= 1.0
            issues.append("missing description in frontmatter")

    lower = content.lower()

    # 触发词检查
    trigger_pats = ["触发", "trigger", "触发词", "触发方式"]
    if not any(p in lower for p in trigger_pats):
        base_score -= 1.5
        issues.append("no trigger section")

    # 工作流/执行步骤检查
    wf_pats = ["##", "步骤", "step", "流程", "执行", "workflow"]
    if sum(1 for p in wf_pats if p in lower) < 2:
        base_score -= 1.0
        issues.append("weak workflow definition")

    # 约束检查
    cons_pats = ["约束", "constraint", "CAN", "CANNOT", "禁止", "不可"]
    if not any(p in content for p in cons_pats):
        base_score -= 1.0
        issues.append("no constraints section")

    # 行数（过长扣分）
    line_count = len(content.splitlines())
    if line_count > 300:
        base_score -= 0.5
        issues.append(f"verbose: {line_count} lines")

    return base_score, issues


def _check_bonus(content: str) -> tuple[float, list[str]]:
    """检查正向加分项，返回 (bonus, issues)

    最高 +5.0：示例覆盖(+1.5) + 错误处理(+0.5) + 评估(+0.5)
    + 约束条目(+0.5) + timeout/crash(+0.5) + 决策规则(+0.5)
    + 执行隔离/并发(+0.5) + setup步骤(+0.5) + version字段(+0.5)
    基准5.0 + bonus最高5.0 = 满分10.0

    :param content: skill.md 文件的完整文本内容
    """
    lower = content.lower()
    checks = [
        ("example coverage", "```", 0.5, "code examples"),
        ("example coverage",
         ["正例", "负例", "positive", "negative",
          "应触发", "不应触发", "should trigger",
          "should not trigger"], 0.5, "pos/neg trigger examples"),
        ("example coverage",
         ["输出格式", "output format", "输出示例",
          "output example", "输出:", "output:"], 0.5,
         "output format examples"),
        ("error handling docs",
         ["crash", "timeout", "failure", "失败",
          "超时", "异常", "error handling", "错误处理"], 0.5,
         "crash/timeout/failure handling"),
        ("eval coverage",
         ["评估", "evaluation", "评分", "scoring",
          "score", "指标", "metric"], 0.5,
         "evaluation/scoring methodology"),
        ("decision rules",
         ["决策", "decision", "keep", "discard",
          "回滚", "rollback"], 0.5,
         "decision rule documentation"),
        ("isolation docs",
         ["隔离", "isolation", "并发", "concurrent",
          "独立", "independent", "subagent"], 0.5,
         "execution isolation/concurrency docs"),
    ]

    bonus = 0.0
    missing_by_cat: dict[str, list[str]] = {}
    for cat, pats, pts, label in checks:
        hit = (pats in lower if isinstance(pats, str)
               else any(p in lower for p in pats))
        if hit:
            bonus += pts
        else:
            missing_by_cat.setdefault(cat, []).append(label)

    # Constraint items count
    constraint_items = re.findall(
        r"(?:^|\n)\s*[-*]\s+(?:CAN|CANNOT|可以|不可|禁止)", content)
    if len(constraint_items) >= 3:
        bonus += 0.5
    else:
        missing_by_cat.setdefault("constraint coverage", []).append(
            f"constraint items ({len(constraint_items)}/3 minimum)")

    # Setup steps count
    setup_heading = re.search(
        r"(?i)##\s*setup(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if setup_heading:
        setup_text = setup_heading.group(1)
        step_count = len(re.findall(
            r"^\s*\d+\.", setup_text, re.MULTILINE))
        if step_count >= 3:
            bonus += 0.5
        else:
            missing_by_cat.setdefault("setup", []).append(
                f"setup steps ({step_count}/3 minimum)")
    else:
        missing_by_cat.setdefault("setup", []).append(
            "no setup section found")

    # version 字段检查（frontmatter 含 version: → +0.5）
    if re.search(r"(?m)^version\s*:", content):
        bonus += 0.5
    else:
        missing_by_cat.setdefault("versioning", []).append(
            "no version field in frontmatter")

    issues = [f"{cat} incomplete: missing {', '.join(ms)}"
              for cat, ms in missing_by_cat.items()]
    return bonus, issues


def check_skill_md(skill_md: Optional[Path]) -> tuple[float, list[str]]:
    """检查 skill.md 定义质量，返回 (score, issues)

    评分体系：基准 5.0 + 正向加分（最高 +5.0）= 满分 10.0
    基准扣分：结构缺陷从 5.0 中扣除
    正向加分：示例/错误处理/评估/决策规则/隔离/setup 等

    :param skill_md: skill.md 文件路径，None 时返回 0 分
    """
    if not skill_md:
        return 0.0, ["skill.md not found"]

    content = skill_md.read_text(encoding="utf-8", errors="replace")
    base_score, base_issues = _check_base_deductions(content)
    bonus, bonus_issues = _check_bonus(content)

    total = max(0.0, min(10.0, base_score + bonus))
    return total, base_issues + bonus_issues


# ===== 维度 2: Pylint =====

def check_pylint(py_files: list[Path]) -> tuple[float, list[str]]:
    """对所有 .py 文件运行 pylint，返回 (avg_score, issues)"""
    if not py_files:
        return 10.0, ["no python files"]

    scores: list[float] = []
    issues: list[str] = []

    for f in py_files:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pylint", "--score=y",
                 "--disable=import-error", str(f)],
                capture_output=True, text=True, timeout=30, check=False)
            match = re.search(
                r"rated at ([\d.]+)/10", result.stdout + result.stderr)
            score = float(match.group(1)) if match else 0.0
            scores.append(score)
            if not match:
                issues.append(f"{f.name}: pylint parse failed")
            elif score < 8.0:
                issues.append(f"{f.name}: pylint {score:.2f}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            scores.append(0.0)
            issues.append(f"{f.name}: pylint timeout/not found")

    avg = sum(scores) / len(scores) if scores else 0.0
    # v2: 直接使用原始 pylint 平均分，不压缩 9-10 区间
    return avg, issues


# ===== 维度 3: Flake8 =====

def check_flake8(py_files: list[Path]) -> tuple[float, int, list[str]]:
    """对所有 .py 文件运行 flake8，返回 (normalized_score, raw_count, issues)"""
    if not py_files:
        return 10.0, 0, ["no python files"]

    total_warnings = 0
    issues: list[str] = []

    for f in py_files:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "flake8", str(f)],
                capture_output=True, text=True, timeout=30, check=False)
            count = len(result.stdout.strip().splitlines()) \
                if result.stdout.strip() else 0
            total_warnings += count
            if count > 0:
                issues.append(f"{f.name}: {count} warnings")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            issues.append(f"{f.name}: flake8 timeout/not found")

    # 归一化: 0 warnings = 10, ~13+ warnings = 0（v2 更严格）
    normalized = max(0.0, 10.0 - total_warnings * 0.75)
    return normalized, total_warnings, issues


# ===== 维度 4: 一致性 =====

def _check_return_type_annotations(
    py_files: list[Path]
) -> tuple[float, list[str]]:
    """检查函数是否有返回类型注解，返回 (deduction, issues)

    每个缺失返回类型的公开函数扣 0.5，上限 3.0。
    """
    deduction = 0.0
    issues: list[str] = []

    for f in py_files:
        try:
            source = f.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(f))
        except (SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_") and node.name != "__init__":
                continue
            if node.returns is None:
                deduction += 0.5
                issues.append(
                    f"{f.name}:{node.name} missing return type")

    return min(deduction, 3.0), issues


def _check_unused_imports(
    py_files: list[Path]
) -> tuple[float, list[str]]:
    """检查未使用的 import，返回 (deduction, issues)

    每个未使用的 import 扣 0.5，上限 3.0。
    使用 pylint 的 unused-import 检查。
    """
    deduction = 0.0
    issues: list[str] = []

    for f in py_files:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pylint",
                 "--disable=all", "--enable=unused-import",
                 "--score=n", str(f)],
                capture_output=True, text=True, timeout=30, check=False)
            unused = re.findall(r"W0611", result.stdout)
            count = len(unused)
            if count > 0:
                deduction += count * 0.5
                issues.append(
                    f"{f.name}: {count} unused import(s)")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return min(deduction, 3.0), issues


def _check_docstring_param_match(
    py_files: list[Path]
) -> tuple[float, list[str]]:
    """检查 docstring 中提到的参数是否与实际函数签名匹配

    每个不匹配扣 0.5，上限 2.0。
    """
    deduction = 0.0
    issues: list[str] = []

    for f in py_files:
        try:
            source = f.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(f))
        except (SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = ast.get_docstring(node)
            if not docstring:
                continue
            # 提取实际参数名
            actual_args = {
                a.arg for a in node.args.args
                if a.arg not in ("self", "cls")
            }
            # 在 docstring 中查找 :param xxx: 或 Args: xxx 格式
            doc_params = set(re.findall(
                r":param\s+(\w+):|^\s+(\w+)\s*[:(]",
                docstring, re.MULTILINE))
            doc_params = {
                p for group in doc_params for p in group if p
            }
            # 排除常见 docstring 段落标题（非参数名）
            section_headers = {
                "Returns", "Raises", "Yields", "Args",
                "Note", "Notes", "Example", "Examples",
                "Attributes", "References", "See",
                "Parameters", "Ranges", "Warnings",
                "Todo", "Deprecated",
            }
            doc_params -= section_headers
            if not doc_params:
                continue
            # 检查 docstring 提到但函数签名没有的参数
            phantom = doc_params - actual_args
            for param in phantom:
                deduction += 0.5
                issues.append(
                    f"{f.name}:{node.name} docstring mentions "
                    f"'{param}' not in signature")

    return min(deduction, 2.0), issues


def _check_script_references(
    content: str, scripts_dir: Path,
    py_files: list[Path]
) -> tuple[float, list[str]]:
    """Check skill.md <-> script cross-references.

    v2: 评估脚本自身（EVAL_SCRIPTS）不计入引用检查，
    且"是否引用评估脚本"改为可选加分（+0.0 → 不扣分）。
    """
    deduction = 0.0
    issues: list[str] = []

    # 检查 skill.md 中引用的脚本是否存在
    for ref in re.findall(r"scripts/(\w+\.(?:py|sh))", content):
        if not (scripts_dir / ref).exists():
            deduction += 2.5
            issues.append(
                f"referenced script missing: scripts/{ref}")

    # 检查存在的脚本：是否被 skill.md 引用 + 是否有 shebang
    # 排除评估脚本自身（自评悖论修复）
    sh_files = (
        list(scripts_dir.glob("*.sh"))
        if scripts_dir.exists() else [])
    non_eval_py = [f for f in py_files if f.name not in EVAL_SCRIPTS]
    for f in non_eval_py + sh_files:
        if f.name not in content:
            deduction += 1.0
            issues.append(
                f"script not referenced in skill.md: {f.name}")
        try:
            first_line = f.read_text(
                encoding="utf-8", errors="replace"
            ).split("\n", 1)[0]
            if not first_line.startswith("#!"):
                deduction += 0.5
                issues.append(f"missing shebang: {f.name}")
        except OSError:
            issues.append(f"cannot read script: {f.name}")

    # v2: 评估脚本引用改为信息性提示（不扣分），鼓励但不强制
    eval_patterns = [
        "evaluate", "eval.sh", "evaluate.sh",
        "evaluate_skill", "评估脚本"]
    if not any(p in content.lower() for p in eval_patterns):
        issues.append(
            "info: skill.md does not mention evaluation script "
            "(optional, no penalty)")

    return deduction, issues


def check_consistency(
    skill_dir: Path, skill_md_path: Optional[Path],
    py_files: list[Path]
) -> tuple[float, list[str]]:
    """检查 skill.md 与脚本的一致性 + 代码内部一致性"""
    if not skill_md_path:
        return 0.0, ["no skill.md for consistency check"]

    content = skill_md_path.read_text(
        encoding="utf-8", errors="replace")
    scripts_dir = skill_dir / "scripts"

    # 收集所有子检查的扣分和问题
    checks = [
        _check_script_references(content, scripts_dir, py_files),
        _check_return_type_annotations(py_files),
        _check_unused_imports(py_files),
        _check_docstring_param_match(py_files),
    ]
    total_deduction = sum(d for d, _ in checks)
    all_issues = [i for _, issues in checks for i in issues]

    return max(0.0, 10.0 - total_deduction), all_issues


# ===== 维度 5: 复杂度 (McCabe) =====


def _parse_mccabe_lines(
    output: str, filename: str,
) -> tuple[list[int], str, int]:
    """Parse mccabe stdout into (complexities, max_func, max_val)."""
    complexities: list[int] = []
    local_max = 0
    local_max_name = ""
    for line in output.strip().splitlines():
        match = re.search(r"'([^']+)'\s+(\d+)$", line)
        if not match:
            continue
        val = int(match.group(2))
        complexities.append(val)
        if val > local_max:
            local_max = val
            local_max_name = f"{filename}:{match.group(1)}"
    return complexities, local_max_name, local_max


def _run_mccabe_on_file(
    f: Path,
) -> tuple[list[int], str, int, list[str]]:
    """Run mccabe on a single file, return complexities + max info.

    Returns (complexities, max_func_name, max_val, issues).
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mccabe", "--min", "1",
             str(f)],
            capture_output=True, text=True, timeout=30,
            check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [], "", 0, [f"{f.name}: mccabe timeout/not found"]
    cx, name, mx = _parse_mccabe_lines(
        result.stdout, f.name)
    return cx, name, mx, []


def _avg_to_score(avg: float) -> float:
    """Map average McCabe complexity to a base score (0-10).

    Ranges: <=3 -> 10.0, 3-5 -> 10-7, 5-8 -> 7-4, >8 -> 4-0.
    """
    if avg <= 3.0:
        return 10.0
    if avg <= 5.0:
        return 10.0 - (avg - 3.0) * 1.5
    if avg <= 8.0:
        return 7.0 - (avg - 5.0) * 1.0
    return max(0.0, 4.0 - (avg - 8.0) * 0.5)


def _max_penalty(
    max_val: int, func_name: str
) -> tuple[float, list[str]]:
    """Compute penalty + issues for max single-function complexity."""
    if max_val > 15:
        return 3.0, [
            f"extreme complexity: {func_name} = {max_val}"]
    if max_val > 10:
        return 1.5, [
            f"high complexity: {func_name} = {max_val}"]
    return 0.0, []


def check_complexity(
    py_files: list[Path]
) -> tuple[float, list[str]]:
    """对所有 .py 文件运行 mccabe 复杂度分析，返回 (score, issues)

    评分规则：
    - 平均复杂度 <=3 -> 10.0 (优秀)
    - 平均复杂度 3-5 -> 线性映射 10.0-7.0
    - 平均复杂度 5-8 -> 线性映射 7.0-4.0
    - 平均复杂度 >8 -> 线性映射 4.0-0.0
    - 最大单函数复杂度 >10 -> 额外扣 1.5
    - 最大单函数复杂度 >15 -> 额外扣 3.0
    """
    if not py_files:
        return 10.0, ["no python files"]

    all_complexities: list[int] = []
    issues: list[str] = []
    max_complexity = 0
    max_func_name = ""

    for f in py_files:
        cx, name, mx, errs = _run_mccabe_on_file(f)
        all_complexities.extend(cx)
        issues.extend(errs)
        if mx > max_complexity:
            max_complexity = mx
            max_func_name = name

    if not all_complexities:
        return 10.0, issues + ["no functions found"]

    avg = sum(all_complexities) / len(all_complexities)
    score = _avg_to_score(avg)

    penalty, penalty_issues = _max_penalty(
        max_complexity, max_func_name)
    score -= penalty
    issues.extend(penalty_issues)

    issues.append(
        f"avg_complexity: {avg:.1f}, "
        f"max: {max_complexity} ({max_func_name}), "
        f"functions: {len(all_complexities)}")

    return max(0.0, min(10.0, score)), issues


# ===== 维度 6: Docstring 覆盖率 =====

def _collect_docstring_stats(
    py_files: list[Path]
) -> dict:
    """Collect docstring statistics from all py files.

    Returns dict with keys: total_defs, with_docstring,
    lengths, shallow, has_module_doc, has_param_docs,
    missing_funcs, parse_errors.
    """
    stats = {
        "total_defs": 0, "with_docstring": 0,
        "lengths": [], "shallow": 0,
        "has_module_doc": False, "has_param_docs": False,
        "missing_funcs": [], "parse_errors": [],
    }
    for f in py_files:
        try:
            source = f.read_text(
                encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(f))
        except (SyntaxError, OSError):
            stats["parse_errors"].append(f.name)
            continue
        if ast.get_docstring(tree):
            stats["has_module_doc"] = True
        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef,
                       ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            stats["total_defs"] += 1
            docstring = ast.get_docstring(node)
            if not docstring:
                stats["missing_funcs"].append(
                    f"{f.name}:{node.name}")
                continue
            stats["with_docstring"] += 1
            doc_len = len(docstring.strip())
            stats["lengths"].append(doc_len)
            if doc_len < 20:
                stats["shallow"] += 1
            param_pat = r":param\s+\w+:|Args:|Parameters:"
            if re.search(param_pat, docstring):
                stats["has_param_docs"] = True
    return stats


def _coverage_to_score(coverage: float) -> float:
    """Map docstring coverage ratio to base score (0-8)."""
    if coverage >= 1.0:
        return 8.0
    if coverage >= 0.8:
        return 6.0 + (coverage - 0.8) * 10.0
    if coverage >= 0.6:
        return 4.0 + (coverage - 0.6) * 10.0
    return coverage / 0.6 * 4.0


def check_docstring_coverage(
    py_files: list[Path]
) -> tuple[float, list[str]]:
    """检查所有函数/类的 docstring 覆盖率，返回 (score, issues)"""
    if not py_files:
        return 10.0, ["no python files"]

    stats = _collect_docstring_stats(py_files)
    issues: list[str] = [
        f"{n}: cannot parse" for n in stats["parse_errors"]]

    if stats["total_defs"] == 0:
        return 10.0, ["no functions/classes found"]

    coverage = stats["with_docstring"] / stats["total_defs"]
    score = _coverage_to_score(coverage)

    # 浅层 docstring 惩罚
    lengths = stats["lengths"]
    if lengths:
        shallow_ratio = stats["shallow"] / len(lengths)
        if shallow_ratio > 0.3:
            score -= 1.5
            issues.append(
                f"shallow docstrings: {stats['shallow']}/"
                f"{len(lengths)} ({shallow_ratio:.0%})")
        avg_len = sum(lengths) / len(lengths)
        if avg_len < 30:
            score -= 1.0
            issues.append(
                f"avg docstring length: {avg_len:.0f} chars")

    # 正向加分
    if stats["has_module_doc"]:
        score += 1.0
    else:
        issues.append("no module docstring")
    if stats["has_param_docs"]:
        score += 1.0
    else:
        issues.append("no param documentation")

    issues.append(
        f"coverage: {stats['with_docstring']}/"
        f"{stats['total_defs']} ({coverage:.0%})")
    missing = stats["missing_funcs"]
    if missing:
        names = ', '.join(missing[:5])
        suffix = (f" +{len(missing) - 5} more"
                  if len(missing) > 5 else "")
        issues.append(f"missing docstrings: {names}{suffix}")

    return max(0.0, min(10.0, score)), issues


# ===== Shell 质量检查（辅助） =====

def _has_shebang(lines: list[str], _content: str) -> bool:
    """Check first line starts with #!."""
    return bool(lines) and lines[0].startswith("#!")


def _has_strict_mode(lines: list[str], _content: str) -> bool:
    """Check for set -e / set -euo pipefail."""
    return any(re.match(r"^set\s+-[euo]", ln) for ln in lines)


def _has_quoted_vars(lines: list[str], content: str) -> bool:
    """Heuristic: few unquoted $VAR references (threshold: 5)."""
    del lines  # unused
    unquoted = re.findall(r'(?<!")\$\{?\w+\}?(?!")', content)
    false_pos = re.findall(
        r'\$\(|^\s*\w+=\$', content, re.MULTILINE)
    return max(0, len(unquoted) - len(false_pos)) <= 5


def _has_error_exit(_lines: list[str], content: str) -> bool:
    """Check for non-zero exit codes."""
    return bool(re.search(r"exit\s+[1-9]", content))


def _has_usage(_lines: list[str], content: str) -> bool:
    """Check for usage documentation."""
    return bool(re.search(r"[Uu]sage|用法", content))


# Shell quality checks: (penalty_if_missing, label, check_fn)
_SHELL_CHECKS: list[tuple[float, str, object]] = [
    (3.0, "missing shebang", _has_shebang),
    (2.0, "missing set -e", _has_strict_mode),
    (1.5, "many unquoted variables", _has_quoted_vars),
    (1.5, "no non-zero exit codes", _has_error_exit),
    (1.0, "no usage documentation", _has_usage),
]


def check_shell_quality(
    sh_files: list[Path]
) -> tuple[float, list[str]]:
    """对所有 .sh 文件进行数据驱动静态质量检查，返回 (avg_score, issues)

    检查维度（每个文件独立评分，取平均）：
    - shebang 行存在 (-3.0)
    - set -e / set -euo pipefail 存在 (-2.0)
    - 变量引用使用双引号（启发式抽样）(-1.5)
    - 错误处理：有 exit 非零退出 (-1.5)
    - 用法文档：有 usage/Usage 字符串 (-1.0)
    """
    if not sh_files:
        return 10.0, ["no shell files"]

    scores: list[float] = []
    issues: list[str] = []

    for f in sh_files:
        try:
            content = f.read_text(
                encoding="utf-8", errors="replace")
        except OSError:
            scores.append(0.0)
            issues.append(f"{f.name}: cannot read")
            continue

        lines = content.splitlines()
        score = 10.0
        file_issues: list[str] = []

        for penalty, label, check_fn in _SHELL_CHECKS:
            if not check_fn(lines, content):
                score -= penalty
                file_issues.append(label)

        scores.append(max(0.0, score))
        if file_issues:
            issues.append(
                f"{f.name}: {'; '.join(file_issues)}")

    avg = sum(scores) / len(scores) if scores else 10.0
    return avg, issues


# ===== 合成与报告 =====

def _find_skill_md(skill_dir: Path) -> Optional[Path]:
    """Locate skill.md (case-insensitive) in skill_dir."""
    return next(
        (skill_dir / n for n in ("skill.md", "SKILL.md")
         if (skill_dir / n).exists()), None)


def _combined_code_quality(
    pylint_score: float, shell_score: float,
    py_count: int, sh_count: int
) -> float:
    """Blend pylint and shell scores by file count weight."""
    total = py_count + sh_count
    if total == 0:
        return 10.0
    return (pylint_score * py_count
            + shell_score * sh_count) / total


def _print_report(
    skill_dir: Path, py_files: list[Path],
    sh_files: list[Path], scores: dict[str, float],
    all_issues: dict[str, list[str]]
) -> None:
    """Print structured evaluation report."""
    header = [
        f"skill_dir: {skill_dir}",
        f"py_files: {len(py_files)}",
        f"sh_files: {len(sh_files)}"]
    dims = [
        ("definition_score", scores['definition']),
        ("pylint_avg", scores['pylint']),
        ("shell_quality", scores['shell']),
        ("code_quality_combined", scores['code_quality']),
        ("flake8_normalized", scores['flake8_norm']),
        ("consistency_score", scores['consistency']),
        ("complexity_score", scores['complexity']),
        ("docstring_coverage_score", scores['docstring']),
    ]
    lines = header + ["---"]
    lines += [f"{k}: {v:.2f}" for k, v in dims]
    lines += [f"flake8_raw: {scores['flake8_raw']}", "---"]
    lines += [
        f"total_score: {scores['total']:.2f}",
        "---",
        "weights: definition=20% pylint=20% flake8=10% "
        "consistency=15% complexity=15% docstring=20%",
        "---"]
    lines += [
        f"{k}: {'; '.join(v)}"
        for k, v in all_issues.items() if v]
    print("\n".join(lines))


def _run_evaluations(
    skill_dir: Path, skill_md: Optional[Path],
    py_files: list[Path], sh_files: list[Path]
) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Run all 6 evaluation dimensions, return (scores, all_issues)."""
    results = {
        "definition": check_skill_md(skill_md),
        "pylint": check_pylint(py_files),
        "shell": check_shell_quality(sh_files),
        "flake8": check_flake8(py_files),
        "consistency": check_consistency(
            skill_dir, skill_md, py_files),
        "complexity": check_complexity(py_files),
        "docstring": check_docstring_coverage(py_files),
    }

    cq_s = _combined_code_quality(
        results["pylint"][0], results["shell"][0],
        len(py_files), len(sh_files))
    d_s = results["definition"][0]
    f_s = results["flake8"][0]
    c_s = results["consistency"][0]
    cx_s = results["complexity"][0]
    dc_s = results["docstring"][0]

    # 6 维加权: 定义20% + Pylint20% + Flake8 10%
    #           + 一致性15% + 复杂度15% + Docstring20%
    total = (
        d_s * 0.20
        + cq_s * 0.20
        + f_s * 0.10
        + c_s * 0.15
        + cx_s * 0.15
        + dc_s * 0.20
    )

    scores = {
        "definition": d_s,
        "pylint": results["pylint"][0],
        "shell": results["shell"][0],
        "code_quality": cq_s,
        "flake8_norm": f_s,
        "flake8_raw": results["flake8"][1],
        "consistency": c_s,
        "complexity": cx_s,
        "docstring": dc_s,
        "total": total,
    }
    all_issues = {
        "definition_issues": results["definition"][1],
        "pylint_issues": results["pylint"][1],
        "shell_issues": results["shell"][1],
        "flake8_issues": results["flake8"][2],
        "consistency_issues": results["consistency"][1],
        "complexity_issues": results["complexity"][1],
        "docstring_issues": results["docstring"][1],
    }
    return scores, all_issues


def main() -> None:
    """Entry point: evaluate a skill directory."""
    if len(sys.argv) < 2:
        print("Usage: evaluate_skill_full.py <skill-dir>")
        sys.exit(1)

    skill_dir = Path(sys.argv[1]).resolve()
    if not skill_dir.is_dir():
        print(f"ERROR: not a directory: {skill_dir}")
        sys.exit(1)

    skill_md = _find_skill_md(skill_dir)
    scripts_dir = skill_dir / "scripts"
    # 排除评估脚本自身（自评悖论修复，v2）
    py_files = (
        [f for f in sorted(scripts_dir.glob("*.py"))
         if f.name not in EVAL_SCRIPTS]
        if scripts_dir.exists() else [])
    sh_files = (
        sorted(scripts_dir.glob("*.sh"))
        if scripts_dir.exists() else [])

    scores, all_issues = _run_evaluations(
        skill_dir, skill_md, py_files, sh_files)
    _print_report(
        skill_dir, py_files, sh_files, scores, all_issues)


if __name__ == "__main__":
    main()
