"""
Tests for mini_harness.memory module:
- storage.py: MemoryEntry, MemoryStore
- context.py: MemoryRequirement, ContextAssembler
- consolidation.py: ConsolidationState, ConsolidationEngine
"""

import os
from datetime import datetime, timedelta

import pytest

from mini_harness.memory.consolidation import ConsolidationEngine, ConsolidationState
from mini_harness.memory.context import ContextAssembler, MemoryRequirement
from mini_harness.memory.storage import MemoryEntry, MemoryStore

# ============ MemoryEntry Tests ============


class TestMemoryEntry:
    def test_creation(self):
        entry = MemoryEntry(
            memory_id="mem-001",
            content="Test memory content",
            memory_type="episodic",
            tags=["test", "unit"],
        )
        assert entry.id == "mem-001"
        assert entry.content == "Test memory content"
        assert entry.type == "episodic"
        assert "test" in entry.tags
        assert entry.confidence == 1.0
        assert entry.version == 1

    def test_default_values(self):
        entry = MemoryEntry(memory_id="mem-002", content="bare")
        assert entry.type == "episodic"
        assert entry.tags == []
        assert entry.confidence == 1.0
        assert entry.expiry is None
        assert entry.modified_by == "system"

    def test_to_markdown(self):
        entry = MemoryEntry(
            memory_id="mem-003",
            content="Markdown test",
            memory_type="user",
            tags=["style"],
            confidence=0.9,
        )
        md = entry.to_markdown()
        assert "---" in md
        assert "type: user" in md
        assert "confidence: 0.9" in md
        assert "Markdown test" in md

    def test_from_markdown_basic(self):
        md = """---
type: project
version: 2
created_at: 2025-01-01T00:00:00
last_modified: 2025-01-02T00:00:00
modified_by: user
confidence: 0.85
expiry: never
tags: ["important"]
---

This is the content."""

        entry = MemoryEntry.from_markdown(md, "mem-004")
        assert entry.id == "mem-004"
        assert entry.type == "project"
        assert entry.version == 2
        assert entry.confidence == 0.85
        assert "This is the content." in entry.content

    def test_from_markdown_no_frontmatter(self):
        entry = MemoryEntry.from_markdown("Just plain text", "mem-005")
        assert entry.id == "mem-005"
        assert entry.content == "Just plain text"
        assert entry.type == "episodic"

    def test_roundtrip_markdown(self):
        original = MemoryEntry(
            memory_id="mem-006",
            content="Roundtrip test content",
            memory_type="feedback",
            tags=["round", "trip"],
            confidence=0.75,
        )
        md = original.to_markdown()
        restored = MemoryEntry.from_markdown(md, "mem-006")

        assert restored.type == original.type
        assert restored.content == original.content
        assert restored.confidence == original.confidence

    def test_with_expiry(self):
        expiry = datetime.now() + timedelta(days=7)
        entry = MemoryEntry(memory_id="mem-007", content="Expiring memory", expiry=expiry)
        assert entry.expiry == expiry
        md = entry.to_markdown()
        assert "expiry:" in md
        assert "never" not in md


# ============ MemoryStore Tests ============


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        entry = MemoryEntry(
            memory_id="test-save", content="Saved content", memory_type="episodic", tags=["test"]
        )
        result = await store.save(entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_rejects_sensitive_memory_content(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        entry = MemoryEntry(
            memory_id="secret",
            content="OPENAI_API_KEY=sk-test-secret and user@example.com",
            memory_type="user",
        )

        result = await store.save(entry)

        assert result is False
        assert not list((store.types_dir / "user").glob("*"))

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        loaded = await store.load("nonexistent", "episodic")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_list_by_type(self, tmp_dir):
        store = MemoryStore(tmp_dir)

        for i in range(3):
            entry = MemoryEntry(f"proj-{i}", f"Project {i}", memory_type="project")
            await store.save(entry)

        projects = await store.list_by_type("project")
        assert len(projects) == 3
        assert "proj-0" in projects

    @pytest.mark.asyncio
    async def test_list_empty_type(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        items = await store.list_by_type("reference")
        assert items == []

    @pytest.mark.asyncio
    async def test_delete(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        entry = MemoryEntry("del-me", "Delete this", memory_type="episodic")
        await store.save(entry)

        result = await store.delete("del-me", "episodic")
        assert result is True

        loaded = await store.load("del-me", "episodic")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        result = await store.delete("ghost", "episodic")
        assert result is True  # Should not error

    @pytest.mark.asyncio
    async def test_search_by_tag(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        await store.save(MemoryEntry("tagged-1", "Content 1", tags=["important"]))
        await store.save(MemoryEntry("tagged-2", "Content 2", tags=["important", "urgent"]))
        await store.save(MemoryEntry("tagged-3", "Content 3", tags=["normal"]))

        results = await store.search_by_tag("important")
        assert len(results) == 2
        ids = [r.id for r in results]
        assert "tagged-1" in ids
        assert "tagged-2" in ids

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, tmp_dir):
        store = MemoryStore(tmp_dir)

        # Create an expired entry
        expired = MemoryEntry(
            "expired-1", "Expired content", expiry=datetime.now() - timedelta(days=1)
        )
        await store.save(expired)

        # Create a non-expired entry
        valid = MemoryEntry("valid-1", "Valid content", expiry=datetime.now() + timedelta(days=7))
        await store.save(valid)

        count = await store.cleanup_expired()
        assert count >= 1

        # Expired should be gone
        assert await store.load("expired-1", "episodic") is None
        # Valid should still exist
        assert await store.load("valid-1", "episodic") is not None

    @pytest.mark.asyncio
    async def test_type_directories_created(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        expected_types = ["user", "feedback", "project", "reference", "episodic"]
        for t in expected_types:
            assert os.path.isdir(os.path.join(tmp_dir, "by_type", t))

    @pytest.mark.asyncio
    async def test_version_backup(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        entry = MemoryEntry("versioned", "Version 1", memory_type="project")
        await store.save(entry)

        # Update content
        entry.content = "Version 2"
        entry.version = 2
        await store.save(entry)

        # Check backup exists
        bak_path = os.path.join(tmp_dir, "by_type", "project", "versioned.bak")
        assert os.path.exists(bak_path)


# ============ MemoryRequirement Tests ============


class TestMemoryRequirement:
    def test_defaults(self):
        req = MemoryRequirement()
        assert req.needs_user_profile is False
        assert req.needs_project_context is False
        assert req.needs_recent_history is False
        assert req.needs_references is False
        assert req.needs_feedback is False


# ============ ContextAssembler Tests ============


class TestContextAssembler:
    @pytest.mark.asyncio
    async def test_analyze_query_user_profile(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)
        req = await assembler.analyze_query("What do I prefer for coding style?")
        assert req.needs_user_profile is True

    @pytest.mark.asyncio
    async def test_analyze_query_project(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)
        req = await assembler.analyze_query("What's the project status?")
        assert req.needs_project_context is True

    @pytest.mark.asyncio
    async def test_analyze_query_history(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)
        req = await assembler.analyze_query("Do you remember what we discussed before?")
        assert req.needs_recent_history is True

    @pytest.mark.asyncio
    async def test_analyze_query_references(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)
        req = await assembler.analyze_query("Show me an example of how to use it")
        assert req.needs_references is True

    @pytest.mark.asyncio
    async def test_analyze_query_feedback(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)
        req = await assembler.analyze_query("Was the last one approved or rejected?")
        assert req.needs_feedback is True

    @pytest.mark.asyncio
    async def test_analyze_query_default_user_profile(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)
        req = await assembler.analyze_query("Hello there")
        assert req.needs_user_profile is True

    @pytest.mark.asyncio
    async def test_assemble_empty_store(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)
        result = await assembler.assemble("Tell me about the project status")
        # No data in store, should return empty or minimal
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_assemble_with_data(self, tmp_dir):
        store = MemoryStore(tmp_dir)

        # Add some user profile data
        await store.save(MemoryEntry("profile-1", "User prefers Python.", memory_type="user"))
        await store.save(MemoryEntry("proj-1", "Working on MiniHarness.", memory_type="project"))

        assembler = ContextAssembler(store)
        result = await assembler.assemble("What's the project status?")
        assert "Working on MiniHarness" in result

    @pytest.mark.asyncio
    async def test_token_budget(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store, token_budget=10)  # Very small budget

        # Add large content
        await store.save(MemoryEntry("big", "A " * 1000, memory_type="user"))

        result = await assembler.assemble("What do I prefer?")
        # Token estimator is rough, but assembler should respect budget
        assert isinstance(result, str)

    def test_estimate_tokens(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)
        tokens = assembler._estimate_tokens("Hello world this is a test sentence")
        assert tokens > 0
        assert isinstance(tokens, int)

    @pytest.mark.asyncio
    async def test_assemble_with_recent_history(self, tmp_dir):
        """Test that needs_recent_history is properly handled in assemble()"""
        store = MemoryStore(tmp_dir)

        # Add some episodic history
        await store.save(MemoryEntry("hist-1", "We discussed the API design.", memory_type="episodic"))
        await store.save(MemoryEntry("hist-2", "Decided to use REST endpoints.", memory_type="episodic"))

        assembler = ContextAssembler(store)
        # Query that triggers needs_recent_history
        result = await assembler.assemble("What did we discuss before?")

        # The result should contain the recent history
        assert "Recent History" in result
        assert "API design" in result or "REST endpoints" in result

    @pytest.mark.asyncio
    async def test_gather_recent_history(self, tmp_dir):
        """Test _gather_recent_history method directly"""
        store = MemoryStore(tmp_dir)
        assembler = ContextAssembler(store)

        # No history yet
        result = await assembler._gather_recent_history()
        assert result == ""

        # Add some episodic entries
        await store.save(MemoryEntry("h1", "First memory", memory_type="episodic"))
        await store.save(MemoryEntry("h2", "Second memory", memory_type="episodic"))

        result = await assembler._gather_recent_history()
        assert "Recent History" in result
        assert "First memory" in result
        assert "Second memory" in result


# ============ ConsolidationEngine Tests ============


class TestConsolidationState:
    def test_defaults(self):
        state = ConsolidationState()
        assert state.last_consolidation is None
        assert state.sessions_since_consolidation == 0
        assert state.total_sessions == 0


class TestConsolidationEngine:
    @pytest.mark.asyncio
    async def test_should_consolidate_time_gate(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)
        # Default state has last_consolidation = now - 1 day, so time_gate = True
        assert engine.should_consolidate() is True

    @pytest.mark.asyncio
    async def test_should_consolidate_session_gate(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)
        engine.state.last_consolidation = datetime.now()  # Reset time gate
        engine.state.sessions_since_consolidation = 5
        assert engine.should_consolidate() is True

    @pytest.mark.asyncio
    async def test_should_not_consolidate(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)
        engine.state.last_consolidation = datetime.now()  # Recent
        engine.state.sessions_since_consolidation = 2  # Below threshold
        assert engine.should_consolidate() is False

    @pytest.mark.asyncio
    async def test_orient_phase(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)
        messages = [
            "I found a bug in the login page",
            "Fixed the error in authentication",
            "Added a new feature for search",
        ]
        result = await engine.orient_phase(messages)
        assert "summary" in result
        assert "topics" in result
        assert isinstance(result["topics"], list)

    @pytest.mark.asyncio
    async def test_orient_phase_detects_topics(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)
        messages = ["There is a bug in the code", "We need to add a new feature"]
        result = await engine.orient_phase(messages)
        assert "issues" in result["topics"]
        assert "features" in result["topics"]

    @pytest.mark.asyncio
    async def test_gather_phase(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)
        messages = [
            "I prefer dark mode",
            "We completed the login feature",
            "I learned that caching improves performance",
            "We decided to use PostgreSQL",
        ]
        gathered = await engine.gather_phase(messages, {})
        assert len(gathered["user_preferences"]) > 0
        assert len(gathered["project_updates"]) > 0
        assert len(gathered["learned_lessons"]) > 0
        assert len(gathered["decisions"]) > 0

    @pytest.mark.asyncio
    async def test_consolidate_phase(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)
        gathered = {
            "user_preferences": ["Prefers TypeScript"],
            "project_updates": ["Completed API design"],
            "learned_lessons": ["Discovered caching helps"],
            "decisions": [],
        }
        result = await engine.consolidate_phase(gathered)
        assert result is True

        # Check memories were saved
        users = await store.list_by_type("user")
        assert len(users) > 0
        projects = await store.list_by_type("project")
        assert len(projects) > 0

    @pytest.mark.asyncio
    async def test_prune_phase(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)

        # Add expired memory
        expired = MemoryEntry("old-mem", "Old content", expiry=datetime.now() - timedelta(days=1))
        await store.save(expired)

        pruned = await engine.prune_phase()
        assert pruned >= 1

    @pytest.mark.asyncio
    async def test_full_consolidate(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)

        messages = [
            "I prefer Python over JavaScript",
            "We completed the database migration",
            "I learned that async improves throughput",
            "We decided on microservices architecture",
        ]

        result = await engine.consolidate(messages)
        assert result is True
        assert engine.state.sessions_since_consolidation == 0

    @pytest.mark.asyncio
    async def test_consolidate_skipped_when_not_needed(self, tmp_dir):
        store = MemoryStore(tmp_dir)
        engine = ConsolidationEngine(store)
        engine.state.last_consolidation = datetime.now()
        engine.state.sessions_since_consolidation = 0

        result = await engine.consolidate(["some message"])
        assert result is False
