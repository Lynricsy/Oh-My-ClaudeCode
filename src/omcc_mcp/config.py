"""配置加载模块

优先级：配置文件 > 环境变量
配置文件路径：~/.omcc-mcp/config.toml

支持配置：
- coder: claude CLI 后端配置（API Token, Base URL, Model）
- advisor/frontend/librarian/looker: OpenCode CLI 模型配置
- chore: OpenCode 模型配置
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """配置错误"""
    pass


# ============================================================================
# 默认模型配置
# ============================================================================

DEFAULT_MODELS = {
    "coder": "glm-4.7",                          # Coder 默认使用 GLM-4.7
    "advisor": "google/gemini-3-pro-preview",     # Advisor 默认模型 (OpenCode 格式)
    "frontend": "google/gemini-3-pro-preview",   # Frontend 默认使用 Advisor 3 Pro
    "librarian": "google/gemini-3-flash-preview", # Librarian 默认使用 Advisor 3 Flash
    "looker": "google/gemini-3-flash-preview",   # Looker 默认使用 Advisor 3 Flash
    "chore": None,                               # Chore 使用 OpenCode 默认模型
}

# Coder 默认配置
DEFAULT_CODER_EXTENDED_CONTEXT = False  # 默认不启用 1m 上下文


def get_config_path() -> Path:
    """获取配置文件路径"""
    return Path.home() / ".omcc-mcp" / "config.toml"


def load_config() -> dict[str, Any]:
    """加载配置，优先级：配置文件 > 环境变量

    Returns:
        配置字典

    Raises:
        ConfigError: 配置文件格式错误时抛出
    """
    config_path = get_config_path()

    # 优先读取配置文件
    if config_path.exists():
        try:
            with open(config_path, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigError(f"配置文件格式错误：{e}")

    # 兜底：从环境变量读取 Coder 配置
    if os.environ.get("CODER_API_TOKEN"):
        return {
            "coder": {
                "api_token": os.environ["CODER_API_TOKEN"],
                "base_url": os.environ.get(
                    "CODER_BASE_URL",
                    "https://open.bigmodel.cn/api/anthropic"
                ),
                "model": os.environ.get("CODER_MODEL", DEFAULT_MODELS["coder"]),
            }
        }

    # 返回空配置（允许使用默认值）
    return {}


def get_agent_model(agent: str, config: dict[str, Any] | None = None) -> str | None:
    """获取代理的模型配置

    Args:
        agent: 代理名称 (coder, advisor, frontend, librarian, looker, chore)
        config: 配置字典，如果为 None 则自动加载

    Returns:
        模型名称，如果未配置则返回默认值
    """
    if config is None:
        config = get_config()

    agent_config = config.get(agent, {})
    
    # 优先使用配置的模型
    if isinstance(agent_config, dict) and "model" in agent_config:
        return agent_config["model"]
    
    # 使用默认模型
    return DEFAULT_MODELS.get(agent)


def get_coder_config_or_none() -> dict[str, Any] | None:
    """获取 Coder 配置，如果未配置则返回 None（不抛出异常）

    Returns:
        Coder 配置字典，或 None
    """
    try:
        config = get_config()
        coder_config = config.get("coder", {})
        if coder_config.get("api_token"):
            return coder_config
        return None
    except ConfigError:
        return None


def get_coder_extended_context(config: dict[str, Any] | None = None) -> bool:
    """获取 Coder 是否启用 1m 扩展上下文

    Args:
        config: 配置字典，如果为 None 则自动加载

    Returns:
        是否启用 1m 扩展上下文
    """
    if config is None:
        config = get_config()

    coder_config = config.get("coder", {})
    if isinstance(coder_config, dict):
        return coder_config.get("extended_context", DEFAULT_CODER_EXTENDED_CONTEXT)
    return DEFAULT_CODER_EXTENDED_CONTEXT


def get_config_example() -> str:
    """获取配置文件示例"""
    return '''# ~/.omcc-mcp/config.toml
# Oh-My-ClaudeCode 配置文件

# ============================================================================
# Coder 配置（使用 claude CLI + 可配置后端）
# ============================================================================
[coder]
api_token = "your-api-token"  # 必填：API Token
base_url = "https://open.bigmodel.cn/api/anthropic"  # API 地址
model = "glm-4.7"  # 模型名称
extended_context = false  # 是否启用 1m 扩展上下文（通过 [1m] 后缀）

# 可选：额外环境变量
[coder.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"

# ============================================================================
# OpenCode CLI 相关代理模型配置
# ============================================================================
[advisor]
model = "gemini-3-pro"  # Advisor 默认模型

[frontend]
model = "gemini-3-pro"  # Frontend 前端/UI 代理

[librarian]
model = "gemini-3-flash"  # Librarian 研究代理（快速、低成本）

[looker]
model = "gemini-3-flash"  # Looker 多模态代理（快速、低成本）

# ============================================================================
# OpenCode 相关代理配置
# ============================================================================
[chore]
model = "anthropic/claude-sonnet-4-20250514"  # Chore 杂务代理
'''


def build_coder_env(config: dict[str, Any]) -> dict[str, str]:
    """构建 Coder 调用所需的环境变量

    Args:
        config: 配置字典

    Returns:
        包含所有环境变量的字典

    Raises:
        ConfigError: Coder 配置无效时抛出
    """
    # 验证 Coder 配置
    validate_coder_config(config)

    coder_config = config.get("coder", {})
    model = coder_config.get("model", DEFAULT_MODELS["coder"])

    # 如果启用 1m 扩展上下文，添加 [1m] 后缀
    extended_context = get_coder_extended_context(config)
    if extended_context and not model.endswith("[1m]"):
        model = f"{model}[1m]"

    env = os.environ.copy()

    # API 认证
    env["ANTHROPIC_AUTH_TOKEN"] = coder_config.get("api_token", "")
    env["ANTHROPIC_BASE_URL"] = coder_config.get(
        "base_url",
        "https://open.bigmodel.cn/api/anthropic"
    )

    # 所有模型别名都映射到配置的模型
    env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model
    env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model
    env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = model
    env["CLAUDE_CODE_SUBAGENT_MODEL"] = model

    # 用户自定义的额外环境变量
    for key, value in coder_config.get("env", {}).items():
        env[key] = str(value)

    return env


def validate_coder_config(config: dict[str, Any]) -> None:
    """验证 Coder 配置有效性（仅在使用 Coder 时调用）

    Args:
        config: 配置字典

    Raises:
        ConfigError: 配置无效时抛出
    """
    coder_config = config.get("coder", {})

    if not coder_config.get("api_token"):
        raise ConfigError(
            f"Coder 工具需要配置 API Token！\n\n"
            f"请创建配置文件：{get_config_path()}\n\n"
            f"配置文件示例：\n{get_config_example()}\n"
            f"或设置环境变量 CODER_API_TOKEN"
        )

    if not coder_config.get("base_url"):
        raise ConfigError("Coder 配置缺少 base_url")


# 全局配置缓存
_config_cache: dict[str, Any] | None = None


def get_config() -> dict[str, Any]:
    """获取配置（带缓存）

    首次调用时加载配置，后续调用直接返回缓存

    Returns:
        配置字典
    """
    global _config_cache

    if _config_cache is None:
        _config_cache = load_config()

    return _config_cache


def reset_config_cache() -> None:
    """重置配置缓存（主要用于测试）"""
    global _config_cache
    _config_cache = None
