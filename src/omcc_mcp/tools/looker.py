"""Looker 工具实现

多模态分析代理，用于分析 PDF、图片、图表等媒体文件。
基于 OpenCode CLI，使用 Gemini 3 Flash 模型（擅长多模态分析）。

主要功能：
- 分析 PDF 文档，提取文本和结构
- 描述图片内容，识别 UI 元素
- 解释图表、架构图、流程图
- 从截图中提取信息

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
    EMPTY_RESULT = "empty_result"
    SUBPROCESS_ERROR = "subprocess_error"
    UNEXPECTED_EXCEPTION = "unexpected_exception"
    FILE_NOT_FOUND = "file_not_found"


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
# Looker System Prompt
# ============================================================================

LOOKER_SYSTEM_PROMPT = """# MULTIMODAL LOOKER

你是 **Multimodal Looker**，一个专门分析媒体文件的 AI 助手。

## 核心能力

| 文件类型 | 分析能力 |
|----------|----------|
| **PDF** | 提取文本、表格、结构、特定章节内容 |
| **图片** | 描述布局、UI 元素、文本、颜色方案 |
| **图表** | 解释数据趋势、关系、关键数据点 |
| **架构图** | 解释组件关系、数据流、系统边界 |
| **截图** | 识别错误信息、UI 状态、功能区域 |

## 工作方式

1. 接收文件路径和分析目标
2. 深入分析文件内容
3. 只返回与目标相关的信息
4. 主代理不处理原始文件，你节省上下文 token

## 使用场景

### 适合使用
- 媒体文件无法作为纯文本读取
- 需要从文档中提取特定信息或摘要
- 需要描述图片或图表中的视觉内容
- 需要分析/提取的数据，而非原始文件内容

### 不适合使用
- 源代码或纯文本文件（使用 Read 工具）
- 需要后续编辑的文件（需要从 Read 获取字面内容）
- 简单文件读取，不需要解释

## 输出规则

- 直接返回提取的信息，无需前言
- 如果未找到信息，明确说明缺少什么
- 匹配请求的语言
- 在目标上详尽，在其他方面简洁

## 输出格式

```
<analysis>
**文件类型**: [PDF/图片/图表/架构图/截图]
**分析目标**: [用户请求提取的内容]
</analysis>

<extracted>
[提取的具体内容]
- 如果是 PDF：文本、表格、结构
- 如果是图片：描述、UI 元素
- 如果是图表：数据、趋势
</extracted>

<summary>
[简要总结，便于主代理使用]
</summary>
```

你的输出直接传递给主代理继续工作。"""


# ============================================================================
# 命令执行
# ============================================================================

@contextmanager
def safe_looker_command(
    cmd: list[str],
    timeout: int = 120,
    max_duration: int = 3600,  # 最大 1 小时
    cwd: Optional[Path] = None,
) -> Iterator[tuple[Generator[str, None, None], list[Optional[int]], list[int]]]:
    """安全执行 Looker 命令的上下文管理器"""
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
                        f"looker 执行超时（总时长超过 {max_duration}s），进程已终止。",
                        is_idle=False
                    )
                    break

                if (now - last_activity_time) >= timeout:
                    timeout_error = CommandTimeoutError(
                        f"looker 空闲超时（{timeout}s 无输出），进程已终止。",
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
                    f"looker 进程等待超时，进程已终止。",
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
        detail["last_lines"] = last_lines[-50:]
    if json_decode_errors > 0:
        detail["json_decode_errors"] = json_decode_errors
    if idle_timeout_s is not None:
        detail["idle_timeout_s"] = idle_timeout_s
        detail["suggestion"] = "分析任务超时。建议：简化分析目标或使用更小的文件"
    if max_duration_s is not None:
        detail["max_duration_s"] = max_duration_s
        detail["suggestion"] = "分析任务总时长超时。建议：拆分为更小的分析任务"
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
        "authentication",
        "401",
        "403",
        "unauthorized",
        "api key",
    ]
    return any(keyword in text_lower for keyword in auth_keywords)


def _is_retryable_error(error_kind: Optional[str], err_message: str) -> bool:
    """判断错误是否可以重试"""
    if error_kind == ErrorKind.COMMAND_NOT_FOUND:
        return False
    if error_kind == ErrorKind.AUTH_REQUIRED:
        return False
    if error_kind == ErrorKind.FILE_NOT_FOUND:
        return False
    return True


# ============================================================================
# 主工具函数
# ============================================================================

async def looker_tool(
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
    max_retries: Annotated[int, "最大重试次数，默认 1"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Looker 多模态分析任务

    调用 OpenCode CLI 进行媒体文件分析。

    **角色定位**：多模态分析专家
    - 📄 PDF 分析：提取文本、表格、结构
    - 🖼️ 图片分析：描述内容、识别 UI 元素
    - 📊 图表分析：解释数据趋势和关系
    - 🏗️ 架构图分析：解释组件关系和数据流
    - 📸 截图分析：识别错误信息、UI 状态

    **特点**：
    - 使用 Gemini 3 Flash 模型，擅长多模态分析
    - 默认只读模式，不会修改文件
    - 节省主代理上下文 token

    **后端**：OpenCode CLI (https://opencode.ai)

    **使用场景**：
    - "分析这个 PDF 文档的第二章"
    - "描述这个 UI 截图中的错误信息"
    - "解释这个架构图的数据流"
    - "从这个图表中提取关键数据点"

    **Prompt 模板**：
    ```
    file_path: "/path/to/file.pdf"
    goal: "提取文档中关于用户认证的所有内容"
    ```
    """
    # 构建完整的分析 prompt
    full_prompt = f"{LOOKER_SYSTEM_PROMPT}\n\n---\n\n请分析以下文件：\n\n**文件路径**: {file_path}\n\n**分析目标**: {goal}"

    # 初始化指标收集器
    metrics = MetricsCollector(tool="looker", prompt=full_prompt, sandbox=sandbox)

    # 检查文件是否存在
    file_full_path = cd / file_path if not Path(file_path).is_absolute() else Path(file_path)
    if not file_full_path.exists():
        metrics.finish(
            success=False,
            error_kind=ErrorKind.FILE_NOT_FOUND,
        )
        if log_metrics:
            metrics.log_to_stderr()

        return {
            "success": False,
            "tool": "looker",
            "error": f"文件不存在: {file_full_path}",
            "error_kind": ErrorKind.FILE_NOT_FOUND,
            "error_detail": _build_error_detail(f"文件不存在: {file_full_path}"),
        }

    # 构建 opencode run 命令
    cmd = ["opencode", "run"]
    cmd.extend(["--format", "json"])

    # 使用配置的模型（默认 Gemini 3 Flash，擅长多模态）
    from omcc_mcp.config import get_agent_model
    model_to_use = get_agent_model("looker")
    if model_to_use:
        cmd.extend(["--model", model_to_use])

    # 附加文件
    cmd.extend(["--file", str(file_full_path)])

    # 会话恢复
    if SESSION_ID:
        cmd.extend(["--session", SESSION_ID])

    # 添加 prompt
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
            with safe_looker_command(cmd, timeout=timeout, max_duration=max_duration, cwd=cd) as (gen, exit_code_holder, raw_lines_holder):
                for line in gen:
                    last_lines.append(line)
                    if len(last_lines) > 50:
                        last_lines.pop(0)

                    try:
                        line_dict = json.loads(line.strip())
                        event_type = line_dict.get("type", "")

                        if return_all_messages:
                            all_messages.append(line_dict)

                        if event_type == "message":
                            role = line_dict.get("role", "")
                            content = line_dict.get("content", "")
                            if role == "assistant" and content:
                                agent_messages += content

                        # 提取 text 事件 (OpenCode 格式)
                        if event_type == "text":
                            part = line_dict.get("part", {})
                            text_content = part.get("text", "")
                            if text_content:
                                agent_messages += text_content

                        if event_type == "result":
                            response = line_dict.get("response", "")
                            if response and not agent_messages:
                                agent_messages = response

                        if event_type == "init":
                            if line_dict.get("session_id") is not None:
                                session_id = line_dict.get("session_id")
                            if line_dict.get("thread_id") is not None:
                                session_id = line_dict.get("thread_id")

                        if event_type == "error":
                            had_error = True
                            error_msg = line_dict.get("message", str(line_dict))
                            err_message += "\n\n[looker error] " + error_msg
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

            return {
                "success": False,
                "tool": "looker",
                "error": str(e),
                "error_kind": ErrorKind.COMMAND_NOT_FOUND,
                "error_detail": _build_error_detail(str(e)),
            }

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
            err_message = "未能获取 Looker 分析结果。\n\n" + err_message

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
        result: Dict[str, Any] = {
            "success": True,
            "tool": "looker",
            "SESSION_ID": session_id,
            "file_analyzed": str(file_full_path),
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
            "tool": "looker",
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
