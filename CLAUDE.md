# Oh-My-ClaudeCode (OMCC)

> Claude + 多代理协作 MCP 服务器

## 项目定位

一个统一的 MCP 服务器，让 Claude (Opus) 作为架构师调度 Coder 执行代码任务、Codex 审核代码质量、Gemini 提供专家咨询，形成自动化的多方协作闭环。

## 核心价值

| 维度 | 价值 |
|------|------|
| **成本优化** | Opus 负责思考（贵但强），Coder 负责执行（量大管饱） |
| **能力互补** | Opus 补足 Coder 创造力短板，Codex 提供独立审核视角，Gemini 提供多元化专家意见 |
| **质量保障** | 双重审核机制（Claude 初审 + Codex 终审） |
| **全自动闭环** | 拆解 → 执行 → 审核 → 重试，无需人工干预 |

## 角色分工

```
Claude (Opus)     →  架构师 + 初审官 + 终审官 + 协调者
Coder (可配置)    →  代码实现者（生成、修改、批量任务）
Codex (OpenAI)    →  独立代码审核者（质量把关）
Gemini (OpenCode) →  多面手专家（架构设计、第二意见）
Frontend (OpenCode) → 前端/UI 专家（界面设计、样式、动效）
Chore (OpenCode)  →  杂务执行者（简单重复任务、批量操作）
Librarian (OpenCode) → 网络研究专家（文档查询 + 网络搜索 + 代码搜索）
Looker (OpenCode) → 多模态分析专家（PDF/图片/图表分析）
```

### Librarian 网络研究能力

Librarian 通过 OpenCode CLI 配置的 MCP 提供网络研究能力：

| MCP | 功能 |
|-----|------|
| **context7** | 官方文档查询（快速获取库/框架文档） |
| **exa** | 主力网络搜索（高质量搜索结果） |
| **Playwright** | 浏览器自动化（headless 模式） |
| **grep** | 代码搜索（grep.app 开源代码搜索） |
| **firecrawl** | 网页抓取（深入阅读网页内容） |

使用场景：
- "React useEffect 的最佳实践" → context7 + exa
- "找到 TanStack Query 的 useQuery 实现" → grep.app
- "为什么 Zod 报这个错误" → exa + grep.app
- "抓取某网页的完整内容" → Playwright / firecrawl

**注意**：本地代码搜索请使用 Claude 的 Explore 代理

## 项目结构

```
Oh-My-ClaudeCode/
├── src/omcc_mcp/             # 源代码
│   ├── __init__.py
│   ├── cli.py                # 入口点
│   ├── server.py             # MCP 服务器主体
│   ├── config.py             # 配置加载
│   └── tools/
│       ├── coder.py          # Coder 工具
│       ├── codex.py          # Codex 工具
│       ├── gemini.py         # Gemini 工具
│       ├── frontend.py       # Frontend 工具（前端/UI）
│       ├── chore.py          # Chore 工具（杂务执行）
│       ├── librarian.py      # Librarian 工具（网络研究）
│       └── looker.py         # Looker 工具（多模态分析）
├── skills/                   # Skills 工作流指导
│   ├── omcc-workflow/        # OMCC 协作流程（Coder/Codex）
│   ├── gemini-collaboration/ # Gemini 协作指南
│   ├── frontend/             # Frontend 前端/UI 指南
│   ├── chore/                # Chore 杂务执行指南
│   ├── librarian/            # Librarian 网络研究指南
│   └── looker/               # Looker 多模态分析指南
├── templates/                # 模板文件
│   └── omcc-global-prompt.md # 全局 CLAUDE.md 模板
├── cases/                    # 实测案例
├── pyproject.toml
├── config.example.toml       # 配置文件示例
├── setup.sh                  # Unix/macOS 安装脚本
├── setup.ps1                 # Windows PowerShell 安装脚本
├── setup.bat                 # Windows 批处理入口
├── README.md                 # 项目说明（中文）
├── README_EN.md              # 项目说明（英文）
└── CLAUDE.md                 # 本文件
```

## 开发里程碑

| 阶段 | 内容 | 状态 |
|------|------|------|
| M0 | 方案设计、技术验证 | ✅ 完成 |
| M1 | 最小可用版本（coder 工具） | ✅ 完成 |
| M2 | 集成 codex 工具 | ✅ 完成 |
| M3 | 协作 Prompt 优化 | ✅ 完成 |
| M4 | 集成 gemini 工具 | ✅ 完成 |
| M5 | 文档、发布 | ✅ 完成 |

## 技术要点

### MCP 工具

| 工具 | 功能 | 后端 | sandbox | 
|------|------|------|---------|
| `coder` | 代码生成/修改 | Claude CLI (可配置) | workspace-write |
| `codex` | 代码审核 | OpenAI Codex | read-only |
| `gemini` | 专家咨询/执行 | OpenCode CLI | workspace-write |
| `frontend` | 前端/UI 开发 | OpenCode CLI | workspace-write |
| `chore` | 杂务执行（批量操作） | OpenCode CLI | workspace-write |
| `librarian` | 网络研究（文档+搜索+GitHub） | OpenCode CLI | read-only |
| `looker` | 多模态分析（PDF/图片） | OpenCode CLI | read-only |

### 核心特性

#### 结构化错误
失败时返回 `error_kind` 和 `error_detail`，便于上层决策是否重试：
```json
{
  "success": false,
  "error": "错误摘要",
  "error_kind": "timeout | upstream_error | ...",
  "error_detail": {
    "message": "错误简述",
    "exit_code": 1,
    "last_lines": ["最后20行输出..."],
    "retries": 0
  }
}
```

#### 重试策略
- **Codex**：默认允许 1 次重试（只读操作无副作用）
- **Coder**：默认不重试（有写入副作用），可通过 `max_retries` 显式启用
- **Gemini**：默认允许 1 次重试
- **Frontend**：默认允许 1 次重试
- **Chore**：默认不重试（简单任务一次完成）
- **Librarian**：默认允许 1 次重试（只读操作无副作用）
- **Looker**：默认允许 1 次重试（只读操作无副作用）

#### 可观察性指标
- `return_metrics=True`：在返回值中包含耗时、Prompt 长度等指标
- `log_metrics=True`：将指标输出到 stderr（JSONL 格式）

#### 命令行参数策略
- **设置源**：`--setting-sources "project"` 仅加载项目级设置
- **System Prompt**：`--append-system-prompt` 通过命令行参数追加角色指令
- **对话 Prompt**：通过 stdin 传递（支持换行符，无长度限制）

### 配置方案

配置文件路径：`~/.omcc-mcp/config.toml`

```toml
# ~/.omcc-mcp/config.toml

# Coder 后端配置（claude CLI + 可配置模型）
[coder]
api_token = "your-api-token"
base_url = "https://open.bigmodel.cn/api/anthropic"
model = "glm-4.7"

# OpenCode CLI 代理模型配置
# 模型格式为 provider/model，需要在 ~/.config/opencode/opencode.jsonc 中配置 provider
[gemini]
model = "google/gemini-3-pro-preview"

[frontend]
model = "google/gemini-3-pro-preview"

[librarian]
model = "google/gemini-3-flash-preview"

[looker]
model = "google/gemini-3-flash-preview"

# Chore 杂务代理配置
[chore]
model = "anthropic/claude-sonnet-4-20250514"
```

### 跨平台实现

通过 `subprocess.Popen(env=custom_env)` 注入环境变量，无需依赖脚本文件。

## 参考资源

- [CodexMCP](https://github.com/GuDaStudio/codexmcp) - 核心参考实现
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP 框架
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- [Codex CLI](https://developers.openai.com/codex/quickstart)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli)

---

> 📅 项目创建: 2026-01-01
> 📅 重命名为 OMCC: 2026-01-03
> 📅 重命名为 Oh-My-ClaudeCode: 2026-01-16
