from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional

from pydantic import ValidationError

from mini_harness.models.parser import ToolUseBlock


class ValidationResult(Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass
class ValidationReport:
    result: ValidationResult
    errors: List[str]
    suggestion: Optional[str] = None


class QualityToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name: str, handler, schema) -> None:
        self.tools[name] = {"handler": handler, "schema": schema, "enabled": True}

    def is_tool_available(self, name: str) -> bool:
        return name in self.tools and self.tools[name]["enabled"]

    def get_tool_schema(self, name: str) -> Optional[Any]:
        return self.tools.get(name, {}).get("schema")


class QualityGate:
    def __init__(self, registry: QualityToolRegistry):
        self.registry = registry

    def validate_tool_call(self, tool_call: ToolUseBlock) -> ValidationReport:
        errors = []

        # 检查 ID 和名称
        if not tool_call.id or not tool_call.name:
            errors.append("工具调用缺少 ID 或名称")
            return ValidationReport(result=ValidationResult.FAIL, errors=errors)

        # 检查工具存在性
        if not self.registry.is_tool_available(tool_call.name):
            errors.append(f"工具 '{tool_call.name}' 未注册")
            return ValidationReport(
                result=ValidationResult.FAIL,
                errors=errors,
                suggestion=f"可用工具: {list(self.registry.tools.keys())}",
            )

        # 检查参数
        schema = self.registry.get_tool_schema(tool_call.name)
        if schema:
            try:
                schema(**tool_call.input)
            except ValidationError as e:
                for error in e.errors():
                    field = ".".join(str(x) for x in error["loc"])
                    errors.append(f"参数 {field}: {error['msg']}")
                return ValidationReport(result=ValidationResult.FAIL, errors=errors)

        return ValidationReport(result=ValidationResult.PASS, errors=[])


@dataclass
class HallucinationResult:
    is_hallucination: bool
    confidence: float
    evidence: str
    suggestion: Optional[str] = None


class HallucinationDetector:
    def __init__(self, registry: QualityToolRegistry):
        self.registry = registry

    def detect(self, tool_call: ToolUseBlock) -> List[HallucinationResult]:
        results = []

        # 工具名幻觉
        if not self.registry.is_tool_available(tool_call.name):
            from difflib import get_close_matches

            available = list(self.registry.tools.keys())
            suggestions = get_close_matches(tool_call.name, available, n=1, cutoff=0.6)
            results.append(
                HallucinationResult(
                    is_hallucination=True,
                    confidence=0.9,
                    evidence=f"工具 '{tool_call.name}' 不存在",
                    suggestion=f"您想要 '{suggestions[0]}' 吗?" if suggestions else None,
                )
            )

        # 参数范围幻觉
        if tool_call.input:
            for key, value in tool_call.input.items():
                if isinstance(value, int):
                    if value < 0 or value > 1000000:
                        results.append(
                            HallucinationResult(
                                is_hallucination=True,
                                confidence=0.7,
                                evidence=f"参数 {key} = {value} 超出常规范围",
                                suggestion="请检查参数值是否合理",
                            )
                        )

        return results
