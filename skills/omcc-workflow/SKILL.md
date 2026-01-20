---
name: omcc-workflow
description: |
  OMCC (Coder-Codex-Gemini) collaboration for code and document tasks.
  Use when: writing/modifying code, editing documents, implementing features, fixing bugs, refactoring, or code review.
  协调 Coder 执行代码/文档改动，Codex 审核代码质量。
---

# OMCC 协作流程

## 角色分工

- **Claude**：架构师 + 验收者 + 最终决策者 + 协调者
- **Coder**：执行者（代码/文档改动）
- **Codex**：审核者 + 高级代码顾问
- **Gemini**：高阶顾问（架构设计、第二意见）→ 详见 `/gemini-collaboration`
- **Frontend**：**前端/UI 专家**（界面设计、样式、动效）
- **Librarian**：网络研究专家（文档查询 + 网络搜索 + 代码搜索）
- **Looker**：多模态分析专家（PDF/图片/图表分析）

## 任务拆分原则（分发给 Coder）

> ⚠️ **一次调用，一个目标**。禁止向 Coder 堆砌多个不相关需求。

- **精准 Prompt**：目标明确、上下文充分、验收标准清晰
- **按模块拆分**：相关改动可合并，独立模块分开
- **阶段性 Review**：每模块 Claude 验收，里程碑后 Codex 审核

## 🎯 如何给 Coder 编写有效的任务提示词

> **核心原则**：Coder 是一位能力有限但勤奋的同事——他从未见过你的代码库，但会严格按照你的指令执行。**任务失败的主要原因是规格不足（under-specification），而非模型能力不足。**

### 1. "坐在你旁边的同事"测试

把 Coder 想象成一个刚入职、从未见过项目代码的初级开发者：
- ❌ 他不知道项目的文件结构和约定
- ❌ 他不了解已有的工具函数和组件
- ❌ 他不清楚潜在的业务约束
- ✅ 但他会严格按照你的指令执行

**因此你需要**：提供完整的上下文、明确的步骤、清晰的交付标准。

### 2. 给方向，不是问问题

| ❌ 模糊的问题 | ✅ 明确的方向 |
|--------------|--------------|
| "为什么返回按钮不工作？" | "在 settings 页面，返回按钮点击后没有导航。请定位 bug，修复它，并验证修复有效。" |
| "加个暗黑模式" | "在 settings 页面添加暗黑模式切换。用户偏好存储在 localStorage 的 `user-prefs` 中。参考 `src/components/Toggle.tsx` 的样式。" |
| "写个用户通知的 API" | "创建用户通知 API 端点。参考 `src/api/messages.ts` 的模式。完成后运行 `npm test` 确保测试通过。" |

### 3. 详细任务提示词模板

```markdown
**任务目标**：[一句话说明要完成什么]

**背景上下文**：
- 项目使用 [框架/技术栈]
- 相关文件在 [目录路径]
- 参考已有实现 [文件路径]

**具体步骤**：
1. [第一步做什么]
2. [第二步做什么]
3. [继续列出所有步骤]

**约束条件**：
- [必须遵守的规则，如编码规范]
- [需要保持兼容的接口]
- [不要修改的文件]

**潜在陷阱**（重要！）：
- [你知道的可能出问题的地方]
- [容易被忽略的边界情况]
- [项目特有的约束]

**交付标准**（Definition of Done）：
- [ ] [具体的验收条件 1]
- [ ] [具体的验收条件 2]
- [ ] 运行 [测试命令] 确保通过

**自检步骤**（Feedback Loop）：
- 完成后运行 [命令] 验证
- 检查 [文件] 确认改动正确
```

### 4. 实际案例对比

**❌ 糟糕的 Prompt**：
```
修复登录 bug
```

**✅ 优秀的 Prompt**：
```markdown
**任务目标**：修复登录功能的 token 刷新问题

**背景上下文**：
- 项目使用 JWT 认证，token 存储在 localStorage
- 认证相关代码在 `src/auth/` 目录
- 参考 `src/auth/refresh.ts` 的刷新逻辑

**问题描述**：
用户报告登录后约 1 小时会被踢出登录。经分析，问题是 token 过期后没有自动刷新。

**具体步骤**：
1. 在 `src/auth/interceptor.ts` 添加 401 响应拦截
2. 检测到 401 时调用 `refreshToken()` 函数
3. 刷新成功后重试原请求
4. 刷新失败时重定向到登录页

**约束条件**：
- 不要修改 `src/auth/login.ts` 的接口签名
- 保持与现有 axios 实例的兼容性

**潜在陷阱**：
- 刷新 token 请求本身也可能返回 401，需要避免无限循环
- 并发请求时可能同时触发多次刷新，需要加锁

**交付标准**：
- [ ] 401 响应能正确触发 token 刷新
- [ ] 刷新成功后原请求能正常重试
- [ ] 刷新失败时用户被正确引导到登录页
- [ ] 运行 `npm test -- --grep "auth"` 测试通过

**自检步骤**：
- 运行 `npm run lint` 确保代码规范
- 检查 Network 面板确认刷新逻辑正常触发
```

### 5. 常见错误

| 错误 | 为什么是问题 | 如何改进 |
|------|-------------|----------|
| 缺少文件路径 | Coder 不知道改哪个文件 | 明确指定目标文件 |
| 没有参考示例 | Coder 不知道项目风格 | 提供类似功能的参考文件 |
| 缺少约束条件 | 可能破坏已有功能 | 说明不要修改的部分 |
| 没有交付标准 | 无法判断是否完成 | 给出可验证的检查点 |
| 忽略潜在陷阱 | 踩到你已知的坑 | 提前告知风险点 |

## 核心流程

### 0. 网络研究：Librarian 查询外部资料（可选）

任务开始前，如果需要查询外部文档或最新信息：
- **调用 Librarian** 查询官方文档、网络搜索、GitHub 代码
- 获取最佳实践、解决方案、外部代码示例
- 将研究结果作为上下文传递给 Coder

```
Librarian(PROMPT="React useEffect 的最佳实践", cd=".")
→ 返回官方文档链接和代码示例
→ 将结果作为上下文传给 Coder
```

**注意**：本地代码搜索请使用 Claude 的 **Explore 代理**

### 1. 执行：Coder 处理所有改动

所有代码、文档等内容改动任务，**直接委托 Coder 执行**。

调用前（复杂任务推荐）：
- **调用 Librarian** 查询外部文档和最佳实践
- 在 PROMPT 中列出修改清单
- **复杂问题可先与 Codex 沟通**：架构设计或复杂方案可先咨询后再委托 Coder 执行

### 2. 验收：Claude 快速检查

Coder 执行完毕后，Claude 快速读取验收：
- **无误** → 继续下一任务
- **有误** → Claude 自行修复

### 3. 审核：Codex 阶段性 Review

阶段性开发完成后，调用 Codex review：
- 检查代码质量、潜在 Bug
- 结论：✅ 通过 / ⚠️ 优化 / ❌ 修改

## 工具参考

| 工具 | 用途 | sandbox | 模型 | 重试 |
|------|------|---------|------|------|
| Coder | 执行改动 | workspace-write | 可配置 | 默认不重试 |
| Codex | 代码审核 | read-only | OpenAI Codex | 默认 1 次 |
| Gemini | 顾问/执行 | workspace-write (yolo) | gemini-3-pro | 默认 1 次 |
| **Frontend** | **前端/UI** | workspace-write | gemini-3-pro | 默认 1 次 |
| Librarian | 网络研究 | read-only | gemini-3-flash | 默认 1 次 |
| Looker | 多模态分析 | read-only | gemini-3-flash | 默认 1 次 |

### Librarian 网络研究能力

Librarian 通过 Gemini CLI 配置的 MCP 提供网络研究能力：

| MCP | 功能 | 示例场景 |
|-----|------|----------|
| **context7** | 官方文档查询 | "React useEffect 最佳实践" |
| **exa** | 网络搜索 | "TypeScript 5.5 新特性" |
| **Playwright** | 浏览器自动化 | "抓取需要 JS 渲染的页面" |
| **grep** | 代码搜索 (grep.app) | "TanStack Query 的 useQuery 实现" |
| **firecrawl** | 网页抓取 | "深入阅读某篇技术文章" |

| 请求类型 | 触发词 | 示例 |
|----------|--------|------|
| **TYPE A** | "如何使用...", "最佳实践..." | 概念/用法问题 |
| **TYPE B** | "X 是如何实现的" | 外部源码查找 |
| **TYPE C** | "为什么报错...", "怎么解决..." | 问题诊断 |
| **TYPE D** | 复杂/模糊请求 | 综合研究 |

**注意**：本地代码搜索请使用 Claude 的 **Explore 代理**

### Looker 多模态分析

| 文件类型 | 分析能力 |
|----------|----------|
| **PDF** | 提取文本、表格、结构 |
| **图片** | 描述内容、识别 UI 元素 |
| **图表** | 解释数据趋势和关系 |
| **架构图** | 解释组件关系和数据流 |
| **截图** | 识别错误信息、UI 状态 |

> 💡 **Gemini 详细指南**：如需了解 Gemini 的具体调用方式和触发场景，请执行 `/gemini-collaboration` 技能。

### 前端/UI 任务路由

**前端/UI 任务应使用 Frontend 代理！**

| 任务类型 | 首选代理 |
|----------|----------|
| 界面布局/组件设计 | **Frontend** |
| 样式/动效实现 | **Frontend** |
| UI 审查/改进 | **Frontend** |
| 代码实现（设计完成后） | Coder |
| 代码审查 | Codex |
| 架构设计/第二意见 | Gemini |

> 💡 **Frontend 详细指南**：执行 `/frontend` 技能获取完整的前端开发指南。

**会话复用**：保存 `SESSION_ID` 保持上下文。

## 独立决策

Coder/Codex/Gemini 的意见仅供参考。你（Claude）是最终决策者，需批判性思考，做出最优决策。

详细参数：[coder-guide.md](coder-guide.md) | [codex-guide.md](codex-guide.md)
