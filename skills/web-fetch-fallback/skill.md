---
name: web-fetch-fallback
description: "WebFetch 失败时的智能备选方案。触发词：/fetch、抓取网页、获取页面内容、WebFetch 失败"
---

# URL 智能抓取路由

当 WebFetch 工具无法访问某些域名时，自动选择最优的备选抓取方式。

## 触发方式

- `/fetch <url>`
- 「帮我抓取这个网页」
- 「WebFetch 失败了，换个方法」
- 当 WebFetch 返回域名限制错误时

## 执行脚本

```bash
bash ~/.claude/skills/web-fetch-fallback/scripts/fetch.sh <url> [method]
```

## 抓取策略

| URL 类型 | 首选方法 | 备选方法 |
|----------|----------|----------|
| GitHub 仓库 | `gh api` 获取 README | curl |
| GitHub 文件 | `gh api` 获取内容 | curl |
| GitHub Issue/PR | `gh issue/pr view` | curl |
| 静态文档站 (*.github.io) | curl + pandoc | agent-browser |
| 博客/文章 | curl + pandoc | agent-browser |
| JS 渲染页面 | agent-browser | - |
| 一般网页 | curl + pandoc | agent-browser |

## 使用示例

### 自动选择（推荐）

```bash
# GitHub 仓库 → 自动用 gh CLI
bash ~/.claude/skills/web-fetch-fallback/scripts/fetch.sh https://github.com/kevinheavey/anchor-bankrun

# 文档站点 → 自动用 curl + pandoc
bash ~/.claude/skills/web-fetch-fallback/scripts/fetch.sh https://kevinheavey.github.io/solana-bankrun/tutorial/

# 博客文章
bash ~/.claude/skills/web-fetch-fallback/scripts/fetch.sh https://www.helius.dev/blog/a-guide-to-testing-solana-programs
```

### 强制指定方法

```bash
# 强制使用 gh CLI
bash ~/.claude/skills/web-fetch-fallback/scripts/fetch.sh https://github.com/user/repo gh

# 强制使用 curl
bash ~/.claude/skills/web-fetch-fallback/scripts/fetch.sh https://example.com curl

# 强制使用 agent-browser（需要 JS 渲染）
bash ~/.claude/skills/web-fetch-fallback/scripts/fetch.sh https://spa-site.com browser
```

## 依赖工具

| 工具 | 用途 | 安装方式 |
|------|------|----------|
| gh | GitHub 内容抓取 | `brew install gh` |
| curl | HTTP 请求 | 系统自带 |
| pandoc | HTML → 纯文本 | `brew install pandoc` |
| html2text | HTML → 纯文本（备选） | `brew install html2text` |
| lynx | HTML → 纯文本（备选） | `brew install lynx` |
| agent-browser | JS 渲染页面 | 已配置 skill |

## 代理支持

脚本自动读取 `https_proxy` 环境变量：

```bash
export https_proxy=http://127.0.0.1:7897
bash ~/.claude/skills/web-fetch-fallback/scripts/fetch.sh https://example.com
```

## 与其他方案对比

| 方案 | 优势 | 限制 |
|------|------|------|
| WebFetch | 简单快速，AI 直接处理 | 有域名黑名单 |
| **web-fetch-fallback** | 智能路由，无域名限制 | 需要本地工具 |
| agent-browser | 支持 JS 渲染，可交互 | 较慢，需启动浏览器 |
| WebSearch | 搜索摘要，无需原文 | 不返回完整内容 |

## 输出格式

- 成功时输出纯文本内容（Markdown 或 Plain Text）
- 失败时显示错误信息和尝试过的方法
