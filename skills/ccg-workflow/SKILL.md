---
name: ccg-workflow
description: |
  CCG (Coder-Codex-Gemini) collaboration for code and document tasks.
  Use when: writing/modifying code, editing documents, implementing features, fixing bugs, refactoring, or code review.
  协调 Coder 执行代码/文档改动，Codex 审核代码质量。
---

# CCG 协作流程

## 角色分工

- **Claude**：架构师 + 验收者 + 最终决策者 + 协调者
- **Coder**：执行者（代码/文档改动）
- **Codex**：审核者 + 高级代码顾问
- **Gemini**：高阶顾问（按需） → 详见 `/gemini-collaboration`
- **Librarian**：深度研究专家（代码搜索 + 网络研究 + 文档查询）
- **Looker**：多模态分析专家（PDF/图片/图表分析）

## 任务拆分原则（分发给 Coder）

> ⚠️ **一次调用，一个目标**。禁止向 Coder 堆砌多个不相关需求。

- **精准 Prompt**：目标明确、上下文充分、验收标准清晰
- **按模块拆分**：相关改动可合并，独立模块分开
- **阶段性 Review**：每模块 Claude 验收，里程碑后 Codex 审核

## 核心流程

### 0. 探索：Librarian 搜索代码（可选）

任务开始前，如果需要了解代码库结构：
- **调用 Librarian** 搜索相关代码位置
- 获取文件路径、函数定义、依赖关系
- 将搜索结果作为上下文传递给 Coder

```
Librarian(PROMPT="找到用户认证相关的代码", cd=".")
→ 返回文件列表和代码解释
→ 将结果作为上下文传给 Coder
```

### 1. 执行：Coder 处理所有改动

所有代码、文档等内容改动任务，**直接委托 Coder 执行**。

调用前（复杂任务推荐）：
- **调用 Librarian 搜索**相关代码位置
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
| Librarian | 深度研究 | read-only | gemini-3-flash | 默认 1 次 |
| Looker | 多模态分析 | read-only | gemini-3-flash | 默认 1 次 |

### Librarian 深度研究能力

Librarian 通过 Gemini CLI 配置的 MCP 提供全方位研究能力：

| MCP | 功能 | 示例场景 |
|-----|------|----------|
| **context7** | 官方文档查询 | "React useEffect 最佳实践" |
| **websearch** | Exa 网络搜索 | "最新的 TypeScript 5.5 特性" |
| **github** | GitHub 代码搜索 | "TanStack Query 的 useQuery 实现" |
| **firecrawl** | 网页抓取 | "深入阅读某篇技术文章" |

| 请求类型 | 触发词 | 示例 |
|----------|--------|------|
| **TYPE A** | "如何使用...", "最佳实践..." | 概念问题 |
| **TYPE B** | "X 在哪实现", "源码位置" | 实现查找 |
| **TYPE C** | "为什么报错...", "怎么解决..." | 问题诊断 |
| **TYPE D** | 复杂/模糊请求 | 综合研究 |

### Looker 多模态分析

| 文件类型 | 分析能力 |
|----------|----------|
| **PDF** | 提取文本、表格、结构 |
| **图片** | 描述内容、识别 UI 元素 |
| **图表** | 解释数据趋势和关系 |
| **架构图** | 解释组件关系和数据流 |
| **截图** | 识别错误信息、UI 状态 |

> 💡 **Gemini 详细指南**：如需了解 Gemini 的具体调用方式和触发场景，请执行 `/gemini-collaboration` 技能。

**会话复用**：保存 `SESSION_ID` 保持上下文。

## 独立决策

Coder/Codex/Gemini 的意见仅供参考。你（Claude）是最终决策者，需批判性思考，做出最优决策。

详细参数：[coder-guide.md](coder-guide.md) | [codex-guide.md](codex-guide.md)
