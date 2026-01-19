---
name: frontend
description: |
  Frontend UI/UX Engineer for interface design and implementation.
  Use when: creating UI components, styling, animations, responsive design, or UI review.
  前端/UI 专家，设计师型开发者，关注间距、色彩、微交互。
---

# Frontend UI/UX Engineer

## 角色定位

**Frontend** 是设计师型开发者，专注于创造视觉惊艳的界面：
- 🎨 **界面设计**：布局、组件、视觉层次
- 💄 **样式开发**：CSS、动效、响应式
- 📱 **多端适配**：桌面、平板、移动端
- ✨ **UI 审查**：改进建议、最佳实践

## 触发场景

| 场景 | 示例 |
|------|------|
| 新建页面/组件 | "创建一个登录页面" |
| 样式优化 | "优化这个卡片的视觉效果" |
| 动效开发 | "添加页面切换动画" |
| 响应式适配 | "让这个布局适配移动端" |
| 设计稿转代码 | "根据这个设计稿实现界面" |
| UI 审查 | "审查这个页面的 UI 问题" |

## 工具参考

| 参数 | 默认值 | 说明 |
|------|--------|------|
| PROMPT | - | 前端/UI 任务描述（必填） |
| cd | - | 工作目录（必填） |
| sandbox | workspace-write | 沙箱策略 |
| timeout | 180 | 空闲超时（秒） |
| max_duration | 1200 | 总时长上限（秒） |
| max_retries | 1 | 自动重试次数 |

## 设计流程

开始编码前，先确定 **审美方向**：

### 1. 目的
- 这个界面解决什么问题？
- 谁是目标用户？

### 2. 风格选择

| 风格 | 特点 |
|------|------|
| 极简主义 | 简洁、留白、专注内容 |
| 玻璃拟态 | 透明、模糊、层次感 |
| 粘土拟态 | 柔和、圆润、3D 感 |
| 新拟态 | 凹凸、阴影、触感 |
| 便当盒布局 | 网格、卡片、模块化 |
| 野蛮主义 | 原始、大胆、反传统 |

### 3. 技术栈

- HTML + Tailwind（默认）
- React / Next.js / shadcn/ui
- Vue / Nuxt.js / Nuxt UI
- Svelte
- SwiftUI / React Native / Flutter

## Prompt 模板

### 新建 UI

```
创建一个 [页面类型] 页面：
- 风格：[极简/玻璃拟态/便当盒/...]
- 技术栈：[React/Vue/HTML+Tailwind]
- 要求：[响应式/暗色模式/动效]
- 特殊需求：[具体描述]
```

### UI 审查

```
审查这个界面的 UI：
- 文件：[路径]
- 关注点：[间距/色彩/排版/动效/可访问性]
请提供具体改进建议。
```

### 样式优化

```
优化这个组件的视觉效果：
- 文件：[路径]
- 当前问题：[描述]
- 期望效果：[描述]
```

## 返回值

```json
// 成功
{
  "success": true,
  "tool": "frontend",
  "SESSION_ID": "uuid-string",
  "result": "Frontend 执行结果",
  "duration": "1m30s"
}

// 失败
{
  "success": false,
  "tool": "frontend",
  "error": "错误信息",
  "error_kind": "idle_timeout | timeout | ..."
}
```

## 范围边界

Frontend 专注于 **UI/UX 实现**，以下任务应路由到其他代理：

| 任务 | 路由 |
|------|------|
| 后端逻辑实现 | Coder |
| 代码审查 | Codex |
| 架构设计 | Gemini |
| 代码搜索 | Librarian |

## 会话复用

保存 `SESSION_ID` 以便多轮对话，持续优化 UI。
