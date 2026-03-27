---
name: reflex-fuzz
description: "反射系统 Fuzz 测试与迭代改进。触发词：/reflex-fuzz、/fuzz-reflex、反射 fuzz、fuzz 测试反射"
---

# Reflex Fuzz — 反射系统 Fuzz 测试与迭代改进

对反射系统进行主动 fuzz 测试：构造测试场景 → 发现问题 → 修复 → 验证 → 循环迭代。

## 触发方式

- `/reflex-fuzz` — 启动单轮 fuzz 测试（完整反射链）
- `/reflex-fuzz loop [interval]` — 启动循环 fuzz（默认 5m 间隔）
- `/reflex-fuzz report` — 输出当前 fuzz 测试进度报告
- 「fuzz 测试反射系统」「反射 fuzz」

## 模式

| 模式 | 触发 | 说明 |
|------|------|------|
| 单轮 | `/reflex-fuzz` | 执行一轮完整反射链：探索→决策→实现→审计→提交→日记→记忆 |
| 循环 | `/reflex-fuzz loop 5m` | 用 /loop 设置定时器，每 N 分钟自动执行一轮 |
| 报告 | `/reflex-fuzz report` | 汇总已完成的 fuzz 轮次和修复清单 |

## 单轮流程（完整反射链，角色严格分离）

### Phase 1: 探索（kaze, Explore）

kaze 读取以下文件，输出现状 + 问题列表：

- `~/mem/mem/workflows/trigger-stats.json` — 全量统计
- `~/.claude/hooks/post-agent-trigger-stats.py` — 实现逻辑
- `~/.claude/hooks/pre-agent-cb-check.py` — CB 拦截逻辑
- `~/.claude/hooks/reflex-config.json` — 共享配置
- `~/mem/mem/workflows/trigger-map.md` — SSOT 转移规则

输出格式：
```
## RN 探索报告
### 统计快照
{反射一行表}
### 问题列表（按优先级）
1. [HIGH/MEDIUM/LOW] {问题} — {位置}
### 推荐本轮修复
{TOP 1 + 理由}
```

如果无问题可修，输出「反射系统健康，本轮跳过」并结束。

或运行收集脚本：
```bash
bash ~/.claude/skills/reflex-fuzz/scripts/explore.sh
```

### Phase 2: 决策（root）

从 kaze 报告中选 TOP 1 问题，制定修复方案。

决策标准：
- HIGH > MEDIUM > LOW
- 同级别选修复成本最低的
- 每轮只修一个问题

### Phase 3: 实现（tetsu, Worker）

执行修复。可能涉及：
- hook 脚本修改
- trigger-stats.json schema 扩展
- trigger-map.md 转移规则更新
- reflex-config.json 配置变更
- CLAUDE.md 规则同步

### Phase 4: 审计（shin, code-reviewer）

验证修复正确性：
- 语法检查（py_compile）
- 逻辑审查（边界条件、向后兼容）
- 一致性（SSOT vs 副本 vs CLAUDE.md）

如果审计失败 → tetsu 修正 → shin 重审，循环直到通过。

### Phase 5: 提交（tetsu）

```bash
git add <files> && git commit -m "fix: {修复描述}" && git push
```

### Phase 6: 日记（fumio）

追加当日日报 `500_Journal/Daily/YYYY-MM-DD.md`：
```
- Round N: {修了什么}，shin 审计{通过/需修正}
```

### Phase 7: 记忆（yume）

保存 workflow run：
```bash
python3 ~/.claude/skills/agent-memory/scripts/cli.py \
  --agent root --store ~/mem/mem/agents/root \
  quick-add --name "Fuzz Round N: {问题}" \
  --description "{一句话}" --type task \
  --keywords "fuzz,roundN,{问题标签}" "{详细内容}"
```

创建 `~/mem/mem/workflows/runs/YYYY-MM-DD-fuzz-roundN.md`

## 测试用例分类

| 类别 | 测试内容 | 优先级 |
|------|---------|--------|
| Happy Path | 常用路径（bug fix、新功能、配置变更等）端到端 | P3 |
| 失败恢复 | Recovery Ladder L1-L4 触发是否正确 | P0 |
| CB 熔断 | 连续失败→OPEN、24h→HALF-OPEN、2胜→CLOSED | P0 |
| 边缘情况 | 并行反射、跳步、agent busy、空任务 | P2 |
| 未触发反射 | devour/define 等使用率为 0 的反射 | P1 |

## 循环模式

启动：
```
/reflex-fuzz loop 5m
```

等效于：
```
/loop 5m /reflex-fuzz
```

停止条件：
- 连续 3 轮 kaze 报告「系统健康」→ 自动建议停止
- 用户手动 CronDelete
- cron 3 天自动过期

## 数据源

| 文件 | 用途 |
|------|------|
| `~/mem/mem/workflows/trigger-stats.json` | 反射统计 + CB + recovery |
| `~/.claude/hooks/post-agent-trigger-stats.py` | 统计 hook 逻辑 |
| `~/.claude/hooks/pre-agent-cb-check.py` | CB 拦截 hook |
| `~/.claude/hooks/reflex-config.json` | 共享配置 |
| `~/mem/mem/workflows/trigger-map.md` | SSOT 转移规则 |
| `~/.claude/rules/trigger-map.md` | 自动加载副本 |
| `~/mem/mem/workflows/runs/*.md` | 历史 workflow runs |

## 约束

1. **角色分离不可压缩** — kaze 只读、shin 只审、tetsu 只改、fumio 只文档
2. **每轮只修一个问题** — 增量可控
3. **审计必须通过** — 不通过则循环修正
4. **健康则跳过** — 不做无意义改动
