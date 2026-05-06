"""System-tray GUI for managing the proxy."""

import os
import sys
import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime

import pystray
from PIL import Image, ImageDraw

from proxy.config import (
    CONFIG_PATH, load_config, save_config, load_api_key, save_api_key,
    is_autostart_enabled, set_autostart, is_already_running,
    BG_DARK, BG_CARD, BG_INPUT, FG_PRIMARY, FG_SECONDARY, FG_MUTED,
    ACCENT, GREEN, RED, FONT, FONT_MONO, LOG_QUEUE,
)
from proxy.server import ProxyServer
from proxy.handler import ProxyHandler


class ProxyManagerApp:
    def __init__(self):
        self.proxy = ProxyServer(ProxyHandler)
        self.cfg = load_config()
        self.tray = None
        self.window = None
        self.log_lines = []

        self._build_window()
        self._build_tray()

        port = self.cfg.get("port", 15800)
        try:
            self.proxy.start(port)
            self._update_status(True)
        except Exception:
            self._update_status(False)

        self._poll_logs()
        self.window.protocol("WM_DELETE_WINDOW", self._hide_window)

    # ── window ──────────────────────────────────────────────────────

    def _build_window(self):
        self.window = tk.Tk()
        self.window.title("DeepSeek 代理管理器")
        self.window.geometry("520x580")
        self.window.resizable(True, True)
        self.window.configure(bg=BG_DARK)

        self._setup_icon()
        self._setup_styles()
        self._build_status_card()
        self._build_tab_bar()

    def _setup_icon(self):
        try:
            ico_path = os.path.join(os.path.dirname(CONFIG_PATH),
                                    "proxy_icon.ico")
            icon_img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            icon_draw = ImageDraw.Draw(icon_img)
            icon_draw.ellipse([6, 6, 58, 58], fill=ACCENT)
            icon_draw.ellipse([18, 18, 46, 46], fill="#ffffff")
            icon_img.save(ico_path, format="ICO", sizes=[(64, 64)])
            self.window.iconbitmap(ico_path)
        except Exception:
            pass

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG_DARK, foreground=FG_PRIMARY,
                        font=(FONT, 10), borderwidth=0,
                        troughcolor=BG_INPUT, fieldbackground=BG_INPUT,
                        insertcolor=FG_PRIMARY)
        style.map(".", foreground=[("disabled", FG_MUTED)])
        style.configure("TFrame", background=BG_DARK)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("TLabel", background=BG_DARK, foreground=FG_PRIMARY,
                        font=(FONT, 10))
        style.configure("Card.TLabel", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 10))
        style.configure("CardSec.TLabel", background=BG_CARD,
                        foreground=FG_SECONDARY, font=(FONT, 9))
        style.configure("CardTitle.TLabel", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 10, "bold"))
        style.configure("Status.TLabel", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 12, "bold"))
        style.configure("StatusSub.TLabel", background=BG_CARD,
                        foreground=FG_SECONDARY, font=(FONT, 9))
        style.configure("TButton", background=ACCENT, foreground="#ffffff",
                        font=(FONT, 10), padding=(12, 6), borderwidth=0)
        style.map("TButton", background=[("active", "#5a9ee6"),
                                         ("pressed", "#3a7bc8")],
                  foreground=[("disabled", FG_MUTED)])
        style.configure("Stop.TButton", background=RED,
                        foreground="#ffffff")
        style.map("Stop.TButton", background=[("active", "#f5a0b5"),
                                              ("pressed", "#e0708a")])
        style.configure("TEntry", fieldbackground=BG_INPUT,
                        foreground=FG_PRIMARY, insertcolor=FG_PRIMARY,
                        borderwidth=1, padding=6)
        style.map("TEntry", fieldbackground=[("focus", "#d8e8f8")])
        style.configure("Active.TLabel", foreground=GREEN,
                        font=(FONT, 10, "bold"))
        style.configure("Inactive.TButton", background=BG_INPUT,
                        foreground=FG_SECONDARY, font=(FONT, 9),
                        padding=(10, 5), borderwidth=0)
        style.map("Inactive.TButton",
                  background=[("active", ACCENT)],
                  foreground=[("active", "#ffffff")])
        style.configure("ModelName.TLabel", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 12))
        style.configure("ModelId.TLabel", background=BG_CARD,
                        foreground=FG_SECONDARY, font=(FONT, 9))
        style.configure("TCheckbutton", background=BG_CARD,
                        foreground=FG_PRIMARY, font=(FONT, 10),
                        indicatorcolor=BG_INPUT, indicatorrelief="flat")
        style.map("TCheckbutton", background=[("active", BG_CARD)],
                  indicatorcolor=[("selected", ACCENT)])
        style.configure("Tab.TButton", background=BG_INPUT,
                        foreground=FG_SECONDARY, font=(FONT, 10),
                        padding=(12, 8), borderwidth=0)
        style.map("Tab.TButton", background=[("active", BG_INPUT)],
                  foreground=[("active", FG_PRIMARY)])
        style.configure("TabSel.TButton", background=ACCENT,
                        foreground="#ffffff", font=(FONT, 11, "bold"),
                        padding=(12, 14), borderwidth=0)
        style.map("TabSel.TButton", background=[("active", ACCENT)],
                  foreground=[("active", "#ffffff")])

    def _build_status_card(self):
        card = ttk.Frame(self.window, style="Card.TFrame", padding=16)
        card.pack(fill=tk.X, padx=16, pady=(16, 8))

        left = ttk.Frame(card, style="Card.TFrame")
        left.pack(side=tk.LEFT, fill=tk.X, expand=True)

        dot_row = ttk.Frame(left, style="Card.TFrame")
        dot_row.pack(anchor=tk.W)

        self.status_dot_label = tk.Label(dot_row, text="●",
                                         font=(FONT, 20), bg=BG_CARD,
                                         fg=RED, bd=0,
                                         highlightthickness=0)
        self.status_dot_label.pack(side=tk.LEFT, padx=(0, 8))

        self.status_label = ttk.Label(dot_row, text="已停止",
                                      style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT)

        self.status_sub = ttk.Label(left, text="",
                                    style="StatusSub.TLabel")
        self.status_sub.pack(anchor=tk.W, pady=(4, 0))

        self.toggle_btn = ttk.Button(card, text="启动",
                                     command=self._toggle)
        self.toggle_btn.pack(side=tk.RIGHT)

    def _build_tab_bar(self):
        tab_bar = ttk.Frame(self.window)
        tab_bar.pack(fill=tk.X, padx=16, pady=(0, 0))
        tab_bar.columnconfigure(0, weight=1, uniform="tab")
        tab_bar.columnconfigure(1, weight=1, uniform="tab")
        tab_bar.columnconfigure(2, weight=1, uniform="tab")

        self._tab_buttons = []
        self._tab_frames = []

        for i, name in enumerate(["设置", "模型", "日志"]):
            btn = ttk.Button(
                tab_bar, text=name,
                style="TabSel.TButton" if i == 0 else "Tab.TButton",
                command=lambda idx=i: self._switch_tab(idx))
            btn.grid(row=0, column=i, sticky="nsew")
            self._tab_buttons.append(btn)

        content = ttk.Frame(self.window)
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        self._build_settings_tab(content)
        self._build_models_tab(content)
        self._build_log_tab(content)

        self._tab_frames = [
            getattr(self, f) for f in
            ("_settings_frame", "_models_frame", "_log_frame")]
        for f in self._tab_frames:
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._switch_tab(0)

    def _build_settings_tab(self, parent):
        frame = ttk.Frame(parent)
        self._settings_frame = frame

        conn_card = ttk.Frame(frame, style="Card.TFrame", padding=16)
        conn_card.pack(fill=tk.X, padx=8, pady=(12, 6))
        conn_card.columnconfigure(1, weight=1)

        ttk.Label(conn_card, text="连接设置",
                  style="CardTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(conn_card, text="端口:", style="Card.TLabel").grid(
            row=1, column=0, sticky=tk.W, pady=4)
        self.port_var = tk.IntVar(value=self.cfg.get("port", 15800))
        ttk.Entry(conn_card, textvariable=self.port_var, width=10).grid(
            row=1, column=1, sticky=tk.W, pady=4)

        ttk.Label(conn_card, text="API 地址:", style="Card.TLabel").grid(
            row=2, column=0, sticky=tk.W, pady=4)
        self.base_var = tk.StringVar(
            value=self.cfg.get("deepseek_base", "https://api.deepseek.com"))
        ttk.Entry(conn_card, textvariable=self.base_var, width=42).grid(
            row=2, column=1, sticky=tk.W, pady=4)

        ttk.Label(conn_card, text="API 密钥:", style="Card.TLabel").grid(
            row=3, column=0, sticky=tk.W, pady=4)
        key_frame = ttk.Frame(conn_card, style="Card.TFrame")
        key_frame.grid(row=3, column=1, sticky=tk.EW, pady=4)
        self.key_var = tk.StringVar(value=load_api_key())
        self.key_entry = ttk.Entry(key_frame, textvariable=self.key_var,
                                   width=32, show="*")
        self.key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            key_frame, text="显示", variable=self.show_key,
            command=self._toggle_key_visibility).pack(
            side=tk.LEFT, padx=(8, 0))

        start_card = ttk.Frame(frame, style="Card.TFrame", padding=16)
        start_card.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(start_card, text="启动项",
                  style="CardTitle.TLabel").pack(
            anchor=tk.W, pady=(0, 8))
        self.autostart_var = tk.BooleanVar(value=is_autostart_enabled())
        ttk.Checkbutton(start_card, text="开机自动启动代理",
                        variable=self.autostart_var,
                        command=self._toggle_autostart).pack(anchor=tk.W)
        ttk.Label(start_card, text="在 Windows 启动文件夹中创建快捷方式",
                  style="CardSec.TLabel").pack(anchor=tk.W, pady=(2, 0))

        save_frame = ttk.Frame(frame)
        save_frame.pack(fill=tk.X, padx=8, pady=(8, 8))
        ttk.Button(save_frame, text="保存设置",
                   command=self._save_settings).pack(side=tk.RIGHT)

    def _build_models_tab(self, parent):
        frame = ttk.Frame(parent)
        self._models_frame = frame

        self.models_container = ttk.Frame(frame)
        self.models_container.pack(fill=tk.BOTH, expand=True,
                                   padx=8, pady=12)
        self._refresh_models_list()

        add_frame = ttk.Frame(frame)
        add_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(add_frame, text="添加模型",
                   command=self._add_model).pack(side=tk.RIGHT)

    def _build_log_tab(self, parent):
        frame = ttk.Frame(parent)
        self._log_frame = frame

        log_card = ttk.Frame(frame, style="Card.TFrame", padding=8)
        log_card.pack(fill=tk.BOTH, expand=True, padx=8, pady=12)

        self.log_text = scrolledtext.ScrolledText(
            log_card, height=18, state=tk.DISABLED,
            font=(FONT_MONO, 9), bg=BG_INPUT, fg=FG_PRIMARY,
            insertbackground=FG_PRIMARY, selectbackground=ACCENT,
            bd=0, highlightthickness=0, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(log_card, style="Card.TFrame")
        btn_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_frame, text="清空",
                   command=self._clear_log).pack(side=tk.RIGHT)

    # ── tray ────────────────────────────────────────────────────────

    def _build_tray(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill=ACCENT)
        self.tray = pystray.Icon(
            "deepseek_proxy", img, "DeepSeek Proxy",
            menu=pystray.Menu(
                pystray.MenuItem("显示", self._show_window, default=True),
                pystray.MenuItem("启动 / 停止", self._toggle),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._quit),
            ))

    # ── actions ─────────────────────────────────────────────────────

    def _toggle(self):
        if self.proxy.is_running():
            self.proxy.stop()
            self._update_status(False)
        else:
            port = self.port_var.get()
            try:
                self.proxy.start(port)
                self._update_status(True)
            except Exception as e:
                messagebox.showerror("错误", f"启动失败: {e}")

    def _update_status(self, running):
        if running:
            self.status_dot_label.config(fg=GREEN)
            self.status_label.config(text="代理运行中")
            self.status_sub.config(
                text=f"监听地址 127.0.0.1:{self.port_var.get()}")
            self.toggle_btn.config(text="停止", style="Stop.TButton")
        else:
            self.status_dot_label.config(fg=RED)
            self.status_label.config(text="代理已停止")
            self.status_sub.config(text="")
            self.toggle_btn.config(text="启动", style="TButton")

    def _save_settings(self):
        port = self.port_var.get()
        base = self.base_var.get().rstrip("/")
        key = self.key_var.get()
        self.cfg["port"] = port
        self.cfg["deepseek_base"] = base
        save_config(self.cfg)
        save_api_key(key)
        messagebox.showinfo(
            "已保存", "设置已保存！\n重启代理以应用新的端口/API地址。")

    def _toggle_key_visibility(self):
        self.key_entry.config(show="" if self.show_key.get() else "*")

    def _toggle_autostart(self):
        set_autostart(self.autostart_var.get())

    def _switch_tab(self, idx):
        for i, btn in enumerate(self._tab_buttons):
            if i == idx:
                btn.config(style="TabSel.TButton")
                self._tab_frames[i].lift()
            else:
                btn.config(style="Tab.TButton")

    def _refresh_models_list(self):
        for w in self.models_container.winfo_children():
            w.destroy()
        models = self.cfg.get("models", [])
        for i, m in enumerate(models):
            enabled = m.get("enabled", True)
            row = ttk.Frame(self.models_container, style="Card.TFrame",
                            padding=12)
            row.pack(fill=tk.X, pady=(0, 6))

            info = ttk.Frame(row, style="Card.TFrame")
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(info, text=m.get("name", m["id"]),
                      style="ModelName.TLabel").pack(anchor=tk.W)
            ttk.Label(info, text=m["id"],
                      style="ModelId.TLabel").pack(anchor=tk.W)

            if enabled:
                lbl = ttk.Label(row, text="● 使用中",
                                style="Active.TLabel")
                lbl.pack(side=tk.RIGHT, padx=(8, 0))
            else:
                btn = ttk.Button(
                    row, text="启用", style="Inactive.TButton",
                    command=lambda idx=i: self._activate_model(idx))
                btn.pack(side=tk.RIGHT, padx=(8, 0))

    def _activate_model(self, idx):
        models = self.cfg.get("models", [])
        for i, m in enumerate(models):
            m["enabled"] = (i == idx)
        self.cfg["models"] = models
        save_config(self.cfg)
        self._refresh_models_list()

    def _add_model(self):
        dlg = tk.Toplevel(self.window)
        dlg.title("添加模型")
        dlg.geometry("340x200")
        dlg.configure(bg=BG_DARK)
        dlg.transient(self.window)
        dlg.grab_set()

        card = ttk.Frame(dlg, style="Card.TFrame", padding=16)
        card.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        ttk.Label(card, text="模型 ID:", style="Card.TLabel").grid(
            row=0, column=0, sticky=tk.W, pady=6)
        id_var = tk.StringVar()
        ttk.Entry(card, textvariable=id_var, width=25).grid(
            row=0, column=1, padx=(8, 0), pady=6)

        ttk.Label(card, text="显示名称:", style="Card.TLabel").grid(
            row=1, column=0, sticky=tk.W, pady=6)
        name_var = tk.StringVar()
        ttk.Entry(card, textvariable=name_var, width=25).grid(
            row=1, column=1, padx=(8, 0), pady=6)

        def _save():
            mid = id_var.get().strip()
            if mid:
                self.cfg.setdefault("models", []).append({
                    "id": mid,
                    "name": name_var.get().strip() or mid,
                    "enabled": True,
                })
                save_config(self.cfg)
                self._refresh_models_list()
            dlg.destroy()

        ttk.Button(card, text="添加", command=_save).grid(
            row=2, column=0, columnspan=2, pady=(16, 0))

    def _clear_log(self):
        self.log_lines = []
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _poll_logs(self):
        while not LOG_QUEUE.empty():
            try:
                msg = LOG_QUEUE.get_nowait()
                ts = datetime.now().strftime("%H:%M:%S")
                self.log_lines.append(f"[{ts}] {msg}")
            except queue.Empty:
                break
        if len(self.log_lines) > 500:
            self.log_lines = self.log_lines[-500:]

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert("1.0", "\n".join(self.log_lines))
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.window.after(1000, self._poll_logs)

    def _show_window(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def _hide_window(self):
        self.window.withdraw()

    def _quit(self):
        if self.proxy.is_running():
            self.proxy.stop()
        if self.tray:
            self.tray.stop()
        self.window.destroy()

    def run(self):
        if self.tray:
            threading.Thread(target=self.tray.run, daemon=True).start()
        self.window.mainloop()
