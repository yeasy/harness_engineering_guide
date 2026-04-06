"""配置管理

统一管理 MiniHarness 的全局配置，从环境变量 / .env 文件加载。
使用单例模式，全局只需调用 get_config() 即可。
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class Config:
    """全局配置（单例）"""

    _instance = None

    def __init__(self):
        # 加载 .env 文件（不覆盖已有环境变量）
        load_dotenv()

        # ---- LLM 配置（OpenAI 兼容 API） ----
        self.LLM_API_KEY = os.getenv("LLM_API_KEY", "")
        self.LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

        # ---- Anthropic Claude API（使用 ClaudeProvider 时需要） ----
        self.ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

        # ---- Agent 行为配置 ----
        self.MAX_TURNS = int(os.getenv("MAX_TURNS", "10"))
        self.MAX_STEPS = int(os.getenv("MAX_STEPS", "10"))
        self.EXECUTION_TIMEOUT_SECONDS = int(os.getenv("EXECUTION_TIMEOUT_SECONDS", "300"))

        # ---- 日志 ----
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def get_instance(cls) -> "Config":
        """单例模式获取配置"""
        if cls._instance is None:
            cls._instance = Config()
        return cls._instance

    @classmethod
    def reset(cls):
        """重置单例（测试用）"""
        cls._instance = None


def get_config() -> Config:
    """获取全局配置"""
    return Config.get_instance()
