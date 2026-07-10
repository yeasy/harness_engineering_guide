"""
Tests for mini_harness.reliability module:
- logging.py: StructuredLogger
- tracing.py: Span, trace_span, TraceCollector
- resilience.py: RetryDecorator, CircuitBreaker
- monitoring.py: MonitoringSystem, Alert, ToolMetrics
"""

import json
import inspect
import sys
import time
from io import StringIO

import pytest

from mini_harness.reliability.logging import StructuredLogger
from mini_harness.reliability.tracing import Span, trace_span, get_trace_id, set_trace_id
from mini_harness.reliability.resilience import (
    RetryDecorator,
    CircuitBreaker,
    RetryConfig,
)
from mini_harness.reliability.monitoring import (
    MonitoringSystem,
    Alert,
    AlertLevel,
    ToolMetrics,
    SystemMetrics,
)


# ============ StructuredLogger Tests ============


class TestStructuredLogger:
    def test_logger_creation(self):
        logger = StructuredLogger()
        assert logger.trace_id is not None
        assert len(logger.trace_id) > 0

    def test_logger_with_custom_trace_id(self):
        custom_id = "trace-123-xyz"
        logger = StructuredLogger(trace_id=custom_id)
        assert logger.trace_id == custom_id

    def test_log_json_format(self, capsys):
        logger = StructuredLogger(trace_id="test-trace-001")
        logger.info("test message", user_id="user-123", action="test_action")

        captured = capsys.readouterr()
        output = captured.out.strip()
        log_entry = json.loads(output)

        assert log_entry["trace_id"] == "test-trace-001"
        assert log_entry["message"] == "test message"
        assert log_entry["level"] == "INFO"
        assert log_entry["user_id"] == "[REDACTED]"
        assert log_entry["action"] == "test_action"
        assert "timestamp" in log_entry

    def test_log_redacts_sensitive_fields(self, capsys):
        logger = StructuredLogger(trace_id="test-trace-002")
        logger.info(
            "request",
            api_key="fixture-secret-value",
            nested={"authorization": "Bearer token-value", "email": "user@example.com"},
        )

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry["api_key"] == "[REDACTED]"
        assert log_entry["nested"]["authorization"] == "[REDACTED]"
        assert log_entry["nested"]["email"] == "[REDACTED]"
        assert "fixture-secret-value" not in captured.out
        assert "token-value" not in captured.out
        assert "user@example.com" not in captured.out

    def test_log_levels(self, capsys):
        logger = StructuredLogger()
        logger.debug("debug msg")
        logger.warning("warning msg")
        logger.error("error msg")

        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')

        logs = [json.loads(line) for line in lines if line]
        assert logs[0]["level"] == "DEBUG"
        assert logs[1]["level"] == "WARNING"
        assert logs[2]["level"] == "ERROR"

    def test_trace_id_propagation(self):
        trace_id_1 = "trace-aaa"
        trace_id_2 = "trace-bbb"

        logger1 = StructuredLogger(trace_id=trace_id_1)
        logger2 = StructuredLogger(trace_id=trace_id_2)

        assert logger1.trace_id == trace_id_1
        assert logger2.trace_id == trace_id_2

    def test_log_tool_call(self, capsys):
        logger = StructuredLogger(trace_id="trace-tool")
        logger.log_tool_call(
            tool_name="bash_exec",
            duration_ms=150.5,
            status="success",
            args=["echo", "hello"]
        )

        captured = capsys.readouterr()
        log_entry = json.loads(captured.out.strip())

        assert log_entry["tool_name"] == "bash_exec"
        assert log_entry["duration_ms"] == 150.5
        assert log_entry["status"] == "success"
        assert log_entry["level"] == "INFO"


# ============ Span Tests ============


class TestSpan:
    def test_span_creation(self):
        span = Span(name="test_operation")
        assert span.name == "test_operation"
        assert span.span_id is not None
        assert len(span.span_id) == 16
        int(span.span_id, 16)
        assert span.trace_id is not None
        assert len(span.trace_id) == 32
        int(span.trace_id, 16)
        assert span.parent_span_id is None
        assert span.error is None

    def test_span_with_parent(self):
        parent_id = "parent-span-123"
        span = Span(name="child_op", parent_id=parent_id)
        assert span.parent_span_id == parent_id

    def test_span_with_custom_trace_id(self):
        trace_id = "custom-trace-456"
        span = Span(name="test_op", trace_id=trace_id)
        assert span.trace_id == trace_id

    def test_span_set_attribute(self):
        span = Span(name="test_op")
        span.set_attribute("tool_name", "bash_exec")
        span.set_attribute("status", "success")

        assert span.attributes["tool_name"] == "bash_exec"
        assert span.attributes["status"] == "success"

    def test_span_redacts_sensitive_attributes(self):
        span = Span(name="test_op")
        span.set_attribute("authorization", "Bearer token-value")
        span.set_attribute("metadata", {"email": "user@example.com"})

        assert span.attributes["authorization"] == "[REDACTED]"
        assert span.attributes["metadata"]["email"] == "[REDACTED]"

    def test_span_set_error(self):
        span = Span(name="test_op")
        span.set_error("Connection timeout")

        assert span.error == "Connection timeout"
        assert span.attributes["error"] is True

    def test_span_duration_calculation(self):
        span = Span(name="test_op")
        span.start_time = 100.0
        span.end_time = 100.5

        duration_ms = span._calculate_duration_ms()
        assert duration_ms == pytest.approx(500.0, rel=0.01)

    def test_span_context_manager(self, capsys):
        with trace_span("test_operation") as span:
            span.set_attribute("test_key", "test_value")
            assert span.start_time is not None
            time.sleep(0.01)

        # After exit, span should be recorded
        assert span.end_time is not None
        assert span.start_time is not None

        # Check output
        captured = capsys.readouterr()
        trace_record = json.loads(captured.out.strip())
        assert trace_record["name"] == "test_operation"
        assert trace_record["attributes"]["test_key"] == "test_value"


# ============ RetryDecorator Tests ============


class TestRetryDecorator:
    def test_async_detection_avoids_deprecated_asyncio_helper(self, monkeypatch):
        def deprecated_probe(_function):
            raise AssertionError("deprecated asyncio probe used")

        monkeypatch.setattr(
            "mini_harness.reliability.resilience.asyncio.iscoroutinefunction",
            deprecated_probe,
        )

        async def async_operation():
            return "ok"

        wrapped = RetryDecorator(max_attempts=1)(async_operation)
        assert inspect.iscoroutinefunction(wrapped)

    def test_successful_call_first_try(self):
        call_count = 0

        @RetryDecorator(max_attempts=3)
        def reliable_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = reliable_function()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_recoverable_error(self):
        call_count = 0

        @RetryDecorator(max_attempts=3, initial_delay=0.01, jitter=False)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert call_count == 3

    def test_max_retries_exceeded(self):
        call_count = 0

        @RetryDecorator(max_attempts=2, initial_delay=0.01, jitter=False)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Connection failed")

        with pytest.raises(ConnectionError):
            always_fails()

        assert call_count == 2

    def test_non_retryable_exception(self):
        call_count = 0

        @RetryDecorator(max_attempts=3, initial_delay=0.01, jitter=False)
        def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid value")

        with pytest.raises(ValueError):
            raises_value_error()

        # Should not retry on non-retryable exception
        assert call_count == 1

    def test_retry_config_delay_calculation(self):
        config = RetryConfig(
            max_attempts=3,
            initial_delay=1.0,
            exponential_base=2.0,
            jitter=False
        )

        delay1 = config.calculate_delay(1)
        delay2 = config.calculate_delay(2)
        delay3 = config.calculate_delay(3)

        assert delay1 == pytest.approx(1.0)
        assert delay2 == pytest.approx(2.0)
        assert delay3 == pytest.approx(4.0)


# ============ CircuitBreaker Tests ============


class TestCircuitBreaker:
    def test_circuit_breaker_closed_state(self):
        breaker = CircuitBreaker(failure_threshold=3)
        assert breaker.is_open is False
        assert breaker.failure_count == 0

    def test_circuit_breaker_opens_on_threshold(self):
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)

        def failing_func():
            raise RuntimeError("failure")

        # First failure
        with pytest.raises(RuntimeError):
            breaker.call(failing_func)
        assert breaker.is_open is False

        # Second failure - should open
        with pytest.raises(RuntimeError):
            breaker.call(failing_func)
        assert breaker.is_open is True

    def test_circuit_breaker_rejects_when_open(self):
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)

        def failing_func():
            raise RuntimeError("failure")

        # Open the circuit
        with pytest.raises(RuntimeError):
            breaker.call(failing_func)
        assert breaker.is_open is True

        # Should reject subsequent calls
        with pytest.raises(RuntimeError, match="Circuit breaker is open"):
            breaker.call(failing_func)

    def test_circuit_breaker_recovery(self):
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        def failing_func():
            raise RuntimeError("failure")

        def success_func():
            return "ok"

        # Open the circuit
        with pytest.raises(RuntimeError):
            breaker.call(failing_func)
        assert breaker.is_open is True

        # Wait for recovery timeout
        time.sleep(0.15)

        # Should attempt recovery
        result = breaker.call(success_func)
        assert result == "ok"
        assert breaker.is_open is False

    def test_circuit_breaker_resets_failure_count_on_success(self):
        breaker = CircuitBreaker(failure_threshold=3)

        call_count = 0

        def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count in [1, 2]:
                raise RuntimeError("failure")
            return "ok"

        # Two failures
        with pytest.raises(RuntimeError):
            breaker.call(sometimes_fails)
        with pytest.raises(RuntimeError):
            breaker.call(sometimes_fails)
        assert breaker.failure_count == 2

        # Success - should reset counter
        result = breaker.call(sometimes_fails)
        assert result == "ok"
        assert breaker.failure_count == 0


# ============ MonitoringSystem Tests ============


class TestMonitoringSystem:
    def test_monitoring_system_creation(self):
        system = MonitoringSystem()
        assert system.error_rate_threshold == 0.1
        assert system.latency_threshold_ms == 5000.0
        assert len(system.alerts) == 0

    def test_record_execution_success(self):
        system = MonitoringSystem()
        system.record_execution("bash_exec", success=True, duration_ms=100.0)

        metrics = system.metrics
        assert metrics.total_executions == 1
        assert metrics.successful_executions == 1
        assert metrics.failed_executions == 0
        assert metrics.total_duration_ms == 100.0

    def test_record_execution_failure(self):
        system = MonitoringSystem()
        system.record_execution("bash_exec", success=False, duration_ms=50.0)

        metrics = system.metrics
        assert metrics.total_executions == 1
        assert metrics.successful_executions == 0
        assert metrics.failed_executions == 1
        assert metrics.failure_rate == 1.0

    def test_tool_metrics_tracking(self):
        system = MonitoringSystem()
        system.record_execution("tool_a", success=True, duration_ms=100.0)
        system.record_execution("tool_a", success=False, duration_ms=50.0)
        system.record_execution("tool_b", success=True, duration_ms=200.0)

        assert "tool_a" in system.metrics.tool_metrics
        assert "tool_b" in system.metrics.tool_metrics
        assert system.metrics.tool_metrics["tool_a"].call_count == 2
        assert system.metrics.tool_metrics["tool_b"].call_count == 1

    def test_alert_generation_error_rate(self):
        system = MonitoringSystem(error_rate_threshold=0.2)

        # Generate failures to exceed threshold
        for _ in range(3):
            system.record_execution("tool", success=False, duration_ms=10.0)
        for _ in range(2):
            system.record_execution("tool", success=True, duration_ms=10.0)

        alerts = system.check_health()
        error_rate_alerts = [a for a in alerts if a.alert_type == "error_rate_high"]
        assert len(error_rate_alerts) > 0
        assert error_rate_alerts[0].level == AlertLevel.CRITICAL

    def test_alert_generation_latency(self):
        system = MonitoringSystem(latency_threshold_ms=100.0)

        # Generate high latency
        system.record_execution("tool", success=True, duration_ms=500.0)
        system.record_execution("tool", success=True, duration_ms=600.0)

        alerts = system.check_health()
        latency_alerts = [a for a in alerts if a.alert_type == "latency_high"]
        assert len(latency_alerts) > 0
        assert latency_alerts[0].level == AlertLevel.WARNING

    def test_alert_generation_tool_failure(self):
        system = MonitoringSystem(tool_failure_threshold=0.3)

        # Tool with high failure rate
        for _ in range(3):
            system.record_execution("unreliable_tool", success=False, duration_ms=10.0)
        for _ in range(1):
            system.record_execution("unreliable_tool", success=True, duration_ms=10.0)

        alerts = system.check_health()
        tool_alerts = [a for a in alerts if "unreliable_tool" in a.alert_type]
        assert len(tool_alerts) > 0

    def test_reset_metrics(self):
        system = MonitoringSystem()
        system.record_execution("tool", success=True, duration_ms=100.0)
        assert system.metrics.total_executions == 1

        system.reset_metrics()
        assert system.metrics.total_executions == 0
        assert len(system.alerts) == 0
