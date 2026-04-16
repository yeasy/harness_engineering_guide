"""
mini_harness/reliability/monitoring.py - Monitoring and alerting system
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class AlertLevel(str, Enum):
    """告警级别"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """告警对象"""

    alert_type: str  # 告警类型 (e.g., 'error_rate_high', 'latency_high')
    level: AlertLevel  # 告警级别
    value: Any  # 触发告警的值
    message: str = ""  # 告警消息
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "alert_type": self.alert_type,
            "level": self.level.value,
            "value": self.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class ToolMetrics:
    """工具级别的指标"""

    tool_name: str
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_duration_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.call_count == 0:
            return 0.0
        return self.success_count / self.call_count

    @property
    def failure_rate(self) -> float:
        """失败率"""
        return 1.0 - self.success_rate

    @property
    def avg_duration_ms(self) -> float:
        """平均耗时"""
        if self.call_count == 0:
            return 0.0
        return self.total_duration_ms / self.call_count

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_name": self.tool_name,
            "call_count": self.call_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "total_duration_ms": self.total_duration_ms,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "avg_duration_ms": self.avg_duration_ms,
        }


@dataclass
class SystemMetrics:
    """系统级别的指标"""

    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_duration_ms: float = 0.0
    tool_metrics: Dict[str, ToolMetrics] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """系统成功率"""
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    @property
    def failure_rate(self) -> float:
        """系统失败率"""
        return 1.0 - self.success_rate

    @property
    def avg_latency_ms(self) -> float:
        """系统平均延迟"""
        if self.total_executions == 0:
            return 0.0
        return self.total_duration_ms / self.total_executions

    def record_execution(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float,
    ) -> None:
        """记录一次执行

        Args:
            tool_name: 工具名称
            success: 是否成功
            duration_ms: 耗时（毫秒）
        """
        self.total_executions += 1
        self.total_duration_ms += duration_ms

        if success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1

        # 更新工具指标
        if tool_name not in self.tool_metrics:
            self.tool_metrics[tool_name] = ToolMetrics(tool_name=tool_name)

        metrics = self.tool_metrics[tool_name]
        metrics.call_count += 1
        metrics.total_duration_ms += duration_ms

        if success:
            metrics.success_count += 1
        else:
            metrics.error_count += 1

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "total_duration_ms": self.total_duration_ms,
            "success_rate": self.success_rate,
            "failure_rate": self.failure_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "tool_metrics": {
                name: metrics.to_dict()
                for name, metrics in self.tool_metrics.items()
            },
        }


class MonitoringSystem:
    """监控系统 - 基于指标生成告警"""

    def __init__(
        self,
        error_rate_threshold: float = 0.1,
        latency_threshold_ms: float = 5000.0,
        tool_failure_threshold: float = 0.2,
    ):
        """初始化监控系统

        Args:
            error_rate_threshold: 错误率阈值（默认 10%）
            latency_threshold_ms: 延迟阈值，毫秒（默认 5000ms）
            tool_failure_threshold: 工具失败率阈值（默认 20%）
        """
        self.error_rate_threshold = error_rate_threshold
        self.latency_threshold_ms = latency_threshold_ms
        self.tool_failure_threshold = tool_failure_threshold

        self.metrics = SystemMetrics()
        self.alerts: List[Alert] = []
        self.alert_history: Dict[str, datetime] = {}  # 告警去重

    def check_health(self) -> List[Alert]:
        """基于当前指标生成告警

        Returns:
            触发的告警列表
        """
        alerts = []

        # 检查系统错误率
        error_rate = self.metrics.failure_rate
        if error_rate > self.error_rate_threshold:
            alert = Alert(
                alert_type="error_rate_high",
                level=AlertLevel.CRITICAL,
                value=error_rate,
                message=f"System error rate is {error_rate:.2%}, threshold is {self.error_rate_threshold:.2%}",
            )
            alerts.append(alert)

        # 检查系统延迟
        avg_latency = self.metrics.avg_latency_ms
        if avg_latency > self.latency_threshold_ms:
            alert = Alert(
                alert_type="latency_high",
                level=AlertLevel.WARNING,
                value=avg_latency,
                message=f"Average latency is {avg_latency:.0f}ms, threshold is {self.latency_threshold_ms:.0f}ms",
            )
            alerts.append(alert)

        # 检查单个工具的失败率
        for tool_name, tool_metrics in self.metrics.tool_metrics.items():
            if tool_metrics.failure_rate > self.tool_failure_threshold:
                alert = Alert(
                    alert_type=f"tool_{tool_name}_unreliable",
                    level=AlertLevel.WARNING,
                    value=tool_metrics.failure_rate,
                    message=(
                        f"Tool '{tool_name}' failure rate is "
                        f"{tool_metrics.failure_rate:.2%}, threshold is "
                        f"{self.tool_failure_threshold:.2%}"
                    ),
                    metadata={"tool_name": tool_name},
                )
                alerts.append(alert)

        return alerts

    def record_execution(
        self,
        tool_name: str,
        success: bool,
        duration_ms: float,
    ) -> None:
        """记录一次执行

        Args:
            tool_name: 工具名称
            success: 是否成功
            duration_ms: 耗时（毫秒）
        """
        self.metrics.record_execution(tool_name, success, duration_ms)

    def process_alerts(self, dedup_window_seconds: float = 300.0) -> None:
        """处理告警，包括去重

        Args:
            dedup_window_seconds: 去重时间窗口（秒，默认 5 分钟）
        """
        alerts = self.check_health()
        now = datetime.now()

        for alert in alerts:
            # 检查是否在去重窗口内
            last_alert_time = self.alert_history.get(alert.alert_type)
            if (
                last_alert_time
                and (now - last_alert_time).total_seconds() < dedup_window_seconds
            ):
                continue  # 跳过重复告警

            # 记录告警
            self.alerts.append(alert)
            self.alert_history[alert.alert_type] = now

            # 输出告警
            self._emit_alert(alert)

    def _emit_alert(self, alert: Alert) -> None:
        """输出告警（可以集成到告警系统）

        Args:
            alert: 告警对象
        """
        alert_dict = alert.to_dict()
        print(json.dumps(alert_dict))

    def get_metrics_report(self) -> Dict[str, Any]:
        """获取指标报告

        Returns:
            指标报告字典
        """
        return self.metrics.to_dict()

    def reset_metrics(self) -> None:
        """重置所有指标"""
        self.metrics = SystemMetrics()
        self.alerts = []
        self.alert_history = {}
