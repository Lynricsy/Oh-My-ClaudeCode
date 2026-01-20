# Reviewer 工具详细规范

## 角色定位

**Reviewer** 是代码审核者 + 任务验收者：
- 🔍 **代码质量审核**：可读性、可维护性、潜在 bug
- ✅ **任务完成度验证**：需求是否完整实现、边界情况是否覆盖
- 🎯 **对齐性检查**：实现是否与原始需求一致
- 🧪 **测试验证**：运行相关单元测试（如 npm test、pytest）

## 重要限制

- Reviewer 可以读取文件和运行测试命令（如 npm test、pytest）
- **严禁修改、创建或删除代码/文档文件**（提示词约束）
- 测试产生的临时文件/缓存可以写入
- 只做检查和验证，不做实际代码改动
- 默认 `sandbox="workspace-write"`（以便运行测试）

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| PROMPT | string | ✅ | 审核任务描述 |
| cd | Path | ✅ | 工作目录 |
| sandbox | string | | 默认 `workspace-write`（以便运行测试） |
| SESSION_ID | string | | 会话 ID |
| return_all_messages | boolean | | 调试时设为 True |
| return_metrics | boolean | | 返回值中包含指标数据，默认 False |
| image | List[Path] | | 附加图片 |
| model | string | | 指定模型 |
| timeout | int | | 空闲超时（秒），默认 300，无输出超过此时间触发 |
| max_duration | int | | 总时长硬上限（秒），默认 7200（2 小时），0 表示无限制 |
| max_retries | int | | 最大重试次数，默认 1（可安全重试） |
| log_metrics | boolean | | 将指标输出到 stderr |

## 返回值

```json
// 成功
{
  "success": true,
  "tool": "reviewer",
  "SESSION_ID": "uuid-string",
  "result": "Reviewer 审核结论"
}

// 失败（结构化错误）
{
  "success": false,
  "tool": "reviewer",
  "error": "错误摘要信息",
  "error_kind": "idle_timeout | timeout | command_not_found | upstream_error | ...",
  "error_detail": {
    "message": "错误简述",
    "exit_code": 1,
    "last_lines": ["最后20行输出..."],
    "json_decode_errors": 0,
    "idle_timeout_s": 300,
    "max_duration_s": 7200,
    "retries": 1
  }
}
```

### error_kind 枚举

| 值 | 说明 |
|----|------|
| `idle_timeout` | 空闲超时（无输出） |
| `timeout` | 总时长超时 |
| `command_not_found` | codex CLI 未安装 |
| `upstream_error` | CLI 返回错误 |
| `json_decode` | JSON 解析失败 |
| `protocol_missing_session` | 未获取 SESSION_ID |
| `empty_result` | 无响应内容 |
| `subprocess_error` | 进程退出码非零 |
| `unexpected_exception` | 未预期异常 |

## Prompt 模板

```
请 review 以下代码改动：

**改动文件**：[文件列表]
**改动目的**：[简要描述]
**原始需求**：[需求描述]

**请检查**：
1. 代码质量（可读性、可维护性）
2. 潜在 Bug 或边界情况
3. 任务完成度（需求是否完整实现）
4. 对齐性（实现是否与需求一致）
5. 运行相关测试命令：[测试命令，如 npm test、pytest]

**请给出明确结论**：
- ✅ 通过：代码质量良好，任务完整完成
- ⚠️ 建议优化：[具体建议]
- ❌ 需要修改：[具体问题]
```

## 使用规范

1. **严格边界**：Reviewer 可运行测试但严禁修改代码文件
2. **必须保存** `SESSION_ID` 以便多轮对话
3. 检查 `success` 字段判断审核是否成功
4. 从 `result` 字段获取审核结论
5. 失败时检查 `error_kind` 了解失败原因

## 重试策略

Reviewer 默认允许 **1 次自动重试**（只读操作无副作用）：
- 超时、网络错误等会自动重试
- `command_not_found` 不会重试（需用户干预）
- 重试采用指数退避（0.5s → 1s → 2s）

## 测试验证示例

```
请 review 用户认证模块的改动：

**改动文件**：
- src/auth/login.ts
- src/auth/token.ts
- tests/auth.test.ts

**改动目的**：添加 token 自动刷新功能

**原始需求**：
- access_token 过期后自动刷新
- 刷新失败时重定向到登录页
- 并发请求时只触发一次刷新

**请检查**：
1. 代码质量和错误处理
2. 是否覆盖了所有边界情况
3. 需求是否完整实现
4. 运行测试：`npm test -- --grep "auth"`

**请给出明确结论**
```
