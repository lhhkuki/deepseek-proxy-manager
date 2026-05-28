"""REST API for proxy manager UI."""

import json
import os
import sys
import queue
import threading
import itertools
import ipaddress
import socket
from datetime import datetime
from urllib.parse import urlparse
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
    rename_account,
    delete_account,
    refresh_account_usage,
)

CSRF_HEADER = "X-AI-Proxy-Manager"
SENSITIVE_MODEL_KEYS = {"api_key"}

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
    body = request.json if isinstance(request.json, dict) else {}
    try:
        return jsonify({"status": "ok", "accounts": import_current_account(body.get("alias"))})
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


@app.route('/api/codex-accounts/<account_id>', methods=['PATCH'])
def rename_codex_account(account_id):
    body = request.json if isinstance(request.json, dict) else {}
    try:
        return jsonify({"status": "ok", "accounts": rename_account(account_id, body.get("alias"))})
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
