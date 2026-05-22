"""
mini_harness/runtime/engine.py
智能体循环实现
"""

import uuid
from typing import AsyncIterator, Optional

from mini_harness.runtime.events import (
    AgentEndEvent,
    AgentStartEvent,
    ErrorEvent,
    Event,
    TextResponseEvent,
    ToolExecuteEvent,
    ToolResultEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from mini_harness.runtime.models import (
    AgentState,
    RuntimeMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from mini_harness.reliability.redaction import sanitize_observability_value


class RuntimeEngine:
    """MiniHarness 运行时引擎"""

    def __init__(self, tool_registry=None):
        self.tool_registry = tool_registry
        self.max_turns = 10
        self.token_budget = 4000  # 简化：每次推理最多 4k Token

    async def run(self, user_input: str) -> AsyncIterator[Event]:
        """运行 Agent，生成事件流"""

        yield AgentStartEvent(metadata={"input_length": len(user_input)})

        session_id = f"sess_{uuid.uuid4().hex[:8]}"
        state = AgentState(session_id=session_id)
        state.add_message(RuntimeMessage.user(user_input))

        for turn in range(self.max_turns):
            yield TurnStartEvent(metadata={"turn_number": turn})

            # 模拟推理：调用 LLM
            response = await self._infer(state)

            if response is None:
                yield ErrorEvent(metadata={"error": "Inference failed", "turn": turn})
                break

            state.add_message(response)
            safe_text = sanitize_observability_value("model_response", response.get_text()[:200])
            yield TextResponseEvent(metadata={"text_preview": safe_text})

            # 处理工具调用
            tool_calls = response.get_tool_calls()

            if tool_calls:
                tool_results = []
                for tool_use in tool_calls:
                    yield ToolExecuteEvent(
                        metadata={"tool_name": tool_use.name, "tool_id": tool_use.id}
                    )

                    result = await self._execute_tool(tool_use)
                    tool_results.append(result)

                    yield ToolResultEvent(
                        metadata={
                            "tool_id": tool_use.id,
                            "is_error": result.is_error,
                            "content_length": len(result.content),
                        }
                    )

                # 添加工具结果到状态
                for result in tool_results:
                    state.add_message(RuntimeMessage.tool_result(result))
            else:
                # 没有工具调用，循环结束
                break

            yield TurnEndEvent(metadata={"turn_number": turn, "has_tool_calls": bool(tool_calls)})

        yield AgentEndEvent(
            metadata={
                "session_id": session_id,
                "turn_count": state.current_turn,
                "final_response_preview": sanitize_observability_value(
                    "model_response",
                    state.messages[-1].get_text()[:200],
                ),
            }
        )

    async def _infer(self, state: AgentState) -> Optional[RuntimeMessage]:
        """模拟推理：返回模拟的 Assistant 消息"""
        # 在真实实现中，这里会调用实际的 LLM API

        last_message = state.messages[-1]
        if any(isinstance(block, ToolResultBlock) for block in last_message.content):
            tool_text = " ".join(
                block.content for block in last_message.content if isinstance(block, ToolResultBlock)
            )
            return RuntimeMessage.assistant([TextBlock(text=f"Tool result received: {tool_text}")])

        # 示例：根据最近一条用户文本输入生成不同的响应
        user_text = last_message.get_text()

        if "bash" in user_text.lower() or "command" in user_text.lower():
            # 建议执行 bash 命令
            return RuntimeMessage.assistant(
                [
                    TextBlock(text="I'll help you execute a bash command."),
                    ToolUseBlock(
                        name="bash_exec", input={"command": "echo 'Hello from MiniHarness'"}
                    ),
                ]
            )
        else:
            # 直接回复
            return RuntimeMessage.assistant(
                [TextBlock(text=f"You asked: {user_text}. How can I help?")]
            )

    async def _execute_tool(self, tool_use: ToolUseBlock) -> ToolResultBlock:
        """执行工具"""
        if self.tool_registry is None:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content="Tool registry not configured",
                is_error=True,
                error_type="ToolRegistryError",
            )

        tool = self.tool_registry.get(tool_use.name)

        if not tool:
            return ToolResultBlock(
                tool_use_id=tool_use.id,
                content=f"Tool '{tool_use.name}' not found",
                is_error=True,
                error_type="ToolNotFoundError",
            )

        try:
            result = await tool.call(tool_use.input)
            # Tool.call() 返回的是 ToolResult 数据类（见 core/tool.py）
            # 将其映射到 ToolResultBlock（携带字符串 content + 错误元数据）
            if hasattr(result, "success") and hasattr(result, "content"):
                return ToolResultBlock(
                    tool_use_id=tool_use.id,
                    content=str(result.content),
                    is_error=not result.success,
                    error_type=getattr(result, "error_type", None),
                )
            # 向后兼容：若工具直接返回字符串，按成功处理
            return ToolResultBlock(tool_use_id=tool_use.id, content=str(result), is_error=False)
        except Exception as e:
            return ToolResultBlock(
                tool_use_id=tool_use.id, content=str(e), is_error=True, error_type=type(e).__name__
            )
