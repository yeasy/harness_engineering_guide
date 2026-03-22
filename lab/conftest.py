"""
Root conftest.py - shared fixtures for all tests
"""

import sys
import os
import pytest
import tempfile
import shutil

# Ensure mini_harness is importable
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory, cleaned up after test."""
    d = tempfile.mkdtemp(prefix="miniharness_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_tool_schema():
    """Sample tool schema for testing."""
    return {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Bash command"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30}
        },
        "required": ["command"]
    }
