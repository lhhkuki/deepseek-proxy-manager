"""REST API for proxy manager UI."""

import json
import os
import sys
import queue
import threading
import itertools
from datetime import datetime
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

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:15801", "file://", "app://"])

proxy_server = None
_logs_history = []
_logs_lock = threading.Lock()
_log_counter = itertools.count()


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
    return jsonify(load_config())


ALLOWED_CONFIG_KEYS = {"port", "models"}
ALLOWED_MODEL_KEYS = {"id", "name", "enabled", "base_url", "api_key", "reasoning", "upstream_format"}

# Block internal/private hosts to prevent SSRF
_BLOCKED_URL_PREFIXES = (
    "http://127.", "http://localhost", "http://10.", "http://172.16.",
    "http://172.17.", "http://172.18.", "http://172.19.", "http://172.20.",
    "http://172.21.", "http://172.22.", "http://172.23.", "http://172.24.",
    "http://172.25.", "http://172.26.", "http://172.27.", "http://172.28.",
    "http://172.29.", "http://172.30.", "http://172.31.", "http://192.168.",
    "http://0.", "ftp://", "file://",
)


def _validate_base_url(url):
    """Reject internal/private URLs to prevent SSRF."""
    if not url:
        return
    lower = url.lower().strip()
    if not lower.startswith("https://"):
        raise ValueError(f"base_url must use HTTPS: {url[:60]}")
    for prefix in _BLOCKED_URL_PREFIXES:
        if lower.startswith(prefix):
            raise ValueError(f"base_url is not allowed: {url[:60]}")


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


@app.route('/api/config', methods=['POST'])
def update_config():
    cfg = request.json
    if not isinstance(cfg, dict):
        return jsonify({"status": "error", "message": "Invalid config format"}), 400
    save_config(_sanitize_config(cfg))
    return jsonify({"status": "ok"})


@app.route('/api/models', methods=['GET'])
def get_models():
    cfg = load_config()
    return jsonify(cfg.get("models", []))


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
    cfg["models"] = sanitized
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


def run_api(port=15801):
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)


if __name__ == "__main__":
    # Start proxy server
    cfg = load_config()
    port = cfg.get("port", 15800)
    proxy = ProxyServer(ProxyHandler)
    try:
        proxy.start(port)
        write_pid_file()
        set_proxy_instance(proxy)
        print(f"Proxy started on port {port}")
    except Exception as e:
        print(f"Proxy start failed: {e}")

    # Start API (blocking)
    run_api()
