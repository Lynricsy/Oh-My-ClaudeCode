"""Looker 工具实现

多模态分析代理，用于分析 PDF、图片、视频、音频等媒体文件。
直接调用 Gemini API，使用 inlineData + base64 格式。

主要功能：
- 分析 PDF 文档，提取文本和结构
- 描述图片内容，识别 UI 元素
- 分析视频内容，描述场景和动作
- 分析音频内容，转录和描述
- 解释图表、架构图、流程图

重要限制：
- Looker 无法调用 MCP 工具
- Looker 只能读取指定的单个文件
- 不适合需要读取多个文件或执行命令的任务

后端：直接调用 Gemini API（需配置 api_key）
"""

from __future__ import annotations

import base64
import json
import mimetypes
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, Literal, Optional

import httpx
from pydantic import Field

from omcc_mcp.config import ConfigError, get_looker_config, validate_looker_config


# ============================================================================
# MIME 类型映射
# ============================================================================

# 支持的媒体类型及其 MIME 类型
SUPPORTED_MIME_TYPES = {
    # 图片
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    # PDF
    ".pdf": "application/pdf",
    # 视频
    ".mp4": "video/mp4",
    ".mpeg": "video/mpeg",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".3gp": "video/3gpp",
    # 音频
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".wma": "audio/x-ms-wma",
}

# 文件大小限制（字节）
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB（base64 后约 27MB）


# ============================================================================
# 错误类型枚举
# ============================================================================

class ErrorKind:
    """结构化错误类型枚举"""
    TIMEOUT = "timeout"
    CONFIG_ERROR = "config_error"
    FILE_NOT_FOUND = "file_not_found"
    FILE_TOO_LARGE = "file_too_large"
    UNSUPPORTED_FORMAT = "unsupported_format"
    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"
    EMPTY_RESULT = "empty_result"
    UNEXPECTED_EXCEPTION = "unexpected_exception"


# ============================================================================
# 指标收集
# ============================================================================

class MetricsCollector:
    """指标收集器"""

    def __init__(self, tool: str, prompt: str, file_path: str):
        self.tool = tool
        self.prompt_chars = len(prompt)
        self.prompt_lines = prompt.count('\n') + 1
        self.file_path = file_path
        self.file_size_bytes = 0
        self.ts_start = datetime.now(timezone.utc)
        self.ts_end: Optional[datetime] = None
        self.duration_ms: int = 0
        self.success: bool = False
        self.error_kind: Optional[str] = None
        self.retries: int = 0
        self.result_chars: int = 0
        self.result_lines: int = 0
        self.prompt_tokens: int = 0
        self.response_tokens: int = 0
        self.total_tokens: int = 0

    def finish(
        self,
        success: bool,
        error_kind: Optional[str] = None,
        result: str = "",
        retries: int = 0,
        prompt_tokens: int = 0,
        response_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """完成指标收集"""
        self.ts_end = datetime.now(timezone.utc)
        self.duration_ms = int((self.ts_end - self.ts_start).total_seconds() * 1000)
        self.success = success
        self.error_kind = error_kind
        self.result_chars = len(result)
        self.result_lines = result.count('\n') + 1 if result else 0
        self.retries = retries
        self.prompt_tokens = prompt_tokens
        self.response_tokens = response_tokens
        self.total_tokens = total_tokens

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "ts_start": self.ts_start.isoformat() if self.ts_start else None,
            "ts_end": self.ts_end.isoformat() if self.ts_end else None,
            "duration_ms": self.duration_ms,
            "tool": self.tool,
            "success": self.success,
            "error_kind": self.error_kind,
            "retries": self.retries,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "prompt_chars": self.prompt_chars,
            "prompt_lines": self.prompt_lines,
            "result_chars": self.result_chars,
            "result_lines": self.result_lines,
            "prompt_tokens": self.prompt_tokens,
            "response_tokens": self.response_tokens,
            "total_tokens": self.total_tokens,
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
| **视频** | 描述场景、动作、对话、关键帧 |
| **音频** | 转录内容、识别说话者、描述音效 |
| **图表** | 解释数据趋势、关系、关键数据点 |
| **架构图** | 解释组件关系、数据流、系统边界 |
| **截图** | 识别错误信息、UI 状态、功能区域 |

## 工作方式

1. 接收文件和分析目标
2. 深入分析文件内容
3. 只返回与目标相关的信息
4. 主代理不处理原始文件，你节省上下文 token

## 重要限制

⚠️ **你无法调用任何 MCP 工具**
⚠️ **你只能分析当前这一个文件**
⚠️ **你无法读取其他文件或执行命令**

如果分析目标需要：
- 读取多个文件 → 告知用户需要分别调用
- 执行命令或脚本 → 告知用户需要使用其他工具
- 访问网络或数据库 → 告知用户你无法做到

## 输出规则

- 直接返回提取的信息，无需前言
- 如果未找到信息，明确说明缺少什么
- 匹配请求的语言
- 在目标上详尽，在其他方面简洁

## 输出格式

```
<analysis>
**文件类型**: [PDF/图片/视频/音频/图表/架构图/截图]
**分析目标**: [用户请求提取的内容]
</analysis>

<extracted>
[提取的具体内容]
- 如果是 PDF：文本、表格、结构
- 如果是图片：描述、UI 元素
- 如果是视频：场景描述、关键帧
- 如果是音频：转录内容、音效描述
- 如果是图表：数据、趋势
</extracted>

<summary>
[简要总结，便于主代理使用]
</summary>
```

---

你的输出直接传递给主代理继续工作。"""


# ============================================================================
# 辅助函数
# ============================================================================

def get_mime_type(file_path: Path) -> Optional[str]:
    """获取文件的 MIME 类型"""
    suffix = file_path.suffix.lower()
    if suffix in SUPPORTED_MIME_TYPES:
        return SUPPORTED_MIME_TYPES[suffix]
    # 尝试使用 mimetypes 模块
    mime_type, _ = mimetypes.guess_type(str(file_path))
    return mime_type


def is_supported_file(file_path: Path) -> bool:
    """检查文件是否支持分析"""
    mime_type = get_mime_type(file_path)
    if not mime_type:
        return False
    # 检查是否为支持的媒体类型
    return any(
        mime_type.startswith(prefix)
        for prefix in ["image/", "video/", "audio/", "application/pdf"]
    )


def get_file_category(mime_type: str) -> str:
    """根据 MIME 类型获取文件分类"""
    if mime_type.startswith("image/"):
        return "图片"
    elif mime_type.startswith("video/"):
        return "视频"
    elif mime_type.startswith("audio/"):
        return "音频"
    elif mime_type == "application/pdf":
        return "PDF"
    return "未知"


def encode_file_to_base64(file_path: Path) -> str:
    """将文件编码为 base64"""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _build_error_detail(
    message: str,
    file_path: Optional[str] = None,
    file_size: Optional[int] = None,
    mime_type: Optional[str] = None,
    api_status: Optional[int] = None,
    retries: int = 0,
) -> Dict[str, Any]:
    """构建结构化错误详情"""
    detail: Dict[str, Any] = {"message": message}
    if file_path:
        detail["file_path"] = file_path
    if file_size is not None:
        detail["file_size_bytes"] = file_size
        detail["file_size_mb"] = round(file_size / (1024 * 1024), 2)
    if mime_type:
        detail["mime_type"] = mime_type
    if api_status is not None:
        detail["api_status"] = api_status
    if retries > 0:
        detail["retries"] = retries
    return detail


# ============================================================================
# Gemini API 调用
# ============================================================================

async def call_gemini_api(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    file_base64: str,
    mime_type: str,
    timeout: int = 120,
) -> Dict[str, Any]:
    """调用 Gemini API 进行多模态分析

    Args:
        base_url: API 基础 URL
        api_key: API Key
        model: 模型名称
        prompt: 分析提示词
        file_base64: 文件的 base64 编码
        mime_type: 文件的 MIME 类型
        timeout: 超时时间（秒）

    Returns:
        API 响应结果
    """
    # 构建请求 URL
    url = f"{base_url.rstrip('/')}/v1beta/models/{model}:generateContent"

    # 构建请求头
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 构建请求体（Gemini 原生格式）
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": prompt
                    },
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": file_base64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 8192
        },
        "systemInstruction": {
            "parts": [
                {
                    "text": LOOKER_SYSTEM_PROMPT
                }
            ]
        }
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
        return {
            "status_code": response.status_code,
            "response": response.json() if response.status_code == 200 else None,
            "error": response.text if response.status_code != 200 else None,
        }


def parse_gemini_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """解析 Gemini API 响应

    Args:
        response: API 响应

    Returns:
        解析后的结果，包含 text, prompt_tokens, response_tokens, total_tokens
    """
    if not response.get("response"):
        return {
            "text": "",
            "prompt_tokens": 0,
            "response_tokens": 0,
            "total_tokens": 0,
        }

    result = response["response"]
    candidates = result.get("candidates", [])
    text = ""

    if candidates:
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if parts:
            text = parts[0].get("text", "")

    # 提取 token 使用统计
    usage = result.get("usageMetadata", {})
    prompt_tokens = usage.get("promptTokenCount", 0)
    response_tokens = usage.get("candidatesTokenCount", 0)
    total_tokens = usage.get("totalTokenCount", 0)

    return {
        "text": text,
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "total_tokens": total_tokens,
    }


# ============================================================================
# 主工具函数
# ============================================================================

async def looker_tool(
    file_path: Annotated[str, "要分析的媒体文件路径（PDF/图片/视频/音频等）"],
    goal: Annotated[str, "分析目标，描述需要从文件中提取什么信息"],
    cd: Annotated[Path, "工作目录"],
    sandbox: Annotated[
        Literal["read-only", "workspace-write", "danger-full-access"],
        Field(description="沙箱策略，Looker 默认只读"),
    ] = "read-only",
    SESSION_ID: Annotated[str, "会话 ID，用于多轮对话"] = "",
    return_all_messages: Annotated[bool, "是否返回完整消息"] = False,
    return_metrics: Annotated[bool, "是否在返回值中包含指标数据"] = False,
    timeout: Annotated[int, "API 超时（秒），默认 120 秒"] = 120,
    max_duration: Annotated[int, "保留参数，未使用"] = 3600,
    max_retries: Annotated[int, "最大重试次数，默认 1"] = 1,
    log_metrics: Annotated[bool, "是否将指标输出到 stderr"] = False,
) -> Dict[str, Any]:
    """执行 Looker 多模态分析任务

    直接调用 Gemini API 进行媒体文件分析。

    **角色定位**：多模态分析专家
    - 📄 PDF 分析：提取文本、表格、结构
    - 🖼️ 图片分析：描述内容、识别 UI 元素
    - 🎬 视频分析：描述场景、动作、对话
    - 🔊 音频分析：转录内容、识别说话者
    - 📊 图表分析：解释数据趋势和关系
    - 🏗️ 架构图分析：解释组件关系和数据流
    - 📸 截图分析：识别错误信息、UI 状态

    **重要限制**：
    - ⚠️ Looker 无法调用 MCP 工具
    - ⚠️ Looker 只能读取指定的单个文件
    - ⚠️ 不适合需要读取多个文件或执行命令的任务

    **后端**：直接调用 Gemini API（需配置 api_key）

    **使用场景**：
    - "分析这个 PDF 文档的第二章"
    - "描述这个 UI 截图中的错误信息"
    - "解释这个架构图的数据流"
    - "分析这个视频的主要内容"
    - "转录这段音频的对话"

    **Prompt 模板**：
    ```
    file_path: "/path/to/file.pdf"
    goal: "提取文档中关于用户认证的所有内容"
    ```
    """
    # 构建完整的分析 prompt
    full_prompt = f"请分析以下文件：\n\n**分析目标**: {goal}"

    # 初始化指标收集器
    metrics = MetricsCollector(tool="looker", prompt=full_prompt, file_path=file_path)

    # 生成或复用会话 ID
    session_id = SESSION_ID if SESSION_ID else str(uuid.uuid4())

    # 解析文件路径
    file_full_path = cd / file_path if not Path(file_path).is_absolute() else Path(file_path)

    # 检查文件是否存在
    if not file_full_path.exists():
        metrics.finish(success=False, error_kind=ErrorKind.FILE_NOT_FOUND)
        if log_metrics:
            metrics.log_to_stderr()

        return {
            "success": False,
            "tool": "looker",
            "error": f"文件不存在: {file_full_path}",
            "error_kind": ErrorKind.FILE_NOT_FOUND,
            "error_detail": _build_error_detail(
                f"文件不存在: {file_full_path}",
                file_path=str(file_full_path),
            ),
        }

    # 检查文件大小
    file_size = file_full_path.stat().st_size
    metrics.file_size_bytes = file_size

    if file_size > MAX_FILE_SIZE:
        metrics.finish(success=False, error_kind=ErrorKind.FILE_TOO_LARGE)
        if log_metrics:
            metrics.log_to_stderr()

        return {
            "success": False,
            "tool": "looker",
            "error": f"文件过大: {file_size / (1024 * 1024):.2f}MB，最大支持 {MAX_FILE_SIZE / (1024 * 1024):.0f}MB",
            "error_kind": ErrorKind.FILE_TOO_LARGE,
            "error_detail": _build_error_detail(
                f"文件过大，超过 {MAX_FILE_SIZE / (1024 * 1024):.0f}MB 限制",
                file_path=str(file_full_path),
                file_size=file_size,
            ),
        }

    # 获取 MIME 类型
    mime_type = get_mime_type(file_full_path)
    if not mime_type or not is_supported_file(file_full_path):
        metrics.finish(success=False, error_kind=ErrorKind.UNSUPPORTED_FORMAT)
        if log_metrics:
            metrics.log_to_stderr()

        supported_formats = ", ".join(sorted(SUPPORTED_MIME_TYPES.keys()))
        return {
            "success": False,
            "tool": "looker",
            "error": f"不支持的文件格式: {file_full_path.suffix}",
            "error_kind": ErrorKind.UNSUPPORTED_FORMAT,
            "error_detail": _build_error_detail(
                f"不支持的文件格式。支持的格式: {supported_formats}",
                file_path=str(file_full_path),
                mime_type=mime_type,
            ),
        }

    # 获取配置
    try:
        validate_looker_config()
        looker_config = get_looker_config()
    except ConfigError as e:
        metrics.finish(success=False, error_kind=ErrorKind.CONFIG_ERROR)
        if log_metrics:
            metrics.log_to_stderr()

        return {
            "success": False,
            "tool": "looker",
            "error": str(e),
            "error_kind": ErrorKind.CONFIG_ERROR,
            "error_detail": _build_error_detail(str(e)),
        }

    base_url = looker_config["base_url"]
    api_key = looker_config["api_key"]
    model = looker_config["model"]

    # 编码文件
    try:
        file_base64 = encode_file_to_base64(file_full_path)
    except Exception as e:
        metrics.finish(success=False, error_kind=ErrorKind.UNEXPECTED_EXCEPTION)
        if log_metrics:
            metrics.log_to_stderr()

        return {
            "success": False,
            "tool": "looker",
            "error": f"文件读取失败: {e}",
            "error_kind": ErrorKind.UNEXPECTED_EXCEPTION,
            "error_detail": _build_error_detail(
                f"文件读取失败: {e}",
                file_path=str(file_full_path),
            ),
        }

    # 执行 API 调用（支持重试）
    retries = 0
    last_error: Optional[str] = None
    result_text = ""
    prompt_tokens = 0
    response_tokens = 0
    total_tokens = 0

    file_category = get_file_category(mime_type)

    while retries <= max_retries:
        try:
            response = await call_gemini_api(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt=full_prompt,
                file_base64=file_base64,
                mime_type=mime_type,
                timeout=timeout,
            )

            if response["status_code"] == 200:
                parsed = parse_gemini_response(response)
                result_text = parsed["text"]
                prompt_tokens = parsed["prompt_tokens"]
                response_tokens = parsed["response_tokens"]
                total_tokens = parsed["total_tokens"]

                if result_text:
                    # 成功
                    metrics.finish(
                        success=True,
                        result=result_text,
                        retries=retries,
                        prompt_tokens=prompt_tokens,
                        response_tokens=response_tokens,
                        total_tokens=total_tokens,
                    )
                    if log_metrics:
                        metrics.log_to_stderr()

                    result: Dict[str, Any] = {
                        "success": True,
                        "tool": "looker",
                        "SESSION_ID": session_id,
                        "file_analyzed": str(file_full_path),
                        "file_type": file_category,
                        "result": result_text,
                        "duration": metrics.format_duration(),
                        "token_usage": {
                            "prompt": prompt_tokens,
                            "response": response_tokens,
                            "total": total_tokens,
                        },
                    }

                    if return_metrics:
                        result["metrics"] = metrics.to_dict()

                    return result
                else:
                    last_error = "API 返回空响应"
            else:
                last_error = f"API 错误 (HTTP {response['status_code']}): {response['error']}"

        except httpx.TimeoutException:
            last_error = f"API 请求超时 ({timeout}s)"
        except httpx.NetworkError as e:
            last_error = f"网络错误: {e}"
        except Exception as e:
            last_error = f"意外错误: {type(e).__name__}: {e}"

        retries += 1
        if retries <= max_retries:
            time.sleep(0.5 * (2 ** (retries - 1)))  # 指数退避

    # 所有重试都失败
    error_kind = ErrorKind.API_ERROR
    if "超时" in (last_error or ""):
        error_kind = ErrorKind.TIMEOUT
    elif "网络" in (last_error or ""):
        error_kind = ErrorKind.NETWORK_ERROR
    elif "空响应" in (last_error or ""):
        error_kind = ErrorKind.EMPTY_RESULT

    metrics.finish(
        success=False,
        error_kind=error_kind,
        retries=retries - 1,
    )
    if log_metrics:
        metrics.log_to_stderr()

    return {
        "success": False,
        "tool": "looker",
        "error": last_error or "未知错误",
        "error_kind": error_kind,
        "error_detail": _build_error_detail(
            last_error or "未知错误",
            file_path=str(file_full_path),
            file_size=file_size,
            mime_type=mime_type,
            retries=retries - 1,
        ),
        "duration": metrics.format_duration(),
    }
