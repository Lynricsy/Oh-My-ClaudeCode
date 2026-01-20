# 前端/UI 开发指南

> **注意**：前端/UI 任务现在应使用专门的 `frontend` 工具！
>
> 本文档保留作为设计参考，实际开发请使用 `/frontend` skill。

## 设计流程参考

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

## 支持的技术栈

- HTML + Tailwind（默认）
- React / Next.js / shadcn/ui
- Vue / Nuxt.js / Nuxt UI / Svelte
- SwiftUI / React Native / Flutter

---

## 使用 Frontend 代理

前端/UI 任务请直接使用 `frontend` 工具：

```
mcp__omcc__frontend(
  PROMPT="创建一个登录页面，风格：玻璃拟态，技术栈：React + Tailwind",
  cd="/path/to/project"
)
```

或执行 `/frontend` skill 获取详细指南。

