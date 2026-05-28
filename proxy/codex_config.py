"""Codex Desktop config switching helpers."""

import json
import glob
import os
import re
import shutil
import sqlite3
import time

PROVIDER_ID = "AIProxyManager"
OFFICIAL_PROVIDER_ID = "openai"
BEARER_TOKEN = "local-proxy"


def codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def config_path():
    return os.path.join(codex_home(), "config.toml")


def auth_path():
    return os.path.join(codex_home(), "auth.json")


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _write_text(path, contents):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(contents)
    os.replace(tmp, path)


def _read_json_object(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_json_object(path, data):
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _backup_file(path):
    if not os.path.exists(path):
        return ""
    backup_dir = os.path.join(codex_home(), "backups_proxy_manager")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int((time.time() % 1) * 1000):03d}-{os.getpid()}"
    backup_path = os.path.join(backup_dir, f"{os.path.basename(path)}.{stamp}.bak")
    with open(path, "rb") as src:
        data = src.read()
    with open(backup_path, "wb") as dst:
        dst.write(data)
    return backup_path


def _provider_sync_backup_dir():
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int((time.time() % 1) * 1000):03d}"
    backup_dir = os.path.join(
        codex_home(),
        "backups_proxy_manager",
        "provider_sync",
        stamp,
    )
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def _toml_quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def _root_key_value(contents, key):
    in_table = False
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$")
    for line in contents.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_table = True
        if in_table or not stripped or stripped.startswith("#"):
            continue
        match = pattern.match(line)
        if match:
            return _unquote(match.group(1))
    return ""


def _provider_value(contents, provider_id, key):
    in_provider = False
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*$")
    for line in contents.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_provider = stripped == f"[model_providers.{provider_id}]"
            continue
        if not in_provider:
            continue
        match = pattern.match(line)
        if match:
            return _unquote(match.group(1))
    return ""


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    return value


def _remove_root_keys(contents, keys):
    result = []
    in_table = False
    patterns = [
        re.compile(rf"^\s*{re.escape(key)}\s*=")
        for key in keys
    ]
    for line in contents.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_table = True
        if not in_table and any(pattern.match(line) for pattern in patterns):
            continue
        result.append(line)
    return "\n".join(result).strip()


def _remove_table(contents, table_name):
    result = []
    skipping = False
    target = f"[{table_name}]"
    for line in contents.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            skipping = stripped == target
        if not skipping:
            result.append(line)
    return "\n".join(result).strip()


def _iter_session_files():
    home = codex_home()
    for folder in ("sessions", "archived_sessions"):
        root = os.path.join(home, folder)
        if not os.path.isdir(root):
            continue
        pattern = os.path.join(root, "**", "*.jsonl")
        yield from glob.iglob(pattern, recursive=True)


def _backup_path(backup_dir, path):
    rel = os.path.relpath(path, codex_home())
    target = os.path.join(backup_dir, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(path, target)


def _sync_session_file_provider(path, target_provider, backup_dir):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return False
    if not lines:
        return False
    try:
        first = json.loads(lines[0])
    except json.JSONDecodeError:
        return False
    if first.get("type") != "session_meta":
        return False
    payload = first.get("payload")
    if not isinstance(payload, dict):
        return False
    if payload.get("model_provider") == target_provider:
        return False

    stat = os.stat(path)
    _backup_path(backup_dir, path)
    payload["model_provider"] = target_provider
    lines[0] = json.dumps(first, ensure_ascii=False, separators=(",", ":")) + "\n"
    tmp = path + ".provider-sync.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)
    os.replace(tmp, path)
    os.utime(path, (stat.st_atime, stat.st_mtime))
    return True


def _sync_state_databases_provider(target_provider, backup_dir):
    changed = 0
    for db_path in glob.glob(os.path.join(codex_home(), "state_*.sqlite")):
        for suffix in ("", "-wal", "-shm"):
            sidecar = db_path + suffix
            if os.path.exists(sidecar):
                _backup_path(backup_dir, sidecar)
        conn = sqlite3.connect(db_path, timeout=2)
        try:
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(threads)").fetchall()
            }
            if "model_provider" not in columns:
                continue
            cursor = conn.execute(
                "UPDATE threads SET model_provider = ? WHERE COALESCE(model_provider, '') <> ?",
                (target_provider, target_provider),
            )
            changed += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
            conn.commit()
        finally:
            conn.close()
    return changed


def _sync_conversation_provider(target_provider):
    """Keep Codex conversations visible after switching model providers."""
    result = {
        "target_provider": target_provider,
        "changed_session_files": 0,
        "sqlite_rows_updated": 0,
        "backup_dir": "",
        "message": "",
    }
    if not os.path.isdir(codex_home()):
        result["message"] = "未找到 Codex 目录，跳过会话同步"
        return result

    backup_dir = _provider_sync_backup_dir()
    result["backup_dir"] = backup_dir
    try:
        for path in _iter_session_files():
            if _sync_session_file_provider(path, target_provider, backup_dir):
                result["changed_session_files"] += 1
        result["sqlite_rows_updated"] = _sync_state_databases_provider(target_provider, backup_dir)
        result["message"] = "已同步 Codex 会话 provider"
    except Exception as exc:
        result["message"] = f"会话 provider 同步失败：{exc}"
    return result


def _active_model_id():
    try:
        from .config import get_active_model_config

        model = get_active_model_config()
        if model:
            return str(model.get("id") or "deepseek-v4-pro")
    except Exception:
        pass
    return "deepseek-v4-pro"


def chatgpt_auth_status():
    path = auth_path()
    data = _read_json_object(path)
    if not data:
        return {
            "authenticated": False,
            "path": path,
            "account": "",
            "message": "未检测到 ChatGPT 官方登录态",
        }
    if str(data.get("auth_mode", "")).lower() != "chatgpt":
        return {
            "authenticated": False,
            "path": path,
            "account": "",
            "message": "auth.json 不是 ChatGPT 官方登录态",
        }
    tokens = data.get("tokens") or {}
    has_token = any(str(tokens.get(key) or "").strip()
                    for key in ("access_token", "id_token", "refresh_token"))
    if not has_token:
        return {
            "authenticated": False,
            "path": path,
            "account": "",
            "message": "ChatGPT 登录 token 为空",
        }
    account = (
        tokens.get("account_id")
        or tokens.get("email")
        or data.get("account_id")
        or "ChatGPT"
    )
    return {
        "authenticated": True,
        "path": path,
        "account": str(account),
        "message": "已检测到 ChatGPT 官方登录态",
    }


def api_key_auth_status():
    path = auth_path()
    data = _read_json_object(path)
    key = str(data.get("OPENAI_API_KEY") or "").strip()
    return {
        "authenticated": bool(key),
        "path": path,
        "message": "已检测到纯 API Key" if key else "未检测到纯 API Key",
    }


def codex_config_status():
    path = config_path()
    contents = _read_text(path)
    provider = _root_key_value(contents, "model_provider")
    base_url = _provider_value(contents, PROVIDER_ID, "base_url")
    requires_auth = _provider_value(contents, PROVIDER_ID, "requires_openai_auth")
    is_proxy = (
        provider == PROVIDER_ID
        and base_url.startswith("http://127.0.0.1:")
        and requires_auth == "true"
    )
    api_auth = api_key_auth_status()
    mode = "pure_api" if is_proxy and api_auth["authenticated"] else (
        "proxy" if is_proxy else ("official" if not provider else "custom")
    )
    return {
        "mode": mode,
        "provider": provider,
        "model": _root_key_value(contents, "model"),
        "base_url": base_url,
        "config_path": path,
        "exists": os.path.exists(path),
        "auth": chatgpt_auth_status(),
        "api_auth": api_auth,
    }


def _proxy_config_contents(contents, port, model):
    contents = _remove_table(contents, f"model_providers.{PROVIDER_ID}")
    contents = _remove_root_keys(contents, {"model_provider", "model"})
    block = "\n".join([
        f"model_provider = {_toml_quote(PROVIDER_ID)}",
        f"model = {_toml_quote(model)}",
        "",
        f"[model_providers.{PROVIDER_ID}]",
        f"name = {_toml_quote(PROVIDER_ID)}",
        'wire_api = "responses"',
        "requires_openai_auth = true",
        f"base_url = {_toml_quote(f'http://127.0.0.1:{port}/v1')}",
        f"experimental_bearer_token = {_toml_quote(BEARER_TOKEN)}",
        "",
    ])
    return (block + "\n" + contents).rstrip() + "\n" if contents else block


def apply_proxy_config(port=None, model=None):
    port = int(port or 15800)
    if port < 1 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    model = (model or _active_model_id()).strip() or "deepseek-v4-pro"
    path = config_path()
    contents = _read_text(path)
    backup_path = _backup_file(path)
    updated = _proxy_config_contents(contents, port, model)
    _write_text(path, updated)
    status = codex_config_status()
    status["backup_path"] = backup_path
    status["conversation_sync"] = _sync_conversation_provider(PROVIDER_ID)
    return status


def apply_pure_api_config(port=None, model=None):
    config_status = apply_proxy_config(port=port, model=model)
    config_backup_path = config_status.get("backup_path", "")
    path = auth_path()
    auth_backup_path = _backup_file(path)
    data = _read_json_object(path)
    data["OPENAI_API_KEY"] = BEARER_TOKEN
    _write_json_object(path, data)
    status = codex_config_status()
    status["backup_path"] = config_backup_path
    status["auth_backup_path"] = auth_backup_path
    status["conversation_sync"] = config_status.get("conversation_sync") or _sync_conversation_provider(PROVIDER_ID)
    return status


def apply_official_config():
    path = config_path()
    contents = _read_text(path)
    backup_path = _backup_file(path)
    contents = _remove_table(contents, f"model_providers.{PROVIDER_ID}")
    if _root_key_value(contents, "model_provider") == PROVIDER_ID:
        contents = _remove_root_keys(contents, {"model_provider", "model"})
    _write_text(path, contents + ("\n" if contents else ""))
    data = _read_json_object(auth_path())
    auth_backup_path = ""
    if data.get("OPENAI_API_KEY") == BEARER_TOKEN:
        auth_backup_path = _backup_file(auth_path())
        data.pop("OPENAI_API_KEY", None)
        _write_json_object(auth_path(), data)
    status = codex_config_status()
    status["backup_path"] = backup_path
    status["auth_backup_path"] = auth_backup_path
    status["conversation_sync"] = _sync_conversation_provider(OFFICIAL_PROVIDER_ID)
    return status
