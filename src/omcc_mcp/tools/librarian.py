"""Librarian 工具实现

一个专注于网络研究的子代理。
基于 OpenCode CLI，使用 Gemini 3 Flash 模型（快速、低成本）。

主要功能：
- 查询官方文档和技术资料
- 搜索最新技术动态和解决方案
- GitHub 代码搜索（外部仓库）
- 网页内容抓取和分析

注意：本地代码库搜索请使用 Claude Code 的 Explore 代理。

后端：OpenCode CLI (https://opencode.ai)
"""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, Iterator, List, Literal, Optional

from pydantic import Field


# ============================================================================
# 错误类型定义
# ============================================================================

class CommandNotFoundError(Exception):
    """命令不存在错误"""
    pass


class CommandTimeoutError(Exception):
    """命令执行超时错误"""
    def __init__(self, message: str, is_idle: bool = False):
        super().__init__(message)
        self.is_idle = is_idle


# ============================================================================
# 错误类型枚举
# ============================================================================

class ErrorKind:
    """结构化错误类型枚举"""
    TIMEOUT = "timeout"
    IDLE_TIMEOUT = "idle_timeout"
    COMMAND_NOT_FOUND = "command_not_found"
    UPSTREAM_ERROR = "upstream_error"
    AUTH_REQUIRED = "auth_required"
    JSON_DECODE = "json_decode"
    PROTOCOL_MISSING_SESSION = "protocol_missing_session"
    EMPTY_RESULT = "empty_result"
    SUBPROCESS_ERROR = "subprocess_error"
    UNEXPECTED_EXCEPTION = "unexpected_exception"


# ============================================================================
# 指标收集
# ============================================================================

class MetricsCollector:
    """指标收集器"""

    def __init__(self, tool: str, prompt: str, sandbox: str):
        self.tool = tool
        self.sandbox = sandbox
        self.prompt_chars = len(prompt)
        self.prompt_lines = prompt.count('\n') + 1
        self.ts_start = datetime.now(timezone.utc)
        self.ts_end: Optional[datetime] = None
        self.duration_ms: int = 0
        self.success: bool = False
        self.error_kind: Optional[str] = None
        self.retries: int = 0
        self.exit_code: Optional[int] = None
        self.result_chars: int = 0
        self.result_lines: int = 0
        self.raw_output_lines: int = 0
        self.json_decode_errors: int = 0

    def finish(
        self,
        success: bool,
        error_kind: Optional[str] = None,
        result: str = "",
        exit_code: Optional[int] = None,
        raw_output_lines: int = 0,
        json_decode_errors: int = 0,
        retries: int = 0,
    ) -> None:
        """完成指标收集"""
        self.ts_end = datetime.now(timezone.utc)
        self.duration_ms = int((self.ts_end - self.ts_start).total_seconds() * 1000)
        self.success = success
        self.error_kind = error_kind
        self.result_chars = len(result)
        self.result_lines = result.count('\n') + 1 if result else 0
        self.exit_code = exit_code
        self.raw_output_lines = raw_output_lines
        self.json_decode_errors = json_decode_errors
        self.retries = retries

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "ts_start": self.ts_start.isoformat() if self.ts_start else None,
            "ts_end": self.ts_end.isoformat() if self.ts_end else None,
            "duration_ms": self.duration_ms,
            "tool": self.tool,
            "sandbox": self.sandbox,
            "success": self.success,
            "error_kind": self.error_kind,
            "retries": self.retries,
            "exit_code": self.exit_code,
            "prompt_chars": self.prompt_chars,
            "prompt_lines": self.prompt_lines,
            "result_chars": self.result_chars,
            "result_lines": self.result_lines,
            "raw_output_lines": self.raw_output_lines,
            "json_decode_errors": self.json_decode_errors,
        }

    def format_duration(self) -> str:
        """格式化耗时为 "xmxs" 格式"""
        total_seconds = self.duration_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m{seconds}s"

    def log_to_stderr(self) -> None:
        """将指标输出到 stderr（JSONL 格式）"""
        metrics = self.to_dict()
        metrics = {k: v for k, v in metrics.items() if v is not None}
        try:
            print(json.dumps(metrics, ensure_ascii=False), file=sys.stderr)
        except Exception:
            pass


# ============================================================================
# Librarian System Prompt
# ============================================================================

LIBRARIAN_SYSTEM_PROMPT = """# THE LIBRARIAN - 网络研究代理

你是 **THE LIBRARIAN**，一个专业的网络研究代理，专注于外部信息检索。

你的职责：通过查找 **证据** 和 **权威链接** 回答关于库、框架、API 和技术的问题。

**重要**：你**不负责**本地代码库搜索。本地代码探索由 Claude 的 Explore 代理处理。

---

## 重要：日期意识

**优先搜索最新信息**：在搜索查询中使用当前年份。
- 优先近 12-18 个月的信息
- 仅当任务明确需要历史信息时才搜索旧版本
- 当旧信息与新信息冲突时，过滤掉旧结果

---

## 核心能力与工具

| 类型 | 能力 | 工具 | 示例场景 |
|------|------|------|----------|
| **文档查询** | 官方文档获取 | context7 | "React useEffect 最佳实践" |
| **网络搜索** | 最新信息检索 | Exa | "TypeScript 5.5 新特性" |
| **代码搜索** | 开源代码搜索 | grep.app | "TanStack Query 的 useQuery 实现" |
| **深度阅读** | 网页内容抓取 | firecrawl | "深入阅读某篇技术文章" |
| **浏览器自动化** | JS 渲染页面 | Playwright | "抓取需要 JS 渲染的页面" |

---

## 阶段 0：请求分类（必须先执行）

| 类型 | 触发词 | 执行策略 |
|------|--------|----------|
| **TYPE A: 概念/用法** | "如何使用...", "最佳实践..." | context7 + Exa（并行） |
| **TYPE B: 源码实现** | "X 是如何实现的", "源码在哪" | grep.app 代码搜索 |
| **TYPE C: 问题诊断** | "为什么报错...", "怎么解决..." | Exa + grep.app |
| **TYPE D: 综合研究** | 复杂/模糊请求 | 全部工具并行 |

---

## 阶段 1：按类型执行

### TYPE A: 概念/用法问题

**并行执行 2-3 调用**：
```
工具 1: context7_resolve-library-id → context7_query-docs
工具 2: Exa 搜索("topic 最佳实践 2026")
工具 3: grep.app 搜索 "usage pattern" (可选)
```

### TYPE B: 外部仓库源码查找

**使用 grep.app 搜索**：
```
步骤 1: grep.app 搜索目标函数/类
步骤 2: 从搜索结果获取 GitHub 链接
步骤 3: 如需深入分析，使用 firecrawl 抓取源码
```

### TYPE C: 问题诊断

**并行执行 3+ 调用**：
```
工具 1: Exa 搜索("error message solution 2026")
工具 2: grep.app 搜索 "error message" 相关代码
工具 3: context7 查询相关文档
```

### TYPE D: 综合研究

**并行执行 4+ 调用**：
```
工具 1-2: 文档（context7 + Exa）
工具 3: grep.app 代码搜索
工具 4: firecrawl 深度阅读
```

---

## 阶段 2：证据综合

### 强制引用格式

每个声明 **必须** 包含来源链接：

```markdown
**声明**: [你主张的内容]

**证据** ([来源](https://github.com/owner/repo/blob/<sha>/path#L10-L20)):
```typescript
// 实际代码
function example() { ... }
```

**解释**: 这样工作是因为 [代码中的具体原因]。
```

### GitHub 永久链接构建

```
https://github.com/<owner>/<repo>/blob/<commit-sha>/<filepath>#L<start>-L<end>

获取 SHA:
- 从克隆: git rev-parse HEAD
- 从 API: gh api repos/owner/repo/commits/HEAD --jq '.sha'
```

---

## 可交付成果

你的输出必须包含：
1. **答案** - 带证据和权威来源链接
2. **代码示例**（如适用）- 带来源归属
3. **不确定声明** - 如果信息不完整

**优先权威链接（官方文档、GitHub 永久链接）而非推测。**

---

## 结构化输出格式

```
<analysis>
**字面请求**: [用户说的话]
**实际需求**: [用户真正想知道什么]
**请求类型**: [TYPE A/B/C/D]
</analysis>

<results>
<evidence>
[带永久链接的证据]
</evidence>

<answer>
[直接回答用户的实际需求]
</answer>

<uncertainty>
[如果有任何不确定的地方，在这里说明]
[或: "信息确认完整"]
</uncertainty>
</results>
```

---

## 通信规则

1. **不提工具名**：说 "我会搜索文档" 而不是 "我会使用 context7"
2. **不要铺垫**：直接回答，跳过 "我来帮你..."
3. **引用来源**：尽可能提供官方文档或 GitHub 链接
4. **使用 Markdown**：代码块带语言标识
5. **简洁为上**：事实 > 观点，证据 > 推测

## 工具限制

Librarian 是只读研究者。以下工具被 **禁止**：
- `write` - 不能创建文件
- `edit` - 不能修改文件
- `background_task` - 不能启动后台任务

## 范围边界

- **本地代码搜索**：请告知用户使用 Claude 的 Explore 代理
- **代码修改**：请路由到 Coder/Frontend 代理

---

## 最终回复要求

**重要**：在你的最终回复中，必须包含完整的研究总结：

1. **研究过程**：简述你做了哪些搜索/查询
2. **关键发现**：列出找到的核心信息和证据
3. **最终答案**：直接回答用户的问题
4. **来源引用**：附上所有使用的权威链接

这样做的原因：调用你的上层 AI 只能看到你的最终回复，无法看到中间的工具调用过程。
因此你需要在最终回复中完整总结你的研究结果。"""


# ============================================================================
# 命令执行
# ============================================================================

@contextmanager
def safe_librarian_command(
    cmd: list[str],
    timeout: int = 120,  # Librarian 使用更短的超时（快速响应）
    max_duration: int = 3600,  # 最大 1 小时
    cwd: Optional[Path] = None,
) -> Iterator[tuple[Generator[str, None, None], list[Optional[int]], list[int]]]:
    """安全执行 Librarian 命令的上下文管理器"""
    opencode_path = shutil.which('opencode')
    if not opencode_path:
        raise CommandNotFoundError(
            "未找到 opencode CLI。请确保已安装 OpenCode CLI 并添加到 PATH。\n"
            "安装指南：https://opencode.ai/docs/cli/"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = opencode_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace',
        cwd=str(cwd) if cwd else None,
    )

    thread: Optional[threading.Thread] = None

    def cleanup() -> None:
        """清理子进程和线程"""
        nonlocal thread
        try:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
        except (OSError, IOError):
            pass
        try:
            if process.stdout and not process.stdout.closed:
                process.stdout.close()
        except (OSError, IOError):
            pass
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
        except (ProcessLookupError, OSError):
            pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)

    try:
        if process.stdin:
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        output_queue: queue.Queue[str | None] = queue.Queue()
        raw_output_lines_holder = [0]
        exit_code_holder: list[Optional[int]] = [None]  # 用于存储 exit_code
        GRACEFUL_SHUTDOWN_DELAY = 0.3

        def is_turn_completed(line: str) -> bool:
            """检查是否回合完成"""
            try:
                data = json.loads(line)
                return data.get("type") == "turn.completed"
            except (json.JSONDecodeError, AttributeError, TypeError):
                return False

        def read_output() -> None:
            """在单独线程中读取进程输出"""
            try:
                if process.stdout:
                    for line in iter(process.stdout.readline, ""):
                        stripped = line.strip()
                        output_queue.put(stripped)
                        if stripped:
                            raw_output_lines_holder[0] += 1
                        if is_turn_completed(stripped):
                            time.sleep(GRACEFUL_SHUTDOWN_DELAY)
                            break
                    process.stdout.close()
            except (OSError, IOError, ValueError):
                pass
            finally:
                output_queue.put(None)

        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()

        def generator() -> Generator[str, None, None]:
            """生成器：读取输出并处理超时"""
            nonlocal thread
            start_time = time.time()
            last_activity_time = time.time()
            timeout_error: CommandTimeoutError | None = None

            while True:
                now = time.time()

                if max_duration > 0 and (now - start_time) >= max_duration:
                    timeout_error = CommandTimeoutError(
                        f"librarian 执行超时（总时长超过 {max_duration}s），进程已终止。",
                        is_idle=False
                    )
                    break

                if (now - last_activity_time) >= timeout:
                    timeout_error = CommandTimeoutError(
                        f"librarian 空闲超时（{timeout}s 无输出），进程已终止。",
                        is_idle=True
                    )
                    break

                try:
                    line = output_queue.get(timeout=0.5)
                    if line is None:
                        break
                    last_activity_time = time.time()
                    if line:
                        yield line
                except queue.Empty:
                    if process.poll() is not None and not thread.is_alive():
                        break

            if timeout_error is not None:
                cleanup()
                raise timeout_error

            exit_code: Optional[int] = None
            try:
                exit_code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                timeout_error = CommandTimeoutError(
                    f"librarian 进程等待超时，进程已终止。",
                    is_idle=False
                )
            finally:
                if thread is not None:
                    thread.join(timeout=5)

            if timeout_error is not None:
                raise timeout_error

            # 将 exit_code 存储到 holder 中，避免 StopIteration 问题
            exit_code_holder[0] = exit_code

            while not output_queue.empty():
                try:
                    line = output_queue.get_nowait()
                    if line is not None:
                        yield line
                except queue.Empty:
                    break

        # 返回 (generator, exit_code_holder, raw_output_lines_holder)
        yield generator(), exit_code_holder, raw_output_lines_holder

    except Exception:
        cleanup()
        raise
    finally:
        cleanup()


def _filter_last_lines(lines: list[str], max_lines: int = 50) -> list[str]:
    """过滤 last_lines，脱敏大内容"""
    import copy
    filtered = []
    for line in lines:
        try:
            data = json.loads(line)
            event_type = data.get("type", "")
            if event_type == "tool_result":
                data = copy.deepcopy(data)
                if "content" in data:
                    data["content"] = "[truncated]"
                filtered.append(json.dumps(data, ensure_ascii=False))
                continue
            filtered.append(line)
        except (json.JSONDecodeError, TypeError, AttributeError):
            filtered.append(line)
    return filtered[-max_lines:]


def _build_error_detail(
    message: str,
    exit_code: Optional[int] = None,
    last_lines: Optional[list[str]] = None,
    json_decode_errors: int = 0,
    idle_timeout_s: Optional[int] = None,
    max_duration_s: Optional[int] = None,
    retries: int = 0,
) -> Dict[str, Any]:
    """构建结构化错误详情"""
    detail: Dict[str, Any] = {"message": message}
    if exit_code is not None:
        detail["exit_code"] = exit_code
    if last_lines:
        detail["last_lines"] = _filter_last_lines(last_lines, max_lines=50)
    if json_decode_errors > 0:
        detail["json_decode_errors"] = json_decode_errors
    if idle_timeout_s is not None:
        detail["idle_timeout_s"] = idle_timeout_s
        detail["suggestion"] = "搜索任务超时。建议：缩小搜索范围或简化查询"
    if max_duration_s is not None:
        detail["max_duration_s"] = max_duration_s
        detail["suggestion"] = "搜索任务总时长超时。建议：拆分为更小的搜索任务"
    if retries > 0:
        detail["retries"] = retries
    return detail


# ============================================================================
# 可重试错误判断
# ============================================================================

def _is_auth_error(text: str) -> bool:
    """检测是否为认证错误"""
    text_lower = text.lower()
    auth_keywords = [
        "waiting for auth",
        "failed to login",
        "precondition check failed",
        "authentication",
        "401",
        "403",
        "unauthorized",
        "not authenticated",
        "login required",
        "sign in",
        "oauth",
        "api key",
    ]
    return any(keyword in text_lower for keyword in auth_keywords)


def _is_retryable_error(error_kind: Optional[str], err_message: str) -> bool:
    """判断错误是否可以重试"""
    if error_kind == ErrorKind.COMMAND_NOT_FOUND:
        return False
    if error_kind == ErrorKind.AUTH_REQUIRED:
        return False
    return True


# ============================================================================
# 主工具函数
# ============================================================================

async def librarian_tool(
    PROMPT: Annotated[str, "网络研究任务描述"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，Librarian 默认只读"),
    ] = "read-only",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "空闲超时（秒），默认 120 秒"] = 120,
    max_duration: Annotated[int, "总时长硬上限（秒），默认 3600 秒（1 小时）"] = 3600,
    max_retries: Annotated[int, "最大重试次数，默认 1"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Librarian 网络研究任务

    调用 OpenCode CLI 进行网络研究（文档查询、网络搜索、GitHub 搜索等）。

    **角色定位**：网络研究专家
    - 📖 文档查询：查询官方文档和技术资料（context7）
    - 🌐 网络搜索：搜索最新技术动态和解决方案（Exa）
    - 🔗 GitHub 搜索：搜索外部仓库代码、Issues、PRs
    - 📄 网页抓取：深度阅读技术文章（firecrawl）

    **特点**：
    - 使用 Gemini 3 Flash 模型，响应快速、成本低
    - 默认只读模式，不会修改代码
    - 专注于外部信息检索，不处理本地代码搜索

    **注意**：本地代码搜索请使用 Claude 的 Explore 代理

    **后端**：OpenCode CLI (https://opencode.ai)

    **使用场景**：
    - "React useEffect 的最佳实践"
    - "TypeScript 5.5 的新特性"
    - "TanStack Query 的 useQuery 实现"
    - "为什么 Zod 报这个错误"

    **Prompt 模板**：
    ```
    请帮我研究以下问题：
    **问题**：[具体问题]
    **技术栈**：[相关库/框架]
    **期望**：[官方文档链接/代码示例/解决方案]
    ```
    """
    # 初始化指标收集器
    metrics = MetricsCollector(tool="librarian", prompt=PROMPT, sandbox=sandbox)

    # 构建 opencode run 命令
    cmd = ["opencode", "run"]
    cmd.extend(["--format", "json"])

    # 使用配置的模型（默认 Gemini 3 Flash，快速、低成本）
    from omcc_mcp.config import get_agent_model
    model_to_use = get_agent_model("librarian")
    if model_to_use:
        cmd.extend(["--model", model_to_use])

    # 会话恢复
    if SESSION_ID:
        cmd.extend(["--session", SESSION_ID])

    # 构建完整的 prompt，包含 system prompt
    full_prompt = f"""{LIBRARIAN_SYSTEM_PROMPT}

---

用户请求：
{PROMPT}
"""

    # 添加 prompt（使用 -- 结束选项解析，防止 prompt 以 - 开头时被误解析）
    cmd.append("--")
    cmd.append(full_prompt)

    # 执行循环（支持重试）
    retries = 0
    last_error: Optional[Dict[str, Any]] = None
    all_last_lines: list[str] = []

    while retries <= max_retries:
        all_messages: list[Dict[str, Any]] = []
        agent_messages = ""
        had_error = False
        err_message = ""
        session_id: Optional[str] = None
        exit_code: Optional[int] = None
        raw_output_lines = 0
        json_decode_errors = 0
        error_kind: Optional[str] = None
        last_lines: list[str] = []

        try:
            with safe_librarian_command(cmd, timeout=timeout, max_duration=max_duration, cwd=cd) as (gen, exit_code_holder, raw_lines_holder):
                for line in gen:
                    last_lines.append(line)
                    if len(last_lines) > 50:
                        last_lines.pop(0)

                    try:
                        line_dict = json.loads(line.strip())
                        event_type = line_dict.get("type", "")

                        # 收集消息
                        if return_all_messages:
                            import copy
                            safe_dict = copy.deepcopy(line_dict)
                            if event_type == "tool_result":
                                if "content" in safe_dict:
                                    safe_dict["content"] = "[truncated]"
                            all_messages.append(safe_dict)

                        # 提取 message 事件中的内容（只保留最后一轮回复）
                        if event_type == "message":
                            role = line_dict.get("role", "")
                            content = line_dict.get("content", "")
                            if role == "assistant" and content:
                                agent_messages = content  # 覆盖而非累加，只保留最后一轮

                        # 提取 text 事件 (OpenCode 格式)
                        # 对于 text 事件，需要累加同一轮回复的多个片段
                        if event_type == "text":
                            part = line_dict.get("part", {})
                            text_content = part.get("text", "")
                            if text_content:
                                # 如果是新的一轮回复（有完整消息），累加
                                # 否则继续累加当前回复的片段
                                agent_messages += text_content

                        # message_end 事件标志一轮回复结束，重置累加
                        if event_type == "message_end":
                            # 不做任何操作，agent_messages 保持当前累加的内容
                            # 下一轮 message 开始时会通过 message 事件覆盖
                            pass

                        # 提取 result 事件
                        if event_type == "result":
                            response = line_dict.get("response", "")
                            if response:
                                agent_messages = response  # 覆盖为最终结果

                        # 提取 session_id
                        if event_type == "init":
                            if line_dict.get("session_id") is not None:
                                session_id = line_dict.get("session_id")
                            if line_dict.get("thread_id") is not None:
                                session_id = line_dict.get("thread_id")

                        # 错误处理
                        if event_type == "error":
                            had_error = True
                            error_msg = line_dict.get("message", str(line_dict))
                            err_message += "\n\n[librarian error] " + error_msg
                            if _is_auth_error(error_msg):
                                error_kind = ErrorKind.AUTH_REQUIRED
                            elif error_kind != ErrorKind.AUTH_REQUIRED:
                                error_kind = ErrorKind.UPSTREAM_ERROR

                    except json.JSONDecodeError:
                        json_decode_errors += 1
                        continue

                    except Exception as error:
                        err_message += f"\n\n[unexpected error] {error}. Line: {line!r}"
                        had_error = True
                        error_kind = ErrorKind.UNEXPECTED_EXCEPTION
                        break
                # for 循环结束后，从 holder 中获取 exit_code 和 raw_output_lines
                exit_code = exit_code_holder[0]
                raw_output_lines = raw_lines_holder[0]

        except CommandNotFoundError as e:
            metrics.finish(
                success=False,
                error_kind=ErrorKind.COMMAND_NOT_FOUND,
                retries=retries,
            )
            if log_metrics:
                metrics.log_to_stderr()

            result: Dict[str, Any] = {
                "success": False,
                "tool": "librarian",
                "error": str(e),
                "error_kind": ErrorKind.COMMAND_NOT_FOUND,
                "error_detail": _build_error_detail(str(e)),
            }
            if return_metrics:
                result["metrics"] = metrics.to_dict()
            return result

        except CommandTimeoutError as e:
            error_kind = ErrorKind.IDLE_TIMEOUT if e.is_idle else ErrorKind.TIMEOUT
            had_error = True
            err_message = str(e)
            success = False
            if retries < max_retries:
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                retries += 1
                time.sleep(0.5 * (2 ** (retries - 1)))
                continue
            else:
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                break

        # 综合判断成功与否
        success = True

        if had_error:
            success = False

        if not agent_messages:
            success = False
            if not error_kind:
                error_kind = ErrorKind.EMPTY_RESULT
            err_message = "未能获取 Librarian 响应内容。\n\n" + err_message

        if exit_code is not None and exit_code != 0 and success:
            success = False
            if not error_kind:
                error_kind = ErrorKind.SUBPROCESS_ERROR
            err_message = f"进程退出码非零：{exit_code}\n\n" + err_message

        if success:
            break
        else:
            if _is_retryable_error(error_kind, err_message) and retries < max_retries:
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                retries += 1
                time.sleep(0.5 * (2 ** (retries - 1)))
            else:
                all_last_lines = last_lines.copy()
                last_error = {
                    "error_kind": error_kind,
                    "err_message": err_message,
                    "exit_code": exit_code,
                    "json_decode_errors": json_decode_errors,
                    "raw_output_lines": raw_output_lines,
                }
                break

    # 完成指标收集
    metrics.finish(
        success=success,
        error_kind=error_kind,
        result=agent_messages,
        exit_code=exit_code,
        raw_output_lines=raw_output_lines,
        json_decode_errors=json_decode_errors,
        retries=retries,
    )
    if log_metrics:
        metrics.log_to_stderr()

    # 构建返回结果
    if success:
        result = {
            "success": True,
            "tool": "librarian",
            "SESSION_ID": session_id,
            "result": agent_messages,
            "duration": metrics.format_duration(),
        }
    else:
        if last_error:
            error_kind = last_error["error_kind"]
            err_message = last_error["err_message"]
            exit_code = last_error["exit_code"]
            json_decode_errors = last_error["json_decode_errors"]

        if error_kind == ErrorKind.AUTH_REQUIRED:
            auth_hint = """请先配置 OpenCode CLI。

1. 运行 opencode 启动交互式配置
2. 或者在 ~/.config/opencode/opencode.jsonc 中配置 provider 和 API Key

参考文档：https://opencode.ai/docs/config/

"""
            err_message = auth_hint + err_message

        result = {
            "success": False,
            "tool": "librarian",
            "error": err_message,
            "error_kind": error_kind,
            "error_detail": _build_error_detail(
                message=err_message.split('\n')[0] if err_message else "未知错误",
                exit_code=exit_code,
                last_lines=all_last_lines,
                json_decode_errors=json_decode_errors,
                idle_timeout_s=timeout if error_kind == ErrorKind.IDLE_TIMEOUT else None,
                max_duration_s=max_duration if error_kind == ErrorKind.TIMEOUT else None,
                retries=retries,
            ),
            "duration": metrics.format_duration(),
        }

    if return_all_messages:
        result["all_messages"] = all_messages

    if return_metrics:
        result["metrics"] = metrics.to_dict()

    return result
