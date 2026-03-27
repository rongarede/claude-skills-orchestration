---
name: skill-authoring
description: "Skill 编写规范与最佳实践。触发词：/skill-authoring、编写 skill、创建技能"
---

# Skill 编写规范

## 核心原则

| 原则 | 说明 |
|------|------|
| 脚本优先 | 功能实现用脚本（sh/python），非内联代码 |
| 可执行性 | Skill 必须可直接执行 |
| 可测试性 | 每个脚本可独立运行验证 |
| 可维护性 | 脚本与文档分离 |

## 实现优先级

| 优先级 | 方式 | 场景 |
|--------|------|------|
| 1 | Bash (.sh) | 系统操作、API 调用、流程自动化 |
| 2 | Python (.py) | 复杂逻辑、数据处理、第三方库 |
| 3 | 内联代码 | 仅当逻辑极简且不可复用 |

## 目录结构

```
skill-name/
├── skill.md          # 触发词、工作流程、使用说明
├── scripts/          # 脚本目录
│   ├── main.sh       # 主脚本
│   └── helper.py     # 辅助脚本
└── templates/        # 模板文件（可选）
```

## Bash 脚本模板

```bash
#!/bin/bash
# ============================================================
# skill-name: 功能描述
# ============================================================

set -e  # 遇错即停

# ==================== 配置 ====================
CONFIG_VAR="value"

# ==================== 工具函数 ====================
check_dependencies() {
    command -v jq >/dev/null || { echo "需要 jq"; exit 1; }
}

# ==================== 主逻辑 ====================
main() {
    check_dependencies
    # 业务逻辑
}

main "$@"
```

## Python 脚本模板

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill-name: 功能描述"""

import sys
from pathlib import Path

def main():
    pass

if __name__ == "__main__":
    main()
```

## skill.md 模板

```markdown
---
name: skill-name
description: "触发条件。触发词：/xxx、关键词"
---

# Skill 名称

简要说明。

## 触发方式

- `/command`
- 「自然语言触发词」

## 执行

\`\`\`bash
bash ~/.claude/skills/skill-name/scripts/main.sh [args]
\`\`\`

## 功能

| 功能 | 说明 |
|------|------|

## 输出示例

\`\`\`
示例输出
\`\`\`
```

## 决策树：脚本 vs 内联

```
需要实现功能？
    │
    ▼
可用 shell 命令组合？ ─是→ Bash 脚本
    │
   否
    ▼
需要复杂数据处理？ ─是→ Python 脚本
    │
   否
    ▼
内联代码
```

## 注意事项

1. 脚本必须有执行权限：`chmod +x script.sh`
2. 头部必须有 shebang：`#!/bin/bash` 或 `#!/usr/bin/env python3`
3. 脚本开头检查依赖（jq, curl, python 等）
4. 网络脚本支持 `https_proxy` 环境变量
5. 错误处理：`set -e` 或 try-except
6. 结构化输出，便于解析
