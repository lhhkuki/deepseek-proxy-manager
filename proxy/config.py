"""Proxy configuration, authentication, constants, and reasoning cache."""

import json
import os
import sys
import time
import queue
import threading
import hashlib
import base64
import secrets

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

LOG_QUEUE = queue.Queue(maxsize=1000)

HOME = os.path.expanduser("~")
CONFIG_PATH = os.path.join(HOME, ".codex", "proxy_config.json")
PID_FILE = os.path.join(HOME, ".codex", "proxy.pid")


def _get_fernet():
    """Get or create a Fernet encryption key bound to this machine."""
    if Fernet is None:
        raise RuntimeError("cryptography package not installed. Run: pip install cryptography")
    key_path = os.path.join(HOME, ".codex", ".fernet_key")
    _FERNET_VERSION = b"F1"
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            raw = f.read()
        if raw.startswith(_FERNET_VERSION):
            key = raw[len(_FERNET_VERSION):]
        else:
            # Legacy key without version prefix
            key = raw
    else:
        import secrets
        key = base64.urlsafe_b64encode(secrets.token_bytes(32))
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(_FERNET_VERSION + key)
    return Fernet(key)


def _encrypt_api_key(plain_key):
    if not plain_key:
        return ""
    try:
        f = _get_fernet()
        return f.encrypt(plain_key.encode("utf-8")).decode("ascii")
    except Exception as e:
        LOG_QUEUE.put_nowait(f"Encrypt API key failed: {e}")
        return ""


def _decrypt_api_key(cipher_text):
    if not cipher_text:
        return ""
    # Try Fernet first
    try:
        f = _get_fernet()
        return f.decrypt(cipher_text.encode("ascii")).decode("utf-8")
    except Exception:
        pass
    # Fallback: old XOR encrypted keys
    try:
        import platform
        material = "|".join([
            platform.node(), os.environ.get("COMPUTERNAME", ""),
            os.environ.get("USERDOMAIN", ""), os.path.expanduser("~"),
        ]).encode("utf-8", errors="replace")
        key = hashlib.sha256(material).digest()
        encrypted = base64.b64decode(cipher_text.encode("ascii"))
        data = bytes(b ^ key[i % len(key)] for i, b in enumerate(encrypted))
        result = data.decode("utf-8")
        # Re-encrypt with Fernet
        save_api_key(result)
        return result
    except Exception:
        return ""


_REASONING_CACHE = {}
_MAX_REASONING = 100
_REASONING_CACHE_TTL = 3600
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
        _REASONING_CACHE[key] = (reasoning_content, time.time())
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
            "upstream_format": "openai",
        },
        {
            "id": "deepseek-chat",
            "name": "DeepSeek V4 Flash",
            "enabled": False,
            "base_url": "https://api.deepseek.com",
            "api_key": "",
            "reasoning": False,
            "upstream_format": "openai",
        },
    ],
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                loaded = json.load(f)
        except (json.JSONDecodeError, OSError):
            LOG_QUEUE.put_nowait("Config corrupted, resetting to defaults")
            # Keep backup of broken config
            try:
                bak = CONFIG_PATH + ".bak"
                with open(CONFIG_PATH, encoding="utf-8") as src:
                    with open(bak, "w", encoding="utf-8") as dst:
                        dst.write(src.read())
            except Exception:
                pass
            return dict(DEFAULT_CONFIG)
        if "deepseek_base" in loaded or "api_key" in loaded:
            loaded = _migrate_old_config(loaded)
        loaded = _decrypt_config_keys(loaded)
        return {**DEFAULT_CONFIG, **loaded}
    return dict(DEFAULT_CONFIG)


def _migrate_old_config(cfg):
    """Migrate old global base_url/api_key to per-model settings."""
    base_url = cfg.pop("deepseek_base", "https://api.deepseek.com")
    api_key = cfg.pop("api_key", "")
    models = cfg.get("models", [])
    if not models:
        models = [{
            "id": "deepseek-chat", "name": "DeepSeek V4 Flash",
            "enabled": True, "base_url": base_url,
            "api_key": api_key, "reasoning": False,
            "upstream_format": "openai",
        }]
    else:
        for m in models:
            if not m.get("base_url"):
                m["base_url"] = base_url
            if not m.get("api_key") and api_key:
                m["api_key"] = api_key
    cfg["models"] = models
    return cfg


_ENCRYPT_PREFIX = "enc:v2:"

def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    to_save = dict(cfg)
    if "models" in to_save:
        to_save["models"] = []
        for m in cfg["models"]:
            mc = dict(m)
            key = mc.get("api_key", "")
            if key and not key.startswith(_ENCRYPT_PREFIX):
                mc["api_key"] = _ENCRYPT_PREFIX + _encrypt_api_key(key)
            to_save["models"].append(mc)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)

def _decrypt_config_keys(cfg):
    """Decrypt API keys in loaded config."""
    for m in cfg.get("models", []):
        key = m.get("api_key", "")
        if key.startswith(_ENCRYPT_PREFIX):
            m["api_key"] = _decrypt_api_key(key[len(_ENCRYPT_PREFIX):])
        # If not prefixed, it's old plaintext — leave as-is, will be encrypted on next save
    return cfg


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
    import sys
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, encoding="utf-8") as f:
                pid = int(f.read().strip())
            if sys.platform == "win32":
                import ctypes
                kernel = ctypes.windll.kernel32
                handle = kernel.OpenProcess(0x0400, False, pid)
                if handle:
                    kernel.CloseHandle(handle)
                    try:
                        s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                        s.close()
                        return True
                    except (ConnectionRefusedError, OSError):
                        os.remove(PID_FILE)
                        return False
            # Non-Windows: skip process check, just test port
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


def cleanup_port(port):
    """Kill any zombie process holding the proxy port."""
    import socket
    import subprocess
    import sys as _sys
    # Try PID file first
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, encoding="utf-8") as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                try:
                    subprocess.run(["taskkill", "/PID", str(old_pid), "/F"],
                                   capture_output=True, timeout=5)
                except Exception:
                    pass
        except (ValueError, OSError):
            pass
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
    # Also check if port is still occupied by an unknown process
    if _sys.platform == "win32":
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.splitlines():
                if f"127.0.0.1:{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = int(parts[-1])
                    if pid != os.getpid():
                        subprocess.run(
                            ["taskkill", "/PID", str(pid), "/F"],
                            capture_output=True, timeout=5)
        except Exception:
            pass


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


