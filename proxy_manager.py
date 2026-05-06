#!/usr/bin/env python3
"""
DeepSeek Proxy Manager — system-tray GUI for managing the Codex ↔ DeepSeek proxy.
"""

import json
import os
import sys
import time
import uuid
import hashlib
import threading
import traceback
import queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server for concurrent subagent requests."""
    daemon_threads = True
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.client import RemoteDisconnected
from datetime import datetime

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import pystray
from PIL import Image, ImageDraw

# ── config paths ────────────────────────────────────────────────────
HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(HOME, ".codex", "proxy_config.json")
AUTH_PATH = os.path.join(HOME, ".codex", "auth.json")

# Reasoning-content cache — DeepSeek V4 Pro requires reasoning_content
# to be passed back on follow-up turns, but Codex doesn't store it.
# We cache it here and re-inject it into incoming requests.
_REASONING_CACHE = {}
_MAX_REASONING = 100


def _cache_reasoning(chat_req, reasoning_content):
    """Store reasoning_content keyed by hash of the last trigger message."""
    if not reasoning_content:
        return
    msgs = chat_req.get("messages", [])
    if not msgs:
        return
    last = msgs[-1]
    pc = last.get("content") or ""
    if isinstance(pc, list):
        pc = json.dumps(pc, ensure_ascii=False)
    if not pc:
        return
    key = hashlib.sha256(pc.encode()).hexdigest()[:16]
    _REASONING_CACHE[key] = reasoning_content
    # Trim
    while len(_REASONING_CACHE) > _MAX_REASONING:
        _REASONING_CACHE.pop(next(iter(_REASONING_CACHE)))

DEFAULT_CONFIG = {
    "port": 15800,
    "deepseek_base": "https://api.deepseek.com",
    "models": [
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "enabled": True},
        {"id": "deepseek-chat", "name": "DeepSeek V4 Flash", "enabled": True},
    ]
}


def is_already_running(port):
    """Check if another proxy manager instance is already running on this port."""
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_api_key():
    if os.path.exists(AUTH_PATH):
        with open(AUTH_PATH) as f:
            return json.load(f).get("OPENAI_API_KEY", "")
    return ""


def save_api_key(key):
    os.makedirs(os.path.dirname(AUTH_PATH), exist_ok=True)
    data = {}
    if os.path.exists(AUTH_PATH):
        with open(AUTH_PATH) as f:
            data = json.load(f)
    data["OPENAI_API_KEY"] = key
    with open(AUTH_PATH, "w") as f:
        json.dump(data, f, indent=2)


# ── autostart ────────────────────────────────────────────────────────
STARTUP_BAT = os.path.join(os.environ.get("APPDATA", ""),
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "DeepSeekProxy.bat")


def is_autostart_enabled():
    return os.path.exists(STARTUP_BAT)


def set_autostart(enable):
    if enable:
        if getattr(sys, 'frozen', False):
            target = f'start "" "{sys.executable}"'
        else:
            target = f'start "" pythonw "{os.path.abspath(__file__)}"'
        with open(STARTUP_BAT, "w") as f:
            f.write(f"@echo off\n{target}\n")
    else:
        if os.path.exists(STARTUP_BAT):
            os.remove(STARTUP_BAT)


# ── light theme colors ────────────────────────────────────────────────
BG_DARK      = "#ffffff"
BG_CARD      = "#f5f5f7"
BG_INPUT     = "#e8e8ed"
FG_PRIMARY   = "#1d1d1f"
FG_SECONDARY = "#6e6e73"
FG_MUTED     = "#aeaeb2"
ACCENT       = "#4A90D9"
GREEN        = "#34c759"
RED          = "#ff3b30"
BORDER       = "#d2d2d7"
FONT         = "Segoe UI"
FONT_MONO    = "Consolas"


# ── proxy server (runs in a thread) ──────────────────────────────────

LOG_QUEUE = queue.Queue()

class ProxyHandler(BaseHTTPRequestHandler):
    """Translates OpenAI Responses API → DeepSeek Chat Completions API."""

    ALLOWED_ROLES = {"system", "user", "assistant", "tool"}
    ROLE_MAP = {"developer": "system"}

    def log_request(self, code="-", size="-"):
        msg = f"{self.command} {self.path} → {code}"
        LOG_QUEUE.put(msg)

    def do_GET(self):
        if self.path == "/v1/models":
            cfg = load_config()
            models = []
            for m in cfg.get("models", []):
                if m.get("enabled", True):
                    models.append({
                        "id": m["id"], "object": "model",
                        "created": 1700000000, "owned_by": "custom"
                    })
            self._json(200, {"object": "list", "data": models})
        elif self.path == "/v1/me":
            self._json(200, {
                "id": "user-proxy", "object": "user",
                "name": "Proxy User", "email": "proxy@local",
                "role": "owner", "added": 1700000000,
            })
        elif self.path == "/v1/organizations":
            self._json(200, {
                "object": "list", "data": [{
                    "id": "org-proxy", "object": "organization",
                    "name": "Proxy Org", "role": "owner",
                    "is_default": True,
                }]
            })
        elif self.path in ("/", "/health"):
            self._json(200, {"status": "ok"})
        elif self.path.startswith("/v1/"):
            self._json(200, {"object": "empty", "data": []})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/v1/responses":
            self._handle_responses()
        elif self.path.startswith("/v1/"):
            self._pass_through(self.path[3:])
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_responses(self):
        body = self._read_body()
        stream = body.get("stream", False)
        chat_req = self._to_chat(body)

        try:
            if stream:
                self._stream(chat_req)
            else:
                data = self._fetch("/chat/completions", chat_req)
                self._json(200, self._to_resp(data, chat_req))
        except HTTPError as e:
            err = ""
            try:
                err = e.read().decode(errors="replace")[:300]
            except Exception:
                pass
            LOG_QUEUE.put(f"Upstream {e.code}: {err}")
            self._safe_json(e.code, {"error": f"Upstream {e.code}: {err}"})
        except ConnectionAbortedError:
            pass  # client disconnected, nothing to do
        except Exception as e:
            LOG_QUEUE.put(f"FATAL: {e}")
            print(f"[FATAL] {traceback.format_exc()}", file=sys.stderr, flush=True)
            self._safe_json(502, {"error": str(e)})

    def _pass_through(self, path):
        body = self._read_body()
        try:
            data = self._fetch(f"/{path}", body)
            self._json(200, data)
        except Exception as e:
            self._json(500, {"error": str(e)})

    # ── translation ────────────────────────────────────────────────

    def _to_chat(self, req):
        messages = []
        instr = req.get("instructions", "")
        if instr:
            messages.append({"role": "system", "content": instr})

        for item in req.get("input", []):
            item_type = item.get("type", "")
            role = item.get("role", "")

            # ── function_call_output → tool message ───────────────
            if item_type == "function_call_output":
                messages.append({
                    "role": "tool",
                    "tool_call_id": item.get("call_id", ""),
                    "content": self._extract_text(item.get("output", "")),
                })
                continue

            # ── function_call → assistant message + tool_calls ────
            if item_type == "function_call":
                tc = {
                    "type": "function",
                    "id": item.get("call_id", ""),
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", ""),
                    }
                }
                # Merge with previous assistant message if it already has tool_calls
                if messages and messages[-1].get("role") == "assistant" and messages[-1].get("tool_calls"):
                    messages[-1]["tool_calls"].append(tc)
                else:
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tc],
                    })
                continue

            # ── reasoning → skip ──────────────────────────────────
            if item_type == "reasoning":
                continue

            # ── item_reference → skip ────────────────────────────
            if item_type == "item_reference":
                continue

            # ── regular message ───────────────────────────────────
            role = self.ROLE_MAP.get(role, role)
            if role not in self.ALLOWED_ROLES:
                role = "user"
            content = self._extract_text(item.get("content", ""))

            msg = {"role": role, "content": content}

            # Tool call ID for tool results (Chat Completions format)
            if role == "tool":
                tc_id = item.get("tool_call_id") or item.get("call_id", "")
                if tc_id:
                    msg["tool_call_id"] = tc_id

            # Translate tool_calls from Responses → Chat Completions format
            tcs = item.get("tool_calls") or []
            if tcs and role == "assistant":
                chat_tcs = []
                for tc in tcs:
                    ctc = {"type": "function", "id": tc.get("call_id", tc.get("id", ""))}
                    ctc["function"] = {
                        "name": tc.get("name", ""),
                        "arguments": tc.get("arguments", ""),
                    }
                    chat_tcs.append(ctc)
                msg["tool_calls"] = chat_tcs

            messages.append(msg)

        # Re-inject cached reasoning_content into assistant messages that lack it.
        for i, m in enumerate(messages):
            if m.get("role") == "assistant" and not m.get("reasoning_content") and i > 0:
                prev = messages[i - 1]
                pc = prev.get("content") or ""
                if isinstance(pc, list):
                    pc = json.dumps(pc, ensure_ascii=False)
                if pc:
                    key = hashlib.sha256(pc.encode()).hexdigest()[:16]
                    rc = _REASONING_CACHE.get(key)
                    if rc:
                        m["reasoning_content"] = rc
                        continue
                # Fallback: inject empty reasoning to satisfy API requirement
                m["reasoning_content"] = ""

        model = self._map_model(req.get("model", "deepseek-v4-pro"))
        chat = {
            "model": model,
            "messages": messages,
            "stream": req.get("stream", False),
        }
        # Explicitly enable thinking for V4 Pro / reasoner models
        if "pro" in model or "reasoner" in model:
            chat["thinking"] = {"type": "enabled"}
        for k in ("temperature", "top_p", "frequency_penalty", "presence_penalty"):
            if k in req:
                chat[k] = req[k]
        if "max_output_tokens" in req:
            chat["max_tokens"] = req["max_output_tokens"]
        if "tools" in req:
            tools = self._xlat_tools(req["tools"])
            if tools:
                chat["tools"] = tools
        if "tool_choice" in req:
            chat["tool_choice"] = req["tool_choice"]
        # Structured output: text.format → response_format
        text_cfg = req.get("text", {})
        if isinstance(text_cfg, dict) and "format" in text_cfg:
            chat["response_format"] = text_cfg["format"]
        return chat

    @staticmethod
    def _extract_text(content):
        """Extract plain text from content which may be a string or array of parts."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, str):
                    parts.append(p)
                elif isinstance(p, dict):
                    t = p.get("type", "")
                    if t == "input_text" or t == "output_text":
                        parts.append(p.get("text", ""))
                    elif t == "input_image":
                        parts.append(str(p.get("image_url", "")))
                    else:
                        parts.append(p.get("text", json.dumps(p)))
            return "\n".join(parts) if parts else ""
        return str(content) if content else ""

    def _map_model(self, model_name):
        """Map unknown model names (e.g. gpt-5.4 from Codex subagents) to configured model."""
        cfg = load_config()
        known = {m["id"] for m in cfg.get("models", []) if m.get("enabled", True)}
        if model_name in known:
            return model_name
        # Map to first enabled model as fallback
        for m in cfg.get("models", []):
            if m.get("enabled", True):
                LOG_QUEUE.put(f"Mapped model '{model_name}' → '{m['id']}'")
                return m["id"]
        return "deepseek-chat"

    def _xlat_tools(self, tools):
        """Convert tool definitions to Chat Completions format.
        Handles function, custom, namespace → wraps as {type: function, function: {...}}"""
        result = []
        for tool in tools:
            t = tool.get("type", "")
            # Only support function-like tools (skip web_search, code_interpreter)
            if t not in ("", "function", "custom", "namespace"):
                continue
            if "function" in tool:
                result.append(tool)
            elif "name" in tool:
                fn = {}
                for k in ("name", "description", "parameters", "strict"):
                    if k in tool:
                        fn[k] = tool[k]
                result.append({"type": "function", "function": fn})
            else:
                # Custom/namespace tool without name — wrap what we can
                fn = {"name": tool.get("id", tool.get("name", f"tool_{uuid.uuid4().hex[:8]}"))}
                if "description" in tool:
                    fn["description"] = tool["description"]
                result.append({"type": "function", "function": fn})
        return result

    def _to_resp(self, chat_resp, chat_req=None):
        choice = (chat_resp.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        usage = chat_resp.get("usage", {})
        rid = chat_resp.get("id", self._gid("resp_"))
        mid = self._gid("msg_")
        content = msg.get("content") or ""
        parts = [{"type": "output_text", "text": content, "annotations": []}]
        output = [{"id": mid, "type": "message", "role": "assistant", "content": parts}]

        # Cache reasoning_content for next turn
        rc = msg.get("reasoning_content", "")
        if rc and chat_req:
            _cache_reasoning(chat_req, rc)

        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            output.append({
                "id": self._gid("fc_"),
                "type": "function_call",
                "call_id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": fn.get("arguments", ""),
            })

        return {
            "id": rid, "object": "response",
            "created_at": chat_resp.get("created", int(time.time())),
            "model": chat_resp.get("model", "unknown"),
            "status": "completed", "output": output,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }
        }

    def _stream(self, chat_req):
        """Stream proxy with full tool-call translation support."""
        resp = self._do_fetch("/chat/completions", chat_req)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        rid = self._gid("resp_")
        text_msg_id = self._gid("msg_")
        started = False
        text_closed = False
        full_text = ""
        full_reasoning = ""
        usage_info = {}
        # Track tool calls being built: index → {call_id, name, fc_id, args}
        tcs = {}
        output_items = []  # accumulated output for response.completed

        def open_text_msg():
            nonlocal text_closed
            if text_closed:
                text_msg_id_new = self._gid("msg_")
                tcs["__text_msg_id"] = text_msg_id_new
                self._sse("response.output_item.added", {
                    "type": "response.output_item.added",
                    "item": {"id": text_msg_id_new, "type": "message", "role": "assistant", "content": []}
                })
                self._sse("response.content_part.added", {
                    "type": "response.content_part.added",
                    "item_id": text_msg_id_new,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                })
                return text_msg_id_new
            return text_msg_id

        def close_text_msg():
            nonlocal text_closed, full_text
            if not text_closed and (full_text or started):
                text_closed = True
                cur_mid = tcs.pop("__text_msg_id", text_msg_id)
                self._sse("response.output_text.done", {
                    "type": "response.output_text.done",
                    "item_id": cur_mid, "output_index": 0, "content_index": 0,
                    "text": full_text,
                })
                self._sse("response.output_item.done", {
                    "type": "response.output_item.done",
                    "item": {"id": cur_mid, "type": "message", "role": "assistant",
                             "content": [{"type": "output_text", "text": full_text, "annotations": []}]}
                })
                output_items.append({"id": cur_mid, "type": "message", "role": "assistant",
                                     "content": [{"type": "output_text", "text": full_text, "annotations": []}]})

        for line in resp:
            raw = line.decode("utf-8").strip()
            if not raw or raw.startswith(":"):
                continue

            if raw == "data: [DONE]":
                # Finalize any open text
                if not text_closed and full_text:
                    close_text_msg()
                # Finalize any open tool calls
                for idx in sorted(tcs.keys()):
                    if idx == "__text_msg_id":
                        continue
                    tc = tcs[idx]
                    self._sse("response.function_call_arguments.done", {
                        "type": "response.function_call_arguments.done",
                        "item_id": tc["fc_id"],
                        "name": tc["name"],
                        "arguments": tc["args"],
                    })
                    self._sse("response.output_item.done", {
                        "type": "response.output_item.done",
                        "item": {"id": tc["fc_id"], "type": "function_call",
                                 "call_id": tc["call_id"], "name": tc["name"],
                                 "arguments": tc["args"]}
                    })
                    output_items.append({"id": tc["fc_id"], "type": "function_call",
                                         "call_id": tc["call_id"], "name": tc["name"],
                                         "arguments": tc["args"]})
                # Send response.completed
                # Cache reasoning_content for next turn
                if full_reasoning:
                    _cache_reasoning(chat_req, full_reasoning)

                self._sse("response.completed", {
                    "type": "response.completed",
                    "response": {
                        "id": rid, "object": "response", "model": chat_req["model"],
                        "status": "completed", "output": output_items,
                        "usage": usage_info,
                    }
                })
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                continue

            if not raw.startswith("data: "):
                continue

            chunk = json.loads(raw[6:])
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta", {})

            # ── initial events ──────────────────────────────────
            if not started:
                started = True
                self._sse("response.created", {
                    "type": "response.created",
                    "response": {"id": rid, "object": "response", "model": chat_req["model"],
                                 "status": "in_progress", "output": []}
                })
                self._sse("response.output_item.added", {
                    "type": "response.output_item.added",
                    "item": {"id": text_msg_id, "type": "message", "role": "assistant", "content": []}
                })
                self._sse("response.content_part.added", {
                    "type": "response.content_part.added",
                    "item_id": text_msg_id,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                })

            # ── text delta ──────────────────────────────────────
            text = delta.get("content", "")
            if text:
                full_text += text
                self._sse("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "item_id": text_msg_id, "output_index": 0, "content_index": 0,
                    "delta": text,
                })

            # ── reasoning delta (not forwarded to Codex) ───────
            rc_delta = delta.get("reasoning_content", "")
            if rc_delta:
                full_reasoning += rc_delta

            # ── tool call delta ─────────────────────────────────
            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index", 0)

                if idx not in tcs:
                    # First time seeing this tool call → close text, open function_call
                    if not text_closed:
                        close_text_msg()
                    fc_id = self._gid("fc_")
                    tcs[idx] = {
                        "call_id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "fc_id": fc_id,
                        "args": "",
                    }
                    self._sse("response.output_item.added", {
                        "type": "response.output_item.added",
                        "item": {"id": fc_id, "type": "function_call",
                                 "call_id": tcs[idx]["call_id"],
                                 "name": tcs[idx]["name"],
                                 "arguments": ""}
                    })

                # Append function name if it came later
                fn_name = tc.get("function", {}).get("name", "")
                if fn_name and not tcs[idx]["name"]:
                    tcs[idx]["name"] = fn_name

                # Append arguments
                fn_args = tc.get("function", {}).get("arguments", "")
                if fn_args:
                    tcs[idx]["args"] += fn_args
                    self._sse("response.function_call_arguments.delta", {
                        "type": "response.function_call_arguments.delta",
                        "item_id": tcs[idx]["fc_id"],
                        "delta": fn_args,
                    })

            # ── usage in final chunk ────────────────────────────
            u = chunk.get("usage")
            if u:
                usage_info = {
                    "input_tokens": u.get("prompt_tokens", 0),
                    "output_tokens": u.get("completion_tokens", 0),
                    "total_tokens": u.get("total_tokens", 0),
                }

    # ── helpers ─────────────────────────────────────────────────────

    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    @classmethod
    def _do_fetch(cls, path, data, timeout=120):
        """Fetch from DeepSeek with retry."""
        cfg = load_config()
        base = cfg.get("deepseek_base", "https://api.deepseek.com")
        key = load_api_key()
        last_err = None
        for attempt in range(cls.MAX_RETRIES):
            try:
                req = Request(f"{base}{path}", data=json.dumps(data).encode(), headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}",
                }, method="POST")
                return urlopen(req, timeout=timeout)
            except (RemoteDisconnected, ConnectionResetError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < cls.MAX_RETRIES - 1:
                    time.sleep(cls.RETRY_DELAY * (attempt + 1))
        raise last_err or RuntimeError("max retries exceeded")

    def _fetch(self, path, data):
        resp = self._do_fetch(path, data)
        return json.loads(resp.read())

    def _read_body(self):
        cl = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(cl)) if cl > 0 else {}

    def _json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _safe_json(self, status, data):
        """Send JSON response; fail silently if client disconnected."""
        try:
            self._json(status, data)
        except (ConnectionAbortedError, ConnectionResetError, OSError):
            pass

    def _sse(self, event_type, data):
        self.wfile.write(f"event: {event_type}\n".encode())
        self.wfile.write(f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
        self.wfile.flush()

    def _gid(self, prefix=""):
        return f"{prefix}{uuid.uuid4().hex[:24]}"


# ── proxy server thread ──────────────────────────────────────────────

class ProxyServer:
    def __init__(self):
        self.server = None
        self.thread = None
        self.running = False

    def start(self, port):
        if self.running:
            return
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", port), ProxyHandler)
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            self.running = True
            LOG_QUEUE.put(f"Proxy started on port {port}")
        except Exception as e:
            LOG_QUEUE.put(f"ERROR: {e}")
            raise

    def _run(self):
        self.server.serve_forever()

    def stop(self):
        if not self.running:
            return
        self.running = False
        # Shutdown in thread to not block GUI
        srv = self.server
        def _shutdown():
            try:
                srv.shutdown()
            except Exception:
                pass
        threading.Thread(target=_shutdown, daemon=True).start()
        LOG_QUEUE.put("Proxy stopped")

    def is_running(self):
        return self.running


# ── GUI ──────────────────────────────────────────────────────────────

class ProxyManagerApp:
    def __init__(self):
        self.proxy = ProxyServer()
        self.cfg = load_config()
        self.tray = None
        self.window = None
        self.log_lines = []

        self._build_window()
        self._build_tray()

        # Auto-start proxy
        port = self.cfg.get("port", 15800)
        try:
            self.proxy.start(port)
            self._update_status(True)
        except Exception:
            self._update_status(False)

        # Start log poller
        self._poll_logs()

        self.window.protocol("WM_DELETE_WINDOW", self._hide_window)

    # ── window ──────────────────────────────────────────────────────

    def _build_window(self):
        self.window = tk.Tk()
        self.window.title("DeepSeek 代理管理器")
        self.window.geometry("520x580")
        self.window.resizable(True, True)
        self.window.configure(bg=BG_DARK)

        # ── app icon ─────────────────────────────────────────────
        try:
            ico_path = os.path.join(os.path.dirname(CONFIG_PATH), "proxy_icon.ico")
            icon_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            icon_draw = ImageDraw.Draw(icon_img)
            icon_draw.ellipse([6, 6, 58, 58], fill=ACCENT)
            icon_draw.ellipse([18, 18, 46, 46], fill="#ffffff")
            icon_img.save(ico_path, format="ICO", sizes=[(64, 64)])
            self.window.iconbitmap(ico_path)
        except Exception:
            pass

        # ── dark theme style ─────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG_DARK, foreground=FG_PRIMARY,
                        font=(FONT, 10), borderwidth=0, troughcolor=BG_INPUT,
                        fieldbackground=BG_INPUT, insertcolor=FG_PRIMARY)
        style.map(".", foreground=[("disabled", FG_MUTED)])
        style.configure("TFrame", background=BG_DARK)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("TLabel", background=BG_DARK, foreground=FG_PRIMARY, font=(FONT, 10))
        style.configure("Card.TLabel", background=BG_CARD, foreground=FG_PRIMARY, font=(FONT, 10))
        style.configure("CardSec.TLabel", background=BG_CARD, foreground=FG_SECONDARY, font=(FONT, 9))
        style.configure("CardTitle.TLabel", background=BG_CARD, foreground=FG_PRIMARY, font=(FONT, 10, "bold"))
        style.configure("Status.TLabel", background=BG_CARD, foreground=FG_PRIMARY, font=(FONT, 12, "bold"))
        style.configure("StatusSub.TLabel", background=BG_CARD, foreground=FG_SECONDARY, font=(FONT, 9))
        style.configure("TButton", background=ACCENT, foreground="#ffffff", font=(FONT, 10),
                        padding=(12, 6), borderwidth=0)
        style.map("TButton",
                  background=[("active", "#5a9ee6"), ("pressed", "#3a7bc8")],
                  foreground=[("disabled", FG_MUTED)])
        style.configure("Stop.TButton", background=RED, foreground="#ffffff")
        style.map("Stop.TButton", background=[("active", "#f5a0b5"), ("pressed", "#e0708a")])
        style.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG_PRIMARY,
                        insertcolor=FG_PRIMARY, borderwidth=1, padding=6)
        style.map("TEntry", fieldbackground=[("focus", "#d8e8f8")])
        # ── model status label ────────────────────────────────────
        style.configure("Active.TLabel", foreground=GREEN, font=(FONT, 10, "bold"))
        style.configure("Inactive.TButton", background=BG_INPUT, foreground=FG_SECONDARY,
                        font=(FONT, 9), padding=(10, 5), borderwidth=0)
        style.map("Inactive.TButton",
                  background=[("active", ACCENT)],
                  foreground=[("active", "#ffffff")])
        style.configure("ModelName.TLabel", background=BG_CARD, foreground=FG_PRIMARY, font=(FONT, 12))
        style.configure("ModelId.TLabel", background=BG_CARD, foreground=FG_SECONDARY, font=(FONT, 9))
        style.configure("TCheckbutton", background=BG_CARD, foreground=FG_PRIMARY, font=(FONT, 10),
                        indicatorcolor=BG_INPUT, indicatorrelief="flat")
        style.map("TCheckbutton",
                  background=[("active", BG_CARD)],
                  indicatorcolor=[("selected", ACCENT)])
        style.configure("TNotebook", background=BG_DARK, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure("TNotebook.Tab", background=BG_INPUT, foreground=FG_SECONDARY,
                        font=(FONT, 10), padding=[16, 8], borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("active", BG_INPUT), ("selected", ACCENT)],
                  foreground=[("active", FG_PRIMARY), ("selected", "#ffffff")],
                  expand=[("selected", [0, 0])])
        # ── custom tab bar styles ──────────────────────────────────
        style.configure("Tab.TButton", background=BG_INPUT, foreground=FG_SECONDARY,
                        font=(FONT, 10), padding=(12, 8), borderwidth=0)
        style.map("Tab.TButton",
                  background=[("active", BG_INPUT)],
                  foreground=[("active", FG_PRIMARY)])
        style.configure("TabSel.TButton", background=ACCENT, foreground="#ffffff",
                        font=(FONT, 11, "bold"), padding=(12, 14), borderwidth=0)
        style.map("TabSel.TButton",
                  background=[("active", ACCENT)],
                  foreground=[("active", "#ffffff")])

        # ── status card ──────────────────────────────────────────
        status_card = ttk.Frame(self.window, style="Card.TFrame", padding=16)
        status_card.pack(fill=tk.X, padx=16, pady=(16, 8))

        status_left = ttk.Frame(status_card, style="Card.TFrame")
        status_left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        dot_row = ttk.Frame(status_left, style="Card.TFrame")
        dot_row.pack(anchor=tk.W)

        self.status_dot_label = tk.Label(dot_row, text="●", font=(FONT, 20),
                                        bg=BG_CARD, fg=RED, bd=0, highlightthickness=0)
        self.status_dot_label.pack(side=tk.LEFT, padx=(0, 8))

        self.status_label = ttk.Label(dot_row, text="已停止", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)

        self.status_sub = ttk.Label(status_left, text="", style="StatusSub.TLabel")
        self.status_sub.pack(anchor=tk.W, pady=(4, 0))

        self.toggle_btn = ttk.Button(status_card, text="启动", command=self._toggle)
        self.toggle_btn.pack(side=tk.RIGHT)

        # ── tab bar ──────────────────────────────────────────────
        tab_bar = ttk.Frame(self.window)
        tab_bar.pack(fill=tk.X, padx=16, pady=(0, 0))
        tab_bar.columnconfigure(0, weight=1, uniform="tab")
        tab_bar.columnconfigure(1, weight=1, uniform="tab")
        tab_bar.columnconfigure(2, weight=1, uniform="tab")

        self._tab_buttons = []
        self._tab_frames = []

        tab_names = ["设置", "模型", "日志"]
        for i, name in enumerate(tab_names):
            btn = ttk.Button(tab_bar, text=name,
                            style="TabSel.TButton" if i == 0 else "Tab.TButton",
                            command=lambda idx=i: self._switch_tab(idx))
            btn.grid(row=0, column=i, sticky="nsew", padx=(0, 0))
            self._tab_buttons.append(btn)

        content_frame = ttk.Frame(self.window)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        # ── Settings tab ─────────────────────────────────────────
        settings_frame = ttk.Frame(content_frame)

        # Connection card
        conn_card = ttk.Frame(settings_frame, style="Card.TFrame", padding=16)
        conn_card.pack(fill=tk.X, padx=8, pady=(12, 6))

        ttk.Label(conn_card, text="连接设置", style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(conn_card, text="端口:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.port_var = tk.IntVar(value=self.cfg.get("port", 15800))
        ttk.Entry(conn_card, textvariable=self.port_var, width=10).grid(row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(conn_card, text="API 地址:", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.base_var = tk.StringVar(value=self.cfg.get("deepseek_base", "https://api.deepseek.com"))
        ttk.Entry(conn_card, textvariable=self.base_var, width=42).grid(row=2, column=1, sticky=tk.W, pady=4)

        ttk.Label(conn_card, text="API 密钥:", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        key_frame = ttk.Frame(conn_card, style="Card.TFrame")
        key_frame.grid(row=3, column=1, sticky=tk.EW, pady=4)
        self.key_var = tk.StringVar(value=load_api_key())
        self.key_entry = ttk.Entry(key_frame, textvariable=self.key_var, width=32, show="*")
        self.key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(key_frame, text="显示", variable=self.show_key,
                        command=self._toggle_key_visibility).pack(side=tk.LEFT, padx=(8, 0))

        conn_card.columnconfigure(1, weight=1)

        # Startup card
        start_card = ttk.Frame(settings_frame, style="Card.TFrame", padding=16)
        start_card.pack(fill=tk.X, padx=8, pady=6)

        ttk.Label(start_card, text="启动项", style="CardTitle.TLabel").pack(anchor=tk.W, pady=(0, 8))
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        ttk.Checkbutton(start_card, text="开机自动启动代理",
                        variable=self.autostart_var,
                        command=self._toggle_autostart).pack(anchor=tk.W)
        ttk.Label(start_card, text="在 Windows 启动文件夹中创建快捷方式",
                  style="CardSec.TLabel").pack(anchor=tk.W, pady=(2, 0))

        # Save button
        save_frame = ttk.Frame(settings_frame)
        save_frame.pack(fill=tk.X, padx=8, pady=(8, 8))
        ttk.Button(save_frame, text="保存设置", command=self._save_settings).pack(side=tk.RIGHT)

        # ── Models tab ───────────────────────────────────────────
        models_frame = ttk.Frame(content_frame)

        self.models_container = ttk.Frame(models_frame)
        self.models_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=12)
        self._refresh_models_list()

        add_frame = ttk.Frame(models_frame)
        add_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(add_frame, text="添加模型", command=self._add_model).pack(side=tk.RIGHT)

        # ── Log tab ──────────────────────────────────────────────
        log_frame = ttk.Frame(content_frame)

        log_card = ttk.Frame(log_frame, style="Card.TFrame", padding=8)
        log_card.pack(fill=tk.BOTH, expand=True, padx=8, pady=12)

        self.log_text = scrolledtext.ScrolledText(
            log_card, height=18, state=tk.DISABLED,
            font=(FONT_MONO, 9), bg=BG_INPUT, fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY, selectbackground=ACCENT,
            bd=0, highlightthickness=0, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        log_btn_frame = ttk.Frame(log_card, style="Card.TFrame")
        log_btn_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(log_btn_frame, text="清空", command=self._clear_log).pack(side=tk.RIGHT)

        # ── stack tab frames and show first ───────────────────────
        self._tab_frames = [settings_frame, models_frame, log_frame]
        for f in self._tab_frames:
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._switch_tab(0)

    def _switch_tab(self, idx):
        for i, btn in enumerate(self._tab_buttons):
            if i == idx:
                btn.config(style="TabSel.TButton")
                self._tab_frames[i].lift()
            else:
                btn.config(style="Tab.TButton")

    # ── tray ────────────────────────────────────────────────────────

    def _build_tray(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill=ACCENT)
        self.tray = pystray.Icon(
            "deepseek_proxy", img, "DeepSeek Proxy",
            menu=pystray.Menu(
                pystray.MenuItem("显示", self._show_window, default=True),
                pystray.MenuItem("启动 / 停止", self._toggle),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._quit),
            )
        )

    # ── actions ─────────────────────────────────────────────────────

    def _toggle(self):
        if self.proxy.is_running():
            self.proxy.stop()
            self._update_status(False)
        else:
            port = self.port_var.get()
            try:
                self.proxy.start(port)
                self._update_status(True)
            except Exception as e:
                messagebox.showerror("错误", f"启动失败: {e}")

    def _update_status(self, running):
        if running:
            self.status_dot_label.config(fg=GREEN)
            self.status_label.config(text="代理运行中")
            self.status_sub.config(text=f"监听地址 127.0.0.1:{self.port_var.get()}")
            self.toggle_btn.config(text="停止", style="Stop.TButton")
        else:
            self.status_dot_label.config(fg=RED)
            self.status_label.config(text="代理已停止")
            self.status_sub.config(text="")
            self.toggle_btn.config(text="启动", style="TButton")

    def _save_settings(self):
        port = self.port_var.get()
        base = self.base_var.get().rstrip("/")
        key = self.key_var.get()

        self.cfg["port"] = port
        self.cfg["deepseek_base"] = base
        save_config(self.cfg)
        save_api_key(key)
        messagebox.showinfo("已保存", "设置已保存！\n重启代理以应用新的端口/API地址。")

    def _toggle_key_visibility(self):
        self.key_entry.config(show="" if self.show_key.get() else "*")

    def _toggle_autostart(self):
        set_autostart(self.autostart_var.get())

    def _refresh_models_list(self):
        for w in self.models_container.winfo_children():
            w.destroy()
        models = self.cfg.get("models", [])
        for i, m in enumerate(models):
            enabled = m.get("enabled", True)
            row = ttk.Frame(self.models_container, style="Card.TFrame", padding=12)
            row.pack(fill=tk.X, pady=(0, 6))

            info = ttk.Frame(row, style="Card.TFrame")
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(info, text=m.get("name", m["id"]), style="ModelName.TLabel").pack(anchor=tk.W)
            ttk.Label(info, text=m["id"], style="ModelId.TLabel").pack(anchor=tk.W)

            if enabled:
                lbl = ttk.Label(row, text="● 使用中", style="Active.TLabel")
                lbl.pack(side=tk.RIGHT, padx=(8, 0))
            else:
                btn = ttk.Button(row, text="启用", style="Inactive.TButton",
                                 command=lambda idx=i: self._activate_model(idx))
                btn.pack(side=tk.RIGHT, padx=(8, 0))

    def _activate_model(self, idx):
        models = self.cfg.get("models", [])
        for i, m in enumerate(models):
            m["enabled"] = (i == idx)
        self.cfg["models"] = models
        save_config(self.cfg)
        self._refresh_models_list()

    def _add_model(self):
        dlg = tk.Toplevel(self.window)
        dlg.title("添加模型")
        dlg.geometry("340x200")
        dlg.configure(bg=BG_DARK)
        dlg.transient(self.window)
        dlg.grab_set()

        card = ttk.Frame(dlg, style="Card.TFrame", padding=16)
        card.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        ttk.Label(card, text="模型 ID:", style="Card.TLabel").grid(row=0, column=0, sticky=tk.W, pady=6)
        id_var = tk.StringVar()
        ttk.Entry(card, textvariable=id_var, width=25).grid(row=0, column=1, padx=(8, 0), pady=6)

        ttk.Label(card, text="显示名称:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=6)
        name_var = tk.StringVar()
        ttk.Entry(card, textvariable=name_var, width=25).grid(row=1, column=1, padx=(8, 0), pady=6)

        def _save():
            mid = id_var.get().strip()
            if mid:
                self.cfg.setdefault("models", []).append({
                    "id": mid,
                    "name": name_var.get().strip() or mid,
                    "enabled": True,
                })
                save_config(self.cfg)
                self._refresh_models_list()
            dlg.destroy()

        ttk.Button(card, text="添加", command=_save).grid(row=2, column=0, columnspan=2, pady=(16, 0))

    def _clear_log(self):
        self.log_lines = []
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _poll_logs(self):
        while not LOG_QUEUE.empty():
            try:
                msg = LOG_QUEUE.get_nowait()
                ts = datetime.now().strftime("%H:%M:%S")
                self.log_lines.append(f"[{ts}] {msg}")
            except queue.Empty:
                break
        # Trim
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-500:]

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", "\n".join(self.log_lines))
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.window.after(1000, self._poll_logs)

    def _show_window(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _hide_window(self):
        self.window.withdraw()

    def _quit(self):
        if self.proxy.is_running():
            self.proxy.stop()
        if self.tray:
            self.tray.stop()
        self.window.destroy()

    def run(self):
        # Run tray in a thread so it doesn't block tkinter
        if self.tray:
            threading.Thread(target=self.tray.run, daemon=True).start()
        self.window.mainloop()


# ── entry point ──────────────────────────────────────────────────────

def main():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
    cfg = load_config()
    port = cfg.get("port", 15800)
    if is_already_running(port):
        # Another instance is already running — just show a message and exit.
        # The system tray icon of the existing instance is still there.
        import tkinter.messagebox as mb
        root = tk.Tk()
        root.withdraw()
        mb.showinfo("DeepSeek 代理管理器",
                    f"代理已在端口 {port} 上运行。\n\n"
                    "请在系统托盘（通知区域）查看图标。")
        root.destroy()
        return
    app = ProxyManagerApp()
    app.run()


if __name__ == "__main__":
    main()
