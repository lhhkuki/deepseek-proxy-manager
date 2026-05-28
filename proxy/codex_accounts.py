"""Local Codex account vault helpers."""

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from .codex_config import auth_path, codex_home, _backup_file, _read_json_object, _write_json_object


def accounts_root():
    return os.path.join(codex_home(), "accounts_proxy_manager")


def accounts_dir():
    return os.path.join(accounts_root(), "accounts")


def accounts_index_path():
    return os.path.join(accounts_root(), "index.json")


def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _safe_alias(value):
    alias = str(value or "").strip()
    return alias[:80] if alias else "Codex account"


def _read_index():
    data = _read_json_object(accounts_index_path())
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        accounts = []
    return {"schema": 1, "accounts": [item for item in accounts if isinstance(item, dict)]}


def _write_index(data):
    os.makedirs(accounts_root(), exist_ok=True)
    _write_json_object(accounts_index_path(), data)


def _account_file(account_id):
    return os.path.join(accounts_dir(), account_id, "auth.json")


def _hash_auth(data):
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _token_present(data):
    if not isinstance(data, dict):
        return False
    if str(data.get("OPENAI_API_KEY") or "").strip():
        return True
    tokens = data.get("tokens")
    return isinstance(tokens, dict) and any(str(tokens.get(key) or "").strip() for key in ("access_token", "id_token", "refresh_token"))


def _usage_error_message(exc):
    message = str(exc)
    if "token_invalidated" in message or "401" in message or "Unauthorized" in message:
        return "额度读取失败：账号登录已失效，请重新登录后再导入。"
    if "Timed out" in message or "timeout" in message.lower():
        return "额度读取超时，请稍后重试。"
    if "Codex CLI executable was not found" in message:
        return "未找到 Codex 程序，无法读取额度。"
    return message[:240]


def _extract_email(data):
    tokens = data.get("tokens") if isinstance(data, dict) else {}
    candidates = []
    if isinstance(tokens, dict):
        candidates.extend([tokens.get("email"), tokens.get("account_email"), tokens.get("user_email")])
        id_token = str(tokens.get("id_token") or "")
        candidates.extend(re.findall(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", id_token))
    candidates.extend([data.get("email"), data.get("account_email")])
    for value in candidates:
        value = str(value or "").strip()
        if "@" in value:
            return value
    return ""


def _auth_summary(data):
    tokens = data.get("tokens") if isinstance(data, dict) else {}
    tokens = tokens if isinstance(tokens, dict) else {}
    mode = str(data.get("auth_mode") or ("api_key" if data.get("OPENAI_API_KEY") else "")).strip()
    account = (
        _extract_email(data)
        or str(tokens.get("account_id") or data.get("account_id") or "").strip()
        or ("API Key" if data.get("OPENAI_API_KEY") else "")
    )
    return {
        "auth_mode": mode,
        "account": account,
        "has_api_key": bool(str(data.get("OPENAI_API_KEY") or "").strip()),
        "has_chatgpt_token": any(str(tokens.get(key) or "").strip() for key in ("access_token", "id_token", "refresh_token")),
        "last_refresh": str(data.get("last_refresh") or tokens.get("last_refresh") or ""),
        "hash": _hash_auth(data),
    }


def _public_account(record, active_hash=""):
    account_id = str(record.get("id") or "")
    auth_data = _read_json_object(_account_file(account_id))
    summary = _auth_summary(auth_data) if auth_data else {}
    auth_hash = summary.get("hash", str(record.get("hash") or ""))
    return {
        "id": account_id,
        "alias": str(record.get("alias") or "Codex account"),
        "account": summary.get("account") or str(record.get("account") or ""),
        "auth_mode": summary.get("auth_mode") or str(record.get("auth_mode") or ""),
        "has_api_key": bool(summary.get("has_api_key")),
        "has_chatgpt_token": bool(summary.get("has_chatgpt_token")),
        "last_refresh": summary.get("last_refresh") or str(record.get("last_refresh") or ""),
        "usage": record.get("usage") if isinstance(record.get("usage"), dict) else None,
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
        "active": bool(active_hash and auth_hash == active_hash),
        "auth_path": _account_file(account_id),
    }


def list_accounts():
    os.makedirs(accounts_dir(), exist_ok=True)
    index = _read_index()
    current = _read_json_object(auth_path())
    current_summary = _auth_summary(current) if current else {}
    active_hash = current_summary.get("hash", "")
    return {
        "codex_home": codex_home(),
        "auth_path": auth_path(),
        "vault_path": accounts_root(),
        "current": {
            "exists": bool(current),
            "account": current_summary.get("account", ""),
            "auth_mode": current_summary.get("auth_mode", ""),
            "has_api_key": bool(current_summary.get("has_api_key")),
            "has_chatgpt_token": bool(current_summary.get("has_chatgpt_token")),
            "last_refresh": current_summary.get("last_refresh", ""),
        },
        "accounts": [_public_account(record, active_hash) for record in index["accounts"]],
    }


def import_current_account(alias=None):
    data = _read_json_object(auth_path())
    if not data or not _token_present(data):
        raise ValueError("Current Codex auth.json has no usable account token.")

    summary = _auth_summary(data)
    account_hash = summary["hash"]
    index = _read_index()
    now = _now()
    existing = next((item for item in index["accounts"] if item.get("hash") == account_hash), None)
    if existing:
        existing["alias"] = _safe_alias(alias or existing.get("alias") or summary.get("account"))
        existing["updated_at"] = now
        existing["account"] = summary.get("account", "")
        existing["auth_mode"] = summary.get("auth_mode", "")
        existing["last_refresh"] = summary.get("last_refresh", "")
        account_id = str(existing["id"])
    else:
        account_id = uuid.uuid4().hex[:12]
        index["accounts"].append({
            "id": account_id,
            "alias": _safe_alias(alias or summary.get("account") or "Codex account"),
            "account": summary.get("account", ""),
            "auth_mode": summary.get("auth_mode", ""),
            "last_refresh": summary.get("last_refresh", ""),
            "hash": account_hash,
            "created_at": now,
            "updated_at": now,
        })

    os.makedirs(os.path.dirname(_account_file(account_id)), exist_ok=True)
    _write_json_object(_account_file(account_id), data)
    _write_index(index)
    return list_accounts()


def switch_account(account_id):
    account_id = str(account_id or "").strip()
    if not account_id:
        raise ValueError("account_id is required.")
    source = _account_file(account_id)
    data = _read_json_object(source)
    if not data or not _token_present(data):
        raise ValueError("Selected account auth file is missing or invalid.")
    index = _read_index()
    record = next((item for item in index["accounts"] if str(item.get("id") or "") == account_id), None)
    summary = _auth_summary(data)
    usage = None
    if summary.get("has_chatgpt_token"):
        try:
            usage = _read_usage_for_auth(source)
            data = _read_json_object(source)
            summary = _auth_summary(data) if data else summary
        except Exception as exc:
            usage = {"ok": False, "message": _usage_error_message(exc), "updated_at": _now()}
    if record is not None:
        record["account"] = summary.get("account", "")
        record["auth_mode"] = summary.get("auth_mode", "")
        record["last_refresh"] = summary.get("last_refresh", "")
        record["hash"] = summary.get("hash", record.get("hash", ""))
        record["updated_at"] = _now()
        if usage is not None:
            record["usage"] = usage
            record["usage_updated_at"] = usage.get("updated_at") or _now()
        _write_index(index)
    backup_path = _backup_file(auth_path())
    _write_json_object(auth_path(), data)
    status = list_accounts()
    status["backup_path"] = backup_path
    return status


def rename_account(account_id, alias):
    account_id = str(account_id or "").strip()
    index = _read_index()
    for item in index["accounts"]:
        if item.get("id") == account_id:
            item["alias"] = _safe_alias(alias)
            item["updated_at"] = _now()
            _write_index(index)
            return list_accounts()
    raise ValueError("Account was not found.")


def delete_account(account_id):
    account_id = str(account_id or "").strip()
    index = _read_index()
    before = len(index["accounts"])
    index["accounts"] = [item for item in index["accounts"] if item.get("id") != account_id]
    if len(index["accounts"]) == before:
        raise ValueError("Account was not found.")
    folder = os.path.dirname(_account_file(account_id))
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    _write_index(index)
    return list_accounts()


def _find_codex_cli():
    explicit = os.environ.get("CODEX_CLI_EXE", "").strip()
    if explicit and os.path.isfile(explicit):
        return explicit
    roots = [
        os.path.join(os.environ.get("LOCALAPPDATA") or "", "OpenAI", "Codex", "bin"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "OpenAI", "Codex", "bin"),
    ]
    candidates = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for folder in os.listdir(root):
            path = os.path.join(root, folder, "codex.exe")
            if os.path.isfile(path):
                candidates.append(path)
    candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    return candidates[0] if candidates else ""


def _rpc_send(proc, payload):
    proc.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    proc.stdin.flush()


def _rpc_stdout_queue(proc):
    q = getattr(proc, "_ai_proxy_stdout_queue", None)
    if q is not None:
        return q
    q = queue.Queue()

    def read_stdout():
        while True:
            line = proc.stdout.readline()
            if not line:
                q.put(None)
                break
            q.put(line)

    thread = threading.Thread(target=read_stdout, daemon=True)
    thread.start()
    proc._ai_proxy_stdout_queue = q
    return q


def _rpc_read_until(proc, response_id, timeout=20):
    deadline = time.time() + timeout
    q = _rpc_stdout_queue(proc)
    while time.time() < deadline:
        remaining = max(0.05, deadline - time.time())
        try:
            line = q.get(timeout=min(0.2, remaining))
        except queue.Empty:
            if proc.poll() is not None:
                break
            continue
        if not line:
            if proc.poll() is not None:
                break
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == response_id:
            if "error" in msg:
                error = msg.get("error") or {}
                raise RuntimeError(str(error.get("message") or error))
            return msg.get("result") or {}
    raise TimeoutError("Timed out waiting for Codex app-server rate limit response.")


def _normalize_usage(payload):
    rate_limits = payload.get("rateLimitsByLimitId", {}).get("codex") if isinstance(payload.get("rateLimitsByLimitId"), dict) else None
    if not isinstance(rate_limits, dict):
        rate_limits = payload.get("rateLimits")
    if not isinstance(rate_limits, dict):
        return {"ok": False, "message": "No Codex rate limit data returned."}

    def window(name):
        value = rate_limits.get(name)
        if not isinstance(value, dict):
            return None
        used = value.get("usedPercent")
        try:
            used = float(used)
        except (TypeError, ValueError):
            used = None
        remaining = None if used is None else max(0, min(100, 100 - used))
        return {
            "used_percent": used,
            "remaining_percent": remaining,
            "window_duration_mins": value.get("windowDurationMins"),
            "resets_at": value.get("resetsAt"),
        }

    return {
        "ok": True,
        "message": "ok",
        "plan_type": rate_limits.get("planType"),
        "rate_limit_reached_type": rate_limits.get("rateLimitReachedType"),
        "primary": window("primary"),
        "secondary": window("secondary"),
        "credits": rate_limits.get("credits") if isinstance(rate_limits.get("credits"), dict) else None,
        "updated_at": _now(),
    }


def _read_usage_for_auth(auth_file):
    codex_cli = _find_codex_cli()
    if not codex_cli:
        raise FileNotFoundError("Codex CLI executable was not found.")
    home = tempfile.mkdtemp(prefix="ai-proxy-codex-usage-")
    proc = None
    try:
        shutil.copy2(auth_file, os.path.join(home, "auth.json"))
        env = os.environ.copy()
        env["CODEX_HOME"] = home
        proc = subprocess.Popen(
            [codex_cli, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _rpc_send(proc, {
            "method": "initialize",
            "id": 1,
            "params": {
                "clientInfo": {
                    "name": "ai_proxy_manager",
                    "title": "AI Proxy Manager",
                    "version": "2.5.1",
                },
                "capabilities": {},
            },
        })
        _rpc_read_until(proc, 1, timeout=15)
        _rpc_send(proc, {"method": "initialized", "params": {}})
        _rpc_send(proc, {"method": "account/read", "id": 2, "params": {"refreshToken": True}})
        _rpc_read_until(proc, 2, timeout=25)
        _rpc_send(proc, {"method": "account/rateLimits/read", "id": 3, "params": None})
        result = _rpc_read_until(proc, 3, timeout=25)
        refreshed = os.path.join(home, "auth.json")
        if os.path.isfile(refreshed):
            refreshed_data = _read_json_object(refreshed)
            if refreshed_data and _token_present(refreshed_data):
                shutil.copy2(refreshed, auth_file)
        return _normalize_usage(result)
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass
        for _ in range(5):
            try:
                shutil.rmtree(home)
                break
            except OSError:
                time.sleep(0.2)
        else:
            try:
                shutil.rmtree(home, ignore_errors=True)
            except Exception:
                pass


def refresh_account_usage(account_id=None):
    index = _read_index()
    ids = {str(account_id)} if account_id else {str(item.get("id")) for item in index["accounts"]}
    now = _now()
    for item in index["accounts"]:
        account_id = str(item.get("id") or "")
        if account_id not in ids:
            continue
        try:
            usage = _read_usage_for_auth(_account_file(account_id))
        except Exception as exc:
            usage = {"ok": False, "message": _usage_error_message(exc), "updated_at": now}
        item["usage"] = usage
        item["usage_updated_at"] = now
    _write_index(index)
    return list_accounts()
