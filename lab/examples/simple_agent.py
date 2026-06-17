#!/usr/bin/env python3
"""
MiniHarness 最小智能体示例

这是一个完整可运行的 Agent，演示了 MiniHarness 的核心概念：
  - 运行时循环（agentic loop）
  - 工具注册与执行
  - 流式事件输出
  - 多轮工具调用

兼容所有 OpenAI API 格式的 LLM 服务（OpenAI、DeepSeek、Qwen、Ollama 等）。

使用方式：
  # OpenAI
  read -rsp "LLM_API_KEY: " LLM_API_KEY; echo; export LLM_API_KEY
  export LLM_BASE_URL="https://api.openai.com/v1"
  export LLM_MODEL="gpt-4o-mini"
  python examples/simple_agent.py "读取 README.md 并总结项目"

  # DeepSeek
  read -rsp "LLM_API_KEY: " LLM_API_KEY; echo; export LLM_API_KEY
  export LLM_BASE_URL="https://api.deepseek.com"
  export LLM_MODEL="deepseek-chat"
  python examples/simple_agent.py "读取 pyproject.toml 并总结依赖"

  # Ollama 本地模型（无需 API Key）
  export LLM_BASE_URL="http://localhost:11434/v1"
  export LLM_MODEL="qwen2.5:7b"
  export LLM_API_KEY="ollama"
  python examples/simple_agent.py "what is 2+2?"
"""

import asyncio
import json
import os
import sys

# 确保 mini_harness 可被导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mini_harness.tools.builtin import FileReadTool
from mini_harness.tools.registry import ToolRegistry
from mini_harness.utils.config import get_config

# ============================================================================
# 1. 配置（统一从 Config 单例读取，支持 .env 文件和环境变量）
# ============================================================================

cfg = get_config()
LLM_API_KEY = cfg.LLM_API_KEY
LLM_BASE_URL = cfg.LLM_BASE_URL
LLM_MODEL = cfg.LLM_MODEL
MAX_TURNS = cfg.MAX_TURNS

SYSTEM_PROMPT = """你是 MiniHarness，一个有帮助的 AI 助手。
这个最小示例默认只开放只读工具，避免演示代码直接执行命令或写入文件：
- file_read: 读取文件内容

当你需要执行操作时，使用工具调用而不是直接回复。
完成任务后，用自然语言总结结果。"""


# ============================================================================
# 2. OpenAI 兼容的 LLM 客户端（轻量封装）
# ============================================================================


class LLMClient:
    """轻量级 OpenAI API 兼容客户端

    不依赖 openai SDK，直接使用 httpx 发送请求，
    这样可以更清楚地展示 API 交互的细节。
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def chat_completion(
        self,
        messages: list,
        tools: list = None,
        stream: bool = False,
    ) -> dict:
        """调用 Chat Completion API"""
        import httpx

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
            "stream": stream,
        }
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient(timeout=120) as client:
            if stream:
                return await self._stream_request(client, url, headers, body)
            else:
                resp = await client.post(url, headers=headers, json=body)
                resp.raise_for_status()
                return resp.json()

    async def _stream_request(self, client, url, headers, body):
        """处理流式响应，合并为完整的 choice"""
        content_parts = []
        tool_calls_map = {}  # index -> {id, name, arguments_parts}
        finish_reason = None

        async with client.stream("POST", url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choice = chunk.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason") or finish_reason

                # 文本内容
                if delta.get("content"):
                    content_parts.append(delta["content"])
                    # 实时输出到终端（流式体验）
                    print(delta["content"], end="", flush=True)

                # 工具调用（增量合并）
                if delta.get("tool_calls"):
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        entry = tool_calls_map[idx]
                        if tc_delta.get("id"):
                            entry["id"] = tc_delta["id"]
                        func = tc_delta.get("function", {})
                        if func.get("name"):
                            entry["function"]["name"] = func["name"]
                        if func.get("arguments"):
                            entry["function"]["arguments"] += func["arguments"]

        # 如果有文本输出，换行
        if content_parts:
            print()

        # 组装为与非流式响应相同的格式
        message = {"role": "assistant", "content": "".join(content_parts) or None}
        if tool_calls_map:
            message["tool_calls"] = [tool_calls_map[i] for i in sorted(tool_calls_map)]

        return {
            "choices": [
                {
                    "message": message,
                    "finish_reason": finish_reason or "stop",
                }
            ],
        }


# ============================================================================
# 3. 简易 Agent 运行时
# ============================================================================


class SimpleAgent:
    """一个最小但完整的 Agent 实现

    核心循环：
      用户输入 → LLM 推理 → 工具调用？ → 执行工具 → 反馈结果 → 继续推理…
    """

    def __init__(self, llm: LLMClient, tool_registry: ToolRegistry):
        self.llm = llm
        self.tool_registry = tool_registry
        self.messages = []
        self.max_turns = MAX_TURNS

    def _get_tools_schema(self) -> list:
        """获取 OpenAI function calling 格式的工具列表"""
        tools = []
        for schema in self.tool_registry.list_tools():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": schema["name"],
                        "description": schema["description"],
                        "parameters": schema["input_schema"],
                    },
                }
            )
        return tools

    async def run(self, user_input: str) -> str:
        """运行 Agent 循环"""

        # 初始化消息列表
        self.messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        tools_schema = self._get_tools_schema()
        print(f"\n🤖 Agent 启动（模型: {self.llm.model}，工具: {len(tools_schema)} 个）")
        print(f"📝 用户: {user_input}\n")

        for turn in range(self.max_turns):
            print(f"--- Turn {turn + 1} ---")

            # Step 1: 调用 LLM（流式）
            response = await self.llm.chat_completion(
                messages=self.messages,
                tools=tools_schema if tools_schema else None,
                stream=True,
            )

            choice = response["choices"][0]
            assistant_msg = choice["message"]
            finish_reason = choice.get("finish_reason", "stop")

            # 将 assistant 消息加入历史
            self.messages.append(assistant_msg)

            # Step 2: 检查是否有工具调用
            tool_calls = assistant_msg.get("tool_calls", [])

            if not tool_calls:
                # 没有工具调用，Agent 结束
                print(f"\n✅ Agent 完成（共 {turn + 1} 轮）")
                return assistant_msg.get("content", "")

            # Step 3: 执行所有工具调用
            print(f"\n🔧 执行 {len(tool_calls)} 个工具调用:")
            for tc in tool_calls:
                func = tc["function"]
                tool_name = func["name"]
                try:
                    arguments = (
                        json.loads(func["arguments"])
                        if isinstance(func["arguments"], str)
                        else func["arguments"]
                    )
                except json.JSONDecodeError:
                    arguments = {}

                print(f"   → {tool_name}({json.dumps(arguments, ensure_ascii=False)[:80]})")

                # 执行工具
                tool = self.tool_registry.get(tool_name)
                if tool:
                    result = await tool.call(arguments)
                    tool_output = result.content
                    if not result.success:
                        tool_output = f"[ERROR] {result.content}"
                else:
                    tool_output = f"[ERROR] 工具 '{tool_name}' 不存在"

                # 截断过长的输出
                if len(tool_output) > 8000:
                    tool_output = tool_output[:8000] + "\n... [输出已截断]"

                print(f"   ← ({len(tool_output)} 字符)")

                # 将工具结果加入消息历史
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_output,
                    }
                )

            print()

        print(f"⚠️  达到最大轮数 ({self.max_turns})")
        return self.messages[-1].get("content", "")


# ============================================================================
# 4. 入口
# ============================================================================


async def main():
    # 检查配置
    if not LLM_API_KEY:
        print("❌ 请设置 LLM_API_KEY 环境变量")
        print()
        print("示例（DeepSeek）：")
        print('  read -rsp "LLM_API_KEY: " LLM_API_KEY; echo; export LLM_API_KEY')
        print('  export LLM_BASE_URL="https://api.deepseek.com"')
        print('  export LLM_MODEL="deepseek-chat"')
        print()
        print("示例（Ollama 本地）：")
        print('  export LLM_API_KEY="ollama"')
        print('  export LLM_BASE_URL="http://localhost:11434/v1"')
        print('  export LLM_MODEL="qwen2.5:7b"')
        sys.exit(1)

    # 获取用户输入
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        user_input = input("请输入任务: ")

    # 初始化工具注册表
    registry = ToolRegistry()
    registry.register(FileReadTool())

    # 初始化 LLM 客户端
    llm = LLMClient(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, model=LLM_MODEL)

    # 创建并运行 Agent
    agent = SimpleAgent(llm=llm, tool_registry=registry)
    final_response = await agent.run(user_input)

    print(f"\n{'='*60}")
    print(f"最终回复:\n{final_response}")


if __name__ == "__main__":
    asyncio.run(main())
