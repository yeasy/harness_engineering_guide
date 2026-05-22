"""
mini_harness/reliability/logging.py - Structured logging system
"""

import json
import uuid
from datetime import datetime
from typing import Optional

from mini_harness.reliability.redaction import sanitize_observability_value


class StructuredLogger:
    """结构化日志系统 - JSON 序列化日志便于日志聚合与分析"""

    def __init__(self, trace_id: Optional[str] = None):
        """初始化日志器

        Args:
            trace_id: 链路追踪ID，用于关联同一请求的日志
        """
        self.trace_id = trace_id or str(uuid.uuid4())

    def log(self, level: str, message: str, **fields) -> None:
        """记录结构化日志为 JSON 格式

        Args:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: 日志消息
            **fields: 自定义字段 (工具名、耗时等)
        """
        safe_fields = {
            key: sanitize_observability_value(key, value)
            for key, value in fields.items()
        }
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "trace_id": self.trace_id,
            "message": message,
            "level": level,
            **safe_fields,
        }
        print(json.dumps(log_entry))

    def debug(self, message: str, **fields) -> None:
        """DEBUG 级别日志"""
        self.log("DEBUG", message, **fields)

    def info(self, message: str, **fields) -> None:
        """INFO 级别日志"""
        self.log("INFO", message, **fields)

    def warning(self, message: str, **fields) -> None:
        """WARNING 级别日志"""
        self.log("WARNING", message, **fields)

    def error(self, message: str, **fields) -> None:
        """ERROR 级别日志"""
        self.log("ERROR", message, **fields)

    def critical(self, message: str, **fields) -> None:
        """CRITICAL 级别日志"""
        self.log("CRITICAL", message, **fields)

    def log_tool_call(
        self,
        tool_name: str,
        duration_ms: float,
        status: str,
        error: Optional[str] = None,
        **extra_fields,
    ) -> None:
        """专用方法记录工具调用

        Args:
            tool_name: 工具名称
            duration_ms: 执行耗时（毫秒）
            status: 执行状态 (success, error, timeout)
            error: 错误信息（如果有）
            **extra_fields: 其他字段
        """
        fields = {
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "status": status,
            **extra_fields,
        }
        if error:
            fields["error"] = error

        level = "ERROR" if status == "error" else "INFO"
        self.log(level, f"Tool call: {tool_name}", **fields)

    def log_agent_step(
        self,
        step_id: str,
        action: str,
        duration_ms: float,
        **extra_fields,
    ) -> None:
        """记录智能体执行步骤

        Args:
            step_id: 步骤ID
            action: 动作类型 (execute, plan, decide, etc)
            duration_ms: 耗时（毫秒）
            **extra_fields: 其他字段
        """
        self.log(
            "INFO",
            f"Agent step: {action}",
            step_id=step_id,
            action=action,
            duration_ms=duration_ms,
            **extra_fields,
        )
