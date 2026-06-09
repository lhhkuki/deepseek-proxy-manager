"""REST API for proxy manager UI."""

import json
import os
import sys
import queue
import threading
import itertools
import ipaddress
import socket
import shutil
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from flask import Flask, jsonify, request
from flask_cors import CORS

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proxy.config import (
    load_config, save_config, get_active_model_config,
    is_autostart_enabled, set_autostart,
    LOG_QUEUE, _REASONING_CACHE, _REASONING_LOCK,
    write_pid_file, remove_pid_file,
)
from proxy.server import ProxyServer
from proxy.handler import ProxyHandler
from proxy.codex_config import (
    codex_config_status,
    apply_proxy_config,
    apply_pure_api_config,
    apply_official_config,
    sync_conversation_history,
    auth_path,
    codex_home,
    config_path,
)
from proxy.codex_launcher import (
    launcher_status,
    launch_and_inject,
    inject_unlock_script,
    stop_launched_codex,
)
from proxy.codex_accounts import (
    list_accounts,
    import_current_account,
    switch_account,
    delete_account,
    refresh_account_usage,
)

CSRF_HEADER = "X-AI-Proxy-Manager"
SENSITIVE_MODEL_KEYS = {"api_key"}
APP_VERSION = "3.0.0"

MODEL_PRESETS = [
    {
        "id": "deepseek-chat",
        "name": "DeepSeek Chat",
        "base_url": "https://api.deepseek.com",
        "upstream_format": "openai",
        "reasoning": False,
        "supports_images": False,
        "description": "DeepSeek 通用聊天模型",
    },
    {
        "id": "deepseek-reasoner",
        "name": "DeepSeek Reasoner",
        "base_url": "https://api.deepseek.com",
        "upstream_format": "openai",
        "reasoning": True,
        "supports_images": False,
        "description": "DeepSeek 推理模型",
    },
    {
        "id": "kimi-k2.6",
        "name": "Kimi Code",
        "base_url": "https://api.kimi.com/coding/v1",
        "upstream_format": "anthropic",
        "reasoning": False,
        "supports_images": True,
        "description": "Kimi Code / Moonshot 编码接口",
    },
    {
        "id": "moonshot-v1-128k",
        "name": "Moonshot 128K",
        "base_url": "https://api.moonshot.cn/v1",
        "upstream_format": "openai",
        "reasoning": False,
        "supports_images": False,
        "description": "Moonshot OpenAI 兼容接口",
    },
    {
        "id": "openrouter/auto",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "upstream_format": "openai",
        "reasoning": False,
        "supports_images": True,
        "description": "OpenRouter 聚合模型入口",
    },
    {
        "id": "qwen-plus",
        "name": "阿里百炼 Qwen Plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "upstream_format": "openai",
        "reasoning": False,
        "supports_images": False,
        "description": "阿里百炼 OpenAI 兼容接口",
    },
    {
        "id": "doubao-seed-1-6",
        "name": "火山方舟 Doubao",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "upstream_format": "openai",
        "reasoning": False,
        "supports_images": False,
        "description": "火山方舟 OpenAI 兼容接口",
    },
]

app = Flask(__name__)
CORS(
    app,
    origins=["http://localhost:5173", "http://127.0.0.1:15801", "file://", "app://"],
    allow_headers=["Content-Type", CSRF_HEADER],
)

proxy_server = None
_logs_history = []
_logs_lock = threading.Lock()
_log_counter = itertools.count()


@app.before_request
def _require_local_app_header_for_mutations():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if request.path.startswith("/api/") and request.headers.get(CSRF_HEADER) != "1":
        return jsonify({"status": "error", "message": "Missing local app request header"}), 403
    return None


def set_proxy_instance(proxy):
    """Called by GUI to share the running proxy instance."""
    global proxy_server
    proxy_server = proxy


def _drain_log_queue():
    """Drain new messages from LOG_QUEUE into persistent history."""
    global _logs_history
    # Drain into local buffer first to avoid holding lock per-message
    batch = []
    while True:
        try:
            batch.append(LOG_QUEUE.get_nowait())
        except queue.Empty:
            break
    if batch:
        with _logs_lock:
            now = datetime.now().strftime("%H:%M:%S")
            for msg in batch:
                _logs_history.append({
                    "id": str(next(_log_counter)),
                    "timestamp": now,
                    "message": msg,
                })
            if len(_logs_history) > 500:
                _logs_history = _logs_history[-500:]


@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(_redact_config(load_config()))


ALLOWED_CONFIG_KEYS = {"port", "models"}
ALLOWED_MODEL_KEYS = {"id", "name", "enabled", "base_url", "api_key", "reasoning", "upstream_format", "supports_images"}

def _validate_base_url(url):
    """Reject internal/private URLs to prevent SSRF."""
    if not url:
        return
    raw = str(url).strip()
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"base_url must use HTTPS: {raw[:60]}")
    host = (parsed.hostname or "").strip().rstrip(".").lower()
    if not host:
        raise ValueError(f"base_url host is required: {raw[:60]}")
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError(f"base_url is not allowed: {raw[:60]}")

    def _is_blocked_ip(value):
        ip = ipaddress.ip_address(value)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_unspecified
            or ip.is_reserved
            or ip.is_multicast
        )

    try:
        if _is_blocked_ip(host):
            raise ValueError(f"base_url is not allowed: {raw[:60]}")
        return
    except ValueError as exc:
        if "base_url is not allowed" in str(exc):
            raise

    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return
    for info in infos:
        address = info[4][0]
        if _is_blocked_ip(address):
            raise ValueError(f"base_url resolves to a private address: {raw[:60]}")


def _redact_model(model):
    if not isinstance(model, dict):
        return model
    redacted = dict(model)
    for key in SENSITIVE_MODEL_KEYS:
        if redacted.get(key):
            redacted[key] = ""
    redacted["has_api_key"] = bool(model.get("api_key"))
    return redacted


def _redact_config(cfg):
    if not isinstance(cfg, dict):
        return cfg
    redacted = dict(cfg)
    models = redacted.get("models")
    if isinstance(models, list):
        redacted["models"] = [_redact_model(m) for m in models]
    return redacted


def _sanitize_config(cfg):
    """Strip unknown fields from config to prevent injection."""
    clean = {}
    for k in ALLOWED_CONFIG_KEYS:
        if k in cfg:
            clean[k] = cfg[k]
    if "models" in clean and isinstance(clean["models"], list):
        sanitized = []
        for m in clean["models"]:
            if not isinstance(m, dict):
                continue
            sm = {mk: mv for mk, mv in m.items() if mk in ALLOWED_MODEL_KEYS}
            _validate_base_url(sm.get("base_url", ""))
            sanitized.append(sm)
        clean["models"] = sanitized
    return clean


def _merge_existing_model_secrets(models):
    existing = {
        str(m.get("id") or ""): m
        for m in load_config().get("models", [])
        if isinstance(m, dict)
    }
    for model in models:
        model_id = str(model.get("id") or "")
        old_model = existing.get(model_id)
        if old_model and not model.get("api_key") and old_model.get("api_key"):
            model["api_key"] = old_model.get("api_key")
    return models


@app.route('/api/config', methods=['POST'])
def update_config():
    cfg = request.json
    if not isinstance(cfg, dict):
        return jsonify({"status": "error", "message": "Invalid config format"}), 400
    try:
        clean = _sanitize_config(cfg)
        if isinstance(clean.get("models"), list):
            clean["models"] = _merge_existing_model_secrets(clean["models"])
        save_config(clean)
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    return jsonify({"status": "ok"})


@app.route('/api/models', methods=['GET'])
def get_models():
    cfg = load_config()
    return jsonify([_redact_model(m) for m in cfg.get("models", [])])


@app.route('/api/models', methods=['POST'])
def update_models():
    models = request.json
    if not isinstance(models, list):
        return jsonify({"status": "error", "message": "Invalid models format"}), 400
    sanitized = []
    for m in models:
        if not isinstance(m, dict):
            continue
        sm = {mk: mv for mk, mv in m.items() if mk in ALLOWED_MODEL_KEYS}
        try:
            _validate_base_url(sm.get("base_url", ""))
        except ValueError as e:
            return jsonify({"status": "error", "message": str(e)}), 400
        sanitized.append(sm)
    cfg = load_config()
    cfg["models"] = _merge_existing_model_secrets(sanitized)
    save_config(cfg)
    return jsonify({"status": "ok"})


@app.route('/api/models/<int:idx>/enable', methods=['POST'])
def enable_model(idx):
    cfg = load_config()
    models = cfg.get("models", [])
    for i, m in enumerate(models):
        m["enabled"] = (i == idx)
    cfg["models"] = models
    save_config(cfg)
    return jsonify({"status": "ok"})


@app.route('/api/models/<int:idx>', methods=['DELETE'])
def delete_model(idx):
    cfg = load_config()
    models = cfg.get("models", [])
    if 0 <= idx < len(models):
        models.pop(idx)
        if models and not any(m.get("enabled", False) for m in models):
            models[0]["enabled"] = True
        cfg["models"] = models
        save_config(cfg)
    return jsonify({"status": "ok"})


@app.route('/api/logs', methods=['GET'])
def get_logs():
    _drain_log_queue()
    with _logs_lock:
        return jsonify(list(_logs_history))


@app.route('/api/status', methods=['GET'])
def get_status():
    global proxy_server
    return jsonify({
        "running": proxy_server.is_running() if proxy_server else False,
        "autostart": is_autostart_enabled(),
    })


@app.route('/api/model-presets', methods=['GET'])
def get_model_presets():
    return jsonify(MODEL_PRESETS)


def _diagnostic_item(key, label, ok, detail="", action=""):
    return {
        "key": key,
        "label": label,
        "ok": bool(ok),
        "detail": str(detail or ""),
        "action": str(action or ""),
    }


@app.route('/api/diagnostics', methods=['GET'])
def get_diagnostics():
    cfg = load_config()
    active_model = get_active_model_config()
    codex = codex_config_status()
    launcher = launcher_status()
    accounts = list_accounts()
    running = proxy_server.is_running() if proxy_server else False
    recent_errors = [
        item for item in list(_logs_history)[-80:]
        if "error" in str(item.get("message", "")).lower()
        or "failed" in str(item.get("message", "")).lower()
        or "fatal" in str(item.get("message", "")).lower()
    ][-8:]
    checks = [
        _diagnostic_item(
            "proxy",
            "本地代理",
            running,
            f"监听端口 {cfg.get('port', 15800)}" if running else "代理未启动",
            "点击右上角启动代理" if not running else "",
        ),
        _diagnostic_item(
            "model",
            "当前模型",
            bool(active_model and active_model.get("api_key")),
            (active_model or {}).get("id") or "未配置模型",
            "在模型页添加 API Key" if not (active_model and active_model.get("api_key")) else "",
        ),
        _diagnostic_item(
            "codex_config",
            "Codex 配置",
            codex.get("mode") in ("official", "proxy", "pure_api"),
            f"模式：{codex.get('mode') or 'unknown'}",
        ),
        _diagnostic_item(
            "codex_auth",
            "Codex 认证",
            bool(codex.get("auth", {}).get("authenticated") or codex.get("api_auth", {}).get("authenticated")),
            codex.get("auth", {}).get("account") or codex.get("api_auth", {}).get("message") or "未检测到认证",
            "在 Codex 登录或启用纯 API" if not (codex.get("auth", {}).get("authenticated") or codex.get("api_auth", {}).get("authenticated")) else "",
        ),
        _diagnostic_item(
            "launcher",
            "Codex 启动器",
            bool(launcher.get("codex_exe")),
            launcher.get("codex_exe") or "未找到 Codex 程序",
            "安装 Codex Desktop 或设置 CODEX_APP_EXE" if not launcher.get("codex_exe") else "",
        ),
        _diagnostic_item(
            "accounts",
            "账号保险箱",
            len(accounts.get("accounts", [])) > 0,
            f"已保存 {len(accounts.get('accounts', []))} 个账号",
            "在账号页保存当前 Codex 账号" if not accounts.get("accounts") else "",
        ),
    ]
    return jsonify({
        "version": APP_VERSION,
        "status": {"running": running, "autostart": is_autostart_enabled()},
        "active_model": _redact_model(active_model or {}),
        "codex": codex,
        "launcher": launcher,
        "accounts": accounts,
        "checks": checks,
        "recent_errors": recent_errors,
    })


def _parse_version(value):
    return [
        int(part)
        for part in str(value or "").lstrip("v").split(".")
        if part.isdigit()
    ]


@app.route('/api/releases/latest', methods=['GET'])
def get_latest_release():
    url = "https://api.github.com/repos/lhhkuki/deepseek-proxy-manager/releases/latest"
    try:
        req = Request(url, headers={"User-Agent": "AI-Proxy-Manager"})
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read(1024 * 1024).decode("utf-8", errors="replace"))
        tag = str(data.get("tag_name") or "")
        return jsonify({
            "ok": True,
            "current_version": APP_VERSION,
            "latest_version": tag.lstrip("v"),
            "update_available": _parse_version(tag) > _parse_version(APP_VERSION),
            "url": data.get("html_url", ""),
            "name": data.get("name", ""),
            "published_at": data.get("published_at", ""),
        })
    except Exception as e:
        return jsonify({
            "ok": False,
            "current_version": APP_VERSION,
            "latest_version": "",
            "update_available": False,
            "url": "",
            "message": str(e),
        })


def _backup_root():
    return os.path.join(codex_home(), "backups_proxy_manager")


def _safe_backup_path(path):
    root = os.path.abspath(_backup_root())
    candidate = os.path.abspath(str(path or ""))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise ValueError("Invalid backup path.")
    except ValueError as exc:
        raise ValueError("Invalid backup path.") from exc
    if not os.path.isfile(candidate):
        raise ValueError("Backup file was not found.")
    return candidate


def _backup_type(path):
    name = os.path.basename(path)
    if name.startswith("config.toml."):
        return "config"
    return ""


def _is_legacy_auth_backup(path):
    name = os.path.basename(path)
    return name.startswith("auth.json.") and name.endswith(".bak")


def _prune_backup_items(items, kind, keep=20):
    typed = [item for item in items if item["type"] == kind]
    typed.sort(key=lambda item: item["updated_at"], reverse=True)
    keep_paths = {item["path"] for item in typed[:keep]}
    for item in typed[keep:]:
        try:
            os.remove(item["path"])
        except OSError:
            pass
    return [item for item in items if item["type"] != kind or item["path"] in keep_paths]


@app.route('/api/backups', methods=['GET'])
def list_backups():
    root = _backup_root()
    items = []
    if os.path.isdir(root):
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                if _is_legacy_auth_backup(full):
                    try:
                        os.remove(full)
                    except OSError:
                        pass
                    continue
                kind = _backup_type(full)
                if not kind:
                    continue
                stat = os.stat(full)
                items.append({
                    "path": full,
                    "name": filename,
                    "type": kind,
                    "size": stat.st_size,
                    "updated_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
    items = _prune_backup_items(items, "config", 20)
    items.sort(key=lambda item: item["updated_at"], reverse=True)
    return jsonify({"root": root, "items": items})


@app.route('/api/backups/restore', methods=['POST'])
def restore_backup():
    body = request.json if isinstance(request.json, dict) else {}
    source = _safe_backup_path(body.get("path"))
    kind = _backup_type(source)
    if kind == "config":
        target = config_path()
    else:
        return jsonify({"status": "error", "message": "Unsupported backup type"}), 400
    current_backup = ""
    if os.path.exists(target):
        current_backup = shutil.copy2(target, target + ".restore-bak")
    shutil.copy2(source, target)
    return jsonify({
        "status": "ok",
        "restored": target,
        "source": source,
        "current_backup": current_backup or "",
    })


@app.route('/api/proxy/start', methods=['POST'])
def start_proxy():
    global proxy_server
    if not proxy_server:
        return jsonify({"status": "error", "message": "proxy instance not ready"}), 503
    cfg = load_config()
    port = cfg.get("port", 15800)
    try:
        proxy_server.start(port)
        write_pid_file()
        return jsonify({"status": "ok", "port": port})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/proxy/stop', methods=['POST'])
def stop_proxy():
    global proxy_server
    if proxy_server:
        proxy_server.stop()
        remove_pid_file()
    return jsonify({"status": "ok"})


@app.route('/api/autostart', methods=['POST'])
def toggle_autostart():
    if not isinstance(request.json, dict):
        return jsonify({"status": "error", "message": "Invalid request"}), 400
    enabled = request.json.get("enabled", False)
    set_autostart(enabled)
    return jsonify({"status": "ok"})


@app.route('/api/codex-config/status', methods=['GET'])
def get_codex_config_status():
    return jsonify(codex_config_status())


@app.route('/api/codex-config/proxy', methods=['POST'])
def use_proxy_codex_config():
    body = request.json if isinstance(request.json, dict) else {}
    cfg = load_config()
    try:
        status = apply_proxy_config(
            port=body.get("port") or cfg.get("port", 15800),
            model=body.get("model"),
        )
        return jsonify({"status": "ok", "codex": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/codex-config/pure-api', methods=['POST'])
def use_pure_api_codex_config():
    body = request.json if isinstance(request.json, dict) else {}
    cfg = load_config()
    try:
        status = apply_pure_api_config(
            port=body.get("port") or cfg.get("port", 15800),
            model=body.get("model"),
        )
        return jsonify({"status": "ok", "codex": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/codex-config/official', methods=['POST'])
def use_official_codex_config():
    try:
        status = apply_official_config()
        return jsonify({"status": "ok", "codex": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/codex-config/sync-conversations', methods=['POST'])
def sync_codex_conversations():
    body = request.json if isinstance(request.json, dict) else {}
    try:
        sync = sync_conversation_history(body.get("mode"))
        status = codex_config_status()
        status["conversation_sync"] = sync
        return jsonify({"status": "ok", "codex": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "codex": codex_config_status()}), 400


@app.route('/api/codex-launcher/status', methods=['GET'])
def get_codex_launcher_status():
    return jsonify(launcher_status())


@app.route('/api/codex-launcher/launch', methods=['POST'])
def launch_codex_with_unlocks():
    body = request.json if isinstance(request.json, dict) else {}
    try:
        return jsonify({
            "status": "ok",
            "launcher": launch_and_inject(terminate_existing=bool(body.get("terminate_existing"))),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "launcher": launcher_status()}), 400


@app.route('/api/codex-launcher/stop', methods=['POST'])
def stop_codex_processes():
    try:
        killed = stop_launched_codex()
        status = launcher_status()
        status["killed"] = killed
        return jsonify({"status": "ok", "launcher": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "launcher": launcher_status()}), 400


@app.route('/api/codex-launcher/inject', methods=['POST'])
def inject_codex_unlocks():
    try:
        inject = inject_unlock_script()
        status = launcher_status()
        status["last_inject"] = inject
        return jsonify({"status": "ok", "launcher": status})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "launcher": launcher_status()}), 400


@app.route('/api/codex-accounts', methods=['GET'])
def get_codex_accounts():
    return jsonify(list_accounts())


@app.route('/api/codex-accounts/import-current', methods=['POST'])
def import_current_codex_account():
    try:
        return jsonify({"status": "ok", "accounts": import_current_account()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "accounts": list_accounts()}), 400


@app.route('/api/codex-accounts/refresh-usage', methods=['POST'])
def refresh_codex_account_usage():
    body = request.json if isinstance(request.json, dict) else {}
    account_id = body.get("account_id")
    try:
        return jsonify({"status": "ok", "accounts": refresh_account_usage(account_id)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "accounts": list_accounts()}), 400


@app.route('/api/codex-accounts/<account_id>/switch', methods=['POST'])
def switch_codex_account(account_id):
    try:
        return jsonify({"status": "ok", "accounts": switch_account(account_id)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "accounts": list_accounts()}), 400


@app.route('/api/codex-accounts/<account_id>', methods=['DELETE'])
def delete_codex_account(account_id):
    try:
        return jsonify({"status": "ok", "accounts": delete_account(account_id)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "accounts": list_accounts()}), 400


def run_api(port=15801):
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)


if __name__ == "__main__":
    cfg = load_config()
    port = cfg.get("port", 15800)
    proxy = ProxyServer(ProxyHandler)
    set_proxy_instance(proxy)
    print(f"Proxy configured on port {port}; waiting for /api/proxy/start")
    run_api()
