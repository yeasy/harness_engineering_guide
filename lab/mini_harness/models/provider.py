"""
mini_harness/models/provider.py - 模型提供者抽象层

支持两种 Provider：
- ClaudeProvider：使用 Anthropic SDK
- OpenAIProvider：使用 OpenAI SDK（兼容所有 OpenAI API 格式的服务，
  如 OpenAI、DeepSeek、Qwen、Ollama、vLLM、LiteLLM 等）
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generator, List, Optional

# 延迟导入，避免未安装时直接报错
_anthropic = None
_openai = None


def _get_anthropic() -> Any:
    global _anthropic
    if _anthropic is None:
        import anthropic

        _anthropic = anthropic
    return _anthropic


def _get_openai() -> Any:
    global _openai
    if _openai is None:
        import openai

        _openai = openai
    return _openai


class ModelProviderType(Enum):
    CLAUDE = "claude"
    OPENAI = "openai"


@dataclass
class ModelConfig:
    """模型配置

    Args:
        provider: 模型提供者类型（CLAUDE 或 OPENAI）
        model_id: 模型名称（如 "gpt-4o", "deepseek-chat", "qwen-plus"）
        api_key: API 密钥
        base_url: API base URL（用于兼容服务，如 "https://api.deepseek.com"）
        timeout: 请求超时（秒）
        max_tokens: 最大生成 token 数
    """

    provider: ModelProviderType
    model_id: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 30
    max_tokens: int = 4096


class ProviderMessage:
    """Provider 层的简单消息对象，避免与 core/runtime Message 混淆"""

    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content


@dataclass
class ProviderResponse:
    """模型响应（非流式）"""

    content: str
    tokens_used: int
    model: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    stop_reason: str = "end_turn"


def _anthropic_tokens_used(usage: Any) -> int:
    return (
        getattr(usage, "input_tokens", 0)
        + getattr(usage, "cache_creation_input_tokens", 0)
        + getattr(usage, "cache_read_input_tokens", 0)
        + getattr(usage, "output_tokens", 0)
    )


class CircuitBreaker:
    """
    三态熔断器：closed -> open -> half-open -> closed
    - closed: 正常状态，所有请求通过
    - open: 故障状态，请求被拒绝
    - half-open: 恢复测试状态，需要多次成功才能关闭
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        reset_timeout: int = 60,
        success_threshold_half_open: int = 3,
    ):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.state = "closed"
        self.last_failure_time = None
        self.success_threshold_half_open = success_threshold_half_open
        self.success_count_half_open = 0

    def record_failure(self) -> None:
        """记录失败"""
        self.failure_count += 1
        self.success_count_half_open = 0

        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.last_failure_time = time.time()

    def record_success(self) -> None:
        """记录成功"""
        if self.state == "closed":
            self.failure_count = 0
        elif self.state == "half-open":
            self.success_count_half_open += 1
            if self.success_count_half_open >= self.success_threshold_half_open:
                self.state = "closed"
                self.failure_count = 0
                self.success_count_half_open = 0

    def is_available(self) -> bool:
        """检查服务是否可用"""
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "half-open"
                self.success_count_half_open = 0
                return True
            return False
        if self.state == "half-open":
            return True
        return False


# ============================================================================
# Provider 抽象基类
# ============================================================================


class BaseProvider(ABC):
    """模型 Provider 的抽象基类"""

    def __init__(self, config: ModelConfig):
        self.config = config

    @abstractmethod
    def complete(
        self, messages: List[ProviderMessage], tools: Optional[List[Dict]] = None
    ) -> ProviderResponse:
        """非流式请求"""
        pass

    @abstractmethod
    def stream(
        self, messages: List[ProviderMessage], tools: Optional[List[Dict]] = None
    ) -> Generator[str, None, None]:
        """流式请求（逐 token 输出文本）"""
        pass

    @abstractmethod
    def complete_with_tools(
        self, messages: List[ProviderMessage], tools: List[Dict]
    ) -> ProviderResponse:
        """带工具调用的请求"""
        pass


# ============================================================================
# Claude Provider（Anthropic SDK）
# ============================================================================


class ClaudeProvider(BaseProvider):
    """Anthropic Claude API Provider"""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        anthropic = _get_anthropic()
        self.client = anthropic.Anthropic(api_key=config.api_key)

    def complete(
        self, messages: List[ProviderMessage], tools: Optional[List[Dict]] = None
    ) -> ProviderResponse:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        kwargs = dict(
            model=self.config.model_id,
            max_tokens=self.config.max_tokens,
            messages=api_messages,
        )
        if tools:
            kwargs["tools"] = tools
        response = self.client.messages.create(**kwargs)

        # 解析 tool_calls
        tool_calls = []
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,
                    }
                )

        return ProviderResponse(
            content="".join(text_parts),
            tokens_used=_anthropic_tokens_used(response.usage),
            model=self.config.model_id,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
        )

    def complete_with_tools(
        self, messages: List[ProviderMessage], tools: List[Dict]
    ) -> ProviderResponse:
        return self.complete(messages, tools=tools)

    def stream(
        self, messages: List[ProviderMessage], tools: Optional[List[Dict]] = None
    ) -> Generator[str, None, None]:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        with self.client.messages.stream(
            model=self.config.model_id,
            max_tokens=self.config.max_tokens,
            messages=api_messages,
        ) as stream:
            for text in stream.text_stream:
                yield text


# ============================================================================
# OpenAI-Compatible Provider（支持 OpenAI、DeepSeek、Qwen、Ollama 等）
# ============================================================================


class OpenAIProvider(BaseProvider):
    """OpenAI API 兼容 Provider

    适用于所有兼容 OpenAI Chat Completion API 的服务：
    - OpenAI (GPT-4o, GPT-4o-mini, o3-mini ...)
    - DeepSeek (deepseek-chat, deepseek-reasoner)
    - 阿里通义千问 Qwen (qwen-plus, qwen-max)
    - Ollama 本地模型 (llama3, qwen2 ...)
    - vLLM / LiteLLM / LocalAI 等自部署服务

    使用方式：
        config = ModelConfig(
            provider=ModelProviderType.OPENAI,
            model_id="deepseek-chat",
            api_key="<LLM_API_KEY>",
            base_url="https://api.deepseek.com",  # 关键：指定 base_url
        )
    """

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        openai = _get_openai()
        kwargs = {"api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.timeout:
            kwargs["timeout"] = config.timeout
        self.client = openai.OpenAI(**kwargs)

    def complete(
        self, messages: List[ProviderMessage], tools: Optional[List[Dict]] = None
    ) -> ProviderResponse:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        kwargs = self._chat_completion_kwargs(
            model=self.config.model_id,
            messages=api_messages,
        )
        if tools:
            # 将 MiniHarness 工具格式转换为 OpenAI function calling 格式
            kwargs["tools"] = self._convert_tools(tools)

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        # 解析 tool_calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args,
                    }
                )

        return ProviderResponse(
            content=message.content or "",
            tokens_used=(
                (response.usage.prompt_tokens + response.usage.completion_tokens)
                if response.usage
                else 0
            ),
            model=self.config.model_id,
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason or "stop",
        )

    def complete_with_tools(
        self, messages: List[ProviderMessage], tools: List[Dict]
    ) -> ProviderResponse:
        return self.complete(messages, tools=tools)

    def stream(
        self, messages: List[ProviderMessage], tools: Optional[List[Dict]] = None
    ) -> Generator[str, None, None]:
        """流式输出（兼容 OpenAI response stream 格式）"""
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        kwargs = self._chat_completion_kwargs(
            model=self.config.model_id,
            messages=api_messages,
            stream=True,
        )
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = self.client.chat.completions.create(**kwargs)
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _chat_completion_kwargs(self, **kwargs) -> Dict[str, Any]:
        token_param = (
            "max_completion_tokens"
            if self._uses_reasoning_completion_tokens()
            else "max_tokens"
        )
        kwargs[token_param] = self.config.max_tokens
        return kwargs

    def _uses_reasoning_completion_tokens(self) -> bool:
        return self.config.base_url is None and self.config.model_id.startswith("o")

    @staticmethod
    def _convert_tools(tools: List[Dict]) -> List[Dict]:
        """将 MiniHarness 工具定义转换为 OpenAI function calling 格式

        MiniHarness 格式（同 Anthropic 格式）：
            {"name": "bash_exec", "description": "...", "input_schema": {...}}

        OpenAI 格式：
            {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
        """
        openai_tools = []
        for tool in tools:
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get(
                            "input_schema", {"type": "object", "properties": {}}
                        ),
                    },
                }
            )
        return openai_tools


# ============================================================================
# 统一工厂方法
# ============================================================================


def create_provider(config: ModelConfig) -> BaseProvider:
    """根据配置创建合适的 Provider"""
    if config.provider == ModelProviderType.CLAUDE:
        return ClaudeProvider(config)
    elif config.provider == ModelProviderType.OPENAI:
        return OpenAIProvider(config)
    else:
        raise ValueError(f"不支持的 provider 类型: {config.provider}")


# ============================================================================
# 模型选择引擎（带熔断器的故障转移）
# ============================================================================


class ModelSelectionEngine:
    """模型选择引擎，支持故障转移"""

    def __init__(self, primary: ModelConfig, fallback_chain: List[ModelConfig] = None):
        self.primary = primary
        self.fallback_chain = fallback_chain or []
        self.breakers = {}
        self._init_breakers()

    def _init_breakers(self) -> None:
        for config in [self.primary] + self.fallback_chain:
            self.breakers[config.model_id] = CircuitBreaker()

    def select_model(self) -> BaseProvider:
        """选择可用的模型 Provider"""
        candidates = [self.primary] + self.fallback_chain
        for config in candidates:
            breaker = self.breakers[config.model_id]
            if breaker.is_available():
                return create_provider(config)
        raise Exception("所有模型不可用")

    def mark_failure(self, model_id: str) -> None:
        if model_id in self.breakers:
            self.breakers[model_id].record_failure()

    def mark_success(self, model_id: str) -> None:
        if model_id in self.breakers:
            self.breakers[model_id].record_success()
