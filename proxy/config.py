"""Proxy configuration, authentication, constants, and reasoning cache."""

import json
import os
import sys
import queue
import threading
import hashlib
import base64

LOG_QUEUE = queue.Queue(maxsize=1000)

HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(HOME, ".codex", "proxy_config.json")
PID_FILE = os.path.join(HOME, ".codex", "proxy.pid")


def _get_machine_key():
    import platform
    parts = [
        platform.node(),
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERDOMAIN", ""),
        os.path.expanduser("~"),
    ]
    key_material = "|".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha256(key_material).digest()


def _encrypt_api_key(plain_key):
    if not plain_key:
        return ""
    key = _get_machine_key()
    data = plain_key.encode("utf-8")
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.b64encode(encrypted).decode("ascii")


def _decrypt_api_key(cipher_text):
    if not cipher_text:
        return ""
    try:
        key = _get_machine_key()
        encrypted = base64.b64decode(cipher_text.encode("ascii"))
        data = bytes(b ^ key[i % len(key)] for i, b in enumerate(encrypted))
        return data.decode("utf-8")
    except Exception:
        return ""


_REASONING_CACHE = {}
_MAX_REASONING = 100
_REASONING_LOCK = threading.Lock()


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
    key = hashlib.sha256(pc.encode()).hexdigest()
    with _REASONING_LOCK:
        _REASONING_CACHE[key] = reasoning_content
        while len(_REASONING_CACHE) > _MAX_REASONING:
            _REASONING_CACHE.pop(next(iter(_REASONING_CACHE)))


DEFAULT_CONFIG = {
    "port": 15800,
    "models": [
        {
            "id": "deepseek-v4-pro",
            "name": "DeepSeek V4 Pro",
            "enabled": True,
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "reasoning": False,
        },
        {
            "id": "deepseek-chat",
            "name": "DeepSeek V4 Flash",
            "enabled": False,
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "reasoning": False,
        },
    ],
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            loaded = json.load(f)
            # Migrate old config: move global deepseek_base/api_key to models
            if "deepseek_base" in loaded or "api_key" in loaded:
                loaded = _migrate_old_config(loaded)
            return {**DEFAULT_CONFIG, **loaded}
    return dict(DEFAULT_CONFIG)


def _migrate_old_config(cfg):
    """Migrate old global base_url/api_key to per-model settings."""
    base_url = cfg.pop("deepseek_base", "https://api.deepseek.com")
    api_key = cfg.pop("api_key", "")
    models = cfg.get("models", [])
    for m in models:
        if not m.get("base_url"):
            m["base_url"] = base_url
        if not m.get("api_key"):
            m["api_key"] = api_key
    cfg["models"] = models
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


API_KEY_FILE = os.path.join(HOME, ".codex", "proxy_api_key.enc")

def load_api_key():
    """Load and decrypt the global API key fallback."""
    if os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, "r", encoding="utf-8") as f:
                encrypted = f.read().strip()
            return _decrypt_api_key(encrypted)
        except Exception:
            return ""
    return ""

def save_api_key(key):
    """Encrypt and save the global API key fallback."""
    os.makedirs(os.path.dirname(API_KEY_FILE), exist_ok=True)
    encrypted = _encrypt_api_key(key)
    with open(API_KEY_FILE, "w", encoding="utf-8") as f:
        f.write(encrypted)


def get_active_model_config():
    """Get the currently enabled model's config."""
    cfg = load_config()
    for m in cfg.get("models", []):
        if m.get("enabled", False):
            return m
    models = cfg.get("models", [])
    return models[0] if models else None


def is_already_running(port):
    import socket
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, encoding="utf-8") as f:
                pid = int(f.read().strip())
            import ctypes
            kernel = ctypes.windll.kernel32
            handle = kernel.OpenProcess(1, False, pid)
            if handle:
                kernel.CloseHandle(handle)
                try:
                    s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                    s.close()
                    return True
                except (ConnectionRefusedError, OSError):
                    os.remove(PID_FILE)
                    return False
        except (ValueError, OSError, ImportError):
            pass
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
        s.close()
        return True
    except (ConnectionRefusedError, OSError):
        return False


def write_pid_file():
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def remove_pid_file():
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass


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
            target = 'start "" "{0}"'.format(sys.executable)
        else:
            import shutil
            pythonw = shutil.which("pythonw")
            if not pythonw:
                pythonw = sys.executable.replace("python.exe", "pythonw.exe")
            main_py = os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "..", "proxy_manager.py")
            target = 'start "" "{0}" "{1}"'.format(pythonw, os.path.normpath(main_py))
        with open(STARTUP_BAT, "w", encoding="utf-8") as f:
            f.write("@echo off\n" + target + "\n")
    else:
        if os.path.exists(STARTUP_BAT):
            os.remove(STARTUP_BAT)


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

