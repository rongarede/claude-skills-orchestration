# 验证命令参考

| 任务类型 | 验证命令模板 |
|----------|--------------|
| TypeScript 代码 | `tsc --noEmit` |
| Rust 代码 | `cargo check` / `cargo build` |
| 单元测试 | `npm test -- --grep '{pattern}'` / `pytest -k {pattern}` |
| API 端点 | `curl -s {url} \| jq .{field}` |
| 文件存在 | `test -f {path} && echo "OK"` |
| 代码包含 | `grep -q '{pattern}' {file} && echo "OK"` |
| Lint 通过 | `eslint {file} --quiet` / `cargo clippy` |
| Build 通过 | `npm run build` / `cargo build --release` |

## 验证规范

```yaml
验证:
  命令: "npm test -- --grep 'login'"
  预期: "exit_code == 0 && stdout contains 'passing'"
  超时: 60s
  重试: 2
```

## 回退策略矩阵

| 失败类型 | 策略 | 行动 |
|----------|------|------|
| 编译错误 | Codex 重试 | 附加错误信息，让 Codex 修复 |
| 测试失败 | Codex 重试 | 附加失败用例，让 Codex 修复 |
| 逻辑错误 | Claude 介入 | Claude 分析根因，重新规划 |
| 超时 | 重试 1 次 | 增加超时时间重试 |
| 连续 2 次失败 | Claude 接管 | 停止 Codex，Claude 完全接管 |
