"""REST API for proxy manager UI."""

import json
import os
import sys
import threading
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
CORS(app)

proxy_server = None
_logs_history = []
_logs_lock = threading.Lock()


def set_proxy_instance(proxy):
    """Called by GUI to share the running proxy instance."""
    global proxy_server
    proxy_server = proxy


def _drain_log_queue():
    """Drain new messages from LOG_QUEUE into persistent history."""
    global _logs_history
    while not LOG_QUEUE.empty():
        try:
            msg = LOG_QUEUE.get_nowait()
            with _logs_lock:
                _logs_history.append({
                    "id": str(datetime.now().timestamp()),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "message": msg,
                })
                if len(_logs_history) > 500:
                    _logs_history = _logs_history[-500:]
        except Exception:
            break


@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(load_config())


ALLOWED_CONFIG_KEYS = {"port", "models"}
ALLOWED_MODEL_KEYS = {"id", "name", "enabled", "base_url", "api_key", "reasoning", "upstream_format"}


def _sanitize_config(cfg):
    """Strip unknown fields from config to prevent injection."""
    clean = {}
    for k in ALLOWED_CONFIG_KEYS:
        if k in cfg:
            clean[k] = cfg[k]
    if "models" in clean and isinstance(clean["models"], list):
        clean["models"] = [
            {mk: mv for mk, mv in m.items() if mk in ALLOWED_MODEL_KEYS}
            for m in clean["models"] if isinstance(m, dict)
        ]
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
    # Filter each model to allowed keys (same as _sanitize_config)
    sanitized = [
        {mk: mv for mk, mv in m.items() if mk in ALLOWED_MODEL_KEYS}
        for m in models if isinstance(m, dict)
    ]
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
