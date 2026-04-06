"""
Tests for mini_harness.models module:
- provider.py: CircuitBreaker, ModelConfig, ModelProviderType, ModelSelectionEngine
- parser.py: TextBlock, ToolUseBlock, ThinkingBlock, ParsedMessage, ResponseParser
- quality.py: ToolRegistry (quality), QualityGate, HallucinationDetector
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from mini_harness.models.parser import ParsedMessage, ResponseParser, TextBlock, ThinkingBlock
from mini_harness.models.parser import ToolUseBlock
from mini_harness.models.parser import ToolUseBlock as ParserToolUseBlock
from mini_harness.models.provider import CircuitBreaker
from mini_harness.models.provider import Message as ProviderMessage
from mini_harness.models.provider import ModelConfig, ModelProviderType, ModelSelectionEngine
from mini_harness.models.quality import (
    HallucinationDetector,
    HallucinationResult,
    QualityGate,
    QualityToolRegistry,
    ValidationReport,
    ValidationResult,
)

# ============ CircuitBreaker Tests ============


class TestCircuitBreaker:
    def test_initial_state(self):
        cb = CircuitBreaker()
        assert cb.state == "closed"
        assert cb.failure_count == 0
        assert cb.is_available() is True

    def test_failure_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "closed"
        assert cb.is_available() is True

        cb.record_failure()  # Third failure -> open
        assert cb.state == "open"
        assert cb.is_available() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0
        assert cb.state == "closed"

    def test_open_to_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0)
        cb.record_failure()
        assert cb.state == "open"

        # With reset_timeout=0, it should immediately transition to half-open
        time.sleep(0.01)
        assert cb.is_available() is True
        assert cb.state == "half-open"

    def test_half_open_needs_multiple_successes(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0, success_threshold_half_open=3)
        cb.record_failure()
        assert cb.state == "open"

        time.sleep(0.01)
        cb.is_available()  # Triggers transition to half-open
        assert cb.state == "half-open"

        cb.record_success()
        assert cb.state == "half-open"  # Still half-open after 1 success
        cb.record_success()
        assert cb.state == "half-open"  # Still half-open after 2 successes
        cb.record_success()
        assert cb.state == "closed"  # Closed after 3 successes

    def test_half_open_failure_resets(self):
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=0, success_threshold_half_open=3)
        cb.record_failure()
        time.sleep(0.01)
        cb.is_available()  # half-open

        cb.record_success()
        cb.record_failure()  # Failure during half-open
        assert cb.success_count_half_open == 0

    def test_custom_thresholds(self):
        cb = CircuitBreaker(failure_threshold=5, reset_timeout=120)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"


# ============ ModelConfig Tests ============


class TestModelConfig:
    def test_creation(self):
        config = ModelConfig(provider=ModelProviderType.CLAUDE, model_id="claude-sonnet-4-20250514")
        assert config.provider == ModelProviderType.CLAUDE
        assert config.max_tokens == 4096
        assert config.timeout == 30

    def test_custom_config(self):
        config = ModelConfig(
            provider=ModelProviderType.CLAUDE,
            model_id="claude-opus-4-20250514",
            api_key="test-key",
            max_tokens=8192,
            timeout=60,
        )
        assert config.api_key == "test-key"
        assert config.max_tokens == 8192


# ============ ModelSelectionEngine Tests ============


class TestModelSelectionEngine:
    def test_select_primary(self):
        primary = ModelConfig(
            provider=ModelProviderType.CLAUDE, model_id="claude-sonnet-4-20250514", api_key="test"
        )
        engine = ModelSelectionEngine(primary)
        provider = engine.select_model()
        assert provider.config.model_id == "claude-sonnet-4-20250514"

    def test_fallback_selection(self):
        primary = ModelConfig(provider=ModelProviderType.CLAUDE, model_id="primary", api_key="test")
        fallback = ModelConfig(
            provider=ModelProviderType.CLAUDE, model_id="fallback", api_key="test"
        )
        engine = ModelSelectionEngine(primary, [fallback])

        # Break primary
        for _ in range(3):
            engine.mark_failure("primary")

        provider = engine.select_model()
        assert provider.config.model_id == "fallback"

    def test_all_unavailable_raises(self):
        primary = ModelConfig(provider=ModelProviderType.CLAUDE, model_id="only", api_key="test")
        engine = ModelSelectionEngine(primary)

        for _ in range(3):
            engine.mark_failure("only")

        with pytest.raises(Exception, match="不可用"):
            engine.select_model()

    def test_mark_success(self):
        primary = ModelConfig(provider=ModelProviderType.CLAUDE, model_id="model-1", api_key="test")
        engine = ModelSelectionEngine(primary)
        engine.mark_success("model-1")
        assert engine.breakers["model-1"].failure_count == 0


# ============ Parser Tests ============


class TestTextBlock:
    def test_defaults(self):
        block = TextBlock()
        assert block.type == "text"
        assert block.text == ""

    def test_with_text(self):
        block = TextBlock(text="Hello world")
        assert block.text == "Hello world"


class TestToolUseBlock:
    def test_defaults(self):
        block = ToolUseBlock()
        assert block.type == "tool_use"
        assert block.name == ""
        assert block.input is None

    def test_with_data(self):
        block = ToolUseBlock(id="tool_123", name="bash_exec", input={"command": "ls"})
        assert block.name == "bash_exec"
        assert block.input["command"] == "ls"


class TestThinkingBlock:
    def test_defaults(self):
        block = ThinkingBlock()
        assert block.type == "thinking"
        assert block.thinking == ""


class TestParsedMessage:
    def test_text_content(self):
        msg = ParsedMessage(
            content_blocks=[TextBlock(text="Hello "), TextBlock(text="world")],
            stop_reason="end_turn",
            tokens_used=100,
        )
        assert msg.text_content() == "Hello world"

    def test_tool_calls(self):
        tool1 = ToolUseBlock(name="bash_exec")
        tool2 = ToolUseBlock(name="file_read")
        msg = ParsedMessage(
            content_blocks=[TextBlock(text="Let me help"), tool1, tool2],
            stop_reason="tool_use",
            tokens_used=200,
        )
        calls = msg.tool_calls()
        assert len(calls) == 2
        assert calls[0].name == "bash_exec"

    def test_empty_message(self):
        msg = ParsedMessage(content_blocks=[], stop_reason="end_turn", tokens_used=0)
        assert msg.text_content() == ""
        assert msg.tool_calls() == []


class TestResponseParser:
    def test_parse_text_response(self):
        raw = {
            "content": [{"type": "text", "text": "Hello!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 50, "output_tokens": 10},
        }
        msg = ResponseParser.parse_response(raw)
        assert msg.text_content() == "Hello!"
        assert msg.stop_reason == "end_turn"
        assert msg.tokens_used == 60

    def test_parse_tool_use_response(self):
        raw = {
            "content": [
                {"type": "text", "text": "I'll run a command."},
                {
                    "type": "tool_use",
                    "id": "tool_abc",
                    "name": "bash_exec",
                    "input": {"command": "ls -la"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        msg = ResponseParser.parse_response(raw)
        assert msg.text_content() == "I'll run a command."
        calls = msg.tool_calls()
        assert len(calls) == 1
        assert calls[0].name == "bash_exec"
        assert calls[0].input == {"command": "ls -la"}
        assert msg.tokens_used == 150

    def test_parse_tool_input_as_string(self):
        raw = {
            "content": [
                {"type": "tool_use", "id": "tool_x", "name": "test", "input": '{"key": "value"}'}
            ],
            "stop_reason": "tool_use",
        }
        msg = ResponseParser.parse_response(raw)
        calls = msg.tool_calls()
        assert calls[0].input == {"key": "value"}

    def test_parse_invalid_json_input(self):
        raw = {
            "content": [
                {"type": "tool_use", "id": "tool_y", "name": "test", "input": "not valid json"}
            ],
            "stop_reason": "tool_use",
        }
        msg = ResponseParser.parse_response(raw)
        calls = msg.tool_calls()
        assert calls[0].input == {}

    def test_parse_empty_content(self):
        raw = {"content": [], "stop_reason": "end_turn"}
        msg = ResponseParser.parse_response(raw)
        assert msg.text_content() == ""
        assert msg.tokens_used == 0

    def test_parse_missing_fields(self):
        raw = {}
        msg = ResponseParser.parse_response(raw)
        assert msg.stop_reason == "end_turn"
        assert msg.tokens_used == 0


# ============ QualityGate Tests ============


class TestQualityToolRegistry:
    def test_register_tool(self):
        registry = QualityToolRegistry()
        registry.register("bash", lambda: None, None)
        assert registry.is_tool_available("bash")

    def test_tool_not_available(self):
        registry = QualityToolRegistry()
        assert registry.is_tool_available("unknown") is False

    def test_get_schema(self):
        registry = QualityToolRegistry()
        registry.register("test", lambda: None, "schema_obj")
        assert registry.get_tool_schema("test") == "schema_obj"


class TestQualityGate:
    def _make_registry(self):
        registry = QualityToolRegistry()
        registry.register("bash_exec", lambda: None, None)
        registry.register("file_read", lambda: None, None)
        return registry

    def test_valid_tool_call(self):
        registry = self._make_registry()
        gate = QualityGate(registry)

        tool_call = ParserToolUseBlock(
            id="tool_001", name="bash_exec", input={"command": "echo hi"}
        )
        report = gate.validate_tool_call(tool_call)
        assert report.result == ValidationResult.PASS
        assert len(report.errors) == 0

    def test_missing_id(self):
        registry = self._make_registry()
        gate = QualityGate(registry)

        tool_call = ParserToolUseBlock(id="", name="bash_exec")
        report = gate.validate_tool_call(tool_call)
        assert report.result == ValidationResult.FAIL

    def test_missing_name(self):
        registry = self._make_registry()
        gate = QualityGate(registry)

        tool_call = ParserToolUseBlock(id="tool_001", name="")
        report = gate.validate_tool_call(tool_call)
        assert report.result == ValidationResult.FAIL

    def test_unregistered_tool(self):
        registry = self._make_registry()
        gate = QualityGate(registry)

        tool_call = ParserToolUseBlock(id="tool_001", name="nonexistent_tool", input={})
        report = gate.validate_tool_call(tool_call)
        assert report.result == ValidationResult.FAIL
        assert report.suggestion is not None


# ============ HallucinationDetector Tests ============


class TestHallucinationDetector:
    def _make_registry(self):
        registry = QualityToolRegistry()
        registry.register("bash_exec", lambda: None, None)
        registry.register("file_read", lambda: None, None)
        return registry

    def test_no_hallucination(self):
        registry = self._make_registry()
        detector = HallucinationDetector(registry)

        tool_call = ParserToolUseBlock(id="t1", name="bash_exec", input={"command": "ls"})
        results = detector.detect(tool_call)
        assert len(results) == 0

    def test_tool_name_hallucination(self):
        registry = self._make_registry()
        detector = HallucinationDetector(registry)

        tool_call = ParserToolUseBlock(id="t1", name="bash_execute", input={})  # Similar but wrong
        results = detector.detect(tool_call)
        assert len(results) > 0
        assert results[0].is_hallucination is True
        assert results[0].confidence >= 0.9

    def test_tool_name_hallucination_with_suggestion(self):
        registry = self._make_registry()
        detector = HallucinationDetector(registry)

        tool_call = ParserToolUseBlock(id="t1", name="bash_exe", input={})  # Close to bash_exec
        results = detector.detect(tool_call)
        hallucination = results[0]
        assert hallucination.is_hallucination is True
        # difflib should suggest "bash_exec"
        if hallucination.suggestion:
            assert "bash_exec" in hallucination.suggestion

    def test_parameter_range_hallucination(self):
        registry = self._make_registry()
        detector = HallucinationDetector(registry)

        tool_call = ParserToolUseBlock(
            id="t1", name="bash_exec", input={"timeout": 99999999}  # Unreasonable value
        )
        results = detector.detect(tool_call)
        assert any(r.is_hallucination for r in results)

    def test_negative_parameter(self):
        registry = self._make_registry()
        detector = HallucinationDetector(registry)

        tool_call = ParserToolUseBlock(id="t1", name="bash_exec", input={"timeout": -100})
        results = detector.detect(tool_call)
        assert any(r.is_hallucination for r in results)

    def test_normal_parameter(self):
        registry = self._make_registry()
        detector = HallucinationDetector(registry)

        tool_call = ParserToolUseBlock(id="t1", name="bash_exec", input={"timeout": 30})
        results = detector.detect(tool_call)
        assert len(results) == 0
