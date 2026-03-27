---
name: reflex-audit
description: "反射链审计与改进。触发词：/reflex-audit、/反射审计、/改进反射链、/reflex-fix"
---

# Reflex Audit — 反射链审计与即时改进

审计反射系统的健康状态，基于 trigger-stats.json 统计数据和 workflow runs 历史记录，评分并产出改进建议。支持两种模式：完整审计和即时修复。

## 触发方式

- `/reflex-audit` — 完整审计模式
- `/反射审计` — 完整审计模式
- `/reflex-fix {问题描述}` — 即时修复模式
- `/改进反射链` — 完整审计模式
- 「反射链有什么问题」「审计反射系统」

## 模式选择

| 模式 | 触发 | 流程 | 适用场景 |
|------|------|------|---------|
| Full Audit | `/reflex-audit` | 5 Phase 完整流程 | 定期体检、系统性改进 |
| Quick Fix | `/reflex-fix {问题}` | 3 步快速修复 | 刚跑完反射链，对某步不满意 |

## 数据源

| 数据 | 路径 | 用途 |
|------|------|------|
| 反射定义 | `~/mem/mem/workflows/trigger-map.md` | 当前规则完整性 |
| 统计数据 | `~/mem/mem/workflows/trigger-stats.json` | 成功/失败/跳过计数 + CB 状态 |
| 历史运行 | `~/mem/mem/workflows/runs/*.md` | 模式分析（重试频率、瓶颈） |
| 配置规则 | `~/.claude/CLAUDE.md` | 反射相关规则一致性 |
| Agent 记忆 | `~/mem/mem/agents/*/` | 反射执行中的经验教训 |

---

## Mode A: Full Audit（完整审计）

### Phase 1: Collect（kaze）

1. 读取 `~/mem/mem/workflows/trigger-stats.json` 全部统计
2. 扫描 `~/mem/mem/workflows/runs/` 目录所有 workflow run 文件
3. 提取每个 Phase 的状态、重试次数、策略
4. 或直接运行收集脚本：

```bash
python3 ~/.claude/skills/reflex-audit/scripts/collect.py
```

输出 JSON 摘要到 stdout。

### Phase 2: Analyze（yomi）

6 维评分，每项 0-10，加权总分映射为 A-F：

| 维度 | 权重 | 检测方式 |
|------|------|---------|
| 覆盖度 | 20% | 11 个反射是否都有使用记录（success > 0） |
| 失败恢复 | 25% | 失败后 Recovery Ladder 是否正确触发 |
| 效率 | 15% | 跳步是否合理（有记录原因） |
| 均衡性 | 15% | 反射间使用比例是否健康（无极端偏斜） |
| CB 健康 | 15% | 有无 OPEN/HALF-OPEN 状态的熔断反射 |
| 一致性 | 10% | trigger-map ↔ CLAUDE.md ↔ rules 三处定义是否同步 |

评分等级：A (90+) / B (80-89) / C (70-79) / D (60-69) / F (<60)

可运行分析脚本：

```bash
python3 ~/.claude/skills/reflex-audit/scripts/analyze.py
```

### Phase 3: Diagnose（shin DA 模式）

交叉检查 workflow runs 中的失败模式：
- 识别：重复失败的反射、从未使用的反射、过度依赖的反射
- 输出「反射健康热力图」（文本表格）

### Phase 4: Report（root 合成）

汇总输出审计报告，格式如下：

```markdown
## 反射链审计报告 — YYYY-MM-DD

### 总评：{等级} ({分数}/100)

| 维度 | 得分 | 说明 |
|------|------|------|
| 覆盖度 | X/10 | ... |
| 失败恢复 | X/10 | ... |
| 效率 | X/10 | ... |
| 均衡性 | X/10 | ... |
| CB 健康 | X/10 | ... |
| 一致性 | X/10 | ... |

### 反射健康热力图

| 反射 | 使用次数 | 成功率 | CB 状态 | 趋势 |
|------|---------|--------|---------|------|
| 调研 | N | X% | CLOSED | ↑/→/↓ |
| ... | ... | ... | ... | ... |

### 改进建议（按优先级）

1. [HIGH] {建议}
2. [MEDIUM] {建议}
3. [LOW] {建议}
```

**Report-before-modify gate**：展示报告后 root 自主决策，直接推进。

### Phase 5: Improve（fumio + tetsu）

root 自主决策后执行改进：
- fumio 更新 trigger-map.md / CLAUDE.md 文档类变更
- tetsu 更新 trigger-stats.json / 重置 CB 状态 / 配置类变更
- 修改后由 shin 快速验证一致性

### Phase 6: 完成反射（终结器）

Phase 5 改进落地后，自动触发标准完成反射：

1. **提交**（tetsu）：将本次审计产生的文件变更 git commit
2. **日记**（fumio）：触发 daily-journal，记录审计结果到当日日报
3. **记忆归档**（yume）：保存审计发现和改进决策到 workflow run

此步骤确保审计任务与标准决策反射的终结行为一致，不遗漏日记和记忆。

---

## Mode B: Quick Fix（即时修复）

触发：`/reflex-fix {问题描述}`

### Step 1: 定位（kaze）

根据用户描述的问题，定位涉及的反射：
- 读取 trigger-map.md 中该反射的转移规则
- 读取 trigger-stats.json 中该反射的统计和 CB 状态
- 读取最近 3 个 workflow runs 中该反射的执行记录

### Step 2: 诊断+修复（root 决策 → tetsu/fumio 执行）

root 分析问题原因，决定修复方案：

| 问题类型 | 修复方案 | 执行者 |
|----------|---------|--------|
| 转移规则不合理 | 修改 trigger-map.md 转移条件 | fumio |
| CB 误触发 | 重置 trigger-stats.json CB 字段 | tetsu |
| 阈值不合适 | 调整 Recovery Ladder 阈值 | fumio |
| Agent prompt 问题 | 更新对应 Agent 的 WhoAmI.md | fumio |
| 流程缺失 | 在 trigger-map.md 新增转移规则 | fumio |

**无 gate**：直接修改，不需要确认步骤。

### Step 3: 验证（haku 快速验证）

- 确认修改后的文件格式正确
- 确认修改未破坏其他反射路径
- 同步 rules/trigger-map.md 副本（如有变更）

### Step 3.5: 端到端实战测试（haku）

修复完成后，必须实际触发相关反射路径验证修复生效：

| 修复类型 | 实战测试方式 |
|----------|-------------|
| 转移规则变更 | 构造一个触发该规则的最小任务，观察转移是否正确 |
| CB/Recovery 修复 | 模拟失败场景，验证恢复路径 |
| Hook 脚本修改 | 用测试输入运行 hook，检查输出 |
| 配置变更 | 触发依赖该配置的反射，确认生效 |
| Skill 创建 | 用 `/skill-name` 触发 skill，验证加载和执行 |

**不可跳过**：Quick Fix 的价值在于快速修复，但未经实战验证的修复可能引入新问题。

### 完成反射（终结器，简化版）

Step 3 验证通过后，触发轻量完成反射：

1. **日记**（fumio）：触发 daily-journal，将本次修复内容记录到当日日报
2. **记忆归档**（yume）：保存修复问题、操作步骤和验证结果到 agent 记忆

Quick Fix 为即时小修复，通常无需单独 commit（修复已包含在上游 commit 中），故省略提交步骤。

---

## 输出示例

### Full Audit 输出示例

```
## 反射链审计报告 — 2026-03-15

### 总评：B+ (82/100)

| 维度 | 得分 | 说明 |
|------|------|------|
| 覆盖度 | 7/10 | 「吞食」「定义」从未使用 |
| 失败恢复 | 9/10 | Recovery Ladder 正常运作 |
| 效率 | 8/10 | 跳步均有记录原因 |
| 均衡性 | 7/10 | 实现反射使用频率是审计的 3 倍 |
| CB 健康 | 10/10 | 全部 CLOSED |
| 一致性 | 10/10 | 三处定义完全同步 |

### 反射健康热力图

| 反射 | 使用 | 成功率 | CB | 趋势 |
|------|------|--------|--------|------|
| 审计 | 47 | 89% | CLOSED | ↑ |
| 实现 | 52 | 94% | CLOSED | → |
| 调研 | 38 | 100% | CLOSED | → |
| 吞食 | 0 | — | CLOSED | — |

### 改进建议

1. [MEDIUM] 吞食/定义反射使用为 0，建议在适当场景主动触发
2. [LOW] 实现/审计比例 3:1，考虑是否部分审计被跳过
```

### Quick Fix 输出示例

```
问题：审计反射 lint 检查太严格，总是失败
定位：trigger-stats.json audit.failure = 5, cb_state = HALF-OPEN
修复：重置 CB 状态 + 在 shin WhoAmI 中降低 lint 严格度
验证：trigger-stats audit.cb_state = CLOSED, 转移规则无破坏
```

## 注意事项

1. Full Audit 的 Phase 4 必须先展示报告，审计通过后直接执行 Phase 5
2. Quick Fix 无需确认，直接执行（可逆操作）
3. 修改 trigger-map.md 后必须同步 rules/trigger-map.md 副本
4. 统计数据（trigger-stats.json）是只增不删的，重置 CB 不清除历史计数
5. 评分基于真实数据，不做主观判断
