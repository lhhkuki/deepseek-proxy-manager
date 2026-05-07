#!/usr/bin/env python3
"""
DeepSeek Proxy Manager — headless proxy + API server.
GUI is provided by the Electron frontend (frontend/).
"""

import os
import sys
import threading
import time
from proxy.config import (
    CONFIG_PATH, DEFAULT_CONFIG, save_config, load_config,
    is_already_running, LOG_QUEUE,
)
from proxy.server import ProxyServer
from proxy.handler import ProxyHandler


def main():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
    cfg = load_config()
    port = cfg.get("port", 15800)

    if is_already_running(port):
        print(f"Proxy already running on port {port}")
        # Still try to open frontend
        return

    # Start proxy server
    proxy = ProxyServer(ProxyHandler)
    try:
        proxy.start(port)
        print(f"Proxy started on http://127.0.0.1:{port}")
    except Exception as e:
        print(f"Failed to start proxy: {e}")
        sys.exit(1)

    # Start Flask API (for frontend)
    api_port = 15801
    try:
        from api_server import app as flask_app, set_proxy_instance
        set_proxy_instance(proxy)

        def run_api():
            flask_app.run(host="127.0.0.1", port=api_port, debug=False,
                          use_reloader=False)

        t = threading.Thread(target=run_api, daemon=True)
        t.start()
        print(f"API server started on http://127.0.0.1:{api_port}")
    except Exception as e:
        print(f"API server optional, skipped: {e}")

    # Keep running
    print("Proxy running. Close this window to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        proxy.stop()


if __name__ == "__main__":
    main()
