"""Chore 工具实现

执行简单、重复、杂务性质的任务。
基于 OpenCode CLI，使用廉价模型节省 token。

主要功能：
- 文件批量重命名
- 简单的文本替换
- 代码格式化
- 依赖更新检查
- 日志清理
- 配置文件批量修改
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, Iterator, Literal, Optional

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
    CONFIG_ERROR = "config_error"
    JSON_DECODE = "json_decode"
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
# Chore System Prompt
# ============================================================================

CHORE_SYSTEM_PROMPT = """# CHORE - 杂务执行者

你是一个专门执行简单、重复、杂务性质任务的代理。

## 核心特点

- 🔧 **简单任务**：不需要复杂设计或创意
- 🔄 **重复操作**：批量处理、多文件修改
- 💰 **节省 token**：使用廉价模型处理消耗大的任务

## 适合的任务类型

| 类型 | 示例 |
|------|------|
| **文件操作** | 批量重命名、移动、整理 |
| **文本替换** | 全局搜索替换、格式统一 |
| **代码格式** | 格式化、lint 修复、排序导入 |
| **依赖管理** | 更新版本、清理未使用依赖 |
| **配置修改** | 批量更新配置项 |
| **日志清理** | 清理旧日志、压缩归档 |
| **文档生成** | 简单的模板填充 |

## 工作原则

1. **直接执行**：不需要复杂分析，直接完成任务
2. **批量处理**：尽可能一次处理多个文件/项目
3. **保持简单**：不添加额外的"优化"或"改进"
4. **报告结果**：简洁列出完成的操作

## 输出格式

```
已完成：
- [操作1]
- [操作2]
- ...

统计：
- 处理文件数：X
- 修改行数：Y
```

## 不适合的任务

这些任务应该使用其他代理：
- 需要创意设计 → Frontend/Gemini
- 需要架构决策 → Codex/Gemini
- 复杂代码实现 → Coder
- 代码审查 → Codex
- 深度研究 → Librarian"""


# ============================================================================
# 命令执行
# ============================================================================

@contextmanager
def safe_chore_command(
    cmd: list[str],
    timeout: int = 120,  # Chore 任务通常较快
    max_duration: int = 600,  # 最大 10 分钟
    prompt: str = "",
    cwd: Optional[Path] = None,
) -> Iterator[Generator[str, None, tuple[Optional[int], int]]]:
    """安全执行 Chore 命令的上下文管理器（使用 OpenCode CLI）"""
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
                if prompt:
                    process.stdin.write(prompt)
            except (BrokenPipeError, OSError):
                pass
            finally:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass

        output_queue: queue.Queue[str | None] = queue.Queue()
        raw_output_lines_holder = [0]
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

        def generator() -> Generator[str, None, tuple[Optional[int], int]]:
            """生成器：读取输出并处理超时"""
            nonlocal thread
            start_time = time.time()
            last_activity_time = time.time()
            timeout_error: CommandTimeoutError | None = None

            while True:
                now = time.time()

                if max_duration > 0 and (now - start_time) >= max_duration:
                    timeout_error = CommandTimeoutError(
                        f"chore 执行超时（总时长超过 {max_duration}s），进程已终止。",
                        is_idle=False
                    )
                    break

                if (now - last_activity_time) >= timeout:
                    timeout_error = CommandTimeoutError(
                        f"chore 空闲超时（{timeout}s 无输出），进程已终止。",
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
                    f"chore 进程等待超时，进程已终止。",
                    is_idle=False
                )
            finally:
                if thread is not None:
                    thread.join(timeout=5)

            if timeout_error is not None:
                raise timeout_error

            while not output_queue.empty():
                try:
                    line = output_queue.get_nowait()
                    if line is not None:
                        yield line
                except queue.Empty:
                    break

            return (exit_code, raw_output_lines_holder[0])

        yield generator()

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
        detail["suggestion"] = "杂务任务超时。建议：拆分为更小的任务"
    if max_duration_s is not None:
        detail["max_duration_s"] = max_duration_s
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
    ]
    return any(keyword in text_lower for keyword in auth_keywords)


def _is_retryable_error(error_kind: Optional[str], err_message: str) -> bool:
    """判断错误是否可以重试"""
    if error_kind == ErrorKind.COMMAND_NOT_FOUND:
        return False
    if error_kind == ErrorKind.AUTH_REQUIRED:
        return False
    if error_kind == ErrorKind.CONFIG_ERROR:
        return False
    return True


# ============================================================================
# 主工具函数
# ============================================================================

async def chore_tool(
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
    max_duration: Annotated[int, "总时长硬上限（秒），默认 600 秒（10 分钟）"] = 600,
    max_retries: Annotated[int, "最大重试次数，默认 0（杂务任务通常不重试）"] = 0,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Chore 杂务任务

    调用 OpenCode CLI 执行简单、重复的杂务任务。

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

    **不适合**：
    - 需要创意设计 → Frontend
    - 需要架构决策 → Codex/Gemini
    - 复杂代码实现 → Coder

    **Prompt 模板**：
    ```
    将所有 .js 文件重命名为 .ts
    将代码中所有 'var' 替换为 'let'
    更新 package.json 中所有依赖到最新版本
    ```
    """
    # 构建完整的 prompt（包含 System Prompt）
    full_prompt = f"{CHORE_SYSTEM_PROMPT}\n\n---\n\n{PROMPT}"
    
    # 初始化指标收集器
    metrics = MetricsCollector(tool="chore", prompt=full_prompt, sandbox=sandbox)

    # 构建 opencode run 命令
    cmd = ["opencode", "run"]
    cmd.extend(["--format", "json"])  # JSON 格式输出
    
    # 会话恢复
    if SESSION_ID:
        cmd.extend(["--session", SESSION_ID])
    
    # 添加 prompt（包含 System Prompt）
    cmd.append(full_prompt)

    # 执行循环
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
            with safe_chore_command(cmd, timeout=timeout, max_duration=max_duration, prompt="", cwd=cd) as gen:
                try:
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
                                err_message += "\n\n[chore error] " + error_msg
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
                except StopIteration as e:
                    if isinstance(e.value, tuple) and len(e.value) == 2:
                        exit_code, raw_output_lines = e.value

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
                "tool": "chore",
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
            err_message = "未能获取 Chore 执行结果。\n\n" + err_message

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
            "tool": "chore",
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

        result = {
            "success": False,
            "tool": "chore",
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
