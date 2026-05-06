#!/usr/bin/env python3
"""
DeepSeek Proxy Manager — system-tray GUI for managing the Codex ↔ DeepSeek proxy.
Supports OpenAI Chat Completions and Anthropic Messages API upstreams.
"""

import os
import tkinter as tk
import tkinter.messagebox as mb

from proxy.config import (
    CONFIG_PATH, DEFAULT_CONFIG, save_config, load_config,
    is_already_running, LOG_QUEUE,
)
from gui.app import ProxyManagerApp


def main():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
    cfg = load_config()
    port = cfg.get("port", 15800)
    if is_already_running(port):
        root = tk.Tk()
        root.withdraw()
        mb.showinfo("DeepSeek 代理管理器",
                    f"代理已在端口 {port} 上运行。\n\n"
                    "请在系统托盘（通知区域）查看图标。")
        root.destroy()
        return
    app = ProxyManagerApp()
    app.run()


if __name__ == "__main__":
    main()
