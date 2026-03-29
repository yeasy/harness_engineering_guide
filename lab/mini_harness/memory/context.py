"""
mini_harness/memory/context.py - Context assembly and memory requirements
"""

import asyncio
from typing import Dict, List, Optional, Any
from mini_harness.memory.storage import MemoryStore


class MemoryRequirement:
    """上下文需求规范"""

    def __init__(self):
        self.needs_user_profile = False
        self.needs_project_context = False
        self.needs_recent_history = False
        self.needs_references = False
        self.needs_feedback = False


class ContextAssembler:
    """上下文组装引擎"""

    def __init__(self, memory_store: MemoryStore, token_budget: int = 50000):
        self.memory_store = memory_store
        self.token_budget = token_budget
        self.cache = {}  # 简单的内存缓存

    async def analyze_query(self, user_message: str) -> MemoryRequirement:
        """分析查询，确定需要的记忆类型"""
        req = MemoryRequirement()
        msg_lower = user_message.lower()

        # 启发式规则
        if any(w in msg_lower for w in ['prefer', 'style', 'like', 'habit']):
            req.needs_user_profile = True

        if any(w in msg_lower for w in ['project', 'task', 'status', 'progress']):
            req.needs_project_context = True

        if any(w in msg_lower for w in ['previous', 'before', 'last', 'remember']):
            req.needs_recent_history = True

        if any(w in msg_lower for w in ['example', 'sample', 'pattern', 'how to']):
            req.needs_references = True

        if any(w in msg_lower for w in ['feedback', 'approved', 'rejected']):
            req.needs_feedback = True

        # 默认：总是需要用户档案
        if not any([req.needs_project_context, req.needs_recent_history,
                    req.needs_references, req.needs_feedback]):
            req.needs_user_profile = True

        return req

    async def _gather_user_profile(self) -> str:
        """收集用户档案"""
        profiles = await self.memory_store.list_by_type('user')

        if not profiles:
            return ""

        sections = []
        for profile_id in profiles:
            entry = await self.memory_store.load(profile_id, 'user')
            if entry:
                sections.append(entry.content)

        return "## User Profile\n\n" + "\n\n".join(sections)

    async def _gather_project_context(self) -> str:
        """收集项目上下文"""
        projects = await self.memory_store.list_by_type('project')

        if not projects:
            return ""

        sections = []
        for proj_id in projects:
            entry = await self.memory_store.load(proj_id, 'project')
            if entry:
                sections.append(entry.content)

        return "## Project Context\n\n" + "\n\n".join(sections)

    async def _gather_references(self) -> str:
        """收集参考资料"""
        refs = await self.memory_store.list_by_type('reference')

        if not refs:
            return ""

        sections = []
        for ref_id in refs:
            entry = await self.memory_store.load(ref_id, 'reference')
            if entry:
                sections.append(entry.content)

        return "## References\n\n" + "\n\n".join(sections)

    async def _gather_feedback(self) -> str:
        """收集反馈记录"""
        feedbacks = await self.memory_store.list_by_type('feedback')

        if not feedbacks:
            return ""

        sections = []
        for fb_id in feedbacks[:5]:  # 仅最近的 5 条反馈
            entry = await self.memory_store.load(fb_id, 'feedback')
            if entry:
                sections.append(entry.content)

        return "## Recent Feedback\n\n" + "\n\n".join(sections)

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算 tokens（实际应使用 tiktoken）"""
        return len(text.split()) // 4 + 1

    async def assemble(self, user_message: str) -> str:
        """组装最终上下文"""
        requirement = await self.analyze_query(user_message)

        gathered = {}
        tasks = []

        if requirement.needs_user_profile:
            tasks.append(('user_profile', self._gather_user_profile()))

        if requirement.needs_project_context:
            tasks.append(('project', self._gather_project_context()))

        if requirement.needs_references:
            tasks.append(('references', self._gather_references()))

        if requirement.needs_feedback:
            tasks.append(('feedback', self._gather_feedback()))

        # 并行执行
        results = await asyncio.gather(*[task[1] for task in tasks])

        for (key, _), result in zip(tasks, results):
            gathered[key] = result

        # 按优先级排序，限制总大小
        priority_order = ['user_profile', 'project', 'references', 'feedback']
        assembled_parts = []
        current_tokens = 0

        for priority in priority_order:
            if priority in gathered and gathered[priority]:
                content = gathered[priority]
                tokens = self._estimate_tokens(content)

                if current_tokens + tokens <= self.token_budget:
                    assembled_parts.append(content)
                    current_tokens += tokens

        return "\n\n".join(assembled_parts)
