"""
mini_harness/reliability/tracing.py - Distributed tracing system
"""

import contextvars
import json
import secrets
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from mini_harness.reliability.redaction import sanitize_observability_value

# 上下文变量，用于在异步调用中追踪 trace_id 和当前 span
_trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
_current_span_var: contextvars.ContextVar[Optional["Span"]] = contextvars.ContextVar(
    "current_span", default=None
)


def get_trace_id() -> str:
    """获取当前链路追踪ID"""
    trace_id = _trace_id_var.get()
    if not trace_id:
        trace_id = _new_trace_id()
        _trace_id_var.set(trace_id)
    return trace_id


def set_trace_id(trace_id: str) -> None:
    """设置链路追踪ID"""
    _trace_id_var.set(trace_id)


def _new_trace_id() -> str:
    """生成 OpenTelemetry/W3C TraceId 形态的 16 字节十六进制字符串。"""
    return secrets.token_hex(16)


def _new_span_id() -> str:
    """生成 OpenTelemetry/W3C SpanId 形态的 8 字节十六进制字符串。"""
    return secrets.token_hex(8)


class Span:
    """单个追踪跨度，使用 OpenTelemetry/W3C 形态的 trace/span ID。"""

    def __init__(
        self,
        name: str,
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
    ):
        """初始化 Span

        Args:
            name: Span 名称
            trace_id: 所属的链路ID
            parent_id: 父 Span ID (用于形成树结构)
        """
        self.span_id = _new_span_id()
        self.name = name
        self.trace_id = trace_id or get_trace_id()
        self.parent_span_id = parent_id
        self.attributes: Dict[str, Any] = {}
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.error: Optional[str] = None

    def set_attribute(self, key: str, value: Any) -> None:
        """设置自定义属性

        Args:
            key: 属性名
            value: 属性值
        """
        self.attributes[key] = sanitize_observability_value(key, value)

    def set_error(self, error_message: str) -> None:
        """标记 Span 为错误状态

        Args:
            error_message: 错误消息
        """
        self.error = sanitize_observability_value("error", error_message)
        self.set_attribute("error", True)

    def _calculate_duration_ms(self) -> float:
        """计算执行耗时（毫秒）"""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        """转换为追踪记录字典"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "duration_ms": self._calculate_duration_ms(),
            "attributes": self.attributes,
            "error": self.error,
            "start_time": (
                datetime.fromtimestamp(self.start_time).isoformat()
                if self.start_time
                else None
            ),
            "end_time": (
                datetime.fromtimestamp(self.end_time).isoformat()
                if self.end_time
                else None
            ),
        }

    def __enter__(self):
        """上下文管理器入口"""
        self.start_time = time.time()
        _current_span_var.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.end_time = time.time()

        if exc_type is not None:
            self.set_error(str(exc_val) or str(exc_type.__name__))

        # 输出追踪记录到日志
        trace_record = self.to_dict()
        print(json.dumps(trace_record))

        _current_span_var.set(None)
        return False


@contextmanager
def trace_span(name: str, trace_id: Optional[str] = None, parent_id: Optional[str] = None):
    """上下文管理器 - 简化 Span 的使用

    使用示例:
        with trace_span('tool_execution') as span:
            span.set_attribute('tool_name', 'web_search')
            # 执行工具
            span.set_attribute('status', 'success')

    Args:
        name: Span 名称
        trace_id: 链路ID (可选，默认自动生成)
        parent_id: 父 Span ID (可选)

    Yields:
        Span: 追踪跨度对象
    """
    span = Span(name, trace_id=trace_id, parent_id=parent_id)
    with span:
        yield span


class TraceCollector:
    """追踪收集器 - 用于测试和调试"""

    def __init__(self):
        """初始化追踪收集器"""
        self.spans: List[Dict[str, Any]] = []

    def clear(self) -> None:
        """清空已收集的追踪"""
        self.spans = []

    def collect(self, span: Span) -> None:
        """收集追踪记录

        Args:
            span: Span 对象
        """
        self.spans.append(span.to_dict())

    def get_trace_tree(self, trace_id: str) -> Dict[str, Any]:
        """获取某个链路的完整追踪树

        Args:
            trace_id: 链路ID

        Returns:
            追踪树字典
        """
        trace_spans = [s for s in self.spans if s["trace_id"] == trace_id]

        # 按 parent_span_id 组织成树
        span_map = {s["span_id"]: s for s in trace_spans}
        root_spans = [s for s in trace_spans if s["parent_span_id"] is None]

        def build_tree(span_id: Optional[str]) -> List[Dict[str, Any]]:
            """递归构建树"""
            children = [
                s for s in trace_spans if s["parent_span_id"] == span_id
            ]
            return [
                {**child, "children": build_tree(child["span_id"])}
                for child in children
            ]

        return {
            "trace_id": trace_id,
            "root_spans": [
                {**root, "children": build_tree(root["span_id"])}
                for root in root_spans
            ],
        }
