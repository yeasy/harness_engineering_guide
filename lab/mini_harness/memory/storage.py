"""
mini_harness/memory/storage.py - Memory storage layer
"""

import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryEntry:
    """记忆条目的完整定义"""

    def __init__(
        self,
        memory_id: str,
        content: str,
        memory_type: str = "episodic",
        tags: List[str] = None,
        confidence: float = 1.0,
        expiry: Optional[datetime] = None,
    ):
        self.id = memory_id
        self.content = content
        self.type = memory_type
        self.tags = tags or []
        self.confidence = confidence
        self.expiry = expiry
        self.created_at = datetime.now()
        self.last_modified = datetime.now()
        self.version = 1
        self.modified_by = "system"

    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        expiry_str = self.expiry.isoformat() if self.expiry else "never"
        frontmatter = f"""---
type: {self.type}
version: {self.version}
created_at: {self.created_at.isoformat()}
last_modified: {self.last_modified.isoformat()}
modified_by: {self.modified_by}
confidence: {self.confidence}
expiry: {expiry_str}
tags: {json.dumps(self.tags)}
---

"""
        return frontmatter + self.content

    @classmethod
    def from_markdown(cls, content: str, memory_id: str) -> "MemoryEntry":
        """从 Markdown 解析"""
        import yaml

        parts = content.split("---")
        if len(parts) < 3:
            # 没有 frontmatter，创建默认项
            return cls(memory_id, content)

        frontmatter_str = parts[1]
        body = "---".join(parts[2:]).strip()

        # 安全解析 YAML，处理可能的解析错误
        try:
            metadata = yaml.safe_load(frontmatter_str)
        except yaml.YAMLError as e:
            print(f"Warning: YAML parsing error in memory {memory_id}: {e}")
            metadata = {}

        # 安全提取 metadata 字段，处理类型转换错误
        try:
            expiry_raw = metadata.get("expiry") if metadata else None
            expiry = None
            if expiry_raw and expiry_raw != "never":
                if isinstance(expiry_raw, datetime):
                    expiry = expiry_raw
                else:
                    try:
                        expiry = datetime.fromisoformat(str(expiry_raw))
                    except (ValueError, TypeError):
                        expiry = None

            entry = cls(
                memory_id=memory_id,
                content=body,
                memory_type=metadata.get("type", "episodic") if metadata else "episodic",
                tags=metadata.get("tags", []) if metadata else [],
                confidence=metadata.get("confidence", 1.0) if metadata else 1.0,
                expiry=expiry,
            )

            entry.version = metadata.get("version", 1) if metadata else 1

            # 安全解析时间戳
            try:
                created_at_raw = metadata.get("created_at") if metadata else None
                if isinstance(created_at_raw, datetime):
                    entry.created_at = created_at_raw
                elif created_at_raw:
                    entry.created_at = datetime.fromisoformat(str(created_at_raw))
            except (ValueError, TypeError):
                entry.created_at = datetime.now()

            try:
                modified_raw = metadata.get("last_modified") if metadata else None
                if isinstance(modified_raw, datetime):
                    entry.last_modified = modified_raw
                elif modified_raw:
                    entry.last_modified = datetime.fromisoformat(str(modified_raw))
            except (ValueError, TypeError):
                entry.last_modified = datetime.now()

            entry.modified_by = metadata.get("modified_by", "unknown") if metadata else "unknown"

            return entry
        except Exception as e:
            print(f"Error parsing metadata for {memory_id}: {e}")
            # 返回带默认值的条目
            return cls(memory_id, body, memory_type="episodic")


class MemoryStore:
    """文件系统存储的记忆库"""

    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 子目录按类型组织
        self.types_dir = self.storage_dir / "by_type"
        self.types_dir.mkdir(exist_ok=True)

        # 缓存访问锁，防止竞态条件
        self._cache_lock = asyncio.Lock()

        self._init_type_dirs()

    def _init_type_dirs(self):
        """初始化类型子目录"""
        for mem_type in ["user", "feedback", "project", "reference", "episodic"]:
            (self.types_dir / mem_type).mkdir(exist_ok=True)

    def _get_path(self, memory_id: str, memory_type: str) -> Path:
        """获取记忆文件路径"""
        return self.types_dir / memory_type / f"{memory_id}.md"

    async def save(self, entry: MemoryEntry) -> bool:
        """保存记忆条目"""
        try:
            path = self._get_path(entry.id, entry.type)
            path.parent.mkdir(parents=True, exist_ok=True)

            # 版本控制：创建备份
            if path.exists():
                backup_path = path.with_suffix(".bak")
                path.rename(backup_path)

            # 写入新内容
            path.write_text(entry.to_markdown(), encoding="utf-8")

            return True
        except Exception as e:
            print(f"Error saving memory {entry.id}: {e}")
            return False

    async def load(self, memory_id: str, memory_type: str = "episodic") -> Optional[MemoryEntry]:
        """加载记忆条目"""
        try:
            path = self._get_path(memory_id, memory_type)
            if not path.exists():
                return None

            content = path.read_text(encoding="utf-8")
            return MemoryEntry.from_markdown(content, memory_id)
        except Exception as e:
            print(f"Error loading memory {memory_id}: {e}")
            return None

    async def list_by_type(self, memory_type: str) -> List[str]:
        """列出某类型的所有记忆"""
        type_dir = self.types_dir / memory_type
        if not type_dir.exists():
            return []

        return [f.stem for f in type_dir.glob("*.md")]

    async def delete(self, memory_id: str, memory_type: str = "episodic") -> bool:
        """删除记忆条目"""
        try:
            path = self._get_path(memory_id, memory_type)
            if path.exists():
                path.unlink()
            return True
        except Exception as e:
            print(f"Error deleting memory {memory_id}: {e}")
            return False

    async def search_by_tag(self, tag: str) -> List[MemoryEntry]:
        """按标签搜索"""
        results = []

        for memory_type in ["user", "feedback", "project", "reference", "episodic"]:
            type_dir = self.types_dir / memory_type
            if not type_dir.exists():
                continue

            for md_file in type_dir.glob("*.md"):
                entry = await self.load(md_file.stem, memory_type)
                if entry and tag in entry.tags:
                    results.append(entry)

        return results

    async def cleanup_expired(self) -> int:
        """清理过期的记忆"""
        count = 0
        now = datetime.now()

        for memory_type in ["user", "feedback", "project", "reference", "episodic"]:
            type_dir = self.types_dir / memory_type
            if not type_dir.exists():
                continue

            for md_file in type_dir.glob("*.md"):
                entry = await self.load(md_file.stem, memory_type)
                if entry and entry.expiry and entry.expiry < now:
                    await self.delete(entry.id, memory_type)
                    count += 1

        return count
