#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto-iterate: 8 维 SKILL.md 评估脚本

对单个 SKILL.md 文件进行 8 维加权评估，输出各维度分数和改进建议。

维度与权重：
  触发准确率(15%) + 结构完整性(15%) + 简洁性(10%) + 约束清晰度(10%)
  + 可执行性(15%) + 防御性(10%) + 示例质量(15%) + 自洽性(10%)

用法: python3 evaluate_skill.py <skill.md-path>
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
    "trigger": 0.15,
    "structure": 0.15,
    "conciseness": 0.10,
    "constraints": 0.10,
    "actionability": 0.15,
    "defensiveness": 0.10,
    "examples": 0.15,
    "consistency": 0.10,
}

# 简洁性阶梯：(上限行数, 分数)
CONCISENESS_TIERS: list[tuple[int, float]] = [
    (80, 10.0),
    (100, 9.0),
    (120, 8.0),
    (140, 7.0),
    (160, 6.0),
    (200, 4.5),
    (250, 3.0),
]
CONCISENESS_FLOOR = 1.5

# 模糊词列表（约束清晰度用）
FUZZY_WORDS: list[str] = [
    "可能", "大概", "一般", "通常",
    "maybe", "probably", "usually",
    "perhaps", "sometimes",
]


# ==================== 工具函数 ====================

def _clamp(val: float, lo: float = 0.0, hi: float = 10.0) -> float:
    """Clamp 值到 [lo, hi]。"""
    return max(lo, min(hi, val))


def _count_re(pattern: str, text: str) -> int:
    """统计正则匹配次数。"""
    return len(re.findall(pattern, text, re.MULTILINE))


def _has_any(text: str, keywords: list[str]) -> bool:
    """text（小写后）是否包含 keywords 中任一项。"""
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


def _get_frontmatter(content: str) -> str:
    """提取 frontmatter 文本（--- 之间），无则返回空字符串。"""
    m = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    return m.group(1) if m else ""


def _get_trigger_section(content: str) -> str:
    """提取触发方式/Trigger 章节。"""
    for heading in ["触发方式", "触发词", "Trigger"]:
        sec = _extract_section(content, heading)
        if sec:
            return sec
    return ""


# ==================== 维度 1: 触发准确率 (15%) ====================

def eval_trigger(content: str) -> DimResult:
    """评估触发准确率，基准 4.0，上限 10.0。

    :param content: skill.md 全文
    """
    score = 0.0
    bonuses: list[str] = []
    deductions: list[str] = []

    fm = _get_frontmatter(content)
    trigger_sec = _get_trigger_section(content)

    # frontmatter description 含触发词 → +1.0
    if _has_any(fm, ["触发", "trigger", "/"]):
        score += 1.0
        bonuses.append("frontmatter has trigger keyword (+1.0)")

    # 独立触发方式章节 → +1.0
    if trigger_sec:
        score += 1.0
        bonuses.append("dedicated trigger section (+1.0)")

    # 多形态覆盖：斜杠/中文/英文各 +0.5，上限 +1.5
    multi = 0.0
    if re.search(r"/\w+", trigger_sec):
        multi += 0.5
        bonuses.append("slash form (+0.5)")
    if re.search(r"[\u4e00-\u9fff]{2,}", trigger_sec):
        multi += 0.5
        bonuses.append("Chinese form (+0.5)")
    if re.search(r"[a-zA-Z]{3,}", trigger_sec):
        multi += 0.5
        bonuses.append("English form (+0.5)")
    score += min(multi, 1.5)

    # 正例/负例 → +1.0
    lower = content.lower()
    pos_neg = ["正例", "负例", "positive", "negative",
               "should trigger", "should not"]
    if any(p in lower for p in pos_neg):
        score += 1.0
        bonuses.append("pos/neg examples (+1.0)")

    # 触发词数量
    trigger_tokens = re.findall(
        r"[/`「]([^/`」\s]+)[`」]?", trigger_sec)
    n = len(trigger_tokens)
    if n < 2:
        score -= 1.0
        deductions.append(f"trigger count {n} < 2 (-1.0)")
    elif n > 8:
        score -= 0.5
        deductions.append(f"trigger count {n} > 8 (-0.5)")

    # 触发词在正文有说明 → +0.5
    body = content.split("##", 2)[-1] if "##" in content else ""
    explained = sum(1 for t in trigger_tokens if t in body)
    if explained >= 1:
        score += 0.5
        bonuses.append("triggers explained in body (+0.5)")

    # 触发词含参数/语法说明（如 <target-type>） → +1.0
    if re.search(r"<\w+[-\w]*>", trigger_sec):
        score += 1.0
        bonuses.append("trigger has parameter syntax (+1.0)")

    # 触发词列表 >= 3 项（覆盖充分） → +1.0
    list_items = re.findall(r"^\s*[-*]\s+", trigger_sec, re.MULTILINE)
    if len(list_items) >= 3:
        score += 1.0
        bonuses.append(f"trigger list >= 3 items ({len(list_items)}) (+1.0)")

    # 触发词去重：无重复触发词 → +0.5；有重复 → -0.5
    if trigger_tokens:
        unique = set(t.lower() for t in trigger_tokens)
        if len(unique) == len(trigger_tokens):
            score += 0.5
            bonuses.append("no duplicate triggers (+0.5)")
        else:
            score -= 0.5
            deductions.append("duplicate triggers (-0.5)")

    # 触发章节含具体用法示例（代码块或反引号命令） → +1.0
    if re.search(r"`[/\w].*`", trigger_sec):
        score += 1.0
        bonuses.append("trigger usage example in backticks (+1.0)")

    # 消歧义：提到不应触发的场景 → +0.5
    neg_kws = ["不触发", "不适用", "should not", "不匹配",
               "排除", "exclude", "不要用"]
    if any(k in lower for k in neg_kws):
        score += 0.5
        bonuses.append("disambiguation / negative scope (+0.5)")

    # frontmatter 含 triggers: 列表字段（结构化触发词声明）→ +0.5
    if re.search(r"^triggers\s*:", fm, re.MULTILINE):
        score += 0.5
        bonuses.append("frontmatter triggers: list field (+0.5)")

    # frontmatter triggers: 列表有 >= 2 个条目（覆盖多别名）→ +0.5
    fm_trigger_items = re.findall(r"^\s+-\s+\S+", fm, re.MULTILINE)
    if len(fm_trigger_items) >= 2:
        score += 0.5
        bonuses.append(f"frontmatter triggers >= 2 items ({len(fm_trigger_items)}) (+0.5)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 维度 2: 结构完整性 (15%) ====================

_STRUCT_SECTIONS: list[tuple[str, list[str], float]] = [
    ("trigger section",
     ["触发方式", "触发词", "Trigger"], 0.5),
    ("setup/workflow",
     ["Setup", "工作流", "Workflow"], 1.0),
    ("execution/loop",
     ["Loop", "执行", "Execution"], 0.5),
    ("evaluation",
     ["Evaluation", "评估"], 1.0),
    ("constraints",
     ["Constraint", "约束"], 0.5),
    ("timeout/crash",
     ["Timeout", "Crash", "超时"], 0.5),
]


def eval_structure(content: str) -> DimResult:
    """评估结构完整性，基准 2.0，上限 10.0。

    :param content: skill.md 全文
    """
    score = 0.0
    bonuses: list[str] = []
    deductions: list[str] = []

    # frontmatter name+description → +1.0
    fm = _get_frontmatter(content)
    if "name:" in fm and "description:" in fm:
        score += 1.0
        bonuses.append("frontmatter name+desc (+1.0)")

    # 各章节
    for label, kws, pts in _STRUCT_SECTIONS:
        if _has_any(content, kws):
            score += pts
            bonuses.append(f"{label} (+{pts})")

    # Setup >= 3 步 → +0.5
    setup = _extract_section(content, "Setup")
    if not setup:
        setup = _extract_section(content, "工作流")
    steps = _count_re(r"^\s*\d+\.\s", setup)
    if steps >= 3:
        score += 0.5
        bonuses.append(f"setup >= 3 steps ({steps}) (+0.5)")

    # 代码块 → +0.5
    cb = _count_re(r"^```", content)
    if cb > 0:
        score += 0.5
        bonuses.append(f"code blocks ({cb}) (+0.5)")

    # CAN/CANNOT >= 4 → +0.5
    can = _count_re(r"^\s*[-*]\s*(?:CAN|CANNOT)", content)
    if can >= 4:
        score += 0.5
        bonuses.append(f"CAN/CANNOT >= 4 ({can}) (+0.5)")

    # 表格 >= 3 行 → +0.5
    tbl = _count_re(r"^\s*\|.*\|", content)
    if tbl >= 3:
        score += 0.5
        bonuses.append(f"table rows >= 3 ({tbl}) (+0.5)")

    # 目标类型表格 → +0.5
    if re.search(r"target.type|目标类型", content, re.IGNORECASE):
        score += 0.5
        bonuses.append("target-type table (+0.5)")

    # 策略指导章节 → +0.5
    if _has_any(content, ["策略", "Strategy", "指导"]):
        score += 0.5
        bonuses.append("strategy section (+0.5)")

    # 执行隔离/并发/安全章节 → +0.5
    if _has_any(content, ["隔离", "Isolation", "CRITICAL"]):
        score += 0.5
        bonuses.append("isolation/safety section (+0.5)")

    # frontmatter 含 version: 或 updated: 字段 → +0.5
    if re.search(r"^(?:version|updated)\s*:", fm, re.MULTILINE):
        score += 0.5
        bonuses.append("frontmatter version/updated field (+0.5)")

    # FAQ/已知问题/注意事项章节 → +0.5
    faq_kws = ["faq", "已知", "known", "注意", "caveats"]
    if _has_any(content, faq_kws):
        score += 0.5
        bonuses.append("FAQ/known issues/caveats section (+0.5)")

    # 明确的输入/输出规格说明章节 → +0.5
    io_heading_kws = ["输入", "输出", "input", "output", "i/o"]
    if _has_any(content, io_heading_kws):
        sec_found = any(
            re.search(
                r"^#{1,4}\s+.*" + re.escape(k) + r".*$",
                content, re.MULTILINE | re.IGNORECASE
            ) for k in io_heading_kws
        )
        if sec_found:
            score += 0.5
            bonuses.append("explicit I/O spec section (+0.5)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 维度 3: 简洁性 (10%) ====================

def eval_conciseness(content: str) -> DimResult:
    """评估简洁性，阶梯制，上限 10.0。

    :param content: skill.md 全文
    """
    bonuses: list[str] = []
    deductions: list[str] = []
    lines = content.splitlines()
    n = len(lines)

    # 阶梯评分
    score = CONCISENESS_FLOOR
    for limit, tier in CONCISENESS_TIERS:
        if n <= limit:
            score = tier
            break
    bonuses.append(f"{n} lines -> base {score}")

    # 空行占比 > 33% → -1.0
    blanks = sum(1 for ln in lines if not ln.strip())
    if n > 0 and blanks / n > 0.33:
        score -= 1.0
        deductions.append(
            f"blank ratio {blanks / n:.0%} > 33% (-1.0)")

    # 连续空行 >= 3 → -0.5
    consec = mx = 0
    for ln in lines:
        consec = consec + 1 if not ln.strip() else 0
        mx = max(mx, consec)
    if mx >= 3:
        score -= 0.5
        deductions.append(
            f"consecutive blanks {mx} >= 3 (-0.5)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 维度 4: 约束清晰度 (10%) ====================

def eval_constraints(content: str) -> DimResult:
    """评估约束清晰度，基准 4.0，上限 10.0。

    :param content: skill.md 全文
    """
    score = 0.0
    bonuses: list[str] = []
    deductions: list[str] = []
    lower = content.lower()

    # CAN/CANNOT 以动词开头 → 每条 +0.3，上限 +2.0
    items = re.findall(
        r"^\s*[-*]\s*(?:CAN(?:NOT)?)\s+\S+",
        content, re.MULTILINE)
    vb = min(len(items) * 0.3, 2.0)
    if vb > 0:
        score += vb
        bonuses.append(
            f"verb-led items ({len(items)}) (+{vb:.1f})")

    # 无模糊词 → +1.5
    found = [w for w in FUZZY_WORDS if w in lower]
    if not found:
        score += 1.5
        bonuses.append("no fuzzy words (+1.5)")
    else:
        deductions.append(f"fuzzy: {found}")

    # Timeout 有具体数值 → +0.5
    if re.search(r"[Tt]imeout.*\d+", content):
        score += 0.5
        bonuses.append("timeout with numeric value (+0.5)")

    # Crash 处理分级 → +0.5
    crash_sec = _extract_section(content, "Crash")
    crash_kws = ["语法", "syntax", "超时", "timeout",
                 "依赖", "dependency", "typo", "连续"]
    hits = sum(1 for k in crash_kws if k in crash_sec.lower())
    if hits >= 2:
        score += 0.5
        bonuses.append(f"crash multi-type ({hits}) (+0.5)")

    # 约束占比 5%-20% → +0.5
    cons_sec = _extract_section(content, "Constraint")
    if not cons_sec:
        cons_sec = _extract_section(content, "约束")
    total_len = len(content)
    if total_len > 0 and cons_sec:
        ratio = len(cons_sec) / total_len
        if 0.05 <= ratio <= 0.20:
            score += 0.5
            bonuses.append(
                f"constraint ratio {ratio:.0%} in range (+0.5)")

    # 有明确 CANNOT 条目 → +1.0
    cannot = _count_re(r"^\s*[-*]\s*CANNOT", content)
    if cannot > 0:
        score += 1.0
        bonuses.append(f"CANNOT items ({cannot}) (+1.0)")

    # 约束有明确的作用域边界（哪些文件/目录受限）→ +1.0
    scope_kws = ["目标范围", "scope", "以外的文件",
                 "outside", "boundary", "边界"]
    if any(k in lower for k in scope_kws):
        score += 1.0
        bonuses.append("scope boundary defined (+1.0)")

    # CAN 和 CANNOT 均存在（双面约束完整）→ +0.5
    can_count = _count_re(r"^\s*[-*]\s*CAN\s", content)
    if can_count > 0 and cannot > 0:
        score += 0.5
        bonuses.append("both CAN and CANNOT present (+0.5)")

    # 约束含优先级/严重性标注（CRITICAL, 必须, MUST）→ +0.5
    priority_kws = ["CRITICAL", "必须", "MUST", "禁止", "严禁"]
    if any(k in content for k in priority_kws):
        score += 0.5
        bonuses.append("priority/severity markers (+0.5)")

    # 约束按类别分组（多个子章节或分类标签）→ +1.0
    cons_headings = re.findall(
        r"^#{2,4}\s+.*(?:Constraint|约束|Crash|Timeout|超时).*$",
        content, re.MULTILINE | re.IGNORECASE)
    if len(cons_headings) >= 2:
        score += 1.0
        bonuses.append(
            f"constraint sub-sections ({len(cons_headings)}) (+1.0)")

    # 约束有违反后果说明 → +0.5
    consequence_kws = ["违反", "violation", "penalty",
                       "discard", "reject", "abort"]
    if any(k in lower for k in consequence_kws):
        score += 0.5
        bonuses.append("constraint violation consequences (+0.5)")

    # 约束有机器可验证格式 → +0.5
    verifiable_kws = ["assert", "check", "validate",
                      "verify", "必须", "must"]
    if any(k in lower for k in verifiable_kws):
        score += 0.5
        bonuses.append("machine-verifiable constraint format (+0.5)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 维度 5: 可执行性 (15%) ====================

def eval_actionability(content: str) -> DimResult:
    """评估可执行性，基准 3.0，上限 10.0。

    :param content: skill.md 全文
    """
    score = 0.0
    bonuses: list[str] = []
    deductions: list[str] = []
    lower = content.lower()

    # 具体命令/可执行代码块 → +1.5
    blocks = re.findall(
        r"```(?:bash|sh|python)?\s*\n(.*?)```",
        content, re.DOTALL)
    exe = [b for b in blocks
           if re.search(r"\b(python3|bash|git|cd|pip)\b", b)]
    if exe:
        score += 1.5
        bonuses.append(
            f"executable code blocks ({len(exe)}) (+1.5)")

    # 步骤编号清晰 → +1.0
    numbered = _count_re(r"^\s*\d+\.\s", content)
    if numbered >= 3:
        score += 1.0
        bonuses.append(f"numbered steps ({numbered}) (+1.0)")

    # 输入/输出说明 → +1.0
    io_kws = ["输入", "输出", "input", "output",
              "返回", "return", "产出"]
    io_hits = sum(1 for k in io_kws if k in lower)
    if io_hits >= 2:
        score += 1.0
        bonuses.append(f"I/O keywords ({io_hits}) (+1.0)")

    # 具体文件路径 → +0.5
    paths = re.findall(r"(?:~/|/|\./)[\w./-]+\.\w+", content)
    if paths:
        score += 0.5
        bonuses.append(
            f"concrete file paths ({len(paths)}) (+0.5)")

    # 条件分支说明 → +1.0
    branch_pats = [r"\bif\b.*(?:then|→|->|：)",
                   r"(?:条件|分支|判断)"]
    if any(re.search(p, lower) for p in branch_pats):
        score += 1.0
        bonuses.append("conditional branching (+1.0)")

    # 无"视情况而定"等模糊指导 → +1.0
    vague = ["视情况而定", "看情况", "酌情",
             "depends on context", "as appropriate"]
    if not any(p in lower for p in vague):
        score += 1.0
        bonuses.append("no vague guidance (+1.0)")
    else:
        deductions.append("vague guidance found")

    # 步骤间数据传递 → +1.0
    flow = ["传递", "接收", "作为输入", "输出到",
            "pipe", "→", "->", "结果写入"]
    if sum(1 for d in flow if d in content) >= 2:
        score += 1.0
        bonuses.append("data flow between steps (+1.0)")

    # 多个可执行代码块（>= 2 个含命令的块）→ +1.0
    if len(exe) >= 2:
        score += 1.0
        bonuses.append(
            f"multiple executable blocks ({len(exe)}) (+1.0)")

    # 决策逻辑明确（keep/discard、通过/失败等二元判定）→ +1.0
    decision_kws = ["keep", "discard", "通过", "失败",
                    "accept", "reject", "保留", "回滚"]
    if sum(1 for k in decision_kws if k in lower) >= 2:
        score += 1.0
        bonuses.append("explicit decision logic (+1.0)")

    # 有明确终止条件 → +0.5
    stop_kws = ["终止", "stop", "exit", "完成",
                "finish", "中断", "interrupt"]
    if any(k in lower for k in stop_kws):
        score += 0.5
        bonuses.append("explicit termination condition (+0.5)")

    # 有角色/责任标注 → +0.5
    role_kws = ["负责", "responsible", "agent",
                "subagent", "executor"]
    if any(k in lower for k in role_kws):
        score += 0.5
        bonuses.append("role/responsibility annotation (+0.5)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 维度 6: 防御性 (10%) ====================

def eval_defensiveness(content: str) -> DimResult:
    """评估防御性，基准 3.0，上限 10.0。

    :param content: skill.md 全文
    """
    score = 0.0
    bonuses: list[str] = []
    deductions: list[str] = []
    lower = content.lower()

    checks: list[tuple[str, list[str], float]] = [
        ("crash/timeout section",
         ["Crash", "Timeout", "异常处理"], 1.0),
        ("crash multi-type",
         ["语法错误", "syntax", "超时", "timeout",
          "依赖缺失", "dependency"], 1.0),
        ("consecutive failure strategy",
         ["连续", "consecutive", "暂停"], 1.0),
        ("rollback mechanism",
         ["回滚", "rollback", "git reset",
          "revert", "discard"], 1.0),
        ("edge case handling",
         ["空输入", "empty", "不存在", "not found",
          "边界", "edge case", "无文件"], 1.0),
        ("retry strategy",
         ["重试", "retry", "修复后重试",
          "重新尝试", "再次"], 1.0),
        ("graceful degradation",
         ["降级", "graceful", "fallback",
          "备选", "alternative", "简单 typo"], 1.0),
    ]

    for label, kws, pts in checks:
        # crash multi-type 需要 >= 2 个命中
        if label == "crash multi-type":
            hits = sum(1 for k in kws if k in lower)
            if hits >= 2:
                score += pts
                bonuses.append(f"{label} ({hits}) (+{pts})")
        elif any(k in lower for k in kws):
            score += pts
            bonuses.append(f"{label} (+{pts})")

    # 保护性检查：进入循环前有前置条件验证 → +1.0
    precond_kws = ["确认目标", "验证", "precondition", "前置",
                   "检查", "validate", "assert"]
    if any(k in lower for k in precond_kws):
        score += 1.0
        bonuses.append("precondition validation (+1.0)")

    # 状态持久化（结果不丢失）→ +1.0
    persist_kws = ["results.tsv", "持久化", "persist",
                   "记录", "追加结果", "写入"]
    if sum(1 for k in persist_kws if k in lower) >= 2:
        score += 1.0
        bonuses.append("state persistence (+1.0)")

    # Circuit Breaker 或熔断策略 → +1.0
    cb_kws = ["熔断", "circuit", "breaker", "冷却",
              "cooldown", "暂停后恢复"]
    if any(k in lower for k in cb_kws):
        score += 1.0
        bonuses.append("circuit breaker / cooldown strategy (+1.0)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 维度 7: 示例质量 (15%) ====================

def eval_examples(content: str) -> DimResult:
    """评估示例质量，基准 3.0，上限 10.0。

    :param content: skill.md 全文
    """
    score = 0.0
    bonuses: list[str] = []
    deductions: list[str] = []
    lower = content.lower()

    # 有代码块 → +0.5
    cb = _count_re(r"^```", content)
    if cb > 0:
        score += 0.5
        bonuses.append(f"has code blocks ({cb}) (+0.5)")

    # 代码块 >= 3 → +1.0
    if cb >= 6:  # 6 个 ``` 标记 = 3 个代码块
        score += 1.0
        bonuses.append("code blocks >= 3 (+1.0)")

    # 有输入示例 → +1.0
    in_kws = ["输入示例", "input example", "输入:",
              "示例输入", "example input"]
    if any(k in lower for k in in_kws):
        score += 1.0
        bonuses.append("input examples (+1.0)")

    # 有输出/结果示例 → +1.0
    out_kws = ["输出示例", "output example", "输出:",
               "示例输出", "output format", "输出格式"]
    if any(k in lower for k in out_kws):
        score += 1.0
        bonuses.append("output examples (+1.0)")

    # results.tsv 格式 → +0.5
    if "results.tsv" in lower or "results_skill.tsv" in lower:
        score += 0.5
        bonuses.append("results.tsv reference (+0.5)")

    # eval_command 示例 → +0.5（严格匹配，防止误报）
    if "eval_command" in lower or re.search(
            r"(?:python3|bash).*(?:evaluate|eval_command)", lower):
        score += 0.5
        bonuses.append("eval_command reference (+0.5)")

    # 正例/负例对比 → +1.0
    pn = ["正例", "负例", "positive", "negative"]
    if sum(1 for p in pn if p in lower) >= 2:
        score += 1.0
        bonuses.append("pos/neg comparison (+1.0)")

    # 多种 target-type → +0.5
    types = ["skill", "skill-full", "memory", "code"]
    th = sum(1 for t in types if t in lower)
    if th >= 2:
        score += 0.5
        bonuses.append(f"multi target-type ({th}) (+0.5)")

    # 具体数值（非 placeholder） → +1.0
    code_spans = re.findall(r"```.*?```", content, re.DOTALL)
    has_nums = any(
        re.search(r"\d+\.\d+|\b\d{2,}\b", b)
        for b in code_spans)
    if has_nums:
        score += 1.0
        bonuses.append("concrete numerics in examples (+1.0)")

    # 错误/失败示例（展示异常场景）→ +1.0
    err_kws = ["error", "crash", "失败", "discard",
               "crash", "不可解析"]
    err_in_example = any(
        any(k in b.lower() for k in err_kws) for b in code_spans)
    if err_in_example:
        score += 1.0
        bonuses.append("error/failure example (+1.0)")

    # 分步骤的完整工作流示例（setup→loop→eval）→ +1.0
    flow_kws = ["setup", "loop", "eval", "baseline",
                "设置", "循环", "评估"]
    flow_hits = sum(1 for k in flow_kws if k in lower)
    if flow_hits >= 3:
        score += 1.0
        bonuses.append(
            f"workflow coverage in examples ({flow_hits}) (+1.0)")

    # 完整端到端流程示例（同时含初始化+循环+结果三类关键词）→ +0.5
    e2e_init = any(k in lower for k in ["setup", "init", "初始化", "准备"])
    e2e_loop = any(k in lower for k in ["loop", "iterate", "循环", "迭代"])
    e2e_out = any(k in lower for k in ["result", "output", "输出", "结果"])
    if e2e_init and e2e_loop and e2e_out:
        score += 0.5
        bonuses.append("full e2e flow example (init+loop+result) (+0.5)")

    # 示例含版本或日期标注 → +0.5
    if re.search(r"v\d+|v2|202\d|版本|version", lower):
        score += 0.5
        bonuses.append("versioned/dated example (+0.5)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 维度 8: 自洽性 (10%) ====================

def eval_consistency(content: str) -> DimResult:
    """评估文档内部一致性，基准 7.0，扣分为主，上限 10.0。

    :param content: skill.md 全文
    """
    score = 7.0
    bonuses: list[str] = []
    deductions: list[str] = []

    eval_sec = (_extract_section(content, "Evaluation")
                or _extract_section(content, "评估"))
    eval_lower = eval_sec.lower()

    # 目标类型表格 → Evaluation 对应
    # 仅从"目标类型"章节提取 type names，避免误匹配其他表格
    type_sec = (_extract_section(content, "目标类型")
                or _extract_section(content, "target.type"))
    type_names = re.findall(r"`(\w[\w-]*)`\s*\|", type_sec)
    bonus_acc = 0.0
    for t in type_names:
        if t.lower() in eval_lower:
            added = min(0.25, 1.5 - bonus_acc)
            bonus_acc += added
            score += added
            bonuses.append(f"type '{t}' in eval (+0.25)")
        else:
            score -= 0.5
            deductions.append(
                f"type '{t}' not in eval (-0.5)")

    # Constraints 引用 target-type 与正文一致 → +0.5
    cons_sec = (_extract_section(content, "Constraint")
                or _extract_section(content, "约束"))
    if re.search(r"target.type|目标类型", cons_sec, re.I) or not type_names:
        score += 0.5
        bonuses.append("constraint-type consistent (+0.5)")

    # Setup 引用文件在 Loop 中有对应 → +0.5
    setup_sec = _extract_section(content, "Setup")
    loop_sec = _extract_section(content, "Loop")
    setup_files = re.findall(r"results\.\w+", setup_sec)
    if setup_files:
        if all(f.lower() in loop_sec.lower() for f in setup_files):
            score += 0.5
            bonuses.append("setup files in loop (+0.5)")
        else:
            score -= 0.5
            deductions.append("setup files not in loop (-0.5)")

    # 无死链接 → +0.5（扩展检测模式）
    refs = re.findall(
        r"(?:见(?:下方|上方)?|see\s+§|refer\s+to|as\s+described\s+in)\s*(\w[\w\s-]*)",
        content, re.IGNORECASE)
    headers = {
        h.lower().strip()
        for h in re.findall(
            r"^#{1,3}\s+(.+)$", content, re.MULTILINE)}
    dead = [r.strip() for r in refs
            if r.strip().lower() not in headers and len(r.strip()) > 1]
    if not dead:
        score += 0.5
        bonuses.append("no dead refs (+0.5)")
    else:
        score -= 0.5
        deductions.append(f"dead refs: {dead[:3]} (-0.5)")

    # CAN 能力在正文有对应 → +0.5
    can_items = re.findall(
        r"^\s*[-*]\s*CAN\s+(.+)$", content, re.MULTILINE)
    body_lower = content.lower()
    explained = sum(
        1 for item in can_items
        if any(w in body_lower
               for w in item.lower().split()[:3]))
    if can_items and explained >= len(can_items) * 0.5:
        score += 0.5
        bonuses.append("CAN items in body (+0.5)")

    return DimResult(_clamp(score), bonuses, deductions)


# ==================== 评估引擎 ====================

EVALUATORS: dict[str, object] = {
    "trigger": eval_trigger,
    "structure": eval_structure,
    "conciseness": eval_conciseness,
    "constraints": eval_constraints,
    "actionability": eval_actionability,
    "defensiveness": eval_defensiveness,
    "examples": eval_examples,
    "consistency": eval_consistency,
}


def evaluate(content: str) -> dict[str, DimResult]:
    """运行全部 8 维评估，返回 {维度名: DimResult}。

    :param content: skill.md 全文
    """
    return {name: fn(content) for name, fn in EVALUATORS.items()}


def compute_total(results: dict[str, DimResult]) -> float:
    """加权总分。

    :param results: 8 维评估结果
    """
    return sum(results[d].score * WEIGHTS[d] for d in WEIGHTS)


# ==================== 报告输出 ====================

def print_report(
    path: str,
    results: dict[str, DimResult],
    total: float,
) -> None:
    """打印 8 维评估报告。

    :param path: 文件路径
    :param results: 8 维评估结果
    :param total: 加权总分
    """
    print(f"file: {path}")
    print("---")

    for dim in WEIGHTS:
        r = results[dim]
        pct = int(WEIGHTS[dim] * 100)
        print(f"{dim}: {r.score:.2f}  (weight: {pct}%)")
        for b in r.bonuses:
            print(f"  + {b}")
        for d in r.deductions:
            print(f"  - {d}")

    print("---")
    print(f"total_score: {total:.2f}")
    print("---")

    # 最弱 3 维度
    ranked = sorted(results.items(), key=lambda kv: kv[1].score)
    print("weakest 3 dimensions (most room for improvement):")
    for dim, r in ranked[:3]:
        print(f"  {dim}: {r.score:.2f}")
        for d in r.deductions:
            print(f"    - {d}")


# ==================== 入口 ====================

def main() -> None:
    """Entry point: evaluate a single SKILL.md file."""
    if len(sys.argv) < 2:
        print("Usage: evaluate_skill.py <skill.md-path>")
        sys.exit(1)

    path = Path(sys.argv[1]).resolve()
    if not path.is_file():
        print(f"ERROR: not a file: {path}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8", errors="replace")
    results = evaluate(content)
    total = compute_total(results)
    print_report(str(path), results, total)


if __name__ == "__main__":
    main()
