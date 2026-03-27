#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto-iterate: 5 维信息质量评估脚本

对 yomi 调研输出进行 5 维信息质量评估，测量给用户带回的信息质量。

维度与权重：
  正确性(25%) + 完整性(25%) + 时效性(15%) + 可操作性(20%) + 源可追溯(15%)

用法:
  python3 evaluate_whoami_functional.py <output_file> [--offline]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple


# ==================== 数据模型 ====================

class DimResult(NamedTuple):
    """单维度评估结果。"""
    score: float
    max_score: float
    detail: str


# ==================== 维度配置 ====================

DIM_CONFIG: dict[str, tuple[str, int, float]] = {
    "correctness":  ("正确性",     25, 2.50),
    "completeness": ("完整性",     25, 2.50),
    "timeliness":   ("时效性",     15, 1.50),
    "actionability": ("可操作性",  20, 2.00),
    "traceability": ("源可追溯",   15, 1.50),
}

_DIM_DISPLAY: dict[str, str] = {
    "correctness":  "正确性    ",
    "completeness": "完整性    ",
    "timeliness":   "时效性    ",
    "actionability": "可操作性  ",
    "traceability": "源可追溯  ",
}

PROXY = "http://127.0.0.1:7897"
CURRENT_YEAR = datetime.now().year


# ==================== 工具函数 ====================

def _clamp(val: float, lo: float, hi: float) -> float:
    """Clamp val to the inclusive range [lo, hi]."""
    return max(lo, min(hi, val))


def _extract_nested_str(val: object) -> str | None:
    """Return first string found in val (if dict) under content/text keys."""
    if not isinstance(val, dict):
        return None
    return next(
        (val[k] for k in ('content', 'text') if isinstance(val.get(k), str)),
        None,
    )


def _extract_from_jsonl_obj(obj: dict, line: str) -> str:
    """Extract text content from a single parsed JSONL object."""
    for key in ('content', 'message', 'text', 'output', 'result'):
        val = obj.get(key)
        if isinstance(val, str):
            return val
        nested = _extract_nested_str(val)
        if nested is not None:
            return nested
    return line


def _parse_one_jsonl_line(line: str) -> str:
    """Parse one JSONL line and extract its text content."""
    try:
        obj = json.loads(line)
        if isinstance(obj, dict):
            return _extract_from_jsonl_obj(obj, line)
        return line
    except (json.JSONDecodeError, TypeError):
        return line


def _parse_jsonl_lines(lines: list[str]) -> list[str]:
    """Parse JSONL lines and extract text from each."""
    return [_parse_one_jsonl_line(line) for line in lines]


def preprocess_content(raw: str) -> str:
    """If input is JSONL agent output, extract text content only."""
    lines = raw.strip().splitlines()
    if not lines:
        return raw
    json_lines = sum(1 for line in lines if line.strip().startswith('{'))
    if json_lines > len(lines) * 0.3:
        texts = _parse_jsonl_lines(lines)
        return '\n'.join(texts) if texts else raw
    return raw


# ==================== 网络验证函数 ====================

def _curl_env() -> dict[str, str]:
    """Build env dict with proxy for curl commands."""
    env = os.environ.copy()
    env["https_proxy"] = PROXY
    env["http_proxy"] = PROXY
    return env


def verify_doi(doi: str) -> bool:
    """Returns True if DOI resolves via CrossRef."""
    try:
        r = subprocess.run(
            ["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}",
             "--max-time", "8",
             f"https://api.crossref.org/works/{doi}"],
            capture_output=True, text=True, timeout=15,
            check=False, env=_curl_env()
        )
        return r.stdout.strip() == "200"
    except (subprocess.TimeoutExpired, OSError):
        return False


def verify_url(url: str) -> bool:
    """Returns True if URL is reachable (2xx or 3xx)."""
    try:
        r = subprocess.run(
            ["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}",
             "--max-time", "5", url],
            capture_output=True, text=True, timeout=10,
            check=False, env=_curl_env()
        )
        return r.stdout.strip() in ("200", "201", "301", "302", "303")
    except (subprocess.TimeoutExpired, OSError):
        return False


def verify_arxiv_format(arxiv_id: str) -> bool:
    """Check if arXiv ID matches valid format."""
    return bool(re.match(r"\d{4}\.\d{4,5}", arxiv_id))


# ==================== 提取函数 ====================

def extract_dois(content: str) -> list[str]:
    """Extract DOI strings from content."""
    return re.findall(r"10\.\d{4,9}/[^\s,;>\]\"']+", content)


def extract_urls(content: str) -> list[str]:
    """Extract HTTP(S) URLs from content."""
    return re.findall(r"https?://[^\s,;>\]\"'<]+", content)


def extract_arxiv_ids(content: str) -> list[str]:
    """Extract arXiv IDs from content."""
    return re.findall(r"\d{4}\.\d{4,5}", content)


def extract_years(content: str) -> list[int]:
    """Extract years (2015-2030) from content."""
    raw = re.findall(r"\b(20[12]\d)\b", content)
    return [int(y) for y in raw if 2015 <= int(y) <= 2030]


# ==================== 维度评估函数 ====================

def _build_identifier_score(
    dois: list[str], urls: list[str], arxiv_ids: list[str],
) -> tuple[float, list[str]]:
    """Score presence of verifiable identifiers."""
    named = [("DOI", dois), ("URL", urls), ("arXiv", arxiv_ids)]
    id_counts = [f"{n}:{len(v)}" for n, v in named if v]
    if not id_counts:
        return 0.0, []
    return 0.5, [f"identifiers found ({', '.join(id_counts)})"]


_VERIFICATION_TIERS: list[tuple[float, float, str]] = [
    (0.8, 1.0, "verification pass rate"),
    (0.5, 0.5, "verification partial"),
    (0.0, 0.0, "verification low"),
]


def _tier_for_ratio(ratio: float) -> tuple[float, str]:
    """Return (points, label) for a verified ratio using tier table."""
    for threshold, pts, label in _VERIFICATION_TIERS:
        if ratio >= threshold:
            return pts, label
    return 0.0, "verification low"


def _score_verification_ratio(
    verified: int, total_checked: int,
) -> tuple[float, str]:
    """Map verified/total ratio to score and label."""
    if total_checked == 0:
        return 0.0, "no identifiers to verify"
    ratio = verified / total_checked
    pts, label = _tier_for_ratio(ratio)
    return pts, f"{label} {verified}/{total_checked} = {ratio:.0%}"


def _verify_items(items: list[str], verify_fn: object) -> int:
    """Count how many items (up to 3) pass verify_fn."""
    return sum(1 for item in items[:3] if verify_fn(item))


def _count_verified(
    dois: list[str], urls: list[str], arxiv_ids: list[str],
) -> tuple[int, int]:
    """Count (verified, total_checked) for up to 3 items per category."""
    categories = [
        (dois, verify_doi),
        (urls, verify_url),
        (arxiv_ids, verify_arxiv_format),
    ]
    verified = sum(_verify_items(items, fn) for items, fn in categories)
    total_checked = sum(len(items[:3]) for items, _ in categories)
    return verified, total_checked


def _build_verification_score(
    dois: list[str], urls: list[str], arxiv_ids: list[str],
    offline: bool,
) -> tuple[float, list[str]]:
    """Score identifier verification (network or offline default)."""
    if offline:
        return 1.0, ["network unavailable, default 1.0 for verification"]
    verified, total_checked = _count_verified(dois, urls, arxiv_ids)
    v_score, v_detail = _score_verification_ratio(verified, total_checked)
    return v_score, [v_detail]


def eval_correctness(content: str, offline: bool = False) -> DimResult:
    """维度 1: 正确性 Correctness (25%, max 2.5)

    核心问题：信息是真的吗？
    """
    dois = extract_dois(content)
    urls = extract_urls(content)
    arxiv_ids = extract_arxiv_ids(content)

    id_score, id_details = _build_identifier_score(dois, urls, arxiv_ids)
    v_score, v_details = _build_verification_score(
        dois, urls, arxiv_ids, offline)

    score = id_score + v_score + 1.0  # +1.0 for no contradiction signals
    details = id_details + v_details + ["no contradiction signals"]

    detail_str = "; ".join(details) if details else "no correctness evidence"
    return DimResult(min(score, 2.5), 2.5, detail_str)


_SOURCE_PATTERNS: dict[str, list[str]] = {
    "API": [r"(?:Semantic Scholar|S2)\s*(?:API|skill)",
            r"CrossRef", r"OpenAlex"],
    "Web": [r"WebSearch", r"Google Scholar", r"DBLP",
            r"搜索", r"search"],
    "Database": [r"IEEE\s*Xplore", r"ACM\s*DL",
                 r"arXiv", r"ePrint", r"USENIX"],
    "Official": [r"官方", r"official", r"主网", r"mainnet"],
}


def _count_distinct_items(content: str) -> int:
    """Count distinct information items in content."""
    paper_headers = re.findall(
        r"(?:###?\s*(?:Paper\s+)?\d|###?\s*\d\.)", content)
    numbered_items = re.findall(
        r"^\s*\d+\.\s+\*?\*?(?:\[|[A-Z])", content, re.MULTILINE)
    distinct_items = max(len(paper_headers), len(numbered_items))
    dois = extract_dois(content)
    arxiv_ids = extract_arxiv_ids(content)
    return max(distinct_items, len(set(dois)), len(set(arxiv_ids)))


def _detect_source_types(content: str) -> set[str]:
    """Detect which source types are mentioned in content."""
    return {
        src_type
        for src_type, patterns in _SOURCE_PATTERNS.items()
        if any(re.search(p, content, re.IGNORECASE) for p in patterns)
    }


def _eval_item_count(content: str) -> tuple[float, str]:
    """Sub-dim: item count score for completeness."""
    item_count = _count_distinct_items(content)
    if item_count >= 3:
        return 0.5, f">=3 distinct items ({item_count})"
    if item_count >= 1:
        return 0.25, f"some items ({item_count})"
    return 0.0, ""


def _eval_source_coverage(content: str) -> tuple[float, str]:
    """Sub-dim: multi-source coverage score for completeness."""
    source_types = _detect_source_types(content)
    if len(source_types) >= 2:
        return 0.5, f"multi-source ({', '.join(sorted(source_types))})"
    if len(source_types) == 1:
        return 0.25, f"single source type ({list(source_types)[0]})"
    return 0.0, ""


def _eval_perspective(content: str) -> tuple[float, str]:
    """Sub-dim: multi-perspective (pros+cons) score for completeness."""
    positive_words = re.findall(
        r"优势|advantage|高效|efficient|改进|improve|贡献|contribution"
        r"|创新|innovation|outperform",
        content, re.IGNORECASE)
    negative_words = re.findall(
        r"局限|limitation|不足|缺点|disadvantage|风险|risk|挑战|challenge"
        r"|瓶颈|bottleneck|问题|weakness",
        content, re.IGNORECASE)
    if positive_words and negative_words:
        return 0.5, "multi-perspective (pros+cons)"
    if positive_words or negative_words:
        return 0.25, "single perspective only"
    return 0.0, ""


def _eval_trends(content: str) -> tuple[float, str]:
    """Sub-dim: trend/pattern recognition score for completeness."""
    trend_words = re.findall(
        r"趋势|trend|pattern|大多数|majority|主流|mainstream"
        r"|转向|shift|演进|evolv|收敛|converg",
        content, re.IGNORECASE)
    if trend_words:
        return 0.5, f"trend/pattern identified ({len(trend_words)} refs)"
    return 0.0, ""


def _eval_honest_gaps(content: str) -> tuple[float, str]:
    """Sub-dim: honest gap reporting score for completeness."""
    uncovered = re.findall(
        r"未发现|no results|无相关|未找到|not found|未覆盖|未验证|遗漏"
        r"|may miss|可能遗漏|样本量有限",
        content, re.IGNORECASE)
    if uncovered:
        return 0.5, f"honest gaps reported ({len(uncovered)})"
    return 0.0, ""


def eval_completeness(content: str) -> DimResult:
    """维度 2: 完整性 Completeness (25%, max 2.5)

    核心问题：该知道的都找到了吗？
    """
    checkers = [
        _eval_item_count,
        _eval_source_coverage,
        _eval_perspective,
        _eval_trends,
        _eval_honest_gaps,
    ]
    score = 0.0
    details: list[str] = []
    for checker in checkers:
        s, d = checker(content)
        score += s
        if d:
            details.append(d)
    detail_str = "; ".join(details) if details else "low completeness"
    return DimResult(min(score, 2.5), 2.5, detail_str)


_TIMELINESS_SIGNALS = (
    r"最新|latest|current|recent|v\d+\.\d+|"
    r"forthcoming|即将|preprint|arXiv\s*20"
)


def _has_timeliness_signals(content: str) -> bool:
    """Return True if content contains timeliness signals."""
    return bool(re.findall(_TIMELINESS_SIGNALS, content, re.IGNORECASE))


def _timeliness_year_bonus(content: str, max_year: int) -> tuple[float, str]:
    """Return bonus score and detail for year-level timeliness."""
    if max_year >= CURRENT_YEAR:
        return 0.75, f"current year ({CURRENT_YEAR}) referenced"
    if max_year == CURRENT_YEAR - 1 and _has_timeliness_signals(content):
        return 0.375, "timeliness signals present"
    return 0.0, ""


def _timeliness_from_years(
    content: str, years: list[int],
) -> tuple[float, list[str]]:
    """Score timeliness when year references are found."""
    max_year = max(years)
    unique_years = sorted(set(years))
    details = [f"years found: {unique_years}"]
    score = 0.0
    if max_year >= CURRENT_YEAR - 1:
        score += 0.75
        details.append(f"recent (max year={max_year})")
    bonus, bonus_detail = _timeliness_year_bonus(content, max_year)
    score += bonus
    if bonus_detail:
        details.append(bonus_detail)
    return score, details


def _timeliness_no_years(content: str) -> tuple[float, list[str]]:
    """Score timeliness when no year references are found."""
    signals = re.findall(
        r"最新|latest|current|v\d+\.\d+",
        content, re.IGNORECASE)
    if signals:
        return 0.75, [f"no years but timeliness signals ({len(signals)})"]
    return 0.0, []


def eval_timeliness(content: str) -> DimResult:
    """维度 3: 时效性 Timeliness (15%, max 1.5)

    核心问题：信息是最新的吗？
    """
    years = extract_years(content)
    if years:
        score, details = _timeliness_from_years(content, years)
    else:
        score, details = _timeliness_no_years(content)
    detail_str = "; ".join(details) if details else "no timeliness evidence"
    return DimResult(min(score, 1.5), 1.5, detail_str)


_ACTIONABILITY_CHECKS: list[tuple[str, str, str]] = [
    (
        r"建议|recommend|应该|should|下一步|next\s*step|"
        r"适合|suitable|可作为|可以.*?参考",
        "advice present ({n} instances)",
        "",
    ),
    (
        r"高优|P0|首先|first|最重要|critical|高优先级|"
        r"中优先级|低优先级|priority|urgent",
        "prioritized ({n} markers)",
        "",
    ),
    (
        r"查看|下载|安装|运行|阅读|contact|visit|"
        r"引用|cite|部署|deploy|关注|追踪|track|"
        r"必引|对比|compare|参照",
        "actionable verbs ({n})",
        "",
    ),
    (
        r"注意|caveat|风险|risk|限制|limitation|"
        r"不足|置信度|confidence|快照|snapshot|持续增长",
        "risks/caveats noted ({n})",
        "",
    ),
]


def _score_actionability_check(
    lower: str, pattern: str, label_tmpl: str
) -> tuple[float, str]:
    """Score one actionability pattern check; return (score, detail)."""
    matches = re.findall(pattern, lower)
    if matches:
        return 0.5, label_tmpl.format(n=len(matches))
    return 0.0, ""


def eval_actionability(content: str) -> DimResult:
    """维度 4: 可操作性 Actionability (20%, max 2.0)

    核心问题：用户拿到能直接用吗？
    """
    lower = content.lower()
    score = 0.0
    details: list[str] = []
    for pattern, label_tmpl, _ in _ACTIONABILITY_CHECKS:
        s, d = _score_actionability_check(lower, pattern, label_tmpl)
        score += s
        if d:
            details.append(d)
    detail_str = "; ".join(details) if details else "low actionability"
    return DimResult(min(score, 2.0), 2.0, detail_str)


_SOURCE_PATTERN = (
    r"(?:"
    r"DOI|doi|arXiv|ePrint|"
    r"\[V\]|\[S\]|\[I\]|\[U\]|"
    r"\[\d+\]|\[来源\]|"
    r"S2\s*(?:API|skill)|"
    r"WebSearch|Semantic\s*Scholar|"
    r"IEEE|ACM|USENIX|DBLP|"
    r"交叉验证|确认|来源|"
    r"https?://"
    r")"
)

_SOURCE_TYPE_PATTERNS: dict[str, str] = {
    "DOI": r"DOI|doi:|10\.\d{4,}",
    "URL": r"https?://",
    "API": r"S2|Semantic Scholar|CrossRef|OpenAlex",
    "Database": r"IEEE|ACM|USENIX|DBLP|arXiv|ePrint",
    "EvidenceTag": r"\[V\]|\[S\]|\[I\]|\[U\]",
    "PaperName": r"[A-Z][a-z]+(?:\s+et\s+al\.)",
}


_SOURCED_RATIO_TIERS: list[tuple[float, float, str]] = [
    (0.6, 0.75, ">=60%"),
    (0.3, 0.50, ">=30%"),
    (0.0, 0.25, ">0%"),
]


def _score_sourced_ratio(
    statement_lines: list[str],
) -> tuple[float, str]:
    """Score sourced-ratio sub-dimension; return (score, detail)."""
    total = len(statement_lines)
    sourced = sum(
        1 for line in statement_lines
        if re.search(_SOURCE_PATTERN, line, re.IGNORECASE)
    )
    ratio = sourced / total if total > 0 else 0
    for threshold, pts, label in _SOURCED_RATIO_TIERS:
        if ratio > threshold or (threshold == 0.0 and ratio > 0):
            return pts, (
                f"sourced ratio {sourced}/{total} = {ratio:.0%} ({label})")
    return 0.0, "no source attributions found"


_SOURCE_DIVERSITY_TIERS: list[tuple[int, float]] = [
    (3, 0.75),
    (2, 0.50),
    (1, 0.25),
]


def _score_source_diversity(content: str) -> tuple[float, str]:
    """Score source-diversity sub-dimension; return (score, detail)."""
    found: set[str] = {
        t for t, p in _SOURCE_TYPE_PATTERNS.items()
        if re.search(p, content, re.IGNORECASE)
    }
    n = len(found)
    label = "types" if n != 1 else "type"
    joined = ', '.join(sorted(found))
    for threshold, pts in _SOURCE_DIVERSITY_TIERS:
        if n >= threshold:
            return pts, f"source diversity {n} {label} ({joined})"
    return 0.0, ""


def eval_traceability(content: str) -> DimResult:
    """维度 5: 源可追溯 Traceability (15%, max 1.5)

    核心问题：每条结论能追到出处吗？
    """
    lines = content.strip().splitlines()
    statement_lines = [
        ln for ln in lines
        if ln.strip()
        and not ln.strip().startswith('#')
        and not ln.strip().startswith('---')
        and not ln.strip().startswith('|')
        and len(ln.strip()) > 10
    ]
    if not statement_lines:
        return DimResult(0.0, 1.5, "no statements found")

    ratio_score, ratio_detail = _score_sourced_ratio(statement_lines)
    div_score, div_detail = _score_source_diversity(content)

    score = ratio_score + div_score
    details = [d for d in (ratio_detail, div_detail) if d]
    detail_str = "; ".join(details) if details else "no traceability"
    return DimResult(min(score, 1.5), 1.5, detail_str)


# ==================== 评估引擎 ====================

def evaluate(content: str, offline: bool = False) -> dict[str, DimResult]:
    """运行全部 5 维评估。"""
    return {
        "correctness":  eval_correctness(content, offline),
        "completeness": eval_completeness(content),
        "timeliness":   eval_timeliness(content),
        "actionability": eval_actionability(content),
        "traceability": eval_traceability(content),
    }


def compute_total(results: dict[str, DimResult]) -> float:
    """加权总分（满分 10.0）。"""
    return sum(r.score for r in results.values())


# ==================== 报告输出 ====================

def print_report(
    path: str,
    results: dict[str, DimResult],
    total: float,
) -> None:
    """打印 5 维信息质量评估报告。"""
    print("=== Information Quality Evaluation ===")
    print(f"File: {path}")
    print()

    for dim_key, (_label, pct, _max_score) in DIM_CONFIG.items():
        result = results[dim_key]
        display = _DIM_DISPLAY[dim_key]
        print(
            f"{display} ({pct}%): "
            f"{result.score:.2f}/{result.max_score:.2f} "
            f"\u2014 {result.detail}"
        )

    print()
    print(f"\u603b\u5206: {total:.2f}/10.00")
    print()
    print(f"---SCORE:{total:.2f}---")


# ==================== 入口 ====================

def main() -> None:
    """Entry point: evaluate information quality of research output."""
    parser = argparse.ArgumentParser(
        description="Evaluate research output information quality "
                    "(5 dimensions)")
    parser.add_argument(
        "output_file",
        help="Path to file containing research output")
    parser.add_argument(
        "--offline",
        action="store_true",
        default=False,
        help="Skip network verification (give default middle score)")

    args = parser.parse_args()
    path = Path(args.output_file).resolve()

    if str(args.output_file) == "/dev/stdin":
        content = sys.stdin.read()
        display_path = "/dev/stdin"
    elif not path.is_file():
        print(f"ERROR: not a file: {path}")
        sys.exit(1)
    else:
        content = path.read_text(encoding="utf-8", errors="replace")
        display_path = str(path)

    content = preprocess_content(content)
    results = evaluate(content, args.offline)
    total = compute_total(results)
    print_report(display_path, results, total)


if __name__ == "__main__":
    main()
