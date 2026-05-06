"""Proxy configuration, authentication, constants, and reasoning cache."""

import json
import os
import sys
import queue
import hashlib

# ── log queue (shared across modules) ──────────────────────────────

LOG_QUEUE = queue.Queue()

HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(HOME, ".codex", "proxy_config.json")
AUTH_PATH = os.path.join(HOME, ".codex", "auth.json")

# ── reasoning cache ──────────────────────────────────────────────────

_REASONING_CACHE = {}
_MAX_REASONING = 100


def cache_reasoning(chat_req, reasoning_content):
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
    while len(_REASONING_CACHE) > _MAX_REASONING:
        _REASONING_CACHE.pop(next(iter(_REASONING_CACHE)))


# ── default config ───────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "port": 15800,
    "deepseek_base": "https://api.deepseek.com",
    "models": [
        {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "enabled": True},
        {"id": "deepseek-chat", "name": "DeepSeek V4 Flash", "enabled": True},
    ],
}


# ── config I/O ───────────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
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


def is_already_running(port):
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


# ── autostart ────────────────────────────────────────────────────────

STARTUP_BAT = os.path.join(
    os.environ.get("APPDATA", ""),
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    "DeepSeekProxy.bat",
)


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


# ── theme colors ─────────────────────────────────────────────────────

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
