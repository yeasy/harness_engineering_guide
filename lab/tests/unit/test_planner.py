"""Tests for mini_harness.orchestration.planner: LLM 生成任务 DAG 的校验、修复与重新规划。"""

import pytest

from mini_harness.models.provider import ProviderResponse
from mini_harness.orchestration.engine import TaskType
from mini_harness.orchestration.planner import (
    PLAN_TOOL_NAME,
    LLMPlanner,
    PlanningError,
    PlanPolicy,
    PlanValidator,
)


def _task(tid, deps=(), task_type="local_agent", description="做点事"):
    return {"id": tid, "task_type": task_type, "description": description, "depends_on": list(deps)}


def _plan(*tasks):
    return {"tasks": list(tasks)}


class ScriptedProvider:
    """按顺序返回预设计划的假模型，并记录每次收到的消息。"""

    def __init__(self, *plans):
        self.plans = list(plans)
        self.calls = []

    def complete_with_tools(self, messages, tools):
        self.calls.append([(m.role, m.content) for m in messages])
        plan = self.plans.pop(0)
        tool_calls = [] if plan is None else [
            {"id": "call_1", "name": PLAN_TOOL_NAME, "arguments": plan}
        ]
        return ProviderResponse(content="", tokens_used=0, model="fake", tool_calls=tool_calls)


# ============ PlanValidator ============


class TestPlanValidator:
    def setup_method(self):
        self.validator = PlanValidator(PlanPolicy(max_tasks=5, max_depth=3))

    def test_valid_diamond(self):
        plan = _plan(_task("a"), _task("b", ["a"]), _task("c", ["a"]), _task("d", ["b", "c"]))
        assert self.validator.validate(plan) == []

    @pytest.mark.parametrize("plan", [None, [], {"tasks": "x"}, {"tasks": []}])
    def test_rejects_malformed(self, plan):
        assert self.validator.validate(plan)

    def test_unknown_dependency(self):
        errors = self.validator.validate(_plan(_task("a", ["ghost"])))
        assert errors == ["任务 a 依赖的 ghost 不存在"]

    def test_self_dependency(self):
        assert self.validator.validate(_plan(_task("a", ["a"]))) == ["任务 a 依赖自身"]

    def test_cycle_reports_path(self):
        errors = self.validator.validate(_plan(_task("a", ["c"]), _task("b", ["a"]), _task("c", ["b"])))
        assert len(errors) == 1 and errors[0].startswith("存在循环依赖")
        assert errors[0].count("->") == 3

    def test_duplicate_id(self):
        assert "任务 id a 重复" in self.validator.validate(_plan(_task("a"), _task("a")))

    def test_disallowed_type(self):
        errors = self.validator.validate(_plan(_task("a", task_type="remote_agent")))
        assert "不在允许列表" in errors[0]

    def test_too_many_tasks(self):
        plan = _plan(*[_task(f"t{i}") for i in range(6)])
        assert any("超过上限 5" in e for e in self.validator.validate(plan))

    def test_chain_too_deep(self):
        plan = _plan(_task("a"), _task("b", ["a"]), _task("c", ["b"]), _task("d", ["c"]))
        assert self.validator.validate(plan) == ["最长依赖链 4 超过上限 3"]

    def test_frozen_ids_are_referable_but_not_redefinable(self):
        assert self.validator.validate(_plan(_task("x", ["a"])), frozen_ids={"a"}) == []
        errors = self.validator.validate(_plan(_task("a")), frozen_ids={"a"})
        assert errors == ["任务 a 已完成，不能重新定义"]


# ============ LLMPlanner ============


class TestLLMPlanner:
    def test_valid_plan_first_try(self):
        provider = ScriptedProvider(_plan(_task("fetch", task_type="local_bash"), _task("sum", ["fetch"])))
        tasks = LLMPlanner(provider).plan("汇总数据")

        assert [t.task_id for t in tasks] == ["fetch", "sum"]
        assert tasks[0].task_type is TaskType.LOCAL_BASH
        assert tasks[1].dependencies == ["fetch"]
        assert len(provider.calls) == 1

    def test_repair_feeds_errors_back(self):
        provider = ScriptedProvider(
            _plan(_task("a", ["b"]), _task("b", ["a"])),  # 有环
            _plan(_task("a"), _task("b", ["a"])),
        )
        tasks = LLMPlanner(provider).plan("目标")

        assert [t.task_id for t in tasks] == ["a", "b"]
        repair_prompt = provider.calls[1][-1]
        assert repair_prompt[0] == "user" and "存在循环依赖" in repair_prompt[1]

    def test_missing_tool_call_counts_as_error(self):
        provider = ScriptedProvider(None, _plan(_task("a")))
        tasks = LLMPlanner(provider).plan("目标")
        assert [t.task_id for t in tasks] == ["a"]
        assert "没有调用 submit_plan" in provider.calls[1][-1][1]

    def test_gives_up_after_max_attempts(self):
        bad = _plan(_task("a", ["ghost"]))
        provider = ScriptedProvider(bad, bad, bad)
        with pytest.raises(PlanningError) as exc:
            LLMPlanner(provider, max_repair_attempts=2).plan("目标")
        assert exc.value.errors == ["任务 a 依赖的 ghost 不存在"]
        assert len(provider.calls) == 3

    def test_replan_freezes_completed_tasks(self):
        provider = ScriptedProvider(
            _plan(_task("fetch")),  # 试图重做已完成任务
            _plan(_task("parse_v2", ["fetch"]), _task("report", ["parse_v2"])),
        )
        tasks = LLMPlanner(provider).replan(
            "生成报告", completed={"fetch": "下载了 3 个文件"}, failed_task="parse", error="编码错误"
        )

        assert [t.task_id for t in tasks] == ["parse_v2", "report"]
        first_prompt = provider.calls[0][0][1]
        assert "fetch: 下载了 3 个文件" in first_prompt and "parse 失败：编码错误" in first_prompt
        assert "任务 fetch 已完成，不能重新定义" in provider.calls[1][-1][1]

    def test_tool_schema_enum_follows_policy(self):
        policy = PlanPolicy(allowed_types={TaskType.LOCAL_AGENT})
        planner = LLMPlanner(ScriptedProvider(), policy=policy)
        item = planner.tool["input_schema"]["properties"]["tasks"]["items"]
        assert item["properties"]["task_type"]["enum"] == ["local_agent"]
