---
name: auto-iterate
version: 2.0
triggers:
  - /auto-iterate
  - 自动迭代
  - 迭代改进
  - Karpathy Loop
description: "Karpathy Loop 式自主迭代改进框架。对 skill/skill-full/memory/code 执行「修改→评估→保留/回滚」无限循环。触发词：/auto-iterate、自动迭代、迭代改进、Karpathy Loop"
---
## 触发方式
- `/auto-iterate <target-type> <target-path>`
- 「自动迭代 X」「迭代改进 X」「Karpathy Loop」
- 正例（should trigger）：`/iterate skill ./SKILL.md`、「帮我迭代改进这个 skill」
- 负例（should not trigger）：一次性编辑、无评估指标的自由修改、普通代码 review
## 目标类型
| target-type | 目标 | 可修改内容 | 评估指标 |
|---|---|---|---|
| `skill` | SKILL.md 文件 | 触发词、流程、约束、结构 | 8 维加权评估（脚本自动） |
| `skill-full` | 完整 skill 目录 | skill.md + 脚本 | 定义+代码+规范+一致性 |
| `memory` | agent 记忆目录 | 记忆文件增删改、索引 | 检索命中率+信噪比+索引 |
| `code` | 代码文件 | 代码逻辑（用户指定边界） | 用户指定 eval_command 输出 |
## Setup
1. **确认目标**：用户指定 target-type 和 target-path
2. **创建分支**：`git checkout -b auto-iterate/<date>-<target>`
3. **读取目标**：完整理解当前状态
4. **初始化 results.tsv**：目标目录下创建（`commit\tscore\tstatus\tdescription`，不 git track）
5. **建立 baseline**：首次评估记录为 baseline（status=keep）→ 进入 Loop
## The Loop
> LOOP FOREVER — 不暂停、不询问，持续迭代直到手动中断。
```
1. 读 git log + results.tsv，理解历史
2. 分析目标，提出一个聚焦的改进点
3. 修改目标文件
4. git commit -m "auto-iterate: <改动简述>"
5. 评估 → score 提升？ → keep；不变/下降？ → git reset --hard HEAD~1
6. 追加结果到 results.tsv → 回到步骤 1
```
### 策略指导
- **先低垂果实**：缺失字段、冗余内容、错误约束；**单点改动**：每次只改一个方面，便于归因
- **简洁优先**：删代码且不降分 = 最佳结果；**不要重复**：results.tsv 中 discard 的方案不要原样重试
### 执行隔离（CRITICAL）
每轮由**独立 subagent** 执行（防止上下文污染）。subagent 接收输入：目标文件、results.tsv、轮次编号；通过 results.tsv + git log 理解历史，将结果写入 results.tsv → 传递 keep/discard 给 root。
## Evaluation
```bash
python3 ~/.claude/skills/auto-iterate/scripts/evaluate_skill.py <path>
python3 ~/.claude/skills/auto-iterate/scripts/evaluate_skill_full.py <dir>
python3 ~/.claude/skills/auto-iterate/scripts/evaluate_memory.py <store> [--agent <name>]
bash ~/.claude/skills/auto-iterate/scripts/evaluate.sh <target>
```
- 总分↑ → keep；总分↓ → discard；skill-full 同 skill；code 类型用用户指定 `eval_command`（如 `"pytest --tb=short -q"`）
## 输入/输出规格
- **输入**：target-type（skill/skill-full/memory/code）+ target-path；**输出**：results.tsv（commit\tscore\tstatus\tdescription）+ 每轮 git commit
## Constraints（按 target-type 适用）
- CAN 修改目标文件内容（增删改重构）
- CAN 修改 skill 目录下的任意文件（skill-full 类型）
- CAN 重组目标目录结构（memory 类型）
- CAN 运行只读命令分析目标
- CANNOT 修改评估方法本身（评估是 ground truth，ground truth 不可变）
- CANNOT 安装新依赖或修改 pyproject.toml
- CANNOT 修改目标范围以外的文件（results.tsv 除外）
### Crash 异常处理（Timeout: 5 分钟/轮，超时视为 crash）
- 语法错误/不可解析 → discard + 记录 crash；简单 typo → 修复后重试（计为同一次迭代）
- 依赖缺失/dependency 不可用 → discard + 记录原因；连续 3 次 crash → 暂停，回顾策略
- Circuit Breaker：连续 5 次 discard → 冷却 1 轮；暂停后恢复时优先尝试结构性改动
## 输入示例 / Input Example
```bash
/auto-iterate skill ~/.claude/skills/my-skill/SKILL.md
```
输出示例 / Output Example（results.tsv）：
```
commit	score	status	description
a1b2c3d	5.78	keep	baseline (8-dim skill evaluation)
e4f5g6h	6.12	keep	remove fuzzy word, add pos/neg triggers
h7i8j9k	6.12	discard	restructure evaluation section (no gain)
i0j1k2l	crash	discard	syntax error in frontmatter (invalid yaml)
```
## 注意事项
- results.tsv 不进 git track，避免污染迭代历史；评估脚本不可修改，确保 ground truth 稳定
- 手动中断后可从最后一个 keep commit 继续
