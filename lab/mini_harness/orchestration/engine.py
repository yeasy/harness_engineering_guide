# orchestration.py
"""Orchestration engine: manages task execution, workflows, and state machines with subagent support."""

import asyncio
import json
import uuid
from collections import deque
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

# ============================================================================
# 1. 枚举定义
# ============================================================================


class TaskType(Enum):
    """Task类型"""

    LOCAL_BASH = "local_bash"
    LOCAL_AGENT = "local_agent"
    IN_PROCESS_TEAMMATE = "in_process_teammate"
    WORKFLOW = "workflow"


class TaskState(Enum):
    """Task生命周期状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class StateType(Enum):
    """工作流状态类型"""

    INITIAL = "initial"
    NORMAL = "normal"
    FINAL = "final"
    ERROR = "error"
    WAIT = "wait"


# ============================================================================
# 2. 数据类
# ============================================================================


@dataclass
class TaskDefinition:
    """Task定义"""

    task_id: str
    task_type: TaskType
    description: str
    dependencies: List[str] = field(default_factory=list)
    timeout_seconds: int = 300
    max_retries: int = 1
    execution_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskExecution:
    """Task执行记录"""

    task_id: str
    state: TaskState
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    attempt: int = 0


@dataclass
class TaskNotification:
    """Task通知消息"""

    id: str
    task_id: str
    state: TaskState
    timestamp: datetime
    result: Optional[Dict[str, Any]] = None
    next_tasks: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """转换为JSON"""
        data = asdict(self)
        data["state"] = self.state.value
        data["timestamp"] = self.timestamp.isoformat()
        return json.dumps(data, indent=2)


@dataclass
class StateDefinition:
    """工作流状态定义"""

    state_id: str
    state_type: StateType
    description: str
    actions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TransitionDefinition:
    """工作流转移定义"""

    from_state: str
    to_state: str
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 3. Task管理器
# ============================================================================


class TaskManager:
    """管理Task的生命周期和依赖关系"""

    def __init__(self):
        self.tasks: Dict[str, TaskDefinition] = {}
        self.executions: Dict[str, TaskExecution] = {}
        self.notification_queue: deque[TaskNotification] = deque()

    def register_task(self, task_def: TaskDefinition) -> None:
        """注册Task"""
        self.tasks[task_def.task_id] = task_def
        self.executions[task_def.task_id] = TaskExecution(
            task_id=task_def.task_id,
            state=TaskState.PENDING,
        )

    def get_task(self, task_id: str) -> Optional[TaskDefinition]:
        """获取Task定义"""
        return self.tasks.get(task_id)

    def get_execution(self, task_id: str) -> Optional[TaskExecution]:
        """获取Task执行记录"""
        return self.executions.get(task_id)

    def can_execute(self, task_id: str) -> Tuple[bool, Optional[str]]:
        """检查Task的所有依赖是否已完成"""
        task = self.get_task(task_id)
        if not task:
            return False, f"Task {task_id} not found"

        for dep_id in task.dependencies:
            dep_exec = self.get_execution(dep_id)
            if not dep_exec or dep_exec.state != TaskState.COMPLETED:
                return False, f"Dependency {dep_id} not completed"

        return True, None

    def mark_running(self, task_id: str) -> None:
        """标记Task为运行中"""
        exec_record = self.executions[task_id]
        exec_record.state = TaskState.RUNNING
        exec_record.start_time = datetime.now()

    def mark_completed(self, task_id: str, result: Dict[str, Any]) -> None:
        """标记Task为完成"""
        exec_record = self.executions[task_id]
        exec_record.state = TaskState.COMPLETED
        exec_record.result = result
        exec_record.end_time = datetime.now()

        # 发送通知
        self._emit_notification(task_id, TaskState.COMPLETED, result)

    def mark_failed(self, task_id: str, error: str) -> None:
        """标记Task为失败"""
        exec_record = self.executions[task_id]
        exec_record.error = error

        # 检查是否还有重试机会
        task = self.get_task(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} not found")
        if exec_record.retry_count < task.max_retries:
            exec_record.state = TaskState.FAILED
            exec_record.retry_count += 1
            exec_record.state = TaskState.PENDING  # 重新加入待执行队列
        else:
            exec_record.state = TaskState.FAILED
            exec_record.end_time = datetime.now()

        # 发送通知
        self._emit_notification(task_id, TaskState.FAILED, None)

    def _emit_notification(
        self, task_id: str, state: TaskState, result: Optional[Dict[str, Any]]
    ) -> None:
        """发出Task完成通知"""
        notification = TaskNotification(
            id=str(uuid.uuid4()),
            task_id=task_id,
            state=state,
            timestamp=datetime.now(),
            result=result,
            next_tasks=self._find_dependent_tasks(task_id),
            metrics={
                "timestamp": datetime.now().isoformat(),
            },
        )
        self.notification_queue.append(notification)

    def _find_dependent_tasks(self, completed_task_id: str) -> List[str]:
        """找出现在可以执行的依赖任务"""
        dependent = []
        for task_id, task in self.tasks.items():
            if completed_task_id in task.dependencies:
                can_exec, _ = self.can_execute(task_id)
                if can_exec:
                    dependent.append(task_id)
        return dependent

    def get_notification(self) -> Optional[TaskNotification]:
        """获取一条通知"""
        if self.notification_queue:
            return self.notification_queue.popleft()
        return None

    def get_execution_status(self) -> Dict[str, Any]:
        """获取全局执行状态"""
        states = {}
        for task_id, exec_record in self.executions.items():
            states[task_id] = {
                "state": exec_record.state.value,
                "result": exec_record.result,
                "error": exec_record.error,
                "start_time": (
                    exec_record.start_time.isoformat() if exec_record.start_time else None
                ),
                "end_time": exec_record.end_time.isoformat() if exec_record.end_time else None,
            }
        return states


# ============================================================================
# 4. 工作流状态机
# ============================================================================


class WorkflowStateMachine:
    """工作流状态机"""

    def __init__(self):
        self.states: Dict[str, StateDefinition] = {}
        self.transitions: List[TransitionDefinition] = []
        self.current_state: Optional[str] = None
        self.context: Dict[str, Any] = {}
        self.execution_log: List[Dict[str, Any]] = []

    def add_state(self, state: StateDefinition) -> None:
        """添加状态"""
        self.states[state.state_id] = state

    def add_transition(self, transition: TransitionDefinition) -> None:
        """添加转移"""
        self.transitions.append(transition)

    def initialize(self, initial_state: str, context: Dict[str, Any]) -> None:
        """初始化状态机"""
        if initial_state not in self.states:
            raise ValueError(f"Initial state {initial_state} not found")

        self.current_state = initial_state
        self.context = context
        self.execution_log = []

        self._log_state_entry(initial_state)

    def find_next_state(self) -> Optional[str]:
        """根据条件找到下一个状态"""
        for transition in self.transitions:
            if transition.from_state != self.current_state:
                continue

            if transition.condition is None:
                return transition.to_state

            try:
                if transition.condition(self.context):
                    return transition.to_state
            except Exception as e:
                print(f"Condition evaluation error: {e}")
                continue

        return None

    def transition(self, new_state: str) -> bool:
        """执行状态转移"""
        if new_state not in self.states:
            return False

        prev_state = self.current_state
        self.current_state = new_state

        self._log_state_entry(new_state)
        return True

    def update_context(self, key: str, value: Any) -> None:
        """更新上下文"""
        self.context[key] = value

    def _log_state_entry(self, state_id: str) -> None:
        """记录进入状态"""
        self.execution_log.append(
            {
                "timestamp": datetime.now().isoformat(),
                "event": "state_entry",
                "state": state_id,
                "context_snapshot": dict(self.context),
            }
        )

    def is_final_state(self) -> bool:
        """检查是否到达终止状态"""
        if self.current_state in self.states:
            return self.states[self.current_state].state_type == StateType.FINAL
        return False

    def is_error_state(self) -> bool:
        """检查是否进入错误状态"""
        if self.current_state in self.states:
            return self.states[self.current_state].state_type == StateType.ERROR
        return False


# ============================================================================
# 5. 智能体上下文隔离
# ============================================================================

_agent_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar("agent_context", default=None)


class AgentContext:
    """Agent执行上下文（隔离）"""

    def __init__(self, agent_id: str, parent_context: Optional[Dict[str, Any]] = None):
        self.agent_id = agent_id
        self.variables: Dict[str, Any] = {}
        self.parent_context = parent_context or {}
        self.execution_log: List[Dict[str, Any]] = []

    def set(self, key: str, value: Any) -> None:
        """设置变量"""
        self.variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """获取变量（先本地后父上下文）"""
        if key in self.variables:
            return self.variables[key]
        return self.parent_context.get(key, default)

    def log(self, message: str, level: str = "info") -> None:
        """记录日志"""
        self.execution_log.append(
            {
                "timestamp": datetime.now().isoformat(),
                "level": level,
                "message": message,
            }
        )

    def __enter__(self):
        """进入上下文"""
        self.token = _agent_context.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        _agent_context.reset(self.token)


# ============================================================================
# 6. 子智能体工厂
# ============================================================================


class SubAgentFactory:
    """创建和管理子Agent"""

    def __init__(self, parent_agent_id: str):
        self.parent_agent_id = parent_agent_id
        self.subagents: Dict[str, "SubAgent"] = {}

    def create_subagent(self, subagent_id: str, task_type: TaskType) -> "SubAgent":
        """创建子Agent"""
        subagent = SubAgent(
            subagent_id=subagent_id,
            parent_agent_id=self.parent_agent_id,
            task_type=task_type,
        )
        self.subagents[subagent_id] = subagent
        return subagent


class SubAgent:
    """子Agent"""

    def __init__(
        self,
        subagent_id: str,
        parent_agent_id: str,
        task_type: TaskType,
    ):
        self.subagent_id = subagent_id
        self.parent_agent_id = parent_agent_id
        self.task_type = task_type
        self.context: Optional[AgentContext] = None

    async def execute(
        self, task: str, parent_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """在隔离上下文中执行任务"""
        with AgentContext(self.subagent_id, parent_context) as ctx:
            self.context = ctx
            ctx.log(f"开始执行子Agent任务: {task}")

            # 模拟执行任务
            result = await self._execute_task(task)

            ctx.log(f"子Agent执行完成")
            return {
                "subagent_id": self.subagent_id,
                "result": result,
                "logs": ctx.execution_log,
            }

    async def _execute_task(self, task: str) -> Dict[str, Any]:
        """执行具体任务"""
        await asyncio.sleep(0.1)  # 模拟异步操作
        return {
            "status": "completed",
            "task": task,
            "agent": self.subagent_id,
        }


# ============================================================================
# 7. 编排引擎
# ============================================================================


class OrchestrationEngine:
    """编排引擎：协调TaskManager和StateMachine"""

    def __init__(self):
        self.task_manager = TaskManager()
        self.state_machine = WorkflowStateMachine()
        self.subagent_factory: Optional[SubAgentFactory] = None
        self.execution_history: List[Dict[str, Any]] = []

    def setup_workflow(
        self,
        states: List[StateDefinition],
        transitions: List[TransitionDefinition],
    ) -> None:
        """配置工作流"""
        for state in states:
            self.state_machine.add_state(state)

        for transition in transitions:
            self.state_machine.add_transition(transition)

    def register_tasks(self, tasks: List[TaskDefinition]) -> None:
        """注册任务"""
        for task in tasks:
            self.task_manager.register_task(task)

    def initialize_subagent_factory(self, parent_agent_id: str) -> None:
        """初始化子Agent工厂"""
        self.subagent_factory = SubAgentFactory(parent_agent_id)

    async def execute_workflow(
        self,
        initial_state: str,
        context: Dict[str, Any],
        max_iterations: int = 100,
    ) -> Dict[str, Any]:
        """执行工作流"""
        self.state_machine.initialize(initial_state, context)
        iterations = 0

        while iterations < max_iterations:
            # 检查是否到达终止状态
            if self.state_machine.is_final_state():
                print("[工作流完成]")
                break

            if self.state_machine.is_error_state():
                print("[进入错误状态]")
                break

            # 找到并执行可执行的Task
            executed = False
            for task_id, task in self.task_manager.tasks.items():
                can_exec, reason = self.task_manager.can_execute(task_id)
                if can_exec:
                    execution = self.task_manager.get_execution(task_id)
                    if execution.state == TaskState.PENDING:
                        print(f"[执行Task] {task_id}")
                        self.task_manager.mark_running(task_id)
                        result = await self._execute_task(task_id, task)
                        if result["success"]:
                            self.task_manager.mark_completed(task_id, result)
                        else:
                            self.task_manager.mark_failed(
                                task_id, result.get("error", "Unknown error")
                            )
                        executed = True

            # 处理通知
            notification = self.task_manager.get_notification()
            if notification:
                print(f"[通知] Task {notification.task_id} 完成")
                print(f"后续可执行Task: {notification.next_tasks}")

            # 尝试状态转移
            next_state = self.state_machine.find_next_state()
            if next_state:
                print(f"[转移] {self.state_machine.current_state} -> {next_state}")
                self.state_machine.transition(next_state)

            if not executed:
                break

            iterations += 1

        return {
            "final_state": self.state_machine.current_state,
            "task_states": self.task_manager.get_execution_status(),
            "workflow_log": self.state_machine.execution_log,
            "iterations": iterations,
        }

    async def _execute_task(self, task_id: str, task: TaskDefinition) -> Dict[str, Any]:
        """执行单个Task"""
        try:
            if task.task_type == TaskType.LOCAL_BASH:
                # 模拟执行bash命令
                return {"success": True, "output": f"Executed {task_id}"}

            elif task.task_type == TaskType.LOCAL_AGENT:
                # 模拟Agent执行
                return {"success": True, "output": f"Agent executed {task_id}"}

            elif task.task_type == TaskType.IN_PROCESS_TEAMMATE:
                # 创建并执行子Agent
                if self.subagent_factory:
                    subagent = self.subagent_factory.create_subagent(
                        f"subagent_{task_id}", task.task_type
                    )
                    context = self.state_machine.context.copy()
                    result = await subagent.execute(task_id, context)
                    return {"success": True, "result": result}
                return {"success": False, "error": "SubAgent factory not initialized"}

            else:
                return {"success": False, "error": f"Unknown task type: {task.task_type}"}

        except Exception as e:
            return {"success": False, "error": str(e)}


# ============================================================================
# 8. 使用示例
# ============================================================================


async def main():
    """演示编排引擎的使用"""

    # 创建编排引擎
    engine = OrchestrationEngine()

    # 定义工作流状态
    states = [
        StateDefinition("start", StateType.INITIAL, "工作流起点"),
        StateDefinition("research", StateType.NORMAL, "研究阶段"),
        StateDefinition("synthesis", StateType.NORMAL, "综合阶段"),
        StateDefinition("implementation", StateType.NORMAL, "实现阶段"),
        StateDefinition("complete", StateType.FINAL, "完成"),
    ]

    # 定义转移
    transitions = [
        TransitionDefinition("start", "research"),
        TransitionDefinition("research", "synthesis"),
        TransitionDefinition("synthesis", "implementation"),
        TransitionDefinition("implementation", "complete"),
    ]

    # 设置工作流
    engine.setup_workflow(states, transitions)

    # 定义Task
    tasks = [
        TaskDefinition(
            task_id="task_0",
            task_type=TaskType.LOCAL_BASH,
            description="数据收集",
        ),
        TaskDefinition(
            task_id="task_1",
            task_type=TaskType.LOCAL_AGENT,
            description="数据分析",
            dependencies=["task_0"],
        ),
        TaskDefinition(
            task_id="task_2",
            task_type=TaskType.IN_PROCESS_TEAMMATE,
            description="模型训练",
            dependencies=["task_1"],
        ),
        TaskDefinition(
            task_id="task_3",
            task_type=TaskType.LOCAL_AGENT,
            description="结果验证",
            dependencies=["task_2"],
        ),
    ]

    # 注册Task
    engine.register_tasks(tasks)

    # 初始化子Agent工厂
    engine.initialize_subagent_factory("main_agent")

    # 执行工作流
    result = await engine.execute_workflow(
        "start",
        {"input_data": "sample_data", "config": {}},
    )

    print("\n" + "=" * 60)
    print("执行结果:")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
