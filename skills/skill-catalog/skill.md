---
name: skill-catalog
description: "汇总所有 Claude Code Skills 的目录与使用指南，支持检查 GitHub 更新。触发词：/skills、技能目录、skill列表、有哪些技能、检查更新"
---

# Skill Catalog - 技能目录

汇总当前所有可用的 Claude Code Skills，按类别分组，方便查找与使用。支持检查 GitHub plugins 更新。

## 触发方式

- `/skills` 或 `/skill-catalog` - 显示技能目录
- `/skills check` 或 `检查技能更新` - 检查 GitHub plugins 更新
- 「有哪些技能」「技能目录」「skill 列表」

---

## 技能分类总览

| 类别 | 数量 | 说明 |
|------|------|------|
| 一、学术写作与研究 | 14 | 论文分析、写作风格、引用管理、叙事表达 |
| 二、论文/学位论文工具 | 12 | LaTeX 编辑、论文审计、DOCX 构建、答辩准备 |
| 三、文献检索与学术数据库 | 3 | arXiv、OpenAlex、Semantic Scholar |
| 四、知识管理（Obsidian / NotebookLM） | 11 | PARA 方法、笔记同步、任务看板、日记 |
| 五、文档处理 | 10 | PDF、DOCX、PPTX、LaTeX、Pandoc 转换 |
| 六、开发工具与协作 | 28 | AI CLI 集成、子代理、门禁循环、规划 |
| 七、可视化与设计 | 4 | Mermaid、科学图表、流程图索引 |
| 八、技能管理 | 10 | 编写规范、快照、复盘、CLAUDE.md 审计 |
| 九、求职与简历 | 2 | ATS 优化、技术简历 |
| 十、项目管理与产品 | 2 | PRD 生成、项目估算 |
| Superpowers 插件技能 | 14 | `superpowers:` 前缀，并行/调试/分支等 |
| 内置技能 | 14 | 无前缀，代码审查/TDD/重构/文档等 |
| **合计** | **124** | 本地 skill 96 + Superpowers 插件 14 + 内置技能 14 |

---

## 一、学术写作与研究（14 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| academic-researcher | 学术研究助手：文献综述、论文分析、学术写作 | 学术研究、paper review |
| academic-writing | 系统化学术写作方法论：研究设计、文献管理、同行评审 | 学术写作、research methodology |
| ai-vibe-writing-skills | 中英文写作风格迁移与错误记忆工作流，多智能体写作闭环 | 写作风格迁移 |
| citation-management | 综合引用管理：Google Scholar/PubMed 检索，多格式引用 | 引用管理、citation |
| communication-storytelling | 将分析/数据转化为有说服力的叙事 | 演讲叙事、storytelling |
| deep-reading-analyst | 深度分析文章/论文/长篇内容，10+ 思维工具 | 分析文章、deep dive |
| humanizer | 去除 AI 写作痕迹，使文本自然 | AI去痕、humanize |
| ml-paper-writing | ML/AI 顶会论文写作（NeurIPS/ICML/ICLR/ACL/AAAI） | ML论文写作 |
| outline-collaborator | 主动协作式提纲伙伴，共同发展写作结构 | 提纲协作、outline |
| reverse-outliner | 逆向工程已发表书籍，生成逐场景结构化大纲 | 逆向提纲、reverse outline |
| scientific-writing | 科学手稿写作核心 skill，全段落深度研究写作 | 科学写作、manuscript |
| section-logic-polisher | 对每个 H3 小节强制逻辑主线，检测段落孤岛 | 段落逻辑、logic polisher |
| style-harmonizer | 去除论文槽位句式，统一跨章节写作风格 | 风格统一、style harmonizer |
| subsection-polisher | 将 sections/*.md 中 H3 单元润色为学刊级散文 | 小节润色、subsection polisher |

---

## 二、论文/学位论文工具（12 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| latex-thesis-zh | 中文学位论文 LaTeX 助手（博士/硕士），深度学习/时间序列/工业控制 | /latex-thesis、编译、xelatex |
| latex-sentence-surgery | LaTeX 论文句子级最小改动（删除/替换）+ 可选四步编译 | 移除这句话、删除这句、替换这句 |
| thesis-audit | 论文完整 gate-loop 审计：审计→修复→重审→编译→提交→日记 | /thesis-audit、论文审计 |
| thesis-rewrite-review-orchestrator | 学位论文章节循环改写编排器，上下文隔离 + subagent + 三重门禁 | 论文改写、章节编排 |
| defense-qa-collector | 论文写作中自动收集答辩预判问题 | /defense、答辩问题 |
| manuscript-review | 系统性预发表手稿审计，结构化修改清单 | manuscript review、论文审稿 |
| paper-mapping | 论文段落级仿写映射：结构、逻辑、方法映射 | /mapping、论文映射、段落映射 |
| paragraph-move-analysis | 逐句拆解论文段落写作动作，可迁移仿写模板 | /paragraph-analysis、段落拆解 |
| research-paper-writer | IEEE/ACM 格式研究论文写作 | 论文写作、paper writer |
| swun-thesis-docx-banshi1 | SWUN 学位论文 DOCX 构建（版式1），使用官方模板 | SWUN论文、版式1 |
| word-to-tex | Word 内容整理为标准 LaTeX 格式 | /wordtotex、Word转LaTeX |
| tikz-flowchart | 生成标准化 TikZ 流程图（Material 配色） | TikZ、流程图 |

---

## 三、文献检索与学术数据库（3 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| arxiv-search | 自然语言检索 arXiv 物理/数学/CS 预印本 | arXiv、论文搜索 |
| openalex-database | 查询分析 OpenAlex 学术文献数据库 | OpenAlex、文献查询 |
| semantic-scholar | Semantic Scholar API 检索/验证 2.14 亿+ 学术论文 | 论文检索、S2搜索、查论文 |

---

## 四、知识管理（Obsidian / NotebookLM）（11 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| obsidian-markdown | Obsidian 风格 Markdown：wikilinks、callouts、属性 | Obsidian笔记、wikilinks |
| obsidian-bases | Obsidian Bases（.base）：视图、过滤器、公式 | Obsidian Bases、.base |
| obsidian-gh-knowledge | Obsidian vault 本地/远程 GitHub 操作 | GitHub知识图谱 |
| para-second-brain | PARA 方法第二大脑维护：分类、归档、月度复盘 | PARA分类、收件箱处理 |
| notebooklm | 自动化 Google NotebookLM：笔记本管理、播客生成 | /notebooklm、create a podcast |
| nb-query | NotebookLM 超富集查询：引用溯源、事实核查 | /nb-query、智能笔记本查询 |
| sync-notebooklm-kb | 同步本地文章目录到 NotebookLM 知识库 | 同步NotebookLM |
| task-dashboard | 扫描活跃项目提取任务并按紧急度排序 | /task-dashboard、今日任务、任务看板 |
| daily-journal | 自动创建/追加当日日记，智能定位章节 | /daily-journal、记录日记、写日报 |
| rss-daily-digest | 抓取 RSS feeds，生成今日新闻摘要 | /rss日报、今日新闻 |
| article-linker | 文章标题→发布链接映射 | /article-linker、查找文章链接 |

---

## 五、文档处理（PDF / DOCX / PPTX / LaTeX / Pandoc）（10 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| pdf | PDF 文件通用处理（阅读、提取、分析） | PDF、读PDF |
| pdf2md-academic | 学术 PDF 转 Markdown：公式、图表、引用保留 | /pdf2md、PDF转Markdown |
| rename-pdf | 提取 PDF 元数据标题并自动重命名 | /renamepdf、重命名PDF |
| docx | 创建/读取/编辑 Word 文档（.docx） | Word文档、.docx |
| docx-diff | 对比两份 DOCX 格式差异（styles/numbering/theme） | /docx-diff、对比docx |
| pandoc | 通用文档转换器（Markdown→PDF/DOCX/HTML/LaTeX 等 40+ 格式） | pandoc、文档转换 |
| pandoc-citeproc-export | LaTeX 通过 pandoc+citeproc 导出 Word，保留 GB/T 7714-2015 引用 | /pandoc-export、LaTeX转Word |
| pptx | 创建/读取/编辑演示文稿（.pptx） | slides、deck、.pptx |
| canvas-design | 设计哲学创建 .png/.pdf 视觉艺术 | 设计、canvas design |
| json-canvas | 创建/编辑 JSON Canvas 文件（.canvas） | JSON Canvas、思维导图 |

---

## 六、开发工具与协作（28 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| collaborating-hub | 统一外部 AI CLI 协作入口：Codex/Gemini/Kimi 三后端 | /collab、协作调用 |
| collaborating-with-codex | Codex CLI 后端实现（由 hub 路由） | /codex |
| collaborating-with-gemini | Gemini CLI 后端实现 | /gemini |
| collaborating-with-kimi | Kimi CLI 后端实现 | /kimi |
| sub-agents | 创建和配置 Claude Code 子代理 | 子代理、sub-agent |
| orchestrator | subagent waves/teams/pipelines 并行执行 | 并行执行、orchestrate |
| gate-loop-orchestrator | 通用 Gate 循环门禁：失败自动修复并复检 | /gate-loop、门禁循环 |
| systematic-debugging | 系统化调试流程 | debug、系统调试 |
| test-driven-development | TDD 工作流：先写测试再实现 | TDD、测试驱动 |
| quality-gates | 任务复杂度评估与质量门禁检查 | 质量门禁、gate |
| task-checkpoint | 任务完成后更新 plan + TODO + commit + push | /checkpoint、任务检查点 |
| task-dispatcher | 路由任务到 Codex 执行，支持并发分派 | /dispatch、任务分派 |
| dependency-tracking | 跨团队/系统项目依赖追踪与管理 | 依赖追踪、dependency |
| sync-configs | 同步配置文件（跨环境/工具） | SYNC-CONFIGS |
| ln-004-agent-sync | 将 skills 和 MCP 配置从 Claude 同步到 Gemini/Codex CLI | agent同步、skills同步 |
| changelog | 每日日期命名变更记录文件（PostToolUse hook） | changelog、变更记录 |
| bug-record | 记录 bug 修复到 bugs.jsonl | /bug、记录bug |
| planning-workflow | 完整规划工作流：架构规划→任务分解→执行 | 规划工作流 |
| planning-with-files | Manus 风格持久化 Markdown 文件规划 | 文件规划 |
| executing-plans | 在独立会话执行已写实现计划 | 执行计划 |
| writing-plans | 多步骤任务规范编写（代码前先计划） | 写计划 |
| web-fetch-fallback | WebFetch 失败时的智能备选方案 | /fetch、WebFetch失败 |
| agent-browser | 自动化浏览器交互：测试/填表/截图/数据提取 | browser、浏览器自动化 |
| makepad-evolution | Makepad 自进化开发系统：知识积累/错误自修正 | Makepad开发 |
| dotnet-enable-autocomplete | 启用 .NET 自动补全 | dotnet |
| plan-writing | 计划文档格式规范 | /plan-writing、写计划 |
| requesting-code-review | 请求代码审查（验证+修复上下文） | code review请求 |
| brainstorming | 创意工作前必用：发散生成特性/方案（本地版，与 superpowers:brainstorming 独立） | brainstorm、头脑风暴 |

---

## 七、可视化与设计（4 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| mermaid-diagrams | Mermaid 流程图、时序图、类图、ER 图、甘特图 | Mermaid、flowchart |
| scientific-visualization | matplotlib/seaborn/plotly 发表级图表 | 科学可视化、publication figure |
| scientific-schematics | Nano Banana Pro AI 发表级科学示意图 | 科学图表、schematics |
| diagram-indexer | 增量解析 Mermaid/Canvas 文件，精确索引流程图 | /diagram-index、流程图索引 |

---

## 八、技能管理（10 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| skill-authoring | Skill 编写规范与最佳实践 | /skill-authoring、编写skill |
| skill-catalog | 汇总所有 Skills 目录，支持 GitHub 更新检查（本 skill） | /skills、技能目录 |
| skill-consolidator | 合并/去重 skill 目录 | skill合并 |
| skill-manager | GitHub-based skills 生命周期管理 | /skill-manager |
| skill-retrospective | 回顾 skill 使用情况，迭代优化 | /skill复盘 |
| skill-snapshot | 创建/恢复可逆 skill 快照 | /skill-snapshot |
| find-skills | 发现和安装适合场景的 agent skill | 发现skill |
| claude-md-improver | 审计并改进 CLAUDE.md 文件 | CLAUDE.md审计 |
| claude-md-management | 综合 CLAUDE.md 管理（审计/质量/改进） | CLAUDE.md管理 |
| learned | /learn 命令的模式存储目录，保存从会话中提取的可复用模式（非独立 skill） | — |

---

## 九、求职与简历（2 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| resume-ats-optimizer | 优化简历以通过 ATS 系统 | 简历优化、ATS |
| tech-resume-optimizer | 软件工程/PM/技术岗简历优化 | 技术简历 |

---

## 十、项目管理与产品（2 个）

| Skill | 描述 | 触发词 |
|-------|------|--------|
| product-requirements | 交互式产品需求收集与 PRD 生成 | PRD、产品需求 |
| project-estimation | 多种估算技术评估项目范围/时间/资源 | 项目估算 |

---

## Superpowers 插件技能（14 个）

> 前缀 `superpowers:`，通过 superpowers-marketplace 安装。

| Skill | 描述 |
|-------|------|
| superpowers:dispatching-parallel-agents | 并行派发多个 agent |
| superpowers:brainstorming | 创意头脑风暴（插件版，增强流程约束，与本地 brainstorming 独立） |
| superpowers:receiving-code-review | 接收代码审查反馈 |
| superpowers:finishing-a-development-branch | 开发分支收尾 |
| superpowers:subagent-driven-development | 子代理驱动开发 |
| superpowers:systematic-debugging | 系统化调试 |
| superpowers:using-git-worktrees | Git worktrees 并行开发 |
| superpowers:using-superpowers | Superpowers 使用指南 |
| superpowers:requesting-code-review | 发起代码审查 |
| superpowers:verification-before-completion | 完成前验证 |
| superpowers:writing-plans | 编写实现计划 |
| superpowers:executing-plans | 执行已写计划 |
| superpowers:writing-skills | 编写新 skill |
| superpowers:test-driven-development | 测试驱动开发 |

---

## 内置技能（14 个）

> 无前缀，Claude Code 原生内置。

| Skill | 描述 |
|-------|------|
| update-codemaps | 更新代码地图 |
| orchestrate | 编排子任务并行执行 |
| plan | 生成结构化任务计划 |
| code-review | 执行代码审查 |
| tdd | 测试驱动开发 |
| checkpoint | 保存进度检查点 |
| refactor-clean | 清理式重构 |
| update-docs | 更新项目文档 |
| build-fix | 修复构建错误 |
| test-coverage | 检查测试覆盖率 |
| verify | 独立验证任务完成 |
| eval | 评估代码/方案质量 |
| e2e | 端到端测试 |
| learn | 从会话中学习并更新记忆 |

---

## 快速查找表

| 我想要... | 使用 Skill |
|-----------|------------|
| 写学术论文 | academic-writing / scientific-writing |
| 分析论文结构 / 建立仿写映射 | paper-mapping |
| 逐句分析段落写作动作 | paragraph-move-analysis |
| 学术 PDF 转 Markdown | pdf2md-academic |
| 转换 Word 到 LaTeX | word-to-tex |
| 编辑/编译 LaTeX 学位论文 | latex-thesis-zh / latex-sentence-surgery |
| 论文完整审计门禁 | thesis-audit |
| 构建 SWUN 学位论文 DOCX | swun-thesis-docx-banshi1 |
| LaTeX 导出 Word（保留引用） | pandoc-citeproc-export |
| 收集答辩预判问题 | defense-qa-collector |
| 检索 arXiv 论文 | arxiv-search |
| 检索 Semantic Scholar | semantic-scholar |
| 查询 OpenAlex 数据库 | openalex-database |
| 管理引用格式 | citation-management |
| 记录今日工作 | daily-journal |
| 查看今日任务看板 | task-dashboard |
| PARA 方法整理笔记 | para-second-brain |
| 查询 NotebookLM 知识库 | nb-query |
| 生成播客 | notebooklm |
| 同步文章到知识库 | sync-notebooklm-kb |
| 调用 Gemini CLI | collaborating-with-gemini |
| 调用 Codex CLI | collaborating-with-codex |
| 调用 Kimi CLI | collaborating-with-kimi |
| 统一调用外部 AI | collaborating-hub |
| 拆分任务并并发分派 | task-dispatcher |
| 门禁循环自动修复 | gate-loop-orchestrator |
| 系统化调试 | systematic-debugging |
| 生成 Mermaid 图 | mermaid-diagrams |
| 科学可视化图表 | scientific-visualization |
| 备份/恢复技能 | skill-snapshot |
| 复盘技能使用情况 | skill-retrospective |
| 编写新 Skill | skill-authoring |
| 审计/改进 CLAUDE.md | claude-md-management |
| 自动化浏览器操作 | agent-browser |
| 获取今日 RSS 新闻 | rss-daily-digest |
| 重命名 PDF 文件 | rename-pdf |
| 创建 Obsidian Canvas | json-canvas |
| 编辑 Obsidian Bases | obsidian-bases |
| 优化简历通过 ATS | resume-ats-optimizer |
| 生成 PRD 文档 | product-requirements |
| 头脑风暴 | brainstorming |
| 检查 skill/plugin 更新 | skill-catalog (`/skills check`) |

---

## 检查 GitHub 更新

当触发 `/skills check` 或「检查技能更新」时，执行脚本：

```bash
bash ~/.claude/skills/skill-catalog/scripts/check-updates.sh
```

### 脚本功能

| 功能 | 说明 |
|------|------|
| 已安装 Plugins | 读取 `~/.claude/plugins/installed_plugins.json`，显示版本和 commit |
| Marketplaces 状态 | 读取 `~/.claude/plugins/known_marketplaces.json`，查询 GitHub API |
| 版本对比 | 对比本地 commit 与远程最新 commit |
| 更新建议 | 列出需要更新的 plugin 及命令 |

### 输出示例

```
=== GitHub Skill/Plugin 更新检查 ===

【已安装 Plugins】

Plugin                              本地版本     安装日期     Commit
----------------------------------- ------------ ------------ --------
superpowers@superpowers-marketplace 4.0.3        2026-01-10   b9e16498
code-simplifier@claude-plugins-off  1.0.0        2026-01-10   N/A

【Marketplaces 远程状态】

Marketplace               GitHub 仓库                         最新 Commit 更新日期     说明
------------------------- ----------------------------------- ---------- ------------ --------------------
claude-plugins-official   anthropics/claude-plugins-official  96276205   2026-01-15   Add plugin directory...
superpowers-marketplace   obra/superpowers-marketplace        d466ee35   2025-12-27   Update superpowers t...

【更新建议】

  所有已安装 plugins 均为最新版本

=== 检查完成 ===
```

### 手动更新命令

```bash
/plugins update superpowers@superpowers-marketplace
/plugins update code-simplifier@claude-plugins-official
```

### 代理配置

脚本自动检测 `https_proxy` 环境变量。如需代理：

```bash
export https_proxy=http://127.0.0.1:7897
bash ~/.claude/skills/skill-catalog/scripts/check-updates.sh
```

---

## 维护说明

本目录由 `skill-catalog` Skill 维护。当新增或修改 Skill 时，请同步更新：

1. 本 Skill（`~/.claude/skills/skill-catalog/skill.md`）
2. 远端 README（`~/.claude/skill-snapshots/README.md`）
3. 执行快照：`/skill-snapshot save skill-catalog`
