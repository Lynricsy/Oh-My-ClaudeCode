# 使用案例

> 💡 **提示**：以下案例展示了如何给 Coder 编写详细的任务提示词。注意观察「✅ 优秀示例」与「❌ 简陋示例」的区别。

---

## 案例 1：批量代码生成

**场景**：用户要求生成多个 API 接口

**流程**：
1. Claude 拆解需求，明确接口列表
2. 调用 Coder 批量生成代码
3. 确认结果，调用 Reviewer review
4. 根据 review 结果迭代

### ❌ 简陋示例（容易失败）

```
PROMPT: 请生成以下 REST API 接口：
- GET /users - 获取用户列表
- POST /users - 创建用户
- GET /users/{id} - 获取单个用户

cd: /project/src
```

### ✅ 优秀示例（推荐）

```markdown
PROMPT: |
  **任务目标**：创建用户管理的 REST API 接口

  **背景上下文**：
  - 项目使用 Express.js + TypeScript
  - 现有路由文件在 `src/routes/` 目录
  - 参考已有的 `src/routes/products.ts` 实现风格
  - 数据库操作使用 Prisma ORM

  **具体步骤**：
  1. 创建 `src/routes/users.ts` 路由文件
  2. 实现以下端点：
     - GET /users - 获取用户列表（支持分页）
     - POST /users - 创建用户（验证必填字段）
     - GET /users/:id - 获取单个用户
  3. 在 `src/routes/index.ts` 中注册路由

  **约束条件**：
  - 遵循项目现有的错误处理模式（参考 `src/middleware/errorHandler.ts`）
  - 使用 zod 进行输入验证
  - 不要修改 `src/app.ts` 主文件

  **潜在陷阱**：
  - 记得处理用户不存在的 404 情况
  - POST 请求需要验证 email 格式
  - 分页参数需要有默认值

  **交付标准**：
  - [ ] 三个端点都能正常响应
  - [ ] 输入验证能拦截非法数据
  - [ ] 运行 `npm run lint` 无错误

  **自检步骤**：
  - 运行 `npm run build` 确保编译通过
  - 运行 `npm test -- --grep "users"` 测试通过

cd: /project/src
SESSION_ID: ""  # 新会话
```

---

## 案例 2：Bug 修复

**场景**：用户报告登录功能异常，约 1 小时后会被踢出登录

**流程**：
1. Claude 分析问题，定位原因（token 过期后没有自动刷新）
2. 调用 Coder 修复代码
3. 调用 Reviewer review 修复质量

### ❌ 简陋示例（容易失败）

```
PROMPT: 修复登录功能的 token 过期问题
目标文件：src/auth/login.py
问题：token 刷新逻辑缺失

cd: /project
```

### ✅ 优秀示例（推荐）

```markdown
PROMPT: |
  **任务目标**：修复登录功能的 token 自动刷新问题

  **背景上下文**：
  - 项目使用 JWT 认证，access_token 有效期 1 小时
  - refresh_token 存储在 httpOnly cookie 中
  - 认证相关代码在 `src/auth/` 目录
  - API 请求使用 axios，实例在 `src/lib/axios.ts`

  **问题描述**：
  用户登录后约 1 小时会被踢出登录。分析发现是 access_token 过期后没有自动刷新，直接返回 401 给用户。

  **具体步骤**：
  1. 在 `src/lib/axios.ts` 添加 response interceptor
  2. 检测到 401 响应时，调用 `POST /auth/refresh` 刷新 token
  3. 刷新成功后，更新 localStorage 中的 access_token
  4. 使用新 token 重试原请求
  5. 刷新失败时（refresh_token 也过期），清除登录状态并重定向到 /login

  **约束条件**：
  - 不要修改 `src/auth/login.ts` 的接口签名
  - 保持与现有 axios 实例的兼容性
  - 刷新接口已存在：`POST /auth/refresh`

  **潜在陷阱**（重要！）：
  - ⚠️ 刷新 token 的请求本身也可能返回 401，需要避免无限循环！
  - ⚠️ 并发请求时可能同时触发多次刷新，需要加锁机制
  - 刷新期间的其他请求应该等待，而不是各自刷新

  **交付标准**：
  - [ ] access_token 过期后能自动刷新
  - [ ] 刷新成功后原请求能正常重试
  - [ ] 刷新失败时用户被正确引导到登录页
  - [ ] 并发请求时只触发一次刷新
  - [ ] 不会出现无限循环刷新

  **自检步骤**：
  - 运行 `npm run lint` 确保代码规范
  - 运行 `npm test -- --grep "auth"` 测试通过

cd: /project
SESSION_ID: "abc-123"  # 复用会话
```

---

## 案例 3：代码审核

**场景**：开发完成后请求 review

### ❌ 简陋示例

```
PROMPT: 请 review src/api/ 目录下的改动

cd: /project
```

### ✅ 优秀示例

```markdown
PROMPT: |
  **审核目标**：review 用户管理 API 的实现

  **改动范围**：
  - `src/routes/users.ts` - 新增用户管理路由
  - `src/services/userService.ts` - 用户服务层
  - `src/validators/userValidator.ts` - 输入验证

  **改动目的**：
  新增用户管理功能，支持用户的增删改查。

  **审核重点**：
  1. 安全性：是否有 SQL 注入、XSS 等风险
  2. 性能：数据库查询是否有 N+1 问题
  3. 错误处理：异常是否被正确捕获和处理
  4. 代码规范：是否符合项目编码规范

  **已知的担忧点**：
  - 用户删除是否需要软删除？
  - 分页性能在大数据量下是否有问题？

  请给出 ✅ 通过 / ⚠️ 建议优化 / ❌ 需要修改 的结论。

cd: /project
sandbox: read-only
SESSION_ID: "abc-123"  # 复用上一步 Coder 的会话
```

**注意**：若之前调用过 Coder 生成代码，建议复用同一 SESSION_ID，让 Reviewer 了解完整上下文。

---

## 案例 4：新功能开发（完整流程）

**场景**：为电商应用添加购物车功能

### 第 1 步：研究（可选，使用 Librarian）

```markdown
PROMPT: |
  查询以下内容：
  1. React 购物车状态管理的最佳实践
  2. 乐观更新（optimistic update）的实现方式
  3. 购物车数量动画的常见方案

cd: /project
```

### 第 2 步：实现（使用 Coder）

```markdown
PROMPT: |
  **任务目标**：实现购物车功能的前端部分

  **背景上下文**：
  - 项目使用 React 18 + TypeScript + Zustand
  - UI 组件库使用 Shadcn/ui
  - 购物车 API 已由后端实现：
    - GET /cart - 获取购物车
    - POST /cart/items - 添加商品
    - DELETE /cart/items/:id - 删除商品

  **具体步骤**：
  1. 创建 `src/stores/cartStore.ts` - Zustand store
  2. 创建 `src/components/Cart/` 组件目录：
     - CartIcon.tsx - 顶栏购物车图标（显示数量）
     - CartDrawer.tsx - 购物车抽屉
     - CartItem.tsx - 单个商品项
  3. 在 `src/components/ProductCard.tsx` 添加"加入购物车"按钮
  4. 实现乐观更新：点击后立即更新 UI，API 失败时回滚

  **约束条件**：
  - 使用 Shadcn/ui 的 Sheet 组件实现抽屉
  - 保持与现有主题色的一致性
  - 不要修改 `src/layouts/` 目录

  **潜在陷阱**：
  - 添加商品时要检查是否已存在，存在则增加数量
  - 删除动画期间要禁用删除按钮，防止重复点击
  - 购物车数量更新需要有动画过渡

  **交付标准**：
  - [ ] 购物车图标显示正确数量
  - [ ] 添加/删除商品后 UI 立即响应
  - [ ] API 失败时能正确回滚并提示用户
  - [ ] 运行 `npm run build` 编译通过

  **自检步骤**：
  - 运行 `npm run lint` 检查代码规范
  - 在浏览器中手动测试添加/删除流程

cd: /project
SESSION_ID: ""
```

### 第 3 步：审核（使用 Reviewer）

```markdown
PROMPT: |
  **审核目标**：review 购物车功能的实现

  **改动范围**：
  - `src/stores/cartStore.ts`
  - `src/components/Cart/` 目录
  - `src/components/ProductCard.tsx`

  **审核重点**：
  1. 状态管理是否合理，有无内存泄漏风险
  2. 乐观更新的回滚逻辑是否正确
  3. 组件是否有不必要的重渲染
  4. 错误边界是否完善

cd: /project
sandbox: read-only
SESSION_ID: "cart-session-123"
```
