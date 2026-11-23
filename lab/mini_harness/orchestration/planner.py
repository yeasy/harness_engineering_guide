"""LLM 规划器：让模型生成任务 DAG，由 Harness 校验、修复和重新规划。

模型只负责“提议”一张任务图；任务图能否执行由 Harness 决定：
1. 通过工具调用（submit_plan）拿到结构化计划，而不是从自由文本里抠 JSON；
2. PlanValidator 做确定性校验（结构、引用、环、策略）；
3. 校验失败时把错误清单回传给模型修复，次数有上限；
4. 执行中某个任务失败时，冻结已完成节点，只让模型重新规划剩余部分。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from ..models.provider import BaseProvider, ProviderMessage
from .engine import TaskDefinition, TaskType

PLAN_TOOL_NAME = "submit_plan"


def build_plan_tool(allowed_types: Iterable[TaskType], max_tasks: int) -> Dict[str, Any]:
    """生成 submit_plan 工具定义；task_type 的枚举值来自策略，而不是写死在提示词里。"""
    return {
        "name": PLAN_TOOL_NAME,
        "description": (
            "提交任务计划。每个任务是 DAG 中的一个节点，depends_on 列出必须先完成的任务 id。"
            f"任务总数不超过 {max_tasks}。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "短标识，如 fetch_data"},
                            "task_type": {
                                "type": "string",
                                "enum": [t.value for t in allowed_types],
                            },
                            "description": {"type": "string"},
                            "depends_on": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "task_type", "description", "depends_on"],
                    },
                }
            },
            "required": ["tasks"],
        },
    }


@dataclass
class PlanPolicy:
    """Harness 对计划施加的硬约束。模型可以不知道这些约束，但无法绕过它们。"""

    allowed_types: Set[TaskType] = field(
        default_factory=lambda: {TaskType.LOCAL_BASH, TaskType.LOCAL_AGENT}
    )
    max_tasks: int = 12
    max_depth: int = 6  # 最长依赖链的节点数，限制串行等待时间


class PlanningError(Exception):
    """模型在允许的修复次数内仍未给出合法计划。"""

    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors


class PlanValidator:
    """确定性校验：同一份输入永远得到同一份错误清单。"""

    def __init__(self, policy: PlanPolicy):
        self.policy = policy

    def validate(self, plan: Any, frozen_ids: Optional[Set[str]] = None) -> List[str]:
        """返回错误清单，空列表表示合法。

        frozen_ids 是重新规划时已完成的任务：新计划可以依赖它们，但不能重新定义它们。
        """
        frozen = frozen_ids or set()
        if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
            return ["计划必须是包含 tasks 数组的对象"]
        if not plan["tasks"]:
            return ["tasks 不能为空"]
        # 分三层检查，前一层不通过就不做后一层：结构不对时谈不上引用，引用不对时谈不上环
        return (
            self._check_fields(plan["tasks"], frozen)
            or self._check_references(plan["tasks"], frozen)
            or self._check_shape(plan["tasks"])
        )

    def _check_fields(self, tasks: List[Any], frozen: Set[str]) -> List[str]:
        """字段与策略：数量上限、id 唯一、类型在白名单内。"""
        errors: List[str] = []
        if len(tasks) > self.policy.max_tasks:
            errors.append(f"任务数 {len(tasks)} 超过上限 {self.policy.max_tasks}")
        allowed = {t.value for t in self.policy.allowed_types}
        seen: Set[str] = set()
        for i, task in enumerate(tasks):
            tid = task.get("id") if isinstance(task, dict) else None
            if not isinstance(tid, str) or not tid:
                errors.append(f"tasks[{i}] 不是带 id 的对象")
                continue
            if tid in seen:
                errors.append(f"任务 id {tid} 重复")
            if tid in frozen:
                errors.append(f"任务 {tid} 已完成，不能重新定义")
            seen.add(tid)
            if task.get("task_type") not in allowed:
                errors.append(
                    f"任务 {tid} 的类型 {task.get('task_type')!r} 不在允许列表 {sorted(allowed)}"
                )
            if not str(task.get("description") or "").strip():
                errors.append(f"任务 {tid} 缺少 description")
            if not isinstance(task.get("depends_on", []), list):
                errors.append(f"任务 {tid} 的 depends_on 必须是数组")
        return errors

    @staticmethod
    def _check_references(tasks: List[Dict[str, Any]], frozen: Set[str]) -> List[str]:
        """引用完整性：依赖必须指向本计划或已完成的任务，且不能指向自身。"""
        known = {t["id"] for t in tasks} | frozen
        errors: List[str] = []
        for task in tasks:
            for dep in task.get("depends_on", []):
                if dep == task["id"]:
                    errors.append(f"任务 {task['id']} 依赖自身")
                elif dep not in known:
                    errors.append(f"任务 {task['id']} 依赖的 {dep} 不存在")
        return errors

    def _check_shape(self, tasks: List[Dict[str, Any]]) -> List[str]:
        """图的形状：无环，且最长依赖链不超过上限。已完成任务不参与，它们不会再执行。"""
        ids = {t["id"] for t in tasks}
        graph = {t["id"]: [d for d in t.get("depends_on", []) if d in ids] for t in tasks}
        cycle = _find_cycle(graph)
        if cycle:
            return [f"存在循环依赖：{' -> '.join(cycle)}"]
        depth = _longest_chain(graph)
        if depth > self.policy.max_depth:
            return [f"最长依赖链 {depth} 超过上限 {self.policy.max_depth}"]
        return []


def _find_cycle(graph: Dict[str, List[str]]) -> List[str]:
    """DFS 找环，返回环上的节点序列（首尾相同），无环返回空列表。"""
    state: Dict[str, int] = {}  # 0/缺省=未访问，1=在栈上，2=已完成
    stack: List[str] = []

    def dfs(node: str) -> List[str]:
        state[node] = 1
        stack.append(node)
        for dep in graph[node]:
            if state.get(dep) == 1:
                return stack[stack.index(dep):] + [dep]
            if state.get(dep, 0) == 0:
                found = dfs(dep)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return []

    for node in graph:
        if state.get(node, 0) == 0:
            found = dfs(node)
            if found:
                return found
    return []


def _longest_chain(graph: Dict[str, List[str]]) -> int:
    """无环图中最长依赖链的节点数。"""
    memo: Dict[str, int] = {}

    def depth(node: str) -> int:
        if node not in memo:
            memo[node] = 1 + max((depth(d) for d in graph[node]), default=0)
        return memo[node]

    return max((depth(n) for n in graph), default=0)


class LLMPlanner:
    """让模型生成任务 DAG，校验失败时带着错误清单让模型修复。"""

    def __init__(
        self,
        provider: BaseProvider,
        policy: Optional[PlanPolicy] = None,
        max_repair_attempts: int = 2,
    ):
        self.provider = provider
        self.policy = policy or PlanPolicy()
        self.validator = PlanValidator(self.policy)
        self.max_repair_attempts = max_repair_attempts
        self.tool = build_plan_tool(
            sorted(self.policy.allowed_types, key=lambda t: t.value), self.policy.max_tasks
        )

    def plan(self, goal: str) -> List[TaskDefinition]:
        """为目标生成初始计划。"""
        prompt = (
            f"目标：{goal}\n\n"
            "把目标分解为可独立执行的任务，调用 submit_plan 提交。"
            "没有数据依赖的任务不要串起来，以便并行执行。"
        )
        return self._plan_with_repair(prompt, frozen_ids=set())

    def replan(
        self,
        goal: str,
        completed: Dict[str, str],
        failed_task: str,
        error: str,
    ) -> List[TaskDefinition]:
        """某个任务失败后，只为剩余工作重新规划；completed 为已完成任务 id 到结果摘要的映射。"""
        done = "\n".join(f"- {tid}: {summary}" for tid, summary in completed.items()) or "（无）"
        prompt = (
            f"目标：{goal}\n\n"
            f"以下任务已完成，结果不会重做，新任务可以在 depends_on 中引用它们：\n{done}\n\n"
            f"任务 {failed_task} 失败：{error}\n\n"
            "请只为尚未完成的工作提交新计划，不要重新定义已完成的任务；"
            f"如果 {failed_task} 的做法本身有问题，用新的 id 换一种做法。"
        )
        return self._plan_with_repair(prompt, frozen_ids=set(completed))

    def _plan_with_repair(self, prompt: str, frozen_ids: Set[str]) -> List[TaskDefinition]:
        messages = [ProviderMessage("user", prompt)]
        errors: List[str] = []
        for _ in range(1 + self.max_repair_attempts):
            response = self.provider.complete_with_tools(messages, [self.tool])
            call = next((c for c in response.tool_calls if c.get("name") == PLAN_TOOL_NAME), None)
            if call is None:
                errors = ["没有调用 submit_plan 工具"]
                plan: Any = None
            else:
                plan = call.get("arguments")
                errors = self.validator.validate(plan, frozen_ids)
            if not errors:
                return self._to_definitions(plan)
            # 修复回合：把上一轮计划放回对话，再附上逐条错误，让模型在原计划上改而不是推倒重来
            messages.append(ProviderMessage("assistant", f"已提交计划：{plan}"))
            messages.append(
                ProviderMessage(
                    "user",
                    "计划未通过校验，请修正以下问题后重新调用 submit_plan：\n"
                    + "\n".join(f"- {e}" for e in errors),
                )
            )
        raise PlanningError(f"{1 + self.max_repair_attempts} 次尝试后计划仍不合法", errors)

    @staticmethod
    def _to_definitions(plan: Dict[str, Any]) -> List[TaskDefinition]:
        return [
            TaskDefinition(
                task_id=t["id"],
                task_type=TaskType(t["task_type"]),
                description=t["description"],
                dependencies=list(t.get("depends_on", [])),
            )
            for t in plan["tasks"]
        ]
