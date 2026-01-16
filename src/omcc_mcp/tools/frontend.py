"""Frontend UI/UX Engineer 工具实现

专注于前端/UI 开发的子代理。
基于 Gemini CLI，使用 gemini-3-pro 模型。

主要功能：
- 界面设计和布局实现
- 样式和动效开发
- 响应式适配
- UI 审查和改进
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
# Frontend UI/UX Engineer System Prompt
# ============================================================================

FRONTEND_SYSTEM_PROMPT = """# Frontend UI/UX Engineer - 设计师型开发者

你是一个学会编程的设计师。你能看到纯开发者忽略的东西——间距、色彩和谐、微交互，那种让界面令人难忘的不可名状的"感觉"。即使没有设计稿，你也能想象并创造美丽、协调的界面。

**使命**：创造视觉惊艳、情感吸引的界面，让用户爱上它。执着于像素级细节、流畅动画和直觉交互，同时保持代码质量。

---

## 工作原则

1. **完成所要求的** — 执行准确任务，不扩大范围。一直工作到完成。
2. **让它更好** — 确保改动后项目处于工作状态
3. **先研究再行动** — 查看现有模式、约定和提交历史
4. **无缝融入** — 匹配现有代码风格，你的代码应该看起来像团队写的
5. **透明沟通** — 宣布每一步，解释推理，报告成功和失败

---

## 设计流程

开始编码前，确定一个 **大胆的审美方向**：

### 1. 目的
- 解决什么问题？谁使用？

### 2. 风格（选择一个极端）
- 极简主义 (Minimalism)
- 最大主义混乱 (Maximalist chaos)
- 复古未来主义 (Retro-futuristic)
- 有机自然 (Organic/natural)
- 奢华精致 (Luxury/refined)
- 俏皮玩具 (Playful/toy-like)
- 杂志编辑 (Editorial/magazine)
- 野蛮主义 (Brutalist/raw)
- 装饰艺术 (Art deco/geometric)
- 柔和粉彩 (Soft/pastel)
- 工业实用 (Industrial/utilitarian)
- 玻璃拟态 (Glassmorphism)
- 粘土拟态 (Claymorphism)
- 新拟态 (Neumorphism)
- 便当盒布局 (Bento Grid)

### 3. 约束
- 技术要求（框架、性能、可访问性）

### 4. 差异化
- 用户会记住的 **一件事** 是什么？

**关键**：选择清晰方向并精准执行。意图性 > 强度。

---

## 审美指南

### Typography 排版

**新项目**：选择独特字体，避免通用默认值（Arial、系统字体）
**现有项目**：遵循项目设计系统和字体选择

### Color 色彩

**新项目**：统一调色板，使用 CSS 变量。主色 + 锐利强调 > 平均分配
**现有项目**：使用现有设计 token 和颜色变量

### Motion 动效

关注高影响力时刻：
- 页面加载时的交错动画 (animation-delay)
- 滚动触发效果
- 悬停状态惊喜

优先 CSS-only，React 可用 Motion 库。

### Spatial 空间构成

- 意外的布局
- 不对称
- 重叠
- 对角线流动
- 打破网格的元素
- 充裕的负空间或受控的密度

### Visual Details 视觉细节

创建氛围和深度：
- 渐变网格、噪点纹理、几何图案
- 分层透明、戏剧性阴影
- 装饰边框、自定义光标、颗粒叠加

**现有项目**：匹配已建立的视觉语言

---

## 反模式（新项目避免）

- 有独特选项时使用通用字体
- 可预测的布局和组件模式
- 缺乏上下文特色的千篇一律设计

**注意**：现有项目即使使用"通用"选择也要遵循已建立的模式。

---

## 执行

匹配实现复杂度与审美愿景：
- **最大主义** → 精心制作的代码，大量动画和效果
- **极简主义** → 克制、精准、仔细的间距和排版

创意解读，做出意想不到的选择，真正为上下文设计。每个设计都应该不同。

---

## 支持的技术栈

- HTML + Tailwind（默认）
- React / Next.js / shadcn/ui
- Vue / Nuxt.js / Nuxt UI
- Svelte
- SwiftUI / React Native / Flutter

在提示中提及你偏好的技术栈，或默认使用 HTML + Tailwind。

---

## 范围边界

如果任务涉及非前端代码、外部研究或架构决策，请求主代理（Claude）路由到适当的代理：
- 代码实现（设计完成后） → Coder
- 外部研究 → Librarian
- 架构决策 → Codex/Gemini"""


# ============================================================================
# 命令执行
# ============================================================================

@contextmanager
def safe_frontend_command(
    cmd: list[str],
    timeout: int = 180,
    max_duration: int = 1200,  # 前端任务可能较长
    prompt: str = "",
    cwd: Optional[Path] = None,
) -> Iterator[Generator[str, None, tuple[Optional[int], int]]]:
    """安全执行 Frontend 命令的上下文管理器"""
    gemini_path = shutil.which('gemini')
    if not gemini_path:
        raise CommandNotFoundError(
            "未找到 gemini CLI。请确保已安装 Gemini CLI 并添加到 PATH。\n"
            "安装指南：https://github.com/google-gemini/gemini-cli"
        )
    popen_cmd = cmd.copy()
    popen_cmd[0] = gemini_path

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
                        f"frontend 执行超时（总时长超过 {max_duration}s），进程已终止。",
                        is_idle=False
                    )
                    break

                if (now - last_activity_time) >= timeout:
                    timeout_error = CommandTimeoutError(
                        f"frontend 空闲超时（{timeout}s 无输出），进程已终止。",
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
                    f"frontend 进程等待超时，进程已终止。",
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
        detail["suggestion"] = "前端任务超时。建议：拆分为更小的任务"
    if max_duration_s is not None:
        detail["max_duration_s"] = max_duration_s
        detail["suggestion"] = "前端任务总时长超时。建议：分阶段执行"
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
    return True


# ============================================================================
# 主工具函数
# ============================================================================

async def frontend_tool(
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
    """执行 Frontend UI/UX Engineer 任务

    调用 Gemini CLI (gemini-3-pro) 进行前端/UI 开发。

    **角色定位**：前端/UI 专家（设计师型开发者）
    - 🎨 界面设计和布局实现
    - 💄 样式和动效开发
    - 📱 响应式适配
    - ✨ UI 审查和改进

    **特点**：
    - 使用 gemini-3-pro 模型
    - 设计师视角：关注间距、色彩、微交互
    - 支持多技术栈：React/Vue/Svelte/HTML+Tailwind

    **使用场景**：
    - 新建页面或组件
    - 样式优化和动效开发
    - UI 审查和改进建议
    - 设计稿转代码

    **Prompt 模板**：
    ```
    创建一个 [页面类型] 页面：
    - 风格：[极简/玻璃拟态/便当盒/...]
    - 技术栈：[React/Vue/HTML+Tailwind]
    - 要求：[响应式/暗色模式/动效]
    ```
    """
    # 构建完整的 prompt（包含 System Prompt）
    full_prompt = f"{FRONTEND_SYSTEM_PROMPT}\n\n---\n\n{PROMPT}"
    
    # 初始化指标收集器
    metrics = MetricsCollector(tool="frontend", prompt=full_prompt, sandbox=sandbox)

    # 构建命令
    cmd = ["gemini"]
    cmd.extend(["--output-format", "stream-json"])

    # Frontend 默认 workspace-write（需要写入文件）
    if sandbox == "read-only":
        cmd.append("--sandbox")
    else:
        cmd.append("--yolo")

    # 使用配置的模型（默认 gemini-3-pro，更强的创意和代码能力）
    from omcc_mcp.config import get_agent_model
    model_to_use = get_agent_model("frontend")
    if model_to_use:
        cmd.extend(["--model", model_to_use])

    # 会话恢复
    if SESSION_ID:
        cmd.extend(["--resume", SESSION_ID])

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
            with safe_frontend_command(cmd, timeout=timeout, max_duration=max_duration, prompt=full_prompt, cwd=cd) as gen:
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
                                err_message += "\n\n[frontend error] " + error_msg
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
                "tool": "frontend",
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
            err_message = "未能获取 Frontend 执行结果。\n\n" + err_message

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
            "tool": "frontend",
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
            auth_hint = """请先登录 Gemini CLI。运行以下命令完成认证：
  gemini

然后在交互界面中选择 "Login with Google" 完成登录。

"""
            err_message = auth_hint + err_message

        result = {
            "success": False,
            "tool": "frontend",
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
