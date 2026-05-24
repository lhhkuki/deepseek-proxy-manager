"""Tests for protocol translation — the core proxy logic.

Run: pytest tests/ -v
"""

import json
import sys
import types

import pytest

# ── Setup: patch dependencies before importing handler ──
sys.path.insert(0, "/tmp/deepseek-proxy-manager")

# Mock threads, queues, filesystem so handler imports cleanly
import threading
import queue
sys.modules["proxy.config"] = types.ModuleType("proxy.config")
cfg = sys.modules["proxy.config"]
cfg.LOG_QUEUE = queue.Queue()
cfg._REASONING_CACHE = {}
cfg._REASONING_LOCK = threading.Lock()
cfg._REASONING_CACHE_TTL = 3600

def _fake_load_config():
    return {
        "models": [
            {"id": "deepseek-v4-pro", "enabled": True,
             "base_url": "https://api.deepseek.com", "api_key": "sk-test",
             "reasoning": False, "upstream_format": "openai"},
        ]
    }

def _fake_get_active():
    return _fake_load_config()["models"][0]

cfg.load_config = _fake_load_config
cfg.get_active_model_config = _fake_get_active
cfg.cache_reasoning = lambda *a, **kw: None

# Now import the handler class
from proxy.handler import ProxyHandler


class TestProxyHandler(ProxyHandler):
    """Minimal handler subclass for testing translations — no HTTP server."""
    def __init__(self):
        self.ALLOWED_ROLES = {"system", "user", "assistant", "tool"}
        self.ROLE_MAP = {"developer": "system"}
        self.MAX_RETRIES = 3
        self.RETRY_DELAY = 2

    def _log_detail(self, msg): pass
    def log_request(self, code="-", size="-"): pass

handler = TestProxyHandler()


# ═══════════════════════════════════════════════════════════════
# OpenAI Chat Completions translation
# ═══════════════════════════════════════════════════════════════

def test_basic_user_message():
    """A single user message → one chat message."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Hello"}]}
        ],
    }
    result = handler._to_chat(req)
    assert result["model"] == "deepseek-v4-pro"
    assert len(result["messages"]) == 1
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][0]["content"] == "Hello"


def test_system_instruction():
    """instructions field → role=system message prepended."""
    req = {
        "model": "deepseek-v4-pro",
        "instructions": "You are helpful.",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}
        ],
    }
    result = handler._to_chat(req)
    assert result["messages"][0]["role"] == "system"
    assert result["messages"][0]["content"] == "You are helpful."
    assert result["messages"][1]["role"] == "user"


def test_system_in_input_takes_priority():
    """If input already has role=system, instructions is not prepended."""
    req = {
        "model": "deepseek-v4-pro",
        "instructions": "Version A",
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": "Version B"}]},
            {"role": "user", "content": [{"type": "input_text", "text": "Hi"}]},
        ],
    }
    result = handler._to_chat(req)
    assert result["messages"][0]["content"] == "Version B"
    assert len(result["messages"]) == 2  # only system + user, no duplicate


def test_function_call_translation():
    """Responses function_call → Chat tool_calls."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "search python"}]},
            {"type": "function_call", "call_id": "fc_001", "name": "web_search",
             "arguments": '{"query": "python"}'},
            {"type": "function_call_output", "call_id": "fc_001",
             "output": "5 results found"},
        ],
    }
    result = handler._to_chat(req)
    msgs = result["messages"]
    assert len(msgs) == 3  # user + assistant(tool_calls) + tool(output)
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "web_search"


def test_function_call_output_translation():
    """Responses function_call_output → Chat role=tool."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "search"}]},
            {"type": "function_call", "call_id": "fc_001", "name": "web_search",
             "arguments": '{"query":"x"}'},
            {"type": "function_call_output", "call_id": "fc_001",
             "output": "Results: found 5 items"},
        ],
    }
    result = handler._to_chat(req)
    msgs = result["messages"]
    assert msgs[2]["role"] == "tool"
    assert msgs[2]["tool_call_id"] == "fc_001"
    assert "found 5 items" in msgs[2]["content"]


def test_consecutive_role_merge():
    """Two consecutive user messages → merged into one."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Part 1"}]},
            {"role": "user", "content": [{"type": "input_text", "text": "Part 2"}]},
        ],
    }
    result = handler._to_chat(req)
    msgs = result["messages"]
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Part 1\nPart 2"


def test_orphan_tool_call_cleanup():
    """Tool call without matching output → stripped."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "query"}]},
            {"type": "function_call", "call_id": "orphan_1", "name": "read_file",
             "arguments": '{"path":"/x"}'},
            # No function_call_output for orphan_1 — it should be removed
        ],
    }
    result = handler._to_chat(req)
    msgs = result["messages"]
    # Only the user message should remain
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"


def test_reasoning_skip():
    """reasoning items are skipped in translation."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Think hard"}]},
            {"type": "reasoning", "content": "Let me think about this..."},
            {"role": "assistant", "content": [{"type": "output_text", "text": "Answer"}]},
        ],
    }
    result = handler._to_chat(req)
    msgs = result["messages"]
    assert len(msgs) == 2  # user + assistant, reasoning skipped


def test_tools_translation():
    """web_search tool → OpenAI function definition."""
    req = {
        "model": "deepseek-v4-pro",
        "tools": [
            {"type": "web_search"},
            {"type": "function", "name": "read_file",
             "description": "Read file", "parameters": {}},
        ],
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
    }
    result = handler._to_chat(req)
    tools = result.get("tools", [])
    assert len(tools) == 2
    assert tools[0]["function"]["name"] == "web_search"
    assert tools[1]["function"]["name"] == "read_file"


# ═══════════════════════════════════════════════════════════════
# Anthropic Messages translation
# ═══════════════════════════════════════════════════════════════

def test_anthropic_basic():
    """Basic message → Anthropic format."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Hello"}]}
        ],
    }
    result = handler._to_anthropic(req)
    assert result["model"] == "deepseek-v4-pro"
    assert len(result["messages"]) == 1
    assert result["messages"][0]["role"] == "user"
    assert result["messages"][0]["content"] == "Hello"


def test_anthropic_system():
    """instructions → system field (not a message)."""
    req = {
        "model": "deepseek-v4-pro",
        "instructions": "You are Claude.",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}
        ],
    }
    result = handler._to_anthropic(req)
    assert result["system"] == "You are Claude."
    assert result["messages"][0]["role"] == "user"


def test_anthropic_tool_use():
    """function_call → Anthropic tool_use block."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "search"}]},
            {"type": "function_call", "call_id": "fc_1", "name": "web_search",
             "arguments": '{"query":"x"}'},
            {"type": "function_call_output", "call_id": "fc_1",
             "output": "5 results found"},
        ],
    }
    result = handler._to_anthropic(req)
    msgs = result["messages"]
    # User, assistant (with tool_use), user (with tool_result)
    assert len(msgs) == 3
    assistant = msgs[1]
    assert assistant["role"] == "assistant"
    assert assistant["content"][0]["type"] == "tool_use"
    assert assistant["content"][0]["name"] == "web_search"

    tool_result = msgs[2]
    assert tool_result["role"] == "user"
    assert tool_result["content"][0]["type"] == "tool_result"


def test_anthropic_orphan_tool_use():
    """function_call without output → stripped in Anthropic."""
    req = {
        "model": "deepseek-v4-pro",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "go"}]},
            {"type": "function_call", "call_id": "orphan", "name": "read",
             "arguments": "{}"},
        ],
    }
    result = handler._to_anthropic(req)
    # Orphan should be removed, only user message remains
    assert len(result["messages"]) == 1
    assert result["messages"][0]["role"] == "user"


# ═══════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════

def test_empty_input():
    """Empty input → empty messages list."""
    req = {"model": "deepseek-v4-pro", "input": []}
    result = handler._to_chat(req)
    assert result["messages"] == []


def test_invalid_input_type():
    """Non-list input → ValueError."""
    with pytest.raises(ValueError, match="must be a list"):
        handler._to_chat({"model": "x", "input": "not a list"})

    with pytest.raises(ValueError, match="must be a list"):
        handler._to_anthropic({"model": "x", "input": "not a list"})


def test_stream_option():
    """stream=True → propagated to chat request."""
    req = {
        "model": "deepseek-v4-pro",
        "stream": True,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Hi"}]}],
    }
    result = handler._to_chat(req)
    assert result["stream"] is True
    assert "stream_options" in result
