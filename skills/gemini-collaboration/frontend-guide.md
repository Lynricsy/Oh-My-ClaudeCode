# 前端/UI 开发指南

> Gemini 是前端/UI 任务的首选代理

## 为什么前端任务应使用 Gemini？

| 优势 | 说明 |
|------|------|
| **设计师视角** | 关注间距、色彩和谐、微交互，不只是"能用" |
| **UI/UX Pro Max** | 集成 57 种 UI 风格、95 种调色板、56 种字体搭配 |
| **多框架支持** | React/Next.js/Vue/Nuxt/Svelte/SwiftUI/Flutter |
| **审美指导** | 内置设计系统、排版规范、动效建议 |

---

## 设计流程

开始编码前，先确定 **审美方向**：

### 1. 目的
- 这个界面解决什么问题？
- 谁是目标用户？

### 2. 风格
选择一个明确的方向：
- 极简主义 (Minimalism)
- 玻璃拟态 (Glassmorphism)
- 粘土拟态 (Claymorphism)
- 新拟态 (Neumorphism)
- 便当盒布局 (Bento Grid)
- 野蛮主义 (Brutalism)
- 复古未来主义 (Retro-futuristic)
- 有机自然 (Organic/Natural)
- 奢华精致 (Luxury/Refined)
- 俏皮玩具 (Playful/Toy-like)

### 3. 约束
- 技术栈要求（框架、性能、可访问性）
- 现有设计系统

### 4. 差异化
- 用户会记住的 **一件事** 是什么？

---

## 审美指南

### Typography 排版

**新项目**：选择独特字体，避免通用默认值（Arial、系统字体）
**现有项目**：遵循项目设计系统和字体选择

```
推荐组合：
- 标题: Inter / Poppins / Satoshi
- 正文: Inter / Plus Jakarta Sans
- 代码: JetBrains Mono / Fira Code
```

### Color 色彩

**新项目**：承诺统一的调色板，使用 CSS 变量。主色 + 锐利强调 > 平均分配
**现有项目**：使用现有设计 token 和颜色变量

```
行业调色板示例：
- SaaS: 蓝紫色系，专业可信
- 电商: 暖色系，促进转化
- 医疗: 蓝绿色系，冷静可靠
- 金融: 深蓝/金色，稳重奢华
```

### Motion 动效

关注高影响力时刻：
- 页面加载时的交错动画 (animation-delay)
- 滚动触发效果
- 悬停状态惊喜

优先使用 CSS-only，React 项目可用 Motion 库。

### Spatial 空间构成

- 意外的布局
- 不对称
- 重叠
- 对角线流动
- 打破网格的元素
- 充裕的负空间或受控的密度

### Visual Details 视觉细节

创建氛围和深度：
- 渐变网格
- 噪点纹理
- 几何图案
- 分层透明
- 戏剧性阴影
- 装饰边框
- 自定义光标
- 颗粒叠加

---

## UI/UX Pro Max Skill

Gemini 可以集成 [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) 技能：

### 内置资源

| 资源 | 数量 |
|------|------|
| UI 风格 | 57 种 |
| 调色板 | 95 种（按行业分类） |
| 字体搭配 | 56 种 |
| 图表类型 | 24 种 |
| UX 指南 | 98 条 |
| 技术栈 | 11 种 |

### 支持的技术栈

- HTML + Tailwind（默认）
- React / Next.js / shadcn/ui
- Vue / Nuxt.js / Nuxt UI / Svelte
- SwiftUI / React Native / Flutter

### 安装到 Gemini CLI

```bash
# 使用 CLI 安装
npm install -g uipro-cli
uipro init --ai gemini

# 或手动复制
# .gemini/skills/ui-ux-pro-max/
# .shared/ui-ux-pro-max/
```

---

## Prompt 模板

### 新项目 UI

```
使用 Gemini 创建 [产品类型] 的 [页面类型]：

**产品**: [描述]
**风格偏好**: [极简/玻璃拟态/便当盒/...]
**技术栈**: [React/Next.js/Vue/...]
**特殊要求**: [暗色模式/响应式/动效/...]

请先分析设计方向，然后生成代码。
```

### UI 审查

```
使用 Gemini 审查这个 UI 设计/代码：

**文件**: [路径]
**关注点**: [间距/色彩/排版/动效/可访问性]

请提供具体改进建议和示例代码。
```

### UI 修复

```
使用 Gemini 改进这个界面的 [问题]：

**当前问题**: [描述]
**期望效果**: [描述]
**限制条件**: [不能改动的部分]
```

---

## 执行原则

### 工作原则

1. **完成所要求的** — 执行准确任务，不扩大范围
2. **让它更好** — 确保改动后项目处于工作状态
3. **先研究再行动** — 查看现有模式、约定和提交历史
4. **无缝融入** — 匹配现有代码风格
5. **透明沟通** — 宣布每一步，解释推理

### 反模式（新项目避免）

- 有独特选项时使用通用字体
- 可预测的布局和组件模式
- 缺乏上下文特色的千篇一律设计

---

## 范围边界

如果任务涉及：
- 代码实现（设计完成后） → 使用 Coder
- 外部研究 → 使用 Librarian
- 架构决策 → 先咨询 Codex/Gemini

Frontend 专注于 **UI/UX 实现**，其他部分由适当的代理处理。
