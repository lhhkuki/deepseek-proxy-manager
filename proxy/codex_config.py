"""Codex Desktop config switching helpers."""

import json
import os
import re
import time

PROVIDER_ID = "AIProxyManager"
BEARER_TOKEN = "local-proxy"


def codex_home():
    return os.path.join(os.path.expanduser("~"), ".codex")


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


def _backup_file(path):
    if not os.path.exists(path):
        return ""
    backup_dir = os.path.join(codex_home(), "backups_proxy_manager")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(backup_dir, f"{os.path.basename(path)}.{stamp}.bak")
    with open(path, "rb") as src:
        data = src.read()
    with open(backup_path, "wb") as dst:
        dst.write(data)
    return backup_path


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
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
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
    mode = "proxy" if is_proxy else ("official" if not provider else "custom")
    return {
        "mode": mode,
        "provider": provider,
        "model": _root_key_value(contents, "model"),
        "base_url": base_url,
        "config_path": path,
        "exists": os.path.exists(path),
        "auth": chatgpt_auth_status(),
    }


def apply_proxy_config(port=None, model=None):
    port = int(port or 15800)
    if port < 1 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    model = (model or _active_model_id()).strip() or "deepseek-v4-pro"
    path = config_path()
    contents = _read_text(path)
    backup_path = _backup_file(path)
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
    updated = (block + "\n" + contents).rstrip() + "\n" if contents else block
    _write_text(path, updated)
    status = codex_config_status()
    status["backup_path"] = backup_path
    return status


def apply_official_config():
    path = config_path()
    contents = _read_text(path)
    backup_path = _backup_file(path)
    contents = _remove_table(contents, f"model_providers.{PROVIDER_ID}")
    if _root_key_value(contents, "model_provider") == PROVIDER_ID:
        contents = _remove_root_keys(contents, {"model_provider", "model"})
    _write_text(path, contents + ("\n" if contents else ""))
    status = codex_config_status()
    status["backup_path"] = backup_path
    return status
