from dataclasses import dataclass
from enum import Enum
import json
from typing import List, Union


@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = None


@dataclass
class ThinkingBlock:
    type: str = "thinking"
    thinking: str = ""


ContentBlock = Union[TextBlock, ToolUseBlock, ThinkingBlock]


@dataclass
class ParsedMessage:
    content_blocks: List[ContentBlock]
    stop_reason: str
    tokens_used: int

    def text_content(self) -> str:
        texts = [b.text for b in self.content_blocks
                 if isinstance(b, TextBlock)]
        return "".join(texts)

    def tool_calls(self) -> List[ToolUseBlock]:
        return [b for b in self.content_blocks
                if isinstance(b, ToolUseBlock)]


class ResponseParser:
    @staticmethod
    def parse_response(raw_response: dict) -> ParsedMessage:
        content_blocks = []
        for block in raw_response.get("content", []):
            block_type = block.get("type")
            if block_type == "text":
                content_blocks.append(TextBlock(text=block.get("text", "")))
            elif block_type == "tool_use":
                input_data = block.get("input", {})
                if isinstance(input_data, str):
                    try:
                        input_data = json.loads(input_data)
                    except Exception:
                        input_data = {}
                content_blocks.append(ToolUseBlock(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    input=input_data
                ))
        return ParsedMessage(
            content_blocks=content_blocks,
            stop_reason=raw_response.get("stop_reason", "end_turn"),
            tokens_used=(
                raw_response.get("usage", {}).get("input_tokens", 0) +
                raw_response.get("usage", {}).get("output_tokens", 0)
            )
        )
