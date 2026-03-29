"""
mini_harness/memory/consolidation.py - Memory consolidation engine
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from mini_harness.memory.storage import MemoryEntry, MemoryStore


@dataclass
class ConsolidationState:
    """整合状态"""
    last_consolidation: Optional[datetime] = None
    sessions_since_consolidation: int = 0
    total_sessions: int = 0


class ConsolidationEngine:
    """记忆整合引擎"""

    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store
        self.state = ConsolidationState(
            last_consolidation=datetime.now() - timedelta(days=1)
        )

    def should_consolidate(self) -> bool:
        """检查是否应该触发整合"""
        # 三门条件
        time_gate = (self.state.last_consolidation is None or
                     (datetime.now() - self.state.last_consolidation
                      > timedelta(hours=24)))
        session_gate = self.state.sessions_since_consolidation >= 5
        # 显式门由外部调用者控制

        return time_gate or session_gate

    async def orient_phase(self,
                          recent_messages: List[str]) -> Dict[str, Any]:
        """阶段 1：确定方向"""
        # 简化实现：提取摘要
        summary = "\n".join(recent_messages[-10:])

        # 识别主题
        topics = set()
        for msg in recent_messages[-5:]:
            if any(w in msg.lower() for w in ['bug', 'error', 'issue']):
                topics.add('issues')
            if any(w in msg.lower() for w in ['feature', 'new', 'add']):
                topics.add('features')
            if any(w in msg.lower() for w in ['refactor', 'improve']):
                topics.add('improvements')

        return {
            'summary': summary,
            'topics': list(topics),
            'scope': 'deep' if len(topics) > 0 else 'shallow'
        }

    async def gather_phase(self, messages: List[str],
                          orient_result: Dict) -> Dict[str, List[str]]:
        """阶段 2：收集信息"""
        gathered = {
            'user_preferences': [],
            'project_updates': [],
            'learned_lessons': [],
            'decisions': []
        }

        for msg in messages[-20:]:
            msg_lower = msg.lower()

            # 提取偏好
            if 'prefer' in msg_lower or 'like' in msg_lower:
                gathered['user_preferences'].append(msg[:100])

            # 提取项目更新
            if any(w in msg_lower for w in ['completed', 'finished', 'done']):
                gathered['project_updates'].append(msg[:100])

            # 提取教训
            if any(w in msg_lower for w in ['learned', 'discovered', 'found']):
                gathered['learned_lessons'].append(msg[:100])

            # 提取决策
            if any(w in msg_lower for w in ['decide', 'choose', 'decided']):
                gathered['decisions'].append(msg[:100])

        return gathered

    async def consolidate_phase(self,
                               gathered: Dict[str, List[str]]) -> bool:
        """阶段 3：融合到长期记忆"""
        try:
            # 更新用户档案
            if gathered['user_preferences']:
                pref_entry = MemoryEntry(
                    f"pref_{datetime.now().timestamp()}",
                    "\n".join(gathered['user_preferences']),
                    memory_type='user',
                    tags=['auto_consolidated']
                )
                await self.memory_store.save(pref_entry)

            # 更新项目进度
            if gathered['project_updates']:
                proj_entry = MemoryEntry(
                    f"proj_{datetime.now().timestamp()}",
                    "\n".join(gathered['project_updates']),
                    memory_type='project',
                    tags=['auto_consolidated']
                )
                await self.memory_store.save(proj_entry)

            # 记录教训
            if gathered['learned_lessons']:
                lesson_entry = MemoryEntry(
                    f"lesson_{datetime.now().timestamp()}",
                    "\n".join(gathered['learned_lessons']),
                    memory_type='episodic',
                    tags=['learning', 'auto_consolidated'],
                    confidence=0.8
                )
                await self.memory_store.save(lesson_entry)

            return True
        except Exception as e:
            print(f"Consolidate phase error: {e}")
            return False

    async def prune_phase(self) -> int:
        """阶段 4：清理过期记忆"""
        removed_count = await self.memory_store.cleanup_expired()

        # 清理低置信度的项
        cutoff = datetime.now() - timedelta(days=30)
        count = 0

        for mem_type in ['episodic', 'feedback']:
            memory_ids = await self.memory_store.list_by_type(mem_type)
            for mid in memory_ids:
                entry = await self.memory_store.load(mid, mem_type)
                if (entry and entry.confidence < 0.3
                    and entry.last_modified < cutoff):
                    await self.memory_store.delete(mid, mem_type)
                    count += 1

        return removed_count + count

    async def consolidate(self, messages: List[str]) -> bool:
        """执行完整的整合流程"""
        if not self.should_consolidate():
            return False

        try:
            print("Starting memory consolidation...")

            # 四个阶段
            orient_result = await self.orient_phase(messages)
            gathered = await self.gather_phase(messages, orient_result)
            success = await self.consolidate_phase(gathered)
            pruned_count = await self.prune_phase()

            if success:
                self.state.last_consolidation = datetime.now()
                self.state.sessions_since_consolidation = 0
                print(f"Consolidation complete. Pruned {pruned_count} entries.")

            return success
        except Exception as e:
            print(f"Consolidation error: {e}")
            return False
