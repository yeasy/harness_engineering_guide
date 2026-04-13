"""
Tests for mini_harness.orchestration module:
- engine.py: TaskManager, WorkflowStateMachine, AgentContext, SubAgentFactory, OrchestrationEngine
"""

import pytest

from mini_harness.orchestration.engine import (
    AgentContext,
    OrchestrationEngine,
    StateDefinition,
    StateType,
    SubAgentFactory,
    TaskDefinition,
    TaskManager,
    TaskNotification,
    TaskState,
    TaskType,
    TransitionDefinition,
    WorkflowStateMachine,
)

# ============ TaskManager Tests ============


class TestTaskManager:
    def test_register_task(self):
        mgr = TaskManager()
        task = TaskDefinition(task_id="t1", task_type=TaskType.LOCAL_BASH, description="Test task")
        mgr.register_task(task)

        assert mgr.get_task("t1") is task
        assert mgr.get_execution("t1") is not None
        assert mgr.get_execution("t1").state == TaskState.PENDING

    def test_get_nonexistent_task(self):
        mgr = TaskManager()
        assert mgr.get_task("ghost") is None

    def test_can_execute_no_dependencies(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "No deps"))
        can, reason = mgr.can_execute("t1")
        assert can is True
        assert reason is None

    def test_can_execute_with_pending_dependency(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "First"))
        mgr.register_task(TaskDefinition("t2", TaskType.LOCAL_BASH, "Second", dependencies=["t1"]))
        can, reason = mgr.can_execute("t2")
        assert can is False
        assert "t1" in reason

    def test_can_execute_with_completed_dependency(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "First"))
        mgr.register_task(TaskDefinition("t2", TaskType.LOCAL_BASH, "Second", dependencies=["t1"]))
        mgr.mark_running("t1")
        mgr.mark_completed("t1", {"output": "done"})

        can, reason = mgr.can_execute("t2")
        assert can is True

    def test_mark_running(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "Test"))
        mgr.mark_running("t1")
        assert mgr.get_execution("t1").state == TaskState.RUNNING
        assert mgr.get_execution("t1").start_time is not None

    def test_mark_completed(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "Test"))
        mgr.mark_running("t1")
        mgr.mark_completed("t1", {"output": "result"})

        exec_rec = mgr.get_execution("t1")
        assert exec_rec.state == TaskState.COMPLETED
        assert exec_rec.result == {"output": "result"}
        assert exec_rec.end_time is not None

    def test_mark_failed_with_retry(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "Test", max_retries=2))
        mgr.mark_running("t1")
        mgr.mark_failed("t1", "Error occurred")

        exec_rec = mgr.get_execution("t1")
        assert exec_rec.state == TaskState.PENDING  # Retryable
        assert exec_rec.retry_count == 1

    def test_mark_failed_no_retry(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "Test", max_retries=1))
        mgr.mark_running("t1")
        mgr.mark_failed("t1", "First error")
        # retry_count now 1, state back to PENDING
        mgr.mark_failed("t1", "Second error")
        # retry_count now exceeds max_retries
        # Actually let's check the logic more carefully:
        # max_retries=1, after first failure retry_count=1, 1 < 1 is False, so it stays FAILED
        # Wait, let me re-read: max_retries=1, first failure: retry_count becomes 1, 1 < 1 is False
        # So it should be FAILED after first failure with max_retries=1
        exec_rec = mgr.get_execution("t1")
        assert exec_rec.state == TaskState.FAILED

    def test_notification_on_complete(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "Test"))
        mgr.mark_running("t1")
        mgr.mark_completed("t1", {"ok": True})

        notification = mgr.get_notification()
        assert notification is not None
        assert notification.task_id == "t1"
        assert notification.state == TaskState.COMPLETED

    def test_notification_queue_empty(self):
        mgr = TaskManager()
        assert mgr.get_notification() is None

    def test_dependent_tasks_in_notification(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "First"))
        mgr.register_task(TaskDefinition("t2", TaskType.LOCAL_BASH, "Second", dependencies=["t1"]))
        mgr.mark_running("t1")
        mgr.mark_completed("t1", {})

        notification = mgr.get_notification()
        assert "t2" in notification.next_tasks

    def test_get_execution_status(self):
        mgr = TaskManager()
        mgr.register_task(TaskDefinition("t1", TaskType.LOCAL_BASH, "Test"))
        status = mgr.get_execution_status()
        assert "t1" in status
        assert status["t1"]["state"] == "pending"


class TestTaskNotification:
    def test_to_json(self):
        from datetime import datetime

        notif = TaskNotification(
            id="n1", task_id="t1", state=TaskState.COMPLETED, timestamp=datetime.now()
        )
        j = notif.to_json()
        assert "completed" in j
        assert "t1" in j


# ============ WorkflowStateMachine Tests ============


class TestWorkflowStateMachine:
    def _make_machine(self):
        sm = WorkflowStateMachine()
        sm.add_state(StateDefinition("start", StateType.INITIAL, "Begin"))
        sm.add_state(StateDefinition("process", StateType.NORMAL, "Processing"))
        sm.add_state(StateDefinition("done", StateType.FINAL, "Complete"))
        sm.add_state(StateDefinition("error", StateType.ERROR, "Error"))
        return sm

    def test_add_state(self):
        sm = self._make_machine()
        assert "start" in sm.states
        assert "done" in sm.states

    def test_initialize(self):
        sm = self._make_machine()
        sm.initialize("start", {"key": "value"})
        assert sm.current_state == "start"
        assert sm.context["key"] == "value"
        assert len(sm.execution_log) == 1

    def test_initialize_invalid_state(self):
        sm = self._make_machine()
        with pytest.raises(ValueError):
            sm.initialize("nonexistent", {})

    def test_transition(self):
        sm = self._make_machine()
        sm.initialize("start", {})
        result = sm.transition("process")
        assert result is True
        assert sm.current_state == "process"

    def test_transition_invalid(self):
        sm = self._make_machine()
        sm.initialize("start", {})
        result = sm.transition("nonexistent")
        assert result is False

    def test_find_next_state_unconditional(self):
        sm = self._make_machine()
        sm.add_transition(TransitionDefinition("start", "process"))
        sm.initialize("start", {})

        next_state = sm.find_next_state()
        assert next_state == "process"

    def test_find_next_state_conditional(self):
        sm = self._make_machine()
        sm.add_transition(
            TransitionDefinition("start", "done", condition=lambda ctx: ctx.get("skip") is True)
        )
        sm.add_transition(
            TransitionDefinition(
                "start", "process", condition=lambda ctx: ctx.get("skip") is not True
            )
        )

        sm.initialize("start", {"skip": False})
        assert sm.find_next_state() == "process"

        sm.initialize("start", {"skip": True})
        assert sm.find_next_state() == "done"

    def test_find_next_state_no_match(self):
        sm = self._make_machine()
        sm.initialize("start", {})
        assert sm.find_next_state() is None

    def test_is_final_state(self):
        sm = self._make_machine()
        sm.initialize("start", {})
        assert sm.is_final_state() is False
        sm.transition("done")
        assert sm.is_final_state() is True

    def test_is_error_state(self):
        sm = self._make_machine()
        sm.initialize("start", {})
        assert sm.is_error_state() is False
        sm.transition("error")
        assert sm.is_error_state() is True

    def test_update_context(self):
        sm = self._make_machine()
        sm.initialize("start", {})
        sm.update_context("result", 42)
        assert sm.context["result"] == 42

    def test_execution_log(self):
        sm = self._make_machine()
        sm.initialize("start", {})
        sm.transition("process")
        sm.transition("done")

        assert len(sm.execution_log) == 3  # start, process, done
        assert sm.execution_log[0]["state"] == "start"
        assert sm.execution_log[1]["state"] == "process"
        assert sm.execution_log[2]["state"] == "done"


# ============ AgentContext Tests ============


class TestAgentContext:
    def test_set_and_get(self):
        ctx = AgentContext("agent-1")
        ctx.set("key", "value")
        assert ctx.get("key") == "value"

    def test_get_default(self):
        ctx = AgentContext("agent-1")
        assert ctx.get("missing", "default") == "default"

    def test_parent_context_fallback(self):
        ctx = AgentContext("agent-1", parent_context={"parent_key": "parent_value"})
        assert ctx.get("parent_key") == "parent_value"

    def test_local_overrides_parent(self):
        ctx = AgentContext("agent-1", parent_context={"key": "parent"})
        ctx.set("key", "local")
        assert ctx.get("key") == "local"

    def test_log(self):
        ctx = AgentContext("agent-1")
        ctx.log("Test message", "info")
        ctx.log("Error message", "error")
        assert len(ctx.execution_log) == 2
        assert ctx.execution_log[0]["message"] == "Test message"
        assert ctx.execution_log[1]["level"] == "error"

    def test_context_manager(self):
        with AgentContext("agent-1") as ctx:
            ctx.set("inside", True)
            assert ctx.get("inside") is True


# ============ SubAgentFactory Tests ============


class TestSubAgentFactory:
    def test_create_subagent(self):
        factory = SubAgentFactory("parent-agent")
        subagent = factory.create_subagent("sub-1", TaskType.LOCAL_AGENT)
        assert subagent.subagent_id == "sub-1"
        assert subagent.parent_agent_id == "parent-agent"
        assert "sub-1" in factory.subagents

    @pytest.mark.asyncio
    async def test_subagent_execute(self):
        factory = SubAgentFactory("parent")
        subagent = factory.create_subagent("sub-1", TaskType.LOCAL_AGENT)
        result = await subagent.execute("test task", {"context_key": "val"})
        assert result["subagent_id"] == "sub-1"
        assert result["result"]["status"] == "completed"
        assert len(result["logs"]) > 0


# ============ OrchestrationEngine Tests ============


class TestOrchestrationEngine:
    @pytest.mark.asyncio
    async def test_simple_workflow(self):
        engine = OrchestrationEngine()

        states = [
            StateDefinition("start", StateType.INITIAL, "Begin"),
            StateDefinition("process", StateType.NORMAL, "Work"),
            StateDefinition("done", StateType.FINAL, "End"),
        ]
        transitions = [
            TransitionDefinition("start", "process"),
            TransitionDefinition("process", "done"),
        ]
        engine.setup_workflow(states, transitions)

        tasks = [
            TaskDefinition("t1", TaskType.LOCAL_BASH, "Task 1"),
            TaskDefinition("t2", TaskType.LOCAL_AGENT, "Task 2", dependencies=["t1"]),
        ]
        engine.register_tasks(tasks)

        result = await engine.execute_workflow("start", {})
        assert result["final_state"] in ["done", "process"]
        assert "t1" in result["task_states"]

    @pytest.mark.asyncio
    async def test_workflow_with_subagent(self):
        engine = OrchestrationEngine()

        states = [
            StateDefinition("start", StateType.INITIAL, "Begin"),
            StateDefinition("work", StateType.NORMAL, "Working"),
            StateDefinition("done", StateType.FINAL, "Done"),
        ]
        transitions = [
            TransitionDefinition("start", "work"),
            TransitionDefinition("work", "done"),
        ]
        engine.setup_workflow(states, transitions)
        engine.initialize_subagent_factory("main")

        tasks = [
            TaskDefinition("t1", TaskType.IN_PROCESS_TEAMMATE, "SubAgent task"),
        ]
        engine.register_tasks(tasks)

        result = await engine.execute_workflow("start", {"data": "test"})
        assert result["task_states"]["t1"]["state"] == "completed"

    @pytest.mark.asyncio
    async def test_empty_workflow(self):
        engine = OrchestrationEngine()
        states = [StateDefinition("only", StateType.FINAL, "Only state")]
        engine.setup_workflow(states, [])

        result = await engine.execute_workflow("only", {})
        assert result["final_state"] == "only"
        assert result["iterations"] == 0
