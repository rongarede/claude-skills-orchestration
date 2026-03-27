#!/bin/bash
# ============================================================
# web-fetch-fallback: URL 智能抓取路由
# 根据 URL 类型自动选择最优抓取方式
# ============================================================

set -e

# ==================== 配置 ====================
PROXY="${https_proxy:-}"
USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
TIMEOUT=30

# ==================== 颜色输出 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ==================== 依赖检查 ====================
check_tool() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# ==================== URL 类型判断 ====================
get_url_type() {
    local url="$1"

    # GitHub 仓库主页
    if [[ "$url" =~ ^https?://github\.com/[^/]+/[^/]+/?$ ]]; then
        echo "github_repo"
    # GitHub 文件
    elif [[ "$url" =~ ^https?://github\.com/[^/]+/[^/]+/blob/ ]]; then
        echo "github_file"
    # GitHub Issue/PR
    elif [[ "$url" =~ ^https?://github\.com/[^/]+/[^/]+/(issues|pull)/[0-9]+ ]]; then
        echo "github_issue"
    # GitHub API
    elif [[ "$url" =~ ^https?://api\.github\.com/ ]]; then
        echo "github_api"
    # GitHub Pages / 文档站点
    elif [[ "$url" =~ \.github\.io ]]; then
        echo "static_site"
    # 常见文档站点
    elif [[ "$url" =~ (docs\.|documentation|readthedocs|gitbook) ]]; then
        echo "docs_site"
    # 博客/文章
    elif [[ "$url" =~ (blog\.|medium\.com|dev\.to|substack|hashnode) ]]; then
        echo "blog"
    # 一般网页
    else
        echo "general"
    fi
}

# ==================== 抓取方法 ====================

# 方法1: gh CLI (GitHub)
fetch_with_gh() {
    local url="$1"
    local url_type="$2"

    if ! check_tool gh; then
        warn "gh CLI 未安装，跳过"
        return 1
    fi

    case "$url_type" in
        github_repo)
            # 提取 owner/repo
            local repo=$(echo "$url" | sed -E 's|https?://github\.com/([^/]+/[^/]+)/?.*|\1|')
            info "使用 gh CLI 获取仓库 README: $repo"
            gh api "repos/$repo/readme" -q '.content' 2>/dev/null | base64 -d
            return $?
            ;;
        github_file)
            # 提取文件路径
            local repo=$(echo "$url" | sed -E 's|https?://github\.com/([^/]+/[^/]+)/blob/[^/]+/(.*)|\1|')
            local branch=$(echo "$url" | sed -E 's|https?://github\.com/[^/]+/[^/]+/blob/([^/]+)/.*|\1|')
            local path=$(echo "$url" | sed -E 's|https?://github\.com/[^/]+/[^/]+/blob/[^/]+/(.*)|\1|')
            info "使用 gh CLI 获取文件: $repo/$path"
            gh api "repos/$repo/contents/$path?ref=$branch" -q '.content' 2>/dev/null | base64 -d
            return $?
            ;;
        github_issue)
            # 提取 issue/PR 信息
            local repo=$(echo "$url" | sed -E 's|https?://github\.com/([^/]+/[^/]+)/(issues|pull)/([0-9]+).*|\1|')
            local type=$(echo "$url" | sed -E 's|https?://github\.com/[^/]+/[^/]+/(issues|pull)/([0-9]+).*|\1|')
            local number=$(echo "$url" | sed -E 's|https?://github\.com/[^/]+/[^/]+/(issues|pull)/([0-9]+).*|\2|')

            if [[ "$type" == "pull" ]]; then
                info "使用 gh CLI 获取 PR #$number"
                gh pr view "$number" -R "$repo"
            else
                info "使用 gh CLI 获取 Issue #$number"
                gh issue view "$number" -R "$repo"
            fi
            return $?
            ;;
        *)
            return 1
            ;;
    esac
}

# 方法2: curl + 文本转换
fetch_with_curl() {
    local url="$1"
    local converter=""

    # 选择转换器
    if check_tool pandoc; then
        converter="pandoc -f html -t plain"
    elif check_tool html2text; then
        converter="html2text"
    elif check_tool lynx; then
        converter="lynx -stdin -dump -nolist"
    else
        converter="cat"  # 原始 HTML
        warn "未找到 HTML 转换工具 (pandoc/html2text/lynx)，输出原始 HTML"
    fi

    info "使用 curl 抓取: $url"

    local curl_opts="-sL --max-time $TIMEOUT -A \"$USER_AGENT\""
    if [[ -n "$PROXY" ]]; then
        curl_opts="$curl_opts -x $PROXY"
    fi

    eval "curl $curl_opts \"$url\"" | $converter
    return $?
}

# 方法3: agent-browser
fetch_with_agent_browser() {
    local url="$1"

    if ! check_tool agent-browser; then
        warn "agent-browser 未安装，跳过"
        return 1
    fi

    info "使用 agent-browser 抓取 (支持 JS 渲染): $url"
    agent-browser open "$url" && agent-browser snapshot -c
    return $?
}

# ==================== 主逻辑 ====================
main() {
    local url="$1"
    local method="${2:-auto}"  # auto, gh, curl, browser

    if [[ -z "$url" ]]; then
        echo "用法: fetch.sh <url> [method]"
        echo ""
        echo "方法:"
        echo "  auto     - 自动选择最优方式 (默认)"
        echo "  gh       - 强制使用 gh CLI"
        echo "  curl     - 强制使用 curl"
        echo "  browser  - 强制使用 agent-browser"
        echo ""
        echo "示例:"
        echo "  fetch.sh https://github.com/user/repo"
        echo "  fetch.sh https://example.com/page curl"
        exit 1
    fi

    local url_type=$(get_url_type "$url")
    info "URL 类型: $url_type"

    # 强制指定方法
    if [[ "$method" != "auto" ]]; then
        case "$method" in
            gh) fetch_with_gh "$url" "$url_type" && exit 0 ;;
            curl) fetch_with_curl "$url" && exit 0 ;;
            browser) fetch_with_agent_browser "$url" && exit 0 ;;
            *) error "未知方法: $method"; exit 1 ;;
        esac
        exit 1
    fi

    # 自动选择: 按优先级尝试
    case "$url_type" in
        github_repo|github_file|github_issue)
            # GitHub 优先用 gh CLI
            if fetch_with_gh "$url" "$url_type"; then
                success "抓取完成 (gh CLI)"
                exit 0
            fi
            warn "gh CLI 失败，尝试 curl..."
            ;;
    esac

    # 尝试 curl
    if fetch_with_curl "$url"; then
        success "抓取完成 (curl)"
        exit 0
    fi

    # 最后尝试 agent-browser
    warn "curl 失败，尝试 agent-browser..."
    if fetch_with_agent_browser "$url"; then
        success "抓取完成 (agent-browser)"
        exit 0
    fi

    error "所有方法均失败"
    exit 1
}

main "$@"
