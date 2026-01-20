"""OMCC-MCP 服务器主体

Oh-My-ClaudeCode 多代理协作 MCP 服务器。
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from omcc_mcp.tools.coder import coder_tool
from omcc_mcp.tools.codex import codex_tool
from omcc_mcp.tools.gemini import gemini_tool
from omcc_mcp.tools.librarian import librarian_tool
from omcc_mcp.tools.looker import looker_tool
from omcc_mcp.tools.frontend import frontend_tool
from omcc_mcp.tools.chore import chore_tool

# 创建 MCP 服务器实例
mcp = FastMCP("OMCC-MCP Server")


@mcp.tool(
    name="coder",
    description="""
    调用可配置的后端模型执行代码生成或修改任务。

    **角色定位**：代码执行者
    - 根据精确的 Prompt 生成或修改代码
    - 执行批量代码任务
    - 成本低，执行力强

    **可配置后端**：需要用户自行配置，推荐使用 GLM-4.7 作为参考案例，
    也可选用其他支持 Claude Code API 的模型（如 Minimax、DeepSeek 等）。

    **使用场景**：
    - 新增功能：根据需求生成代码
    - 修复 Bug：根据问题描述修改代码
    - 重构：根据目标进行代码重构
    - 批量任务：执行大量相似的代码修改

    **注意**：Coder 需要写权限，默认 sandbox 为 workspace-write

    **Prompt 模板**：
    ```
    请执行以下代码任务：
    **任务类型**：[新增功能 / 修复 Bug / 重构 / 其他]
    **目标文件**：[文件路径]
    **具体要求**：
    1. [要求1]
    2. [要求2]
    **约束条件**：
    - [约束1]
    **验收标准**：
    - [标准1]
    ```
    """,
)
async def coder(
    PROMPT: Annotated[str, "发送给 Coder 的任务指令，需要精确、具体"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认允许写工作区"),
    ] = "workspace-write",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"] = 300,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 3600 秒（1 小时），0 表示无限制"] = 3600,
    max_retries: Annotated[int, "最大重试次数，默认 0（Coder 有写入副作用，默认不重试）"] = 0,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Coder 代码任务"""
    return await coder_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="codex",
    description="""
    调用 Codex 进行代码审核。

    **角色定位**：代码审核者
    - 检查代码质量（可读性、可维护性、潜在 bug）
    - 评估需求完成度
    - 给出明确结论：✅ 通过 / ⚠️ 建议优化 / ❌ 需要修改

    **使用场景**：
    - Coder 完成代码后，调用 Codex 进行质量审核
    - 需要独立第三方视角时
    - 代码合入前的最终检查

    **注意**：Codex 仅审核，严禁修改代码，默认 sandbox 为 read-only

    **Prompt 模板**：
    ```
    请 review 以下代码改动：
    **改动文件**：[文件列表]
    **改动目的**：[简要描述]
    **请检查**：
    1. 代码质量（可读性、可维护性）
    2. 潜在 Bug 或边界情况
    3. 需求完成度
    **请给出明确结论**：
    - ✅ 通过：代码质量良好，可以合入
    - ⚠️ 建议优化：[具体建议]
    - ❌ 需要修改：[具体问题]
    ```
    """,
)
async def codex(
    PROMPT: Annotated[str, "审核任务描述"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认只读"),
    ] = "read-only",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    skip_git_repo_check: Annotated[
        bool,
        "允许在非 Git 仓库中运行",
    ] = True,
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    image: Annotated[
        Optional[List[Path]],
        Field(description="附加图片文件路径列表"),
    ] = None,
    model: Annotated[
        str,
        Field(description="指定模型，默认使用 Codex 自己的配置"),
    ] = "",
    yolo: Annotated[
        bool,
        Field(description="无需审批运行所有命令（跳过沙箱）"),
    ] = False,
    profile: Annotated[
        str,
        "从 ~/.codex/config.toml 加载的配置文件名称",
    ] = "",
    timeout: Annotated[int, "空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"] = 300,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 7200 秒（2 小时），0 表示无限制"] = 7200,
    max_retries: Annotated[int, "最大重试次数，默认 1（Codex 只读可安全重试）"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Codex 代码审核"""
    return await codex_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        skip_git_repo_check=skip_git_repo_check,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        image=image,
        model=model,
        yolo=yolo,
        profile=profile,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="gemini",
    description="""
    调用 Gemini CLI 进行代码执行、技术咨询或代码审核。

    **角色定位**：多面手（与 Claude、Codex 同等级别的顶级 AI 专家）
    - 高阶顾问：架构设计、技术选型、复杂方案讨论
    - 独立审核：代码 Review、方案评审、质量把关
    - 代码执行：原型开发、功能实现（尤其擅长前端/UI）

    **使用场景**：
    - 用户明确要求使用 Gemini
    - 需要第二意见或独立视角
    - 架构设计和技术讨论
    - 前端/UI 原型开发

    **注意**：Gemini 权限灵活，默认 yolo=true，由 Claude 按场景控制
    **重试策略**：默认允许 1 次重试

    **Prompt 模板**：
    ```
    请提供专业意见/执行以下任务：
    **任务类型**：[咨询 / 审核 / 执行]
    **背景信息**：[项目上下文]
    **具体问题/任务**：
    1. [问题/任务1]
    2. [问题/任务2]
    **期望输出**：
    - [输出格式/内容要求]
    ```
    """,
)
async def gemini(
    PROMPT: Annotated[str, "任务指令，需提供充分背景信息"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，默认允许写工作区"),
    ] = "workspace-write",
    yolo: Annotated[
        bool,
        Field(description="无需审批运行所有命令（跳过沙箱），默认 true"),
    ] = True,
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    model: Annotated[
        str,
        Field(description="指定模型版本，默认使用 gemini-3-pro-preview"),
    ] = "",
    timeout: Annotated[int, "空闲超时（秒），无输出超过此时间触发超时，默认 300 秒"] = 300,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 3600 秒（1 小时），0 表示无限制"] = 3600,
    max_retries: Annotated[int, "最大重试次数，默认 1"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Gemini 任务"""
    return await gemini_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        yolo=yolo,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        model=model,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="librarian",
    description="""
    调用 Librarian 进行网络研究（文档查询、网络搜索、GitHub 搜索等）。

    **角色定位**：网络研究专家
    - 📖 文档查询：查询官方文档和技术资料（context7）
    - 🌐 网络搜索：搜索最新技术动态和解决方案（Exa）
    - 🔗 代码搜索：通过 grep.app 搜索开源代码库
    - 📄 网页抓取：深度阅读技术文章（firecrawl）

    **请求分类**：
    | 类型 | 触发词 | 示例 |
    |------|--------|------|
    | TYPE A | "如何使用...", "最佳实践..." | 概念/用法问题 |
    | TYPE B | "X 是如何实现的" | 外部源码查找 |
    | TYPE C | "为什么报错...", "怎么解决..." | 问题诊断 |
    | TYPE D | 复杂/模糊请求 | 综合研究 |

    **使用场景**：
    - "React useEffect 的最佳实践"
    - "TypeScript 5.5 的新特性"
    - "TanStack Query 的 useQuery 实现"
    - "为什么 Zod 报这个错误"

    **特点**：
    - 使用 gemini-3-flash 模型（快速、低成本）
    - 默认只读模式，不会修改代码
    - 通过 Gemini CLI 配置的 MCP 提供研究能力

    **注意**：
    - Librarian 专注于外部信息检索，不负责本地代码库搜索
    - 本地代码搜索请使用 Claude 的 Explore 代理
    - 默认 sandbox 为 read-only

    **Prompt 模板**：
    ```
    请帮我研究以下问题：
    **问题**：[具体问题]
    **技术栈**：[相关库/框架]
    **期望**：[官方文档链接/代码示例/解决方案]
    ```
    """,
)
async def librarian(
    PROMPT: Annotated[str, "搜索或理解任务描述"],
    cd: Annotated[Path, "工作目录（代码库根目录）"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，Librarian 默认只读"),
    ] = "read-only",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "空闲超时（秒），默认 120 秒（Librarian 追求快速响应）"] = 120,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 3600 秒（1 小时）"] = 3600,
    max_retries: Annotated[int, "最大重试次数，默认 1（只读可安全重试）"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Librarian 代码搜索任务"""
    return await librarian_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="looker",
    description="""
    调用 Looker 进行多模态文件分析。

    **角色定位**：多模态分析专家
    - 📄 PDF 分析：提取文本、表格、结构
    - 🖼️ 图片分析：描述内容、识别 UI 元素
    - 📊 图表分析：解释数据趋势和关系
    - 🏗️ 架构图分析：解释组件关系和数据流
    - 📸 截图分析：识别错误信息、UI 状态

    **使用场景**：
    - 需要分析 PDF 文档内容
    - 描述 UI 截图中的元素
    - 解释架构图或流程图
    - 从图表中提取数据

    **适合使用**：
    - 媒体文件无法作为纯文本读取
    - 需要从文档中提取特定信息或摘要
    - 需要描述图片或图表中的视觉内容

    **不适合使用**：
    - 源代码或纯文本文件（使用 Read 工具）
    - 需要后续编辑的文件（需要从 Read 获取字面内容）

    **特点**：
    - 使用 gemini-3-flash 模型（擅长多模态分析）
    - 默认只读模式，不会修改文件
    - 节省主代理上下文 token

    **注意**：Looker 仅分析文件，严禁修改，默认 sandbox 为 read-only

    **Prompt 模板**：
    ```
    file_path: "/path/to/file.pdf"
    goal: "提取文档中关于用户认证的所有内容"
    ```
    """,
)
async def looker(
    file_path: Annotated[str, "要分析的媒体文件路径（PDF/图片/图表等）"],
    goal: Annotated[str, "分析目标，描述需要从文件中提取什么信息"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，Looker 默认只读"),
    ] = "read-only",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "空闲超时（秒），默认 120 秒"] = 120,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 3600 秒（1 小时）"] = 3600,
    max_retries: Annotated[int, "最大重试次数，默认 1（只读可安全重试）"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Looker 多模态分析任务"""
    return await looker_tool(
        file_path=file_path,
        goal=goal,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="frontend",
    description="""
    调用 Frontend UI/UX Engineer 进行前端/UI 开发。

    **角色定位**：前端/UI 专家（设计师型开发者）
    - 🎨 界面设计和布局实现
    - 💄 样式和动效开发
    - 📱 响应式适配
    - ✨ UI 审查和改进

    **使用场景**：
    - 新建页面或组件
    - 样式优化和动效开发
    - UI 审查和改进建议
    - 设计稿转代码

    **适合使用**：
    - 任何前端/UI 开发任务
    - 需要设计师视角的界面优化
    - 响应式和动效实现

    **不适合使用**：
    - 非前端代码实现（使用 Coder）
    - 代码审查（使用 Codex）
    - 外部研究（使用 Librarian）

    **特点**：
    - 使用 gemini-3-pro 模型（强创意和代码能力）
    - 设计师视角：关注间距、色彩、微交互
    - 支持多技术栈：React/Vue/Svelte/HTML+Tailwind

    **集成 UI/UX Pro Max**：
    - 57 种 UI 风格
    - 95 种调色板
    - 56 种字体搭配

    **Prompt 模板**：
    ```
    创建一个 [页面类型] 页面：
    - 风格：[极简/玻璃拟态/便当盒/...]
    - 技术栈：[React/Vue/HTML+Tailwind]
    - 要求：[响应式/暗色模式/动效]
    ```
    """,
)
async def frontend(
    PROMPT: Annotated[str, "前端/UI 任务描述和需求"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，Frontend 默认 workspace-write"),
    ] = "workspace-write",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "空闲超时（秒），默认 180 秒"] = 180,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 3600 秒（1 小时）"] = 3600,
    max_retries: Annotated[int, "最大重试次数，默认 1"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Frontend UI/UX Engineer 任务"""
    return await frontend_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


@mcp.tool(
    name="chore",
    description="""
    调用 Chore 执行简单、重复、杂务性质的任务。

    **角色定位**：杂务执行者
    - 🔧 简单任务（不需要复杂设计）
    - 🔄 重复操作（批量处理）
    - 💰 节省 token（使用廉价模型）

    **使用场景**：
    - 文件批量重命名/移动
    - 全局文本替换
    - 代码格式化/lint 修复
    - 依赖版本更新
    - 配置文件批量修改
    - 日志清理

    **适合使用**：
    - 简单、明确、不需要设计的任务
    - 批量处理多个文件
    - token 消耗大但逻辑简单的操作

    **不适合使用**：
    - 需要创意设计（使用 Frontend）
    - 需要架构决策（使用 Codex/Gemini）
    - 复杂代码实现（使用 Coder）

    **特点**：
    - 使用可配置后端（与 Coder 相同，廉价模型）
    - 默认不重试（简单任务一次完成）
    - 快速执行，120s 空闲超时

    **Prompt 模板**：
    ```
    将所有 .js 文件重命名为 .ts
    将代码中所有 'var' 替换为 'let'
    更新 package.json 中所有依赖到最新版本
    ```
    """,
)
async def chore(
    PROMPT: Annotated[str, "杂务任务描述"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，Chore 默认 workspace-write"),
    ] = "workspace-write",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "空闲超时（秒），默认 120 秒"] = 120,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 3600 秒（1 小时）"] = 3600,
    max_retries: Annotated[int, "最大重试次数，默认 0（杂务任务通常不重试）"] = 0,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Chore 杂务任务"""
    return await chore_tool(
        PROMPT=PROMPT,
        cd=cd,
        sandbox=sandbox,
        SESSION_ID=SESSION_ID,
        return_all_messages=return_all_messages,
        return_metrics=return_metrics,
        timeout=timeout,
        max_duration=max_duration,
        max_retries=max_retries,
        log_metrics=log_metrics,
    )


def run() -> None:
    """启动 MCP 服务器"""
    mcp.run(transport="stdio")
